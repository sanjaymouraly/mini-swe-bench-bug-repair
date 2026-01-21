# CLI Reference — `bugbench`

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

All commands accept `--help`. Global behaviour is configured through environment
variables (see [`docs/CONFIGURATION_AND_PROVIDERS.md`](CONFIGURATION_AND_PROVIDERS.md)).

---

## Command overview

| Command | Purpose |
| :--- | :--- |
| `bugbench list` | List the 12 benchmark tasks, with filters |
| `bugbench inspect <task_id>` | Show a task's issue report, allowed files, and metadata |
| `bugbench validate` | Run the 8 dataset quality gates over every task |
| `bugbench reference` | Run the verified reference oracle (must resolve 100%) |
| `bugbench baseline --mode <mode>` | Run the `noop`, `incomplete`, or `regression` baseline |
| `bugbench evaluate-patch` | Evaluate a local `.patch` file (no AI API needed) |
| `bugbench run-agent` | Execute an LLM provider or installed coding agent |
| `bugbench runs` | List recorded evaluation runs |
| `bugbench compare` | Compare several runs side by side |
| `bugbench export <run_id>` | Export a run to JSON / JSONL / CSV |
| `bugbench providers` | List, configure, or test AI providers |
| `bugbench serve` | Start the FastAPI backend and web dashboard |

---

## `bugbench list`

```bash
bugbench list
bugbench list --difficulty hard
bugbench list --category concurrency_races
bugbench list --search cache
bugbench list --json
```

| Option | Description |
| :--- | :--- |
| `-d, --difficulty` | `easy`, `medium`, or `hard` |
| `-c, --category` | e.g. `pagination_api`, `cache_expiration`, `concurrency_races` |
| `-s, --search` | Free-text keyword match over id, title, summary, and package |
| `--json` | Emit machine-readable JSON instead of a table |

## `bugbench inspect <task_id>`

```bash
bugbench inspect pagiflow-001
bugbench inspect pagiflow-001 --json
```

Prints the full issue report, allowed modifiable files, base revision, test
suite hash, and reproduction instructions. Exit code `2` if the task is unknown.

## `bugbench validate`

```bash
bugbench validate
bugbench validate --sandbox docker --repeat 2
bugbench validate --task pagiflow-001 --output dataset_validation.json
```

Runs the 8 quality gates per task and writes a machine-readable report.
**Exits non-zero if any task fails a gate**, so it is usable as a CI gate.

| Option | Description |
| :--- | :--- |
| `-t, --task` | Validate only specific task IDs (repeatable) |
| `-r, --repeat` | Isolated repeat runs used by the stability gate (default `2`) |
| `--sandbox` | `auto`, `docker`, `bwrap`, `subprocess` |
| `-o, --output` | Write the JSON report to a file |

The 8 gates are documented in [`docs/BENCHMARK_SPEC.md`](BENCHMARK_SPEC.md).

## `bugbench reference`

```bash
bugbench reference
bugbench reference --workers 4 --sandbox docker
```

Evaluates the verified reference solution for every selected task. This is the
*oracle*: it must resolve 100% of tasks, otherwise the dataset is broken.
**Exits non-zero if the resolution rate is not 100%.**

## `bugbench baseline --mode <mode>`

```bash
bugbench baseline --mode noop
bugbench baseline --mode incomplete --workers 4
bugbench baseline --mode regression --sandbox docker
```

| Mode | Expected outcome | Purpose |
| :--- | :--- | :--- |
| `noop` | 0% resolved, 0 regressions | Proves the buggy revision really fails |
| `incomplete` | 0% resolved, 0 regressions | Proves partial fixes are rejected |
| `regression` | 0% resolved, regressions on every task | Proves careless fixes are caught |

## `bugbench evaluate-patch`

```bash
bugbench evaluate-patch --patch examples/sample_patches/pagiflow-001.patch
bugbench evaluate-patch --patch my-fixes/ --task pagiflow-001
```

Evaluates a manually written or externally produced unified diff. This is the
fully **offline** path: no API key, no network, no model. The patch is applied
to a fresh checkout of the original buggy revision and graded exactly like an
agent submission.

## `bugbench run-agent`

```bash
bugbench run-agent --provider custom_openai --model my-model
bugbench run-agent --provider ollama --workers 3
bugbench run-agent --provider openai --max-cost 2.50
bugbench run-agent --provider codex_cli --task ttlcachex-002
```

