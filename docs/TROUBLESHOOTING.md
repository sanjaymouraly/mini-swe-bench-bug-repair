# Troubleshooting Guide

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

---

## 1. Windows PowerShell execution policy

**Symptom**

```
.\.venv\Scripts\Activate.ps1 : File cannot be loaded because running scripts is disabled on this system.
```

**Fix** (one time, for your user only):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Close and reopen PowerShell, then activate again. You do **not** need to run
PowerShell as Administrator.

If you prefer not to change the policy at all, skip activation and call the
interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m bugbench.cli.main list
```

or install the console script into the venv and use its full path:

```powershell
.\.venv\Scripts\bugbench.exe list
```

---

## 2. `bugbench` is not recognised after activation

**Symptom**

```
The term 'bugbench' is not recognized as the name of a cmdlet.
```

**Fix**

The console script lives in `.venv\Scripts` (Windows) or `.venv/bin` (Linux).
Activate the environment, or add that directory to `PATH`:

```powershell
$env:PATH += ";$PWD\.venv\Scripts"
```

---

## 3. Docker Desktop is installed but the daemon is unreachable

**Symptom**

```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock.
```

or, from the dashboard, every task fails with `ENV_ERROR`.

**Fix**

1. Start Docker Desktop and wait until it reports **Engine running**.
2. On Windows, confirm the WSL 2 backend is enabled in Docker Desktop settings.
3. Verify with `docker info`.

**Linux only** — add your user to the `docker` group:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

---

## 4. Docker Desktop cannot see the project directory (Windows)

**Symptom**

The container starts but the workspace mount is empty, and tasks fail with
collection errors or `ENV_ERROR`.

**Fix**

Docker Desktop only shares specific drives. Open
**Settings → Resources → File sharing** and add the drive that contains the
repository (usually `C:\`).

---

## 5. `docker: command not found` / image not found

**Symptom**

```
The selected sandbox mode is 'docker' but the image
'software-bug-repair-benchmark-runner:latest' is not available.
```

**Fix**

Build the runner image:

```bash
docker build --target runner -t software-bug-repair-benchmark-runner:latest -f Dockerfile .
```

Check what is present:

```bash
docker images | grep software-bug-repair
```

---

## 6. The Docker build fails while downloading from PyPI

**Symptom**

```
ERROR: Could not install packages due to an OSError:
HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Max retries exceeded
```

**Cause** — a slow or interrupted connection to PyPI, not a code problem.

**Fix** — retry the build. The Dockerfile already uses
`--retries 10` and a 120 s pip timeout for this reason:

```bash
docker build --target runner -t software-bug-repair-benchmark-runner:latest -f Dockerfile .
```

If your network needs a mirror, set it for the build:

```bash
docker build --build-arg PIP_INDEX_URL=https://your-mirror/simple \
  --target runner -t software-bug-repair-benchmark-runner:latest -f Dockerfile .
