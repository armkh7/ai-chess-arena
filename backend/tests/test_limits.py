"""Cost guards: games per visitor per hour, per day, and in the queue."""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app.config import Settings
from app.limits import RateLimiter, minutes_text, seconds_until_tomorrow, start_of_day
from app.main import create_app
from tests.conftest import ScriptedPlayer
from tests.test_api import FOOLS_MATE, MODELS, RateLimitedPlayer, level_engine, start


def test_rate_limiter_slides():
    now = [0.0]
    limiter = RateLimiter(2, window=3600, clock=lambda: now[0])
    limiter.hit("ip")
    limiter.hit("ip")
    assert limiter.retry_after("other") == 0  # per key
    now[0] = 600
    assert limiter.retry_after("ip") == pytest.approx(3000)  # the first hit expires at 3600
    now[0] = 3600
    assert limiter.retry_after("ip") == 0


def test_no_limit_when_zero():
    limiter = RateLimiter(0, window=3600)
    for _ in range(10):
        limiter.hit("ip")
    assert limiter.retry_after("ip") == 0


def test_day_boundaries():
    noon = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    assert start_of_day(noon) == datetime(2026, 11, 22, tzinfo=UTC)
    assert seconds_until_tomorrow(noon) == 12 * 3600
    assert minutes_text(30) == "1 minute"
    assert minutes_text(3000) == "50 minutes"


class Gate:
    """Players that wait until the test lets them move: keeps games in their slots."""

    def __init__(self):
        self.open = asyncio.Event()

    def player(self, model, effort, on_rate_limit):
        gate = self

        class Waiting(RateLimitedPlayer):
            async def respond(self, messages, *, timeout=None):
                await gate.open.wait()
                return await super().respond(messages, timeout=timeout)

        return Waiting(model, list(FOOLS_MATE[model]), on_rate_limit)


async def make_api(make_player, **limits):
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        create_tables_on_startup=True,
        move_time_limit_seconds=0,
        public_models_file="",
        judge_enabled=False,
        **limits,
    )

    async def models():
        return MODELS

    return create_app(
        settings, make_player=make_player, make_evaluator=level_engine, model_source=models
    )


def instant(model, effort, on_rate_limit):
    return ScriptedPlayer(model, list(FOOLS_MATE[model]))


async def client_for(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_a_visitor_can_start_only_so_many_games_per_hour():
    app = await make_api(instant, games_per_visitor_per_hour=2, games_per_day=0)
    async with app.router.lifespan_context(app), await client_for(app) as api:
        await start(api)
        await start(api)
        resp = await api.post("/games", json={"white": "w/free:free", "black": "b/paid"})
        assert resp.status_code == 429
        assert "2 games per hour" in resp.json()["detail"]
        assert 3000 < int(resp.headers["Retry-After"]) <= 3600
        await app.state.service.wait_all()


async def test_rejected_requests_dont_use_up_the_visitors_games():
    app = await make_api(instant, games_per_visitor_per_hour=1, games_per_day=0)
    async with app.router.lifespan_context(app), await client_for(app) as api:
        bad = await api.post("/games", json={"white": "nope/model", "black": "b/paid"})
        assert bad.status_code == 422
        await start(api)  # still allowed: the invalid request didn't count
        await app.state.service.wait_all()


async def test_the_site_stops_at_the_daily_cap():
    app = await make_api(instant, games_per_visitor_per_hour=0, games_per_day=2)
    async with app.router.lifespan_context(app), await client_for(app) as api:
        await start(api)
        await start(api)
        resp = await api.post("/games", json={"white": "w/free:free", "black": "b/paid"})
        assert resp.status_code == 429
        assert "today's limit of 2 games" in resp.json()["detail"]
        await app.state.service.wait_all()


async def test_a_full_queue_refuses_new_games():
    gate = Gate()
    app = await make_api(
        gate.player,
        max_concurrent_games=1,
        max_waiting_games=1,
        games_per_visitor_per_hour=0,
        games_per_day=0,
    )
    async with app.router.lifespan_context(app), await client_for(app) as api:
        await start(api)  # takes the only slot
        await start(api)  # waits
        await asyncio.sleep(0.01)
        assert app.state.service.waiting == 1
        resp = await api.post("/games", json={"white": "w/free:free", "black": "b/paid"})
        assert resp.status_code == 429
        assert "busy" in resp.json()["detail"]
        gate.open.set()
        await app.state.service.wait_all()
        assert app.state.service.waiting == 0
