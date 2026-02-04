"""Pipeline orchestration."""

from pathlib import Path
from typing import Any

from podcast_pipeline.config import Config, load_config
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.stages.analyze import AnalyzeStage
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.stages.ingest import IngestStage
from podcast_pipeline.stages.render import RenderStage
from podcast_pipeline.stages.review import ReviewStage
from podcast_pipeline.stages.transcribe import TranscribeStage
from podcast_pipeline.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


class Pipeline:
    """Pipeline orchestrator."""

    STAGE_ORDER = ["ingest", "transcribe", "analyze", "review", "render"]

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.stages: dict[str, Stage] = {
            "ingest": IngestStage(self.config),
            "transcribe": TranscribeStage(self.config),
            "analyze": AnalyzeStage(self.config),
            "review": ReviewStage(self.config),
            "render": RenderStage(self.config),
        }

    def create_job(
        self,
        video_path: Path,
        name: str | None = None,
        job_id: str | None = None,
    ) -> Job:
        """Create a new job from a video file.

        Args:
            video_path: Path to input video
            name: Optional job name (defaults to video filename)

        Returns:
            Created Job instance
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Generate job ID (allow override to keep UI + pipeline in sync)
        job_name = name or video_path.stem
        if job_id is None:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            job_id = f"{timestamp}_{job_name}"

        # Create job
        job = Job(
            job_id=job_id,
            input_file=str(video_path.absolute()),
        )

        # Create job directory
        jobs_dir = self.config.paths.jobs_dir
        jobs_dir.mkdir(parents=True, exist_ok=True)
        job.save(jobs_dir)

        logger.info(
            "job_created",
            job_id=job_id,
            input_file=str(video_path),
        )

        return job

    def load_job(self, job_id: str) -> Job:
        """Load an existing job.

        Args:
            job_id: Job ID

        Returns:
            Loaded Job instance
        """
        job_dir = self.config.paths.jobs_dir / job_id
        return Job.load(job_dir)

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all jobs.

        Returns:
            List of job summaries
        """
        jobs_dir = self.config.paths.jobs_dir
        if not jobs_dir.exists():
            return []

        summaries = []
        for job_dir in sorted(jobs_dir.iterdir(), reverse=True):
            state_file = job_dir / "state.json"
            if state_file.exists():
                try:
                    job = Job.load(job_dir)
                    summaries.append(
                        {
                            "job_id": job.job_id,
                            "status": job.status.value,
                            "created": job.created_at.isoformat(),
                            "stages": {
                                name: stage.status.value
                                for name, stage in job.stages.items()
                            },
                        }
                    )
                except Exception as e:
                    logger.warning(
                        "job_load_failed",
                        job_dir=str(job_dir),
                        error=str(e),
                    )

        return summaries

    def run(
        self,
        job: Job,
        stage: str | None = None,
        until_stage: str | None = None,
    ) -> dict[str, StageResult]:
        """Run pipeline stages.

        Args:
            job: Job to run
            stage: Specific stage to run (optional)
            until_stage: Run all stages up to and including this one

        Returns:
            Dict of stage results
        """
        job_dir = job.get_job_dir(self.config.paths.jobs_dir)
        results: dict[str, StageResult] = {}

        # Determine which stages to run
        if stage:
            stages_to_run = [stage]
        elif until_stage:
            try:
                idx = self.STAGE_ORDER.index(until_stage)
                stages_to_run = self.STAGE_ORDER[: idx + 1]
            except ValueError:
                raise ValueError(f"Unknown stage: {until_stage}")
        else:
            stages_to_run = self.STAGE_ORDER

        logger.info(
            "pipeline_starting",
            job_id=job.job_id,
            stages=stages_to_run,
        )

        for stage_name in stages_to_run:
            if stage_name not in self.stages:
                logger.warning("unknown_stage", stage=stage_name)
                continue

            stage_impl = self.stages[stage_name]

            # Check if stage should run
            current_status = job.stages.get(stage_name)
            if current_status and current_status.status == StageStatus.COMPLETE:
                logger.info(
                    "stage_already_complete",
                    stage=stage_name,
                )
                continue

            # Special handling for review stage
            if stage_name == "review":
                result = stage_impl.execute(job, job_dir)
                results[stage_name] = result

                # If review is waiting, stop here
                if result.data.get("status") == "waiting_for_review":
                    logger.info(
                        "waiting_for_review",
                        job_id=job.job_id,
                    )
                    break
            else:
                result = stage_impl.execute(job, job_dir)
                results[stage_name] = result

                if not result.success:
                    logger.error(
                        "stage_failed",
                        stage=stage_name,
                        error=result.error,
                    )
                    break

        logger.info(
            "pipeline_complete",
            job_id=job.job_id,
            results={k: v.success for k, v in results.items()},
        )

        return results


def create_and_run_pipeline(
    video_path: Path,
    name: str | None = None,
    stage: str | None = None,
    config: Config | None = None,
) -> tuple[Job, dict[str, StageResult]]:
    """Convenience function to create a job and run the pipeline.

    Args:
        video_path: Path to input video
        name: Optional job name
        stage: Specific stage to run (or all if None)
        config: Optional config (loads default if None)

    Returns:
        Tuple of (Job, stage results)
    """
    setup_logging()
    pipeline = Pipeline(config)
    job = pipeline.create_job(video_path, name)
    results = pipeline.run(job, stage=stage)
    return job, results
