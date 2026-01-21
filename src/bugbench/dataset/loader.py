"""Dataset loader for Mini SWE-Bench tasks and confidential evaluation assets."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from bugbench.config import AppConfig
from bugbench.dataset.builder import compute_sha256, ensure_task_git_repo
from bugbench.models import BenchmarkTask, Difficulty, TaskCategory


class DatasetLoader:
    """Loads, filters, and inspects benchmark tasks and their evaluation suites."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig.from_env()

    def list_task_dirs(self) -> list[Path]:
        if not self.config.benchmarks_dir.exists():
            return []
        return sorted(
            [
                p
                for p in self.config.benchmarks_dir.iterdir()
                if p.is_dir() and (p / "task.json").exists()
            ],
            key=lambda p: p.name,
        )

    def load_task(self, task_id_or_dir: str | Path, ensure_git: bool = False) -> BenchmarkTask:
        if isinstance(task_id_or_dir, Path):
            task_dir = task_id_or_dir.resolve()
        else:
            task_dir = (self.config.benchmarks_dir / task_id_or_dir).resolve()

        task_json_path = task_dir / "task.json"
        if not task_json_path.exists():
            raise FileNotFoundError(f"Task metadata not found: {task_json_path}")

        data = json.loads(task_json_path.read_text(encoding="utf-8"))
        repo_dir = task_dir / "repo"

        issue_md = task_dir / "issue.md"
        if issue_md.exists() and not data.get("issue_description"):
            data["issue_description"] = issue_md.read_text(encoding="utf-8")

        if ensure_git and repo_dir.exists() and not data.get("base_revision"):
            base_rev = ensure_task_git_repo(repo_dir)
            shutil.rmtree(repo_dir / ".git", ignore_errors=True)
            data["base_revision"] = base_rev

        # Compute test suite and reference patch hashes if not already set or to verify
        existing_test_path = repo_dir / "tests"
        issue_test_path = task_dir / "evaluation"
        private_test_path = self.get_private_test_dir(data["task_id"])
        computed_test_hash = compute_sha256(
            [existing_test_path, issue_test_path, private_test_path]
        )
        if not data.get("test_suite_hash"):
            data["test_suite_hash"] = computed_test_hash

        ref_patch_path = task_dir / "patches" / "reference.patch"
        if ref_patch_path.exists() and not data.get("reference_patch_hash"):
            data["reference_patch_hash"] = compute_sha256([ref_patch_path])

        data["repo_path"] = str(repo_dir)
        data["task_dir"] = str(task_dir)
        return BenchmarkTask.model_validate(data)

    def load_all_tasks(
        self,
        difficulty: str | Difficulty | None = None,
        category: str | TaskCategory | None = None,
        task_ids: list[str] | None = None,
        search: str | None = None,
        ensure_git: bool = False,
    ) -> list[BenchmarkTask]:
        tasks: list[BenchmarkTask] = []
        for task_dir in self.list_task_dirs():
            task = self.load_task(task_dir, ensure_git=ensure_git)
            if task_ids and task.task_id not in task_ids:
                continue
            if difficulty and task.difficulty.value != str(difficulty).lower():
                continue
            if category and task.category.value != str(category).lower():
                continue
            if search:
                q = search.lower()
                haystack = (
                    f"{task.task_id} {task.title} {task.summary} "
                    f"{task.category.value} {task.package_name}"
                ).lower()
                if q not in haystack:
                    continue
            tasks.append(task)
        return tasks

    def get_private_test_dir(self, task_id: str) -> Path:
        return (self.config.private_tests_dir / task_id).resolve()

    def get_private_test_file(self, task_id: str) -> Path:
        return self.get_private_test_dir(task_id) / "test_private.py"

    def get_issue_test_file(self, task_id: str) -> Path:
        return (self.config.benchmarks_dir / task_id / "evaluation" / "test_issue.py").resolve()

    def get_reference_patch_path(self, task_id: str) -> Path:
        return (self.config.benchmarks_dir / task_id / "patches" / "reference.patch").resolve()

    def get_incomplete_patch_path(self, task_id: str) -> Path:
        return (self.config.benchmarks_dir / task_id / "patches" / "incomplete.patch").resolve()

    def get_regression_patch_path(self, task_id: str) -> Path:
        return (self.config.benchmarks_dir / task_id / "patches" / "regression.patch").resolve()

    def load_reference_patch(self, task_id: str) -> str:
        path = self.get_reference_patch_path(task_id)
        if not path.exists():
            raise FileNotFoundError(f"Reference patch missing for {task_id}: {path}")
        return path.read_text(encoding="utf-8")

    def get_reference_patch(self, task_id: str) -> str:
        return self.load_reference_patch(task_id)

    def get_incomplete_patch(self, task_id: str) -> str:
        path = self.get_incomplete_patch_path(task_id)
        if not path.exists():
            raise FileNotFoundError(f"Incomplete patch missing for {task_id}: {path}")
        return path.read_text(encoding="utf-8")

    def get_regression_patch(self, task_id: str) -> str:
        path = self.get_regression_patch_path(task_id)
        if not path.exists():
            raise FileNotFoundError(f"Regression patch missing for {task_id}: {path}")
        return path.read_text(encoding="utf-8")

    def get_repo_dir(self, task_id: str) -> Path:
        return (self.config.benchmarks_dir / task_id / "repo").resolve()

    def get_private_test_paths(self, task: BenchmarkTask | str) -> list[Path]:
        tid = task.task_id if isinstance(task, BenchmarkTask) else task
        pdir = self.get_private_test_dir(tid)
        if not pdir.exists():
            return []
        return sorted(pdir.glob("test_*.py"))

    def filter_tasks(
        self,
        difficulty: str | Difficulty | None = None,
        category: str | TaskCategory | None = None,
        task_ids: list[str] | None = None,
        search: str | None = None,
    ) -> list[BenchmarkTask]:
        return self.load_all_tasks(
            difficulty=difficulty,
            category=category,
            task_ids=task_ids,
            search=search,
        )
