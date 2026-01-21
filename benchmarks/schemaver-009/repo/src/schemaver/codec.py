"""Versioned event codec and schema migrations."""

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
