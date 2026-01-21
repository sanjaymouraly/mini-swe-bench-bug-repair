"""Issue-specific FAIL_TO_PASS tests for idempobox-011."""

import pytest
from idempobox import (
    IdempotencyPayloadMismatchError,
    IdempotentProcessor,
)


def test_key_reuse_with_different_payload_raises_mismatch_error():
    proc = IdempotentProcessor()
    proc.process("pay_1", {"amount": 50, "to": "alice"}, lambda p: {"status": "ok", "amt": p["amount"]})

    with pytest.raises(IdempotencyPayloadMismatchError):
        proc.process("pay_1", {"amount": 500, "to": "alice"}, lambda p: {"status": "ok", "amt": p["amount"]})
    assert proc.execution_count == 1


def test_volatile_headers_and_nested_key_order_ignored_in_fingerprint():
    proc = IdempotentProcessor()
    p1 = {"meta": {"_trace_id": "t1", "channel": "web"}, "amount": 250, "_timestamp": 1000}
    p2 = {"_timestamp": 2000, "amount": 250, "meta": {"channel": "web", "_trace_id": "t2"}}

    res1 = proc.process("pay_2", p1, lambda _: {"tx": "abc"})
    res2 = proc.process("pay_2", p2, lambda _: {"tx": "xyz"})
    assert res1 == {"tx": "abc"}
    assert res2 == {"tx": "abc"}
    assert proc.execution_count == 1


def test_transient_handler_failure_releases_key_for_subsequent_retry():
    proc = IdempotentProcessor()
    should_fail = True

    def flaky_handler(p):
        if should_fail:
            raise RuntimeError("database timeout")
        return {"ok": p["amount"]}

    with pytest.raises(RuntimeError, match="database timeout"):
        proc.process("pay_retry", {"amount": 75}, flaky_handler)

    should_fail = False
    res = proc.process("pay_retry", {"amount": 75}, flaky_handler)
    assert res == {"ok": 75}
    assert proc.execution_count == 2
