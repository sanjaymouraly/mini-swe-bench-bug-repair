# `pagiflow` — Fix cursor=0 falsy termination and has_more=False echo loops in PaginatedCollector

PaginatedCollector stops early when next_cursor is integer 0, loops extra pages when has_more=False echoes a cursor token, and aborts on empty intermediate pages.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
