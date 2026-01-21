"""Pre-existing preservation tests for ledgersql."""

import pytest
from ledgersql import InsufficientFundsError, SQLiteLedger, TransferSpec


def test_single_transfer_and_journal():
    ledger = SQLiteLedger()
    ledger.create_account("alice", 1000)
    ledger.create_account("bob", 500)
    ledger.transfer(TransferSpec("tx1", "alice", "bob", 300, "invoice"))
    assert ledger.get_balance("alice") == 700
    assert ledger.get_balance("bob") == 800
    journal = ledger.list_journal()
    assert len(journal) == 1
    assert journal[0]["tx_id"] == "tx1"


def test_insufficient_funds_single_transfer():
    ledger = SQLiteLedger()
    ledger.create_account("alice", 100)
    ledger.create_account("bob", 100)
    with pytest.raises(InsufficientFundsError):
        ledger.transfer(TransferSpec("tx_fail", "alice", "bob", 250))
    assert ledger.get_balance("alice") == 100
    assert ledger.get_balance("bob") == 100
