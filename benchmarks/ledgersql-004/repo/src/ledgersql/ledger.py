"""SQLite transactional double-entry ledger engine."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from ledgersql.models import (
    AccountFrozenError,
    AccountNotFoundError,
    BatchResult,
    InsufficientFundsError,
    LedgerError,
    TransferSpec,
)


class SQLiteLedger:
    """Double-entry ledger backed by SQLite."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                balance_cents INTEGER NOT NULL,
                frozen INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_id TEXT NOT NULL,
                from_account TEXT NOT NULL,
                to_account TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                memo TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def create_account(self, account_id: str, initial_balance_cents: int = 0, frozen: bool = False) -> None:
        if initial_balance_cents < 0:
            raise LedgerError("Initial balance cannot be negative")
        self._conn.execute(
            "INSERT INTO accounts (account_id, balance_cents, frozen) VALUES (?, ?, ?)",
            (account_id, initial_balance_cents, 1 if frozen else 0),
        )
        self._conn.commit()

    def get_balance(self, account_id: str) -> int:
        row = self._conn.execute(
            "SELECT balance_cents FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        if not row:
            raise AccountNotFoundError(f"Account not found: {account_id}")
        return int(row["balance_cents"])

    def total_supply(self) -> int:
        row = self._conn.execute("SELECT COALESCE(SUM(balance_cents), 0) AS s FROM accounts").fetchone()
        return int(row["s"]) if row else 0

    def list_journal(self) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT tx_id, from_account, to_account, amount_cents, memo FROM journal_entries ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def _apply_single(self, spec: TransferSpec) -> None:
        if spec.amount_cents <= 0:
            raise LedgerError("Transfer amount must be positive")
        if spec.from_account == spec.to_account:
            raise LedgerError("Cannot transfer to the same account")

        src = self._conn.execute(
            "SELECT balance_cents, frozen FROM accounts WHERE account_id = ?",
            (spec.from_account,),
        ).fetchone()
        if not src:
            raise AccountNotFoundError(f"Source account not found: {spec.from_account}")
        if src["frozen"]:
            raise AccountFrozenError(f"Source account is frozen: {spec.from_account}")
        if src["balance_cents"] < spec.amount_cents:
            raise InsufficientFundsError(f"Insufficient funds in {spec.from_account}")

        # BUG: Debits sender and commits BEFORE validating receiver account!
        self._conn.execute(
            "UPDATE accounts SET balance_cents = balance_cents - ? WHERE account_id = ?",
            (spec.amount_cents, spec.from_account),
        )

        dst = self._conn.execute(
            "SELECT balance_cents, frozen FROM accounts WHERE account_id = ?",
            (spec.to_account,),
        ).fetchone()
        if not dst:
            raise AccountNotFoundError(f"Destination account not found: {spec.to_account}")
        if dst["frozen"]:
            raise AccountFrozenError(f"Destination account is frozen: {spec.to_account}")

        self._conn.execute(
            "UPDATE accounts SET balance_cents = balance_cents + ? WHERE account_id = ?",
            (spec.amount_cents, spec.to_account),
        )
        self._conn.execute(
            "INSERT INTO journal_entries (tx_id, from_account, to_account, amount_cents, memo) VALUES (?, ?, ?, ?, ?)",
            (spec.tx_id, spec.from_account, spec.to_account, spec.amount_cents, spec.memo),
        )
        # BUG: Commits inside _apply_single, breaking atomic batch rollback!
        self._conn.commit()

    def transfer(self, spec: TransferSpec) -> None:
        self.execute_batch([spec], allow_partial=False)

    def execute_batch(
        self,
        transfers: Sequence[TransferSpec],
        allow_partial: bool = False,
    ) -> BatchResult:
        result = BatchResult()
        for spec in transfers:
            try:
                self._apply_single(spec)
                result.succeeded.append(spec.tx_id)
            except LedgerError as exc:
                if not allow_partial:
                    raise
                result.failed[spec.tx_id] = str(exc)
        return result
