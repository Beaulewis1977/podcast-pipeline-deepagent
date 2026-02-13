"""Recovery and resume regression tests.

Tests cover:
- Runtime/canonical state reconciliation after simulated interruption
- Resumable job identification
- Resume preparation (stage reset + runtime cleanup)
- Service client resumable jobs contract
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from podcast_pipeline.models.job import Job, JobStage, StageStatus
from podcast_pipeline.service.recovery import (
    list_resumable_jobs,
    prepare_resume,
    reconcile_all_jobs,
    reconcile_job,
    startup_reconcile,
)
from podcast_pipeline.service.supervisor import RuntimeMeta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_job(
    jobs_dir: Path,
    job_id: str = "test-job-001",
    *,
    stages: dict[str, StageStatus] | None = None,
) -> Job:
    """Create a test job with specified stage statuses on disk."""
    default_stages = {
        "ingest": StageStatus.PENDING,
        "transcribe": StageStatus.PENDING,
        "analyze": StageStatus.PENDING,
        "review": StageStatus.PENDING,
        "render": StageStatus.PENDING,
    }
    if stages:
        default_stages.update(stages)

    initial_status = (
        StageStatus.RUNNING
        if any(status != StageStatus.PENDING for status in default_stages.values())
        else StageStatus.PENDING
    )

    job = Job(
        job_id=job_id,
        input_file="/tmp/test.mp4",  # noqa: S108
        status=initial_status,
        stages={name: JobStage(status=status) for name, status in default_stages.items()},
    )
    job._update_overall_status()
    job.save(jobs_dir)
    return job


def _write_runtime(
    jobs_dir: Path,
    job_id: str,
    *,
    status: str = "running",
    heartbeat_age_seconds: float = 0,
    pid: int = 99999,
) -> RuntimeMeta:
    """Write a runtime.json with controllable heartbeat age."""
    now = datetime.now(UTC)
    heartbeat = now.timestamp() - heartbeat_age_seconds
    heartbeat_iso = datetime.fromtimestamp(heartbeat, tz=UTC).isoformat()
    meta = RuntimeMeta(
        job_id=job_id,
        pid=pid,
        started_at=now.isoformat(),
        heartbeat=heartbeat_iso,
        status=status,
    )
    meta.save(jobs_dir / job_id)
    return meta


# ---------------------------------------------------------------------------
# Reconciliation tests
# ---------------------------------------------------------------------------


class TestReconcileJob:
    """Tests for reconcile_job and reconcile_all_jobs."""

    def test_reconcile_stale_runtime_marks_interrupted(self, tmp_path: Path) -> None:
        """A running runtime with stale heartbeat is marked interrupted."""
        _create_test_job(
            tmp_path,
            stages={"ingest": StageStatus.COMPLETE, "transcribe": StageStatus.RUNNING},
        )
        _write_runtime(tmp_path, "test-job-001", heartbeat_age_seconds=120)

        changed = reconcile_job(tmp_path / "test-job-001")
        assert changed is True

        # Runtime should be corrected
        meta = RuntimeMeta.load(tmp_path / "test-job-001")
        assert meta is not None
        assert meta.status == "interrupted"

    def test_reconcile_running_stage_without_runtime_marks_failed(self, tmp_path: Path) -> None:
        """A stage marked 'running' without live runtime gets marked 'failed'."""
        _create_test_job(
            tmp_path,
            stages={"ingest": StageStatus.COMPLETE, "transcribe": StageStatus.RUNNING},
        )
        # No runtime.json at all

        changed = reconcile_job(tmp_path / "test-job-001")
        assert changed is True

        job = Job.load(tmp_path / "test-job-001")
        assert job.stages["transcribe"].status == StageStatus.FAILED
        assert "Interrupted" in (job.stages["transcribe"].error or "")

    def test_reconcile_complete_job_unchanged(self, tmp_path: Path) -> None:
        """A fully complete job is not modified by reconciliation."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.COMPLETE,
                "review": StageStatus.COMPLETE,
                "render": StageStatus.COMPLETE,
            },
        )

        changed = reconcile_job(tmp_path / "test-job-001")
        assert changed is False

    def test_reconcile_dead_pid_marks_interrupted(self, tmp_path: Path) -> None:
        """A running runtime whose PID is dead is marked interrupted."""
        _create_test_job(
            tmp_path,
            stages={"ingest": StageStatus.COMPLETE, "transcribe": StageStatus.RUNNING},
        )
        # Use PID 1 which is unlikely to be our process but usually alive;
        # use PID 0 which will get PermissionError.
        # Instead, use a very high PID that almost certainly doesn't exist.
        _write_runtime(
            tmp_path,
            "test-job-001",
            heartbeat_age_seconds=0,  # fresh heartbeat
            pid=4_000_000,  # non-existent PID
        )

        changed = reconcile_job(tmp_path / "test-job-001")
        assert changed is True

        meta = RuntimeMeta.load(tmp_path / "test-job-001")
        assert meta is not None
        assert meta.status == "interrupted"

    def test_reconcile_all_jobs_counts_corrected(self, tmp_path: Path) -> None:
        """reconcile_all_jobs returns count of corrected jobs."""
        _create_test_job(
            tmp_path,
            job_id="job-a",
            stages={"ingest": StageStatus.RUNNING},
        )
        _create_test_job(
            tmp_path,
            job_id="job-b",
            stages={"ingest": StageStatus.COMPLETE},
        )
        # job-a has running stage + no runtime = needs correction
        # job-b is fine
        corrected = reconcile_all_jobs(tmp_path)
        assert corrected == 1

    def test_reconcile_missing_dir_returns_zero(self, tmp_path: Path) -> None:
        """reconcile_all_jobs on non-existent dir returns 0."""
        assert reconcile_all_jobs(tmp_path / "nonexistent") == 0

    def test_reconcile_preserves_completed_runtime(self, tmp_path: Path) -> None:
        """A runtime with status=complete is not corrected."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.COMPLETE,
                "review": StageStatus.COMPLETE,
                "render": StageStatus.COMPLETE,
            },
        )
        _write_runtime(tmp_path, "test-job-001", status="complete")

        changed = reconcile_job(tmp_path / "test-job-001")
        assert changed is False


# ---------------------------------------------------------------------------
# Resumable job identification tests
# ---------------------------------------------------------------------------


class TestListResumableJobs:
    """Tests for list_resumable_jobs."""

    def test_resumable_after_interruption(self, tmp_path: Path) -> None:
        """Job with completed + failed stages is resumable."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.FAILED,
            },
        )

        resumable = list_resumable_jobs(tmp_path)
        assert len(resumable) == 1
        assert resumable[0].job_id == "test-job-001"
        assert resumable[0].resume_stage == "transcribe"
        assert "ingest" in resumable[0].completed_stages
        assert "transcribe" in resumable[0].failed_stages

    def test_not_resumable_without_completed_work(self, tmp_path: Path) -> None:
        """Job with no completed stages is not resumable."""
        _create_test_job(tmp_path, stages={"ingest": StageStatus.FAILED})

        resumable = list_resumable_jobs(tmp_path)
        assert len(resumable) == 0

    def test_not_resumable_when_fully_complete(self, tmp_path: Path) -> None:
        """Fully completed job is not resumable."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.COMPLETE,
                "review": StageStatus.COMPLETE,
                "render": StageStatus.COMPLETE,
            },
        )

        resumable = list_resumable_jobs(tmp_path)
        assert len(resumable) == 0

    def test_not_resumable_when_actively_running(self, tmp_path: Path) -> None:
        """Job with live (non-stale) runtime is not resumable."""
        import os

        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.RUNNING,
            },
        )
        # Write a fresh runtime with our own PID (guaranteed alive).
        _write_runtime(
            tmp_path,
            "test-job-001",
            heartbeat_age_seconds=0,
            pid=os.getpid(),
        )

        resumable = list_resumable_jobs(tmp_path)
        assert len(resumable) == 0

    def test_resumable_interrupted_flag(self, tmp_path: Path) -> None:
        """Job with interrupted runtime is flagged as interrupted."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.FAILED,
            },
        )
        _write_runtime(tmp_path, "test-job-001", status="interrupted")

        resumable = list_resumable_jobs(tmp_path)
        assert len(resumable) == 1
        assert resumable[0].interrupted is True

    def test_multiple_resumable_jobs(self, tmp_path: Path) -> None:
        """Multiple interrupted jobs are all returned."""
        _create_test_job(
            tmp_path,
            job_id="job-a",
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.FAILED,
            },
        )
        _create_test_job(
            tmp_path,
            job_id="job-b",
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.FAILED,
            },
        )

        resumable = list_resumable_jobs(tmp_path)
        assert len(resumable) == 2
        ids = {r.job_id for r in resumable}
        assert ids == {"job-a", "job-b"}

    def test_resumable_empty_dir(self, tmp_path: Path) -> None:
        """Empty jobs directory returns empty list."""
        assert list_resumable_jobs(tmp_path) == []


