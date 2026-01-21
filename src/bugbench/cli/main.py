"""Complete `bugbench` CLI implementation using Typer and Rich."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bugbench import DISCLAIMER, __version__
from bugbench.agents.pricing import format_usd
from bugbench.agents.registry import AgentRegistry
from bugbench.config import AppConfig
from bugbench.dataset.loader import DatasetLoader
from bugbench.dataset.validator import DatasetValidator
from bugbench.models import EvaluationRunSummary, SandboxMode
from bugbench.orchestrator.runner import BenchmarkRunner
from bugbench.storage.database import BenchmarkDatabase
from bugbench.storage.exporter import ResultExporter

app = typer.Typer(
    name="bugbench",
    help=f"Mini SWE-Bench: Automated Software Bug Repair Evaluation (v{__version__})\n\n{DISCLAIMER}",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _print_run_summary_table(run: EvaluationRunSummary) -> None:
    console.print(
        Panel(
            f"[bold cyan]Run ID:[/bold cyan] {run.run_id}\n"
            f"[bold cyan]Run Name:[/bold cyan] {run.run_name}\n"
            f"[bold cyan]Agent / Model:[/bold cyan] {run.agent_id} ({run.provider}/{run.model})\n"
            f"[bold cyan]Sandbox Mode:[/bold cyan] {run.sandbox_mode}\n"
            f"[bold green]Resolved:[/bold green] {run.resolved_count}/{run.total_tasks} ({run.resolved_rate}%)\n"
            f"[bold yellow]Issue-Fix Rate:[/bold yellow] {run.issue_fix_count}/{run.total_tasks} ({run.issue_fix_rate}%)\n"
            f"[bold magenta]Regression-Free Rate:[/bold magenta] {run.regression_free_count}/{run.total_tasks} ({run.regression_free_rate}%) "
            f"[Regressions: {run.regression_count}]\n"
            f"[bold blue]Patch Applicability:[/bold blue] {run.patch_valid_count}/{run.total_tasks} ({run.patch_valid_rate}%)\n"
            f"[bold white]Total Duration:[/bold white] {run.total_duration_ms:.0f} ms\n"
            f"[bold white]Tokens:[/bold white] {run.total_tokens if run.total_tokens is not None else 'n/a'}"
            f"    [bold white]Est. Cost:[/bold white] "
            f"{format_usd(run.estimated_cost_usd)}",
            title="Evaluation Run Summary",
            expand=False,
        )
    )

    table = Table(title=f"Per-Task Evaluation Results ({run.run_id})")
    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Difficulty")
    table.add_column("Category")
    table.add_column("Status")
    table.add_column("FAIL_TO_PASS")
    table.add_column("PASS_TO_PASS")
    table.add_column("Private")
    table.add_column("Regression")
    table.add_column("Time (ms)", justify="right")

    for tr in run.task_results:
        status_str = (
            f"[green]{tr.resolution_status.value}[/green]"
            if tr.resolved
            else (
                f"[red]{tr.resolution_status.value}[/red]"
                if tr.has_regression
                else f"[yellow]{tr.resolution_status.value}[/yellow]"
            )
        )
        f2p = (
            f"{tr.fail_to_pass.passed_count}/{tr.fail_to_pass.total_count}"
            if tr.fail_to_pass
            else "-"
        )
        p2p = (
            f"{tr.pass_to_pass.passed_count}/{tr.pass_to_pass.total_count}"
            if tr.pass_to_pass
            else "-"
        )
        priv = (
            f"{tr.private_tests.passed_count}/{tr.private_tests.total_count}"
            if tr.private_tests
            else "-"
        )
        reg = "[red]YES[/red]" if tr.has_regression else "[green]NO[/green]"
        table.add_row(
            tr.task_id,
            tr.difficulty.value,
            tr.category.value,
            status_str,
            f2p,
            p2p,
            priv,
            reg,
            f"{tr.duration_ms:.0f}",
        )
    console.print(table)


@app.command("list")
def list_tasks(
    difficulty: str | None = typer.Option(
        None, "--difficulty", "-d", help="Filter by easy, medium, hard"
    ),
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by task category"),
    search: str | None = typer.Option(None, "--search", "-s", help="Keyword search"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """List benchmark tasks with optional difficulty, category, and keyword filters."""
    loader = DatasetLoader()
    tasks = loader.load_all_tasks(
        difficulty=difficulty, category=category, search=search, ensure_git=True
    )
    if json_output:
        typer.echo(json.dumps([t.model_dump() for t in tasks], indent=2))
        return

    table = Table(title=f"Mini SWE-Bench Tasks ({len(tasks)} total)")
    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Difficulty")
    table.add_column("Category")
    table.add_column("Package")
    table.add_column("Title")
    table.add_column("Base SHA")

    for t in tasks:
        table.add_row(
            t.task_id,
            t.difficulty.value,
            t.category.value,
            t.package_name,
            t.title,
            t.base_revision[:10],
        )
    console.print(table)


@app.command("inspect")
def inspect_task(
    task_id: str = typer.Argument(..., help="Task identifier (e.g. pagiflow-001)"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Inspect a single benchmark task's metadata, issue report, and allowed files."""
    loader = DatasetLoader()
    try:
        task = loader.load_task(task_id, ensure_git=True)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(json.dumps(task.model_dump(), indent=2))
        return

    console.print(
        Panel(
            f"[bold cyan]Task ID:[/bold cyan] {task.task_id}\n"
            f"[bold cyan]Title:[/bold cyan] {task.title}\n"
            f"[bold cyan]Difficulty:[/bold cyan] {task.difficulty.value}\n"
            f"[bold cyan]Category:[/bold cyan] {task.category.value}\n"
            f"[bold cyan]Package:[/bold cyan] {task.package_name}\n"
            f"[bold cyan]Base Revision:[/bold cyan] {task.base_revision}\n"
            f"[bold cyan]Allowed Files:[/bold cyan] {', '.join(task.allowed_files)}\n"
            f"[bold cyan]Test Suite Hash:[/bold cyan] {task.test_suite_hash}\n\n"
            f"[bold yellow]Issue Report:[/bold yellow]\n{task.issue_description}\n\n"
            f"[bold green]Reproduction Instructions:[/bold green]\n{task.reproduction_instructions}",
            title=f"Task Inspection: {task.task_id}",
        )
    )


