"""Render stage: Export final content for all platforms."""

import importlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from podcast_pipeline.config import Config, PlatformSpec, ThumbnailTargetSpec
from podcast_pipeline.models.edit_plan import EditPlan
from podcast_pipeline.models.job import Job
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.stages.review import ReviewDecisions
from podcast_pipeline.utils.editing import find_word_boundaries, snap_cut_range
from podcast_pipeline.utils.ffmpeg import FFmpegError, get_video_info, run_ffmpeg, run_ffprobe
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
MAX_THUMBNAIL_EXPORTS = 4
MIN_THUMBNAIL_OFFSET_SECONDS = 0.5
PROFILE_LEVEL_CODECS = {"h264", "libx264", "h265", "hevc", "libx265"}
THUMBNAIL_COMPLIANCE_PLATFORMS = ("youtube", "spotify_video", "apple_video")
_EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class _CutRange:
    """Typed cut metadata used to derive transition policy per join."""

    start: float
    end: float
    kind: Literal["filler", "content"]


class PlatformComplianceError(RuntimeError):
    """Raised when post-render platform compliance checks fail."""

    def __init__(
        self,
        platform: str,
        issues: list[str],
        warnings: list[str] | None = None,
    ) -> None:
        self.platform = platform
        self.issues = issues
        self.warnings = warnings or []
        super().__init__("; ".join(issues))


