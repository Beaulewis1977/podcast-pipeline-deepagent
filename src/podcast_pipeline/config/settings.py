"""Configuration settings with Pydantic models."""

import ipaddress
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Self

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_MODEL_PROVIDERS = {"gemini", "kimi"}
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
SUPPORTED_MODELS_BY_PROVIDER = {
    "gemini": SUPPORTED_GEMINI_MODELS,
    "kimi": SUPPORTED_KIMI_MODELS,
}

SERVICE_HOST_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")
VIDEO_LEVEL_PATTERN = re.compile(r"^(?:[1-6](?:\.[0-2])?|1\.3)$")
H264_CODECS = {"h264", "libx264"}
H265_CODECS = {"h265", "hevc", "libx265"}
CODECS_WITH_PROFILE_LEVEL = H264_CODECS | H265_CODECS
H264_PROFILES = {"baseline", "main", "high", "high10", "high422", "high444"}
H265_PROFILES = {"main", "main10", "mainstillpicture"}
PIX_FMT_BY_CODEC = {
    "h264": {"yuv420p", "yuv422p", "yuv444p"},
    "libx264": {"yuv420p", "yuv422p", "yuv444p"},
    "h265": {"yuv420p", "yuv420p10le", "yuv422p10le", "yuv444p10le"},
    "hevc": {"yuv420p", "yuv420p10le", "yuv422p10le", "yuv444p10le"},
    "libx265": {"yuv420p", "yuv420p10le", "yuv422p10le", "yuv444p10le"},
}


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
    """Filler word detection configuration."""

    words: list[str] = Field(
        default_factory=lambda: [
            "um",
            "uh",
            "hmm",
            "er",
            "ah",
            "like",
            "you know",
            "basically",
            "actually",
            "so",
        ]
    )
    min_confidence: float = 0.5
    min_duration_ms: int = 150
    padding_ms: int = 50


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

    @classmethod
    def from_env(cls) -> "APIKeysConfig":
        """Load API keys from environment variables."""
        return cls(
            gemini=os.getenv("GEMINI_API_KEY"),
            kimi=os.getenv("KIMI_API_KEY"),
            openai=os.getenv("OPENAI_API_KEY"),
            youtube=os.getenv("YOUTUBE_API_KEY"),
        )


class Config(BaseModel):
    """Complete pipeline configuration."""

    paths: PathsConfig = Field(default_factory=PathsConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    fillers: FillerConfig = Field(default_factory=FillerConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    platforms: PlatformSpecs = Field(default_factory=PlatformSpecs)
    api_keys: APIKeysConfig = Field(default_factory=APIKeysConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)


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
