"""Pre-existing preservation tests for ttlcachex."""

import pytest
from ttlcachex import TTLCache


def test_single_get_set_and_expiration():
    now = 100.0
    cache = TTLCache(maxsize=4, default_ttl=10.0, clock=lambda: now)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"
    now = 111.0
    assert cache.get("k1") is None
    assert cache.stats.expired_evictions == 1


def test_lru_eviction_order():
    now = 0.0
    cache = TTLCache(maxsize=2, default_ttl=100.0, clock=lambda: now)
    cache.set("a", 1)
    cache.set("b", 2)
    # Touch 'a' so 'b' becomes least-recently-used
    assert cache.get("a") == 1
    cache.set("c", 3)
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_delete_and_clear():
    cache = TTLCache(maxsize=3, default_ttl=50.0)
    cache.set("x", 42)
    assert cache.delete("x") is True
    assert cache.delete("x") is False
    cache.set("y", 99)
    cache.clear()
    assert cache.get("y") is None


def test_invalid_maxsize():
    with pytest.raises(ValueError):
        TTLCache(maxsize=0)
