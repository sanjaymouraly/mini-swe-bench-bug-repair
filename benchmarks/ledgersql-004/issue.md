# Issue: `SQLiteLedger.execute_batch` leaves partial transfers committed on failure

## Description
`SQLiteLedger` manages double-entry account balances and journal entries in SQLite. `execute_batch(transfers, allow_partial=False)` has two transaction-integrity bugs:

1. **Atomic Batch (`allow_partial=False`) does not roll back earlier transfers**:
   `_apply_transfer()` calls `self._conn.commit()` after each transfer (and updates the sender's balance before verifying whether the recipient account is frozen or missing). When transfer #3 in a 4-transfer atomic batch fails (`InsufficientFundsError` or `AccountFrozenError`), transfers #1 and #2 (plus the sender debit of transfer #3!) remain committed in SQLite! An atomic batch with `allow_partial=False` must be all-or-nothing: if any transfer fails, the entire batch must be rolled back and the exception re-raised.
2. **Partial Batch (`allow_partial=True`) leaves half-applied debit leg on recipient failure**:
   When `allow_partial=True`, each individual transfer in the batch should be isolated in its own SQLite `SAVEPOINT` (or validated atomically). Currently, if the sender has sufficient funds, the sender's balance is debited in SQLite before checking if the destination account is frozen; when `AccountFrozenError` is caught in `allow_partial=True`, the sender's debit is never rolled back, destroying money conservation!

## Expected Behavior
- When `allow_partial=False`, if any transfer in `transfers` fails, zero balance changes or `journal_entries` from the batch may persist in SQLite, and the `LedgerError` must be raised.
- When `allow_partial=True`, each failed transfer must roll back its own changes completely (using a `SAVEPOINT`) while valid transfers in the same batch succeed and commit.
- Total money across all accounts must remain strictly conserved across any combination of valid and invalid transfers.
