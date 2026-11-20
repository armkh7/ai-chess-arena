"""App settings, read from environment variables or a `.env` file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    llm_max_tokens: int = 2000
    # Free models are often rate limited (HTTP 429). Wait and retry: 15s, 30s, 45s, 60s.
    rate_limit_retries: int = 4
    rate_limit_wait_seconds: float = 15.0

    # Game rules
    max_full_moves: int = 60  # after this many moves per side the game stops
    max_illegal_retries: int = 3  # extra tries after an illegal move before forfeiting

    # Database (used from Phase 3)
    database_url: str = "postgresql+psycopg://arena:arena@localhost:5432/arena"


@lru_cache
def get_settings() -> Settings:
    return Settings()
