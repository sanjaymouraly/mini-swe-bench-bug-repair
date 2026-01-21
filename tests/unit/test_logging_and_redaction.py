"""Unit tests for secret redaction and structured logging."""

from __future__ import annotations

from bugbench.logging_utils import redact_secrets, sanitize_dict


def test_redact_secrets_masks_api_keys_and_bearer_tokens() -> None:
    raw = (
        "Authorization: Bearer sk-1234567890abcdefghijklmnop "
        "and OPENAI_API_KEY=sk-proj-abcdefgh1234567890 "
        "and anthropic sk-ant-api03-1234567890abcdef"
    )
    redacted = redact_secrets(raw)
    assert "sk-1234567890abcdefghijklmnop" not in redacted
    assert "sk-proj-abcdefgh1234567890" not in redacted
    assert "sk-ant-api03-1234567890abcdef" not in redacted
    assert "REDACTED" in redacted


def test_sanitize_dict_masks_sensitive_keys() -> None:
    payload = {
        "provider": "openai",
        "api_key": "sk-super-secret-value-1234567890",
        "nested": {
            "authorization": "Bearer secret-token-9876543210",
            "model": "gpt-4o",
        },
    }
    clean = sanitize_dict(payload)
    assert "REDACTED" in clean["api_key"]
    assert "super-secret" not in clean["api_key"]
    assert "REDACTED" in clean["nested"]["authorization"]
    assert clean["nested"]["model"] == "gpt-4o"
