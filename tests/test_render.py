"""Tests for render stage and platform exports."""

import json
from pathlib import Path

from podcast_pipeline.config import PlatformSpec, load_config
from podcast_pipeline.stages.render import RenderStage


class TestPlatformSpecs:
    """Tests for platform specifications."""

    def test_youtube_spec_defaults(self) -> None:
        """Test YouTube platform spec defaults."""
        config = load_config()
        spec = config.platforms.youtube

        assert spec.width == 1920
        assert spec.height == 1080
        assert spec.aspect_ratio == "16:9"
        assert spec.video_codec == "libx264"
        assert spec.audio_only is False

    def test_tiktok_spec_defaults(self) -> None:
        """Test TikTok platform spec defaults."""
        config = load_config()
        spec = config.platforms.tiktok

        assert spec.width == 1080
        assert spec.height == 1920
        assert spec.aspect_ratio == "9:16"
        assert spec.max_duration == 60
        assert spec.crop_mode == "center"

    def test_instagram_spec_defaults(self) -> None:
        """Test Instagram platform spec defaults."""
        config = load_config()
        spec = config.platforms.instagram

        assert spec.width == 1080
        assert spec.height == 1920
        assert spec.aspect_ratio == "9:16"
        assert spec.max_duration == 90
        assert spec.min_duration == 3

    def test_linkedin_spec_defaults(self) -> None:
        """Test LinkedIn platform spec (square)."""
        config = load_config()
        spec = config.platforms.linkedin

        assert spec.width == 1080
        assert spec.height == 1080
        assert spec.aspect_ratio == "1:1"
        assert spec.max_duration == 600

    def test_twitter_spec_defaults(self) -> None:
        """Test Twitter platform spec."""
        config = load_config()
        spec = config.platforms.twitter

        assert spec.width == 1280
        assert spec.height == 720
        assert spec.max_duration == 140  # 2:20

    def test_spotify_is_audio_only(self) -> None:
        """Test Spotify is audio-only."""
        config = load_config()
        spec = config.platforms.spotify

        assert spec.audio_only is True
        assert spec.audio_codec == "libmp3lame"

    def test_apple_is_audio_only(self) -> None:
        """Test Apple Podcasts is audio-only."""
        config = load_config()
        spec = config.platforms.apple

        assert spec.audio_only is True
        assert spec.audio_codec == "aac"


class TestRenderStage:
    """Tests for RenderStage class."""

    def test_render_stage_name(self) -> None:
        """Test render stage has correct name."""
        config = load_config()
        stage = RenderStage(config)
        assert stage.name == "render"

    def test_get_platform_spec_youtube(self) -> None:
        """Test getting YouTube platform spec."""
        config = load_config()
        stage = RenderStage(config)
        spec = stage._get_platform_spec("youtube")

        assert spec is not None
        assert spec.video_codec == "libx264"

    def test_get_platform_spec_unknown(self) -> None:
        """Test getting unknown platform spec returns None."""
        config = load_config()
        stage = RenderStage(config)
        spec = stage._get_platform_spec("unknown_platform")

        assert spec is None

    def test_find_input_video_mp4(self, tmp_path: Path) -> None:
        """Test finding MP4 input video."""
        config = load_config()
        stage = RenderStage(config)

        # Create input directory with video
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        video_path = input_dir / "raw.mp4"
        video_path.write_bytes(b"fake video data")

        result = stage._find_input_video(tmp_path)
        assert result == video_path

    def test_find_input_video_mov(self, tmp_path: Path) -> None:
        """Test finding MOV input video."""
        config = load_config()
        stage = RenderStage(config)

        input_dir = tmp_path / "input"
        input_dir.mkdir()
        video_path = input_dir / "raw.mov"
        video_path.write_bytes(b"fake video data")

        result = stage._find_input_video(tmp_path)
        assert result == video_path

    def test_find_input_video_none(self, tmp_path: Path) -> None:
        """Test finding video returns None when missing."""
        config = load_config()
        stage = RenderStage(config)

        input_dir = tmp_path / "input"
        input_dir.mkdir()

        result = stage._find_input_video(tmp_path)
        assert result is None


class TestAspectRatioConversion:
    """Tests for aspect ratio conversion logic."""

    def test_build_video_filters_same_ratio(self) -> None:
        """Test video filters when aspect ratios match."""
        config = load_config()
        stage = RenderStage(config)
        spec = PlatformSpec(width=1920, height=1080, aspect_ratio="16:9")

        filters = stage._build_video_filters(1920, 1080, 1920, 1080, spec)

        assert len(filters) == 1
        assert "scale=1920:1080" in filters[0]

    def test_build_video_filters_horizontal_to_vertical(self) -> None:
        """Test converting 16:9 to 9:16 (crop sides)."""
        config = load_config()
        stage = RenderStage(config)
        spec = PlatformSpec(width=1080, height=1920, aspect_ratio="9:16", crop_mode="center")

        filters = stage._build_video_filters(1920, 1080, 1080, 1920, spec)

        # Should have crop and scale
        assert len(filters) == 2
        assert "crop" in filters[0]
        assert "scale" in filters[1]

    def test_build_video_filters_to_square(self) -> None:
        """Test converting 16:9 to 1:1 (crop sides)."""
        config = load_config()
        stage = RenderStage(config)
        spec = PlatformSpec(width=1080, height=1080, aspect_ratio="1:1", crop_mode="center")

        filters = stage._build_video_filters(1920, 1080, 1080, 1080, spec)

        assert len(filters) == 2
        assert "crop" in filters[0]
        assert "scale=1080:1080" in filters[1]


class TestMarketingDocGeneration:
    """Tests for marketing document generation."""

    def test_generate_marketing_doc(self, tmp_path: Path) -> None:
        """Test marketing document generation."""
        config = load_config()
        stage = RenderStage(config)

        # Create analysis directory with data
        analysis_dir = tmp_path / "analysis"
        analysis_dir.mkdir()

        analysis_data = {
            "marketing": {
                "youtube": {
                    "titles": ["Test Title 1", "Test Title 2"],
                    "description": "Test description",
                    "hashtags": ["#test", "#podcast"],
                },
                "tiktok": {
                    "description": "TikTok caption",
                    "hashtags": ["#viral", "#fyp"],
                },
            },
            "metadata": {
                "summary": "Test episode summary",
                "topics": ["tech", "ai"],
                "mood": "informative",
            },
        }

        (analysis_dir / "analysis.json").write_text(json.dumps(analysis_data))

        result = stage._generate_marketing_doc(tmp_path)

        assert result is not None
        assert "marketing" in result

        # Check the file was created
        doc_path = tmp_path / "output" / "marketing" / "copy.md"
        assert doc_path.exists()

        content = doc_path.read_text()
        assert "YouTube" in content
        assert "TikTok" in content
        assert "Test Title 1" in content