@app.command("validate")
def validate_dataset(
    task: list[str] | None = typer.Option(
        None, "--task", "-t", help="Specific task ID(s) to validate"
    ),
    repeat: int = typer.Option(
        2, "--repeat", "-r", help="Number of isolated runs for stability verification"
    ),
    sandbox: SandboxMode = typer.Option(
        SandboxMode.AUTO, "--sandbox", help="Sandbox mode (auto, docker, bwrap, subprocess)"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write validation report JSON to file"
    ),
) -> None:
    """Run all 8 programmatic quality gates across the benchmark dataset."""
    cfg = AppConfig.from_env()
    db = BenchmarkDatabase(config=cfg)
    validator = DatasetValidator(config=cfg, sandbox_mode=sandbox)
    summary = validator.validate_dataset(task_ids=task or None, repeat_runs=repeat)
    db.save_validation_summary(summary)

    table = Table(
        title=f"Dataset Quality Gate Report ({summary.valid_tasks}/{summary.total_tasks} Valid)"
    )
    table.add_column("Task ID", style="cyan")
    table.add_column("Difficulty")
    table.add_column("Gates Passed")
    table.add_column("Base Revision")
    table.add_column("Status")
    table.add_column("Duration (ms)", justify="right")

    for rep in summary.task_reports:
        passed_cnt = sum(1 for c in rep.checks if c.passed)
        tot_cnt = len(rep.checks)
        status_txt = "[green]PASS[/green]" if rep.passed else "[red]FAIL[/red]"
        table.add_row(
            rep.task_id,
            rep.difficulty.value,
            f"{passed_cnt}/{tot_cnt}",
            rep.base_revision[:10],
            status_txt,
            f"{rep.duration_ms:.0f}",
        )
    console.print(table)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary.model_dump(), indent=2), encoding="utf-8")
        console.print(f"Saved validation report to [cyan]{output}[/cyan]")

    if not summary.all_passed:
        raise typer.Exit(code=1)


