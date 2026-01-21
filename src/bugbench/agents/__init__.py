"""Multi-provider coding agent and offline patch adapters for Mini SWE-Bench."""

from bugbench.agents.base import AgentAdapter, AgentOutput
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
from bugbench.agents.registry import AgentRegistry

__all__ = [
    "AgentAdapter",
    "AgentOutput",
    "AgentRegistry",
    "AnthropicAdapter",
    "ClaudeCodeCLIAdapter",
    "CodexCLIAdapter",
    "CustomOpenAICompatibleAdapter",
    "IncompleteBaselineAdapter",
    "NoOpBaselineAdapter",
    "OfflinePatchAdapter",
    "OllamaLocalAdapter",
    "OpenAIAdapter",
    "OpenRouterAdapter",
    "ReferenceOracleAdapter",
    "RegressionBaselineAdapter",
]
