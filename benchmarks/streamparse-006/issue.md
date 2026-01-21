# Issue: `ChunkedNDJSONReader` corrupts multi-byte UTF-8 across chunk boundaries and miscalculates `byte_offset` after malformed lines

## Description
`ChunkedNDJSONReader` streams arbitrary-sized `bytes` chunks of NDJSON records with configurable `ErrorPolicy` (`RAISE`, `SKIP`, `QUARANTINE`) and required field validation. Two bugs occur:

1. **Multi-byte UTF-8 characters split across `bytes` chunks**:
   `parse_chunks()` calls `chunk.decode("utf-8")` on each incoming `bytes` chunk individually before buffering. When a multi-byte UTF-8 sequence (e.g., `€`, `é`, `🚀`) straddles the boundary between two chunks, `chunk.decode("utf-8")` raises `UnicodeDecodeError`! The reader must buffer raw `bytes` (splitting on `b"\n"`) and decode complete lines, or use an incremental decoder while tracking exact raw byte lengths.
2. **Incorrect `byte_offset` after malformed records in `QUARANTINE` / `SKIP` mode**:
   Each `ParsedRecord` and `QuarantinedRecord` records the starting `byte_offset` (0-indexed byte position in the stream where that line began, including `\r\n` or `\n` lengths of prior lines) and 1-indexed `line_number`. Currently, when a line fails JSON parsing or required-field validation, the error branch `continue`s before advancing `current_byte_offset += len(raw_line_with_newline)`, causing all subsequent records to have shifted byte offsets!

## Expected Behavior
- Arbitrary chunk boundaries (even 1-byte or 3-byte chunks splitting multi-byte UTF-8 characters or `\r\n` delimiters) must produce identical parsed records to single-chunk parsing.
- Empty/whitespace-only lines must still advance `current_byte_offset` by their exact byte length and increment `line_number`.
- Malformed JSON lines or records missing `required_fields` must be handled according to `error_policy` (`RAISE`, `SKIP`, `QUARANTINE`), and `current_byte_offset` must always advance by the exact raw byte length of every line (including its trailing `\r\n` or `\n`).
