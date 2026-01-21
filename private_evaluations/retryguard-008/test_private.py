"""Private evaluation tests for retryguard-008."""

from retryguard import HTTPError, RetryExecutor, RetryPolicy


def test_429_with_retry_after_succeeds_on_final_retry():
    attempts = 0

    def flaky_endpoint():
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise HTTPError(429, "Rate limited", retry_after=50.0)
        return {"status": 200}

    exec_ = RetryExecutor(RetryPolicy(max_retries=2, max_backoff=3.0), sleep_fn=lambda _: None)
    res = exec_.execute(flaky_endpoint)
    assert res == {"status": 200}
    assert attempts == 3
    assert exec_.sleep_history == [3.0, 3.0]
