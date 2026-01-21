# Contributing to Mini SWE-Bench

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

Thank you for contributing to **Mini SWE-Bench** (`software-bug-repair-benchmark`)!

---

## 1. Development Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

The 12 benchmark tasks are committed to the repository, so the bootstrap step
is only needed after changing a task definition:

```bash
python scripts/bootstrap_repos.py
```

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) for the full Linux and
Windows PowerShell setup, including Docker.

---

## 2. Code Quality & Verification Standards

Every change must pass all five automated checks before submission:

```bash
# 1. Lint
ruff check src/ tests/ scripts/

# 2. Formatting
ruff format --check src/ tests/ scripts/

# 3. Static type checking
mypy src/bugbench

# 4. Framework unit, property-based, and integration tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -v tests/

# 5. 8-Point Dataset Quality Gate verification across all benchmark tasks
bugbench validate --output artifacts/reports/dataset_validation.json
```

CI runs the same checks (`.github/workflows/ci.yml`). The slower Docker-backed
gates live in a separate workflow
(`.github/workflows/docker-validation.yml`) so a normal PR does not pay for
them; run it locally with:

```bash
docker build --target runner -t software-bug-repair-benchmark-runner:latest -f Dockerfile .
bugbench validate --sandbox docker --repeat 2
```

---

## 3. Guidelines for New Benchmark Tasks

When contributing a new benchmark task, edit the canonical definition in
`scripts/benchmark_defs/part*.py` and regenerate the dataset with
`python scripts/bootstrap_repos.py`. See
[`docs/BENCHMARK_SPEC.md`](docs/BENCHMARK_SPEC.md) for the full authoring guide.

1. **100% Originality**: Tasks must be originally authored for Mini SWE-Bench.
   Never copy tasks or code from official SWE-bench datasets.
2. **Realistic Engineering Complexity**: Avoid trivial syntax errors or
   one-line constant typos. Include enough realistic surrounding behavior that
   careless fixes break `PASS_TO_PASS` preservation tests.
3. **Complete Patch Triplet**: Include `reference.patch` (resolves 100% of
   suites), `incomplete.patch` (fixes only part of the issue), and
   `regression.patch` (fixes the issue symptom while breaking existing
   functionality).
4. **Determinism**: Do not rely on wall-clock `time.time()` sleeps, external
   network calls, or unseeded randomness. Pass injectable clocks or
   deterministic fixtures.
5. **Objective acceptance criteria**: The issue must state the expected
   behaviour precisely enough that a test can verify it without ambiguity.
6. **No hardcoding escape hatches**: The task must not be solvable by
   special-casing the expected outputs.

---

## 4. Guidelines for Framework Changes

- Keep the module boundaries intact: `dataset/`, `agents/`, `grading/`,
  `sandbox/`, `orchestrator/`, `storage/`, `api/`, `cli/`.
- New behaviour needs a test. The suite has unit, property-based
  (Hypothesis), integration, and browser-level (Playwright) coverage.
- Never log a secret. Use `get_logger()` and `redact_secrets()` from
  `src/bugbench/logging_utils.py`; do not add a raw `print()` of configuration.
- Never commit credentials, `.env`, local paths, or generated run artifacts.
  Check `.gitignore` before adding files.

---

## 5. Reporting Results

If you publish benchmark results, please include:

- the `run_id` and the exact command used,
- the provider, model, and sandbox mode,
- the `benchmark_version`,
- the full exported report (JSON/JSONL/CSV).

Do not present Mini SWE-Bench scores as comparable to official SWE-bench
results. This is an independent practice benchmark with a different dataset
and a different grading model.

---

## 6. Pull Requests

Fill in the pull request template, make sure the checklist is satisfied, and
expect review comments focused on:

- dataset validity (the 8 gates must pass),
- regression safety (does the change preserve existing behaviour?),
- security (does it widen the trust boundary?).

---

## 7. Code of Conduct

Be respectful and constructive. Assume good faith. Discussions about benchmark
methodology are welcome; personal attacks are not.

---

## 8. License

Contributions are accepted under the [MIT License](LICENSE).
