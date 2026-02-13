"""HTTP routes for job create / run / status / list / resume / recovery.

All business logic is delegated to :class:`Pipeline` and :class:`Job`
from the core package -- route handlers only translate HTTP concerns.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.recovery import (
    list_resumable_jobs,
    prepare_resume,
    reconcile_all_jobs,
)
from podcast_pipeline.service.schemas import (
    BackgroundRunRequest,
    BackgroundRunResponse,
    CreateJobRequest,
    CreateJobResponse,
    JobDetailResponse,
    JobListResponse,
    JobSummary,
    ResumableJobItem,
    ResumableJobsResponse,
    ResumeJobRequest,
    ResumeJobResponse,
    RunJobRequest,
    RunQualityControls,
    RunJobResponse,
    StageDetail,
)
from podcast_pipeline.service.supervisor import Supervisor
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _get_pipeline(request: Request) -> Pipeline:
    """Retrieve the shared Pipeline instance from app state."""
    pipeline: Pipeline = request.app.state.pipeline
    return pipeline


def _get_supervisor(request: Request) -> Supervisor:
    """Retrieve the shared Supervisor instance from app state."""
    supervisor: Supervisor = request.app.state.supervisor
    return supervisor


def _load_job_or_404(pipeline: Pipeline, job_id: str) -> Job:
    """Load a job or raise 404."""
    try:
        return pipeline.load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc


def _persist_run_quality_controls(
    pipeline: Pipeline,
    job: Job,
    controls: RunQualityControls | None,
) -> None:
    """Persist optional run quality controls into job config."""
    if controls is None:
        return

    job.config["render_quality_controls"] = controls.model_dump()
    job.save(pipeline.config.paths.jobs_dir)
    logger.info(
        "run_quality_controls_persisted",
        job_id=job.job_id,
        controls=job.config["render_quality_controls"],
    )


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
    except (FileNotFoundError, OSError, ValueError) as exc:
        logger.exception("create_job_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return CreateJobResponse(
        job_id=job.job_id,
        status=job.status.value,
        input_file=job.input_file,
        created_at=job.created_at,
    )


# --------------------------------------------------------------------------
# GET /jobs/resumable  -- list jobs that can be resumed after crash/restart
# --------------------------------------------------------------------------


@router.get("/resumable", response_model=ResumableJobsResponse)
async def get_resumable_jobs(request: Request) -> ResumableJobsResponse:
    """Return a list of jobs that can be resumed after an interruption.

    Triggers reconciliation first to correct stale runtime metadata,
    then identifies jobs with completed work remaining to be done.
    """
    pipeline = _get_pipeline(request)
    jobs_dir = pipeline.config.paths.jobs_dir
    reconcile_all_jobs(jobs_dir)
    resumable = list_resumable_jobs(jobs_dir)
    return ResumableJobsResponse(
        jobs=[
            ResumableJobItem(
                job_id=r.job_id,
                status=r.status,
                resume_stage=r.resume_stage,
                completed_stages=r.completed_stages,
                failed_stages=r.failed_stages,
                interrupted=r.interrupted,
            )
            for r in resumable
        ]
    )


# --------------------------------------------------------------------------
# POST /jobs/reconcile  -- force reconciliation of all jobs
# --------------------------------------------------------------------------


@router.post("/reconcile")
async def reconcile_jobs(request: Request) -> dict[str, int]:
    """Force reconciliation of all job runtime metadata.

    Returns the count of jobs that had corrections applied.
    """
    pipeline = _get_pipeline(request)
    corrected = reconcile_all_jobs(pipeline.config.paths.jobs_dir)
    return {"corrected": corrected}


# --------------------------------------------------------------------------
# POST /jobs/{job_id}/run  -- start (or continue) a pipeline run
# --------------------------------------------------------------------------


@router.post("/{job_id}/run", response_model=RunJobResponse)
async def run_job(
    job_id: str,
    request: Request,
    body: RunJobRequest | None = None,
) -> RunJobResponse:
    """Trigger a synchronous pipeline run for a job.

    For background (non-blocking) execution see the supervisor module,
    which wraps this call in an ``asyncio.Task``.
    """
    pipeline = _get_pipeline(request)
    job = _load_job_or_404(pipeline, job_id)

    try:
        request_body = body or RunJobRequest()
        _persist_run_quality_controls(pipeline, job, request_body.quality_controls)
        results = pipeline.run(
            job,
            stage=request_body.stage,
            until_stage=request_body.until_stage,
        )
        failed = [name for name, r in results.items() if not r.success]
        started = len(results) > 0
        if failed:
            return RunJobResponse(
                job_id=job_id,
                status="failed",
                message=f"Stages failed: {', '.join(failed)}",
                started=started,
                completed=False,
                rejected=False,
            )
        return RunJobResponse(
            job_id=job_id,
            status="complete",
            message=f"Ran {len(results)} stage(s) successfully",
            started=started,
            completed=True,
            rejected=False,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        logger.exception("run_job_failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# POST /jobs/{job_id}/run/background  -- non-blocking background run
# --------------------------------------------------------------------------


@router.post("/{job_id}/run/background", response_model=BackgroundRunResponse)
async def run_job_background(
    job_id: str,
    request: Request,
    body: BackgroundRunRequest | None = None,
) -> BackgroundRunResponse:
    """Start a non-blocking pipeline run via the supervisor.

    Returns 409 if the job already has an active background run
    (duplicate run guard).
    """
    pipeline = _get_pipeline(request)
    supervisor = _get_supervisor(request)
    job = _load_job_or_404(pipeline, job_id)

    request_body = body or BackgroundRunRequest()
    accepted = supervisor.start_run(
        job,
        stage=request_body.stage,
        until_stage=request_body.until_stage,
    )
    if not accepted:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} already has an active run",
        )
    return BackgroundRunResponse(
        job_id=job_id,
        accepted=True,
        message="Background run started",
    )


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
    """Resume a job from the first incomplete stage (or a specific one).

    Uses the recovery module to prepare the job (reset target stage,
    clear stale runtime metadata) before starting the pipeline run.
    """
    pipeline = _get_pipeline(request)
    _load_job_or_404(pipeline, job_id)  # Validate job exists

    jobs_dir = pipeline.config.paths.jobs_dir

    try:
        job = prepare_resume(jobs_dir, job_id, from_stage=body.from_stage)
    except ValueError as exc:
        if "no incomplete stages to resume" not in str(exc):
            raise HTTPException(
                status_code=422,
                detail=[
                    {
                        "loc": ["body", "from_stage"],
                        "msg": str(exc),
                        "type": "value_error",
                    }
                ],
            ) from exc
        return ResumeJobResponse(
            job_id=job_id,
            status="complete",
            message=str(exc),
            started=False,
            completed=True,
            rejected=False,
        )

    # Determine which stage we are resuming from.
    resume_stage: str | None = body.from_stage
    if resume_stage is None:
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
            started=False,
            completed=True,
            rejected=False,
        )

    resume_until_stage = body.until_stage or Pipeline.STAGE_ORDER[-1]
    resume_start_index = Pipeline.STAGE_ORDER.index(resume_stage)
    resume_end_index = Pipeline.STAGE_ORDER.index(resume_until_stage)
    if resume_end_index < resume_start_index:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "until_stage"],
                    "msg": "until_stage must be the same as or after from_stage",
                    "type": "value_error",
                }
            ],
        )

    # Background (non-blocking) resume via supervisor
    if body.background:
        supervisor = _get_supervisor(request)
        accepted = supervisor.start_run(
            job,
            stage=resume_stage,
            until_stage=resume_until_stage,
        )
        if not accepted:
            raise HTTPException(
                status_code=409,
                detail=f"Job {job_id} already has an active run",
            )
        return ResumeJobResponse(
            job_id=job_id,
            status="running",
            message=f"Background resume started from {resume_stage} through {resume_until_stage}",
            started=True,
            completed=False,
            rejected=False,
        )

    # Synchronous (blocking) resume
    try:
        results = pipeline.run(
            job,
            stage=resume_stage,
            until_stage=resume_until_stage,
        )
        failed = [name for name, r in results.items() if not r.success]
        started = len(results) > 0
        if failed:
            return ResumeJobResponse(
                job_id=job_id,
                status="failed",
                message=f"Resume failed at stage(s): {', '.join(failed)}",
                started=started,
                completed=False,
                rejected=False,
            )
        return ResumeJobResponse(
            job_id=job_id,
            status="complete",
            message=f"Resumed from {resume_stage} through {resume_until_stage}",
            started=started,
            completed=True,
            rejected=False,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        logger.exception("resume_job_failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
