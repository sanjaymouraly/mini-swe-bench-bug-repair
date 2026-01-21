"""Pre-existing preservation tests for streamparse."""

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
