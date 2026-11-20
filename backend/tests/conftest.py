import copy
import json

from app.llm.openrouter import LLMResponse


def reply(move: str, reasoning: str = "test") -> str:
    """A well-formed model reply."""
    return json.dumps({"reasoning": reasoning, "move": move})


class ScriptedPlayer:
    """Plays pre-written replies in order. An Exception in the script is raised instead."""

    def __init__(self, name: str, script: list[str | Exception]) -> None:
        self.name = name
        self._script = iter(script)
        self.calls: list[list[dict[str, str]]] = []

    async def respond(self, messages: list[dict[str, str]]) -> LLMResponse:
        self.calls.append(copy.deepcopy(messages))
        item = next(self._script)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(
            content=item,
            model=self.name,
            latency_ms=100,
            prompt_tokens=50,
            completion_tokens=10,
            cost_usd=0.0001,
        )
