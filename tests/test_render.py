"""Tests for render stage and platform exports."""

import json
from collections import namedtuple
from pathlib import Path
from typing import Any

import pytest

from podcast_pipeline.config import PlatformSpec, load_config
from podcast_pipeline.models.edit_plan import EditPlan, FillerCutRange
from podcast_pipeline.models.job import Job
from podcast_pipeline.stages.render import PlatformComplianceError, RenderStage
from podcast_pipeline.stages.review import ReviewDecisions
from podcast_pipeline.utils.ffmpeg import FFmpegError


def _create_review_ready_job(tmp_path: Path, platforms: list[str]) -> Job:
    """Create a review-approved job directory layout for render tests."""
    review_dir = tmp_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_state = {
        "review_complete": True,
        "export_platforms": platforms,
    }
    (review_dir / "review_state.json").write_text(json.dumps(review_state))

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / "raw.mp4"
    input_path.write_bytes(b"fake-video")

    return Job(job_id="render-test-job", input_file=str(input_path))


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

    def test_spotify_video_spec_defaults(self) -> None:
        """Spotify video target should use conservative H.264 MP4 defaults."""
        config = load_config()
        spec = config.platforms.spotify_video

        assert spec.audio_only is False
        assert spec.container == "mp4"
        assert spec.video_codec == "libx264"
        assert spec.video_profile == "high"
        assert spec.video_level == "4.1"
        assert spec.pix_fmt == "yuv420p"
        assert spec.gop == 30
        assert spec.keyint_min == 30

    def test_apple_video_spec_defaults(self) -> None:
        """Apple video target should use conservative MP4 defaults."""
        config = load_config()
        spec = config.platforms.apple_video

        assert spec.audio_only is False
        assert spec.container == "mp4"
        assert spec.video_codec == "libx264"
        assert spec.video_profile == "high"
        assert spec.video_level == "4.0"
        assert spec.pix_fmt == "yuv420p"
        assert spec.gop == 30
        assert spec.keyint_min == 30

    def test_thumbnail_config_defaults_cover_selected_video_targets(self) -> None:
        """Thumbnail config should define typed constraints for youtube/spotify_video/apple_video."""
        config = load_config()

        youtube = config.thumbnails.youtube
        spotify_video = config.thumbnails.spotify_video
        apple_video = config.thumbnails.apple_video

        assert (youtube.width, youtube.height, youtube.aspect_ratio) == (1280, 720, "16:9")
        assert (spotify_video.width, spotify_video.height, spotify_video.aspect_ratio) == (
            1280,
            720,
            "16:9",
        )
        assert (apple_video.width, apple_video.height, apple_video.aspect_ratio) == (
            3000,
            3000,
            "1:1",
        )
        assert "jpg" in youtube.formats
        assert youtube.max_size_bytes == 2 * 1024 * 1024

    def test_thumbnail_config_rejects_mismatched_aspect_ratio(self, tmp_path: Path) -> None:
        """Invalid thumbnail width/height to aspect mapping should fail fast."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "thumbnails:",
                    "  youtube:",
                    "    width: 1280",
                    "    height: 720",
                    "    aspect_ratio: '1:1'",
                    "    formats: [jpg]",
                    "    max_size_bytes: 2097152",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"aspect_ratio|width|height"):
            load_config(config_path)

    def test_platform_spec_defaults_preserve_legacy_audio_only_targets(self) -> None:
        """Dedicated video targets must not change legacy spotify/apple audio-only presets."""
        config = load_config()

        spotify = config.platforms.spotify
        apple = config.platforms.apple

        assert spotify.audio_only is True
        assert spotify.container == "mp3"
        assert spotify.audio_codec == "libmp3lame"
        assert spotify.audio_bitrate == "320k"

        assert apple.audio_only is True
        assert apple.container == "m4a"
        assert apple.audio_codec == "aac"
        assert apple.audio_bitrate == "128k"

    def test_apple_hls_platform_spec_defaults(self) -> None:
        """apple_hls target should parse typed VOD HLS defaults."""
        config = load_config()
        spec = config.platforms.apple_hls

        assert spec.container == "hls"
        assert spec.video_codec == "libx264"
        assert spec.hls is not None
        assert spec.hls.playlist_type == "vod"
        assert spec.hls.master_playlist_name == "master.m3u8"
        assert spec.hls.variant_playlist_pattern == "variant_%v.m3u8"
        assert spec.hls.segment_filename_pattern == "segment_%v_%03d.ts"

    def test_hls_config_validation_requires_variant_token(self, tmp_path: Path) -> None:
        """HLS variant pattern should fail fast when '%v' placeholder is missing."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  apple_hls:",
                    "    hls:",
                    "      variant_playlist_pattern: variant.m3u8",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"variant_playlist_pattern|%v"):
            load_config(config_path)

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("master_playlist_name", "../master.m3u8"),
            ("master_playlist_name", "/absolute/master.m3u8"),
            ("variant_playlist_pattern", "variants/variant_%v.m3u8"),
            ("segment_filename_pattern", r"..\\segment_%v_%03d.ts"),
        ],
    )
    def test_hls_config_validation_rejects_unsafe_filenames(
        self,
        tmp_path: Path,
        field_name: str,
        value: str,
    ) -> None:
        """HLS config names must remain simple filenames in the output directory."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  apple_hls:",
                    "    hls:",
                    f"      {field_name}: '{value}'",
                ]
            )
        )

        with pytest.raises(ValueError, match=field_name):
            load_config(config_path)

    def test_video_profile_validation_includes_platform_name(self, tmp_path: Path) -> None:
        """Invalid H.264 profile values should fail with target context."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  spotify_video:",
                    "    video_profile: superhigh",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"video_profile|spotify_video") as exc:
            load_config(config_path)

        message = str(exc.value)
        assert "spotify_video" in message
        assert "video_profile" in message

    def test_video_level_validation_rejects_invalid_values(self, tmp_path: Path) -> None:
        """Invalid video levels should fail before render starts."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  apple_video:",
                    "    video_level: level-4",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"video_level|apple_video") as exc:
            load_config(config_path)

        message = str(exc.value)
        assert "apple_video" in message
        assert "video_level" in message

    def test_video_level_validation_accepts_h264_level_1_3(self, tmp_path: Path) -> None:
        """H.264 level 1.3 should parse cleanly for compliant video targets."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  apple_video:",
                    "    video_profile: high",
                    "    video_level: '1.3'",
                    "    pix_fmt: yuv420p",
                    "    gop: 30",
                    "    keyint_min: 30",
                ]
            )
        )

        config = load_config(config_path)
        assert config.platforms.apple_video.video_level == "1.3"

    def test_pix_fmt_validation_rejects_codec_mismatch(self, tmp_path: Path) -> None:
        """Unsupported pixel format + codec combinations should fail fast."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  spotify_video:",
                    "    pix_fmt: yuv444p10le",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"pix_fmt|spotify_video") as exc:
            load_config(config_path)

        message = str(exc.value)
        assert "spotify_video" in message
        assert "pix_fmt" in message

    def test_keyframe_validation_rejects_keyint_min_over_gop(self, tmp_path: Path) -> None:
        """Invalid keyframe cadence should fail at config load."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  spotify_video:",
                    "    gop: 30",
                    "    keyint_min: 45",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"keyint_min|spotify_video") as exc:
            load_config(config_path)

        message = str(exc.value)
        assert "spotify_video" in message
        assert "keyint_min" in message


class TestEnhancementConfig:
    """Tests for typed Phase 6 enhancement config behavior."""

    def test_config_deesser_defaults_enable_conservative_baseline(self) -> None:
        """De-esser should be on by default with conservative tuning."""
        config = load_config()

        assert config.enhancements.deesser.enabled is True
        assert config.enhancements.deesser.intensity == pytest.approx(0.2)
        assert config.enhancements.deesser.max_deessing == pytest.approx(0.5)
        assert config.enhancements.deesser.frequency == pytest.approx(0.5)
        assert config.enhancements.deesser.output_mode == "o"
        assert config.enhancements.deesser.click_safety_enabled is True

    def test_config_dereverb_defaults_disabled_with_safe_fallback(self) -> None:
        """Dereverb should remain opt-in with safe missing-dependency behavior."""
        config = load_config()

        assert config.enhancements.dereverb.enabled is False
        assert config.enhancements.dereverb.fallback_mode == "warn_skip"
        assert config.enhancements.dereverb.prop_decrease == pytest.approx(0.85)
        assert config.enhancements.dereverb.stationary is False

    def test_config_color_correction_defaults_disabled(self) -> None:
        """Color correction should be explicit opt-in."""
        config = load_config()

        assert config.enhancements.color_correction.enabled is False
        assert config.enhancements.color_correction.normalize_strength == pytest.approx(1.0)
        assert config.enhancements.color_correction.normalize_enabled is True
        assert config.enhancements.color_correction.grayworld_enabled is True
        assert config.enhancements.color_correction.eq_enabled is False

    def test_color_config_defaults_keep_correction_disabled(self) -> None:
        """Color config defaults should preserve existing output behavior."""
        config = load_config()

        assert config.enhancements.color_correction.enabled is False
        assert config.enhancements.color_correction.normalize_enabled is True
        assert config.enhancements.color_correction.normalize_strength == pytest.approx(1.0)

    def test_config_deesser_bounds_validation(self, tmp_path: Path) -> None:
        """Out-of-range deesser tuning values should fail at config load."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "enhancements:",
                    "  deesser:",
                    "    intensity: 1.4",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"deesser|intensity"):
            load_config(config_path)

    def test_config_color_correction_eq_bounds_validation(self, tmp_path: Path) -> None:
        """EQ tuning should reject values outside conservative bounds."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "enhancements:",
                    "  color_correction:",
                    "    eq_enabled: true",
                    "    eq_saturation: 4.5",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"color_correction|eq_saturation"):
            load_config(config_path)

    def test_color_config_bounds_reject_normalize_strength_out_of_range(
        self,
        tmp_path: Path,
    ) -> None:
        """Normalize strength should stay within canonical 0..1 bounds."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "enhancements:",
                    "  color_correction:",
                    "    normalize_strength: 1.5",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"color_correction|normalize_strength"):
            load_config(config_path)


class TestSmoothingConfig:
    """Tests for typed Phase 7 smoothing configuration defaults and validation."""

    def test_smoothing_config_defaults_are_conservative(self) -> None:
        """Default smoothing policy should be enabled with mild transition values."""
        config = load_config()

        assert config.smoothing.enabled is True
        assert config.smoothing.micro_fade_ms == pytest.approx(30.0)
        assert config.smoothing.content_audio_crossfade_ms == pytest.approx(150.0)
        assert config.smoothing.content_video_dissolve_ms == pytest.approx(300.0)
        assert config.smoothing.max_snap_shift_ms == pytest.approx(250.0)
        assert config.smoothing.join_clamp_ratio == pytest.approx(0.35)
        assert config.smoothing.require_transition_filters is False

    def test_smoothing_config_accepts_yaml_overrides(self, tmp_path: Path) -> None:
        """Smoothing overrides should parse as typed runtime settings."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "smoothing:",
                    "  enabled: true",
                    "  micro_fade_ms: 18",
                    "  content_audio_crossfade_ms: 120",
                    "  content_video_dissolve_ms: 220",
                    "  max_snap_shift_ms: 180",
                    "  join_clamp_ratio: 0.25",
                    "  require_transition_filters: true",
                ]
            )
        )

        config = load_config(config_path)

        assert config.smoothing.micro_fade_ms == pytest.approx(18.0)
        assert config.smoothing.content_audio_crossfade_ms == pytest.approx(120.0)
        assert config.smoothing.content_video_dissolve_ms == pytest.approx(220.0)
        assert config.smoothing.max_snap_shift_ms == pytest.approx(180.0)
        assert config.smoothing.join_clamp_ratio == pytest.approx(0.25)
        assert config.smoothing.require_transition_filters is True

    def test_smoothing_config_rejects_invalid_join_clamp_ratio(self, tmp_path: Path) -> None:
        """Clamp ratio above 0.5 should fail fast during config load."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "smoothing:",
                    "  join_clamp_ratio: 0.75",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"smoothing|join_clamp_ratio"):
            load_config(config_path)

    def test_smoothing_config_rejects_negative_micro_fade(self, tmp_path: Path) -> None:
        """Negative smoothing durations should be rejected."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "smoothing:",
                    "  micro_fade_ms: -5",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"smoothing|micro_fade_ms"):
            load_config(config_path)


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

    def test_marketing_doc_spotify_video_apple_video_instagram_facebook_order(
        self, tmp_path: Path
    ) -> None:
        """Marketing doc should include all supported marketing platforms in stable order."""
        config = load_config()
        stage = RenderStage(config)

        analysis_dir = tmp_path / "analysis"
        analysis_dir.mkdir()

        analysis_data = {
            "marketing": {
                "youtube": {"description": "YT"},
                "spotify": {"description": "Spotify audio"},
                "spotify_video": {"description": "Spotify video"},
                "apple": {"description": "Apple audio"},
                "apple_video": {"description": "Apple video"},
                "tiktok": {"description": "TikTok"},
                "instagram": {"description": "Instagram"},
                "linkedin": {"description": "LinkedIn"},
                "twitter": {"description": "Twitter"},
                "facebook": {"description": "Facebook"},
            },
            "metadata": {
                "summary": "Episode summary",
                "topics": ["growth"],
                "mood": "energetic",
            },
        }
        (analysis_dir / "analysis.json").write_text(json.dumps(analysis_data))

        stage._generate_marketing_doc(tmp_path)

        content = (tmp_path / "output" / "marketing" / "copy.md").read_text()
        lines = [line.strip() for line in content.splitlines()]
        expected_sections = [
            "## YouTube",
            "## Spotify",
            "## Spotify Video",
            "## Apple Podcasts",
            "## Apple Podcasts Video",
            "## TikTok",
            "## Instagram Reels",
            "## LinkedIn",
            "## Twitter/X",
            "## Facebook",
        ]

        previous_index = -1
        for section in expected_sections:
            assert section in lines, f"Missing section: {section}"
            current_index = lines.index(section)
            assert current_index > previous_index, f"Section out of order: {section}"
            previous_index = current_index

    def test_marketing_doc_full_platform_headers_present_with_partial_payload(
        self, tmp_path: Path
    ) -> None:
        """Marketing doc should keep full platform headers even when payload is sparse."""
        stage = RenderStage(load_config())

        analysis_dir = tmp_path / "analysis"
        analysis_dir.mkdir()
        (analysis_dir / "analysis.json").write_text(
            json.dumps(
                {
                    "marketing": {
                        "youtube": {
                            "titles": ["Hook title"],
                            "description": "Primary long-form description",
                            "hashtags": ["#podcast"],
                        }
                    },
                    "metadata": {
                        "summary": "Sparse payload",
                        "topics": ["topic"],
                        "mood": "focused",
                    },
                }
            )
        )

        stage._generate_marketing_doc(tmp_path)

        content = (tmp_path / "output" / "marketing" / "copy.md").read_text()
        lines = [line.strip() for line in content.splitlines()]
        for section in (
            "## YouTube",
            "## Spotify",
            "## Spotify Video",
            "## Apple Podcasts",
            "## Apple Podcasts Video",
            "## TikTok",
            "## Instagram Reels",
            "## LinkedIn",
            "## Twitter/X",
            "## Facebook",
        ):
            assert section in lines, f"Missing section: {section}"


