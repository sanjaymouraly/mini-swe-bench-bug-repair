"""Benchmark task definitions 005 to 008."""

from __future__ import annotations

from typing import Any

TASKS_PART2: list[dict[str, Any]] = [
    # =========================================================================
    # TASK 005: chronoshift-005 (Hard — Time zones, daylight-saving transitions, and date handling)
    # =========================================================================
    {
        "task_id": "chronoshift-005",
        "title": "Fix DST wall-clock drift, nonexistent spring-forward times, and UTC elapsed calculation",
        "difficulty": "hard",
        "category": "timezone_dst",
        "package_name": "chronoshift",
        "summary": "DailyWindowScheduler shifts wall-clock hours across DST transitions by adding UTC timedeltas, fails to detect nonexistent spring-forward gap times, and miscomputes real elapsed seconds across offset changes.",
        "allowed_files": ["src/chronoshift/scheduler.py"],
        "issue_md": """# Issue: DST wall-clock drift, spring-forward gap handling, and elapsed duration errors in `chronoshift`

## Description
`chronoshift` calculates timezone-aware maintenance windows and real elapsed SLA durations using `zoneinfo`. Three bugs occur across Daylight Saving Time transitions (e.g., `America/New_York`):

1. **`generate_daily_occurrences` shifts wall-clock hour after DST transition**:
   `generate_daily_occurrences(start_date, days, hour, minute, tz_name)` converts the initial timestamp to UTC and adds `timedelta(days=i)` in UTC before converting back to `ZoneInfo(tz_name)`. Across the spring-forward transition (`2026-03-08`), a `09:00 America/New_York` schedule shifts to `10:00 EDT`! Each day's occurrence must be anchored to `(hour, minute)` in the target timezone's local wall clock.
2. **`resolve_wall_time` fails to detect nonexistent spring-forward times**:
   During spring-forward (`2026-03-08` in `America/New_York`, where `02:00` jumps to `03:00`), `02:30` does not exist. Python's `datetime(..., tzinfo=tz)` does not raise automatically; a time is nonexistent if converting `dt.astimezone(UTC).astimezone(tz)` produces a different local wall time `(hour, minute)` or offset than `dt`.
   - When `nonexistent_policy == "raise"`, `resolve_wall_time` must raise `NonExistentTimeError`.
   - When `nonexistent_policy == "shift_forward"`, it must advance to the valid post-transition instant (`dt.astimezone(UTC).astimezone(tz)` or the start of the new hour `03:00 EDT` — specifically, shifting forward by the gap duration, which `dt.replace(fold=0).astimezone(UTC).astimezone(tz)` gives in Python's `zoneinfo`, or shifting to the exact post-transition minute `03:30 EDT` / `03:00 EDT`: let's standardize on `dt.replace(fold=0).astimezone(UTC).astimezone(tz)` so `02:30` shifts forward by the 1-hour DST gap to `03:30 EDT`!).
3. **`real_elapsed_seconds(start_dt, end_dt)` strips tzinfo instead of comparing in UTC**:
   Stripping `tzinfo` treats the 23-hour spring-forward day as 24 hours and the 25-hour fall-back day as 24 hours. It must convert both aware datetimes to `UTC` before subtracting.

## Expected Behavior
- `generate_daily_occurrences` preserves local wall-clock `(hour, minute)` across DST transitions.
- `resolve_wall_time` detects nonexistent spring-forward wall times, raising `NonExistentTimeError` on `"raise"` and shifting forward by the DST gap (`dt.replace(fold=0).astimezone(UTC).astimezone(tz)`) on `"shift_forward"`, and respects `fold` (`0` vs `1`) for ambiguous fall-back times.
- `real_elapsed_seconds` returns exact UTC elapsed seconds between two timezone-aware datetimes.
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/chronoshift/__init__.py": '''"""chronoshift: Timezone-aware recurring window and SLA duration calculator."""

from chronoshift.scheduler import (
    DailyWindowScheduler,
    NonExistentTimeError,
    real_elapsed_seconds,
    resolve_wall_time,
)

__all__ = [
    "DailyWindowScheduler",
    "NonExistentTimeError",
    "real_elapsed_seconds",
    "resolve_wall_time",
]
''',
            "src/chronoshift/scheduler.py": '''"""Timezone-aware scheduling and DST transition utilities."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


class NonExistentTimeError(ValueError):
    """Raised when a local wall-clock time falls inside a DST spring-forward gap."""


def resolve_wall_time(
    target_date: date,
    hour: int,
    minute: int,
    tz_name: str,
    nonexistent_policy: str = "shift_forward",
    fold: int = 0,
) -> datetime:
    """Resolve a local wall-clock (date, hour, minute) in `tz_name`."""
    tz = ZoneInfo(tz_name)
    # BUG: Does not check whether (target_date, hour, minute) is nonexistent in tz!
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=tz,
        fold=fold,
    )


def real_elapsed_seconds(start_dt: datetime, end_dt: datetime) -> float:
    """Return actual elapsed seconds between two timezone-aware datetimes."""
    if start_dt.tzinfo is None or end_dt.tzinfo is None:
        raise ValueError("Both start_dt and end_dt must be timezone-aware")
    # BUG: Strips tzinfo instead of converting to UTC, miscounting across DST!
    naive_start = start_dt.replace(tzinfo=None)
    naive_end = end_dt.replace(tzinfo=None)
    return (naive_end - naive_start).total_seconds()


class DailyWindowScheduler:
    """Generates recurring daily schedule instants in a target timezone."""

    def __init__(self, tz_name: str = "UTC", nonexistent_policy: str = "shift_forward") -> None:
        self.tz_name = tz_name
        self.nonexistent_policy = nonexistent_policy

    def generate_daily_occurrences(
        self,
        start_date: date,
        days: int,
        hour: int,
        minute: int = 0,
    ) -> list[datetime]:
        if days <= 0:
            return []
        tz = ZoneInfo(self.tz_name)
        first = resolve_wall_time(
            start_date, hour, minute, self.tz_name, nonexistent_policy=self.nonexistent_policy
        )
        first_utc = first.astimezone(UTC)
        # BUG: Adds 24h increments in UTC, shifting local wall time across DST!
        return [(first_utc + timedelta(days=i)).astimezone(tz) for i in range(days)]
''',
        },
        "reference_files": {
            "src/chronoshift/scheduler.py": '''"""Timezone-aware scheduling and DST transition utilities."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


class NonExistentTimeError(ValueError):
    """Raised when a local wall-clock time falls inside a DST spring-forward gap."""


def _is_nonexistent_wall_time(dt: datetime, tz: ZoneInfo) -> bool:
    roundtrip = dt.replace(fold=0).astimezone(UTC).astimezone(tz)
    return (
        roundtrip.year != dt.year
        or roundtrip.month != dt.month
        or roundtrip.day != dt.day
        or roundtrip.hour != dt.hour
        or roundtrip.minute != dt.minute
    )


def resolve_wall_time(
    target_date: date,
    hour: int,
    minute: int,
    tz_name: str,
    nonexistent_policy: str = "shift_forward",
    fold: int = 0,
) -> datetime:
    """Resolve a local wall-clock (date, hour, minute) in `tz_name`."""
    tz = ZoneInfo(tz_name)
    candidate = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=tz,
        fold=fold,
    )
    if _is_nonexistent_wall_time(candidate, tz):
        if nonexistent_policy == "raise":
            raise NonExistentTimeError(
                f"Nonexistent local time {target_date} {hour:02d}:{minute:02d} in {tz_name}"
            )
        if nonexistent_policy == "shift_forward":
            return candidate.replace(fold=0).astimezone(UTC).astimezone(tz)
        raise ValueError(f"Unsupported nonexistent_policy: {nonexistent_policy}")
    return candidate


def real_elapsed_seconds(start_dt: datetime, end_dt: datetime) -> float:
    """Return actual elapsed seconds between two timezone-aware datetimes."""
    if start_dt.tzinfo is None or end_dt.tzinfo is None:
        raise ValueError("Both start_dt and end_dt must be timezone-aware")
    return (end_dt.astimezone(UTC) - start_dt.astimezone(UTC)).total_seconds()


class DailyWindowScheduler:
    """Generates recurring daily schedule instants in a target timezone."""

    def __init__(self, tz_name: str = "UTC", nonexistent_policy: str = "shift_forward") -> None:
        self.tz_name = tz_name
        self.nonexistent_policy = nonexistent_policy

    def generate_daily_occurrences(
        self,
        start_date: date,
        days: int,
        hour: int,
        minute: int = 0,
    ) -> list[datetime]:
        if days <= 0:
            return []
        occurrences: list[datetime] = []
        for i in range(days):
            cur_date = start_date + timedelta(days=i)
            dt = resolve_wall_time(
                cur_date,
                hour,
                minute,
                self.tz_name,
                nonexistent_policy=self.nonexistent_policy,
            )
            occurrences.append(dt)
        return occurrences
''',
        },
        "incomplete_files": {
            "src/chronoshift/scheduler.py": '''"""Timezone-aware scheduling and DST transition utilities."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


class NonExistentTimeError(ValueError):
    """Raised when a local wall-clock time falls inside a DST spring-forward gap."""


def resolve_wall_time(
    target_date: date,
    hour: int,
    minute: int,
    tz_name: str,
    nonexistent_policy: str = "shift_forward",
    fold: int = 0,
) -> datetime:
    tz = ZoneInfo(tz_name)
    # Incomplete: still does not detect nonexistent spring-forward times!
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=tz,
        fold=fold,
    )


