"""Hierarchical configuration merging and environment variable parsing."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


def coerce_env_value(raw: str) -> Any:
    """Coerce string environment variable values into bool, int, float, list, or str."""
    val = raw.strip()
    low = val.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    if "," in val:
        return [coerce_env_value(part) for part in val.split(",") if part.strip()]
    return val


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge override mapping into base mapping."""
    result = dict(base)
    for k, v in override.items():
        # BUG 1 & 2: Ignores falsy values (`if v:`) and overwrites nested dicts shallowly!
        if v:
            result[k] = v
    return result


def parse_env_vars(environ: Mapping[str, str], prefix: str = "APP") -> dict[str, Any]:
    """Extract hierarchical configuration from environment variables starting with `PREFIX__`."""
    prefix_tag = f"{prefix.upper()}__"
    parsed: dict[str, Any] = {}
    for env_key, raw_val in environ.items():
        if not env_key.startswith(prefix_tag):
            continue
        remainder = env_key[len(prefix_tag) :]
        # BUG 3: Splits on single underscore `_` instead of double underscore `__`!
        parts = [p.lower() for p in remainder.split("_") if p]
        if not parts:
            continue
        cursor = parsed
        for part in parts[:-1]:
            if part not in cursor or not isinstance(cursor[part], dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = coerce_env_value(raw_val)
    return parsed


class ConfigLoader:
    """Loads and resolves configuration across defaults, profile, env, and CLI layers."""

    def __init__(self, env_prefix: str = "APP") -> None:
        self.env_prefix = env_prefix

    def resolve(
        self,
        defaults: Mapping[str, Any],
        profile: Mapping[str, Any] | None = None,
        environ: Mapping[str, str] | None = None,
        cli_overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged = copy.deepcopy(dict(defaults))
        if profile:
            merged = deep_merge(merged, profile)
        if environ:
            env_layer = parse_env_vars(environ, prefix=self.env_prefix)
            merged = deep_merge(merged, env_layer)
        if cli_overrides:
            merged = deep_merge(merged, cli_overrides)
        return merged
