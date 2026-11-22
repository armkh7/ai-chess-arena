"""The models visitors can pick on the site, read from `public_models.toml`."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, field_validator

from app.config import ReasoningEffort

BACKEND_DIR = Path(__file__).resolve().parents[1]


class PublicModels(BaseModel):
    models: list[str]
    reasoning_effort: ReasoningEffort | None = None  # for games on the site, unless asked

    @field_validator("models")
    @classmethod
    def _listed_once(cls, models: list[str]) -> list[str]:
        if not models:
            raise ValueError("list at least one model")
        twice = sorted({m for m in models if models.count(m) > 1})
        if twice:
            raise ValueError(f"listed twice: {', '.join(twice)}")
        return models


def load_public_models(path: str) -> PublicModels | None:
    """The site's model list. None when `path` is empty: every OpenRouter model is allowed.

    A relative path is relative to the backend folder, so it works from any directory.
    """
    if not path:
        return None
    file = Path(path)
    if not file.is_absolute():
        file = BACKEND_DIR / file
    with file.open("rb") as f:
        return PublicModels.model_validate(tomllib.load(f))
