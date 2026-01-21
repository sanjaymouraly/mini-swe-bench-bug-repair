"""Markdown report generation for evaluation runs and dataset validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bugbench import OFFICIAL_DISCLAIMER
from bugbench.models import EvaluationRunSummary, TaskEvaluationResult


def _suite_counts(suite: Any) -> tuple[int, int]:
    """Return (passed, total) for a suite result, tolerating dicts and models."""
    if suite is None:
        return (0, 0)
    if isinstance(suite, dict):
        return (int(suite.get("passed_count", 0)), int(suite.get("total_count", 0)))
    return (int(getattr(suite, "passed_count", 0)), int(getattr(suite, "total_count", 0)))


class MarkdownReportGenerator:
    """Generates reproducible Markdown evaluation reports."""

    @staticmethod
    def _normalise(run_data: EvaluationRunSummary | dict[str, Any]) -> dict[str, Any]:
        """Accept either an ``EvaluationRunSummary`` or its ``model_dump()``."""
        if isinstance(run_data, EvaluationRunSummary):
            return run_data.model_dump()
        return run_data

    @staticmethod
    def generate_run_report(run_data: EvaluationRunSummary | dict[str, Any]) -> str:
        """Render a Markdown report for one evaluation run."""
        data = MarkdownReportGenerator._normalise(run_data)

        results: list[dict[str, Any]] = list(data.get("task_results") or [])
        total_tasks = int(data.get("total_tasks", 0))
        total_tokens = data.get("total_tokens")
        cost = data.get("estimated_cost_usd")
        cost_cell = f"${float(cost):.6f}" if cost is not None else "n/a (unmeasured)"
        tokens_cell = str(total_tokens) if total_tokens is not None else "n/a"

        lines = [
            f"# Benchmark Evaluation Report: {data.get('run_name', 'Run')}",
            "",
            f"> **Disclaimer:** {OFFICIAL_DISCLAIMER}",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| **Run ID** | `{data.get('run_id')}` |",
            f"| **Agent / Adapter** | `{data.get('agent_id')}` "
            f"(`{data.get('provider')}` / `{data.get('model')}`) |",
            f"| **Sandbox Mode** | `{data.get('sandbox_mode')}` |",
            f"| **Status** | `{data.get('status')}` |",
            f"| **Resolved Tasks** | **{data.get('resolved_count', 0)} / {total_tasks} "
            f"({float(data.get('resolved_rate', 0.0)):.2f}%)** |",
            f"| **Issue-Fix Rate** | {data.get('issue_fix_count', 0)} / {total_tasks} "
            f"({float(data.get('issue_fix_rate', 0.0)):.2f}%) |",
            f"| **Regression-Free Rate** | {float(data.get('regression_free_rate', 0.0)):.2f}% "
            f"({data.get('regression_count', 0)} regressions) |",
            f"| **Patch Applicability** | {float(data.get('patch_valid_rate', 0.0)):.2f}% |",
            f"| **Integrity Violations** | {data.get('integrity_violation_count', 0)} |",
            f"| **Execution Failures** | {data.get('execution_failure_count', 0)} |",
            f"| **Total Duration** | {float(data.get('total_duration_ms', 0.0)):.1f} ms |",
            f"| **Total Tokens** | {tokens_cell} |",
            f"| **Estimated Cost** | {cost_cell} |",
            "",
            "## Per-Task Breakdown",
            "",
            "| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS "
            "| Private | Regression | Time (ms) |",
            "| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |",
        ]

        for r in results:
            ftp_passed, ftp_total = _suite_counts(r.get("fail_to_pass"))
            ptp_passed, ptp_total = _suite_counts(r.get("pass_to_pass"))
            prv_passed, prv_total = _suite_counts(r.get("private_tests"))
            reg_str = "YES" if r.get("has_regression") else "NO"
            lines.append(
                f"| `{r.get('task_id')}` | {r.get('difficulty')} | `{r.get('category')}` | "
                f"**{r.get('resolution_status')}** | {ftp_passed}/{ftp_total} | "
                f"{ptp_passed}/{ptp_total} | {prv_passed}/{prv_total} | "
                f"{reg_str} | {float(r.get('duration_ms', 0.0)):.0f} |"
            )

        lines.append("")
        lines.append("## Notes")
        lines.append("")
        lines.append(
            "- `Resolved` requires the issue tests to pass, every preservation test to "
            "remain green, the private evaluation suite to pass, and the patch to be "
            "applicable and integrity-clean."
        )
        lines.append(
            "- A passing test suite is evidence for the behaviours it covers, not proof "
            "of universal correctness. These 12 tasks are a practice benchmark, not a "
            "complete specification of any real system."
        )
        if cost is None:
            lines.append(
                "- No cost is reported because the provider did not return a usable "
                "price alongside real token usage. Unmeasured is not the same as free."
            )
        lines.append("")
        return "\n".join(lines)

    @classmethod
    def write_run_report(
        cls, run_data: EvaluationRunSummary | dict[str, Any], output_path: Path
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = cls.generate_run_report(run_data)
        output_path.write_text(content, encoding="utf-8")
        return output_path

    @staticmethod
    def generate_task_breakdown(results: list[TaskEvaluationResult]) -> str:
        """Render a compact per-task table for a list of task results."""
        lines = [
            "| Task ID | Status | Resolved | Issue Fixed | Regression |",
            "| :--- | :--- | :---: | :---: | :---: |",
        ]
        for tr in results:
            lines.append(
                f"| `{tr.task_id}` | {tr.resolution_status.value} | "
                f"{'YES' if tr.resolved else 'no'} | "
                f"{'YES' if tr.issue_fixed else 'no'} | "
                f"{'YES' if tr.has_regression else 'no'} |"
            )
        lines.append("")
        return "\n".join(lines)
