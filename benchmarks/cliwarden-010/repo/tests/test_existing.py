"""Pre-existing preservation tests for cliwarden."""

from cliwarden import EXIT_CONFIG_ERROR, EXIT_OK, CLIRunner, ConfigError


def test_valid_command_execution():
    runner = CLIRunner()
    res = runner.run(["--target", "service-a", "--workers", "8", "--fast"])
    assert res.exit_code == EXIT_OK
    assert "service-a" in res.stdout
    assert res.stderr == ""


def test_config_error_exit_code():
    def bad_cfg(_opts):
        raise ConfigError("missing credentials.yaml")

    runner = CLIRunner(handler=bad_cfg)
    res = runner.run(["--target", "prod"])
    assert res.exit_code == EXIT_CONFIG_ERROR
    assert "credentials.yaml" in res.stderr
