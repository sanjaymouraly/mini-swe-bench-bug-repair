# `retryguard` — Fix max_retries off-by-one, Retry-After cap, non-retryable 4xx, and TokenBucket capacity ceiling

RetryExecutor makes max_retries total attempts instead of 1 + max_retries, sleeps after the final failure, ignores max_backoff on Retry-After, retries non-retryable 4xx errors, and allows TokenBucketLimiter to exceed capacity.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
