"""Sandboxed command and pytest execution (Docker, Bubblewrap, and Hardened Subprocess)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from bugbench.config import AppConfig
from bugbench.logging_utils import get_logger, redact_secrets
from bugbench.models import ExecutionStatus, SandboxMode, SuiteExecutionResult, TestCaseOutcome

logger = get_logger("bugbench.sandbox")


@dataclass
class CommandResult:
    status: ExecutionStatus
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    sandbox_used: str


class SandboxExecutor:
    """Executes test suites and commands inside an isolated sandbox environment."""

    def __init__(
        self, config: AppConfig | None = None, mode_override: SandboxMode | None = None
    ) -> None:
        self.config = config or AppConfig.from_env()
        self.mode_override = mode_override

    @property
    def effective_mode(self) -> SandboxMode:
        if self.mode_override and self.mode_override != SandboxMode.AUTO:
            return self.mode_override
        return self.config.resolve_effective_sandbox()

    def build_docker_command(
        self,
        repo_dir: Path,
        inner_cmd: list[str],
        ro_mounts: list[tuple[Path, str]] | None = None,
    ) -> list[str]:
        """Build the hardened `docker run` command list."""
        repo_abs = str(repo_dir.resolve())
        cmd = [
            "docker",
            "run",
            "--rm",
            "--user",
            "1000:1000",
            "--cpus",
            str(self.config.cpu_limit),
            "--memory",
            f"{self.config.memory_limit_mb}m",
            "--pids-limit",
            str(self.config.max_pids),
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--security-opt",
            "no-new-privileges:true",
            "--cap-drop",
            "ALL",
            "-e",
            "PYTHONPATH=/workspace/src",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "-e",
            "HOME=/tmp",
            "-v",
            f"{repo_abs}:/workspace:rw",
            "-w",
            "/workspace",
        ]
        if self.config.network_disabled:
            cmd.extend(["--network", "none"])

        if ro_mounts:
            for host_path, container_path in ro_mounts:
                cmd.extend(["-v", f"{host_path.resolve()}:{container_path}:ro"])

        cmd.append(self.config.docker_image)
        cmd.extend(inner_cmd)
        return cmd

    def build_bwrap_command(
        self,
        repo_dir: Path,
        inner_cmd: list[str],
        ro_mounts: list[tuple[Path, str]] | None = None,
    ) -> list[str]:
        """Build the Linux Bubblewrap (`bwrap`) isolated namespace command list."""
        cmd = [
            "bwrap",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind-try",
            "/lib64",
            "/lib64",
            "--ro-bind",
            "/bin",
            "/bin",
            "--ro-bind-try",
            "/etc/alternatives",
            "/etc/alternatives",
            "--ro-bind-try",
            "/etc/localtime",
            "/etc/localtime",
            "--ro-bind-try",
            "/usr/share/zoneinfo",
            "/usr/share/zoneinfo",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--bind",
            str(repo_dir.resolve()),
            "/workspace",
            "--chdir",
            "/workspace",
            "--unshare-ipc",
            "--unshare-pid",
            "--die-with-parent",
            "--clearenv",
            "--setenv",
            "PATH",
            "/usr/local/bin:/usr/bin:/bin",
            "--setenv",
            "PYTHONPATH",
            "/workspace/src",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "1",
            "--setenv",
            "HOME",
            "/tmp",
        ]
        if self.config.network_disabled:
            cmd.append("--unshare-net")

        if ro_mounts:
            for host_path, container_path in ro_mounts:
                cmd.extend(["--ro-bind", str(host_path.resolve()), container_path])

        cmd.extend(inner_cmd)
        return cmd

    def run_command(
        self,
        repo_dir: Path,
        inner_cmd: list[str],
        ro_mounts: list[tuple[Path, str]] | None = None,
        timeout_seconds: int | None = None,
    ) -> CommandResult:
        """Execute a command inside the configured sandbox with timeout and resource tracking."""
        mode = self.effective_mode
        timeout = timeout_seconds or self.config.default_timeout_seconds
        start_t = time.perf_counter()

        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "PYTHONPATH": str((repo_dir / "src").resolve()),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "HOME": tempfile.gettempdir(),
            "LANG": "C.UTF-8",
        }
        # Preserve Windows-required system variables when running on Windows
        for win_key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"):
            if win_key in os.environ:
                clean_env[win_key] = os.environ[win_key]

        if mode == SandboxMode.DOCKER:
            full_cmd = self.build_docker_command(repo_dir, inner_cmd, ro_mounts=ro_mounts)
            exec_cwd = None
            exec_env = None  # docker uses -e flags; needs host PATH/DOCKER_HOST to talk to daemon
        elif mode == SandboxMode.BWRAP and shutil.which("bwrap"):
            full_cmd = self.build_bwrap_command(repo_dir, inner_cmd, ro_mounts=ro_mounts)
            exec_cwd = None
            exec_env = clean_env
        else:
            mode = SandboxMode.SUBPROCESS
            full_cmd = inner_cmd
            exec_cwd = repo_dir.resolve()
            exec_env = clean_env

        try:
            proc = subprocess.run(
                full_cmd,
                cwd=exec_cwd,
                env=exec_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            stdout = redact_secrets(proc.stdout or "")
            stderr = redact_secrets(proc.stderr or "")

            # Detect OOM / SIGKILL (exit code 137) or MemoryError
            if proc.returncode == 137 or "MemoryError" in stderr or "MemoryError" in stdout:
                status = ExecutionStatus.RESOURCE_EXHAUSTED
            elif proc.returncode < 0 or proc.returncode in (134, 139):
                status = ExecutionStatus.CRASH
            elif mode == SandboxMode.DOCKER and proc.returncode in (125, 126, 127):
                status = ExecutionStatus.ENV_ERROR
            else:
                status = ExecutionStatus.COMPLETED

            return CommandResult(
                status=status,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=elapsed_ms,
                sandbox_used=mode.value,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            out = (
                exc.stdout.decode("utf-8", errors="replace")
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or "")
            )
            err = (
                exc.stderr.decode("utf-8", errors="replace")
                if isinstance(exc.stderr, bytes)
                else (exc.stderr or "")
            )
            return CommandResult(
                status=ExecutionStatus.TIMEOUT,
                exit_code=124,
                stdout=redact_secrets(out),
                stderr=redact_secrets(err + f"\nExecution timed out after {timeout}s."),
                duration_ms=elapsed_ms,
                sandbox_used=mode.value,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            return CommandResult(
                status=ExecutionStatus.ENV_ERROR,
                exit_code=125,
                stdout="",
                stderr=redact_secrets(f"Sandbox execution error: {exc}"),
                duration_ms=elapsed_ms,
                sandbox_used=mode.value,
            )

    def run_pytest_suite(
        self,
        repo_dir: Path,
        suite_name: str,
        test_target: Path,
        timeout_seconds: int | None = None,
    ) -> SuiteExecutionResult:
        """Execute a pytest suite against `repo_dir` and parse per-test JUnit XML results."""
        repo_resolved = repo_dir.resolve()
        target_resolved = test_target.resolve()

        # We write the JUnit XML inside repo_dir/.tmp_eval_report.xml and remove it immediately after
        report_filename = f".junit_{suite_name.lower()}.xml"
        host_report_path = repo_resolved / report_filename

        mode = self.effective_mode
        ro_mounts: list[tuple[Path, str]] = []

        if mode in (SandboxMode.DOCKER, SandboxMode.BWRAP):
            if target_resolved.is_relative_to(repo_resolved):
                rel_target = target_resolved.relative_to(repo_resolved).as_posix()
                sandbox_test_arg = f"/workspace/{rel_target}"
            else:
                # Mount external test file read-only at /tmp_eval_test.py or /eval_suite/test.py
                sandbox_test_arg = f"/tmp/{target_resolved.name}"
                # Copy external test into a temporary file inside repo_dir or mount read-only
                # Using a read-only mount keeps external test immutable to candidate code!
                ro_mounts.append((target_resolved, f"/eval_{suite_name.lower()}.py"))
                sandbox_test_arg = f"/eval_{suite_name.lower()}.py"

            sandbox_report_arg = f"/workspace/{report_filename}"
            python_bin = "python3" if mode == SandboxMode.DOCKER else sys.executable
            inner_cmd = [
                python_bin,
                "-m",
                "pytest",
                sandbox_test_arg,
                f"--junitxml={sandbox_report_arg}",
                "-q",
                "--tb=short",
                "-o",
                "cache_dir=/tmp/pytest_cache",
            ]
        else:
            inner_cmd = [
                sys.executable,
                "-m",
                "pytest",
                str(target_resolved),
                f"--junitxml={host_report_path}",
                "-q",
                "--tb=short",
                "-o",
                f"cache_dir={tempfile.gettempdir()}/pytest_cache_{os.getpid()}",
            ]

        cmd_res = self.run_command(
            repo_dir=repo_resolved,
            inner_cmd=inner_cmd,
            ro_mounts=ro_mounts,
            timeout_seconds=timeout_seconds,
        )

        test_cases: list[TestCaseOutcome] = []
        passed_count = 0
        failed_count = 0
        error_count = 0
        skipped_count = 0

        if host_report_path.exists():
            try:
                tree = ET.parse(host_report_path)  # noqa: S314
                root = tree.getroot()
                for tc in root.iter("testcase"):
                    classname = tc.attrib.get("classname", "")
                    name = tc.attrib.get("name", "")
                    test_id = f"{classname}::{name}" if classname else name
                    time_s = float(tc.attrib.get("time", "0.0") or 0.0)
                    failure_el = tc.find("failure")
                    error_el = tc.find("error")
                    skipped_el = tc.find("skipped")

                    if failure_el is not None:
                        outcome = "failed"
                        passed = False
                        failed_count += 1
                        msg = (
                            failure_el.attrib.get("message", "") + "\n" + (failure_el.text or "")
                        ).strip()
                    elif error_el is not None:
                        outcome = "error"
                        passed = False
                        error_count += 1
                        msg = (
                            error_el.attrib.get("message", "") + "\n" + (error_el.text or "")
                        ).strip()
                    elif skipped_el is not None:
                        outcome = "skipped"
                        passed = False
                        skipped_count += 1
                        msg = skipped_el.attrib.get("message", "Skipped")
                    else:
                        outcome = "passed"
                        passed = True
                        passed_count += 1
                        msg = ""

                    test_cases.append(
                        TestCaseOutcome(
                            test_id=test_id,
                            suite=suite_name,
                            passed=passed,
                            outcome=outcome,
                            duration_ms=round(time_s * 1000.0, 3),
                            message=msg[:2000],
                        )
                    )
            except Exception as exc:
                logger.warning("Failed to parse JUnit XML for %s: %s", suite_name, exc)
            finally:
                host_report_path.unlink(missing_ok=True)

        total_count = passed_count + failed_count + error_count + skipped_count

        # If pytest crashed or had syntax error during collection (no testcase elements emitted)
        exec_status = cmd_res.status
        if exec_status == ExecutionStatus.COMPLETED and total_count == 0 and cmd_res.exit_code != 0:
            error_count = 1
            total_count = 1
            test_cases.append(
                TestCaseOutcome(
                    test_id=f"{suite_name}::collection",
                    suite=suite_name,
                    passed=False,
                    outcome="error",
                    duration_ms=cmd_res.duration_ms,
                    message=(cmd_res.stderr or cmd_res.stdout)[:2000],
                )
            )

        return SuiteExecutionResult(
            suite_name=suite_name,
            execution_status=exec_status,
            exit_code=cmd_res.exit_code,
            duration_ms=round(cmd_res.duration_ms, 2),
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            skipped_count=skipped_count,
            total_count=total_count,
            test_cases=test_cases,
            stdout=cmd_res.stdout[:10000],
            stderr=cmd_res.stderr[:10000],
        )