class TestRenderEnhancementAndThumbnailOutputs:
    """Tests for enhancement and thumbnail artifact behavior."""

    def test_audio_enhancement_chain_includes_denoise_eq_and_limiter(self) -> None:
        """Enhancement filter chain should include denoise, EQ, and limiting steps."""
        config = load_config()
        stage = RenderStage(config)

        filters = stage._build_audio_enhancement_filters()

        assert any("afftdn" in item for item in filters)
        assert any("equalizer" in item for item in filters)
        assert any("alimiter" in item for item in filters)

    def test_audio_enhancement_chain_respects_noise_reduction_off(self) -> None:
        """Enhancement chain should skip denoise filter when config disables it."""
        config = load_config()
        config.audio.noise_reduction = "off"
        stage = RenderStage(config)

        filters = stage._build_audio_enhancement_filters()
        assert all("afftdn" not in item for item in filters)
        assert any("acompressor" in item for item in filters)

    def test_deesser_filter_uses_typed_config_defaults(self) -> None:
        """De-esser should be present when enabled in enhancement config."""
        stage = RenderStage(load_config())

        filters = stage._build_audio_enhancement_filters()

        assert any(item.startswith("deesser=") for item in filters)

    def test_adeclick_filter_respects_click_safety_toggle(self) -> None:
        """Final click-safety filter should only be present when enabled."""
        config = load_config()
        config.enhancements.deesser.click_safety_enabled = False
        stage = RenderStage(config)

        filters = stage._build_audio_enhancement_filters()

        assert all("adeclick" not in item for item in filters)

    def test_audio_chain_ordering_dialog_cleanup_then_deesser_then_limiter_then_adeclick(
        self,
    ) -> None:
        """Audio chain should keep deterministic ordering for cleanup, de-esser, and safety."""
        stage = RenderStage(load_config())

        filters = stage._build_audio_enhancement_filters()
        highpass_idx = next(i for i, item in enumerate(filters) if item.startswith("highpass="))
        deesser_idx = next(i for i, item in enumerate(filters) if item.startswith("deesser="))
        compressor_idx = next(
            i for i, item in enumerate(filters) if item.startswith("acompressor=")
        )
        limiter_idx = next(i for i, item in enumerate(filters) if item.startswith("alimiter="))
        adeclick_idx = next(i for i, item in enumerate(filters) if item.startswith("adeclick="))

        assert highpass_idx < deesser_idx < compressor_idx < limiter_idx < adeclick_idx

    def test_thumbnail_export_generates_images_and_manifest(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Thumbnail export should create concrete image artifacts and manifest metadata."""
        config = load_config()
        stage = RenderStage(config)
        input_video = tmp_path / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"video-bytes")

        analysis_dir = tmp_path / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "analysis.json").write_text(
            json.dumps(
                {
                    "thumbnail_frames": [
                        {
                            "timestamp": "00:10",
                            "timestamp_seconds": 10.0,
                            "visual_description": "Guest reaction shot",
                            "suggested_text_overlay": "Big reveal",
                            "emotion": "surprised",
                        },
                        {
                            "timestamp": "00:45",
                            "timestamp_seconds": 45.0,
                            "visual_description": "Host emphasizing key idea",
                            "suggested_text_overlay": "Do this now",
                            "emotion": "excited",
                        },
                    ]
                }
            )
        )

        def _fake_ffmpeg(args: list[str]) -> None:
            output_path = Path(args[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"thumbnail-bytes")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)

        outputs, result = stage._export_thumbnail_assets(
            job_dir=tmp_path,
            input_video=input_video,
            video_info={"duration": 90.0},
            decisions=ReviewDecisions(review_complete=True, selected_thumbnail=1),
        )

        assert result["status"] == "complete"
        assert result["generated"] == 2
        assert any(path.endswith("thumbnail_01.jpg") for path in outputs)
        assert any(path.endswith("manifest.json") for path in outputs)

        manifest_path = tmp_path / "output" / "thumbnails" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["generated"] == 2
        assert manifest["thumbnails"][0]["is_selected"] is True

    def test_thumbnail_export_uses_duration_fallback_for_sparse_analysis(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Sparse thumbnail metadata should still produce deterministic fallback images."""
        config = load_config()
        stage = RenderStage(config)
        input_video = tmp_path / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"video-bytes")

        analysis_dir = tmp_path / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "analysis.json").write_text(json.dumps({"thumbnail_frames": []}))

        def _fake_ffmpeg(args: list[str]) -> None:
            output_path = Path(args[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"thumbnail-bytes")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)

        outputs, result = stage._export_thumbnail_assets(
            job_dir=tmp_path,
            input_video=input_video,
            video_info={"duration": 120.0},
            decisions=ReviewDecisions(review_complete=True),
        )

        assert result["status"] == "complete"
        assert result["source"] == "duration_fallback"
        assert result["generated"] == 4
        assert any(path.endswith("manifest.json") for path in outputs)


