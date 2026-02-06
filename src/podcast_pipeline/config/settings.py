"""Configuration settings with Pydantic models."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


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
    preset: str = "medium"
    fps: int | None = None
    crop_mode: str = "center"  # center, top, bottom, smart
    audio_only: bool = False  # True for audio-only platforms


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


class ServiceConfig(BaseModel):
    """Backend service connection settings.

    Used by Streamlit and desktop clients to reach the FastAPI backend.
    """

    host: str = "127.0.0.1"
    port: int = 8787
    timeout: float = 30.0
    retries: int = 2

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