```

---

## 7. `bugbench validate` fails on a task

**Symptom** — a row in the report shows fewer than `8/8` gates.

**Read the failing gate first.** The report stores the reason for each check:

```bash
bugbench validate --task <task_id> --sandbox docker -o report.json
python -c "import json;d=json.load(open('report.json'));[print(c['check_id'],c['passed'],c['details']) for c in d['task_reports'][0]['checks']]"
```

The usual causes:

| Gate | Typical cause |
| :--- | :--- |
| `2_pass_to_pass_on_buggy` | The "buggy" revision already fails a preservation test — the source and the test disagree |
| `3_fail_to_pass_fails_before_repair` | The issue test does not actually reproduce the bug |
| `4_reference_patch_applies_cleanly` | The reference patch was regenerated against a different base revision |
| `5_reference_patch_passes_all_tests` | The reference fix is incomplete or breaks a preservation test |
| `7_negative_patches_rejected` | The `incomplete` or `regression` variant accidentally resolves the task |
| `8_repeat_run_stability` | A test is non-deterministic (wall clock, random seed, network) |

Regenerate the dataset after fixing the definitions:

```bash
python scripts/bootstrap_repos.py
bugbench validate --sandbox docker
```

---

## 8. Every task reports `INVALID_PATCH`

**Symptom** — `Patch does not apply cleanly to base revision`.

**Causes and fixes**

- The patch was generated against a different revision. The grader always
  applies to the pinned base revision, so an agent must start from the exact
  buggy state.
- Line endings differ. On Windows, ensure `core.autocrlf=false` (the workspace
  provisioner sets it) and that the patch uses LF endings.
- The patch touches files outside `task.allowed_files`. The error lists the
  offending paths.

---

## 9. Every task reports `INTEGRITY_VIOLATION`

**Symptom** — `Test or configuration tampering detected` or
`Unauthorized file modification`.

The patch touched something it should not have:

- `tests/*`, `test_*.py`, `conftest.py`
- `pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`
- `task.json`, `evaluation/*`, `private_evaluations/*`
- any path outside `task.allowed_files`

The grader also rejects obvious evaluation shortcuts, such as
`pytest.skip(...)`, `os._exit(0)`, reading `PYTEST_CURRENT_TEST`, or
introspecting the call stack.

---

## 10. The agent produces `NO_CHANGES`

**Symptom** — the run reports `No code changes were generated or submitted`.

**Causes**

- The model returned prose instead of code. Check the run log
  (`bugbench runs` then the dashboard **Run Evaluation** tab) — the agent log
  records what the model actually returned.
- The model's diff had hunk line counts that did not match. Mini SWE-Bench
  recovers from this automatically with `git apply --recount`, a three-way
  merge, and GNU `patch`, but a response that is not a diff at all cannot be
  recovered.
- The provider returned an empty response. The adapter retries once and then
  records the provider error in the agent log.

**Workaround** — make the response format explicit in the prompt, or use a
model that follows the file-block format. The built-in prompt already asks for
complete replacement files in a ` ```python:src/pkg/mod.py ` block.

---

## 11. A provider reports `401` or `403`

**Symptom** — `bugbench providers --test <provider>` shows
`reachable: true, authenticated: false`.

**Fix**

- Check the key: `echo $OPENAI_API_KEY` (Windows: `$env:OPENAI_API_KEY`).
- Confirm you are using the API key, not a session cookie. Mini SWE-Bench
  never extracts cookies from a browser.
- A **ChatGPT Plus/Pro subscription does not include API credits.** You need a
  key from `platform.openai.com`.
- Confirm the base URL matches the provider: OpenAI is
  `https://api.openai.com/v1`, Anthropic is `https://api.anthropic.com`
  (no `/v1` suffix — the adapter adds the path).

---

## 12. `bugbench providers --test` says no models were found

**Symptom** — `No model specified and model discovery returned 0 models`.

**Fix**

- Give the base URL including the API version path
  (for example `https://gateway.example/v1`), because the adapter appends
  `/models`.
- Some gateways expose `/v1/models` but not `/models`; set the base URL to
  the version root.
- For Ollama, make sure the server is running: `ollama serve`, then
  `ollama list`.

---

## 13. Ollama is installed but the connection is refused

**Symptom** — `could not connect to ollama server`.

**Fix**

```bash
ollama serve          # start the server (it may not auto-start)
curl http://localhost:11434/api/tags
```

On Windows, run `ollama serve` in a separate terminal window.

---

## 14. Tests are slow to start

**Symptom** — each suite takes many seconds before running.

**Cause** — third-party pytest plugins are being auto-loaded.

**Fix** — the sandboxes already set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. When
running tests by hand, do the same:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

---

## 15. The dashboard shows no runs

**Symptom** — the **Overview** tab reports `0` recorded runs.

**Fix**

Runs are stored in `artifacts/bugbench.db`. Either no run has been executed
yet, or the dashboard is using a different artifacts directory. Check
`GET /api/health` — the `config` block shows the resolved `db_path` and
`artifacts_dir`.

Run one to populate it:

```bash
bugbench reference --sandbox docker
```

---

## 16. The dashboard is not reachable from another machine

**Fix** — bind to all interfaces and allow the port through the firewall:

```bash
bugbench serve --host 0.0.0.0 --port 8000
```

> The dashboard has no authentication. Do not expose it to an untrusted
> network. See [`SECURITY.md`](../SECURITY.md).

---

## 17. `ruff format --check` fails in CI

**Fix**

```bash
.venv/bin/ruff format src tests scripts
.venv/bin/ruff check src tests scripts --fix
```

---

## 18. `mypy` reports errors after a dependency upgrade

**Fix** — the project pins `mypy` in `requirements.lock`. Recreate the
environment from the lock file rather than upgrading in place:

```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## 19. Git reports CRLF warnings on Windows

**Symptom** — `warning: LF will be replaced by CRLF`.

**Cause** — Git's Windows default. The benchmark already normalises line
endings to LF when it provisions a workspace, so this warning is cosmetic for
the benchmark itself.

**Fix** (if it bothers you):

```bash
git config --global core.autocrlf false
```

---

## 20. A run stops early with status `STOPPED_BUDGET`

**Symptom** — the run status is `STOPPED_BUDGET` and fewer tasks were
evaluated than requested.

**Cause** — the accumulated priced spend reached `--max-cost`.

**Fix** — raise the cap, use a cheaper model, or run fewer tasks. Note that the
cap is only enforced when a price is actually known.

---

## Getting help

If none of the above helps, collect the following and open an issue:

```bash
bugbench --help
python --version
git --version
docker version
curl -s http://localhost:8000/api/health
```

Please do **not** include API keys. Mini SWE-Bench redacts secrets from logs
and reports, but a key pasted into an issue is a leaked key.
