"""Configuration settings with Pydantic models."""

import ipaddress
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Self

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_MODEL_PROVIDERS = {"gemini", "kimi", "claude"}
SUPPORTED_GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-latest",
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gemini-2.5-pro",
}
SUPPORTED_KIMI_MODELS = {
    "kimi-k2.5",
    "moonshot-v1-128k",
}
SUPPORTED_CLAUDE_MODELS = {
    "claude-sonnet-4-6",  # Best cost/performance (RECOMMENDED)
    "claude-haiku-4-5",  # Fast, cheaper
    "claude-opus-4-6",  # Most intelligent, highest cost
}
SUPPORTED_MODELS_BY_PROVIDER = {
    "gemini": SUPPORTED_GEMINI_MODELS,
    "kimi": SUPPORTED_KIMI_MODELS,
    "claude": SUPPORTED_CLAUDE_MODELS,
}

SERVICE_HOST_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")
VIDEO_LEVEL_PATTERN = re.compile(r"^(?:[1-6](?:\.[0-2])?|1\.3)$")
H264_CODECS = {"h264", "libx264", "h264_nvenc"}
H265_CODECS = {"h265", "hevc", "libx265", "hevc_nvenc"}
AV1_CODECS = {"av1", "libsvtav1"}
CODECS_WITH_PROFILE_LEVEL = H264_CODECS | H265_CODECS
H264_PROFILES = {"baseline", "main", "high", "high10", "high422", "high444"}
H265_PROFILES = {"main", "main10", "mainstillpicture"}
# NVENC uses p010le for 10-bit HEVC; libx265 uses yuv420p10le
PIX_FMT_BY_CODEC = {
    "h264": {"yuv420p", "yuv422p", "yuv444p"},
    "libx264": {"yuv420p", "yuv422p", "yuv444p"},
    "h264_nvenc": {"yuv420p", "yuv422p", "yuv444p"},
    "h265": {"yuv420p", "yuv420p10le", "yuv422p10le", "yuv444p10le"},
    "hevc": {"yuv420p", "yuv420p10le", "yuv422p10le", "yuv444p10le"},
    "libx265": {"yuv420p", "yuv420p10le", "yuv422p10le", "yuv444p10le"},
    "hevc_nvenc": {"yuv420p", "p010le"},
    "av1": {"yuv420p", "yuv420p10le"},
    "libsvtav1": {"yuv420p", "yuv420p10le"},
}
# Short-form vertical aspect ratios eligible for RIFE 60fps uplift
SHORT_FORM_ASPECT_RATIOS = {"9:16"}
THUMBNAIL_FORMATS = {"jpg", "jpeg", "png", "webp"}


class PathsConfig(BaseModel):
    """Path configuration."""

    jobs_dir: Path = Path("./jobs")
    models_cache: Path = Path("./models")


