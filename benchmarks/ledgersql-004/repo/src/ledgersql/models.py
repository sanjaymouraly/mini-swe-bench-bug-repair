"""Domain models and exceptions for ledgersql."""

from __future__ import annotations

from dataclasses import dataclass, field


class LedgerError(Exception):
    """Base exception for ledger errors."""


class InsufficientFundsError(LedgerError):
    """Raised when an account balance would drop below zero."""


class AccountFrozenError(LedgerError):
    """Raised when attempting to debit or credit a frozen account."""


class AccountNotFoundError(LedgerError):
    """Raised when an account ID does not exist."""


@dataclass(frozen=True)
class TransferSpec:
    tx_id: str
    from_account: str
    to_account: str
    amount_cents: int
    memo: str = ""


@dataclass
class BatchResult:
    succeeded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
