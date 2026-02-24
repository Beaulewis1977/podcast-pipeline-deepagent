"""Background pipeline run orchestration with heartbeat metadata.

The supervisor provides non-blocking job execution by wrapping
pipeline runs in ``asyncio`` tasks. It persists runtime metadata
(pid, started_at, heartbeat, last_known_stage) to a ``runtime.json``
file under each job directory for crash/restart reconciliation and
guards against duplicate concurrent runs for the same job ID.

Phase 9 adds :class:`GPULease` -- a shared semaphore-based context
manager that serializes GPU-heavy workloads (thumbnail generation
and NVENC encoding) across concurrent jobs to prevent contention
on single-GPU machines.
"""

import asyncio
import json
import os
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 5.0
RUN_TIMEOUT_SECONDS = 1800.0


# ──────────────────────────────────────────────────────────────────────────────
# GPU Lease — cross-job serialization of GPU-heavy workloads
# ──────────────────────────────────────────────────────────────────────────────


class GPULease:
    """Semaphore-based context manager for serializing GPU-heavy operations.

    Thumbnail generation and NVENC-heavy encoding stages must not run
    concurrently across different jobs on a single-GPU machine.  The
    ``GPULease`` wraps a :class:`threading.Semaphore` with ``permits=1``
    so that at most one GPU-heavy workload is active at any time.

    Same-job stages already execute sequentially (the pipeline processes
    stages in order), so the lease only gates concurrent **cross-job**
    GPU operations.

    Usage::

        gpu_lease = GPULease()  # created once on Supervisor

        with gpu_lease.acquire(job_id="job-42", operation="thumbnail_gen"):
            # run GPU-heavy work
            ...

    The lease is non-blocking for the **same** job if it already holds it;
    different jobs block until the lease is released.
    """

    def __init__(self, permits: int = 1) -> None:
        self._semaphore = threading.Semaphore(permits)
        self._lock = threading.Lock()
        self._holder_job_id: str | None = None
        self._holder_operation: str | None = None

    @property
    def holder_job_id(self) -> str | None:
        """Return the job_id currently holding the GPU lease, or None."""
        with self._lock:
            return self._holder_job_id

    @property
    def holder_operation(self) -> str | None:
        """Return the operation name of the current lease holder."""
        with self._lock:
            return self._holder_operation

    def is_held(self) -> bool:
        """Return True if the GPU lease is currently held by any job."""
        with self._lock:
            return self._holder_job_id is not None

    @contextmanager
    def acquire(
        self,
        job_id: str,
        operation: str = "gpu",
        timeout: float | None = None,
    ) -> Generator[None, None, None]:
        """Acquire the GPU lease for a job.

        Args:
            job_id: Identifier of the job requesting GPU access.
            operation: Descriptive name of the GPU operation (for logging).
            timeout: Maximum seconds to wait.  ``None`` = wait indefinitely.

        Yields:
            Control once the lease is acquired.

        Raises:
            TimeoutError: If the lease cannot be acquired within ``timeout``.
        """
        logger.info(
            "gpu_lease_requested",
            job_id=job_id,
            operation=operation,
        )

        if timeout is not None:
            acquired = self._semaphore.acquire(timeout=timeout)
        else:
            # Block indefinitely until the semaphore is available.
            acquired = self._semaphore.acquire(blocking=True)

        if not acquired:
            raise TimeoutError(
                f"GPU lease not acquired within {timeout}s for job {job_id} ({operation})"
            )

        with self._lock:
            self._holder_job_id = job_id
            self._holder_operation = operation

        logger.info(
            "gpu_lease_acquired",
            job_id=job_id,
            operation=operation,
        )

        try:
            yield
        finally:
            with self._lock:
                self._holder_job_id = None
                self._holder_operation = None
            self._semaphore.release()
            logger.info(
                "gpu_lease_released",
                job_id=job_id,
                operation=operation,
            )


