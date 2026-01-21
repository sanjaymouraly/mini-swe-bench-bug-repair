"""Multi-provider LLM API adapters (OpenAI, Anthropic, OpenRouter, Custom OpenAI, Ollama)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from bugbench.agents.base import (
    AgentAdapter,
    AgentOutput,
    apply_llm_response_to_workspace,
    build_repair_prompt,
    collect_workspace_diff,
    extract_unified_diff,
)

__all__ = ["extract_unified_diff"]

from bugbench.agents.pricing import extract_discovered_pricing, resolve_pricing
from bugbench.logging_utils import get_logger, redact_secrets
from bugbench.models import BenchmarkTask, ConnectionTestResult, ProviderConfigModel

logger = get_logger("bugbench.agents.llm")

_PREFERRED_MODEL_SUBSTRINGS = [
    "claude-sonnet",
    "claude-3-7",
    "claude-3-5",
    "gpt-4.1",
    "gpt-4o",
    "o3-mini",
    "qwen2.5-coder",
    "deepseek-coder",
    "deepseek-chat",
    "codestral",
    "llama-3.3",
    "llama3",
]


def select_best_discovered_model(models: list[str]) -> str:
    """Select a suitable code-capable model from a provider's discovered model list."""
    if not models:
        return ""
    # Filter out embedding/audio/moderation/tts/whisper models
    non_chat_keywords = (
        "embed",
        "whisper",
        "tts",
        "dall-e",
        "moderation",
        "rerank",
        "babbage",
        "davinci",
    )
    candidates = [m for m in models if not any(kw in m.lower() for kw in non_chat_keywords)]
    if not candidates:
        candidates = models

    for pref in _PREFERRED_MODEL_SUBSTRINGS:
        for m in candidates:
            if pref in m.lower():
                return m
    return candidates[0]


def calculate_cost_usd(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cfg: ProviderConfigModel,
) -> float | None:
    """Compute estimated provider cost ONLY when both token counts and pricing are configured."""
    if (
        prompt_tokens is None
        or completion_tokens is None
        or cfg.input_cost_per_1k_tokens is None
        or cfg.output_cost_per_1k_tokens is None
    ):
        return None
    cost = (prompt_tokens / 1000.0) * cfg.input_cost_per_1k_tokens + (
        completion_tokens / 1000.0
    ) * cfg.output_cost_per_1k_tokens
    return round(cost, 6)


