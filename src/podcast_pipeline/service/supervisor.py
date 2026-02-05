"""Background pipeline run orchestration with heartbeat metadata.

The supervisor provides non-blocking job execution by wrapping
pipeline runs in ``asyncio`` tasks. It persists runtime metadata
(pid, started_at, heartbeat, last_known_stage) to a ``runtime.json``
file under each job directory for crash/restart reconciliation and
guards against duplicate concurrent runs for the same job ID.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from podcast_pipeline.models.job import Job
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 5


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
    ) -> None:
        self.job_id = job_id
        self.pid = pid
        self.started_at = started_at
        self.heartbeat = heartbeat
        self.last_known_stage = last_known_stage
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "pid": self.pid,
            "started_at": self.started_at,
            "heartbeat": self.heartbeat,
            "last_known_stage": self.last_known_stage,
            "status": self.status,
        }

    def save(self, job_dir: Path) -> None:
        """Atomically write runtime.json into the job directory."""
        runtime_file = job_dir / "runtime.json"
        tmp = runtime_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2))
        tmp.rename(runtime_file)

    @classmethod
    def load(cls, job_dir: Path) -> "RuntimeMeta | None":
        """Load runtime metadata from job directory, or None if absent."""
        runtime_file = job_dir / "runtime.json"
        if not runtime_file.exists():
            return None
        data = json.loads(runtime_file.read_text())
        return cls(
            job_id=data["job_id"],
            pid=data["pid"],
            started_at=data["started_at"],
            heartbeat=data["heartbeat"],
            last_known_stage=data.get("last_known_stage"),
            status=data.get("status", "unknown"),
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

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
        # job_id -> asyncio.Task
        self._active: dict[str, asyncio.Task[None]] = {}

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
        # Automatically clean up entry when task finishes
        task.add_done_callback(lambda _t: self._active.pop(job.job_id, None))
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
            status="running",
        )
        meta.save(job_dir)

        loop = asyncio.get_running_loop()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(meta, job_dir))

        try:
            # Run the blocking pipeline in a thread so we don't stall the event loop
            await loop.run_in_executor(
                None,
                lambda: self.pipeline.run(job, stage=stage, until_stage=until_stage),
            )
            meta.status = "complete"
        except Exception:
            logger.exception("background_run_failed", job_id=job.job_id)
            meta.status = "failed"
        finally:
            heartbeat_task.cancel()
            meta.heartbeat = datetime.now(UTC).isoformat()
            meta.save(job_dir)

    @staticmethod
    async def _heartbeat_loop(meta: RuntimeMeta, job_dir: Path) -> None:
        """Periodically update heartbeat timestamp while the run is active."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                meta.heartbeat = datetime.now(UTC).isoformat()
                meta.save(job_dir)
        except asyncio.CancelledError:
            return


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
