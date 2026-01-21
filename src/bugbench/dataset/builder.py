"""Deterministic Git repository initializer and hash calculator for benchmark tasks."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

DETERMINISTIC_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Mini SWE-Bench",
    "GIT_AUTHOR_EMAIL": "benchmark@bugbench.local",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "Mini SWE-Bench",
    "GIT_COMMITTER_EMAIL": "benchmark@bugbench.local",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    "TZ": "UTC",
    "LC_ALL": "C",
}


def normalize_line_endings(path: Path) -> None:
    """Normalize text files under path to LF (\\n) for cross-platform determinism."""
    files = [path] if path.is_file() else [p for p in sorted(path.rglob("*")) if p.is_file()]

    for file_path in files:
        if any(
            part in file_path.parts
            for part in (".git", "__pycache__", ".pytest_cache", ".hypothesis")
        ) or any(part.endswith(".egg-info") for part in file_path.parts):
            continue
        try:
            raw = file_path.read_bytes()
            if b"\x00" in raw:
                continue  # skip binary
            normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            if normalized != raw:
                file_path.write_bytes(normalized)
        except Exception:
            continue


def clean_repo_transients(repo_dir: Path) -> None:
    """Remove transient build/test artifacts from a repository directory."""
    if not repo_dir.exists():
        return
    for item in list(repo_dir.rglob("*")):
        if not item.exists():
            continue
        if item.name in (
            "__pycache__",
            ".pytest_cache",
            ".hypothesis",
            ".coverage",
        ) or item.name.endswith(".egg-info"):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
        elif item.is_file() and item.suffix in (".pyc", ".pyo"):
            item.unlink(missing_ok=True)


def compute_sha256(paths: list[Path]) -> str:
    """Compute a deterministic SHA-256 digest over a list of files or directories."""
    hasher = hashlib.sha256()
    collected: list[tuple[str, Path]] = []
    for base in paths:
        if not base.exists():
            continue
        if base.is_file():
            collected.append((base.name, base))
        else:
            for p in sorted(base.rglob("*")):
                if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
                    rel = p.relative_to(base).as_posix()
                    collected.append((f"{base.name}/{rel}", p))

    for rel_key, fpath in sorted(collected, key=lambda x: x[0]):
        raw = fpath.read_bytes().replace(b"\r\n", b"\n")
        hasher.update(rel_key.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(raw)
        hasher.update(b"\x00")
    return hasher.hexdigest()


def ensure_task_git_repo(repo_dir: Path, force_reinit: bool = False) -> str:
    """Ensure `repo_dir` is a clean Git repository with a deterministic base commit SHA."""
    repo_dir = repo_dir.resolve()
    clean_repo_transients(repo_dir)
    normalize_line_endings(repo_dir)

    git_dir = repo_dir / ".git"
    if force_reinit and git_dir.exists():
        shutil.rmtree(git_dir, ignore_errors=True)

    env = {**os.environ, **DETERMINISTIC_GIT_ENV}

    if not git_dir.exists():
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "core.autocrlf", "false"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "core.fileMode", "false"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Mini SWE-Bench"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "benchmark@bugbench.local"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            check=True,
        )
        # Ensure consistent file mode (0644) for all files before staging
        for p in repo_dir.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                with contextlib.suppress(Exception):
                    os.chmod(p, 0o644)
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial buggy benchmark revision", "--no-gpg-sign"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            check=True,
        )

    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()
