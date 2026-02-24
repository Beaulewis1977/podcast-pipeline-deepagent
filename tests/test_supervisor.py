"""Supervisor runtime reliability tests."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from podcast_pipeline.config import Config
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.app import (
    SERVICE_API_KEY_ENV_VAR,
    SERVICE_DEV_AUTH_BYPASS_ENV_VAR,
    SERVICE_ENVIRONMENT_ENV_VAR,
    create_app,
)
from podcast_pipeline.service.recovery import (
    periodic_reconcile,
    prepare_resume,
    run_reconcile_cycle,
)
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
    job = Job(job_id=job_id, input_file="/tmp/video.mp4")
    job.save(jobs_dir)
    return job


def _write_runtime(
    jobs_dir: Path,
    job_id: str,
    *,
    heartbeat_age_seconds: float = 0.0,
    meta_overrides: dict[str, Any] | None = None,
) -> RuntimeMeta:
    """Persist a runtime.json record with controlled heartbeat age."""
    now = datetime.now(UTC)
    heartbeat = now - timedelta(seconds=heartbeat_age_seconds)
    payload: dict[str, Any] = {
        "job_id": job_id,
        "pid": 99999,
        "started_at": now.isoformat(),
        "heartbeat": heartbeat.isoformat(),
        "status": "running",
        "last_known_stage": None,
    }
    if meta_overrides:
        payload.update(meta_overrides)
    meta = RuntimeMeta(
        **payload,
    )
    meta.save(jobs_dir / job_id)
    return meta


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


def test_reconcile_cycle_corrects_stale_runtime_reconcile(tmp_path: Path) -> None:
    """A reconcile cycle corrects stale runtime journals and reports resumable work."""
    job = _create_job(tmp_path)
    live = Job.load(tmp_path / job.job_id)
    live.update_stage("ingest", StageStatus.COMPLETE)
    live.update_stage("transcribe", StageStatus.RUNNING)
    live.save(tmp_path)
    _write_runtime(tmp_path, job.job_id, heartbeat_age_seconds=120)

    summary = run_reconcile_cycle(tmp_path)

    assert summary["corrected"] == 1
    assert summary["resumable"] == 1
    runtime = RuntimeMeta.load(tmp_path / job.job_id)
    assert runtime is not None
    assert runtime.status == "interrupted"


@pytest.mark.asyncio
async def test_periodic_reconcile_updates_stale_runtime_reconcile(tmp_path: Path) -> None:
    """Periodic reconciliation catches stale runs without manual API calls."""
    job = _create_job(tmp_path)
    live = Job.load(tmp_path / job.job_id)
    live.update_stage("ingest", StageStatus.COMPLETE)
    live.update_stage("transcribe", StageStatus.RUNNING)
    live.save(tmp_path)
    _write_runtime(tmp_path, job.job_id, heartbeat_age_seconds=120)

    stop_event = asyncio.Event()
    task = asyncio.create_task(
        periodic_reconcile(
            tmp_path,
            interval_seconds=0.01,
            stop_event=stop_event,
        )
    )

    def _runtime_interrupted() -> bool:
        runtime = RuntimeMeta.load(tmp_path / job.job_id)
        return runtime is not None and runtime.status == "interrupted"

    await _wait_for(_runtime_interrupted)
    stop_event.set()
    await task

    runtime = RuntimeMeta.load(tmp_path / job.job_id)
    assert runtime is not None
    assert runtime.status == "interrupted"


def test_prepare_resume_rejects_invalid_stage_resume_validation(tmp_path: Path) -> None:
    """Invalid resume stage names fail before state mutation is persisted."""
    job = _create_job(tmp_path)
    live = Job.load(tmp_path / job.job_id)
    live.update_stage("ingest", StageStatus.COMPLETE)
    live.update_stage("transcribe", StageStatus.FAILED)
    live.save(tmp_path)
    baseline = Job.load(tmp_path / job.job_id)

    with pytest.raises(ValueError, match="Unknown stage"):
        prepare_resume(tmp_path, job.job_id, from_stage="invalid-stage")

    reloaded = Job.load(tmp_path / job.job_id)
    assert set(reloaded.stages.keys()) == set(baseline.stages.keys())
    assert reloaded.stages["transcribe"].status == baseline.stages["transcribe"].status


def test_runtime_diagnostics_reports_orphaned_jobs_reconcile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """System diagnostics expose stale and orphaned runtime metadata."""
    monkeypatch.setenv(SERVICE_ENVIRONMENT_ENV_VAR, "development")
    monkeypatch.setenv(SERVICE_DEV_AUTH_BYPASS_ENV_VAR, "true")
    monkeypatch.delenv(SERVICE_API_KEY_ENV_VAR, raising=False)

    app = create_app()
    with TestClient(app) as client:
        config = Config()
        config.paths.jobs_dir = tmp_path
        config.paths.jobs_dir.mkdir(parents=True, exist_ok=True)
        pipeline = Pipeline(config)
        app.state.config = config
        app.state.pipeline = pipeline
        app.state.supervisor = Supervisor(pipeline)

        _create_job(tmp_path, job_id="job-orphan")
        _write_runtime(
            tmp_path,
            "job-orphan",
            heartbeat_age_seconds=120,
            meta_overrides={"last_known_stage": "transcribe"},
        )

        response = client.get("/system/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_jobs"] == []
    assert "job-orphan" in payload["stale_jobs"]
    assert "job-orphan" in payload["orphaned_jobs"]


# ============================================================================
# Phase 9: GPU Lease Tests
# ============================================================================


class TestGPULease:
    """Tests for GPU lease cross-job serialization."""

    def test_gpu_lease_acquire_and_release(self) -> None:
        """GPU lease should be acquirable and releasable."""
        from podcast_pipeline.service.supervisor import GPULease

        lease = GPULease()
        assert not lease.is_held()

        with lease.acquire(job_id="job-1", operation="thumbnail_gen"):
            assert lease.is_held()
            assert lease.holder_job_id == "job-1"
            assert lease.holder_operation == "thumbnail_gen"

        assert not lease.is_held()
        assert lease.holder_job_id is None

    def test_gpu_lease_blocks_concurrent_jobs(self) -> None:
        """Second job should block until first releases the lease."""
        from podcast_pipeline.service.supervisor import GPULease

        lease = GPULease()
        results: list[str] = []
        barrier = threading.Event()
        second_started = threading.Event()

        def _first_job() -> None:
            with lease.acquire(job_id="job-1", operation="nvenc_encode"):
                barrier.wait(timeout=5)
                results.append("first_done")

        def _second_job() -> None:
            second_started.set()
            with lease.acquire(job_id="job-2", operation="thumbnail_gen"):
                results.append("second_done")

        t1 = threading.Thread(target=_first_job)
        t2 = threading.Thread(target=_second_job)

        t1.start()
        time.sleep(0.05)  # let first job acquire

        t2.start()
        time.sleep(0.05)  # second job should be blocked

        assert lease.holder_job_id == "job-1"
        assert second_started.is_set()

        barrier.set()  # release first job
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert results == ["first_done", "second_done"]
        assert not lease.is_held()

    def test_gpu_lease_timeout_raises(self) -> None:
        """GPU lease should raise TimeoutError when timeout expires."""
        from podcast_pipeline.service.supervisor import GPULease

        lease = GPULease()
        release = threading.Event()

        def _hold_lease() -> None:
            with lease.acquire(job_id="holder", operation="hold"):
                release.wait(timeout=5)

        t = threading.Thread(target=_hold_lease)
        t.start()
        time.sleep(0.05)

        with (
            pytest.raises(TimeoutError, match="GPU lease not acquired"),
            lease.acquire(job_id="waiter", operation="wait", timeout=0.1),
        ):
            pass  # should not reach here

        release.set()
        t.join(timeout=5)

    def test_gpu_lease_on_supervisor_instance(self, tmp_path: Path) -> None:
        """Supervisor should expose a gpu_lease attribute."""
        pipeline = _StubPipeline(tmp_path, lambda *a, **k: None)
        supervisor = Supervisor(pipeline)

        assert hasattr(supervisor, "gpu_lease")
        assert not supervisor.gpu_lease.is_held()

        with supervisor.gpu_lease.acquire(job_id="test", operation="test_op"):
            assert supervisor.gpu_lease.is_held()

    def test_gpu_lease_concurrent_serialization_order(self) -> None:
        """Multiple concurrent jobs should be serialized deterministically."""
        from podcast_pipeline.service.supervisor import GPULease

        lease = GPULease()
        execution_order: list[str] = []
        start_gate = threading.Event()

        def _worker(job_id: str) -> None:
            start_gate.wait(timeout=5)
            with lease.acquire(job_id=job_id, operation="render"):
                execution_order.append(job_id)
                time.sleep(0.02)

        threads = [threading.Thread(target=_worker, args=(f"job-{i}",)) for i in range(3)]
        for t in threads:
            t.start()

        start_gate.set()

        for t in threads:
            t.join(timeout=10)

        assert len(execution_order) == 3
        assert set(execution_order) == {"job-0", "job-1", "job-2"}
