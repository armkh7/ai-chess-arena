"""FastAPI app. Run with `uvicorn app.main:app` after `alembic upgrade head`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analysis.engine import Stockfish
from app.api.routes import ModelCatalog, ModelSource, router
from app.config import ReasoningEffort, Settings, get_settings
from app.game.players import LLMPlayer
from app.llm.openrouter import OnRateLimit, OpenRouterClient, fetch_models
from app.public_models import load_public_models
from app.service import EvaluatorFactory, GameService, PlayerFactory
from app.storage.db import create_tables, make_engine, make_sessions
from app.storage.games import GameStore

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    make_player: PlayerFactory | None = None,
    make_evaluator: EvaluatorFactory | None = None,
    model_source: ModelSource | None = None,
) -> FastAPI:
    """Build the app. Tests swap in scripted players, a fake engine and a fixed model list."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env.")
        engine = make_engine(settings.database_url)
        if settings.create_tables_on_startup:
            await create_tables(engine)
        store = GameStore(make_sessions(engine))
        if interrupted := await store.mark_interrupted():
            log.warning(
                "Marked %d unfinished game(s) from a previous run as interrupted", interrupted
            )

        client = None
        player_factory = make_player
        if player_factory is None:
            client = OpenRouterClient.from_settings(settings)  # one client shared by all games

            def player_factory(
                model: str, effort: ReasoningEffort | None, on_rate_limit: OnRateLimit
            ) -> LLMPlayer:
                return LLMPlayer(
                    client, model, reasoning_effort=effort, on_rate_limit=on_rate_limit
                )

        app.state.settings = settings
        app.state.public_models = load_public_models(settings.public_models_file)
        app.state.catalog = ModelCatalog(
            model_source or (lambda: fetch_models(settings.openrouter_base_url))
        )
        app.state.service = GameService(
            store,
            settings,
            player_factory,
            make_evaluator or (lambda: Stockfish.from_settings(settings)),
        )
        try:
            yield
        finally:
            await app.state.service.shutdown()
            if client:
                await client.aclose()
            await engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
