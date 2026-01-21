"""Data models for pagiflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PaginationError(Exception):
    """Raised when pagination encounters a cycle or malformed response."""


@dataclass
class PaginationConfig:
    max_pages: int = 100
    id_key: str | None = "id"
    deduplicate: bool = True
    stop_on_empty_page: bool = False
    detect_cycles: bool = True


@dataclass
class PageEnvelope:
    items: list[dict[str, Any]] = field(default_factory=list)
    next_cursor: str | int | None = None
    has_more: bool | None = None
    total_count: int | None = None
