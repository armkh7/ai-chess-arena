"""Analyze a finished game move by move, then settle move-limit games by evaluation.

Every position is evaluated once. A move's quality is the difference between the position
before it (with the best move available) and the position after it (with the move played).
"""

import chess

from app.analysis import metrics
from app.analysis.engine import Evaluation, Evaluator
from app.game.models import (
    Color,
    GameAnalysis,
    GameRecord,
    MoveAnalysis,
    MoveLabel,
    MoveRecord,
    PlayerAnalysis,
    Termination,
)
from app.game.pgn import build_pgn


def _terminal_evaluation(board: chess.Board) -> Evaluation | None:
    """Positions where the game is over need no engine: mate is lost, stalemate is 0."""
    if board.is_checkmate():
        return Evaluation(
            score=-metrics.MATE if board.turn == chess.WHITE else metrics.MATE, best_move=None
        )
    if board.is_stalemate() or board.is_insufficient_material():
        return Evaluation(score=0, best_move=None)
    return None


async def _evaluate(board: chess.Board, evaluator: Evaluator) -> Evaluation:
    return _terminal_evaluation(board) or await evaluator.evaluate(board)


def _analyze_move(
    move: MoveRecord, before: Evaluation, after: Evaluation, best_san: str | None
) -> MoveAnalysis:
    sign = 1 if move.color is Color.WHITE else -1  # flip to the mover's point of view
    mover_before = sign * before.score
    mover_after = sign * after.score
    win_before = metrics.win_percent(mover_before)
    win_after = metrics.win_percent(mover_after)
    best_uci = before.best_move.uci() if before.best_move else None
    return MoveAnalysis(
        ply=move.ply,
        color=move.color,
        eval_before=before.score,
        eval_after=after.score,
        best_san=best_san,
        best_uci=best_uci,
        cp_loss=max(0, metrics.capped(mover_before) - metrics.capped(mover_after)),
        win_before=round(win_before, 1),
        win_after=round(win_after, 1),
        accuracy=metrics.move_accuracy(win_before, win_after),
        label=metrics.move_label(win_before - win_after, is_best=best_uci == move.uci),
    )


def _summarize(moves: list[MoveAnalysis], color: Color) -> PlayerAnalysis:
    mine = [m for m in moves if m.color is color]
    counts = {label: sum(1 for m in mine if m.label is label) for label in MoveLabel}
    return PlayerAnalysis(
        accuracy=metrics.game_accuracy([m.accuracy for m in mine]),
        acpl=round(sum(m.cp_loss for m in mine) / len(mine)) if mine else 0,
        counts=counts,
    )


async def analyze_game(record: GameRecord, evaluator: Evaluator) -> GameAnalysis:
    board = chess.Board()
    before = await _evaluate(board, evaluator)
    analyzed: list[MoveAnalysis] = []
    for move in record.moves:
        best_san = board.san(before.best_move) if before.best_move else None
        board.push(chess.Move.from_uci(move.uci))
        after = await _evaluate(board, evaluator)
        analyzed.append(_analyze_move(move, before, after, best_san))
        before = after

    return GameAnalysis(
        engine=evaluator.name,
        depth=evaluator.depth,
        final_eval=before.score,
        white=_summarize(analyzed, Color.WHITE),
        black=_summarize(analyzed, Color.BLACK),
        moves=analyzed,
    )


def adjudicate(record: GameRecord, min_cp: int) -> None:
    """A game stopped by the move limit goes to the side Stockfish rates ahead by `min_cp`.

    Otherwise it stays a draw. Games that ended any other way are left alone.
    """
    if record.analysis is None or record.termination not in (
        Termination.MOVE_LIMIT,
        Termination.ADJUDICATION,
    ):
        return
    score = record.analysis.final_eval
    if abs(score) >= min_cp:
        record.winner = Color.WHITE if score > 0 else Color.BLACK
        record.result = "1-0" if score > 0 else "0-1"
        record.termination = Termination.ADJUDICATION
    else:
        record.winner = None
        record.result = "1/2-1/2"
        record.termination = Termination.MOVE_LIMIT


async def analyze_record(record: GameRecord, evaluator: Evaluator, adjudicate_min_cp: int) -> None:
    """Analyze, adjudicate if needed, and rebuild the PGN with evaluations. Updates `record`."""
    record.analysis = await analyze_game(record, evaluator)
    adjudicate(record, adjudicate_min_cp)
    record.pgn = build_pgn(record)
