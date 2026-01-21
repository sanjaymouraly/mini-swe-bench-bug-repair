# Issue: `TTLCache` serves stale expired items in `get_many()` / `__contains__()` and resets TTL on `keep_ttl=True`

## Description
`TTLCache` is an in-memory LRU+TTL cache with injectable monotonic clock support. We found three bugs:

1. **`get_many(keys)` ignores TTL expiration**:
   `get_many()` looks up keys directly in `self._store` without checking whether entries have expired at the current clock timestamp. Expired entries are returned to the caller, not evicted, and recorded as cache hits instead of misses/expirations.
2. **`key in cache` (`__contains__`) returns `True` for expired keys**:
   Checking `if k in cache:` returns `True` even after the key's TTL has elapsed, whereas `cache.get(k)` returns `None`. `__contains__` must evict expired entries and return `False` without incrementing hit/miss counters.
3. **`set(key, value, keep_ttl=True)` resets TTL instead of preserving remaining TTL**:
   When updating an existing **unexpired** entry with `keep_ttl=True` (and `ttl=None`), `set()` overwrites `expires_at` using `default_ttl` instead of keeping the existing entry's `expires_at`. If the existing entry was already expired (or did not exist), `keep_ttl=True` should fall back to `ttl` / `default_ttl`.

## Expected Behavior
- `get_many(keys)` must evict expired entries, increment `stats.misses` and `stats.expired_evictions` for expired keys, update LRU order and `stats.hits` for live keys, and return only live `{key: value}` pairs.
- `key in cache` must return `False` (and purge the expired entry) if the key is expired.
- `set(key, value, keep_ttl=True)` must preserve the existing `expires_at` timestamp when updating a currently live key.
