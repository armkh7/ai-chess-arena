import copy
import json

from app.llm.openrouter import LLMResponse


def reply(move: str, reasoning: str = "test") -> str:
    """A well-formed model reply."""
    return json.dumps({"reasoning": reasoning, "move": move})


class ScriptedPlayer:
    """Plays pre-written replies in order.

    A string becomes a normal reply, an `LLMResponse` is returned as is (to fake token counts
    or a cut-off reply), and an Exception is raised.
    """

    def __init__(self, name: str, script: list[str | LLMResponse | Exception]) -> None:
        self.name = name
        self._script = iter(script)
        self.calls: list[list[dict[str, str]]] = []
        self.timeouts: list[float | None] = []

    async def respond(
        self, messages: list[dict[str, str]], *, timeout: float | None = None
    ) -> LLMResponse:
        self.calls.append(copy.deepcopy(messages))
        self.timeouts.append(timeout)
        item = next(self._script)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(
            content=item,
            model=self.name,
            latency_ms=100,
            prompt_tokens=50,
            completion_tokens=10,
            cost_usd=0.0001,
        )
