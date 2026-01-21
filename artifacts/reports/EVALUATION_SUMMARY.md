# Mini SWE-Bench — Reproducible Evaluation Summary

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

Benchmark version `1.0.0`. Every row below is a run recorded in the local SQLite database (`artifacts/bugbench.db`) and can be reproduced with the command shown.

## Results at a glance

| Run | Adapter / Model | Sandbox | Resolved | Issue fixed | Regression-free | Patch valid | Tokens | Est. cost |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | ---: | ---: |
| Reference Oracle (Docker) | `reference-oracle` | `docker` | **12/12 (100.0%)** | 12/12 (100.0%) | 100.0% (0 reg) | 100.0% | n/a | n/a |
| Reference Oracle (Subprocess) | `reference-oracle` | `subprocess` | **12/12 (100.0%)** | 12/12 (100.0%) | 100.0% (0 reg) | 100.0% | n/a | n/a |
| No-Op Baseline (Docker) | `noop-baseline` | `docker` | **0/12 (0.0%)** | 0/12 (0.0%) | 100.0% (0 reg) | 0.0% | n/a | n/a |
| No-Op Baseline (Subprocess) | `noop-baseline` | `subprocess` | **0/12 (0.0%)** | 0/12 (0.0%) | 100.0% (0 reg) | 0.0% | n/a | n/a |
| Incomplete Patch Baseline | `incomplete-baseline` | `subprocess` | **0/12 (0.0%)** | 0/12 (0.0%) | 100.0% (0 reg) | 100.0% | n/a | n/a |
| Regression-Inducing Baseline | `regression-baseline` | `subprocess` | **0/12 (0.0%)** | 2/12 (16.67%) | 0.0% (12 reg) | 100.0% | n/a | n/a |
| Live Agent Suite | `custom_openai:minimax-m3.1-flash:free` | `docker` | **7/12 (58.33%)** | 7/12 (58.33%) | 100.0% (0 reg) | 66.67% | 45200 | $0.0000 |
| Live Agent Retry (provider outage) | `custom_openai:minimax-m3.1-flash:free` | `docker` | **0/4 (0.0%)** | 0/4 (0.0%) | 100.0% (0 reg) | 0.0% | n/a | n/a |

## What each baseline proves

- **Reference Oracle** — the verified fix resolves every task with no regressions. If this is not 100%, the dataset is broken.
- **No-Op Baseline** — the unmodified buggy revision resolves nothing. This proves the issue tests genuinely fail before repair.
- **Incomplete Patch Baseline** — a partial fix that misses a boundary case is rejected, so the private evaluation suite is doing its job.
- **Regression-Inducing Baseline** — a fix that breaks existing behaviour is caught and classified as `REGRESSION`, never as resolved.
- **Live Agent Suite** — a real model given only the repository and the issue report. Its patches are graded by exactly the same pipeline.

---

# Benchmark Evaluation Report: Reference Oracle Baseline

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

## Summary Metrics

| Metric | Value |
| :--- | :--- |
| **Run ID** | `run-1792585944-178e13` |
| **Agent / Adapter** | `reference-oracle` (`offline` / `reference`) |
| **Sandbox Mode** | `docker` |
| **Status** | `COMPLETED` |
| **Resolved Tasks** | **12 / 12 (100.00%)** |
| **Issue-Fix Rate** | 12 / 12 (100.00%) |
| **Regression-Free Rate** | 100.00% (0 regressions) |
| **Patch Applicability** | 100.00% |
| **Integrity Violations** | 0 |
| **Execution Failures** | 0 |
| **Total Duration** | 30053.2 ms |
| **Total Tokens** | n/a |
| **Estimated Cost** | n/a (unmeasured) |

## Per-Task Breakdown

| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS | Private | Regression | Time (ms) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |
| `atomicvault-012` | hard | `atomic_file_ops` | **RESOLVED** | 3/3 | 1/1 | 1/1 | NO | 10478 |
| `chronoshift-005` | hard | `timezone_dst` | **RESOLVED** | 2/2 | 3/3 | 1/1 | NO | 10840 |
| `cliwarden-010` | easy | `cli_validation` | **RESOLVED** | 2/2 | 2/2 | 1/1 | NO | 9582 |
| `concurqueue-003` | hard | `concurrency_races` | **RESOLVED** | 2/2 | 3/3 | 1/1 | NO | 8777 |
| `confighier-007` | easy | `config_precedence` | **RESOLVED** | 1/1 | 2/2 | 1/1 | NO | 9774 |
| `idempobox-011` | hard | `idempotency` | **RESOLVED** | 3/3 | 2/2 | 1/1 | NO | 8840 |
| `ledgersql-004` | medium | `sqlite_transactions` | **RESOLVED** | 2/2 | 2/2 | 2/2 | NO | 9357 |
| `pagiflow-001` | easy | `pagination_api` | **RESOLVED** | 3/3 | 4/4 | 2/2 | NO | 9429 |
| `retryguard-008` | medium | `retry_ratelimit` | **RESOLVED** | 3/3 | 3/3 | 1/1 | NO | 10595 |
| `schemaver-009` | medium | `serialization_compat` | **RESOLVED** | 3/3 | 3/3 | 1/1 | NO | 9370 |
| `streamparse-006` | medium | `streaming_parser` | **RESOLVED** | 2/2 | 3/3 | 1/1 | NO | 9387 |
| `ttlcachex-002` | easy | `cache_expiration` | **RESOLVED** | 3/3 | 4/4 | 2/2 | NO | 9001 |

## Notes

- `Resolved` requires the issue tests to pass, every preservation test to remain green, the private evaluation suite to pass, and the patch to be applicable and integrity-clean.
- A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.
- No cost is reported because the provider did not return a usable price alongside real token usage. Unmeasured is not the same as free.

---

# Benchmark Evaluation Report: Reference Oracle Baseline

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

## Summary Metrics

| Metric | Value |
| :--- | :--- |
| **Run ID** | `run-1792586281-540613` |
| **Agent / Adapter** | `reference-oracle` (`offline` / `reference`) |
| **Sandbox Mode** | `subprocess` |
| **Status** | `COMPLETED` |
| **Resolved Tasks** | **12 / 12 (100.00%)** |
| **Issue-Fix Rate** | 12 / 12 (100.00%) |
| **Regression-Free Rate** | 100.00% (0 regressions) |
| **Patch Applicability** | 100.00% |
| **Integrity Violations** | 0 |
| **Execution Failures** | 0 |
| **Total Duration** | 13145.8 ms |
| **Total Tokens** | n/a |
| **Estimated Cost** | n/a (unmeasured) |

## Per-Task Breakdown

| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS | Private | Regression | Time (ms) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |
| `atomicvault-012` | hard | `atomic_file_ops` | **RESOLVED** | 3/3 | 1/1 | 1/1 | NO | 5020 |
| `chronoshift-005` | hard | `timezone_dst` | **RESOLVED** | 2/2 | 3/3 | 1/1 | NO | 3799 |
| `cliwarden-010` | easy | `cli_validation` | **RESOLVED** | 2/2 | 2/2 | 1/1 | NO | 3991 |
| `concurqueue-003` | hard | `concurrency_races` | **RESOLVED** | 2/2 | 3/3 | 1/1 | NO | 4486 |
| `confighier-007` | easy | `config_precedence` | **RESOLVED** | 1/1 | 2/2 | 1/1 | NO | 5055 |
| `idempobox-011` | hard | `idempotency` | **RESOLVED** | 3/3 | 2/2 | 1/1 | NO | 4065 |
| `ledgersql-004` | medium | `sqlite_transactions` | **RESOLVED** | 2/2 | 2/2 | 2/2 | NO | 4070 |
| `pagiflow-001` | easy | `pagination_api` | **RESOLVED** | 3/3 | 4/4 | 2/2 | NO | 4896 |
| `retryguard-008` | medium | `retry_ratelimit` | **RESOLVED** | 3/3 | 3/3 | 1/1 | NO | 3938 |
| `schemaver-009` | medium | `serialization_compat` | **RESOLVED** | 3/3 | 3/3 | 1/1 | NO | 3325 |
| `streamparse-006` | medium | `streaming_parser` | **RESOLVED** | 2/2 | 3/3 | 1/1 | NO | 3443 |
| `ttlcachex-002` | easy | `cache_expiration` | **RESOLVED** | 3/3 | 4/4 | 2/2 | NO | 2374 |

## Notes

- `Resolved` requires the issue tests to pass, every preservation test to remain green, the private evaluation suite to pass, and the patch to be applicable and integrity-clean.
- A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.
- No cost is reported because the provider did not return a usable price alongside real token usage. Unmeasured is not the same as free.

---

# Benchmark Evaluation Report: Baseline (NOOP)

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