def real_elapsed_seconds(start_dt: datetime, end_dt: datetime) -> float:
    if start_dt.tzinfo is None or end_dt.tzinfo is None:
        raise ValueError("Both start_dt and end_dt must be timezone-aware")
    return (end_dt.astimezone(UTC) - start_dt.astimezone(UTC)).total_seconds()


class DailyWindowScheduler:
    def __init__(self, tz_name: str = "UTC", nonexistent_policy: str = "shift_forward") -> None:
        self.tz_name = tz_name
        self.nonexistent_policy = nonexistent_policy

    def generate_daily_occurrences(
        self,
        start_date: date,
        days: int,
        hour: int,
        minute: int = 0,
    ) -> list[datetime]:
        return [
            resolve_wall_time(start_date + timedelta(days=i), hour, minute, self.tz_name)
            for i in range(max(0, days))
        ]
''',
        },
        "regression_files": {
            "src/chronoshift/scheduler.py": '''"""Timezone-aware scheduling and DST transition utilities."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


class NonExistentTimeError(ValueError):
    pass


def resolve_wall_time(
    target_date: date,
    hour: int,
    minute: int,
    tz_name: str,
    nonexistent_policy: str = "shift_forward",
    fold: int = 0,
) -> datetime:
    tz = ZoneInfo(tz_name)
    dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=tz, fold=fold)
    rt = dt.replace(fold=0).astimezone(UTC).astimezone(tz)
    if (rt.hour, rt.minute) != (dt.hour, dt.minute):
        if nonexistent_policy == "raise":
            raise NonExistentTimeError("Gap")
        return rt
    return dt


def real_elapsed_seconds(start_dt: datetime, end_dt: datetime) -> float:
    # REGRESSION: Accepts naive datetimes without raising ValueError and returns abs() instead of signed!
    return abs((end_dt - start_dt).total_seconds())


class DailyWindowScheduler:
    def __init__(self, tz_name: str = "UTC", nonexistent_policy: str = "shift_forward") -> None:
        self.tz_name = tz_name
        self.nonexistent_policy = nonexistent_policy

    def generate_daily_occurrences(
        self,
        start_date: date,
        days: int,
        hour: int,
        minute: int = 0,
    ) -> list[datetime]:
        return [
            resolve_wall_time(start_date + timedelta(days=i), hour, minute, self.tz_name, self.nonexistent_policy)
            for i in range(days)
        ]
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for chronoshift."""

from datetime import UTC, date, datetime
import pytest
from chronoshift import DailyWindowScheduler, real_elapsed_seconds, resolve_wall_time


def test_utc_daily_schedule():
    sched = DailyWindowScheduler("UTC")
    occ = sched.generate_daily_occurrences(date(2026, 1, 10), days=3, hour=14, minute=30)
    assert len(occ) == 3
    assert [d.hour for d in occ] == [14, 14, 14]
    assert [d.day for d in occ] == [10, 11, 12]


def test_real_elapsed_seconds_rejects_naive_datetime():
    aware = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    naive = datetime(2026, 1, 1, 13, 0)
    with pytest.raises(ValueError):
        real_elapsed_seconds(aware, naive)


