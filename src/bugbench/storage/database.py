"""SQLite storage backend with WAL concurrency and PostgreSQL migration readiness."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from bugbench.config import AppConfig
from bugbench.models import (
    DatasetValidationSummary,
    EvaluationRunSummary,
    TaskEvaluationResult,
    utc_now_iso,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id TEXT PRIMARY KEY,
    run_name TEXT NOT NULL,
    benchmark_version TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    sandbox_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    total_tasks INTEGER NOT NULL DEFAULT 0,
    completed_tasks INTEGER NOT NULL DEFAULT 0,
    resolved_count INTEGER NOT NULL DEFAULT 0,
    resolved_rate REAL NOT NULL DEFAULT 0.0,
    issue_fix_count INTEGER NOT NULL DEFAULT 0,
    issue_fix_rate REAL NOT NULL DEFAULT 0.0,
    regression_count INTEGER NOT NULL DEFAULT 0,
    regression_free_count INTEGER NOT NULL DEFAULT 0,
    regression_free_rate REAL NOT NULL DEFAULT 0.0,
    patch_valid_count INTEGER NOT NULL DEFAULT 0,
    patch_valid_rate REAL NOT NULL DEFAULT 0.0,
    integrity_violation_count INTEGER NOT NULL DEFAULT 0,
    execution_failure_count INTEGER NOT NULL DEFAULT 0,
    total_duration_ms REAL NOT NULL DEFAULT 0.0,
    total_tokens INTEGER,
    estimated_cost_usd REAL,
    is_demo INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    category TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    issue_fixed INTEGER NOT NULL DEFAULT 0,
    has_regression INTEGER NOT NULL DEFAULT 0,
    resolution_status TEXT NOT NULL,
    duration_ms REAL NOT NULL DEFAULT 0.0,
    result_json TEXT NOT NULL,
    UNIQUE(run_id, task_id),
    FOREIGN KEY(run_id) REFERENCES evaluation_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    all_passed INTEGER NOT NULL,
    report_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_evals_run_id ON task_evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_task_evals_task_id ON task_evaluations(task_id);
CREATE INDEX IF NOT EXISTS idx_run_logs_run_id ON run_logs(run_id);
"""


