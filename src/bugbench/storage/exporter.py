"""Export evaluation runs and comparisons to JSON, JSONL, CSV, and Markdown."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from bugbench.models import EvaluationRunSummary


class ResultExporter:
    """Formats and writes `EvaluationRunSummary` artifacts to JSON, JSONL, CSV, or Markdown."""

    @staticmethod
    def to_json(run: EvaluationRunSummary, indent: int = 2) -> str:
        return json.dumps(run.model_dump(), indent=indent)

    @staticmethod
    def to_jsonl(run: EvaluationRunSummary) -> str:
        lines: list[str] = []
        header = run.model_dump(exclude={"task_results"})
        header["record_type"] = "run_summary"
        lines.append(json.dumps(header))
        for tr in run.task_results:
            row = tr.model_dump()
            row["record_type"] = "task_evaluation"
            lines.append(json.dumps(row))
        return "\n".join(lines) + "\n"

    @staticmethod
    def to_csv(run: EvaluationRunSummary) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "run_id",
                "task_id",
                "title",
                "difficulty",
                "category",
                "agent_id",
                "provider",
                "model",
                "sandbox_mode",
                "resolved",
                "issue_fixed",
                "has_regression",
                "private_passed",
                "resolution_status",
                "failure_classification",
                "pass_to_pass_passed",
                "pass_to_pass_total",
                "fail_to_pass_passed",
                "fail_to_pass_total",
                "private_passed_count",
                "private_total_count",
                "patch_applies_cleanly",
                "patch_integrity_passed",
                "added_lines",
                "removed_lines",
                "duration_ms",
                "total_tokens",
                "estimated_cost_usd",
                "base_revision",
                "patch_sha256",
            ]
        )
        for tr in run.task_results:
            p2p_pass = tr.pass_to_pass.passed_count if tr.pass_to_pass else 0
            p2p_tot = tr.pass_to_pass.total_count if tr.pass_to_pass else 0
            f2p_pass = tr.fail_to_pass.passed_count if tr.fail_to_pass else 0
            f2p_tot = tr.fail_to_pass.total_count if tr.fail_to_pass else 0
            priv_pass = tr.private_tests.passed_count if tr.private_tests else 0
            priv_tot = tr.private_tests.total_count if tr.private_tests else 0
            writer.writerow(
                [
                    tr.run_id,
                    tr.task_id,
                    tr.title,
                    tr.difficulty.value,
                    tr.category.value,
                    tr.agent_id,
                    tr.provider,
                    tr.model,
                    tr.sandbox_mode,
                    tr.resolved,
                    tr.issue_fixed,
                    tr.has_regression,
                    tr.private_passed,
                    tr.resolution_status.value,
                    tr.failure_classification,
                    p2p_pass,
                    p2p_tot,
                    f2p_pass,
                    f2p_tot,
                    priv_pass,
                    priv_tot,
                    tr.patch_validation.applies_cleanly,
                    tr.patch_validation.integrity_passed,
                    tr.patch_validation.added_lines,
                    tr.patch_validation.removed_lines,
                    tr.duration_ms,
                    tr.total_tokens if tr.total_tokens is not None else "",
                    tr.estimated_cost_usd if tr.estimated_cost_usd is not None else "",
                    tr.base_revision,
                    tr.patch_validation.patch_sha256,
                ]
            )
        return buf.getvalue()

    @staticmethod
    def to_markdown(run: EvaluationRunSummary) -> str:
        """Render the run as a human-readable Markdown report."""
        from bugbench.reporting.markdown_generator import MarkdownReportGenerator

        return MarkdownReportGenerator.generate_run_report(run)

    @staticmethod
    def export_to_file(
        run: EvaluationRunSummary, output_path: Path, fmt: str | None = None
    ) -> Path:
        resolved = output_path.resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        ext = (fmt or resolved.suffix.lstrip(".")).lower()
        if ext == "jsonl":
            content = ResultExporter.to_jsonl(run)
        elif ext == "csv":
            content = ResultExporter.to_csv(run)
        elif ext in ("md", "markdown"):
            content = ResultExporter.to_markdown(run)
        else:
            content = ResultExporter.to_json(run)
        resolved.write_text(content, encoding="utf-8")
        return resolved
