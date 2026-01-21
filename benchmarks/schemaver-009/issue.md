# Issue: `EventCodec` fails multi-hop `v1 -> v3` migration, shares mutable default `tags`, and drops unknown fields

## Description
`schemaver` deserializes versioned event payloads (`schema_version` 1, 2, or 3) into the current `v3` `EventEnvelope` and re-serializes them with forward/backward compatibility. Four bugs occur:

1. **Multi-hop `v1 -> v2 -> v3` migration stops at `v2`**:
   In `EventCodec.deserialize(raw)`, a `v1` payload (which has `"full_name"` and `"amount_dollars"`) is migrated to `v2` (splitting `"full_name"` into `"first_name"` and `"last_name"`), but `elif version == 2:` is used instead of chaining into the `v2 -> v3` migration (which converts `"amount_dollars"` to integer `"amount_cents"` and sets `schema_version = 3`).
2. **In-place mutation of caller's input dictionary**:
   `deserialize(raw)` mutates the caller's `raw` dictionary directly during migration.
3. **Shared mutable default `tags` list**:
   When `"tags"` is omitted in a payload, `EventEnvelope` uses a shared default list reference, so appending to `env1.tags` mutates `env2.tags` across unrelated deserialized events!
4. **Forward-compatible unknown fields are dropped on `serialize()`**:
   When a newer producer includes extra fields not in the known v3 schema (e.g., `"region": "ap-south-1"`, `"experiment_id": 42`), `deserialize()` drops them instead of storing them in `envelope.extra` and re-emitting them in `serialize()`.

## Expected Behavior
- `v1` and `v2` payloads migrate all the way to `v3` (`schema_version=3`, `first_name`, `last_name`, `amount_cents`, `tags`) without mutating the input dict.
- Each `EventEnvelope` gets an independent `tags` list and `extra` dict.
- Unknown fields are preserved in `envelope.extra` and included at the top level when `codec.serialize(envelope)` is called.
