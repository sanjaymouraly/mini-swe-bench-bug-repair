# Issue: Race conditions and lost wakeups in `KeyedResourcePool.acquire` / `release`

## Description
`KeyedResourcePool` coordinates concurrent worker leases with both a global concurrency limit (`max_total`) and a per-tenant key limit (`max_per_key`). Under multi-threaded load, three concurrency bugs occur:

1. **Unsynchronized check-then-act & `if` instead of `while` wait loop**:
   `acquire()` checks capacity outside a `while` loop on `self._cond`, and sleeps briefly before incrementing `_total_active` and `_key_counts[key]`. When multiple threads contend on the same key or wake up simultaneously, both `max_per_key` and `max_total` are exceeded.
2. **Deadline drift & timeout failure**:
   When waiting with a `timeout`, `acquire()` must recompute remaining time (`deadline - time.monotonic()`) inside the `while` loop and raise `PoolTimeoutError` immediately if `remaining <= 0` when capacity is still unavailable.
3. **Lost wakeups on `release()` (`notify()` instead of `notify_all()`) and unvalidated release**:
   When a thread waiting on key `"A"` is at the head of the condition queue (blocked by `max_per_key` for `"A"`) and a slot for key `"B"` is released (freeing global capacity for a thread waiting on `"B"`), calling `self._cond.notify()` only wakes the blocked `"A"` thread, leaving the `"B"` thread stuck until timeout! `release()` must hold `self._cond`, validate that the key actually has an active lease (raising `ReleaseError` if not), decrement counts safely, and call `self._cond.notify_all()`.

## Expected Behavior
- At no point may `active_for_key(key) > max_per_key` or `total_active > max_total`, even under high multi-threaded contention.
- Peak concurrency trackers (`peak_total`, `peak_per_key[key]`) must accurately reflect synchronized state.
- Releasing an unacquired or already-released key must raise `ReleaseError`.
