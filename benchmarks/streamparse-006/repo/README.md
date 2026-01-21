# `streamparse` — Fix multi-byte UTF-8 chunk boundary splitting and byte-offset tracking on quarantined records

ChunkedNDJSONReader decodes byte chunks before splitting lines (failing when multi-byte UTF-8 chars or CRLF split across chunks) and fails to advance byte_offset when quarantining/skipping malformed records.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
