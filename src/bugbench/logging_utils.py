"""Structured logging and secret redaction utilities for Mini SWE-Bench."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

# Patterns that commonly represent API keys or bearer secrets
_SECRET_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9_\-]{12,})"),
    re.compile(r"(sk-ant-[a-zA-Z0-9_\-]{12,})"),
    re.compile(r"(sk-or-v1-[a-zA-Z0-9_\-]{12,})"),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9._\-]{10,})", re.IGNORECASE),
    re.compile(
        r"((?:api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?)([a-zA-Z0-9._\-]{8,})",
        re.IGNORECASE,
    ),
]


def redact_secrets(text: str, extra_secrets: list[str] | None = None) -> str:
    """Redact API keys, tokens, and configured secret values from text."""
    if not text:
        return text
    redacted = text
    # Redact environment-configured secret values
    env_secret_keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "CUSTOM_OPENAI_API_KEY",
    ]
    secrets_to_mask: list[str] = []
    if extra_secrets:
        secrets_to_mask.extend(s for s in extra_secrets if s and len(s) >= 6)
    for env_key in env_secret_keys:
        val = os.environ.get(env_key, "").strip()
        if val and len(val) >= 6:
            secrets_to_mask.append(val)

    for secret in secrets_to_mask:
        redacted = redacted.replace(secret, "***REDACTED***")

    # Apply regex patterns
    redacted = _SECRET_PATTERNS[0].sub("sk-***REDACTED***", redacted)
    redacted = _SECRET_PATTERNS[1].sub("sk-ant-***REDACTED***", redacted)
    redacted = _SECRET_PATTERNS[2].sub("sk-or-v1-***REDACTED***", redacted)
    redacted = _SECRET_PATTERNS[3].sub(r"\1***REDACTED***", redacted)
    redacted = _SECRET_PATTERNS[4].sub(r"\1***REDACTED***", redacted)
    return redacted


class RedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from log messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(a) if isinstance(a, str) else a for a in record.args
                )
        return True


def get_logger(name: str = "bugbench") -> logging.Logger:
    """Return a configured logger with secret redaction enabled."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        level_name = os.environ.get("BUGBENCH_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        logger.setLevel(level)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask secret keys in a dictionary."""
    result: dict[str, Any] = {}
    for k, v in data.items():
        lower_k = k.lower()
        # ``*_env`` keys hold the *name* of an environment variable (for example
        # ``OPENAI_API_KEY``), never a secret value, so they must not be masked.
        is_secret_field = (
            any(s in lower_k for s in ("api_key", "secret", "password", "token"))
            and "tokens" not in lower_k
            and "max_tokens" not in lower_k
            and not lower_k.endswith("_env")
        )
        if is_secret_field:
            if isinstance(v, str) and v:
                result[k] = f"{v[:4]}...REDACTED" if len(v) > 8 else "***REDACTED***"
            else:
                result[k] = ""
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v)
        elif isinstance(v, str):
            result[k] = redact_secrets(v)
        else:
            result[k] = v
    return result
