#!/usr/bin/env python3
"""Bootstrap and deterministically build all 12 benchmark repositories and patches."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))
if str(ROOT_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "scripts"))

from benchmark_defs.part1 import TASKS_PART1  # noqa: E402
from benchmark_defs.part2 import TASKS_PART2  # noqa: E402
from benchmark_defs.part3 import TASKS_PART3  # noqa: E402

from bugbench.dataset.builder import (  # noqa: E402
    DETERMINISTIC_GIT_ENV,
    clean_repo_transients,
    compute_sha256,
    ensure_task_git_repo,
    normalize_line_endings,
)


def _generate_repo_pyproject(pkg_name: str, summary: str) -> str:
    return f"""[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{pkg_name}"
version = "0.1.0"
description = "{summary}"
readme = "README.md"
requires-python = ">=3.12"
dependencies = []

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
"""


def _generate_repo_readme(task_def: dict[str, Any]) -> str:
    pkg = task_def["package_name"]
    return f"""# `{pkg}` — {task_def["title"]}

{task_def["summary"]}

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
"""


def _diff_variant_against_head(repo_dir: Path, variant_files: dict[str, str]) -> str:
    """Apply `variant_files` to `repo_dir`, capture `git diff HEAD`, and restore `HEAD`."""
    env = {**os.environ, **DETERMINISTIC_GIT_ENV}
    for rel_path, content in variant_files.items():
        target = repo_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        norm = content.replace("\r\n", "\n")
        if not norm.endswith("\n"):
            norm += "\n"
        target.write_text(norm, encoding="utf-8")

    proc = subprocess.run(
        ["git", "diff", "--no-color", "--no-ext-diff", "HEAD"],
        cwd=repo_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    diff_text = proc.stdout.replace("\r\n", "\n")
    subprocess.run(
        ["git", "checkout", "--", "."],
        cwd=repo_dir,
        env=env,
        capture_output=True,
        check=True,
    )
    return diff_text


def build_all_benchmarks(root: Path = ROOT_DIR) -> list[str]:
    benchmarks_dir = root / "benchmarks"
    private_dir = root / "private_evaluations"
    benchmarks_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)

    all_tasks = TASKS_PART1 + TASKS_PART2 + TASKS_PART3
    built_ids: list[str] = []

    for tdef in all_tasks:
        task_id = tdef["task_id"]
        pkg = tdef["package_name"]
        task_dir = benchmarks_dir / task_id
        if task_dir.exists():
            shutil.rmtree(task_dir)
        priv_task_dir = private_dir / task_id
        if priv_task_dir.exists():
            shutil.rmtree(priv_task_dir)

        repo_dir = task_dir / "repo"
        eval_dir = task_dir / "evaluation"
        patches_dir = task_dir / "patches"

        repo_dir.mkdir(parents=True, exist_ok=True)
        eval_dir.mkdir(parents=True, exist_ok=True)
        patches_dir.mkdir(parents=True, exist_ok=True)
        priv_task_dir.mkdir(parents=True, exist_ok=True)

        # Write repo pyproject.toml and README.md
        (repo_dir / "pyproject.toml").write_text(
            _generate_repo_pyproject(pkg, tdef["summary"]), encoding="utf-8"
        )
        (repo_dir / "README.md").write_text(_generate_repo_readme(tdef), encoding="utf-8")

        # Write buggy source files
        for rel_path, code in tdef["files"].items():
            f = repo_dir / rel_path
            f.parent.mkdir(parents=True, exist_ok=True)
            norm = code.replace("\r\n", "\n")
            if not norm.endswith("\n"):
                norm += "\n"
            f.write_text(norm, encoding="utf-8")

        # Write existing preservation tests
        tests_dir = repo_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "test_existing.py").write_text(
            tdef["existing_tests"].replace("\r\n", "\n"), encoding="utf-8"
        )

        # Write issue.md
        issue_md_text = tdef["issue_md"].replace("\r\n", "\n")
        (task_dir / "issue.md").write_text(issue_md_text, encoding="utf-8")

        # Write FAIL_TO_PASS issue tests
        issue_test_file = eval_dir / "test_issue.py"
        issue_test_file.write_text(tdef["issue_tests"].replace("\r\n", "\n"), encoding="utf-8")

        # Write PRIVATE evaluation tests
        private_test_file = priv_task_dir / "test_private.py"
        private_test_file.write_text(tdef["private_tests"].replace("\r\n", "\n"), encoding="utf-8")

        # Initialize deterministic Git commit to compute exact base_revision and generate diffs
        base_rev = ensure_task_git_repo(repo_dir, force_reinit=True)

        ref_diff = _diff_variant_against_head(repo_dir, tdef["reference_files"])
        inc_diff = _diff_variant_against_head(repo_dir, tdef["incomplete_files"])
        reg_diff = _diff_variant_against_head(repo_dir, tdef["regression_files"])

        ref_patch_path = patches_dir / "reference.patch"
        inc_patch_path = patches_dir / "incomplete.patch"
        reg_patch_path = patches_dir / "regression.patch"

        ref_patch_path.write_text(ref_diff, encoding="utf-8")
        inc_patch_path.write_text(inc_diff, encoding="utf-8")
        reg_patch_path.write_text(reg_diff, encoding="utf-8")

        # Remove .git from benchmark template directory so outer Git repository tracks all files cleanly;
        # `ensure_task_git_repo` recreates the exact same `base_rev` deterministically on demand.
        shutil.rmtree(repo_dir / ".git", ignore_errors=True)
        clean_repo_transients(repo_dir)
        normalize_line_endings(task_dir)
        normalize_line_endings(priv_task_dir)

        test_suite_hash = compute_sha256([tests_dir, eval_dir, priv_task_dir])
        ref_patch_hash = compute_sha256([ref_patch_path])

        task_metadata = {
            "task_id": task_id,
            "title": tdef["title"],
            "difficulty": tdef["difficulty"],
            "category": tdef["category"],
            "package_name": pkg,
            "summary": tdef["summary"],
            "issue_description": issue_md_text,
            "reproduction_instructions": tdef["reproduction"],
            "pinned_environment": {
                "python_version": "3.12",
                "dependencies": ["pytest>=8.3.0"],
                "test_command": "pytest -q",
                "docker_image": "software-bug-repair-benchmark-runner:latest",
            },
            "base_revision": base_rev,
            "allowed_files": tdef["allowed_files"],
            "pass_to_pass_tests": ["tests/test_existing.py"],
            "fail_to_pass_tests": ["evaluation/test_issue.py"],
            "private_tests": [f"private_evaluations/{task_id}/test_private.py"],
            "test_suite_hash": test_suite_hash,
            "reference_patch_hash": ref_patch_hash,
        }

        (task_dir / "task.json").write_text(
            json.dumps(task_metadata, indent=2) + "\n", encoding="utf-8"
        )
        built_ids.append(task_id)
        print(f"Built {task_id} (base_revision={base_rev[:12]}, ref_hash={ref_patch_hash[:12]})")

    return built_ids


if __name__ == "__main__":
    ids = build_all_benchmarks()
    print(f"Successfully bootstrapped {len(ids)} benchmark tasks.")
