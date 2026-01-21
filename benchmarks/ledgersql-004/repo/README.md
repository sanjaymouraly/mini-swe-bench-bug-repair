# `ledgersql` — Fix atomic batch rollback and savepoint isolation in SQLiteLedger.execute_batch

SQLiteLedger commits intermediate transfers during atomic batches and leaves partial debit legs applied when a destination account check fails in partial batches.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
