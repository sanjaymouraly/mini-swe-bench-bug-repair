"""Private concurrency conflict and result immutability tests for idempobox-011."""

import threading
import time
import pytest
from idempobox import IdempotencyConflictError, IdempotentProcessor


def test_concurrent_in_flight_duplicate_raises_conflict_and_cached_result_is_isolated():
    proc = IdempotentProcessor()
    entered = threading.Event()
    release = threading.Event()

    def slow_handler(_p):
        entered.set()
        release.wait(timeout=2.0)
        return {"items": [1, 2]}

    t = threading.Thread(target=lambda: proc.process("k_flight", {"x": 1}, slow_handler))
    t.start()
    entered.wait(timeout=2.0)

    with pytest.raises(IdempotencyConflictError):
        proc.process("k_flight", {"x": 1}, slow_handler)

    release.set()
    t.join(timeout=2.0)

    # Mutating returned dict must not corrupt cached result for future replays
    out1 = proc.process("k_flight", {"x": 1}, slow_handler)
    out1["items"].append(999)
    out2 = proc.process("k_flight", {"x": 1}, slow_handler)
    assert out2 == {"items": [1, 2]}