class TestRenderEnhancementFilterCapabilities:
    """Tests for FFmpeg filter capability preflight checks."""

    def test_ffmpeg_filter_capability_defaults_only_require_enabled_paths(self) -> None:
        """Default required filters should reflect currently enabled enhancement toggles."""
        stage = RenderStage(load_config())

        required = stage._required_enhancement_filters()

        assert "deesser" in required
        assert "adeclick" in required
        assert "normalize" not in required
        assert "grayworld" not in required

    def test_ffmpeg_filter_capability_fail_fast_lists_missing_filters(
        self,
        monkeypatch,
    ) -> None:
        """Missing required filters should produce actionable preflight errors."""
        config = load_config()
        config.enhancements.color_correction.enabled = True
        stage = RenderStage(config)

        monkeypatch.setattr(stage, "_probe_available_ffmpeg_filters", lambda: {"deesser"})

        with pytest.raises(RuntimeError, match="missing required FFmpeg filter"):
            stage._ensure_filter_capabilities()

    def test_fail_fast_render_preflight_on_filter_capability_errors(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Render run should fail before per-platform execution when filters are unavailable."""
        stage = RenderStage(load_config())
        job = _create_review_ready_job(tmp_path, ["youtube"])

        monkeypatch.setattr(
            stage,
            "_ensure_filter_capabilities",
            lambda: (_ for _ in ()).throw(
                RuntimeError("Render preflight failed: missing required FFmpeg filter(s): deesser")
            ),
        )

        result = stage.run(job, tmp_path)

        assert result.success is False
        assert "missing required FFmpeg filter" in (result.error or "")


class TestThumbnailCompliance:
    """Tests for per-target thumbnail compliance generation and validation."""

    def test_thumbnail_compliance_generates_target_outputs_for_selected_platforms(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Selected platforms should receive derived thumbnail assets after compliance pass."""
        stage = RenderStage(load_config())
        source_thumbnail = tmp_path / "output" / "thumbnails" / "thumbnail_01.jpg"
        source_thumbnail.parent.mkdir(parents=True, exist_ok=True)
        source_thumbnail.write_bytes(b"thumbnail")

        def _fake_transform(_source: Path, target: Path, _spec) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"derived")

        monkeypatch.setattr(stage, "_transform_thumbnail_to_spec", _fake_transform)
        monkeypatch.setattr(stage, "_validate_thumbnail_asset", lambda *_args, **_kwargs: [])

        result = stage._enforce_thumbnail_target_compliance(
            job_dir=tmp_path,
            selected_platforms=["youtube", "spotify_video"],
            thumbnail_result={"thumbnail_paths": ["output/thumbnails/thumbnail_01.jpg"]},
        )

        assert result["status"] == "complete"
        assert result["platform_results"]["youtube"]["status"] == "success"
        assert result["platform_results"]["spotify_video"]["status"] == "success"
        assert any(path.startswith("output/thumbnails/youtube/") for path in result["outputs"])
        assert any(
            path.startswith("output/thumbnails/spotify_video/") for path in result["outputs"]
        )

    def test_thumbnail_compliance_fails_with_target_specific_diagnostics(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Compliance failures should return explicit platform-specific issue payloads."""
        stage = RenderStage(load_config())
        source_thumbnail = tmp_path / "output" / "thumbnails" / "thumbnail_01.jpg"
        source_thumbnail.parent.mkdir(parents=True, exist_ok=True)
        source_thumbnail.write_bytes(b"thumbnail")

        def _fake_transform(_source: Path, target: Path, _spec) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"derived")

        monkeypatch.setattr(stage, "_transform_thumbnail_to_spec", _fake_transform)
        monkeypatch.setattr(
            stage,
            "_validate_thumbnail_asset",
            lambda _path, _spec, platform: (
                [f"{platform}: thumbnail dimensions mismatch"] if platform == "apple_video" else []
            ),
        )

        result = stage._enforce_thumbnail_target_compliance(
            job_dir=tmp_path,
            selected_platforms=["apple_video"],
            thumbnail_result={"thumbnail_paths": ["output/thumbnails/thumbnail_01.jpg"]},
        )

        assert result["status"] == "failed"
        assert "apple_video" in result["error"]
        assert result["platform_results"]["apple_video"]["status"] == "failed"
        assert (
            "thumbnail dimensions mismatch"
            in result["platform_results"]["apple_video"]["issues"][0]
        )

    def test_thumbnail_compliance_fail_fast_when_required_assets_missing(
        self, tmp_path: Path
    ) -> None:
        """Selected target requiring thumbnails should fail when no generated assets exist."""
        stage = RenderStage(load_config())

        result = stage._enforce_thumbnail_target_compliance(
            job_dir=tmp_path,
            selected_platforms=["youtube"],
            thumbnail_result={"status": "skipped", "thumbnail_paths": []},
        )

        assert result["status"] == "failed"
        assert "no generated thumbnail assets" in result["error"]
        assert result["platform_results"]["youtube"]["status"] == "failed"


class TestPhase6ScopeBoundary:
    """Tests that lock enhancement-only behavior for Phase 6."""

    def test_phase6_scope_boundary_blocks_edit_core_filter_names(self) -> None:
        """Enhancement chain must not include edit-core transition filters."""
        stage = RenderStage(load_config())

        filters = stage._build_audio_enhancement_filters()

        assert all("acrossfade" not in item for item in filters)
        assert all("xfade" not in item for item in filters)

    def test_enhancement_disabled_noop_for_phase6_optional_filters(self) -> None:
        """Disabled Phase 6 enhancement toggles should add no optional filters."""
        config = load_config()
        config.enhancements.deesser.enabled = False
        config.enhancements.deesser.click_safety_enabled = False
        config.enhancements.color_correction.enabled = False
        stage = RenderStage(config)

        filters = stage._build_audio_enhancement_filters()
        required = stage._required_enhancement_filters()

        assert all("deesser" not in item for item in filters)
        assert all("adeclick" not in item for item in filters)
        assert "normalize" not in required
        assert "grayworld" not in required
        assert "eq" not in required


class TestRenderDereverbPath:
    """Tests for optional noisereduce-backed dereverb preprocessing."""

    def test_dereverb_disabled_returns_original_input(self, tmp_path: Path) -> None:
        """Disabled dereverb should not alter render input path."""
        config = load_config()
        config.enhancements.dereverb.enabled = False
        stage = RenderStage(config)
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        prepared = stage._prepare_optional_dereverb_input(
            input_video=input_video,
            output_dir=output_dir,
            platform="youtube",
        )

        assert prepared == input_video

    def test_dereverb_noisereduce_missing_warn_skip_fallback(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Missing noisereduce should safely skip dereverb when fallback is warn_skip."""
        config = load_config()
        config.enhancements.dereverb.enabled = True
        config.enhancements.dereverb.fallback_mode = "warn_skip"
        stage = RenderStage(config)
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.importlib.import_module",
            lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("noisereduce")),
        )

        prepared = stage._prepare_optional_dereverb_input(
            input_video=input_video,
            output_dir=output_dir,
            platform="youtube",
        )

        assert prepared == input_video

    def test_dereverb_noisereduce_missing_fail_fallback_raises(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Missing noisereduce should raise when fallback policy is fail."""
        config = load_config()
        config.enhancements.dereverb.enabled = True
        config.enhancements.dereverb.fallback_mode = "fail"
        stage = RenderStage(config)
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.importlib.import_module",
            lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("noisereduce")),
        )

        with pytest.raises(RuntimeError, match="noisereduce"):
            stage._prepare_optional_dereverb_input(
                input_video=input_video,
                output_dir=output_dir,
                platform="youtube",
            )


class TestAudioEnhancementGuardrails:
    """Regression tests for audio enhancement behavior across platform paths."""

    def test_audio_enhancement_ordering_keeps_deesser_before_limiter(self) -> None:
        """De-esser should remain upstream of compressor/limiter in enhancement ordering."""
        stage = RenderStage(load_config())

        filters = stage._build_audio_enhancement_filters()
        deesser_idx = next(i for i, item in enumerate(filters) if item.startswith("deesser="))
        compressor_idx = next(
            i for i, item in enumerate(filters) if item.startswith("acompressor=")
        )
        limiter_idx = next(i for i, item in enumerate(filters) if item.startswith("alimiter="))

        assert deesser_idx < compressor_idx < limiter_idx

    def test_audio_enhancement_no_op_when_optional_paths_disabled(self) -> None:
        """Optional enhancement toggles should not inject phase-6-only filters when disabled."""
        config = load_config()
        config.audio.noise_reduction = "off"
        config.enhancements.deesser.enabled = False
        config.enhancements.deesser.click_safety_enabled = False
        stage = RenderStage(config)

        filters = stage._build_audio_enhancement_filters()

        assert all("afftdn" not in item for item in filters)
        assert all("deesser" not in item for item in filters)
        assert all("adeclick" not in item for item in filters)
        assert any(item.startswith("acompressor=") for item in filters)
        assert any(item.startswith("alimiter=") for item in filters)

    def test_audio_enhancement_platform_safe_uses_prepared_input_path(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Render platform dispatch should consume dereverb-prepared input when provided."""
        config = load_config()
        stage = RenderStage(config)
        prepared_input = tmp_path / "prepared.mkv"
        prepared_input.write_bytes(b"prepared")
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"raw")
        captured: dict[str, Path] = {}

        monkeypatch.setattr(
            stage,
            "_prepare_optional_dereverb_input",
            lambda **_kwargs: prepared_input,
        )

        def _fake_render_video(
            _output_dir: Path,
            render_input_video: Path,
            *_args,
            **_kwargs,
        ) -> list[str]:
            captured["input"] = render_input_video
            return ["output/youtube/final.mp4"]

        monkeypatch.setattr(stage, "_render_video", _fake_render_video)

        outputs = stage._render_platform(
            job_dir=tmp_path,
            input_video=input_video,
            platform="youtube",
            spec=config.platforms.youtube,
            decisions=ReviewDecisions(review_complete=True),
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        assert outputs == ["output/youtube/final.mp4"]
        assert captured["input"] == prepared_input


class TestRenderColorCorrection:
    """Tests for optional canonical FFmpeg color correction filters."""

    def test_color_correction_normalize_and_grayworld_filters_when_enabled(self) -> None:
        """Enabled color correction should emit canonical normalize + grayworld filters."""
        config = load_config()
        config.enhancements.color_correction.enabled = True
        stage = RenderStage(config)

        filters = stage._build_color_correction_filters()

        assert any(item.startswith("normalize") for item in filters)
        assert any(item.startswith("grayworld") for item in filters)

    def test_color_correction_eq_filter_is_optional(self) -> None:
        """EQ filter should only be emitted when eq toggle is enabled."""
        config = load_config()
        config.enhancements.color_correction.enabled = True
        config.enhancements.color_correction.eq_enabled = True
        stage = RenderStage(config)

        filters = stage._build_color_correction_filters()

        assert any(item.startswith("eq=") for item in filters)

    def test_color_correction_filters_wired_into_render_video(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Render video command should include color filters when color correction is enabled."""
        config = load_config()
        config.enhancements.color_correction.enabled = True
        stage = RenderStage(config)
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")
        output_dir = tmp_path / "output"
        captured: dict[str, list[str]] = {}

        def _fake_ffmpeg(args: list[str]) -> None:
            captured["args"] = args
            output_file = Path(args[-1])
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"rendered")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)
        monkeypatch.setattr(stage, "_validate_video_platform_compliance", lambda *_a, **_k: None)

        stage._render_video(
            output_dir=output_dir,
            input_video=input_video,
            platform="youtube",
            spec=config.platforms.youtube,
            decisions=ReviewDecisions(review_complete=True),
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        args = captured["args"]
        assert "-vf" in args
        vf_filter = args[args.index("-vf") + 1]
        assert "normalize" in vf_filter
        assert "grayworld" in vf_filter

    def test_color_disabled_noop_returns_no_color_filters(self) -> None:
        """Disabled color correction should produce no additional color filters."""
        config = load_config()
        config.enhancements.color_correction.enabled = False
        stage = RenderStage(config)

        assert stage._build_color_correction_filters() == []

    def test_color_canonical_filters_exclude_legacy_filter_names(self) -> None:
        """Color correction should use only canonical normalize/grayworld/eq filters."""
        config = load_config()
        config.enhancements.color_correction.enabled = True
        config.enhancements.color_correction.eq_enabled = True
        stage = RenderStage(config)

        filters = stage._build_color_correction_filters()
        rendered = ",".join(filters)

        assert "autowhite" not in rendered
        assert "autolevels" not in rendered
        assert "normalize" in rendered
        assert "grayworld" in rendered

    def test_color_no_edit_graph_impact_when_enabled(self) -> None:
        """Color filters should not alter trim/concat edit graph structure."""
        edit_plan = EditPlan(
            filler_cuts=[FillerCutRange(start_seconds=1.0, end_seconds=2.0, word="um")]
        )
        baseline = RenderStage(load_config())
        color_config = load_config()
        color_config.enhancements.color_correction.enabled = True
        color_enabled = RenderStage(color_config)

        vf_baseline = baseline._build_video_filters(
            1920, 1080, 1920, 1080, baseline.config.platforms.youtube
        )
        vf_color = color_enabled._build_video_filters(
            1920,
            1080,
            1920,
            1080,
            color_enabled.config.platforms.youtube,
        )
        base_filter = baseline._build_edit_plan_filter(edit_plan, 10.0, vf_baseline, [])
        color_filter = color_enabled._build_edit_plan_filter(edit_plan, 10.0, vf_color, [])

        assert base_filter is not None
        assert color_filter is not None
        assert base_filter[0].count("trim=start=") == color_filter[0].count("trim=start=")
        assert base_filter[0].count("atrim=start=") == color_filter[0].count("atrim=start=")
        assert "concat=n=2:v=1:a=0" in base_filter[0]
        assert "concat=n=2:v=0:a=1" in base_filter[0]
        assert "concat=n=2:v=1:a=0" in color_filter[0]
        assert "concat=n=2:v=0:a=1" in color_filter[0]


class TestRenderEditPlanSmoothing:
    """Tests for snapped cuts and transition-aware edit-plan filter construction."""

    def test_edit_plan_filter_micro_fade_applies_to_trimmed_segments(self, monkeypatch) -> None:
        """All keep segments should receive edge micro fades."""
        stage = RenderStage(load_config())
        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": False, "xfade": False},
        )
        edit_plan = EditPlan(
            filler_cuts=[FillerCutRange(start_seconds=1.0, end_seconds=2.0, word="um")]
        )

        rendered = stage._build_edit_plan_filter(edit_plan, 10.0, [], [])

        assert rendered is not None
        filter_complex = rendered[0]
        assert "afade=t=in" in filter_complex
        assert "afade=t=out" in filter_complex

    def test_edit_plan_filter_acrossfade_applies_for_content_join(self, monkeypatch) -> None:
        """Content joins should use acrossfade when filter support is available."""
        stage = RenderStage(load_config())
        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": True, "xfade": False},
        )
        edit_plan = EditPlan(
            content_cuts=[{"start_seconds": 2.0, "end_seconds": 3.0, "reason": "tangent"}]
        )

        rendered = stage._build_edit_plan_filter(edit_plan, 8.0, [], [])

        assert rendered is not None
        assert "acrossfade=" in rendered[0]

    def test_edit_plan_filter_xfade_applies_with_normalization_for_content_join(
        self,
        monkeypatch,
    ) -> None:
        """Content joins should use normalized xfade path when available."""
        stage = RenderStage(load_config())
        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": False, "xfade": True},
        )
        edit_plan = EditPlan(
            content_cuts=[{"start_seconds": 2.0, "end_seconds": 3.0, "reason": "tangent"}]
        )

        rendered = stage._build_edit_plan_filter(edit_plan, 8.0, [], [])

        assert rendered is not None
        assert "xfade=transition=fade" in rendered[0]
        assert "fps=30" in rendered[0]
        assert "settb=AVTB" in rendered[0]

    def test_edit_plan_filter_clamp_limits_short_segment_transition_duration(
        self,
        monkeypatch,
    ) -> None:
        """Short adjacent keep segments should clamp heavy transition durations."""
        config = load_config()
        config.smoothing.content_audio_crossfade_ms = 300.0
        config.smoothing.join_clamp_ratio = 0.35
        stage = RenderStage(config)
        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": True, "xfade": False},
        )
        edit_plan = EditPlan(
            content_cuts=[{"start_seconds": 0.2, "end_seconds": 0.4, "reason": "pause"}]
        )

        rendered = stage._build_edit_plan_filter(edit_plan, 1.0, [], [])

        assert rendered is not None
        assert "acrossfade=d=0.070" in rendered[0]

    def test_edit_plan_filter_transition_filler_only_skips_heavy_transitions(
        self,
        monkeypatch,
    ) -> None:
        """Filler-only joins should not apply content-grade acrossfade/xfade transitions."""
        stage = RenderStage(load_config())
        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": True, "xfade": True},
        )
        edit_plan = EditPlan(filler_cuts=[{"start_seconds": 1.0, "end_seconds": 1.4, "word": "um"}])

        rendered = stage._build_edit_plan_filter(edit_plan, 5.0, [], [])

        assert rendered is not None
        assert "acrossfade=" not in rendered[0]
        assert "xfade=" not in rendered[0]

    def test_edit_plan_filter_timestamp_reset_applied_for_each_segment(self, monkeypatch) -> None:
        """Trimmed segments should always reset timestamps before join logic."""
        stage = RenderStage(load_config())
        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": False, "xfade": False},
        )
        edit_plan = EditPlan(
            content_cuts=[{"start_seconds": 2.0, "end_seconds": 3.0, "reason": "tangent"}]
        )

        rendered = stage._build_edit_plan_filter(edit_plan, 8.0, [], [])

        assert rendered is not None
        assert rendered[0].count("setpts=PTS-STARTPTS") >= 2
        assert rendered[0].count("asetpts=PTS-STARTPTS") >= 2

    def test_phase6_transition_enhancement_order_remains_additive(self, monkeypatch) -> None:
        """Phase 6 enhancement filters should run after transition/join operations."""
        stage = RenderStage(load_config())
        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": True, "xfade": False},
        )
        edit_plan = EditPlan(
            content_cuts=[{"start_seconds": 2.0, "end_seconds": 3.0, "reason": "tangent"}]
        )
        af_filters = stage._build_audio_enhancement_filters()

        rendered = stage._build_edit_plan_filter(edit_plan, 8.0, [], af_filters)

        assert rendered is not None
        transition_index = rendered[0].find("acrossfade=")
        enhancement_index = rendered[0].find("highpass=f=70")
        assert transition_index >= 0
        assert enhancement_index > transition_index

    def test_edit_plan_filter_snap_uses_transcript_word_boundaries(self, monkeypatch) -> None:
        """Cut boundaries should snap to nearby transcript gaps before building trims."""
        stage = RenderStage(load_config())
        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": False, "xfade": False},
        )
        edit_plan = EditPlan(
            filler_cuts=[{"start_seconds": 1.15, "end_seconds": 1.85, "word": "um"}]
        )
        transcript_words = [
            {"word": "we", "start": 0.8, "end": 1.0},
            {"word": "should", "start": 1.2, "end": 1.4},
            {"word": "ship", "start": 1.8, "end": 2.0},
            {"word": "today", "start": 2.2, "end": 2.4},
        ]

        rendered = stage._build_edit_plan_filter(
            edit_plan,
            4.0,
            [],
            [],
            transcript_words=transcript_words,
        )

        assert rendered is not None
        filter_complex = rendered[0]
        assert "trim=start=0.000:end=1.100" in filter_complex
        assert "trim=start=2.100:end=4.000" in filter_complex

    def test_render_legacy_edit_plan_payload_remains_executable(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Legacy edit_plan.json payloads should still build smoothing-aware render filters."""
        stage = RenderStage(load_config())
        review_dir = tmp_path / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "edit_plan.json").write_text(
            json.dumps(
                {
                    "filler_cuts": [
                        {
                            "start_seconds": 1.15,
                            "end_seconds": 1.85,
                            "word": "um",
                        }
                    ],
                    "content_cuts": [
                        {
                            "start_seconds": 3.15,
                            "end_seconds": 3.85,
                            "reason": "off-topic tangent",
                        }
                    ],
                    "clip_ranges": [],
                }
            )
        )

        edit_plan = stage._load_edit_plan(tmp_path)
        assert edit_plan is not None

        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": True, "xfade": False},
        )
        transcript_words = [
            {"word": "we", "start": 0.8, "end": 1.0},
            {"word": "should", "start": 1.2, "end": 1.4},
            {"word": "ship", "start": 1.8, "end": 2.0},
            {"word": "today", "start": 2.2, "end": 2.4},
            {"word": "cut", "start": 2.8, "end": 3.0},
            {"word": "this", "start": 3.2, "end": 3.4},
            {"word": "part", "start": 3.8, "end": 4.0},
        ]

        rendered = stage._build_edit_plan_filter(
            edit_plan,
            7.0,
            [],
            stage._build_audio_enhancement_filters(),
            transcript_words=transcript_words,
        )

        assert rendered is not None
        filter_complex = rendered[0]
        assert "trim=start=0.000:end=1.100" in filter_complex
        assert "trim=start=2.100:end=3.100" in filter_complex
        assert "trim=start=3.850:end=7.000" in filter_complex
        assert "acrossfade=" in filter_complex
        transition_index = filter_complex.find("acrossfade=")
        enhancement_index = filter_complex.find("highpass=f=70")
        assert transition_index >= 0
        assert enhancement_index > transition_index


