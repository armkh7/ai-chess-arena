from types import SimpleNamespace

import pytest
from openai.types import CompletionUsage

from app.cli import save_game
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


def test_save_game(tmp_path):
    record = GameRecord(white_model="w", black_model="b", show_legal_moves=True, max_full_moves=10)
    record.pgn = "*"
    json_path, pgn_path = save_game(record, tmp_path / "games")
    assert GameRecord.model_validate_json(json_path.read_text()).white_model == "w"
    assert pgn_path.read_text().strip() == "*"
