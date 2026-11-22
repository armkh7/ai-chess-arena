"""The leaderboard: Elo, what counts as a ranked game, and the judge's stats."""

import pytest

from app.game.models import (
    GameAnalysis,
    GameRecord,
    JudgeReport,
    JudgeResult,
    PlayerAnalysis,
    Termination,
)
from app.leaderboard import build_leaderboard, expected_score
from tests.test_api import start
from tests.test_judge import REPORT, api, fools_mate  # noqa: F401  (`api` is a fixture)


def game(white, black, result, termination=Termination.CHECKMATE, **extra) -> GameRecord:
    return GameRecord(
        white_model=white, black_model=black, result=result, termination=termination, **extra
    )


def by_model(rows):
    return {row.model: row for row in rows}


def test_expected_score():
    assert expected_score(1500, 1500) == 0.5
    assert expected_score(1700, 1500) == pytest.approx(0.76, abs=0.01)


def test_a_win_moves_ratings_by_half_k_between_equals():
    rows = by_model(build_leaderboard([game("a", "b", "1-0")]))
    assert (rows["a"].rating, rows["b"].rating) == (1516, 1484)
    assert (rows["a"].wins, rows["b"].losses) == (1, 1)
    assert [r.model for r in build_leaderboard([game("a", "b", "1-0")])] == ["a", "b"]


def test_a_draw_between_equals_changes_nothing():
    rows = by_model(build_leaderboard([game("a", "b", "1/2-1/2")]))
    assert rows["a"].rating == rows["b"].rating == 1500
    assert rows["a"].draws == 1


def test_provider_failures_and_unfinished_games_dont_count_but_forfeits_do():
    rows = by_model(
        build_leaderboard(
            [
                game("a", "b", "*", Termination.API_ERROR),
                game("a", "b", "0-1", Termination.API_ERROR),
                game("a", "c", "0-1", Termination.FORFEIT_ILLEGAL_MOVES),
            ]
        )
    )
    assert "b" not in rows
    assert (rows["a"].games, rows["a"].losses) == (1, 1)


def test_provisional_until_five_games():
    games = [game("a", "b", "1-0") for _ in range(5)] + [game("a", "c", "1-0")]
    rows = by_model(build_leaderboard(games))
    assert rows["a"].provisional is False
    assert rows["b"].provisional is False  # exactly 5 games
    assert rows["c"].provisional is True


def test_accuracy_grade_and_honesty_come_from_analysis_and_judge():
    def analysis(white_acc, black_acc):
        player = lambda acc: PlayerAnalysis(accuracy=acc, acpl=0, counts={})  # noqa: E731
        return GameAnalysis(
            engine="x",
            depth=1,
            final_eval=0,
            white=player(white_acc),
            black=player(black_acc),
            moves=[],
        )

    report = JudgeReport.model_validate(REPORT)  # white F, black A; ply 3 (White) not matched
    games = [
        game(
            "a", "b", "0-1", analysis=analysis(60, 90), judge=JudgeResult(model="j", report=report)
        ),
        game("b", "a", "1-0", analysis=analysis(80, 70)),
    ]
    rows = by_model(build_leaderboard(games))
    assert rows["a"].accuracy == 65.0  # (60 + 70) / 2
    assert rows["b"].accuracy == 85.0
    assert (rows["a"].grade, rows["b"].grade) == ("F", "A")
    assert rows["a"].honest == 0  # its one judged moment didn't match
    assert rows["b"].honest is None  # the judge picked no moment of Black's


async def test_leaderboard_endpoint_ranks_finished_games(api):  # noqa: F811
    await start(api)
    await api.service.wait_all()
    rows = (await api.get("/leaderboard")).json()
    assert [r["model"] for r in rows] == ["b/paid", "w/free:free"]  # Black mated
    assert rows[0]["rating"] == 1516
    assert rows[0]["grade"] == "A"  # from the scripted judge's report
    assert rows[0]["provisional"] is True


async def test_fools_mate_helper_is_ranked():
    rows = by_model(build_leaderboard([await fools_mate()]))
    assert rows["b/model"].wins == 1
