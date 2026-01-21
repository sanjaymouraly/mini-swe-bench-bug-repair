"""Automated dataset validation and 8-point quality gate checker for Mini SWE-Bench."""

from __future__ import annotations

import time

from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.grading.engine import GradingEngine
from bugbench.models import (
    BenchmarkTask,
    DatasetValidationSummary,
    QualityGateCheck,
    ResolutionStatus,
    SandboxMode,
    TaskValidationReport,
)


class DatasetValidator:
    """Programmatically verifies all 8 dataset quality gates for every benchmark task."""

    def __init__(
        self,
        config: AppConfig | None = None,
        sandbox_mode: SandboxMode | None = None,
    ) -> None:
        self.config = config or AppConfig.from_env()
        self.loader = DatasetLoader(self.config)
        self.grader = GradingEngine(self.config, self.loader, sandbox_mode=sandbox_mode)

    def validate_task(self, task: BenchmarkTask, repeat_runs: int = 2) -> TaskValidationReport:
        start_t = time.perf_counter()
        checks: list[QualityGateCheck] = []

        # Run 1: No-op baseline on the unmodified buggy revision (with test execution enabled)
        t0 = time.perf_counter()
        noop_res = self.grader.grade_patch(
            task=task,
            patch_text="",
            run_id="validation-noop",
            agent_id="noop",
            run_tests_on_empty_patch=True,
        )
        t_noop = (time.perf_counter() - t0) * 1000.0

        # Check 1: Original repository runs and collects tests cleanly
        repo_runs_ok = (
            noop_res.pass_to_pass is not None
            and noop_res.pass_to_pass.total_count > 0
            and noop_res.fail_to_pass is not None
            and noop_res.fail_to_pass.total_count > 0
        )
        checks.append(
            QualityGateCheck(
                check_id="1_repo_installs_and_runs",
                description="Original repository imports and executes test suites cleanly",
                passed=repo_runs_ok,
                details=(
                    f"Collected {noop_res.pass_to_pass.total_count if noop_res.pass_to_pass else 0} P2P "
                    f"and {noop_res.fail_to_pass.total_count if noop_res.fail_to_pass else 0} F2P tests"
                ),
                duration_ms=round(t_noop, 2),
            )
        )

        # Check 2: Pre-existing preservation tests pass on the buggy revision
        p2p_ok = noop_res.pass_to_pass is not None and noop_res.pass_to_pass.all_passed
        checks.append(
            QualityGateCheck(
                check_id="2_pass_to_pass_on_buggy",
                description="Pre-existing preservation tests (PASS_TO_PASS) pass on buggy revision",
                passed=p2p_ok,
                details=(
                    f"Passed {noop_res.pass_to_pass.passed_count}/{noop_res.pass_to_pass.total_count}"
                    if noop_res.pass_to_pass
                    else "PASS_TO_PASS suite did not run"
                ),
                duration_ms=0.0,
            )
        )

        # Check 3: At least one issue-focused test fails before repair
        f2p_fails_before = (
            noop_res.fail_to_pass is not None
            and noop_res.fail_to_pass.total_count > 0
            and noop_res.fail_to_pass.failed_count > 0
        )
        checks.append(
            QualityGateCheck(
                check_id="3_fail_to_pass_fails_before_repair",
                description="Issue-specific tests (FAIL_TO_PASS) fail on buggy revision",
                passed=f2p_fails_before,
                details=(
                    f"Failed {noop_res.fail_to_pass.failed_count}/{noop_res.fail_to_pass.total_count} F2P tests on buggy code"
                    if noop_res.fail_to_pass
                    else "FAIL_TO_PASS suite did not run"
                ),
                duration_ms=0.0,
            )
        )

        # Check 6 (from same noop run): No-op submission does not resolve the task
        noop_rejected = (
            not noop_res.resolved and noop_res.resolution_status == ResolutionStatus.NO_CHANGES
        )
        checks.append(
            QualityGateCheck(
                check_id="6_noop_submission_rejected",
                description="No-op submission does not resolve the task",
                passed=noop_rejected,
                details=f"No-op resolved={noop_res.resolved}, status={noop_res.resolution_status.value}",
                duration_ms=0.0,
            )
        )

        # Run 2: Reference patch evaluation
        t1 = time.perf_counter()
        ref_patch_path = self.loader.get_reference_patch_path(task.task_id)
        ref_patch_text = (
            ref_patch_path.read_text(encoding="utf-8") if ref_patch_path.exists() else ""
        )
        ref_res = self.grader.grade_patch(
            task=task,
            patch_text=ref_patch_text,
            run_id="validation-reference",
            agent_id="reference",
            include_private_tests=True,
        )
        t_ref = (time.perf_counter() - t1) * 1000.0

        # Check 4: Reference patch applies cleanly and passes integrity check
        ref_applies = (
            ref_res.patch_validation.applies_cleanly
            and ref_res.patch_validation.integrity_passed
            and not ref_res.patch_validation.is_empty
        )
        checks.append(
            QualityGateCheck(
                check_id="4_reference_patch_applies_cleanly",
                description="Reference patch applies cleanly to base revision and passes integrity",
                passed=ref_applies,
                details=(
                    f"Modified {ref_res.patch_validation.modified_files}, "
                    f"+{ref_res.patch_validation.added_lines}/-{ref_res.patch_validation.removed_lines}"
                    if ref_applies
                    else "; ".join(ref_res.patch_validation.errors)
                ),
                duration_ms=round(t_ref, 2),
            )
        )

        # Check 5: Reference patch passes all issue-resolution, preservation, and private tests
        ref_passes_all = (
            ref_res.resolved
            and not ref_res.has_regression
            and ref_res.private_passed
            and ref_res.private_tests is not None
            and ref_res.private_tests.all_passed
        )
        checks.append(
            QualityGateCheck(
                check_id="5_reference_patch_passes_all_tests",
                description="Reference patch resolves issue, preservation, and private evaluation tests",
                passed=ref_passes_all,
                details=ref_res.explanation,
                duration_ms=0.0,
            )
        )

        # Check 7: Incomplete and regression-inducing patches are rejected
        t2 = time.perf_counter()
        inc_path = self.loader.get_incomplete_patch_path(task.task_id)
        reg_path = self.loader.get_regression_patch_path(task.task_id)
        inc_rejected = False
        reg_rejected = False
        negative_details: list[str] = []

        if inc_path.exists():
            inc_res = self.grader.grade_patch(
                task=task,
                patch_text=inc_path.read_text(encoding="utf-8"),
                run_id="validation-incomplete",
                agent_id="incomplete",
                include_private_tests=True,
            )
            inc_rejected = not inc_res.resolved
            negative_details.append(f"incomplete: {inc_res.resolution_status.value}")
        else:
            negative_details.append("incomplete.patch missing")

        if reg_path.exists():
            reg_res = self.grader.grade_patch(
                task=task,
                patch_text=reg_path.read_text(encoding="utf-8"),
                run_id="validation-regression",
                agent_id="regression",
                include_private_tests=True,
            )
            reg_rejected = (not reg_res.resolved) and reg_res.has_regression
            negative_details.append(
                f"regression: {reg_res.resolution_status.value} (has_regression={reg_res.has_regression})"
            )
        else:
            negative_details.append("regression.patch missing")

        t_neg = (time.perf_counter() - t2) * 1000.0
        checks.append(
            QualityGateCheck(
                check_id="7_negative_patches_rejected",
                description="Incomplete and regression-inducing patches are rejected accurately",
                passed=(inc_rejected and reg_rejected),
                details=", ".join(negative_details),
                duration_ms=round(t_neg, 2),
            )
        )

        # Check 8: Stability across repeated isolated runs
        t3 = time.perf_counter()
        stable = True
        for _ in range(max(1, repeat_runs - 1)):
            repeat_ref = self.grader.grade_patch(
                task=task,
                patch_text=ref_patch_text,
                run_id="validation-repeat",
                agent_id="reference",
                include_private_tests=True,
            )
            if not repeat_ref.resolved or repeat_ref.has_regression:
                stable = False
                break
        t_rep = (time.perf_counter() - t3) * 1000.0
        checks.append(
            QualityGateCheck(
                check_id="8_repeat_run_stability",
                description="Tests are deterministic and stable across repeated isolated runs",
                passed=stable and ref_passes_all,
                details=f"Verified across {repeat_runs} isolated runs",
                duration_ms=round(t_rep, 2),
            )
        )

        # Sort checks by ID
        checks.sort(key=lambda c: c.check_id)
        all_ok = all(c.passed for c in checks)
        total_ms = (time.perf_counter() - start_t) * 1000.0

        return TaskValidationReport(
            task_id=task.task_id,
            title=task.title,
            difficulty=task.difficulty,
            category=task.category,
            passed=all_ok,
            base_revision=noop_res.base_revision,
            test_suite_hash=task.test_suite_hash,
            reference_patch_hash=task.reference_patch_hash,
            checks=checks,
            duration_ms=round(total_ms, 2),
        )

    def validate_dataset(
        self,
        task_ids: list[str] | None = None,
        repeat_runs: int = 2,
    ) -> DatasetValidationSummary:
        start_t = time.perf_counter()
        tasks = self.loader.load_all_tasks(task_ids=task_ids, ensure_git=True)
        reports: list[TaskValidationReport] = []
        valid_count = 0
        invalid_count = 0

        for task in tasks:
            rep = self.validate_task(task, repeat_runs=repeat_runs)
            reports.append(rep)
            if rep.passed:
                valid_count += 1
            else:
                invalid_count += 1

        total_ms = (time.perf_counter() - start_t) * 1000.0
        return DatasetValidationSummary(
            total_tasks=len(tasks),
            valid_tasks=valid_count,
            invalid_tasks=invalid_count,
            all_passed=(len(tasks) > 0 and invalid_count == 0),
            total_duration_ms=round(total_ms, 2),
            task_reports=reports,
        )
