"""TTL + LRU cache implementation."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from ttlcachex.stats import CacheStats


@dataclass
class CacheEntry:
    value: Any
    expires_at: float | None

    def is_expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at


class TTLCache:
    """In-memory LRU cache with per-key TTL expiration and injectable clock."""

    def __init__(
        self,
        maxsize: int = 128,
        default_ttl: float | None = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be > 0")
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self._clock = clock
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self.stats = CacheStats()

    def _compute_expiry(self, now: float, ttl: float | None) -> float | None:
        effective = self.default_ttl if ttl is None else ttl
        if effective is None:
            return None
        return now + effective

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        keep_ttl: bool = False,
    ) -> None:
        now = self._clock()
        # BUG: ignores keep_ttl=True on existing live entry
        expires_at = self._compute_expiry(now, ttl)

        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = CacheEntry(value=value, expires_at=expires_at)
        self.stats.sets += 1

        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)
            self.stats.lru_evictions += 1

    def get(self, key: str, default: Any = None) -> Any:
        now = self._clock()
        entry = self._store.get(key)
        if entry is None:
            self.stats.misses += 1
            return default
        if entry.is_expired(now):
            del self._store[key]
            self.stats.expired_evictions += 1
            self.stats.misses += 1
            return default
        self._store.move_to_end(key)
        self.stats.hits += 1
        return entry.value

    def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        # BUG: does not check expiration or update stats/LRU properly for expired entries
        result: dict[str, Any] = {}
        for k in keys:
            if k in self._store:
                self.stats.hits += 1
                result[k] = self._store[k].value
            else:
                self.stats.misses += 1
        return result

    def __contains__(self, key: str) -> bool:
        # BUG: returns True for expired keys
        return key in self._store

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()
