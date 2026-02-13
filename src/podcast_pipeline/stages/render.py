"""Render stage: Export final content for all platforms."""

import json
import shutil
from pathlib import Path
from typing import Any

from podcast_pipeline.config import Config, PlatformSpec
from podcast_pipeline.models.edit_plan import EditPlan
from podcast_pipeline.models.job import Job
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.stages.review import ReviewDecisions
from podcast_pipeline.utils.ffmpeg import FFmpegError, get_video_info, run_ffmpeg
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

VIDEO_QUALITY_PRESET = {
    "draft": "veryfast",
    "high": "slow",
    "ultra": "veryslow",
}
VIDEO_QUALITY_BITRATE_FACTOR = {
    "draft": 0.65,
    "standard": 1.0,
    "high": 1.2,
    "ultra": 1.4,
}


class RenderStage(Stage):
    """Render final exports for all platforms."""

    name = "render"

    def __init__(self, config: Config):
        super().__init__(config)

    def run(self, job: Job, job_dir: Path) -> StageResult:
        """Execute render stage.

        Creates platform-specific exports based on review decisions.
        """
        # Check review is complete
        review_path = job_dir / "review" / "review_state.json"
        if not review_path.exists():
            return StageResult(
                success=False,
                error="Review not complete. Run review stage first.",
            )

        decisions = ReviewDecisions.model_validate_json(review_path.read_text())
        if not decisions.review_complete:
            return StageResult(
                success=False,
                error="Review not marked as complete. Approve the review first.",
            )

        edit_plan = self._load_edit_plan(job_dir)
        quality_controls = self._resolve_quality_controls(job)

        # Get input video
        input_video = self._find_input_video(job_dir)
        if not input_video:
            return StageResult(
                success=False,
                error="Input video not found",
            )

        # Get video info for aspect ratio calculations
        video_info = get_video_info(input_video)

        outputs: list[str] = []
        errors: list[str] = []
        platform_results: dict[str, dict[str, Any]] = {}
        selected_platforms = list(dict.fromkeys(decisions.export_platforms))
        preflight_error = self._run_render_preflight(input_video, job_dir, selected_platforms)
        if preflight_error is not None:
            return StageResult(success=False, error=preflight_error)

        self.logger.info("render_quality_controls", controls=quality_controls)

        # Export for each selected platform
        for platform in selected_platforms:
            self.logger.info("rendering_platform", platform=platform)

            try:
                spec = self._get_platform_spec(platform)
                if spec is None:
                    error_msg = f"{platform}: Unsupported platform"
                    errors.append(error_msg)
                    platform_results[platform] = {
                        "status": "failed",
                        "outputs": [],
                        "error": error_msg,
                    }
                    self.logger.error("render_platform_failed", platform=platform, error=error_msg)
                    continue

                runtime_spec = self._apply_video_quality_profile(
                    spec,
                    video_quality=quality_controls["video_quality"],
                )
                out = self._render_platform(
                    job_dir,
                    input_video,
                    platform,
                    runtime_spec,
                    decisions,
                    video_info,
                    edit_plan,
                    normalize_audio=quality_controls["audio_normalize"],
                )
                outputs.extend(out)
                platform_results[platform] = {
                    "status": "success",
                    "outputs": out,
                    "settings": {
                        "video_quality": quality_controls["video_quality"],
                        "audio_normalize": quality_controls["audio_normalize"],
                        "preset": runtime_spec.preset,
                        "video_bitrate": runtime_spec.video_bitrate,
                        "audio_bitrate": runtime_spec.audio_bitrate,
                    },
                }
                self.logger.info(
                    "render_platform_complete",
                    platform=platform,
                    outputs=out,
                    settings=platform_results[platform]["settings"],
                )

            except FFmpegError as e:
                error_msg = f"{platform}: FFmpeg error - {e}"
                errors.append(error_msg)
                platform_results[platform] = {
                    "status": "failed",
                    "outputs": [],
                    "error": error_msg,
                    "settings": {
                        "video_quality": quality_controls["video_quality"],
                        "audio_normalize": quality_controls["audio_normalize"],
                    },
                }
                self.logger.exception("render_failed", platform=platform, error=str(e))
            except Exception as e:
                error_msg = f"{platform}: {e}"
                errors.append(error_msg)
                platform_results[platform] = {
                    "status": "failed",
                    "outputs": [],
                    "error": error_msg,
                    "settings": {
                        "video_quality": quality_controls["video_quality"],
                        "audio_normalize": quality_controls["audio_normalize"],
                    },
                }
                self.logger.exception("render_failed", platform=platform)

        # Generate marketing copy document
        try:
            marketing_out = self._generate_marketing_doc(job_dir)
            if marketing_out:
                outputs.append(marketing_out)
        except Exception as e:
            self.logger.warning("marketing_doc_failed", error=str(e))

        # Export short-form clips
        try:
            clip_outputs = self._export_clips(job_dir, input_video, edit_plan)
            outputs.extend(clip_outputs)
        except (FFmpegError, FileNotFoundError, RuntimeError) as e:
            clip_error = f"clips: {e}"
            errors.append(clip_error)
            self.logger.exception("clip_export_failed", error=str(e))

        failed_platforms = [
            platform
            for platform, details in platform_results.items()
            if details.get("status") != "success"
        ]
        if failed_platforms and len(failed_platforms) == len(platform_results):
            render_status = "failed"
        elif failed_platforms or errors:
            render_status = "degraded"
        else:
            render_status = "complete"

        self.logger.info(
            "render_complete",
            status=render_status,
            outputs=outputs,
            errors=errors,
            platform_results=platform_results,
        )

        if errors:
            if failed_platforms:
                error_message = f"Platform export failures: {', '.join(failed_platforms)}"
            else:
                error_message = "; ".join(errors)
            return StageResult(
                success=False,
                error=error_message,
                outputs=outputs,
                data={
                    "status": render_status,
                    "errors": errors,
                    "platform_results": platform_results,
                    "quality_controls": quality_controls,
                },
            )

        return StageResult(
            success=True,
            outputs=outputs,
            data={
                "status": render_status,
                "errors": errors,
                "platform_results": platform_results,
                "quality_controls": quality_controls,
            },
        )

    def _resolve_quality_controls(self, job: Job) -> dict[str, Any]:
        """Resolve render quality controls from persisted job config."""
        raw_controls = job.config.get("render_quality_controls", {})
        controls = raw_controls if isinstance(raw_controls, dict) else {}

        raw_quality = str(controls.get("video_quality", "standard")).lower()
        if raw_quality not in VIDEO_QUALITY_BITRATE_FACTOR:
            self.logger.warning("invalid_video_quality_control", value=raw_quality)
            raw_quality = "standard"

        raw_audio_normalize = controls.get("audio_normalize", True)
        if isinstance(raw_audio_normalize, bool):
            audio_normalize = raw_audio_normalize
        else:
            audio_normalize = str(raw_audio_normalize).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        return {
            "video_quality": raw_quality,
            "audio_normalize": audio_normalize,
        }

    def _run_render_preflight(
        self,
        input_video: Path,
        job_dir: Path,
        selected_platforms: list[str],
    ) -> str | None:
        """Ensure render output paths and free space are sufficient."""
        output_root = job_dir / "output"
        output_root.mkdir(parents=True, exist_ok=True)

        source_size = input_video.stat().st_size
        platform_factor = max(1, len(selected_platforms))
        required_bytes = max(int(source_size * (platform_factor + 0.75)), 300 * 1024 * 1024)
        free_bytes = shutil.disk_usage(output_root).free
        if free_bytes < required_bytes:
            return (
                "Render preflight failed: insufficient disk space for platform exports. "
                f"Required ≥ {required_bytes / (1024 * 1024):.1f} MiB, "
                f"available {free_bytes / (1024 * 1024):.1f} MiB at {output_root}."
            )
        return None

    def _assert_output_exists(self, output_path: Path, artifact_name: str) -> None:
        """Verify output artifacts exist and are non-empty after FFmpeg calls."""
        if not output_path.exists():
            raise FileNotFoundError(
                f"Render output verification failed: {artifact_name} missing at {output_path}."
            )
        if output_path.stat().st_size == 0:
            raise RuntimeError(
                f"Render output verification failed: {artifact_name} is empty at {output_path}."
            )

    def _apply_video_quality_profile(self, spec: PlatformSpec, video_quality: str) -> PlatformSpec:
        """Derive runtime encoding settings from the selected quality profile."""
        if video_quality == "standard":
            return spec

        tuned_spec = spec.model_copy(deep=True)
        bitrate_factor = VIDEO_QUALITY_BITRATE_FACTOR[video_quality]
        tuned_spec.audio_bitrate = self._scale_bitrate(spec.audio_bitrate, bitrate_factor)
        if not tuned_spec.audio_only:
            tuned_spec.video_bitrate = self._scale_bitrate(spec.video_bitrate, bitrate_factor)
            tuned_spec.preset = VIDEO_QUALITY_PRESET[video_quality]
        return tuned_spec

    def _scale_bitrate(self, bitrate: str, factor: float) -> str:
        """Scale bitrate strings like 8M/320k while preserving units."""
        normalized = bitrate.strip()
        if len(normalized) < 2:
            return bitrate

        unit = normalized[-1]
        if unit.lower() not in {"k", "m"}:
            return bitrate

        try:
            value = float(normalized[:-1])
        except ValueError:
            return bitrate

        scaled_value = value * factor
        if unit.lower() == "k":
            scaled_value = max(32.0, scaled_value)
            value_text = str(int(round(scaled_value)))
        else:
            scaled_value = max(0.1, scaled_value)
            value_text = f"{scaled_value:.2f}".rstrip("0").rstrip(".")
        return f"{value_text}{unit}"

    def _get_platform_spec(self, platform: str) -> PlatformSpec | None:
        """Get platform spec by name."""
        return getattr(self.config.platforms, platform, None)

    def _find_input_video(self, job_dir: Path) -> Path | None:
        """Find the input video file."""
        input_dir = job_dir / "input"
        for ext in [".mp4", ".mov", ".mkv", ".avi", ".webm"]:
            path = input_dir / f"raw{ext}"
            if path.exists():
                return path
        return None

    def _load_edit_plan(self, job_dir: Path) -> EditPlan | None:
        """Load edit plan if present."""
        edit_path = job_dir / "review" / "edit_plan.json"
        if not edit_path.exists():
            return None

        try:
            return EditPlan.model_validate_json(edit_path.read_text())
        except Exception as e:
            self.logger.warning("edit_plan_load_failed", error=str(e))
            return None

    def _render_platform(
        self,
        job_dir: Path,
        input_video: Path,
        platform: str,
        spec: PlatformSpec,
        decisions: ReviewDecisions,
        video_info: dict[str, Any],
        edit_plan: EditPlan | None,
        normalize_audio: bool,
    ) -> list[str]:
        """Render export for a specific platform."""
        output_dir = job_dir / "output" / platform
        output_dir.mkdir(parents=True, exist_ok=True)

        # Audio-only platforms
        if spec.audio_only:
            return self._render_audio_only(output_dir, input_video, platform, spec, normalize_audio)

        # Video platforms
        return self._render_video(
            output_dir,
            input_video,
            platform,
            spec,
            decisions,
            video_info,
            edit_plan,
            normalize_audio,
        )

    def _render_audio_only(
        self,
        output_dir: Path,
        input_video: Path,
        platform: str,
        spec: PlatformSpec,
        normalize_audio: bool,
    ) -> list[str]:
        """Render audio-only export (Spotify, Apple Podcasts)."""
        ext = {"mp3": "mp3", "m4a": "m4a", "aac": "m4a"}.get(spec.container, "mp3")
        output_file = output_dir / f"audio.{ext}"

        args = [
            "-i",
            str(input_video),
            "-vn",  # No video
            "-c:a",
            spec.audio_codec,
            "-b:a",
            spec.audio_bitrate,
            "-ar",
            str(self.config.audio.sample_rate),
            "-ac",
            str(spec.audio_channels),
            str(output_file),
        ]

        run_ffmpeg(args)
        self._assert_output_exists(output_file, f"{platform} audio export")

        if normalize_audio:
            self._normalize_loudness(output_file, spec.loudness_lufs)
        else:
            self.logger.info("loudness_normalization_disabled", platform=platform)
        self._assert_output_exists(output_file, f"{platform} audio export")

        self.logger.info(f"{platform}_rendered", output=str(output_file))
        return [str(output_file.relative_to(output_dir.parent.parent))]

    def _render_video(
        self,
        output_dir: Path,
        input_video: Path,
        platform: str,
        spec: PlatformSpec,
        decisions: ReviewDecisions,
        video_info: dict[str, Any],
        edit_plan: EditPlan | None,
        normalize_audio: bool,
    ) -> list[str]:
        """Render video export with aspect ratio conversion."""
        output_file = output_dir / f"final.{spec.container}"

        # Get source dimensions
        src_width = video_info.get("width", 1920)
        src_height = video_info.get("height", 1080)
        src_duration = video_info.get("duration", 0)

        # Calculate target dimensions
        target_width = spec.width or src_width
        target_height = spec.height or src_height

        # Build video filters
        vf_filters = self._build_video_filters(
            src_width, src_height, target_width, target_height, spec
        )

        # Build audio filters
        af_filters: list[str] = []

        edit_filter = self._build_edit_plan_filter(
            edit_plan,
            src_duration,
            vf_filters,
            af_filters,
        )

        # Handle duration limits
        duration_args = []
        if spec.max_duration and src_duration > spec.max_duration:
            duration_args = ["-t", str(spec.max_duration)]
            self.logger.info(
                "truncating_video",
                platform=platform,
                original=src_duration,
                max=spec.max_duration,
            )

        # Build FFmpeg command
        args = ["-i", str(input_video)]

        # Duration limit
        args.extend(duration_args)

        if edit_filter:
            filter_complex, video_map, audio_map = edit_filter
            args.extend(["-filter_complex", filter_complex, "-map", video_map, "-map", audio_map])
        else:
            # Video filters
            if vf_filters:
                args.extend(["-vf", ",".join(vf_filters)])

            # Audio filters
            if af_filters:
                args.extend(["-af", ",".join(af_filters)])

        # Video encoding
        args.extend(
            [
                "-c:v",
                spec.video_codec,
                "-preset",
                spec.preset,
                "-b:v",
                spec.video_bitrate,
                "-pix_fmt",
                spec.pix_fmt,
            ]
        )

        # FPS if specified
        if spec.fps:
            args.extend(["-r", str(spec.fps)])

        # Audio encoding
        args.extend(
            [
                "-c:a",
                spec.audio_codec,
                "-b:a",
                spec.audio_bitrate,
                "-ac",
                str(spec.audio_channels),
            ]
        )

        # Container-specific options
        if spec.container == "mp4":
            args.extend(["-movflags", "+faststart"])

        args.append(str(output_file))

        run_ffmpeg(args)
        self._assert_output_exists(output_file, f"{platform} video export")

        if normalize_audio:
            self._normalize_loudness(output_file, spec.loudness_lufs)
        else:
            self.logger.info("loudness_normalization_disabled", platform=platform)
        self._assert_output_exists(output_file, f"{platform} video export")

        self.logger.info(f"{platform}_rendered", output=str(output_file))
        return [str(output_file.relative_to(output_dir.parent.parent))]

    def _build_video_filters(
        self,
        src_width: int,
        src_height: int,
        target_width: int,
        target_height: int,
        spec: PlatformSpec,
    ) -> list[str]:
        """Build FFmpeg video filter chain for aspect ratio conversion."""
        filters = []

        src_ratio = src_width / src_height
        target_ratio = target_width / target_height

        # Determine if we need to crop or letterbox
        if abs(src_ratio - target_ratio) < 0.01:
            # Same aspect ratio, just scale
            filters.append(f"scale={target_width}:{target_height}")
        elif src_ratio > target_ratio:
            # Source is wider - crop sides or letterbox top/bottom
            if spec.crop_mode in ["center", "smart"]:
                # Crop to fit
                new_width = int(src_height * target_ratio)
                x_offset = (src_width - new_width) // 2
                filters.append(f"crop={new_width}:{src_height}:{x_offset}:0")
                filters.append(f"scale={target_width}:{target_height}")
            else:
                # Letterbox (add black bars top/bottom)
                filters.append(f"scale={target_width}:-2")
                filters.append(f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black")
        # Source is taller - crop top/bottom or letterbox sides
        elif spec.crop_mode in ["center", "smart", "top", "bottom"]:
            # Crop to fit
            new_height = int(src_width / target_ratio)
            if spec.crop_mode == "center":
                y_offset = (src_height - new_height) // 2
            elif spec.crop_mode == "top":
                y_offset = 0
            elif spec.crop_mode == "bottom":
                y_offset = src_height - new_height
            else:  # smart - default to center
                y_offset = (src_height - new_height) // 2
            filters.append(f"crop={src_width}:{new_height}:0:{y_offset}")
            filters.append(f"scale={target_width}:{target_height}")
        else:
            # Letterbox (add black bars on sides)
            filters.append(f"scale=-2:{target_height}")
            filters.append(f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black")

        return filters

    def _build_edit_plan_filter(
        self,
        edit_plan: EditPlan | None,
        duration: float,
        vf_filters: list[str],
        af_filters: list[str],
    ) -> tuple[str, str, str] | None:
        """Build filter_complex for edit plan cuts and optional scaling."""
        if not edit_plan or duration <= 0:
            return None

        cut_ranges = self._collect_cut_ranges(edit_plan)
        if not cut_ranges:
            return None

        keep_ranges = self._invert_cut_ranges(cut_ranges, duration)
        if not keep_ranges:
            # Cuts cover the entire duration - this would result in empty output
            raise ValueError(
                "EditPlan removes entire content: cuts span the full video duration. "
                "Review and adjust the edit plan to retain some content."
            )

        # Check if single keep range covers full duration (with tolerance for floats)
        if len(keep_ranges) == 1:
            start, end = keep_ranges[0]
            if start <= 0.001 and end >= duration - 0.001:
                return None

        filter_parts: list[str] = []
        for idx, (start, end) in enumerate(keep_ranges):
            filter_parts.append(
                f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{idx}]"
            )
            filter_parts.append(
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{idx}]"
            )

        concat_inputs = "".join([f"[v{i}][a{i}]" for i in range(len(keep_ranges))])
        filter_parts.append(f"{concat_inputs}concat=n={len(keep_ranges)}:v=1:a=1[outv][outa]")

        video_label = "outv"
        audio_label = "outa"

        if vf_filters:
            filter_parts.append(f"[outv]{','.join(vf_filters)}[vfinal]")
            video_label = "vfinal"
        if af_filters:
            filter_parts.append(f"[outa]{','.join(af_filters)}[afinal]")
            audio_label = "afinal"

        return ";".join(filter_parts), f"[{video_label}]", f"[{audio_label}]"

    def _collect_cut_ranges(self, edit_plan: EditPlan) -> list[tuple[float, float]]:
        """Collect cut ranges from edit plan in seconds."""
        ranges: list[tuple[float, float]] = []

        for cut in edit_plan.filler_cuts:
            start = max(0.0, float(cut.start_seconds))
            end = max(0.0, float(cut.end_seconds))
            if end > start:
                ranges.append((start, end))

        for content_cut in edit_plan.content_cuts:
            start = max(0.0, float(content_cut.start_seconds))
            end = max(0.0, float(content_cut.end_seconds))
            if end > start:
                ranges.append((start, end))

        return self._merge_ranges(ranges)

    def _merge_ranges(self, ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Merge overlapping ranges."""
        if not ranges:
            return []

        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        merged = [sorted_ranges[0]]
        for start, end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def _invert_cut_ranges(
        self,
        ranges: list[tuple[float, float]],
        duration: float,
    ) -> list[tuple[float, float]]:
        """Convert cut ranges to keep ranges."""
        if duration <= 0:
            return []

        keep_ranges: list[tuple[float, float]] = []
        cursor = 0.0
        for start, end in ranges:
            if start > cursor:
                keep_ranges.append((cursor, min(start, duration)))
            cursor = max(cursor, end)

        if cursor < duration:
            keep_ranges.append((cursor, duration))

        return keep_ranges

    def _export_clips(
        self,
        job_dir: Path,
        input_video: Path,
        edit_plan: EditPlan | None,
    ) -> list[str]:
        """Export short-form clips from edit plan ranges."""
        if not edit_plan or not edit_plan.clip_ranges:
            return []

        clips_dir = job_dir / "output" / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[str] = []
        clip_errors: list[str] = []
        for idx, clip in enumerate(edit_plan.clip_ranges, 1):
            start = max(0.0, float(clip.start_seconds))
            end = max(0.0, float(clip.end_seconds))
            if end <= start:
                continue

            clip_path = clips_dir / f"clip_{idx:02d}.mp4"
            args = [
                "-i",
                str(input_video),
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(clip_path),
            ]
            try:
                run_ffmpeg(args)
                self._assert_output_exists(clip_path, f"clip_{idx:02d} export")
                outputs.append(str(clip_path.relative_to(job_dir)))
            except (FFmpegError, FileNotFoundError, RuntimeError) as e:
                error_msg = f"clip_{idx:02d}: {e}"
                clip_errors.append(error_msg)
                self.logger.error("clip_export_failed", clip=idx, error=str(e))

        if outputs:
            self.logger.info("clips_exported", count=len(outputs))
        if clip_errors:
            raise RuntimeError("; ".join(clip_errors))

        return outputs

    def _normalize_loudness(self, audio_file: Path, target_lufs: float) -> None:
        """Normalize audio to target LUFS using pyloudnorm."""
        try:
            import pyloudnorm as pyln
            import soundfile as sf

            # For video files, we need to extract audio first
            is_video = audio_file.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]

            if is_video:
                # Extract audio to temp file
                temp_audio = audio_file.with_suffix(".temp.wav")
                run_ffmpeg(
                    [
                        "-i",
                        str(audio_file),
                        "-vn",
                        "-acodec",
                        "pcm_s16le",
                        "-ar",
                        "44100",
                        str(temp_audio),
                    ]
                )
                audio_to_process = temp_audio
            else:
                audio_to_process = audio_file

            # Read audio
            data, rate = sf.read(str(audio_to_process))

            # Handle mono audio
            if len(data.shape) == 1:
                data = data.reshape(-1, 1)

            # Measure loudness
            meter = pyln.Meter(rate)
            loudness = meter.integrated_loudness(data)

            self.logger.debug(
                "loudness_measured",
                file=str(audio_file),
                current=loudness,
                target=target_lufs,
            )

            # Skip if already close enough or if loudness is -inf (silent)
            if loudness == float("-inf") or abs(loudness - target_lufs) < 0.5:
                if is_video and temp_audio.exists():
                    temp_audio.unlink()
                return

            # Normalize
            normalized = pyln.normalize.loudness(data, loudness, target_lufs)

            if is_video:
                # Write normalized audio
                sf.write(str(temp_audio), normalized, rate)

                # Mux back into video
                temp_video = audio_file.with_suffix(".temp.mp4")
                run_ffmpeg(
                    [
                        "-i",
                        str(audio_file),
                        "-i",
                        str(temp_audio),
                        "-c:v",
                        "copy",
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-shortest",
                        str(temp_video),
                    ]
                )

                # Replace original
                temp_video.replace(audio_file)
                temp_audio.unlink()
            else:
                # Write back directly
                sf.write(str(audio_file), normalized, rate)

            self.logger.info(
                "loudness_normalized",
                file=str(audio_file),
                from_lufs=loudness,
                to_lufs=target_lufs,
            )

        except ImportError:
            self.logger.warning(
                "pyloudnorm_not_available",
                message="Skipping loudness normalization",
            )
        except Exception as e:
            self.logger.warning(
                "loudness_normalization_failed",
                error=str(e),
            )

    def _generate_marketing_doc(self, job_dir: Path) -> str | None:
        """Generate marketing copy markdown document."""
        analysis_path = job_dir / "analysis" / "analysis.json"
        if not analysis_path.exists():
            return None

        analysis = json.loads(analysis_path.read_text())
        marketing = analysis.get("marketing", {})
        metadata = analysis.get("metadata", {})

        output_dir = job_dir / "output" / "marketing"
        output_dir.mkdir(parents=True, exist_ok=True)

        doc_path = output_dir / "copy.md"

        lines = [
            "# Marketing Copy",
            "",
            f"**Episode Summary:** {metadata.get('summary', 'N/A')}",
            f"**Topics:** {', '.join(metadata.get('topics', []))}",
            f"**Mood:** {metadata.get('mood', 'N/A')}",
            "",
            "---",
            "",
        ]

        # All platforms
        platform_sections = [
            ("YouTube", "youtube"),
            ("Spotify", "spotify"),
            ("Apple Podcasts", "apple"),
            ("TikTok", "tiktok"),
            ("Instagram Reels", "instagram"),
            ("LinkedIn", "linkedin"),
            ("Twitter/X", "twitter"),
            ("Facebook", "facebook"),
        ]

        for platform_name, platform_key in platform_sections:
            platform_data = marketing.get(platform_key, {})

            lines.extend(
                [
                    f"## {platform_name}",
                    "",
                ]
            )

            # Titles (if available)
            titles = platform_data.get("titles", [])
            if titles:
                lines.append("### Titles")
                for i, title in enumerate(titles, 1):
                    lines.append(f"{i}. {title}")
                lines.append("")

            # Description
            description = platform_data.get("description", "")
            if description:
                lines.extend(
                    [
                        "### Description",
                        "",
                        description,
                        "",
                    ]
                )

            # Hashtags
            hashtags = platform_data.get("hashtags", [])
            if hashtags:
                lines.append(f"**Hashtags:** {' '.join(hashtags)}")
                lines.append("")

            lines.extend(
                [
                    "---",
                    "",
                ]
            )

        doc_path.write_text("\n".join(lines))
        self.logger.info("marketing_doc_generated", path=str(doc_path))

        return str(doc_path.relative_to(job_dir))
