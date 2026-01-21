# Issue: `PaginatedCollector.collect_all` drops pages on `next_cursor=0` and loops when `has_more=False` echoes last cursor

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
