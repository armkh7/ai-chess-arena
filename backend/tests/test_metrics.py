import pytest

from app.analysis.metrics import (
    MATE,
    format_eval,
    game_accuracy,
    move_accuracy,
    move_label,
    win_percent,
)
from app.game.models import MoveLabel


def test_win_percent():
    assert win_percent(0) == pytest.approx(50)
    assert win_percent(300) == pytest.approx(100 - win_percent(-300))
    assert 75 < win_percent(300) < 76  # +3 pawns is about a 75% winning chance
    assert win_percent(MATE) == win_percent(1_000)  # capped at ±10 pawns


def test_move_accuracy():
    assert move_accuracy(60, 60) == 100
    assert move_accuracy(60, 70) == 100  # improving the position is never penalized
    assert 60 < move_accuracy(60, 50) < 65
    assert move_accuracy(90, 5) == 0


@pytest.mark.parametrize(
    ("drop", "label"),
    [
        (2, MoveLabel.GOOD),
        (5, MoveLabel.INACCURACY),
        (12, MoveLabel.MISTAKE),
        (40, MoveLabel.BLUNDER),
    ],
)
def test_move_label(drop, label):
    assert move_label(drop, is_best=False) is label


def test_best_move_label_wins():
    assert move_label(30, is_best=True) is MoveLabel.BEST


def test_game_accuracy_punishes_blunders():
    assert game_accuracy([]) is None
    assert game_accuracy([100, 100]) == 100
    steady = game_accuracy([80] * 10)
    one_blunder = game_accuracy([90] * 9 + [0])
    assert one_blunder < steady  # same plain average (81 vs 80), but the blunder costs more


def test_format_eval():
    assert format_eval(135) == "+1.35"
    assert format_eval(-40) == "-0.40"
    assert format_eval(MATE - 3) == "#3"
    assert format_eval(-(MATE - 2)) == "#-2"
