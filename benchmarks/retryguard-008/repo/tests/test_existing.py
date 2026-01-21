"""Pre-existing preservation tests for retryguard."""

import pytest
from retryguard import RetryExecutor, RetryPolicy, TokenBucketLimiter


def test_immediate_success_on_first_try():
    exec_ = RetryExecutor(RetryPolicy(max_retries=2), sleep_fn=lambda _: None)
    assert exec_.execute(lambda: "ok") == "ok"
    assert exec_.sleep_history == []


def test_exponential_backoff_calculation():
    policy = RetryPolicy(base_backoff=1.0, multiplier=2.0, max_backoff=5.0)
    assert policy.compute_delay(0) == 1.0
    assert policy.compute_delay(1) == 2.0
    assert policy.compute_delay(2) == 4.0
    assert policy.compute_delay(3) == 5.0


def test_invalid_limiter_params():
    with pytest.raises(ValueError):
        TokenBucketLimiter(rate_per_sec=0, capacity=5)
