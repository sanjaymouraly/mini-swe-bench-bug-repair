"""Chunked NDJSON stream reader."""

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
