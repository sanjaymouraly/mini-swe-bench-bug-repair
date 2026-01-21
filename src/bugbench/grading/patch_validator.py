"""Rigorous patch verification, anti-tampering, and integrity analysis."""

from __future__ import annotations

import fnmatch
import hashlib
import re
import subprocess
from pathlib import Path

from bugbench.models import BenchmarkTask, PatchValidationResult
from bugbench.sandbox.workspace import verify_no_symlink_escapes

_FORBIDDEN_FILE_PATTERNS = [
    "tests/*",
    "*/tests/*",
    "test_*.py",
    "*_test.py",
    "conftest.py",
    "*/conftest.py",
    "pyproject.toml",
    "pytest.ini",
    "setup.cfg",
    "tox.ini",
    "task.json",
    "evaluation/*",
    "private_evaluations/*",
]

_SUSPICIOUS_CODE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bPYTEST_CURRENT_TEST\b"),
        "Environment inspection for PYTEST_CURRENT_TEST in production code",
    ),
    (
        re.compile(r"\bsys\._getframe\b|\binspect\.(?:stack|currentframe)\b"),
        "Call-stack introspection shortcut detected in patch",
    ),
    (
        re.compile(r"\bos\._exit\s*\(\s*0\s*\)"),
        "Forced os._exit(0) process termination shortcut detected",
    ),
    (
        re.compile(r"@pytest\.mark\.(?:skip|xfail)|pytest\.skip\s*\(|unittest\.skip"),
        "Test skipping or xfail directive injected",
    ),
]


def _strip_diff_prefix(raw_path: str) -> str:
    p = raw_path.strip().split("\t")[0].strip()
    if p in ("/dev/null", "dev/null"):
        return ""
    if p.startswith(("a/", "b/")):
        p = p[2:]
    return p.replace("\\", "/")


