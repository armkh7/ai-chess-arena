"""The judge agent: a LangChain agent that reviews a finished game and writes a report.

It's a reasoning model (through OpenRouter) in LangChain's `create_agent` loop. It gathers
evidence with read-only tools (`app.judge.tools`), comparing what each model *said* about its
moves with what the moves did and what Stockfish thinks, then grades both players with a
rubric. Every thought and tool call is reported through `on_step`, so the website can show
the agent working.

The report is submitted through a final `submit_report` tool rather than LangChain's
`ToolStrategy`: that one forces a tool call on every turn, and providers switch thinking off
when a tool call is forced. A report that fails validation goes back to the model as a tool
error so it can fix it; the loop below stops as soon as a report is accepted.
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any, Protocol

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openrouter import ChatOpenRouter

from app.config import ReasoningEffort, Settings
from app.game.models import GameRecord, JudgeReport, JudgeResult, JudgeStep
from app.judge.tools import SUBMIT_REPORT, GameView, make_tools, step_title

OnStep = Callable[[JudgeStep], None]

SYSTEM_PROMPT = """\
You are the judge of a chess game between two AI language models. On each turn a model was
shown the position and replied with a move and a short explanation. Stockfish has already
analyzed every move. Your report is shown to spectators right after the game.

How to work:
1. Call get_game_overview first, then get_key_moments.
2. Examine the 2-4 moments that decided the game with get_move_details. Use show_board when
   the position itself matters, and get_moves to see how a phase of the game went.
3. For each moment, compare three things: what the model SAID (its explanation), what the move
   actually DID on the board, and what Stockfish says. Models often describe threats or plans
   that aren't there; catching that is the most interesting part of your job.
4. Call submit_report exactly once, as your last step. Use about 6-10 tool calls in total.

Rules:
- Stockfish is the ground truth for move quality. Never invent moves, evaluations or lines.
- Write moves in normal notation (14. Nf3, 14... Nf6), not ply numbers, in your report text.
- Short, specific and vivid, for chess fans. No filler.
- A forfeit (illegal moves) or a loss on time is a reliability failure: say so plainly.

Grading rubric (one grade per player, explanations first, then the grade):
- A: accurate play (roughly 85%+ accuracy), no blunders, explanations consistently true.
- B: solid play with an occasional mistake; explanations mostly true.
- C: uneven: at least one blunder or several mistakes; explanations often vague or wrong.
- D: poor: repeated blunders, or explanations that rarely match the position.
- F: lost by forfeit or on time, or collapsed with explanations unrelated to the moves.
"""


class Judge(Protocol):
    async def judge(self, record: GameRecord, on_step: OnStep | None = None) -> JudgeResult: ...


def _thinking(message: AIMessage) -> str:
    """The model's visible reasoning in one message: its thinking plus any text it wrote."""
    parts = [message.additional_kwargs.get("reasoning_content") or ""]
    if isinstance(message.content, str):
        parts.append(message.content)
    else:
        parts += [b.get("text", "") for b in message.content if isinstance(b, dict)]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


class LangChainJudge:
    def __init__(
        self,
        model: BaseChatModel,
        model_name: str,
        *,
        timeout: float = 240,
        max_steps: int = 40,
    ) -> None:
        self.model = model
        self.model_name = model_name
        self.timeout = timeout
        self.max_steps = max_steps  # LangGraph recursion limit: model + tool steps together

    @classmethod
    def from_settings(cls, settings: Settings) -> "LangChainJudge":
        return cls(
            make_model(
                settings.judge_model, settings.openrouter_api_key, settings.judge_reasoning_effort
            ),
            settings.judge_model,
            timeout=settings.judge_timeout_seconds,
        )

    async def judge(self, record: GameRecord, on_step: OnStep | None = None) -> JudgeResult:
        result = JudgeResult(model=self.model_name)
        view = GameView(record)
        agent = create_agent(self.model, make_tools(record), system_prompt=SYSTEM_PROMPT)
        task = (
            f"Judge this game: {record.white_model} (White) vs {record.black_model} (Black), "
            f"result {record.result}. Investigate with your tools, then submit your report."
        )

        def add(step: JudgeStep) -> None:
            result.steps.append(step)
            if on_step:
                on_step(step)

        started = time.monotonic()
        rejection: str | None = None  # why the last submitted report was rejected, if it was
        try:
            async with asyncio.timeout(self.timeout):
                stream = agent.astream(
                    {"messages": [("user", task)]},
                    {"recursion_limit": self.max_steps},
                    stream_mode="updates",
                )
                async for update in stream:
                    for message in _messages(update):
                        if isinstance(message, AIMessage):
                            _count_usage(result, message)
                            if text := _thinking(message):
                                add(JudgeStep(kind="thinking", text=text))
                            for call in message.tool_calls:
                                args = call.get("args") or {}
                                purpose = args.get("purpose") or (
                                    "Writing up the verdict."
                                    if call["name"] == SUBMIT_REPORT
                                    else ""
                                )
                                add(
                                    JudgeStep(
                                        kind="tool",
                                        text=purpose,
                                        tool=call["name"],
                                        title=step_title(view, call["name"], args),
                                    )
                                )
                        elif isinstance(message, ToolMessage) and message.name == SUBMIT_REPORT:
                            if message.status == "error":
                                rejection = _rejection_reason(str(message.content))
                            else:
                                result.report = JudgeReport.model_validate_json(
                                    str(message.content)
                                )
                    # Stop right here: asking the stream for more would start another model
                    # call after the report was already accepted.
                    if result.report is not None:
                        break
                await stream.aclose()
            if result.report is None:
                result.error = (
                    f"The judge's report was rejected: {rejection[:300]}"
                    if rejection
                    else "The judge finished without submitting a report."
                )
        except TimeoutError:
            result.error = f"The judge took longer than {self.timeout:.0f} s and was stopped."
        except Exception as exc:  # the game is already finished: keep it, note the failure
            result.error = f"{type(exc).__name__}: {exc}"
        result.seconds = round(time.monotonic() - started, 1)
        return result


def make_model(model: str, api_key: str, effort: ReasoningEffort | None) -> BaseChatModel:
    return ChatOpenRouter(
        model=model,
        openrouter_api_key=api_key,
        max_tokens=8000,  # thinking counts toward it; only used tokens are billed
        reasoning={"effort": effort} if effort else None,
        app_title="AI Chess Arena",
        max_retries=2,
    )


def _rejection_reason(content: str) -> str:
    """The validation errors from LangChain's tool error message, without the echo of the
    whole submitted report that comes first ("... with error:\\n black: Field required\\n
    Please fix the error and try again.")."""
    reason = content.split("with error:", 1)[-1]
    reason = reason.split("Please fix", 1)[0]
    return " ".join(reason.split())


def _messages(update: dict[str, Any]) -> list[Any]:
    """Messages added by each graph node in one `stream_mode="updates"` chunk."""
    found = []
    for data in update.values():
        if isinstance(data, dict):
            found += data.get("messages", [])
    return found


def _count_usage(result: JudgeResult, message: AIMessage) -> None:
    usage = message.usage_metadata or {}
    result.input_tokens += usage.get("input_tokens", 0)
    result.output_tokens += usage.get("output_tokens", 0)
    cost = message.response_metadata.get("cost")
    if isinstance(cost, int | float):
        result.cost_usd = round(result.cost_usd + cost, 6)
