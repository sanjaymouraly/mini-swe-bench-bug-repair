"""FastAPI application serving the Mini SWE-Bench API and web dashboard."""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bugbench import DISCLAIMER, __repo_slug__, __version__
from bugbench.agents.registry import AgentRegistry
from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.dataset.validator import DatasetValidator
from bugbench.models import ProviderConfigModel, SandboxMode
from bugbench.orchestrator.runner import BenchmarkRunner, request_run_cancellation
from bugbench.storage.database import BenchmarkDatabase
from bugbench.storage.exporter import ResultExporter


class LaunchRunRequest(BaseModel):
    provider: str = "reference"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    patch_text: str | None = None
    patch_path: str | None = None
    task_ids: list[str] | None = None
    difficulty: str | None = None
    category: str | None = None
    run_name: str | None = None
    max_workers: int = Field(default=1, ge=1, le=8)
    sandbox_mode: SandboxMode | None = None
    include_private_tests: bool = True
    timeout_seconds: int = Field(default=60, ge=5, le=600)
    async_exec: bool = False


class ValidateDatasetRequest(BaseModel):
    task_ids: list[str] | None = None
    repeat_runs: int = Field(default=2, ge=1, le=5)


class TestProviderRequest(BaseModel):
    provider: str
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or AppConfig.from_env()
    db = BenchmarkDatabase(config=cfg)
    loader = DatasetLoader(cfg)
    runner = BenchmarkRunner(config=cfg, db=db, loader=loader)
    registry = AgentRegistry(cfg)
    validator = DatasetValidator(config=cfg)

    app = FastAPI(
        title="Mini SWE-Bench: Automated Software Bug Repair Evaluation",
        description=DISCLAIMER,
        version=__version__,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index_page() -> Response:
        index_html = static_dir / "index.html"
        if not index_html.exists():
            return HTMLResponse("<h1>Mini SWE-Bench Dashboard</h1>")
        return FileResponse(str(index_html), media_type="text/html")

    @app.get("/api/health")
    def health_check() -> dict[str, Any]:
        tasks = loader.load_all_tasks(ensure_git=False)
        return {
            "status": "ok",
            "version": __version__,
            "repo_slug": __repo_slug__,
            "disclaimer": DISCLAIMER,
            "task_count": len(tasks),
            "config": cfg.sanitized_summary(),
        }

    @app.get("/api/overview")
    def get_overview() -> dict[str, Any]:
        tasks = loader.load_all_tasks(ensure_git=False)
        runs, total_runs = db.list_runs(limit=25, include_task_results=True)
        latest_val = db.get_latest_validation_summary()

        diff_counts: dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
        cat_counts: dict[str, int] = {}
        for t in tasks:
            diff_counts[t.difficulty.value] = diff_counts.get(t.difficulty.value, 0) + 1
            cat_counts[t.category.value] = cat_counts.get(t.category.value, 0) + 1

        return {
            "version": __version__,
            "disclaimer": DISCLAIMER,
            "total_tasks": len(tasks),
            "difficulty_counts": diff_counts,
            "category_counts": cat_counts,
            "total_runs": total_runs,
            "recent_runs": [r.model_dump(exclude={"task_results"}) for r in runs[:10]],
            "latest_validation": latest_val.model_dump() if latest_val else None,
            "sandbox_mode": cfg.resolve_effective_sandbox().value,
            "cost_totals": db.get_cost_totals(),
        }

    @app.get("/api/tasks")
    def list_tasks(
        difficulty: str | None = Query(default=None),
        category: str | None = Query(default=None),
        search: str | None = Query(default=None),
    ) -> dict[str, Any]:
        tasks = loader.load_all_tasks(
            difficulty=difficulty,
            category=category,
            search=search,
            ensure_git=True,
        )
        return {
            "total": len(tasks),
            "tasks": [t.model_dump() for t in tasks],
        }

    @app.get("/api/tasks/{task_id}")
    def get_task_detail(task_id: str) -> dict[str, Any]:
        try:
            task = loader.load_task(task_id, ensure_git=True)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        repo_dir = Path(task.repo_path)
        source_files: dict[str, str] = {}
        src_root = repo_dir / "src"
        if src_root.exists():
            for py_file in sorted(src_root.rglob("*.py")):
                rel = py_file.relative_to(repo_dir).as_posix()
                source_files[rel] = py_file.read_text(encoding="utf-8")

        existing_test_file = repo_dir / "tests" / "test_existing.py"
        existing_tests_code = (
            existing_test_file.read_text(encoding="utf-8") if existing_test_file.exists() else ""
        )

        return {
            "task": task.model_dump(),
            "source_files": source_files,
            "existing_tests_code": existing_tests_code,
        }

    @app.post("/api/validate")
    def run_dataset_validation(req: ValidateDatasetRequest) -> dict[str, Any]:
        summary = validator.validate_dataset(
            task_ids=req.task_ids,
            repeat_runs=req.repeat_runs,
        )
        db.save_validation_summary(summary)
        return summary.model_dump()

    @app.get("/api/validation/latest")
    def get_latest_validation() -> dict[str, Any]:
        summary = db.get_latest_validation_summary()
        if not summary:
            return {"available": False, "summary": None}
        return {"available": True, "summary": summary.model_dump()}

    @app.get("/api/providers")
    def list_providers() -> dict[str, Any]:
        return {
            "providers": registry.list_providers(),
            "presets": registry.list_connection_presets(),
        }

    @app.post("/api/providers/configure")
    def configure_provider(cfg_model: ProviderConfigModel) -> dict[str, Any]:
        cfg.save_provider_setting(cfg_model)
        return {
            "status": "saved",
            "provider": cfg_model.provider,
            "providers": registry.list_providers(),
        }

    @app.post("/api/providers/test")
    def test_provider(req: TestProviderRequest) -> dict[str, Any]:
        res = registry.test_provider_connection(
            provider=req.provider,
            base_url=req.base_url,
            api_key=req.api_key,
            model=req.model,
        )
        return res.model_dump()

    @app.get("/api/runs")
    def list_runs(
        provider: str | None = Query(default=None),
        status: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        include_tasks: bool = Query(default=False),
    ) -> dict[str, Any]:
        runs, total = db.list_runs(
            provider=provider,
            status=status,
            limit=limit,
            offset=offset,
            include_task_results=include_tasks,
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "runs": [r.model_dump() for r in runs],
        }

    @app.post("/api/runs")
    def launch_run(req: LaunchRunRequest) -> dict[str, Any]:
        patch_path_obj = Path(req.patch_path) if req.patch_path else None
        run_id = f"run-{int(time.time())}-{uuid.uuid4().hex[:6]}"

        if req.async_exec:

            def _bg() -> None:
                try:
                    runner.run_suite(
                        provider=req.provider,
                        model=req.model,
                        base_url=req.base_url,
                        api_key=req.api_key,
                        patch_path=patch_path_obj,
                        patch_text=req.patch_text,
                        task_ids=req.task_ids,
                        difficulty=req.difficulty,
                        category=req.category,
                        run_name=req.run_name,
                        run_id=run_id,
                        max_workers=req.max_workers,
                        sandbox_mode=req.sandbox_mode,
                        include_private_tests=req.include_private_tests,
                        timeout_seconds=req.timeout_seconds,
                    )
                except Exception as exc:
                    db.append_run_log(run_id, f"Run failed with error: {exc}", level="ERROR")

            t = threading.Thread(target=_bg, daemon=True)
            t.start()
            # Wait briefly so initial run record is saved in DB
            for _ in range(20):
                if db.get_run(run_id) is not None:
                    break
                time.sleep(0.05)
            current = db.get_run(run_id)
            return {
                "run_id": run_id,
                "status": "RUNNING",
                "run": current.model_dump() if current else None,
            }

        try:
            summary = runner.run_suite(
                provider=req.provider,
                model=req.model,
                base_url=req.base_url,
                api_key=req.api_key,
                patch_path=patch_path_obj,
                patch_text=req.patch_text,
                task_ids=req.task_ids,
                difficulty=req.difficulty,
                category=req.category,
                run_name=req.run_name,
                run_id=run_id,
                max_workers=req.max_workers,
                sandbox_mode=req.sandbox_mode,
                include_private_tests=req.include_private_tests,
                timeout_seconds=req.timeout_seconds,
            )
            return summary.model_dump()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        return run.model_dump()

    @app.get("/api/runs/{run_id}/logs")
    def get_run_logs(run_id: str, limit: int = Query(default=500, ge=1, le=2000)) -> dict[str, Any]:
        run = db.get_run(run_id)
        logs = db.get_run_logs(run_id, limit=limit)
        return {
            "run_id": run_id,
            "status": run.status if run else "UNKNOWN",
            "completed_tasks": run.completed_tasks if run else 0,
            "total_tasks": run.total_tasks if run else 0,
            "logs": logs,
        }

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict[str, Any]:
        cancelled = request_run_cancellation(run_id)
        return {"run_id": run_id, "cancellation_requested": cancelled}

    @app.get("/api/runs/{run_id}/tasks/{task_id}")
    def get_run_task_detail(run_id: str, task_id: str) -> dict[str, Any]:
        tr = db.get_task_evaluation(run_id, task_id)
        if not tr:
            raise HTTPException(
                status_code=404, detail=f"Task result {task_id} not found in run {run_id}"
            )
        return tr.model_dump()

    @app.get("/api/runs/{run_id}/export")
    def export_run(
        run_id: str,
        fmt: str = Query(default="json", pattern="^(json|jsonl|csv|md)$"),
    ) -> Response:
        run = db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

        if fmt == "jsonl":
            content = ResultExporter.to_jsonl(run)
            media_type = "application/x-ndjson"
            filename = f"{run_id}.jsonl"
        elif fmt == "csv":
            content = ResultExporter.to_csv(run)
            media_type = "text/csv"
            filename = f"{run_id}.csv"
        elif fmt == "md":
            content = ResultExporter.to_markdown(run)
            media_type = "text/markdown"
            filename = f"{run_id}.md"
        else:
            content = ResultExporter.to_json(run)
            media_type = "application/json"
            filename = f"{run_id}.json"

        return PlainTextResponse(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/compare")
    def compare_runs(
        run_ids: str | None = Query(
            default=None, description="Comma-separated list of run_ids to compare"
        ),
    ) -> dict[str, Any]:
        ids = [r.strip() for r in run_ids.split(",") if r.strip()] if run_ids else None
        return db.compare_runs(run_ids=ids)

    return app
