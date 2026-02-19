"""Tests for render stage and platform exports."""

import json
from collections import namedtuple
from pathlib import Path

import pytest

from podcast_pipeline.config import PlatformSpec, load_config
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
