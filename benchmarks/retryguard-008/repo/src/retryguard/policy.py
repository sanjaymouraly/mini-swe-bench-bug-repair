"""Retry policy and HTTP error definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


class HTTPError(Exception):
    """Represents an HTTP status failure with optional Retry-After."""

    def __init__(self, status_code: int, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, attempts: int, last_exception: BaseException | None = None) -> None:
        super().__init__(f"Exhausted after {attempts} attempts: {last_exception}")
        self.attempts = attempts
        self.last_exception = last_exception


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_backoff: float = 0.5
    max_backoff: float = 10.0
    multiplier: float = 2.0
    retryable_status_codes: set[int] = field(
        default_factory=lambda: {408, 429, 500, 502, 503, 504}
    )

    def compute_delay(self, retry_index: int, retry_after: float | None = None) -> float:
        """Compute backoff delay for 0-indexed `retry_index`."""
        if retry_after is not None:
            # BUG: Does not clamp retry_after to max_backoff!
            return max(0.0, retry_after)
        raw = self.base_backoff * (self.multiplier**retry_index)
        return min(self.max_backoff, raw)
