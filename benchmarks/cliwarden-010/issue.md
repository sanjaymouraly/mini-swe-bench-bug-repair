# Issue: `CLIRunner` bypasses validation on `--dry-run`, uses wrong exit codes, and pollutes `stdout` on errors

## Description
`cliwarden` is a command-line runner enforcing structured exit codes:
- `EXIT_OK = 0`
- `EXIT_USAGE_ERROR = 2` (unknown flags, missing required `--target`, mutually exclusive `--fast` and `--thorough`, or invalid `--workers` count `<= 0` or `> 64`)
- `EXIT_CONFIG_ERROR = 3` (`ConfigError` raised by handler)
- `EXIT_RUNTIME_ERROR = 4` (unhandled `RuntimeError` raised by handler)
- `EXIT_INTERRUPTED = 130` (`KeyboardInterrupt` raised by handler)

Three bugs exist in `src/cliwarden/runner.py`:

1. **`--dry-run` short-circuits BEFORE argument validation**:
   When `--dry-run` is passed alongside invalid flags (e.g. `["--dry-run", "--workers", "0"]` or `["--dry-run", "--fast", "--thorough"]` or missing `--target`), `CLIRunner.run()` immediately returns `exit_code=0` without validating the arguments! `--dry-run` must validate all arguments first, and only skip invoking the handler after validation succeeds.
2. **Validation errors return exit code `1` and print to `stdout` instead of `stderr`**:
   Usage/validation errors must return `EXIT_USAGE_ERROR` (`2`) and write the error message to `stderr` (leaving `stdout` empty `""`).
3. **`KeyboardInterrupt` returns `1` instead of `EXIT_INTERRUPTED` (`130`)**:
   When the command handler raises `KeyboardInterrupt`, `run()` catches `Exception` or returns `1` instead of returning `EXIT_INTERRUPTED` (`130`) with `"Interrupted
"` on `stderr`.

## Expected Behavior
- Full argument validation always runs before `--dry-run` short-circuiting.
- Usage/validation errors return `exit_code=2`, `stdout=""`, and non-empty `stderr`.
- `ConfigError` returns `exit_code=3`, `RuntimeError` returns `exit_code=4`, and `KeyboardInterrupt` returns `exit_code=130` (all writing error details to `stderr`).