class TestRenderStatusSemantics:
    """Tests for top-level render status and platform result details."""

    def test_partial_failure_marks_render_failed(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Any required platform failure should fail the render stage."""
        config = load_config()
        stage = RenderStage(config)
        job = _create_review_ready_job(tmp_path, ["youtube", "spotify"])

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.get_video_info",
            lambda _input: {"width": 1920, "height": 1080, "duration": 30.0, "fps": 30.0},
        )
        monkeypatch.setattr(stage, "_generate_marketing_doc", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(stage, "_export_clips", lambda *_args, **_kwargs: [])

        def _fake_render_platform(
            _job_dir: Path,
            _input_video: Path,
            platform: str,
            *_args,
            **_kwargs,
        ) -> list[str]:
            if platform == "youtube":
                raise FFmpegError("simulated ffmpeg failure")
            return [f"output/{platform}/final.mp4"]

        monkeypatch.setattr(stage, "_render_platform", _fake_render_platform)

        result = stage.run(job, tmp_path)

        assert result.success is False
        assert result.data["status"] == "degraded"
        assert "youtube" in (result.error or "")
        assert result.data["platform_results"]["youtube"]["status"] == "failed"
        assert result.data["platform_results"]["spotify"]["status"] == "success"

    def test_platform_status_reports_unsupported_targets(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Unsupported selected platforms should be surfaced as explicit failures."""
        config = load_config()
        stage = RenderStage(config)
        job = _create_review_ready_job(tmp_path, ["unknown_platform"])

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.get_video_info",
            lambda _input: {"width": 1920, "height": 1080, "duration": 30.0, "fps": 30.0},
        )
        monkeypatch.setattr(stage, "_generate_marketing_doc", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(stage, "_export_clips", lambda *_args, **_kwargs: [])

        result = stage.run(job, tmp_path)

        assert result.success is False
        assert result.data["status"] == "failed"
        assert result.data["platform_results"]["unknown_platform"]["status"] == "failed"
        assert (
            "Unsupported platform" in result.data["platform_results"]["unknown_platform"]["error"]
        )


class TestRenderGuardrails:
    """Tests for render preflight and output verification checks."""

    def test_preflight_fails_when_render_disk_space_is_low(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Render should fail early when free space is below preflight requirements."""
        config = load_config()
        stage = RenderStage(config)
        job = _create_review_ready_job(tmp_path, ["youtube"])

        mock_usage = namedtuple("usage", ["total", "used", "free"])
        monkeypatch.setattr(
            "podcast_pipeline.stages.render.shutil.disk_usage",
            lambda _path: mock_usage(total=1024, used=1023, free=1),
        )
        monkeypatch.setattr(
            "podcast_pipeline.stages.render.get_video_info",
            lambda _input: {"width": 1920, "height": 1080, "duration": 30.0, "fps": 30.0},
        )
        monkeypatch.setattr(stage, "_generate_marketing_doc", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(stage, "_export_clips", lambda *_args, **_kwargs: [])

        result = stage.run(job, tmp_path)

        assert result.success is False
        assert "Render preflight failed" in (result.error or "")

    def test_output_exists_missing_platform_file_marks_failure(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Missing FFmpeg output files should fail render with actionable errors."""
        config = load_config()
        stage = RenderStage(config)
        job = _create_review_ready_job(tmp_path, ["youtube"])

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.get_video_info",
            lambda _input: {"width": 1920, "height": 1080, "duration": 30.0, "fps": 30.0},
        )
        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", lambda _args: None)
        monkeypatch.setattr(stage, "_normalize_loudness", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(stage, "_generate_marketing_doc", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(stage, "_export_clips", lambda *_args, **_kwargs: [])

        result = stage.run(job, tmp_path)

        assert result.success is False
        youtube_result = result.data["platform_results"]["youtube"]
        assert youtube_result["status"] == "failed"
        assert "output verification failed" in youtube_result["error"].lower()


class TestRenderComplianceWiring:
    """Tests for profile/level flags and ffprobe-backed compliance validation."""

    def test_profile_flag_and_level_flag_and_gop_keyframe_flags_for_h264(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """H.264 exports should include profile/level and keyframe cadence flags."""
        config = load_config()
        stage = RenderStage(config)
        spec = config.platforms.spotify_video
        output_dir = tmp_path / "output"
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")
        captured: dict[str, list[str]] = {}

        def _fake_ffmpeg(args: list[str]) -> None:
            captured["args"] = args
            output_file = Path(args[-1])
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"rendered")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)
        monkeypatch.setattr(stage, "_validate_video_platform_compliance", lambda *_a, **_k: None)

        stage._render_video(
            output_dir=output_dir,
            input_video=input_video,
            platform="spotify_video",
            spec=spec,
            decisions=ReviewDecisions(review_complete=True),
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        args = captured["args"]
        assert "-profile:v" in args
        assert args[args.index("-profile:v") + 1] == "high"
        assert "-level:v" in args
        assert args[args.index("-level:v") + 1] == "4.1"
        assert "-g" in args
        assert args[args.index("-g") + 1] == "30"
        assert "-keyint_min" in args
        assert args[args.index("-keyint_min") + 1] == "30"

    def test_keyframe_flags_skip_when_codec_not_profile_level_compatible(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Non-H.264/H.265 codecs should skip profile/level and keyframe flags."""
        config = load_config()
        stage = RenderStage(config)
        spec = PlatformSpec(
            container="mp4",
            video_codec="vp9",
            video_bitrate="4M",
            audio_codec="aac",
            audio_bitrate="128k",
            pix_fmt="yuv420p",
            gop=30,
            keyint_min=30,
        )
        output_dir = tmp_path / "output"
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")
        captured: dict[str, list[str]] = {}

        def _fake_ffmpeg(args: list[str]) -> None:
            captured["args"] = args
            output_file = Path(args[-1])
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"rendered")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)
        monkeypatch.setattr(stage, "_validate_video_platform_compliance", lambda *_a, **_k: None)

        stage._render_video(
            output_dir=output_dir,
            input_video=input_video,
            platform="youtube",
            spec=spec,
            decisions=ReviewDecisions(review_complete=True),
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        args = captured["args"]
        assert "-profile:v" not in args
        assert "-level:v" not in args
        assert "-g" not in args
        assert "-keyint_min" not in args

    def test_spotify_video_compliance_topology_and_duration_parity_pass(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Valid Spotify probe output should pass topology and duration checks."""
        config = load_config()
        stage = RenderStage(config)

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffprobe",
            lambda _path: {
                "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "60.0"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "profile": "High",
                        "level": 41,
                        "pix_fmt": "yuv420p",
                        "duration": "60.0",
                        "start_time": "0.0",
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "duration": "60.02",
                        "start_time": "0.0",
                    },
                ],
            },
        )

        stage._validate_video_platform_compliance(
            platform="spotify_video",
            output_file=tmp_path / "final.mp4",
            spec=config.platforms.spotify_video,
        )

    def test_spotify_video_compliance_fails_topology(self, tmp_path: Path, monkeypatch) -> None:
        """Spotify validation should fail when expected stream topology is missing."""
        config = load_config()
        stage = RenderStage(config)

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffprobe",
            lambda _path: {
                "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "60.0"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "profile": "High",
                        "level": 41,
                        "pix_fmt": "yuv420p",
                        "duration": "60.0",
                    }
                ],
            },
        )

        with pytest.raises(PlatformComplianceError, match="topology"):
            stage._validate_video_platform_compliance(
                platform="spotify_video",
                output_file=tmp_path / "final.mp4",
                spec=config.platforms.spotify_video,
            )

    def test_spotify_video_duration_parity_compliance_fails(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Spotify validation should fail when audio/video durations diverge."""
        config = load_config()
        stage = RenderStage(config)

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffprobe",
            lambda _path: {
                "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "60.0"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "profile": "High",
                        "level": 41,
                        "pix_fmt": "yuv420p",
                        "duration": "60.0",
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "duration": "58.9",
                    },
                ],
            },
        )

        with pytest.raises(PlatformComplianceError, match="duration parity"):
            stage._validate_video_platform_compliance(
                platform="spotify_video",
                output_file=tmp_path / "final.mp4",
                spec=config.platforms.spotify_video,
            )

    def test_apple_video_compliance_accepts_mp4_topology(self, tmp_path: Path, monkeypatch) -> None:
        """Apple video compliance should pass for valid mp4 topology and metadata."""
        config = load_config()
        stage = RenderStage(config)

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffprobe",
            lambda _path: {
                "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "30.0"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "profile": "High",
                        "level": 40,
                        "pix_fmt": "yuv420p",
                        "duration": "30.0",
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "duration": "30.0",
                    },
                ],
            },
        )

        stage._validate_video_platform_compliance(
            platform="apple_video",
            output_file=tmp_path / "final.mp4",
            spec=config.platforms.apple_video,
        )

    def test_apple_video_compliance_rejects_non_mp4_container(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Apple video compliance should reject non mp4/mov outputs."""
        config = load_config()
        stage = RenderStage(config)

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffprobe",
            lambda _path: {
                "format": {"format_name": "matroska,webm", "duration": "30.0"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "profile": "High",
                        "level": 40,
                        "pix_fmt": "yuv420p",
                        "duration": "30.0",
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "duration": "30.0",
                    },
                ],
            },
        )

        with pytest.raises(PlatformComplianceError, match="container mismatch"):
            stage._validate_video_platform_compliance(
                platform="apple_video",
                output_file=tmp_path / "final.mp4",
                spec=config.platforms.apple_video,
            )


