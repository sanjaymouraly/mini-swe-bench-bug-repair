"""Issue-specific FAIL_TO_PASS tests for streamparse-006."""

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
