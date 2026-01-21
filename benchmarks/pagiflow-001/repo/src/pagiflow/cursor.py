"""Envelope normalization utilities."""

from __future__ import annotations

from typing import Any

from pagiflow.models import PageEnvelope, PaginationError


def normalize_envelope(raw: dict[str, Any]) -> PageEnvelope:
    """Normalize diverse REST API response envelopes into a PageEnvelope."""
    if not isinstance(raw, dict):
        raise PaginationError(f"Expected dict response envelope, got {type(raw).__name__}")

    if "items" in raw and isinstance(raw["items"], list):
        items = raw["items"]
    elif "data" in raw and isinstance(raw["data"], list):
        items = raw["data"]
    elif "results" in raw and isinstance(raw["results"], list):
        items = raw["results"]
    else:
        raise PaginationError("Envelope missing 'items', 'data', or 'results' list")

    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    next_cursor = raw.get("next_cursor", meta.get("next_cursor"))
    has_more = raw.get("has_more", meta.get("has_more"))
    total_count = raw.get("total_count", meta.get("total_count"))

    return PageEnvelope(
        items=list(items),
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
    )
