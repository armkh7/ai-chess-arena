"""Request and response bodies."""

from pydantic import BaseModel, Field

from app.config import ReasoningEffort
from app.game.models import GameRecord
from app.storage.games import GameStatus, GameSummary


class GameRequest(BaseModel):
    white: str = Field(examples=["openai/gpt-4o-mini"], description="Model id for White")
    black: str = Field(examples=["meta-llama/llama-3.3-70b-instruct"])
    max_moves: int | None = Field(None, ge=1, description="Moves per side (default from settings)")
    show_legal_moves: bool = True
    reasoning_effort: ReasoningEffort | None = None
    move_time_limit: float | None = Field(
        None, ge=5, le=300, description="Seconds per reply (default from settings)"
    )
    analysis: bool = True
    judge: bool = Field(True, description="Have the judge agent review the game (needs analysis)")


class ArenaStatus(BaseModel):
    """Whether visitors can start games. Only *that* games are paused, never the credit left."""

    games_paused: bool


class ModelOut(BaseModel):
    """A model visitors can pick. No prices: costs are for the site owner only."""

    id: str
    name: str
    context_length: int | None
    is_free: bool


class GameCreated(BaseModel):
    id: str
    status: GameStatus
    stream_url: str


class GamePage(BaseModel):
    games: list[GameSummary]
    total: int


class GameDetail(BaseModel):
    status: GameStatus
    error: str | None
    game: GameRecord
