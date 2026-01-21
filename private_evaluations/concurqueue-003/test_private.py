"""Private stress and broadcast wakeup tests for concurqueue-003."""

import threading
import time
from concurqueue import KeyedResourcePool


def test_cross_key_notify_all_prevents_lost_wakeup():
    # max_total=1, max_per_key=1: releasing k1 must wake waiter on k2 even if another k1 waiter queued first
    pool = KeyedResourcePool(max_total=2, max_per_key=1)
    pool.acquire("k1")
    pool.acquire("k2")

    results: list[str] = []

    def wait_k1():
        # Blocked by max_per_key on k1
        with pool.lease("k1", timeout=2.0):
            results.append("k1_second")

    def wait_k3():
        # Blocked only by max_total=2; releasing k2 should allow k3 to proceed immediately!
        with pool.lease("k3", timeout=2.0):
            results.append("k3")

    t1 = threading.Thread(target=wait_k1)
    t3 = threading.Thread(target=wait_k3)
    t1.start()
    time.sleep(0.02)
    t3.start()
    time.sleep(0.02)

    # Release k2: k1 is still held, so only k3 can run now!
    pool.release("k2")
    t3.join(timeout=1.0)
    assert "k3" in results

    pool.release("k1")
    t1.join(timeout=1.0)
    assert results == ["k3", "k1_second"]
    assert pool. snapshot() == {}