class TestRenderLoudnessBitratePreservation:
    """Tests for keeping configured audio codec/bitrate during loudness normalization."""

    def test_render_video_passes_audio_codec_and_bitrate_to_loudness_normalization(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Video render should pass platform codec/bitrate into normalization step."""
        config = load_config()
        stage = RenderStage(config)
        spec = config.platforms.spotify_video
        output_dir = tmp_path / "output"
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")
        captured: dict[str, Any] = {}

        def _fake_ffmpeg(args: list[str]) -> None:
            output_file = Path(args[-1])
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"rendered")

        def _fake_normalize(
            _audio_file: Path,
            _target_lufs: float,
            *,
            audio_codec: str | None = None,
            audio_bitrate: str | None = None,
        ) -> dict[str, Any]:
            captured["audio_codec"] = audio_codec
            captured["audio_bitrate"] = audio_bitrate
            return {"status": "normalized", "method": "test"}

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)
        monkeypatch.setattr(stage, "_normalize_loudness", _fake_normalize)
        monkeypatch.setattr(stage, "_validate_video_platform_compliance", lambda *_a, **_k: None)

        stage._render_video(
            output_dir=output_dir,
            input_video=input_video,
            platform="spotify_video",
            spec=spec,
            decisions=ReviewDecisions(review_complete=True),
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=True,
        )

        assert captured["audio_codec"] == spec.audio_codec
        assert captured["audio_bitrate"] == spec.audio_bitrate

    def test_ffmpeg_fallback_uses_requested_audio_codec_and_bitrate_for_video(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """ffmpeg fallback should preserve configured codec/bitrate for video remux."""
        config = load_config()
        stage = RenderStage(config)
        input_video = tmp_path / "final.mp4"
        input_video.write_bytes(b"video")
        captured_args: dict[str, list[str]] = {}

        def _fake_ffmpeg(args: list[str]) -> None:
            captured_args["args"] = args
            output_file = Path(args[-1])
            output_file.write_bytes(b"normalized-video")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)

        ok = stage._normalize_loudness_with_ffmpeg(
            input_video,
            target_lufs=-14.0,
            audio_codec="aac",
            audio_bitrate="192k",
        )

        assert ok is True
        args = captured_args["args"]
        assert "-c:a" in args
        assert args[args.index("-c:a") + 1] == "aac"
        assert "-b:a" in args
        assert args[args.index("-b:a") + 1] == "192k"

    def test_platform_status_includes_validation_details_for_compliance_error(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Compliance failures should propagate with structured validation details."""
        config = load_config()
        stage = RenderStage(config)
        job = _create_review_ready_job(tmp_path, ["spotify_video"])

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.get_video_info",
            lambda _input: {"width": 1920, "height": 1080, "duration": 30.0, "fps": 30.0},
        )
        monkeypatch.setattr(stage, "_generate_marketing_doc", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(stage, "_export_clips", lambda *_args, **_kwargs: [])

        def _raise_compliance_error(
            _job_dir: Path,
            _input_video: Path,
            _platform: str,
            *_args,
            **_kwargs,
        ) -> list[str]:
            raise PlatformComplianceError(
                platform="spotify_video",
                issues=["duration parity check failed"],
                warnings=["possible EDL risk"],
            )

        monkeypatch.setattr(stage, "_render_platform", _raise_compliance_error)

        result = stage.run(job, tmp_path)

        assert result.success is False
        platform_result = result.data["platform_results"]["spotify_video"]
        assert platform_result["status"] == "failed"
        assert platform_result["error_type"] == "compliance_error"
        assert "compliance validation failed" in platform_result["error"]
        assert platform_result["validation"]["issues"] == ["duration parity check failed"]
        assert platform_result["validation"]["warnings"] == ["possible EDL risk"]


class TestRenderHLSArtifacts:
    """Tests for apple_hls rendering and playlist integrity validation."""

    def test_render_hls_writes_master_playlist_and_variant_playlist(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """HLS render should require and validate master + variant + segment artifacts."""
        config = load_config()
        stage = RenderStage(config)
        spec = config.platforms.apple_hls
        output_dir = tmp_path / "output" / "apple_hls"
        output_dir.mkdir(parents=True, exist_ok=True)
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")

        def _fake_ffmpeg(args: list[str]) -> None:
            assert "-f" in args
            assert args[args.index("-f") + 1] == "hls"
            assert "-master_pl_name" in args
            assert "-var_stream_map" in args

            (output_dir / "master.m3u8").write_text(
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-VERSION:3",
                        "#EXT-X-STREAM-INF:BANDWIDTH=1200000",
                        "variant_0.m3u8",
                    ]
                )
            )
            (output_dir / "variant_0.m3u8").write_text(
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:6",
                        "#EXTINF:6.0,",
                        "segment_0_000.ts",
                    ]
                )
            )
            (output_dir / "segment_0_000.ts").write_bytes(b"segment-data")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)

        outputs = stage._render_hls(
            output_dir=output_dir,
            input_video=input_video,
            platform="apple_hls",
            spec=spec,
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        assert "output/apple_hls/master.m3u8" in outputs
        assert "output/apple_hls/variant_0.m3u8" in outputs
        assert "output/apple_hls/segment_0_000.ts" in outputs

    def test_master_playlist_validation_fails_when_variant_playlist_missing(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Master playlist validation should fail when referenced variant is missing."""
        config = load_config()
        stage = RenderStage(config)
        spec = config.platforms.apple_hls
        output_dir = tmp_path / "output" / "apple_hls"
        output_dir.mkdir(parents=True, exist_ok=True)
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")

        def _fake_ffmpeg(_args: list[str]) -> None:
            (output_dir / "master.m3u8").write_text(
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-STREAM-INF:BANDWIDTH=1200000",
                        "variant_0.m3u8",
                    ]
                )
            )

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)

        with pytest.raises((FileNotFoundError, RuntimeError), match="variant playlist"):
            stage._render_hls(
                output_dir=output_dir,
                input_video=input_video,
                platform="apple_hls",
                spec=spec,
                video_info={"width": 1920, "height": 1080, "duration": 30.0},
                edit_plan=None,
                normalize_audio=False,
            )

    def test_render_hls_rejects_unsafe_segment_template(self, tmp_path: Path) -> None:
        """Runtime must reject unsafe templates even if model validation is bypassed."""
        config = load_config()
        stage = RenderStage(config)
        spec = config.platforms.apple_hls.model_copy(deep=True)
        assert spec.hls is not None
        spec.hls.segment_filename_pattern = "../segment_%v_%03d.ts"

        output_dir = tmp_path / "output" / "apple_hls"
        output_dir.mkdir(parents=True, exist_ok=True)
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"video")

        with pytest.raises(ValueError, match="segment_filename_pattern"):
            stage._render_hls(
                output_dir=output_dir,
                input_video=input_video,
                platform="apple_hls",
                spec=spec,
                video_info={"width": 1920, "height": 1080, "duration": 30.0},
                edit_plan=None,
                normalize_audio=False,
            )

    def test_validate_hls_artifacts_rejects_variant_path_traversal(self, tmp_path: Path) -> None:
        """Playlist references that escape output_dir must fail validation."""
        config = load_config()
        stage = RenderStage(config)
        spec = config.platforms.apple_hls
        output_dir = tmp_path / "output" / "apple_hls"
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "master.m3u8").write_text(
            "\n".join(
                [
                    "#EXTM3U",
                    "#EXT-X-STREAM-INF:BANDWIDTH=1200000",
                    "variant_0.m3u8",
                ]
            )
        )
        (output_dir / "variant_0.m3u8").write_text(
            "\n".join(
                [
                    "#EXTM3U",
                    "#EXTINF:6.0,",
                    "../segment_0_000.ts",
                ]
            )
        )

        with pytest.raises(RuntimeError, match=r"path traversal|escapes output directory"):
            stage._validate_hls_artifacts(output_dir=output_dir, platform="apple_hls", spec=spec)


class TestVideoWorkflowDocs:
    """Tests for operator-facing workflow boundary documentation."""

    def test_readme_documents_apple_video_and_apple_hls_boundaries(self) -> None:
        """README should clearly separate artifact generation from publication workflows."""
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text().lower()

        assert "apple_video" in readme
        assert "apple_hls" in readme
        assert "provider-mediated" in readme
        assert "hosted vs non-hosted" in readme
        assert "subscriptions remain audio-only" in readme
        assert "does not perform direct platform upload automation" in readme


# ---------------------------------------------------------------------------
# Phase 8 Regression Tests: disabled passes = Phase 7 baseline
# ---------------------------------------------------------------------------


class TestPhase8PassesDisabledRegression:
    """Regression tests verifying that disabled Phase 8 passes don't affect behavior."""

    def test_render_skips_debreathing_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detect_breath_extension must never be called when de_breathing_enabled=False."""
        from podcast_pipeline.config.settings import SmoothingConfig
        from podcast_pipeline.utils import vad as vad_module

        vad_called = {"count": 0}

        def _spy_detect_breath(*args: Any, **kwargs: Any) -> float:
            vad_called["count"] += 1
            return 0.05  # Would return a non-zero value if called

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.detect_breath_extension",
            _spy_detect_breath,
        )
        monkeypatch.setattr(vad_module, "_vad_model", None)

        config = load_config()
        config.smoothing = SmoothingConfig(de_breathing_enabled=False)
        stage = RenderStage(config)

        # Build a simple filler-cut filter with de-breathing disabled.
        # The _apply_de_breathing_pass is called by _build_edit_plan_filter.
        # With de_breathing_enabled=False it should not call detect_breath_extension.
        edit_plan = EditPlan(
            filler_cuts=[
                FillerCutRange(start_seconds=1.0, end_seconds=1.5, word="um"),
            ],
            content_cuts=[],
            clip_ranges=[],
        )

        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": False, "xfade": False},
        )

        stage._build_edit_plan_filter(
            edit_plan,
            5.0,
            [],
            [],
            transcript_words=[],
        )

        assert vad_called["count"] == 0, (
            "detect_breath_extension should not be called when de_breathing_enabled=False"
        )

    def test_render_skips_noise_floor_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """measure_rms_db must never be called when noise_floor_match_enabled=False."""
        from podcast_pipeline.config.settings import SmoothingConfig

        rms_called = {"count": 0}

        def _spy_measure_rms(*args: Any, **kwargs: Any) -> float:
            rms_called["count"] += 1
            return -20.0  # Would return a value if called

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.measure_rms_db",
            _spy_measure_rms,
        )

        config = load_config()
        config.smoothing = SmoothingConfig(noise_floor_match_enabled=False)
        stage = RenderStage(config)

        edit_plan = EditPlan(
            filler_cuts=[
                FillerCutRange(start_seconds=1.0, end_seconds=1.5, word="um"),
            ],
            content_cuts=[],
            clip_ranges=[],
        )

        monkeypatch.setattr(
            stage,
            "_resolve_transition_filter_availability",
            lambda *, needs_content_transitions: {"acrossfade": False, "xfade": False},
        )

        stage._build_edit_plan_filter(
            edit_plan,
            5.0,
            [],
            [],
            transcript_words=[],
        )

        assert rms_called["count"] == 0, (
            "measure_rms_db should not be called when noise_floor_match_enabled=False"
        )

    def test_render_skips_pose_match_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """scan_best_frame_pair must never be called when pose_match_enabled=False."""
        from podcast_pipeline.config.settings import SmoothingConfig

        pose_called = {"count": 0}

        def _spy_scan_best_frame_pair(*args: Any, **kwargs: Any) -> tuple[int, int, float]:
            pose_called["count"] += 1
            return 0, 0, float("inf")

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.scan_best_frame_pair",
            _spy_scan_best_frame_pair,
        )

        config = load_config()
        config.smoothing = SmoothingConfig(pose_match_enabled=False)
        stage = RenderStage(config)

        # _apply_pose_match_pass(keep_ranges, join_kinds, video_path) returns early
        # when pose_match_enabled=False, never calling scan_best_frame_pair.
        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"fake-video")

        keep_ranges: list[tuple[float, float]] = [(0.0, 1.0), (2.0, 5.0)]
        join_kinds: list[Any] = ["content"]

        result_ranges, result_kinds, bridge_clips = stage._apply_pose_match_pass(
            keep_ranges,
            join_kinds,
            input_video,
        )

        assert pose_called["count"] == 0, (
            "scan_best_frame_pair should not be called when pose_match_enabled=False"
        )
        # Unchanged output when disabled
        assert result_ranges == keep_ranges
        assert result_kinds == join_kinds
        assert bridge_clips == {}

    def test_smoothing_config_all_phase8_disabled_preserves_phase7_fields(
        self,
    ) -> None:
        """Disabling all Phase 8 features must not alter Phase 7 smoothing fields."""
        from podcast_pipeline.config.settings import SmoothingConfig

        phase7_defaults = SmoothingConfig()
        phase8_disabled = SmoothingConfig(
            de_breathing_enabled=False,
            noise_floor_match_enabled=False,
            pose_match_enabled=False,
            rife_enabled=False,
        )

        # Phase 7 fields must be identical
        assert phase8_disabled.enabled == phase7_defaults.enabled
        assert phase8_disabled.micro_fade_ms == phase7_defaults.micro_fade_ms
        assert (
            phase8_disabled.content_audio_crossfade_ms == phase7_defaults.content_audio_crossfade_ms
        )
        assert (
            phase8_disabled.content_video_dissolve_ms == phase7_defaults.content_video_dissolve_ms
        )
        assert phase8_disabled.max_snap_shift_ms == phase7_defaults.max_snap_shift_ms
        assert phase8_disabled.join_clamp_ratio == phase7_defaults.join_clamp_ratio
        assert (
            phase8_disabled.require_transition_filters == phase7_defaults.require_transition_filters
        )

    def test_noise_floor_no_correction_below_threshold(self) -> None:
        """compute_noise_floor_correction returns None when delta < threshold."""
        from podcast_pipeline.utils.noise_match import compute_noise_floor_correction

        # delta_db = 2.0 < threshold_db = 3.0 -> no correction
        result = compute_noise_floor_correction(-20.0, -22.0, threshold_db=3.0)
        assert result is None

    def test_noise_floor_correction_applied_above_threshold(self) -> None:
        """compute_noise_floor_correction returns a volume filter when delta >= threshold."""
        from podcast_pipeline.utils.noise_match import compute_noise_floor_correction

        # delta_db = 5.0 > threshold_db = 3.0 -> correction applied
        result = compute_noise_floor_correction(-20.0, -25.0, threshold_db=3.0)
        assert result is not None
        assert result.startswith("volume=")
        assert "eval=frame" in result

    def test_noise_floor_exact_threshold_applies_correction(self) -> None:
        """compute_noise_floor_correction uses strict less-than: exactly at threshold = correction applied.

        The guard is `if delta_db < threshold_db: return None`.
        At delta_db == threshold_db, the condition is False so correction IS applied.
        """
        from podcast_pipeline.utils.noise_match import compute_noise_floor_correction

        # delta_db = 3.0 == threshold_db = 3.0 -> NOT less-than -> correction applied
        result = compute_noise_floor_correction(-20.0, -23.0, threshold_db=3.0)
        assert result is not None
        assert result.startswith("volume=")
        assert "eval=frame" in result


# ---------------------------------------------------------------------------
# Phase 9 — HEVC 10-bit, AV1 experimental, NVENC fallback, force_60fps_shortform
# ---------------------------------------------------------------------------


class TestPlatformSpecHevc10bit:
    """Tests for HEVC 10-bit platform profile validation (Phase 9)."""

    def test_platform_spec_hevc_nvenc_main10_p010le_is_valid(self) -> None:
        """hevc_nvenc + main10 + p010le is the canonical NVENC 10-bit HEVC combination."""
        spec = PlatformSpec(
            video_codec="hevc_nvenc",
            video_profile="main10",
            pix_fmt="p010le",
            preset="p7",
        )
        assert spec.video_codec == "hevc_nvenc"
        assert spec.video_profile == "main10"
        assert spec.pix_fmt == "p010le"

    def test_platform_spec_libx265_main10_yuv420p10le_is_valid(self) -> None:
        """libx265 with main10 profile and yuv420p10le pix_fmt is valid for software fallback."""
        spec = PlatformSpec(
            video_codec="libx265",
            video_profile="main10",
            pix_fmt="yuv420p10le",
            preset="slow",
        )
        assert spec.video_codec == "libx265"
        assert spec.video_profile == "main10"
        assert spec.pix_fmt == "yuv420p10le"

    def test_platform_spec_hevc_nvenc_rejects_invalid_pix_fmt(self, tmp_path: Path) -> None:
        """hevc_nvenc does not accept yuv420p10le — only yuv420p or p010le."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  youtube_ultra:",
                    "    video_codec: hevc_nvenc",
                    "    video_profile: main10",
                    "    pix_fmt: yuv420p10le",
                    "    preset: p7",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"pix_fmt|hevc_nvenc|youtube_ultra"):
            load_config(config_path)

    def test_platform_spec_hevc_nvenc_rejects_uhq_preset_with_p010le(self) -> None:
        """hevc_nvenc + p010le + uhq preset is forbidden (known RTX artifact regression)."""
        with pytest.raises(ValueError, match=r"uhq|p010le|hevc_nvenc"):
            PlatformSpec(
                video_codec="hevc_nvenc",
                video_profile="main10",
                pix_fmt="p010le",
                preset="uhq",
            )

    def test_platform_spec_hevc_nvenc_rejects_hq_preset_with_p010le(self) -> None:
        """hevc_nvenc + p010le + hq preset is also forbidden for RTX safety."""
        with pytest.raises(ValueError, match=r"hq|p010le|hevc_nvenc"):
            PlatformSpec(
                video_codec="hevc_nvenc",
                video_profile="main10",
                pix_fmt="p010le",
                preset="hq",
            )

    def test_platform_spec_hevc_nvenc_allows_p7_preset(self) -> None:
        """p7 is the recommended RTX preset for 10-bit HEVC and must be accepted."""
        spec = PlatformSpec(
            video_codec="hevc_nvenc",
            video_profile="main10",
            pix_fmt="p010le",
            preset="p7",
        )
        assert spec.preset == "p7"

    def test_platform_spec_libx265_invalid_profile_rejected(self, tmp_path: Path) -> None:
        """libx265 with an invalid HEVC profile must fail fast."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  youtube_ultra:",
                    "    video_codec: libx265",
                    "    video_profile: high",
                    "    pix_fmt: yuv420p10le",
                    "    preset: slow",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"video_profile|libx265|youtube_ultra"):
            load_config(config_path)

    def test_youtube_ultra_platform_spec_defaults_hevc10_nvenc(self) -> None:
        """youtube_ultra default should express NVENC HEVC 10-bit intent."""
        config = load_config()
        spec = config.platforms.youtube_ultra

        assert spec.video_codec == "hevc_nvenc"
        assert spec.video_profile == "main10"
        assert spec.pix_fmt == "p010le"
        assert spec.preset == "p7"
        assert spec.width == 3840
        assert spec.height == 2160
        assert spec.aspect_ratio == "16:9"

    def test_youtube_ultra_yaml_override_to_software_x265(self, tmp_path: Path) -> None:
        """Operators can override youtube_ultra to use libx265 software fallback explicitly."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  youtube_ultra:",
                    "    video_codec: libx265",
                    "    video_profile: main10",
                    "    pix_fmt: yuv420p10le",
                    "    preset: slow",
                ]
            )
        )

        config = load_config(config_path)
        spec = config.platforms.youtube_ultra

        assert spec.video_codec == "libx265"
        assert spec.video_profile == "main10"
        assert spec.pix_fmt == "yuv420p10le"


