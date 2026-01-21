"""Shared pytest fixtures for Mini SWE-Bench test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.models import SandboxMode
from bugbench.storage.database import BenchmarkDatabase


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def test_config(project_root: Path, tmp_path: Path) -> AppConfig:
    db_path = tmp_path / "test_bugbench.db"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        root_dir=project_root,
        benchmarks_dir=project_root / "benchmarks",
        private_tests_dir=project_root / "private_evaluations",
        artifacts_dir=artifacts_dir,
        db_path=db_path,
        sandbox_mode=SandboxMode.SUBPROCESS,
    )


@pytest.fixture
def dataset_loader(test_config: AppConfig) -> DatasetLoader:
    return DatasetLoader(test_config)


@pytest.fixture
def test_db(test_config: AppConfig) -> BenchmarkDatabase:
    return BenchmarkDatabase(test_config.db_path)
