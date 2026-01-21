# `concurqueue` — Fix check-then-act race condition and lost wakeups in KeyedResourcePool

KeyedResourcePool checks and mutates active lease counters outside a synchronized while-loop and uses single notify(), causing quota overruns and deadlocks under concurrent contention.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
