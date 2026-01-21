# `cliwarden` — Fix --dry-run validation bypass, stderr usage error routing, and POSIX exit codes

CLIRunner short-circuits on --dry-run before validating arguments, writes validation errors to stdout with exit code 1 instead of stderr with exit code 2, and mishandles KeyboardInterrupt.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
