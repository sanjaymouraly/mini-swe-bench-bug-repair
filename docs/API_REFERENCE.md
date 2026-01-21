# HTTP API Reference

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

The dashboard is served by the same FastAPI application that backs the CLI.
Start it with:

```bash
bugbench serve --host 127.0.0.1 --port 8000
```

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

All responses are JSON unless the `export` endpoint is used, which streams
`text/csv` or `application/x-ndjson`.

---

## Health & overview

### `GET /api/health`

Liveness probe plus the resolved configuration (secrets redacted).

```json
{
  "status": "ok",
  "version": "1.0.0",
  "repo_slug": "software-bug-repair-benchmark",
  "disclaimer": "This is an independent SWE-bench-inspired practice benchmark...",
  "task_count": 12,
  "config": { "sandbox_mode": "auto", "effective_sandbox_mode": "docker", "...": "..." }
}
```

### `GET /api/overview`

Benchmark-level aggregates for the dashboard home screen.

| Field | Description |
| :--- | :--- |
| `total_tasks` | Number of benchmark tasks (12) |
| `difficulty_counts` | `{"easy": 4, "medium": 4, "hard": 4}` |
| `category_counts` | Task count per category |
| `total_runs` | Number of recorded evaluation runs |
| `recent_runs` | Up to 10 recent run summaries |
| `latest_validation` | The most recent dataset quality-gate report |
| `sandbox_mode` | Effective sandbox backend |
| `cost_totals` | `{total_tokens, total_cost_usd, total_runs, priced_runs}` across **all** runs |

`total_cost_usd` is `null` when no run reported a measurable cost. It is never
`0.0` to mean "unknown".

## Tasks

### `GET /api/tasks`

Query parameters: `difficulty`, `category`, `search`.

```json
{ "total": 12, "tasks": [ { "task_id": "pagiflow-001", "...": "..." } ] }
```

### `GET /api/tasks/{task_id}`

Full task metadata, the issue report, the current source files, and the
preservation test code.

```json
{
  "task": { "task_id": "pagiflow-001", "allowed_files": ["..."], "...": "..." },
  "source_files": { "src/pagiflow/client.py": "..." },
  "existing_tests_code": "..."
}
```

Returns `404` if the task does not exist.

## Dataset validation

### `POST /api/validate`

```json
{ "task_ids": ["pagiflow-001"], "repeat_runs": 2 }
```

Runs the 8 quality gates and stores the report. Returns the full
`DatasetValidationSummary`, including per-task check results.

### `GET /api/validation/latest`

```json
{ "available": true, "summary": { "all_passed": true, "valid_tasks": 12, "...": "..." } }
```

## Providers

### `GET /api/providers`

```json
{
  "providers": [
    {
      "id": "custom_openai",
      "name": "Custom OpenAI-Compatible API",
      "requires_api_key": false,
      "description": "...",
      "configured_base_url": "https://gateway.example/v1",
      "configured_model": "my-model",
      "has_api_key": true,
      "max_cost_usd": 5.0,
      "input_cost_per_1k_tokens": null,
      "output_cost_per_1k_tokens": null,
      "pricing_source": "",
      "preset": {
        "id": "custom_openai",
        "label": "Custom OpenAI-compatible API",
        "default_base_url": "",
        "api_key_env": "CUSTOM_OPENAI_API_KEY",
        "cost_tier": "varies",
        "notes": "..."
      }
    }
  ],
  "presets": [ { "id": "openai", "...": "..." } ]
}
```

API key values are never returned — only `has_api_key`.

### `POST /api/providers/configure`

Body matches the `ProviderConfigModel`:

```json
{
  "provider": "custom_openai",
  "base_url": "https://gateway.example/v1",
  "api_key": "sk-...",
  "model": "my-model",
  "temperature": 0.0,
  "max_tokens": 4096,
  "timeout_seconds": 60,
  "max_cost_usd": 5.0,
  "input_cost_per_1k_tokens": null,
  "output_cost_per_1k_tokens": null,
  "allow_builtin_pricing_estimates": false
}
```

