"""Configuration and provider settings management for Mini SWE-Bench."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from bugbench.logging_utils import sanitize_dict
from bugbench.models import ProviderConfigModel, SandboxMode

load_dotenv()


def get_project_root() -> Path:
    """Resolve the repository root directory."""
    env_root = os.environ.get("BUGBENCH_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # Default: two levels above src/bugbench/config.py -> repo root
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "benchmarks").exists() or (candidate / "pyproject.toml").exists():
        return candidate
    return Path.cwd().resolve()


_CACHED_EFFECTIVE_SANDBOX: dict[str, SandboxMode] = {}


class AppConfig(BaseModel):
    root_dir: Path = Field(default_factory=get_project_root)
    benchmarks_dir: Path = Field(default_factory=lambda: get_project_root() / "benchmarks")
    private_tests_dir: Path = Field(
        default_factory=lambda: get_project_root() / "private_evaluations"
    )
    artifacts_dir: Path = Field(default_factory=lambda: get_project_root() / "artifacts")
    db_path: Path = Field(default_factory=lambda: get_project_root() / "artifacts" / "bugbench.db")
    sandbox_mode: SandboxMode = SandboxMode.AUTO
    docker_image: str = "software-bug-repair-benchmark-runner:latest"
    default_timeout_seconds: int = 60
    memory_limit_mb: int = 512
    cpu_limit: float = 1.0
    max_pids: int = 64
    network_disabled: bool = True
    temperature: float = 0.0
    max_tokens: int = 4096
    max_cost_usd: float = 5.0

    @classmethod
    def from_env(cls, root_dir: Path | None = None) -> AppConfig:
        root = (root_dir or get_project_root()).resolve()
        benchmarks_dir = Path(os.environ.get("BUGBENCH_BENCHMARKS_DIR", str(root / "benchmarks")))
        if not benchmarks_dir.is_absolute():
            benchmarks_dir = (root / benchmarks_dir).resolve()

        private_dir = Path(
            os.environ.get("BUGBENCH_PRIVATE_TESTS_DIR", str(root / "private_evaluations"))
        )
        if not private_dir.is_absolute():
            private_dir = (root / private_dir).resolve()

        artifacts_dir = Path(os.environ.get("BUGBENCH_ARTIFACTS_DIR", str(root / "artifacts")))
        if not artifacts_dir.is_absolute():
            artifacts_dir = (root / artifacts_dir).resolve()

        db_url = os.environ.get("BUGBENCH_DB_URL", "")
        if db_url.startswith("sqlite:///"):
            rel_db = db_url.replace("sqlite:///", "", 1)
            db_path = Path(rel_db)
            if not db_path.is_absolute():
                db_path = (root / db_path).resolve()
        else:
            db_path = artifacts_dir / "bugbench.db"

        mode_str = os.environ.get("BUGBENCH_SANDBOX_MODE", "auto").lower()
        try:
            sandbox_mode = SandboxMode(mode_str)
        except ValueError:
            sandbox_mode = SandboxMode.AUTO

        return cls(
            root_dir=root,
            benchmarks_dir=benchmarks_dir,
            private_tests_dir=private_dir,
            artifacts_dir=artifacts_dir,
            db_path=db_path,
            sandbox_mode=sandbox_mode,
            docker_image=os.environ.get(
                "BUGBENCH_DOCKER_IMAGE", "software-bug-repair-benchmark-runner:latest"
            ),
            default_timeout_seconds=int(os.environ.get("BUGBENCH_DEFAULT_TIMEOUT_SECONDS", "60")),
            memory_limit_mb=int(os.environ.get("BUGBENCH_MEMORY_LIMIT_MB", "512")),
            cpu_limit=float(os.environ.get("BUGBENCH_CPU_LIMIT", "1.0")),
            max_pids=int(os.environ.get("BUGBENCH_MAX_PIDS", "64")),
            network_disabled=os.environ.get("BUGBENCH_NETWORK_DISABLED", "true").lower()
            in ("1", "true", "yes"),
            temperature=float(os.environ.get("BUGBENCH_TEMPERATURE", "0.0")),
            max_tokens=int(os.environ.get("BUGBENCH_MAX_TOKENS", "4096")),
            max_cost_usd=float(os.environ.get("BUGBENCH_MAX_COST_USD", "5.0")),
        )

    def resolve_effective_sandbox(self) -> SandboxMode:
        """Resolve AUTO sandbox mode based on available system isolation tools."""
        if self.sandbox_mode != SandboxMode.AUTO:
            return self.sandbox_mode
        cache_key = self.docker_image
        if cache_key in _CACHED_EFFECTIVE_SANDBOX:
            return _CACHED_EFFECTIVE_SANDBOX[cache_key]
        # Check if docker is installed, daemon is running, and runner image exists
        if shutil.which("docker"):
            import subprocess

            try:
                proc = subprocess.run(
                    ["docker", "image", "inspect", self.docker_image],
                    capture_output=True,
                    timeout=3,
                    check=False,
                )
                if proc.returncode == 0:
                    _CACHED_EFFECTIVE_SANDBOX[cache_key] = SandboxMode.DOCKER
                    return SandboxMode.DOCKER
            except Exception:
                pass
        # Check if bubblewrap is available and functional on Linux
        if shutil.which("bwrap"):
            import subprocess

            try:
                proc = subprocess.run(
                    [
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
                        "--proc",
                        "/proc",
                        "--dev",
                        "/dev",
                        "--unshare-net",
                        "true",
                    ],
                    capture_output=True,
                    timeout=3,
                    check=False,
                )
                if proc.returncode == 0:
                    _CACHED_EFFECTIVE_SANDBOX[cache_key] = SandboxMode.BWRAP
                    return SandboxMode.BWRAP
            except Exception:
                pass
        _CACHED_EFFECTIVE_SANDBOX[cache_key] = SandboxMode.SUBPROCESS
        return SandboxMode.SUBPROCESS

    # provider id -> (env prefix, default base URL)
    _PROVIDER_ENV: dict[str, tuple[str, str]] = {
        "openai": ("OPENAI", "https://api.openai.com/v1"),
        "anthropic": ("ANTHROPIC", "https://api.anthropic.com"),
        "openrouter": ("OPENROUTER", "https://openrouter.ai/api/v1"),
        "custom_openai": ("CUSTOM_OPENAI", ""),
        "ollama": ("OLLAMA", "http://localhost:11434/v1"),
    }

    def get_provider_config(self, provider: str) -> ProviderConfigModel:
        """Load provider settings combining runtime settings file and environment variables.

        Precedence (highest first): saved local settings > environment variables >
        built-in defaults. Secret values are never written to logs or exports.
        """
        p = provider.lower().strip()
        saved = self.load_saved_provider_settings().get(p, {})
        env_prefix, default_base_url = self._PROVIDER_ENV.get(p, (p.upper(), ""))

        def _env(suffix: str) -> str:
            return os.environ.get(f"{env_prefix}_{suffix}", "")

        base_url = saved.get("base_url") or _env("BASE_URL") or default_base_url
        api_key = saved.get("api_key") or _env("API_KEY") or ""
        model = saved.get("model") or _env("MODEL") or ""

        # Ollama's OpenAI-compatible endpoint does not require a key, but some
        # gateways in front of it do; keep the harmless placeholder.
        if p == "ollama" and not api_key:
            api_key = "ollama"

        return ProviderConfigModel(
            provider=p,
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=float(saved.get("temperature", self.temperature)),
            max_tokens=int(saved.get("max_tokens", self.max_tokens)),
            timeout_seconds=int(saved.get("timeout_seconds", self.default_timeout_seconds)),
            max_cost_usd=float(saved.get("max_cost_usd", self.max_cost_usd)),
            input_cost_per_1k_tokens=saved.get("input_cost_per_1k_tokens"),
            output_cost_per_1k_tokens=saved.get("output_cost_per_1k_tokens"),
            pricing_source=saved.get("pricing_source", ""),
            allow_builtin_pricing_estimates=bool(
                saved.get("allow_builtin_pricing_estimates", False)
            ),
        )

    @property
    def settings_file_path(self) -> Path:
        return self.artifacts_dir / "tmp" / "provider_settings.json"

    def load_saved_provider_settings(self) -> dict[str, dict[str, Any]]:
        if not self.settings_file_path.exists():
            return {}
        try:
            return json.loads(self.settings_file_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_provider_setting(self, cfg: ProviderConfigModel) -> None:
        self.settings_file_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.load_saved_provider_settings()
        existing[cfg.provider] = cfg.model_dump()
        self.settings_file_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        # Set restrictive permissions on POSIX systems
        with contextlib.suppress(Exception):
            os.chmod(self.settings_file_path, 0o600)

    def sanitized_summary(self) -> dict[str, Any]:
        data = {
            "root_dir": str(self.root_dir),
            "benchmarks_dir": str(self.benchmarks_dir),
            "private_tests_dir": str(self.private_tests_dir),
            "artifacts_dir": str(self.artifacts_dir),
            "db_path": str(self.db_path),
            "configured_sandbox_mode": self.sandbox_mode.value,
            "effective_sandbox_mode": self.resolve_effective_sandbox().value,
            "docker_image": self.docker_image,
            "default_timeout_seconds": self.default_timeout_seconds,
            "memory_limit_mb": self.memory_limit_mb,
            "cpu_limit": self.cpu_limit,
            "max_pids": self.max_pids,
            "network_disabled": self.network_disabled,
        }
        return sanitize_dict(data)
