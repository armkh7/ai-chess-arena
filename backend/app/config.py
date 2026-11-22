"""App settings, read from environment variables or a `.env` file."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ReasoningEffort = Literal["low", "medium", "high"]


class Settings(BaseSettings):
    # `.env` is looked up in the current folder and in the repo root (when run from backend/).
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "AI Chess Arena"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_timeout_seconds: float = 90.0
    # Max output tokens per reply. Reasoning models spend hidden "thinking" tokens before they
    # answer, and those count too: at 2000 they were often cut off before writing the move.
    # It's a ceiling, not a charge: only tokens actually used are billed.
    llm_max_tokens: int = 8000
    # How long reasoning models think: "low" / "medium" / "high", or unset for the model's
    # default. Lower is faster and cheaper but usually plays weaker.
    reasoning_effort: ReasoningEffort | None = None
    # Free models are often rate limited (HTTP 429). Wait and retry: 15s, 30s, 45s, 60s.
    rate_limit_retries: int = 4
    rate_limit_wait_seconds: float = 15.0

    # Game rules
    # Games play until they end on the board (mate, draw, forfeit). This is only a safety cap
    # that real games shouldn't reach; if one does, Stockfish adjudicates the final position.
    max_full_moves: int = 150
    max_illegal_retries: int = 3  # extra tries after an illegal move before forfeiting
    # Seconds per reply, like a chess clock. Too slow counts as a failed try (rate-limit waits
    # don't count). 0 = no limit.
    move_time_limit_seconds: float = 30.0

    # Stockfish analysis
    stockfish_path: str = "stockfish"  # command name on PATH, or a full path
    analysis_depth: int = 14  # search depth per position: higher is stronger but slower
    analysis_time_seconds: float = 0.25  # max time per position (0 = no limit, depth only)
    analysis_threads: int = 2
    analysis_hash_mb: int = 128
    # At the move limit, a side ahead by at least this many centipawns (300 = 3 pawns) wins.
    adjudicate_min_cp: int = 300

    # Judge agent (LangChain): reviews each finished game, after Stockfish, and grades both
    # players. A reasoning model with tool calling, through OpenRouter. ~$0.005 per game.
    judge_enabled: bool = True
    judge_model: str = "anthropic/claude-haiku-5.5"
    judge_reasoning_effort: ReasoningEffort | None = "medium"
    judge_timeout_seconds: float = 240.0

    # Database: set DATABASE_URL in .env (see .env.example). Only the API needs it.
    database_url: str | None = None
    create_tables_on_startup: bool = False  # tests only; real databases use Alembic migrations

    # API
    max_concurrent_games: int = 3  # more games wait in a queue
    max_moves_limit: int = 150  # highest max_moves a client may ask for
    cors_origins: list[str] = ["http://localhost:3000"]  # the frontend's address
    # The models visitors can pick (relative to backend/). Empty = every OpenRouter model.
    public_models_file: str = "public_models.toml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