# ---------------------------------------------------------------------------
# Resume preparation tests
# ---------------------------------------------------------------------------


class TestPrepareResume:
    """Tests for prepare_resume."""

    def test_prepare_resume_resets_failed_stage(self, tmp_path: Path) -> None:
        """Failed stage is reset to pending for resume."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.FAILED,
            },
        )

        job = prepare_resume(tmp_path, "test-job-001")
        assert job.stages["transcribe"].status == StageStatus.PENDING

    def test_prepare_resume_clears_runtime(self, tmp_path: Path) -> None:
        """Runtime journal is cleared after resume preparation."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.FAILED,
            },
        )
        _write_runtime(tmp_path, "test-job-001", status="interrupted")

        prepare_resume(tmp_path, "test-job-001")
        runtime = RuntimeMeta.load(tmp_path / "test-job-001")
        assert runtime is None

    def test_prepare_resume_auto_detects_stage(self, tmp_path: Path) -> None:
        """Without from_stage, first incomplete stage is used."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.FAILED,
            },
        )

        job = prepare_resume(tmp_path, "test-job-001")
        assert job.stages["analyze"].status == StageStatus.PENDING

    def test_prepare_resume_explicit_stage(self, tmp_path: Path) -> None:
        """Explicit from_stage resets that specific stage."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.FAILED,
                "review": StageStatus.FAILED,
            },
        )

        job = prepare_resume(tmp_path, "test-job-001", from_stage="review")
        # Review should be reset, analyze left as-is
        assert job.stages["review"].status == StageStatus.PENDING
        assert job.stages["analyze"].status == StageStatus.FAILED

    def test_prepare_resume_raises_for_complete_job(self, tmp_path: Path) -> None:
        """ValueError raised when all stages are complete."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.COMPLETE,
                "review": StageStatus.COMPLETE,
                "render": StageStatus.COMPLETE,
            },
        )

        with pytest.raises(ValueError, match="no incomplete stages"):
            prepare_resume(tmp_path, "test-job-001")

    def test_prepare_resume_raises_for_missing_job(self, tmp_path: Path) -> None:
        """FileNotFoundError raised for non-existent job."""
        with pytest.raises(FileNotFoundError):
            prepare_resume(tmp_path, "no-such-job")

    def test_prepare_resume_saved_to_disk(self, tmp_path: Path) -> None:
        """Resume preparation persists the updated state to disk."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.FAILED,
            },
        )

        prepare_resume(tmp_path, "test-job-001")

        # Re-load from disk
        reloaded = Job.load(tmp_path / "test-job-001")
        assert reloaded.stages["transcribe"].status == StageStatus.PENDING


