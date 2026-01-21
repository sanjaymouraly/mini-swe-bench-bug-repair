"""Issue-specific FAIL_TO_PASS tests for retryguard-008."""

import pytest
from retryguard import (
    HTTPError,
    RetryExecutor,
    RetryExhaustedError,
    RetryPolicy,
    TokenBucketLimiter,
)


def test_max_retries_zero_executes_once_and_max_retries_three_executes_four_times():
    calls = 0

    def fail_always():
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    exec0 = RetryExecutor(RetryPolicy(max_retries=0), sleep_fn=lambda _: None)
    with pytest.raises(RetryExhaustedError) as exc_info:
        exec0.execute(fail_always)
    assert calls == 1
    assert exc_info.value.attempts == 1
    assert exec0.sleep_history == []

    calls = 0
    exec3 = RetryExecutor(RetryPolicy(max_retries=3, base_backoff=0.5), sleep_fn=lambda _: None)
    with pytest.raises(RetryExhaustedError) as exc_info3:
        exec3.execute(fail_always)
    assert calls == 4
    assert exc_info3.value.attempts == 4
    # Must sleep only 3 times (between the 4 attempts), NOT after the 4th attempt!
    assert len(exec3.sleep_history) == 3


def test_non_retryable_4xx_aborts_immediately_and_retry_after_is_capped():
    calls = 0

    def bad_request():
        nonlocal calls
        calls += 1
        raise HTTPError(400, "Bad Request")

    exec_ = RetryExecutor(RetryPolicy(max_retries=3), sleep_fn=lambda _: None)
    with pytest.raises(HTTPError) as err:
        exec_.execute(bad_request)
    assert err.value.status_code == 400
    assert calls == 1

    # Retry-After=120s must be capped to max_backoff=5.0s
    policy = RetryPolicy(max_retries=2, max_backoff=5.0)
    assert policy.compute_delay(0, retry_after=120.0) == 5.0


def test_token_bucket_uses_injected_clock_and_caps_at_capacity():
    now = 100.0
    limiter = TokenBucketLimiter(rate_per_sec=2.0, capacity=4.0, clock=lambda: now)
    assert limiter.try_acquire(3.0) is True
    assert limiter.available_tokens == 1.0

    # Advance 100 seconds: tokens must cap at capacity=4.0, not 201.0!
    now = 200.0
    assert limiter.available_tokens == 4.0
