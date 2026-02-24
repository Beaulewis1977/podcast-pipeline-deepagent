"""Ingest stage: Extract metadata, audio, and create proxy."""

import json
import shutil
from pathlib import Path

from podcast_pipeline.config import Config
from podcast_pipeline.models.job import Job
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.utils.ffmpeg import (
    FFmpegError,
    create_proxy,
    extract_audio,
    get_video_metadata,
    run_ffmpeg,
)

VALID_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

# Path within job_dir where the sync artifact is written.
SYNC_ARTIFACT_NAME = "intermediate/sync_artifact.json"


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
            - intermediate/sync_artifact.json (when multiple audio tracks detected)
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

            # Phase 9.7: Auto-sync when multiple audio tracks are detected.
            sync_artifact_path = intermediate_dir / "sync_artifact.json"
            sync_data = self._run_sync_estimation(
                input_path, metadata, intermediate_dir, sync_artifact_path
            )
            if sync_data is not None:
                outputs.append(str(sync_artifact_path.relative_to(job_dir)))

            return StageResult(
                success=True,
                outputs=outputs,
                data={"metadata": metadata, "sync": sync_data},
            )

        except Exception as e:
            return StageResult(
                success=False,
                error=str(e),
                outputs=outputs,
            )

    # -------------------------------------------------------------------------
    # Sync estimation helpers
    # -------------------------------------------------------------------------

    def _run_sync_estimation(
        self,
        input_path: Path,
        metadata: dict,  # type: ignore[type-arg]
        intermediate_dir: Path,
        artifact_path: Path,
    ) -> dict | None:  # type: ignore[type-arg]
        """Run bounded cross-correlation sync if multiple audio tracks exist.

        Args:
            input_path: Original input video path.
            metadata: Ingest metadata dict (includes ``audio_track_count``).
            intermediate_dir: Directory for temporary extraction files.
            artifact_path: Where to write the JSON sync artifact.

        Returns:
            The artifact dict that was written, or ``None`` when sync is not
            applicable (single track or estimation unavailable).
        """
        audio_track_count = int(metadata.get("audio_track_count", 1))
        if audio_track_count < 2:
            self.logger.info(
                "sync_skipped",
                reason="single_audio_track",
                audio_track_count=audio_track_count,
            )
            return None

        self.logger.info(
            "sync_starting",
            audio_track_count=audio_track_count,
            input=str(input_path),
        )

        # Extract the two audio streams (track 0 = reference, track 1 = external)
        ref_wav = intermediate_dir / "sync_ref.wav"
        ext_wav = intermediate_dir / "sync_ext.wav"
        try:
            self._extract_stream_wav(input_path, ref_wav, stream_index=0)
            self._extract_stream_wav(input_path, ext_wav, stream_index=1)
        except FFmpegError as exc:
            self.logger.warning(
                "sync_stream_extraction_failed",
                error=str(exc),
                skip="continuing without sync artifact",
            )
            return None

        # Run the bounded cross-correlation estimator
        try:
            from podcast_pipeline.utils.sync import SyncEstimator

            estimator = SyncEstimator(search_window_s=60.0)
            result = estimator._estimate_from_wavs(ref_wav, ext_wav)
        except Exception as exc:
            self.logger.warning(
                "sync_estimation_failed",
                error=str(exc),
                skip="continuing without sync artifact",
            )
            return None
        finally:
            # Clean up temporary extraction files
            import contextlib

            for wav in (ref_wav, ext_wav):
                with contextlib.suppress(OSError):
                    wav.unlink(missing_ok=True)

        artifact = result.as_artifact()
        artifact_path.write_text(json.dumps(artifact, indent=2))

        self.logger.info(
            "sync_artifact_written",
            offset_ms=artifact["offset_ms"],
            confidence=artifact["confidence"],
            low_confidence=artifact["low_confidence"],
            no_clap=artifact["no_clap"],
            path=str(artifact_path),
        )
        return artifact

    @staticmethod
    def _extract_stream_wav(src: Path, dst: Path, stream_index: int) -> None:
        """Extract a single audio stream from *src* into a mono 8 kHz WAV.

        Args:
            src: Source audio/video file.
            dst: Destination WAV file.
            stream_index: 0-based audio stream index (``-map 0:a:N``).

        Raises:
            FFmpegError: Propagated from run_ffmpeg on failure.
        """
        args = [
            "-i",
            str(src),
            "-map",
            f"0:a:{stream_index}",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-t",
            "60",
            "-vn",
            str(dst),
        ]
        run_ffmpeg(args, timeout=120)

    # -------------------------------------------------------------------------
    # Preflight / output verification helpers
    # -------------------------------------------------------------------------

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
                f"Required >= {required_bytes / (1024 * 1024):.1f} MiB, "
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
