"""Issue-specific FAIL_TO_PASS tests for ttlcachex-002."""

from ttlcachex import TTLCache


def test_get_many_filters_expired_entries_and_updates_stats():
    now = 50.0
    cache = TTLCache(maxsize=10, default_ttl=10.0, clock=lambda: now)
    cache.set("short", "val_short", ttl=5.0)
    cache.set("long", "val_long", ttl=20.0)

    now = 56.0  # 'short' is expired, 'long' is live
    batch = cache.get_many(["short", "long", "missing"])
    assert batch == {"long": "val_long"}
    assert cache.stats.hits == 1
    assert cache.stats.misses == 2
    assert cache.stats.expired_evictions == 1


def test_contains_respects_ttl_expiration():
    now = 10.0
    cache = TTLCache(maxsize=5, default_ttl=5.0, clock=lambda: now)
    cache.set("token", "abc")
    assert ("token" in cache) is True
    now = 15.0
    assert ("token" in cache) is False


def test_set_with_keep_ttl_preserves_remaining_lifetime():
    now = 100.0
    cache = TTLCache(maxsize=5, default_ttl=30.0, clock=lambda: now)
    cache.set("session", {"count": 1}, ttl=10.0)  # expires at 110.0

    now = 106.0
    cache.set("session", {"count": 2}, keep_ttl=True)
    assert cache.get("session") == {"count": 2}

    now = 111.0  # past original 110.0 expiry!
    assert cache.get("session") is None
