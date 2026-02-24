"""Tests for configuration system."""

from pathlib import Path

import pytest

from podcast_pipeline.config import (
    Config,
    FillerConfig,
    ModelConfig,
    PathsConfig,
    load_config,
)
from podcast_pipeline.config.settings import (
    SUPPORTED_CLAUDE_MODELS,
    SUPPORTED_MODEL_PROVIDERS,
    SUPPORTED_MODELS_BY_PROVIDER,
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
        assert "um" in config.disfluencies
        assert "uh" in config.disfluencies
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


class TestClaudeProviderConfig:
    """Tests for Claude provider config registration and validation."""

    def test_claude_in_supported_providers(self):
        """'claude' must appear in SUPPORTED_MODEL_PROVIDERS."""
        assert "claude" in SUPPORTED_MODEL_PROVIDERS

    def test_supported_claude_models_set(self):
        """SUPPORTED_CLAUDE_MODELS must contain the three expected model IDs."""
        assert "claude-sonnet-4-6" in SUPPORTED_CLAUDE_MODELS
        assert "claude-haiku-4-5" in SUPPORTED_CLAUDE_MODELS
        assert "claude-opus-4-6" in SUPPORTED_CLAUDE_MODELS

    def test_supported_models_by_provider_contains_claude(self):
        """SUPPORTED_MODELS_BY_PROVIDER must map 'claude' to its model set."""
        assert "claude" in SUPPORTED_MODELS_BY_PROVIDER
        assert SUPPORTED_MODELS_BY_PROVIDER["claude"] is SUPPORTED_CLAUDE_MODELS

    def test_model_config_accepts_claude_provider(self):
        """ModelConfig should accept provider='claude' with a valid Claude model."""
        mc = ModelConfig(
            provider="claude",
            model="claude-sonnet-4-6",
            fallback_provider=None,
            fallback_model=None,
        )
        assert mc.provider == "claude"
        assert mc.model == "claude-sonnet-4-6"

    def test_model_config_accepts_claude_haiku(self):
        """ModelConfig should accept claude-haiku-4-5 with claude provider."""
        mc = ModelConfig(
            provider="claude",
            model="claude-haiku-4-5",
            fallback_provider=None,
            fallback_model=None,
        )
        assert mc.model == "claude-haiku-4-5"

    def test_model_config_accepts_claude_opus(self):
        """ModelConfig should accept claude-opus-4-6 with claude provider."""
        mc = ModelConfig(
            provider="claude",
            model="claude-opus-4-6",
            fallback_provider=None,
            fallback_model=None,
        )
        assert mc.model == "claude-opus-4-6"

    def test_model_config_rejects_unknown_claude_model(self):
        """ModelConfig should reject unsupported Claude model IDs."""
        with pytest.raises(ValueError, match="not supported for provider 'claude'"):
            ModelConfig(
                provider="claude",
                model="claude-4-turbo-unknown",
                fallback_provider=None,
                fallback_model=None,
            )

    def test_model_config_rejects_unknown_provider(self):
        """ModelConfig should reject providers not in SUPPORTED_MODEL_PROVIDERS."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            ModelConfig(
                provider="openai",
                model="gpt-4o",
                fallback_provider=None,
                fallback_model=None,
            )

    def test_model_config_claude_as_fallback(self):
        """ModelConfig should allow claude as the fallback_provider."""
        mc = ModelConfig(
            provider="gemini",
            model="gemini-2.5-flash",
            fallback_provider="claude",
            fallback_model="claude-sonnet-4-6",
        )
        assert mc.fallback_provider == "claude"
        assert mc.fallback_model == "claude-sonnet-4-6"

    def test_api_keys_config_has_anthropic_field(self):
        """APIKeysConfig must include the 'anthropic' field."""
        config = Config()
        assert hasattr(config.api_keys, "anthropic")
        assert config.api_keys.anthropic is None

    def test_api_keys_config_loads_anthropic_key_from_env(self, monkeypatch):
        """APIKeysConfig.from_env should load ANTHROPIC_API_KEY."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        config = load_config()
        assert config.api_keys.anthropic == "sk-ant-test-key"
