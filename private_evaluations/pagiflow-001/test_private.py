"""Private adversarial evaluation tests for pagiflow-001."""

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
