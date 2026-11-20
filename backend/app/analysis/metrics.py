"""Scoring formulas: winning chances, move accuracy, labels.

They follow Lichess's published method, so the numbers mean the same thing chess players
already know from Lichess's "accuracy" and "?!/?/??" marks.

Evaluations are integers in centipawns (100 = one pawn) from White's point of view.
A forced mate is stored as ±(MATE - moves to mate): mate in 3 for White is 99997.
"""

import math
from statistics import fmean, harmonic_mean

from app.game.models import MoveLabel

MATE = 100_000
EVAL_CAP = 1_000  # evaluations beyond ±10 pawns count as "completely winning"

# Drop in the mover's winning chance (percentage points) that makes a move a ...
INACCURACY_DROP = 5.0
MISTAKE_DROP = 10.0
BLUNDER_DROP = 15.0


def is_mate(score: int) -> bool:
    return abs(score) > MATE - 1_000


def capped(score: int) -> int:
    return max(-EVAL_CAP, min(EVAL_CAP, score))


def win_percent(score: int) -> float:
    """Chance of winning (0-100) for a side with this evaluation, Lichess's formula."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * capped(score))) - 1)


def move_accuracy(win_before: float, win_after: float) -> float:
    """0-100: 100 when the move keeps all winning chances, falling fast as they drop."""
    drop = max(0.0, win_before - win_after)
    accuracy = 103.1668 * math.exp(-0.04354 * drop) - 3.1669
    return round(max(0.0, min(100.0, accuracy)), 1)


def move_label(win_drop: float, *, is_best: bool) -> MoveLabel:
    if is_best:
        return MoveLabel.BEST
    if win_drop >= BLUNDER_DROP:
        return MoveLabel.BLUNDER
    if win_drop >= MISTAKE_DROP:
        return MoveLabel.MISTAKE
    if win_drop >= INACCURACY_DROP:
        return MoveLabel.INACCURACY
    return MoveLabel.GOOD


def game_accuracy(accuracies: list[float]) -> float | None:
    """One player's accuracy for the whole game.

    Average of the plain mean and the harmonic mean: the harmonic mean pulls the score down
    for blunders, so one terrible move counts for more than one great move. (Lichess uses the
    same idea with a volatility-weighted mean.) Moves under 10 count as 10 so a single
    blunder doesn't zero the whole game.
    """
    if not accuracies:
        return None
    harmonic = harmonic_mean([max(a, 10.0) for a in accuracies])
    return round((fmean(accuracies) + harmonic) / 2, 1)


def format_eval(score: int) -> str:
    """+1.35, -0.40, #3 (White mates in 3), #-2 (Black mates in 2)."""
    if is_mate(score):
        moves = MATE - abs(score)
        return f"#{moves}" if score > 0 else f"#-{moves}"
    return f"{score / 100:+.2f}"
