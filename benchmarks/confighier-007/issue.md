# Issue: `ConfigLoader` drops sibling nested keys, ignores `False`/`0`/`""` CLI overrides, and misparses single underscores in env vars

## Description
`ConfigLoader` merges configuration from 4 layers in increasing precedence:
`defaults < profile < env_vars < cli_overrides`.

Three bugs exist in `src/confighier/loader.py`:

1. **Shallow dictionary merge wipes nested sibling settings**:
   When `profile`, `env_vars`, or `cli_overrides` overrides a single key inside a nested section (e.g., `{"db": {"port": 5433}}`), `merge_layers` uses shallow assignment (`result[k] = v`), wiping out `db.host` and `db.max_connections` from the lower-priority layer! Nested dictionaries must be merged recursively without mutating the caller's input dictionaries.
2. **Falsy CLI overrides (`False`, `0`, `""`, `[]`) are ignored**:
   In `apply_cli_overrides`, the filter uses `if v:` instead of `if v is not None:`, so passing `--no-debug` (`{"debug": False}`) or `{"retries": 0}` is discarded and the default `True` / `3` remains active! Only `None` values in `cli_overrides` mean "flag not provided on CLI".
3. **Environment variable hierarchy splitting on single `_` instead of `__`**:
   Environment variables use `PREFIX__SECTION__FIELD_NAME` where double underscore `__` separates hierarchy levels and single underscore `_` is part of the key name (e.g. `APP__DB__MAX_CONNECTIONS=20` -> `{"db": {"max_connections": 20}}`). Currently `parse_env_vars` splits on `"_"` after stripping the prefix, turning `MAX_CONNECTIONS` into nested `{"max": {"connections": 20}}`!

## Expected Behavior
- Nested dicts are deep-merged across all 4 precedence layers without mutating input dicts.
- `cli_overrides` ignores keys whose value is `None`, but preserves `False`, `0`, `""`, and `[]`.
- `parse_env_vars` splits hierarchy levels strictly on `"__"`, preserving single underscores in lowercase key names.
