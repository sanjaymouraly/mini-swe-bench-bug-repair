# `ttlcachex` — Fix stale expired entries in get_many/__contains__ and preserve TTL on keep_ttl=True

TTLCache returns expired entries in get_many() and `key in cache`, miscounts hit/miss metrics on expired batch reads, and overwrites remaining TTL when set(..., keep_ttl=True) is called.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
