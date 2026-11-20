"""Data records for a game: every attempt, every move, and the final result."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class Color(StrEnum):
    WHITE = "white"
    BLACK = "black"

    @property
    def opponent(self) -> "Color":
        return Color.BLACK if self is Color.WHITE else Color.WHITE


class Termination(StrEnum):
    # Natural endings (names match python-chess's `chess.Termination`)
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    INSUFFICIENT_MATERIAL = "insufficient_material"
    SEVENTYFIVE_MOVES = "seventyfive_moves"
    FIVEFOLD_REPETITION = "fivefold_repetition"
    FIFTY_MOVES = "fifty_moves"
    THREEFOLD_REPETITION = "threefold_repetition"
    # Arena endings
    MOVE_LIMIT = "move_limit"  # Phase 2 will adjudicate these with Stockfish
    FORFEIT_ILLEGAL_MOVES = "forfeit_illegal_moves"
    API_ERROR = "api_error"


class Attempt(BaseModel):
    """One reply from a model. A move takes several attempts if earlier ones were rejected."""

    raw_reply: str
    move_text: str | None = None  # the move as the model wrote it
    reasoning: str | None = None
    error: str | None = None  # why it was rejected; None if accepted
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


class MoveRecord(BaseModel):
    ply: int  # half-move index, starting at 1
    move_number: int  # full-move number as written in chess notation
    color: Color
    san: str  # standard notation, e.g. "Nf3"
    uci: str  # from-to squares, e.g. "g1f3"
    fen_before: str
    fen_after: str
    reasoning: str | None
    attempts: list[Attempt]

    @property
    def illegal_attempts(self) -> int:
        return len(self.attempts) - 1


class PlayerStats(BaseModel):
    model: str
    moves: int
    illegal_attempts: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    avg_latency_ms: int


class GameRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    white_model: str
    black_model: str
    show_legal_moves: bool
    max_full_moves: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    result: str = "*"  # "1-0", "0-1", "1/2-1/2", or "*" (unfinished/aborted)
    termination: Termination | None = None
    winner: Color | None = None
    error: str | None = None  # set when the game was aborted by an API error
    moves: list[MoveRecord] = Field(default_factory=list)
    # Rejected attempts of the final turn when a player forfeited or the API failed.
    failed_attempts: list[Attempt] = Field(default_factory=list)
    failed_color: Color | None = None
    pgn: str = ""

    def model_for(self, color: Color) -> str:
        return self.white_model if color is Color.WHITE else self.black_model

    def player_stats(self, color: Color) -> PlayerStats:
        attempts = [a for m in self.moves if m.color is color for a in m.attempts]
        if self.failed_color is color:
            attempts += self.failed_attempts
        moves = [m for m in self.moves if m.color is color]
        return PlayerStats(
            model=self.model_for(color),
            moves=len(moves),
            illegal_attempts=sum(1 for a in attempts if a.error),
            prompt_tokens=sum(a.prompt_tokens or 0 for a in attempts),
            completion_tokens=sum(a.completion_tokens or 0 for a in attempts),
            cost_usd=round(sum(a.cost_usd or 0 for a in attempts), 6),
            avg_latency_ms=(sum(a.latency_ms for a in attempts) // len(attempts))
            if attempts
            else 0,
        )
