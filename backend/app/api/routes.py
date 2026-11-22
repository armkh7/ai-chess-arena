"""Endpoints.

GET  /models                 models visitors can pick (`public_models.toml`), with OpenRouter
                             prices (cached for 10 minutes)
POST /games                  start a game; returns at once, the game plays in the background
GET  /games                  finished and running games, newest first
GET  /games/{id}             one game with every move, attempt and the analysis
GET  /games/{id}/stream      live events (Server-Sent Events): the history, then each new event
"""

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import GameCreated, GameDetail, GamePage, GameRequest, ModelOut
from app.config import Settings
from app.live import Event
from app.llm.openrouter import ModelInfo
from app.public_models import PublicModels
from app.service import GameService, NewGame, replay_events

router = APIRouter()

ModelSource = Callable[[], Awaitable[list[ModelInfo]]]


class ModelCatalog:
    """OpenRouter's model list, fetched at most every `ttl` seconds."""

    def __init__(self, source: ModelSource, ttl: float = 600) -> None:
        self._source = source
        self._ttl = ttl
        self._models: list[ModelInfo] = []
        self._fetched_at = 0.0

    async def get(self) -> list[ModelInfo]:
        if not self._models or time.monotonic() - self._fetched_at > self._ttl:
            self._models = await self._source()
            self._fetched_at = time.monotonic()
        return self._models


def _service(request: Request) -> GameService:
    return request.app.state.service


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _public(request: Request) -> PublicModels | None:
    return request.app.state.public_models


async def _available_models(request: Request) -> list[ModelInfo]:
    """The site's models in their listed order, or every OpenRouter model if there's no list.

    A listed model that OpenRouter no longer offers is left out.
    """
    models = await request.app.state.catalog.get()
    public = _public(request)
    if public is None:
        return models
    by_id = {m.id: m for m in models}
    return [by_id[model_id] for model_id in public.models if model_id in by_id]


@router.get("/models", response_model=list[ModelOut])
async def list_models(request: Request, free: bool = False) -> list[ModelOut]:
    models = await _available_models(request)
    return [ModelOut(**vars(m), is_free=m.is_free) for m in models if not free or m.is_free]


@router.post("/games", response_model=GameCreated, status_code=202)
async def start_game(body: GameRequest, request: Request) -> GameCreated:
    settings = _settings(request)
    public = _public(request)
    available = {m.id for m in await _available_models(request)}
    unknown = [m for m in (body.white, body.black) if m not in available]
    if unknown:
        raise HTTPException(422, f"Model(s) not available: {', '.join(unknown)}. See GET /models.")
    max_moves = body.max_moves or settings.max_full_moves
    if max_moves > settings.max_moves_limit:
        raise HTTPException(422, f"max_moves can be at most {settings.max_moves_limit}.")
    default_effort = (public and public.reasoning_effort) or settings.reasoning_effort

    record = await _service(request).start(
        NewGame(
            white=body.white,
            black=body.black,
            max_moves=max_moves,
            show_legal_moves=body.show_legal_moves,
            reasoning_effort=body.reasoning_effort or default_effort,
            move_time_limit=body.move_time_limit or settings.move_time_limit_seconds or None,
            analysis=body.analysis,
        )
    )
    return GameCreated(id=record.id, status="queued", stream_url=f"/games/{record.id}/stream")


@router.get("/games", response_model=GamePage)
async def list_games(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> GamePage:
    games, total = await _service(request).store.list_games(limit=limit, offset=offset)
    return GamePage(games=games, total=total)


@router.get("/games/{game_id}", response_model=GameDetail)
async def get_game(game_id: str, request: Request) -> GameDetail:
    stored = await _service(request).store.get(game_id)
    if stored is None:
        raise HTTPException(404, "Game not found")
    return GameDetail(status=stored.status, error=stored.error, game=stored.record)


def _sse(event: Event) -> str:
    if event.type == "ping":
        return ": ping\n\n"  # a comment line: keeps proxies from closing an idle connection
    return f"event: {event.type}\ndata: {json.dumps(event.data)}\n\n"


@router.get("/games/{game_id}/stream")
async def stream_game(game_id: str, request: Request) -> StreamingResponse:
    service = _service(request)
    channel = service.live.get(game_id)

    if channel is not None:
        events: AsyncIterator[Event] = channel.subscribe()
    else:  # not running (anymore): replay it from the database
        stored = await service.store.get(game_id)
        if stored is None:
            raise HTTPException(404, "Game not found")
        saved = [Event(t, d) for t, d in replay_events(stored.record, stored.status, stored.error)]

        async def replay() -> AsyncIterator[Event]:
            for event in saved:
                yield event

        events = replay()

    async def body() -> AsyncIterator[str]:
        async for event in events:
            if await request.is_disconnected():
                break
            yield _sse(event)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}  # no proxy buffering
    return StreamingResponse(body(), media_type="text/event-stream", headers=headers)
