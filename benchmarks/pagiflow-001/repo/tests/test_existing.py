"""Pre-existing preservation tests for pagiflow."""

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
