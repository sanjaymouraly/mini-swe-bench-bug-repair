"""Retry executor implementation."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from retryguard.policy import HTTPError, RetryExhaustedError, RetryPolicy

T = TypeVar("T")


class RetryExecutor:
    """Executes callables with configurable retry and backoff policy."""

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self._sleep = sleep_fn
        self.sleep_history: list[float] = []

    def execute(self, func: Callable[[], T]) -> T:
        last_exc: BaseException | None = None
        attempts = 0

        # BUG: Loops range(max_retries) instead of range(max_retries + 1),
        # retries non-retryable 4xx errors, and sleeps after the final failed attempt!
        for attempt in range(self.policy.max_retries):
            attempts += 1
            try:
                return func()
            except HTTPError as exc:
                last_exc = exc
                delay = self.policy.compute_delay(attempt, retry_after=exc.retry_after)
                self.sleep_history.append(delay)
                self._sleep(delay)
            except Exception as exc:
                last_exc = exc
                delay = self.policy.compute_delay(attempt)
                self.sleep_history.append(delay)
                self._sleep(delay)

        raise RetryExhaustedError(attempts=attempts, last_exception=last_exc)
