"""Full benchmark lifecycle runner with parallelism, retries, cancellation, and persistence."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bugbench import __version__
from bugbench.agents.base import AgentAdapter
from bugbench.agents.registry import AgentRegistry
from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.grading.engine import GradingEngine
from bugbench.logging_utils import get_logger, redact_secrets
from bugbench.models import (
    BenchmarkTask,
    CategoryMetric,
    DifficultyMetric,
    EvaluationRunSummary,
    ExecutionStatus,
    ResolutionStatus,
    SandboxMode,
    TaskEvaluationResult,
    utc_now_iso,
)
from bugbench.sandbox.workspace import EphemeralWorkspace
from bugbench.storage.database import BenchmarkDatabase
from bugbench.storage.exporter import ResultExporter

logger = get_logger("bugbench.orchestrator")

# Active cancellation events keyed by run_id
_ACTIVE_CANCEL_EVENTS: dict[str, threading.Event] = {}
_CANCEL_LOCK = threading.Lock()


def request_run_cancellation(run_id: str) -> bool:
    """Signal an in-progress run to cancel before executing remaining tasks."""
    with _CANCEL_LOCK:
        ev = _ACTIVE_CANCEL_EVENTS.get(run_id)
        if ev is not None:
            ev.set()
            return True
    return False


class BenchmarkRunner:
    """Orchestrates end-to-end task loading, workspace isolation, agent execution, grading, and storage."""

    def __init__(
        self,
        config: AppConfig | None = None,
        db: BenchmarkDatabase | None = None,
        loader: DatasetLoader | None = None,
    ) -> None:
        self.config = config or AppConfig.from_env()
        self.db = db or BenchmarkDatabase(config=self.config)
        self.loader = loader or DatasetLoader(self.config)
        self.registry = AgentRegistry(self.config)

    @staticmethod
    def compute_aggregates(run: EvaluationRunSummary) -> EvaluationRunSummary:
        """Recompute run-level metrics, category breakdown, and difficulty breakdown from task_results."""
        results = sorted(run.task_results, key=lambda r: r.task_id)
        run.task_results = results
        completed = len(results)
        run.completed_tasks = completed
        denom = max(1, run.total_tasks if run.status == "COMPLETED" else completed)

        resolved_cnt = sum(1 for r in results if r.resolved)
        issue_fix_cnt = sum(1 for r in results if r.issue_fixed)
        reg_cnt = sum(1 for r in results if r.has_regression)
        reg_free_cnt = sum(1 for r in results if not r.has_regression)
        valid_cnt = sum(1 for r in results if r.patch_validation.applies_cleanly)
        integrity_viol_cnt = sum(
            1 for r in results if r.resolution_status == ResolutionStatus.INTEGRITY_VIOLATION
        )
        exec_fail_cnt = sum(1 for r in results if r.execution_status != ExecutionStatus.COMPLETED)

        run.resolved_count = resolved_cnt
        run.resolved_rate = round((resolved_cnt / denom) * 100.0, 2) if completed else 0.0
        run.issue_fix_count = issue_fix_cnt
        run.issue_fix_rate = round((issue_fix_cnt / denom) * 100.0, 2) if completed else 0.0
        run.regression_count = reg_cnt
        run.regression_free_count = reg_free_cnt
        run.regression_free_rate = round((reg_free_cnt / denom) * 100.0, 2) if completed else 0.0
        run.patch_valid_count = valid_cnt
        run.patch_valid_rate = round((valid_cnt / denom) * 100.0, 2) if completed else 0.0
        run.integrity_violation_count = integrity_viol_cnt
        run.execution_failure_count = exec_fail_cnt

        # Token and cost totals (only when reported)
        tok_values = [r.total_tokens for r in results if r.total_tokens is not None]
        run.total_tokens = sum(tok_values) if tok_values else None
        cost_values = [r.estimated_cost_usd for r in results if r.estimated_cost_usd is not None]
        run.estimated_cost_usd = round(sum(cost_values), 6) if cost_values else None

        # Category breakdown
        cat_map: dict[str, list[TaskEvaluationResult]] = {}
        diff_map: dict[str, list[TaskEvaluationResult]] = {}
        for r in results:
            cat_map.setdefault(r.category.value, []).append(r)
            diff_map.setdefault(r.difficulty.value, []).append(r)

        run.category_breakdown = [
            CategoryMetric(
                category=cat,
                total=len(items),
                resolved=sum(1 for i in items if i.resolved),
                issue_fixed=sum(1 for i in items if i.issue_fixed),
                regressions=sum(1 for i in items if i.has_regression),
                resolved_rate=round((sum(1 for i in items if i.resolved) / len(items)) * 100.0, 2),
            )
            for cat, items in sorted(cat_map.items())
        ]

        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
        run.difficulty_breakdown = [
            DifficultyMetric(
                difficulty=diff,
                total=len(items),
                resolved=sum(1 for i in items if i.resolved),
                issue_fixed=sum(1 for i in items if i.issue_fixed),
                regressions=sum(1 for i in items if i.has_regression),
                resolved_rate=round((sum(1 for i in items if i.resolved) / len(items)) * 100.0, 2),
            )
            for diff, items in sorted(
                diff_map.items(), key=lambda kv: difficulty_order.get(kv[0], 99)
            )
        ]
        return run

    def execute_single_task(
        self,
        task: BenchmarkTask,
        adapter: AgentAdapter,
        run_id: str,
        sandbox_mode: SandboxMode | None = None,
        include_private_tests: bool = True,
        run_tests_on_empty_patch: bool = False,
        timeout_seconds: int | None = None,
        infra_retries: int = 1,
    ) -> TaskEvaluationResult:
        """Run the complete isolated lifecycle for a single benchmark task."""
        grader = GradingEngine(
            config=self.config,
            loader=self.loader,
            sandbox_mode=sandbox_mode,
        )

        last_result: TaskEvaluationResult | None = None
        for attempt in range(max(1, infra_retries + 1)):
            try:
                # Step 1: Create isolated Agent Workspace containing ONLY repo/ and ISSUE.md
                with EphemeralWorkspace(
                    task=task, purpose="agent", include_issue_file=True
                ) as agent_ws:
                    assert agent_ws.repo_dir is not None
                    agent_out = adapter.generate_patch(task, agent_ws.repo_dir)
                    patch_diff = agent_out.patch_diff
                    if not patch_diff.strip():
                        # Check if agent modified files directly in workspace without returning diff string
                        patch_diff = agent_ws.collect_git_diff()

                # Step 2: Grade the collected patch in a fresh clean Grading Workspace
                res = grader.grade_patch(
                    task=task,
                    patch_text=patch_diff,
                    run_id=run_id,
                    agent_id=adapter.agent_id,
                    provider=adapter.provider,
                    model=agent_out.model_used or adapter.model,
                    include_private_tests=include_private_tests,
                    run_tests_on_empty_patch=run_tests_on_empty_patch,
                    timeout_seconds=timeout_seconds,
                    agent_logs=agent_out.logs,
                    prompt_tokens=agent_out.prompt_tokens,
                    completion_tokens=agent_out.completion_tokens,
                    total_tokens=agent_out.total_tokens,
                    estimated_cost_usd=agent_out.estimated_cost_usd,
                )
                last_result = res
                if res.execution_status != ExecutionStatus.ENV_ERROR or attempt >= infra_retries:
                    return res
                logger.warning(
                    "Infrastructure ENV_ERROR on %s (attempt %d/%d); retrying...",
                    task.task_id,
                    attempt + 1,
                    infra_retries + 1,
                )
            except Exception as exc:
                err_msg = redact_secrets(str(exc))
                last_result = TaskEvaluationResult(
                    run_id=run_id,
                    task_id=task.task_id,
                    title=task.title,
                    difficulty=task.difficulty,
                    category=task.category,
                    agent_id=adapter.agent_id,
                    provider=adapter.provider,
                    model=adapter.model,
                    sandbox_mode=(sandbox_mode or self.config.resolve_effective_sandbox()).value,
                    base_revision=task.base_revision,
                    test_suite_hash=task.test_suite_hash,
                    execution_status=ExecutionStatus.ENV_ERROR,
                    resolution_status=ResolutionStatus.EXECUTION_FAILURE,
                    resolved=False,
                    failure_classification="AGENT_OR_INFRA_ERROR",
                    explanation=f"Agent execution failed: {err_msg}",
                    agent_logs=err_msg,
                )
                if attempt >= infra_retries:
                    return last_result

        assert last_result is not None
        return last_result

    def run_suite(
        self,
        provider: str = "reference",
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        patch_path: Path | None = None,
        patch_text: str | None = None,
        task_ids: list[str] | None = None,
        difficulty: str | None = None,
        category: str | None = None,
        run_name: str | None = None,
        run_id: str | None = None,
        max_workers: int = 1,
        sandbox_mode: SandboxMode | None = None,
        include_private_tests: bool = True,
        timeout_seconds: int | None = None,
        infra_retries: int = 1,
        save_artifacts: bool = True,
    ) -> EvaluationRunSummary:
        """Execute a benchmark suite across selected tasks and persist results."""
        start_t = time.perf_counter()
        tasks = self.loader.load_all_tasks(
            difficulty=difficulty,
            category=category,
            task_ids=task_ids,
            ensure_git=True,
        )
        if not tasks:
            raise ValueError("No benchmark tasks matched the provided filter criteria.")

        adapter = self.registry.create_adapter(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            patch_path=patch_path,
            patch_text=patch_text,
        )

        rid = run_id or f"run-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        effective_sb = (sandbox_mode or self.config.resolve_effective_sandbox()).value
        rname = run_name or f"{adapter.agent_id} ({len(tasks)} tasks)"

        run_summary = EvaluationRunSummary(
            run_id=rid,
            run_name=rname,
            benchmark_version=__version__,
            agent_id=adapter.agent_id,
            provider=adapter.provider,
            model=adapter.model,
            sandbox_mode=effective_sb,
            status="RUNNING",
            created_at=utc_now_iso(),
            total_tasks=len(tasks),
            config_snapshot=self.config.sanitized_summary(),
        )
        self.db.save_run(run_summary)
        self.db.append_run_log(
            rid,
            f"Started run '{rname}' (agent={adapter.agent_id}, sandbox={effective_sb}, tasks={len(tasks)})",
        )

        cancel_event = threading.Event()
        with _CANCEL_LOCK:
            _ACTIVE_CANCEL_EVENTS[rid] = cancel_event

        run_tests_on_empty = provider.lower() in ("noop", "noop-baseline")
        results_lock = threading.Lock()
        # Cost budget: stop the run once the accumulated (accurately priced)
        # spend exceeds the configured cap. Only enforced when a cost is known.
        budget_usd = self.config.get_provider_config(provider).max_cost_usd
        budget_exceeded = threading.Event()

        def _worker(t: BenchmarkTask) -> TaskEvaluationResult | None:
            if cancel_event.is_set() or budget_exceeded.is_set():
                return None
            self.db.append_run_log(rid, f"[{t.task_id}] Starting evaluation ({t.title})...")
            res = self.execute_single_task(
                task=t,
                adapter=adapter,
                run_id=rid,
                sandbox_mode=sandbox_mode,
                include_private_tests=include_private_tests,
                run_tests_on_empty_patch=run_tests_on_empty,
                timeout_seconds=timeout_seconds,
                infra_retries=infra_retries,
            )
            with results_lock:
                run_summary.task_results.append(res)
                self.compute_aggregates(run_summary)
                self.db.save_run(run_summary)
            self.db.append_run_log(
                rid,
                f"[{t.task_id}] Completed -> {res.resolution_status.value} ({res.duration_ms:.0f}ms) | {res.explanation}",
            )
            # Enforce the run cost budget across priced tasks only.
            if (
                budget_usd
                and budget_usd > 0
                and run_summary.estimated_cost_usd is not None
                and run_summary.estimated_cost_usd >= budget_usd
            ):
                budget_exceeded.set()
                cancel_event.set()
                self.db.append_run_log(
                    rid,
                    f"Cost budget reached: ${run_summary.estimated_cost_usd:.4f} >= "
                    f"${budget_usd:.4f}. Stopping remaining tasks.",
                    level="WARNING",
                )
            return res

        try:
            if max_workers <= 1 or len(tasks) == 1:
                for t in tasks:
                    if cancel_event.is_set():
                        break
                    _worker(t)
            else:
                with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as pool:
                    futures = [pool.submit(_worker, t) for t in tasks]
                    for fut in as_completed(futures):
                        fut.result()

            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            run_summary.total_duration_ms = round(elapsed_ms, 2)
            run_summary.completed_at = utc_now_iso()
            if budget_exceeded.is_set():
                run_summary.status = "STOPPED_BUDGET"
            elif cancel_event.is_set():
                run_summary.status = "CANCELLED"
            else:
                run_summary.status = "COMPLETED"
            self.compute_aggregates(run_summary)
            self.db.save_run(run_summary)
            self.db.append_run_log(
                rid,
                f"Run {run_summary.status}: Resolved {run_summary.resolved_count}/{run_summary.total_tasks} "
                f"({run_summary.resolved_rate}%), Regressions: {run_summary.regression_count}, "
                f"Duration: {run_summary.total_duration_ms:.0f}ms.",
            )

            if save_artifacts:
                reports_dir = self.config.artifacts_dir / "reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                ResultExporter.export_to_file(run_summary, reports_dir / f"{rid}.json", fmt="json")
        finally:
            with _CANCEL_LOCK:
                _ACTIVE_CANCEL_EVENTS.pop(rid, None)

        return run_summary
