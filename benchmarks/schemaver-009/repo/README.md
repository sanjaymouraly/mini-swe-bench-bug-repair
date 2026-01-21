# `schemaver` — Fix multi-hop v1->v3 schema migration, shared mutable defaults, and unknown field round-tripping

EventCodec only performs single-hop migration on v1 payloads, shares a mutable default tags list across instances, mutates caller dicts in-place, and strips forward-compatible unknown fields on round-trip.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
