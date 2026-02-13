"""Ingest stage: Extract metadata, audio, and create proxy."""

import json
import shutil
from pathlib import Path

from podcast_pipeline.config import Config
from podcast_pipeline.models.job import Job
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.utils.ffmpeg import (
    create_proxy,
    extract_audio,
    get_video_metadata,
)

VALID_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


class IngestStage(Stage):
    """Extract metadata, audio, and create analysis proxy."""

    name = "ingest"

    def __init__(self, config: Config):
        super().__init__(config)

    def run(self, job: Job, job_dir: Path) -> StageResult:
        """Execute ingest stage.

        Creates:
            - intermediate/metadata.json
            - intermediate/audio.wav (16kHz mono for Whisper)
            - intermediate/proxy.mp4 (720p for AI analysis)
            - input/raw.* (copy or symlink of original)
        """
        input_path = Path(job.input_file)

        # Validate input file
        if not input_path.exists():
            return StageResult(
                success=False,
                error=f"Input file not found: {input_path}",
            )

        if input_path.suffix.lower() not in VALID_EXTENSIONS:
            return StageResult(
                success=False,
                error=f"Invalid file type: {input_path.suffix}. Supported: {VALID_EXTENSIONS}",
            )

        # Create directories
        input_dir = job_dir / "input"
        intermediate_dir = job_dir / "intermediate"
        self._run_preflight_checks(input_path, job_dir, input_dir, intermediate_dir)

        outputs: list[str] = []

        try:
            # Copy or symlink input file
            dest_input = input_dir / f"raw{input_path.suffix}"
            if not dest_input.exists():
                shutil.copy2(input_path, dest_input)
            self._assert_output_exists(dest_input, "input copy")
            outputs.append(str(dest_input.relative_to(job_dir)))
            self.logger.info("input_copied", source=str(input_path), dest=str(dest_input))

            # Extract metadata
            self.logger.info("extracting_metadata", file=str(input_path))
            metadata = get_video_metadata(input_path)
            metadata_path = intermediate_dir / "metadata.json"
            metadata_path.write_text(json.dumps(metadata, indent=2))
            self._assert_output_exists(metadata_path, "metadata output")
            outputs.append(str(metadata_path.relative_to(job_dir)))
            self.logger.info(
                "metadata_extracted",
                duration=metadata.get("duration", 0),
                format=metadata.get("format"),
            )

            # Extract audio for Whisper (16kHz mono WAV)
            audio_path = intermediate_dir / "audio.wav"
            self.logger.info("extracting_audio")
            extract_audio(input_path, audio_path, sample_rate=16000, mono=True)
            self._assert_output_exists(audio_path, "audio extraction")
            outputs.append(str(audio_path.relative_to(job_dir)))

            # Create proxy for AI analysis (720p)
            proxy_path = intermediate_dir / "proxy.mp4"
            self.logger.info("creating_proxy")
            create_proxy(input_path, proxy_path, resolution="720", crf=28)
            self._assert_output_exists(proxy_path, "proxy output")
            outputs.append(str(proxy_path.relative_to(job_dir)))

            return StageResult(
                success=True,
                outputs=outputs,
                data={"metadata": metadata},
            )

        except Exception as e:
            return StageResult(
                success=False,
                error=str(e),
                outputs=outputs,
            )

    def _run_preflight_checks(
        self,
        input_path: Path,
        job_dir: Path,
        input_dir: Path,
        intermediate_dir: Path,
    ) -> None:
        """Validate output directories and disk capacity before ingest work."""
        input_dir.mkdir(parents=True, exist_ok=True)
        intermediate_dir.mkdir(parents=True, exist_ok=True)

        source_size = input_path.stat().st_size
        required_bytes = max(int(source_size * 3), 250 * 1024 * 1024)
        disk_target = job_dir if job_dir.exists() else job_dir.parent
        free_bytes = shutil.disk_usage(disk_target).free
        if free_bytes < required_bytes:
            raise RuntimeError(
                "Ingest preflight failed: insufficient disk space for copy/audio/proxy outputs. "
                f"Required ≥ {required_bytes / (1024 * 1024):.1f} MiB, "
                f"available {free_bytes / (1024 * 1024):.1f} MiB at {disk_target}."
            )

    def _assert_output_exists(self, output_path: Path, artifact_name: str) -> None:
        """Ensure FFmpeg and write operations produced real output files."""
        if not output_path.exists():
            raise FileNotFoundError(
                f"Ingest output verification failed: {artifact_name} missing at {output_path}."
            )
        if output_path.stat().st_size == 0:
            raise RuntimeError(
                f"Ingest output verification failed: {artifact_name} is empty at {output_path}."
            )
