"""Base stage class and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from podcast_pipeline.config import Config
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StageResult:
    """Result of a stage execution."""

    success: bool
    outputs: list[str] = field(default_factory=list)
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class Stage(ABC):
    """Base class for pipeline stages."""

    name: str = "base"

    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger(f"stage.{self.name}")

    @abstractmethod
    def run(self, job: Job, job_dir: Path) -> StageResult:
        """Execute the stage.

        Args:
            job: Job instance
            job_dir: Path to job directory

        Returns:
            StageResult with success status and outputs
        """
        ...

    def should_run(self, job: Job) -> bool:
        """Check if this stage should run.

        Args:
            job: Job instance

        Returns:
            True if stage should run
        """
        stage = job.stages.get(self.name)
        if stage is None:
            return True
        return stage.status not in (StageStatus.COMPLETE, StageStatus.SKIPPED)

    def execute(self, job: Job, job_dir: Path) -> StageResult:
        """Execute the stage with state management.

        Args:
            job: Job instance
            job_dir: Path to job directory

        Returns:
            StageResult
        """
        if not self.should_run(job):
            self.logger.info("stage_skipped", stage=self.name, reason="already_complete")
            return StageResult(
                success=True,
                outputs=job.stages[self.name].outputs,
            )

        self.logger.info("stage_started", stage=self.name, job_id=job.job_id)
        job.update_stage(self.name, StageStatus.RUNNING)
        job.save(self.config.paths.jobs_dir)

        try:
            result = self.run(job, job_dir)

            if result.success:
                job.update_stage(
                    self.name,
                    StageStatus.COMPLETE,
                    outputs=result.outputs,
                )
                self.logger.info(
                    "stage_completed",
                    stage=self.name,
                    job_id=job.job_id,
                    outputs=result.outputs,
                )
            else:
                job.update_stage(
                    self.name,
                    StageStatus.FAILED,
                    error=result.error,
                )
                self.logger.error(
                    "stage_failed",
                    stage=self.name,
                    job_id=job.job_id,
                    error=result.error,
                )

        except Exception as e:
            error_msg = str(e)
            job.update_stage(self.name, StageStatus.FAILED, error=error_msg)
            self.logger.exception(
                "stage_exception",
                stage=self.name,
                job_id=job.job_id,
                error=error_msg,
            )
            result = StageResult(success=False, error=error_msg)

        job.save(self.config.paths.jobs_dir)
        return result
