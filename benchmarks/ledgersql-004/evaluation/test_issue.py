"""Issue-specific FAIL_TO_PASS tests for ledgersql-004."""

import pytest
from ledgersql import AccountFrozenError, InsufficientFundsError, SQLiteLedger, TransferSpec


def test_atomic_batch_rolls_back_all_transfers_on_later_failure():
    ledger = SQLiteLedger()
    ledger.create_account("a", 1000)
    ledger.create_account("b", 1000)
    ledger.create_account("c", 100)

    batch = [
        TransferSpec("tx1", "a", "b", 400),
        TransferSpec("tx2", "b", "c", 200),
        TransferSpec("tx3", "c", "a", 500),  # fails: c only has 300 at this point
    ]
    with pytest.raises(InsufficientFundsError):
        ledger.execute_batch(batch, allow_partial=False)

    assert ledger.get_balance("a") == 1000
    assert ledger.get_balance("b") == 1000
    assert ledger.get_balance("c") == 100
    assert ledger.list_journal() == []


def test_partial_batch_savepoint_rolls_back_sender_debit_when_receiver_frozen():
    ledger = SQLiteLedger()
    ledger.create_account("alice", 1000)
    ledger.create_account("bob", 500)
    ledger.create_account("frozen_vault", 200, frozen=True)

    batch = [
        TransferSpec("tx1", "alice", "bob", 300),
        TransferSpec("tx2", "alice", "frozen_vault", 400),  # fails on frozen destination
        TransferSpec("tx3", "bob", "alice", 100),
    ]
    res = ledger.execute_batch(batch, allow_partial=True)
    assert res.succeeded == ["tx1", "tx3"]
    assert "tx2" in res.failed
    # Alice: 1000 - 300 + 100 = 800 (tx2's 400 debit MUST be rolled back!)
    assert ledger.get_balance("alice") == 800
    assert ledger.get_balance("bob") == 700
    assert ledger.get_balance("frozen_vault") == 200
    assert ledger.total_supply() == 1700
