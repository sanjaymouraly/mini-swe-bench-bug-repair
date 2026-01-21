# Benchmark Task Specification & Authoring Guide

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

---

## 1. The 12 Curated Benchmark Tasks

| Task ID | Package | Category | Difficulty | Allowed Modifiable File | Base Git SHA | Bug Summary |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `pagiflow-001` | `pagiflow` | `pagination_api` | Easy | `src/pagiflow/client.py` | `164e51624d3e` | Falsy `next_cursor=0` terminates pagination after page 1; `has_more=False` with echoed cursor loops until `max_pages`. |
| `ttlcachex-002` | `ttlcachex` | `cache_expiration` | Easy | `src/ttlcachex/cache.py` | `5ada1827a6cd` | `get_many()` and `__contains__()` bypass TTL expiration checks; `set(..., keep_ttl=True)` resets existing expiration. |
| `concurqueue-003` | `concurqueue` | `concurrency_races` | Hard | `src/concurqueue/pool.py` | `4b0b1a5ad48b` | Lock released between capacity check and counter increment allows over-allocation; `notify()` causes lost wakeups across keys. |
| `ledgersql-004` | `ledgersql` | `sqlite_transactions` | Medium | `src/ledgersql/ledger.py` | `2c11583af21c` | Failed batch transfer leaves partial debit and in-memory sequence drift; `allow_partial=True` rolls back entire transaction instead of per-item `SAVEPOINT`. |
| `chronoshift-005` | `chronoshift` | `timezone_dst` | Hard | `src/chronoshift/scheduler.py` | `2108290bab24` | Adding `timedelta(days=N)` in UTC shifts local wall-clock hour across DST transitions; spring-forward nonexistent times are not rolled forward. |
| `streamparse-006` | `streamparse` | `streaming_parser` | Medium | `src/streamparse/parser.py` | `5d9fdb6c51de` | Escaped quotes (`\"`) break CSV field tokenizer; `skip_malformed=True` fails to reset multiline buffer after unclosed quote. |
| `confighier-007` | `confighier` | `config_precedence` | Easy | `src/confighier/loader.py` | `80e78ad4aab0` | Shallow `.update()` wipes sibling nested keys; falsy CLI overrides (`0`, `False`, `""`) are ignored; single underscores in env keys are split into nested dicts. |
| `retryguard-008` | `retryguard` | `retry_ratelimit` | Medium | `src/retryguard/policy.py` | `5b34c261230c` | `max_retries` treated as total attempts (off-by-one); `429 Retry-After` header ignored in favor of exponential backoff; `full_jitter` exceeds `max_delay`. |
| `schemaver-009` | `schemaver` | `serialization_compat` | Medium | `src/schemaver/codec.py` | `533f4da0afeb` | v1-to-v2 upcaster drops unknown extensions, mutates caller dictionary in place, and converts `amount_cents=0` to `None`. |
| `cliwarden-010` | `cliwarden` | `cli_validation` | Easy | `src/cliwarden/runner.py` | `f3f538a41081` | `--dry-run` short-circuits before flag validation; usage errors return exit code `1` on `stdout` instead of `2` on `stderr`; `KeyboardInterrupt` returns `1` instead of `130`. |
| `idempobox-011` | `idempobox` | `idempotency` | Hard | `src/idempobox/processor.py` | `62ebe35109c0` | Reused key with mutated payload returns cached result instead of `IdempotencyConflictError`; dict key order changes fingerprint; handler exception permanently locks key as `IN_PROGRESS`. |
| `atomicvault-012` | `atomicvault` | `atomic_file_ops` | Hard | `src/atomicvault/storage.py` | `8c37ed974430` | `put()` moves live target to `.bak` before temp write completes (destroying live file on mid-stream error); `recover()` ignores `.tmp`/`.bak` files; nested `..` bypasses path check. |

---

## 2. The 8 Automated Dataset Quality Gates

