# Issue: `IdempotentProcessor` fails to detect altered payloads on key reuse, hashes volatile headers, and locks keys after handler failure

## Description
`IdempotentProcessor` ensures payment and webhook commands are executed at-most-once per `idempotency_key`. Three critical bugs exist:

1. **Silent payload mismatch on `COMPLETED` key reuse**:
   When a client retries with an existing `idempotency_key` that already `COMPLETED`, `process()` immediately returns `record.result` **without verifying that the new request's semantic fingerprint matches `record.fingerprint`**! If a client accidentally reuses key `"idem_123"` for a `$500` payment after a `$50` payment, it must raise `IdempotencyPayloadMismatchError`.
2. **Non-canonical fingerprinting & volatile metadata pollution**:
   `compute_payload_fingerprint(payload)` must recursively sort dictionary keys and ignore volatile transport metadata keys (`"_trace_id"`, `"_timestamp"`, `"_request_id"`) at any nesting level so that semantically identical retries with a new `_trace_id` or different dict key order produce the exact same SHA-256 fingerprint.
3. **Failed handler execution leaves key stuck in `IN_PROGRESS`**:
   When `handler(payload)` raises an exception, `process()` leaves the record in `IN_PROGRESS` state inside `self._records`. Subsequent retries with the same `idempotency_key` then fail with `IdempotencyConflictError("already in progress")` instead of being allowed to retry! Only genuinely concurrent in-flight executions should raise `IdempotencyConflictError`.

## Expected Behavior
- Replaying the same `idempotency_key` with an identical semantic payload (ignoring `_trace_id`, `_timestamp`, `_request_id` and dict key order) returns the cached result without re-invoking `handler`.
- Reusing an `idempotency_key` (whether `IN_PROGRESS` or `COMPLETED`) with a different semantic payload raises `IdempotencyPayloadMismatchError`.
- If `handler` raises an exception, the in-progress lock record is removed (or marked retryable) before re-raising the exception so a subsequent retry can execute.
