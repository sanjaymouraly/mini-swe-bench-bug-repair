"""Private immutability and multi-level falsy override tests for confighier-007."""

from confighier import ConfigLoader


def test_resolve_does_not_mutate_inputs_and_preserves_empty_string_override():
    defaults = {"service": {"name": "api", "prefix": "/v1", "tags": ["a", "b"]}}
    cli = {"service": {"prefix": "", "tags": []}}
    loader = ConfigLoader()
    out = loader.resolve(defaults, cli_overrides=cli)
    assert out["service"]["name"] == "api"
    assert out["service"]["prefix"] == ""
    assert out["service"]["tags"] == []
    # Original defaults must not be mutated
    assert defaults["service"]["prefix"] == "/v1"
    assert defaults["service"]["tags"] == ["a", "b"]
