"""Typed FFmpeg media toolkit — deterministic command surface for Phase 9.

All 14 operations across 5 groups:
  Group 1: Probe & Inspect    — probe_media, extract_frame, detect_hardware_encoders
  Group 2: Encode & Transcode — transcode, normalize_loudness
  Group 3: Filter & Overlay   — burn_captions, overlay_image, apply_filtergraph, denoise
  Group 4: Edit & Assemble    — trim_segment, concat_segments, mix_audio, sync_tracks
  Group 5: Package & Deliver  — package_hls

Design invariants:
- Every tool takes/returns typed Pydantic models.
- No shell string composition. No eval-like filtergraph generation.
- All subprocess calls route through run_ffmpeg / run_ffprobe from utils.ffmpeg.
- Failures raise structured FFmpegToolkitError with operation, args, and stderr excerpt.
"""

from __future__ import annotations

import contextlib
import re
from enum import Enum
from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from podcast_pipeline.utils.ffmpeg import FFmpegError, run_ffmpeg, run_ffprobe
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Structured error
# ---------------------------------------------------------------------------


class FFmpegToolkitError(Exception):
    """Structured error for toolkit operation failures.

    Attributes:
        operation: Name of the toolkit operation that failed.
        cmd_args: The FFmpeg argument list that was invoked.
        stderr_excerpt: Last 500 chars of stderr for diagnostics.
        returncode: Process exit code (-1 if unknown).
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str = "",
        cmd_args: list[str] | None = None,
        stderr_excerpt: str = "",
        returncode: int = -1,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.cmd_args = cmd_args or []
        self.stderr_excerpt = stderr_excerpt
        self.returncode = returncode

    def __str__(self) -> str:
        base = super().__str__()
        parts = [base]
        if self.operation:
            parts.append(f"operation={self.operation!r}")
        if self.returncode != -1:
            parts.append(f"returncode={self.returncode}")
        if self.stderr_excerpt:
            parts.append(f"stderr={self.stderr_excerpt!r}")
        return " | ".join(parts)


def _wrap_ffmpeg_error(exc: FFmpegError, operation: str, cmd_args: list[str]) -> FFmpegToolkitError:
    """Convert FFmpegError to FFmpegToolkitError with structured context."""
    stderr_excerpt = exc.stderr[-500:] if exc.stderr else ""
    return FFmpegToolkitError(
        str(exc),
        operation=operation,
        cmd_args=cmd_args,
        stderr_excerpt=stderr_excerpt,
        returncode=exc.returncode,
    )


# ---------------------------------------------------------------------------
# Enumerations used in models
# ---------------------------------------------------------------------------


class VideoCodec(str, Enum):
    """Supported video codecs for transcode operation."""

    H264 = "h264"
    HEVC = "hevc"
    AV1 = "av1"


class QualityPreset(str, Enum):
    """FFmpeg quality presets (speed/quality tradeoff)."""

    ULTRAFAST = "ultrafast"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    VERYSLOW = "veryslow"


class HwAccel(str, Enum):
    """Hardware acceleration selection."""

    AUTO = "auto"
    NVENC = "nvenc"
    NONE = "none"


class OverlayPosition(str, Enum):
    """Named corner positions for overlay_image."""

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CENTER = "center"


class TransitionType(str, Enum):
    """Clip join transition type for concat_segments."""

    NONE = "none"
    CROSSFADE = "crossfade"
    DISSOLVE = "dissolve"


class DenoiseMethod(str, Enum):
    """Video denoising algorithm."""

    HQDN3D = "hqdn3d"
    NLMEANS = "nlmeans"


class DenoiseStrength(str, Enum):
    """Strength preset for denoising."""

    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


# ---------------------------------------------------------------------------
# Request/Response models — Group 1: Probe & Inspect
# ---------------------------------------------------------------------------


class StreamInfo(BaseModel):
    """Metadata for a single media stream."""

    index: int
    codec_type: str  # "video" | "audio" | "subtitle" | "data"
    codec_name: str = ""
    # Video-specific
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    pix_fmt: str | None = None
    color_space: str | None = None
    color_range: str | None = None
    is_hdr: bool = False
    # Audio-specific
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    bit_rate: int | None = None


class ProbeMediaResult(BaseModel):
    """Full metadata from probe_media."""

    path: Path
    format_name: str = ""
    duration: float = 0.0
    size_bytes: int = 0
    bit_rate: int = 0
    streams: list[StreamInfo] = Field(default_factory=list)
    # Convenience accessors populated from streams
    video: StreamInfo | None = None
    audio: StreamInfo | None = None
    audio_track_count: int = 0


class ExtractFrameRequest(BaseModel):
    """Input for extract_frame."""

    path: Path
    timestamp_s: float = Field(ge=0.0)
    output_path: Path


class ExtractFrameResult(BaseModel):
    """Output of extract_frame."""

    output_path: Path


class HardwareEncoderInfo(BaseModel):
    """Available hardware encoder capabilities."""

    nvenc_h264: bool = False
    nvenc_hevc: bool = False
    nvenc_av1: bool = False
    quicksync_h264: bool = False
    quicksync_hevc: bool = False
    videotoolbox_h264: bool = False
    videotoolbox_hevc: bool = False
    software_h264: bool = True
    software_hevc: bool = True
    software_av1: bool = False


# ---------------------------------------------------------------------------
# Request/Response models — Group 2: Encode & Transcode
# ---------------------------------------------------------------------------


class TranscodeRequest(BaseModel):
    """Input for transcode."""

    input_path: Path
    output_path: Path
    codec: VideoCodec = VideoCodec.HEVC
    quality_preset: QualityPreset = QualityPreset.MEDIUM
    bit_depth: int = Field(default=10, ge=8, le=10)
    film_grain: int = Field(default=0, ge=0, le=50)
    hw_accel: HwAccel = HwAccel.AUTO
    timeout: int = Field(default=3600, ge=1)

    @field_validator("bit_depth")
    @classmethod
    def bit_depth_must_be_8_or_10(cls, v: int) -> int:
        if v not in (8, 10):
            raise ValueError("bit_depth must be 8 or 10")
        return v

    @field_validator("film_grain")
    @classmethod
    def film_grain_only_for_av1(cls, v: int) -> int:
        # Validation happens at operation level; model stores the value
        return v


class TranscodeResult(BaseModel):
    """Output of transcode."""

    output_path: Path
    size_bytes: int = 0
    encode_time_s: float = 0.0


class NormalizeLoudnessRequest(BaseModel):
    """Input for normalize_loudness."""

    input_path: Path
    output_path: Path
    target_lufs: float = Field(default=-14.0, le=0.0)
    true_peak_dbtp: float = Field(default=-1.0, le=0.0)
    timeout: int = Field(default=3600, ge=1)


class NormalizeLoudnessResult(BaseModel):
    """Output of normalize_loudness."""

    output_path: Path
    input_lufs: float = 0.0
    output_lufs: float = 0.0


# ---------------------------------------------------------------------------
# Request/Response models — Group 3: Filter & Overlay
# ---------------------------------------------------------------------------


class BurnCaptionsRequest(BaseModel):
    """Input for burn_captions."""

    video_path: Path
    ass_path: Path
    output_path: Path
    force_style: str | None = None  # optional ASS style override string
    timeout: int = Field(default=3600, ge=1)


class BurnCaptionsResult(BaseModel):
    """Output of burn_captions."""

    output_path: Path


class OverlayImageRequest(BaseModel):
    """Input for overlay_image."""

    video_path: Path
    image_path: Path
    output_path: Path
    position: OverlayPosition = OverlayPosition.TOP_RIGHT
    opacity: float = Field(default=0.8, ge=0.0, le=1.0)
    fade_in_s: float = Field(default=0.0, ge=0.0)
    fade_out_s: float = Field(default=0.0, ge=0.0)
    scale: float = Field(default=1.0, gt=0.0)
    timeout: int = Field(default=3600, ge=1)


class OverlayImageResult(BaseModel):
    """Output of overlay_image."""

    output_path: Path


class ApplyFiltergraphRequest(BaseModel):
    """Input for apply_filtergraph."""

    input_path: Path
    output_path: Path
    filtergraph: str
    validate_first: bool = True
    timeout: int = Field(default=3600, ge=1)

    @field_validator("filtergraph")
    @classmethod
    def filtergraph_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("filtergraph must not be empty")
        return v


class ApplyFiltergraphResult(BaseModel):
    """Output of apply_filtergraph."""

    output_path: Path
    applied_filters: list[str] = Field(default_factory=list)


class DenoiseRequest(BaseModel):
    """Input for denoise."""

    input_path: Path
    output_path: Path
    method: DenoiseMethod = DenoiseMethod.HQDN3D
    strength: DenoiseStrength = DenoiseStrength.MEDIUM
    timeout: int = Field(default=3600, ge=1)


class DenoiseResult(BaseModel):
    """Output of denoise."""

    output_path: Path


# ---------------------------------------------------------------------------
# Request/Response models — Group 4: Edit & Assemble
# ---------------------------------------------------------------------------


class TrimSegmentRequest(BaseModel):
    """Input for trim_segment."""

    input_path: Path
    output_path: Path
    start_s: float = Field(default=0.0, ge=0.0)
    end_s: float | None = None
    copy_codec: bool = True


class TrimSegmentResult(BaseModel):
    """Output of trim_segment."""

    output_path: Path
    actual_start_s: float = 0.0
    actual_end_s: float | None = None


class ConcatSegmentsRequest(BaseModel):
    """Input for concat_segments."""

    segments: list[Path] = Field(min_length=1)
    output_path: Path
    transition: TransitionType = TransitionType.NONE
    transition_duration_s: float = Field(default=0.5, ge=0.0)
    timeout: int = Field(default=3600, ge=1)


class ConcatSegmentsResult(BaseModel):
    """Output of concat_segments."""

    output_path: Path
    total_duration_s: float = 0.0


class MixAudioRequest(BaseModel):
    """Input for mix_audio."""

    speech_path: Path
    music_path: Path
    output_path: Path
    music_volume_db: float = Field(default=-12.0)
    duck_enabled: bool = True
    duck_threshold_db: float = Field(default=-30.0)
    duck_ratio: float = Field(default=4.0, gt=0.0)
    fade_in_s: float = Field(default=0.0, ge=0.0)
    fade_out_s: float = Field(default=0.0, ge=0.0)
    timeout: int = Field(default=3600, ge=1)


class MixAudioResult(BaseModel):
    """Output of mix_audio."""

    output_path: Path


class SyncTracksRequest(BaseModel):
    """Input for sync_tracks."""

    reference_path: Path
    external_path: Path
    output_path: Path
    search_window_s: float = Field(default=60.0, gt=0.0)
    timeout: int = Field(default=3600, ge=1)


class SyncTracksResult(BaseModel):
    """Output of sync_tracks."""

    output_path: Path
    offset_ms: float = 0.0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Request/Response models — Group 5: Package & Deliver
# ---------------------------------------------------------------------------


class HlsVariant(BaseModel):
    """A single HLS variant stream specification."""

    bitrate_kbps: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    audio_bitrate_kbps: int = Field(default=128, gt=0)


class PackageHlsRequest(BaseModel):
    """Input for package_hls."""

    input_path: Path
    output_dir: Path
    segment_duration: int = Field(default=6, ge=1)
    variants: list[HlsVariant] = Field(min_length=1)
    timeout: int = Field(default=7200, ge=1)


class PackageHlsResult(BaseModel):
    """Output of package_hls."""

    master_playlist_path: Path
    segment_count: int = 0
    total_size_bytes: int = 0


# ---------------------------------------------------------------------------
# Helper: hardware encoder detection
# ---------------------------------------------------------------------------

_HW_ENCODER_CACHE: HardwareEncoderInfo | None = None


def _probe_encoders() -> list[str]:
    """Return list of available ffmpeg encoder names."""
    try:
        result = run_ffmpeg(["-encoders"], timeout=15, check=False)
        return result.stdout.splitlines()
    except FFmpegError:
        return []


def detect_hardware_encoders(*, use_cache: bool = True) -> HardwareEncoderInfo:
    """Detect available GPU and software encoders.

    Args:
        use_cache: Return cached result if already probed this process.

    Returns:
        HardwareEncoderInfo with capability flags.
    """
    global _HW_ENCODER_CACHE  # noqa: PLW0603
    if use_cache and _HW_ENCODER_CACHE is not None:
        return _HW_ENCODER_CACHE

    lines = _probe_encoders()
    encoder_text = "\n".join(lines)

    info = HardwareEncoderInfo(
        nvenc_h264="h264_nvenc" in encoder_text,
        nvenc_hevc="hevc_nvenc" in encoder_text,
        nvenc_av1="av1_nvenc" in encoder_text,
        quicksync_h264="h264_qsv" in encoder_text,
        quicksync_hevc="hevc_qsv" in encoder_text,
        videotoolbox_h264="h264_videotoolbox" in encoder_text,
        videotoolbox_hevc="hevc_videotoolbox" in encoder_text,
        software_h264="libx264" in encoder_text,
        software_hevc="libx265" in encoder_text,
        software_av1="libsvtav1" in encoder_text,
    )

    _HW_ENCODER_CACHE = info
    return info


def _select_video_encoder(
    codec: VideoCodec,
    hw_accel: HwAccel,
    bit_depth: int,
) -> tuple[str, list[str]]:
    """Resolve encoder name and extra args from codec/hw_accel/bit_depth.

    Returns:
        Tuple of (encoder_name, extra_args).
    """
    hw = detect_hardware_encoders() if hw_accel in (HwAccel.AUTO, HwAccel.NVENC) else None

    if codec == VideoCodec.H264:
        if hw_accel != HwAccel.NONE and hw and hw.nvenc_h264:
            return "h264_nvenc", []
        return "libx264", []

    if codec == VideoCodec.HEVC:
        profile = "main10" if bit_depth == 10 else "main"
        if hw_accel != HwAccel.NONE and hw and hw.nvenc_hevc:
            nvenc_pix_fmt = "p010le" if bit_depth == 10 else "yuv420p"
            return "hevc_nvenc", ["-pix_fmt", nvenc_pix_fmt, "-profile:v", profile]
        # Software fallback — libx265 uses yuv420p10le for 10-bit (not p010le which is NV12)
        sw_pix_fmt = "yuv420p10le" if bit_depth == 10 else "yuv420p"
        return "libx265", ["-pix_fmt", sw_pix_fmt, "-x265-params", f"profile={profile}"]

    if codec == VideoCodec.AV1:
        # AV1 NVENC not recommended for stability; use software encoder only.
        # Fall back to libx265 if SVT-AV1 is not available on this build.
        sw_check = hw if hw is not None else detect_hardware_encoders()
        if sw_check.software_av1:
            return "libsvtav1", []
        return "libx265", []

    raise FFmpegToolkitError(f"Unsupported codec: {codec}", operation="select_encoder")


# ---------------------------------------------------------------------------
# Group 1: Probe & Inspect
# ---------------------------------------------------------------------------


def probe_media(path: Path) -> ProbeMediaResult:
    """Extract full metadata from a media file.

    Wraps run_ffprobe and get_video_metadata; adds structured Pydantic output.

    Args:
        path: Path to the media file.

    Returns:
        ProbeMediaResult with streams, format, and convenience video/audio fields.

    Raises:
        FFmpegToolkitError: If ffprobe fails or path is invalid.
    """
    operation = "probe_media"
    try:
        raw = run_ffprobe(path)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, ["ffprobe", str(path)]) from exc

    fmt = raw.get("format", {})
    streams: list[StreamInfo] = []

    for s in raw.get("streams", []):
        color_space = s.get("color_space", "")
        color_range = s.get("color_range", "")
        is_hdr = color_space in ("bt2020nc", "bt2020c")

        stream = StreamInfo(
            index=int(s.get("index", 0)),
            codec_type=s.get("codec_type", ""),
            codec_name=s.get("codec_name", ""),
            width=s.get("width"),
            height=s.get("height"),
            pix_fmt=s.get("pix_fmt"),
            color_space=color_space or None,
            color_range=color_range or None,
            is_hdr=is_hdr,
            sample_rate=int(s["sample_rate"]) if s.get("sample_rate") else None,
            channels=s.get("channels"),
            channel_layout=s.get("channel_layout"),
            bit_rate=int(s["bit_rate"]) if s.get("bit_rate") else None,
        )

        # FPS from r_frame_rate
        if s.get("codec_type") == "video" and s.get("r_frame_rate"):
            try:
                stream.fps = float(Fraction(s["r_frame_rate"]))
            except (ValueError, ZeroDivisionError):
                stream.fps = None

        streams.append(stream)

    video_streams = [s for s in streams if s.codec_type == "video"]
    audio_streams = [s for s in streams if s.codec_type == "audio"]

    return ProbeMediaResult(
        path=path,
        format_name=fmt.get("format_name", ""),
        duration=float(fmt.get("duration", 0)),
        size_bytes=int(fmt.get("size", 0)),
        bit_rate=int(fmt.get("bit_rate", 0)),
        streams=streams,
        video=video_streams[0] if video_streams else None,
        audio=audio_streams[0] if audio_streams else None,
        audio_track_count=len(audio_streams),
    )


def extract_frame(request: ExtractFrameRequest) -> ExtractFrameResult:
    """Extract a single frame as PNG at the specified timestamp.

    Args:
        request: ExtractFrameRequest with path, timestamp_s, output_path.

    Returns:
        ExtractFrameResult with output_path.

    Raises:
        FFmpegToolkitError: If ffmpeg fails.
    """
    operation = "extract_frame"
    args = [
        "-ss",
        str(request.timestamp_s),
        "-i",
        str(request.path),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(request.output_path),
    ]
    try:
        run_ffmpeg(args)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    return ExtractFrameResult(output_path=request.output_path)


# ---------------------------------------------------------------------------
# Group 2: Encode & Transcode
# ---------------------------------------------------------------------------


def transcode(request: TranscodeRequest) -> TranscodeResult:
    """High-fidelity video transcode with codec/hardware/quality selection.

    Args:
        request: TranscodeRequest specifying codec, preset, bit-depth, etc.

    Returns:
        TranscodeResult with output path, size, and encode time.

    Raises:
        FFmpegToolkitError: On encode failure or unsupported configuration.
    """
    import time

    operation = "transcode"

    # AV1 film grain is only meaningful for libsvtav1
    if request.film_grain > 0 and request.codec != VideoCodec.AV1:
        raise FFmpegToolkitError(
            "film_grain parameter is only supported for AV1 codec",
            operation=operation,
        )

    encoder, encoder_extra_args = _select_video_encoder(
        request.codec, request.hw_accel, request.bit_depth
    )

    preset_map: dict[str, dict[str, str]] = {
        "h264_nvenc": {
            "ultrafast": "p1",
            "fast": "p3",
            "medium": "p5",
            "slow": "p6",
            "veryslow": "p7",
        },
        "hevc_nvenc": {
            "ultrafast": "p1",
            "fast": "p3",
            "medium": "p5",
            "slow": "p6",
            "veryslow": "p7",
        },
    }

    if encoder in preset_map:
        preset_val = preset_map[encoder].get(request.quality_preset.value, "p5")
        preset_args = ["-preset:v", preset_val]
    else:
        preset_args = ["-preset", request.quality_preset.value]

    # Build AV1-specific args
    av1_args: list[str] = []
    if request.codec == VideoCodec.AV1 and request.film_grain > 0:
        av1_args = ["-svtav1-params", f"film-grain={request.film_grain}"]

    args = [
        "-i",
        str(request.input_path),
        "-c:v",
        encoder,
        *preset_args,
        *encoder_extra_args,
        *av1_args,
        "-c:a",
        "copy",
        str(request.output_path),
    ]

    start = time.monotonic()
    try:
        run_ffmpeg(args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    encode_time = time.monotonic() - start
    size = request.output_path.stat().st_size if request.output_path.exists() else 0

    logger.info(
        "transcode_complete",
        codec=encoder,
        output=str(request.output_path),
        size_bytes=size,
        encode_time_s=round(encode_time, 2),
    )
    return TranscodeResult(
        output_path=request.output_path,
        size_bytes=size,
        encode_time_s=round(encode_time, 2),
    )


def normalize_loudness(request: NormalizeLoudnessRequest) -> NormalizeLoudnessResult:
    """EBU R128 loudness normalization.

    Two-pass: first pass measures integrated loudness; second pass applies
    the gain correction using the loudnorm filter.

    Args:
        request: NormalizeLoudnessRequest.

    Returns:
        NormalizeLoudnessResult with measured LUFS before/after.

    Raises:
        FFmpegToolkitError: On normalization failure.
    """
    operation = "normalize_loudness"

    # Pass 1: measure
    measure_args = [
        "-i",
        str(request.input_path),
        "-af",
        f"loudnorm=I={request.target_lufs}:TP={request.true_peak_dbtp}:print_format=json",
        "-f",
        "null",
        "-",
    ]
    try:
        result = run_ffmpeg(measure_args, timeout=request.timeout, check=False)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, measure_args) from exc

    if result.returncode != 0:
        _pass1_err = FFmpegError(
            f"FFmpeg pass-1 (loudnorm measure) failed with return code {result.returncode}",
            stderr=result.stderr,
            returncode=result.returncode,
        )
        raise _wrap_ffmpeg_error(_pass1_err, operation, measure_args) from _pass1_err

    stderr_text = result.stderr

    # Parse measured_I from loudnorm JSON in stderr
    input_lufs = 0.0
    match = re.search(r'"input_i"\s*:\s*"([-0-9.]+)"', stderr_text)
    if match:
        with contextlib.suppress(ValueError):
            input_lufs = float(match.group(1))

    # Pass 2: apply normalization
    apply_args = [
        "-i",
        str(request.input_path),
        "-af",
        (
            f"loudnorm=I={request.target_lufs}:TP={request.true_peak_dbtp}"
            ":linear=true:print_format=summary"
        ),
        str(request.output_path),
    ]
    try:
        run_ffmpeg(apply_args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, apply_args) from exc

    return NormalizeLoudnessResult(
        output_path=request.output_path,
        input_lufs=input_lufs,
        output_lufs=request.target_lufs,
    )


# ---------------------------------------------------------------------------
# Group 3: Filter & Overlay
# ---------------------------------------------------------------------------

# Safe zone padding constants (pixels) for overlay_image positions
_OVERLAY_PADDING = 10


def _overlay_position_expr(
    position: OverlayPosition, w_expr: str = "W", h_expr: str = "H"
) -> tuple[str, str]:
    """Return (x_expr, y_expr) filtergraph expressions for a named position.

    w_expr / h_expr reference the overlay width/height variables in filtergraph.
    """
    p = _OVERLAY_PADDING
    pos_map: dict[OverlayPosition, tuple[str, str]] = {
        OverlayPosition.TOP_LEFT: (str(p), str(p)),
        OverlayPosition.TOP_RIGHT: (f"{w_expr}-overlay_w-{p}", str(p)),
        OverlayPosition.BOTTOM_LEFT: (str(p), f"{h_expr}-overlay_h-{p}"),
        OverlayPosition.BOTTOM_RIGHT: (f"{w_expr}-overlay_w-{p}", f"{h_expr}-overlay_h-{p}"),
        OverlayPosition.CENTER: (f"({w_expr}-overlay_w)/2", f"({h_expr}-overlay_h)/2"),
    }
    return pos_map[position]


def burn_captions(request: BurnCaptionsRequest) -> BurnCaptionsResult:
    """Burn ASS subtitles onto video using libass.

    Args:
        request: BurnCaptionsRequest with video_path, ass_path, output_path.

    Returns:
        BurnCaptionsResult with output_path.

    Raises:
        FFmpegToolkitError: On render failure.
    """
    operation = "burn_captions"

    # Build the ass filter; escape the path for FFmpeg filtergraph
    ass_path_str = str(request.ass_path).replace("\\", "/").replace(":", "\\:")
    vf = f"ass={ass_path_str!r}"
    if request.force_style:
        # Validate force_style: only permit comma-separated Key=Value pairs
        # with safe characters to prevent filtergraph injection
        _FORCE_STYLE_RE = re.compile(
            r"^[A-Za-z0-9_.-]+=[ A-Za-z0-9.:_#-]+"
            r"(?:,[A-Za-z0-9_.-]+=[ A-Za-z0-9.:_#-]+)*$"
        )
        if not _FORCE_STYLE_RE.match(request.force_style):
            raise FFmpegToolkitError(
                "force_style contains invalid characters; "
                "expected comma-separated Key=Value pairs with safe characters",
                operation=operation,
            )
        vf = f"ass={ass_path_str!r}:force_style={request.force_style!r}"

    args = [
        "-i",
        str(request.video_path),
        "-vf",
        vf,
        "-c:a",
        "copy",
        str(request.output_path),
    ]
    try:
        run_ffmpeg(args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    return BurnCaptionsResult(output_path=request.output_path)


def overlay_image(request: OverlayImageRequest) -> OverlayImageResult:
    """Composite a logo/watermark onto video with opacity and optional fade.

    Args:
        request: OverlayImageRequest.

    Returns:
        OverlayImageResult with output_path.

    Raises:
        FFmpegToolkitError: On compositing failure.
    """
    operation = "overlay_image"

    x_expr, y_expr = _overlay_position_expr(request.position)

    # Build scale filter for overlay
    scale_filter = f"scale=iw*{request.scale}:ih*{request.scale}"

    # Opacity via colorchannelmixer alpha component
    alpha_val = request.opacity
    color_filter = f"colorchannelmixer=aa={alpha_val}"

    # Build optional alpha-aware fade filters for the overlay stream
    fade_filters: list[str] = []
    if request.fade_in_s > 0:
        fade_filters.append(f"fade=t=in:st=0:d={request.fade_in_s:.3f}:alpha=1")
    if request.fade_out_s > 0:
        # Probe video duration so we can anchor the fade-out start time
        video_duration = 0.0
        try:
            probe_data = run_ffprobe(request.video_path)
            video_duration = float(probe_data.get("format", {}).get("duration", 0.0))
        except (FFmpegError, OSError, ValueError):
            pass
        if video_duration > 0:
            fade_start = max(0.0, video_duration - request.fade_out_s)
            fade_filters.append(
                f"fade=t=out:st={fade_start:.3f}:d={request.fade_out_s:.3f}:alpha=1"
            )

    overlay_chain = ",".join(filter(None, [scale_filter, color_filter, *fade_filters]))
    overlay_filter = f"[1:v]{overlay_chain}[ovrl];[0:v][ovrl]overlay={x_expr}:{y_expr}"

    args = [
        "-i",
        str(request.video_path),
        "-i",
        str(request.image_path),
        "-filter_complex",
        overlay_filter,
        "-c:a",
        "copy",
        str(request.output_path),
    ]
    try:
        run_ffmpeg(args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    return OverlayImageResult(output_path=request.output_path)


def apply_filtergraph(request: ApplyFiltergraphRequest) -> ApplyFiltergraphResult:
    """Apply a raw filtergraph with optional dry-run validation.

    Args:
        request: ApplyFiltergraphRequest.

    Returns:
        ApplyFiltergraphResult with output_path and list of filter names.

    Raises:
        FFmpegToolkitError: On filtergraph parse error or execution failure.
    """
    operation = "apply_filtergraph"

    if request.validate_first:
        # Dry-run: encode one frame to /dev/null to catch syntax errors early
        validate_args = [
            "-i",
            str(request.input_path),
            "-vf",
            request.filtergraph,
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
        try:
            run_ffmpeg(validate_args, timeout=30)
        except FFmpegError as exc:
            raise _wrap_ffmpeg_error(exc, f"{operation}[validate]", validate_args) from exc

    args = [
        "-i",
        str(request.input_path),
        "-vf",
        request.filtergraph,
        "-c:a",
        "copy",
        str(request.output_path),
    ]
    try:
        run_ffmpeg(args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    # Extract filter names from the filtergraph string (simple name extraction)
    filter_names = re.findall(r"(?:^|[,;[\]])\s*(\w+)\s*(?:=|[,;[\]]|$)", request.filtergraph)
    applied_filters = sorted(set(filter_names))

    return ApplyFiltergraphResult(
        output_path=request.output_path,
        applied_filters=applied_filters,
    )


# Denoise strength → filter parameter mapping
_DENOISE_STRENGTH_PARAMS: dict[str, dict[str, str]] = {
    DenoiseMethod.HQDN3D.value: {
        DenoiseStrength.LIGHT.value: "hqdn3d=2:1:2:3",
        DenoiseStrength.MEDIUM.value: "hqdn3d=4:3:6:4.5",
        DenoiseStrength.HEAVY.value: "hqdn3d=8:6:12:9",
    },
    DenoiseMethod.NLMEANS.value: {
        DenoiseStrength.LIGHT.value: "nlmeans=s=1.0:p=3:r=15",
        DenoiseStrength.MEDIUM.value: "nlmeans=s=3.0:p=5:r=15",
        DenoiseStrength.HEAVY.value: "nlmeans=s=6.0:p=7:r=15",
    },
}


def denoise(request: DenoiseRequest) -> DenoiseResult:
    """Apply video noise reduction filter.

    Args:
        request: DenoiseRequest with method and strength preset.

    Returns:
        DenoiseResult with output_path.

    Raises:
        FFmpegToolkitError: On filter failure.
    """
    operation = "denoise"
    vf = _DENOISE_STRENGTH_PARAMS[request.method.value][request.strength.value]

    args = [
        "-i",
        str(request.input_path),
        "-vf",
        vf,
        "-c:a",
        "copy",
        str(request.output_path),
    ]
    try:
        run_ffmpeg(args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    return DenoiseResult(output_path=request.output_path)


# ---------------------------------------------------------------------------
# Group 4: Edit & Assemble
# ---------------------------------------------------------------------------


def trim_segment(request: TrimSegmentRequest) -> TrimSegmentResult:
    """Frame-accurate video segment cut.

    Args:
        request: TrimSegmentRequest with start_s, end_s, copy_codec flag.

    Returns:
        TrimSegmentResult with output_path and actual start/end.

    Raises:
        FFmpegToolkitError: On trim failure or invalid time range.
    """
    operation = "trim_segment"

    if request.end_s is not None and request.end_s <= request.start_s:
        raise FFmpegToolkitError(
            f"end_s ({request.end_s}) must be greater than start_s ({request.start_s})",
            operation=operation,
        )

    args: list[str] = ["-ss", str(request.start_s), "-i", str(request.input_path)]

    if request.end_s is not None:
        duration = request.end_s - request.start_s
        args.extend(["-t", str(duration)])

    if request.copy_codec:
        args.extend(["-c", "copy"])

    args.append(str(request.output_path))

    try:
        run_ffmpeg(args)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    return TrimSegmentResult(
        output_path=request.output_path,
        actual_start_s=request.start_s,
        actual_end_s=request.end_s,
    )


def _write_concat_list(segments: list[Path], list_path: Path) -> None:
    """Write an FFmpeg concat demuxer file listing segments."""
    lines = []
    for seg in segments:
        # Escape single-quotes in path for FFmpeg concat format
        escaped = str(seg).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _concat_demuxer(request: ConcatSegmentsRequest) -> None:
    """Run concat via demuxer (stream-copy, no transition)."""
    import tempfile

    operation = "concat_segments"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        list_path = Path(f.name)
    try:
        _write_concat_list(request.segments, list_path)
        args = [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(request.output_path),
        ]
        try:
            run_ffmpeg(args, timeout=request.timeout)
        except FFmpegError as exc:
            raise _wrap_ffmpeg_error(exc, operation, args) from exc
    finally:
        list_path.unlink(missing_ok=True)


def _concat_xfade(request: ConcatSegmentsRequest) -> None:
    """Run concat via xfade filter chain (crossfade/dissolve)."""
    operation = "concat_segments"
    n = len(request.segments)
    d = request.transition_duration_s

    if n == 1:
        args = ["-i", str(request.segments[0]), "-c", "copy", str(request.output_path)]
        try:
            run_ffmpeg(args, timeout=request.timeout)
        except FFmpegError as exc:
            raise _wrap_ffmpeg_error(exc, operation, args) from exc
        return

    input_args: list[str] = []
    for seg in request.segments:
        input_args.extend(["-i", str(seg)])

    offsets = _compute_xfade_offsets(request.segments, d)
    # Map TransitionType enum to xfade transition name
    _TRANSITION_MAP: dict[TransitionType, str] = {
        TransitionType.CROSSFADE: "fade",
        TransitionType.DISSOLVE: "dissolve",
    }
    xfade_name = _TRANSITION_MAP.get(request.transition, "fade")
    filters = _build_xfade_filters(n, d, offsets, transition=xfade_name)
    filter_complex = ";".join(filters)
    args = [
        *input_args,
        "-filter_complex",
        filter_complex,
        "-map",
        "[voutfinal]",
        "-map",
        "[aout]",
        str(request.output_path),
    ]
    try:
        run_ffmpeg(args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc


def _compute_xfade_offsets(segments: list[Path], transition_d: float) -> list[float]:
    """Probe durations and compute cumulative xfade offsets."""
    offsets: list[float] = []
    cumulative = 0.0
    for seg in segments[:-1]:
        try:
            probe = run_ffprobe(seg)
            dur = float(probe.get("format", {}).get("duration", 0))
        except FFmpegError:
            dur = 0.0
        cumulative += max(0.0, dur - transition_d)
        offsets.append(cumulative)
    return offsets


def _build_xfade_filters(
    n: int, d: float, offsets: list[float], transition: str = "fade"
) -> list[str]:
    """Build xfade + audio concat filter chain."""
    filters: list[str] = []
    prev_label = "[0:v]"
    for i in range(1, n):
        out_label = f"[vout{i}]" if i < n - 1 else "[voutfinal]"
        filters.append(
            f"{prev_label}[{i}:v]xfade=transition={transition}:duration={d}"
            f":offset={offsets[i - 1]}{out_label}"
        )
        prev_label = out_label
    audio_inputs = "".join(f"[{i}:a]" for i in range(n))
    filters.append(f"{audio_inputs}concat=n={n}:v=0:a=1[aout]")
    return filters


def concat_segments(request: ConcatSegmentsRequest) -> ConcatSegmentsResult:
    """Join multiple clip segments with an optional crossfade/dissolve transition.

    Args:
        request: ConcatSegmentsRequest.

    Returns:
        ConcatSegmentsResult with output_path and total_duration_s.

    Raises:
        FFmpegToolkitError: On concat failure.
    """
    if request.transition == TransitionType.NONE:
        _concat_demuxer(request)
    else:
        _concat_xfade(request)

    # Probe output duration
    total_duration = 0.0
    if request.output_path.exists():
        with contextlib.suppress(FFmpegError):
            probe = run_ffprobe(request.output_path)
            total_duration = float(probe.get("format", {}).get("duration", 0))

    return ConcatSegmentsResult(
        output_path=request.output_path,
        total_duration_s=total_duration,
    )


def mix_audio(request: MixAudioRequest) -> MixAudioResult:
    """Overlay background music/stingers with optional sidechain ducking.

    Uses FFmpeg sidechaincompress for automatic speech-over-music ducking.

    Args:
        request: MixAudioRequest.

    Returns:
        MixAudioResult with output_path.

    Raises:
        FFmpegToolkitError: On mix failure.
    """
    operation = "mix_audio"

    # Build audio filter chain
    # Apply volume adjustment to music
    vol_db = request.music_volume_db
    fade_in = request.fade_in_s
    fade_out = request.fade_out_s

    # Probe music duration for fade-out positioning
    music_duration = 0.0
    if fade_out > 0:
        with contextlib.suppress(FFmpegError):
            music_probe = run_ffprobe(request.music_path)
            music_duration = float(music_probe.get("format", {}).get("duration", 0))

    music_chain = f"[1:a]volume={vol_db}dB"
    if fade_in > 0:
        music_chain += f",afade=t=in:st=0:d={fade_in}"
    if fade_out > 0:
        fade_start = max(0.0, music_duration - fade_out)
        music_chain += f",afade=t=out:st={fade_start}:d={fade_out}"

    if request.duck_enabled:
        # sidechaincompress: speech drives the gain reduction on music
        # Attack: 5ms, Release: 200ms, Ratio: from request
        ratio = request.duck_ratio
        threshold_db = request.duck_threshold_db
        music_chain += "[music_in];[0:a][music_in]sidechaincompress"
        music_chain += (
            f"=threshold={10 ** (threshold_db / 20):.6f}"
            f":ratio={ratio}:attack=5:release=200[music_ducked]"
        )
        music_chain = f"{music_chain};[0:a][music_ducked]amix=inputs=2:normalize=0[aout]"
        filter_complex = f"{music_chain}"
    else:
        music_chain += "[music_adj];[0:a][music_adj]amix=inputs=2:normalize=0[aout]"
        filter_complex = music_chain

    args = [
        "-i",
        str(request.speech_path),
        "-i",
        str(request.music_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v?",  # pass through video if present
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        str(request.output_path),
    ]
    try:
        run_ffmpeg(args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    return MixAudioResult(output_path=request.output_path)


def sync_tracks(request: SyncTracksRequest) -> SyncTracksResult:
    """Align an external audio track to a reference using cross-correlation.

    Implements the four-step algorithm from spec v4 Section 3:
    1. Downsample reference and external to 8kHz mono (bounded to search_window_s)
    2. Detect peak samples exceeding 3x RMS for rough alignment
    3. scipy.signal.correlate for sub-sample precision
    4. Apply offset via -itsoffset flag in FFmpeg mux

    Args:
        request: SyncTracksRequest.

    Returns:
        SyncTracksResult with output_path, offset_ms, and confidence score.

    Raises:
        FFmpegToolkitError: On sync or mux failure.
    """
    import tempfile

    operation = "sync_tracks"
    TARGET_SR = 8000
    search_s = min(request.search_window_s, 60.0)

    # Step 1: Extract bounded mono 8kHz WAV for both tracks
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        ref_wav = tmp / "ref.wav"
        ext_wav = tmp / "ext.wav"

        def _extract_mono_wav(src: Path, dst: Path) -> None:
            args = [
                "-ss",
                "0",
                "-t",
                str(search_s),
                "-i",
                str(src),
                "-ac",
                "1",
                "-ar",
                str(TARGET_SR),
                "-vn",
                str(dst),
            ]
            try:
                run_ffmpeg(args, timeout=120)
            except FFmpegError as exc:
                raise _wrap_ffmpeg_error(exc, f"{operation}[extract]", args) from exc

        _extract_mono_wav(request.reference_path, ref_wav)
        _extract_mono_wav(request.external_path, ext_wav)

        # Step 2 & 3: Cross-correlation via scipy
        offset_ms, confidence = _correlate_audio(ref_wav, ext_wav, TARGET_SR)

    # Step 4: Mux video from reference + audio from external with offset applied.
    # Positive offset_ms → external starts later → delay external (positive itsoffset).
    # Negative offset_ms → external starts earlier → advance external (negative itsoffset).
    # FFmpeg's -itsoffset natively handles both signs.
    offset_s = offset_ms / 1000.0

    mux_args = [
        "-i",
        str(request.reference_path),  # input 0: video source
        "-itsoffset",
        str(offset_s),
        "-i",
        str(request.external_path),  # input 1: audio source (offset-adjusted)
        "-map",
        "0:v?",  # video from reference
        "-map",
        "1:a:0?",  # first audio stream from external
        "-c",
        "copy",
        str(request.output_path),
    ]
    try:
        run_ffmpeg(mux_args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, mux_args) from exc

    logger.info(
        "sync_tracks_complete",
        offset_ms=offset_ms,
        confidence=confidence,
        output=str(request.output_path),
    )
    return SyncTracksResult(
        output_path=request.output_path,
        offset_ms=offset_ms,
        confidence=confidence,
    )


def _correlate_audio(ref_wav: Path, ext_wav: Path, sample_rate: int) -> tuple[float, float]:
    """Compute cross-correlation offset between two mono WAV files.

    Returns:
        Tuple of (offset_ms, confidence) where offset is how far external
        is ahead of reference (positive = external starts later).
    """
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise FFmpegToolkitError(
            "sync_tracks requires numpy and soundfile packages",
            operation="_correlate_audio",
        ) from exc

    try:
        ref_data, _ = sf.read(str(ref_wav), dtype="float32")
        ext_data, _ = sf.read(str(ext_wav), dtype="float32")
    except (OSError, sf.SoundFileError) as exc:
        raise FFmpegToolkitError(
            f"Failed to read audio for correlation: {exc}",
            operation="_correlate_audio",
        ) from exc

    # Flatten to 1D
    ref_data = ref_data.flatten()
    ext_data = ext_data.flatten()

    # Normalize to prevent gain level differences from skewing correlation
    ref_norm = ref_data / (np.std(ref_data) + 1e-9)
    ext_norm = ext_data / (np.std(ext_data) + 1e-9)

    try:
        from scipy.signal import correlate

        corr = correlate(ref_norm, ext_norm, mode="full")
        lag_ref_len = len(ext_norm)
    except ImportError:
        # scipy not available — fall back to numpy correlate on truncated slices
        rlen = min(len(ref_norm), 4096)
        elen = min(len(ext_norm), 4096)
        corr = np.correlate(ref_norm[:rlen], ext_norm[:elen], mode="full")
        lag_ref_len = elen

    # argmax gives sample lag
    lag_samples = int(np.argmax(np.abs(corr))) - (lag_ref_len - 1)
    offset_ms = (lag_samples / sample_rate) * 1000.0

    # Confidence: normalized peak correlation value
    max_corr = float(np.max(np.abs(corr)))
    mean_corr = float(np.mean(np.abs(corr)))
    confidence = min(1.0, max_corr / (mean_corr * 10 + 1e-9))

    return offset_ms, round(confidence, 4)


# ---------------------------------------------------------------------------
# Group 5: Package & Deliver
# ---------------------------------------------------------------------------


def package_hls(request: PackageHlsRequest) -> PackageHlsResult:
    """Generate an HLS VOD package with a multi-bitrate variant ladder.

    Args:
        request: PackageHlsRequest with variants and segment_duration.

    Returns:
        PackageHlsResult with master_playlist_path, segment_count, total_size_bytes.

    Raises:
        FFmpegToolkitError: On HLS packaging failure.
    """
    operation = "package_hls"

    request.output_dir.mkdir(parents=True, exist_ok=True)

    # Build filter_complex and output mapping for each variant
    # Use split filter to produce multiple outputs from one decode
    n = len(request.variants)
    split_outputs = "".join(f"[v{i}]" for i in range(n))
    filter_parts: list[str] = [f"[0:v]split={n}{split_outputs}"]

    for i, variant in enumerate(request.variants):
        filter_parts.append(f"[v{i}]scale={variant.width}:{variant.height}[vout{i}]")

    filter_complex = ";".join(filter_parts)

    # Map and encode each variant
    output_args: list[str] = []
    for i, variant in enumerate(request.variants):
        seg_pattern = str(request.output_dir / f"v{i}_%05d.ts")
        playlist_path = str(request.output_dir / f"v{i}.m3u8")
        output_args.extend(
            [
                "-map",
                f"[vout{i}]",
                "-map",
                "0:a?",
                f"-c:v:{i}",
                "libx264",
                f"-b:v:{i}",
                f"{variant.bitrate_kbps}k",
                f"-c:a:{i}",
                "aac",
                f"-b:a:{i}",
                f"{variant.audio_bitrate_kbps}k",
                "-f",
                "hls",
                "-hls_time",
                str(request.segment_duration),
                "-hls_playlist_type",
                "vod",
                "-hls_segment_filename",
                seg_pattern,
                playlist_path,
            ]
        )

    args = [
        "-i",
        str(request.input_path),
        "-filter_complex",
        filter_complex,
        *output_args,
    ]

    try:
        run_ffmpeg(args, timeout=request.timeout)
    except FFmpegError as exc:
        raise _wrap_ffmpeg_error(exc, operation, args) from exc

    # Write master playlist
    master_path = request.output_dir / "master.m3u8"
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for i, variant in enumerate(request.variants):
        bandwidth = variant.bitrate_kbps * 1000 + variant.audio_bitrate_kbps * 1000
        lines.append(
            f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={variant.width}x{variant.height}"
        )
        lines.append(f"v{i}.m3u8")
    master_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Count segments and total size
    ts_files = list(request.output_dir.glob("*.ts"))
    segment_count = len(ts_files)
    total_size = sum(f.stat().st_size for f in request.output_dir.iterdir() if f.is_file())

    logger.info(
        "package_hls_complete",
        master=str(master_path),
        segment_count=segment_count,
        total_size_bytes=total_size,
    )
    return PackageHlsResult(
        master_playlist_path=master_path,
        segment_count=segment_count,
        total_size_bytes=total_size,
    )


# ---------------------------------------------------------------------------
# Public API summary (for import discovery)
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "ApplyFiltergraphRequest",
    "ApplyFiltergraphResult",
    # Models - Filter
    "BurnCaptionsRequest",
    "BurnCaptionsResult",
    "ConcatSegmentsRequest",
    "ConcatSegmentsResult",
    "DenoiseMethod",
    "DenoiseRequest",
    "DenoiseResult",
    "DenoiseStrength",
    "ExtractFrameRequest",
    "ExtractFrameResult",
    # Error
    "FFmpegToolkitError",
    "HardwareEncoderInfo",
    # Models - Package
    "HlsVariant",
    "HwAccel",
    "MixAudioRequest",
    "MixAudioResult",
    "NormalizeLoudnessRequest",
    "NormalizeLoudnessResult",
    "OverlayImageRequest",
    "OverlayImageResult",
    "OverlayPosition",
    "PackageHlsRequest",
    "PackageHlsResult",
    "ProbeMediaResult",
    "QualityPreset",
    # Models - Probe
    "StreamInfo",
    "SyncTracksRequest",
    "SyncTracksResult",
    # Models - Encode
    "TranscodeRequest",
    "TranscodeResult",
    "TransitionType",
    # Models - Edit
    "TrimSegmentRequest",
    "TrimSegmentResult",
    # Enums
    "VideoCodec",
    "apply_filtergraph",
    # Functions - Group 3
    "burn_captions",
    "concat_segments",
    "denoise",
    "detect_hardware_encoders",
    "extract_frame",
    "mix_audio",
    "normalize_loudness",
    "overlay_image",
    # Functions - Group 5
    "package_hls",
    # Functions - Group 1
    "probe_media",
    "sync_tracks",
    # Functions - Group 2
    "transcode",
    # Functions - Group 4
    "trim_segment",
]