class TestPlatformSpecAv1Experimental:
    """Tests for AV1 experimental opt-in gate (Phase 9)."""

    def test_platform_spec_av1_requires_experimental_flag(self) -> None:
        """AV1 codec without av1_experimental=True must be rejected at config validation."""
        with pytest.raises(ValueError, match=r"av1_experimental|libsvtav1|AV1"):
            PlatformSpec(
                video_codec="libsvtav1",
                pix_fmt="yuv420p",
                preset="medium",
            )

    def test_platform_spec_av1_accepted_with_experimental_flag(self) -> None:
        """AV1 with av1_experimental=True must be accepted — explicit operator opt-in."""
        spec = PlatformSpec(
            video_codec="libsvtav1",
            pix_fmt="yuv420p",
            preset="medium",
            av1_experimental=True,
        )
        assert spec.video_codec == "libsvtav1"
        assert spec.av1_experimental is True

    def test_platform_spec_av1_yaml_without_flag_rejected(self, tmp_path: Path) -> None:
        """AV1 codec in YAML without av1_experimental fails at config load."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  youtube_ultra:",
                    "    video_codec: libsvtav1",
                    "    pix_fmt: yuv420p",
                    "    preset: medium",
                ]
            )
        )

        with pytest.raises(ValueError, match=r"av1_experimental|libsvtav1|AV1"):
            load_config(config_path)

    def test_platform_spec_av1_yaml_with_flag_accepted(self, tmp_path: Path) -> None:
        """AV1 codec in YAML with av1_experimental: true loads cleanly."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "platforms:",
                    "  youtube_ultra:",
                    "    video_codec: libsvtav1",
                    "    pix_fmt: yuv420p",
                    "    preset: medium",
                    "    av1_experimental: true",
                ]
            )
        )

        config = load_config(config_path)
        assert config.platforms.youtube_ultra.video_codec == "libsvtav1"
        assert config.platforms.youtube_ultra.av1_experimental is True

    def test_platform_spec_av1_experimental_defaults_false_for_non_av1(self) -> None:
        """Non-AV1 codecs should default av1_experimental=False with no error."""
        spec = PlatformSpec(video_codec="libx264")
        assert spec.av1_experimental is False

        spec2 = PlatformSpec(
            video_codec="hevc_nvenc", video_profile="main10", pix_fmt="p010le", preset="p7"
        )
        assert spec2.av1_experimental is False

    def test_platform_spec_av1_not_default_activated_in_standard_profiles(self) -> None:
        """Standard platform profiles must not silently enable AV1."""
        config = load_config()

        for platform_name in (
            "youtube",
            "tiktok",
            "instagram",
            "linkedin",
            "twitter",
            "facebook",
            "spotify_video",
            "apple_video",
        ):
            spec = getattr(config.platforms, platform_name)
            if not spec.audio_only:
                assert spec.av1_experimental is False, (
                    f"{platform_name} should not have av1_experimental=True"
                )


