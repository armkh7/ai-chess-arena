import io

import chess.pgn

from app.game.models import Color, Termination
from app.game.runner import GameRunner
from app.llm.openrouter import LLMError, LLMResponse, LLMTimeout
from tests.conftest import ScriptedPlayer, reply


def runner(white, black, **kwargs) -> GameRunner:
    return GameRunner(white, black, **{"max_full_moves": 60, "max_illegal_retries": 3, **kwargs})


async def test_fools_mate():
    white = ScriptedPlayer("w", [reply("f3"), reply("g4")])
    black = ScriptedPlayer("b", [reply("e5"), reply("Qh4#", "Mate.")])
    record = await runner(white, black).play()

    assert record.result == "0-1"
    assert record.termination is Termination.CHECKMATE
    assert record.winner is Color.BLACK
    assert [m.san for m in record.moves] == ["f3", "e5", "g4", "Qh4#"]
    assert record.moves[-1].reasoning == "Mate."
    assert record.moves[0].ply == 1 and record.moves[3].move_number == 2


async def test_illegal_move_is_retried_with_feedback():
    white = ScriptedPlayer("w", [reply("e5"), reply("e4")])  # e5 is illegal for White's first move
    black = ScriptedPlayer("b", [reply("e5")])
    record = await runner(white, black, max_full_moves=1).play()

    first = record.moves[0]
    assert first.san == "e4"
    assert first.illegal_attempts == 1
    assert "not a legal move" in first.attempts[0].error
    # The second request contains the rejected reply and the reason.
    retry_messages = white.calls[1]
    assert retry_messages[-2]["role"] == "assistant"
    assert "rejected" in retry_messages[-1]["content"]
    assert record.termination is Termination.MOVE_LIMIT
    assert record.result == "1/2-1/2"


async def test_forfeit_after_too_many_illegal_moves():
    white = ScriptedPlayer("w", [reply("Ke2")] * 4)  # king is blocked by its own pawn
    black = ScriptedPlayer("b", [])
    record = await runner(white, black, max_illegal_retries=3).play()

    assert record.termination is Termination.FORFEIT_ILLEGAL_MOVES
    assert record.winner is Color.BLACK
    assert record.result == "0-1"
    assert len(record.failed_attempts) == 4
    assert record.failed_color is Color.WHITE
    assert record.player_stats(Color.WHITE).illegal_attempts == 4


async def test_unreadable_reply_counts_as_rejected():
    white = ScriptedPlayer("w", ["I am not sure what to do.", reply("d4")])
    black = ScriptedPlayer("b", [reply("d5")])
    record = await runner(white, black, max_full_moves=1).play()
    assert record.moves[0].attempts[0].error.startswith("No move found")
    assert record.moves[0].san == "d4"


async def test_reply_cut_off_by_token_limit_is_explained():
    cut_off = LLMResponse(
        content="", model="w", latency_ms=100, completion_tokens=2000, finish_reason="length"
    )
    white = ScriptedPlayer("w", [cut_off, "", reply("e4")])
    black = ScriptedPlayer("b", [reply("e5")])
    record = await runner(white, black, max_full_moves=1).play()

    first, second = record.moves[0].attempts[:2]
    assert first.error.startswith("Empty reply: ran out of tokens while thinking (2,000 tokens)")
    assert first.finish_reason == "length"
    assert second.error.startswith("Empty reply. Answer with JSON")
    # The model is told why, so it can think less next time.
    assert "Think less" in white.calls[1][-1]["content"]


async def test_slow_reply_is_retried_with_feedback():
    white = ScriptedPlayer("w", [LLMTimeout("w: no reply within 30s"), reply("e4")])
    black = ScriptedPlayer("b", [reply("e5")])
    record = await runner(white, black, max_full_moves=1, move_time_limit=30).play()

    first = record.moves[0].attempts[0]
    assert first.timed_out
    assert first.error.startswith("No reply within 30s")
    assert first.latency_ms == 30_000
    assert record.moves[0].san == "e4"
    assert white.timeouts == [30, 30]  # the limit is passed on every request
    # No reply arrived, so the retry adds only our message, not an empty assistant turn.
    assert [m["role"] for m in white.calls[1]] == ["system", "user", "user"]
    assert "answer faster" in white.calls[1][-1]["content"]
    assert record.move_time_limit == 30


async def test_repeated_timeouts_lose_on_time():
    white = ScriptedPlayer("w", [LLMTimeout("slow")] * 4)
    black = ScriptedPlayer("b", [])
    record = await runner(white, black, max_illegal_retries=3, move_time_limit=10).play()

    assert record.termination is Termination.TIMEOUT
    assert record.winner is Color.BLACK
    assert record.result == "0-1"


async def test_no_time_limit_by_default():
    white = ScriptedPlayer("w", [reply("e4")])
    black = ScriptedPlayer("b", [reply("e5")])
    await runner(white, black, max_full_moves=1).play()
    assert white.timeouts == [None]


async def test_api_error_aborts_game():
    white = ScriptedPlayer("w", [reply("e4")])
    black = ScriptedPlayer("b", [LLMError("rate limited")])
    record = await runner(white, black).play()

    assert record.result == "*"
    assert record.termination is Termination.API_ERROR
    assert record.error == "rate limited"
    assert record.failed_color is Color.BLACK
    assert len(record.moves) == 1


async def test_threefold_repetition_ends_game():
    white = ScriptedPlayer("w", [reply(m) for m in ["Nf3", "Ng1"] * 2])
    black = ScriptedPlayer("b", [reply(m) for m in ["Nf6", "Ng8"] * 2])
    record = await runner(white, black).play()

    assert record.termination is Termination.THREEFOLD_REPETITION
    assert record.result == "1/2-1/2"
    # After 7 moves White can claim the draw: Ng1 would repeat the start position a third time.
    assert len(record.moves) == 7


async def test_pgn_and_stats():
    white = ScriptedPlayer("openai/w", [reply("f3"), reply("g4")])
    black = ScriptedPlayer("meta/b", [reply("e5", "Center."), reply("Qh4#")])
    record = await runner(white, black).play()

    game = chess.pgn.read_game(io.StringIO(record.pgn))
    assert game.headers["White"] == "openai/w"
    assert game.headers["Result"] == "0-1"
    assert game.headers["Termination"] == "checkmate"
    assert len(list(game.mainline_moves())) == 4
    assert "Center." in record.pgn

    stats = record.player_stats(Color.BLACK)
    assert stats.moves == 2
    assert stats.prompt_tokens == 100
    assert stats.cost_usd == 0.0002
    assert stats.avg_latency_ms == 100


async def test_callbacks_fire():
    seen_moves, seen_rejections = [], []

    async def on_move(move):
        seen_moves.append(move.san)

    white = ScriptedPlayer("w", [reply("Ke2"), reply("e4")])
    black = ScriptedPlayer("b", [reply("e5")])
    await runner(
        white,
        black,
        max_full_moves=1,
        on_move=on_move,
        on_rejected=lambda color, attempt: seen_rejections.append((color, attempt.move_text)),
    ).play()

    assert seen_moves == ["e4", "e5"]
    assert seen_rejections == [(Color.WHITE, "Ke2")]
