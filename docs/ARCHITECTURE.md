# System Architecture — Mini SWE-Bench (`bugbench`)

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

---

## 1. End-to-End Evaluation Lifecycle

Every benchmark evaluation executes an 8-stage deterministic pipeline:

```text
+-------------------------------------------------------------------------+
| 1. Task & Asset Resolution (`DatasetLoader`)                            |
|    - Loads `benchmarks/<task_id>/task.json` & `issue.md`                |
|    - Verifies SHA-256 test suite hash & deterministic Git base revision |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| 2. Isolated Agent Workspace Provisioning (`EphemeralWorkspace`)         |
|    - Creates ephemeral checkout containing ONLY `repo/` and `ISSUE.md`  |
|    - Excludes `reference.patch`, `evaluation/test_issue.py`, and        |
|      `private_evaluations/<task_id>/test_private.py`                    |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| 3. Candidate Repair Execution (`AgentAdapter`)                          |
|    - Offline Patch / Baseline Oracle / LLM API / CLI Coding Agent       |
|    - Collects unified Git diff (`git diff HEAD`) & redacts secrets      |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| 4. Clean Grading Checkout (`EphemeralWorkspace(purpose="grading")`)     |
|    - Discards the agent workspace completely                            |
|    - Initializes a fresh checkout of the original buggy repository      |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| 5. Patch Verification & Anti-Tampering (`PatchValidator`)               |
|    - Verifies unified diff syntax & `git apply --check`                 |
|    - Rejects edits outside `task.allowed_files`                         |
|    - Rejects test/config tampering (`tests/*`, `pyproject.toml`)        |
|    - Scans added lines for shortcuts (`pytest.skip`, `os._exit(0)`,     |
|      `PYTEST_CURRENT_TEST`, stack introspection)                        |
|    - Scans workspace for symlink escapes (`verify_no_symlink_escapes`)  |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| 6. Isolated 3-Suite Sandbox Execution (`SandboxExecutor`)               |
|    - Suite A: `PASS_TO_PASS` (`tests/test_existing.py`)                 |
|    - Suite B: `FAIL_TO_PASS` (`evaluation/test_issue.py`)               |
|    - Suite C: `PRIVATE` (`private_evaluations/<id>/test_private.py`)    |
|    - Enforces network isolation, CPU/RAM/PID limits & JUnit XML parsing |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| 7. Multi-Dimensional Grading (`GradingEngine`)                          |
|    - `RESOLVED` iff Patch Valid + Integrity Pass + All 3 Suites Pass    |
|    - `REGRESSION` if any `PASS_TO_PASS` preservation test fails         |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| 8. Persistence, Analytics & Export (`BenchmarkDatabase` / `Exporter`)   |
|    - Thread-safe SQLite WAL storage + JSON / JSONL / CSV / MD exports   |
+-------------------------------------------------------------------------+
```

---

## 2. Multi-Tier Sandbox Execution (`SandboxExecutor`)

`src/bugbench/sandbox/executor.py` supports three execution backends, selected automatically (`SandboxMode.AUTO`) or explicitly via `--sandbox`:

1. **Docker Container Isolation (`SandboxMode.DOCKER`)**:
   - Runs inside `software-bug-repair-benchmark-runner:latest` as non-root UID/GID `1000:1000`.
   - Network disabled (`--network none`).
   - Resource limits enforced (`--cpus 1.0`, `--memory 512m`, `--pids-limit 64`).
   - Read-only root filesystem (`--read-only`) with `noexec,nosuid` `/tmp` tmpfs.
   - All Linux capabilities dropped (`--cap-drop ALL`, `--security-opt no-new-privileges:true`).
   - External evaluation tests (`test_issue.py`, `test_private.py`) are bind-mounted **read-only (`:ro`)** into the container so candidate code cannot modify or overwrite them during test execution.

2. **Linux Bubblewrap Namespace Isolation (`SandboxMode.BWRAP`)**:
   - Uses `bwrap --unshare-net --unshare-ipc --unshare-pid --die-with-parent`.
   - Mounts system libraries (`/usr`, `/lib`, `/lib64`, `/bin`) read-only (`--ro-bind`), mounts an isolated `/tmp` (`--tmpfs /tmp`), and binds only the ephemeral repository checkout read-write.

3. **Hardened Subprocess Mode (`SandboxMode.SUBPROCESS`)**:
   - Cross-platform fallback for Windows PowerShell, macOS, or CI environments without Docker/Bubblewrap.
   - Strips proxy and credential environment variables, sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTHONHASHSEED=0`, and `TZ=UTC`, and enforces process-group termination on timeout.

---

## 3. Provider & Cost-Control Layer

```
+------------------+     +----------------------+     +------------------------+
| Connection       | --> | AgentAdapter         | --> | PricingResolver       |
| Preset           |     | (OpenAI-compatible,  |     | (provider_discovery /  |
| (base URL, key   |     |  Anthropic, CLI)     |     |  manual / estimate)    |
|  env var, tier)  |     +----------------------+     +------------------------+
+------------------+                                                      |
                                                                          v
                                                            +-----------------------------+
                                                            | Token usage + price -> cost  |
                                                            | NULL when unmeasured          |
                                                            +-----------------------------+
```

`src/bugbench/agents/pricing.py` owns pricing resolution:

- **Discovery first.** `OpenAICompatibleBaseAdapter.discover_models()` caches any
  per-model rates published in the provider's `/models` payload. Recognised
  field names cover per-1k, per-1M, and per-token shapes.
- **Manual overrides win.** A rate entered with
  `bugbench providers --configure ... --input-cost-per-1k ...` takes precedence.
- **Bundled estimates are opt-in.** `BUILTIN_PRICING_ESTIMATES` holds clearly
  labelled estimates for common OpenAI and Anthropic models. They are only used
  when `allow_builtin_pricing_estimates` is enabled, because published rates
  change frequently.
- **Unknown stays unknown.** `calculate_cost_usd()` returns `None` unless real
  token usage *and* a price are both present. `None` is rendered as `n/a`, never
  as `$0.00`.

The orchestrator enforces the per-run budget
(`AppConfig.get_provider_config(...).max_cost_usd`). When the accumulated
priced spend reaches the cap, the remaining tasks are skipped and the run is
stored with status `STOPPED_BUDGET`. The cap is never applied to an unpriced
provider, so an unknown price can never silently consume a budget.

---

## 4. Patch Application Robustness

Models frequently return a diff whose hunk line counts are slightly wrong, or
which omits the `diff --git` header. `src/bugbench/agents/base.py` normalises
such output rather than discarding an otherwise correct repair:

1. `apply_llm_response_to_workspace()` first looks for a complete-file block
   (`` ```python:src/pkg/mod.py `` ), including the `### File:` heading style.
2. Otherwise it looks for a unified diff and calls `apply_unified_diff()`, which:
   - synthesises missing `diff --git` headers via `_ensure_git_headers()`,
   - applies with `git apply --recount` (hunk counts are recomputed),
   - falls back to `git apply --3way --recount`,
   - finally falls back to GNU `patch -p1` if it is installed.
3. Every path writes only inside the agent workspace, and every written path is
   checked with `validate_safe_relative_path()` to block traversal and symlink
   escapes.

---

## 5. Storage Layer & PostgreSQL Migration Path

`src/bugbench/storage/database.py` uses standard ANSI SQL tables (`evaluation_runs`, `task_evaluations`, `run_logs`, `dataset_validations`) with JSON columns for structured nested telemetry.

- **Default Local Deployment**: Zero-configuration SQLite in Write-Ahead Logging (`WAL`) mode at `artifacts/bugbench.db`.
- **Safe concurrent writes**: every statement runs under a re-entrant lock and a
  per-operation connection with `busy_timeout=5000`; WAL mode lets readers
  proceed while a writer holds the lock.
- **Aggregations**: `get_cost_totals()` sums token usage and cost across *all*
  runs (not just the most recent page) and returns `None` when a metric was
  never measured.
- **PostgreSQL Migration Path**:
  1. Set `BUGBENCH_DB_URL=postgresql://user:password@host:5432/bugbench`.
  2. Replace `sqlite3.connect(...)` in `BenchmarkDatabase._connect()` with `psycopg.connect(self.db_url)` and convert `?` positional placeholders to `%s`. The schema uses only `TEXT`, `INTEGER`, `REAL`, and `TEXT` columns, all directly compatible with PostgreSQL `TEXT`/`NUMERIC`/`JSONB`.

---

## 6. Reproducibility Model

Every number in a report can be traced back to a hash:

| Artifact | Recorded as |
| :--- | :--- |
| Benchmark task content | `test_suite_hash` (SHA-256 over tests + issue tests + private tests) |
| Reference solution | `reference_patch_hash` (SHA-256 of `reference.patch`) |
| Base revision | `base_revision` (deterministic Git commit SHA) |
| Submitted patch | `patch_validation.patch_sha256` |
| Dataset | `benchmark_version` |
| Run | `run_id`, `created_at`, `completed_at`, `sandbox_mode`, `config_snapshot` |

The base commit is reproducible because `ensure_task_git_repo()` creates the
repository with a fixed author, committer, timestamp, and timezone, and forces
`core.autocrlf=false`. `scripts/bootstrap_repos.py` regenerates all 12 tasks
from `scripts/benchmark_defs/` and produces byte-identical output, which is
checked in CI.

---

## 7. Module Map

```text
src/bugbench/
├── models.py              # Pydantic domain models (tasks, results, statuses)
├── config.py              # AppConfig, provider settings, env precedence
├── logging_utils.py       # structured logging + secret redaction
├── agents/
│   ├── base.py            # AgentAdapter ABC, prompt building, patch application
│   ├── offline.py         # reference / noop / incomplete / regression / manual patch
│   ├── llm_providers.py   # OpenAI, Anthropic, OpenRouter, custom, Ollama
│   ├── cli_agents.py      # Codex CLI, Claude Code CLI
│   ├── pricing.py         # pricing discovery, presets, cost resolution
│   └── registry.py        # adapter factory + provider catalog
├── dataset/
│   ├── builder.py         # deterministic Git init, hashing, line-ending normalisation
│   ├── loader.py          # task discovery and metadata loading
│   └── validator.py       # the 8 quality gates
├── grading/
│   ├── patch_validator.py # diff parsing, applicability, anti-tampering
│   └── engine.py          # 3-suite execution + resolution decision
├── sandbox/
│   ├── workspace.py       # ephemeral isolated checkouts, path safety
│   └── executor.py        # Docker / bubblewrap / subprocess execution
├── orchestrator/runner.py # suite execution, parallelism, retries, budgets
├── storage/
│   ├── database.py        # SQLite WAL repository
│   └── exporter.py        # JSON / JSONL / CSV export
├── reporting/             # Markdown report generation
├── api/app.py             # FastAPI application
└── cli/main.py            # Typer CLI
```
