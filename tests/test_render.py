"""Tests for render stage and platform exports."""

import json
from collections import namedtuple
from pathlib import Path

from podcast_pipeline.config import PlatformSpec, load_config
from podcast_pipeline.models.job import Job
from podcast_pipeline.stages.render import RenderStage
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