## Summary Metrics

| Metric | Value |
| :--- | :--- |
| **Run ID** | `run-1792586074-9c6fca` |
| **Agent / Adapter** | `noop-baseline` (`offline` / `noop`) |
| **Sandbox Mode** | `docker` |
| **Status** | `COMPLETED` |
| **Resolved Tasks** | **0 / 12 (0.00%)** |
| **Issue-Fix Rate** | 0 / 12 (0.00%) |
| **Regression-Free Rate** | 100.00% (0 regressions) |
| **Patch Applicability** | 0.00% |
| **Integrity Violations** | 0 |
| **Execution Failures** | 0 |
| **Total Duration** | 30213.3 ms |
| **Total Tokens** | n/a |
| **Estimated Cost** | n/a (unmeasured) |

## Per-Task Breakdown

| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS | Private | Regression | Time (ms) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |
| `atomicvault-012` | hard | `atomic_file_ops` | **NO_CHANGES** | 0/3 | 1/1 | 0/1 | NO | 11354 |
| `chronoshift-005` | hard | `timezone_dst` | **NO_CHANGES** | 0/2 | 3/3 | 0/1 | NO | 8556 |
| `cliwarden-010` | easy | `cli_validation` | **NO_CHANGES** | 0/2 | 2/2 | 0/1 | NO | 11687 |
| `concurqueue-003` | hard | `concurrency_races` | **NO_CHANGES** | 1/2 | 3/3 | 0/1 | NO | 10122 |
| `confighier-007` | easy | `config_precedence` | **NO_CHANGES** | 0/1 | 2/2 | 0/1 | NO | 9450 |
| `idempobox-011` | hard | `idempotency` | **NO_CHANGES** | 1/3 | 2/2 | 0/1 | NO | 8558 |
| `ledgersql-004` | medium | `sqlite_transactions` | **NO_CHANGES** | 0/2 | 2/2 | 1/2 | NO | 8954 |
| `pagiflow-001` | easy | `pagination_api` | **NO_CHANGES** | 0/3 | 4/4 | 1/2 | NO | 10760 |
| `retryguard-008` | medium | `retry_ratelimit` | **NO_CHANGES** | 0/3 | 3/3 | 0/1 | NO | 8532 |
| `schemaver-009` | medium | `serialization_compat` | **NO_CHANGES** | 0/3 | 3/3 | 0/1 | NO | 9757 |
| `streamparse-006` | medium | `streaming_parser` | **NO_CHANGES** | 0/2 | 3/3 | 0/1 | NO | 8387 |
| `ttlcachex-002` | easy | `cache_expiration` | **NO_CHANGES** | 0/3 | 4/4 | 2/2 | NO | 6956 |

## Notes

- `Resolved` requires the issue tests to pass, every preservation test to remain green, the private evaluation suite to pass, and the patch to be applicable and integrity-clean.
- A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.
- No cost is reported because the provider did not return a usable price alongside real token usage. Unmeasured is not the same as free.

---

# Benchmark Evaluation Report: Baseline (NOOP)

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

## Summary Metrics

| Metric | Value |
| :--- | :--- |
| **Run ID** | `run-1792586294-2a71db` |
| **Agent / Adapter** | `noop-baseline` (`offline` / `noop`) |
| **Sandbox Mode** | `subprocess` |
| **Status** | `COMPLETED` |
| **Resolved Tasks** | **0 / 12 (0.00%)** |
| **Issue-Fix Rate** | 0 / 12 (0.00%) |
| **Regression-Free Rate** | 100.00% (0 regressions) |
| **Patch Applicability** | 0.00% |
| **Integrity Violations** | 0 |
| **Execution Failures** | 0 |
| **Total Duration** | 10690.4 ms |
| **Total Tokens** | n/a |
| **Estimated Cost** | n/a (unmeasured) |

## Per-Task Breakdown

| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS | Private | Regression | Time (ms) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |
| `atomicvault-012` | hard | `atomic_file_ops` | **NO_CHANGES** | 0/3 | 1/1 | 0/1 | NO | 3203 |
| `chronoshift-005` | hard | `timezone_dst` | **NO_CHANGES** | 0/2 | 3/3 | 0/1 | NO | 3077 |
| `cliwarden-010` | easy | `cli_validation` | **NO_CHANGES** | 0/2 | 2/2 | 0/1 | NO | 3168 |
| `concurqueue-003` | hard | `concurrency_races` | **NO_CHANGES** | 1/2 | 3/3 | 0/1 | NO | 3275 |
| `confighier-007` | easy | `config_precedence` | **NO_CHANGES** | 0/1 | 2/2 | 0/1 | NO | 3500 |
| `idempobox-011` | hard | `idempotency` | **NO_CHANGES** | 1/3 | 2/2 | 0/1 | NO | 3407 |
| `ledgersql-004` | medium | `sqlite_transactions` | **NO_CHANGES** | 0/2 | 2/2 | 1/2 | NO | 3575 |
| `pagiflow-001` | easy | `pagination_api` | **NO_CHANGES** | 0/3 | 4/4 | 1/2 | NO | 3294 |
| `retryguard-008` | medium | `retry_ratelimit` | **NO_CHANGES** | 0/3 | 3/3 | 0/1 | NO | 3268 |
| `schemaver-009` | medium | `serialization_compat` | **NO_CHANGES** | 0/3 | 3/3 | 0/1 | NO | 3321 |
| `streamparse-006` | medium | `streaming_parser` | **NO_CHANGES** | 0/2 | 3/3 | 0/1 | NO | 3004 |
| `ttlcachex-002` | easy | `cache_expiration` | **NO_CHANGES** | 0/3 | 4/4 | 2/2 | NO | 3192 |

## Notes

- `Resolved` requires the issue tests to pass, every preservation test to remain green, the private evaluation suite to pass, and the patch to be applicable and integrity-clean.
- A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.
- No cost is reported because the provider did not return a usable price alongside real token usage. Unmeasured is not the same as free.

---

# Benchmark Evaluation Report: Baseline (INCOMPLETE)

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

## Summary Metrics

| Metric | Value |
| :--- | :--- |
| **Run ID** | `run-1792586306-acc858` |
| **Agent / Adapter** | `incomplete-baseline` (`offline` / `incomplete`) |
| **Sandbox Mode** | `subprocess` |
| **Status** | `COMPLETED` |
| **Resolved Tasks** | **0 / 12 (0.00%)** |
| **Issue-Fix Rate** | 0 / 12 (0.00%) |
| **Regression-Free Rate** | 100.00% (0 regressions) |
| **Patch Applicability** | 100.00% |
| **Integrity Violations** | 0 |
| **Execution Failures** | 0 |
| **Total Duration** | 10897.5 ms |
| **Total Tokens** | n/a |
| **Estimated Cost** | n/a (unmeasured) |

## Per-Task Breakdown

| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS | Private | Regression | Time (ms) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |
| `atomicvault-012` | hard | `atomic_file_ops` | **UNRESOLVED** | 2/3 | 1/1 | 0/1 | NO | 3328 |
| `chronoshift-005` | hard | `timezone_dst` | **UNRESOLVED** | 1/2 | 3/3 | 1/1 | NO | 3126 |
| `cliwarden-010` | easy | `cli_validation` | **UNRESOLVED** | 1/2 | 2/2 | 0/1 | NO | 3204 |
| `concurqueue-003` | hard | `concurrency_races` | **UNRESOLVED** | 1/2 | 3/3 | 0/1 | NO | 3605 |
| `confighier-007` | easy | `config_precedence` | **UNRESOLVED** | 0/1 | 2/2 | 1/1 | NO | 3771 |
| `idempobox-011` | hard | `idempotency` | **UNRESOLVED** | 1/3 | 2/2 | 0/1 | NO | 3716 |
| `ledgersql-004` | medium | `sqlite_transactions` | **UNRESOLVED** | 1/2 | 2/2 | 0/2 | NO | 3824 |
| `pagiflow-001` | easy | `pagination_api` | **UNRESOLVED** | 2/3 | 4/4 | 0/2 | NO | 3125 |
| `retryguard-008` | medium | `retry_ratelimit` | **UNRESOLVED** | 1/3 | 3/3 | 0/1 | NO | 3313 |
| `schemaver-009` | medium | `serialization_compat` | **UNRESOLVED** | 2/3 | 3/3 | 0/1 | NO | 3263 |
| `streamparse-006` | medium | `streaming_parser` | **UNRESOLVED** | 1/2 | 3/3 | 0/1 | NO | 3339 |
| `ttlcachex-002` | easy | `cache_expiration` | **UNRESOLVED** | 2/3 | 4/4 | 2/2 | NO | 3154 |

## Notes

