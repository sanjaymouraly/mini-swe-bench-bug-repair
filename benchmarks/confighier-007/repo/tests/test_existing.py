"""Pre-existing preservation tests for confighier."""

from confighier import ConfigLoader, coerce_env_value


def test_coerce_env_value_types():
    assert coerce_env_value("true") is True
    assert coerce_env_value("false") is False
    assert coerce_env_value("8080") == 8080
    assert coerce_env_value("1.5") == 1.5
    assert coerce_env_value("a,b,c") == ["a", "b", "c"]


def test_basic_top_level_override():
    loader = ConfigLoader(env_prefix="APP")
    defaults = {"host": "127.0.0.1", "port": 8000}
    res = loader.resolve(defaults, profile={"port": 9000})
    assert res == {"host": "127.0.0.1", "port": 9000}
