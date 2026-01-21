"""Pre-existing preservation tests for schemaver."""

import pytest
from schemaver import EventCodec, canonical_hash


def test_v3_native_roundtrip():
    codec = EventCodec()
    raw = {
        "event_id": "evt_100",
        "schema_version": 3,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "amount_cents": 2500,
        "tags": ["vip"],
    }
    env = codec.deserialize(raw)
    assert env.first_name == "Ada"
    assert env.amount_cents == 2500
    assert codec.serialize(env) == raw


def test_canonical_hash_key_order_invariance():
    d1 = {"b": 2, "a": 1, "nested": {"z": 9, "y": 8}}
    d2 = {"a": 1, "nested": {"y": 8, "z": 9}, "b": 2}
    assert canonical_hash(d1) == canonical_hash(d2)


def test_unsupported_schema_version_raises():
    codec = EventCodec()
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        codec.deserialize({"event_id": "e1", "schema_version": 99})
