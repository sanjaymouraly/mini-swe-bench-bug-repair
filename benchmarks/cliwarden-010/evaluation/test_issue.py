"""Issue-specific FAIL_TO_PASS tests for cliwarden-010."""

from cliwarden import (
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_RUNTIME_ERROR,
    EXIT_USAGE_ERROR,
    CLIRunner,
)


def test_dry_run_still_validates_invalid_arguments():
    runner = CLIRunner()
    # Mutually exclusive flags with --dry-run must fail with exit code 2
    res1 = runner.run(["--target", "app", "--fast", "--thorough", "--dry-run"])
    assert res1.exit_code == EXIT_USAGE_ERROR
    assert res1.stdout == ""
    assert res1.stderr != ""

    # Out-of-range workers with --dry-run must fail with exit code 2
    res2 = runner.run(["--target", "app", "--workers", "0", "--dry-run"])
    assert res2.exit_code == EXIT_USAGE_ERROR
    assert res2.stdout == ""

    # Valid --dry-run succeeds without calling handler
    called = False

    def should_not_run(_opts):
        nonlocal called
        called = True
        return "ran"

    res3 = CLIRunner(handler=should_not_run).run(["--target", "app", "--dry-run"])
    assert res3.exit_code == EXIT_OK
    assert called is False


def test_keyboard_interrupt_and_runtime_error_exit_codes():
    def interrupt_handler(_opts):
        raise KeyboardInterrupt()

    res_int = CLIRunner(handler=interrupt_handler).run(["--target", "svc"])
    assert res_int.exit_code == EXIT_INTERRUPTED
    assert res_int.stdout == ""

    def crash_handler(_opts):
        raise RuntimeError("disk full")

    res_err = CLIRunner(handler=crash_handler).run(["--target", "svc"])
    assert res_err.exit_code == EXIT_RUNTIME_ERROR
    assert "disk full" in res_err.stderr
