"""Exceptions for concurqueue."""


class QuotaConfigurationError(ValueError):
    """Raised when pool limits are invalid."""


class PoolTimeoutError(TimeoutError):
    """Raised when a lease cannot be acquired before timeout."""


class ReleaseError(RuntimeError):
    """Raised when releasing a key that has no active leases."""
