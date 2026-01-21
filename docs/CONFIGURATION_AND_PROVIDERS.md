# Configuration, Providers & Cost Control

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

---

## 1. Environment variables (`.env`)

Copy `.env.example` to `.env` and set only what you need. `.env` is
git-ignored, and no credential is ever hardcoded in the source.

### Core paths and storage

| Variable | Default | Description |
| :--- | :--- | :--- |
| `BUGBENCH_DB_URL` | `sqlite:///artifacts/bugbench.db` | Database location (`sqlite:///` prefix) |
| `BUGBENCH_BENCHMARKS_DIR` | `benchmarks` | Benchmark dataset root |
| `BUGBENCH_PRIVATE_TESTS_DIR` | `private_evaluations` | Confidential test root |
| `BUGBENCH_ARTIFACTS_DIR` | `artifacts` | Run artifacts and reports root |

### Sandbox execution

| Variable | Default | Description |
| :--- | :--- | :--- |
| `BUGBENCH_SANDBOX_MODE` | `auto` | `auto`, `docker`, `bwrap`, or `subprocess` |
| `BUGBENCH_DOCKER_IMAGE` | `software-bug-repair-benchmark-runner:latest` | Runner image name |
| `BUGBENCH_DEFAULT_TIMEOUT_SECONDS` | `60` | Per-suite execution timeout |
| `BUGBENCH_MEMORY_LIMIT_MB` | `512` | Container memory limit |
| `BUGBENCH_CPU_LIMIT` | `1.0` | Container CPU quota |
| `BUGBENCH_MAX_PIDS` | `64` | Container process limit |
| `BUGBENCH_NETWORK_DISABLED` | `true` | Disable network access inside sandboxes |

### Provider connection

| Provider | Key variable | Base URL variable | Model variable |
| :--- | :--- | :--- | :--- |
| `openai` | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `OPENAI_MODEL` |
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` | `ANTHROPIC_MODEL` |
| `openrouter` | `OPENROUTER_API_KEY` | `OPENROUTER_BASE_URL` | `OPENROUTER_MODEL` |
| `custom_openai` | `CUSTOM_OPENAI_API_KEY` | `CUSTOM_OPENAI_BASE_URL` | `CUSTOM_OPENAI_MODEL` |
| `ollama` | *(none)* | `OLLAMA_BASE_URL` | `OLLAMA_MODEL` |

The `codex_cli` and `claude_code_cli` adapters use the installed CLI's own
authentication and therefore need no variables here.

### Budgets

| Variable | Default | Description |
| :--- | :--- | :--- |
| `BUGBENCH_MAX_COST_USD` | `5.00` | Default per-run spend cap. `0` disables it. |
| `BUGBENCH_MAX_TOKENS` | `4096` | Maximum tokens per model response |
| `BUGBENCH_TEMPERATURE` | `0.0` | Default sampling temperature |
| `BUGBENCH_LOG_LEVEL` | `INFO` | Logging verbosity |

---

## 2. ChatGPT subscription vs. the OpenAI developer API

A consumer **ChatGPT Plus, Pro, or Team subscription** (`chatgpt.com`) is
billed separately from the **OpenAI developer API** (`platform.openai.com`) and
**does not include API credits**. The same applies to Claude Pro vs. the
Anthropic API.

Mini SWE-Bench uses only official provider APIs. It **never** performs browser
cookie extraction, session scraping, or unofficial subscription-to-API proxying.

If you want to avoid paid API credits entirely, use any of these:

1. **Offline patch mode** — `bugbench evaluate-patch --patch my.patch`
2. **Reference / baseline modes** — `bugbench reference`, `bugbench baseline`
3. **Local Ollama** — `bugbench run-agent --provider ollama --model qwen2.5:7b`
4. **OpenRouter free-tier models** — `bugbench run-agent --provider openrouter --model <free-model>`

---

## 3. Easy-connect presets

`bugbench providers --presets` (and the **Providers & Settings** dashboard tab)
list a one-click preset per provider:

| Preset | Default base URL | Key variable | Cost tier |
| :--- | :--- | :--- | :--- |
| ChatGPT / OpenAI API | `https://api.openai.com/v1` | `OPENAI_API_KEY` | paid |
| Claude API (Anthropic) | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | paid |
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | mixed |
| Custom OpenAI-compatible | *(you provide)* | `CUSTOM_OPENAI_API_KEY` | varies |
| Local Ollama | `http://localhost:11434/v1` | *(none)* | free |
| Codex CLI | *(installed CLI)* | *(its own)* | external |
| Claude Code CLI | *(installed CLI)* | *(its own)* | external |

