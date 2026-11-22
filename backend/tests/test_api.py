"""The API with scripted players, a fake engine and in-memory SQLite: no network, no Docker."""

import json
from contextlib import asynccontextmanager

import chess
import httpx
import pytest

from app.analysis.engine import Evaluation
from app.config import Settings
from app.game.models import GameRecord
from app.llm.openrouter import LLMResponse, ModelInfo
from app.main import create_app
from app.storage.db import create_tables, make_engine, make_sessions
from app.storage.games import GameStatus, GameStore
from tests.conftest import ScriptedPlayer, reply

MODELS = [
    ModelInfo("w/free:free", "White Free", 8000, 0.0, 0.0),
    ModelInfo("b/paid", "Black Paid", 8000, 1e-6, 2e-6),
    ModelInfo("crash/model", "Crashes", 8000, 0.0, 0.0),
]

FOOLS_MATE = {
    "w/free:free": [reply("f3"), reply("g4")],
    "b/paid": [reply("e5", "Center."), reply("Qh4#", "Mate.")],
    "crash/model": [RuntimeError("bug in a player")],
}


class LevelEngine:
    """Says every position is equal: enough to check that analysis runs and gets saved."""

    name = "LevelFish"
    depth = 1

    async def evaluate(self, board: chess.Board) -> Evaluation:
        return Evaluation(0, next(iter(board.legal_moves)))


@asynccontextmanager
async def level_engine():
    yield LevelEngine()


class RateLimitedPlayer(ScriptedPlayer):
    """Reports one rate-limit wait before its first reply."""

    def __init__(self, name, script, on_rate_limit):
        super().__init__(name, script)
        self._on_rate_limit = on_rate_limit

    async def respond(self, messages, *, timeout=None) -> LLMResponse:
        if not self.calls:
            self._on_rate_limit(self.name, 15.0, 1)
        return await super().respond(messages, timeout=timeout)


@pytest.fixture
async def api():
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        create_tables_on_startup=True,
        move_time_limit_seconds=0,
        max_full_moves=20,
        max_moves_limit=50,
        public_models_file="",  # every model in MODELS; the site's list has its own tests
        judge_enabled=False,  # never call a real model; the judge has its own tests
    )

    def make_player(model, effort, on_rate_limit):
        return RateLimitedPlayer(model, list(FOOLS_MATE[model]), on_rate_limit)

    async def models():
        return MODELS

    app = create_app(
        settings, make_player=make_player, make_evaluator=level_engine, model_source=models
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.service = app.state.service
            yield client


async def start(api, white="w/free:free", black="b/paid", **body) -> str:
    resp = await api.post("/games", json={"white": white, "black": black, **body})
    assert resp.status_code == 202, resp.text
    return resp.json()["id"]


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


async def test_health_and_models(api):
    assert (await api.get("/health")).json() == {"status": "ok"}
    every = (await api.get("/models")).json()
    free = (await api.get("/models", params={"free": True})).json()
    assert len(every) == 3
    assert [m["id"] for m in free] == ["w/free:free", "crash/model"]
    assert free[0]["is_free"] is True


async def test_game_plays_in_background_and_is_saved(api):
    game_id = await start(api)
    await api.service.wait_all()

    detail = (await api.get(f"/games/{game_id}")).json()
    assert detail["status"] == "finished"
    game = detail["game"]
    assert game["result"] == "0-1"
    assert game["termination"] == "checkmate"
    assert [m["san"] for m in game["moves"]] == ["f3", "e5", "g4", "Qh4#"]
    assert game["analysis"]["engine"] == "LevelFish"

    page = (await api.get("/games")).json()
    assert page["total"] == 1
    summary = page["games"][0]
    assert summary["id"] == game_id
    assert summary["moves"] == 4
    assert summary["winner"] == "black"
    assert summary["white_accuracy"] is not None


async def test_live_events_in_order(api):
    game_id = await start(api)
    channel = api.service.live[game_id]
    await api.service.wait_all()

    types = [event.type for event in channel.history]
    # White waits out a rate limit and moves, then Black does the same.
    assert types[:5] == ["game", "status", "rate_limited", "move", "rate_limited"]
    assert types.count("move") == 4
    assert types[-3:] == ["status", "analysis", "end"]  # analyzing, its result, the end
    assert channel.history[-1].data["result"] == "0-1"
    assert game_id not in api.service.live  # finished games leave memory


async def test_stream_replays_a_finished_game(api):
    game_id = await start(api)
    await api.service.wait_all()

    resp = await api.get(f"/games/{game_id}/stream")
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    assert [t for t, _ in events] == ["game", "move", "move", "move", "move", "analysis", "end"]
    assert events[0][1]["white_model"] == "w/free:free"
    assert events[4][1]["reasoning"] == "Mate."
    assert events[-1][1] == {
        "status": "finished",
        "result": "0-1",
        "termination": "checkmate",
        "winner": "black",
        "error": None,
    }


async def test_unknown_model_is_rejected(api):
    resp = await api.post("/games", json={"white": "nope/model", "black": "b/paid"})
    assert resp.status_code == 422
    assert "nope/model" in resp.json()["detail"]


async def test_a_model_cant_play_itself(api):
    resp = await api.post("/games", json={"white": "b/paid", "black": "b/paid"})
    assert resp.status_code == 422
    assert "different models" in resp.json()["detail"]


async def test_max_moves_is_capped(api):
    resp = await api.post(
        "/games", json={"white": "w/free:free", "black": "b/paid", "max_moves": 51}
    )
    assert resp.status_code == 422


async def test_crash_is_recorded_as_error(api):
    game_id = await start(api, white="crash/model")
    await api.service.wait_all()
    detail = (await api.get(f"/games/{game_id}")).json()
    assert detail["status"] == "error"
    assert detail["error"] == "RuntimeError: bug in a player"


async def test_unknown_game_is_404(api):
    assert (await api.get("/games/missing")).status_code == 404
    assert (await api.get("/games/missing/stream")).status_code == 404


async def test_unfinished_games_are_marked_interrupted():
    engine = make_engine("sqlite+aiosqlite://")
    await create_tables(engine)
    store = GameStore(make_sessions(engine))
    record = GameRecord(white_model="a", black_model="b")
    await store.save(record, GameStatus.RUNNING)

    assert await store.mark_interrupted() == 1
    assert (await store.get(record.id)).status is GameStatus.INTERRUPTED
    await engine.dispose()
