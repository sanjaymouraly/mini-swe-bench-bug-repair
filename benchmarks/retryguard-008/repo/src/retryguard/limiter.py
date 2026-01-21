"""Token bucket rate limiter."""

from __future__ import annotations

import time
from collections.abc import Callable


class TokenBucketLimiter:
    """Token bucket rate limiter with injectable monotonic clock."""

    def __init__(
        self,
        rate_per_sec: float,
        capacity: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_sec <= 0 or capacity <= 0:
            raise ValueError("rate_per_sec and capacity must be > 0")
        self.rate_per_sec = rate_per_sec
        self.capacity = capacity
        self._clock = clock
        self._tokens = float(capacity)
        self._last_ts = self._clock()

    def _refill(self) -> None:
        # BUG: Uses time.time() instead of self._clock() and does not cap at self.capacity!
        now = time.time()
        elapsed = max(0.0, now - self._last_ts)
        self._last_ts = now
        self._tokens = self._tokens + elapsed * self.rate_per_sec

    def try_acquire(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens
