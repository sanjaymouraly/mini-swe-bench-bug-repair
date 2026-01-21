"""Pre-existing preservation tests for concurqueue."""

import pytest
from concurqueue import KeyedResourcePool, QuotaConfigurationError, ReleaseError


def test_single_thread_lease_and_snapshot():
    pool = KeyedResourcePool(max_total=4, max_per_key=2)
    with pool.lease("tenant_a"):
        assert pool.total_active == 1
        assert pool.active_for_key("tenant_a") == 1
        assert pool.snapshot() == {"tenant_a": 1}
    assert pool.total_active == 0
    assert pool.active_for_key("tenant_a") == 0


def test_over_release_raises_release_error():
    pool = KeyedResourcePool(max_total=2, max_per_key=1)
    with pytest.raises(ReleaseError):
        pool.release("nonexistent")


def test_invalid_quota_configuration():
    with pytest.raises(QuotaConfigurationError):
        KeyedResourcePool(max_total=2, max_per_key=5)
