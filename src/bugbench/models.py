"""Core domain models for Mini SWE-Bench."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


TaskDifficulty = Difficulty


class TaskCategory(StrEnum):
    PAGINATION_API = "pagination_api"
    CACHE_EXPIRATION = "cache_expiration"
    CONCURRENCY_RACES = "concurrency_races"
    SQLITE_TRANSACTIONS = "sqlite_transactions"
    TIMEZONE_DST = "timezone_dst"
    STREAMING_PARSER = "streaming_parser"
    CONFIG_PRECEDENCE = "config_precedence"
    RETRY_RATELIMIT = "retry_ratelimit"
    SERIALIZATION_COMPAT = "serialization_compat"
    CLI_VALIDATION = "cli_validation"
    IDEMPOTENCY = "idempotency"
    ATOMIC_FILE_OPS = "atomic_file_ops"


class SandboxMode(StrEnum):
    AUTO = "auto"
    DOCKER = "docker"
    BWRAP = "bwrap"
    SUBPROCESS = "subprocess"


class ExecutionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"
    CRASH = "CRASH"
    ENV_ERROR = "ENV_ERROR"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    CANCELLED = "CANCELLED"


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    REGRESSION = "REGRESSION"
    INVALID_PATCH = "INVALID_PATCH"
    INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    NO_CHANGES = "NO_CHANGES"


class PinnedEnvironment(BaseModel):
    python_version: str = "3.12"
    dependencies: list[str] = Field(default_factory=list)
    test_command: str = "pytest -q"
    docker_image: str = "software-bug-repair-benchmark-runner:latest"


class BenchmarkTask(BaseModel):
    task_id: str
    title: str
    difficulty: Difficulty
    category: TaskCategory
    package_name: str
    summary: str
    issue_description: str
    reproduction_instructions: str
    pinned_environment: PinnedEnvironment = Field(default_factory=PinnedEnvironment)
    base_revision: str = ""
    allowed_files: list[str] = Field(default_factory=list)
    pass_to_pass_tests: list[str] = Field(default_factory=list)
    fail_to_pass_tests: list[str] = Field(default_factory=list)
    private_tests: list[str] = Field(default_factory=list)
    test_suite_hash: str = ""
    reference_patch_hash: str = ""
    repo_path: str = ""
    task_dir: str = ""


class PatchValidationResult(BaseModel):
    is_empty: bool = False
    applies_cleanly: bool = False
    integrity_passed: bool = False
    patch_sha256: str = ""
    modified_files: list[str] = Field(default_factory=list)
    unauthorized_files: list[str] = Field(default_factory=list)
    tampered_tests: list[str] = Field(default_factory=list)
    suspicious_patterns: list[str] = Field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def is_valid_and_safe(self) -> bool:
        return not self.is_empty and self.applies_cleanly and self.integrity_passed


class TestCaseOutcome(BaseModel):
    test_id: str
    suite: str  # "PASS_TO_PASS", "FAIL_TO_PASS", "PRIVATE"
    passed: bool
    outcome: str  # "passed", "failed", "error", "skipped"
    duration_ms: float = 0.0
    message: str = ""


class SuiteExecutionResult(BaseModel):
    suite_name: str  # "PASS_TO_PASS", "FAIL_TO_PASS", "PRIVATE"
    execution_status: ExecutionStatus = ExecutionStatus.COMPLETED
    exit_code: int = 0
    duration_ms: float = 0.0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    total_count: int = 0
    test_cases: list[TestCaseOutcome] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""

    @property
    def all_passed(self) -> bool:
        return (
            self.execution_status == ExecutionStatus.COMPLETED
            and self.exit_code == 0
            and self.total_count > 0
            and self.passed_count == self.total_count
            and self.failed_count == 0
            and self.error_count == 0
        )


class TaskEvaluationResult(BaseModel):
    run_id: str
    task_id: str
    title: str
    difficulty: Difficulty
    category: TaskCategory
    agent_id: str
    provider: str = "offline"
    model: str = "manual"
    sandbox_mode: str = "subprocess"
    base_revision: str = ""
    test_suite_hash: str = ""
    patch_diff: str = ""
    patch_validation: PatchValidationResult = Field(default_factory=PatchValidationResult)
    pass_to_pass: SuiteExecutionResult | None = None
    fail_to_pass: SuiteExecutionResult | None = None
    private_tests: SuiteExecutionResult | None = None
    execution_status: ExecutionStatus = ExecutionStatus.COMPLETED
    resolution_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    resolved: bool = False
    issue_fixed: bool = False
    has_regression: bool = False
    private_passed: bool = False
    failure_classification: str = ""
    explanation: str = ""
    duration_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    started_at: str = Field(default_factory=utc_now_iso)
    completed_at: str = Field(default_factory=utc_now_iso)
    agent_logs: str = ""


class CategoryMetric(BaseModel):
    category: str
    total: int = 0
    resolved: int = 0
    issue_fixed: int = 0
    regressions: int = 0
    resolved_rate: float = 0.0


class DifficultyMetric(BaseModel):
    difficulty: str
    total: int = 0
    resolved: int = 0
    issue_fixed: int = 0
    regressions: int = 0
    resolved_rate: float = 0.0


class EvaluationRunSummary(BaseModel):
    run_id: str
    run_name: str
    benchmark_version: str = "1.0.0"
    agent_id: str
    provider: str = "offline"
    model: str = "manual"
    sandbox_mode: str = "subprocess"
    status: str = "COMPLETED"  # RUNNING, COMPLETED, FAILED, CANCELLED
    created_at: str = Field(default_factory=utc_now_iso)
    completed_at: str | None = None
    total_tasks: int = 0
    completed_tasks: int = 0
    resolved_count: int = 0
    resolved_rate: float = 0.0
    issue_fix_count: int = 0
    issue_fix_rate: float = 0.0
    regression_count: int = 0
    regression_free_count: int = 0
    regression_free_rate: float = 0.0
    patch_valid_count: int = 0
    patch_valid_rate: float = 0.0
    integrity_violation_count: int = 0
    execution_failure_count: int = 0
    total_duration_ms: float = 0.0
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    is_demo: bool = False
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    category_breakdown: list[CategoryMetric] = Field(default_factory=list)
    difficulty_breakdown: list[DifficultyMetric] = Field(default_factory=list)
    task_results: list[TaskEvaluationResult] = Field(default_factory=list)


class QualityGateCheck(BaseModel):
    check_id: str
    description: str
    passed: bool
    details: str = ""
    duration_ms: float = 0.0


class TaskValidationReport(BaseModel):
    task_id: str
    title: str
    difficulty: Difficulty
    category: TaskCategory
    passed: bool
    base_revision: str = ""
    test_suite_hash: str = ""
    reference_patch_hash: str = ""
    checks: list[QualityGateCheck] = Field(default_factory=list)
    duration_ms: float = 0.0


class DatasetValidationSummary(BaseModel):
    benchmark_version: str = "1.0.0"
    timestamp: str = Field(default_factory=utc_now_iso)
    total_tasks: int = 0
    valid_tasks: int = 0
    invalid_tasks: int = 0
    all_passed: bool = False
    total_duration_ms: float = 0.0
    task_reports: list[TaskValidationReport] = Field(default_factory=list)


class ProviderConfigModel(BaseModel):
    provider: str  # "openai", "anthropic", "openrouter", "custom_openai", "ollama", "codex_cli", "claude_code_cli", "offline"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout_seconds: int = 60
    max_cost_usd: float = 5.0
    input_cost_per_1k_tokens: float | None = None
    output_cost_per_1k_tokens: float | None = None
    # Where the pricing above came from: "manual", "provider_discovery",
    # "builtin_estimate" or "" (unknown).
    pricing_source: str = ""
    # Opt-in use of the bundled (clearly-labelled) price estimates.
    allow_builtin_pricing_estimates: bool = False


class ConnectionTestResult(BaseModel):
    provider: str
    reachable: bool
    authenticated: bool
    selected_model: str = ""
    discovered_models: list[str] = Field(default_factory=list)
    message: str = ""
    latency_ms: float = 0.0
