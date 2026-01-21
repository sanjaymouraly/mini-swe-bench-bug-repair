"""Exceptions for idempobox."""


class IdempotencyConflictError(RuntimeError):
    """Raised when a duplicate request arrives while the first is still IN_PROGRESS."""


class IdempotencyPayloadMismatchError(ValueError):
    """Raised when an idempotency key is reused with a different semantic payload."""
