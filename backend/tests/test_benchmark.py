import asyncio
from collections import Counter

import pytest

from app.benchmark import pairings, run_games, summarize, to_markdown
from app.game.runner import GameRunner
from app.llm.openrouter import LLMError, LLMTimeout
from tests.conftest import ScriptedPlayer, reply


def test_pairings_cover_every_pair_and_balance_colors():
    models = ["a", "b", "c", "d"]
    games = pairings(models)
    assert len(games) == 6  # 4 models -> 6 pairs
    assert {frozenset(g) for g in games} == {
        frozenset(p)
        for p in [("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d")]
    }
    whites = Counter(white for white, _ in games)
    assert max(whites.values()) - min(whites.get(m, 0) for m in models) <= 1


def test_two_games_per_pair_swap_colors():
    assert pairings(["a", "b"], games_per_pair=2) == [("a", "b"), ("b", "a")]


async def test_run_games_limits_concurrency_and_survives_crashes():
    running = peak = 0

    async def play(white, black):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        if white == "crash":
            raise RuntimeError("boom")
        return await GameRunner(
            ScriptedPlayer(white, [reply("e4")]),
            ScriptedPlayer(black, [reply("e5")]),
            max_full_moves=1,
        ).play()

    finished = []
    records = await run_games(
        [("a", "b"), ("c", "d"), ("crash", "x"), ("e", "f")],
        play,
        concurrency=2,
        on_done=lambda r: finished.append(r.white_model),
    )
    assert peak == 2
    assert len(records) == len(finished) == 4
    assert records[2].error == "RuntimeError: boom"


async def game(white_script, black_script, **kwargs):
    return await GameRunner(
        ScriptedPlayer("white/model", white_script),
        ScriptedPlayer("black/model", black_script),
        max_illegal_retries=1,
        **kwargs,
    ).play()


async def test_summary_counts_results_and_failures():
    records = [
        await game([reply("f3"), reply("g4")], [reply("e5"), reply("Qh4#")]),  # black mates
        await game([reply("Ke2"), reply("Ke2")], []),  # white forfeits
        await game([LLMTimeout("slow"), LLMTimeout("slow")], [], move_time_limit=10),  # timeout
        await game([reply("e4")], [LLMError("rate limited")]),  # aborted on black's turn
    ]
    results = {r.model: r for r in summarize(records)}
    white, black = results["white/model"], results["black/model"]

    assert (white.wins, white.draws, white.losses) == (0, 0, 3)
    assert (white.forfeits, white.timeouts, white.api_errors) == (1, 1, 0)
    assert white.finish_rate == pytest.approx(0.5)  # 2 of 4 games without a failure
    assert white.illegal_rate == pytest.approx(4 / 7)  # 2 illegal + 2 timeouts of 7 replies

    assert (black.wins, black.api_errors) == (3, 1)
    assert black.score == 1.0
    assert black.finish_rate == pytest.approx(0.75)


async def test_ranking_puts_reliable_models_first_and_writes_markdown():
    records = [await game([reply("Ke2"), reply("Ke2")], [])]  # white forfeits
    results = summarize(records)
    assert [r.model for r in results] == ["black/model", "white/model"]

    md = to_markdown(results, "Model benchmark", ["- test run"])
    assert md.startswith("# Model benchmark")
    assert "| Model | Games | Finish |" in md
    assert "| white/model | 1 | 0% | 0% | 0-0-1 |" in md
    assert "1 forfeit" in md