def test_resolve_normal_wall_time():
    dt = resolve_wall_time(date(2026, 6, 15), 10, 15, "America/New_York")
    assert dt.hour == 10
    assert dt.minute == 15
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for chronoshift-005."""

from datetime import date
import pytest
from chronoshift import (
    DailyWindowScheduler,
    NonExistentTimeError,
    real_elapsed_seconds,
    resolve_wall_time,
)


def test_daily_schedule_preserves_wall_clock_across_spring_forward_dst():
    # America/New_York springs forward on 2026-03-08
    sched = DailyWindowScheduler("America/New_York")
    occ = sched.generate_daily_occurrences(date(2026, 3, 7), days=3, hour=9, minute=0)
    assert [(d.hour, d.minute) for d in occ] == [(9, 0), (9, 0), (9, 0)]
    # Real elapsed time between 09:00 EST on Mar 7 and 09:00 EDT on Mar 8 is 23 hours (82800s)
    assert real_elapsed_seconds(occ[0], occ[1]) == 23 * 3600


def test_nonexistent_spring_forward_time_raise_and_shift():
    # 2026-03-08 02:30 does not exist in America/New_York
    with pytest.raises(NonExistentTimeError):
        resolve_wall_time(
            date(2026, 3, 8), 2, 30, "America/New_York", nonexistent_policy="raise"
        )

    shifted = resolve_wall_time(
        date(2026, 3, 8), 2, 30, "America/New_York", nonexistent_policy="shift_forward"
    )
    assert (shifted.hour, shifted.minute) == (3, 30)
''',
        "private_tests": '''"""Private DST fall-back fold and 25-hour day tests for chronoshift-005."""

from datetime import date
from chronoshift import DailyWindowScheduler, real_elapsed_seconds, resolve_wall_time


def test_fall_back_25_hour_day_and_fold_disambiguation():
    # America/New_York falls back on 2026-11-01 at 02:00 -> 01:00
    sched = DailyWindowScheduler("America/New_York")
    occ = sched.generate_daily_occurrences(date(2026, 10, 31), days=3, hour=9, minute=0)
    assert [(d.hour, d.minute) for d in occ] == [(9, 0), (9, 0), (9, 0)]
    # Between Oct 31 09:00 EDT and Nov 1 09:00 EST is 25 hours (90000s)
    assert real_elapsed_seconds(occ[0], occ[1]) == 25 * 3600

    # Ambiguous time 01:30 on 2026-11-01 has fold=0 (EDT) and fold=1 (EST), 3600s apart
    first_130 = resolve_wall_time(date(2026, 11, 1), 1, 30, "America/New_York", fold=0)
    second_130 = resolve_wall_time(date(2026, 11, 1), 1, 30, "America/New_York", fold=1)
    assert real_elapsed_seconds(first_130, second_130) == 3600.0
''',
    },
    # =========================================================================
    # TASK 006: streamparse-006 (Medium — Streaming file parsing and malformed records)
    # =========================================================================
    {
        "task_id": "streamparse-006",
        "title": "Fix multi-byte UTF-8 chunk boundary splitting and byte-offset tracking on quarantined records",
        "difficulty": "medium",
        "category": "streaming_parser",
        "package_name": "streamparse",
        "summary": "ChunkedNDJSONReader decodes byte chunks before splitting lines (failing when multi-byte UTF-8 chars or CRLF split across chunks) and fails to advance byte_offset when quarantining/skipping malformed records.",
        "allowed_files": ["src/streamparse/reader.py", "src/streamparse/models.py"],
        "issue_md": """# Issue: `ChunkedNDJSONReader` corrupts multi-byte UTF-8 across chunk boundaries and miscalculates `byte_offset` after malformed lines

## Description
`ChunkedNDJSONReader` streams arbitrary-sized `bytes` chunks of NDJSON records with configurable `ErrorPolicy` (`RAISE`, `SKIP`, `QUARANTINE`) and required field validation. Two bugs occur:

1. **Multi-byte UTF-8 characters split across `bytes` chunks**:
   `parse_chunks()` calls `chunk.decode("utf-8")` on each incoming `bytes` chunk individually before buffering. When a multi-byte UTF-8 sequence (e.g., `€`, `é`, `🚀`) straddles the boundary between two chunks, `chunk.decode("utf-8")` raises `UnicodeDecodeError`! The reader must buffer raw `bytes` (splitting on `b"\\n"`) and decode complete lines, or use an incremental decoder while tracking exact raw byte lengths.
2. **Incorrect `byte_offset` after malformed records in `QUARANTINE` / `SKIP` mode**:
   Each `ParsedRecord` and `QuarantinedRecord` records the starting `byte_offset` (0-indexed byte position in the stream where that line began, including `\\r\\n` or `\\n` lengths of prior lines) and 1-indexed `line_number`. Currently, when a line fails JSON parsing or required-field validation, the error branch `continue`s before advancing `current_byte_offset += len(raw_line_with_newline)`, causing all subsequent records to have shifted byte offsets!