Stored at `artifacts/tmp/provider_settings.json` with `0600` permissions.

### `POST /api/providers/test`

```json
{ "provider": "custom_openai", "base_url": null, "api_key": null, "model": null }
```

Returns:

```json
{
  "provider": "custom_openai",
  "reachable": true,
  "authenticated": true,
  "selected_model": "my-model",
  "discovered_models": ["model-a", "model-b"],
  "message": "Connected to https://gateway.example/v1; 2 model(s) available. Selected: my-model. Pricing: provider_discovery.",
  "latency_ms": 123.4
}
```

## Runs

### `GET /api/runs`

Query parameters: `provider`, `status`, `limit` (1–200), `offset`, `include_tasks`.

```json
{ "total": 6, "limit": 50, "offset": 0, "runs": [ { "...": "..." } ] }
```

### `POST /api/runs`

```json
{
  "provider": "custom_openai",
  "model": "my-model",
  "base_url": null,
  "api_key": null,
  "patch_text": null,
  "patch_path": null,
  "task_ids": null,
  "difficulty": null,
  "category": null,
  "run_name": "My evaluation",
  "max_workers": 2,
  "sandbox_mode": "docker",
  "include_private_tests": true,
  "timeout_seconds": 60,
  "async_exec": true
}
```

With `async_exec: true` the call returns immediately:

```json
{ "run_id": "run-1792582959-546fb3", "status": "RUNNING", "run": { "...": "..." } }
```

With `async_exec: false` (default) it blocks and returns the finished summary.
Returns `400` when no task matches the filters.

### `GET /api/runs/{run_id}`

The full run summary including every task result, patch diff, and per-test outcome.

### `GET /api/runs/{run_id}/logs`

```json
{
  "run_id": "run-...",
  "status": "RUNNING",
  "completed_tasks": 3,
  "total_tasks": 12,
  "logs": [ { "timestamp": "...", "level": "INFO", "message": "..." } ]
}
```

### `POST /api/runs/{run_id}/cancel`

```json
{ "run_id": "run-...", "cancellation_requested": true }
```

Stops the run before the remaining tasks start. Tasks already in flight finish.

### `GET /api/runs/{run_id}/tasks/{task_id}`

The full `TaskEvaluationResult` for one task in one run: patch validation,
per-suite per-test outcomes, stdout/stderr, and the unified diff.

### `GET /api/runs/{run_id}/export?fmt=json|jsonl|csv`

Streams the run as a downloadable file.

## Comparison

### `GET /api/compare?run_ids=id1,id2`

```json
{
  "runs": [ { "run_id": "...", "resolved_rate": 100.0, "estimated_cost_usd": null, "...": "..." } ],
  "task_matrix": [
    {
      "task_id": "pagiflow-001",
      "title": "...",
      "difficulty": "easy",
      "category": "pagination_api",
      "outcomes": {
        "run-1": { "agent_id": "...", "resolved": true, "issue_fixed": true, "has_regression": false, "resolution_status": "RESOLVED", "duration_ms": 1234.0 }
      }
    }
  ]
}
```

Omit `run_ids` to compare the 20 most recent runs.

---

## Resolution statuses

| Status | Meaning |
| :--- | :--- |
| `RESOLVED` | Issue fixed, no regressions, patch valid and integrity-clean |
| `UNRESOLVED` | Patch applied but the issue (or a private test) still fails |
| `REGRESSION` | A `PASS_TO_PASS` preservation test broke |
| `INVALID_PATCH` | The diff did not apply to the base revision |
| `INTEGRITY_VIOLATION` | Unauthorized file, test tampering, or a detected shortcut |
| `EXECUTION_FAILURE` | Timeout, crash, or environment failure during test execution |
| `NO_CHANGES` | The submission was empty |

A task counts as **resolved** only when it is `RESOLVED`. `issue_fixed` is
reported separately and is `true` when the issue tests pass even if a
preservation test regressed — the two are deliberately not conflated.
