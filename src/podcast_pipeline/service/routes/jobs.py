"""HTTP routes for job create / run / status / list / resume.

All business logic is delegated to :class:`Pipeline` and :class:`Job`
from the core package -- route handlers only translate HTTP concerns.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.schemas import (
    CreateJobRequest,
    CreateJobResponse,
    JobDetailResponse,
    JobListResponse,
    JobSummary,
    ResumeJobRequest,
    ResumeJobResponse,
    RunJobRequest,
    RunJobResponse,
    StageDetail,
)
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _get_pipeline(request: Request) -> Pipeline:
    """Retrieve the shared Pipeline instance from app state."""
    pipeline: Pipeline = request.app.state.pipeline
    return pipeline


def _load_job_or_404(pipeline: Pipeline, job_id: str) -> Job:
    """Load a job or raise 404."""
    try:
        return pipeline.load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc


def _job_to_detail(job: Job) -> JobDetailResponse:
    """Map a Job model to the API detail response."""
    return JobDetailResponse(
        job_id=job.job_id,
        status=job.status.value,
        input_file=job.input_file,
        created_at=job.created_at,
        updated_at=job.updated_at,
        stages={
            name: StageDetail(
                status=stage.status.value,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
                outputs=stage.outputs,
                error=stage.error,
                progress_percent=stage.progress_percent,
                progress_message=stage.progress_message,
            )
            for name, stage in job.stages.items()
        },
        error=job.error,
    )


# --------------------------------------------------------------------------
# POST /jobs  -- create a new job
# --------------------------------------------------------------------------


@router.post("", response_model=CreateJobResponse, status_code=201)
async def create_job(body: CreateJobRequest, request: Request) -> CreateJobResponse:
    """Create a new pipeline job from a video file path."""
    pipeline = _get_pipeline(request)
    video_path = Path(body.video_path)

    if not video_path.exists():
        raise HTTPException(status_code=400, detail=f"Video file not found: {body.video_path}")

    try:
        job = pipeline.create_job(video_path, name=body.name)
    except Exception as exc:
        logger.exception("create_job_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return CreateJobResponse(
        job_id=job.job_id,
        status=job.status.value,
        input_file=job.input_file,
        created_at=job.created_at,
    )


# --------------------------------------------------------------------------
# POST /jobs/{job_id}/run  -- start (or continue) a pipeline run
# --------------------------------------------------------------------------


@router.post("/{job_id}/run", response_model=RunJobResponse)
async def run_job(job_id: str, body: RunJobRequest, request: Request) -> RunJobResponse:
    """Trigger a synchronous pipeline run for a job.

    For background (non-blocking) execution see the supervisor module,
    which wraps this call in an ``asyncio.Task``.
    """
    pipeline = _get_pipeline(request)
    job = _load_job_or_404(pipeline, job_id)

    try:
        results = pipeline.run(job, stage=body.stage, until_stage=body.until_stage)
        failed = [name for name, r in results.items() if not r.success]
        if failed:
            return RunJobResponse(
                job_id=job_id,
                status="failed",
                message=f"Stages failed: {', '.join(failed)}",
            )
        return RunJobResponse(
            job_id=job_id,
            status="complete",
            message=f"Ran {len(results)} stage(s) successfully",
        )
    except Exception as exc:
        logger.exception("run_job_failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# GET /jobs/{job_id}  -- job detail / status
# --------------------------------------------------------------------------


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: str, request: Request) -> JobDetailResponse:
    """Return full status for a single job."""
    pipeline = _get_pipeline(request)
    job = _load_job_or_404(pipeline, job_id)
    return _job_to_detail(job)


# --------------------------------------------------------------------------
# GET /jobs  -- list all jobs
# --------------------------------------------------------------------------


@router.get("", response_model=JobListResponse)
async def list_jobs(request: Request) -> JobListResponse:
    """Return a summary list of all known jobs."""
    pipeline = _get_pipeline(request)
    raw = pipeline.list_jobs()
    return JobListResponse(
        jobs=[
            JobSummary(
                job_id=j["job_id"],
                status=j["status"],
                created=j["created"],
                stages=j["stages"],
            )
            for j in raw
        ]
    )


# --------------------------------------------------------------------------
# POST /jobs/{job_id}/resume  -- resume a paused / failed job
# --------------------------------------------------------------------------


@router.post("/{job_id}/resume", response_model=ResumeJobResponse)
async def resume_job(job_id: str, body: ResumeJobRequest, request: Request) -> ResumeJobResponse:
    """Resume a job from the first incomplete stage (or a specific one)."""
    pipeline = _get_pipeline(request)
    job = _load_job_or_404(pipeline, job_id)

    # Determine resume point
    if body.from_stage:
        resume_stage = body.from_stage
    else:
        # Find first non-complete stage
        resume_stage = None
        for stage_name in Pipeline.STAGE_ORDER:
            stage_obj = job.stages.get(stage_name)
            if stage_obj and stage_obj.status != StageStatus.COMPLETE:
                resume_stage = stage_name
                break

    if resume_stage is None:
        return ResumeJobResponse(
            job_id=job_id,
            status="complete",
            message="All stages already complete, nothing to resume",
        )

    # Reset the target stage so the pipeline will re-run it
    job.update_stage(resume_stage, StageStatus.PENDING)
    job.save(pipeline.config.paths.jobs_dir)

    try:
        results = pipeline.run(job, stage=resume_stage)
        failed = [name for name, r in results.items() if not r.success]
        if failed:
            return ResumeJobResponse(
                job_id=job_id,
                status="failed",
                message=f"Resume failed at stage(s): {', '.join(failed)}",
            )
        return ResumeJobResponse(
            job_id=job_id,
            status="running",
            message=f"Resumed from {resume_stage}",
        )
    except Exception as exc:
        logger.exception("resume_job_failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
