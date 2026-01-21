"""Offline patch evaluation and baseline adapters (No-Op, Reference, Incomplete, Regression)."""

from __future__ import annotations

from pathlib import Path

from bugbench.agents.base import AgentAdapter, AgentOutput
from bugbench.dataset.loader import DatasetLoader
from bugbench.models import BenchmarkTask


class NoOpBaselineAdapter(AgentAdapter):
    """Returns an empty patch (no modifications) to verify baseline failure detection."""

    agent_id = "noop-baseline"
    provider = "offline"
    model = "noop"

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        return AgentOutput(
            patch_diff="",
            logs=f"No-op baseline adapter executed on {task.task_id}; returning empty patch.",
            model_used="noop",
        )


NoOpAgentAdapter = NoOpBaselineAdapter


class ReferenceOracleAdapter(AgentAdapter):
    """Loads the verified reference patch for oracle baseline verification."""

    agent_id = "reference-oracle"
    provider = "offline"
    model = "reference"

    def __init__(self, loader: DatasetLoader | None = None, mode: str = "reference") -> None:
        self.loader = loader or DatasetLoader()
        self.mode = mode

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        patch_text = self.loader.load_reference_patch(task.task_id)
        return AgentOutput(
            patch_diff=patch_text,
            logs=f"Loaded reference patch for {task.task_id}.",
            model_used="reference",
        )


class IncompleteBaselineAdapter(AgentAdapter):
    """Loads the task's partial/incomplete patch for negative quality-gate verification."""

    agent_id = "incomplete-baseline"
    provider = "offline"
    model = "incomplete"

    def __init__(self, loader: DatasetLoader | None = None) -> None:
        self.loader = loader or DatasetLoader()

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        path = self.loader.get_incomplete_patch_path(task.task_id)
        patch_text = path.read_text(encoding="utf-8") if path.exists() else ""
        return AgentOutput(
            patch_diff=patch_text,
            logs=f"Loaded incomplete patch for {task.task_id}.",
            model_used="incomplete",
        )


class RegressionBaselineAdapter(AgentAdapter):
    """Loads the task's regression-inducing patch for negative quality-gate verification."""

    agent_id = "regression-baseline"
    provider = "offline"
    model = "regression"

    def __init__(self, loader: DatasetLoader | None = None) -> None:
        self.loader = loader or DatasetLoader()

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        path = self.loader.get_regression_patch_path(task.task_id)
        patch_text = path.read_text(encoding="utf-8") if path.exists() else ""
        return AgentOutput(
            patch_diff=patch_text,
            logs=f"Loaded regression patch for {task.task_id}.",
            model_used="regression",
        )


class OfflinePatchAdapter(AgentAdapter):
    """Evaluates manually written or externally generated Git patches without any AI API."""

    agent_id = "offline-patch"
    provider = "offline"
    model = "manual-patch"

    def __init__(
        self,
        patch_path: Path | None = None,
        patch_text: str | None = None,
    ) -> None:
        self.patch_path = patch_path
        self.patch_text = patch_text

    def generate_patch(self, task: BenchmarkTask, repo_dir: Path) -> AgentOutput:
        if self.patch_text is not None:
            return AgentOutput(
                patch_diff=self.patch_text,
                logs="Evaluated direct patch text.",
                model_used="manual-patch",
            )
        if self.patch_path is None:
            raise ValueError("OfflinePatchAdapter requires either patch_path or patch_text.")

        resolved_path = self.patch_path.resolve()
        if resolved_path.is_dir():
            # Look for <task_id>.patch or <task_id>.diff inside the directory
            for ext in (".patch", ".diff"):
                candidate = resolved_path / f"{task.task_id}{ext}"
                if candidate.exists():
                    return AgentOutput(
                        patch_diff=candidate.read_text(encoding="utf-8"),
                        logs=f"Loaded patch file {candidate.name}",
                        model_used="manual-patch",
                    )
            return AgentOutput(
                patch_diff="",
                logs=f"No patch file found for {task.task_id} in {resolved_path}",
                model_used="manual-patch",
            )

        if not resolved_path.exists():
            raise FileNotFoundError(f"Patch file not found: {resolved_path}")

        return AgentOutput(
            patch_diff=resolved_path.read_text(encoding="utf-8"),
            logs=f"Loaded patch file {resolved_path.name}",
            model_used="manual-patch",
        )
