"""Issue-specific FAIL_TO_PASS tests for schemaver-009."""

from schemaver import EventCodec


def test_v1_to_v3_multihop_migration_without_mutating_caller_dict():
    codec = EventCodec()
    v1_payload = {
        "event_id": "evt_v1",
        "schema_version": 1,
        "full_name": "Grace Hopper",
        "amount_dollars": 19.95,
    }
    original_copy = dict(v1_payload)
    env = codec.deserialize(v1_payload)

    assert v1_payload == original_copy, "Input dictionary was mutated in place!"
    assert env.schema_version == 3
    assert env.first_name == "Grace"
    assert env.last_name == "Hopper"
    assert env.amount_cents == 1995


def test_default_tags_are_isolated_across_instances():
    codec = EventCodec()
    e1 = codec.deserialize({"event_id": "1", "schema_version": 3, "first_name": "A", "last_name": "B", "amount_cents": 10})
    e2 = codec.deserialize({"event_id": "2", "schema_version": 3, "first_name": "C", "last_name": "D", "amount_cents": 20})
    e1.tags.append("mutated")
    assert e2.tags == []


def test_unknown_forward_compatible_fields_preserved_on_roundtrip():
    codec = EventCodec()
    raw = {
        "event_id": "evt_fwd",
        "schema_version": 2,
        "first_name": "Alan",
        "last_name": "Turing",
        "amount_dollars": 50.0,
        "trace_region": "eu-central-1",
        "feature_flags": {"beta": True},
    }
    env = codec.deserialize(raw)
    serialized = codec.serialize(env)
    assert serialized["schema_version"] == 3
    assert serialized["amount_cents"] == 5000
    assert serialized["trace_region"] == "eu-central-1"
    assert serialized["feature_flags"] == {"beta": True}
