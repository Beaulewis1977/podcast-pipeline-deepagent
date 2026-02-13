"""Job state management models."""

import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator


class StageStatus(StrEnum):
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
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    progress_message: str | None = None

    @model_validator(mode="after")
    def validate_stage_consistency(self) -> "JobStage":
        """Reject contradictory stage runtime combinations."""
        if self.status == StageStatus.COMPLETE and self.error:
            raise ValueError("Complete stages cannot contain an error message")
        if self.status in {StageStatus.PENDING, StageStatus.WAITING, StageStatus.SKIPPED}:
            if self.progress_percent is not None:
                raise ValueError(
                    f"{self.status.value} stages cannot include progress_percent "
                    f"(got {self.progress_percent})"
                )
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be earlier than started_at")
        return self


class Job(BaseModel):
    """Complete job state."""

    DEFAULT_STAGES: ClassVar[tuple[str, ...]] = (
        "ingest",
        "transcribe",
        "analyze",
        "review",
        "render",
    )
    JOB_ID_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")

    job_id: str = Field(min_length=1, max_length=128)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: StageStatus = StageStatus.PENDING
    input_file: str
    stages: dict[str, JobStage] = Field(default_factory=dict)
    error: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, value: str) -> str:
        """Validate job identifiers are safe as directory names."""
        if value != value.strip():
            raise ValueError("job_id cannot include leading or trailing whitespace")
        if "/" in value or "\\" in value:
            raise ValueError("job_id cannot contain path separators")
        if ".." in value:
            raise ValueError("job_id cannot include '..' path traversal tokens")
        if not cls.JOB_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "job_id must start with an alphanumeric character and contain only "
                "letters, numbers, spaces, '.', '_' or '-'"
            )
        return value

    @model_validator(mode="after")
    def validate_job_consistency(self) -> "Job":
        """Reject contradictory top-level job state combinations."""
        if self.status == StageStatus.COMPLETE and self.error:
            raise ValueError("Complete jobs cannot contain a top-level error")

        if self.status == StageStatus.PENDING:
            has_progress = any(stage.progress_percent is not None for stage in self.stages.values())
            if has_progress:
                raise ValueError("Pending jobs cannot include stage progress_percent values")

            has_active_stage = any(
                stage.status != StageStatus.PENDING for stage in self.stages.values()
            )
            if has_active_stage:
                raise ValueError("Pending jobs cannot include non-pending stage statuses")

        return self

    def model_post_init(self, __context: Any) -> None:
        """Initialize default stages if not provided."""
        for stage_name in self.DEFAULT_STAGES:
            if stage_name not in self.stages:
                self.stages[stage_name] = JobStage()

    @classmethod
    def validate_stage_name(cls, stage_name: str) -> None:
        """Validate that a stage name is part of the supported pipeline."""
        if stage_name not in cls.DEFAULT_STAGES:
            valid_stages = ", ".join(cls.DEFAULT_STAGES)
            raise ValueError(f"Unknown stage: {stage_name}. Expected one of: {valid_stages}")

    def get_job_dir(self, base_path: Path) -> Path:
        """Get the job directory path."""
        return base_path / self.job_id

    def save(self, base_path: Path) -> None:
        """Save job state to state.json."""
        job_dir = self.get_job_dir(base_path)
        job_dir.mkdir(parents=True, exist_ok=True)
        state_file = job_dir / "state.json"
        self.updated_at = datetime.now(UTC)
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
        self.validate_stage_name(stage_name)
        if stage_name not in self.stages:
            self.stages[stage_name] = JobStage()

        stage = self.stages[stage_name]
        stage.status = status

        if status == StageStatus.RUNNING:
            stage.started_at = datetime.now(UTC)
            stage.completed_at = None
        elif status in (StageStatus.COMPLETE, StageStatus.FAILED):
            stage.completed_at = datetime.now(UTC)

        if status != StageStatus.FAILED and error is None:
            stage.error = None

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
        self.validate_stage_name(stage_name)
        if stage_name not in self.stages:
            self.stages[stage_name] = JobStage()

        stage = self.stages[stage_name]
        if progress_percent is not None:
            if not 0 <= progress_percent <= 100:
                raise ValueError(
                    f"progress_percent must be between 0 and 100 (got {progress_percent})"
                )
            if stage.status in {StageStatus.PENDING, StageStatus.WAITING, StageStatus.SKIPPED}:
                raise ValueError(
                    f"Cannot set progress_percent while stage '{stage_name}' "
                    f"is {stage.status.value}"
                )
            stage.progress_percent = progress_percent
        if progress_message is not None:
            stage.progress_message = progress_message

        self.updated_at = datetime.now(UTC)

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
