# `atomicvault` — Fix mid-write target loss, orphan temp cleanup, crash recovery, and path traversal in AtomicVault

AtomicVault moves live files to .bak before completing temp writes (destroying live files when a writer fails mid-stream), fails to clean up .tmp files or restore .bak files on recover(), and allows nested '..' path traversal.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