class OpenAICompatibleBaseAdapter(AgentAdapter):
    """Base adapter for OpenAI API, OpenRouter, Ollama, and custom OpenAI-compatible endpoints."""

    requires_api_key: bool = True

    def __init__(
        self,
        config: ProviderConfigModel,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.cfg = config
        self.provider = config.provider
        self.model = config.model
        self.agent_id = f"{config.provider}:{config.model or 'auto'}"
        self._client = http_client
        self._discovered_pricing: dict[str, tuple[float, float]] = {}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/software-bug-repair-benchmark"
            headers["X-Title"] = "Mini SWE-Bench"
        return headers

    def discover_models(self) -> list[str]:
        """Query the provider's /models endpoint to discover available models.

        Any per-model pricing published in the response is cached in
        ``self._discovered_pricing`` so cost reporting stays accurate.
        """
        if not self.cfg.base_url:
            raise ValueError(f"Base URL is not configured for provider '{self.provider}'.")
        if self.requires_api_key and not self.cfg.api_key:
            raise ValueError(
                f"API key is required for provider '{self.provider}'. "
                "Configure it via environment variables or `bugbench providers configure`."
            )

        base = self.cfg.base_url.rstrip("/")
        models_url = f"{base}/models"
        client = self._client or httpx.Client(timeout=self.cfg.timeout_seconds)
        should_close = self._client is None
        try:
            resp = client.get(models_url, headers=self._headers())
            if resp.status_code == 404 and self.provider == "ollama":
                # Fallback to Ollama native /api/tags
                alt_base = base[:-3] if base.endswith("/v1") else base
                resp = client.get(f"{alt_base}/api/tags")
                resp.raise_for_status()
                payload = resp.json()
                return [m["name"] for m in payload.get("models", []) if "name" in m]

            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", [])
            if not isinstance(data, list):
                return []
            models: list[str] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                model_id = item.get("id")
                if not model_id:
                    continue
                model_id = str(model_id)
                models.append(model_id)
                rates = extract_discovered_pricing(item)
                if rates is not None:
                    self._discovered_pricing[model_id] = rates
            return models
        finally:
            if should_close:
                client.close()

    def apply_resolved_pricing(self, model_id: str) -> str:
        """Resolve and store pricing for ``model_id``; returns the pricing source."""
        in_rate, out_rate, source = resolve_pricing(
            self.provider,
            model_id,
            manual_input=self.cfg.input_cost_per_1k_tokens,
            manual_output=self.cfg.output_cost_per_1k_tokens,
            discovered=self._discovered_pricing.get(model_id),
            allow_builtin_estimate=self.cfg.allow_builtin_pricing_estimates,
        )
        self.cfg.input_cost_per_1k_tokens = in_rate
        self.cfg.output_cost_per_1k_tokens = out_rate
        self.cfg.pricing_source = source
        return source

    def ensure_model_selected(self) -> str:
        """Return configured model or discover available models from the endpoint."""
        if self.cfg.model:
            self.model = self.cfg.model
            if self.model not in self._discovered_pricing:
                # Try to enrich pricing for an explicitly configured model.
                try:
                    self.discover_models()
                except Exception:  # noqa: BLE001 - pricing is best-effort
                    logger.debug("Could not refresh pricing for model %s", self.model)
            self.apply_resolved_pricing(self.model)
            return self.model
        discovered = self.discover_models()
        if not discovered:
            raise RuntimeError(
                f"No model specified and model discovery returned 0 models from {self.cfg.base_url}."
            )
        chosen = select_best_discovered_model(discovered)
        self.model = chosen
        self.cfg.model = chosen
        self.agent_id = f"{self.provider}:{chosen}"
        self.apply_resolved_pricing(chosen)
        logger.info(
            "Auto-discovered %d models on %s; selected '%s' (pricing source: %s)",
            len(discovered),
            self.provider,
            chosen,
            self.cfg.pricing_source or "unknown",
        )
        return chosen

    def test_connection(self) -> ConnectionTestResult:
        start_t = time.perf_counter()
        if not self.cfg.base_url:
            return ConnectionTestResult(
                provider=self.provider,
                reachable=False,
                authenticated=False,
                message="Base URL is not configured.",
            )
        if self.requires_api_key and not self.cfg.api_key:
            return ConnectionTestResult(
                provider=self.provider,
                reachable=False,
                authenticated=False,
                message=(
                    f"API key is not configured for '{self.provider}'. "
                    "Provide base_url, api_key, and model via environment or settings."
                ),
            )
        try:
            models = self.discover_models()
            elapsed = (time.perf_counter() - start_t) * 1000.0
            selected = self.cfg.model or select_best_discovered_model(models)
            pricing_source = self.apply_resolved_pricing(selected) if selected else ""
            return ConnectionTestResult(
                provider=self.provider,
                reachable=True,
                authenticated=True,
                selected_model=selected,
                discovered_models=models[:50],
                message=(
                    f"Connected to {self.cfg.base_url}; {len(models)} model(s) available. "
                    f"Selected: {selected or 'none'}. "
                    f"Pricing: {pricing_source or 'unknown'}."
                ),
                latency_ms=round(elapsed, 2),
            )
        except httpx.HTTPStatusError as exc:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            code = exc.response.status_code
            auth_ok = code not in (401, 403)
            return ConnectionTestResult(
                provider=self.provider,
                reachable=True,
                authenticated=auth_ok,
                selected_model=self.cfg.model,
                message=redact_secrets(
                    f"HTTP {code} from {self.cfg.base_url}: {exc.response.text[:300]}"
                ),
                latency_ms=round(elapsed, 2),
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return ConnectionTestResult(
                provider=self.provider,
                reachable=False,
                authenticated=False,
                selected_model=self.cfg.model,
                message=redact_secrets(f"Connection failed: {exc}"),
                latency_ms=round(elapsed, 2),
            )

    def _post_chat_with_retry(
        self, url: str, body: dict[str, Any], max_retries: int = 2
    ) -> dict[str, Any]:
        client = self._client or httpx.Client(timeout=self.cfg.timeout_seconds)
        should_close = self._client is None
        last_exc: Exception | None = None
        try:
            for attempt in range(max_retries + 1):
                try:
                    resp = client.post(url, headers=self._headers(), json=body)
                    if resp.status_code in (429, 502, 503, 504) and attempt < max_retries:
                        retry_after = float(resp.headers.get("Retry-After", 0.5 * (2**attempt)))
                        time.sleep(min(retry_after, 5.0))
                        continue
                    resp.raise_for_status()
                    return resp.json()
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                    last_exc = exc
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (
                        429,
                        502,
                        503,
                        504,
                    ):
                        raise
                    if attempt < max_retries:
                        time.sleep(0.5 * (2**attempt))
                        continue
                    raise
            raise RuntimeError(f"Request failed after retries: {last_exc}")
        finally:
            if should_close:
                client.close()

    def _request_chat(self, url: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """POST a chat completion, retrying once when the provider returns no choices.

        Some gateways occasionally return a well-formed but empty response (for
        example when a routed backend fails silently). A single retry turns
        that transient failure into a usable answer instead of a bogus
        "no changes submitted" result.
        """
        last_error = ""
        for attempt in range(2):
            data = self._post_chat_with_retry(url, payload)
            choices = data.get("choices") or []
            if choices:
                return data, ""
            # Some gateways signal a routing/backend failure with an "error"
            # object and no choices at all. Surface that verbatim.
            provider_error = data.get("error")
            if provider_error:
                detail = (
                    provider_error.get("message")
                    if isinstance(provider_error, dict)
                    else str(provider_error)
                )
                last_error = (
                    f"Provider returned an error payload (attempt {attempt + 1}/2): {detail}"
                )
            else:
                last_error = (
                    f"Provider returned no choices (attempt {attempt + 1}/2). "
                    f"Response keys: {sorted(data.keys())}"
                )
            logger.warning("%s for model %s", last_error, payload.get("model"))
            if attempt == 0:
                time.sleep(1.0)
        return data, last_error

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        model_id = self.ensure_model_selected()
        system_prompt, user_prompt = build_repair_prompt(task, repo_dir)
        url = f"{self.cfg.base_url.rstrip('/')}/chat/completions"

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }

        data, provider_error = self._request_chat(url, payload)
        choices = data.get("choices", [])
        if not choices:
            return AgentOutput(
                patch_diff="",
                logs=redact_secrets(
                    f"Empty choices returned by {self.provider} ({model_id}). {provider_error}"
                ),
                model_used=model_id,
            )

        content = choices[0].get("message", {}).get("content", "") or ""
        usage = data.get("usage", {}) or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        cost = calculate_cost_usd(prompt_tokens, completion_tokens, self.cfg)
        applied, status_msg = apply_llm_response_to_workspace(content, repo_dir)

        diff_text = collect_workspace_diff(repo_dir) if applied else ""

        return AgentOutput(
            patch_diff=diff_text,
            logs=redact_secrets(
                f"Model: {model_id} | {status_msg}\nResponse length: {len(content)} chars"
            ),
            model_used=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
        )


class OpenAIAdapter(OpenAICompatibleBaseAdapter):
    requires_api_key = True


class OpenRouterAdapter(OpenAICompatibleBaseAdapter):
    requires_api_key = True


class CustomOpenAICompatibleAdapter(OpenAICompatibleBaseAdapter):
    requires_api_key = False


class OllamaLocalAdapter(OpenAICompatibleBaseAdapter):
    requires_api_key = False


class AnthropicAdapter(AgentAdapter):
    """Adapter for Anthropic Claude API (/v1/messages and /v1/models)."""

    def __init__(
        self,
        config: ProviderConfigModel,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.cfg = config
        self.provider = "anthropic"
        self.model = config.model
        self.agent_id = f"anthropic:{config.model or 'auto'}"
        self._client = http_client
        self._discovered_pricing: dict[str, tuple[float, float]] = {}

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.cfg.api_key,
            "anthropic-version": "2023-06-01",
        }

    def discover_models(self) -> list[str]:
        if not self.cfg.api_key:
            raise ValueError("Anthropic API key is required.")
        base = (self.cfg.base_url or "https://api.anthropic.com").rstrip("/")
        url = f"{base}/v1/models" if not base.endswith("/v1") else f"{base}/models"
        client = self._client or httpx.Client(timeout=self.cfg.timeout_seconds)
        should_close = self._client is None
        try:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json().get("data", [])
            models: list[str] = []
            for item in data:
                if not isinstance(item, dict) or "id" not in item:
                    continue
                model_id = str(item["id"])
                models.append(model_id)
                rates = extract_discovered_pricing(item)
                if rates is not None:
                    self._discovered_pricing[model_id] = rates
            return models
        finally:
            if should_close:
                client.close()

    def apply_resolved_pricing(self, model_id: str) -> str:
        """Resolve and store pricing for ``model_id``; returns the pricing source."""
        in_rate, out_rate, source = resolve_pricing(
            "anthropic",
            model_id,
            manual_input=self.cfg.input_cost_per_1k_tokens,
            manual_output=self.cfg.output_cost_per_1k_tokens,
            discovered=self._discovered_pricing.get(model_id),
            allow_builtin_estimate=self.cfg.allow_builtin_pricing_estimates,
        )
        self.cfg.input_cost_per_1k_tokens = in_rate
        self.cfg.output_cost_per_1k_tokens = out_rate
        self.cfg.pricing_source = source
        return source

    def ensure_model_selected(self) -> str:
        if self.cfg.model:
            self.model = self.cfg.model
            if self.model not in self._discovered_pricing:
                try:
                    self.discover_models()
                except Exception:  # noqa: BLE001 - pricing is best-effort
                    logger.debug("Could not refresh pricing for model %s", self.model)
            self.apply_resolved_pricing(self.model)
            return self.model
        discovered = self.discover_models()
        if not discovered:
            raise RuntimeError("No Anthropic model specified and /v1/models returned no models.")
        chosen = select_best_discovered_model(discovered)
        self.model = chosen
        self.cfg.model = chosen
        self.agent_id = f"anthropic:{chosen}"
        self.apply_resolved_pricing(chosen)
        return chosen

    def test_connection(self) -> ConnectionTestResult:
        start_t = time.perf_counter()
        if not self.cfg.api_key:
            return ConnectionTestResult(
                provider="anthropic",
                reachable=False,
                authenticated=False,
                message="Anthropic API key is not configured.",
            )
        try:
            models = self.discover_models()
            elapsed = (time.perf_counter() - start_t) * 1000.0
            selected = self.cfg.model or select_best_discovered_model(models)
            pricing_source = self.apply_resolved_pricing(selected) if selected else ""
            return ConnectionTestResult(
                provider="anthropic",
                reachable=True,
                authenticated=True,
                selected_model=selected,
                discovered_models=models[:50],
                message=(
                    f"Connected to Anthropic API; {len(models)} model(s) discovered. "
                    f"Selected: {selected}. Pricing: {pricing_source or 'unknown'}."
                ),
                latency_ms=round(elapsed, 2),
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return ConnectionTestResult(
                provider="anthropic",
                reachable=False,
                authenticated=False,
                selected_model=self.cfg.model,
                message=redact_secrets(f"Anthropic connection check failed: {exc}"),
                latency_ms=round(elapsed, 2),
            )

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        model_id = self.ensure_model_selected()
        system_prompt, user_prompt = build_repair_prompt(task, repo_dir)
        base = (self.cfg.base_url or "https://api.anthropic.com").rstrip("/")
        url = f"{base}/v1/messages" if not base.endswith("/v1") else f"{base}/messages"

        payload = {
            "model": model_id,
            "max_tokens": self.cfg.max_tokens,
            "temperature": self.cfg.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        client = self._client or httpx.Client(timeout=self.cfg.timeout_seconds)
        should_close = self._client is None
        data: dict[str, Any] = {}
        last_error = ""
        try:
            for attempt in range(2):
                resp = client.post(url, headers=self._headers(), json=payload)
                if resp.status_code in (429, 502, 503, 504) and attempt == 0:
                    time.sleep(float(resp.headers.get("Retry-After", 1.0)))
                    continue
                resp.raise_for_status()
                data = resp.json()
                if data.get("content"):
                    break
                last_error = f"Anthropic returned an empty content block (attempt {attempt + 1}/2)."
                logger.warning("%s (model %s)", last_error, model_id)
                if attempt == 0:
                    time.sleep(1.0)
        finally:
            if should_close:
                client.close()

        blocks = data.get("content", [])
        text_parts = [
            b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        ]
        content = "\n".join(text_parts)
        if not content:
            return AgentOutput(
                patch_diff="",
                logs=redact_secrets(
                    f"Anthropic model {model_id} returned no text content. {last_error}"
                ),
                model_used=model_id,
            )

        usage = data.get("usage", {}) or {}
        in_tok = usage.get("input_tokens")
        out_tok = usage.get("output_tokens")
        tot_tok = (in_tok + out_tok) if (in_tok is not None and out_tok is not None) else None
        cost = calculate_cost_usd(in_tok, out_tok, self.cfg)

        applied, status_msg = apply_llm_response_to_workspace(content, repo_dir)
        diff_text = collect_workspace_diff(repo_dir) if applied else ""

        return AgentOutput(
            patch_diff=diff_text,
            logs=redact_secrets(f"Anthropic model: {model_id} | {status_msg}"),
            model_used=model_id,
            prompt_tokens=in_tok,
            completion_tokens=out_tok,
            total_tokens=tot_tok,
            estimated_cost_usd=cost,
        )
