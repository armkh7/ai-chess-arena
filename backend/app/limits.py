"""Limits that keep a public site affordable: games per visitor, per day, and in the queue."""

import math
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta


class RateLimiter:
    """At most `limit` hits per key in a sliding `window` (seconds). In memory: a restart
    forgets it, which is fine for a per-visitor limit (the daily cap is in the database)."""

    def __init__(
        self, limit: int, window: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit  # 0 = no limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def retry_after(self, key: str) -> float:
        """Seconds until `key` may hit again; 0 if it may now."""
        if not self.limit:
            return 0.0
        hits = self._hits[key]
        now = self._clock()
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) < self.limit:
            return 0.0
        return self.window - (now - hits[0])

    def hit(self, key: str) -> None:
        if self.limit:
            self._hits[key].append(self._clock())


def start_of_day(now: datetime | None = None) -> datetime:
    """Midnight UTC today: the daily game cap resets then."""
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def seconds_until_tomorrow(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return math.ceil((start_of_day(now) + timedelta(days=1) - now).total_seconds())


def minutes_text(seconds: float) -> str:
    minutes = max(1, math.ceil(seconds / 60))
    return f"{minutes} minute{'s' if minutes != 1 else ''}"
