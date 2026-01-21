"""Unit tests for provider pricing resolution, presets, and cost reporting."""

from __future__ import annotations

import pytest

from bugbench.agents.pricing import (
    builtin_estimate,
    extract_discovered_pricing,
    format_usd,
    get_preset,
    list_presets,
    resolve_pricing,
)
from bugbench.agents.registry import AgentRegistry
from bugbench.config import AppConfig


def test_every_ai_provider_has_a_connection_preset() -> None:
    presets = {p["id"] for p in list_presets()}
    for expected in (
        "openai",
        "anthropic",
        "openrouter",
        "custom_openai",
        "ollama",
        "codex_cli",
        "claude_code_cli",
    ):
        assert expected in presets


def test_preset_exposes_base_url_key_env_and_cost_tier() -> None:
    openai = get_preset("openai")
    assert openai is not None
    assert openai["default_base_url"] == "https://api.openai.com/v1"
    assert openai["api_key_env"] == "OPENAI_API_KEY"
    assert openai["cost_tier"] == "paid"
    # The ChatGPT-subscription caveat must be present for OpenAI.
    assert "does NOT include API credits" in openai["notes"]


def test_ollama_preset_is_free_and_needs_no_key() -> None:
    ollama = get_preset("ollama")
    assert ollama is not None
    assert ollama["cost_tier"] == "free"
    assert ollama["api_key_env"] == ""


def test_extract_discovered_pricing_per_1k_fields() -> None:
    entry = {"id": "some-model", "input_idr_per_1k": 0.81, "output_idr_per_1k": 3.241}
    assert extract_discovered_pricing(entry) == (0.81, 3.241)


def test_extract_discovered_pricing_per_million_fields() -> None:
    entry = {"id": "m", "input_idr_per_1m": 810, "output_idr_per_1m": 3240}
    assert extract_discovered_pricing(entry) == (0.81, 3.24)


def test_extract_discovered_pricing_per_token_fields() -> None:
    entry = {"id": "m", "input_cost_per_token": 0.0000005, "output_cost_per_token": 0.000002}
    assert extract_discovered_pricing(entry) == (0.0005, 0.002)


def test_extract_discovered_pricing_returns_none_without_rates() -> None:
    assert extract_discovered_pricing({"id": "m", "context_window": 128000}) is None
    assert extract_discovered_pricing({}) is None
    assert extract_discovered_pricing("not-a-dict") is None  # type: ignore[arg-type]


def test_zero_priced_model_is_reported_as_free_not_unknown() -> None:
    assert extract_discovered_pricing({"input_idr_per_1k": 0, "output_idr_per_1k": 0}) == (0.0, 0.0)


def test_resolve_pricing_prefers_manual_over_discovery() -> None:
    in_rate, out_rate, source = resolve_pricing(
        "openai",
        "gpt-4o",
        manual_input=1.0,
        manual_output=2.0,
        discovered=(0.5, 1.0),
    )
    assert (in_rate, out_rate, source) == (1.0, 2.0, "manual")


def test_resolve_pricing_prefers_discovery_over_builtin_estimate() -> None:
    in_rate, out_rate, source = resolve_pricing(
        "openai",
        "gpt-4o",
        discovered=(0.5, 1.0),
        allow_builtin_estimate=True,
    )
    assert (in_rate, out_rate, source) == (0.5, 1.0, "provider_discovery")


def test_resolve_pricing_unknown_when_no_source_available() -> None:
    in_rate, out_rate, source = resolve_pricing("openai", "some-new-model")
    assert in_rate is None
    assert out_rate is None
    assert source == ""


def test_builtin_estimate_is_opt_in_and_prefix_matched() -> None:
    assert resolve_pricing("openai", "gpt-4o")[2] == ""
    in_rate, out_rate, source = resolve_pricing(
        "openai", "gpt-4o-2024-08-06", allow_builtin_estimate=True
    )
    assert source == "builtin_estimate"
    assert in_rate is not None and out_rate is not None


def test_builtin_estimate_unknown_model_returns_none() -> None:
    assert builtin_estimate("openai", "totally-unknown-model") is None


def test_format_usd_distinguishes_unknown_from_zero() -> None:
    assert format_usd(None) == "n/a"
    assert format_usd(0.0) == "$0.00"
    assert format_usd(0.000004) == "$0.000004"
    assert format_usd(1.5) == "$1.5000"


def test_provider_config_reads_env_over_defaults(
    test_config: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUSTOM_OPENAI_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("CUSTOM_OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("CUSTOM_OPENAI_MODEL", "my-model")
    cfg = test_config.get_provider_config("custom_openai")
    assert cfg.base_url == "https://gateway.example/v1"
    assert cfg.api_key == "secret-key"
    assert cfg.model == "my-model"


def test_provider_config_prefers_saved_settings_over_env(
    test_config: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://from-env/v1")
    saved = test_config.get_provider_config("openai")
    saved.base_url = "https://from-settings/v1"
    saved.model = "saved-model"
    test_config.save_provider_setting(saved)

    reloaded = test_config.get_provider_config("openai")
    assert reloaded.base_url == "https://from-settings/v1"
    assert reloaded.model == "saved-model"


def test_registry_exposes_pricing_and_presets(test_config: AppConfig) -> None:
    registry = AgentRegistry(test_config)
    providers = {p["id"]: p for p in registry.list_providers()}
    assert "openai" in providers
    assert providers["openai"]["preset"]["api_key_env"] == "OPENAI_API_KEY"
    assert "max_cost_usd" in providers["openai"]
    assert "pricing_source" in providers["openai"]
    assert len(registry.list_connection_presets()) >= 7


def test_saved_provider_settings_are_not_world_readable(test_config: AppConfig) -> None:
    import os
    import stat

    saved = test_config.get_provider_config("openai")
    saved.api_key = "super-secret"
    test_config.save_provider_setting(saved)
    mode = stat.S_IMODE(os.stat(test_config.settings_file_path).st_mode)
    assert mode == 0o600
    # The secret must be on disk (it is the operator's own key) but the file
    # must not be readable by other users.
    assert "super-secret" in test_config.settings_file_path.read_text()
