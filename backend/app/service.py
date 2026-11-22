"""Runs games in the background for the API.

`start()` saves a new game and returns at once; the game plays in an asyncio task. Every move
is saved to the database and published to the game's live channel, then Stockfish analyzes
the finished game and the judge agent writes its report, each of its steps published live.
At most `max_concurrent` games play at the same time; the rest wait.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from pydantic import BaseModel

from app.analysis.analyzer import analyze_record
from app.analysis.engine import EngineNotFound, Evaluator
from app.config import ReasoningEffort, Settings
from app.costs import append_cost, log_path
from app.game.models import Attempt, Color, GameRecord, JudgeStep, MoveRecord
from app.game.players import Player
from app.game.runner import GameRunner
from app.judge.agent import Judge
from app.live import GameChannel
from app.llm.openrouter import OnRateLimit
from app.storage.games import GameStatus, GameStore

log = logging.getLogger(__name__)

# (model id, reasoning effort, rate-limit callback) -> a player. Tests pass scripted players.
PlayerFactory = Callable[[str, ReasoningEffort | None, OnRateLimit], Player]
# A fresh engine per analysis, e.g. `lambda: Stockfish(...)`. None = no analysis.
EvaluatorFactory = Callable[[], AbstractAsyncContextManager[Evaluator]]
# The judge agent for one game. None = no judging. Tests pass a scripted judge.
JudgeFactory = Callable[[], Judge]


class NewGame(BaseModel):
    """A validated request to play a game."""

    white: str
    black: str
    max_moves: int
    show_legal_moves: bool = True
    reasoning_effort: ReasoningEffort | None = None
    move_time_limit: float | None = None
    analysis: bool = True
    judge: bool = True  # needs the analysis: the judge reads Stockfish's verdicts


def _end_event(record: GameRecord, status: GameStatus, error: str | None) -> dict[str, Any]:
    """The last event. It also carries the final turn's failed tries (a forfeit or API error),
    so the game page needs nothing but the stream."""
    return {
        "status": status.value,
        "result": record.result,
        "termination": record.termination.value if record.termination else None,
        "winner": record.winner.value if record.winner else None,
        "error": error or record.error,
        "failed_color": record.failed_color.value if record.failed_color else None,
        "failed_attempts": [a.model_dump(mode="json") for a in record.failed_attempts],
    }


def game_event(record: GameRecord, status: GameStatus) -> dict[str, Any]:
    """The first event of every stream: who plays and with which settings."""
    return {
        "id": record.id,
        "status": status.value,
        "white_model": record.white_model,
        "black_model": record.black_model,
        "max_moves": record.max_full_moves,
        "show_legal_moves": record.show_legal_moves,
        "reasoning_effort": record.reasoning_effort,
        "move_time_limit": record.move_time_limit,
    }


def replay_events(record: GameRecord, status: GameStatus, error: str | None) -> list[tuple]:
    """The events of a game that's no longer live, rebuilt from the database."""
    events: list[tuple[str, dict[str, Any]]] = [("game", game_event(record, status))]
    events += [("move", move.model_dump(mode="json")) for move in record.moves]
    if record.analysis:
        events.append(("analysis", record.analysis.model_dump(mode="json")))
    if record.judge:
        events += [("judge_step", step.model_dump(mode="json")) for step in record.judge.steps]
        events.append(("judge", record.judge.model_dump(mode="json")))
    events.append(("end", _end_event(record, status, error)))
    return events


