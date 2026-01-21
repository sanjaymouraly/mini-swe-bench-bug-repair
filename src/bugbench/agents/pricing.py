"""Provider pricing resolution and connection presets for Mini SWE-Bench.

Cost accounting rules (deliberately conservative):

* A cost is **only** reported when the provider returned real token usage **and**
  a price per 1k tokens is known.
* Prices come from one of three sources, recorded in ``pricing_source``:
    - ``provider_discovery`` -- read live from the provider's ``/models`` payload
      (most accurate; used when the endpoint publishes per-model rates).
    - ``builtin_estimate``   -- a bundled, clearly-labelled estimate table. These
      rates change frequently, so they are only used when explicitly requested
      and are always reported as estimates.
    - ``manual``             -- rates the operator entered by hand.
* When no pricing is available the cost is reported as ``None`` (unknown), never
  as ``0.0``, so that "free" is never confused with "unmeasured".
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Connection presets: one-click "easy connect" for the dashboard and CLI.
# ---------------------------------------------------------------------------

PROVIDER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "label": "ChatGPT / OpenAI API",
        "default_base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "cost_tier": "paid",
        "docs_url": "https://platform.openai.com/api-keys",
        "notes": (
            "Requires an API key from platform.openai.com. A ChatGPT Plus/Pro "
            "subscription does NOT include API credits and cannot be used here."
        ),
    },
    {
        "id": "anthropic",
        "label": "Claude API (Anthropic)",
        "default_base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "cost_tier": "paid",
        "docs_url": "https://console.anthropic.com/settings/keys",
        "notes": "Direct Anthropic Messages API. Key required; model auto-discovered.",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "default_base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "cost_tier": "mixed",
        "docs_url": "https://openrouter.ai/keys",
        "notes": "One key, many models. Publishes per-model pricing in /models.",
    },
    {
        "id": "custom_openai",
        "label": "Custom OpenAI-compatible API",
        "default_base_url": "",
        "api_key_env": "CUSTOM_OPENAI_API_KEY",
        "cost_tier": "varies",
        "docs_url": "",
        "notes": (
            "Any OpenAI-compatible endpoint (self-hosted gateway, Groq, DeepSeek, "
            "Together, vLLM, LM Studio). Base URL, key and model are all required "
            "or auto-discovered."
        ),
    },
    {
        "id": "ollama",
        "label": "Local Ollama (free)",
        "default_base_url": "http://localhost:11434/v1",
        "api_key_env": "",
        "cost_tier": "free",
        "docs_url": "https://ollama.com/library",
        "notes": "Local open-weights inference. No key, no cost, fully offline.",
    },
    {
        "id": "codex_cli",
        "label": "Codex CLI (installed agent)",
        "default_base_url": "",
        "api_key_env": "",
        "cost_tier": "external",
        "docs_url": "https://github.com/openai/codex",
        "notes": "Uses the codex CLI's own authentication; not managed by bugbench.",
    },
    {
        "id": "claude_code_cli",
        "label": "Claude Code CLI (installed agent)",
        "default_base_url": "",
        "api_key_env": "",
        "cost_tier": "external",
        "docs_url": "https://github.com/anthropics/claude-code",
        "notes": "Uses the claude CLI's own authentication; not managed by bugbench.",
    },
]

_PRESETS_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in PROVIDER_PRESETS}


def get_preset(provider: str) -> dict[str, Any] | None:
    """Return the connection preset for a provider id, or None."""
    return _PRESETS_BY_ID.get(provider.lower())


def list_presets() -> list[dict[str, Any]]:
    """Return all connection presets."""
    return [dict(p) for p in PROVIDER_PRESETS]


# ---------------------------------------------------------------------------
# Built-in price estimates (USD per 1,000 tokens).
#
# These are ESTIMATES bundled with the tool, not live provider data. They are
# surfaced as "builtin_estimate" so a reader can always tell them apart from
# provider-reported figures. Update the table when rates change, or prefer
# provider discovery / manual configuration for accuracy.
# ---------------------------------------------------------------------------

BUILTIN_PRICING_ESTIMATES: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o": (0.0025, 0.0100),
        "gpt-4o-mini": (0.00015, 0.00060),
        "gpt-4.1": (0.0020, 0.0080),
        "gpt-4.1-mini": (0.00040, 0.00160),
        "gpt-4.1-nano": (0.00010, 0.00040),
        "o3-mini": (0.00110, 0.00440),
        "o4-mini": (0.00110, 0.00440),
    },
    "anthropic": {
        "claude-3-5-haiku": (0.00080, 0.00400),
        "claude-3-5-sonnet": (0.00300, 0.01500),
        "claude-3-7-sonnet": (0.00300, 0.01500),
        "claude-sonnet-4": (0.00300, 0.01500),
        "claude-sonnet-4-5": (0.00300, 0.01500),
        "claude-opus-4": (0.01500, 0.07500),
        "claude-haiku-4-5": (0.00100, 0.00500),
    },
}


def builtin_estimate(provider: str, model: str) -> tuple[float, float] | None:
    """Look up a bundled price estimate for ``provider``/``model``.

    Matching is exact first, then longest-prefix, so newer point releases
    (e.g. ``claude-sonnet-4-5-20250929``) still resolve to their family rate.
    """
    table = BUILTIN_PRICING_ESTIMATES.get(provider.lower())
    if not table or not model:
        return None
    key = model.lower()
    if key in table:
        return table[key]
    best: tuple[int, tuple[float, float]] | None = None
    for name, rates in table.items():
        if key.startswith(name) and (best is None or len(name) > best[0]):
            best = (len(name), rates)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Provider-reported pricing discovery
# ---------------------------------------------------------------------------

# Field names used by the various OpenAI-compatible gateways to publish rates.
_INPUT_PER_1K_KEYS = (
    "input_cost_per_1k_tokens",
    "input_price_per_1k",
    "input_idr_per_1k",
    "prompt_cost_per_1k_tokens",
)
_OUTPUT_PER_1K_KEYS = (
    "output_cost_per_1k_tokens",
    "output_price_per_1k",
    "output_idr_per_1k",
    "completion_cost_per_1k_tokens",
)
_INPUT_PER_TOKEN_KEYS = ("input_cost_per_token",)
_OUTPUT_PER_TOKEN_KEYS = ("output_cost_per_token",)
# Some gateways publish per-million rates instead of per-1k.
_PER_MILLION_SCALE_KEYS = (
    "input_idr_per_1m",
    "output_idr_per_1m",
    "input_cost_per_1m",
    "output_cost_per_1m",
)


def _extract_rate(entry: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in entry:
            continue
        raw = entry[key]
        if not isinstance(raw, (int, float)) or raw < 0:
            continue
        return float(raw)
    return None


def extract_discovered_pricing(entry: dict[str, Any]) -> tuple[float, float] | None:
    """Extract (input, output) USD per 1k tokens from a provider model entry.

    Supports the common shapes:
      * ``{"input_cost_per_1k_tokens": 0.5, "output_cost_per_1k_tokens": 1.5}``
      * ``{"input_idr_per_1k": 0.81, "output_idr_per_1k": 3.24}``
      * ``{"input_idr_per_1m": 810, "output_idr_per_1m": 3240}``
      * ``{"input_cost_per_token": 0.0000005, ...}``
    """
    if not isinstance(entry, dict):
        return None

    in_rate = _extract_rate(entry, _INPUT_PER_1K_KEYS)
    out_rate = _extract_rate(entry, _OUTPUT_PER_1K_KEYS)

    if in_rate is None:
        per_token = _extract_rate(entry, _INPUT_PER_TOKEN_KEYS)
        in_rate = per_token * 1000.0 if per_token is not None else None
    if out_rate is None:
        per_token = _extract_rate(entry, _OUTPUT_PER_TOKEN_KEYS)
        out_rate = per_token * 1000.0 if per_token is not None else None

    if in_rate is None or out_rate is None:
        in_m = _extract_rate(entry, ("input_idr_per_1m", "input_cost_per_1m"))
        out_m = _extract_rate(entry, ("output_idr_per_1m", "output_cost_per_1m"))
        if in_m is not None and out_m is not None:
            in_rate, out_rate = in_m / 1000.0, out_m / 1000.0

    if in_rate is None and out_rate is None:
        return None
    return (in_rate if in_rate is not None else 0.0, out_rate if out_rate is not None else 0.0)


def resolve_pricing(
    provider: str,
    model: str,
    *,
    manual_input: float | None = None,
    manual_output: float | None = None,
    discovered: tuple[float, float] | None = None,
    allow_builtin_estimate: bool = False,
) -> tuple[float | None, float | None, str]:
    """Resolve pricing for a provider/model.

    Returns ``(input_per_1k, output_per_1k, source)`` where ``source`` is one of
    ``"manual"``, ``"provider_discovery"``, ``"builtin_estimate"`` or ``""``
    (unknown).
    """
    if manual_input is not None and manual_output is not None:
        return manual_input, manual_output, "manual"
    if discovered is not None:
        return discovered[0], discovered[1], "provider_discovery"
    if allow_builtin_estimate:
        est = builtin_estimate(provider, model)
        if est is not None:
            return est[0], est[1], "builtin_estimate"
    return None, None, ""


def format_usd(value: float | None) -> str:
    """Format a USD amount for display, distinguishing unknown from zero."""
    if value is None:
        return "n/a"
    if value == 0:
        return "$0.00"
    if value < 0.01:
        return f"${value:.6f}"
    return f"${value:.4f}"
