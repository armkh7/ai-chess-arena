"""Players answer a list of chat messages. The runner owns the prompts and the rules."""

from typing import Protocol

from app.config import ReasoningEffort
from app.llm.openrouter import LLMResponse, OnRateLimit, OpenRouterClient


class Player(Protocol):
    name: str

    async def respond(
        self, messages: list[dict[str, str]], *, timeout: float | None = None
    ) -> LLMResponse:
        """Raise `LLMTimeout` if there's no answer within `timeout` seconds."""
        ...


class LLMPlayer:
    """A model on OpenRouter. Several players can share one client."""

    def __init__(
        self,
        client: OpenRouterClient,
        model: str,
        *,
        reasoning_effort: ReasoningEffort | None = None,
        on_rate_limit: OnRateLimit | None = None,
    ) -> None:
        self.name = model
        self._client = client
        self._reasoning_effort = reasoning_effort
        self._on_rate_limit = on_rate_limit

    async def respond(
        self, messages: list[dict[str, str]], *, timeout: float | None = None
    ) -> LLMResponse:
        return await self._client.chat(
            self.name,
            messages,
            timeout=timeout,
            reasoning_effort=self._reasoning_effort,
            on_rate_limit=self._on_rate_limit,
        )
