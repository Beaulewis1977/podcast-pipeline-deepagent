"""Request and response schemas for the service API.

Strict Pydantic models defining the JSON contract between
the FastAPI backend and any client (Streamlit, Tauri, CLI).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

STAGE_ORDER = ("ingest", "transcribe", "analyze", "review", "render")
STAGE_INDEX = {stage_name: index for index, stage_name in enumerate(STAGE_ORDER)}
StageName = Literal["ingest", "transcribe", "analyze", "review", "render"]


def _validate_stage_window(
    start_stage: StageName | None,
    until_stage: StageName | None,
    start_field: str,
) -> None:
    """Ensure until_stage is equal to or after the selected start stage."""
    if start_stage is None or until_stage is None:
        return
    if STAGE_INDEX[until_stage] < STAGE_INDEX[start_stage]:
        raise ValueError(f"until_stage must be the same as or after {start_field}")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """GET /health response."""

    status: str = "ok"


# ---------------------------------------------------------------------------
# Job creation
# ---------------------------------------------------------------------------


class CreateJobRequest(BaseModel):
    """POST /jobs request body."""

    video_path: str = Field(..., description="Absolute path to input video file")
    name: str | None = Field(None, description="Optional human-friendly job name")


class CreateJobResponse(BaseModel):
    """POST /jobs response body."""

    job_id: str
    status: str
    input_file: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Job run
# ---------------------------------------------------------------------------


class RunJobRequest(BaseModel):
    """POST /jobs/{job_id}/run request body."""

    stage: StageName | None = Field(None, description="Specific stage to run")
    until_stage: StageName | None = Field(None, description="Run up to and including this stage")

    @model_validator(mode="after")
    def validate_stage_window(self) -> "RunJobRequest":
        """Validate stage and until_stage ordering."""
        _validate_stage_window(self.stage, self.until_stage, "stage")
        return self


class RunJobResponse(BaseModel):
    """POST /jobs/{job_id}/run response body."""

    job_id: str
    status: Literal["complete", "failed", "running"]
    message: str
    started: bool = Field(
        ...,
        description="True when this request started stage execution",
    )
    completed: bool = Field(
        ...,
        description="True when the requested work completed successfully",
    )
    rejected: bool = Field(
        ...,
        description="True when the request was rejected without starting work",
    )


# ---------------------------------------------------------------------------
# Job status / detail
# ---------------------------------------------------------------------------


class StageDetail(BaseModel):
    """Status of a single pipeline stage."""

    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None
    progress_percent: int | None = None
    progress_message: str | None = None


class JobDetailResponse(BaseModel):
    """GET /jobs/{job_id} response body."""

    job_id: str
    status: str
    input_file: str
    created_at: datetime
    updated_at: datetime
    stages: dict[str, StageDetail]
    error: str | None = None


# ---------------------------------------------------------------------------
# Job listing
# ---------------------------------------------------------------------------


class JobSummary(BaseModel):
    """Single entry in the jobs list."""

    job_id: str
    status: str
    created: str
    stages: dict[str, str]


class JobListResponse(BaseModel):
    """GET /jobs response body."""

    jobs: list[JobSummary]


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


class ResumeJobRequest(BaseModel):
    """POST /jobs/{job_id}/resume request body."""

    from_stage: StageName | None = Field(
        None,
        description="Stage to resume from (defaults to first incomplete stage)",
    )
    until_stage: StageName | None = Field(
        None,
        description="Stop resuming after this stage (defaults to final stage)",
    )
    background: bool = Field(
        False,
        description="Run the resume in the background (non-blocking)",
    )

    @model_validator(mode="after")
    def validate_stage_window(self) -> "ResumeJobRequest":
        """Validate from_stage and until_stage ordering."""
        _validate_stage_window(self.from_stage, self.until_stage, "from_stage")
        return self


class ResumeJobResponse(BaseModel):
    """POST /jobs/{job_id}/resume response body."""

    job_id: str
    status: Literal["complete", "failed", "running"]
    message: str
    started: bool = Field(
        ...,
        description="True when this request started stage execution",
    )
    completed: bool = Field(
        ...,
        description="True when the requested work completed successfully",
    )
    rejected: bool = Field(
        ...,
        description="True when the request was rejected without starting work",
    )


# ---------------------------------------------------------------------------
# Background run
# ---------------------------------------------------------------------------


class BackgroundRunRequest(BaseModel):
    """POST /jobs/{job_id}/run/background request body."""

    stage: StageName | None = Field(None, description="Specific stage to run")
    until_stage: StageName | None = Field(None, description="Run up to and including this stage")

    @model_validator(mode="after")
    def validate_stage_window(self) -> "BackgroundRunRequest":
        """Validate stage and until_stage ordering."""
        _validate_stage_window(self.stage, self.until_stage, "stage")
        return self


class BackgroundRunResponse(BaseModel):
    """POST /jobs/{job_id}/run/background response body."""

    job_id: str
    accepted: bool
    message: str


# ---------------------------------------------------------------------------
# Resumable jobs (recovery)
# ---------------------------------------------------------------------------


class ResumableJobItem(BaseModel):
    """Single entry in the resumable jobs list."""

    job_id: str
    status: str
    resume_stage: str
    completed_stages: list[str] = Field(default_factory=list)
    failed_stages: list[str] = Field(default_factory=list)
    interrupted: bool = False


class ResumableJobsResponse(BaseModel):
    """GET /jobs/resumable response body."""

    jobs: list[ResumableJobItem]