Every task in `benchmarks/<task_id>/` must pass all 8 automated checks in `bugbench validate`:

1. **`1_repo_installs_and_runs`**: Original buggy repository imports cleanly and collects both `PASS_TO_PASS` and `FAIL_TO_PASS` test suites.
2. **`2_pre_existing_tests_pass`**: All pre-existing preservation tests (`tests/test_existing.py`) pass on the unmodified buggy revision.
3. **`3_issue_tests_fail_before_repair`**: At least one issue-reproducing test (`evaluation/test_issue.py`) fails on the unmodified buggy revision.
4. **`4_reference_patch_resolves_all`**: Applying `patches/reference.patch` passes `PatchValidator` integrity checks and resolves 100% of `PASS_TO_PASS`, `FAIL_TO_PASS`, and confidential `PRIVATE` tests (`private_evaluations/<task_id>/test_private.py`).
5. **`5_noop_baseline_fails`**: Submitting an empty patch produces `ResolutionStatus.NO_CHANGES` (`resolved=False`).
6. **`6_incomplete_patch_rejected`**: Applying `patches/incomplete.patch` leaves at least one `FAIL_TO_PASS` or `PRIVATE` test failing (`resolved=False`).
7. **`7_regression_patch_detected`**: Applying `patches/regression.patch` breaks at least one `PASS_TO_PASS` preservation test and is classified as `ResolutionStatus.REGRESSION` (`has_regression=True`, `resolved=False`).
8. **`8_deterministic_across_repeated_runs`**: Repeated isolated evaluations of `patches/reference.patch` produce identical test counts and pass/fail outcomes.

---

## 3. Task Directory Layout

```text
benchmarks/<task_id>/
├── task.json                 # machine-readable metadata (see below)
├── issue.md                  # the issue report handed to the agent
├── repo/                     # the buggy repository, as a standalone package
│   ├── pyproject.toml
│   ├── README.md
│   ├── src/<package>/...     # the code the agent may modify
│   └── tests/test_existing.py# PASS_TO_PASS preservation suite
├── evaluation/
│   └── test_issue.py         # FAIL_TO_PASS issue-reproduction suite
└── patches/
    ├── reference.patch       # the verified fix
    ├── incomplete.patch      # a partial fix (must be rejected)
    └── regression.patch      # a fix that breaks preservation tests

private_evaluations/<task_id>/
└── test_private.py           # PRIVATE boundary / property suite
```

The `repo/` directory contains **no** `.git` directory in Git. The base
revision is recreated deterministically on demand by `ensure_task_git_repo()`,
so the recorded `base_revision` SHA is always reproducible.

## 4. `task.json` Schema

```json
{
  "task_id": "pagiflow-001",
  "title": "Fix cursor=0 falsy termination and has_more=False echo loops",
  "difficulty": "easy",
  "category": "pagination_api",
  "package_name": "pagiflow",
  "summary": "One-paragraph description of the defect.",
  "issue_description": "# Issue: ...\n\n## Description ...",
  "reproduction_instructions": "pytest evaluation/test_issue.py -q",
  "pinned_environment": {
    "python_version": "3.12",
    "dependencies": ["pytest>=8.3.0"],
    "test_command": "pytest -q",
    "docker_image": "software-bug-repair-benchmark-runner:latest"
  },
  "base_revision": "164e51624d3e0b4cf9af0d086e8a5d4137ddae90",
  "allowed_files": ["src/pagiflow/client.py", "src/pagiflow/cursor.py", "src/pagiflow/models.py"],
  "pass_to_pass_tests": ["tests/test_existing.py"],
  "fail_to_pass_tests": ["evaluation/test_issue.py"],
  "private_tests": ["private_evaluations/pagiflow-001/test_private.py"],
  "test_suite_hash": "6d28c10cb437b6a4d2269ccc9b43fec59b601fc1145b358c4ea5577a8af9e2b3",
  "reference_patch_hash": "9a8bc414ec58dc51686af94d4b23441887dbd5bcf7965cdd9cc176da084fff7f"
}
```

