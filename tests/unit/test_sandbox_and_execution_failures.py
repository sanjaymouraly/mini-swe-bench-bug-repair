"""Unit tests for SandboxExecutor timeouts, crashes, retries, and run cancellation."""

from __future__ import annotations

from pathlib import Path

from bugbench.agents.base import AgentAdapter, AgentOutput
from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.models import (
    BenchmarkTask,
    ExecutionStatus,
    ResolutionStatus,
    SandboxMode,
)
from bugbench.orchestrator.runner import BenchmarkRunner, request_run_cancellation
from bugbench.sandbox.executor import SandboxExecutor
from bugbench.sandbox.workspace import EphemeralWorkspace
from bugbench.storage.database import BenchmarkDatabase


def test_sandbox_executor_enforces_timeout(
    test_config: AppConfig, dataset_loader: DatasetLoader, tmp_path: Path
) -> None:
    task = dataset_loader.load_task("pagiflow-001")
    executor = SandboxExecutor(test_config, mode_override=SandboxMode.SUBPROCESS)

    with EphemeralWorkspace(task, base_temp_dir=tmp_path) as ws:
        assert ws.repo_dir is not None
        slow_test = tmp_path / "test_hang.py"
        slow_test.write_text(
            "import time\ndef test_hang_forever():\n    time.sleep(10)\n",
            encoding="utf-8",
        )
        res = executor.run_pytest_suite(
            repo_dir=ws.repo_dir,
            suite_name="FAIL_TO_PASS",
            test_target=slow_test,
            timeout_seconds=1,
        )
        assert res.execution_status == ExecutionStatus.TIMEOUT
        assert res.all_passed is False


class FlakyFirstAttemptAdapter(AgentAdapter):
    """Fails on attempt 1 with a transient RuntimeError, then returns reference patch on attempt 2."""

    agent_id = "flaky-adapter"
    provider = "custom"
    model = "flaky-v1"

    def __init__(self, ref_patch: str) -> None:
        self.ref_patch = ref_patch
        self.attempts = 0

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("Transient network socket reset")
        return AgentOutput(patch_diff=self.ref_patch, logs="Recovered on attempt 2")


def test_orchestrator_retries_transient_infra_failure_and_resolves(
    test_config: AppConfig,
    dataset_loader: DatasetLoader,
    test_db: BenchmarkDatabase,
) -> None:
    runner = BenchmarkRunner(test_config, test_db, dataset_loader)
    task = dataset_loader.load_task("confighier-007")
    ref_patch = dataset_loader.get_reference_patch("confighier-007")
    flaky_adapter = FlakyFirstAttemptAdapter(ref_patch)

    result = runner.execute_single_task(
        task=task,
        adapter=flaky_adapter,
        run_id="run-retry-test",
        sandbox_mode=SandboxMode.SUBPROCESS,
        infra_retries=1,
    )
    assert flaky_adapter.attempts == 2
    assert result.resolved is True
    assert result.resolution_status == ResolutionStatus.RESOLVED


def test_request_run_cancellation_returns_false_for_unknown_run() -> None:
    assert request_run_cancellation("nonexistent-run-id") is False
