"""Idempotent request processor and payload fingerprinting."""

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