## Expected Behavior
- Arbitrary chunk boundaries (even 1-byte or 3-byte chunks splitting multi-byte UTF-8 characters or `\\r\\n` delimiters) must produce identical parsed records to single-chunk parsing.
- Empty/whitespace-only lines must still advance `current_byte_offset` by their exact byte length and increment `line_number`.
- Malformed JSON lines or records missing `required_fields` must be handled according to `error_policy` (`RAISE`, `SKIP`, `QUARANTINE`), and `current_byte_offset` must always advance by the exact raw byte length of every line (including its trailing `\\r\\n` or `\\n`).
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/streamparse/__init__.py": '''"""streamparse: Chunked streaming NDJSON parser with quarantine recovery."""

from streamparse.models import (
    ErrorPolicy,
    MalformedRecordError,
    ParsedRecord,
    QuarantinedRecord,
    StreamSummary,
)
from streamparse.reader import ChunkedNDJSONReader

__all__ = [
    "ChunkedNDJSONReader",
    "ErrorPolicy",
    "MalformedRecordError",
    "ParsedRecord",
    "QuarantinedRecord",
    "StreamSummary",
]
''',
            "src/streamparse/models.py": '''"""Models for streamparse."""

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
''',
            "src/streamparse/reader.py": r'''"""Chunked NDJSON stream reader."""

from __future__ import annotations

import json
from collections.abc import Iterable

from streamparse.models import (
    ErrorPolicy,
    MalformedRecordError,
    ParsedRecord,
    QuarantinedRecord,
    StreamSummary,
)


class ChunkedNDJSONReader:
    """Parses streaming byte chunks of NDJSON records with offset tracking."""

    def __init__(
        self,
        error_policy: ErrorPolicy = ErrorPolicy.QUARANTINE,
        required_fields: list[str] | None = None,
    ) -> None:
        self.error_policy = ErrorPolicy(error_policy)
        self.required_fields = required_fields or []

    def parse_chunks(self, chunks: Iterable[bytes]) -> StreamSummary:
        summary = StreamSummary()
        # BUG 1: Decodes each chunk independently as str, crashing when multi-byte UTF-8 splits across chunks!
        text_buf = ""
        line_number = 0
        byte_offset = 0

        for chunk in chunks:
            text_buf += chunk.decode("utf-8")
            while "\n" in text_buf:
                line_str, text_buf = text_buf.split("\n", 1)
                line_number += 1
                raw_len = len(line_str.encode("utf-8")) + 1
                stripped = line_str.strip()
                if not stripped:
                    byte_offset += raw_len
                    continue

                self._process_line(
                    stripped, line_number, byte_offset, raw_len, summary
                )
                # BUG 2: _process_line only updates byte_offset on success inside or inconsistent!

        if text_buf.strip():
            line_number += 1
            raw_len = len(text_buf.encode("utf-8"))
            self._process_line(text_buf.strip(), line_number, byte_offset, raw_len, summary)

        return summary

    def _process_line(
        self,
        stripped: str,
        line_number: int,
        byte_offset: int,
        raw_len: int,
        summary: StreamSummary,
    ) -> None:
        try:
            obj = json.loads(stripped)
            if not isinstance(obj, dict):
                raise ValueError("Record must be a JSON object")
            for req in self.required_fields:
                if req not in obj:
                    raise ValueError(f"Missing required field: {req}")
        except Exception as exc:
            if self.error_policy == ErrorPolicy.RAISE:
                raise MalformedRecordError(f"Line {line_number}: {exc}") from exc
            elif self.error_policy == ErrorPolicy.SKIP:
                summary.skipped_count += 1
                return
            else:
                summary.quarantined.append(
                    QuarantinedRecord(
                        line_number=line_number,
                        byte_offset=byte_offset,
                        raw_line=stripped,
                        reason=str(exc),
                    )
                )
                return

        summary.records.append(
            ParsedRecord(line_number=line_number, byte_offset=byte_offset, data=obj)
        )
        summary.total_bytes_processed += raw_len
''',
        },
        "reference_files": {
            "src/streamparse/reader.py": r'''"""Chunked NDJSON stream reader."""

from __future__ import annotations

import json
from collections.abc import Iterable

from streamparse.models import (
    ErrorPolicy,
    MalformedRecordError,
    ParsedRecord,
    QuarantinedRecord,
    StreamSummary,
)


class ChunkedNDJSONReader:
    """Parses streaming byte chunks of NDJSON records with exact byte-offset tracking."""

    def __init__(
        self,
        error_policy: ErrorPolicy = ErrorPolicy.QUARANTINE,
        required_fields: list[str] | None = None,
    ) -> None:
        self.error_policy = ErrorPolicy(error_policy)
        self.required_fields = required_fields or []

    def parse_chunks(self, chunks: Iterable[bytes]) -> StreamSummary:
        summary = StreamSummary()
        byte_buf = bytearray()
        line_number = 0
        byte_offset = 0

        for chunk in chunks:
            if not chunk:
                continue
            byte_buf.extend(chunk)
            while True:
                nl_idx = byte_buf.find(b"\n")
                if nl_idx == -1:
                    break
                raw_line = bytes(byte_buf[: nl_idx + 1])
                del byte_buf[: nl_idx + 1]
                line_len = len(raw_line)
                line_number += 1
                self._consume_raw_line(raw_line, line_number, byte_offset, summary)
                byte_offset += line_len
                summary.total_bytes_processed += line_len

        if byte_buf:
            raw_line = bytes(byte_buf)
            line_len = len(raw_line)
            if raw_line.strip():
                line_number += 1
                self._consume_raw_line(raw_line, line_number, byte_offset, summary)
            byte_offset += line_len
            summary.total_bytes_processed += line_len

        return summary

    def _consume_raw_line(
        self,
        raw_line: bytes,
        line_number: int,
        byte_offset: int,
        summary: StreamSummary,
    ) -> None:
        content_bytes = raw_line.rstrip(b"\r\n")
        if not content_bytes.strip():
            return

        try:
            line_str = content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            self._handle_error(
                raw_text=content_bytes.decode("utf-8", errors="replace"),
                line_number=line_number,
                byte_offset=byte_offset,
                reason=f"Invalid UTF-8 encoding: {exc}",
                summary=summary,
            )
            return

        stripped = line_str.strip()
        try:
            obj = json.loads(stripped)
            if not isinstance(obj, dict):
                raise ValueError("Record must be a JSON object")
            for req in self.required_fields:
                if req not in obj:
                    raise ValueError(f"Missing required field: {req}")
        except Exception as exc:
            self._handle_error(
                raw_text=stripped,
                line_number=line_number,
                byte_offset=byte_offset,
                reason=str(exc),
                summary=summary,
            )
            return

        summary.records.append(
            ParsedRecord(line_number=line_number, byte_offset=byte_offset, data=obj)
        )

    def _handle_error(
        self,
        raw_text: str,
        line_number: int,
        byte_offset: int,
        reason: str,
        summary: StreamSummary,
    ) -> None:
        if self.error_policy == ErrorPolicy.RAISE:
            raise MalformedRecordError(f"Line {line_number}: {reason}")
        if self.error_policy == ErrorPolicy.SKIP:
            summary.skipped_count += 1
            return
        summary.quarantined.append(
            QuarantinedRecord(
                line_number=line_number,
                byte_offset=byte_offset,
                raw_line=raw_text,
                reason=reason,
            )
        )
''',
        },
        "incomplete_files": {
            "src/streamparse/reader.py": r'''"""Chunked NDJSON stream reader."""

from __future__ import annotations

import json
from collections.abc import Iterable

from streamparse.models import (
    ErrorPolicy,
    MalformedRecordError,
    ParsedRecord,
    QuarantinedRecord,
    StreamSummary,
)


class ChunkedNDJSONReader:
    def __init__(
        self,
        error_policy: ErrorPolicy = ErrorPolicy.QUARANTINE,
        required_fields: list[str] | None = None,
    ) -> None:
        self.error_policy = ErrorPolicy(error_policy)
        self.required_fields = required_fields or []

    def parse_chunks(self, chunks: Iterable[bytes]) -> StreamSummary:
        summary = StreamSummary()
        byte_buf = bytearray()
        line_number = 0
        byte_offset = 0

        for chunk in chunks:
            byte_buf.extend(chunk)
            while b"\n" in byte_buf:
                idx = byte_buf.find(b"\n")
                raw = bytes(byte_buf[: idx + 1])
                del byte_buf[: idx + 1]
                line_number += 1
                line_str = raw.rstrip(b"\r\n").decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue
                try:
                    obj = json.loads(line_str)
                    for req in self.required_fields:
                        if req not in obj:
                            raise ValueError(f"Missing {req}")
                    summary.records.append(ParsedRecord(line_number, byte_offset, obj))
                    byte_offset += len(raw)
                except Exception as exc:
                    if self.error_policy == ErrorPolicy.RAISE:
                        raise MalformedRecordError(str(exc)) from exc
                    # Incomplete: still forgets to update byte_offset when quarantined or skipped!
                    summary.quarantined.append(QuarantinedRecord(line_number, byte_offset, line_str, str(exc)))
        return summary
''',
        },
        "regression_files": {
            "src/streamparse/reader.py": r'''"""Chunked NDJSON stream reader."""

from __future__ import annotations

import json
from collections.abc import Iterable

from streamparse.models import (
    ErrorPolicy,
    ParsedRecord,
    QuarantinedRecord,
    StreamSummary,
)


class ChunkedNDJSONReader:
    def __init__(
        self,
        error_policy: ErrorPolicy = ErrorPolicy.QUARANTINE,
        required_fields: list[str] | None = None,
    ) -> None:
        self.error_policy = ErrorPolicy(error_policy)
        self.required_fields = required_fields or []

    def parse_chunks(self, chunks: Iterable[bytes]) -> StreamSummary:
        summary = StreamSummary()
        full = b"".join(chunks)
        offset = 0
        for line_no, raw in enumerate(full.splitlines(keepends=True), start=1):
            txt = raw.rstrip(b"\r\n").decode("utf-8", errors="replace").strip()
            if txt:
                try:
                    obj = json.loads(txt)
                    summary.records.append(ParsedRecord(line_no, offset, obj))
                except Exception as exc:
                    # REGRESSION: Ignores ErrorPolicy.RAISE and required_fields validation!
                    summary.quarantined.append(QuarantinedRecord(line_no, offset, txt, str(exc)))
            offset += len(raw)
        summary.total_bytes_processed = offset
        return summary
''',
        },
        "existing_tests": r'''"""Pre-existing preservation tests for streamparse."""

import pytest
from streamparse import ChunkedNDJSONReader, ErrorPolicy, MalformedRecordError


def test_single_chunk_valid_ndjson():
    payload = b'{"id": 1, "event": "click"}\n{"id": 2, "event": "view"}\n'
    reader = ChunkedNDJSONReader(required_fields=["id", "event"])
    res = reader.parse_chunks([payload])
    assert len(res.records) == 2
    assert res.records[0].data["id"] == 1
    assert res.records[1].data["event"] == "view"


def test_raise_policy_raises_malformed_record_error():
    payload = b'{"id": 1}\nNOT_JSON\n'
    reader = ChunkedNDJSONReader(error_policy=ErrorPolicy.RAISE)
    with pytest.raises(MalformedRecordError):
        reader.parse_chunks([payload])


def test_required_fields_validation():
    payload = b'{"id": 1}\n'
    reader = ChunkedNDJSONReader(error_policy=ErrorPolicy.RAISE, required_fields=["id", "user"])
    with pytest.raises(MalformedRecordError, match="user"):
        reader.parse_chunks([payload])
''',
        "issue_tests": r'''"""Issue-specific FAIL_TO_PASS tests for streamparse-006."""

from streamparse import ChunkedNDJSONReader, ErrorPolicy


def test_multibyte_utf8_split_across_small_byte_chunks():
    # '€' is 3 bytes in UTF-8 (\xe2\x82\xac), '🚀' is 4 bytes (\xf0\x9f\x9a\x80)
    raw = '{"id": 1, "msg": "Price 99€ 🚀"}\n{"id": 2, "msg": "Café"}\n'.encode("utf-8")
    # Split into 3-byte chunks so multi-byte sequences straddle chunk boundaries
    chunks = [raw[i : i + 3] for i in range(0, len(raw), 3)]

    reader = ChunkedNDJSONReader()
    summary = reader.parse_chunks(chunks)
    assert len(summary.records) == 2
    assert summary.records[0].data["msg"] == "Price 99€ 🚀"
    assert summary.records[1].data["msg"] == "Café"
    assert summary.quarantined == []


def test_quarantine_advances_byte_offset_for_subsequent_records():
    line1 = b'{"id": 1}\n'          # 10 bytes (offset 0)
    line2 = b'{malformed_json}\n'   # 17 bytes (offset 10)
    line3 = b'{"id": 3}\n'          # 10 bytes (offset 27)
    reader = ChunkedNDJSONReader(error_policy=ErrorPolicy.QUARANTINE, required_fields=["id"])
    summary = reader.parse_chunks([line1 + line2 + line3])

    assert len(summary.records) == 2
    assert len(summary.quarantined) == 1
    assert summary.records[0].byte_offset == 0
    assert summary.quarantined[0].byte_offset == 10
    assert summary.quarantined[0].line_number == 2
    assert summary.records[1].byte_offset == 27
    assert summary.records[1].line_number == 3
    assert summary.total_bytes_processed == 37
''',
        "private_tests": r'''"""Private CRLF, trailing line without newline, and SKIP policy offset tests for streamparse-006."""

from streamparse import ChunkedNDJSONReader, ErrorPolicy


def test_crlf_split_across_chunks_and_skip_policy_offsets():
    raw = b'{"id": 1}\r\n{"missing_id": 2}\r\n{"id": 3}'
    # Split right between \r and \n
    chunks = [raw[:10], raw[10:20], raw[20:]]
    reader = ChunkedNDJSONReader(error_policy=ErrorPolicy.SKIP, required_fields=["id"])
    summary = reader.parse_chunks(chunks)

    assert summary.skipped_count == 1
    assert len(summary.records) == 2
    assert summary.records[0].byte_offset == 0
    assert summary.records[1].byte_offset == len(b'{"id": 1}\r\n{"missing_id": 2}\r\n')
    assert summary.records[1].data["id"] == 3
    assert summary.total_bytes_processed == len(raw)
''',
    },
    # =========================================================================
    # TASK 007: confighier-007 (Easy — Configuration precedence and environment overrides)
    # =========================================================================
    {
        "task_id": "confighier-007",
        "title": "Fix deep merge sibling wiping, falsy CLI overrides, and single-underscore env keys",
        "difficulty": "easy",
        "category": "config_precedence",
        "package_name": "confighier",
        "summary": "ConfigLoader wipes sibling nested keys during layer merging, ignores explicit falsy CLI overrides (False, 0, ''), and splits single underscores in env var names instead of only double underscores.",
        "allowed_files": ["src/confighier/loader.py"],
        "issue_md": """# Issue: `ConfigLoader` drops sibling nested keys, ignores `False`/`0`/`""` CLI overrides, and misparses single underscores in env vars

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
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/confighier/__init__.py": '''"""confighier: Hierarchical configuration loader with env and CLI precedence."""

from confighier.loader import ConfigLoader, coerce_env_value, deep_merge, parse_env_vars

__all__ = ["ConfigLoader", "coerce_env_value", "deep_merge", "parse_env_vars"]
''',
            "src/confighier/loader.py": '''"""Hierarchical configuration merging and environment variable parsing."""

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
''',
        },
        "reference_files": {
            "src/confighier/loader.py": '''"""Hierarchical configuration merging and environment variable parsing."""

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
    """Recursively merge `override` into `base`, ignoring only `None` override values."""
    result: dict[str, Any] = copy.deepcopy(dict(base))
    for k, v in override.items():
        if v is None:
            continue
        if isinstance(v, Mapping) and isinstance(result.get(k), Mapping):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def parse_env_vars(environ: Mapping[str, str], prefix: str = "APP") -> dict[str, Any]:
    """Extract hierarchical configuration from environment variables starting with `PREFIX__`."""
    prefix_tag = f"{prefix.upper()}__"
    parsed: dict[str, Any] = {}
    for env_key, raw_val in environ.items():
        if not env_key.startswith(prefix_tag):
            continue
        remainder = env_key[len(prefix_tag) :]
        parts = [p.lower() for p in remainder.split("__") if p]
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
        merged: dict[str, Any] = copy.deepcopy(dict(defaults))
        if profile:
            merged = deep_merge(merged, profile)
        if environ:
            env_layer = parse_env_vars(environ, prefix=self.env_prefix)
            merged = deep_merge(merged, env_layer)
        if cli_overrides:
            merged = deep_merge(merged, cli_overrides)
        return merged
''',
        },
        "incomplete_files": {
            "src/confighier/loader.py": '''"""Hierarchical configuration merging and environment variable parsing."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


