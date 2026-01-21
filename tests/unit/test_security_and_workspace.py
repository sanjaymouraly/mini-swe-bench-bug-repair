"""Security, workspace isolation, symlink escape, and anti-tampering tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bugbench.dataset.loader import DatasetLoader
from bugbench.grading.patch_validator import PatchValidator
from bugbench.sandbox.workspace import (
    EphemeralWorkspace,
    WorkspaceSecurityError,
    validate_safe_relative_path,
    verify_no_symlink_escapes,
)


def test_validate_safe_relative_path_blocks_traversal_and_absolute_paths(
    tmp_path: Path,
) -> None:
    safe = validate_safe_relative_path(tmp_path, "src/pkg/module.py")
    assert safe == (tmp_path / "src/pkg/module.py").resolve()

    with pytest.raises(WorkspaceSecurityError, match="Parent directory traversal"):
        validate_safe_relative_path(tmp_path, "src/../../outside.py")

    with pytest.raises(WorkspaceSecurityError, match="Absolute or drive-prefixed"):
        validate_safe_relative_path(tmp_path, "/etc/passwd")

    with pytest.raises(WorkspaceSecurityError, match="Absolute or drive-prefixed"):
        validate_safe_relative_path(tmp_path, "C:\\Windows\\System32")


def test_verify_no_symlink_escapes_detects_external_symlink(
    tmp_path: Path,
) -> None:
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    outside_file = tmp_path / "secret_outside.txt"
    outside_file.write_text("confidential", encoding="utf-8")

    escape_link = ws_dir / "leak.txt"
    escape_link.symlink_to(outside_file)

    with pytest.raises(WorkspaceSecurityError, match="Symlink escape detected"):
        verify_no_symlink_escapes(ws_dir)


def test_ephemeral_workspace_detects_wrong_base_revision(
    dataset_loader: DatasetLoader, tmp_path: Path
) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    tampered_task = task.model_copy(
        update={"base_revision": "0000000000000000000000000000000000000000"}
    )

    with (
        pytest.raises(WorkspaceSecurityError, match="Base revision mismatch"),
        EphemeralWorkspace(tampered_task, base_temp_dir=tmp_path),
    ):
        pass


@pytest.mark.parametrize(
    ("injected_line", "expected_keyword"),
    [
        ("import os; os._exit(0)", "os._exit(0)"),
        ("import os; _ = os.environ.get('PYTEST_CURRENT_TEST')", "PYTEST_CURRENT_TEST"),
        ("import inspect; _ = inspect.stack()", "introspection"),
        ("import sys; _ = sys._getframe()", "introspection"),
    ],
)
def test_patch_validator_blocks_evaluation_shortcuts(
    dataset_loader: DatasetLoader,
    tmp_path: Path,
    injected_line: str,
    expected_keyword: str,
) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    validator = PatchValidator()

    patch = (
        "diff --git a/src/pagiflow/client.py b/src/pagiflow/client.py\n"
        "--- a/src/pagiflow/client.py\n"
        "+++ b/src/pagiflow/client.py\n"
        "@@ -1,3 +1,4 @@\n"
        f"+{injected_line}\n"
        ' """Paginated API client and ETag conditional response cache."""\n'
    )
    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        res = validator.validate_and_apply(task, ws.repo_dir, patch, apply_changes=False)
        assert res.integrity_passed is False
        assert any(expected_keyword in s for s in res.suspicious_patterns)


def test_patch_validator_blocks_pyproject_and_unauthorized_source_file(
    dataset_loader: DatasetLoader, tmp_path: Path
) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    validator = PatchValidator()

    config_tamper = (
        "diff --git a/pyproject.toml b/pyproject.toml\n"
        "--- a/pyproject.toml\n"
        "+++ b/pyproject.toml\n"
        "@@ -1,3 +1,4 @@\n"
        "+# tampered\n"
        " [build-system]\n"
    )
    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        res_cfg = validator.validate_and_apply(
            task, ws.repo_dir, config_tamper, apply_changes=False
        )
        assert res_cfg.integrity_passed is False
        assert "pyproject.toml" in res_cfg.tampered_tests

        unauth_patch = (
            "diff --git a/src/pagiflow/__init__.py b/src/pagiflow/__init__.py\n"
            "--- a/src/pagiflow/__init__.py\n"
            "+++ b/src/pagiflow/__init__.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+# unauthorized edit to __init__.py\n"
        )
        res_unauth = validator.validate_and_apply(
            task, ws.repo_dir, unauth_patch, apply_changes=False
        )
        assert res_unauth.integrity_passed is False
        assert "src/pagiflow/__init__.py" in res_unauth.unauthorized_files
