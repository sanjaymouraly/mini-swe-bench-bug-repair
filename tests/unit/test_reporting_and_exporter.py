"""Unit tests for MarkdownReportGenerator and ResultExporter."""

from __future__ import annotations

from pathlib import Path

from bugbench import OFFICIAL_DISCLAIMER
from bugbench.models import (
    EvaluationRunSummary,
    ExecutionStatus,
    PatchValidationResult,
    ResolutionStatus,
    SuiteExecutionResult,
    TaskCategory,
    TaskDifficulty,
    TaskEvaluationResult,
)
from bugbench.reporting.markdown_generator import MarkdownReportGenerator
from bugbench.storage.exporter import ResultExporter


def _sample_task() -> TaskEvaluationResult:
    return TaskEvaluationResult(
        run_id="run-test-001",
        task_id="pagiflow-001",
        title="Fix pagination",
        difficulty=TaskDifficulty.EASY,
        category=TaskCategory.PAGINATION_API,
        agent_id="reference-oracle",
        provider="offline",
        model="reference",
        sandbox_mode="subprocess",
        base_revision="164e51624d3e",
        test_suite_hash="hash123",
        patch_validation=PatchValidationResult(
            is_empty=False,
            applies_cleanly=True,
            integrity_passed=True,
            added_lines=10,
            removed_lines=2,
            patch_sha256="sha123",
        ),
        pass_to_pass=SuiteExecutionResult(suite_name="PASS_TO_PASS", passed_count=4, total_count=4),
        fail_to_pass=SuiteExecutionResult(suite_name="FAIL_TO_PASS", passed_count=3, total_count=3),
        private_tests=SuiteExecutionResult(suite_name="PRIVATE", passed_count=2, total_count=2),
        execution_status=ExecutionStatus.COMPLETED,
        resolution_status=ResolutionStatus.RESOLVED,
        resolved=True,
        issue_fixed=True,
        has_regression=False,
        private_passed=True,
        failure_classification="RESOLVED_CLEANLY",
        duration_ms=1200.0,
    )


def _sample_run() -> EvaluationRunSummary:
    return EvaluationRunSummary(
        run_id="run-test-001",
        run_name="Unit Test Run",
        agent_id="reference-oracle",
        provider="offline",
        model="reference",
        sandbox_mode="subprocess",
        status="COMPLETED",
        total_tasks=1,
        completed_tasks=1,
        resolved_count=1,
        resolved_rate=100.0,
        issue_fix_count=1,
        issue_fix_rate=100.0,
        task_results=[_sample_task()],
    )


def test_markdown_report_from_model(tmp_path: Path) -> None:
    md_path = MarkdownReportGenerator.write_run_report(_sample_run(), tmp_path / "report.md")
    md_text = md_path.read_text(encoding="utf-8")

    assert OFFICIAL_DISCLAIMER in md_text
    assert "`pagiflow-001`" in md_text
    assert "**1 / 1 (100.00%)**" in md_text
    # The per-task suite counts must come from the real model fields.
    assert "3/3" in md_text
    assert "4/4" in md_text
    assert "2/2" in md_text
    # An unmeasured cost must never be rendered as $0.00.
    assert "n/a (unmeasured)" in md_text


def test_markdown_report_from_model_dump() -> None:
    """The generator must also accept the dict form of the same run."""
    run = _sample_run()
    md_text = MarkdownReportGenerator.generate_run_report(run.model_dump())
    assert "`pagiflow-001`" in md_text
    assert "**1 / 1 (100.00%)**" in md_text


def test_markdown_report_shows_measured_cost() -> None:
    run = _sample_run()
    run.estimated_cost_usd = 0.123456
    run.total_tokens = 4242
    md_text = MarkdownReportGenerator.generate_run_report(run)
    assert "$0.123456" in md_text
    assert "4242" in md_text


def test_markdown_report_marks_regression() -> None:
    run = _sample_run()
    task = run.task_results[0]
    task.resolved = False
    task.issue_fixed = True
    task.has_regression = True
    task.resolution_status = ResolutionStatus.REGRESSION
    md_text = MarkdownReportGenerator.generate_run_report(run)
    assert "REGRESSION" in md_text


def test_exporter_writes_every_format(tmp_path: Path) -> None:
    run_model = _sample_run()

    json_path = ResultExporter.export_to_file(run_model, tmp_path / "run.json", fmt="json")
    jsonl_path = ResultExporter.export_to_file(run_model, tmp_path / "run.jsonl", fmt="jsonl")
    csv_path = ResultExporter.export_to_file(run_model, tmp_path / "run.csv", fmt="csv")
    md_path = ResultExporter.export_to_file(run_model, tmp_path / "run.md", fmt="md")

    assert json_path.exists()
    assert len(jsonl_path.read_text(encoding="utf-8").strip().splitlines()) == 2
    csv_lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(csv_lines) == 2
    assert "pagiflow-001" in csv_lines[1]
    assert "`pagiflow-001`" in md_path.read_text(encoding="utf-8")


def test_exporter_infers_format_from_extension(tmp_path: Path) -> None:
    run_model = _sample_run()
    md_path = ResultExporter.export_to_file(run_model, tmp_path / "inferred.md")
    assert md_path.read_text(encoding="utf-8").startswith("# Benchmark Evaluation Report")
