"""cliwarden: Structured CLI argument validator and POSIX exit-code runner."""

from cliwarden.runner import (
    EXIT_CONFIG_ERROR,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_RUNTIME_ERROR,
    EXIT_USAGE_ERROR,
    CLIResult,
    CLIRunner,
    ConfigError,
)

__all__ = [
    "CLIResult",
    "CLIRunner",
    "ConfigError",
    "EXIT_CONFIG_ERROR",
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_RUNTIME_ERROR",
    "EXIT_USAGE_ERROR",
]
