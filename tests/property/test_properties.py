"""Property-based tests using Hypothesis for Mini SWE-Bench core invariants."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from bugbench.agents.llm_providers import extract_unified_diff
from bugbench.logging_utils import redact_secrets


@settings(max_examples=30)
@given(
    secret_suffix=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
        min_size=16,
        max_size=40,
    ),
    prefix_text=st.text(min_size=0, max_size=40),
    suffix_text=st.text(min_size=0, max_size=40),
)
def test_property_openai_key_always_redacted(
    secret_suffix: str, prefix_text: str, suffix_text: str
) -> None:
    token = f"sk-{secret_suffix}"
    message = f"{prefix_text} Authorization: Bearer {token} {suffix_text}"
    cleaned = redact_secrets(message)
    assert token not in cleaned


@settings(max_examples=25)
@given(
    file_stem=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
        min_size=1,
        max_size=15,
    ),
    added_line=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789_ =+-",
        min_size=1,
        max_size=40,
    ),
)
def test_property_extract_unified_diff_preserves_header_and_trailing_newline(
    file_stem: str, added_line: str
) -> None:
    raw = (
        f"Explanation before\n```diff\n"
        f"diff --git a/src/{file_stem}.py b/src/{file_stem}.py\n"
        f"--- a/src/{file_stem}.py\n"
        f"+++ b/src/{file_stem}.py\n"
        f"@@ -1,1 +1,1 @@\n"
        f"-old\n"
        f"+{added_line}\n"
        f"```\nFooter note"
    )
    extracted = extract_unified_diff(raw)
    assert extracted.startswith(f"diff --git a/src/{file_stem}.py b/src/{file_stem}.py")
    assert extracted.endswith("\n")
    assert f"+{added_line}" in extracted
