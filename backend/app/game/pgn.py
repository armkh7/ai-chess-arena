"""Export a game as PGN, the standard chess game format.

With Stockfish analysis, each move also gets its evaluation (`[%eval ...]`, which Lichess
draws as a graph when you import the game) and a ?!/?/?? mark for inaccuracies, mistakes
and blunders.
"""

import chess
import chess.engine
import chess.pgn

from app.analysis.metrics import MATE, is_mate
from app.game.models import GameRecord, MoveAnalysis, MoveLabel

NAGS = {
    MoveLabel.INACCURACY: chess.pgn.NAG_DUBIOUS_MOVE,  # ?!
    MoveLabel.MISTAKE: chess.pgn.NAG_MISTAKE,  # ?
    MoveLabel.BLUNDER: chess.pgn.NAG_BLUNDER,  # ??
}


def _pov_score(score: int) -> chess.engine.PovScore | None:
    if abs(score) == MATE:  # the game is already over: nothing to evaluate
        return None
    if is_mate(score):
        moves = MATE - abs(score)
        value: chess.engine.Score = chess.engine.Mate(moves if score > 0 else -moves)
    else:
        value = chess.engine.Cp(score)
    return chess.engine.PovScore(value, chess.WHITE)


def _verdict(analysis: MoveAnalysis) -> str | None:
    if analysis.label in NAGS and analysis.best_san:
        return f"{analysis.label.value.capitalize()}. {analysis.best_san} was best."
    return None


def build_pgn(record: GameRecord) -> str:
    board = chess.Board()
    for move in record.moves:
        board.push(chess.Move.from_uci(move.uci))

    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = "AI Chess Arena"
    game.headers["Site"] = "?"  # set to the live URL after deploy
    game.headers["Date"] = record.started_at.strftime("%Y.%m.%d")
    game.headers["White"] = record.white_model
    game.headers["Black"] = record.black_model
    game.headers["Result"] = record.result
    if record.termination:
        game.headers["Termination"] = record.termination.value
    analysis = record.analysis.moves if record.analysis else [None] * len(record.moves)
    if record.analysis:
        game.headers["Annotator"] = f"{record.analysis.engine} (depth {record.analysis.depth})"

    # Comment = the model's reasoning, then the engine's verdict and evaluation.
    for node, move, verdict in zip(game.mainline(), record.moves, analysis, strict=True):
        parts = [move.reasoning, _verdict(verdict) if verdict else None]
        node.comment = " ".join(p for p in parts if p)
        if verdict:
            if verdict.label in NAGS:
                node.nags.add(NAGS[verdict.label])
            if (score := _pov_score(verdict.eval_after)) is not None:
                node.set_eval(score)

    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
    return game.accept(exporter)
