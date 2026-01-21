"""Benchmark task definitions 009 to 012."""

from __future__ import annotations

from typing import Any

TASKS_PART3: list[dict[str, Any]] = [
    # =========================================================================
    # TASK 009: schemaver-009 (Medium — Serialization and backward compatibility)
    # =========================================================================
    {
        "task_id": "schemaver-009",
        "title": "Fix multi-hop v1->v3 schema migration, shared mutable defaults, and unknown field round-tripping",
        "difficulty": "medium",
        "category": "serialization_compat",
        "package_name": "schemaver",
        "summary": "EventCodec only performs single-hop migration on v1 payloads, shares a mutable default tags list across instances, mutates caller dicts in-place, and strips forward-compatible unknown fields on round-trip.",
        "allowed_files": ["src/schemaver/codec.py"],
        "issue_md": """# Issue: `EventCodec` fails multi-hop `v1 -> v3` migration, shares mutable default `tags`, and drops unknown fields

## Description
`schemaver` deserializes versioned event payloads (`schema_version` 1, 2, or 3) into the current `v3` `EventEnvelope` and re-serializes them with forward/backward compatibility. Four bugs occur:

1. **Multi-hop `v1 -> v2 -> v3` migration stops at `v2`**:
   In `EventCodec.deserialize(raw)`, a `v1` payload (which has `"full_name"` and `"amount_dollars"`) is migrated to `v2` (splitting `"full_name"` into `"first_name"` and `"last_name"`), but `elif version == 2:` is used instead of chaining into the `v2 -> v3` migration (which converts `"amount_dollars"` to integer `"amount_cents"` and sets `schema_version = 3`).
2. **In-place mutation of caller's input dictionary**:
   `deserialize(raw)` mutates the caller's `raw` dictionary directly during migration.
3. **Shared mutable default `tags` list**:
   When `"tags"` is omitted in a payload, `EventEnvelope` uses a shared default list reference, so appending to `env1.tags` mutates `env2.tags` across unrelated deserialized events!
4. **Forward-compatible unknown fields are dropped on `serialize()`**:
   When a newer producer includes extra fields not in the known v3 schema (e.g., `"region": "ap-south-1"`, `"experiment_id": 42`), `deserialize()` drops them instead of storing them in `envelope.extra` and re-emitting them in `serialize()`.

## Expected Behavior
- `v1` and `v2` payloads migrate all the way to `v3` (`schema_version=3`, `first_name`, `last_name`, `amount_cents`, `tags`) without mutating the input dict.
- Each `EventEnvelope` gets an independent `tags` list and `extra` dict.
- Unknown fields are preserved in `envelope.extra` and included at the top level when `codec.serialize(envelope)` is called.
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/schemaver/__init__.py": '''"""schemaver: Versioned event serializer with multi-hop schema evolution."""

from schemaver.codec import CURRENT_SCHEMA_VERSION, EventCodec, EventEnvelope, canonical_hash

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "EventCodec",
    "EventEnvelope",
    "canonical_hash",
]
''',
            "src/schemaver/codec.py": '''"""Versioned event codec and schema migrations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

CURRENT_SCHEMA_VERSION = 3
_DEFAULT_TAGS: list[str] = []


class EventEnvelope:
    """Normalized v3 event envelope."""

    def __init__(
        self,
        event_id: str,
        first_name: str,
        last_name: str,
        amount_cents: int,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        tags: list[str] = _DEFAULT_TAGS,  # BUG: Shared mutable default list!
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.event_id = event_id
        self.first_name = first_name
        self.last_name = last_name
        self.amount_cents = amount_cents
        self.schema_version = schema_version
        self.tags = tags
        self.extra = extra or {}


def canonical_hash(payload: dict[str, Any]) -> str:
    """Return deterministic SHA-256 hex digest of a JSON-serializable dictionary."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EventCodec:
    """Migrates and serializes event payloads across schema versions 1, 2, and 3."""

    def deserialize(self, raw: dict[str, Any]) -> EventEnvelope:
        # BUG: Mutates caller's `raw` in place and uses `if / elif` instead of chaining v1->v2->v3!
        data = raw
        version = int(data.get("schema_version", 1))
        if version not in (1, 2, 3):
            raise ValueError(f"Unsupported schema_version: {version}")

        if version == 1:
            full = str(data.pop("full_name", "")).strip()
            parts = full.split(" ", 1)
            data["first_name"] = parts[0] if parts else ""
            data["last_name"] = parts[1] if len(parts) > 1 else ""
            data["schema_version"] = 2
        elif version == 2:
            dollars = float(data.pop("amount_dollars", 0.0))
            data["amount_cents"] = int(round(dollars * 100))
            data["schema_version"] = 3

        tags = data.get("tags", _DEFAULT_TAGS)
        return EventEnvelope(
            event_id=str(data["event_id"]),
            first_name=str(data.get("first_name", "")),
            last_name=str(data.get("last_name", "")),
            amount_cents=int(data.get("amount_cents", 0)),
            schema_version=int(data.get("schema_version", CURRENT_SCHEMA_VERSION)),
            tags=tags,
        )

    def serialize(self, envelope: EventEnvelope) -> dict[str, Any]:
        # BUG: Drops envelope.extra fields!
        return {
            "event_id": envelope.event_id,
            "schema_version": envelope.schema_version,
            "first_name": envelope.first_name,
            "last_name": envelope.last_name,
            "amount_cents": envelope.amount_cents,
            "tags": list(envelope.tags),
        }
''',
        },
        "reference_files": {
            "src/schemaver/codec.py": '''"""Versioned event codec and schema migrations."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

CURRENT_SCHEMA_VERSION = 3
_KNOWN_V3_FIELDS = {
    "event_id",
    "schema_version",
    "first_name",
    "last_name",
    "amount_cents",
    "tags",
}


class EventEnvelope:
    """Normalized v3 event envelope."""

    def __init__(
        self,
        event_id: str,
        first_name: str,
        last_name: str,
        amount_cents: int,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        tags: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.event_id = event_id
        self.first_name = first_name
        self.last_name = last_name
        self.amount_cents = amount_cents
        self.schema_version = schema_version
        self.tags = list(tags) if tags is not None else []
        self.extra = copy.deepcopy(extra) if extra is not None else {}


def canonical_hash(payload: dict[str, Any]) -> str:
    """Return deterministic SHA-256 hex digest of a JSON-serializable dictionary."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EventCodec:
    """Migrates and serializes event payloads across schema versions 1, 2, and 3."""

    def deserialize(self, raw: dict[str, Any]) -> EventEnvelope:
        data = copy.deepcopy(raw)
        version = int(data.get("schema_version", 1))
        if version not in (1, 2, 3):
            raise ValueError(f"Unsupported schema_version: {version}")

        if version == 1:
            full = str(data.pop("full_name", "")).strip()
            parts = full.split(" ", 1)
            data["first_name"] = parts[0] if parts else ""
            data["last_name"] = parts[1] if len(parts) > 1 else ""
            version = 2
            data["schema_version"] = 2

        if version == 2:
            if "amount_dollars" in data:
                dollars = float(data.pop("amount_dollars", 0.0))
                data["amount_cents"] = int(round(dollars * 100))
            version = 3
            data["schema_version"] = 3

        raw_tags = data.get("tags")
        tags = list(raw_tags) if isinstance(raw_tags, list) else []
        extra = {k: v for k, v in data.items() if k not in _KNOWN_V3_FIELDS}

        return EventEnvelope(
            event_id=str(data["event_id"]),
            first_name=str(data.get("first_name", "")),
            last_name=str(data.get("last_name", "")),
            amount_cents=int(data.get("amount_cents", 0)),
            schema_version=CURRENT_SCHEMA_VERSION,
            tags=tags,
            extra=extra,
        )

    def serialize(self, envelope: EventEnvelope) -> dict[str, Any]:
        out: dict[str, Any] = copy.deepcopy(envelope.extra)
        out.update(
            {
                "event_id": envelope.event_id,
                "schema_version": envelope.schema_version,
                "first_name": envelope.first_name,
                "last_name": envelope.last_name,
                "amount_cents": envelope.amount_cents,
                "tags": list(envelope.tags),
            }
        )
        return out
''',
        },
        "incomplete_files": {
            "src/schemaver/codec.py": '''"""Versioned event codec and schema migrations."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

CURRENT_SCHEMA_VERSION = 3


class EventEnvelope:
    def __init__(
        self,
        event_id: str,
        first_name: str,
        last_name: str,
        amount_cents: int,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        tags: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.event_id = event_id
        self.first_name = first_name
        self.last_name = last_name
        self.amount_cents = amount_cents
        self.schema_version = schema_version
        self.tags = list(tags) if tags is not None else []
        self.extra = extra or {}


def canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EventCodec:
    def deserialize(self, raw: dict[str, Any]) -> EventEnvelope:
        data = copy.deepcopy(raw)
        version = int(data.get("schema_version", 1))
        if version not in (1, 2, 3):
            raise ValueError(f"Unsupported schema_version: {version}")
        if version == 1:
            parts = str(data.pop("full_name", "")).strip().split(" ", 1)
            data["first_name"] = parts[0] if parts else ""
            data["last_name"] = parts[1] if len(parts) > 1 else ""
            version = 2
        if version == 2:
            dollars = float(data.pop("amount_dollars", 0.0))
            data["amount_cents"] = int(round(dollars * 100))
            data["schema_version"] = 3
        # Incomplete: still does not preserve unknown fields in extra!
        return EventEnvelope(
            event_id=str(data["event_id"]),
            first_name=str(data.get("first_name", "")),
            last_name=str(data.get("last_name", "")),
            amount_cents=int(data.get("amount_cents", 0)),
            schema_version=3,
            tags=data.get("tags"),
        )

    def serialize(self, envelope: EventEnvelope) -> dict[str, Any]:
        return {
            "event_id": envelope.event_id,
            "schema_version": envelope.schema_version,
            "first_name": envelope.first_name,
            "last_name": envelope.last_name,
            "amount_cents": envelope.amount_cents,
            "tags": list(envelope.tags),
        }
''',
        },
        "regression_files": {
            "src/schemaver/codec.py": '''"""Versioned event codec and schema migrations."""

from __future__ import annotations

import copy
from typing import Any

CURRENT_SCHEMA_VERSION = 3
_KNOWN = {"event_id", "schema_version", "first_name", "last_name", "amount_cents", "tags"}


class EventEnvelope:
    def __init__(
        self,
        event_id: str,
        first_name: str,
        last_name: str,
        amount_cents: int,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        tags: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.event_id = event_id
        self.first_name = first_name
        self.last_name = last_name
        self.amount_cents = amount_cents
        self.schema_version = schema_version
        self.tags = list(tags) if tags is not None else []
        self.extra = extra or {}


def canonical_hash(payload: dict[str, Any]) -> str:
    # REGRESSION: Does not sort keys in canonical_hash!
    return str(list(payload.items()))


class EventCodec:
    def deserialize(self, raw: dict[str, Any]) -> EventEnvelope:
        data = copy.deepcopy(raw)
        version = int(data.get("schema_version", 1))
        if version == 1:
            parts = str(data.pop("full_name", "")).strip().split(" ", 1)
            data["first_name"] = parts[0] if parts else ""
            data["last_name"] = parts[1] if len(parts) > 1 else ""
            version = 2
        if version == 2:
            dollars = float(data.pop("amount_dollars", 0.0))
            data["amount_cents"] = int(round(dollars * 100))
            data["schema_version"] = 3
        extra = {k: v for k, v in data.items() if k not in _KNOWN}
        return EventEnvelope(
            event_id=str(data["event_id"]),
            first_name=str(data.get("first_name", "")),
            last_name=str(data.get("last_name", "")),
            amount_cents=int(data.get("amount_cents", 0)),
            schema_version=3,
            tags=data.get("tags"),
            extra=extra,
        )

    def serialize(self, envelope: EventEnvelope) -> dict[str, Any]:
        return {
            **envelope.extra,
            "event_id": envelope.event_id,
            "schema_version": envelope.schema_version,
            "first_name": envelope.first_name,
            "last_name": envelope.last_name,
            "amount_cents": envelope.amount_cents,
            "tags": list(envelope.tags),
        }
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for schemaver."""

import pytest
from schemaver import EventCodec, canonical_hash


def test_v3_native_roundtrip():
    codec = EventCodec()
    raw = {
        "event_id": "evt_100",
        "schema_version": 3,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "amount_cents": 2500,
        "tags": ["vip"],
    }
    env = codec.deserialize(raw)
    assert env.first_name == "Ada"
    assert env.amount_cents == 2500
    assert codec.serialize(env) == raw


def test_canonical_hash_key_order_invariance():
    d1 = {"b": 2, "a": 1, "nested": {"z": 9, "y": 8}}
    d2 = {"a": 1, "nested": {"y": 8, "z": 9}, "b": 2}
    assert canonical_hash(d1) == canonical_hash(d2)


def test_unsupported_schema_version_raises():
    codec = EventCodec()
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        codec.deserialize({"event_id": "e1", "schema_version": 99})
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for schemaver-009."""

from schemaver import EventCodec


def test_v1_to_v3_multihop_migration_without_mutating_caller_dict():
    codec = EventCodec()
    v1_payload = {
        "event_id": "evt_v1",
        "schema_version": 1,
        "full_name": "Grace Hopper",
        "amount_dollars": 19.95,
    }
    original_copy = dict(v1_payload)
    env = codec.deserialize(v1_payload)

    assert v1_payload == original_copy, "Input dictionary was mutated in place!"
    assert env.schema_version == 3
    assert env.first_name == "Grace"
    assert env.last_name == "Hopper"
    assert env.amount_cents == 1995


def test_default_tags_are_isolated_across_instances():
    codec = EventCodec()
    e1 = codec.deserialize({"event_id": "1", "schema_version": 3, "first_name": "A", "last_name": "B", "amount_cents": 10})
    e2 = codec.deserialize({"event_id": "2", "schema_version": 3, "first_name": "C", "last_name": "D", "amount_cents": 20})
    e1.tags.append("mutated")
    assert e2.tags == []


def test_unknown_forward_compatible_fields_preserved_on_roundtrip():
    codec = EventCodec()
    raw = {
        "event_id": "evt_fwd",
        "schema_version": 2,
        "first_name": "Alan",
        "last_name": "Turing",
        "amount_dollars": 50.0,
        "trace_region": "eu-central-1",
        "feature_flags": {"beta": True},
    }
    env = codec.deserialize(raw)
    serialized = codec.serialize(env)
    assert serialized["schema_version"] == 3
    assert serialized["amount_cents"] == 5000
    assert serialized["trace_region"] == "eu-central-1"
    assert serialized["feature_flags"] == {"beta": True}
''',
        "private_tests": '''"""Private boundary tests for schemaver-009."""

from schemaver import EventCodec


def test_single_word_full_name_in_v1_and_deep_copy_of_extra():
    codec = EventCodec()
    raw = {
        "event_id": "e_single",
        "schema_version": 1,
        "full_name": "Plato",
        "amount_dollars": 12.34,
        "metadata": {"source": "mobile"},
    }
    env = codec.deserialize(raw)
    assert env.first_name == "Plato"
    assert env.last_name == ""
    assert env.amount_cents == 1234
    raw["metadata"]["source"] = "mutated_outside"
    assert codec.serialize(env)["metadata"]["source"] == "mobile"
''',
    },
    # =========================================================================
    # TASK 010: cliwarden-010 (Easy — CLI input validation and exit-code correctness)
    # =========================================================================
    {
        "task_id": "cliwarden-010",
        "title": "Fix --dry-run validation bypass, stderr usage error routing, and POSIX exit codes",
        "difficulty": "easy",
        "category": "cli_validation",
        "package_name": "cliwarden",
        "summary": "CLIRunner short-circuits on --dry-run before validating arguments, writes validation errors to stdout with exit code 1 instead of stderr with exit code 2, and mishandles KeyboardInterrupt.",
        "allowed_files": ["src/cliwarden/runner.py"],
        "issue_md": """# Issue: `CLIRunner` bypasses validation on `--dry-run`, uses wrong exit codes, and pollutes `stdout` on errors

## Description
`cliwarden` is a command-line runner enforcing structured exit codes:
- `EXIT_OK = 0`
- `EXIT_USAGE_ERROR = 2` (unknown flags, missing required `--target`, mutually exclusive `--fast` and `--thorough`, or invalid `--workers` count `<= 0` or `> 64`)
- `EXIT_CONFIG_ERROR = 3` (`ConfigError` raised by handler)
- `EXIT_RUNTIME_ERROR = 4` (unhandled `RuntimeError` raised by handler)
- `EXIT_INTERRUPTED = 130` (`KeyboardInterrupt` raised by handler)

Three bugs exist in `src/cliwarden/runner.py`:

1. **`--dry-run` short-circuits BEFORE argument validation**:
   When `--dry-run` is passed alongside invalid flags (e.g. `["--dry-run", "--workers", "0"]` or `["--dry-run", "--fast", "--thorough"]` or missing `--target`), `CLIRunner.run()` immediately returns `exit_code=0` without validating the arguments! `--dry-run` must validate all arguments first, and only skip invoking the handler after validation succeeds.
2. **Validation errors return exit code `1` and print to `stdout` instead of `stderr`**:
   Usage/validation errors must return `EXIT_USAGE_ERROR` (`2`) and write the error message to `stderr` (leaving `stdout` empty `""`).
3. **`KeyboardInterrupt` returns `1` instead of `EXIT_INTERRUPTED` (`130`)**:
   When the command handler raises `KeyboardInterrupt`, `run()` catches `Exception` or returns `1` instead of returning `EXIT_INTERRUPTED` (`130`) with `"Interrupted\n"` on `stderr`.

## Expected Behavior
- Full argument validation always runs before `--dry-run` short-circuiting.
- Usage/validation errors return `exit_code=2`, `stdout=""`, and non-empty `stderr`.
- `ConfigError` returns `exit_code=3`, `RuntimeError` returns `exit_code=4`, and `KeyboardInterrupt` returns `exit_code=130` (all writing error details to `stderr`).
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/cliwarden/__init__.py": '''"""cliwarden: Structured CLI argument validator and POSIX exit-code runner."""

from cliwarden.runner import (
    EXIT_CONFIG_ERROR,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_RUNTIME_ERROR,
    EXIT_USAGE_ERROR,
    CLIResult,
    CLIRunner,
    ConfigError,
)

__all__ = [
    "CLIResult",
    "CLIRunner",
    "ConfigError",
    "EXIT_CONFIG_ERROR",
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_RUNTIME_ERROR",
    "EXIT_USAGE_ERROR",
]
''',
            "src/cliwarden/runner.py": r'''"""CLI argument parser, validator, and structured exit-code runner."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

EXIT_OK = 0
EXIT_USAGE_ERROR = 2
EXIT_CONFIG_ERROR = 3
EXIT_RUNTIME_ERROR = 4
EXIT_INTERRUPTED = 130


class ConfigError(Exception):
    """Raised when configuration file or environment is invalid."""


@dataclass
class CLIResult:
    exit_code: int
    stdout: str
    stderr: str


class CLIRunner:
    """Validates CLI flags and executes a handler with POSIX exit codes."""

    def __init__(self, handler: Callable[[dict[str, Any]], str] | None = None) -> None:
        self.handler = handler or (lambda opts: f"Executed on {opts['target']} (workers={opts['workers']})\n")

    def run(self, argv: Sequence[str]) -> CLIResult:
        args = list(argv)

        # BUG 1: Short-circuits on --dry-run BEFORE validating flags and arguments!
        if "--dry-run" in args:
            return CLIResult(exit_code=EXIT_OK, stdout="DRY RUN OK\n", stderr="")

        target: str | None = None
        workers: int = 4
        fast = False
        thorough = False
        dry_run = False

        i = 0
        while i < len(args):
            tok = args[i]
            if tok == "--target":
                if i + 1 >= len(args) or args[i + 1].startswith("--"):
                    # BUG 2: Returns exit_code=1 and writes error to stdout!
                    return CLIResult(exit_code=1, stdout="Error: --target requires a value\n", stderr="")
                target = args[i + 1]
                i += 2
            elif tok == "--workers":
                if i + 1 >= len(args):
                    return CLIResult(exit_code=1, stdout="Error: --workers requires an integer\n", stderr="")
                try:
                    workers = int(args[i + 1])
                except ValueError:
                    return CLIResult(exit_code=1, stdout="Error: --workers must be an integer\n", stderr="")
                i += 2
            elif tok == "--fast":
                fast = True
                i += 1
            elif tok == "--thorough":
                thorough = True
                i += 1
            elif tok == "--dry-run":
                dry_run = True
                i += 1
            else:
                return CLIResult(exit_code=1, stdout=f"Error: Unknown option {tok}\n", stderr="")

        if not target:
            return CLIResult(exit_code=1, stdout="Error: --target is required\n", stderr="")
        if fast and thorough:
            return CLIResult(exit_code=1, stdout="Error: --fast and --thorough are mutually exclusive\n", stderr="")
        if workers <= 0 or workers > 64:
            return CLIResult(exit_code=1, stdout="Error: --workers must be between 1 and 64\n", stderr="")

        opts = {
            "target": target,
            "workers": workers,
            "mode": "fast" if fast else ("thorough" if thorough else "normal"),
            "dry_run": dry_run,
        }

        try:
            out = self.handler(opts)
            return CLIResult(exit_code=EXIT_OK, stdout=out, stderr="")
        except ConfigError as exc:
            return CLIResult(exit_code=EXIT_CONFIG_ERROR, stdout="", stderr=f"Config error: {exc}\n")
        except BaseException as exc:
            # BUG 3: Catches KeyboardInterrupt here and returns 1 instead of 130!
            return CLIResult(exit_code=1, stdout="", stderr=f"Error: {exc}\n")
''',
        },
        "reference_files": {
            "src/cliwarden/runner.py": r'''"""CLI argument parser, validator, and structured exit-code runner."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

EXIT_OK = 0
EXIT_USAGE_ERROR = 2
EXIT_CONFIG_ERROR = 3
EXIT_RUNTIME_ERROR = 4
EXIT_INTERRUPTED = 130


class ConfigError(Exception):
    """Raised when configuration file or environment is invalid."""


@dataclass
class CLIResult:
    exit_code: int
    stdout: str
    stderr: str


def _usage_error(message: str) -> CLIResult:
    return CLIResult(exit_code=EXIT_USAGE_ERROR, stdout="", stderr=f"Usage error: {message}\n")


class CLIRunner:
    """Validates CLI flags and executes a handler with POSIX exit codes."""

    def __init__(self, handler: Callable[[dict[str, Any]], str] | None = None) -> None:
        self.handler = handler or (lambda opts: f"Executed on {opts['target']} (workers={opts['workers']})\n")

    def run(self, argv: Sequence[str]) -> CLIResult:
        args = list(argv)

        target: str | None = None
        workers: int = 4
        fast = False
        thorough = False
        dry_run = False

        i = 0
        while i < len(args):
            tok = args[i]
            if tok == "--target":
                if i + 1 >= len(args) or args[i + 1].startswith("--"):
                    return _usage_error("--target requires a value")
                target = args[i + 1].strip()
                i += 2
            elif tok == "--workers":
                if i + 1 >= len(args):
                    return _usage_error("--workers requires an integer")
                try:
                    workers = int(args[i + 1])
                except ValueError:
                    return _usage_error("--workers must be an integer")
                i += 2
            elif tok == "--fast":
                fast = True
                i += 1
            elif tok == "--thorough":
                thorough = True
                i += 1
            elif tok == "--dry-run":
                dry_run = True
                i += 1
            else:
                return _usage_error(f"Unknown option {tok}")

        if not target:
            return _usage_error("--target is required")
        if fast and thorough:
            return _usage_error("--fast and --thorough are mutually exclusive")
        if workers <= 0 or workers > 64:
            return _usage_error("--workers must be between 1 and 64")

        opts = {
            "target": target,
            "workers": workers,
            "mode": "fast" if fast else ("thorough" if thorough else "normal"),
            "dry_run": dry_run,
        }

        if dry_run:
            return CLIResult(
                exit_code=EXIT_OK,
                stdout=f"DRY RUN OK: target={target} workers={workers} mode={opts['mode']}\n",
                stderr="",
            )

        try:
            out = self.handler(opts)
            return CLIResult(exit_code=EXIT_OK, stdout=out, stderr="")
        except KeyboardInterrupt:
            return CLIResult(exit_code=EXIT_INTERRUPTED, stdout="", stderr="Interrupted\n")
        except ConfigError as exc:
            return CLIResult(exit_code=EXIT_CONFIG_ERROR, stdout="", stderr=f"Config error: {exc}\n")
        except Exception as exc:
            return CLIResult(exit_code=EXIT_RUNTIME_ERROR, stdout="", stderr=f"Runtime error: {exc}\n")
''',
        },
        "incomplete_files": {
            "src/cliwarden/runner.py": r'''"""CLI argument parser, validator, and structured exit-code runner."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

EXIT_OK = 0
EXIT_USAGE_ERROR = 2
EXIT_CONFIG_ERROR = 3
EXIT_RUNTIME_ERROR = 4
EXIT_INTERRUPTED = 130


class ConfigError(Exception):
    pass


@dataclass
class CLIResult:
    exit_code: int
    stdout: str
    stderr: str


class CLIRunner:
    def __init__(self, handler: Callable[[dict[str, Any]], str] | None = None) -> None:
        self.handler = handler or (lambda opts: f"Executed on {opts['target']} (workers={opts['workers']})\n")

    def run(self, argv: Sequence[str]) -> CLIResult:
        args = list(argv)
        # Incomplete fix: still short-circuits on --dry-run before validating!
        if "--dry-run" in args:
            return CLIResult(exit_code=EXIT_OK, stdout="DRY RUN OK\n", stderr="")

        target: str | None = None
        workers: int = 4
        fast = False
        thorough = False
        i = 0
        while i < len(args):
            tok = args[i]
            if tok == "--target" and i + 1 < len(args):
                target = args[i + 1]
                i += 2
            elif tok == "--workers" and i + 1 < len(args):
                try:
                    workers = int(args[i + 1])
                except ValueError:
                    return CLIResult(exit_code=EXIT_USAGE_ERROR, stdout="", stderr="Invalid workers\n")
                i += 2
            elif tok == "--fast":
                fast = True
                i += 1
            elif tok == "--thorough":
                thorough = True
                i += 1
            else:
                return CLIResult(exit_code=EXIT_USAGE_ERROR, stdout="", stderr="Usage error\n")

        if not target or (fast and thorough) or workers <= 0 or workers > 64:
            return CLIResult(exit_code=EXIT_USAGE_ERROR, stdout="", stderr="Usage error\n")

        try:
            out = self.handler({"target": target, "workers": workers, "mode": "normal", "dry_run": False})
            return CLIResult(exit_code=EXIT_OK, stdout=out, stderr="")
        except KeyboardInterrupt:
            return CLIResult(exit_code=EXIT_INTERRUPTED, stdout="", stderr="Interrupted\n")
        except ConfigError as exc:
            return CLIResult(exit_code=EXIT_CONFIG_ERROR, stdout="", stderr=str(exc))
        except Exception as exc:
            return CLIResult(exit_code=EXIT_RUNTIME_ERROR, stdout="", stderr=str(exc))
''',
        },
        "regression_files": {
            "src/cliwarden/runner.py": r'''"""CLI argument parser, validator, and structured exit-code runner."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

EXIT_OK = 0
EXIT_USAGE_ERROR = 2
EXIT_CONFIG_ERROR = 3
EXIT_RUNTIME_ERROR = 4
EXIT_INTERRUPTED = 130


class ConfigError(Exception):
    pass


@dataclass
class CLIResult:
    exit_code: int
    stdout: str
    stderr: str


class CLIRunner:
    def __init__(self, handler: Callable[[dict[str, Any]], str] | None = None) -> None:
        self.handler = handler or (lambda opts: f"Executed on {opts['target']} (workers={opts['workers']})\n")

    def run(self, argv: Sequence[str]) -> CLIResult:
        # REGRESSION: Always returns EXIT_USAGE_ERROR even on valid commands!
        return CLIResult(exit_code=EXIT_USAGE_ERROR, stdout="", stderr="Usage error\n")
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for cliwarden."""

from cliwarden import EXIT_CONFIG_ERROR, EXIT_OK, CLIRunner, ConfigError


def test_valid_command_execution():
    runner = CLIRunner()
    res = runner.run(["--target", "service-a", "--workers", "8", "--fast"])
    assert res.exit_code == EXIT_OK
    assert "service-a" in res.stdout
    assert res.stderr == ""


def test_config_error_exit_code():
    def bad_cfg(_opts):
        raise ConfigError("missing credentials.yaml")

    runner = CLIRunner(handler=bad_cfg)
    res = runner.run(["--target", "prod"])
    assert res.exit_code == EXIT_CONFIG_ERROR
    assert "credentials.yaml" in res.stderr
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for cliwarden-010."""

from cliwarden import (
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_RUNTIME_ERROR,
    EXIT_USAGE_ERROR,
    CLIRunner,
)


def test_dry_run_still_validates_invalid_arguments():
    runner = CLIRunner()
    # Mutually exclusive flags with --dry-run must fail with exit code 2
    res1 = runner.run(["--target", "app", "--fast", "--thorough", "--dry-run"])
    assert res1.exit_code == EXIT_USAGE_ERROR
    assert res1.stdout == ""
    assert res1.stderr != ""

    # Out-of-range workers with --dry-run must fail with exit code 2
    res2 = runner.run(["--target", "app", "--workers", "0", "--dry-run"])
    assert res2.exit_code == EXIT_USAGE_ERROR
    assert res2.stdout == ""

    # Valid --dry-run succeeds without calling handler
    called = False

    def should_not_run(_opts):
        nonlocal called
        called = True
        return "ran"

    res3 = CLIRunner(handler=should_not_run).run(["--target", "app", "--dry-run"])
    assert res3.exit_code == EXIT_OK
    assert called is False


def test_keyboard_interrupt_and_runtime_error_exit_codes():
    def interrupt_handler(_opts):
        raise KeyboardInterrupt()

    res_int = CLIRunner(handler=interrupt_handler).run(["--target", "svc"])
    assert res_int.exit_code == EXIT_INTERRUPTED
    assert res_int.stdout == ""

    def crash_handler(_opts):
        raise RuntimeError("disk full")

    res_err = CLIRunner(handler=crash_handler).run(["--target", "svc"])
    assert res_err.exit_code == EXIT_RUNTIME_ERROR
    assert "disk full" in res_err.stderr
''',
        "private_tests": '''"""Private boundary tests for cliwarden-010."""

from cliwarden import EXIT_USAGE_ERROR, CLIRunner


def test_unknown_flag_and_missing_target_value_return_exit_2_on_stderr():
    runner = CLIRunner()
    r1 = runner.run(["--target", "--fast"])
    assert r1.exit_code == EXIT_USAGE_ERROR
    assert r1.stdout == ""
    assert r1.stderr != ""

    r2 = runner.run(["--target", "svc", "--unknown-flag"])
    assert r2.exit_code == EXIT_USAGE_ERROR
    assert r2.stdout == ""
''',
    },
    # =========================================================================
    # TASK 011: idempobox-011 (Hard — Idempotency and duplicate processing)
    # =========================================================================
    {
        "task_id": "idempobox-011",
        "title": "Fix idempotency payload mismatch detection, canonical fingerprinting, and failed lock cleanup",
        "difficulty": "hard",
        "category": "idempotency",
        "package_name": "idempobox",
        "summary": "IdempotentProcessor silently returns cached results when an idempotency key is reused with a different payload, includes volatile trace headers in fingerprints, and leaves failed executions permanently locked in IN_PROGRESS.",
        "allowed_files": ["src/idempobox/processor.py", "src/idempobox/exceptions.py"],
        "issue_md": """# Issue: `IdempotentProcessor` fails to detect altered payloads on key reuse, hashes volatile headers, and locks keys after handler failure

## Description
`IdempotentProcessor` ensures payment and webhook commands are executed at-most-once per `idempotency_key`. Three critical bugs exist:

1. **Silent payload mismatch on `COMPLETED` key reuse**:
   When a client retries with an existing `idempotency_key` that already `COMPLETED`, `process()` immediately returns `record.result` **without verifying that the new request's semantic fingerprint matches `record.fingerprint`**! If a client accidentally reuses key `"idem_123"` for a `$500` payment after a `$50` payment, it must raise `IdempotencyPayloadMismatchError`.
2. **Non-canonical fingerprinting & volatile metadata pollution**:
   `compute_payload_fingerprint(payload)` must recursively sort dictionary keys and ignore volatile transport metadata keys (`"_trace_id"`, `"_timestamp"`, `"_request_id"`) at any nesting level so that semantically identical retries with a new `_trace_id` or different dict key order produce the exact same SHA-256 fingerprint.
3. **Failed handler execution leaves key stuck in `IN_PROGRESS`**:
   When `handler(payload)` raises an exception, `process()` leaves the record in `IN_PROGRESS` state inside `self._records`. Subsequent retries with the same `idempotency_key` then fail with `IdempotencyConflictError("already in progress")` instead of being allowed to retry! Only genuinely concurrent in-flight executions should raise `IdempotencyConflictError`.

## Expected Behavior
- Replaying the same `idempotency_key` with an identical semantic payload (ignoring `_trace_id`, `_timestamp`, `_request_id` and dict key order) returns the cached result without re-invoking `handler`.
- Reusing an `idempotency_key` (whether `IN_PROGRESS` or `COMPLETED`) with a different semantic payload raises `IdempotencyPayloadMismatchError`.
- If `handler` raises an exception, the in-progress lock record is removed (or marked retryable) before re-raising the exception so a subsequent retry can execute.
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/idempobox/__init__.py": '''"""idempobox: Idempotent command and webhook processor."""

from idempobox.exceptions import IdempotencyConflictError, IdempotencyPayloadMismatchError
from idempobox.processor import IdempotentProcessor, compute_payload_fingerprint

__all__ = [
    "IdempotencyConflictError",
    "IdempotencyPayloadMismatchError",
    "IdempotentProcessor",
    "compute_payload_fingerprint",
]
''',
            "src/idempobox/exceptions.py": '''"""Exceptions for idempobox."""


class IdempotencyConflictError(RuntimeError):
    """Raised when a duplicate request arrives while the first is still IN_PROGRESS."""


class IdempotencyPayloadMismatchError(ValueError):
    """Raised when an idempotency key is reused with a different semantic payload."""
''',
            "src/idempobox/processor.py": '''"""Idempotent request processor and payload fingerprinting."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from idempobox.exceptions import IdempotencyConflictError, IdempotencyPayloadMismatchError

VOLATILE_KEYS = {"_trace_id", "_timestamp", "_request_id"}


@dataclass
class IdempotencyRecord:
    key: str
    fingerprint: str
    status: str  # "IN_PROGRESS" or "COMPLETED"
    result: Any = None


def compute_payload_fingerprint(payload: dict[str, Any]) -> str:
    """Compute SHA-256 fingerprint of a request payload."""
    # BUG: Does not strip VOLATILE_KEYS recursively and does not sort keys!
    raw = json.dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotentProcessor:
    """Thread-safe idempotent command execution coordinator."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, IdempotencyRecord] = {}
        self.execution_count: int = 0

    def process(
        self,
        idempotency_key: str,
        payload: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
    ) -> Any:
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")

        fp = compute_payload_fingerprint(payload)

        with self._lock:
            existing = self._records.get(idempotency_key)
            if existing is not None:
                # BUG 1: Does not check existing.fingerprint != fp to raise IdempotencyPayloadMismatchError!
                if existing.status == "IN_PROGRESS":
                    raise IdempotencyConflictError(
                        f"Request with key {idempotency_key!r} is currently IN_PROGRESS"
                    )
                return existing.result

            self._records[idempotency_key] = IdempotencyRecord(
                key=idempotency_key,
                fingerprint=fp,
                status="IN_PROGRESS",
            )

        # BUG 3: If handler raises an exception, the record remains stuck in IN_PROGRESS!
        self.execution_count += 1
        result = handler(payload)

        with self._lock:
            self._records[idempotency_key] = IdempotencyRecord(
                key=idempotency_key,
                fingerprint=fp,
                status="COMPLETED",
                result=result,
            )
        return result
''',
        },
        "reference_files": {
            "src/idempobox/processor.py": '''"""Idempotent request processor and payload fingerprinting."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from idempobox.exceptions import IdempotencyConflictError, IdempotencyPayloadMismatchError

VOLATILE_KEYS = {"_trace_id", "_timestamp", "_request_id"}


@dataclass
class IdempotencyRecord:
    key: str
    fingerprint: str
    status: str  # "IN_PROGRESS" or "COMPLETED"
    result: Any = None


def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_volatile(v)
            for k, v in sorted(obj.items())
            if k not in VOLATILE_KEYS
        }
    if isinstance(obj, list):
        return [_strip_volatile(item) for item in obj]
    return obj


def compute_payload_fingerprint(payload: dict[str, Any]) -> str:
    """Compute canonical SHA-256 fingerprint of a semantic payload excluding volatile keys."""
    cleaned = _strip_volatile(payload)
    raw = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotentProcessor:
    """Thread-safe idempotent command execution coordinator."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, IdempotencyRecord] = {}
        self.execution_count: int = 0

    def process(
        self,
        idempotency_key: str,
        payload: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
    ) -> Any:
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")

        fp = compute_payload_fingerprint(payload)

        with self._lock:
            existing = self._records.get(idempotency_key)
            if existing is not None:
                if existing.fingerprint != fp:
                    raise IdempotencyPayloadMismatchError(
                        f"Idempotency key {idempotency_key!r} reused with different payload"
                    )
                if existing.status == "IN_PROGRESS":
                    raise IdempotencyConflictError(
                        f"Request with key {idempotency_key!r} is currently IN_PROGRESS"
                    )
                return copy.deepcopy(existing.result)

            self._records[idempotency_key] = IdempotencyRecord(
                key=idempotency_key,
                fingerprint=fp,
                status="IN_PROGRESS",
            )

        try:
            self.execution_count += 1
            result = handler(payload)
        except BaseException:
            with self._lock:
                self._records.pop(idempotency_key, None)
            raise

        with self._lock:
            self._records[idempotency_key] = IdempotencyRecord(
                key=idempotency_key,
                fingerprint=fp,
                status="COMPLETED",
                result=copy.deepcopy(result),
            )
        return copy.deepcopy(result)
''',
        },
        "incomplete_files": {
            "src/idempobox/processor.py": '''"""Idempotent request processor and payload fingerprinting."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from idempobox.exceptions import IdempotencyConflictError, IdempotencyPayloadMismatchError

VOLATILE_KEYS = {"_trace_id", "_timestamp", "_request_id"}


@dataclass
class IdempotencyRecord:
    key: str
    fingerprint: str
    status: str
    result: Any = None


def compute_payload_fingerprint(payload: dict[str, Any]) -> str:
    # Incomplete: only strips top-level volatile keys, not nested ones!
    cleaned = {k: v for k, v in payload.items() if k not in VOLATILE_KEYS}
    raw = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotentProcessor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, IdempotencyRecord] = {}
        self.execution_count: int = 0

    def process(
        self,
        idempotency_key: str,
        payload: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
    ) -> Any:
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        fp = compute_payload_fingerprint(payload)
        with self._lock:
            existing = self._records.get(idempotency_key)
            if existing is not None:
                if existing.fingerprint != fp:
                    raise IdempotencyPayloadMismatchError("Mismatch")
                if existing.status == "IN_PROGRESS":
                    raise IdempotencyConflictError("In progress")
                return existing.result
            self._records[idempotency_key] = IdempotencyRecord(idempotency_key, fp, "IN_PROGRESS")

        # Incomplete: still does not clean up IN_PROGRESS when handler raises!
        self.execution_count += 1
        result = handler(payload)
        with self._lock:
            self._records[idempotency_key] = IdempotencyRecord(idempotency_key, fp, "COMPLETED", result)
        return result
''',
        },
        "regression_files": {
            "src/idempobox/processor.py": '''"""Idempotent request processor and payload fingerprinting."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any


def compute_payload_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class IdempotentProcessor:
    def __init__(self) -> None:
        self.execution_count: int = 0

    def process(
        self,
        idempotency_key: str,
        payload: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
    ) -> Any:
        # REGRESSION: Executes handler every time without caching idempotent responses!
        self.execution_count += 1
        return handler(payload)
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for idempobox."""

import pytest
from idempobox import IdempotentProcessor


def test_exact_duplicate_replay_executes_handler_once():
    proc = IdempotentProcessor()
    payload = {"amount": 100, "currency": "USD"}
    r1 = proc.process("key_1", payload, lambda p: {"charged": p["amount"]})
    r2 = proc.process("key_1", payload, lambda p: {"charged": p["amount"]})
    assert r1 == {"charged": 100}
    assert r2 == {"charged": 100}
    assert proc.execution_count == 1


def test_empty_key_rejected():
    proc = IdempotentProcessor()
    with pytest.raises(ValueError):
        proc.process("   ", {"a": 1}, lambda p: p)
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for idempobox-011."""

import pytest
from idempobox import (
    IdempotencyPayloadMismatchError,
    IdempotentProcessor,
)


def test_key_reuse_with_different_payload_raises_mismatch_error():
    proc = IdempotentProcessor()
    proc.process("pay_1", {"amount": 50, "to": "alice"}, lambda p: {"status": "ok", "amt": p["amount"]})

    with pytest.raises(IdempotencyPayloadMismatchError):
        proc.process("pay_1", {"amount": 500, "to": "alice"}, lambda p: {"status": "ok", "amt": p["amount"]})
    assert proc.execution_count == 1


def test_volatile_headers_and_nested_key_order_ignored_in_fingerprint():
    proc = IdempotentProcessor()
    p1 = {"meta": {"_trace_id": "t1", "channel": "web"}, "amount": 250, "_timestamp": 1000}
    p2 = {"_timestamp": 2000, "amount": 250, "meta": {"channel": "web", "_trace_id": "t2"}}

    res1 = proc.process("pay_2", p1, lambda _: {"tx": "abc"})
    res2 = proc.process("pay_2", p2, lambda _: {"tx": "xyz"})
    assert res1 == {"tx": "abc"}
    assert res2 == {"tx": "abc"}
    assert proc.execution_count == 1


def test_transient_handler_failure_releases_key_for_subsequent_retry():
    proc = IdempotentProcessor()
    should_fail = True

    def flaky_handler(p):
        if should_fail:
            raise RuntimeError("database timeout")
        return {"ok": p["amount"]}

    with pytest.raises(RuntimeError, match="database timeout"):
        proc.process("pay_retry", {"amount": 75}, flaky_handler)

    should_fail = False
    res = proc.process("pay_retry", {"amount": 75}, flaky_handler)
    assert res == {"ok": 75}
    assert proc.execution_count == 2
''',
        "private_tests": '''"""Private concurrency conflict and result immutability tests for idempobox-011."""

import threading
import time
import pytest
from idempobox import IdempotencyConflictError, IdempotentProcessor


def test_concurrent_in_flight_duplicate_raises_conflict_and_cached_result_is_isolated():
    proc = IdempotentProcessor()
    entered = threading.Event()
    release = threading.Event()

    def slow_handler(_p):
        entered.set()
        release.wait(timeout=2.0)
        return {"items": [1, 2]}

    t = threading.Thread(target=lambda: proc.process("k_flight", {"x": 1}, slow_handler))
    t.start()
    entered.wait(timeout=2.0)

    with pytest.raises(IdempotencyConflictError):
        proc.process("k_flight", {"x": 1}, slow_handler)

    release.set()
    t.join(timeout=2.0)

    # Mutating returned dict must not corrupt cached result for future replays
    out1 = proc.process("k_flight", {"x": 1}, slow_handler)
    out1["items"].append(999)
    out2 = proc.process("k_flight", {"x": 1}, slow_handler)
    assert out2 == {"items": [1, 2]}
''',
    },
    # =========================================================================
    # TASK 012: atomicvault-012 (Hard — File operations, atomic writes, and recovery from partial failures)
    # =========================================================================
    {
        "task_id": "atomicvault-012",
        "title": "Fix mid-write target loss, orphan temp cleanup, crash recovery, and path traversal in AtomicVault",
        "difficulty": "hard",
        "category": "atomic_file_ops",
        "package_name": "atomicvault",
        "summary": "AtomicVault moves live files to .bak before completing temp writes (destroying live files when a writer fails mid-stream), fails to clean up .tmp files or restore .bak files on recover(), and allows nested '..' path traversal.",
        "allowed_files": ["src/atomicvault/storage.py"],
        "issue_md": """# Issue: `AtomicVault` loses live files on mid-write failure, fails crash recovery, and allows `a/../../` path traversal

## Description
`AtomicVault` manages crash-safe artifact files and a SHA-256 `manifest.json` inside a root directory. Three critical reliability/security bugs were discovered:

1. **Nested path traversal bypass (`subdir/../../escape.txt`)**:
   `_resolve_path(rel_path)` only checks `rel_path.startswith("..") or rel_path.startswith("/")`. Passing `"nested/../../outside.txt"` escapes the vault root! It must resolve the path and verify `candidate.is_relative_to(self.root)` (and reject reserved `"manifest.json"` or `*.tmp` / `*.bak` names), raising `VaultSecurityError`.
2. **Mid-write exception destroys existing live file and leaves `.tmp` behind**:
   In `put(rel_path, content_or_writer, keep_backup=True)`:
   Currently, if the target file already exists, `put()` renames `target -> target.bak` **before** writing the new content to `target.tmp`. When `content_or_writer` (a callable `writer(file_obj)`) raises an exception mid-write, `target` is gone and `target.tmp` is left behind!
   Instead:
   - Write to a temporary file in the same directory first (`<name>.tmp`).
   - If writing fails, unlink the `.tmp` file and re-raise `VaultWriteError` without touching the live `target` file or `manifest.json`!
   - Only after the `.tmp` file is completely written and flushed: if `keep_backup=True` and `target` exists, copy/link `target` to `<name>.bak` (or replace atomically) and `os.replace(tmp_path, target)`, then update `manifest.json` atomically.
3. **`recover()` after simulated crash does not clean `.tmp` files or restore missing targets from `.bak`**:
   When an external crash leaves orphaned `*.tmp` files or a `<name>.bak` file where `<name>` is missing, `recover()` must:
   - Delete all orphaned `*.tmp` files across the vault.
   - If a `<name>.bak` file exists and its corresponding `<name>` target does not exist, restore `<name>.bak` -> `<name>`.
   - Rebuild `manifest.json` with accurate SHA-256 digests of all live artifact files (excluding `manifest.json`, `*.tmp`, and `*.bak`).

## Expected Behavior
- Any path escaping `self.root` raises `VaultSecurityError`.
- Failed writes leave existing target files and `manifest.json` completely intact and leave zero `.tmp` files behind.
- `recover()` cleans up `.tmp` files, restores orphaned `.bak` files when the primary target is missing, and synchronizes `manifest.json`.
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/atomicvault/__init__.py": '''"""atomicvault: Crash-safe atomic file storage and manifest manager."""

from atomicvault.storage import AtomicVault, VaultSecurityError, VaultWriteError, sha256_bytes

__all__ = ["AtomicVault", "VaultSecurityError", "VaultWriteError", "sha256_bytes"]
''',
            "src/atomicvault/storage.py": r'''"""Atomic file storage with SHA-256 manifest and crash recovery."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO


class VaultSecurityError(ValueError):
    """Raised when a relative path attempts to escape the vault root."""


class VaultWriteError(RuntimeError):
    """Raised when an artifact write fails."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AtomicVault:
    """Manages atomic file writes, backups, and a SHA-256 manifest."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        if not self.manifest_path.exists():
            self._write_manifest({})

    def _resolve_path(self, rel_path: str) -> Path:
        # BUG 1: Only checks startswith(".."), allowing "a/../../escape.txt"!
        clean = rel_path.replace("\\", "/").strip()
        if not clean or clean.startswith("/") or clean.startswith(".."):
            raise VaultSecurityError(f"Unsafe path: {rel_path}")
        return self.root / clean

    def _read_manifest(self) -> dict[str, str]:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, data: dict[str, str]) -> None:
        self.manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def put(
        self,
        rel_path: str,
        content_or_writer: bytes | Callable[[BinaryIO], None],
        keep_backup: bool = True,
    ) -> str:
        target = self._resolve_path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(target.name + ".tmp")
        bak_path = target.with_name(target.name + ".bak")

        # BUG 2: Moves live target to .bak BEFORE writing tmp_path, and doesn't clean up tmp_path on failure!
        if keep_backup and target.exists():
            target.replace(bak_path)

        try:
            with open(tmp_path, "wb") as f:
                if callable(content_or_writer):
                    content_or_writer(f)
                else:
                    f.write(content_or_writer)
        except Exception as exc:
            raise VaultWriteError(f"Failed writing {rel_path}: {exc}") from exc

        tmp_path.replace(target)
        digest = sha256_bytes(target.read_bytes())
        manifest = self._read_manifest()
        manifest[rel_path.replace("\\", "/")] = digest
        self._write_manifest(manifest)
        return digest

    def get(self, rel_path: str) -> bytes:
        target = self._resolve_path(rel_path)
        if not target.exists():
            raise FileNotFoundError(rel_path)
        return target.read_bytes()

    def recover(self) -> dict[str, str]:
        # BUG 3: Does not remove orphaned .tmp files or restore .bak files when target is missing!
        return self._read_manifest()
''',
        },
        "reference_files": {
            "src/atomicvault/storage.py": r'''"""Atomic file storage with SHA-256 manifest and crash recovery."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO


class VaultSecurityError(ValueError):
    """Raised when a relative path attempts to escape the vault root."""


class VaultWriteError(RuntimeError):
    """Raised when an artifact write fails."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AtomicVault:
    """Manages atomic file writes, backups, and a SHA-256 manifest."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        if not self.manifest_path.exists():
            self._write_manifest({})

    def _resolve_path(self, rel_path: str) -> Path:
        clean = rel_path.replace("\\", "/").strip()
        if not clean or clean.startswith("/") or ":" in clean:
            raise VaultSecurityError(f"Unsafe path: {rel_path}")
        parts = Path(clean).parts
        if ".." in parts:
            raise VaultSecurityError(f"Path traversal rejected: {rel_path}")
        candidate = (self.root / clean).resolve()
        if not candidate.is_relative_to(self.root) or candidate == self.root:
            raise VaultSecurityError(f"Path escapes vault root: {rel_path}")
        if candidate == self.manifest_path or candidate.name.endswith((".tmp", ".bak")):
            raise VaultSecurityError(f"Reserved vault filename rejected: {rel_path}")
        return candidate

    def _read_manifest(self) -> dict[str, str]:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, data: dict[str, str]) -> None:
        tmp_manifest = self.root / f".manifest.{uuid.uuid4().hex[:8]}.tmp"
        try:
            tmp_manifest.write_text(
                json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
            )
            os.replace(tmp_manifest, self.manifest_path)
        finally:
            tmp_manifest.unlink(missing_ok=True)

    def put(
        self,
        rel_path: str,
        content_or_writer: bytes | Callable[[BinaryIO], None],
        keep_backup: bool = True,
    ) -> str:
        target = self._resolve_path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
        bak_path = target.with_name(target.name + ".bak")

        try:
            with open(tmp_path, "wb") as f:
                if callable(content_or_writer):
                    content_or_writer(f)
                else:
                    f.write(content_or_writer)
                f.flush()
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise VaultWriteError(f"Failed writing {rel_path}: {exc}") from exc

        if keep_backup and target.exists():
            shutil.copy2(target, bak_path)

        os.replace(tmp_path, target)
        digest = sha256_bytes(target.read_bytes())
        manifest = self._read_manifest()
        norm_rel = target.relative_to(self.root).as_posix()
        manifest[norm_rel] = digest
        self._write_manifest(manifest)
        return digest

    def get(self, rel_path: str) -> bytes:
        target = self._resolve_path(rel_path)
        if not target.exists():
            raise FileNotFoundError(rel_path)
        return target.read_bytes()

    def recover(self) -> dict[str, str]:
        # Step 1: Delete any orphaned .tmp files
        for tmp_file in list(self.root.rglob("*.tmp")):
            if tmp_file.is_file():
                tmp_file.unlink(missing_ok=True)

        # Step 2: Restore any .bak file whose primary artifact file is missing
        for bak_file in list(self.root.rglob("*.bak")):
            if not bak_file.is_file():
                continue
            primary = bak_file.with_name(bak_file.name[:-4])
            if not primary.exists():
                os.replace(bak_file, primary)

        # Step 3: Rebuild manifest from live artifact files
        rebuilt: dict[str, str] = {}
        for fpath in sorted(self.root.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath == self.manifest_path or fpath.name.endswith((".tmp", ".bak")):
                continue
            rel = fpath.relative_to(self.root).as_posix()
            rebuilt[rel] = sha256_bytes(fpath.read_bytes())

        self._write_manifest(rebuilt)
        return rebuilt
''',
        },
        "incomplete_files": {
            "src/atomicvault/storage.py": r'''"""Atomic file storage with SHA-256 manifest and crash recovery."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO


class VaultSecurityError(ValueError):
    pass


class VaultWriteError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AtomicVault:
    def __init__(self, root_dir: str | Path) -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        if not self.manifest_path.exists():
            self._write_manifest({})

    def _resolve_path(self, rel_path: str) -> Path:
        clean = rel_path.replace("\\", "/").strip()
        if not clean or clean.startswith("/"):
            raise VaultSecurityError(rel_path)
        candidate = (self.root / clean).resolve()
        if not candidate.is_relative_to(self.root):
            raise VaultSecurityError(rel_path)
        return candidate

    def _read_manifest(self) -> dict[str, str]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, data: dict[str, str]) -> None:
        self.manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def put(
        self,
        rel_path: str,
        content_or_writer: bytes | Callable[[BinaryIO], None],
        keep_backup: bool = True,
    ) -> str:
        target = self._resolve_path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(target.name + ".tmp")
        bak_path = target.with_name(target.name + ".bak")
        try:
            with open(tmp_path, "wb") as f:
                if callable(content_or_writer):
                    content_or_writer(f)
                else:
                    f.write(content_or_writer)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise VaultWriteError(str(exc)) from exc

        if keep_backup and target.exists():
            shutil.copy2(target, bak_path)
        os.replace(tmp_path, target)
        digest = sha256_bytes(target.read_bytes())
        m = self._read_manifest()
        m[target.relative_to(self.root).as_posix()] = digest
        self._write_manifest(m)
        return digest

    def get(self, rel_path: str) -> bytes:
        target = self._resolve_path(rel_path)
        return target.read_bytes()

    def recover(self) -> dict[str, str]:
        # Incomplete: still does not clean .tmp or restore .bak in recover()!
        return self._read_manifest()
''',
        },
        "regression_files": {
            "src/atomicvault/storage.py": r'''"""Atomic file storage with SHA-256 manifest and crash recovery."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO


class VaultSecurityError(ValueError):
    pass


class VaultWriteError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AtomicVault:
    def __init__(self, root_dir: str | Path) -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"

    def put(
        self,
        rel_path: str,
        content_or_writer: bytes | Callable[[BinaryIO], None],
        keep_backup: bool = True,
    ) -> str:
        # REGRESSION: Does not write manifest.json at all!
        target = (self.root / rel_path).resolve()
        if not target.is_relative_to(self.root):
            raise VaultSecurityError("Traversal")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            if callable(content_or_writer):
                content_or_writer(f)
            else:
                f.write(content_or_writer)
        return ""

    def get(self, rel_path: str) -> bytes:
        return (self.root / rel_path).read_bytes()

    def recover(self) -> dict[str, str]:
        return {}
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for atomicvault."""

import json
from atomicvault import AtomicVault, sha256_bytes


def test_put_and_get_updates_manifest(tmp_path):
    vault = AtomicVault(tmp_path / "vault")
    digest = vault.put("configs/app.bin", b"hello-world")
    assert digest == sha256_bytes(b"hello-world")
    assert vault.get("configs/app.bin") == b"hello-world"

    manifest = json.loads((tmp_path / "vault" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["configs/app.bin"] == digest
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for atomicvault-012."""

import pytest
from atomicvault import AtomicVault, VaultSecurityError, VaultWriteError, sha256_bytes


def test_failed_midstream_write_preserves_existing_file_and_cleans_temp(tmp_path):
    vault = AtomicVault(tmp_path / "vault")
    vault.put("data/state.json", b'{"version": 1}')

    def failing_writer(f):
        f.write(b'{"version": ')
        raise RuntimeError("disk I/O interruption")

    with pytest.raises(VaultWriteError):
        vault.put("data/state.json", failing_writer, keep_backup=True)

    # Original file must still exist intact!
    assert vault.get("data/state.json") == b'{"version": 1}'
    # No .tmp files may remain
    assert list((tmp_path / "vault").rglob("*.tmp")) == []


def test_recover_restores_orphaned_bak_and_removes_tmp_and_rebuilds_manifest(tmp_path):
    vault_dir = tmp_path / "vault"
    vault = AtomicVault(vault_dir)
    vault.put("models/weights.bin", b"v1_weights")

    # Simulate an external crash where primary was removed, .bak exists, and an orphan .tmp exists
    primary = vault_dir / "models" / "weights.bin"
    bak = vault_dir / "models" / "weights.bin.bak"
    orphan_tmp = vault_dir / "models" / "weights.bin.tmp"
    primary.replace(bak)
    orphan_tmp.write_bytes(b"corrupted_partial")

    rebuilt = vault.recover()
    assert not orphan_tmp.exists()
    assert primary.exists()
    assert vault.get("models/weights.bin") == b"v1_weights"
    assert rebuilt["models/weights.bin"] == sha256_bytes(b"v1_weights")


def test_nested_path_traversal_rejected(tmp_path):
    vault = AtomicVault(tmp_path / "vault")
    with pytest.raises(VaultSecurityError):
        vault.put("subdir/../../outside.txt", b"exploit")
''',
        "private_tests": '''"""Private security and backup rotation tests for atomicvault-012."""

import pytest
from atomicvault import AtomicVault, VaultSecurityError


def test_reserved_filenames_and_backup_preservation(tmp_path):
    vault = AtomicVault(tmp_path / "vault")
    with pytest.raises(VaultSecurityError):
        vault.put("manifest.json", b"{}")
    with pytest.raises(VaultSecurityError):
        vault.put("secret.tmp", b"123")

    vault.put("doc.txt", b"first")
    vault.put("doc.txt", b"second", keep_backup=True)
    assert vault.get("doc.txt") == b"second"
    assert (tmp_path / "vault" / "doc.txt.bak").read_bytes() == b"first"
''',
    },
]
