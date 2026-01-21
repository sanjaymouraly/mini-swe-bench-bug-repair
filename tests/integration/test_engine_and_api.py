"""Integration tests for GradingEngine, BenchmarkRunner, CLI, and FastAPI REST API."""

from __future__ import annotations

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from bugbench.api.app import create_app
from bugbench.cli.main import app as cli_app
from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.dataset.validator import DatasetValidator
from bugbench.grading.engine import GradingEngine
from bugbench.models import ResolutionStatus, SandboxMode
from bugbench.orchestrator.runner import BenchmarkRunner
from bugbench.storage.database import BenchmarkDatabase


def test_grading_engine_distinguishes_reference_noop_incomplete_and_regression(
    test_config: AppConfig, dataset_loader: DatasetLoader
) -> None:
    engine = GradingEngine(test_config, dataset_loader, sandbox_mode=SandboxMode.SUBPROCESS)
    task = dataset_loader.load_task("pagiflow-001")

    # 1. Reference patch -> RESOLVED
    ref_patch = dataset_loader.get_reference_patch("pagiflow-001")
    ref_res = engine.grade_patch(
        task=task,
        patch_text=ref_patch,
        run_id="int-test",
        agent_id="reference-oracle",
    )
    assert ref_res.resolved is True
    assert ref_res.resolution_status == ResolutionStatus.RESOLVED
    assert ref_res.failure_classification == "RESOLVED_CLEANLY"

    # 2. No-op patch -> NO_CHANGES
    noop_res = engine.grade_patch(
        task=task,
        patch_text="",
        run_id="int-test",
        agent_id="noop",
        run_tests_on_empty_patch=True,
    )
    assert noop_res.resolved is False
    assert noop_res.resolution_status == ResolutionStatus.NO_CHANGES
    assert noop_res.has_regression is False

    # 3. Incomplete patch -> UNRESOLVED
    inc_patch = dataset_loader.get_incomplete_patch("pagiflow-001")
    inc_res = engine.grade_patch(
        task=task,
        patch_text=inc_patch,
        run_id="int-test",
        agent_id="incomplete",
    )
    assert inc_res.resolved is False
    assert inc_res.resolution_status == ResolutionStatus.UNRESOLVED

    # 4. Regression patch -> REGRESSION
    reg_patch = dataset_loader.get_regression_patch("pagiflow-001")
    reg_res = engine.grade_patch(
        task=task,
        patch_text=reg_patch,
        run_id="int-test",
        agent_id="regression",
    )
    assert reg_res.resolved is False
    assert reg_res.has_regression is True
    assert reg_res.resolution_status == ResolutionStatus.REGRESSION


def test_dataset_validator_passes_all_8_gates_on_single_task(
    test_config: AppConfig, dataset_loader: DatasetLoader
) -> None:
    validator = DatasetValidator(test_config, sandbox_mode=SandboxMode.SUBPROCESS)
    task = dataset_loader.load_task("confighier-007")
    report = validator.validate_task(task, repeat_runs=2)
    assert report.passed is True
    assert len(report.checks) == 8
    assert all(c.passed for c in report.checks)


def test_runner_and_fastapi_endpoints(
    test_config: AppConfig,
    dataset_loader: DatasetLoader,
    test_db: BenchmarkDatabase,
) -> None:
    runner = BenchmarkRunner(test_config, test_db, dataset_loader)
    summary = runner.run_suite(
        provider="reference",
        run_name="Integration Reference Run",
        task_ids=["confighier-007"],
        sandbox_mode=SandboxMode.SUBPROCESS,
        max_workers=1,
    )
    assert summary.resolved_count == 1
    assert summary.resolved_rate == 100.0

    noop_summary = runner.run_suite(
        provider="noop",
        run_name="Integration NoOp Run",
        task_ids=["confighier-007"],
        sandbox_mode=SandboxMode.SUBPROCESS,
        max_workers=1,
    )
    assert noop_summary.resolved_count == 0

    app = create_app(test_config)
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    overview = client.get("/api/overview")
    assert overview.status_code == 200
    assert overview.json()["total_tasks"] == 12

    tasks_resp = client.get("/api/tasks?difficulty=easy")
    assert tasks_resp.status_code == 200
    assert len(tasks_resp.json()["tasks"]) == 4

    task_detail = client.get("/api/tasks/pagiflow-001")
    assert task_detail.status_code == 200
    assert "source_files" in task_detail.json()
    assert "reference_patch" not in task_detail.json()

    runs_resp = client.get("/api/runs")
    assert runs_resp.status_code == 200
    assert len(runs_resp.json()["runs"]) == 2

    run_detail = client.get(f"/api/runs/{summary.run_id}")
    assert run_detail.status_code == 200
    assert run_detail.json()["resolved_count"] == 1

    cmp_resp = client.get(f"/api/compare?run_ids={summary.run_id},{noop_summary.run_id}")
    assert cmp_resp.status_code == 200
    assert len(cmp_resp.json()["task_matrix"]) == 1


def test_cli_list_and_inspect() -> None:
    cli_runner = CliRunner()
    res_list = cli_runner.invoke(cli_app, ["list"])
    assert res_list.exit_code == 0
    assert "pagiflow-001" in res_list.stdout

    res_inspect = cli_runner.invoke(cli_app, ["inspect", "pagiflow-001"])
    assert res_inspect.exit_code == 0
    assert "pagiflow-001" in res_inspect.stdout
