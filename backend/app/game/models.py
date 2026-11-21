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
    MOVE_LIMIT = "move_limit"  # move limit reached, final position roughly equal: draw
    ADJUDICATION = "adjudication"  # move limit reached, Stockfish saw a clear winner
    FORFEIT_ILLEGAL_MOVES = "forfeit_illegal_moves"
    TIMEOUT = "timeout"  # kept running out of time on a move: loses on time
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
    finish_reason: str | None = None  # "stop", or "length" if cut off by the token limit
    timed_out: bool = False  # no reply within the move time limit


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


class MoveLabel(StrEnum):
    BEST = "best"  # the engine's top choice
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"


class MoveAnalysis(BaseModel):
    """Stockfish's verdict on one move (filled in by `app.analysis`)."""

    ply: int
    color: Color
    # Evaluations are in centipawns (1/100 of a pawn) from White's point of view.
    # Forced mates are stored as ±(100000 - moves to mate), see `app.analysis.metrics`.
    eval_before: int
    eval_after: int
    best_san: str | None  # what Stockfish would have played
    best_uci: str | None
    cp_loss: int  # how much the move gave away, from the mover's point of view
    win_before: float  # mover's winning chance in %, before and after the move
    win_after: float
    accuracy: float  # 0-100
    label: MoveLabel


class PlayerAnalysis(BaseModel):
    accuracy: float | None  # 0-100, None if the player made no moves
    acpl: int  # average centipawn loss per move: lower is better
    counts: dict[MoveLabel, int]


class GameAnalysis(BaseModel):
    engine: str  # e.g. "Stockfish 19"
    depth: int
    final_eval: int  # evaluation of the last position, same units as `MoveAnalysis`
    white: PlayerAnalysis
    black: PlayerAnalysis
    moves: list[MoveAnalysis]

    def player(self, color: Color) -> PlayerAnalysis:
        return self.white if color is Color.WHITE else self.black


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
    show_legal_moves: bool = True
    max_full_moves: int = 60
    reasoning_effort: str | None = None  # "low" / "medium" / "high", None = model default
    move_time_limit: float | None = None  # seconds per reply, None = no limit
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
    analysis: GameAnalysis | None = None  # Stockfish analysis, added after the game
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
