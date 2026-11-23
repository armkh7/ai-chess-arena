"""New games pause when the OpenRouter credit runs low, or by hand."""

import httpx
import pytest

from app.config import Settings
from app.credits import CreditGuard, fetch_credits_left
from app.llm.openrouter import LLMError
from app.main import create_app
from tests.conftest import ScriptedPlayer
from tests.test_api import FOOLS_MATE, MODELS, level_engine, start
from tests.test_limits import client_for, instant


class Balance:
    """A fake credit source the test can change; counts how often it's asked."""

    def __init__(self, left: float) -> None:
        self.left = left
        self.calls = 0

    async def __call__(self) -> float:
        self.calls += 1
        if isinstance(self.left, Exception):
            raise self.left
        return self.left


async def test_games_pause_under_the_minimum_and_resume_above_it():
    now = [0.0]
    balance = Balance(3.0)
    guard = CreditGuard(balance, 0.5, ttl=60, clock=lambda: now[0])
    assert not await guard.paused()

    balance.left = 0.4
    assert not await guard.paused()  # still the cached value
    now[0] = 61
    assert await guard.paused()

    balance.left = 9.0  # credit added
    now[0] = 122
    assert not await guard.paused()
    assert balance.calls == 3


async def test_a_failed_check_keeps_the_last_known_credit():
    now = [0.0]
    balance = Balance(0.2)
    guard = CreditGuard(balance, 0.5, clock=lambda: now[0])
    assert await guard.paused()
    balance.left = RuntimeError("OpenRouter is down")
    now[0] = 100
    assert await guard.paused()


async def test_no_key_or_no_minimum_means_no_check():
    assert not await CreditGuard(None, 0.5).paused()
    balance = Balance(0.0)
    assert not await CreditGuard(balance, 0).paused()
    assert balance.calls == 0


async def test_games_can_be_paused_by_hand():
    assert await CreditGuard(Balance(100.0), 0.5, paused_by_hand=True).paused()


async def test_credit_left_is_the_lower_of_key_limit_and_account(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer k"
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {"limit": 9, "limit_remaining": 0.3}})
        return httpx.Response(200, json={"data": {"total_credits": 10, "total_usage": 1.25}})

    original = httpx.AsyncClient

    def client(**kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    assert await fetch_credits_left("k", "https://or.test/api/v1") == pytest.approx(0.3)


async def make_api(balance: Balance, make_player=instant, **settings):
    config = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        create_tables_on_startup=True,
        move_time_limit_seconds=0,
        public_models_file="",
        judge_enabled=False,
        games_per_visitor_per_hour=0,
        games_per_day=0,
        **settings,
    )

    async def models():
        return MODELS

    return create_app(
        config,
        make_player=make_player,
        make_evaluator=level_engine,
        model_source=models,
        credit_source=balance,
    )


async def test_the_api_refuses_new_games_while_paused():
    app = await make_api(Balance(0.3))
    async with app.router.lifespan_context(app), await client_for(app) as api:
        assert (await api.get("/status")).json() == {"games_paused": True}
        resp = await api.post("/games", json={"white": "w/free:free", "black": "b/paid"})
        assert resp.status_code == 503
        assert "paused" in resp.json()["detail"]
        assert "$" not in resp.text  # visitors never see amounts
        assert (await api.get("/games")).json()["total"] == 0  # no dead game saved


async def test_the_api_plays_when_there_is_enough_credit():
    app = await make_api(Balance(5.0))
    async with app.router.lifespan_context(app), await client_for(app) as api:
        assert (await api.get("/status")).json() == {"games_paused": False}
        await start(api)
        await app.state.service.wait_all()


async def test_a_provider_failure_rechecks_the_credit_at_once():
    def broke(model, effort, on_rate_limit):
        if model == "w/free:free":
            return ScriptedPlayer(model, [LLMError("402 insufficient credits")])
        return ScriptedPlayer(model, list(FOOLS_MATE[model]))

    balance = Balance(5.0)
    app = await make_api(balance, broke)
    async with app.router.lifespan_context(app), await client_for(app) as api:
        await start(api)  # checks the credit: $5
        await app.state.service.wait_all()
        balance.left = 0.0  # the game failed because the credit just ran out
        assert (await api.get("/status")).json() == {"games_paused": True}  # not cached