- `Resolved` requires the issue tests to pass, every preservation test to remain green, the private evaluation suite to pass, and the patch to be applicable and integrity-clean.
- A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.
- No cost is reported because the provider did not return a usable price alongside real token usage. Unmeasured is not the same as free.

---

# Benchmark Evaluation Report: Baseline (REGRESSION)

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

## Summary Metrics

| Metric | Value |
| :--- | :--- |
| **Run ID** | `run-1792586317-07d0de` |
| **Agent / Adapter** | `regression-baseline` (`offline` / `regression`) |
| **Sandbox Mode** | `subprocess` |
| **Status** | `COMPLETED` |
| **Resolved Tasks** | **0 / 12 (0.00%)** |
| **Issue-Fix Rate** | 2 / 12 (16.67%) |
| **Regression-Free Rate** | 0.00% (12 regressions) |
| **Patch Applicability** | 100.00% |
| **Integrity Violations** | 0 |
| **Execution Failures** | 0 |
| **Total Duration** | 10854.1 ms |
| **Total Tokens** | n/a |
| **Estimated Cost** | n/a (unmeasured) |

## Per-Task Breakdown

| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS | Private | Regression | Time (ms) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |
| `atomicvault-012` | hard | `atomic_file_ops` | **REGRESSION** | 1/3 | 0/1 | 0/1 | YES | 3316 |
| `chronoshift-005` | hard | `timezone_dst` | **REGRESSION** | 1/2 | 2/3 | 0/1 | YES | 3488 |
| `cliwarden-010` | easy | `cli_validation` | **REGRESSION** | 0/2 | 0/2 | 1/1 | YES | 3223 |
| `concurqueue-003` | hard | `concurrency_races` | **REGRESSION** | 2/2 | 2/3 | 0/1 | YES | 3558 |
| `confighier-007` | easy | `config_precedence` | **REGRESSION** | 0/1 | 1/2 | 1/1 | YES | 3322 |
| `idempobox-011` | hard | `idempotency` | **REGRESSION** | 1/3 | 0/2 | 0/1 | YES | 5541 |
| `ledgersql-004` | medium | `sqlite_transactions` | **REGRESSION** | 2/2 | 1/2 | 1/2 | YES | 3385 |
| `pagiflow-001` | easy | `pagination_api` | **REGRESSION** | 3/3 | 2/4 | 1/2 | YES | 3223 |
| `retryguard-008` | medium | `retry_ratelimit` | **REGRESSION** | 0/3 | 2/3 | 0/1 | YES | 2791 |
| `schemaver-009` | medium | `serialization_compat` | **REGRESSION** | 3/3 | 1/3 | 1/1 | YES | 2812 |
| `streamparse-006` | medium | `streaming_parser` | **REGRESSION** | 2/2 | 1/3 | 0/1 | YES | 2702 |
| `ttlcachex-002` | easy | `cache_expiration` | **REGRESSION** | 3/3 | 3/4 | 2/2 | YES | 1595 |

## Notes

- `Resolved` requires the issue tests to pass, every preservation test to remain green, the private evaluation suite to pass, and the patch to be applicable and integrity-clean.
- A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.
- No cost is reported because the provider did not return a usable price alongside real token usage. Unmeasured is not the same as free.

---

# Benchmark Evaluation Report: minimax-m3.1-flash:free (live agent suite v2)

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

## Summary Metrics

| Metric | Value |
| :--- | :--- |
| **Run ID** | `run-1792582959-546fb3` |
| **Agent / Adapter** | `custom_openai:minimax-m3.1-flash:free` (`custom_openai` / `minimax-m3.1-flash:free`) |
| **Sandbox Mode** | `docker` |
| **Status** | `COMPLETED` |
| **Resolved Tasks** | **7 / 12 (58.33%)** |
| **Issue-Fix Rate** | 7 / 12 (58.33%) |
| **Regression-Free Rate** | 100.00% (0 regressions) |
| **Patch Applicability** | 66.67% |
| **Integrity Violations** | 0 |
| **Execution Failures** | 0 |
| **Total Duration** | 1206345.0 ms |
| **Total Tokens** | 45200 |
| **Estimated Cost** | $0.000000 |

## Per-Task Breakdown

| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS | Private | Regression | Time (ms) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |
| `atomicvault-012` | hard | `atomic_file_ops` | **NO_CHANGES** | 0/0 | 0/0 | 0/0 | NO | 34 |
| `chronoshift-005` | hard | `timezone_dst` | **RESOLVED** | 2/2 | 3/3 | 1/1 | NO | 2724 |
| `cliwarden-010` | easy | `cli_validation` | **RESOLVED** | 2/2 | 2/2 | 1/1 | NO | 2954 |
| `concurqueue-003` | hard | `concurrency_races` | **RESOLVED** | 2/2 | 3/3 | 1/1 | NO | 2738 |
| `confighier-007` | easy | `config_precedence` | **RESOLVED** | 1/1 | 2/2 | 1/1 | NO | 2585 |
| `idempobox-011` | hard | `idempotency` | **UNRESOLVED** | 3/3 | 2/2 | 0/1 | NO | 3231 |
| `ledgersql-004` | medium | `sqlite_transactions` | **NO_CHANGES** | 0/0 | 0/0 | 0/0 | NO | 32 |
| `pagiflow-001` | easy | `pagination_api` | **RESOLVED** | 3/3 | 4/4 | 2/2 | NO | 2823 |
| `retryguard-008` | medium | `retry_ratelimit` | **RESOLVED** | 3/3 | 3/3 | 1/1 | NO | 3831 |
| `schemaver-009` | medium | `serialization_compat` | **NO_CHANGES** | 0/0 | 0/0 | 0/0 | NO | 33 |
| `streamparse-006` | medium | `streaming_parser` | **NO_CHANGES** | 0/0 | 0/0 | 0/0 | NO | 32 |
| `ttlcachex-002` | easy | `cache_expiration` | **RESOLVED** | 3/3 | 4/4 | 2/2 | NO | 2672 |

## Notes

- `Resolved` requires the issue tests to pass, every preservation test to remain green, the private evaluation suite to pass, and the patch to be applicable and integrity-clean.
- A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.

---

# Benchmark Evaluation Report: minimax-m3.1-flash:free (retry of gateway-failed tasks)

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

## Summary Metrics

| Metric | Value |
| :--- | :--- |
| **Run ID** | `run-1792584273-b3f2ac` |
| **Agent / Adapter** | `custom_openai:minimax-m3.1-flash:free` (`custom_openai` / `minimax-m3.1-flash:free`) |
| **Sandbox Mode** | `docker` |
| **Status** | `COMPLETED` |
| **Resolved Tasks** | **0 / 4 (0.00%)** |
| **Issue-Fix Rate** | 0 / 4 (0.00%) |
| **Regression-Free Rate** | 100.00% (0 regressions) |
| **Patch Applicability** | 0.00% |
| **Integrity Violations** | 0 |
| **Execution Failures** | 0 |
| **Total Duration** | 1206200.6 ms |
| **Total Tokens** | n/a |
| **Estimated Cost** | n/a (unmeasured) |

## Per-Task Breakdown

| Task ID | Difficulty | Category | Status | FAIL_TO_PASS | PASS_TO_PASS | Private | Regression | Time (ms) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | ---: |
| `atomicvault-012` | hard | `atomic_file_ops` | **NO_CHANGES** | 0/0 | 0/0 | 0/0 | NO | 57 |
| `ledgersql-004` | medium | `sqlite_transactions` | **NO_CHANGES** | 0/0 | 0/0 | 0/0 | NO | 58 |
| `schemaver-009` | medium | `serialization_compat` | **NO_CHANGES** | 0/0 | 0/0 | 0/0 | NO | 49 |
| `streamparse-006` | medium | `streaming_parser` | **NO_CHANGES** | 0/0 | 0/0 | 0/0 | NO | 41 |

## Notes

- `Resolved` requires the issue tests to pass, every preservation test to remain green, the private evaluation suite to pass, and the patch to be applicable and integrity-clean.
- A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.
- No cost is reported because the provider did not return a usable price alongside real token usage. Unmeasured is not the same as free.

---

## Reproducing these numbers

```bash
# Every baseline is fully offline and needs no API key.
bugbench validate --sandbox docker
bugbench reference --sandbox docker --workers 4
bugbench baseline --mode noop --sandbox docker --workers 4
bugbench baseline --mode incomplete --sandbox docker --workers 4
bugbench baseline --mode regression --sandbox docker --workers 4

# Agent mode needs a provider; the model is auto-discovered if omitted.
bugbench run-agent --provider custom_openai --sandbox docker --workers 3
```

> A passing test suite is evidence for the behaviours it covers, not proof of universal correctness. These 12 tasks are a practice benchmark, not a complete specification of any real system.