# ---------------------------------------------------------------------------
# Startup reconciliation tests
# ---------------------------------------------------------------------------


class TestStartupReconcile:
    """Tests for startup_reconcile integration helper."""

    def test_startup_reconcile_returns_summary(self, tmp_path: Path) -> None:
        """startup_reconcile returns corrected and resumable counts."""
        _create_test_job(
            tmp_path,
            job_id="job-stale",
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.RUNNING,
            },
        )
        # No runtime -> reconcile will mark transcribe as failed
        result = startup_reconcile(tmp_path)
        assert result["corrected"] == 1
        assert result["resumable"] == 1

    def test_startup_reconcile_empty_dir(self, tmp_path: Path) -> None:
        """startup_reconcile on empty dir returns zeros."""
        result = startup_reconcile(tmp_path)
        assert result == {"corrected": 0, "resumable": 0}

    def test_startup_reconcile_no_resumable_after_full_complete(self, tmp_path: Path) -> None:
        """Fully complete jobs yield zero resumable count."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.COMPLETE,
                "review": StageStatus.COMPLETE,
                "render": StageStatus.COMPLETE,
            },
        )
        result = startup_reconcile(tmp_path)
        assert result["corrected"] == 0
        assert result["resumable"] == 0

    def test_startup_reconcile_mixed_jobs(self, tmp_path: Path) -> None:
        """Mix of complete, interrupted, and pending jobs reconciled correctly."""
        # Job 1: complete -- not touched
        _create_test_job(
            tmp_path,
            job_id="job-done",
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.COMPLETE,
                "review": StageStatus.COMPLETE,
                "render": StageStatus.COMPLETE,
            },
        )
        # Job 2: interrupted mid-run -- needs reconciliation
        _create_test_job(
            tmp_path,
            job_id="job-interrupted",
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.COMPLETE,
                "analyze": StageStatus.RUNNING,
            },
        )
        # Job 3: pending only -- not resumable (no completed work)
        _create_test_job(
            tmp_path,
            job_id="job-fresh",
            stages={
                "ingest": StageStatus.PENDING,
            },
        )

        result = startup_reconcile(tmp_path)
        assert result["corrected"] == 1  # job-interrupted
        assert result["resumable"] == 1  # job-interrupted (after correction)


# ---------------------------------------------------------------------------
# End-to-end reconcile-then-resume scenario tests
# ---------------------------------------------------------------------------


class TestReconcileThenResume:
    """Integration-style tests that chain reconcile -> list -> resume."""

    def test_reconcile_then_list_then_resume(self, tmp_path: Path) -> None:
        """Full recovery flow: reconcile stale job, list it, resume it."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.RUNNING,
            },
        )
        _write_runtime(tmp_path, "test-job-001", heartbeat_age_seconds=120)

        # Step 1: Reconcile
        corrected = reconcile_all_jobs(tmp_path)
        assert corrected == 1

        # Step 2: List resumable
        resumable = list_resumable_jobs(tmp_path)
        assert len(resumable) == 1
        assert resumable[0].job_id == "test-job-001"
        assert resumable[0].resume_stage == "transcribe"
        assert resumable[0].interrupted is True

        # Step 3: Prepare resume
        job = prepare_resume(tmp_path, "test-job-001")
        assert job.stages["transcribe"].status == StageStatus.PENDING

        # After resume preparation, runtime should be cleared
        assert RuntimeMeta.load(tmp_path / "test-job-001") is None

    def test_reconcile_multiple_stages_interrupted(self, tmp_path: Path) -> None:
        """Job with multiple running stages gets all corrected."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.RUNNING,
                "analyze": StageStatus.RUNNING,
            },
        )

        corrected = reconcile_all_jobs(tmp_path)
        assert corrected == 1

        job = Job.load(tmp_path / "test-job-001")
        assert job.stages["transcribe"].status == StageStatus.FAILED
        assert job.stages["analyze"].status == StageStatus.FAILED

    def test_resume_idempotent_on_already_pending(self, tmp_path: Path) -> None:
        """Resuming a job whose target stage is already pending is safe."""
        _create_test_job(
            tmp_path,
            stages={
                "ingest": StageStatus.COMPLETE,
                "transcribe": StageStatus.PENDING,
            },
        )

        job = prepare_resume(tmp_path, "test-job-001", from_stage="transcribe")
        assert job.stages["transcribe"].status == StageStatus.PENDING
