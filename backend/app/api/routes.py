"""Endpoints.

GET  /models                 models visitors can pick (`public_models.toml`; cached 10 minutes)
POST /games                  start a game; returns at once, the game plays in the background
GET  /games                  finished and running games, newest first
GET  /games/{id}             one game with every move, attempt and the analysis
GET  /games/{id}/stream      live events (Server-Sent Events): the history, then each new event
GET  /leaderboard            Elo ratings and per-model stats from finished games
GET  /status                 whether new games are paused (low OpenRouter credit, or by hand)

No response contains costs: they're for the site owner (`app.costs`).
"""

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.api.schemas import (
    ArenaStatus,
    GameCreated,
    GameDetail,
    GamePage,
    GameRequest,
    ModelOut,
)
from app.config import Settings
from app.costs import strip_costs
from app.leaderboard import LeaderboardRow, build_leaderboard
from app.limits import minutes_text, seconds_until_tomorrow, start_of_day
from app.live import SYNCED, Event
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


def _too_many(message: str, retry_after: float) -> HTTPException:
    return HTTPException(429, message, headers={"Retry-After": str(max(1, round(retry_after)))})


PAUSED = "New games are paused for now. You can still watch every past game and the leaderboard."


@router.get("/status", response_model=ArenaStatus)
async def arena_status(request: Request) -> ArenaStatus:
    return ArenaStatus(games_paused=await request.app.state.credits.paused())


async def _check_limits(request: Request, visitor: str) -> None:
    """Cost guards: paused games (low credit), a full queue, the daily cap, then the
    visitor's hourly limit."""
    settings = _settings(request)
    service = _service(request)

    if await request.app.state.credits.paused():
        raise HTTPException(503, PAUSED)

    if settings.max_waiting_games and service.waiting >= settings.max_waiting_games:
        raise _too_many(
            "The arena is busy: all game slots are taken and the queue is full. "
            "Please try again in a few minutes.",
            120,
        )
    if settings.games_per_day:
        today = await service.store.count_since(start_of_day())
        cap = settings.games_per_day
        if today >= cap:
            raise _too_many(
                f"The arena has reached today's limit of {cap} game{'s' if cap != 1 else ''}. "
                "Come back tomorrow!",
                seconds_until_tomorrow(),
            )
    wait = request.app.state.visitor_limiter.retry_after(visitor)
    if wait:
        limit = settings.games_per_visitor_per_hour
        raise _too_many(
            f"You can start {limit} game{'s' if limit != 1 else ''} per hour. "
            f"Please try again in {minutes_text(wait)}.",
            wait,
        )


@router.post("/games", response_model=GameCreated, status_code=202)
async def start_game(body: GameRequest, request: Request) -> GameCreated:
    settings = _settings(request)
    public = _public(request)
    available = {m.id for m in await _available_models(request)}
    unknown = [m for m in (body.white, body.black) if m not in available]
    if unknown:
        raise HTTPException(422, f"Model(s) not available: {', '.join(unknown)}. See GET /models.")
    if body.white == body.black:
        raise HTTPException(422, "Pick two different models: a model can't play itself.")
    max_moves = body.max_moves or settings.max_full_moves
    if max_moves > settings.max_moves_limit:
        raise HTTPException(422, f"max_moves can be at most {settings.max_moves_limit}.")
    default_effort = (public and public.reasoning_effort) or settings.reasoning_effort

    visitor = request.client.host if request.client else "unknown"
    await _check_limits(request, visitor)
    request.app.state.visitor_limiter.hit(visitor)

    record = await _service(request).start(
        NewGame(
            white=body.white,
            black=body.black,
            max_moves=max_moves,
            show_legal_moves=body.show_legal_moves,
            reasoning_effort=body.reasoning_effort or default_effort,
            move_time_limit=body.move_time_limit or settings.move_time_limit_seconds or None,
            analysis=body.analysis,
            judge=body.judge,
        )
    )
    return GameCreated(id=record.id, status="queued", stream_url=f"/games/{record.id}/stream")


@router.get("/games", response_model=GamePage)
async def list_games(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    games, total = await _service(request).store.list_games(limit=limit, offset=offset)
    return _without_costs(GamePage(games=games, total=total))


@router.get("/games/{game_id}", response_model=GameDetail)
async def get_game(game_id: str, request: Request) -> JSONResponse:
    stored = await _service(request).store.get(game_id)
    if stored is None:
        raise HTTPException(404, "Game not found")
    return _without_costs(GameDetail(status=stored.status, error=stored.error, game=stored.record))


@router.get("/leaderboard", response_model=list[LeaderboardRow])
async def leaderboard(request: Request) -> list[LeaderboardRow]:
    return build_leaderboard(await _service(request).store.finished_games())


def _without_costs(body: BaseModel) -> JSONResponse:
    """A response without costs: they're for the site owner (see `app.costs`)."""
    return JSONResponse(strip_costs(body.model_dump(mode="json")))


def _sse(event: Event) -> str:
    if event.type == "ping":
        return ": ping\n\n"  # a comment line: keeps proxies from closing an idle connection
    return f"event: {event.type}\ndata: {json.dumps(strip_costs(event.data))}\n\n"


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
            yield SYNCED  # same shape as a live stream: history, then the marker

        events = replay()

    async def body() -> AsyncIterator[str]:
        async for event in events:
            if await request.is_disconnected():
                break
            yield _sse(event)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}  # no proxy buffering
    return StreamingResponse(body(), media_type="text/event-stream", headers=headers)
