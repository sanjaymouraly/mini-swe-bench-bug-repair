"""Models for streamparse."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorPolicy(StrEnum):
    RAISE = "raise"
    SKIP = "skip"
    QUARANTINE = "quarantine"


class MalformedRecordError(ValueError):
    """Raised when a record is invalid and policy is RAISE."""


@dataclass
class ParsedRecord:
    line_number: int
    byte_offset: int
    data: dict[str, Any]


@dataclass
class QuarantinedRecord:
    line_number: int
    byte_offset: int
    raw_line: str
    reason: str


@dataclass
class StreamSummary:
    records: list[ParsedRecord] = field(default_factory=list)
    quarantined: list[QuarantinedRecord] = field(default_factory=list)
    skipped_count: int = 0
    total_bytes_processed: int = 0
