"""Unit tests for PatchValidator and anti-tampering enforcement."""

from __future__ import annotations

from pathlib import Path

from bugbench.dataset.loader import DatasetLoader
from bugbench.grading.patch_validator import PatchValidator
from bugbench.sandbox.workspace import EphemeralWorkspace


def test_empty_patch_is_marked_empty(dataset_loader: DatasetLoader, tmp_path: Path) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    validator = PatchValidator()

    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        res = validator.validate_and_apply(task, ws.repo_dir, "")
        assert res.is_empty is True
        assert res.applies_cleanly is False


def test_valid_reference_patch_passes_all_checks(
    dataset_loader: DatasetLoader, tmp_path: Path
) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    ref_patch = dataset_loader.get_reference_patch("pagiflow-001")
    validator = PatchValidator()

    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        res = validator.validate_and_apply(task, ws.repo_dir, ref_patch)
        assert res.is_empty is False
        assert res.applies_cleanly is True
        assert res.integrity_passed is True
        assert res.modified_files == ["src/pagiflow/client.py"]
        assert res.added_lines > 0


def test_patch_modifying_test_file_is_rejected_for_integrity(
    dataset_loader: DatasetLoader, tmp_path: Path
) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    validator = PatchValidator()

    tamper_patch = """diff --git a/tests/test_existing.py b/tests/test_existing.py
--- a/tests/test_existing.py
+++ b/tests/test_existing.py
@@ -1,3 +1,4 @@
+import pytest; pytest.skip("skip all")
 from __future__ import annotations
"""
    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        res = validator.validate_and_apply(task, ws.repo_dir, tamper_patch)
        assert res.integrity_passed is False
        assert len(res.tampered_tests) > 0 or len(res.unauthorized_files) > 0


def test_patch_with_pytest_skip_in_source_is_rejected(
    dataset_loader: DatasetLoader, tmp_path: Path
) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    validator = PatchValidator()

    shortcut_patch = """diff --git a/src/pagiflow/paginator.py b/src/pagiflow/paginator.py
--- a/src/pagiflow/paginator.py
+++ b/src/pagiflow/paginator.py
@@ -1,3 +1,4 @@
+import pytest; pytest.skip("bypass")
 \"\"\"Cursor and offset pagination engine with ETag conditional caching.\"\"\"
"""
    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        res = validator.validate_and_apply(task, ws.repo_dir, shortcut_patch)
        assert res.integrity_passed is False
        assert len(res.suspicious_patterns) > 0


def test_malformed_diff_is_rejected(dataset_loader: DatasetLoader, tmp_path: Path) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    validator = PatchValidator()

    bad_diff = """diff --git a/src/pagiflow/paginator.py b/src/pagiflow/paginator.py
--- a/src/pagiflow/paginator.py
+++ b/src/pagiflow/paginator.py
@@ -999,5 +999,5 @@
-nonexistent line
+replacement line
"""
    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        res = validator.validate_and_apply(task, ws.repo_dir, bad_diff)
        assert res.applies_cleanly is False
        assert len(res.errors) > 0
