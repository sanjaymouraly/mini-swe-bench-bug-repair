"""Unit tests for robust LLM patch application (diff normalisation + fallbacks)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bugbench.agents.base import (
    _ensure_git_headers,
    apply_llm_response_to_workspace,
    apply_unified_diff,
    collect_workspace_diff,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "mod.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t.local",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t.local",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, env=env, check=True, capture_output=True
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--no-gpg-sign"],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
    )
    return repo


def test_ensure_git_headers_synthesises_missing_header() -> None:
    raw = "--- a/src/mod.py\n+++ b/src/mod.py\n@@ -1 +1 @@\n-x = 1\n+x = 9\n"
    out = _ensure_git_headers(raw)
    assert out.splitlines()[0] == "diff --git a/src/mod.py b/src/mod.py"


def test_ensure_git_headers_leaves_existing_header_untouched() -> None:
    raw = "diff --git a/src/mod.py b/src/mod.py\n--- a/src/mod.py\n+++ b/src/mod.py\n"
    assert _ensure_git_headers(raw) == raw


def test_apply_unified_diff_with_wrong_hunk_line_counts_is_recovered(git_repo: Path) -> None:
    """A model that miscounts hunk lines must still be able to apply its fix."""
    bad_counts = (
        "diff --git a/src/mod.py b/src/mod.py\n"
        "--- a/src/mod.py\n"
        "+++ b/src/mod.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-x = 1\n"
        "+x = 42\n"
        "y = 2\n"
        "z = 3\n"
    )
    ok, message = apply_unified_diff(git_repo, bad_counts)
    assert ok, message
    assert "x = 42" in (git_repo / "src" / "mod.py").read_text(encoding="utf-8")


def test_apply_unified_diff_without_git_header_is_accepted(git_repo: Path) -> None:
    raw = "--- a/src/mod.py\n+++ b/src/mod.py\n@@ -1,3 +1,3 @@\n x = 1\n-y = 2\n+y = 20\n z = 3\n"
    ok, message = apply_unified_diff(git_repo, raw)
    assert ok, message
    assert "y = 20" in (git_repo / "src" / "mod.py").read_text(encoding="utf-8")


def test_apply_unified_diff_rejects_non_diff_payload(git_repo: Path) -> None:
    ok, message = apply_unified_diff(git_repo, "I could not reproduce the issue.")
    assert not ok
    assert "unified diff" in message


def test_apply_llm_response_uses_file_block(git_repo: Path) -> None:
    response = "```python:src/mod.py\nx = 1\ny = 200\nz = 3\n```"
    applied, message = apply_llm_response_to_workspace(response, git_repo)
    assert applied, message
    assert "y = 200" in (git_repo / "src" / "mod.py").read_text(encoding="utf-8")


def test_apply_llm_response_uses_heading_style_file_block(git_repo: Path) -> None:
    response = "### File: `src/mod.py`\n```python\nx = 99\ny = 2\nz = 3\n```"
    applied, message = apply_llm_response_to_workspace(response, git_repo)
    assert applied, message
    assert "x = 99" in (git_repo / "src" / "mod.py").read_text(encoding="utf-8")


def test_apply_llm_response_uses_diff_block(git_repo: Path) -> None:
    response = (
        "```diff\n"
        "diff --git a/src/mod.py b/src/mod.py\n"
        "--- a/src/mod.py\n"
        "+++ b/src/mod.py\n"
        "@@ -1,3 +1,3 @@\n"
        " x = 1\n"
        "-y = 2\n"
        "+y = 22\n"
        " z = 3\n"
        "```"
    )
    applied, message = apply_llm_response_to_workspace(response, git_repo)
    assert applied, message
    assert "y = 22" in (git_repo / "src" / "mod.py").read_text(encoding="utf-8")


def test_apply_llm_response_reports_garbage(git_repo: Path) -> None:
    applied, message = apply_llm_response_to_workspace("no code here", git_repo)
    assert not applied
    assert "No valid file block" in message


def test_file_block_cannot_escape_the_workspace(git_repo: Path) -> None:
    from bugbench.sandbox.workspace import WorkspaceSecurityError

    response = "```python:src/../../etc/evil.py\npass\n```"
    with pytest.raises(WorkspaceSecurityError):
        apply_llm_response_to_workspace(response, git_repo)


def test_collect_workspace_diff_includes_new_files(git_repo: Path) -> None:
    (git_repo / "src" / "newmod.py").write_text("q = 1\n", encoding="utf-8")
    diff = collect_workspace_diff(git_repo)
    assert "newmod.py" in diff
    assert "+q = 1" in diff
