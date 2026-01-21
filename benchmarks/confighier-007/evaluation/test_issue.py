"""Issue-specific FAIL_TO_PASS tests for confighier-007."""

from confighier import ConfigLoader


def test_deep_merge_preserves_sibling_keys_and_handles_single_underscore_env_keys():
    loader = ConfigLoader(env_prefix="APP")
    defaults = {
        "debug": True,
        "retries": 3,
        "db": {
            "host": "localhost",
            "port": 5432,
            "max_connections": 10,
        },
    }
    profile = {"db": {"port": 5433}}
    environ = {
        "APP__DB__MAX_CONNECTIONS": "50",
        "APP__DEBUG": "false",
    }
    cli_overrides = {
        "retries": 0,
        "db": {"host": None},  # None means CLI flag not provided; keep "localhost"
    }

    resolved = loader.resolve(
        defaults=defaults,
        profile=profile,
        environ=environ,
        cli_overrides=cli_overrides,
    )
    assert resolved["debug"] is False
    assert resolved["retries"] == 0
    assert resolved["db"] == {
        "host": "localhost",
        "port": 5433,
        "max_connections": 50,
    }
