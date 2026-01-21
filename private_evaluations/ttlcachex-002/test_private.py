"""Private evaluation tests for ttlcachex-002."""

from ttlcachex import TTLCache


def test_keep_ttl_on_already_expired_key_uses_new_default_ttl():
    now = 10.0
    cache = TTLCache(maxsize=5, default_ttl=20.0, clock=lambda: now)
    cache.set("k", "v1", ttl=5.0)  # expires at 15.0

    now = 16.0  # already expired
    cache.set("k", "v2", keep_ttl=True)  # should get new expiry 16 + 20 = 36.0
    now = 30.0
    assert cache.get("k") == "v2"
    now = 37.0
    assert cache.get("k") is None


def test_get_many_stores_none_values_without_confusion():
    now = 0.0
    cache = TTLCache(maxsize=5, default_ttl=10.0, clock=lambda: now)
    cache.set("nullable", None, ttl=10.0)
    res = cache.get_many(["nullable", "absent"])
    assert "nullable" in res
    assert res["nullable"] is None
    assert "absent" not in res
