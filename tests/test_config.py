"""Tests for configuration system."""

import os
from pathlib import Path

import pytest

from podcast_pipeline.config import (
    Config,
    FillerConfig,
    PathsConfig,
    PlatformSpec,
    load_config,
)


class TestConfig:
    """Tests for Config model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        assert config.paths.jobs_dir == Path("./jobs")
        assert config.models.provider == "gemini"
        assert config.transcription.device == "cuda"

    def test_filler_config(self):
        """Test filler word configuration."""
        config = FillerConfig()
        assert "um" in config.words
        assert "uh" in config.words
        assert config.min_confidence == 0.5
        assert config.min_duration_ms == 150

    def test_platform_specs(self):
        """Test platform specifications."""
        config = Config()
        assert config.platforms.youtube.loudness_lufs == -14.0
        assert config.platforms.spotify.loudness_lufs == -16.0
        assert config.platforms.spotify.container == "mp3"

    def test_load_config_with_env(self, monkeypatch):
        """Test loading config with environment variables."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        config = load_config()
        assert config.api_keys.gemini == "test-key-123"

    def test_custom_paths(self):
        """Test custom path configuration."""
        paths = PathsConfig(jobs_dir=Path("/custom/jobs"))
        assert paths.jobs_dir == Path("/custom/jobs")
