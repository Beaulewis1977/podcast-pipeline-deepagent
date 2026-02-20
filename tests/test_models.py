"""Tests for Pydantic models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from podcast_pipeline.models.analysis import (
    AnalysisResult,
    ContentCut,
    MarketingCopy,
    Metadata,
    ViralClip,
)
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.models.transcript import FillerCut, Segment, Word


class TestJob:
    """Tests for Job model."""

    def test_create_job(self):
        """Test creating a new job."""
        job = Job(
            job_id="test-001",
            input_file="/path/to/video.mp4",
        )
        assert job.job_id == "test-001"
        assert job.status == StageStatus.PENDING
        assert "ingest" in job.stages
        assert "transcribe" in job.stages

    def test_update_stage(self):
        """Test updating stage status."""
        job = Job(job_id="test-001", input_file="/test.mp4")
        job.update_stage("ingest", StageStatus.RUNNING)
        assert job.stages["ingest"].status == StageStatus.RUNNING
        assert job.stages["ingest"].started_at is not None

        job.update_stage("ingest", StageStatus.COMPLETE, outputs=["audio.wav"])
        assert job.stages["ingest"].status == StageStatus.COMPLETE
        assert job.stages["ingest"].completed_at is not None
        assert "audio.wav" in job.stages["ingest"].outputs

    def test_save_and_load(self, temp_dir: Path):
        """Test saving and loading job state."""
        job = Job(
            job_id="test-save-001",
            input_file="/path/to/video.mp4",
        )
        job.update_stage("ingest", StageStatus.COMPLETE)

        job.save(temp_dir)

        # Load and verify
        job_dir = temp_dir / "test-save-001"
        loaded = Job.load(job_dir)

        assert loaded.job_id == job.job_id
        assert loaded.stages["ingest"].status == StageStatus.COMPLETE


class TestTranscript:
    """Tests for transcript models."""

    def test_word_model(self):
        """Test Word model."""
        word = Word(word="hello", start=0.0, end=0.5, confidence=0.99)
        assert word.word == "hello"
        assert word.end - word.start == 0.5

    def test_segment_model(self):
        """Test Segment model."""
        segment = Segment(
            start=0.0,
            end=5.0,
            text="Hello world",
            words=[Word(word="Hello", start=0.0, end=0.3, confidence=0.99)],
        )
        assert len(segment.words) == 1

    def test_filler_cut_model(self):
        """Test FillerCut model."""
        cut = FillerCut(start=2.5, end=2.8, word="um", confidence=0.85)
        assert cut.word == "um"
        assert cut.end - cut.start == pytest.approx(0.3)

    def test_word_confidence_out_of_bounds_rejected(self):
        """Word confidence must stay within [0, 1]."""
        with pytest.raises(ValidationError):
            Word(word="oops", start=0.0, end=0.4, confidence=1.2)

        with pytest.raises(ValidationError):
            Word(word="oops", start=0.0, end=0.4, confidence=-0.1)

    def test_segment_backwards_range_rejected(self):
        """Segment end must be after start."""
        with pytest.raises(ValidationError):
            Segment(start=3.0, end=2.0, text="invalid")


class TestAnalysis:
    """Tests for analysis models."""

    def test_content_cut_model(self):
        """Test ContentCut model."""
        cut = ContentCut(
            start="02:15",
            end="02:45",
            start_seconds=135.0,
            end_seconds=165.0,
            reason="Off-topic tangent",
        )
        assert cut.end_seconds - cut.start_seconds == 30.0

    def test_viral_clip_model(self):
        """Test ViralClip model."""
        clip = ViralClip(
            start="15:30",
            end="16:00",
            start_seconds=930.0,
            end_seconds=960.0,
            description="Interesting moment",
            virality_score=8,
            suggested_hook="Must watch this!",
        )
        assert clip.virality_score == 8

    def test_content_cut_backwards_seconds_rejected(self):
        """Content cuts reject backwards seconds ranges."""
        with pytest.raises(ValidationError):
            ContentCut(
                start="02:45",
                end="02:15",
                start_seconds=165.0,
                end_seconds=135.0,
                reason="Invalid",
            )

    def test_viral_clip_string_seconds_mismatch_rejected(self):
        """Viral clips reject mismatched string and numeric timestamps."""
        with pytest.raises(ValidationError):
            ViralClip(
                start="01:00",
                end="01:30",
                start_seconds=0.0,
                end_seconds=90.0,
                description="Mismatch",
                virality_score=6,
            )

    def test_viral_clip_invalid_time_format_rejected(self):
        """Viral clips require MM:SS or HH:MM:SS time strings."""
        with pytest.raises(ValidationError):
            ViralClip(
                start="1m30s",
                end="2m00s",
                start_seconds=90.0,
                end_seconds=120.0,
                description="Bad format",
                virality_score=6,
            )

    def test_analysis_result_model(self):
        """Test full AnalysisResult model."""
        result = AnalysisResult(
            content_cuts=[],
            viral_clips=[],
            thumbnail_frames=[],
            marketing=MarketingCopy(),
            metadata=Metadata(summary="Test summary", topics=["AI"]),
        )
        assert result.metadata.summary == "Test summary"
        assert "AI" in result.metadata.topics

    def test_marketing_copy_platform_matrix_contract(self) -> None:
        """MarketingCopy should expose the full supported platform matrix."""
        expected_platforms = (
            "youtube",
            "spotify",
            "spotify_video",
            "apple",
            "apple_video",
            "tiktok",
            "instagram",
            "linkedin",
            "twitter",
            "facebook",
        )
        assert tuple(MarketingCopy.model_fields) == expected_platforms

    def test_marketing_copy_dump_load_round_trip_preserves_all_platform_keys(self) -> None:
        """Marketing payload should retain all platform keys through validation cycles."""
        payload = {
            "marketing": {
                "youtube": {
                    "titles": ["YouTube title"],
                    "description": "YouTube description",
                    "hashtags": ["#youtube"],
                },
                "spotify": {
                    "titles": ["Spotify title"],
                    "description": "Spotify description",
                    "hashtags": ["#spotify"],
                },
                "spotify_video": {
                    "titles": ["Spotify Video title"],
                    "description": "Spotify Video description",
                    "hashtags": ["#spotifyvideo"],
                },
                "apple": {
                    "titles": ["Apple title"],
                    "description": "Apple description",
                    "hashtags": ["#apple"],
                },
                "apple_video": {
                    "titles": ["Apple Video title"],
                    "description": "Apple Video description",
                    "hashtags": ["#applevideo"],
                },
                "tiktok": {
                    "titles": ["TikTok title"],
                    "description": "TikTok description",
                    "hashtags": ["#tiktok"],
                },
                "instagram": {
                    "titles": ["Instagram title"],
                    "description": "Instagram description",
                    "hashtags": ["#instagram"],
                },
                "linkedin": {
                    "titles": ["LinkedIn title"],
                    "description": "LinkedIn description",
                    "hashtags": ["#linkedin"],
                },
                "twitter": {
                    "titles": ["Twitter title"],
                    "description": "Twitter description",
                    "hashtags": ["#twitter"],
                },
                "facebook": {
                    "titles": ["Facebook title"],
                    "description": "Facebook description",
                    "hashtags": ["#facebook"],
                },
            }
        }

        validated = AnalysisResult.model_validate(payload)
        dumped = validated.model_dump()
        round_tripped = AnalysisResult.model_validate(dumped).model_dump()
        expected_keys = list(payload["marketing"])

        assert list(dumped["marketing"]) == expected_keys
        assert list(round_tripped["marketing"]) == expected_keys
        assert (
            round_tripped["marketing"]["spotify_video"]["description"]
            == "Spotify Video description"
        )
        assert round_tripped["marketing"]["apple_video"]["description"] == "Apple Video description"
