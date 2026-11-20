import io

import chess
import chess.pgn
import pytest

from app.analysis.analyzer import analyze_record
from app.analysis.engine import Evaluation
from app.analysis.metrics import MATE
from app.game.models import Color, GameRecord, MoveLabel, Termination
from app.game.runner import GameRunner
from tests.conftest import ScriptedPlayer, reply


class FakeEngine:
    """Returns scripted evaluations in order: (score from White's view, best move in UCI)."""

    name = "FakeFish"
    depth = 1

    def __init__(self, script: list[tuple[int, str | None]]) -> None:
        self._script = iter(script)
        self.positions: list[str] = []

    async def evaluate(self, board: chess.Board) -> Evaluation:
        self.positions.append(board.fen())
        score, best = next(self._script)
        return Evaluation(score, chess.Move.from_uci(best) if best else None)


async def play(white_moves, black_moves, **kwargs) -> GameRecord:
    white = ScriptedPlayer("w", [reply(m) for m in white_moves])
    black = ScriptedPlayer("b", [reply(m) for m in black_moves])
    return await GameRunner(white, black, max_illegal_retries=0, **kwargs).play()


async def fools_mate_analyzed() -> tuple[GameRecord, FakeEngine]:
    record = await play(["f3", "g4"], ["e5", "Qh4#"])
    engine = FakeEngine(
        [
            (20, "e2e4"),  # start: best is e4
            (-60, "e7e5"),  # after 1. f3: Black's best is e5
            (-60, "b1c3"),  # after 1... e5: Black's best move keeps the evaluation
            (-(MATE - 1), "d8h4"),  # after 2. g4: Black mates in 1 with Qh4
            # after 2... Qh4#: checkmate, no engine call needed
        ]
    )
    await analyze_record(record, engine, adjudicate_min_cp=300)
    return record, engine


async def test_move_labels_and_losses():
    record, engine = await fools_mate_analyzed()
    moves = record.analysis.moves

    assert [m.label for m in moves] == [
        MoveLabel.INACCURACY,  # 1. f3: +0.20 -> -0.60
        MoveLabel.BEST,  # 1... e5: the engine's choice
        MoveLabel.BLUNDER,  # 2. g4: allows mate in one
        MoveLabel.BEST,  # 2... Qh4#
    ]
    assert moves[0].cp_loss == 80
    assert moves[0].best_san == "e4"
    assert moves[2].cp_loss == 940  # from -0.60 to "lost", capped at -10 pawns
    assert moves[2].best_san == "Nc3"
    assert len(engine.positions) == 4  # the final checkmate wasn't sent to the engine


async def test_player_summary():
    record, _ = await fools_mate_analyzed()
    white, black = record.analysis.white, record.analysis.black

    assert black.accuracy == 100
    assert white.accuracy < 50
    assert white.counts[MoveLabel.BLUNDER] == 1
    assert white.counts[MoveLabel.INACCURACY] == 1
    assert black.counts[MoveLabel.BEST] == 2
    assert white.acpl == (80 + 940) // 2
    assert record.analysis.engine == "FakeFish"
    # Checkmate results are never changed by analysis.
    assert record.termination is Termination.CHECKMATE and record.result == "0-1"


async def test_pgn_has_evals_and_marks():
    record, _ = await fools_mate_analyzed()
    game = chess.pgn.read_game(io.StringIO(record.pgn))
    nodes = list(game.mainline())

    assert game.headers["Annotator"] == "FakeFish (depth 1)"
    assert chess.pgn.NAG_DUBIOUS_MOVE in nodes[0].nags  # f3?!
    assert chess.pgn.NAG_BLUNDER in nodes[2].nags  # g4??
    assert "Blunder. Nc3 was best." in nodes[2].comment
    assert nodes[0].eval().white().score() == -60
    assert nodes[2].eval().white().mate() == -1
    assert nodes[3].eval() is None  # checkmate: nothing left to evaluate


async def test_analysis_survives_json_round_trip():
    record, _ = await fools_mate_analyzed()
    loaded = GameRecord.model_validate_json(record.model_dump_json())
    assert loaded.analysis == record.analysis


@pytest.mark.parametrize(
    ("final_eval", "result", "termination", "winner"),
    [
        (450, "1-0", Termination.ADJUDICATION, Color.WHITE),
        (-(MATE - 4), "0-1", Termination.ADJUDICATION, Color.BLACK),
        (120, "1/2-1/2", Termination.MOVE_LIMIT, None),
    ],
)
async def test_move_limit_adjudication(final_eval, result, termination, winner):
    record = await play(["e4"], ["e5"], max_full_moves=1)
    assert record.termination is Termination.MOVE_LIMIT

    engine = FakeEngine([(20, "e2e4"), (30, "e7e5"), (final_eval, None)])
    await analyze_record(record, engine, adjudicate_min_cp=300)

    assert record.result == result
    assert record.termination is termination
    assert record.winner is winner
    headers = chess.pgn.read_game(io.StringIO(record.pgn)).headers
    assert headers["Result"] == result
    assert headers["Termination"] == termination.value
