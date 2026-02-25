"""Regression tests for pipeline run locking behavior."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from podcast_pipeline.config import Config
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.stages.base import StageResult
from podcast_pipeline.utils.locks import JobLockAcquisitionError


class SleepStage:
    """Simple stage used to hold a lock during tests."""

    def __init__(self, *, delay_seconds: float, success: bool = True) -> None:
        self.delay_seconds = delay_seconds
        self.success = success

    def execute(self, job: Job, job_dir: Path) -> StageResult:
        time.sleep(self.delay_seconds)
        if self.success:
            return StageResult(success=True)
        return StageResult(success=False, error="forced-stage-failure")


def _seed_job(config: Config, job_id: str) -> Job:
    job = Job(job_id=job_id, input_file="/tmp/test.mp4")
    job.save(config.paths.jobs_dir)
    return job


def test_near_simultaneous_run_requests_allow_single_runner(config: Config) -> None:
    """Two near-simultaneous run attempts should allow only one executor."""
    seeded_job = _seed_job(config, "job-lock-race")
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def _attempt_run() -> None:
        pipeline = Pipeline(config)
        pipeline.stages["ingest"] = SleepStage(delay_seconds=0.25)
        loaded_job = pipeline.load_job(seeded_job.job_id)
        barrier.wait()
        outcome = "success"
        try:
            pipeline.run(loaded_job, stage="ingest")
        except JobLockAcquisitionError:
            outcome = "locked"
        with outcomes_lock:
            outcomes.append(outcome)

    worker_a = threading.Thread(target=_attempt_run)
    worker_b = threading.Thread(target=_attempt_run)
    worker_a.start()
    worker_b.start()
    worker_a.join(timeout=5)
    worker_b.join(timeout=5)

    assert not worker_a.is_alive()
    assert not worker_b.is_alive()
    assert sorted(outcomes) == ["locked", "success"]


def test_unknown_stage_rejection_preserves_job_state(config: Config) -> None:
    """Unknown stage inputs should fail fast and keep stage state untouched."""
    seeded_job = _seed_job(config, "job-lock-invalid-stage")
    pipeline = Pipeline(config)
    loaded_job = pipeline.load_job(seeded_job.job_id)

    with pytest.raises(ValueError, match="Unknown stage: bogus-stage"):
        pipeline.run(loaded_job, stage="bogus-stage")

    reloaded = pipeline.load_job(seeded_job.job_id)
    assert reloaded.status == StageStatus.PENDING
    assert all(stage.status == StageStatus.PENDING for stage in reloaded.stages.values())
    assert not (config.paths.jobs_dir / seeded_job.job_id / ".run.lock").exists()


def test_lock_is_released_after_stage_failure(config: Config) -> None:
    """A failed run should release lock so next run can proceed."""
    seeded_job = _seed_job(config, "job-lock-release")
    pipeline = Pipeline(config)
    pipeline.stages["ingest"] = SleepStage(delay_seconds=0.01, success=False)

    first_result = pipeline.run(pipeline.load_job(seeded_job.job_id), stage="ingest")
    assert first_result["ingest"].success is False

    pipeline.stages["ingest"] = SleepStage(delay_seconds=0.01, success=True)
    second_result = pipeline.run(pipeline.load_job(seeded_job.job_id), stage="ingest")
    assert second_result["ingest"].success is True
