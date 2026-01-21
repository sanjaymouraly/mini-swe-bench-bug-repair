# `idempobox` — Fix idempotency payload mismatch detection, canonical fingerprinting, and failed lock cleanup

IdempotentProcessor silently returns cached results when an idempotency key is reused with a different payload, includes volatile trace headers in fingerprints, and leaves failed executions permanently locked in IN_PROGRESS.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