class ModelConfig(BaseModel):
    """AI model configuration.

    Supported Gemini models (as of Feb 2026):
    - gemini-2.5-flash-latest: Best balance of cost/performance for video (RECOMMENDED)
    - gemini-3-flash: Latest model with Agentic Vision
    - gemini-3-pro: Most intelligent model
    - gemini-2.5-pro: Excellent video understanding, 2M context

    NOTE: gemini-2.0-flash is RETIRING on March 3, 2026!

    Supported Kimi models:
    - kimi-k2.5: Latest multimodal model (RECOMMENDED)
    - moonshot-v1-128k: Legacy model (for backward compatibility)
    """

    provider: str = "gemini"
    model: str = "gemini-2.5-flash"  # Best cost/performance for video
    fallback_provider: str | None = "kimi"
    fallback_model: str | None = "kimi-k2.5"  # Latest Kimi multimodal model

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        """Ensure provider is supported."""
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_MODEL_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_MODEL_PROVIDERS))
            raise ValueError(f"Unsupported provider '{value}'. Expected one of: {allowed}")
        return normalized

    @field_validator("fallback_provider")
    @classmethod
    def validate_fallback_provider(cls, value: str | None) -> str | None:
        """Ensure fallback provider is supported when configured."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_MODEL_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_MODEL_PROVIDERS))
            raise ValueError(f"Unsupported fallback_provider '{value}'. Expected one of: {allowed}")
        return normalized

    @model_validator(mode="after")
    def validate_model_compatibility(self) -> Self:
        """Ensure model/fallback selections are compatible with configured providers."""
        supported_primary = SUPPORTED_MODELS_BY_PROVIDER[self.provider]
        if self.model not in supported_primary:
            allowed = ", ".join(sorted(supported_primary))
            raise ValueError(
                f"Model '{self.model}' is not supported for provider '{self.provider}'. "
                f"Expected one of: {allowed}"
            )

        if self.fallback_provider is None:
            if self.fallback_model is not None:
                raise ValueError("fallback_model requires fallback_provider to be configured")
            return self

        if self.fallback_model is None:
            raise ValueError("fallback_provider requires fallback_model to be configured")

        supported_fallback = SUPPORTED_MODELS_BY_PROVIDER[self.fallback_provider]
        if self.fallback_model not in supported_fallback:
            allowed = ", ".join(sorted(supported_fallback))
            raise ValueError(
                f"Fallback model '{self.fallback_model}' is not supported for provider "
                f"'{self.fallback_provider}'. Expected one of: {allowed}"
            )

        return self


class TranscriptionConfig(BaseModel):
    """Transcription model configuration."""

    provider: str = "whisper"
    model: str = "large-v3"
    device: str = "cuda"  # or "cpu"
    compute_type: str = "float16"  # or "int8" for lower memory


class FillerConfig(BaseModel):
    """Filler word detection and triage configuration."""

    # Categorised word lists (Phase 8)
    disfluencies: list[str] = Field(default_factory=lambda: ["um", "uh", "hmm", "er", "ah"])
    hedge_words: list[str] = Field(
        default_factory=lambda: ["like", "you know", "basically", "actually", "so"]
    )
    custom_words: list[str] = Field(default_factory=list)

    # Backward-compat flat list — treated as extra disfluencies when present
    words: list[str] = Field(default_factory=list)

    # Existing detection thresholds (unchanged)
    min_confidence: float = 0.5
    min_duration_ms: int = 150
    padding_ms: int = 50

    # Phase 8: Pause-based protection gate
    protect_pause_threshold_ms: float = Field(default=300.0, ge=0.0)

    # Phase 8: LLM semantic triage (hedge words only)
    enable_llm_triage: bool = True
    llm_triage_model: str = "gemini-2.5-flash-lite"
    llm_triage_max_context_words: int = 5

    @field_validator("llm_triage_model")
    @classmethod
    def reject_reasoning_models(cls, v: str) -> str:
        """Reject known reasoning/CoT models — too slow and expensive for per-filler triage."""
        forbidden_prefixes = ("o1", "o3", "gemini-3-pro", "gemini-pro-thinking")
        lowered = v.lower()
        for prefix in forbidden_prefixes:
            if lowered.startswith(prefix):
                raise ValueError(
                    f"llm_triage_model '{v}' is a reasoning/CoT model and is forbidden "
                    f"for filler triage (too slow and expensive). "
                    f"Use 'gemini-2.5-flash-lite' instead."
                )
        return v


class AudioConfig(BaseModel):
    """Audio processing configuration."""

    target_loudness: dict[str, float] = Field(
        default_factory=lambda: {
            "youtube": -14.0,
            "spotify": -16.0,
            "apple": -16.0,
            "tiktok": -14.0,
        }
    )
    noise_reduction: str = "auto"  # auto, off, or threshold value
    sample_rate: int = 44100


class DeesserConfig(BaseModel):
    """Typed de-esser and click-safety settings."""

    enabled: bool = True
    intensity: float = Field(default=0.2, ge=0.0, le=1.0)
    max_deessing: float = Field(default=0.5, ge=0.0, le=1.0)
    frequency: float = Field(default=0.5, ge=0.0, le=1.0)
    output_mode: str = "o"
    click_safety_enabled: bool = True
    adeclick_window: float = Field(default=55.0, ge=10.0, le=100.0)
    adeclick_overlap: float = Field(default=75.0, ge=50.0, le=95.0)
    adeclick_arorder: float = Field(default=2.0, ge=0.0, le=25.0)
    adeclick_threshold: float = Field(default=2.0, ge=1.0, le=100.0)
    adeclick_burst: float = Field(default=2.0, ge=0.0, le=10.0)
    adeclick_method: str = "a"

    @field_validator("output_mode")
    @classmethod
    def validate_output_mode(cls, value: str) -> str:
        """Restrict deesser output mode to FFmpeg-supported values."""
        normalized = value.strip().lower()
        if normalized not in {"i", "o", "e"}:
            raise ValueError("output_mode must be one of: i, o, e")
        return normalized

    @field_validator("adeclick_method")
    @classmethod
    def validate_adeclick_method(cls, value: str) -> str:
        """Restrict adeclick overlap method to FFmpeg-supported values."""
        normalized = value.strip().lower()
        if normalized not in {"a", "add", "s", "save"}:
            raise ValueError("adeclick_method must be one of: a, add, s, save")
        return normalized


class DereverbConfig(BaseModel):
    """Optional lightweight dereverb preprocessing settings."""

    enabled: bool = False
    prop_decrease: float = Field(default=0.85, ge=0.0, le=1.0)
    stationary: bool = False
    fallback_mode: str = "warn_skip"

    @field_validator("fallback_mode")
    @classmethod
    def validate_fallback_mode(cls, value: str) -> str:
        """Control behavior when optional dependencies are unavailable."""
        normalized = value.strip().lower()
        if normalized not in {"warn_skip", "fail"}:
            raise ValueError("fallback_mode must be one of: warn_skip, fail")
        return normalized


class ColorCorrectionConfig(BaseModel):
    """Optional video color correction settings using canonical FFmpeg filters."""

    enabled: bool = False
    normalize_enabled: bool = True
    normalize_strength: float = Field(default=1.0, ge=0.0, le=1.0)
    grayworld_enabled: bool = True
    eq_enabled: bool = False
    eq_saturation: float = Field(default=1.0, ge=0.5, le=3.0)
    eq_contrast: float = Field(default=1.0, ge=0.5, le=2.0)
    eq_brightness: float = Field(default=0.0, ge=-0.2, le=0.2)
    eq_gamma: float = Field(default=1.0, ge=0.1, le=10.0)


class EnhancementsConfig(BaseModel):
    """Phase 6 enhancement feature flags and tuning."""

    deesser: DeesserConfig = Field(default_factory=DeesserConfig)
    dereverb: DereverbConfig = Field(default_factory=DereverbConfig)
    color_correction: ColorCorrectionConfig = Field(default_factory=ColorCorrectionConfig)


class SmoothingConfig(BaseModel):
    """Phase 7 transition smoothing and cut-boundary snapping policy."""

    enabled: bool = True
    micro_fade_ms: float = Field(default=30.0, ge=0.0, le=250.0)
    content_audio_crossfade_ms: float = Field(default=150.0, ge=0.0, le=1200.0)
    content_video_dissolve_ms: float = Field(default=300.0, ge=0.0, le=2000.0)
    max_snap_shift_ms: float = Field(default=250.0, ge=0.0, le=1000.0)
    join_clamp_ratio: float = Field(default=0.35, gt=0.0, le=0.5)
    require_transition_filters: bool = False

    # Phase 8: De-breathing at cut boundaries
    de_breathing_enabled: bool = True
    de_breathing_window_ms: float = Field(default=200.0, ge=0.0, le=500.0)
    de_breathing_max_extend_ms: float = Field(default=150.0, ge=0.0, le=300.0)

    # Phase 8: Noise-floor matching across joins
    noise_floor_match_enabled: bool = True
    noise_floor_match_threshold_db: float = Field(default=3.0, ge=0.0, le=20.0)
    noise_floor_match_ramp_ms: float = Field(default=50.0, ge=0.0, le=200.0)

    # Phase 8: Pose matching for optimal cut-point frame selection
    pose_match_enabled: bool = True
    pose_match_search_window_ms: float = Field(default=200.0, ge=0.0, le=500.0)
    pose_match_rife_threshold: float = Field(default=2.5, gt=0.0)

    # Phase 8: RIFE AI frame interpolation (disabled by default — requires manual RIFE setup)
    rife_enabled: bool = False
    rife_num_bridge_frames: int = Field(default=4, ge=1, le=16)
    rife_script_path: str = ""
    rife_fallback_to_xfade: bool = True

    # Phase 9: Explicit 30→60fps RIFE uplift for short-form vertical exports.
    # When True, applies RIFE 60fps interpolation ONLY to TikTok/Reels/Shorts targets
    # (aspect_ratio="9:16").  Long-form exports are never affected regardless of this flag.
    # Requires rife_enabled=True and a valid rife_script_path to have any effect.
    force_60fps_shortform: bool = False


class HLSConfig(BaseModel):
    """Typed HLS muxer configuration for provider hand-off artifacts."""

    segment_duration: int = Field(default=6, ge=1, le=30)
    playlist_type: str = "vod"
    master_playlist_name: str = "master.m3u8"
    variant_playlist_pattern: str = "variant_%v.m3u8"
    segment_filename_pattern: str = "segment_%v_%03d.ts"
    var_stream_map: str = "v:0,a:0"

    @staticmethod
    def _validate_safe_filename(value: str, field_name: str) -> str:
        """Restrict HLS artifact names to simple, relative filenames."""
        name = value.strip()
        if not name:
            raise ValueError(f"{field_name} cannot be empty")

        posix = PurePosixPath(name)
        windows = PureWindowsPath(name)
        if posix.is_absolute() or windows.is_absolute() or windows.drive:
            raise ValueError(f"{field_name} must be a relative filename")
        if "/" in name or "\\" in name or len(posix.parts) != 1:
            raise ValueError(f"{field_name} must not include directory separators")
        if any(part in {".", ".."} for part in posix.parts):
            raise ValueError(f"{field_name} must not include '.' or '..' segments")
        return name

    @field_validator("playlist_type")
    @classmethod
    def validate_playlist_type(cls, value: str) -> str:
        """Restrict playlist type to FFmpeg HLS muxer-safe values."""
        normalized = value.strip().lower()
        if normalized not in {"vod", "event"}:
            raise ValueError("playlist_type must be one of: vod, event")
        return normalized

    @field_validator("variant_playlist_pattern")
    @classmethod
    def validate_variant_pattern(cls, value: str) -> str:
        """Ensure variant pattern can generate indexed playlists."""
        pattern = cls._validate_safe_filename(value, "variant_playlist_pattern")
        if "%v" not in pattern:
            raise ValueError("variant_playlist_pattern must include '%v'")
        if not pattern.endswith(".m3u8"):
            raise ValueError("variant_playlist_pattern must end with '.m3u8'")
        return pattern

    @field_validator("master_playlist_name")
    @classmethod
    def validate_master_name(cls, value: str) -> str:
        """Ensure master playlist naming remains deterministic."""
        name = cls._validate_safe_filename(value, "master_playlist_name")
        if not name.endswith(".m3u8"):
            raise ValueError("master_playlist_name must end with '.m3u8'")
        return name

    @field_validator("segment_filename_pattern")
    @classmethod
    def validate_segment_pattern(cls, value: str) -> str:
        """Ensure segment pattern supports deterministic stream/segment naming."""
        pattern = cls._validate_safe_filename(value, "segment_filename_pattern")
        if "%v" not in pattern or "%03d" not in pattern:
            raise ValueError("segment_filename_pattern must include '%v' and '%03d' placeholders")
        if not pattern.endswith(".ts"):
            raise ValueError("segment_filename_pattern must end with '.ts'")
        return pattern


class ThumbnailTargetSpec(BaseModel):
    """Per-platform thumbnail compliance constraints."""

    width: int = Field(default=1280, ge=64)
    height: int = Field(default=720, ge=64)
    aspect_ratio: str = "16:9"
    formats: list[str] = Field(default_factory=lambda: ["jpg", "png"])
    max_size_bytes: int = Field(default=2 * 1024 * 1024, ge=16 * 1024)
    source: str = "official"
    notes: str = ""

    @field_validator("formats", mode="before")
    @classmethod
    def normalize_formats(cls, value: Any) -> list[str]:
        """Normalize and validate configured image formats."""
        raw_formats: list[Any]
        if isinstance(value, str):
            raw_formats = [part.strip() for part in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            raw_formats = list(value)
        else:
            raw_formats = []

        normalized: list[str] = []
        for item in raw_formats:
            text = str(item).strip().lower()
            if not text:
                continue
            if text not in THUMBNAIL_FORMATS:
                allowed = ", ".join(sorted(THUMBNAIL_FORMATS))
                raise ValueError(
                    f"Unsupported thumbnail format '{text}'. Expected one of: {allowed}"
                )
            if text not in normalized:
                normalized.append(text)

        if not normalized:
            raise ValueError("Thumbnail formats must include at least one value")
        return normalized

    @model_validator(mode="after")
    def validate_aspect_ratio(self) -> Self:
        """Ensure declared aspect ratio aligns with configured width/height."""
        ratio = self.aspect_ratio.strip()
        match = re.fullmatch(r"(\d+)\s*:\s*(\d+)", ratio)
        if not match:
            raise ValueError("aspect_ratio must use '<width>:<height>' format (for example, 16:9)")

        ratio_w = int(match.group(1))
        ratio_h = int(match.group(2))
        if ratio_w <= 0 or ratio_h <= 0:
            raise ValueError("aspect_ratio values must be positive integers")

        expected = ratio_w / ratio_h
        actual = self.width / self.height
        if abs(expected - actual) > 0.02:
            raise ValueError(
                "aspect_ratio does not match width/height "
                f"(aspect={self.aspect_ratio}, width={self.width}, height={self.height})"
            )
        return self


class ThumbnailSpecs(BaseModel):
    """Thumbnail constraints for selected export targets."""

    youtube: ThumbnailTargetSpec = Field(
        default_factory=lambda: ThumbnailTargetSpec(
            width=1280,
            height=720,
            aspect_ratio="16:9",
            formats=["jpg", "png"],
            max_size_bytes=2 * 1024 * 1024,
            source="official",
            notes="YouTube custom thumbnail guideline baseline.",
        )
    )
    spotify_video: ThumbnailTargetSpec = Field(
        default_factory=lambda: ThumbnailTargetSpec(
            width=1280,
            height=720,
            aspect_ratio="16:9",
            formats=["jpg", "png"],
            max_size_bytes=2 * 1024 * 1024,
            source="project_policy",
            notes=(
                "Spotify does not publish strict video-episode thumbnail dimensions; "
                "policy aligns to YouTube-safe 16:9 assets for cross-platform parity."
            ),
        )
    )
    apple_video: ThumbnailTargetSpec = Field(
        default_factory=lambda: ThumbnailTargetSpec(
            width=3000,
            height=3000,
            aspect_ratio="1:1",
            formats=["jpg", "png"],
            max_size_bytes=2 * 1024 * 1024,
            source="official",
            notes="Apple Podcasts artwork baseline for cover/episode visual assets.",
        )
    )


class PlatformSpec(BaseModel):
    """Export specifications for a platform."""

    container: str = "mp4"
    video_codec: str = "libx264"
    video_bitrate: str = "8M"
    audio_codec: str = "aac"
    audio_bitrate: str = "256k"
    audio_channels: int = 2
    loudness_lufs: float = -14.0
    resolution: str | None = None  # None = keep original
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None  # e.g., "16:9", "9:16", "1:1"
    max_duration: int | None = None  # seconds
    min_duration: int | None = None  # seconds
    pix_fmt: str = "yuv420p"
    video_profile: str | None = None
    video_level: str | None = None
    preset: str = "medium"
    fps: int | None = None
    gop: int | None = Field(default=None, ge=1)
    keyint_min: int | None = Field(default=None, ge=1)
    hls: HLSConfig | None = None
    crop_mode: str = "center"  # center, top, bottom, smart
    audio_only: bool = False  # True for audio-only platforms
    # Phase 9: AV1 is explicitly experimental and opt-in; never auto-activated
    av1_experimental: bool = False

    @model_validator(mode="after")
    def validate_compliance_fields(self) -> Self:
        """Validate codec-aware profile/level/pixel-format and keyframe fields."""
        codec = (self.video_codec or "").strip().lower()
        pix_fmt = (self.pix_fmt or "").strip().lower()
        profile = self.video_profile.strip().lower() if self.video_profile else None
        level = self.video_level.strip() if self.video_level else None

        self.video_codec = codec or self.video_codec
        self.pix_fmt = pix_fmt or self.pix_fmt
        self.video_profile = profile
        self.video_level = level

        if profile and codec not in CODECS_WITH_PROFILE_LEVEL:
            raise ValueError(
                f"video_profile is not supported for codec '{self.video_codec}'. "
                "Use null for codecs without profile controls."
            )
        if level and codec not in CODECS_WITH_PROFILE_LEVEL:
            raise ValueError(
                f"video_level is not supported for codec '{self.video_codec}'. "
                "Use null for codecs without level controls."
            )

        if codec in H264_CODECS and profile and profile not in H264_PROFILES:
            allowed = ", ".join(sorted(H264_PROFILES))
            raise ValueError(
                f"Invalid video_profile '{self.video_profile}' for codec '{self.video_codec}'. "
                f"Expected one of: {allowed}"
            )
        if codec in H265_CODECS and profile and profile not in H265_PROFILES:
            allowed = ", ".join(sorted(H265_PROFILES))
            raise ValueError(
                f"Invalid video_profile '{self.video_profile}' for codec '{self.video_codec}'. "
                f"Expected one of: {allowed}"
            )

        if level and not VIDEO_LEVEL_PATTERN.fullmatch(level):
            raise ValueError(
                f"Invalid video_level '{self.video_level}'. Expected numeric AVC/HEVC level such as 4, 4.0, 4.1."
            )

        if codec in PIX_FMT_BY_CODEC and pix_fmt and pix_fmt not in PIX_FMT_BY_CODEC[codec]:
            allowed = ", ".join(sorted(PIX_FMT_BY_CODEC[codec]))
            raise ValueError(
                f"Invalid pix_fmt '{self.pix_fmt}' for codec '{self.video_codec}'. "
                f"Expected one of: {allowed}"
            )

        # Reject hevc_nvenc + uhq + highbitdepth combination (known RTX artifacts).
        # p7 preset must be used for 10-bit NVENC instead.
        if codec == "hevc_nvenc" and pix_fmt == "p010le" and self.preset in {"uhq", "hq"}:
            raise ValueError(
                "hevc_nvenc with p010le (10-bit) should not use 'uhq' or 'hq' preset "
                "due to known RTX artifacts. Use 'p7' or 'slow' instead."
            )

        # AV1 opt-in gate: av1_experimental must be True when using an AV1 codec.
        if codec in AV1_CODECS and not self.av1_experimental:
            raise ValueError(
                f"AV1 codec '{self.video_codec}' requires av1_experimental=true. "
                "AV1 output is experimental and must be explicitly enabled."
            )

        if self.keyint_min is not None and self.gop is None:
            raise ValueError("keyint_min requires gop to be set")
        if self.gop is not None and self.keyint_min is not None and self.keyint_min > self.gop:
            raise ValueError(f"keyint_min ({self.keyint_min}) cannot exceed gop ({self.gop})")

        return self


class PlatformSpecs(BaseModel):
    """Platform-specific export specifications."""

    youtube: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_bitrate="8M",
            audio_codec="aac",
            audio_bitrate="256k",
            loudness_lufs=-14.0,
            preset="medium",
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            fps=30,
        )
    )
    spotify: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp3",
            audio_codec="libmp3lame",
            audio_bitrate="320k",
            loudness_lufs=-16.0,
            audio_only=True,
        )
    )
    apple: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="m4a",
            audio_codec="aac",
            audio_bitrate="128k",
            loudness_lufs=-16.0,
            audio_only=True,
        )
    )
    spotify_video: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_profile="high",
            video_level="4.1",
            video_bitrate="8M",
            audio_codec="aac",
            audio_bitrate="192k",
            loudness_lufs=-14.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            fps=30,
            gop=30,
            keyint_min=30,
            pix_fmt="yuv420p",
            preset="medium",
        )
    )
    apple_video: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_profile="high",
            video_level="4.0",
            video_bitrate="8M",
            audio_codec="aac",
            audio_bitrate="160k",
            loudness_lufs=-16.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            fps=30,
            gop=30,
            keyint_min=30,
            pix_fmt="yuv420p",
            preset="medium",
        )
    )
    apple_hls: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="hls",
            video_codec="libx264",
            video_profile="high",
            video_level="4.0",
            video_bitrate="8M",
            audio_codec="aac",
            audio_bitrate="160k",
            loudness_lufs=-16.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            fps=30,
            gop=30,
            keyint_min=30,
            pix_fmt="yuv420p",
            preset="medium",
            hls=HLSConfig(
                segment_duration=6,
                playlist_type="vod",
                master_playlist_name="master.m3u8",
                variant_playlist_pattern="variant_%v.m3u8",
                segment_filename_pattern="segment_%v_%03d.ts",
                var_stream_map="v:0,a:0",
            ),
        )
    )
    tiktok: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_bitrate="5M",
            audio_codec="aac",
            audio_bitrate="128k",
            loudness_lufs=-14.0,
            width=1080,
            height=1920,
            aspect_ratio="9:16",
            max_duration=60,
            fps=30,
            crop_mode="center",
            preset="fast",
        )
    )
    instagram: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_bitrate="5M",
            audio_codec="aac",
            audio_bitrate="128k",
            loudness_lufs=-14.0,
            width=1080,
            height=1920,
            aspect_ratio="9:16",
            max_duration=90,
            min_duration=3,
            fps=30,
            crop_mode="center",
            preset="fast",
        )
    )
    linkedin: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_bitrate="6M",
            audio_codec="aac",
            audio_bitrate="192k",
            loudness_lufs=-14.0,
            width=1080,
            height=1080,
            aspect_ratio="1:1",
            max_duration=600,
            fps=30,
            crop_mode="center",
            preset="medium",
        )
    )
    twitter: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_bitrate="5M",
            audio_codec="aac",
            audio_bitrate="128k",
            loudness_lufs=-14.0,
            width=1280,
            height=720,
            aspect_ratio="16:9",
            max_duration=140,  # 2:20
            fps=30,
            preset="fast",
        )
    )
    facebook: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_bitrate="8M",
            audio_codec="aac",
            audio_bitrate="256k",
            loudness_lufs=-14.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            max_duration=14400,  # 4 hours
            fps=30,
            preset="medium",
        )
    )
    # Phase 9: HEVC 10-bit "Ultra" quality profile — NEW DEFAULT for highest quality exports.
    # Runtime encoder selection: hevc_nvenc (NVENC GPU) -> libx265 (CPU software fallback).
    # The video_codec field here is the *preferred* codec; render stage resolves the actual
    # encoder at runtime using detect_hardware_encoders().  Use preset "p7" (not "uhq") for
    # RTX-5060-Ti compatibility (avoids uhq + highbitdepth artifact regression).
    youtube_ultra: PlatformSpec = Field(
        default_factory=lambda: PlatformSpec(
            container="mp4",
            video_codec="hevc_nvenc",
            video_profile="main10",
            video_bitrate="12M",
            audio_codec="aac",
            audio_bitrate="320k",
            loudness_lufs=-14.0,
            preset="p7",
            width=3840,
            height=2160,
            aspect_ratio="16:9",
            fps=30,
            pix_fmt="p010le",
        )
    )

    @model_validator(mode="after")
    def validate_video_target_requirements(self) -> Self:
        """Enforce fail-fast requirements for dedicated video podcast targets."""
        for platform_name in ("spotify_video", "apple_video"):
            spec = getattr(self, platform_name)
            missing = []
            for field_name in ("video_profile", "video_level", "pix_fmt", "gop", "keyint_min"):
                value = getattr(spec, field_name)
                if value is None or value == "":
                    missing.append(field_name)
            if missing:
                missing_fields = ", ".join(missing)
                raise ValueError(
                    f"{platform_name}: missing required compliance field(s): {missing_fields}"
                )
            if spec.audio_only:
                raise ValueError(f"{platform_name}: audio_only must be false for video targets")
            if spec.video_codec not in CODECS_WITH_PROFILE_LEVEL:
                raise ValueError(
                    f"{platform_name}: codec '{spec.video_codec}' does not support profile/level controls"
                )

        return self

    @model_validator(mode="after")
    def validate_hevc10_ultra_profiles(self) -> Self:
        """Validate HEVC 10-bit Ultra profiles that are present on the spec object."""
        ultra_spec = getattr(self, "youtube_ultra", None)
        if ultra_spec is None:
            return self
        codec = (ultra_spec.video_codec or "").strip().lower()
        if codec in H265_CODECS and ultra_spec.video_profile not in H265_PROFILES:
            allowed = ", ".join(sorted(H265_PROFILES))
            raise ValueError(
                f"youtube_ultra: invalid video_profile '{ultra_spec.video_profile}' "
                f"for HEVC codec. Expected one of: {allowed}"
            )
        return self


class ServiceConfig(BaseModel):
    """Backend service connection settings.

    Used by Streamlit and desktop clients to reach the FastAPI backend.
    """

    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65535)
    timeout: float = Field(default=30.0, gt=0.0)
    retries: int = Field(default=2, ge=0)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        """Validate service host format and reject unsafe URL-style values."""
        host = value.strip()
        if not host:
            raise ValueError("host cannot be empty")
        if host != value:
            raise ValueError("host cannot include leading or trailing whitespace")
        if host.startswith(("http://", "https://")):
            raise ValueError("host must not include URL scheme")
        if "/" in host:
            raise ValueError("host must not include path separators")

        if host.startswith("[") and host.endswith("]"):
            ipv6 = host[1:-1]
            try:
                ipaddress.IPv6Address(ipv6)
            except ValueError as exc:
                raise ValueError(f"Invalid IPv6 host: {host}") from exc
            return host

        if ":" in host:
            raise ValueError("host must not include a port; configure ports via ServiceConfig.port")

        if not SERVICE_HOST_PATTERN.fullmatch(host):
            raise ValueError("host must contain only letters, numbers, dots, and hyphens")

        return host

    @property
    def base_url(self) -> str:
        """Build the base URL from host and port."""
        return f"http://{self.host}:{self.port}"


class APIKeysConfig(BaseModel):
    """API keys loaded from environment."""

    gemini: str | None = None
    kimi: str | None = None
    openai: str | None = None
    youtube: str | None = None
    anthropic: str | None = None

    @classmethod
    def from_env(cls) -> "APIKeysConfig":
        """Load API keys from environment variables."""
        return cls(
            gemini=os.getenv("GEMINI_API_KEY"),
            kimi=os.getenv("KIMI_API_KEY"),
            openai=os.getenv("OPENAI_API_KEY"),
            youtube=os.getenv("YOUTUBE_API_KEY"),
            anthropic=os.getenv("ANTHROPIC_API_KEY"),
        )


class CaptionConfig(BaseModel):
    """Phase 9 caption burn-in settings.

    Controls whether ASS captions are generated and burned into exported video.
    Requires a ``word_alignment.json`` artifact from the transcription stage.
    """

    enabled: bool = Field(
        default=False,
        description="When True, caption burn-in is attempted for each export.",
    )
    alignment_filename: str = Field(
        default="word_alignment.json",
        description="Filename (relative to job artifacts dir) for word-level alignment data.",
    )
    max_words_per_line: int = Field(
        default=7,
        ge=1,
        le=20,
        description="Maximum words grouped into a single dialogue event.",
    )
    gap_threshold_s: float = Field(
        default=1.5,
        ge=0.1,
        le=10.0,
        description="Silence gap (seconds) that forces a new dialogue event.",
    )


class BrandingConfig(BaseModel):
    """Phase 9 branding profile configuration.

    Controls which BrandingProfile is active for a job and where profile YAML
    files are stored.  Both fields are optional so existing configs that do
    not mention ``branding:`` continue to work without changes.
    """

    active_profile: str | None = Field(
        default=None,
        description=(
            "Name of the active BrandingProfile (without .yaml extension). "
            "Set to null / omit to run without branding."
        ),
    )
    branding_dir: Path = Field(
        default=Path("branding"),
        description="Directory that holds branding/<name>.yaml profile files.",
    )
    captions: CaptionConfig = Field(
        default_factory=CaptionConfig,
        description="Caption burn-in settings (word-level ASS subtitle generation).",
    )


class Config(BaseModel):
    """Complete pipeline configuration."""

    paths: PathsConfig = Field(default_factory=PathsConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    fillers: FillerConfig = Field(default_factory=FillerConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    enhancements: EnhancementsConfig = Field(default_factory=EnhancementsConfig)
    smoothing: SmoothingConfig = Field(default_factory=SmoothingConfig)
    thumbnails: ThumbnailSpecs = Field(default_factory=ThumbnailSpecs)
    platforms: PlatformSpecs = Field(default_factory=PlatformSpecs)
    api_keys: APIKeysConfig = Field(default_factory=APIKeysConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    branding: BrandingConfig = Field(default_factory=BrandingConfig)


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file and environment."""
    # Load .env file if present
    load_dotenv()

    config_data: dict[str, Any] = {}

    # Load YAML config if provided
    if config_path and config_path.exists():
        with open(config_path) as f:
            yaml_data = yaml.safe_load(f)
            if yaml_data:
                config_data = yaml_data
    else:
        # Check default locations
        for default_path in [Path("config.yaml"), Path("config.yml")]:
            if default_path.exists():
                with open(default_path) as f:
                    yaml_data = yaml.safe_load(f)
                    if yaml_data:
                        config_data = yaml_data
                break

    # Create config from data
    config = Config(**config_data) if config_data else Config()

    # Override API keys from environment
    config.api_keys = APIKeysConfig.from_env()

    return config