def coerce_env_value(raw: str) -> Any:
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
    result: dict[str, Any] = copy.deepcopy(dict(base))
    for k, v in override.items():
        if v is None:
            continue
        if isinstance(v, Mapping) and isinstance(result.get(k), Mapping):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def parse_env_vars(environ: Mapping[str, str], prefix: str = "APP") -> dict[str, Any]:
    prefix_tag = f"{prefix.upper()}__"
    parsed: dict[str, Any] = {}
    for env_key, raw_val in environ.items():
        if not env_key.startswith(prefix_tag):
            continue
        remainder = env_key[len(prefix_tag) :]
        # Incomplete fix: still splits on single underscore!
        parts = [p.lower() for p in remainder.split("_") if p]
        cursor = parsed
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = coerce_env_value(raw_val)
    return parsed


class ConfigLoader:
    def __init__(self, env_prefix: str = "APP") -> None:
        self.env_prefix = env_prefix

    def resolve(
        self,
        defaults: Mapping[str, Any],
        profile: Mapping[str, Any] | None = None,
        environ: Mapping[str, str] | None = None,
        cli_overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = copy.deepcopy(dict(defaults))
        if profile:
            merged = deep_merge(merged, profile)
        if environ:
            merged = deep_merge(merged, parse_env_vars(environ, prefix=self.env_prefix))
        if cli_overrides:
            merged = deep_merge(merged, cli_overrides)
        return merged
''',
        },
        "regression_files": {
            "src/confighier/loader.py": '''"""Hierarchical configuration merging and environment variable parsing."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


def coerce_env_value(raw: str) -> Any:
    # REGRESSION: Returns raw string without coercing ints, bools, or comma lists!
    return raw


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = copy.deepcopy(dict(base))
    for k, v in override.items():
        if v is None:
            continue
        if isinstance(v, Mapping) and isinstance(result.get(k), Mapping):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def parse_env_vars(environ: Mapping[str, str], prefix: str = "APP") -> dict[str, Any]:
    prefix_tag = f"{prefix.upper()}__"
    parsed: dict[str, Any] = {}
    for env_key, raw_val in environ.items():
        if not env_key.startswith(prefix_tag):
            continue
        parts = [p.lower() for p in env_key[len(prefix_tag) :].split("__") if p]
        cursor = parsed
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = coerce_env_value(raw_val)
    return parsed


class ConfigLoader:
    def __init__(self, env_prefix: str = "APP") -> None:
        self.env_prefix = env_prefix

    def resolve(
        self,
        defaults: Mapping[str, Any],
        profile: Mapping[str, Any] | None = None,
        environ: Mapping[str, str] | None = None,
        cli_overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = copy.deepcopy(dict(defaults))
        if profile:
            merged = deep_merge(merged, profile)
        if environ:
            merged = deep_merge(merged, parse_env_vars(environ, prefix=self.env_prefix))
        if cli_overrides:
            merged = deep_merge(merged, cli_overrides)
        return merged
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for confighier."""

from confighier import ConfigLoader, coerce_env_value


def test_coerce_env_value_types():
    assert coerce_env_value("true") is True
    assert coerce_env_value("false") is False
    assert coerce_env_value("8080") == 8080
    assert coerce_env_value("1.5") == 1.5
    assert coerce_env_value("a,b,c") == ["a", "b", "c"]


def test_basic_top_level_override():
    loader = ConfigLoader(env_prefix="APP")
    defaults = {"host": "127.0.0.1", "port": 8000}
    res = loader.resolve(defaults, profile={"port": 9000})
    assert res == {"host": "127.0.0.1", "port": 9000}
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for confighier-007."""

from confighier import ConfigLoader


def test_deep_merge_preserves_sibling_keys_and_handles_single_underscore_env_keys():
    loader = ConfigLoader(env_prefix="APP")
    defaults = {
        "debug": True,
        "retries": 3,
        "db": {
            "host": "localhost",
            "port": 5432,
            "max_connections": 10,
        },
    }
    profile = {"db": {"port": 5433}}
    environ = {
        "APP__DB__MAX_CONNECTIONS": "50",
        "APP__DEBUG": "false",
    }
    cli_overrides = {
        "retries": 0,
        "db": {"host": None},  # None means CLI flag not provided; keep "localhost"
    }

    resolved = loader.resolve(
        defaults=defaults,
        profile=profile,
        environ=environ,
        cli_overrides=cli_overrides,
    )
    assert resolved["debug"] is False
    assert resolved["retries"] == 0
    assert resolved["db"] == {
        "host": "localhost",
        "port": 5433,
        "max_connections": 50,
    }
''',
        "private_tests": '''"""Private immutability and multi-level falsy override tests for confighier-007."""

from confighier import ConfigLoader


def test_resolve_does_not_mutate_inputs_and_preserves_empty_string_override():
    defaults = {"service": {"name": "api", "prefix": "/v1", "tags": ["a", "b"]}}
    cli = {"service": {"prefix": "", "tags": []}}
    loader = ConfigLoader()
    out = loader.resolve(defaults, cli_overrides=cli)
    assert out["service"]["name"] == "api"
    assert out["service"]["prefix"] == ""
    assert out["service"]["tags"] == []
    # Original defaults must not be mutated
    assert defaults["service"]["prefix"] == "/v1"
    assert defaults["service"]["tags"] == ["a", "b"]
''',
    },
    # =========================================================================
    # TASK 008: retryguard-008 (Medium — Retry logic, rate limiting, and backoff)
    # =========================================================================
    {
        "task_id": "retryguard-008",
        "title": "Fix max_retries off-by-one, Retry-After cap, non-retryable 4xx, and TokenBucket capacity ceiling",
        "difficulty": "medium",
        "category": "retry_ratelimit",
        "package_name": "retryguard",
        "summary": "RetryExecutor makes max_retries total attempts instead of 1 + max_retries, sleeps after the final failure, ignores max_backoff on Retry-After, retries non-retryable 4xx errors, and allows TokenBucketLimiter to exceed capacity.",
        "allowed_files": [
            "src/retryguard/executor.py",
            "src/retryguard/limiter.py",
            "src/retryguard/policy.py",
        ],
        "issue_md": """# Issue: `RetryExecutor` off-by-one attempts, trailing sleep, uncapped `Retry-After`, and `TokenBucketLimiter` overflow

## Description
`retryguard` provides `RetryExecutor` and `TokenBucketLimiter`. Four bugs were reported:

1. **Off-by-one attempt count & trailing sleep in `RetryExecutor.execute`**:
   `max_retries` specifies the number of **retries after the initial attempt** (so `max_retries=0` means 1 attempt total; `max_retries=3` means up to 4 attempts total). Currently `execute()` loops `for attempt in range(self.policy.max_retries):` (making 0 attempts when `max_retries=0`!) and calls `self._sleep(delay)` even after the final failed attempt before raising `RetryExhaustedError`.
2. **Non-retryable HTTP status codes (`400`, `401`, `403`, `404`) are retried**:
   When `HTTPError` is raised with a status code not in `policy.retryable_status_codes` (default `{408, 429, 500, 502, 503, 504}`), `RetryExecutor` should immediately re-raise the `HTTPError` without sleeping or retrying.
3. **`Retry-After` header ignores `policy.max_backoff` cap**:
   When `HTTPError(status_code=429, retry_after=300.0)` is caught, `compute_delay` uses `retry_after` directly without clamping to `min(retry_after, self.policy.max_backoff)`.
4. **`TokenBucketLimiter` uses `time.time()` instead of injected clock and exceeds `capacity`**:
   `_refill()` uses `time.time()` instead of `self._clock()` and adds refilled tokens without clamping to `min(self.capacity, self._tokens + added)`.

## Expected Behavior
- `max_retries=N` runs 1 initial attempt plus up to `N` retries, sleeping only between attempts (never after the last failed attempt).
- Non-retryable `HTTPError` status codes re-raise immediately on the first failure.
- `Retry-After` backoff is clamped to `[0.0, policy.max_backoff]`.
- `TokenBucketLimiter` uses `self._clock()` and never accumulates more than `self.capacity` tokens.
""",
        "reproduction": """pytest evaluation/test_issue.py -q""",
        "files": {
            "src/retryguard/__init__.py": '''"""retryguard: Resilient retry executor and token-bucket rate limiter."""

from retryguard.executor import RetryExecutor
from retryguard.limiter import TokenBucketLimiter
from retryguard.policy import HTTPError, RetryExhaustedError, RetryPolicy

__all__ = [
    "HTTPError",
    "RetryExecutor",
    "RetryExhaustedError",
    "RetryPolicy",
    "TokenBucketLimiter",
]
''',
            "src/retryguard/policy.py": '''"""Retry policy and HTTP error definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


class HTTPError(Exception):
    """Represents an HTTP status failure with optional Retry-After."""

    def __init__(self, status_code: int, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, attempts: int, last_exception: BaseException | None = None) -> None:
        super().__init__(f"Exhausted after {attempts} attempts: {last_exception}")
        self.attempts = attempts
        self.last_exception = last_exception


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_backoff: float = 0.5
    max_backoff: float = 10.0
    multiplier: float = 2.0
    retryable_status_codes: set[int] = field(
        default_factory=lambda: {408, 429, 500, 502, 503, 504}
    )

    def compute_delay(self, retry_index: int, retry_after: float | None = None) -> float:
        """Compute backoff delay for 0-indexed `retry_index`."""
        if retry_after is not None:
            # BUG: Does not clamp retry_after to max_backoff!
            return max(0.0, retry_after)
        raw = self.base_backoff * (self.multiplier**retry_index)
        return min(self.max_backoff, raw)
''',
            "src/retryguard/limiter.py": '''"""Token bucket rate limiter."""

from __future__ import annotations

import time
from collections.abc import Callable


class TokenBucketLimiter:
    """Token bucket rate limiter with injectable monotonic clock."""

    def __init__(
        self,
        rate_per_sec: float,
        capacity: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_sec <= 0 or capacity <= 0:
            raise ValueError("rate_per_sec and capacity must be > 0")
        self.rate_per_sec = rate_per_sec
        self.capacity = capacity
        self._clock = clock
        self._tokens = float(capacity)
        self._last_ts = self._clock()

    def _refill(self) -> None:
        # BUG: Uses time.time() instead of self._clock() and does not cap at self.capacity!
        now = time.time()
        elapsed = max(0.0, now - self._last_ts)
        self._last_ts = now
        self._tokens = self._tokens + elapsed * self.rate_per_sec

    def try_acquire(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens
''',
            "src/retryguard/executor.py": '''"""Retry executor implementation."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from retryguard.policy import HTTPError, RetryExhaustedError, RetryPolicy

T = TypeVar("T")


class RetryExecutor:
    """Executes callables with configurable retry and backoff policy."""

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self._sleep = sleep_fn
        self.sleep_history: list[float] = []

    def execute(self, func: Callable[[], T]) -> T:
        last_exc: BaseException | None = None
        attempts = 0

        # BUG: Loops range(max_retries) instead of range(max_retries + 1),
        # retries non-retryable 4xx errors, and sleeps after the final failed attempt!
        for attempt in range(self.policy.max_retries):
            attempts += 1
            try:
                return func()
            except HTTPError as exc:
                last_exc = exc
                delay = self.policy.compute_delay(attempt, retry_after=exc.retry_after)
                self.sleep_history.append(delay)
                self._sleep(delay)
            except Exception as exc:
                last_exc = exc
                delay = self.policy.compute_delay(attempt)
                self.sleep_history.append(delay)
                self._sleep(delay)

        raise RetryExhaustedError(attempts=attempts, last_exception=last_exc)
''',
        },
        "reference_files": {
            "src/retryguard/policy.py": '''"""Retry policy and HTTP error definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


class HTTPError(Exception):
    """Represents an HTTP status failure with optional Retry-After."""

    def __init__(self, status_code: int, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, attempts: int, last_exception: BaseException | None = None) -> None:
        super().__init__(f"Exhausted after {attempts} attempts: {last_exception}")
        self.attempts = attempts
        self.last_exception = last_exception


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_backoff: float = 0.5
    max_backoff: float = 10.0
    multiplier: float = 2.0
    retryable_status_codes: set[int] = field(
        default_factory=lambda: {408, 429, 500, 502, 503, 504}
    )

    def compute_delay(self, retry_index: int, retry_after: float | None = None) -> float:
        """Compute backoff delay for 0-indexed `retry_index`, clamped to `max_backoff`."""
        if retry_after is not None:
            return min(self.max_backoff, max(0.0, retry_after))
        raw = self.base_backoff * (self.multiplier**retry_index)
        return min(self.max_backoff, raw)
''',
            "src/retryguard/limiter.py": '''"""Token bucket rate limiter."""

from __future__ import annotations

import time
from collections.abc import Callable


class TokenBucketLimiter:
    """Token bucket rate limiter with injectable monotonic clock."""

    def __init__(
        self,
        rate_per_sec: float,
        capacity: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_sec <= 0 or capacity <= 0:
            raise ValueError("rate_per_sec and capacity must be > 0")
        self.rate_per_sec = rate_per_sec
        self.capacity = capacity
        self._clock = clock
        self._tokens = float(capacity)
        self._last_ts = self._clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_ts)
        self._last_ts = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_sec)

    def try_acquire(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens
''',
            "src/retryguard/executor.py": '''"""Retry executor implementation."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from retryguard.policy import HTTPError, RetryExhaustedError, RetryPolicy

T = TypeVar("T")


class RetryExecutor:
    """Executes callables with configurable retry and backoff policy."""

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self._sleep = sleep_fn
        self.sleep_history: list[float] = []

    def execute(self, func: Callable[[], T]) -> T:
        if self.policy.max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        last_exc: BaseException | None = None
        total_allowed = self.policy.max_retries + 1

        for attempt in range(total_allowed):
            try:
                return func()
            except HTTPError as exc:
                if exc.status_code not in self.policy.retryable_status_codes:
                    raise
                last_exc = exc
                if attempt < self.policy.max_retries:
                    delay = self.policy.compute_delay(attempt, retry_after=exc.retry_after)
                    self.sleep_history.append(delay)
                    self._sleep(delay)
            except Exception as exc:
                last_exc = exc
                if attempt < self.policy.max_retries:
                    delay = self.policy.compute_delay(attempt)
                    self.sleep_history.append(delay)
                    self._sleep(delay)

        raise RetryExhaustedError(attempts=total_allowed, last_exception=last_exc)
''',
        },
        "incomplete_files": {
            "src/retryguard/executor.py": '''"""Retry executor implementation."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from retryguard.policy import HTTPError, RetryExhaustedError, RetryPolicy

T = TypeVar("T")


class RetryExecutor:
    def __init__(
        self,
        policy: RetryPolicy | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self._sleep = sleep_fn
        self.sleep_history: list[float] = []

    def execute(self, func: Callable[[], T]) -> T:
        last_exc: BaseException | None = None
        total_allowed = self.policy.max_retries + 1
        for attempt in range(total_allowed):
            try:
                return func()
            except HTTPError as exc:
                if exc.status_code not in self.policy.retryable_status_codes:
                    raise
                last_exc = exc
                if attempt < self.policy.max_retries:
                    delay = self.policy.compute_delay(attempt, retry_after=exc.retry_after)
                    self.sleep_history.append(delay)
                    self._sleep(delay)
            except Exception as exc:
                last_exc = exc
                if attempt < self.policy.max_retries:
                    delay = self.policy.compute_delay(attempt)
                    self.sleep_history.append(delay)
                    self._sleep(delay)
        raise RetryExhaustedError(attempts=total_allowed, last_exception=last_exc)
''',
        },
        "regression_files": {
            "src/retryguard/policy.py": '''"""Retry policy and HTTP error definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


class HTTPError(Exception):
    def __init__(self, status_code: int, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


class RetryExhaustedError(Exception):
    def __init__(self, attempts: int, last_exception: BaseException | None = None) -> None:
        super().__init__(f"Exhausted after {attempts} attempts")
        self.attempts = attempts
        self.last_exception = last_exception


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_backoff: float = 0.5
    max_backoff: float = 10.0
    multiplier: float = 2.0
    retryable_status_codes: set[int] = field(
        default_factory=lambda: {408, 429, 500, 502, 503, 504}
    )

    def compute_delay(self, retry_index: int, retry_after: float | None = None) -> float:
        # REGRESSION: Always returns 0.0 instead of exponential backoff!
        return 0.0
''',
        },
        "existing_tests": '''"""Pre-existing preservation tests for retryguard."""

import pytest
from retryguard import RetryExecutor, RetryPolicy, TokenBucketLimiter


def test_immediate_success_on_first_try():
    exec_ = RetryExecutor(RetryPolicy(max_retries=2), sleep_fn=lambda _: None)
    assert exec_.execute(lambda: "ok") == "ok"
    assert exec_.sleep_history == []


def test_exponential_backoff_calculation():
    policy = RetryPolicy(base_backoff=1.0, multiplier=2.0, max_backoff=5.0)
    assert policy.compute_delay(0) == 1.0
    assert policy.compute_delay(1) == 2.0
    assert policy.compute_delay(2) == 4.0
    assert policy.compute_delay(3) == 5.0


def test_invalid_limiter_params():
    with pytest.raises(ValueError):
        TokenBucketLimiter(rate_per_sec=0, capacity=5)
''',
        "issue_tests": '''"""Issue-specific FAIL_TO_PASS tests for retryguard-008."""

import pytest
from retryguard import (
    HTTPError,
    RetryExecutor,
    RetryExhaustedError,
    RetryPolicy,
    TokenBucketLimiter,
)


def test_max_retries_zero_executes_once_and_max_retries_three_executes_four_times():
    calls = 0

    def fail_always():
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    exec0 = RetryExecutor(RetryPolicy(max_retries=0), sleep_fn=lambda _: None)
    with pytest.raises(RetryExhaustedError) as exc_info:
        exec0.execute(fail_always)
    assert calls == 1
    assert exc_info.value.attempts == 1
    assert exec0.sleep_history == []

    calls = 0
    exec3 = RetryExecutor(RetryPolicy(max_retries=3, base_backoff=0.5), sleep_fn=lambda _: None)
    with pytest.raises(RetryExhaustedError) as exc_info3:
        exec3.execute(fail_always)
    assert calls == 4
    assert exc_info3.value.attempts == 4
    # Must sleep only 3 times (between the 4 attempts), NOT after the 4th attempt!
    assert len(exec3.sleep_history) == 3


def test_non_retryable_4xx_aborts_immediately_and_retry_after_is_capped():
    calls = 0

    def bad_request():
        nonlocal calls
        calls += 1
        raise HTTPError(400, "Bad Request")

    exec_ = RetryExecutor(RetryPolicy(max_retries=3), sleep_fn=lambda _: None)
    with pytest.raises(HTTPError) as err:
        exec_.execute(bad_request)
    assert err.value.status_code == 400
    assert calls == 1

    # Retry-After=120s must be capped to max_backoff=5.0s
    policy = RetryPolicy(max_retries=2, max_backoff=5.0)
    assert policy.compute_delay(0, retry_after=120.0) == 5.0


def test_token_bucket_uses_injected_clock_and_caps_at_capacity():
    now = 100.0
    limiter = TokenBucketLimiter(rate_per_sec=2.0, capacity=4.0, clock=lambda: now)
    assert limiter.try_acquire(3.0) is True
    assert limiter.available_tokens == 1.0

    # Advance 100 seconds: tokens must cap at capacity=4.0, not 201.0!
    now = 200.0
    assert limiter.available_tokens == 4.0
''',
        "private_tests": '''"""Private evaluation tests for retryguard-008."""

from retryguard import HTTPError, RetryExecutor, RetryPolicy


def test_429_with_retry_after_succeeds_on_final_retry():
    attempts = 0

    def flaky_endpoint():
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise HTTPError(429, "Rate limited", retry_after=50.0)
        return {"status": 200}

    exec_ = RetryExecutor(RetryPolicy(max_retries=2, max_backoff=3.0), sleep_fn=lambda _: None)
    res = exec_.execute(flaky_endpoint)
    assert res == {"status": 200}
    assert attempts == 3
    assert exec_.sleep_history == [3.0, 3.0]
''',
    },
]