class TestSmoothingConfigForce60fps:
    """Tests for SmoothingConfig.force_60fps_shortform (Phase 9)."""

    def test_force_60fps_shortform_defaults_false(self) -> None:
        """force_60fps_shortform must default to False — no silent 60fps uplift."""
        from podcast_pipeline.config.settings import SmoothingConfig

        config = SmoothingConfig()
        assert config.force_60fps_shortform is False

    def test_force_60fps_shortform_loaded_from_yaml(self, tmp_path: Path) -> None:
        """force_60fps_shortform should load from YAML when explicitly set."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "smoothing:",
                    "  force_60fps_shortform: true",
                ]
            )
        )

        config = load_config(config_path)
        assert config.smoothing.force_60fps_shortform is True

    def test_force_60fps_shortform_default_config_yaml_is_false(self) -> None:
        """Default config.yaml must keep force_60fps_shortform=false."""
        config = load_config()
        assert config.smoothing.force_60fps_shortform is False

    def test_force_60fps_shortform_coexists_with_phase8_rife_fields(self) -> None:
        """force_60fps_shortform must coexist with existing Phase 8 RIFE fields."""
        from podcast_pipeline.config.settings import SmoothingConfig

        cfg = SmoothingConfig(
            rife_enabled=True,
            rife_script_path="/path/to/rife.py",
            rife_fallback_to_xfade=True,
            force_60fps_shortform=True,
        )
        assert cfg.rife_enabled is True
        assert cfg.force_60fps_shortform is True

    def test_force_60fps_shortform_disabled_when_all_phase8_disabled(self) -> None:
        """Disabling all Phase 8/9 features must include force_60fps_shortform=False."""
        from podcast_pipeline.config.settings import SmoothingConfig

        cfg = SmoothingConfig(
            rife_enabled=False,
            force_60fps_shortform=False,
        )
        assert cfg.force_60fps_shortform is False


# ---------------------------------------------------------------------------
# Phase 9 — Runtime encoder capability and fallback regression tests
# ---------------------------------------------------------------------------


class TestEncoderCapabilityDetection:
    """Regression tests for _resolve_video_encoder NVENC detection branches and fallback."""

    def _make_stage_with_hw(self, **hw_flags: bool) -> RenderStage:
        """Create a RenderStage with injected HardwareEncoderInfo capability flags."""
        from podcast_pipeline.utils.ffmpeg_toolkit import HardwareEncoderInfo

        config = load_config()
        stage = RenderStage(config)
        stage._hw_encoders = HardwareEncoderInfo(**hw_flags)
        return stage

    # --- hevc_nvenc -> libx265 fallback chain ---

    def test_encoder_capability_hevc_nvenc_selects_nvenc_when_gpu_present(self) -> None:
        """When nvenc_hevc=True, _resolve_video_encoder must select hevc_nvenc directly."""
        stage = self._make_stage_with_hw(nvenc_hevc=True)
        spec = PlatformSpec(
            video_codec="hevc_nvenc",
            video_profile="main10",
            pix_fmt="p010le",
            preset="p7",
        )
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube_ultra")

        assert encoder == "hevc_nvenc"
        assert extra_args == []

    def test_encoder_capability_hevc_nvenc_fallback_to_libx265_when_no_gpu(self) -> None:
        """When nvenc_hevc=False, hevc_nvenc request must fall back to libx265."""
        stage = self._make_stage_with_hw(nvenc_hevc=False)
        spec = PlatformSpec(
            video_codec="hevc_nvenc",
            video_profile="main10",
            pix_fmt="p010le",
            preset="p7",
        )
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube_ultra")

        assert encoder == "libx265"
        # Extra args must override pix_fmt from p010le to yuv420p10le for software x265
        assert "-pix_fmt" in extra_args
        pf_idx = extra_args.index("-pix_fmt")
        assert extra_args[pf_idx + 1] == "yuv420p10le"
        # Profile should be passed as x265-params
        assert any("profile=" in arg for arg in extra_args)

    def test_encoder_fallback_x265_uses_yuv420p_when_pix_fmt_is_yuv420p(self) -> None:
        """hevc_nvenc fallback with yuv420p source must keep yuv420p (not upgrade to 10-bit)."""
        stage = self._make_stage_with_hw(nvenc_hevc=False)
        spec = PlatformSpec(
            video_codec="hevc_nvenc",
            video_profile="main",
            pix_fmt="yuv420p",
            preset="medium",
        )
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube_ultra")

        assert encoder == "libx265"
        pf_idx = extra_args.index("-pix_fmt")
        assert extra_args[pf_idx + 1] == "yuv420p"  # NOT 10-bit

    # --- h264_nvenc -> libx264 fallback chain ---

    def test_encoder_capability_h264_nvenc_selects_nvenc_when_gpu_present(self) -> None:
        """When nvenc_h264=True, h264_nvenc spec must select hardware encoder."""
        stage = self._make_stage_with_hw(nvenc_h264=True)
        spec = PlatformSpec(video_codec="h264_nvenc")
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube")

        assert encoder == "h264_nvenc"
        assert extra_args == []

    def test_encoder_capability_h264_nvenc_fallback_to_libx264_when_no_gpu(self) -> None:
        """When nvenc_h264=False, h264_nvenc request must fall back to libx264."""
        stage = self._make_stage_with_hw(nvenc_h264=False)
        spec = PlatformSpec(video_codec="h264_nvenc")
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube")

        assert encoder == "libx264"
        assert extra_args == []

    # --- AV1 experimental path ---

    def test_encoder_capability_av1_with_software_support_logs_and_proceeds(self) -> None:
        """AV1 codec with software_av1=True must be returned verbatim (no fallback)."""
        stage = self._make_stage_with_hw(software_av1=True)
        spec = PlatformSpec(
            video_codec="libsvtav1",
            pix_fmt="yuv420p",
            preset="medium",
            av1_experimental=True,
        )
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube_ultra")

        assert encoder == "libsvtav1"
        assert extra_args == []

    def test_encoder_capability_av1_without_software_support_falls_back_to_libx265(
        self,
    ) -> None:
        """AV1 codec with software_av1=False falls back to libx265."""
        stage = self._make_stage_with_hw(software_av1=False)
        spec = PlatformSpec(
            video_codec="libsvtav1",
            pix_fmt="yuv420p",
            preset="medium",
            av1_experimental=True,
        )
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube_ultra")

        # When AV1 is unavailable, fall back to libx265 to avoid FFmpeg failure
        assert encoder == "libx265"
        assert extra_args == []

    # --- Standard codecs: verbatim pass-through ---

    def test_encoder_capability_libx264_passes_through_unchanged(self) -> None:
        """libx264 must always pass through without hardware lookup."""
        stage = self._make_stage_with_hw()
        spec = PlatformSpec(video_codec="libx264")
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube")

        assert encoder == "libx264"
        assert extra_args == []

    def test_encoder_capability_libx265_passes_through_unchanged_even_with_gpu(self) -> None:
        """Explicit libx265 must bypass the NVENC fallback chain entirely."""
        stage = self._make_stage_with_hw(nvenc_hevc=True)  # GPU available but spec says software
        spec = PlatformSpec(
            video_codec="libx265",
            video_profile="main10",
            pix_fmt="yuv420p10le",
            preset="slow",
        )
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube_ultra")

        # Explicitly configured libx265 must NOT be upgraded to hevc_nvenc
        assert encoder == "libx265"
        assert extra_args == []


class TestShortformVerticalDetection:
    """Regression tests for _is_shortform_vertical platform spec detection."""

    def test_shortform_vertical_detects_tiktok_9_16_aspect(self) -> None:
        """TikTok (9:16) must be identified as short-form vertical."""
        config = load_config()
        stage = RenderStage(config)

        tiktok_spec = PlatformSpec(width=1080, height=1920, aspect_ratio="9:16", max_duration=60)
        assert stage._is_shortform_vertical(tiktok_spec) is True

    def test_shortform_vertical_detects_instagram_9_16_aspect(self) -> None:
        """Instagram Reels (9:16) must also be identified as short-form vertical."""
        config = load_config()
        stage = RenderStage(config)

        instagram_spec = PlatformSpec(width=1080, height=1920, aspect_ratio="9:16", max_duration=90)
        assert stage._is_shortform_vertical(instagram_spec) is True

    def test_shortform_vertical_rejects_youtube_16_9(self) -> None:
        """YouTube (16:9) must NOT be treated as short-form vertical."""
        config = load_config()
        stage = RenderStage(config)

        youtube_spec = PlatformSpec(width=1920, height=1080, aspect_ratio="16:9")
        assert stage._is_shortform_vertical(youtube_spec) is False

    def test_shortform_vertical_rejects_linkedin_square(self) -> None:
        """LinkedIn square (1:1) must NOT trigger short-form uplift."""
        config = load_config()
        stage = RenderStage(config)

        linkedin_spec = PlatformSpec(width=1080, height=1080, aspect_ratio="1:1")
        assert stage._is_shortform_vertical(linkedin_spec) is False

    def test_shortform_vertical_rejects_youtube_ultra_16_9(self) -> None:
        """youtube_ultra (16:9 4K) must NOT be treated as short-form vertical."""
        config = load_config()
        stage = RenderStage(config)

        ultra_spec = PlatformSpec(
            video_codec="hevc_nvenc",
            video_profile="main10",
            pix_fmt="p010le",
            preset="p7",
            width=3840,
            height=2160,
            aspect_ratio="16:9",
        )
        assert stage._is_shortform_vertical(ultra_spec) is False

    def test_shortform_vertical_handles_missing_aspect_ratio(self) -> None:
        """A spec with no aspect_ratio must not be treated as short-form vertical."""
        config = load_config()
        stage = RenderStage(config)

        spec = PlatformSpec(width=1920, height=1080)  # aspect_ratio=None
        assert stage._is_shortform_vertical(spec) is False


class TestForce60fpsShortformGating:
    """Regression tests: force_60fps_shortform only affects 9:16 targets, never long-form."""

    def test_force_60fps_tiktok_and_instagram_are_shortform_targets(self) -> None:
        """TikTok and Instagram spec aspect ratios confirm they are short-form vertical targets."""
        config = load_config()
        stage = RenderStage(config)

        assert stage._is_shortform_vertical(config.platforms.tiktok) is True
        assert stage._is_shortform_vertical(config.platforms.instagram) is True

    def test_force_60fps_longform_exports_always_skipped(self) -> None:
        """_is_shortform_vertical returns False for all non-9:16 platform specs."""
        config = load_config()
        stage = RenderStage(config)

        longform_platforms = ["youtube", "facebook", "twitter", "linkedin", "youtube_ultra"]
        for platform_name in longform_platforms:
            spec = getattr(config.platforms, platform_name, None)
            if spec is None or spec.audio_only:
                continue
            assert stage._is_shortform_vertical(spec) is False, (
                f"{platform_name} should not be treated as short-form vertical"
            )

    def test_force_60fps_rife_unavailable_returns_none(self, tmp_path: Path) -> None:
        """When RIFE script path is empty, _apply_shortform_60fps_rife returns None."""
        config = load_config()
        config.smoothing.rife_script_path = ""  # No RIFE configured
        stage = RenderStage(config)

        input_video = tmp_path / "input.mp4"
        input_video.write_bytes(b"fake")
        output_dir = tmp_path / "out"
        output_dir.mkdir()

        result = stage._apply_shortform_60fps_rife(input_video, output_dir, "tiktok")
        assert result is None  # Graceful fallback when RIFE unavailable

    def test_force_60fps_default_config_does_not_affect_any_platform(self) -> None:
        """With force_60fps_shortform=False (default), no platform is marked for RIFE uplift."""
        config = load_config()
        assert config.smoothing.force_60fps_shortform is False

        stage = RenderStage(config)
        # Gate condition: smoothing.force_60fps_shortform AND rife_enabled AND is_shortform_vertical
        # First check in gate fails immediately — no platforms are processed
        # Confirm: even shortform platforms won't receive uplift
        tiktok_spec = config.platforms.tiktok
        # Gate = False (force_60fps_shortform off) -> no uplift regardless
        gate_passes = (
            config.smoothing.force_60fps_shortform
            and config.smoothing.rife_enabled
            and stage._is_shortform_vertical(tiktok_spec)
        )
        assert gate_passes is False


class TestLegacyPlatformUnaffectedByPhase9Options:
    """Regression suite: enabling Phase 9 options must not affect legacy platform exports."""

    def test_youtube_spec_unchanged_when_phase9_hevc_configured(self) -> None:
        """YouTube spec must remain H.264 even when youtube_ultra HEVC is configured."""
        config = load_config()
        youtube = config.platforms.youtube

        assert youtube.video_codec == "libx264"
        assert youtube.pix_fmt == "yuv420p"
        assert youtube.av1_experimental is False

    def test_tiktok_spec_fps_unchanged_when_force_60fps_disabled(self) -> None:
        """TikTok spec must remain at 30fps when force_60fps_shortform=False."""
        config = load_config()
        assert config.smoothing.force_60fps_shortform is False

        tiktok = config.platforms.tiktok
        assert tiktok.video_codec == "libx264"
        assert tiktok.fps == 30  # Stays at 30fps - no silent uplift

    def test_spotify_video_and_apple_video_unchanged_by_hevc_addition(self) -> None:
        """Compliance video platforms (spotify_video, apple_video) must remain H.264."""
        config = load_config()

        for platform_name in ("spotify_video", "apple_video"):
            spec = getattr(config.platforms, platform_name)
            assert spec.video_codec == "libx264", f"{platform_name} codec changed unexpectedly"
            assert spec.av1_experimental is False
            assert spec.pix_fmt == "yuv420p"

    def test_audio_only_platforms_completely_unaffected_by_phase9(self) -> None:
        """Audio-only platforms (spotify, apple) must be completely unaffected."""
        config = load_config()

        spotify = config.platforms.spotify
        apple = config.platforms.apple

        assert spotify.audio_only is True
        assert apple.audio_only is True
        assert spotify.av1_experimental is False
        assert apple.av1_experimental is False

    def test_resolve_encoder_with_default_libx264_unaffected_by_hevc_capability(self) -> None:
        """libx264 encoder must be selected unchanged regardless of GPU HEVC capability."""
        from podcast_pipeline.utils.ffmpeg_toolkit import HardwareEncoderInfo

        config = load_config()
        stage = RenderStage(config)
        # Even with full NVENC capability, libx264 spec stays as-is
        stage._hw_encoders = HardwareEncoderInfo(nvenc_h264=True, nvenc_hevc=True)

        spec = config.platforms.youtube  # libx264 spec
        encoder, extra_args = stage._resolve_video_encoder(spec, "youtube")

        assert encoder == "libx264"
        assert extra_args == []


class TestCaptionBurnIn:
    """Tests for _burn_captions integration — Task 2 (09-06) and Task 3 regression coverage."""

    def _make_stage_with_captions(self, enabled: bool = True) -> RenderStage:
        """Return a RenderStage with caption burn-in enabled/disabled."""
        config = load_config()
        config.branding.captions.enabled = enabled
        return RenderStage(config)

    def test_caption_burn_missing_alignment_raises_runtime_error(self, tmp_path: Path) -> None:
        """_burn_captions must raise RuntimeError when word_alignment.json is absent."""
        stage = self._make_stage_with_captions(enabled=True)
        spec = load_config().platforms.youtube

        video_path = tmp_path / "output" / "youtube" / "final.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        output_dir = video_path.parent
        # No transcribe/ directory — alignment artifact is absent.

        with pytest.raises(RuntimeError, match=r"word_alignment\.json"):
            stage._burn_captions(
                video_path=video_path,
                output_dir=output_dir,
                job_dir=tmp_path,
                platform="youtube",
                spec=spec,
            )

    def test_caption_burn_produces_captioned_output_file(self, tmp_path: Path, monkeypatch) -> None:
        """_burn_captions must return a captioned video path when alignment exists."""
        import json as _json

        stage = self._make_stage_with_captions(enabled=True)
        spec = load_config().platforms.youtube

        # Create word_alignment.json artifact.
        transcribe_dir = tmp_path / "transcribe"
        transcribe_dir.mkdir(parents=True)
        word_data = {
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.5},
                {"word": "world", "start": 0.6, "end": 1.1},
            ]
        }
        (transcribe_dir / "word_alignment.json").write_text(_json.dumps(word_data))

        video_path = tmp_path / "output" / "youtube" / "final.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        output_dir = video_path.parent

        def _fake_ffmpeg(args: list[str]) -> None:
            """Simulate FFmpeg by writing the output file."""
            out = Path(args[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"captioned-video")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)

        result = stage._burn_captions(
            video_path=video_path,
            output_dir=output_dir,
            job_dir=tmp_path,
            platform="youtube",
            spec=spec,
        )

        assert result is not None
        assert result.exists()
        assert result.name.startswith("captioned")

    def test_caption_burn_ffmpeg_uses_ass_filter(self, tmp_path: Path, monkeypatch) -> None:
        """_burn_captions must pass the ass= filter to FFmpeg for libass rendering."""
        import json as _json

        stage = self._make_stage_with_captions(enabled=True)
        spec = load_config().platforms.youtube

        transcribe_dir = tmp_path / "transcribe"
        transcribe_dir.mkdir(parents=True)
        (transcribe_dir / "word_alignment.json").write_text(
            _json.dumps({"words": [{"word": "test", "start": 0.0, "end": 0.5}]})
        )

        video_path = tmp_path / "output" / "youtube" / "final.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        output_dir = video_path.parent

        captured_args: list[list[str]] = []

        def _capture_ffmpeg(args: list[str]) -> None:
            captured_args.append(list(args))
            out = Path(args[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"captioned")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _capture_ffmpeg)

        stage._burn_captions(
            video_path=video_path,
            output_dir=output_dir,
            job_dir=tmp_path,
            platform="youtube",
            spec=spec,
        )

        assert captured_args, "run_ffmpeg should have been called"
        args = captured_args[0]
        assert "-vf" in args
        vf_idx = args.index("-vf")
        assert "ass=" in args[vf_idx + 1]

    def test_caption_burn_unsupported_aspect_ratio_returns_none(self, tmp_path: Path) -> None:
        """_burn_captions must return None and log warning for unsupported ratios."""
        import json as _json

        stage = self._make_stage_with_captions(enabled=True)
        spec = PlatformSpec(
            container="mp4",
            video_codec="libx264",
            video_bitrate="4M",
            audio_codec="aac",
            audio_bitrate="128k",
            pix_fmt="yuv420p",
            aspect_ratio="4:3",  # not in SUPPORTED_ASPECT_RATIOS
        )

        transcribe_dir = tmp_path / "transcribe"
        transcribe_dir.mkdir(parents=True)
        (transcribe_dir / "word_alignment.json").write_text(
            _json.dumps({"words": [{"word": "hi", "start": 0.0, "end": 0.3}]})
        )

        video_path = tmp_path / "output" / "custom" / "final.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        output_dir = video_path.parent

        result = stage._burn_captions(
            video_path=video_path,
            output_dir=output_dir,
            job_dir=tmp_path,
            platform="custom",
            spec=spec,
        )

        # Unsupported ratio should produce None, not an exception.
        assert result is None

    def test_caption_burn_ffmpeg_failure_raises_runtime_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """FFmpeg libass failure must surface as RuntimeError with actionable message."""
        import json as _json

        stage = self._make_stage_with_captions(enabled=True)
        spec = load_config().platforms.youtube

        transcribe_dir = tmp_path / "transcribe"
        transcribe_dir.mkdir(parents=True)
        (transcribe_dir / "word_alignment.json").write_text(
            _json.dumps({"words": [{"word": "hi", "start": 0.0, "end": 0.3}]})
        )

        video_path = tmp_path / "output" / "youtube" / "final.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        output_dir = video_path.parent

        def _fail_ffmpeg(_args: list[str]) -> None:
            raise FFmpegError("libass not found")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fail_ffmpeg)

        with pytest.raises(RuntimeError, match="Caption burn-in failed"):
            stage._burn_captions(
                video_path=video_path,
                output_dir=output_dir,
                job_dir=tmp_path,
                platform="youtube",
                spec=spec,
            )

    def test_caption_burn_disabled_skips_burn_in_render_video(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """_render_video must skip caption burn when decisions.captions_enabled is False."""
        config = load_config()
        stage = RenderStage(config)
        spec = config.platforms.youtube

        output_dir = tmp_path / "output" / "youtube"
        input_video = tmp_path / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"video")

        burn_calls: list[str] = []

        def _record_burn(*_args: Any, **_kwargs: Any) -> Path | None:
            burn_calls.append("called")
            return None

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffmpeg",
            lambda args: (
                Path(args[-1]).parent.mkdir(parents=True, exist_ok=True)
                or Path(args[-1]).write_bytes(b"rendered")
                or None
            ),
        )
        monkeypatch.setattr(stage, "_burn_captions", _record_burn)
        monkeypatch.setattr(stage, "_normalize_loudness", lambda *_a, **_k: None)
        monkeypatch.setattr(stage, "_validate_video_platform_compliance", lambda *_a, **_k: None)

        stage._render_video(
            output_dir=output_dir,
            input_video=input_video,
            platform="youtube",
            spec=spec,
            decisions=ReviewDecisions(review_complete=True, captions_enabled=False),
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        assert burn_calls == [], "_burn_captions must not be called when captions_enabled=False"

    def test_caption_burn_enabled_calls_burn_in_render_video(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """_render_video must invoke _burn_captions when decisions.captions_enabled is True."""
        config = load_config()
        stage = RenderStage(config)
        spec = config.platforms.youtube

        output_dir = tmp_path / "output" / "youtube"
        input_video = tmp_path / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"video")

        captioned_video = tmp_path / "output" / "youtube" / "captioned.mp4"
        burn_calls: list[str] = []

        def _fake_burn(*_args: Any, **_kwargs: Any) -> Path | None:
            burn_calls.append("called")
            captioned_video.parent.mkdir(parents=True, exist_ok=True)
            captioned_video.write_bytes(b"captioned")
            return captioned_video

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffmpeg",
            lambda args: (
                Path(args[-1]).parent.mkdir(parents=True, exist_ok=True)
                or Path(args[-1]).write_bytes(b"rendered")
                or None
            ),
        )
        monkeypatch.setattr(stage, "_burn_captions", _fake_burn)
        monkeypatch.setattr(stage, "_normalize_loudness", lambda *_a, **_k: None)
        monkeypatch.setattr(stage, "_validate_video_platform_compliance", lambda *_a, **_k: None)

        stage._render_video(
            output_dir=output_dir,
            input_video=input_video,
            platform="youtube",
            spec=spec,
            decisions=ReviewDecisions(review_complete=True, captions_enabled=True),
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        assert len(burn_calls) == 1, (
            "_burn_captions should be called exactly once when captions_enabled=True"
        )

    def test_caption_burn_legacy_alignment_location_discovered(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """_burn_captions should find word_alignment.json in analysis/ if transcribe/ is absent."""
        import json as _json

        stage = self._make_stage_with_captions(enabled=True)
        spec = load_config().platforms.youtube

        # Place alignment only in legacy analysis/ location.
        analysis_dir = tmp_path / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "word_alignment.json").write_text(
            _json.dumps({"words": [{"word": "legacy", "start": 0.0, "end": 0.4}]})
        )

        video_path = tmp_path / "output" / "youtube" / "final.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        output_dir = video_path.parent

        def _fake_ffmpeg(args: list[str]) -> None:
            out = Path(args[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"captioned")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)

        # Should succeed using legacy path — no RuntimeError raised.
        result = stage._burn_captions(
            video_path=video_path,
            output_dir=output_dir,
            job_dir=tmp_path,
            platform="youtube",
            spec=spec,
        )
        assert result is not None

    def test_caption_burn_ass_file_generated_per_aspect_ratio(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """_burn_captions must generate a per-ratio .ass file in the output directory."""
        import json as _json

        stage = self._make_stage_with_captions(enabled=True)
        spec = load_config().platforms.tiktok  # 9:16

        transcribe_dir = tmp_path / "transcribe"
        transcribe_dir.mkdir(parents=True)
        (transcribe_dir / "word_alignment.json").write_text(
            _json.dumps({"words": [{"word": "tiktok", "start": 0.0, "end": 0.5}]})
        )

        video_path = tmp_path / "output" / "tiktok" / "final.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        output_dir = video_path.parent

        def _fake_ffmpeg(args: list[str]) -> None:
            out = Path(args[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"captioned")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_ffmpeg)

        stage._burn_captions(
            video_path=video_path,
            output_dir=output_dir,
            job_dir=tmp_path,
            platform="tiktok",
            spec=spec,
        )

        # ASS file should exist and reflect 9:16 ratio naming.
        ass_files = list(output_dir.glob("*.ass"))
        assert ass_files, "ASS file must be written to output_dir"
        assert any("9_16" in f.name for f in ass_files), "ASS filename should include aspect ratio"


class TestGAP7RenderWiring:
    """GAP-7 regression tests: ReviewDecisions fields must actually affect render output.

    Prior to Phase 09-12, captions_enabled/sound_kit_enabled/branding_profile_name were
    persisted by the UI but silently ignored by render.py.  These tests lock the new
    gating behaviour so it cannot regress.
    """

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_stage() -> RenderStage:
        """Return a RenderStage with default config."""
        return RenderStage(load_config())

    @staticmethod
    def _fake_ffmpeg_writer(args: list[str]) -> None:
        """Simulate FFmpeg by writing empty bytes to the last argument path."""
        out = Path(args[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"rendered")

    def _call_render_video(  # noqa: PLR0913
        self,
        stage: RenderStage,
        monkeypatch: Any,
        tmp_path: Path,
        *,
        decisions: ReviewDecisions,
        mock_mix_stingers: bool = True,
        mock_burn_captions: bool = True,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Call _render_video with mocks; return (stinger_calls, burn_calls)."""
        config = load_config()
        spec = config.platforms.youtube

        input_video = tmp_path / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"video")
        output_dir = tmp_path / "output" / "youtube"

        stinger_calls: list[dict[str, Any]] = []
        burn_calls: list[dict[str, Any]] = []

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffmpeg",
            self._fake_ffmpeg_writer,
        )
        monkeypatch.setattr(stage, "_normalize_loudness", lambda *_a, **_k: None)
        monkeypatch.setattr(stage, "_validate_video_platform_compliance", lambda *_a, **_k: None)

        if mock_mix_stingers:

            def _fake_mix(*_args: Any, **kwargs: Any) -> Path:
                stinger_calls.append(dict(kwargs))
                video = output_dir / "stingered.mp4"
                video.parent.mkdir(parents=True, exist_ok=True)
                video.write_bytes(b"stingered")
                return video

            monkeypatch.setattr(stage, "_mix_stingers", _fake_mix)

        if mock_burn_captions:

            def _fake_burn(*_args: Any, **kwargs: Any) -> Path | None:
                burn_calls.append(dict(kwargs))
                return None

            monkeypatch.setattr(stage, "_burn_captions", _fake_burn)

        stage._render_video(
            output_dir=output_dir,
            input_video=input_video,
            platform="youtube",
            spec=spec,
            decisions=decisions,
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        return stinger_calls, burn_calls

    # ── Tests ──────────────────────────────────────────────────────────────────

    def test_render_video_captions_gate_respects_decisions(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """_burn_captions called when captions_enabled=True; skipped when False."""
        stage = self._make_stage()

        # captions_enabled=True → _burn_captions MUST be called.
        _, burn_calls_on = self._call_render_video(
            stage,
            monkeypatch,
            tmp_path / "on",
            decisions=ReviewDecisions(review_complete=True, captions_enabled=True),
        )
        assert len(burn_calls_on) == 1, "_burn_captions must be called when captions_enabled=True"

        # captions_enabled=False → _burn_captions MUST NOT be called.
        _, burn_calls_off = self._call_render_video(
            stage,
            monkeypatch,
            tmp_path / "off",
            decisions=ReviewDecisions(review_complete=True, captions_enabled=False),
        )
        assert burn_calls_off == [], "_burn_captions must be skipped when captions_enabled=False"

    def test_render_video_sound_kit_gate_respects_decisions(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """_mix_stingers called when sound_kit_enabled=True; skipped when False."""
        stage = self._make_stage()

        # sound_kit_enabled=True → _mix_stingers MUST be called.
        stinger_calls_on, _ = self._call_render_video(
            stage,
            monkeypatch,
            tmp_path / "on",
            decisions=ReviewDecisions(review_complete=True, sound_kit_enabled=True),
        )
        assert len(stinger_calls_on) == 1, (
            "_mix_stingers must be called when sound_kit_enabled=True"
        )

        # sound_kit_enabled=False → _mix_stingers MUST NOT be called.
        stinger_calls_off, _ = self._call_render_video(
            stage,
            monkeypatch,
            tmp_path / "off",
            decisions=ReviewDecisions(review_complete=True, sound_kit_enabled=False),
        )
        assert stinger_calls_off == [], "_mix_stingers must be skipped when sound_kit_enabled=False"

    def test_render_video_branding_profile_override(self, tmp_path: Path, monkeypatch: Any) -> None:
        """decisions.branding_profile_name flows into _burn_captions and _mix_stingers."""
        stage = self._make_stage()

        stinger_calls, burn_calls = self._call_render_video(
            stage,
            monkeypatch,
            tmp_path,
            decisions=ReviewDecisions(
                review_complete=True,
                captions_enabled=True,
                sound_kit_enabled=True,
                branding_profile_name="custom",
            ),
        )

        assert len(stinger_calls) == 1, "_mix_stingers must be called with profile override"
        assert stinger_calls[0].get("profile_name_override") == "custom", (
            "_mix_stingers must receive profile_name_override='custom'"
        )

        assert len(burn_calls) == 1, "_burn_captions must be called with profile override"
        assert burn_calls[0].get("profile_name_override") == "custom", (
            "_burn_captions must receive profile_name_override='custom'"
        )

    def test_burn_captions_aspect_ratio_override(self, tmp_path: Path, monkeypatch: Any) -> None:
        """_burn_captions uses aspect_ratio_override when provided, ignoring spec.aspect_ratio."""
        import json as _json

        stage = self._make_stage()
        config = load_config()
        spec = config.platforms.youtube  # spec has 16:9

        # Provide alignment artifact so the caption path can proceed.
        transcribe_dir = tmp_path / "transcribe"
        transcribe_dir.mkdir(parents=True)
        (transcribe_dir / "word_alignment.json").write_text(
            _json.dumps({"words": [{"word": "test", "start": 0.0, "end": 0.5}]})
        )

        video_path = tmp_path / "output" / "youtube" / "final.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        output_dir = video_path.parent

        generated_ass_paths: list[str] = []

        def _capture_ffmpeg(args: list[str]) -> None:
            """Record the ass= filter path; write output."""
            for arg in args:
                if arg.startswith("ass="):
                    generated_ass_paths.append(arg[4:])
            out = Path(args[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"captioned")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _capture_ffmpeg)

        result = stage._burn_captions(
            video_path=video_path,
            output_dir=output_dir,
            job_dir=tmp_path,
            platform="youtube",
            spec=spec,
            aspect_ratio_override="9:16",  # override spec's 16:9
        )

        assert result is not None
        # The ASS file written to output_dir must reflect "9:16" not "16:9".
        ass_files = list(output_dir.glob("*.ass"))
        assert any("9_16" in f.name for f in ass_files), (
            "ASS filename must reflect the overridden aspect ratio 9:16, not spec's 16:9"
        )

    def test_mix_stingers_profile_name_override(self, tmp_path: Path, monkeypatch: Any) -> None:
        """_mix_stingers uses profile_name_override instead of config.branding.active_profile."""
        stage = self._make_stage()

        loaded_profiles: list[str] = []

        def _fake_load_profile(name: str, branding_dir: Any) -> None:
            loaded_profiles.append(name)

        monkeypatch.setattr(
            "podcast_pipeline.utils.branding.load_profile",
            _fake_load_profile,
        )

        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"video")
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Call with profile_name_override — the override profile name must be used.
        stage._mix_stingers(
            video_path=video_path,
            output_dir=output_dir,
            platform="youtube",
            edit_plan=None,
            src_duration=60.0,
            profile_name_override="my_custom_profile",
        )

        assert "my_custom_profile" in loaded_profiles, (
            "_mix_stingers must use profile_name_override when provided"
        )

    def test_render_video_captions_disabled_ignores_config(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """decisions.captions_enabled=False skips captions even when config.branding.captions.enabled=True.

        This is the key regression: the UI decision must take precedence over config.yaml.
        """
        config = load_config()
        config.branding.captions.enabled = True  # config says enabled...
        stage = RenderStage(config)

        burn_calls: list[str] = []

        def _record_burn(*_args: Any, **_kwargs: Any) -> Path | None:
            burn_calls.append("called")
            return None

        monkeypatch.setattr(
            "podcast_pipeline.stages.render.run_ffmpeg",
            self._fake_ffmpeg_writer,
        )
        monkeypatch.setattr(stage, "_burn_captions", _record_burn)
        monkeypatch.setattr(stage, "_normalize_loudness", lambda *_a, **_k: None)
        monkeypatch.setattr(stage, "_validate_video_platform_compliance", lambda *_a, **_k: None)

        input_video = tmp_path / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"video")
        output_dir = tmp_path / "output" / "youtube"
        spec = config.platforms.youtube

        stage._render_video(
            output_dir=output_dir,
            input_video=input_video,
            platform="youtube",
            spec=spec,
            decisions=ReviewDecisions(
                review_complete=True,
                captions_enabled=False,  # ...but UI says disabled
            ),
            video_info={"width": 1920, "height": 1080, "duration": 30.0},
            edit_plan=None,
            normalize_audio=False,
        )

        assert burn_calls == [], (
            "_burn_captions must NOT be called when decisions.captions_enabled=False, "
            "even when config.branding.captions.enabled=True"
        )
