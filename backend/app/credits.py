"""How much OpenRouter credit is left, so new games pause before the money runs out.

Without this, a game started with no credit left stops on its first move ("the model provider
failed") and the visitor thinks the site is broken. Instead the API refuses new games while
the credit left is under `min_credits_usd`, and the home page says new games are paused.

Visitors only ever learn *that* games are paused, never the amounts: those are for the owner.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

# Returns the credit left in USD.
CreditSource = Callable[[], Awaitable[float]]


async def fetch_credits_left(api_key: str, base_url: str = "https://openrouter.ai/api/v1") -> float:
    """The lower of what's left of the key's own spending limit and of the account balance.

    `GET /key` has `limit_remaining` (None when the key has no limit); `GET /credits` has the
    account's `total_credits` and `total_usage`. Both work with a normal API key.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=10, headers=headers) as http:
        key, credits = await asyncio.gather(
            http.get(f"{base_url}/key"), http.get(f"{base_url}/credits")
        )
    key.raise_for_status()
    credits.raise_for_status()
    account = credits.json()["data"]
    left = [float(account["total_credits"]) - float(account["total_usage"])]
    if (key_left := key.json()["data"].get("limit_remaining")) is not None:
        left.append(float(key_left))
    return min(left)


class CreditGuard:
    """Says whether new games are paused: by hand (`paused_by_hand`), or because the credit
    left is under `minimum`. The credit is checked at most every `ttl` seconds."""

    def __init__(
        self,
        source: CreditSource | None,
        minimum: float,
        *,
        paused_by_hand: bool = False,
        ttl: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source  # None: no key, nothing to check (tests, local runs)
        self.minimum = minimum  # 0 = no check
        self.paused_by_hand = paused_by_hand
        self._ttl = ttl
        self._clock = clock
        self._lock = asyncio.Lock()
        self.left: float | None = None  # last known credit left, USD
        self._checked_at: float | None = None
        self._was_low = False

    async def paused(self) -> bool:
        if self.paused_by_hand:
            return True
        if self._source is None or not self.minimum:
            return False
        await self._refresh()
        low = self.left is not None and self.left < self.minimum
        if low != self._was_low:  # tell the owner when the pause starts and ends
            self._was_low = low
            if low:
                log.warning(
                    "New games paused: $%.2f of OpenRouter credit left (minimum $%.2f). "
                    "Add credit or raise the key's limit.",
                    self.left,
                    self.minimum,
                )
            else:
                log.warning("New games resumed: $%.2f of OpenRouter credit left.", self.left)
        return low

    def expire(self) -> None:
        """Check again on the next request: a game just failed at the provider, which may mean
        the credit ran out."""
        self._checked_at = None

    async def _refresh(self) -> None:
        async with self._lock:
            now = self._clock()
            if self._checked_at is not None and now - self._checked_at < self._ttl:
                return
            assert self._source is not None
            try:
                self.left = await self._source()
            except Exception:  # OpenRouter hiccup: keep the last known value, retry later
                log.warning("Couldn't check the OpenRouter credit left", exc_info=True)
            self._checked_at = now