@app.command("baseline")
def run_baseline(
    mode: str = typer.Option(
        "noop", "--mode", "-m", help="Baseline mode: noop, incomplete, or regression"
    ),
    task: list[str] | None = typer.Option(None, "--task", "-t", help="Filter by task ID(s)"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel workers"),
    sandbox: SandboxMode = typer.Option(SandboxMode.AUTO, "--sandbox", help="Sandbox mode"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Export run summary to file"),
) -> None:
    """Run the No-Op, Incomplete, or Regression baseline evaluation across tasks."""
    runner = BenchmarkRunner()
    run_name = f"Baseline ({mode.upper()})"
    summary = runner.run_suite(
        provider=mode,
        task_ids=task or None,
        run_name=run_name,
        max_workers=workers,
        sandbox_mode=sandbox,
    )
    _print_run_summary_table(summary)
    if output:
        ResultExporter.export_to_file(summary, output)
        console.print(f"Exported baseline report to [cyan]{output}[/cyan]")


@app.command("reference")
def run_reference(
    task: list[str] | None = typer.Option(None, "--task", "-t", help="Filter by task ID(s)"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel workers"),
    sandbox: SandboxMode = typer.Option(SandboxMode.AUTO, "--sandbox", help="Sandbox mode"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Export run summary to file"),
) -> None:
    """Run the verified Reference Oracle evaluation across tasks (must resolve 100%)."""
    runner = BenchmarkRunner()
    summary = runner.run_suite(
        provider="reference",
        task_ids=task or None,
        run_name="Reference Oracle Baseline",
        max_workers=workers,
        sandbox_mode=sandbox,
    )
    _print_run_summary_table(summary)
    if output:
        ResultExporter.export_to_file(summary, output)
        console.print(f"Exported reference report to [cyan]{output}[/cyan]")
    if summary.resolved_count != summary.total_tasks:
        raise typer.Exit(code=1)


@app.command("evaluate-patch")
def evaluate_patch(
    patch: Path = typer.Option(
        ..., "--patch", "-p", help="Path to unified .patch/.diff file or directory of patches"
    ),
    task: list[str] | None = typer.Option(None, "--task", "-t", help="Target task ID(s)"),
    run_name: str | None = typer.Option(None, "--run-name", help="Custom run name"),
    sandbox: SandboxMode = typer.Option(SandboxMode.AUTO, "--sandbox", help="Sandbox mode"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Export result to file"),
) -> None:
    """Evaluate a manually written or externally generated Git patch offline without an AI API."""
    if not patch.exists():
        console.print(f"[red]Error:[/red] Patch path not found: {patch}")
        raise typer.Exit(code=2)

    runner = BenchmarkRunner()
    summary = runner.run_suite(
        provider="offline",
        patch_path=patch,
        task_ids=task or None,
        run_name=run_name or f"Offline Patch ({patch.name})",
        sandbox_mode=sandbox,
    )
    _print_run_summary_table(summary)
    if output:
        ResultExporter.export_to_file(summary, output)
        console.print(f"Exported patch evaluation to [cyan]{output}[/cyan]")


@app.command("run-agent")
def run_agent(
    provider: str = typer.Option(
        ...,
        "--provider",
        help="Provider ID (openai, anthropic, openrouter, custom_openai, ollama, codex_cli, claude_code_cli, reference, noop)",
    ),
    model: str | None = typer.Option(
        None, "--model", help="Model name (auto-discovered if omitted on supported endpoints)"
    ),
    base_url: str | None = typer.Option(None, "--base-url", help="Override API base URL"),
    api_key: str | None = typer.Option(None, "--api-key", help="Override API key"),
    task: list[str] | None = typer.Option(None, "--task", "-t", help="Specific task ID(s)"),
    difficulty: str | None = typer.Option(None, "--difficulty", "-d", help="Filter by difficulty"),
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel workers"),
    timeout: int = typer.Option(60, "--timeout", help="Timeout per task in seconds"),
    max_cost: float | None = typer.Option(
        None,
        "--max-cost",
        help="Maximum USD spend for this run (0 disables the cap; needs known pricing)",
    ),
    sandbox: SandboxMode = typer.Option(SandboxMode.AUTO, "--sandbox", help="Sandbox mode"),
    run_name: str | None = typer.Option(None, "--run-name", help="Custom run label"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Export run report to file"),
) -> None:
    """Execute a coding agent or LLM provider across selected benchmark tasks."""
    runner = BenchmarkRunner()
    if max_cost is not None:
        # Persist the cap for this provider so the orchestrator can enforce it.
        pcfg = runner.config.get_provider_config(provider)
        pcfg.max_cost_usd = max_cost
        runner.config.save_provider_setting(pcfg)
    summary = runner.run_suite(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        task_ids=task or None,
        difficulty=difficulty,
        category=category,
        run_name=run_name,
        max_workers=workers,
        sandbox_mode=sandbox,
        timeout_seconds=timeout,
    )
    _print_run_summary_table(summary)
    if output:
        ResultExporter.export_to_file(summary, output)
        console.print(f"Exported run summary to [cyan]{output}[/cyan]")


@app.command("runs")
def list_runs_cmd(
    provider: str | None = typer.Option(None, "--provider", help="Filter by provider"),
    status: str | None = typer.Option(None, "--status", help="Filter by status"),
    limit: int = typer.Option(25, "--limit", help="Maximum runs to display"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """List recorded evaluation runs from the SQLite database."""
    db = BenchmarkDatabase()
    runs, total = db.list_runs(provider=provider, status=status, limit=limit)
    if json_output:
        typer.echo(json.dumps([r.model_dump() for r in runs], indent=2))
        return

    table = Table(title=f"Recorded Evaluation Runs ({len(runs)}/{total})")
    table.add_column("Run ID", style="cyan")
    table.add_column("Run Name")
    table.add_column("Agent")
    table.add_column("Sandbox")
    table.add_column("Resolved")
    table.add_column("Issue Fix")
    table.add_column("Regressions")
    table.add_column("Status")

    for r in runs:
        table.add_row(
            r.run_id,
            r.run_name,
            r.agent_id,
            r.sandbox_mode,
            f"{r.resolved_count}/{r.total_tasks} ({r.resolved_rate}%)",
            f"{r.issue_fix_count}/{r.total_tasks} ({r.issue_fix_rate}%)",
            str(r.regression_count),
            r.status,
        )
    console.print(table)


@app.command("compare")
def compare_runs_cmd(
    runs: str | None = typer.Option(
        None, "--runs", "-r", help="Comma-separated run IDs to compare"
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON comparison"),
) -> None:
    """Compare multiple evaluation runs across resolution rate, issue fixes, and regressions."""
    db = BenchmarkDatabase()
    run_ids = [x.strip() for x in runs.split(",") if x.strip()] if runs else None
    comp = db.compare_runs(run_ids=run_ids)
    if json_output:
        typer.echo(json.dumps(comp, indent=2))
        return

    table = Table(title="Evaluation Run Comparison")
    table.add_column("Run ID", style="cyan")
    table.add_column("Run Name")
    table.add_column("Agent")
    table.add_column("Resolved %")
    table.add_column("Issue Fixed %")
    table.add_column("Regression-Free %")
    table.add_column("Patch Valid %")
    table.add_column("Duration (ms)", justify="right")

    for r in comp.get("runs", []):
        table.add_row(
            r["run_id"],
            r["run_name"],
            r["agent_id"],
            f"{r['resolved_count']}/{r['total_tasks']} ({r['resolved_rate']}%)",
            f"{r['issue_fix_count']}/{r['total_tasks']} ({r['issue_fix_rate']}%)",
            f"{r['regression_free_rate']}% ({r['regression_count']} reg)",
            f"{r['patch_valid_rate']}%",
            f"{r['total_duration_ms']:.0f}",
        )
    console.print(table)


@app.command("export")
def export_run_cmd(
    run_id: str = typer.Argument(..., help="Run ID to export"),
    fmt: str = typer.Option(
        "json", "--format", "-f", help="Export format: json, jsonl, csv, or md"
    ),
    output: Path = typer.Option(..., "--output", "-o", help="Output file path"),
) -> None:
    """Export an evaluation run to JSON, JSONL, CSV, or Markdown."""
    db = BenchmarkDatabase()
    run = db.get_run(run_id)
    if not run:
        console.print(f"[red]Error:[/red] Run '{run_id}' not found.")
        raise typer.Exit(code=2)
    saved = ResultExporter.export_to_file(run, output, fmt=fmt)
    console.print(f"Exported run [cyan]{run_id}[/cyan] ({fmt.upper()}) to [green]{saved}[/green]")


@app.command("providers")
def manage_providers(
    test: str | None = typer.Option(
        None, "--test", help="Test connectivity and discover models for a provider"
    ),
    configure: str | None = typer.Option(
        None, "--configure", help="Save configuration for a provider ID"
    ),
    base_url: str | None = typer.Option(None, "--base-url", help="API Base URL"),
    api_key: str | None = typer.Option(None, "--api-key", help="API Key"),
    model: str | None = typer.Option(None, "--model", help="Preferred model identifier"),
    input_cost: float | None = typer.Option(
        None, "--input-cost-per-1k", help="Manual USD price per 1k input tokens"
    ),
    output_cost: float | None = typer.Option(
        None, "--output-cost-per-1k", help="Manual USD price per 1k output tokens"
    ),
    max_cost: float | None = typer.Option(
        None, "--max-cost", help="Maximum USD spend for a single run (0 disables the cap)"
    ),
    use_builtin_estimates: bool | None = typer.Option(
        None,
        "--use-builtin-estimates/--no-builtin-estimates",
        help="Allow the bundled (labelled) price estimates when live pricing is unavailable",
    ),
    presets: bool = typer.Option(
        False, "--presets", help="Show the 'easy connect' connection presets and exit"
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """List, configure, or test connectivity/model-discovery for AI providers and CLI agents."""
    cfg = AppConfig.from_env()
    registry = AgentRegistry(cfg)

    if presets:
        preset_list = registry.list_connection_presets()
        if json_output:
            typer.echo(json.dumps(preset_list, indent=2))
            return
        table = Table(title="Easy-Connect Provider Presets")
        table.add_column("Provider", style="cyan")
        table.add_column("Label")
        table.add_column("Default Base URL")
        table.add_column("API Key Env Var")
        table.add_column("Cost Tier")
        for p in preset_list:
            table.add_row(
                p["id"],
                p["label"],
                p["default_base_url"] or "(you provide)",
                p["api_key_env"] or "(none)",
                p["cost_tier"],
            )
        console.print(table)
        console.print(
            "\n[dim]A ChatGPT Plus/Pro subscription does not include OpenAI API credits.[/dim]"
        )
        return

    if configure:
        current = cfg.get_provider_config(configure)
        if base_url is not None:
            current.base_url = base_url
        if api_key is not None:
            current.api_key = api_key
        if model is not None:
            current.model = model
        if input_cost is not None:
            current.input_cost_per_1k_tokens = input_cost
            current.pricing_source = "manual"
        if output_cost is not None:
            current.output_cost_per_1k_tokens = output_cost
            current.pricing_source = "manual"
        if max_cost is not None:
            current.max_cost_usd = max_cost
        if use_builtin_estimates is not None:
            current.allow_builtin_pricing_estimates = use_builtin_estimates
        cfg.save_provider_setting(current)
        console.print(f"[green]Saved configuration for provider '{configure}'.[/green]")

    if test:
        res = registry.test_provider_connection(
            provider=test, base_url=base_url, api_key=api_key, model=model
        )
        if json_output:
            typer.echo(json.dumps(res.model_dump(), indent=2))
            return
        color = "green" if (res.reachable and res.authenticated) else "red"
        console.print(
            Panel(
                f"[bold]Provider:[/bold] {res.provider}\n"
                f"[bold]Reachable:[/bold] {res.reachable}\n"
                f"[bold]Authenticated:[/bold] {res.authenticated}\n"
                f"[bold]Selected Model:[/bold] {res.selected_model or 'N/A'}\n"
                f"[bold]Discovered Models:[/bold] {', '.join(res.discovered_models[:10]) or 'None'}\n"
                f"[bold]Message:[/bold] [{color}]{res.message}[/{color}]",
                title=f"Provider Connection Check: {test}",
            )
        )
        return

    providers = registry.list_providers()
    if json_output:
        typer.echo(json.dumps(providers, indent=2))
        return

    table = Table(title="Supported Providers & Coding Agent Adapters")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Cost Tier")
    table.add_column("Configured URL")
    table.add_column("Model")
    table.add_column("Key Set")
    table.add_column("In $/1k")
    table.add_column("Out $/1k")
    for p in providers:
        preset = p.get("preset") or {}
        in_rate = p.get("input_cost_per_1k_tokens")
        out_rate = p.get("output_cost_per_1k_tokens")
        table.add_row(
            p["id"],
            p["name"],
            preset.get("cost_tier", "-"),
            p.get("configured_base_url", "") or "-",
            p.get("configured_model", "") or "(auto)",
            "Yes" if p.get("has_api_key") else "No",
            f"{in_rate:g}" if in_rate is not None else "n/a",
            f"{out_rate:g}" if out_rate is not None else "n/a",
        )
    console.print(table)
    console.print(
        "\n[dim]Pricing is reported only when the provider returned real token usage AND a "
        "price is known. 'n/a' means unmeasured, not free.[/dim]"
    )


@app.command("serve")
def serve_dashboard(
    host: str = typer.Option(
        "0.0.0.0", "--host", help="Bind host (use 0.0.0.0 for container/preview access)"
    ),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
) -> None:
    """Start the FastAPI backend and responsive web dashboard."""
    console.print(
        f"[bold green]Starting Mini SWE-Bench Dashboard at http://{host}:{port}[/bold green]"
    )
    uvicorn.run("bugbench.api.app:create_app", host=host, port=port, reload=reload, factory=True)


if __name__ == "__main__":
    app()
