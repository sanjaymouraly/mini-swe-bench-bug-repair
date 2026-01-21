"""Private CRLF, trailing line without newline, and SKIP policy offset tests for streamparse-006."""

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
