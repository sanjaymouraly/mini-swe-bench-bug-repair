"""Adapters for installed CLI coding agents (Codex CLI and Claude Code CLI)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from bugbench.agents.base import AgentAdapter, AgentOutput
from bugbench.logging_utils import redact_secrets
from bugbench.models import BenchmarkTask, ConnectionTestResult


class CodexCLIAdapter(AgentAdapter):
    """Invokes the installed `codex` CLI inside the isolated agent repository workspace."""

    agent_id = "codex-cli"
    provider = "codex_cli"
    model = "codex-cli"

    def __init__(self, timeout_seconds: int = 120, binary_name: str = "codex") -> None:
        self.timeout_seconds = timeout_seconds
        self.binary_name = binary_name

    def test_connection(self) -> ConnectionTestResult:
        exe = shutil.which(self.binary_name)
        if not exe:
            return ConnectionTestResult(
                provider="codex_cli",
                reachable=False,
                authenticated=False,
                selected_model="codex-cli",
                message=f"'{self.binary_name}' CLI executable not found on PATH.",
            )
        return ConnectionTestResult(
            provider="codex_cli",
            reachable=True,
            authenticated=True,
            selected_model="codex-cli",
            discovered_models=["codex-cli"],
            message=f"Found Codex CLI binary at {exe}",
        )

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        exe = shutil.which(self.binary_name)
        if not exe:
            raise RuntimeError(f"Codex CLI ('{self.binary_name}') is not installed on PATH.")

        prompt = (
            f"Fix the bug described below in this repository. Only edit files in {task.allowed_files}. "
            f"Do not modify test files.\n\n{task.issue_description}"
        )
        proc = subprocess.run(
            [exe, "--quiet", prompt],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        diff_proc = subprocess.run(
            ["git", "diff", "--no-color", "--no-ext-diff", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        return AgentOutput(
            patch_diff=diff_proc.stdout.replace("\r\n", "\n"),
            logs=redact_secrets((proc.stdout or "") + "\n" + (proc.stderr or ""))[:4000],
            model_used="codex-cli",
        )


class ClaudeCodeCLIAdapter(AgentAdapter):
    """Invokes the installed `claude` (Claude Code) CLI inside the isolated agent workspace."""

    agent_id = "claude-code-cli"
    provider = "claude_code_cli"
    model = "claude-code-cli"

    def __init__(self, timeout_seconds: int = 120, binary_name: str = "claude") -> None:
        self.timeout_seconds = timeout_seconds
        self.binary_name = binary_name

    def test_connection(self) -> ConnectionTestResult:
        exe = shutil.which(self.binary_name)
        if not exe:
            return ConnectionTestResult(
                provider="claude_code_cli",
                reachable=False,
                authenticated=False,
                selected_model="claude-code-cli",
                message=f"'{self.binary_name}' CLI executable not found on PATH.",
            )
        return ConnectionTestResult(
            provider="claude_code_cli",
            reachable=True,
            authenticated=True,
            selected_model="claude-code-cli",
            discovered_models=["claude-code-cli"],
            message=f"Found Claude Code CLI binary at {exe}",
        )

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        exe = shutil.which(self.binary_name)
        if not exe:
            raise RuntimeError(f"Claude Code CLI ('{self.binary_name}') is not installed on PATH.")

        prompt = (
            f"Fix the bug described below in this repository. Only edit files in {task.allowed_files}. "
            f"Do not modify test files.\n\n{task.issue_description}"
        )
        proc = subprocess.run(
            [exe, "-p", prompt],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        diff_proc = subprocess.run(
            ["git", "diff", "--no-color", "--no-ext-diff", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        return AgentOutput(
            patch_diff=diff_proc.stdout.replace("\r\n", "\n"),
            logs=redact_secrets((proc.stdout or "") + "\n" + (proc.stderr or ""))[:4000],
            model_used="claude-code-cli",
        )
