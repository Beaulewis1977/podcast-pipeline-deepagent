"""Job state management models."""

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    """Status values for pipeline stages."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    WAITING = "waiting"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobStage(BaseModel):
    """State of a single pipeline stage."""

    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None
    provider: str | None = None
    model: str | None = None
    progress_percent: int | None = None
    progress_message: str | None = None


class Job(BaseModel):
    """Complete job state."""

    job_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: StageStatus = StageStatus.PENDING
    input_file: str
    stages: dict[str, JobStage] = Field(default_factory=dict)
    error: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Initialize default stages if not provided."""
        default_stages = ["ingest", "transcribe", "analyze", "review", "render"]
        for stage_name in default_stages:
            if stage_name not in self.stages:
                self.stages[stage_name] = JobStage()

    def get_job_dir(self, base_path: Path) -> Path:
        """Get the job directory path."""
        return base_path / self.job_id

    def save(self, base_path: Path) -> None:
        """Save job state to state.json."""
        job_dir = self.get_job_dir(base_path)
        job_dir.mkdir(parents=True, exist_ok=True)
        state_file = job_dir / "state.json"
        self.updated_at = datetime.now(timezone.utc)
        # Write to temp file first, then rename (atomic write)
        temp_file = state_file.with_suffix(".tmp")
        temp_file.write_text(self.model_dump_json(indent=2))
        temp_file.rename(state_file)

    @classmethod
    def load(cls, job_dir: Path) -> "Job":
        """Load job state from state.json."""
        state_file = job_dir / "state.json"
        if not state_file.exists():
            raise FileNotFoundError(f"No state.json found in {job_dir}")
        return cls.model_validate_json(state_file.read_text())

    def update_stage(
        self,
        stage_name: str,
        status: StageStatus,
        outputs: list[str] | None = None,
        error: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        """Update a stage's status."""
        if stage_name not in self.stages:
            self.stages[stage_name] = JobStage()

        stage = self.stages[stage_name]
        stage.status = status

        if status == StageStatus.RUNNING:
            stage.started_at = datetime.now(timezone.utc)
        elif status in (StageStatus.COMPLETE, StageStatus.FAILED):
            stage.completed_at = datetime.now(timezone.utc)

        if outputs is not None:
            stage.outputs = outputs
        if error is not None:
            stage.error = error
        if provider is not None:
            stage.provider = provider
        if model is not None:
            stage.model = model

        # Update overall job status based on stages
        self._update_overall_status()

    def update_stage_progress(
        self,
        stage_name: str,
        progress_percent: int | None = None,
        progress_message: str | None = None,
    ) -> None:
        """Update a stage's progress without changing status."""
        if stage_name not in self.stages:
            self.stages[stage_name] = JobStage()

        stage = self.stages[stage_name]
        if progress_percent is not None:
            stage.progress_percent = progress_percent
        if progress_message is not None:
            stage.progress_message = progress_message

        self.updated_at = datetime.now(timezone.utc)

    def _update_overall_status(self) -> None:
        """Update overall job status based on stage statuses."""
        statuses = [s.status for s in self.stages.values()]

        if any(s == StageStatus.FAILED for s in statuses):
            self.status = StageStatus.FAILED
        elif any(s == StageStatus.WAITING for s in statuses):
            self.status = StageStatus.WAITING
        elif any(s == StageStatus.RUNNING for s in statuses):
            self.status = StageStatus.RUNNING
        elif all(s == StageStatus.COMPLETE for s in statuses):
            self.status = StageStatus.COMPLETE
        else:
            self.status = StageStatus.RUNNING
