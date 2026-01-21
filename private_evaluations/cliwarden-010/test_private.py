"""Private boundary tests for cliwarden-010."""

from cliwarden import EXIT_USAGE_ERROR, CLIRunner


def test_unknown_flag_and_missing_target_value_return_exit_2_on_stderr():
    runner = CLIRunner()
    r1 = runner.run(["--target", "--fast"])
    assert r1.exit_code == EXIT_USAGE_ERROR
    assert r1.stdout == ""
    assert r1.stderr != ""

    r2 = runner.run(["--target", "svc", "--unknown-flag"])
    assert r2.exit_code == EXIT_USAGE_ERROR
    assert r2.stdout == ""