**Cost tier** is a rough expectation, not a price:
`free` (local/self-hosted), `paid` (commercial API),
`mixed` (paid *and* free models), `varies` (your own gateway),
`external` (billed by the installed CLI, outside bugbench's accounting).

---

## 4. Automatic model discovery

When a base URL and key are configured but **no model is given**, Mini SWE-Bench
discovers the model instead of guessing:

1. `GET {base_url}/models` is queried (Ollama falls back to `/api/tags`).
2. Non-chat models are filtered out (`text-embedding-*`, `whisper-*`, `tts-*`,
   `dall-e-*`, `moderation-*`, `rerank-*`).
3. A code-capable model is preferred, using a preference order over known
   strong coding families.
4. The selection is **always reported** in the CLI output, the run log, and the
   dashboard — a model identifier is never invented or assumed.

```bash
bugbench providers --test custom_openai
```

```
Selected Model: my-model
Discovered Models: model-a, model-b, model-c
Message: Connected to https://gateway.example/v1; 3 model(s) available.
         Selected: my-model. Pricing: provider_discovery.
```

---

## 5. Cost control

### When is a cost reported?

A cost is reported **only** when both of these are true:

- the provider returned real token usage, and
- a price per 1,000 tokens is known.

Otherwise the cost is `null` (shown as **n/a**), never `0.00`. "Unmeasured" and
"free" are different things and are never conflated.

### Where prices come from

| Source | Label | Notes |
| :--- | :--- | :--- |
| Provider `/models` payload | `provider_discovery` | Most accurate; used automatically when the gateway publishes rates |
| Your own values | `manual` | `bugbench providers --configure ... --input-cost-per-1k ... --output-cost-per-1k ...` |
| Bundled table | `builtin_estimate` | **Opt-in**; clearly labelled because rates change frequently |

The bundled estimates cover common OpenAI and Anthropic models and are used
only when you explicitly enable them with `--use-builtin-estimates`.

Recognised provider fields include `input_cost_per_1k_tokens`,
`input_idr_per_1k`, `input_idr_per_1m`, and `input_cost_per_token`.

### Per-run spend cap

```bash
bugbench run-agent --provider custom_openai --max-cost 2.50
```

When the accumulated, accurately priced spend of a run reaches the cap, the
remaining tasks are skipped and the run is recorded with status
`STOPPED_BUDGET`. The cap is **not** enforced when no price is known — an
unpriced provider never silently burns budget.

### Where cost shows up

- CLI run summary panel: tokens and estimated cost
- Dashboard **Overview**: cumulative tokens and cost across all runs
- Dashboard **Comparison**: per-run cost column
- Run reports: `total_tokens` and `estimated_cost_usd` in JSON/JSONL/CSV

---

## 6. How the agent sees the repository

An agent never sees the answer. For every task, `EphemeralWorkspace(purpose="agent")`
provisions a fresh temporary directory containing only:

- `repo/` — the buggy checkout at the pinned base revision
- `ISSUE.md` — the issue report

The reference patch, the issue test suite, and the private test suite are
**never** mounted into the agent workspace. Grading then happens in a second,
completely separate checkout.

---

## 7. Installed CLI coding agents

```bash
bugbench run-agent --provider codex_cli
bugbench run-agent --provider claude_code_cli
```

These adapters shell out to the `codex` / `claude` binaries inside the
isolated agent workspace and collect the resulting `git diff`. They rely on the
CLI's own login state, so their cost is billed by the CLI, not by Mini
SWE-Bench; reported token counts and costs are `null` for these adapters.
