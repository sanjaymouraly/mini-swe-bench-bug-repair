"""Unit tests for agent adapters, diff extraction, and provider registry."""

from __future__ import annotations

from bugbench.agents.llm_providers import extract_unified_diff
from bugbench.agents.registry import AgentRegistry
from bugbench.config import AppConfig


def test_extract_unified_diff_from_markdown_fence() -> None:
    response = """Here is the fix:
```diff
diff --git a/src/foo.py b/src/foo.py
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,1 +1,1 @@
-x = 1
+x = 2
```
Hope this helps!"""
    diff = extract_unified_diff(response)
    assert diff.startswith("diff --git a/src/foo.py b/src/foo.py")
    assert "+x = 2\n" in diff


def test_provider_catalog_and_adapter_factory(test_config: AppConfig) -> None:
    registry = AgentRegistry(test_config)
    catalog = registry.list_providers()
    provider_ids = {p["id"] for p in catalog}
    assert {
        "offline",
        "reference",
        "noop",
        "incomplete",
        "regression",
        "openai",
        "anthropic",
        "openrouter",
        "custom_openai",
        "ollama",
        "codex_cli",
        "claude_code_cli",
    }.issubset(provider_ids)

    ref_adapter = registry.create_adapter("reference")
    assert ref_adapter.agent_id == "reference-oracle"

    noop_adapter = registry.create_adapter("noop")
    assert noop_adapter.agent_id == "noop-baseline"
