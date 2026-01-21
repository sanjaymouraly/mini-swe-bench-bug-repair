"""Unit tests for LLM provider adapters, model discovery, and error handling using httpx.MockTransport."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from bugbench.agents.cli_agents import ClaudeCodeCLIAdapter, CodexCLIAdapter
from bugbench.agents.llm_providers import (
    AnthropicAdapter,
    CustomOpenAICompatibleAdapter,
    OpenAIAdapter,
    calculate_cost_usd,
    select_best_discovered_model,
)
from bugbench.dataset.loader import DatasetLoader
from bugbench.models import ProviderConfigModel
from bugbench.sandbox.workspace import EphemeralWorkspace


def test_select_best_discovered_model_filters_embeddings_and_picks_coding_model() -> None:
    models = [
        "text-embedding-3-small",
        "whisper-1",
        "llama-3.1-8b",
        "qwen2.5-coder:32b",
    ]
    selected = select_best_discovered_model(models)
    assert selected == "qwen2.5-coder:32b"


def test_calculate_cost_usd_only_when_pricing_configured() -> None:
    cfg_no_price = ProviderConfigModel(provider="openai", model="gpt-4o")
    assert calculate_cost_usd(1000, 500, cfg_no_price) is None

    cfg_priced = ProviderConfigModel(
        provider="openai",
        model="gpt-4o",
        input_cost_per_1k_tokens=0.0025,
        output_cost_per_1k_tokens=0.01,
    )
    assert calculate_cost_usd(1000, 500, cfg_priced) == pytest.approx(0.0075)


def test_custom_openai_auto_model_discovery_and_patch_generation(
    dataset_loader: DatasetLoader, tmp_path: Path
) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    ref_patch = dataset_loader.get_reference_patch("pagiflow-001")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "text-embedding-ada-002"},
                        {"id": "deepseek-coder-v2"},
                    ]
                },
            )
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content.decode("utf-8"))
            assert body["model"] == "deepseek-coder-v2"
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": f"Here is the patch:\n```diff\n{ref_patch}```"}}
                    ],
                    "usage": {
                        "prompt_tokens": 500,
                        "completion_tokens": 120,
                        "total_tokens": 620,
                    },
                },
            )
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    cfg = ProviderConfigModel(
        provider="custom_openai",
        base_url="https://mock.local/v1",
        api_key="sk-mock-secret-key-1234567890",
        model="",  # Intentionally empty to trigger auto-discovery!
        input_cost_per_1k_tokens=0.001,
        output_cost_per_1k_tokens=0.002,
    )
    adapter = CustomOpenAICompatibleAdapter(cfg, http_client=mock_client)

    conn = adapter.test_connection()
    assert conn.reachable is True
    assert conn.authenticated is True
    assert conn.selected_model == "deepseek-coder-v2"

    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        out = adapter.generate_patch(task, ws.repo_dir)
        assert "diff --git" in out.patch_diff
        assert out.model_used == "deepseek-coder-v2"
        assert out.total_tokens == 620
        assert out.estimated_cost_usd == pytest.approx(0.00074)


def test_openai_invalid_credentials_and_rate_limit_errors_redact_api_key() -> None:
    secret_key = "sk-live-secret-9876543210abcdefghij"  # noqa: S105

    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": f"Invalid API key provided: {secret_key}"}},
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(handler_401))
    cfg = ProviderConfigModel(
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_key=secret_key,
        model="gpt-4o",
    )
    adapter = OpenAIAdapter(cfg, http_client=mock_client)
    conn = adapter.test_connection()
    assert conn.authenticated is False
    assert secret_key not in conn.message
    assert "REDACTED" in conn.message


def test_anthropic_missing_api_key_connection_test() -> None:
    cfg = ProviderConfigModel(
        provider="anthropic",
        base_url="https://api.anthropic.com",
        api_key="",
        model="claude-3-5-sonnet-latest",
    )
    adapter = AnthropicAdapter(cfg)
    conn = adapter.test_connection()
    assert conn.authenticated is False
    assert "API key" in conn.message


def test_cli_agents_report_status_cleanly() -> None:
    codex = CodexCLIAdapter(binary_name="nonexistent-codex-binary-xyz")
    res_codex = codex.test_connection()
    assert res_codex.reachable is False
    assert "not found" in res_codex.message

    claude = ClaudeCodeCLIAdapter(binary_name="nonexistent-claude-binary-xyz")
    res_claude = claude.test_connection()
    assert res_claude.reachable is False
