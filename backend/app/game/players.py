"""Players answer a list of chat messages. The runner owns the prompts and the rules."""

from typing import Protocol

from app.llm.openrouter import LLMResponse, OpenRouterClient


class Player(Protocol):
    name: str

    async def respond(
        self, messages: list[dict[str, str]], *, timeout: float | None = None
    ) -> LLMResponse:
        """Raise `LLMTimeout` if there's no answer within `timeout` seconds."""
        ...


class LLMPlayer:
    """A model on OpenRouter."""

    def __init__(self, client: OpenRouterClient, model: str) -> None:
        self.name = model
        self._client = client

    async def respond(
        self, messages: list[dict[str, str]], *, timeout: float | None = None
    ) -> LLMResponse:
        return await self._client.chat(self.name, messages, timeout=timeout)
