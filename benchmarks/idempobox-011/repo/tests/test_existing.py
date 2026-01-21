"""Pre-existing preservation tests for idempobox."""

import pytest
from idempobox import IdempotentProcessor


def test_exact_duplicate_replay_executes_handler_once():
    proc = IdempotentProcessor()
    payload = {"amount": 100, "currency": "USD"}
    r1 = proc.process("key_1", payload, lambda p: {"charged": p["amount"]})
    r2 = proc.process("key_1", payload, lambda p: {"charged": p["amount"]})
    assert r1 == {"charged": 100}
    assert r2 == {"charged": 100}
    assert proc.execution_count == 1


def test_empty_key_rejected():
    proc = IdempotentProcessor()
    with pytest.raises(ValueError):
        proc.process("   ", {"a": 1}, lambda p: p)
