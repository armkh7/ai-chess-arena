"""Live game events, kept in memory while a game runs.

Each running game has a channel. It remembers every event so far, so a viewer who connects
mid-game first gets the whole history and then each new event as it happens.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    type: str  # game, status, move, rejected, rate_limited, analysis, end
    data: dict[str, Any]


PING = Event("ping", {})  # sent when nothing happened for a while, keeps the connection open
# Sent once after the history: everything before it already happened. The page applies the
# history in one update, so it shows the current position instead of racing through moves.
SYNCED = Event("synced", {})


@dataclass
class GameChannel:
    history: list[Event] = field(default_factory=list)
    closed: bool = False
    _subscribers: set[asyncio.Queue[Event | None]] = field(default_factory=set)

    def publish(self, type_: str, data: dict[str, Any]) -> None:
        event = Event(type_, data)
        self.history.append(event)
        for queue in self._subscribers:
            queue.put_nowait(event)

    def close(self) -> None:
        self.closed = True
        for queue in self._subscribers:
            queue.put_nowait(None)

    async def subscribe(self, ping_after: float = 15.0) -> AsyncIterator[Event]:
        """Every event so far, `SYNCED`, then new ones until the game ends. `PING` while idle."""
        queue: asyncio.Queue[Event | None] = asyncio.Queue()
        # Copy the history and subscribe in one step (no `await` between them), so no event
        # can slip in between and be missed or sent twice.
        backlog = list(self.history)
        closed = self.closed
        if not closed:
            self._subscribers.add(queue)
        try:
            for event in backlog:
                yield event
            yield SYNCED
            if closed:
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=ping_after)
                except TimeoutError:
                    yield PING
                    continue
                if event is None:
                    return
                yield event
        finally:
            self._subscribers.discard(queue)