class RuntimeMeta:
    """Serialisable runtime metadata persisted beside each job's state.json."""

    def __init__(
        self,
        job_id: str,
        pid: int,
        started_at: str,
        heartbeat: str,
        last_known_stage: str | None = None,
        status: str = "running",
        timed_out_at: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.job_id = job_id
        self.pid = pid
        self.started_at = started_at
        self.heartbeat = heartbeat
        self.last_known_stage = last_known_stage
        self.status = status
        self.timed_out_at = timed_out_at
        self.timeout_seconds = timeout_seconds

    def to_dict(self) -> dict[str, Any]:
        """Return a dict of all public fields for JSON serialisation."""
        return {
            "job_id": self.job_id,
            "pid": self.pid,
            "started_at": self.started_at,
            "heartbeat": self.heartbeat,
            "last_known_stage": self.last_known_stage,
            "status": self.status,
            "timed_out_at": self.timed_out_at,
            "timeout_seconds": self.timeout_seconds,
        }

    def save(self, job_dir: Path) -> None:
        """Atomically write runtime.json into the job directory."""
        runtime_file = job_dir / "runtime.json"
        tmp = runtime_file.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.to_dict(), indent=2))
            tmp.rename(runtime_file)
        except OSError:
            logger.exception("runtime_meta_save_failed", job_dir=str(job_dir))

    @classmethod
    def load(cls, job_dir: Path) -> "RuntimeMeta | None":
        """Load runtime metadata from job directory, or None if absent."""
        runtime_file = job_dir / "runtime.json"
        if not runtime_file.exists():
            return None
        try:
            data = json.loads(runtime_file.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("runtime_meta_load_failed", path=str(runtime_file))
            return None
        return cls(
            job_id=data["job_id"],
            pid=data["pid"],
            started_at=data["started_at"],
            heartbeat=data["heartbeat"],
            last_known_stage=data.get("last_known_stage"),
            status=data.get("status", "unknown"),
            timed_out_at=data.get("timed_out_at"),
            timeout_seconds=data.get("timeout_seconds"),
        )

    @classmethod
    def clear(cls, job_dir: Path) -> None:
        """Remove runtime metadata file."""
        runtime_file = job_dir / "runtime.json"
        if runtime_file.exists():
            runtime_file.unlink()


class Supervisor:
    """Manages background pipeline runs and prevents duplicate execution.

    This object is stored on ``app.state`` and shared across requests.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        *,
        heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
        run_timeout_seconds: float = RUN_TIMEOUT_SECONDS,
    ) -> None:
        self.pipeline = pipeline
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.run_timeout_seconds = run_timeout_seconds
        # job_id -> asyncio.Task
        self._active: dict[str, asyncio.Task[None]] = {}
        # Phase 9: shared GPU lease for cross-job serialization of
        # Thumbnail generation and NVENC encoding workloads.
        self.gpu_lease = GPULease()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_running(self, job_id: str) -> bool:
        """Return True if a background task is currently active for this job."""
        task = self._active.get(job_id)
        return task is not None and not task.done()

    def start_run(
        self,
        job: Job,
        *,
        stage: str | None = None,
        until_stage: str | None = None,
    ) -> bool:
        """Launch a background pipeline run. Returns False if already running."""
        if self.is_running(job.job_id):
            return False

        task: asyncio.Task[None] = asyncio.create_task(
            self._run_with_heartbeat(job, stage=stage, until_stage=until_stage),
        )
        self._active[job.job_id] = task

        # Clean up entry when task finishes, but only if the mapping still
        # points to *this* task (a rapid restart may have replaced it).
        job_id = job.job_id

        def _cleanup(finished_task: asyncio.Task[None]) -> None:
            if self._active.get(job_id) is finished_task:
                del self._active[job_id]

        task.add_done_callback(_cleanup)
        return True

    def active_jobs(self) -> list[str]:
        """Return list of job_ids with active background runs."""
        return [jid for jid, t in self._active.items() if not t.done()]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_with_heartbeat(
        self,
        job: Job,
        *,
        stage: str | None = None,
        until_stage: str | None = None,
    ) -> None:
        """Execute pipeline.run in a thread and emit periodic heartbeats."""
        job_dir = job.get_job_dir(self.pipeline.config.paths.jobs_dir)
        now_iso = datetime.now(UTC).isoformat()
        meta = RuntimeMeta(
            job_id=job.job_id,
            pid=os.getpid(),
            started_at=now_iso,
            heartbeat=now_iso,
            timeout_seconds=self.run_timeout_seconds,
            status="running",
        )
        meta.last_known_stage = self._resolve_last_known_stage(job_dir)
        meta.save(job_dir)

        loop = asyncio.get_running_loop()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(meta, job_dir))
        run_future = loop.run_in_executor(
            None,
            lambda: self.pipeline.run(job, stage=stage, until_stage=until_stage),
        )

        try:
            # Run the blocking pipeline in a thread so we don't stall the event loop.
            await asyncio.wait_for(
                run_future,
                timeout=self.run_timeout_seconds,
            )
            meta.status = "complete"
        except TimeoutError:
            run_future.cancel()
            meta.status = "timed_out"
            meta.timed_out_at = datetime.now(UTC).isoformat()
            logger.exception(
                "background_run_timed_out",
                job_id=job.job_id,
                timeout_seconds=self.run_timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("background_run_failed", job_id=job.job_id, error=str(exc))
            meta.status = "failed"
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            meta.heartbeat = datetime.now(UTC).isoformat()
            meta.last_known_stage = self._resolve_last_known_stage(job_dir, meta.last_known_stage)
            meta.save(job_dir)

    async def _heartbeat_loop(self, meta: RuntimeMeta, job_dir: Path) -> None:
        """Periodically update heartbeat timestamp while the run is active."""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval_seconds)
                meta.heartbeat = datetime.now(UTC).isoformat()
                meta.last_known_stage = self._resolve_last_known_stage(
                    job_dir,
                    meta.last_known_stage,
                )
                meta.save(job_dir)
        except asyncio.CancelledError:
            return

    @staticmethod
    def _resolve_last_known_stage(job_dir: Path, fallback: str | None = None) -> str | None:
        """Read state.json and infer the latest stage with activity."""
        try:
            job = Job.load(job_dir)
        except Exception:
            return fallback

        for stage_name in reversed(Pipeline.STAGE_ORDER):
            stage = job.stages.get(stage_name)
            if stage is None:
                continue
            if stage.status in {
                StageStatus.RUNNING,
                StageStatus.COMPLETE,
                StageStatus.FAILED,
                StageStatus.WAITING,
            }:
                return stage_name
        return fallback


def is_stale_runtime(job_dir: Path, max_age_seconds: float = 30.0) -> bool:
    """Check whether a runtime.json heartbeat is stale (crash indicator).

    Returns True if a runtime file exists, claims to be running, but
    its heartbeat is older than *max_age_seconds*.
    """
    meta = RuntimeMeta.load(job_dir)
    if meta is None or meta.status != "running":
        return False
    try:
        last_beat = datetime.fromisoformat(meta.heartbeat)
        age = (datetime.now(UTC) - last_beat).total_seconds()
        return age > max_age_seconds
    except (ValueError, TypeError):
        return True
