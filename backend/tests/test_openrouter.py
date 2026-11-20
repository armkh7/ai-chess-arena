from types import SimpleNamespace

import httpx
import pytest
from openai import RateLimitError
from openai.types import CompletionUsage

from app.cli import console, save_game
from app.game.models import GameRecord
from app.llm.openrouter import LLMError, OpenRouterClient, parse_models


def test_parse_models():
    payload = {
        "data": [
            {
                "id": "z/paid",
                "name": "Paid",
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
            },
            {"id": "a/free:free", "name": "Free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "openrouter/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
            {"id": "openrouter/free", "pricing": {"prompt": "0", "completion": "0"}},
            {
                "id": "x/music-gen",
                "pricing": {"prompt": "0", "completion": "0"},
                "architecture": {"output_modalities": ["audio"]},
            },
        ]
    }
    models = parse_models(payload)
    assert [m.id for m in models] == ["a/free:free", "z/paid"]
    assert models[0].is_free and not models[1].is_free
    assert models[1].completion_price == pytest.approx(2e-6)


def test_missing_key():
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        OpenRouterClient("")


async def test_chat_reads_content_usage_and_cost(monkeypatch):
    client = OpenRouterClient("test-key")
    usage = CompletionUsage.model_validate(
        {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "cost": 0.00042}
    )
    fake = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"move": "e4"}'))],
        usage=usage,
        model="openai/gpt-4o-mini",
        model_extra={},
    )

    async def create(**kwargs):
        assert kwargs["extra_body"] == {"usage": {"include": True}}
        return fake

    monkeypatch.setattr(client._client.chat.completions, "create", create)
    resp = await client.chat("openai/gpt-4o-mini", [{"role": "user", "content": "hi"}])
    assert resp.content == '{"move": "e4"}'
    assert resp.prompt_tokens == 120
    assert resp.cost_usd == pytest.approx(0.00042)


async def test_chat_without_choices_raises(monkeypatch):
    client = OpenRouterClient("test-key")

    async def create(**kwargs):
        return SimpleNamespace(
            choices=[], usage=None, model="x", model_extra={"error": "overloaded"}
        )

    monkeypatch.setattr(client._client.chat.completions, "create", create)
    with pytest.raises(LLMError, match="overloaded"):
        await client.chat("x", [])


def rate_limit_error(headers=None) -> RateLimitError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(429, request=request, headers=headers or {})
    body = {"message": "Provider returned error", "metadata": {"raw": "busy upstream"}}
    return RateLimitError("Error code: 429", response=response, body=body)


def ok_response():
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"move": "e4"}'))],
        usage=None,
        model="x",
        model_extra={},
    )


def rate_limited_client(monkeypatch, failures: int, headers=None, retries: int = 4):
    waits, notices = [], []

    async def fake_sleep(seconds):
        waits.append(seconds)

    client = OpenRouterClient(
        "test-key",
        rate_limit_retries=retries,
        rate_limit_wait_seconds=10,
        on_rate_limit=lambda model, seconds, retry: notices.append(retry),
        sleep=fake_sleep,
    )
    calls = {"n": 0}

    async def create(**kwargs):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise rate_limit_error(headers)
        return ok_response()

    monkeypatch.setattr(client._client.chat.completions, "create", create)
    return client, waits, notices


async def test_rate_limit_waits_and_retries(monkeypatch):
    client, waits, notices = rate_limited_client(monkeypatch, failures=2)
    resp = await client.chat("x", [])
    assert resp.content == '{"move": "e4"}'
    assert waits == [10, 20]  # wait grows with each retry
    assert notices == [1, 2]


async def test_rate_limit_gives_up_with_provider_message(monkeypatch):
    client, waits, _ = rate_limited_client(monkeypatch, failures=99, retries=2)
    with pytest.raises(LLMError, match="gave up after 2 retries.*busy upstream"):
        await client.chat("x", [])
    assert waits == [10, 20]


async def test_rate_limit_uses_retry_after_header(monkeypatch):
    client, waits, _ = rate_limited_client(monkeypatch, failures=1, headers={"retry-after": "3"})
    await client.chat("x", [])
    assert waits == [3.0]


def test_console_keeps_free_suffix_as_text():
    with console.capture() as captured:
        console.print("google/gemma-4-31b-it:free: Error code: 429")
    assert ":free:" in captured.get()


def test_save_game(tmp_path):
    record = GameRecord(white_model="w", black_model="b", show_legal_moves=True, max_full_moves=10)
    record.pgn = "*"
    json_path, pgn_path = save_game(record, tmp_path / "games")
    assert GameRecord.model_validate_json(json_path.read_text()).white_model == "w"
    assert pgn_path.read_text().strip() == "*"
