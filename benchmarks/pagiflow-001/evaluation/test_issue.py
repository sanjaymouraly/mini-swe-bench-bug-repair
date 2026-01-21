"""Issue-specific FAIL_TO_PASS tests for pagiflow-001."""

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