class RenderStage(Stage):
    """Render final exports for all platforms."""

    name = "render"
    _ffmpeg_filter_cache: set[str] | None = None

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
        if preflight_error is None:
            try:
                self._ensure_filter_capabilities()
            except RuntimeError as e:
                preflight_error = str(e)
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

            except PlatformComplianceError as e:
                error_msg = f"{platform}: compliance validation failed - {e}"
                errors.append(error_msg)
                platform_results[platform] = {
                    "status": "failed",
                    "outputs": [],
                    "error_type": "compliance_error",
                    "error": error_msg,
                    "validation": {
                        "issues": e.issues,
                        "warnings": e.warnings,
                    },
                    "settings": {
                        "video_quality": quality_controls["video_quality"],
                        "audio_normalize": quality_controls["audio_normalize"],
                    },
                }
                self.logger.exception(
                    "render_platform_compliance_failed",
                    platform=platform,
                    issues=e.issues,
                    warnings=e.warnings,
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

        thumbnail_outputs, thumbnail_result = self._export_thumbnail_assets(
            job_dir=job_dir,
            input_video=input_video,
            video_info=video_info,
            decisions=decisions,
        )
        outputs.extend(thumbnail_outputs)
        if thumbnail_result.get("status") == "failed":
            error_message = str(thumbnail_result.get("error", "thumbnail export failed"))
            errors.append(f"thumbnails: {error_message}")
            self.logger.error("thumbnail_export_failed", error=error_message)
        elif thumbnail_result.get("status") == "complete":
            self.logger.info(
                "thumbnail_export_complete",
                count=thumbnail_result.get("generated", 0),
                source=thumbnail_result.get("source"),
            )

        thumbnail_compliance = self._enforce_thumbnail_target_compliance(
            job_dir=job_dir,
            selected_platforms=selected_platforms,
            thumbnail_result=thumbnail_result,
        )
        outputs.extend(thumbnail_compliance.get("outputs", []))
        thumbnail_result["compliance"] = thumbnail_compliance.get("platform_results", {})
        if thumbnail_compliance.get("status") == "failed":
            error_message = str(thumbnail_compliance.get("error", "thumbnail compliance failed"))
            errors.append(f"thumbnails: {error_message}")
            self.logger.error(
                "thumbnail_compliance_failed",
                error=error_message,
                platform_results=thumbnail_compliance.get("platform_results", {}),
            )
        elif thumbnail_compliance.get("status") == "complete":
            self.logger.info(
                "thumbnail_compliance_complete",
                validated_platforms=thumbnail_compliance.get("validated_platforms", []),
            )

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
                    "thumbnail_result": thumbnail_result,
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
                "thumbnail_result": thumbnail_result,
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

    def _required_enhancement_filters(self) -> set[str]:
        """Compute required FFmpeg filters from currently enabled enhancement paths."""
        required: set[str] = set()
        if self.config.enhancements.deesser.enabled:
            required.add("deesser")
            if self.config.enhancements.deesser.click_safety_enabled:
                required.add("adeclick")

        color = self.config.enhancements.color_correction
        if color.enabled:
            if color.normalize_enabled:
                required.add("normalize")
            if color.grayworld_enabled:
                required.add("grayworld")
            if color.eq_enabled:
                required.add("eq")

        smoothing = self.config.smoothing
        if smoothing.enabled and smoothing.require_transition_filters:
            if smoothing.content_audio_crossfade_ms > 0:
                required.add("acrossfade")
            if smoothing.content_video_dissolve_ms > 0:
                required.add("xfade")

        return required

    def _probe_available_ffmpeg_filters(self) -> set[str]:
        """Probe and cache available filter names from local FFmpeg binary."""
        if RenderStage._ffmpeg_filter_cache is not None:
            return RenderStage._ffmpeg_filter_cache

        cmd = ["ffmpeg", "-hide_banner", "-filters"]
        try:
            result = subprocess.run(  # noqa: S603 — cmd is a hardcoded list, no user input
                cmd,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("Render preflight failed: `ffmpeg -filters` timed out.") from e
        except FileNotFoundError as e:
            raise RuntimeError(
                "Render preflight failed: ffmpeg binary not found in PATH. Install FFmpeg first."
            ) from e

        if result.returncode != 0:
            stderr = result.stderr.strip() or "unknown ffmpeg error"
            raise RuntimeError(
                "Render preflight failed: unable to inspect FFmpeg filters "
                f"(exit {result.returncode}: {stderr})."
            )

        available: set[str] = set()
        for line in result.stdout.splitlines():
            match = re.match(r"^\s*[T.][S.][C.]\s+([A-Za-z0-9_]+)\s+", line)
            if match:
                available.add(match.group(1))

        if not available:
            raise RuntimeError(
                "Render preflight failed: could not parse filter list from `ffmpeg -filters` output."
            )

        RenderStage._ffmpeg_filter_cache = available
        return available

    def _ensure_filter_capabilities(self) -> None:
        """Fail fast when enabled enhancement filters are unavailable in local FFmpeg."""
        required = self._required_enhancement_filters()
        if not required:
            return

        available = self._probe_available_ffmpeg_filters()
        missing = sorted(required - available)
        if missing:
            missing_list = ", ".join(missing)
            raise RuntimeError(
                "Render preflight failed: missing required FFmpeg filter(s): "
                f"{missing_list}. Install an FFmpeg build with these filters or disable the "
                "corresponding enhancement flags in config.yaml."
            )

        self.logger.info(
            "render_filter_capability_check_passed",
            required=sorted(required),
        )

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

    def _resolve_hls_template_path(self, output_dir: Path, template: str, field_name: str) -> Path:
        """Resolve HLS output template path while preventing directory escape."""
        value = template.strip()
        if not value:
            raise ValueError(f"HLS {field_name} cannot be empty")

        posix = PurePosixPath(value)
        windows = PureWindowsPath(value)
        if posix.is_absolute() or windows.is_absolute() or windows.drive:
            raise ValueError(f"HLS {field_name} must be a relative filename")
        if "/" in value or "\\" in value or len(posix.parts) != 1:
            raise ValueError(f"HLS {field_name} must not include directory separators")
        if any(part in {".", ".."} for part in posix.parts):
            raise ValueError(f"HLS {field_name} must not include '.' or '..' segments")

        output_root = output_dir.resolve()
        candidate = (output_root / value).resolve()
        if not candidate.is_relative_to(output_root):
            raise ValueError(f"HLS {field_name} resolves outside output directory: {value}")
        return candidate

    def _resolve_hls_reference_path(
        self,
        *,
        base_dir: Path,
        reference: str,
        output_root: Path,
        artifact_name: str,
    ) -> Path:
        """Resolve HLS playlist references while blocking absolute/escaped targets."""
        ref = reference.strip()
        if not ref:
            raise RuntimeError(f"{artifact_name} contains an empty artifact reference")
        if "://" in ref:
            raise RuntimeError(f"{artifact_name} contains unsupported URI reference: {ref}")

        posix = PurePosixPath(ref)
        windows = PureWindowsPath(ref)
        if posix.is_absolute() or windows.is_absolute() or windows.drive:
            raise RuntimeError(f"{artifact_name} contains absolute path reference: {ref}")
        if any(part in {".", ".."} for part in posix.parts):
            raise RuntimeError(f"{artifact_name} contains unsafe path traversal reference: {ref}")

        resolved = (base_dir / ref).resolve()
        if not resolved.is_relative_to(output_root):
            raise RuntimeError(f"{artifact_name} reference escapes output directory: {ref}")
        return resolved

    def _create_dereverb_audio_track(self, input_video: Path, output_dir: Path) -> Path:
        """Extract and process a temporary audio track with optional noisereduce dereverb."""
        dereverb = self.config.enhancements.dereverb

        try:
            noisereduce_module = importlib.import_module("noisereduce")
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Dereverb is enabled but optional dependency 'noisereduce' is not installed."
            ) from e

        reduce_noise = getattr(noisereduce_module, "reduce_noise", None)
        if not callable(reduce_noise):
            raise TypeError("Dereverb is enabled but noisereduce.reduce_noise is unavailable.")

        source_wav = output_dir / "_dereverb_source.wav"
        processed_wav = output_dir / "_dereverb_processed.wav"

        run_ffmpeg(
            [
                "-i",
                str(input_video),
                "-vn",
                "-c:a",
                "pcm_s16le",
                "-ar",
                str(self.config.audio.sample_rate),
                "-ac",
                "2",
                str(source_wav),
            ]
        )
        self._assert_output_exists(source_wav, "dereverb source audio")

        try:
            import soundfile as sf

            samples, sample_rate = sf.read(source_wav, always_2d=True)
            if getattr(samples, "size", 0) == 0:
                raise RuntimeError("Dereverb source audio is empty.")

            denoised = reduce_noise(
                y=samples.T,
                sr=int(sample_rate),
                prop_decrease=dereverb.prop_decrease,
                stationary=dereverb.stationary,
            )
            processed_samples = denoised.T if hasattr(denoised, "T") else samples
            sf.write(processed_wav, processed_samples, int(sample_rate))
        except (RuntimeError, ValueError, OSError, TypeError) as e:
            raise RuntimeError(f"Dereverb processing failed: {e}") from e

        self._assert_output_exists(processed_wav, "dereverb processed audio")
        return processed_wav

    def _prepare_optional_dereverb_input(
        self,
        *,
        input_video: Path,
        output_dir: Path,
        platform: str,
        audio_bitrate: str = "256k",
    ) -> Path:
        """Optionally preprocess audio with noisereduce and remux with original video."""
        dereverb = self.config.enhancements.dereverb
        if not dereverb.enabled:
            return input_video

        try:
            processed_audio = self._create_dereverb_audio_track(
                input_video=input_video,
                output_dir=output_dir,
            )
            remuxed_input = output_dir / "_dereverb_input.mkv"
            run_ffmpeg(
                [
                    "-i",
                    str(input_video),
                    "-i",
                    str(processed_audio),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    audio_bitrate,
                    str(remuxed_input),
                ]
            )
            self._assert_output_exists(remuxed_input, f"{platform} dereverb remux input")
        except (FFmpegError, FileNotFoundError, RuntimeError, TypeError) as e:
            if dereverb.fallback_mode == "fail":
                raise
            self.logger.warning(
                "dereverb_preprocess_skipped",
                platform=platform,
                reason=str(e),
            )
            return input_video

        return remuxed_input

    def _build_audio_enhancement_filters(self) -> list[str]:
        """Build speech-focused enhancement chain for export audio tracks."""
        filters: list[str] = []

        # Stage 1: dialog cleanup
        noise_mode = str(self.config.audio.noise_reduction).strip().lower()
        if noise_mode not in {"", "off", "false", "0"}:
            noise_floor = -25.0
            if noise_mode not in {"auto", "on", "true", "1"}:
                try:
                    noise_floor = float(noise_mode)
                except ValueError:
                    self.logger.warning("invalid_noise_reduction_setting", value=noise_mode)
            noise_floor = min(max(noise_floor, -80.0), -8.0)
            filters.append(f"afftdn=nf={noise_floor:.1f}")

        filters.extend(
            [
                "highpass=f=70",
                "lowpass=f=12000",
                "equalizer=f=240:t=q:w=1.2:g=1.8",
                "equalizer=f=3200:t=q:w=1.0:g=2.2",
            ]
        )

        # Stage 2: FFmpeg-native de-essing
        deesser = self.config.enhancements.deesser
        if deesser.enabled:
            filters.append(
                "deesser="
                f"i={deesser.intensity:.3f}:"
                f"m={deesser.max_deessing:.3f}:"
                f"f={deesser.frequency:.3f}:"
                f"s={deesser.output_mode}"
            )

        # Stage 3: final dynamics shaping
        filters.extend(
            [
                "acompressor=threshold=-18dB:ratio=2.5:attack=5:release=120",
                "alimiter=limit=0.95",
            ]
        )

        # Stage 4: final click-safety cleanup
        if deesser.enabled and deesser.click_safety_enabled:
            filters.append(
                "adeclick="
                f"window={deesser.adeclick_window:.3f}:"
                f"overlap={deesser.adeclick_overlap:.3f}:"
                f"arorder={deesser.adeclick_arorder:.3f}:"
                f"threshold={deesser.adeclick_threshold:.3f}:"
                f"burst={deesser.adeclick_burst:.3f}:"
                f"method={deesser.adeclick_method}"
            )

        return filters

    def _build_color_correction_filters(self) -> list[str]:
        """Build optional canonical FFmpeg color correction chain."""
        color = self.config.enhancements.color_correction
        if not color.enabled:
            return []

        filters: list[str] = []
        if color.normalize_enabled:
            filters.append(f"normalize=strength={color.normalize_strength:.3f}")
        if color.grayworld_enabled:
            filters.append("grayworld")
        if color.eq_enabled:
            filters.append(
                "eq="
                f"saturation={color.eq_saturation:.3f}:"
                f"contrast={color.eq_contrast:.3f}:"
                f"brightness={color.eq_brightness:.3f}:"
                f"gamma={color.eq_gamma:.3f}"
            )
        return filters

    def _load_thumbnail_candidates(
        self,
        job_dir: Path,
    ) -> tuple[list[dict[str, Any]], str]:
        """Load and normalize thumbnail candidates from analysis output."""
        analysis_path = job_dir / "analysis" / "analysis.json"
        if not analysis_path.exists():
            return [], "missing_analysis"

        try:
            analysis_payload = json.loads(analysis_path.read_text())
        except json.JSONDecodeError as e:
            self.logger.warning("thumbnail_candidate_load_failed", error=str(e))
            return [], "invalid_analysis_json"

        raw_candidates = analysis_payload.get("thumbnail_frames", [])
        if not isinstance(raw_candidates, list):
            return [], "invalid_thumbnail_payload"

        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_candidates):
            if not isinstance(raw, dict):
                continue

            timestamp_seconds = self._parse_timestamp_seconds(raw.get("timestamp_seconds"))
            if timestamp_seconds is None:
                timestamp_seconds = self._parse_timestamp_seconds(raw.get("timestamp"))
            if timestamp_seconds is None:
                continue

            normalized.append(
                {
                    "analysis_index": index,
                    "timestamp": str(
                        raw.get("timestamp") or self._format_timestamp(timestamp_seconds)
                    ),
                    "timestamp_seconds": timestamp_seconds,
                    "visual_description": str(raw.get("visual_description", "")),
                    "suggested_text_overlay": str(raw.get("suggested_text_overlay", "")),
                    "emotion": str(raw.get("emotion", "")),
                    "source": "analysis",
                }
            )

        return normalized, "analysis"

    def _build_fallback_thumbnail_candidates(self, video_duration: float) -> list[dict[str, Any]]:
        """Build deterministic fallback thumbnail timestamps for sparse analysis output."""
        if video_duration <= MIN_THUMBNAIL_OFFSET_SECONDS * 2:
            return []

        fallback_positions = [0.12, 0.32, 0.52, 0.72]
        upper_bound = max(video_duration - MIN_THUMBNAIL_OFFSET_SECONDS, 0.0)
        candidates: list[dict[str, Any]] = []
        for position in fallback_positions:
            timestamp_seconds = min(max(video_duration * position, 0.0), upper_bound)
            candidates.append(
                {
                    "analysis_index": None,
                    "timestamp": self._format_timestamp(timestamp_seconds),
                    "timestamp_seconds": timestamp_seconds,
                    "visual_description": "",
                    "suggested_text_overlay": "",
                    "emotion": "",
                    "source": "duration_fallback",
                }
            )
        return candidates

    def _rank_thumbnail_candidates(
        self,
        candidates: list[dict[str, Any]],
        video_duration: float,
        selected_thumbnails: list[int],
    ) -> list[dict[str, Any]]:
        """Rank candidates deterministically using review preference and quality hints."""
        if not candidates:
            return []

        ranked: list[dict[str, Any]] = []
        total = len(candidates)
        selected_rank_map = {index: rank for rank, index in enumerate(selected_thumbnails, start=1)}
        for index, candidate in enumerate(candidates):
            score = float(total - index)
            analysis_index = candidate.get("analysis_index")
            if isinstance(analysis_index, int) and analysis_index in selected_rank_map:
                # Explicit review ranking outranks heuristic candidate score.
                selection_rank = selected_rank_map[analysis_index]
                score += max(0.0, 6.0 - float(selection_rank))
            if candidate.get("suggested_text_overlay"):
                score += 0.8
            if candidate.get("visual_description"):
                score += 0.5
            if candidate.get("emotion"):
                score += 0.3

            timestamp_seconds = float(candidate.get("timestamp_seconds", 0.0))
            if video_duration > 0:
                normalized_position = timestamp_seconds / video_duration
                if 0.1 <= normalized_position <= 0.9:
                    score += 0.75
                else:
                    score -= 0.5

            ranked_candidate = dict(candidate)
            ranked_candidate["score"] = round(score, 4)
            ranked.append(ranked_candidate)

        ranked.sort(
            key=lambda row: (
                -float(row.get("score", 0.0)),
                float(row.get("timestamp_seconds", 0.0)),
            )
        )
        return ranked[:MAX_THUMBNAIL_EXPORTS]

    def _export_thumbnail_assets(
        self,
        job_dir: Path,
        input_video: Path,
        video_info: dict[str, Any],
        decisions: ReviewDecisions,
    ) -> tuple[list[str], dict[str, Any]]:
        """Extract and persist thumbnail images from ranked frame candidates."""
        video_duration = max(float(video_info.get("duration", 0.0) or 0.0), 0.0)
        candidates, source = self._load_thumbnail_candidates(job_dir)
        if not candidates:
            candidates = self._build_fallback_thumbnail_candidates(video_duration)
            if candidates:
                source = "duration_fallback"

        if not candidates:
            return [], {
                "status": "skipped",
                "source": source,
                "generated": 0,
                "reason": "no_thumbnail_candidates",
            }

        selected_thumbnails = self._resolve_ranked_thumbnail_selection(decisions)
        selected_rank_map = {index: rank for rank, index in enumerate(selected_thumbnails, start=1)}
        ranked_candidates = self._rank_thumbnail_candidates(
            candidates=candidates,
            video_duration=video_duration,
            selected_thumbnails=selected_thumbnails,
        )

        thumbnail_dir = job_dir / "output" / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[str] = []
        manifest_candidates: list[dict[str, Any]] = []
        extraction_errors: list[str] = []

        max_timestamp = (
            max(video_duration - MIN_THUMBNAIL_OFFSET_SECONDS, 0.0) if video_duration > 0 else None
        )

        for rank, candidate in enumerate(ranked_candidates, start=1):
            raw_timestamp = float(candidate.get("timestamp_seconds", 0.0))
            timestamp_seconds = max(raw_timestamp, 0.0)
            if max_timestamp is not None:
                timestamp_seconds = min(timestamp_seconds, max_timestamp)

            thumbnail_path = thumbnail_dir / f"thumbnail_{rank:02d}.jpg"
            args = [
                "-ss",
                f"{timestamp_seconds:.3f}",
                "-i",
                str(input_video),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(thumbnail_path),
            ]

            try:
                run_ffmpeg(args)
                self._assert_output_exists(thumbnail_path, f"thumbnail_{rank:02d}")
            except (FFmpegError, FileNotFoundError, RuntimeError) as e:
                extraction_errors.append(
                    f"{candidate.get('timestamp')} ({timestamp_seconds:.2f}s): {e}"
                )
                continue

            relative_path = str(thumbnail_path.relative_to(job_dir))
            outputs.append(relative_path)
            raw_analysis_index = candidate.get("analysis_index")
            analysis_index = raw_analysis_index if isinstance(raw_analysis_index, int) else None
            selection_rank = (
                selected_rank_map.get(analysis_index) if analysis_index is not None else None
            )
            is_selected = selection_rank is not None
            manifest_candidates.append(
                {
                    "rank": rank,
                    "path": relative_path,
                    "timestamp": candidate.get("timestamp"),
                    "timestamp_seconds": round(timestamp_seconds, 3),
                    "score": candidate.get("score"),
                    "source": candidate.get("source", source),
                    "analysis_index": analysis_index,
                    "is_selected": is_selected,
                    "selection_rank": selection_rank,
                    "visual_description": candidate.get("visual_description", ""),
                    "suggested_text_overlay": candidate.get("suggested_text_overlay", ""),
                    "emotion": candidate.get("emotion", ""),
                }
            )

        manifest_payload = {
            "generated_at": self._format_timestamp_seconds(),
            "source": source,
            "selected_thumbnail_index": decisions.selected_thumbnail,
            "selected_thumbnail_indices": selected_thumbnails,
            "generated": len(manifest_candidates),
            "errors": extraction_errors,
            "thumbnails": manifest_candidates,
        }
        manifest_path = thumbnail_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2))
        outputs.append(str(manifest_path.relative_to(job_dir)))

        if manifest_candidates:
            return outputs, {
                "status": "complete",
                "source": source,
                "generated": len(manifest_candidates),
                "thumbnail_paths": [item["path"] for item in manifest_candidates],
            }

        return outputs, {
            "status": "failed",
            "source": source,
            "generated": 0,
            "thumbnail_paths": [],
            "error": extraction_errors[0]
            if extraction_errors
            else "thumbnail extraction failed for all candidates",
        }

    def _resolve_ranked_thumbnail_selection(self, decisions: ReviewDecisions) -> list[int]:
        """Normalize ranked thumbnail selection from review decisions."""
        ranked: list[int] = []
        if decisions.selected_thumbnail is not None:
            ranked.append(decisions.selected_thumbnail)
        for index in decisions.selected_thumbnails:
            if index not in ranked:
                ranked.append(index)
            if len(ranked) >= 3:
                break
        return ranked

    def _thumbnail_spec_for_platform(self, platform: str) -> ThumbnailTargetSpec | None:
        """Return configured thumbnail constraints for a target platform when required."""
        if platform not in THUMBNAIL_COMPLIANCE_PLATFORMS:
            return None
        return getattr(self.config.thumbnails, platform, None)

    def _enforce_thumbnail_target_compliance(
        self,
        job_dir: Path,
        selected_platforms: list[str],
        thumbnail_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate target thumbnail artifacts and validate constraints per selected target."""
        required_targets = [
            platform
            for platform in selected_platforms
            if self._thumbnail_spec_for_platform(platform) is not None
        ]
        if not required_targets:
            return {"status": "skipped", "outputs": [], "platform_results": {}}

        raw_thumbnail_paths = thumbnail_result.get("thumbnail_paths")
        thumbnail_paths = raw_thumbnail_paths if isinstance(raw_thumbnail_paths, list) else []
        if not thumbnail_paths:
            missing_results: dict[str, dict[str, Any]] = {
                platform: {
                    "status": "failed",
                    "issues": ["no generated thumbnail assets available for compliance validation"],
                    "outputs": [],
                }
                for platform in required_targets
            }
            return {
                "status": "failed",
                "outputs": [],
                "platform_results": missing_results,
                "error": "no generated thumbnail assets available for selected target compliance",
            }

        outputs: list[str] = []
        platform_results: dict[str, dict[str, Any]] = {}
        validated_platforms: list[str] = []
        failed_platforms: list[str] = []

        for platform in required_targets:
            spec = self._thumbnail_spec_for_platform(platform)
            if spec is None:
                continue

            issues: list[str] = []
            platform_outputs: list[str] = []
            for rank, relative_source_path in enumerate(thumbnail_paths, start=1):
                source_path = job_dir / str(relative_source_path)
                if not source_path.exists():
                    issues.append(f"source thumbnail missing: {relative_source_path}")
                    continue

                target_path = self._derive_target_thumbnail_path(
                    job_dir=job_dir,
                    platform=platform,
                    rank=rank,
                    extension=spec.formats[0],
                )

                try:
                    self._transform_thumbnail_to_spec(source_path, target_path, spec)
                    validation_issues = self._validate_thumbnail_asset(target_path, spec, platform)
                    if validation_issues:
                        issues.extend(validation_issues)
                        continue
                except (FFmpegError, FileNotFoundError, RuntimeError, OSError, ValueError) as exc:
                    issues.append(str(exc))
                    continue

                relative_target_path = str(target_path.relative_to(job_dir))
                platform_outputs.append(relative_target_path)
                outputs.append(relative_target_path)

            if issues:
                failed_platforms.append(platform)
                platform_results[platform] = {
                    "status": "failed",
                    "issues": issues,
                    "outputs": platform_outputs,
                    "constraints": spec.model_dump(),
                }
            else:
                validated_platforms.append(platform)
                platform_results[platform] = {
                    "status": "success",
                    "issues": [],
                    "outputs": platform_outputs,
                    "constraints": spec.model_dump(),
                }

        if failed_platforms:
            issue_summary = "; ".join(
                f"{platform}: {', '.join(platform_results[platform]['issues'][:2])}"
                for platform in failed_platforms
            )
            return {
                "status": "failed",
                "outputs": outputs,
                "platform_results": platform_results,
                "validated_platforms": validated_platforms,
                "error": f"thumbnail compliance failed - {issue_summary}",
            }

        return {
            "status": "complete",
            "outputs": outputs,
            "platform_results": platform_results,
            "validated_platforms": validated_platforms,
        }

    def _derive_target_thumbnail_path(
        self,
        job_dir: Path,
        platform: str,
        rank: int,
        extension: str,
    ) -> Path:
        """Build deterministic output path for target-specific thumbnail artifacts."""
        target_dir = job_dir / "output" / "thumbnails" / platform
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"thumbnail_{rank:02d}.{extension}"

    def _transform_thumbnail_to_spec(
        self,
        source_path: Path,
        target_path: Path,
        spec: ThumbnailTargetSpec,
    ) -> None:
        """Transform a canonical thumbnail image into platform-specific constraints."""
        source_width, source_height = self._thumbnail_dimensions(source_path)
        transform_filter = self._build_thumbnail_transform_filter(
            source_width=source_width,
            source_height=source_height,
            target_width=spec.width,
            target_height=spec.height,
        )
        ffmpeg_args = [
            "-i",
            str(source_path),
            "-vf",
            transform_filter,
            "-frames:v",
            "1",
            str(target_path),
        ]
        run_ffmpeg(ffmpeg_args)
        self._assert_output_exists(target_path, f"{target_path.parent.name} thumbnail")

    def _build_thumbnail_transform_filter(
        self,
        source_width: int,
        source_height: int,
        target_width: int,
        target_height: int,
    ) -> str:
        """Build deterministic crop/scale filter that fills target dimensions."""
        source_ratio = source_width / source_height
        target_ratio = target_width / target_height

        if abs(source_ratio - target_ratio) < 0.001:
            return f"scale={target_width}:{target_height}"

        if source_ratio > target_ratio:
            # Wider source: crop left/right.
            crop_width = round(source_height * target_ratio)
            x_offset = max((source_width - crop_width) // 2, 0)
            return f"crop={crop_width}:{source_height}:{x_offset}:0,scale={target_width}:{target_height}"

        # Taller source: crop top/bottom.
        crop_height = round(source_width / target_ratio)
        y_offset = max((source_height - crop_height) // 2, 0)
        return (
            f"crop={source_width}:{crop_height}:0:{y_offset},scale={target_width}:{target_height}"
        )

    def _thumbnail_dimensions(self, path: Path) -> tuple[int, int]:
        """Read image dimensions from ffprobe metadata."""
        probe_data = run_ffprobe(path, extra_args=["-select_streams", "v:0"])
        streams = probe_data.get("streams", [])
        if not streams:
            raise ValueError(f"Unable to read thumbnail stream metadata: {path}")

        stream = streams[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid thumbnail dimensions for {path}: {width}x{height}")
        return width, height

    def _validate_thumbnail_asset(
        self,
        path: Path,
        spec: ThumbnailTargetSpec,
        platform: str,
    ) -> list[str]:
        """Validate one generated thumbnail against target constraints."""
        issues: list[str] = []

        extension = path.suffix.lstrip(".").lower()
        if extension == "jpeg":
            extension = "jpg"
        allowed_extensions = ["jpg" if fmt == "jpeg" else fmt for fmt in spec.formats]
        if extension not in allowed_extensions:
            issues.append(
                f"{platform}: unsupported thumbnail format '{path.suffix}' "
                f"(allowed: {', '.join(spec.formats)})"
            )

        try:
            size_bytes = path.stat().st_size
        except OSError as exc:
            return [f"{platform}: unable to read thumbnail size for {path} ({exc})"]
        if size_bytes > spec.max_size_bytes:
            issues.append(
                f"{platform}: thumbnail size {size_bytes} exceeds max_size_bytes={spec.max_size_bytes}"
            )

        try:
            width, height = self._thumbnail_dimensions(path)
        except (ValueError, FFmpegError, FileNotFoundError) as exc:
            issues.append(f"{platform}: {exc}")
            return issues
        if width != spec.width or height != spec.height:
            issues.append(
                f"{platform}: thumbnail dimensions {width}x{height} do not match required "
                f"{spec.width}x{spec.height}"
            )

        return issues

    def _parse_timestamp_seconds(self, value: Any) -> float | None:
        """Parse timestamp-like values into seconds."""
        if isinstance(value, (int, float)):
            return max(float(value), 0.0)
        total_seconds = 0.0
        is_valid = False

        if isinstance(value, str):
            normalized = value.strip()
            parts = normalized.split(":") if normalized else []

            if len(parts) in {2, 3}:
                try:
                    numbers = [float(part) for part in parts]
                except ValueError:
                    numbers = []

                if numbers and all(number >= 0 for number in numbers):
                    if len(numbers) == 2:
                        minutes, seconds = numbers
                        is_valid = seconds < 60
                        total_seconds = (minutes * 60.0) + seconds
                    else:
                        hours, minutes, seconds = numbers
                        is_valid = minutes < 60 and seconds < 60
                        total_seconds = (hours * 3600.0) + (minutes * 60.0) + seconds

        return total_seconds if is_valid else None

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as MM:SS or HH:MM:SS."""
        rounded = max(round(seconds), 0)
        minutes, second = divmod(rounded, 60)
        hours, minute = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minute:02d}:{second:02d}"
        return f"{minute:02d}:{second:02d}"

    def _format_timestamp_seconds(self) -> str:
        """Timestamp helper for JSON artifacts."""
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()

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
            value_text = str(round(scaled_value))
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
        prepared_input = self._prepare_optional_dereverb_input(
            input_video=input_video,
            output_dir=output_dir,
            platform=platform,
            audio_bitrate=spec.audio_bitrate,
        )

        # HLS packaging target
        if platform == "apple_hls" or spec.container == "hls":
            return self._render_hls(
                output_dir,
                prepared_input,
                platform,
                spec,
                video_info,
                edit_plan,
                normalize_audio,
            )

        # Audio-only platforms
        if spec.audio_only:
            return self._render_audio_only(
                output_dir, prepared_input, platform, spec, normalize_audio
            )

        # Video platforms
        return self._render_video(
            output_dir,
            prepared_input,
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
        ]
        enhancement_filters = self._build_audio_enhancement_filters()
        if enhancement_filters:
            args.extend(["-af", ",".join(enhancement_filters)])
        args.append(str(output_file))

        run_ffmpeg(args)
        self._assert_output_exists(output_file, f"{platform} audio export")

        if normalize_audio:
            self._normalize_loudness(
                output_file,
                spec.loudness_lufs,
                audio_codec=spec.audio_codec,
                audio_bitrate=spec.audio_bitrate,
            )
        else:
            self.logger.info("loudness_normalization_disabled", platform=platform)
        self._assert_output_exists(output_file, f"{platform} audio export")

        self.logger.info(f"{platform}_rendered", output=str(output_file))
        return [str(output_file.relative_to(output_dir.parent.parent))]

    def _render_hls(
        self,
        output_dir: Path,
        input_video: Path,
        platform: str,
        spec: PlatformSpec,
        video_info: dict[str, Any],
        edit_plan: EditPlan | None,
        normalize_audio: bool,
    ) -> list[str]:
        """Render Apple-focused HLS VOD artifacts and verify playlist integrity."""
        if spec.hls is None:
            raise ValueError("HLS render requires platform.hls configuration")

        src_width = video_info.get("width", 1920)
        src_height = video_info.get("height", 1080)
        src_duration = video_info.get("duration", 0)

        target_width = spec.width or src_width
        target_height = spec.height or src_height
        vf_filters = self._build_video_filters(
            src_width, src_height, target_width, target_height, spec
        )
        af_filters = self._build_audio_enhancement_filters()
        transcript_words = self._load_transcript_words(output_dir.parent.parent)
        edit_filter = self._build_edit_plan_filter(
            edit_plan,
            src_duration,
            vf_filters,
            af_filters,
            transcript_words=transcript_words,
        )

        duration_args: list[str] = []
        if spec.max_duration and src_duration > spec.max_duration:
            duration_args = ["-t", str(spec.max_duration)]

        args = ["-i", str(input_video), *duration_args]

        if edit_filter:
            filter_complex, video_map, audio_map = edit_filter
            args.extend(["-filter_complex", filter_complex, "-map", video_map, "-map", audio_map])
        else:
            args.extend(["-map", "0:v:0", "-map", "0:a:0"])
            if vf_filters:
                args.extend(["-vf", ",".join(vf_filters)])
            if af_filters:
                args.extend(["-af", ",".join(af_filters)])

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
        codec_supports_profile_level = self._supports_profile_level_flags(spec.video_codec)
        if codec_supports_profile_level and spec.video_profile:
            args.extend(["-profile:v", spec.video_profile])
        if codec_supports_profile_level and spec.video_level:
            args.extend(["-level:v", spec.video_level])
        if codec_supports_profile_level and spec.gop is not None:
            args.extend(["-g", str(spec.gop)])
        if codec_supports_profile_level and spec.keyint_min is not None:
            args.extend(["-keyint_min", str(spec.keyint_min)])
        if spec.fps:
            args.extend(["-r", str(spec.fps)])

        segment_template_path = self._resolve_hls_template_path(
            output_dir,
            spec.hls.segment_filename_pattern,
            "segment_filename_pattern",
        )
        variant_playlist_path = self._resolve_hls_template_path(
            output_dir,
            spec.hls.variant_playlist_pattern,
            "variant_playlist_pattern",
        )

        args.extend(
            [
                "-c:a",
                spec.audio_codec,
                "-b:a",
                spec.audio_bitrate,
                "-ac",
                str(spec.audio_channels),
                "-f",
                "hls",
                "-hls_time",
                str(spec.hls.segment_duration),
                "-hls_playlist_type",
                spec.hls.playlist_type,
                "-master_pl_name",
                spec.hls.master_playlist_name,
                "-var_stream_map",
                spec.hls.var_stream_map,
                "-hls_segment_filename",
                str(segment_template_path),
                str(variant_playlist_path),
            ]
        )

        run_ffmpeg(args)
        if normalize_audio:
            self.logger.info(
                "hls_loudness_normalization_skipped",
                platform=platform,
                reason="HLS variant ladder generated in a single ffmpeg invocation",
            )

        outputs = self._validate_hls_artifacts(output_dir=output_dir, platform=platform, spec=spec)
        self.logger.info(f"{platform}_rendered", outputs=outputs)
        return outputs

    def _validate_hls_artifacts(
        self,
        output_dir: Path,
        platform: str,
        spec: PlatformSpec,
    ) -> list[str]:
        """Validate HLS master/variant playlists and referenced segment files."""
        if spec.hls is None:
            raise ValueError("HLS validation requires platform.hls configuration")

        output_root = output_dir.resolve()
        master_playlist = output_root / spec.hls.master_playlist_name
        self._assert_output_exists(master_playlist, f"{platform} master playlist")

        master_entries = [
            line.strip()
            for line in master_playlist.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        variant_playlists = [entry for entry in master_entries if entry.endswith(".m3u8")]
        if not variant_playlists:
            raise RuntimeError(
                f"{platform} master playlist missing variant playlist references: {master_playlist}"
            )

        artifact_paths: list[Path] = [master_playlist]
        for variant_ref in variant_playlists:
            variant_path = self._resolve_hls_reference_path(
                base_dir=master_playlist.parent,
                reference=variant_ref,
                output_root=output_root,
                artifact_name=f"{platform} master playlist",
            )
            self._assert_output_exists(variant_path, f"{platform} variant playlist")
            artifact_paths.append(variant_path)

            segment_entries = [
                line.strip()
                for line in variant_path.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            if not segment_entries:
                raise RuntimeError(
                    f"{platform} variant playlist missing segment entries: {variant_path}"
                )

            for segment_ref in segment_entries:
                segment_path = self._resolve_hls_reference_path(
                    base_dir=variant_path.parent,
                    reference=segment_ref,
                    output_root=output_root,
                    artifact_name=f"{platform} variant playlist",
                )
                self._assert_output_exists(segment_path, f"{platform} HLS segment")
                artifact_paths.append(segment_path)

        deduped = sorted(
            {path: path for path in artifact_paths}.values(), key=lambda item: str(item)
        )
        job_root = output_dir.parent.parent.resolve()
        return [str(path.relative_to(job_root)) for path in deduped]

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
        af_filters = self._build_audio_enhancement_filters()
        transcript_words = self._load_transcript_words(output_dir.parent.parent)

        edit_filter = self._build_edit_plan_filter(
            edit_plan,
            src_duration,
            vf_filters,
            af_filters,
            transcript_words=transcript_words,
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

        codec_supports_profile_level = self._supports_profile_level_flags(spec.video_codec)
        if codec_supports_profile_level and spec.video_profile:
            args.extend(["-profile:v", spec.video_profile])
        if codec_supports_profile_level and spec.video_level:
            args.extend(["-level:v", spec.video_level])
        if codec_supports_profile_level and spec.gop is not None:
            args.extend(["-g", str(spec.gop)])
        if codec_supports_profile_level and spec.keyint_min is not None:
            args.extend(["-keyint_min", str(spec.keyint_min)])

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
            self._normalize_loudness(
                output_file,
                spec.loudness_lufs,
                audio_codec=spec.audio_codec,
                audio_bitrate=spec.audio_bitrate,
            )
        else:
            self.logger.info("loudness_normalization_disabled", platform=platform)
        self._assert_output_exists(output_file, f"{platform} video export")
        self._validate_video_platform_compliance(
            platform=platform,
            output_file=output_file,
            spec=spec,
        )

        self.logger.info(f"{platform}_rendered", output=str(output_file))
        return [str(output_file.relative_to(output_dir.parent.parent))]

    def _supports_profile_level_flags(self, video_codec: str) -> bool:
        """Return whether a codec supports profile/level and GOP cadence flags."""
        return video_codec.strip().lower() in PROFILE_LEVEL_CODECS

    def _expected_probe_codec(self, configured_codec: str) -> str | None:
        """Map encoder names to ffprobe codec_name values for compliance checks."""
        normalized = configured_codec.strip().lower()
        if normalized in {"h264", "libx264"}:
            return "h264"
        if normalized in {"h265", "hevc", "libx265"}:
            return "hevc"
        return None

    def _parse_numeric_probe_value(self, value: Any) -> float | None:
        """Parse ffprobe numeric fields that may be strings or numbers."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_probe_level(self, value: Any) -> float | None:
        """Parse ffprobe level values (e.g., 41 -> 4.1)."""
        if value is None:
            return None
        if isinstance(value, int):
            return value / 10.0
        parsed = self._parse_numeric_probe_value(value)
        if parsed is None:
            return None
        return parsed / 10.0 if parsed > 10 else parsed

    def _validate_video_platform_compliance(
        self,
        platform: str,
        output_file: Path,
        spec: PlatformSpec,
    ) -> None:
        """Run post-render compliance checks for strict video podcast targets."""
        if platform not in {"spotify_video", "apple_video"}:
            return

        probe_data = run_ffprobe(output_file)
        streams = probe_data.get("streams", [])
        format_info = probe_data.get("format", {})
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

        issues: list[str] = []
        warnings: list[str] = []

        if len(video_streams) != 1 or len(audio_streams) != 1:
            issues.append(
                "topology check failed: expected exactly 1 video stream and 1 audio stream"
            )

        if video_streams:
            video_stream = video_streams[0]
            expected_codec = self._expected_probe_codec(spec.video_codec)
            actual_codec = str(video_stream.get("codec_name", "")).strip().lower()
            if expected_codec and actual_codec and actual_codec != expected_codec:
                issues.append(f"codec mismatch: expected {expected_codec}, found {actual_codec}")

            actual_pix_fmt = str(video_stream.get("pix_fmt", "")).strip().lower()
            expected_pix_fmt = spec.pix_fmt.strip().lower()
            if expected_pix_fmt and actual_pix_fmt and actual_pix_fmt != expected_pix_fmt:
                issues.append(
                    f"pix_fmt mismatch: expected {expected_pix_fmt}, found {actual_pix_fmt}"
                )

            if spec.video_profile:
                expected_profile = spec.video_profile.strip().lower()
                actual_profile = str(video_stream.get("profile", "")).strip().lower()
                if actual_profile and actual_profile != expected_profile:
                    issues.append(
                        f"profile mismatch: expected {expected_profile}, found {actual_profile}"
                    )
                elif not actual_profile:
                    warnings.append("profile metadata missing from ffprobe output")

            if spec.video_level:
                expected_level = self._parse_numeric_probe_value(spec.video_level)
                actual_level = self._parse_probe_level(video_stream.get("level"))
                if expected_level is not None and actual_level is not None:
                    if abs(actual_level - expected_level) > 0.05:
                        issues.append(
                            f"level mismatch: expected {spec.video_level}, found {actual_level:.1f}"
                        )
                elif expected_level is not None:
                    warnings.append("level metadata missing from ffprobe output")

        if len(video_streams) == 1 and len(audio_streams) == 1:
            video_stream = video_streams[0]
            audio_stream = audio_streams[0]
            fallback_duration = self._parse_numeric_probe_value(format_info.get("duration"))
            video_duration = self._parse_numeric_probe_value(video_stream.get("duration"))
            audio_duration = self._parse_numeric_probe_value(audio_stream.get("duration"))
            if video_duration is None:
                video_duration = fallback_duration
            if audio_duration is None:
                audio_duration = fallback_duration

            if video_duration is not None and audio_duration is not None:
                delta = abs(video_duration - audio_duration)
                if delta > 0.25:
                    issues.append(
                        "duration parity check failed: "
                        f"audio/video delta {delta:.3f}s exceeds 0.250s"
                    )
            else:
                warnings.append("duration metadata unavailable for parity check")

        if platform == "spotify_video":
            format_name = str(format_info.get("format_name", "")).lower()
            if format_name and "mp4" not in format_name and "mov" not in format_name:
                issues.append(
                    f"container mismatch: expected mp4-compatible format, found {format_name}"
                )

            # Spotify docs flag edit-list (EDL) risk; ffprobe-only detection is heuristic.
            non_zero_starts = []
            for stream in video_streams + audio_streams:
                start_value = self._parse_numeric_probe_value(stream.get("start_time"))
                if start_value is not None and abs(start_value) > 0.1:
                    non_zero_starts.append(start_value)
            if non_zero_starts:
                warnings.append(
                    "non-zero stream start_time detected; possible EDL/timeline offset risk"
                )

            if spec.gop is not None and spec.fps:
                keyframe_interval = spec.gop / spec.fps
                if keyframe_interval > 2.0:
                    warnings.append(
                        "configured keyframe cadence exceeds 2s; may degrade seek behavior"
                    )
        elif platform == "apple_video":
            format_name = str(format_info.get("format_name", "")).lower()
            if format_name and "mp4" not in format_name and "mov" not in format_name:
                issues.append(
                    "container mismatch: expected MP4/MOV-compatible Apple video format, "
                    f"found {format_name}"
                )

        if warnings:
            self.logger.warning(
                "render_platform_compliance_warnings",
                platform=platform,
                warnings=warnings,
                output=str(output_file),
            )

        if issues:
            raise PlatformComplianceError(platform=platform, issues=issues, warnings=warnings)

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

        filters.extend(self._build_color_correction_filters())
        return filters

    def _build_edit_plan_filter(
        self,
        edit_plan: EditPlan | None,
        duration: float,
        vf_filters: list[str],
        af_filters: list[str],
        *,
        transcript_words: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str, str] | None:
        """Build transition-aware filter_complex for edit-plan cuts."""
        if not edit_plan or duration <= 0:
            return None

        cut_ranges = self._collect_cut_ranges(edit_plan)
        if not cut_ranges:
            return None

        cut_ranges = self._apply_word_boundary_snapping(cut_ranges, transcript_words)
        cut_ranges = self._merge_ranges(cut_ranges)
        keep_ranges, join_kinds = self._invert_cut_ranges(cut_ranges, duration)
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

        keep_durations = [max(end - start, 0.0) for start, end in keep_ranges]
        if not any(segment > _EPSILON for segment in keep_durations):
            return None

        smoothing = self.config.smoothing
        micro_fade_s = (smoothing.micro_fade_ms / 1000.0) if smoothing.enabled else 0.0
        base_crossfade_s = (
            smoothing.content_audio_crossfade_ms / 1000.0 if smoothing.enabled else 0.0
        )
        base_dissolve_s = smoothing.content_video_dissolve_ms / 1000.0 if smoothing.enabled else 0.0
        has_content_join = any(kind == "content" for kind in join_kinds)
        transition_available = self._resolve_transition_filter_availability(
            needs_content_transitions=has_content_join
        )
        normalize_for_xfade = has_content_join and transition_available["xfade"]

        filter_parts: list[str] = []
        for idx, (start, end) in enumerate(keep_ranges):
            segment_duration = keep_durations[idx]
            video_chain = f"trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS"
            if normalize_for_xfade:
                video_chain = f"{video_chain},fps=30,format=yuv420p,settb=AVTB"
            filter_parts.append(f"[0:v]{video_chain}[v{idx}]")
            audio_chain = f"atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS"
            if micro_fade_s > 0 and segment_duration > _EPSILON:
                fade_duration = min(micro_fade_s, max((segment_duration / 2.0) - _EPSILON, 0.0))
                if fade_duration > _EPSILON:
                    fade_out_start = max(segment_duration - fade_duration, 0.0)
                    audio_chain = (
                        f"{audio_chain},afade=t=in:st=0:d={fade_duration:.3f},"
                        f"afade=t=out:st={fade_out_start:.3f}:d={fade_duration:.3f}"
                    )
            filter_parts.append(f"[0:a]{audio_chain}[a{idx}]")

        video_label = "v0"
        audio_label = "a0"
        video_duration = keep_durations[0]
        audio_duration = keep_durations[0]
        for idx in range(1, len(keep_ranges)):
            next_video = f"v{idx}"
            next_audio = f"a{idx}"
            next_duration = keep_durations[idx]
            join_kind = join_kinds[idx - 1] if idx - 1 < len(join_kinds) else "filler"
            join_label_audio = f"a_join{idx}"
            join_label_video = f"v_join{idx}"

            apply_content_audio = (
                join_kind == "content"
                and base_crossfade_s > 0
                and transition_available["acrossfade"]
            )
            if apply_content_audio:
                crossfade_s = self._clamp_transition_duration(
                    base_duration_s=base_crossfade_s,
                    left_duration_s=audio_duration,
                    right_duration_s=next_duration,
                    clamp_ratio=smoothing.join_clamp_ratio,
                )
                if crossfade_s > _EPSILON:
                    filter_parts.append(
                        f"[{audio_label}][{next_audio}]"
                        f"acrossfade=d={crossfade_s:.3f}:c1=tri:c2=tri[{join_label_audio}]"
                    )
                    audio_duration = max(audio_duration + next_duration - crossfade_s, 0.0)
                else:
                    filter_parts.append(
                        f"[{audio_label}][{next_audio}]concat=n=2:v=0:a=1[{join_label_audio}]"
                    )
                    audio_duration += next_duration
            else:
                filter_parts.append(
                    f"[{audio_label}][{next_audio}]concat=n=2:v=0:a=1[{join_label_audio}]"
                )
                audio_duration += next_duration
            audio_label = join_label_audio

            apply_content_video = (
                join_kind == "content" and base_dissolve_s > 0 and transition_available["xfade"]
            )
            if apply_content_video:
                dissolve_s = self._clamp_transition_duration(
                    base_duration_s=base_dissolve_s,
                    left_duration_s=video_duration,
                    right_duration_s=next_duration,
                    clamp_ratio=smoothing.join_clamp_ratio,
                )
                if dissolve_s > _EPSILON:
                    offset = max(video_duration - dissolve_s, 0.0)
                    filter_parts.append(
                        f"[{video_label}][{next_video}]"
                        f"xfade=transition=fade:duration={dissolve_s:.3f}:offset={offset:.3f}"
                        f"[{join_label_video}]"
                    )
                    video_duration = max(video_duration + next_duration - dissolve_s, 0.0)
                else:
                    filter_parts.append(
                        f"[{video_label}][{next_video}]concat=n=2:v=1:a=0[{join_label_video}]"
                    )
                    video_duration += next_duration
            else:
                filter_parts.append(
                    f"[{video_label}][{next_video}]concat=n=2:v=1:a=0[{join_label_video}]"
                )
                video_duration += next_duration
            video_label = join_label_video

        if vf_filters:
            filter_parts.append(f"[{video_label}]{','.join(vf_filters)}[vfinal]")
            video_label = "vfinal"
        if af_filters:
            filter_parts.append(f"[{audio_label}]{','.join(af_filters)}[afinal]")
            audio_label = "afinal"

        return ";".join(filter_parts), f"[{video_label}]", f"[{audio_label}]"

    def _collect_cut_ranges(self, edit_plan: EditPlan) -> list[_CutRange]:
        """Collect typed cut ranges from edit plan in seconds."""
        ranges: list[_CutRange] = []

        for cut in edit_plan.filler_cuts:
            start = max(0.0, float(cut.start_seconds))
            end = max(0.0, float(cut.end_seconds))
            if end > start:
                ranges.append(_CutRange(start=start, end=end, kind="filler"))

        for content_cut in edit_plan.content_cuts:
            start = max(0.0, float(content_cut.start_seconds))
            end = max(0.0, float(content_cut.end_seconds))
            if end > start:
                ranges.append(_CutRange(start=start, end=end, kind="content"))
        return ranges

    def _apply_word_boundary_snapping(
        self,
        ranges: list[_CutRange],
        transcript_words: list[dict[str, Any]] | None,
    ) -> list[_CutRange]:
        """Snap cut boundaries to transcript word gaps when timing metadata exists."""
        if not ranges or not transcript_words or not self.config.smoothing.enabled:
            return ranges

        boundaries = find_word_boundaries(transcript_words)
        if not boundaries:
            return ranges

        max_shift_s = max(self.config.smoothing.max_snap_shift_ms / 1000.0, 0.0)
        snapped: list[_CutRange] = []
        for cut in ranges:
            snapped_start, snapped_end = snap_cut_range(
                cut.start,
                cut.end,
                boundaries,
                max_shift_seconds=max_shift_s,
            )
            if snapped_end <= snapped_start:
                snapped_start, snapped_end = cut.start, cut.end
            snapped.append(_CutRange(start=snapped_start, end=snapped_end, kind=cut.kind))
        return snapped

    def _merge_ranges(self, ranges: list[_CutRange]) -> list[_CutRange]:
        """Merge overlapping cut ranges while preserving content-cut priority."""
        if not ranges:
            return []

        sorted_ranges = sorted(ranges, key=lambda item: item.start)
        merged = [sorted_ranges[0]]
        for current in sorted_ranges[1:]:
            previous = merged[-1]
            if current.start <= (previous.end + _EPSILON):
                merged_kind: Literal["filler", "content"] = (
                    "content"
                    if previous.kind == "content" or current.kind == "content"
                    else "filler"
                )
                merged[-1] = _CutRange(
                    start=previous.start,
                    end=max(previous.end, current.end),
                    kind=merged_kind,
                )
            else:
                merged.append(current)
        return merged

    def _invert_cut_ranges(
        self,
        ranges: list[_CutRange],
        duration: float,
    ) -> tuple[list[tuple[float, float]], list[Literal["filler", "content"]]]:
        """Convert typed cut ranges into keep segments and join transition kinds."""
        if duration <= 0:
            return [], []

        keep_ranges: list[tuple[float, float]] = []
        join_kinds: list[Literal["filler", "content"]] = []
        cursor = 0.0
        for cut in ranges:
            start = min(max(cut.start, 0.0), duration)
            end = min(max(cut.end, 0.0), duration)
            if end <= start:
                continue
            if start > cursor:
                keep_ranges.append((cursor, min(start, duration)))
            if keep_ranges and end < duration:
                join_kinds.append(cut.kind)
            cursor = max(cursor, end)

        if cursor < duration:
            keep_ranges.append((cursor, duration))

        filtered_keep_ranges = [
            (start, end) for start, end in keep_ranges if (end - start) > _EPSILON
        ]
        expected_joins = max(len(filtered_keep_ranges) - 1, 0)
        return filtered_keep_ranges, join_kinds[:expected_joins]

    def _load_transcript_words(self, job_dir: Path) -> list[dict[str, Any]]:
        """Load transcript word timestamps for cut-boundary snapping."""
        transcript_path = job_dir / "analysis" / "transcript.json"
        if not transcript_path.exists():
            return []
        try:
            payload = json.loads(transcript_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.warning(
                "render_transcript_load_failed", path=str(transcript_path), error=str(exc)
            )
            return []

        words: list[dict[str, Any]] = []
        raw_words = payload.get("words") if isinstance(payload, dict) else None
        if isinstance(raw_words, list):
            words.extend(item for item in raw_words if isinstance(item, dict))

        raw_segments = payload.get("segments") if isinstance(payload, dict) else None
        if isinstance(raw_segments, list):
            for segment in raw_segments:
                if not isinstance(segment, dict):
                    continue
                segment_words = segment.get("words")
                if not isinstance(segment_words, list):
                    continue
                words.extend(item for item in segment_words if isinstance(item, dict))
        return words

    def _resolve_transition_filter_availability(
        self,
        *,
        needs_content_transitions: bool,
    ) -> dict[str, bool]:
        """Resolve optional transition filter support and fallback policy."""
        default_result = {"acrossfade": False, "xfade": False}
        smoothing = self.config.smoothing
        if not smoothing.enabled or not needs_content_transitions:
            return default_result

        requested: set[str] = set()
        if smoothing.content_audio_crossfade_ms > 0:
            requested.add("acrossfade")
        if smoothing.content_video_dissolve_ms > 0:
            requested.add("xfade")
        if not requested:
            return default_result

        try:
            available = self._probe_available_ffmpeg_filters()
        except RuntimeError as exc:
            if smoothing.require_transition_filters:
                raise
            self.logger.warning(
                "render_transition_filter_probe_failed",
                error=str(exc),
            )
            return default_result

        missing = sorted(requested - available)
        if missing:
            message = (
                "Render transition filters unavailable; falling back to concat joins for "
                f"{', '.join(missing)}."
            )
            if smoothing.require_transition_filters:
                raise RuntimeError(
                    "Render preflight failed: missing required transition filter(s): "
                    f"{', '.join(missing)}."
                )
            self.logger.warning(
                "render_transition_filters_missing",
                missing=missing,
                fallback="concat",
                message=message,
            )

        return {name: (name in available) for name in default_result}

    def _clamp_transition_duration(
        self,
        *,
        base_duration_s: float,
        left_duration_s: float,
        right_duration_s: float,
        clamp_ratio: float,
    ) -> float:
        """Clamp transition durations to avoid over-consuming short segments."""
        if base_duration_s <= 0 or left_duration_s <= 0 or right_duration_s <= 0:
            return 0.0
        max_allowed = min(left_duration_s, right_duration_s) * clamp_ratio
        return max(min(base_duration_s, max_allowed), 0.0)

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
                self.logger.exception("clip_export_failed", clip=idx, error=str(e))

        if outputs:
            self.logger.info("clips_exported", count=len(outputs))
        if clip_errors:
            raise RuntimeError("; ".join(clip_errors))

        return outputs

    def _normalize_loudness(
        self,
        audio_file: Path,
        target_lufs: float,
        *,
        audio_codec: str | None = None,
        audio_bitrate: str | None = None,
    ) -> dict[str, Any]:
        """Normalize audio to target LUFS with optional-dependency fallback."""
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
                return {"status": "skipped", "method": "pyloudnorm", "reason": "already_normalized"}

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
                        "-c:a",
                        audio_codec or "aac",
                        "-b:a",
                        audio_bitrate or "192k",
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
                # Determine whether the caller requested a non-WAV codec/bitrate.
                # soundfile can only write uncompressed PCM formats (WAV/FLAC/AIFF
                # etc.), so if a compressed codec like "aac", "libmp3lame", "libopus"
                # is requested we must write a temporary WAV first and then
                # re-encode it with ffmpeg.
                _wav_codecs = {None, "pcm_s16le", "pcm_s24le", "pcm_f32le", "wav"}
                needs_reencode = audio_codec not in _wav_codecs or audio_bitrate is not None

                if needs_reencode:
                    # Write normalized PCM to a temp WAV, then re-encode to target.
                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False, dir=audio_file.parent
                    ) as tmp_fd:
                        tmp_wav = Path(tmp_fd.name)
                    try:
                        sf.write(str(tmp_wav), normalized, rate)
                        # Re-encode into a separate file so the original is only
                        # replaced once the encode succeeds (atomic swap).
                        tmp_encoded = audio_file.with_name(
                            f"{audio_file.stem}.normalized_tmp{audio_file.suffix}"
                        )
                        run_ffmpeg(
                            [
                                "-i",
                                str(tmp_wav),
                                "-c:a",
                                audio_codec or "aac",
                                *(["-b:a", audio_bitrate] if audio_bitrate is not None else []),
                                str(tmp_encoded),
                            ]
                        )
                        # Atomic replace — only clobbers original on success.
                        tmp_encoded.replace(audio_file)
                    finally:
                        if tmp_wav.exists():
                            tmp_wav.unlink()
                        # Clean up partial encode output if something went wrong.
                        tmp_encoded_path = audio_file.with_name(
                            f"{audio_file.stem}.normalized_tmp{audio_file.suffix}"
                        )
                        if tmp_encoded_path.exists() and tmp_encoded_path != audio_file:
                            tmp_encoded_path.unlink()
                else:
                    # Plain WAV / no special codec — write back directly.
                    sf.write(str(audio_file), normalized, rate)

            self.logger.info(
                "loudness_normalized",
                file=str(audio_file),
                from_lufs=loudness,
                to_lufs=target_lufs,
            )
            return {"status": "normalized", "method": "pyloudnorm"}

        except ImportError:
            self.logger.warning(
                "pyloudnorm_not_available",
                message="Falling back to ffmpeg loudnorm",
            )
            if self._normalize_loudness_with_ffmpeg(
                audio_file,
                target_lufs,
                audio_codec=audio_codec,
                audio_bitrate=audio_bitrate,
            ):
                return {"status": "normalized", "method": "ffmpeg_loudnorm"}
            return {
                "status": "skipped",
                "method": "none",
                "reason": "normalization_dependencies_unavailable",
            }
        except Exception as e:
            self.logger.warning(
                "loudness_normalization_failed",
                error=str(e),
            )
            if self._normalize_loudness_with_ffmpeg(
                audio_file,
                target_lufs,
                audio_codec=audio_codec,
                audio_bitrate=audio_bitrate,
            ):
                return {
                    "status": "normalized",
                    "method": "ffmpeg_loudnorm",
                    "reason": "pyloudnorm_failed",
                }
            return {"status": "failed", "method": "none", "reason": str(e)}

    def _normalize_loudness_with_ffmpeg(
        self,
        audio_file: Path,
        target_lufs: float,
        *,
        audio_codec: str | None = None,
        audio_bitrate: str | None = None,
    ) -> bool:
        """Fallback normalization path when pyloudnorm stack is unavailable."""
        suffix = audio_file.suffix.lower()
        temp_output = audio_file.with_name(f"{audio_file.stem}.normalized{suffix}")
        loudnorm_filter = f"loudnorm=I={target_lufs}:LRA=11:TP=-1.5"

        try:
            if suffix in {".mp4", ".mov", ".mkv", ".webm"}:
                args = [
                    "-i",
                    str(audio_file),
                    "-c:v",
                    "copy",
                    "-af",
                    loudnorm_filter,
                    "-c:a",
                    audio_codec or "aac",
                    "-b:a",
                    audio_bitrate or "192k",
                    str(temp_output),
                ]
            else:
                codec = audio_codec or ("libmp3lame" if suffix == ".mp3" else "aac")
                bitrate = audio_bitrate or ("320k" if suffix == ".mp3" else "192k")
                args = [
                    "-i",
                    str(audio_file),
                    "-af",
                    loudnorm_filter,
                    "-c:a",
                    codec,
                    "-b:a",
                    bitrate,
                    str(temp_output),
                ]

            run_ffmpeg(args)
            self._assert_output_exists(temp_output, "fallback loudness normalization")
            temp_output.replace(audio_file)
            self.logger.info(
                "loudness_normalized_with_ffmpeg",
                file=str(audio_file),
                target=target_lufs,
            )
            return True
        except (FFmpegError, FileNotFoundError, RuntimeError) as e:
            self.logger.warning("ffmpeg_loudnorm_fallback_failed", error=str(e))
            if temp_output.exists():
                temp_output.unlink(missing_ok=True)
            return False

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
            ("Spotify Video", "spotify_video"),
            ("Apple Podcasts", "apple"),
            ("Apple Podcasts Video", "apple_video"),
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