class PatchValidator:
    """Validates unified Git diffs for applicability, boundary rules, and integrity."""

    def parse_unified_diff(
        self, patch_text: str
    ) -> tuple[list[str], int, int, list[str], list[str]]:
        """Return (modified_files, added_lines, removed_lines, added_code_lines, format_errors)."""
        normalized = patch_text.replace("\r\n", "\n")
        files: list[str] = []
        added_count = 0
        removed_count = 0
        added_lines: list[str] = []
        errors: list[str] = []

        has_diff_header = False
        lines = normalized.split("\n")
        for line in lines:
            if line.startswith("diff --git "):
                has_diff_header = True
                parts = line.split()
                if len(parts) >= 4:
                    src_p = _strip_diff_prefix(parts[2])
                    dst_p = _strip_diff_prefix(parts[3])
                    for candidate in (src_p, dst_p):
                        if candidate and candidate not in files:
                            files.append(candidate)
            elif line.startswith("--- "):
                has_diff_header = True
                src_p = _strip_diff_prefix(line[4:])
                if src_p and src_p not in files:
                    files.append(src_p)
            elif line.startswith("+++ "):
                has_diff_header = True
                dst_p = _strip_diff_prefix(line[4:])
                if dst_p and dst_p not in files:
                    files.append(dst_p)
            elif line.startswith("rename from "):
                src_p = _strip_diff_prefix(line[len("rename from ") :])
                if src_p and src_p not in files:
                    files.append(src_p)
            elif line.startswith("rename to "):
                dst_p = _strip_diff_prefix(line[len("rename to ") :])
                if dst_p and dst_p not in files:
                    files.append(dst_p)
            elif line.startswith(("new file mode 120000", "old mode 120000", "new mode 120000")):
                errors.append("Symlink mode (120000) is forbidden in candidate patches")
            elif line.startswith("+") and not line.startswith("+++"):
                added_count += 1
                added_lines.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                removed_count += 1

        if normalized.strip() and not has_diff_header:
            errors.append(
                "Malformed patch: missing unified diff headers ('---'/'+++' or 'diff --git')"
            )

        return files, added_count, removed_count, added_lines, errors

    def _is_file_allowed(self, file_path: str, allowed_patterns: list[str]) -> bool:
        if not allowed_patterns:
            # Default: allow files under src/ only
            return file_path.startswith("src/")
        return any(file_path == pat or fnmatch.fnmatch(file_path, pat) for pat in allowed_patterns)

    def _is_forbidden_test_or_config(self, file_path: str) -> bool:
        return any(fnmatch.fnmatch(file_path, pat) for pat in _FORBIDDEN_FILE_PATTERNS)

    def validate_and_apply(
        self,
        task: BenchmarkTask,
        repo_dir: Path,
        patch_text: str,
        apply_changes: bool = True,
    ) -> PatchValidationResult:
        """Validate a candidate patch against `task` rules and optionally apply it to `repo_dir`."""
        normalized = patch_text.replace("\r\n", "\n") if patch_text else ""
        if normalized and not normalized.endswith("\n"):
            normalized += "\n"

        if not normalized.strip():
            return PatchValidationResult(
                is_empty=True,
                applies_cleanly=False,
                integrity_passed=False,
                patch_sha256="",
                errors=["Patch is empty (no changes submitted)."],
            )

        patch_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        modified_files, added_count, removed_count, added_code, parse_errors = (
            self.parse_unified_diff(normalized)
        )

        unauthorized_files: list[str] = []
        tampered_tests: list[str] = []
        suspicious_patterns: list[str] = []
        errors: list[str] = list(parse_errors)

        for fpath in modified_files:
            # Check path traversal or absolute path
            if fpath.startswith("/") or ".." in Path(fpath).parts or ":" in fpath:
                unauthorized_files.append(fpath)
                errors.append(f"Path traversal or absolute path in diff: {fpath}")
                continue

            if self._is_forbidden_test_or_config(fpath):
                tampered_tests.append(fpath)
                unauthorized_files.append(fpath)
                errors.append(
                    f"Test or configuration tampering detected on protected file: {fpath}"
                )
                continue

            if not self._is_file_allowed(fpath, task.allowed_files):
                unauthorized_files.append(fpath)
                errors.append(
                    f"Unauthorized file modification: '{fpath}' is outside allowed paths {task.allowed_files}"
                )

        # Scan added code lines for suspicious evaluation bypass patterns
        joined_added = "\n".join(added_code)
        for regex, description in _SUSPICIOUS_CODE_PATTERNS:
            if regex.search(joined_added):
                suspicious_patterns.append(description)
                errors.append(f"Suspicious pattern: {description}")

        if not modified_files and not errors:
            errors.append("Patch contains no recognizable file modifications.")

        # Verify patch applicability via `git apply --check`
        applies_cleanly = False
        patch_file = repo_dir / ".tmp_candidate.patch"
        try:
            if not parse_errors and modified_files:
                patch_file.write_text(normalized, encoding="utf-8")
                check_proc = subprocess.run(
                    ["git", "apply", "--check", str(patch_file.name)],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if check_proc.returncode == 0:
                    applies_cleanly = True
                else:
                    err_detail = (check_proc.stderr or check_proc.stdout).strip()
                    errors.append(f"Patch does not apply cleanly to base revision: {err_detail}")

                if (
                    applies_cleanly
                    and apply_changes
                    and not unauthorized_files
                    and not tampered_tests
                    and not suspicious_patterns
                ):
                    apply_proc = subprocess.run(
                        ["git", "apply", str(patch_file.name)],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if apply_proc.returncode != 0:
                        applies_cleanly = False
                        errors.append(
                            f"git apply failed: {(apply_proc.stderr or apply_proc.stdout).strip()}"
                        )
                    else:
                        verify_no_symlink_escapes(repo_dir)
        except Exception as exc:
            applies_cleanly = False
            errors.append(f"Patch validation security check failed: {exc}")
        finally:
            patch_file.unlink(missing_ok=True)

        integrity_passed = (
            len(unauthorized_files) == 0
            and len(tampered_tests) == 0
            and len(suspicious_patterns) == 0
            and len(parse_errors) == 0
        )

        return PatchValidationResult(
            is_empty=False,
            applies_cleanly=applies_cleanly,
            integrity_passed=integrity_passed,
            patch_sha256=patch_hash,
            modified_files=modified_files,
            unauthorized_files=unauthorized_files,
            tampered_tests=tampered_tests,
            suspicious_patterns=suspicious_patterns,
            added_lines=added_count,
            removed_lines=removed_count,
            errors=errors,
        )
