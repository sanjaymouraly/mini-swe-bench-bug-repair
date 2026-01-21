# `confighier` — Fix deep merge sibling wiping, falsy CLI overrides, and single-underscore env keys

ConfigLoader wipes sibling nested keys during layer merging, ignores explicit falsy CLI overrides (False, 0, ''), and splits single underscores in env var names instead of only double underscores.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
