"""Supervisor runtime reliability tests."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.service.supervisor import RuntimeMeta, Supervisor


class _StubPipeline:
    """Minimal pipeline stub used to drive supervisor behavior in tests."""

    def __init__(self, jobs_dir: Path, run_impl):
        self.config = SimpleNamespace(paths=SimpleNamespace(jobs_dir=jobs_dir))
        self._run_impl = run_impl

    def run(
        self,
        job: Job,
        *,
        stage: str | None = None,
        until_stage: str | None = None,
    ) -> dict[str, Any]:
        self._run_impl(job, stage=stage, until_stage=until_stage)
        return {}


def _create_job(jobs_dir: Path, job_id: str = "job-001") -> Job:
    """Create and persist a basic test job."""
    job = Job(job_id=job_id, input_file="/tmp/video.mp4")  # noqa: S108
    job.save(jobs_dir)
    return job


async def _wait_for(predicate, timeout_seconds: float = 1.0) -> None:
    """Poll until predicate returns True or fail after timeout."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    pytest.fail("Timed out waiting for supervisor state transition")


@pytest.mark.asyncio
async def test_heartbeat_persists_last_known_stage(tmp_path: Path) -> None:
    """Heartbeat writes include the latest stage touched by pipeline execution."""

    def _run_impl(job: Job, **_kwargs: object) -> None:
        job_dir = tmp_path / job.job_id

        live = Job.load(job_dir)
        live.update_stage("ingest", StageStatus.RUNNING)
        live.save(tmp_path)
        time.sleep(0.04)

        live = Job.load(job_dir)
        live.update_stage("ingest", StageStatus.COMPLETE)
        live.update_stage("transcribe", StageStatus.RUNNING)
        live.save(tmp_path)
        time.sleep(0.04)

        live = Job.load(job_dir)
        live.update_stage("transcribe", StageStatus.COMPLETE)
        live.save(tmp_path)

    pipeline = _StubPipeline(tmp_path, _run_impl)
    supervisor = Supervisor(
        pipeline,
        heartbeat_interval_seconds=0.01,
        run_timeout_seconds=5.0,
    )
    job = _create_job(tmp_path)

    assert supervisor.start_run(job) is True
    await _wait_for(lambda: not supervisor.is_running(job.job_id))

    meta = RuntimeMeta.load(tmp_path / job.job_id)
    assert meta is not None
    assert meta.status == "complete"
    assert meta.last_known_stage == "transcribe"


@pytest.mark.asyncio
async def test_timeout_marks_runtime_timed_out(tmp_path: Path) -> None:
    """Hung runs are marked timed_out with timeout metadata."""

    def _run_impl(_job: Job, **_kwargs: object) -> None:
        time.sleep(0.25)

    pipeline = _StubPipeline(tmp_path, _run_impl)
    supervisor = Supervisor(
        pipeline,
        heartbeat_interval_seconds=0.01,
        run_timeout_seconds=0.05,
    )
    job = _create_job(tmp_path)

    assert supervisor.start_run(job) is True
    await _wait_for(lambda: not supervisor.is_running(job.job_id))

    meta = RuntimeMeta.load(tmp_path / job.job_id)
    assert meta is not None
    assert meta.status == "timed_out"
    assert meta.timed_out_at is not None
    assert meta.timeout_seconds == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_duplicate_guard_recovers_after_timeout(tmp_path: Path) -> None:
    """Duplicate-run prevention remains intact before and after timeout exit."""

    def _run_impl(_job: Job, **_kwargs: object) -> None:
        time.sleep(0.20)

    pipeline = _StubPipeline(tmp_path, _run_impl)
    supervisor = Supervisor(
        pipeline,
        heartbeat_interval_seconds=0.01,
        run_timeout_seconds=0.05,
    )
    job = _create_job(tmp_path)

    assert supervisor.start_run(job) is True
    await asyncio.sleep(0.01)
    assert supervisor.start_run(job) is False

    await _wait_for(lambda: not supervisor.is_running(job.job_id))
    assert supervisor.start_run(job) is True
    await _wait_for(lambda: not supervisor.is_running(job.job_id))