`difficulty` is one of `easy` / `medium` / `hard`.
`category` is one of `pagination_api`, `cache_expiration`, `concurrency_races`,
`sqlite_transactions`, `timezone_dst`, `streaming_parser`, `config_precedence`,
`retry_ratelimit`, `serialization_compat`, `cli_validation`, `idempotency`,
`atomic_file_ops`.

## 5. Test Suite Design Rules

The three suites are deliberately separated so that the grader can tell the
difference between "fixed the bug" and "broke something else":

- **`PASS_TO_PASS`** — pre-existing behaviour that must survive the patch. These
  tests pass on the buggy revision, so a patch that breaks them has introduced
  a regression.
- **`FAIL_TO_PASS`** — the issue itself. These fail before the fix and must
  pass after it. They are published in the repository under `evaluation/`;
  they are **not** confidential.
- **`PRIVATE`** — boundary, property-based, and adversarial cases that are not
  published. They exist to stop a patch from special-casing the visible
  assertions.

> **Honesty note.** Anything under `benchmarks/` is public once the repository
> is published, and the README says so plainly. `private_evaluations/` is
> stored separately so a *confidential* run can be performed, but a published
> GitHub checkout cannot keep a secret. Mini SWE-Bench does not pretend
> otherwise.

Tests should be deterministic. Avoid wall-clock dependencies, random seeds
without an explicit seed, and network access.

---

## 6. Adding a New Benchmark Task

The 12 tasks are generated from a single source of truth so the dataset can be
rebuilt byte-for-byte:

```text
scripts/benchmark_defs/
├── part1.py   # tasks 001-004
├── part2.py   # tasks 005-008
├── part3.py   # tasks 009-012
└── __init__.py  # ALL_TASKS
```

To add a task:

1. Append a task definition to the appropriate `part*.py`. Each definition
   contains:
   - `task_id`, `title`, `difficulty`, `category`, `package_name`, `summary`
   - `allowed_files`
   - `files` — the **buggy** source files
   - `existing_tests` — the `PASS_TO_PASS` suite
   - `issue_tests` — the `FAIL_TO_PASS` suite
   - `private_tests` — the `PRIVATE` suite
   - `issue_md` and `reproduction`
   - `reference_files`, `incomplete_files`, `regression_files` — the three
     patch variants, expressed as the *content* of the changed files
2. Regenerate the dataset:

   ```bash
   python scripts/bootstrap_repos.py
   ```

   This writes `benchmarks/`, `private_evaluations/`, and every `task.json`
   with recomputed hashes and base revisions.
3. Verify:

   ```bash
   bugbench validate --task <task_id> --sandbox docker
   ```

   All 8 gates must pass. The validation report is the acceptance criterion,
   not a human review.

4. Confirm the whole suite still behaves:

   ```bash
   bugbench reference            # must resolve 12+1 / 12+1
   bugbench baseline --mode noop  # must resolve 0 / 12+1
   ```

### Writing a good issue report

A good `issue.md` contains:

- A title that states the observable symptom, not the fix.
- A description of the **expected** vs. **actual** behaviour, with concrete
  input/output examples.
- The exact reproduction command.
- Any legitimate context (e.g. "0-indexed numeric cursors are valid").

It must **not** name the function to change, the line to change, or the
algorithm to use. The agent should have to find the defect.

### Writing the three patch variants

| Variant | Must |
| :--- | :--- |
| `reference` | Fix the issue completely, keep every preservation test green |
| `incomplete` | Look plausible, fix the obvious case, miss a boundary case (so a `FAIL_TO_PASS` or `PRIVATE` test still fails) |
| `regression` | Fix the issue but break at least one preservation test (so `has_regression` is true) |

A variant that accidentally resolves the task is a dataset bug: the validator
rejects the whole task rather than silently including it.
