"""Costs: hidden from visitors, logged for the owner."""

import csv
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.config import Settings
from app.costs import append_cost, strip_costs, summarize
from app.game.models import Attempt, Color, GameRecord, JudgeResult, MoveRecord
from app.llm.openrouter import LLMResponse
from app.main import create_app
from tests.conftest import ScriptedPlayer, reply
from tests.test_api import MODELS, level_engine, start


def test_strip_costs_removes_them_at_any_depth():
    data = {"cost_usd": 1, "moves": [{"attempts": [{"cost_usd": 2, "san": "e4"}]}], "x": None}
    assert strip_costs(data) == {"moves": [{"attempts": [{"san": "e4"}]}], "x": None}


def paid(move: str) -> LLMResponse:
    return LLMResponse(
        content=reply(move),
        model="m",
        latency_ms=100,
        prompt_tokens=500,
        completion_tokens=50,
        cost_usd=0.001,
    )


SCRIPTS = {
    "w/free:free": [paid("f3"), paid("g4")],
    "b/paid": [paid("e5"), paid("Qh4#")],
}


@pytest.fixture
async def api(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        create_tables_on_startup=True,
        move_time_limit_seconds=0,
        public_models_file="",
        judge_enabled=False,
        cost_log_file=str(tmp_path / "logs" / "costs.csv"),
    )

    async def models():
        return MODELS

    app = create_app(
        settings,
        make_player=lambda model, effort, cb: ScriptedPlayer(model, list(SCRIPTS[model])),
        make_evaluator=level_engine,
        model_source=models,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.service = app.state.service
            client.log = tmp_path / "logs" / "costs.csv"
            yield client


async def test_visitors_never_see_costs(api):
    game_id = await start(api)
    await api.service.wait_all()

    responses = [
        await api.get("/models"),
        await api.get("/games"),
        await api.get(f"/games/{game_id}"),
        await api.get(f"/games/{game_id}/stream"),
    ]
    for resp in responses:
        assert resp.status_code == 200
        assert "cost_usd" not in resp.text
        assert "price" not in resp.text


async def test_each_finished_game_is_logged(api):
    game_id = await start(api)
    await api.service.wait_all()

    rows = list(csv.DictReader(api.log.open()))
    assert len(rows) == 1
    row = rows[0]
    assert row["game_id"] == game_id
    assert (row["result"], row["termination"], row["moves"]) == ("0-1", "checkmate", "4")
    assert float(row["white_cost_usd"]) == pytest.approx(0.002)
    assert float(row["total_cost_usd"]) == pytest.approx(0.004)
    # ...and the database still has it, for the owner
    stored = await api.service.store.get(game_id)
    assert json.dumps(stored.record.model_dump(mode="json")).count("cost_usd") > 0


def record(white, black, cost_each, judge_cost, finished):
    """A one-move-each game where every reply cost `cost_each`."""

    def move(ply, color):
        return MoveRecord(
            ply=ply,
            move_number=1,
            color=color,
            san="x",
            uci="a1a1",
            fen_before="",
            fen_after="",
            reasoning=None,
            attempts=[Attempt(raw_reply="", cost_usd=cost_each)],
        )

    return GameRecord(
        white_model=white,
        black_model=black,
        finished_at=finished,
        moves=[move(1, Color.WHITE), move(2, Color.BLACK)],
        judge=JudgeResult(model="judge/model", cost_usd=judge_cost),
    )


def test_summary_by_day_month_and_model(tmp_path):
    log = tmp_path / "costs.csv"
    now = datetime(2026, 11, 22, 18, tzinfo=UTC)
    append_cost(log, record("a/x", "b/y", 0.01, 0.004, datetime(2026, 11, 22, 9, tzinfo=UTC)))
    append_cost(log, record("a/x", "c/z", 0.02, 0.004, datetime(2026, 11, 3, 9, tzinfo=UTC)))
    append_cost(log, record("b/y", "c/z", 0.03, 0.004, datetime(2026, 10, 30, 9, tzinfo=UTC)))

    s = summarize(log, now)
    assert (s.today.games, s.today.usd) == (1, pytest.approx(0.024))
    assert (s.this_month.games, s.this_month.usd) == (2, pytest.approx(0.024 + 0.044))
    assert s.total.games == 3
    assert s.judge.usd == pytest.approx(0.012)
    assert (s.by_model["a/x"].games, s.by_model["a/x"].usd) == (2, pytest.approx(0.03))
    assert log.read_text().splitlines()[0].startswith("finished_at,game_id,")


def test_no_log_means_an_empty_summary(tmp_path):
    assert summarize(tmp_path / "missing.csv").total.games == 0
