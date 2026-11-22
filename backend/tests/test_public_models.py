import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.public_models import load_public_models
from tests.test_api import FOOLS_MATE, MODELS, RateLimitedPlayer, level_engine, start


def test_the_sites_list_loads():
    public = load_public_models("public_models.toml")
    assert public.reasoning_effort == "low"
    assert len(public.models) == 5
    assert "baidu/ernie-5.5-flash-preview:free" in public.models


def test_no_file_means_every_model():
    assert load_public_models("") is None


@pytest.mark.parametrize(
    ("models", "error"), [("[]", "at least one"), ('["a/x", "b/y", "a/x"]', "listed twice: a/x")]
)
def test_bad_lists_are_refused(tmp_path, models, error):
    file = tmp_path / "models.toml"
    file.write_text(f"models = {models}\n")
    with pytest.raises(ValidationError, match=error):
        load_public_models(str(file))


@pytest.fixture
async def site(tmp_path):
    """The API with a site list: two known models (in this order) and one OpenRouter dropped."""
    file = tmp_path / "public_models.toml"
    file.write_text('reasoning_effort = "low"\nmodels = ["b/paid", "gone/model", "w/free:free"]\n')
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        create_tables_on_startup=True,
        move_time_limit_seconds=0,
        public_models_file=str(file),
    )

    async def models():
        return MODELS

    app = create_app(
        settings,
        make_player=lambda model, effort, cb: RateLimitedPlayer(model, list(FOOLS_MATE[model]), cb),
        make_evaluator=level_engine,
        model_source=models,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.service = app.state.service
            yield client


async def test_only_listed_models_are_shown(site):
    models = (await site.get("/models")).json()
    assert [m["id"] for m in models] == ["b/paid", "w/free:free"]  # listed order, gone/ left out
    free = (await site.get("/models", params={"free": True})).json()
    assert [m["id"] for m in free] == ["w/free:free"]


async def test_unlisted_model_is_refused(site):
    resp = await site.post("/games", json={"white": "crash/model", "black": "b/paid"})
    assert resp.status_code == 422
    assert "not available: crash/model" in resp.json()["detail"]


async def test_games_use_the_lists_effort_unless_asked(site):
    default = await start(site)
    high = await start(site, reasoning_effort="high")
    await site.service.wait_all()
    assert (await site.get(f"/games/{default}")).json()["game"]["reasoning_effort"] == "low"
    assert (await site.get(f"/games/{high}")).json()["game"]["reasoning_effort"] == "high"
