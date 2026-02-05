"""Request and response schemas for the service API.

Strict Pydantic models defining the JSON contract between
the FastAPI backend and any client (Streamlit, Tauri, CLI).
"""

from datetime import datetime

from pydantic import BaseModel, Field

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

    stage: str | None = Field(None, description="Specific stage to run")
    until_stage: str | None = Field(None, description="Run up to and including this stage")


class RunJobResponse(BaseModel):
    """POST /jobs/{job_id}/run response body."""

    job_id: str
    status: str
    message: str


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

    from_stage: str | None = Field(
        None,
        description="Stage to resume from (defaults to first incomplete stage)",
    )


class ResumeJobResponse(BaseModel):
    """POST /jobs/{job_id}/resume response body."""

    job_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Background run
# ---------------------------------------------------------------------------


class BackgroundRunRequest(BaseModel):
    """POST /jobs/{job_id}/run/background request body."""

    stage: str | None = Field(None, description="Specific stage to run")
    until_stage: str | None = Field(None, description="Run up to and including this stage")


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
