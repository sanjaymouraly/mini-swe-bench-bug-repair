"""Deterministic grading engine for Mini SWE-Bench."""

from __future__ import annotations

import time

from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.grading.patch_validator import PatchValidator
from bugbench.models import (
    BenchmarkTask,
    ExecutionStatus,
    ResolutionStatus,
    SandboxMode,
    TaskEvaluationResult,
    utc_now_iso,
)
from bugbench.sandbox.executor import SandboxExecutor
from bugbench.sandbox.workspace import EphemeralWorkspace


class GradingEngine:
    """Grades a candidate Git patch against a benchmark task in a clean environment."""

    def __init__(
        self,
        config: AppConfig | None = None,
        loader: DatasetLoader | None = None,
        sandbox_mode: SandboxMode | None = None,
    ) -> None:
        self.config = config or AppConfig.from_env()
        self.loader = loader or DatasetLoader(self.config)
        self.validator = PatchValidator()
        self.executor = SandboxExecutor(self.config, mode_override=sandbox_mode)

    def grade_patch(
        self,
        task: BenchmarkTask,
        patch_text: str,
        run_id: str = "manual-run",
        agent_id: str = "offline",
        provider: str = "offline",
        model: str = "manual",
        include_private_tests: bool = True,
        run_tests_on_empty_patch: bool = False,
        timeout_seconds: int | None = None,
        agent_logs: str = "",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        estimated_cost_usd: float | None = None,
    ) -> TaskEvaluationResult:
        """Execute full patch verification and 3-phase test grading in a fresh checkout."""
        started_at = utc_now_iso()
        start_t = time.perf_counter()

        with EphemeralWorkspace(task, purpose="grading") as ws:
            assert ws.repo_dir is not None
            repo_dir = ws.repo_dir
            base_rev = ws.base_commit

            validation = self.validator.validate_and_apply(
                task=task,
                repo_dir=repo_dir,
                patch_text=patch_text,
                apply_changes=True,
            )

            # Case 1: Integrity violation (test tampering, unauthorized file, shortcut)
            if not validation.is_empty and not validation.integrity_passed:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                return TaskEvaluationResult(
                    run_id=run_id,
                    task_id=task.task_id,
                    title=task.title,
                    difficulty=task.difficulty,
                    category=task.category,
                    agent_id=agent_id,
                    provider=provider,
                    model=model,
                    sandbox_mode=self.executor.effective_mode.value,
                    base_revision=base_rev,
                    test_suite_hash=task.test_suite_hash,
                    patch_diff=patch_text,
                    patch_validation=validation,
                    execution_status=ExecutionStatus.COMPLETED,
                    resolution_status=ResolutionStatus.INTEGRITY_VIOLATION,
                    resolved=False,
                    issue_fixed=False,
                    has_regression=False,
                    private_passed=False,
                    failure_classification="PATCH_INTEGRITY_VIOLATION",
                    explanation="; ".join(validation.errors),
                    duration_ms=round(elapsed_ms, 2),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=estimated_cost_usd,
                    started_at=started_at,
                    completed_at=utc_now_iso(),
                    agent_logs=agent_logs,
                )

            # Case 2: Non-empty patch that fails to apply cleanly
            if not validation.is_empty and not validation.applies_cleanly:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                return TaskEvaluationResult(
                    run_id=run_id,
                    task_id=task.task_id,
                    title=task.title,
                    difficulty=task.difficulty,
                    category=task.category,
                    agent_id=agent_id,
                    provider=provider,
                    model=model,
                    sandbox_mode=self.executor.effective_mode.value,
                    base_revision=base_rev,
                    test_suite_hash=task.test_suite_hash,
                    patch_diff=patch_text,
                    patch_validation=validation,
                    execution_status=ExecutionStatus.COMPLETED,
                    resolution_status=ResolutionStatus.INVALID_PATCH,
                    resolved=False,
                    issue_fixed=False,
                    has_regression=False,
                    private_passed=False,
                    failure_classification="PATCH_DOES_NOT_APPLY",
                    explanation="; ".join(validation.errors),
                    duration_ms=round(elapsed_ms, 2),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=estimated_cost_usd,
                    started_at=started_at,
                    completed_at=utc_now_iso(),
                    agent_logs=agent_logs,
                )

            # Case 3: Empty patch when not running baseline test inspection
            if validation.is_empty and not run_tests_on_empty_patch:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                return TaskEvaluationResult(
                    run_id=run_id,
                    task_id=task.task_id,
                    title=task.title,
                    difficulty=task.difficulty,
                    category=task.category,
                    agent_id=agent_id,
                    provider=provider,
                    model=model,
                    sandbox_mode=self.executor.effective_mode.value,
                    base_revision=base_rev,
                    test_suite_hash=task.test_suite_hash,
                    patch_diff="",
                    patch_validation=validation,
                    execution_status=ExecutionStatus.COMPLETED,
                    resolution_status=ResolutionStatus.NO_CHANGES,
                    resolved=False,
                    issue_fixed=False,
                    has_regression=False,
                    private_passed=False,
                    failure_classification="EMPTY_PATCH_SUBMITTED",
                    explanation="No code changes were generated or submitted.",
                    duration_ms=round(elapsed_ms, 2),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=estimated_cost_usd,
                    started_at=started_at,
                    completed_at=utc_now_iso(),
                    agent_logs=agent_logs,
                )

            # Run the 3 test phases in the isolated sandbox
            existing_test_file = repo_dir / "tests" / "test_existing.py"
            issue_test_file = self.loader.get_issue_test_file(task.task_id)
            private_test_file = self.loader.get_private_test_file(task.task_id)

            pass_to_pass_res = self.executor.run_pytest_suite(
                repo_dir=repo_dir,
                suite_name="PASS_TO_PASS",
                test_target=existing_test_file,
                timeout_seconds=timeout_seconds,
            )

            fail_to_pass_res = self.executor.run_pytest_suite(
                repo_dir=repo_dir,
                suite_name="FAIL_TO_PASS",
                test_target=issue_test_file,
                timeout_seconds=timeout_seconds,
            )

            private_res = None
            if include_private_tests and private_test_file.exists():
                private_res = self.executor.run_pytest_suite(
                    repo_dir=repo_dir,
                    suite_name="PRIVATE",
                    test_target=private_test_file,
                    timeout_seconds=timeout_seconds,
                )

            # Determine overall execution status
            suites = [s for s in (pass_to_pass_res, fail_to_pass_res, private_res) if s is not None]
            overall_exec_status = ExecutionStatus.COMPLETED
            for s in suites:
                if s.execution_status != ExecutionStatus.COMPLETED:
                    overall_exec_status = s.execution_status
                    break

            p2p_ok = pass_to_pass_res.all_passed
            f2p_ok = fail_to_pass_res.all_passed
            priv_ok = private_res.all_passed if private_res is not None else True

            has_regression = not p2p_ok
            issue_fixed = f2p_ok and priv_ok and not validation.is_empty

            if overall_exec_status != ExecutionStatus.COMPLETED:
                resolution = ResolutionStatus.EXECUTION_FAILURE
                resolved = False
                classification = f"EXECUTION_{overall_exec_status.value}"
                explanation = f"Test execution failed with infrastructure/runtime status {overall_exec_status.value}."
            elif validation.is_empty:
                resolution = ResolutionStatus.NO_CHANGES
                resolved = False
                classification = "NO_OP_BASELINE_UNRESOLVED"
                explanation = (
                    f"Unmodified repository baseline: PASS_TO_PASS={pass_to_pass_res.passed_count}/{pass_to_pass_res.total_count}, "
                    f"FAIL_TO_PASS={fail_to_pass_res.passed_count}/{fail_to_pass_res.total_count}."
                )
            elif has_regression:
                resolution = ResolutionStatus.REGRESSION
                resolved = False
                classification = "REGRESSION_INTRODUCED"
                explanation = (
                    f"Patch broke existing functionality: {pass_to_pass_res.failed_count + pass_to_pass_res.error_count} "
                    f"PASS_TO_PASS preservation test(s) failed."
                )
            elif not f2p_ok:
                resolution = ResolutionStatus.UNRESOLVED
                resolved = False
                classification = "ISSUE_TESTS_STILL_FAILING"
                explanation = (
                    f"Issue not fully resolved: {fail_to_pass_res.passed_count}/{fail_to_pass_res.total_count} "
                    f"FAIL_TO_PASS issue test(s) passed."
                )
            elif not priv_ok and private_res is not None:
                resolution = ResolutionStatus.UNRESOLVED
                resolved = False
                classification = "PRIVATE_EVALUATION_TESTS_FAILED"
                explanation = (
                    f"Public issue tests passed, but {private_res.failed_count + private_res.error_count} "
                    f"private boundary/property test(s) failed ({private_res.passed_count}/{private_res.total_count} passed)."
                )
            else:
                resolution = ResolutionStatus.RESOLVED
                resolved = True
                classification = "RESOLVED_CLEANLY"
                priv_msg = (
                    f", PRIVATE={private_res.passed_count}/{private_res.total_count}"
                    if private_res is not None
                    else ""
                )
                explanation = (
                    f"Task resolved without regressions: FAIL_TO_PASS={fail_to_pass_res.passed_count}/{fail_to_pass_res.total_count}, "
                    f"PASS_TO_PASS={pass_to_pass_res.passed_count}/{pass_to_pass_res.total_count}{priv_msg}."
                )

            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            return TaskEvaluationResult(
                run_id=run_id,
                task_id=task.task_id,
                title=task.title,
                difficulty=task.difficulty,
                category=task.category,
                agent_id=agent_id,
                provider=provider,
                model=model,
                sandbox_mode=self.executor.effective_mode.value,
                base_revision=base_rev,
                test_suite_hash=task.test_suite_hash,
                patch_diff=patch_text,
                patch_validation=validation,
                pass_to_pass=pass_to_pass_res,
                fail_to_pass=fail_to_pass_res,
                private_tests=private_res,
                execution_status=overall_exec_status,
                resolution_status=resolution,
                resolved=resolved,
                issue_fixed=issue_fixed,
                has_regression=has_regression,
                private_passed=priv_ok,
                failure_classification=classification,
                explanation=explanation,
                duration_ms=round(elapsed_ms, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                started_at=started_at,
                completed_at=utc_now_iso(),
                agent_logs=agent_logs,
            )
