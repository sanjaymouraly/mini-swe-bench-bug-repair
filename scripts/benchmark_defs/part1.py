"""Benchmark task definitions 001 to 004."""

from __future__ import annotations

from typing import Any

TASKS_PART1: list[dict[str, Any]] = [
    # =========================================================================
    # TASK 001: pagiflow-001 (Easy — Pagination and incorrect API response handling)
    # =========================================================================
    {
        "task_id": "pagiflow-001",
        "title": "Fix cursor=0 falsy termination and has_more=False echo loops in PaginatedCollector",
        "difficulty": "easy",
        "category": "pagination_api",
        "package_name": "pagiflow",
        "summary": "PaginatedCollector stops early when next_cursor is integer 0, loops extra pages when has_more=False echoes a cursor token, and aborts on empty intermediate pages.",
        "allowed_files": [
            "src/pagiflow/client.py",
            "src/pagiflow/cursor.py",
            "src/pagiflow/models.py",
        ],
        "issue_md": """# Issue: `PaginatedCollector.collect_all` drops pages on `next_cursor=0` and loops when `has_more=False` echoes last cursor

## Description
We use `PaginatedCollector` to harvest records from cursor-paginated and offset-paginated REST endpoints. Three bugs occur in production:

1. **Integer `0` cursor treated as falsy (`if not envelope.next_cursor:`)**:
   Some APIs use 0-indexed numeric cursors where page 1 returns `{"items": [...], "next_cursor": 0, "has_more": true}`. Because `0` is falsy in Python, `collect_all` treats `next_cursor=0` as "no cursor" and terminates prematurely after the first page. Note: empty string `""` or `None` means no cursor, whereas integer `0` or string `"0"` is a valid cursor!
2. **Echoed `next_cursor` when `has_more=False`**:
   Several APIs return the last cursor token in `next_cursor` even on the terminal page where `has_more=False` (e.g., `{"items": [...], "next_cursor": "cur_final", "has_more": false}`). `collect_all` checks `envelope.next_cursor` without respecting `envelope.has_more is False`, causing it to keep fetching until `max_pages` is exhausted or a cyclic cursor error is raised.
3. **Filtered empty intermediate page (`items=[]` with `has_more=True`)**:
   When `stop_on_empty_page=False` (the default), a server-side filtered page may return `items=[]` while `has_more=True` and a valid `next_cursor` is present. Currently `collect_all` breaks immediately whenever `not envelope.items`, ignoring `stop_on_empty_page=False`.

## Expected Behavior
- When `envelope.has_more` is explicitly `False`, pagination must stop after processing the current page's items.
- Integer `0` and string `"0"` must be treated as valid non-empty cursors (`next_cursor is not None and next_cursor != ""`).
- When `envelope.items` is empty (`[]`), pagination should only stop if `config.stop_on_empty_page` is `True` OR if there is no next page (`not envelope.has_more` or no valid `next_cursor`).
- Existing deduplication (`id_key`), item transformation, and cycle detection must continue working without regression.
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/pagiflow/__init__.py": '''"""pagiflow: Resilient REST API pagination collector."""

from pagiflow.client import PaginatedCollector
from pagiflow.cursor import normalize_envelope
from pagiflow.models import PageEnvelope, PaginationConfig, PaginationError

__all__ = [
    "PageEnvelope",
    "PaginatedCollector",
    "PaginationConfig",
    "PaginationError",
    "normalize_envelope",
]
''',
            "src/pagiflow/models.py": '''"""Data models for pagiflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PaginationError(Exception):
    """Raised when pagination encounters a cycle or malformed response."""


@dataclass
class PaginationConfig:
    max_pages: int = 100
    id_key: str | None = "id"
    deduplicate: bool = True
    stop_on_empty_page: bool = False
    detect_cycles: bool = True


@dataclass
class PageEnvelope:
    items: list[dict[str, Any]] = field(default_factory=list)
    next_cursor: str | int | None = None
    has_more: bool | None = None
    total_count: int | None = None
''',
            "src/pagiflow/cursor.py": '''"""Envelope normalization utilities."""

from __future__ import annotations

from typing import Any

from pagiflow.models import PageEnvelope, PaginationError


def normalize_envelope(raw: dict[str, Any]) -> PageEnvelope:
    """Normalize diverse REST API response envelopes into a PageEnvelope."""
    if not isinstance(raw, dict):
        raise PaginationError(f"Expected dict response envelope, got {type(raw).__name__}")

    if "items" in raw and isinstance(raw["items"], list):
        items = raw["items"]
    elif "data" in raw and isinstance(raw["data"], list):
        items = raw["data"]
    elif "results" in raw and isinstance(raw["results"], list):
        items = raw["results"]
    else:
        raise PaginationError("Envelope missing 'items', 'data', or 'results' list")

    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    next_cursor = raw.get("next_cursor", meta.get("next_cursor"))
    has_more = raw.get("has_more", meta.get("has_more"))
    total_count = raw.get("total_count", meta.get("total_count"))

    return PageEnvelope(
        items=list(items),
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
    )
''',
            "src/pagiflow/client.py": '''"""Paginated API collector implementation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pagiflow.cursor import normalize_envelope
from pagiflow.models import PaginationConfig, PaginationError

FetchFunc = Callable[[str | int | None], dict[str, Any]]
TransformFunc = Callable[[dict[str, Any]], dict[str, Any]]


class PaginatedCollector:
    """Collects items across paginated API responses with deduplication and cycle protection."""

    def __init__(
        self,
        config: PaginationConfig | None = None,
        transform: TransformFunc | None = None,
    ) -> None:
        self.config = config or PaginationConfig()
        self.transform = transform
        self.pages_fetched: int = 0

    def collect_all(
        self,
        fetch_page: FetchFunc,
        initial_cursor: str | int | None = None,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        seen_ids: set[Any] = set()
        seen_cursors: set[str] = set()
        cursor: str | int | None = initial_cursor
        self.pages_fetched = 0

        while self.pages_fetched < self.config.max_pages:
            if cursor is not None and cursor != "":
                cursor_key = f"{type(cursor).__name__}:{cursor}"
                if self.config.detect_cycles and cursor_key in seen_cursors:
                    raise PaginationError(f"Detected pagination cursor cycle at {cursor!r}")
                seen_cursors.add(cursor_key)

            raw = fetch_page(cursor)
            envelope = normalize_envelope(raw)
            self.pages_fetched += 1

            # BUG 1: Unconditionally breaks on empty items, ignoring stop_on_empty_page=False
            if not envelope.items:
                break

            for item in envelope.items:
                processed = self.transform(item) if self.transform else item
                if self.config.deduplicate and self.config.id_key and self.config.id_key in processed:
                    item_id = processed[self.config.id_key]
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                collected.append(processed)

            # BUG 2 & 3: Ignores explicit has_more=False when next_cursor is echoed,
            # and uses truthiness `if not envelope.next_cursor:` which fails on integer 0!
            if not envelope.next_cursor:
                break

            cursor = envelope.next_cursor

        return collected
''',
        },
        "reference_files": {
            "src/pagiflow/client.py": '''"""Paginated API collector implementation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pagiflow.cursor import normalize_envelope
from pagiflow.models import PaginationConfig, PaginationError

FetchFunc = Callable[[str | int | None], dict[str, Any]]
TransformFunc = Callable[[dict[str, Any]], dict[str, Any]]


def _has_valid_cursor(cursor: str | int | None) -> bool:
    if cursor is None:
        return False
    if isinstance(cursor, str) and cursor == "":
        return False
    return True


class PaginatedCollector:
    """Collects items across paginated API responses with deduplication and cycle protection."""

    def __init__(
        self,
        config: PaginationConfig | None = None,
        transform: TransformFunc | None = None,
    ) -> None:
        self.config = config or PaginationConfig()
        self.transform = transform
        self.pages_fetched: int = 0

    def collect_all(
        self,
        fetch_page: FetchFunc,
        initial_cursor: str | int | None = None,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        seen_ids: set[Any] = set()
        seen_cursors: set[str] = set()
        cursor: str | int | None = initial_cursor
        self.pages_fetched = 0

        while self.pages_fetched < self.config.max_pages:
            if _has_valid_cursor(cursor):
                cursor_key = f"{type(cursor).__name__}:{cursor}"
                if self.config.detect_cycles and cursor_key in seen_cursors:
                    raise PaginationError(f"Detected pagination cursor cycle at {cursor!r}")
                seen_cursors.add(cursor_key)

            raw = fetch_page(cursor)
            envelope = normalize_envelope(raw)
            self.pages_fetched += 1

            if not envelope.items and self.config.stop_on_empty_page:
                break

            for item in envelope.items:
                processed = self.transform(item) if self.transform else item
                if self.config.deduplicate and self.config.id_key and self.config.id_key in processed:
                    item_id = processed[self.config.id_key]
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                collected.append(processed)

            if envelope.has_more is False:
                break

            if not _has_valid_cursor(envelope.next_cursor):
                break

            cursor = envelope.next_cursor

        return collected
''',
        },
        "incomplete_files": {
            "src/pagiflow/client.py": '''"""Paginated API collector implementation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pagiflow.cursor import normalize_envelope
from pagiflow.models import PaginationConfig, PaginationError

FetchFunc = Callable[[str | int | None], dict[str, Any]]
TransformFunc = Callable[[dict[str, Any]], dict[str, Any]]


class PaginatedCollector:
    """Collects items across paginated API responses with deduplication and cycle protection."""

    def __init__(
        self,
        config: PaginationConfig | None = None,
        transform: TransformFunc | None = None,
    ) -> None:
        self.config = config or PaginationConfig()
        self.transform = transform
        self.pages_fetched: int = 0

    def collect_all(
        self,
        fetch_page: FetchFunc,
        initial_cursor: str | int | None = None,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        seen_ids: set[Any] = set()
        seen_cursors: set[str] = set()
        cursor: str | int | None = initial_cursor
        self.pages_fetched = 0

        while self.pages_fetched < self.config.max_pages:
            if cursor is not None and cursor != "":
                cursor_key = f"{type(cursor).__name__}:{cursor}"
                if self.config.detect_cycles and cursor_key in seen_cursors:
                    raise PaginationError(f"Detected pagination cursor cycle at {cursor!r}")
                seen_cursors.add(cursor_key)

            raw = fetch_page(cursor)
            envelope = normalize_envelope(raw)
            self.pages_fetched += 1

            for item in envelope.items:
                processed = self.transform(item) if self.transform else item
                if self.config.deduplicate and self.config.id_key and self.config.id_key in processed:
                    item_id = processed[self.config.id_key]
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                collected.append(processed)

            if envelope.has_more is False:
                break

            # Still buggy on integer 0 cursor!
            if not envelope.next_cursor:
                break

            cursor = envelope.next_cursor

        return collected
''',
        },
        "regression_files": {
            "src/pagiflow/client.py": '''"""Paginated API collector implementation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pagiflow.cursor import normalize_envelope
from pagiflow.models import PaginationConfig

FetchFunc = Callable[[str | int | None], dict[str, Any]]
TransformFunc = Callable[[dict[str, Any]], dict[str, Any]]


class PaginatedCollector:
    """Collects items across paginated API responses."""

    def __init__(
        self,
        config: PaginationConfig | None = None,
        transform: TransformFunc | None = None,
    ) -> None:
        self.config = config or PaginationConfig()
        self.transform = transform
        self.pages_fetched: int = 0

    def collect_all(
        self,
        fetch_page: FetchFunc,
        initial_cursor: str | int | None = None,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        cursor: str | int | None = initial_cursor
        self.pages_fetched = 0

        while self.pages_fetched < self.config.max_pages:
            raw = fetch_page(cursor)
            envelope = normalize_envelope(raw)
            self.pages_fetched += 1

            # Regression: stripped deduplication, transform, and cycle detection!
            collected.extend(envelope.items)

            if envelope.has_more is False:
                break
            if envelope.next_cursor is None or envelope.next_cursor == "":
                break
            cursor = envelope.next_cursor

        return collected
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for pagiflow."""

import pytest
from pagiflow import PaginatedCollector, PaginationConfig, PaginationError, normalize_envelope


def test_standard_string_cursor_traversal():
    pages = {
        None: {"items": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}], "next_cursor": "c2", "has_more": True},
        "c2": {"items": [{"id": 3, "name": "c"}], "next_cursor": None, "has_more": False},
    }
    collector = PaginatedCollector()
    res = collector.collect_all(lambda c: pages[c])
    assert [r["id"] for r in res] == [1, 2, 3]
    assert collector.pages_fetched == 2


def test_deduplication_across_pages():
    pages = {
        None: {"data": [{"id": 10}, {"id": 20}], "next_cursor": "p2"},
        "p2": {"data": [{"id": 20}, {"id": 30}], "next_cursor": None},
    }
    collector = PaginatedCollector(PaginationConfig(deduplicate=True, id_key="id"))
    res = collector.collect_all(lambda c: pages[c])
    assert [r["id"] for r in res] == [10, 20, 30]


def test_transform_callback_and_cycle_detection():
    pages = {
        None: {"results": [{"id": 1, "val": 5}], "next_cursor": "loop"},
        "loop": {"results": [{"id": 2, "val": 6}], "next_cursor": "loop"},
    }
    collector = PaginatedCollector(transform=lambda x: {**x, "val": x["val"] * 2})
    with pytest.raises(PaginationError, match="cycle"):
        collector.collect_all(lambda c: pages[c])


def test_normalize_envelope_errors():
    with pytest.raises(PaginationError):
        normalize_envelope({"unexpected": 123})
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for pagiflow-001."""

from pagiflow import PaginatedCollector, PaginationConfig


def test_integer_zero_cursor_is_followed():
    pages = {
        None: {"items": [{"id": "a"}], "next_cursor": 0, "has_more": True},
        0: {"items": [{"id": "b"}], "next_cursor": 1, "has_more": True},
        1: {"items": [{"id": "c"}], "next_cursor": None, "has_more": False},
    }
    collector = PaginatedCollector()
    items = collector.collect_all(lambda c: pages[c])
    assert [i["id"] for i in items] == ["a", "b", "c"]
    assert collector.pages_fetched == 3


def test_has_more_false_stops_even_when_cursor_echoed():
    call_count = 0

    def fetch(cursor):
        nonlocal call_count
        call_count += 1
        if cursor is None:
            return {"items": [{"id": 1}], "next_cursor": "cur_1", "has_more": True}
        return {"items": [{"id": 2}], "next_cursor": "cur_1_echo", "has_more": False}

    collector = PaginatedCollector(PaginationConfig(max_pages=10))
    items = collector.collect_all(fetch)
    assert [i["id"] for i in items] == [1, 2]
    assert call_count == 2


def test_empty_intermediate_page_continues_when_has_more_true():
    pages = {
        None: {"items": [{"id": 1}], "next_cursor": "filtered_empty", "has_more": True},
        "filtered_empty": {"items": [], "next_cursor": "final_page", "has_more": True},
        "final_page": {"items": [{"id": 2}], "next_cursor": None, "has_more": False},
    }
    collector = PaginatedCollector(PaginationConfig(stop_on_empty_page=False))
    items = collector.collect_all(lambda c: pages[c])
    assert [i["id"] for i in items] == [1, 2]
    assert collector.pages_fetched == 3
''',
        "private_tests": '''"""Private adversarial evaluation tests for pagiflow-001."""

from pagiflow import PaginatedCollector, PaginationConfig


def test_string_zero_cursor_and_stop_on_empty_true():
    pages = {
        None: {"items": [{"id": 100}], "next_cursor": "0", "has_more": True},
        "0": {"items": [{"id": 200}], "next_cursor": "", "has_more": False},
    }
    collector = PaginatedCollector()
    res = collector.collect_all(lambda c: pages[c])
    assert [r["id"] for r in res] == [100, 200]

    # When stop_on_empty_page=True, an empty intermediate page MUST stop immediately
    pages_stop = {
        None: {"items": [], "next_cursor": "next", "has_more": True},
        "next": {"items": [{"id": 999}], "next_cursor": None, "has_more": False},
    }
    c2 = PaginatedCollector(PaginationConfig(stop_on_empty_page=True))
    assert c2.collect_all(lambda c: pages_stop[c]) == []
    assert c2.pages_fetched == 1


def test_nested_meta_envelope_with_zero_cursor():
    pages = {
        None: {"data": [{"id": 1}], "meta": {"next_cursor": 0, "has_more": True}},
        0: {"data": [{"id": 2}], "meta": {"next_cursor": 0, "has_more": False}},
    }
    collector = PaginatedCollector()
    res = collector.collect_all(lambda c: pages[c])
    assert [r["id"] for r in res] == [1, 2]
    assert collector.pages_fetched == 2
''',
    },
    # =========================================================================
    # TASK 002: ttlcachex-002 (Easy — Cache expiration and stale data)
    # =========================================================================
    {
        "task_id": "ttlcachex-002",
        "title": "Fix stale expired entries in get_many/__contains__ and preserve TTL on keep_ttl=True",
        "difficulty": "easy",
        "category": "cache_expiration",
        "package_name": "ttlcachex",
        "summary": "TTLCache returns expired entries in get_many() and `key in cache`, miscounts hit/miss metrics on expired batch reads, and overwrites remaining TTL when set(..., keep_ttl=True) is called.",
        "allowed_files": ["src/ttlcachex/cache.py", "src/ttlcachex/stats.py"],
        "issue_md": """# Issue: `TTLCache` serves stale expired items in `get_many()` / `__contains__()` and resets TTL on `keep_ttl=True`

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
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/ttlcachex/__init__.py": '''"""ttlcachex: In-memory TTL + LRU cache with batch operations and telemetry."""

from ttlcachex.cache import CacheEntry, TTLCache
from ttlcachex.stats import CacheStats

__all__ = ["CacheEntry", "CacheStats", "TTLCache"]
''',
            "src/ttlcachex/stats.py": '''"""Cache telemetry statistics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    lru_evictions: int = 0
    expired_evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total > 0 else 0.0
''',
            "src/ttlcachex/cache.py": '''"""TTL + LRU cache implementation."""

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
''',
        },
        "reference_files": {
            "src/ttlcachex/cache.py": '''"""TTL + LRU cache implementation."""

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
        existing = self._store.get(key)
        if existing is not None and existing.is_expired(now):
            del self._store[key]
            self.stats.expired_evictions += 1
            existing = None

        if keep_ttl and existing is not None and ttl is None:
            expires_at = existing.expires_at
        else:
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
        result: dict[str, Any] = {}
        for k in keys:
            marker = object()
            val = self.get(k, default=marker)
            if val is not marker:
                result[k] = val
        return result

    def __contains__(self, key: str) -> bool:
        now = self._clock()
        entry = self._store.get(key)
        if entry is None:
            return False
        if entry.is_expired(now):
            del self._store[key]
            self.stats.expired_evictions += 1
            return False
        return True

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()
''',
        },
        "incomplete_files": {
            "src/ttlcachex/cache.py": '''"""TTL + LRU cache implementation."""

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
        # Incomplete fix: still ignores keep_ttl!
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
        result: dict[str, Any] = {}
        for k in keys:
            marker = object()
            val = self.get(k, default=marker)
            if val is not marker:
                result[k] = val
        return result

    def __contains__(self, key: str) -> bool:
        now = self._clock()
        entry = self._store.get(key)
        return entry is not None and not entry.is_expired(now)

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()
''',
        },
        "regression_files": {
            "src/ttlcachex/cache.py": '''"""TTL + LRU cache implementation."""

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
        existing = self._store.get(key)
        if keep_ttl and existing is not None and not existing.is_expired(now) and ttl is None:
            expires_at = existing.expires_at
        else:
            expires_at = self._compute_expiry(now, ttl)

        self._store[key] = CacheEntry(value=value, expires_at=expires_at)
        self.stats.sets += 1

        while len(self._store) > self.maxsize:
            # REGRESSION: evicts most-recently-inserted item (last=True) instead of LRU (last=False)!
            self._store.popitem(last=True)
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
        result: dict[str, Any] = {}
        for k in keys:
            marker = object()
            val = self.get(k, default=marker)
            if val is not marker:
                result[k] = val
        return result

    def __contains__(self, key: str) -> bool:
        now = self._clock()
        entry = self._store.get(key)
        if entry is None or entry.is_expired(now):
            self._store.pop(key, None)
            return False
        return True

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for ttlcachex."""

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
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for ttlcachex-002."""

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
''',
        "private_tests": '''"""Private evaluation tests for ttlcachex-002."""

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
''',
    },
    # =========================================================================
    # TASK 003: concurqueue-003 (Hard — Concurrent access and race conditions)
    # =========================================================================
    {
        "task_id": "concurqueue-003",
        "title": "Fix check-then-act race condition and lost wakeups in KeyedResourcePool",
        "difficulty": "hard",
        "category": "concurrency_races",
        "package_name": "concurqueue",
        "summary": "KeyedResourcePool checks and mutates active lease counters outside a synchronized while-loop and uses single notify(), causing quota overruns and deadlocks under concurrent contention.",
        "allowed_files": ["src/concurqueue/pool.py", "src/concurqueue/exceptions.py"],
        "issue_md": """# Issue: Race conditions and lost wakeups in `KeyedResourcePool.acquire` / `release`

## Description
`KeyedResourcePool` coordinates concurrent worker leases with both a global concurrency limit (`max_total`) and a per-tenant key limit (`max_per_key`). Under multi-threaded load, three concurrency bugs occur:

1. **Unsynchronized check-then-act & `if` instead of `while` wait loop**:
   `acquire()` checks capacity outside a `while` loop on `self._cond`, and sleeps briefly before incrementing `_total_active` and `_key_counts[key]`. When multiple threads contend on the same key or wake up simultaneously, both `max_per_key` and `max_total` are exceeded.
2. **Deadline drift & timeout failure**:
   When waiting with a `timeout`, `acquire()` must recompute remaining time (`deadline - time.monotonic()`) inside the `while` loop and raise `PoolTimeoutError` immediately if `remaining <= 0` when capacity is still unavailable.
3. **Lost wakeups on `release()` (`notify()` instead of `notify_all()`) and unvalidated release**:
   When a thread waiting on key `"A"` is at the head of the condition queue (blocked by `max_per_key` for `"A"`) and a slot for key `"B"` is released (freeing global capacity for a thread waiting on `"B"`), calling `self._cond.notify()` only wakes the blocked `"A"` thread, leaving the `"B"` thread stuck until timeout! `release()` must hold `self._cond`, validate that the key actually has an active lease (raising `ReleaseError` if not), decrement counts safely, and call `self._cond.notify_all()`.

## Expected Behavior
- At no point may `active_for_key(key) > max_per_key` or `total_active > max_total`, even under high multi-threaded contention.
- Peak concurrency trackers (`peak_total`, `peak_per_key[key]`) must accurately reflect synchronized state.
- Releasing an unacquired or already-released key must raise `ReleaseError`.
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/concurqueue/__init__.py": '''"""concurqueue: Thread-safe keyed concurrency limiter and resource pool."""

from concurqueue.exceptions import PoolTimeoutError, QuotaConfigurationError, ReleaseError
from concurqueue.pool import KeyedResourcePool, LeaseContext

__all__ = [
    "KeyedResourcePool",
    "LeaseContext",
    "PoolTimeoutError",
    "QuotaConfigurationError",
    "ReleaseError",
]
''',
            "src/concurqueue/exceptions.py": '''"""Exceptions for concurqueue."""


class QuotaConfigurationError(ValueError):
    """Raised when pool limits are invalid."""


class PoolTimeoutError(TimeoutError):
    """Raised when a lease cannot be acquired before timeout."""


class ReleaseError(RuntimeError):
    """Raised when releasing a key that has no active leases."""
''',
            "src/concurqueue/pool.py": '''"""Keyed concurrency pool implementation."""

from __future__ import annotations

import threading
import time
from types import TracebackType

from concurqueue.exceptions import PoolTimeoutError, QuotaConfigurationError, ReleaseError


class LeaseContext:
    """Context manager for an acquired key lease."""

    def __init__(self, pool: KeyedResourcePool, key: str, timeout: float | None = None) -> None:
        self.pool = pool
        self.key = key
        self.timeout = timeout
        self._acquired = False

    def __enter__(self) -> LeaseContext:
        self.pool.acquire(self.key, timeout=self.timeout)
        self._acquired = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._acquired:
            self._acquired = False
            self.pool.release(self.key)


class KeyedResourcePool:
    """Coordinates global and per-key concurrency quotas across threads."""

    def __init__(self, max_total: int = 10, max_per_key: int = 2) -> None:
        if max_total <= 0 or max_per_key <= 0 or max_per_key > max_total:
            raise QuotaConfigurationError(
                "max_total and max_per_key must be > 0 and max_per_key <= max_total"
            )
        self.max_total = max_total
        self.max_per_key = max_per_key
        self._cond = threading.Condition()
        self._total_active = 0
        self._key_counts: dict[str, int] = {}
        self.peak_total = 0
        self.peak_per_key: dict[str, int] = {}

    def _can_acquire(self, key: str) -> bool:
        return (
            self._total_active < self.max_total
            and self._key_counts.get(key, 0) < self.max_per_key
        )

    def acquire(self, key: str, timeout: float | None = None) -> bool:
        # BUG: Checks capacity with `if` instead of `while`, and mutates state outside lock!
        with self._cond:
            if not self._can_acquire(key):
                waited = self._cond.wait(timeout=timeout)
                if not waited and not self._can_acquire(key):
                    raise PoolTimeoutError(f"Timed out acquiring lease for key={key!r}")

        # Race window outside lock!
        time.sleep(0.0005)
        cur_key = self._key_counts.get(key, 0) + 1
        self._key_counts[key] = cur_key
        self._total_active += 1
        if self._total_active > self.peak_total:
            self.peak_total = self._total_active
        if cur_key > self.peak_per_key.get(key, 0):
            self.peak_per_key[key] = cur_key
        return True

    def release(self, key: str) -> None:
        # BUG: Mutates without lock, does not validate over-release, and uses single notify()
        cur = self._key_counts.get(key, 0)
        if cur <= 0:
            raise ReleaseError(f"Key {key!r} has no active leases to release")
        self._key_counts[key] = cur - 1
        self._total_active -= 1
        with self._cond:
            self._cond.notify()

    def lease(self, key: str, timeout: float | None = None) -> LeaseContext:
        return LeaseContext(self, key, timeout=timeout)

    def active_for_key(self, key: str) -> int:
        with self._cond:
            return self._key_counts.get(key, 0)

    @property
    def total_active(self) -> int:
        with self._cond:
            return self._total_active

    def snapshot(self) -> dict[str, int]:
        with self._cond:
            return {k: v for k, v in self._key_counts.items() if v > 0}
''',
        },
        "reference_files": {
            "src/concurqueue/pool.py": '''"""Keyed concurrency pool implementation."""

from __future__ import annotations

import threading
import time
from types import TracebackType

from concurqueue.exceptions import PoolTimeoutError, QuotaConfigurationError, ReleaseError


class LeaseContext:
    """Context manager for an acquired key lease."""

    def __init__(self, pool: KeyedResourcePool, key: str, timeout: float | None = None) -> None:
        self.pool = pool
        self.key = key
        self.timeout = timeout
        self._acquired = False

    def __enter__(self) -> LeaseContext:
        self.pool.acquire(self.key, timeout=self.timeout)
        self._acquired = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._acquired:
            self._acquired = False
            self.pool.release(self.key)


class KeyedResourcePool:
    """Coordinates global and per-key concurrency quotas across threads."""

    def __init__(self, max_total: int = 10, max_per_key: int = 2) -> None:
        if max_total <= 0 or max_per_key <= 0 or max_per_key > max_total:
            raise QuotaConfigurationError(
                "max_total and max_per_key must be > 0 and max_per_key <= max_total"
            )
        self.max_total = max_total
        self.max_per_key = max_per_key
        self._cond = threading.Condition()
        self._total_active = 0
        self._key_counts: dict[str, int] = {}
        self.peak_total = 0
        self.peak_per_key: dict[str, int] = {}

    def _can_acquire(self, key: str) -> bool:
        return (
            self._total_active < self.max_total
            and self._key_counts.get(key, 0) < self.max_per_key
        )

    def acquire(self, key: str, timeout: float | None = None) -> bool:
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        with self._cond:
            while not self._can_acquire(key):
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise PoolTimeoutError(f"Timed out acquiring lease for key={key!r}")
                    self._cond.wait(timeout=remaining)
                else:
                    self._cond.wait()

            cur_key = self._key_counts.get(key, 0) + 1
            self._key_counts[key] = cur_key
            self._total_active += 1
            if self._total_active > self.peak_total:
                self.peak_total = self._total_active
            if cur_key > self.peak_per_key.get(key, 0):
                self.peak_per_key[key] = cur_key
            return True

    def release(self, key: str) -> None:
        with self._cond:
            cur = self._key_counts.get(key, 0)
            if cur <= 0 or self._total_active <= 0:
                raise ReleaseError(f"Key {key!r} has no active leases to release")
            if cur == 1:
                del self._key_counts[key]
            else:
                self._key_counts[key] = cur - 1
            self._total_active -= 1
            self._cond.notify_all()

    def lease(self, key: str, timeout: float | None = None) -> LeaseContext:
        return LeaseContext(self, key, timeout=timeout)

    def active_for_key(self, key: str) -> int:
        with self._cond:
            return self._key_counts.get(key, 0)

    @property
    def total_active(self) -> int:
        with self._cond:
            return self._total_active

    def snapshot(self) -> dict[str, int]:
        with self._cond:
            return {k: v for k, v in self._key_counts.items() if v > 0}
''',
        },
        "incomplete_files": {
            "src/concurqueue/pool.py": '''"""Keyed concurrency pool implementation."""

from __future__ import annotations

import threading
from types import TracebackType

from concurqueue.exceptions import PoolTimeoutError, QuotaConfigurationError, ReleaseError


class LeaseContext:
    def __init__(self, pool: KeyedResourcePool, key: str, timeout: float | None = None) -> None:
        self.pool = pool
        self.key = key
        self.timeout = timeout
        self._acquired = False

    def __enter__(self) -> LeaseContext:
        self.pool.acquire(self.key, timeout=self.timeout)
        self._acquired = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._acquired:
            self._acquired = False
            self.pool.release(self.key)


class KeyedResourcePool:
    def __init__(self, max_total: int = 10, max_per_key: int = 2) -> None:
        if max_total <= 0 or max_per_key <= 0 or max_per_key > max_total:
            raise QuotaConfigurationError("Invalid quota")
        self.max_total = max_total
        self.max_per_key = max_per_key
        self._cond = threading.Condition()
        self._total_active = 0
        self._key_counts: dict[str, int] = {}
        self.peak_total = 0
        self.peak_per_key: dict[str, int] = {}

    def _can_acquire(self, key: str) -> bool:
        return (
            self._total_active < self.max_total
            and self._key_counts.get(key, 0) < self.max_per_key
        )

    def acquire(self, key: str, timeout: float | None = None) -> bool:
        # Incomplete fix: still uses `if` instead of `while`, so notify_all wakes multiple threads that all proceed!
        with self._cond:
            if not self._can_acquire(key):
                self._cond.wait(timeout=timeout)
                if not self._can_acquire(key):
                    raise PoolTimeoutError(f"Timed out acquiring lease for key={key!r}")
            cur_key = self._key_counts.get(key, 0) + 1
            self._key_counts[key] = cur_key
            self._total_active += 1
            if self._total_active > self.peak_total:
                self.peak_total = self._total_active
            if cur_key > self.peak_per_key.get(key, 0):
                self.peak_per_key[key] = cur_key
            return True

    def release(self, key: str) -> None:
        with self._cond:
            cur = self._key_counts.get(key, 0)
            if cur <= 0:
                raise ReleaseError(f"Key {key!r} has no active leases to release")
            self._key_counts[key] = cur - 1
            self._total_active -= 1
            self._cond.notify_all()

    def lease(self, key: str, timeout: float | None = None) -> LeaseContext:
        return LeaseContext(self, key, timeout=timeout)

    def active_for_key(self, key: str) -> int:
        with self._cond:
            return self._key_counts.get(key, 0)

    @property
    def total_active(self) -> int:
        with self._cond:
            return self._total_active

    def snapshot(self) -> dict[str, int]:
        with self._cond:
            return {k: v for k, v in self._key_counts.items() if v > 0}
''',
        },
        "regression_files": {
            "src/concurqueue/pool.py": '''"""Keyed concurrency pool implementation."""

from __future__ import annotations

import threading
import time
from types import TracebackType

from concurqueue.exceptions import PoolTimeoutError, QuotaConfigurationError


class LeaseContext:
    def __init__(self, pool: KeyedResourcePool, key: str, timeout: float | None = None) -> None:
        self.pool = pool
        self.key = key
        self.timeout = timeout

    def __enter__(self) -> LeaseContext:
        self.pool.acquire(self.key, timeout=self.timeout)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.pool.release(self.key)


class KeyedResourcePool:
    def __init__(self, max_total: int = 10, max_per_key: int = 2) -> None:
        if max_total <= 0 or max_per_key <= 0 or max_per_key > max_total:
            raise QuotaConfigurationError("Invalid quota")
        self.max_total = max_total
        self.max_per_key = max_per_key
        self._cond = threading.Condition()
        self._total_active = 0
        self._key_counts: dict[str, int] = {}
        self.peak_total = 0
        self.peak_per_key: dict[str, int] = {}

    def acquire(self, key: str, timeout: float | None = None) -> bool:
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        with self._cond:
            while self._total_active >= self.max_total or self._key_counts.get(key, 0) >= self.max_per_key:
                if deadline is not None:
                    rem = deadline - time.monotonic()
                    if rem <= 0:
                        raise PoolTimeoutError("Timeout")
                    self._cond.wait(rem)
                else:
                    self._cond.wait()
            self._key_counts[key] = self._key_counts.get(key, 0) + 1
            self._total_active += 1
            return True

    def release(self, key: str) -> None:
        with self._cond:
            # REGRESSION: Silently ignores over-release instead of raising ReleaseError!
            self._key_counts[key] = max(0, self._key_counts.get(key, 0) - 1)
            self._total_active = max(0, self._total_active - 1)
            self._cond.notify_all()

    def lease(self, key: str, timeout: float | None = None) -> LeaseContext:
        return LeaseContext(self, key, timeout=timeout)

    def active_for_key(self, key: str) -> int:
        return self._key_counts.get(key, 0)

    @property
    def total_active(self) -> int:
        return self._total_active

    def snapshot(self) -> dict[str, int]:
        return dict(self._key_counts)
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for concurqueue."""

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
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS concurrency tests for concurqueue-003."""

import threading
import time
import pytest
from concurqueue import KeyedResourcePool, PoolTimeoutError


def test_concurrent_contention_never_exceeds_per_key_or_total_limits():
    pool = KeyedResourcePool(max_total=4, max_per_key=2)
    barrier = threading.Barrier(16)
    errors: list[Exception] = []

    def worker(idx: int) -> None:
        key = f"k_{idx % 3}"
        try:
            barrier.wait(timeout=1.0)
            for _ in range(3):
                with pool.lease(key, timeout=0.35):
                    if pool.active_for_key(key) > 2 or pool.total_active > 4:
                        raise AssertionError(
                            f"Quota violated: key={pool.active_for_key(key)}, total={pool.total_active}"
                        )
                    time.sleep(0.002)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)

    assert not errors, f"Worker errors: {errors}"
    assert pool.peak_total <= 4
    assert all(v <= 2 for v in pool.peak_per_key.values())
    assert pool.total_active == 0


def test_timeout_under_contention_with_multiple_waiters():
    pool = KeyedResourcePool(max_total=2, max_per_key=1)
    pool.acquire("k1")
    start = time.monotonic()
    with pytest.raises(PoolTimeoutError):
        pool.acquire("k1", timeout=0.06)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.04
    pool.release("k1")
    assert pool.total_active == 0
''',
        "private_tests": '''"""Private stress and broadcast wakeup tests for concurqueue-003."""

import threading
import time
from concurqueue import KeyedResourcePool


def test_cross_key_notify_all_prevents_lost_wakeup():
    # max_total=1, max_per_key=1: releasing k1 must wake waiter on k2 even if another k1 waiter queued first
    pool = KeyedResourcePool(max_total=2, max_per_key=1)
    pool.acquire("k1")
    pool.acquire("k2")

    results: list[str] = []

    def wait_k1():
        # Blocked by max_per_key on k1
        with pool.lease("k1", timeout=2.0):
            results.append("k1_second")

    def wait_k3():
        # Blocked only by max_total=2; releasing k2 should allow k3 to proceed immediately!
        with pool.lease("k3", timeout=2.0):
            results.append("k3")

    t1 = threading.Thread(target=wait_k1)
    t3 = threading.Thread(target=wait_k3)
    t1.start()
    time.sleep(0.02)
    t3.start()
    time.sleep(0.02)

    # Release k2: k1 is still held, so only k3 can run now!
    pool.release("k2")
    t3.join(timeout=1.0)
    assert "k3" in results

    pool.release("k1")
    t1.join(timeout=1.0)
    assert results == ["k3", "k1_second"]
    assert pool. snapshot() == {}
''',
    },
    # =========================================================================
    # TASK 004: ledgersql-004 (Medium — SQLite transactions and rollback correctness)
    # =========================================================================
    {
        "task_id": "ledgersql-004",
        "title": "Fix atomic batch rollback and savepoint isolation in SQLiteLedger.execute_batch",
        "difficulty": "medium",
        "category": "sqlite_transactions",
        "package_name": "ledgersql",
        "summary": "SQLiteLedger commits intermediate transfers during atomic batches and leaves partial debit legs applied when a destination account check fails in partial batches.",
        "allowed_files": ["src/ledgersql/ledger.py", "src/ledgersql/models.py"],
        "issue_md": """# Issue: `SQLiteLedger.execute_batch` leaves partial transfers committed on failure

## Description
`SQLiteLedger` manages double-entry account balances and journal entries in SQLite. `execute_batch(transfers, allow_partial=False)` has two transaction-integrity bugs:

1. **Atomic Batch (`allow_partial=False`) does not roll back earlier transfers**:
   `_apply_transfer()` calls `self._conn.commit()` after each transfer (and updates the sender's balance before verifying whether the recipient account is frozen or missing). When transfer #3 in a 4-transfer atomic batch fails (`InsufficientFundsError` or `AccountFrozenError`), transfers #1 and #2 (plus the sender debit of transfer #3!) remain committed in SQLite! An atomic batch with `allow_partial=False` must be all-or-nothing: if any transfer fails, the entire batch must be rolled back and the exception re-raised.
2. **Partial Batch (`allow_partial=True`) leaves half-applied debit leg on recipient failure**:
   When `allow_partial=True`, each individual transfer in the batch should be isolated in its own SQLite `SAVEPOINT` (or validated atomically). Currently, if the sender has sufficient funds, the sender's balance is debited in SQLite before checking if the destination account is frozen; when `AccountFrozenError` is caught in `allow_partial=True`, the sender's debit is never rolled back, destroying money conservation!

## Expected Behavior
- When `allow_partial=False`, if any transfer in `transfers` fails, zero balance changes or `journal_entries` from the batch may persist in SQLite, and the `LedgerError` must be raised.
- When `allow_partial=True`, each failed transfer must roll back its own changes completely (using a `SAVEPOINT`) while valid transfers in the same batch succeed and commit.
- Total money across all accounts must remain strictly conserved across any combination of valid and invalid transfers.
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/ledgersql/__init__.py": '''"""ledgersql: Double-entry SQLite transactional ledger."""

from ledgersql.ledger import SQLiteLedger
from ledgersql.models import (
    AccountFrozenError,
    AccountNotFoundError,
    BatchResult,
    InsufficientFundsError,
    LedgerError,
    TransferSpec,
)

__all__ = [
    "AccountFrozenError",
    "AccountNotFoundError",
    "BatchResult",
    "InsufficientFundsError",
    "LedgerError",
    "SQLiteLedger",
    "TransferSpec",
]
''',
            "src/ledgersql/models.py": '''"""Domain models and exceptions for ledgersql."""

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
''',
            "src/ledgersql/ledger.py": '''"""SQLite transactional double-entry ledger engine."""

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
''',
        },
        "reference_files": {
            "src/ledgersql/ledger.py": '''"""SQLite transactional double-entry ledger engine."""

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
        self._conn = sqlite3.connect(db_path, isolation_level=None)
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

    def create_account(self, account_id: str, initial_balance_cents: int = 0, frozen: bool = False) -> None:
        if initial_balance_cents < 0:
            raise LedgerError("Initial balance cannot be negative")
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "INSERT INTO accounts (account_id, balance_cents, frozen) VALUES (?, ?, ?)",
                (account_id, initial_balance_cents, 1 if frozen else 0),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

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

    def _apply_single_in_tx(self, spec: TransferSpec) -> None:
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

    def transfer(self, spec: TransferSpec) -> None:
        self.execute_batch([spec], allow_partial=False)

    def execute_batch(
        self,
        transfers: Sequence[TransferSpec],
        allow_partial: bool = False,
    ) -> BatchResult:
        result = BatchResult()
        self._conn.execute("BEGIN")
        try:
            for idx, spec in enumerate(transfers):
                sp_name = f"sp_tx_{idx}"
                self._conn.execute(f"SAVEPOINT {sp_name}")
                try:
                    self._apply_single_in_tx(spec)
                    self._conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                    result.succeeded.append(spec.tx_id)
                except LedgerError as exc:
                    self._conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                    self._conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                    if not allow_partial:
                        raise
                    result.failed[spec.tx_id] = str(exc)
            self._conn.execute("COMMIT")
            return result
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
''',
        },
        "incomplete_files": {
            "src/ledgersql/ledger.py": '''"""SQLite transactional double-entry ledger engine."""

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
        src = self._conn.execute(
            "SELECT balance_cents, frozen FROM accounts WHERE account_id = ?",
            (spec.from_account,),
        ).fetchone()
        if not src:
            raise AccountNotFoundError(spec.from_account)
        if src["frozen"]:
            raise AccountFrozenError(spec.from_account)
        if src["balance_cents"] < spec.amount_cents:
            raise InsufficientFundsError(spec.from_account)

        # Incomplete: still debits sender before checking destination frozen status without savepoint!
        self._conn.execute(
            "UPDATE accounts SET balance_cents = balance_cents - ? WHERE account_id = ?",
            (spec.amount_cents, spec.from_account),
        )
        dst = self._conn.execute(
            "SELECT balance_cents, frozen FROM accounts WHERE account_id = ?",
            (spec.to_account,),
        ).fetchone()
        if not dst or dst["frozen"]:
            raise AccountFrozenError(spec.to_account)
        self._conn.execute(
            "UPDATE accounts SET balance_cents = balance_cents + ? WHERE account_id = ?",
            (spec.amount_cents, spec.to_account),
        )
        self._conn.execute(
            "INSERT INTO journal_entries (tx_id, from_account, to_account, amount_cents, memo) VALUES (?, ?, ?, ?, ?)",
            (spec.tx_id, spec.from_account, spec.to_account, spec.amount_cents, spec.memo),
        )

    def transfer(self, spec: TransferSpec) -> None:
        self.execute_batch([spec], allow_partial=False)

    def execute_batch(
        self,
        transfers: Sequence[TransferSpec],
        allow_partial: bool = False,
    ) -> BatchResult:
        result = BatchResult()
        try:
            for spec in transfers:
                try:
                    self._apply_single(spec)
                    result.succeeded.append(spec.tx_id)
                except LedgerError as exc:
                    if not allow_partial:
                        self._conn.rollback()
                        raise
                    result.failed[spec.tx_id] = str(exc)
            self._conn.commit()
            return result
        except Exception:
            self._conn.rollback()
            raise
''',
        },
        "regression_files": {
            "src/ledgersql/ledger.py": '''"""SQLite transactional double-entry ledger engine."""

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
    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, isolation_level=None)
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

    def create_account(self, account_id: str, initial_balance_cents: int = 0, frozen: bool = False) -> None:
        self._conn.execute(
            "INSERT INTO accounts (account_id, balance_cents, frozen) VALUES (?, ?, ?)",
            (account_id, initial_balance_cents, 1 if frozen else 0),
        )

    def get_balance(self, account_id: str) -> int:
        row = self._conn.execute(
            "SELECT balance_cents FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        if not row:
            raise AccountNotFoundError(account_id)
        return int(row["balance_cents"])

    def total_supply(self) -> int:
        row = self._conn.execute("SELECT COALESCE(SUM(balance_cents), 0) AS s FROM accounts").fetchone()
        return int(row["s"]) if row else 0

    def list_journal(self) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT tx_id, from_account, to_account, amount_cents, memo FROM journal_entries ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def transfer(self, spec: TransferSpec) -> None:
        self.execute_batch([spec], allow_partial=False)

    def execute_batch(
        self,
        transfers: Sequence[TransferSpec],
        allow_partial: bool = False,
    ) -> BatchResult:
        result = BatchResult()
        self._conn.execute("BEGIN")
        try:
            for idx, spec in enumerate(transfers):
                sp = f"sp_{idx}"
                self._conn.execute(f"SAVEPOINT {sp}")
                try:
                    src = self._conn.execute("SELECT balance_cents, frozen FROM accounts WHERE account_id = ?", (spec.from_account,)).fetchone()
                    dst = self._conn.execute("SELECT balance_cents, frozen FROM accounts WHERE account_id = ?", (spec.to_account,)).fetchone()
                    if not src or not dst:
                        raise AccountNotFoundError("Missing account")
                    if src["frozen"] or dst["frozen"]:
                        raise AccountFrozenError("Frozen")
                    if src["balance_cents"] < spec.amount_cents:
                        raise InsufficientFundsError("Overdraft")
                    self._conn.execute("UPDATE accounts SET balance_cents = balance_cents - ? WHERE account_id = ?", (spec.amount_cents, spec.from_account))
                    self._conn.execute("UPDATE accounts SET balance_cents = balance_cents + ? WHERE account_id = ?", (spec.amount_cents, spec.to_account))
                    # REGRESSION: Forgot to insert into journal_entries!
                    self._conn.execute(f"RELEASE SAVEPOINT {sp}")
                    result.succeeded.append(spec.tx_id)
                except LedgerError as exc:
                    self._conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                    self._conn.execute(f"RELEASE SAVEPOINT {sp}")
                    if not allow_partial:
                        raise
                    result.failed[spec.tx_id] = str(exc)
            self._conn.execute("COMMIT")
            return result
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for ledgersql."""

import pytest
from ledgersql import InsufficientFundsError, SQLiteLedger, TransferSpec


def test_single_transfer_and_journal():
    ledger = SQLiteLedger()
    ledger.create_account("alice", 1000)
    ledger.create_account("bob", 500)
    ledger.transfer(TransferSpec("tx1", "alice", "bob", 300, "invoice"))
    assert ledger.get_balance("alice") == 700
    assert ledger.get_balance("bob") == 800
    journal = ledger.list_journal()
    assert len(journal) == 1
    assert journal[0]["tx_id"] == "tx1"


def test_insufficient_funds_single_transfer():
    ledger = SQLiteLedger()
    ledger.create_account("alice", 100)
    ledger.create_account("bob", 100)
    with pytest.raises(InsufficientFundsError):
        ledger.transfer(TransferSpec("tx_fail", "alice", "bob", 250))
    assert ledger.get_balance("alice") == 100
    assert ledger.get_balance("bob") == 100
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for ledgersql-004."""

import pytest
from ledgersql import AccountFrozenError, InsufficientFundsError, SQLiteLedger, TransferSpec


def test_atomic_batch_rolls_back_all_transfers_on_later_failure():
    ledger = SQLiteLedger()
    ledger.create_account("a", 1000)
    ledger.create_account("b", 1000)
    ledger.create_account("c", 100)

    batch = [
        TransferSpec("tx1", "a", "b", 400),
        TransferSpec("tx2", "b", "c", 200),
        TransferSpec("tx3", "c", "a", 500),  # fails: c only has 300 at this point
    ]
    with pytest.raises(InsufficientFundsError):
        ledger.execute_batch(batch, allow_partial=False)

    assert ledger.get_balance("a") == 1000
    assert ledger.get_balance("b") == 1000
    assert ledger.get_balance("c") == 100
    assert ledger.list_journal() == []


def test_partial_batch_savepoint_rolls_back_sender_debit_when_receiver_frozen():
    ledger = SQLiteLedger()
    ledger.create_account("alice", 1000)
    ledger.create_account("bob", 500)
    ledger.create_account("frozen_vault", 200, frozen=True)

    batch = [
        TransferSpec("tx1", "alice", "bob", 300),
        TransferSpec("tx2", "alice", "frozen_vault", 400),  # fails on frozen destination
        TransferSpec("tx3", "bob", "alice", 100),
    ]
    res = ledger.execute_batch(batch, allow_partial=True)
    assert res.succeeded == ["tx1", "tx3"]
    assert "tx2" in res.failed
    # Alice: 1000 - 300 + 100 = 800 (tx2's 400 debit MUST be rolled back!)
    assert ledger.get_balance("alice") == 800
    assert ledger.get_balance("bob") == 700
    assert ledger.get_balance("frozen_vault") == 200
    assert ledger.total_supply() == 1700
''',
        "private_tests": '''"""Private conservation and boundary tests for ledgersql-004."""

import pytest
from ledgersql import AccountNotFoundError, LedgerError, SQLiteLedger, TransferSpec


def test_atomic_batch_rolls_back_when_destination_missing():
    ledger = SQLiteLedger()
    ledger.create_account("u1", 500)
    ledger.create_account("u2", 500)

    with pytest.raises(AccountNotFoundError):
        ledger.execute_batch(
            [
                TransferSpec("t1", "u1", "u2", 200),
                TransferSpec("t2", "u2", "ghost_account", 100),
            ],
            allow_partial=False,
        )
    assert ledger.get_balance("u1") == 500
    assert ledger.get_balance("u2") == 500
    assert ledger.total_supply() == 1000


def test_self_transfer_and_negative_amount_rejected_in_partial_batch():
    ledger = SQLiteLedger()
    ledger.create_account("u1", 500)
    ledger.create_account("u2", 500)
    res = ledger.execute_batch(
        [
            TransferSpec("bad_self", "u1", "u1", 100),
            TransferSpec("bad_neg", "u1", "u2", -50),
            TransferSpec("good", "u1", "u2", 150),
        ],
        allow_partial=True,
    )
    assert res.succeeded == ["good"]
    assert len(res.failed) == 2
    assert ledger.get_balance("u1") == 350
    assert ledger.get_balance("u2") == 650
''',
    },
]
