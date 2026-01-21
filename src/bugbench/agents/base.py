"""Base agent adapter interface and workspace prompt/patch helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from bugbench.models import BenchmarkTask, ConnectionTestResult
from bugbench.sandbox.workspace import validate_safe_relative_path


@dataclass
class AgentOutput:
    patch_diff: str
    logs: str = ""
    model_used: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None


class AgentAdapter(ABC):
    """Abstract base class for all repair agents and offline patch sources."""

    agent_id: str = "base"
    provider: str = "offline"
    model: str = "manual"

    @abstractmethod
    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        """Inspect `repo_dir` and generate a unified Git diff resolving `task`."""

    def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            provider=self.provider,
            reachable=True,
            authenticated=True,
            selected_model=self.model,
            discovered_models=[self.model],
            message=f"Offline adapter '{self.agent_id}' is ready.",
        )


def build_repair_prompt(task: BenchmarkTask, repo_dir: Path) -> tuple[str, str]:
    """Build system and user prompts from the isolated workspace without leaking hidden tests."""
    system_prompt = (
        "You are an expert Python software engineer repairing a bug in a repository.\n"
        "You must fix the root cause described in the issue report without breaking "
        "existing functionality.\n"
        "Do NOT modify test files or configuration files. Only modify allowed source "
        "files under `src/`.\n"
        "\n"
        "## Response format (follow this exactly)\n"
        "Return ONE or MORE complete replacement files, each in its own fenced block, "
        "using exactly this shape:\n"
        "\n"
        "```python:src/package/module.py\n"
        "<the ENTIRE updated content of that file, unmodified except for your fix>\n"
        "```\n"
        "\n"
        "Rules for the response format:\n"
        "- The fence header must be ```python: followed by the path relative to the "
        "repository root (for example ```python:src/pkg/module.py).\n"
        "- The block body must be the FULL new content of the file, not a fragment "
        "and not a diff.\n"
        "- Include every file you changed, and nothing else.\n"
        "- Add no commentary before or after the blocks.\n"
        "\n"
        "A unified git diff inside a ```diff ... ``` block is accepted as an "
        "alternative, but complete replacement files are more reliable."
    )

    file_sections: list[str] = []
    src_dir = repo_dir / "src"
    if src_dir.exists():
        for py_file in sorted(src_dir.rglob("*.py")):
            rel = py_file.relative_to(repo_dir).as_posix()
            content = py_file.read_text(encoding="utf-8")
            file_sections.append(f"### File: `{rel}`\n```python\n{content}\n```")

    user_prompt = (
        f"# Task: {task.task_id} — {task.title}\n\n"
        f"## Allowed Modifiable Files\n"
        + "\n".join(f"- `{p}`" for p in task.allowed_files)
        + f"\n\n## Issue Description\n{task.issue_description}\n\n"
        f"## Reproduction Instructions\n{task.reproduction_instructions}\n\n"
        f"## Repository Source Code\n\n" + "\n\n".join(file_sections) + "\n\n## Your Answer\n"
        "Return the complete updated file(s) in the format described above.\n"
    )
    return system_prompt, user_prompt


_FILE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*[:\s]\s*(src/[a-zA-Z0-9_./\-]+\.py)\s*\n(.*?)```",
    re.DOTALL,
)
_DIFF_BLOCK_RE = re.compile(
    r"```(?:diff|patch)\s*\n(.*?)```",
    re.DOTALL,
)
# Some models mirror the "### File: `path`" heading used in the prompt.
_HEADING_FILE_BLOCK_RE = re.compile(
    r"###+\s*File:\s*`?(src/[a-zA-Z0-9_./\-]+\.py)`?\s*\n+```(?:python|py)?\n(.*?)```",
    re.DOTALL,
)


def extract_unified_diff(response_text: str) -> str:
    """Extract a unified diff from markdown fences or raw LLM response text."""
    diff_matches = _DIFF_BLOCK_RE.findall(response_text)
    candidate = diff_matches[0] if diff_matches else response_text
    normalized = candidate.replace("\r\n", "\n").strip("\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _ensure_git_headers(diff_text: str) -> str:
    """Add missing ``diff --git`` headers to a unified diff.

    Many models emit a bare ``---``/``+++``/``@@`` sequence. ``git apply``
    accepts that, but the presence of an explicit header makes multi-file
    patches and renames unambiguous. Sections that already carry a
    ``diff --git`` header are left untouched.
    """
    lines = diff_text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    section_has_header = False
    while i < n:
        line = lines[i]
        if line.startswith("diff --git "):
            section_has_header = True
            out.append(line)
            i += 1
            continue
        if line.startswith("@@"):
            # A new hunk implies a new file section.
            section_has_header = False
            out.append(line)
            i += 1
            continue
        if line.startswith("--- "):
            # Look ahead for the matching "+++ " header.
            src_path = line[4:].split("\t")[0].strip()
            dst_path = src_path
            j = i + 1
            while j < n and not lines[j].startswith("+++ "):
                j += 1
            if j < n:
                dst_path = lines[j][4:].split("\t")[0].strip()
            if not section_has_header:
                if not src_path.startswith(("a/", "b/")):
                    src_path = f"a/{src_path.lstrip('/')}"
                if not dst_path.startswith(("a/", "b/")):
                    dst_path = f"b/{dst_path.lstrip('/')}"
                out.append(f"diff --git {src_path} {dst_path}")
                section_has_header = True
            out.append(line)
            i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _apply_with_git(repo_dir: Path, diff_text: str, extra_args: list[str]) -> tuple[bool, str]:
    tmp_patch = repo_dir / ".llm_candidate.patch"
    try:
        tmp_patch.write_text(diff_text, encoding="utf-8")
        proc = subprocess.run(
            ["git", "apply", *extra_args, str(tmp_patch.name)],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return True, "Applied unified diff via git apply."
        return False, (proc.stderr or proc.stdout).strip()
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a log line
        return False, f"git apply error: {exc}"
    finally:
        tmp_patch.unlink(missing_ok=True)


def collect_workspace_diff(repo_dir: Path) -> str:
    """Collect the unified diff of the agent's changes in ``repo_dir``.

    Untracked files under ``src/`` are intent-added first so that newly
    created modules also appear in the diff.
    """
    src_subdir = repo_dir / "src"
    if src_subdir.exists():
        subprocess.run(
            ["git", "add", "-N", "src"],
            cwd=repo_dir,
            capture_output=True,
            check=False,
        )
    proc = subprocess.run(
        ["git", "diff", "--no-color", "--no-ext-diff", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.replace("\r\n", "\n")


def apply_unified_diff(repo_dir: Path, raw_diff: str) -> tuple[bool, str]:
    """Apply a model-generated unified diff to ``repo_dir``, tolerating common defects.

    Models frequently emit diffs with slightly wrong hunk line counts or
    without ``diff --git`` headers. Rather than discarding an otherwise
    correct repair, the diff is normalised and applied with increasingly
    forgiving strategies:

    1. ``git apply --recount`` (recomputes hunk line counts).
    2. ``git apply --3way --recount`` (three-way merge fallback).
    3. GNU ``patch -p1`` (different fuzzy-matching implementation).
    """
    if not raw_diff or "--- " not in raw_diff or "+++ " not in raw_diff:
        return False, "Response does not contain a recognisable unified diff."

    normalized = raw_diff.replace("\r\n", "\n").strip("\n") + "\n"
    with_header = _ensure_git_headers(normalized)

    attempts: list[tuple[list[str], str]] = [
        (["--recount", "--whitespace=nowarn"], "git apply --recount"),
        (["--3way", "--recount", "--whitespace=nowarn"], "git apply --3way --recount"),
    ]
    errors: list[str] = []
    for args, label in attempts:
        ok, err = _apply_with_git(repo_dir, with_header, args)
        if ok:
            return True, f"Applied unified diff via {label}."
        errors.append(f"{label}: {err}")

    # Last resort: GNU patch, if available on this host.
    if shutil.which("patch"):
        try:
            proc = subprocess.run(
                ["patch", "-p1", "-N", "--no-backup-if-mismatch", "-r", "-"],
                cwd=repo_dir,
                input=with_header,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                return True, "Applied unified diff via GNU patch."
            errors.append(f"patch: {(proc.stdout or proc.stderr or '').strip()}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"patch: {exc}")

    return False, "; ".join(errors)


def apply_llm_response_to_workspace(response_text: str, repo_dir: Path) -> tuple[bool, str]:
    """Parse an LLM response (file blocks or unified diff) and apply it to `repo_dir`."""
    # First check for explicit file replacement blocks: ```python:src/pkg/mod.py
    file_matches = _FILE_BLOCK_RE.findall(response_text) or _HEADING_FILE_BLOCK_RE.findall(
        response_text
    )
    if file_matches:
        applied_files: list[str] = []
        for rel_path, new_content in file_matches:
            rel_clean = rel_path.strip()
            target = validate_safe_relative_path(repo_dir, rel_clean)
            target.parent.mkdir(parents=True, exist_ok=True)
            normalized = new_content.replace("\r\n", "\n")
            if not normalized.endswith("\n"):
                normalized += "\n"
            target.write_text(normalized, encoding="utf-8")
            applied_files.append(rel_clean)
        return True, f"Updated files in workspace: {', '.join(applied_files)}"

    # Second check for unified diff blocks: ```diff ... ```
    diff_matches = _DIFF_BLOCK_RE.findall(response_text)
    candidate_diff = diff_matches[0] if diff_matches else response_text
    if "--- " in candidate_diff and "+++ " in candidate_diff:
        return apply_unified_diff(repo_dir, candidate_diff)

    return False, "No valid file block or unified diff found in model response."
