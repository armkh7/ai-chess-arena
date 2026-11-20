"""Thin async client for OpenRouter (OpenAI-compatible API)."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from openai import APIError, AsyncOpenAI, RateLimitError

from app.config import Settings


class LLMError(Exception):
    """The model could not be reached or returned no usable response."""


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str  # model id reported back by OpenRouter
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    context_length: int | None
    prompt_price: float  # USD per token
    completion_price: float  # USD per token

    @property
    def is_free(self) -> bool:
        return self.id.endswith(":free") or (self.prompt_price == 0 and self.completion_price == 0)


def _price(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_models(payload: dict[str, Any]) -> list[ModelInfo]:
    """Turn OpenRouter's `GET /models` response into `ModelInfo` objects."""
    models = []
    for item in payload.get("data", []):
        pricing = item.get("pricing") or {}
        prompt_price = _price(pricing.get("prompt"))
        completion_price = _price(pricing.get("completion"))
        # Skip OpenRouter's routers ("openrouter/auto", "openrouter/free"): each call may hit a
        # different model, so their results can't be credited to one player.
        if item["id"].startswith("openrouter/") or prompt_price < 0 or completion_price < 0:
            continue
        # Skip models that can't answer in text (image, audio or music generators).
        outputs = (item.get("architecture") or {}).get("output_modalities")
        if outputs is not None and "text" not in outputs:
            continue
        models.append(
            ModelInfo(
                id=item["id"],
                name=item.get("name", item["id"]),
                context_length=item.get("context_length"),
                prompt_price=prompt_price,
                completion_price=completion_price,
            )
        )
    return sorted(models, key=lambda m: m.id)


def _rate_limit_details(exc: RateLimitError) -> str:
    """OpenRouter puts the provider's own message in `error.metadata.raw`; fall back to ours."""
    body = exc.body if isinstance(exc.body, dict) else {}
    raw = (body.get("metadata") or {}).get("raw") or body.get("message") or str(exc)
    return str(raw)[:200]


def _retry_after(exc: RateLimitError) -> float | None:
    try:
        return float(exc.response.headers.get("retry-after", ""))
    except ValueError:
        return None


# Called before each rate-limit wait with (model, seconds, retry number).
OnRateLimit = Callable[[str, float, int], None]


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 90.0,
        max_tokens: int = 2000,
        app_name: str = "AI Chess Arena",
        rate_limit_retries: int = 4,
        rate_limit_wait_seconds: float = 15.0,
        on_rate_limit: OnRateLimit | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add it.")
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._rate_limit_retries = rate_limit_retries
        self._rate_limit_wait = rate_limit_wait_seconds
        self.on_rate_limit = on_rate_limit
        self._sleep = sleep
        # The SDK retries server errors (5xx) and short 429s within a few seconds. Free models
        # are often limited for longer, so `chat` adds its own slower retries on top.
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=2,
            default_headers={"X-Title": app_name},
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenRouterClient":
        return cls(
            settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
            app_name=settings.app_name,
            rate_limit_retries=settings.rate_limit_retries,
            rate_limit_wait_seconds=settings.rate_limit_wait_seconds,
        )

    async def chat(self, model: str, messages: list[dict[str, str]]) -> LLMResponse:
        for retry in range(self._rate_limit_retries + 1):
            start = time.perf_counter()
            try:
                resp = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=self._max_tokens,
                    extra_body={"usage": {"include": True}},  # ask OpenRouter to report cost
                )
                break
            except RateLimitError as exc:
                if retry == self._rate_limit_retries:
                    raise LLMError(
                        f"{model}: rate limited (HTTP 429), gave up after {retry} retries. "
                        f"Free models share a small quota: wait a few minutes or pick another "
                        f"model. Provider said: {_rate_limit_details(exc)}"
                    ) from exc
                wait = min(_retry_after(exc) or self._rate_limit_wait * (retry + 1), 120.0)
                if self.on_rate_limit:
                    self.on_rate_limit(model, wait, retry + 1)
                await self._sleep(wait)
            except APIError as exc:
                raise LLMError(f"{model}: {exc}") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)

        if not resp.choices:
            error = (resp.model_extra or {}).get("error")
            raise LLMError(f"{model}: no choices in response ({error or 'unknown error'})")

        usage = resp.usage
        cost = (usage.model_extra or {}).get("cost") if usage else None
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=resp.model or model,
            latency_ms=latency_ms,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            cost_usd=float(cost) if cost is not None else None,
        )

    async def list_models(self) -> list[ModelInfo]:
        return await fetch_models(self._base_url)


async def fetch_models(base_url: str = "https://openrouter.ai/api/v1") -> list[ModelInfo]:
    """All models OpenRouter offers, with prices. This endpoint is public: no key needed."""
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(f"{base_url}/models")
        resp.raise_for_status()
        return parse_models(resp.json())
