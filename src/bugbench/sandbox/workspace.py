"""Ephemeral isolated repository workspace creation and security checks."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from types import TracebackType

from bugbench.dataset.builder import (
    DETERMINISTIC_GIT_ENV,
    clean_repo_transients,
    ensure_task_git_repo,
    normalize_line_endings,
)
from bugbench.models import BenchmarkTask


class WorkspaceSecurityError(Exception):
    """Raised when path traversal, symlink escape, or workspace tampering is detected."""


def validate_safe_relative_path(root: Path, rel_path: str | Path) -> Path:
    """Ensure a relative path stays strictly inside `root` without symlink escape."""
    root_resolved = root.resolve()
    rel_str = str(rel_path).replace("\\", "/")
    if rel_str.startswith("/") or ":" in rel_str:
        raise WorkspaceSecurityError(f"Absolute or drive-prefixed path rejected: {rel_path}")
    parts = Path(rel_str).parts
    if ".." in parts:
        raise WorkspaceSecurityError(f"Parent directory traversal ('..') rejected: {rel_path}")
    candidate = (root_resolved / rel_str).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise WorkspaceSecurityError(f"Path escapes workspace root ({root_resolved}): {rel_path}")
    return candidate


def verify_no_symlink_escapes(workspace_dir: Path) -> None:
    """Scan a workspace directory and reject any symlinks pointing outside the workspace."""
    root_resolved = workspace_dir.resolve()
    for root_str, dirs, files in os.walk(root_resolved, followlinks=False):
        current_root = Path(root_str)
        if ".git" in current_root.parts:
            continue
        for entry in list(dirs) + list(files):
            entry_path = current_root / entry
            if entry_path.is_symlink():
                target = entry_path.resolve()
                if not target.is_relative_to(root_resolved):
                    raise WorkspaceSecurityError(
                        f"Symlink escape detected: {entry_path} -> {target}"
                    )


class EphemeralWorkspace:
    """Context manager that provisions a clean, isolated repository checkout for a task."""

    def __init__(
        self,
        task: BenchmarkTask,
        purpose: str = "grading",
        base_temp_dir: Path | None = None,
        include_issue_file: bool = False,
    ) -> None:
        self.task = task
        self.purpose = purpose
        self.base_temp_dir = base_temp_dir
        self.include_issue_file = include_issue_file
        self.workspace_root: Path | None = None
        self.repo_dir: Path | None = None
        self.base_commit: str = ""

    def create(self) -> Path:
        if self.base_temp_dir:
            self.base_temp_dir.mkdir(parents=True, exist_ok=True)
            temp_parent = str(self.base_temp_dir)
        else:
            temp_parent = tempfile.gettempdir()

        unique_name = f"bugbench_{self.task.task_id}_{self.purpose}_{uuid.uuid4().hex[:10]}"
        self.workspace_root = Path(
            tempfile.mkdtemp(prefix=unique_name + "_", dir=temp_parent)
        ).resolve()
        self.repo_dir = self.workspace_root / "repo"

        src_repo = Path(self.task.repo_path).resolve()
        if not src_repo.exists():
            raise FileNotFoundError(f"Source repository not found: {src_repo}")

        # Copy only the clean source files (ignoring any existing .git or __pycache__)
        shutil.copytree(
            src_repo,
            self.repo_dir,
            symlinks=False,
            ignore=shutil.ignore_patterns(
                ".git", "__pycache__", ".pytest_cache", "*.pyc", "*.egg-info", ".hypothesis"
            ),
        )
        clean_repo_transients(self.repo_dir)
        normalize_line_endings(self.repo_dir)

        # Initialize deterministic Git commit and verify revision hash
        self.base_commit = ensure_task_git_repo(self.repo_dir, force_reinit=True)
        if self.task.base_revision and self.base_commit != self.task.base_revision:
            raise WorkspaceSecurityError(
                f"Base revision mismatch for {self.task.task_id}: "
                f"expected {self.task.base_revision}, got {self.base_commit}"
            )

        if self.include_issue_file:
            issue_file = self.workspace_root / "ISSUE.md"
            issue_file.write_text(self.task.issue_description, encoding="utf-8")

        # Ensure world-readable/writable inside sandbox for UID 1000 container execution
        for p in self.workspace_root.rglob("*"):
            try:
                if p.is_dir():
                    os.chmod(p, 0o755)
                else:
                    os.chmod(p, 0o644)
            except Exception:
                pass
        try:
            os.chmod(self.workspace_root, 0o755)
            os.chmod(self.repo_dir, 0o755)
        except Exception:
            pass

        return self.repo_dir

    def collect_git_diff(self) -> str:
        """Collect unified Git diff of tracked and newly created allowed files in the workspace."""
        if not self.repo_dir or not self.repo_dir.exists():
            return ""
        verify_no_symlink_escapes(self.repo_dir)
        clean_repo_transients(self.repo_dir)
        normalize_line_endings(self.repo_dir)

        env = {**os.environ, **DETERMINISTIC_GIT_ENV}
        # Stage untracked files under src/ if any were created by an agent, then diff against HEAD
        src_subdir = self.repo_dir / "src"
        if src_subdir.exists():
            subprocess.run(
                ["git", "add", "-N", "src"],
                cwd=self.repo_dir,
                env=env,
                capture_output=True,
                check=False,
            )
        proc = subprocess.run(
            ["git", "diff", "--no-color", "--no-ext-diff", "HEAD"],
            cwd=self.repo_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        diff_text = proc.stdout.replace("\r\n", "\n")
        return diff_text

    def cleanup(self) -> None:
        if self.workspace_root and self.workspace_root.exists():
            shutil.rmtree(self.workspace_root, ignore_errors=True)

    def __enter__(self) -> EphemeralWorkspace:
        self.create()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.cleanup()
