"""Backend crash-recovery and state reconciliation logic.

This module provides functions to:

1. **Reconcile** runtime journal files (``runtime.json``) against
   canonical job state (``state.json``) after a process restart.
2. **Identify resumable jobs** -- jobs whose pipeline was interrupted
   mid-run and can safely be retried from the last incomplete stage.
3. **Prepare a resume** by resetting stale stages so the pipeline
   treats them as runnable again.

The reconciliation strategy is conservative:

* A ``runtime.json`` that claims "running" but whose heartbeat is stale
  (or whose PID is no longer alive) is corrected to ``"interrupted"``.
* A ``state.json`` stage marked ``running`` without a live heartbeat is
  downgraded to ``failed`` so the resume logic can re-queue it.
* Completed stages are never touched.

Usage::

    from podcast_pipeline.service.recovery import (
        reconcile_all_jobs,
        list_resumable_jobs,
        prepare_resume,
    )

    reconcile_all_jobs(jobs_dir)
    resumable = list_resumable_jobs(jobs_dir)
    for info in resumable:
        prepare_resume(jobs_dir, info.job_id, from_stage=info.resume_stage)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel, Field

from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.supervisor import RuntimeMeta, is_stale_runtime
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# Maximum heartbeat age (seconds) before a runtime is considered stale.
_STALE_HEARTBEAT_SECONDS = 30.0
DEFAULT_RECONCILE_INTERVAL_SECONDS = 30.0


class ResumableJob(BaseModel):
    """Description of a job that can be resumed."""

    job_id: str
    status: str
    resume_stage: str
    completed_stages: list[str] = Field(default_factory=list)
    failed_stages: list[str] = Field(default_factory=list)
    interrupted: bool = False


def _is_pid_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we lack permission to signal it.
        return True
    return True


def reconcile_job(job_dir: Path) -> bool:
    """Reconcile a single job's runtime journal with canonical state.

    Returns ``True`` if any corrections were applied.
    """
    state_file = job_dir / "state.json"
    if not state_file.exists():
        return False

    try:
        job = Job.load(job_dir)
    except Exception:
        logger.warning("reconcile_skip_invalid", job_dir=str(job_dir))
        return False

    changed = False
    runtime = RuntimeMeta.load(job_dir)

    # --- Runtime journal corrections ---
    if runtime is not None and runtime.status == "running":
        stale = is_stale_runtime(job_dir, max_age_seconds=_STALE_HEARTBEAT_SECONDS)
        pid_dead = not _is_pid_alive(runtime.pid)
        if stale or pid_dead:
            runtime.status = "interrupted"
            runtime.save(job_dir)
            logger.info(
                "runtime_corrected",
                job_id=job.job_id,
                reason="stale_heartbeat" if stale else "dead_pid",
            )
            changed = True

    # --- Canonical stage corrections ---
    for stage_name, stage_obj in job.stages.items():
        if stage_obj.status == StageStatus.RUNNING:
            # A stage marked running with no live runtime is interrupted.
            if runtime is None or runtime.status != "running":
                stage_obj.status = StageStatus.FAILED
                stage_obj.error = "Interrupted: process exited before stage completed"
                changed = True
                logger.info(
                    "stage_corrected",
                    job_id=job.job_id,
                    stage=stage_name,
                    new_status="failed",
                )

    if changed:
        job._update_overall_status()
        job.save(job_dir.parent)

    return changed


def reconcile_all_jobs(jobs_dir: Path) -> int:
    """Reconcile every job under *jobs_dir*.

    Returns the number of jobs that had corrections applied.
    """
    if not jobs_dir.exists():
        return 0

    corrected = 0
    for entry in jobs_dir.iterdir():
        if entry.is_dir() and (entry / "state.json").exists():
            if reconcile_job(entry):
                corrected += 1
    return corrected


def run_reconcile_cycle(jobs_dir: Path) -> dict[str, int]:
    """Reconcile all jobs and return corrected/resumable summary."""
    corrected = reconcile_all_jobs(jobs_dir)
    resumable = list_resumable_jobs(jobs_dir)
    return {"corrected": corrected, "resumable": len(resumable)}


async def periodic_reconcile(
    jobs_dir: Path,
    *,
    interval_seconds: float = DEFAULT_RECONCILE_INTERVAL_SECONDS,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run reconciliation repeatedly until cancelled or stop_event is set."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be > 0")

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        await asyncio.sleep(interval_seconds)
        if stop_event is not None and stop_event.is_set():
            return

        summary = run_reconcile_cycle(jobs_dir)
        if summary["corrected"] > 0:
            logger.info(
                "periodic_reconcile_corrected",
                corrected=summary["corrected"],
                resumable=summary["resumable"],
            )


def _first_incomplete_stage(job: Job) -> str | None:
    """Return the name of the first non-complete stage in pipeline order."""
    for stage_name in Pipeline.STAGE_ORDER:
        stage_obj = job.stages.get(stage_name)
        if stage_obj is None or stage_obj.status != StageStatus.COMPLETE:
            return stage_name
    return None


def list_resumable_jobs(jobs_dir: Path) -> list[ResumableJob]:
    """List jobs that can be resumed after reconciliation.

    A job is resumable if:
    * It has at least one completed stage (work was done).
    * It has at least one non-complete stage (work remains).
    * It is not currently running (no live runtime).
    """
    if not jobs_dir.exists():
        return []

    resumable: list[ResumableJob] = []

    for entry in sorted(jobs_dir.iterdir()):
        if not entry.is_dir():
            continue
        state_file = entry / "state.json"
        if not state_file.exists():
            continue

        try:
            job = Job.load(entry)
        except Exception:
            logger.warning("resumable_scan_skip", job_dir=str(entry))
            continue

        # Skip jobs that are actively running.
        runtime = RuntimeMeta.load(entry)
        if runtime is not None and runtime.status == "running":
            if not is_stale_runtime(entry, max_age_seconds=_STALE_HEARTBEAT_SECONDS):
                continue

        completed = [
            name
            for name in Pipeline.STAGE_ORDER
            if job.stages.get(name) and job.stages[name].status == StageStatus.COMPLETE
        ]
        failed = [
            name
            for name in Pipeline.STAGE_ORDER
            if job.stages.get(name) and job.stages[name].status == StageStatus.FAILED
        ]

        # Must have some completed work and remaining work.
        if not completed:
            continue

        resume_stage = _first_incomplete_stage(job)
        if resume_stage is None:
            continue  # All stages complete.

        # Detect if the job was interrupted (runtime says so, or a stage was running).
        interrupted = (runtime is not None and runtime.status == "interrupted") or any(
            job.stages.get(s) and job.stages[s].status == StageStatus.RUNNING
            for s in Pipeline.STAGE_ORDER
        )

        resumable.append(
            ResumableJob(
                job_id=job.job_id,
                status=job.status.value,
                resume_stage=resume_stage,
                completed_stages=completed,
                failed_stages=failed,
                interrupted=interrupted,
            )
        )

    return resumable


def prepare_resume(
    jobs_dir: Path,
    job_id: str,
    from_stage: str | None = None,
) -> Job:
    """Prepare a job for resume by resetting the target stage to ``pending``.

    Parameters
    ----------
    jobs_dir:
        Root jobs directory.
    job_id:
        Job identifier.
    from_stage:
        Stage to resume from.  If ``None``, defaults to the first
        non-complete stage in pipeline order.

    Returns
    -------
    The updated :class:`Job` object (already saved to disk).

    Raises
    ------
    FileNotFoundError
        If the job does not exist.
    ValueError
        If there is no stage to resume.
    """
    job_dir = jobs_dir / job_id
    job = Job.load(job_dir)

    if from_stage is not None:
        Job.validate_stage_name(from_stage)

    if from_stage is None:
        from_stage = _first_incomplete_stage(job)
    if from_stage is None:
        raise ValueError(f"Job {job_id} has no incomplete stages to resume")

    # Reset the target stage so pipeline will re-run it.
    job.update_stage(from_stage, StageStatus.PENDING)

    # Clear runtime journal so supervisor doesn't think a run is active.
    RuntimeMeta.clear(job_dir)

    job.save(jobs_dir)
    logger.info("job_prepared_for_resume", job_id=job_id, from_stage=from_stage)
    return job


def startup_reconcile(jobs_dir: Path) -> dict[str, int]:
    """Run reconciliation and return a summary suitable for logging.

    Intended to be called once during service lifespan startup so that
    stale runtime metadata is corrected before any client queries arrive.

    Returns
    -------
    A dict with keys ``corrected`` (number of jobs fixed) and
    ``resumable`` (number of jobs available for resume).
    """
    summary = run_reconcile_cycle(jobs_dir)
    logger.info(
        "startup_reconcile_complete",
        corrected=summary["corrected"],
        resumable=summary["resumable"],
    )
    return summary
