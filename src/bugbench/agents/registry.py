"""Registry and factory for coding agent and offline adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bugbench.agents.base import AgentAdapter
from bugbench.agents.cli_agents import ClaudeCodeCLIAdapter, CodexCLIAdapter
from bugbench.agents.llm_providers import (
    AnthropicAdapter,
    CustomOpenAICompatibleAdapter,
    OllamaLocalAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
)
from bugbench.agents.offline import (
    IncompleteBaselineAdapter,
    NoOpBaselineAdapter,
    OfflinePatchAdapter,
    ReferenceOracleAdapter,
    RegressionBaselineAdapter,
)
from bugbench.agents.pricing import get_preset, list_presets
from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.logging_utils import sanitize_dict
from bugbench.models import ConnectionTestResult, ProviderConfigModel

SUPPORTED_PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "offline",
        "name": "Offline Manual Patch",
        "requires_api_key": False,
        "description": "Evaluate local unified Git patches (.patch/.diff) without any AI service or network calls.",
    },
    {
        "id": "reference",
        "name": "Reference Oracle Baseline",
        "requires_api_key": False,
        "description": "Evaluates the verified reference solution for each benchmark task (100% expected resolution).",
    },
    {
        "id": "noop",
        "name": "No-Op Baseline",
        "requires_api_key": False,
        "description": "Evaluates the unmodified repository state (0% expected resolution) to verify issue reproduction.",
    },
    {
        "id": "incomplete",
        "name": "Incomplete Patch Baseline",
        "requires_api_key": False,
        "description": "Evaluates partial fixes that miss edge cases or private tests.",
    },
    {
        "id": "regression",
        "name": "Regression-Inducing Baseline",
        "requires_api_key": False,
        "description": "Evaluates careless fixes that break existing preservation tests (PASS_TO_PASS).",
    },
    {
        "id": "openai",
        "name": "OpenAI API",
        "requires_api_key": True,
        "description": "Direct OpenAI API (platform.openai.com). Note: A consumer ChatGPT Plus/Pro subscription does NOT include API credits.",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude API",
        "requires_api_key": True,
        "description": "Direct Anthropic Messages API (console.anthropic.com).",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter API",
        "requires_api_key": True,
        "description": "OpenRouter unified gateway supporting commercial and free/open-weight coding models.",
    },
    {
        "id": "custom_openai",
        "name": "Custom OpenAI-Compatible API",
        "requires_api_key": False,
        "description": "Any OpenAI-compatible endpoint (Together, Groq, Fireworks, DeepSeek, vLLM) with auto model discovery.",
    },
    {
        "id": "ollama",
        "name": "Local Ollama / Open-Weights Server",
        "requires_api_key": False,
        "description": "Local model server (e.g. http://localhost:11434/v1) for free, private local inference.",
    },
    {
        "id": "codex_cli",
        "name": "Codex CLI Agent",
        "requires_api_key": False,
        "description": "Invokes an installed `codex` CLI agent directly inside the isolated repository workspace.",
    },
    {
        "id": "claude_code_cli",
        "name": "Claude Code CLI Agent",
        "requires_api_key": False,
        "description": "Invokes an installed `claude` CLI agent directly inside the isolated repository workspace.",
    },
]


class AgentRegistry:
    """Factory and configuration manager for all supported adapters."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig.from_env()
        self.loader = DatasetLoader(self.config)

    def list_providers(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in SUPPORTED_PROVIDERS:
            pid = item["id"]
            cfg = self.config.get_provider_config(pid)
            entry = dict(item)
            entry["configured_base_url"] = cfg.base_url
            entry["configured_model"] = cfg.model
            entry["has_api_key"] = bool(cfg.api_key)
            entry["max_cost_usd"] = cfg.max_cost_usd
            entry["input_cost_per_1k_tokens"] = cfg.input_cost_per_1k_tokens
            entry["output_cost_per_1k_tokens"] = cfg.output_cost_per_1k_tokens
            entry["pricing_source"] = cfg.pricing_source
            preset = get_preset(pid)
            if preset:
                entry["preset"] = preset
            results.append(sanitize_dict(entry))
        return results

    def create_adapter(
        self,
        provider: str,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        patch_path: Path | None = None,
        patch_text: str | None = None,
    ) -> AgentAdapter:
        p = provider.lower().strip()
        if p in ("noop", "noop-baseline"):
            return NoOpBaselineAdapter()
        if p in ("reference", "oracle", "reference-oracle"):
            return ReferenceOracleAdapter(self.loader)
        if p in ("incomplete", "incomplete-baseline"):
            return IncompleteBaselineAdapter(self.loader)
        if p in ("regression", "regression-baseline"):
            return RegressionBaselineAdapter(self.loader)
        if p in ("offline", "patch", "manual"):
            return OfflinePatchAdapter(patch_path=patch_path, patch_text=patch_text)
        if p == "codex_cli":
            return CodexCLIAdapter(timeout_seconds=self.config.default_timeout_seconds)
        if p == "claude_code_cli":
            return ClaudeCodeCLIAdapter(timeout_seconds=self.config.default_timeout_seconds)

        cfg: ProviderConfigModel = self.config.get_provider_config(p)
        if base_url is not None and base_url.strip():
            cfg.base_url = base_url.strip()
        if api_key is not None and api_key.strip():
            cfg.api_key = api_key.strip()
        if model is not None and model.strip():
            cfg.model = model.strip()

        if p == "openai":
            return OpenAIAdapter(cfg)
        if p == "anthropic":
            return AnthropicAdapter(cfg)
        if p == "openrouter":
            return OpenRouterAdapter(cfg)
        if p == "custom_openai":
            return CustomOpenAICompatibleAdapter(cfg)
        if p in ("ollama", "local"):
            return OllamaLocalAdapter(cfg)

        raise ValueError(f"Unsupported provider '{provider}'.")

    def list_connection_presets(self) -> list[dict[str, Any]]:
        """Return the 'easy connect' presets for every supported provider."""
        return list_presets()

    def test_provider_connection(
        self,
        provider: str,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> ConnectionTestResult:
        adapter = self.create_adapter(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        return adapter.test_connection()