class GameService:
    def __init__(
        self,
        store: GameStore,
        settings: Settings,
        make_player: PlayerFactory,
        make_evaluator: EvaluatorFactory | None,
        make_judge: JudgeFactory | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self._make_player = make_player
        self._make_evaluator = make_evaluator
        self._make_judge = make_judge
        self._slots = asyncio.Semaphore(settings.max_concurrent_games)
        self._tasks: set[asyncio.Task[None]] = set()
        self.live: dict[str, GameChannel] = {}

    @property
    def waiting(self) -> int:
        """Games in the queue: those beyond the free slots. (Counting tasks blocked on the
        semaphore would miss a game started a moment ago that hasn't reached it yet.)"""
        return max(0, len(self._tasks) - self.settings.max_concurrent_games)

    async def start(self, new: NewGame) -> GameRecord:
        record = GameRecord(
            white_model=new.white,
            black_model=new.black,
            show_legal_moves=new.show_legal_moves,
            max_full_moves=new.max_moves,
            reasoning_effort=new.reasoning_effort,
            move_time_limit=new.move_time_limit,
        )
        await self.store.save(record, GameStatus.QUEUED)
        channel = GameChannel()
        channel.publish("game", game_event(record, GameStatus.QUEUED))
        self.live[record.id] = channel

        task = asyncio.create_task(self._run(record, new, channel), name=f"game-{record.id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return record

    async def wait_all(self) -> None:
        """Wait for every running game (tests, shutdown)."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _set_status(
        self, record: GameRecord, channel: GameChannel, status: GameStatus
    ) -> None:
        await self.store.save(record, status)
        data: dict[str, Any] = {"status": status.value}
        if record.termination:  # game over: show the result while Stockfish and the judge work
            data |= {
                "result": record.result,
                "termination": record.termination.value,
                "winner": record.winner.value if record.winner else None,
            }
        channel.publish("status", data)

    async def _log_cost(self, record: GameRecord) -> None:
        """One line in the owner's cost log. A failure here never affects the game."""
        path = log_path(self.settings.cost_log_file)
        if path is None:
            return
        try:
            await asyncio.to_thread(append_cost, path, record)
        except OSError:
            log.exception("Couldn't write the cost of game %s to %s", record.id, path)

    async def _run(self, record: GameRecord, new: NewGame, channel: GameChannel) -> None:
        status, error = GameStatus.FINISHED, None
        try:
            async with self._slots:
                await self._play(record, new, channel)
        except asyncio.CancelledError:
            status = GameStatus.INTERRUPTED
            raise
        except Exception as exc:  # a bug, not a chess result: keep the game, record the error
            log.exception("Game %s crashed", record.id)
            status, error = GameStatus.ERROR, f"{type(exc).__name__}: {exc}"
        finally:
            await asyncio.shield(self.store.save(record, status, error))
            if status is GameStatus.FINISHED and record.moves:
                await self._log_cost(record)
            channel.publish("end", _end_event(record, status, error))
            channel.close()
            self.live.pop(record.id, None)

    async def _play(self, record: GameRecord, new: NewGame, channel: GameChannel) -> None:
        await self._set_status(record, channel, GameStatus.RUNNING)

        def on_rate_limit(model: str, seconds: float, retry: int) -> None:
            channel.publish("rate_limited", {"model": model, "seconds": seconds, "retry": retry})

        async def on_move(move: MoveRecord) -> None:
            await self.store.save(record, GameStatus.RUNNING)  # a refresh never loses a move
            channel.publish("move", move.model_dump(mode="json"))

        def on_rejected(color: Color, attempt: Attempt) -> None:
            channel.publish(
                "rejected", {"color": color.value, "attempt": attempt.model_dump(mode="json")}
            )

        runner = GameRunner(
            self._make_player(new.white, new.reasoning_effort, on_rate_limit),
            self._make_player(new.black, new.reasoning_effort, on_rate_limit),
            max_full_moves=new.max_moves,
            max_illegal_retries=self.settings.max_illegal_retries,
            show_legal_moves=new.show_legal_moves,
            move_time_limit=new.move_time_limit,
            on_move=on_move,
            on_rejected=on_rejected,
        )
        await runner.play(record)

        if new.analysis and record.moves and self._make_evaluator:
            await self._set_status(record, channel, GameStatus.ANALYZING)
            try:
                async with self._make_evaluator() as engine:
                    await analyze_record(record, engine, self.settings.adjudicate_min_cp)
            except EngineNotFound:
                log.warning("Stockfish not found: game %s saved without analysis", record.id)
            if record.analysis:
                channel.publish("analysis", record.analysis.model_dump(mode="json"))

        if new.judge and record.analysis and self._make_judge:
            await self._set_status(record, channel, GameStatus.JUDGING)

            def on_step(step: JudgeStep) -> None:
                channel.publish("judge_step", step.model_dump(mode="json"))

            # Never raises: a failed judge is recorded in `record.judge.error`.
            record.judge = await self._make_judge().judge(record, on_step)
            channel.publish("judge", record.judge.model_dump(mode="json"))
