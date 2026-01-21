"""Private conservation and boundary tests for ledgersql-004."""

import pytest
from ledgersql import AccountNotFoundError, LedgerError, SQLiteLedger, TransferSpec


def test_atomic_batch_rolls_back_when_destination_missing():
    ledger = SQLiteLedger()
    ledger.create_account("u1", 500)
    ledger.create_account("u2", 500)

    with pytest.raises(AccountNotFoundError):
        ledger.execute_batch(
            [
                TransferSpec("t1", "u1", "u2", 200),
                TransferSpec("t2", "u2", "ghost_account", 100),
            ],
            allow_partial=False,
        )
    assert ledger.get_balance("u1") == 500
    assert ledger.get_balance("u2") == 500
    assert ledger.total_supply() == 1000


def test_self_transfer_and_negative_amount_rejected_in_partial_batch():
    ledger = SQLiteLedger()
    ledger.create_account("u1", 500)
    ledger.create_account("u2", 500)
    res = ledger.execute_batch(
        [
            TransferSpec("bad_self", "u1", "u1", 100),
            TransferSpec("bad_neg", "u1", "u2", -50),
            TransferSpec("good", "u1", "u2", 150),
        ],
        allow_partial=True,
    )
    assert res.succeeded == ["good"]
    assert len(res.failed) == 2
    assert ledger.get_balance("u1") == 350
    assert ledger.get_balance("u2") == 650
