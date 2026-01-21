"""Unit tests for DatasetLoader and benchmark metadata."""

from __future__ import annotations

import pytest

from bugbench.dataset.loader import DatasetLoader
from bugbench.models import TaskCategory, TaskDifficulty


def test_load_all_12_benchmark_tasks(dataset_loader: DatasetLoader) -> None:
    tasks = dataset_loader.load_all_tasks()
    assert len(tasks) == 12
    task_ids = [t.task_id for t in tasks]
    expected = [
        "atomicvault-012",
        "chronoshift-005",
        "cliwarden-010",
        "concurqueue-003",
        "confighier-007",
        "idempobox-011",
        "ledgersql-004",
        "pagiflow-001",
        "retryguard-008",
        "schemaver-009",
        "streamparse-006",
        "ttlcachex-002",
    ]
    assert task_ids == expected


def test_filter_tasks_by_difficulty_and_category(dataset_loader: DatasetLoader) -> None:
    easy_tasks = dataset_loader.filter_tasks(difficulty=TaskDifficulty.EASY)
    assert len(easy_tasks) == 4
    assert {t.task_id for t in easy_tasks} == {
        "pagiflow-001",
        "ttlcachex-002",
        "confighier-007",
        "cliwarden-010",
    }

    sql_tasks = dataset_loader.filter_tasks(category=TaskCategory.SQLITE_TRANSACTIONS)
    assert len(sql_tasks) == 1
    assert sql_tasks[0].task_id == "ledgersql-004"


def test_load_task_patches_and_test_paths(dataset_loader: DatasetLoader) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    ref_patch = dataset_loader.get_reference_patch("pagiflow-001")
    inc_patch = dataset_loader.get_incomplete_patch("pagiflow-001")
    reg_patch = dataset_loader.get_regression_patch("pagiflow-001")

    assert "diff --git" in ref_patch
    assert "diff --git" in inc_patch
    assert "diff --git" in reg_patch
    assert ref_patch != inc_patch

    private_paths = dataset_loader.get_private_test_paths(task)
    assert len(private_paths) == 1
    assert private_paths[0].exists()


def test_load_nonexistent_task_raises(dataset_loader: DatasetLoader) -> None:
    with pytest.raises(FileNotFoundError):
        dataset_loader.load_task("nonexistent-999")
