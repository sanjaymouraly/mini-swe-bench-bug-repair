"""Private boundary tests for schemaver-009."""

from schemaver import EventCodec


def test_single_word_full_name_in_v1_and_deep_copy_of_extra():
    codec = EventCodec()
    raw = {
        "event_id": "e_single",
        "schema_version": 1,
        "full_name": "Plato",
        "amount_dollars": 12.34,
        "metadata": {"source": "mobile"},
    }
    env = codec.deserialize(raw)
    assert env.first_name == "Plato"
    assert env.last_name == ""
    assert env.amount_cents == 1234
    raw["metadata"]["source"] = "mutated_outside"
    assert codec.serialize(env)["metadata"]["source"] == "mobile"
