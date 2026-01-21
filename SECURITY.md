# Security Policy & Sandbox Threat Model

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

---

## 1. Execution Isolation & Container Hardening

Mini SWE-Bench evaluates candidate patches and AI-generated code using a
defense-in-depth isolation strategy
(`src/bugbench/sandbox/executor.py` and `src/bugbench/sandbox/workspace.py`):

1. **Docker Container Isolation (`--sandbox docker`)** — the default and the
   recommended backend for untrusted patches:
   - Executes inside `software-bug-repair-benchmark-runner:latest` as non-root
     UID/GID `1000:1000`.
   - Outbound and inbound network access is disabled (`--network none`).
   - Strict resource limits: `--cpus 1.0`, `--memory 512m`, `--pids-limit 64`.
   - Root filesystem is mounted read-only (`--read-only`) with a bounded
     `noexec,nosuid` `/tmp` tmpfs
     (`--tmpfs /tmp:rw,noexec,nosuid,size=64m`).
   - All Linux capabilities are dropped (`--cap-drop ALL`) and privilege
     escalation is blocked (`--security-opt no-new-privileges:true`).
   - Host Docker socket (`/var/run/docker.sock`) and host credentials /
     environment variables are **never** mounted or passed into evaluation
     containers. `docker-compose.yml` follows the same rule.
   - External evaluation tests (`test_issue.py`, `test_private.py`) are mounted
     **read-only (`:ro`)** at runtime so candidate code cannot overwrite or
     tamper with test files.

2. **Linux Bubblewrap Namespace Isolation (`--sandbox bwrap`)**:
   - Uses unprivileged PID/IPC/network namespaces
     (`--unshare-net --unshare-ipc --unshare-pid --die-with-parent`) with
     read-only system mounts (`/usr`, `/lib`, `/lib64`, `/bin`).

3. **Hardened Subprocess Mode (`--sandbox subprocess`)** — the cross-platform
   fallback (Windows, macOS, or CI without Docker):
   - Runs with a **sanitised environment**: only `PATH`, `PYTHONPATH`,
     `PYTHONDONTWRITEBYTECODE`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD`, `HOME`, and
     `LANG` are passed through. Proxy and credential variables are dropped.
   - Uses process-group termination on timeout.
   - **This mode is not a security boundary.** It is intended for trusted
     patches and for environments where Docker is unavailable. Do not use it to
     execute untrusted third-party code.

4. **Workspace & Patch Anti-Tampering (`PatchValidator` & `EphemeralWorkspace`)**:
   - Rejects relative paths containing `..`, absolute paths, or Windows drive
     prefixes (`validate_safe_relative_path`).
   - Walks the workspace after patch application to detect and block symlink
     escapes (`verify_no_symlink_escapes`).
   - Blocks modifications outside `task.allowed_files` and rejects patches that
     touch `tests/*`, `test_*.py`, `conftest.py`, `pyproject.toml`, `pytest.ini`,
     `setup.cfg`, `tox.ini`, `task.json`, `evaluation/*`, or
     `private_evaluations/*`.
   - Rejects injected evaluation shortcuts: `pytest.skip(...)`,
     `@pytest.mark.skip` / `xfail`, `os._exit(0)`, reads of
     `PYTEST_CURRENT_TEST`, and call-stack introspection
     (`sys._getframe`, `inspect.stack`).

5. **Agent / grading separation**:
   - The agent workspace contains **only** `repo/` and `ISSUE.md`. The
     reference patch, the issue test suite, and the private test suite are never
     mounted into it.
   - Grading always happens in a **separate, freshly provisioned** checkout of
     the original buggy revision, so a candidate patch cannot influence the
     environment it is graded in.
   - Every attempt starts from the original clean state; no test result,
     patched file, container, or cached artifact is shared between runs.

---

## 2. Important Production & Multi-Tenant Warning

> **Important Security Notice:**
> Ordinary Docker container isolation shares the host Linux kernel and is **not**
> a complete security boundary against hostile, untrusted multi-tenant code
> execution on a public internet service. If you deploy Mini SWE-Bench to
> evaluate arbitrary untrusted third-party submissions in a public multi-tenant
> environment, run evaluation workers inside dedicated hardware-virtualized
> sandboxes (such as **Firecracker microVMs**, **gVisor (`runsc`)**, **Kata
> Containers**, or ephemeral single-use cloud VMs).

Additional notes:

- The dashboard has **no authentication**. Bind it to `127.0.0.1` for local
  use. Do not expose it to an untrusted network.
- The `stop` path of a run is cooperative: an in-flight task finishes before
  the run is marked cancelled.

---

## 3. Credential Hygiene & Secret Redaction

- API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`,
  `CUSTOM_OPENAI_API_KEY`) are strictly optional and read from environment
  variables or local git-ignored configuration
  (`artifacts/tmp/provider_settings.json`, mode `0600`).
- `.env` is git-ignored. No credential is ever hardcoded in the source, and
  `.env.example` contains only empty placeholders.
- `src/bugbench/logging_utils.py` automatically redacts Bearer tokens,
  `sk-...` keys, and sensitive dictionary fields before writing logs, SQLite
  records, or API responses.
- The API never returns a stored API key: `GET /api/providers` exposes only a
  boolean `has_api_key` flag.

---

## 4. Reporting a Vulnerability

Please report security issues privately through GitHub's
**Security → Report a vulnerability** feature rather than opening a public
issue. Include the affected version, a reproduction, and the impact you
observed. Do not include real API keys.

---

## 5. Dependency Supply Chain

- Runtime and development dependencies are pinned in `requirements.lock`.
- The Docker runner image uses a separate, smaller pinned set in
  `docker/requirements-runner.txt`.
- The runner image is built from `python:3.12-slim` and installs only
  `git`, `pytest`, and `hypothesis`.
