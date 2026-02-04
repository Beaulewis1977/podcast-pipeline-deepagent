"""Tests for Pydantic models."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from podcast_pipeline.models.analysis import (
    AnalysisResult,
    ContentCut,
    MarketingCopy,
    Metadata,
    ViralClip,
)
from podcast_pipeline.models.job import Job, JobStage, StageStatus
from podcast_pipeline.models.transcript import FillerCut, Segment, TranscriptResult, Word


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
