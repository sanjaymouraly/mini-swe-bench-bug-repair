# Issue: `RetryExecutor` off-by-one attempts, trailing sleep, uncapped `Retry-After`, and `TokenBucketLimiter` overflow

## Description
`retryguard` provides `RetryExecutor` and `TokenBucketLimiter`. Four bugs were reported:

1. **Off-by-one attempt count & trailing sleep in `RetryExecutor.execute`**:
   `max_retries` specifies the number of **retries after the initial attempt** (so `max_retries=0` means 1 attempt total; `max_retries=3` means up to 4 attempts total). Currently `execute()` loops `for attempt in range(self.policy.max_retries):` (making 0 attempts when `max_retries=0`!) and calls `self._sleep(delay)` even after the final failed attempt before raising `RetryExhaustedError`.
2. **Non-retryable HTTP status codes (`400`, `401`, `403`, `404`) are retried**:
   When `HTTPError` is raised with a status code not in `policy.retryable_status_codes` (default `{408, 429, 500, 502, 503, 504}`), `RetryExecutor` should immediately re-raise the `HTTPError` without sleeping or retrying.
3. **`Retry-After` header ignores `policy.max_backoff` cap**:
   When `HTTPError(status_code=429, retry_after=300.0)` is caught, `compute_delay` uses `retry_after` directly without clamping to `min(retry_after, self.policy.max_backoff)`.
4. **`TokenBucketLimiter` uses `time.time()` instead of injected clock and exceeds `capacity`**:
   `_refill()` uses `time.time()` instead of `self._clock()` and adds refilled tokens without clamping to `min(self.capacity, self._tokens + added)`.

## Expected Behavior
- `max_retries=N` runs 1 initial attempt plus up to `N` retries, sleeping only between attempts (never after the last failed attempt).
- Non-retryable `HTTPError` status codes re-raise immediately on the first failure.
- `Retry-After` backoff is clamped to `[0.0, policy.max_backoff]`.
- `TokenBucketLimiter` uses `self._clock()` and never accumulates more than `self.capacity` tokens.