| Option | Description |
| :--- | :--- |
| `--provider` | `openai`, `anthropic`, `openrouter`, `custom_openai`, `ollama`, `codex_cli`, `claude_code_cli`, `reference`, `noop`, `incomplete`, `regression`, `offline` |
| `--model` | Model ID. If omitted, it is auto-discovered from `/v1/models` and the selection is reported. |
| `--base-url` | Override the API base URL for this run |
| `--api-key` | Override the API key for this run (prefer the environment variable) |
| `-t, --task` | Restrict to specific task IDs (repeatable) |
| `-d, --difficulty` | Filter by difficulty |
| `-c, --category` | Filter by category |
| `-w, --workers` | Parallel tasks (1–8) |
| `--timeout` | Per-task timeout in seconds (default `60`) |
| `--max-cost` | Maximum USD spend for the run. `0` disables the cap. Only enforced when a price is known. |
| `--sandbox` | `auto`, `docker`, `bwrap`, `subprocess` |
| `--run-name` | Label stored with the run |
| `-o, --output` | Export the run report to a file |

## `bugbench runs`

```bash
bugbench runs
bugbench runs --provider custom_openai --status COMPLETED --limit 10
bugbench runs --json
```

## `bugbench compare`

```bash
bugbench compare --runs run-1234-abcd,run-5678-efgh
bugbench compare --json
```

With no `--runs`, the 20 most recent runs are compared.

## `bugbench export <run_id>`

```bash
bugbench export run-1234-abcd --format csv --output results.csv
bugbench export run-1234-abcd --format jsonl --output results.jsonl
```

| Format | Shape |
| :--- | :--- |
| `json` | One object with the full run summary and per-task results |
| `jsonl` | One JSON object per line (one per task result) |
| `csv` | One row per task result, flat columns |

## `bugbench providers`

```bash
bugbench providers                      # table of every adapter and its status
bugbench providers --presets            # the "easy connect" presets
bugbench providers --test ollama       # connectivity + model discovery
bugbench providers --test custom_openai --json
bugbench providers --configure openai --model gpt-4o --max-cost 2.00
bugbench providers --configure openai --input-cost-per-1k 0.0025 --output-cost-per-1k 0.01
```

| Option | Description |
| :--- | :--- |
| `--test <provider>` | Check reachability, authentication, and discover models |
| `--configure <provider>` | Persist settings for a provider |
| `--base-url` / `--api-key` / `--model` | Connection details |
| `--input-cost-per-1k` / `--output-cost-per-1k` | Manual USD rates, used when the provider does not publish its own |
| `--max-cost` | Per-run spend cap in USD (`0` disables) |
| `--use-builtin-estimates` | Allow the bundled, clearly-labelled price estimates |
| `--presets` | Print the connection presets and exit |
| `--json` | Machine-readable output |

Settings are written to `artifacts/tmp/provider_settings.json` with `0600`
permissions. Secrets are redacted from all logs and exports.

## `bugbench serve`

```bash
bugbench serve
bugbench serve --host 0.0.0.0 --port 8080
```

Starts the FastAPI backend and the dashboard at `http://localhost:8000`.

---

## Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | Success |
| `1` | A quality gate or reference-oracle check failed |
| `2` | Bad usage (unknown task, missing patch file, unknown provider) |

## Environment variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `BUGBENCH_DB_URL` | `sqlite:///artifacts/bugbench.db` | Database location |
| `BUGBENCH_BENCHMARKS_DIR` | `benchmarks` | Benchmark dataset root |
| `BUGBENCH_PRIVATE_TESTS_DIR` | `private_evaluations` | Confidential test root |
| `BUGBENCH_ARTIFACTS_DIR` | `artifacts` | Run artifacts root |
| `BUGBENCH_SANDBOX_MODE` | `auto` | `auto`, `docker`, `bwrap`, `subprocess` |
| `BUGBENCH_DOCKER_IMAGE` | `software-bug-repair-benchmark-runner:latest` | Runner image |
| `BUGBENCH_DEFAULT_TIMEOUT_SECONDS` | `60` | Per-suite timeout |
| `BUGBENCH_MEMORY_LIMIT_MB` | `512` | Container memory limit |
| `BUGBENCH_CPU_LIMIT` | `1.0` | Container CPU quota |
| `BUGBENCH_MAX_PIDS` | `64` | Container process limit |
| `BUGBENCH_NETWORK_DISABLED` | `true` | Disable network inside sandboxes |
| `BUGBENCH_MAX_COST_USD` | `5.00` | Default per-run spend cap |
| `BUGBENCH_LOG_LEVEL` | `INFO` | Logging verbosity |
