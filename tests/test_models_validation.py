"""Focused validation tests for job and config invariants."""

import pytest
from pydantic import ValidationError

from podcast_pipeline.config import ModelConfig, ServiceConfig
from podcast_pipeline.models.job import Job, JobStage, StageStatus


class TestJobModelValidation:
    """Validation invariants for runtime job state models."""

    def test_job_rejects_path_traversal_job_id(self):
        """Job IDs cannot include path traversal tokens."""
        with pytest.raises(ValidationError):
            Job(job_id="../escape", input_file="/tmp/video.mp4")  # noqa: S108

    def test_job_rejects_path_separator_job_id(self):
        """Job IDs cannot include separators that escape jobs_dir."""
        with pytest.raises(ValidationError):
            Job(job_id="foo/bar", input_file="/tmp/video.mp4")  # noqa: S108

    def test_job_rejects_complete_status_with_error(self):
        """Top-level COMPLETE + error is contradictory."""
        with pytest.raises(ValidationError):
            Job(
                job_id="job-complete-with-error",
                input_file="/tmp/video.mp4",  # noqa: S108
                status=StageStatus.COMPLETE,
                error="unexpected failure",
            )

    def test_job_rejects_pending_status_with_stage_progress(self):
        """Pending jobs cannot report stage progress yet."""
        with pytest.raises(ValidationError):
            Job(
                job_id="job-pending-with-progress",
                input_file="/tmp/video.mp4",  # noqa: S108
                status=StageStatus.PENDING,
                stages={
                    "ingest": JobStage(status=StageStatus.PENDING, progress_percent=10),
                },
            )

    def test_job_stage_rejects_pending_status_with_progress(self):
        """Pending stages cannot include progress_percent."""
        with pytest.raises(ValidationError):
            JobStage(status=StageStatus.PENDING, progress_percent=25)

    def test_job_stage_rejects_complete_status_with_error(self):
        """Complete stages cannot still carry an error."""
        with pytest.raises(ValidationError):
            JobStage(status=StageStatus.COMPLETE, error="still failing")

    def test_job_update_stage_progress_rejects_out_of_bounds(self):
        """Runtime progress updates enforce 0-100 range."""
        job = Job(job_id="job-progress-range", input_file="/tmp/video.mp4")  # noqa: S108
        job.update_stage("ingest", StageStatus.RUNNING)

        with pytest.raises(ValueError, match="between 0 and 100"):
            job.update_stage_progress("ingest", progress_percent=101)

        with pytest.raises(ValueError, match="between 0 and 100"):
            job.update_stage_progress("ingest", progress_percent=-1)

    def test_job_update_stage_progress_rejects_pending_stage(self):
        """Pending stages cannot receive runtime progress updates."""
        job = Job(job_id="job-pending-progress", input_file="/tmp/video.mp4")  # noqa: S108

        with pytest.raises(ValueError, match="Cannot set progress_percent"):
            job.update_stage_progress("ingest", progress_percent=10)


class TestConfigModelValidation:
    """Validation invariants for runtime config models."""

    def test_config_rejects_unknown_provider(self):
        """Primary model provider must be known."""
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai")

    def test_config_rejects_unsupported_model_for_provider(self):
        """Model choices must match provider capability."""
        with pytest.raises(ValidationError):
            ModelConfig(provider="gemini", model="moonshot-v1-128k")

    def test_config_requires_fallback_provider_and_model_pair(self):
        """Fallback provider/model must be configured together."""
        with pytest.raises(ValidationError):
            ModelConfig(fallback_provider="kimi", fallback_model=None)

        with pytest.raises(ValidationError):
            ModelConfig(fallback_provider=None, fallback_model="kimi-k2.5")

    def test_config_rejects_unsupported_fallback_model(self):
        """Fallback model must be supported by fallback provider."""
        with pytest.raises(ValidationError):
            ModelConfig(fallback_provider="kimi", fallback_model="gemini-2.5-flash")

    def test_config_rejects_service_host_with_scheme_or_port(self):
        """Service host must be host-only with no URL scheme/port."""
        with pytest.raises(ValidationError):
            ServiceConfig(host="http://localhost")

        with pytest.raises(ValidationError):
            ServiceConfig(host="localhost:8787")

    def test_config_rejects_service_port_out_of_bounds(self):
        """Service port must remain within valid TCP bounds."""
        with pytest.raises(ValidationError):
            ServiceConfig(port=0)

        with pytest.raises(ValidationError):
            ServiceConfig(port=70000)

    def test_config_accepts_valid_ipv6_host(self):
        """Bracketed IPv6 hosts remain valid."""
        config = ServiceConfig(host="[::1]", port=8787)
        assert config.base_url == "http://[::1]:8787"
