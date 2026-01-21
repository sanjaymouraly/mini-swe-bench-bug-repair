"""Issue-specific FAIL_TO_PASS concurrency tests for concurqueue-003."""

import threading
import time
import pytest
from concurqueue import KeyedResourcePool, PoolTimeoutError


def test_concurrent_contention_never_exceeds_per_key_or_total_limits():
    pool = KeyedResourcePool(max_total=4, max_per_key=2)
    barrier = threading.Barrier(16)
    errors: list[Exception] = []

    def worker(idx: int) -> None:
        key = f"k_{idx % 3}"
        try:
            barrier.wait(timeout=1.0)
            for _ in range(3):
                with pool.lease(key, timeout=0.35):
                    if pool.active_for_key(key) > 2 or pool.total_active > 4:
                        raise AssertionError(
                            f"Quota violated: key={pool.active_for_key(key)}, total={pool.total_active}"
                        )
                    time.sleep(0.002)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)

    assert not errors, f"Worker errors: {errors}"
    assert pool.peak_total <= 4
    assert all(v <= 2 for v in pool.peak_per_key.values())
    assert pool.total_active == 0


def test_timeout_under_contention_with_multiple_waiters():
    pool = KeyedResourcePool(max_total=2, max_per_key=1)
    pool.acquire("k1")
    start = time.monotonic()
    with pytest.raises(PoolTimeoutError):
        pool.acquire("k1", timeout=0.06)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.04
    pool.release("k1")
    assert pool.total_active == 0