class BenchmarkDatabase:
    """Thread-safe SQLite database repository for evaluation runs, task grades, and logs."""

    def __init__(self, db_path: Path | None = None, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig.from_env()
        self.db_path = (db_path or self.config.db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def save_run(self, run: EvaluationRunSummary) -> None:
        """Insert or update an evaluation run and all its task results atomically."""
        with self._lock, self._connect() as conn:
            summary_payload = run.model_dump()
            conn.execute(
                """
                INSERT INTO evaluation_runs (
                    run_id, run_name, benchmark_version, agent_id, provider, model,
                    sandbox_mode, status, created_at, completed_at, total_tasks,
                    completed_tasks, resolved_count, resolved_rate, issue_fix_count,
                    issue_fix_rate, regression_count, regression_free_count,
                    regression_free_rate, patch_valid_count, patch_valid_rate,
                    integrity_violation_count, execution_failure_count,
                    total_duration_ms, total_tokens, estimated_cost_usd,
                    is_demo, summary_json
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(run_id) DO UPDATE SET
                    run_name=excluded.run_name,
                    status=excluded.status,
                    completed_at=excluded.completed_at,
                    total_tasks=excluded.total_tasks,
                    completed_tasks=excluded.completed_tasks,
                    resolved_count=excluded.resolved_count,
                    resolved_rate=excluded.resolved_rate,
                    issue_fix_count=excluded.issue_fix_count,
                    issue_fix_rate=excluded.issue_fix_rate,
                    regression_count=excluded.regression_count,
                    regression_free_count=excluded.regression_free_count,
                    regression_free_rate=excluded.regression_free_rate,
                    patch_valid_count=excluded.patch_valid_count,
                    patch_valid_rate=excluded.patch_valid_rate,
                    integrity_violation_count=excluded.integrity_violation_count,
                    execution_failure_count=excluded.execution_failure_count,
                    total_duration_ms=excluded.total_duration_ms,
                    total_tokens=excluded.total_tokens,
                    estimated_cost_usd=excluded.estimated_cost_usd,
                    summary_json=excluded.summary_json
                """,
                (
                    run.run_id,
                    run.run_name,
                    run.benchmark_version,
                    run.agent_id,
                    run.provider,
                    run.model,
                    run.sandbox_mode,
                    run.status,
                    run.created_at,
                    run.completed_at,
                    run.total_tasks,
                    run.completed_tasks,
                    run.resolved_count,
                    run.resolved_rate,
                    run.issue_fix_count,
                    run.issue_fix_rate,
                    run.regression_count,
                    run.regression_free_count,
                    run.regression_free_rate,
                    run.patch_valid_count,
                    run.patch_valid_rate,
                    run.integrity_violation_count,
                    run.execution_failure_count,
                    run.total_duration_ms,
                    run.total_tokens,
                    run.estimated_cost_usd,
                    1 if run.is_demo else 0,
                    json.dumps(summary_payload),
                ),
            )

            for tr in run.task_results:
                conn.execute(
                    """
                    INSERT INTO task_evaluations (
                        run_id, task_id, difficulty, category, agent_id,
                        resolved, issue_fixed, has_regression, resolution_status,
                        duration_ms, result_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, task_id) DO UPDATE SET
                        resolved=excluded.resolved,
                        issue_fixed=excluded.issue_fixed,
                        has_regression=excluded.has_regression,
                        resolution_status=excluded.resolution_status,
                        duration_ms=excluded.duration_ms,
                        result_json=excluded.result_json
                    """,
                    (
                        run.run_id,
                        tr.task_id,
                        tr.difficulty.value,
                        tr.category.value,
                        tr.agent_id,
                        1 if tr.resolved else 0,
                        1 if tr.issue_fixed else 0,
                        1 if tr.has_regression else 0,
                        tr.resolution_status.value,
                        tr.duration_ms,
                        json.dumps(tr.model_dump()),
                    ),
                )
            conn.commit()

    def append_run_log(self, run_id: str, message: str, level: str = "INFO") -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO run_logs (run_id, timestamp, level, message) VALUES (?, ?, ?, ?)",
                (run_id, utc_now_iso(), level, message),
            )
            conn.commit()

    def get_run_logs(self, run_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, level, message FROM run_logs WHERE run_id = ? ORDER BY id ASC LIMIT ?",
                (run_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> EvaluationRunSummary | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT summary_json FROM evaluation_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            data = json.loads(row["summary_json"])
            return EvaluationRunSummary.model_validate(data)

    def list_runs(
        self,
        provider: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_task_results: bool = False,
    ) -> tuple[list[EvaluationRunSummary], int]:
        where_clauses: list[str] = []
        params: list[Any] = []
        if provider:
            where_clauses.append("provider = ?")
            params.append(provider)
        if status:
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        with self._lock, self._connect() as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM evaluation_runs {where_sql}",  # noqa: S608
                params,
            ).fetchone()
            total = int(count_row["cnt"]) if count_row else 0

            rows = conn.execute(
                f"SELECT summary_json FROM evaluation_runs {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
                [*params, limit, offset],
            ).fetchall()

            runs: list[EvaluationRunSummary] = []
            for r in rows:
                data = json.loads(r["summary_json"])
                if not include_task_results:
                    data["task_results"] = []
                runs.append(EvaluationRunSummary.model_validate(data))
            return runs, total

    def get_task_evaluation(self, run_id: str, task_id: str) -> TaskEvaluationResult | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM task_evaluations WHERE run_id = ? AND task_id = ?",
                (run_id, task_id),
            ).fetchone()
            if not row:
                return None
            return TaskEvaluationResult.model_validate(json.loads(row["result_json"]))

    def compare_runs(self, run_ids: list[str] | None = None) -> dict[str, Any]:
        """Compare multiple evaluation runs side-by-side across tasks, categories, and regressions."""
        if run_ids:
            runs = [r for rid in run_ids if (r := self.get_run(rid)) is not None]
        else:
            runs, _ = self.list_runs(limit=20, include_task_results=True)

        run_summaries = []
        task_matrix: dict[str, dict[str, Any]] = {}

        for run in runs:
            run_summaries.append(
                {
                    "run_id": run.run_id,
                    "run_name": run.run_name,
                    "agent_id": run.agent_id,
                    "provider": run.provider,
                    "model": run.model,
                    "sandbox_mode": run.sandbox_mode,
                    "created_at": run.created_at,
                    "total_tasks": run.total_tasks,
                    "resolved_count": run.resolved_count,
                    "resolved_rate": run.resolved_rate,
                    "issue_fix_count": run.issue_fix_count,
                    "issue_fix_rate": run.issue_fix_rate,
                    "regression_count": run.regression_count,
                    "regression_free_rate": run.regression_free_rate,
                    "patch_valid_rate": run.patch_valid_rate,
                    "total_duration_ms": run.total_duration_ms,
                    "total_tokens": run.total_tokens,
                    "estimated_cost_usd": run.estimated_cost_usd,
                }
            )
            for tr in run.task_results:
                if tr.task_id not in task_matrix:
                    task_matrix[tr.task_id] = {
                        "task_id": tr.task_id,
                        "title": tr.title,
                        "difficulty": tr.difficulty.value,
                        "category": tr.category.value,
                        "outcomes": {},
                    }
                task_matrix[tr.task_id]["outcomes"][run.run_id] = {
                    "agent_id": run.agent_id,
                    "resolved": tr.resolved,
                    "issue_fixed": tr.issue_fixed,
                    "has_regression": tr.has_regression,
                    "resolution_status": tr.resolution_status.value,
                    "duration_ms": tr.duration_ms,
                }

        return {
            "runs": run_summaries,
            "task_matrix": sorted(task_matrix.values(), key=lambda x: x["task_id"]),
        }

    def save_validation_summary(self, summary: DatasetValidationSummary) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO dataset_validations (timestamp, all_passed, report_json) VALUES (?, ?, ?)",
                (
                    summary.timestamp,
                    1 if summary.all_passed else 0,
                    json.dumps(summary.model_dump()),
                ),
            )
            conn.commit()

    def get_cost_totals(self) -> dict[str, Any]:
        """Aggregate token usage and estimated cost across every recorded run.

        Returns ``None`` for a metric when no run reported it, so that "not
        measured" is never confused with "zero".
        """
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(total_tokens) AS tokens,
                    SUM(estimated_cost_usd) AS cost,
                    COUNT(*) AS runs,
                    SUM(CASE WHEN estimated_cost_usd IS NOT NULL THEN 1 ELSE 0 END) AS priced_runs
                FROM evaluation_runs
                """
            ).fetchone()
        if not row:
            return {"total_tokens": None, "total_cost_usd": None, "total_runs": 0, "priced_runs": 0}
        return {
            "total_tokens": int(row["tokens"]) if row["tokens"] is not None else None,
            "total_cost_usd": round(float(row["cost"]), 6) if row["cost"] is not None else None,
            "total_runs": int(row["runs"] or 0),
            "priced_runs": int(row["priced_runs"] or 0),
        }

    def get_latest_validation_summary(self) -> DatasetValidationSummary | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM dataset_validations ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return DatasetValidationSummary.model_validate(json.loads(row["report_json"]))
