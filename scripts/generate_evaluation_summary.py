#!/usr/bin/env python3
"""Generate the combined `artifacts/reports/EVALUATION_SUMMARY.md` from recorded runs.

Every number in the generated file comes from a run that is actually stored in
the local SQLite database. Nothing is synthesised, and no run is invented.

Usage:
    python scripts/generate_evaluation_summary.py
    python scripts/generate_evaluation_summary.py --run <run_id> ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bugbench import OFFICIAL_DISCLAIMER, __version__  # noqa: E402
from bugbench.config import AppConfig  # noqa: E402
from bugbench.models import EvaluationRunSummary  # noqa: E402
from bugbench.reporting.markdown_generator import MarkdownReportGenerator  # noqa: E402
from bugbench.storage.database import BenchmarkDatabase  # noqa: E402

# Preferred order for the summary. Runs are matched by name (and optionally by
# sandbox backend) so the script is stable across re-runs.
#   (label, name substring, sandbox or None for "any")
SECTION_ORDER = [
    ("Reference Oracle (Docker)", "reference", "docker"),
    ("Reference Oracle (Subprocess)", "reference", "subprocess"),
    ("No-Op Baseline (Docker)", "noop", "docker"),
    ("No-Op Baseline (Subprocess)", "noop", "subprocess"),
    ("Incomplete Patch Baseline", "incomplete", None),
    ("Regression-Inducing Baseline", "regression", None),
    ("Live Agent Suite", "live agent suite", None),
    ("Live Agent Retry (provider outage)", "retry of gateway-failed", None),
]


def _pick_run(
    runs: list[EvaluationRunSummary], needle: str, sandbox: str | None = None
) -> EvaluationRunSummary | None:
    """Return the most recent run whose name contains ``needle``."""
    matches = [
        r
        for r in runs
        if needle.lower() in (r.run_name or "").lower()
        and (sandbox is None or (r.sandbox_mode or "").lower() == sandbox.lower())
    ]
    if not matches:
        return None
    return max(matches, key=lambda r: r.created_at or "")


def build_summary(runs: list[EvaluationRunSummary]) -> str:
    lines = [
        "# Mini SWE-Bench — Reproducible Evaluation Summary",
        "",
        f"> **Disclaimer:** {OFFICIAL_DISCLAIMER}",
        "",
        f"Benchmark version `{__version__}`. "
        "Every row below is a run recorded in the local SQLite database "
        "(`artifacts/bugbench.db`) and can be reproduced with the command shown.",
        "",
        "## Results at a glance",
        "",
        "| Run | Adapter / Model | Sandbox | Resolved | Issue fixed | Regression-free | Patch valid | Tokens | Est. cost |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | ---: | ---: |",
    ]

    selected: list[tuple[str, EvaluationRunSummary]] = []
    for label, needle, sandbox in SECTION_ORDER:
        run = _pick_run(runs, needle, sandbox)
        if run is not None:
            selected.append((label, run))

    for label, run in selected:
        tokens = str(run.total_tokens) if run.total_tokens is not None else "n/a"
        cost = f"${run.estimated_cost_usd:.4f}" if run.estimated_cost_usd is not None else "n/a"
        lines.append(
            f"| {label} | `{run.agent_id}` | `{run.sandbox_mode}` | "
            f"**{run.resolved_count}/{run.total_tasks} ({run.resolved_rate}%)** | "
            f"{run.issue_fix_count}/{run.total_tasks} ({run.issue_fix_rate}%) | "
            f"{run.regression_free_rate}% ({run.regression_count} reg) | "
            f"{run.patch_valid_rate}% | {tokens} | {cost} |"
        )

    lines.append("")
    lines.append("## What each baseline proves")
    lines.append("")
    lines.append(
        "- **Reference Oracle** — the verified fix resolves every task with no "
        "regressions. If this is not 100%, the dataset is broken."
    )
    lines.append(
        "- **No-Op Baseline** — the unmodified buggy revision resolves nothing. "
        "This proves the issue tests genuinely fail before repair."
    )
    lines.append(
        "- **Incomplete Patch Baseline** — a partial fix that misses a boundary "
        "case is rejected, so the private evaluation suite is doing its job."
    )
    lines.append(
        "- **Regression-Inducing Baseline** — a fix that breaks existing "
        "behaviour is caught and classified as `REGRESSION`, never as resolved."
    )
    lines.append(
        "- **Live Agent Suite** — a real model given only the repository and the "
        "issue report. Its patches are graded by exactly the same pipeline."
    )
    lines.append("")

    for _label, run in selected:
        lines.append("---")
        lines.append("")
        lines.append(MarkdownReportGenerator.generate_run_report(run))

    lines.append("---")
    lines.append("")
    lines.append("## Reproducing these numbers")
    lines.append("")
    lines.append("```bash")
    lines.append("# Every baseline is fully offline and needs no API key.")
    lines.append("bugbench validate --sandbox docker")
    lines.append("bugbench reference --sandbox docker --workers 4")
    lines.append("bugbench baseline --mode noop --sandbox docker --workers 4")
    lines.append("bugbench baseline --mode incomplete --sandbox docker --workers 4")
    lines.append("bugbench baseline --mode regression --sandbox docker --workers 4")
    lines.append("")
    lines.append("# Agent mode needs a provider; the model is auto-discovered if omitted.")
    lines.append("bugbench run-agent --provider custom_openai --sandbox docker --workers 3")
    lines.append("```")
    lines.append("")
    lines.append(
        "> A passing test suite is evidence for the behaviours it covers, not proof "
        "of universal correctness. These 12 tasks are a practice benchmark, not a "
        "complete specification of any real system."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None, help="Output markdown path")
    parser.add_argument("--run", action="append", default=None, help="Include a specific run_id")
    args = parser.parse_args()

    cfg = AppConfig.from_env()
    db = BenchmarkDatabase(config=cfg)

    if args.run:
        runs = []
        for run_id in args.run:
            run = db.get_run(run_id)
            if run is None:
                print(f"Run not found: {run_id}", file=sys.stderr)
                return 2
            runs.append(run)
    else:
        runs, _ = db.list_runs(limit=100, include_task_results=True)

    if not runs:
        print("No recorded runs found. Run `bugbench reference` first.", file=sys.stderr)
        return 1

    out = args.output or (cfg.artifacts_dir / "reports" / "EVALUATION_SUMMARY.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_summary(runs), encoding="utf-8")
    print(f"Wrote evaluation summary to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
