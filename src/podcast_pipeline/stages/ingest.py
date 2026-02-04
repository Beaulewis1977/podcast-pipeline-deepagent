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
        input_dir.mkdir(parents=True, exist_ok=True)
        intermediate_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[str] = []

        try:
            # Copy or symlink input file
            dest_input = input_dir / f"raw{input_path.suffix}"
            if not dest_input.exists():
                shutil.copy2(input_path, dest_input)
            outputs.append(str(dest_input.relative_to(job_dir)))
            self.logger.info("input_copied", source=str(input_path), dest=str(dest_input))

            # Extract metadata
            self.logger.info("extracting_metadata", file=str(input_path))
            metadata = get_video_metadata(input_path)
            metadata_path = intermediate_dir / "metadata.json"
            metadata_path.write_text(json.dumps(metadata, indent=2))
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
            outputs.append(str(audio_path.relative_to(job_dir)))

            # Create proxy for AI analysis (720p)
            proxy_path = intermediate_dir / "proxy.mp4"
            self.logger.info("creating_proxy")
            create_proxy(input_path, proxy_path, resolution="720", crf=28)
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
