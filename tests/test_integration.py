"""Integration tests for the full podcast pipeline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from podcast_pipeline.config import load_config
from podcast_pipeline.models.job import Job, JobStage, StageStatus
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.stages.base import StageResult


class TestPipelineIntegration:
    """Integration tests for Pipeline class."""

    def test_pipeline_creation(self) -> None:
        """Test pipeline can be created with config."""
        config = load_config()
        pipeline = Pipeline(config)
        assert pipeline is not None
        assert pipeline.config == config

    def test_create_job(self, tmp_path: Path) -> None:
        """Test creating a new job."""
        config = load_config()
        config.paths.jobs_dir = tmp_path
        
        pipeline = Pipeline(config)
        
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")
        
        job = pipeline.create_job(video_path, "test_episode")
        
        assert job is not None
        assert "test_episode" in job.job_id
        assert job.input_file == str(video_path)

    def test_load_job(self, tmp_path: Path) -> None:
        """Test loading an existing job."""
        config = load_config()
        config.paths.jobs_dir = tmp_path
        
        pipeline = Pipeline(config)
        
        # Create a fake video and job
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")
        
        created_job = pipeline.create_job(video_path, "test_load")
        
        # Load the job
        loaded_job = pipeline.load_job(created_job.job_id)
        
        assert loaded_job.job_id == created_job.job_id
        assert loaded_job.input_file == created_job.input_file

    def test_load_nonexistent_job(self, tmp_path: Path) -> None:
        """Test loading a job that doesn't exist."""
        config = load_config()
        config.paths.jobs_dir = tmp_path
        
        pipeline = Pipeline(config)
        
        with pytest.raises(FileNotFoundError):
            pipeline.load_job("nonexistent_job_id")

    def test_list_jobs_empty(self, tmp_path: Path) -> None:
        """Test listing jobs when none exist."""
        config = load_config()
        config.paths.jobs_dir = tmp_path
        
        pipeline = Pipeline(config)
        jobs = pipeline.list_jobs()
        
        assert jobs == []

    def test_list_jobs_with_jobs(self, tmp_path: Path) -> None:
        """Test listing jobs when jobs exist."""
        config = load_config()
        config.paths.jobs_dir = tmp_path
        
        pipeline = Pipeline(config)
        
        # Create some jobs
        for i in range(3):
            video_path = tmp_path / f"video_{i}.mp4"
            video_path.write_bytes(b"fake video")
            pipeline.create_job(video_path, f"episode_{i}")
        
        jobs = pipeline.list_jobs()
        
        assert len(jobs) == 3


class TestStageExecution:
    """Tests for stage execution."""

    def test_ingest_stage_requires_video(self, tmp_path: Path) -> None:
        """Test ingest stage fails without video."""
        from podcast_pipeline.stages.ingest import IngestStage
        
        config = load_config()
        stage = IngestStage(config)
        
        job = Job(job_id="test", input_file="nonexistent.mp4")
        
        result = stage.run(job, tmp_path)
        
        assert result.success is False
        assert "not found" in result.error.lower() or "not exist" in result.error.lower()

    def test_analyze_stage_requires_transcript(self, tmp_path: Path) -> None:
        """Test analyze stage fails without transcript."""
        from podcast_pipeline.stages.analyze import AnalyzeStage
        
        config = load_config()
        stage = AnalyzeStage(config)
        
        job = Job(job_id="test", input_file="test.mp4")
        
        result = stage.run(job, tmp_path)
        
        assert result.success is False
        assert "transcript" in result.error.lower()

    def test_render_stage_requires_review(self, tmp_path: Path) -> None:
        """Test render stage fails without review."""
        from podcast_pipeline.stages.render import RenderStage
        
        config = load_config()
        stage = RenderStage(config)
        
        job = Job(job_id="test", input_file="test.mp4")
        
        result = stage.run(job, tmp_path)
        
        assert result.success is False
        assert "review" in result.error.lower()


class TestJobStateManagement:
    """Tests for job state management."""

    def test_job_stage_update(self) -> None:
        """Test updating job stage status."""
        job = Job(job_id="test", input_file="test.mp4")
        
        job.update_stage("ingest", StageStatus.RUNNING)
        assert job.stages["ingest"].status == StageStatus.RUNNING
        assert job.stages["ingest"].started_at is not None
        
        job.update_stage("ingest", StageStatus.COMPLETE, outputs=["test_output.mp4"])
        assert job.stages["ingest"].status == StageStatus.COMPLETE
        assert job.stages["ingest"].completed_at is not None
        assert "test_output.mp4" in job.stages["ingest"].outputs

    def test_job_save_and_load(self, tmp_path: Path) -> None:
        """Test saving and loading job state."""
        job = Job(job_id="test_save", input_file="video.mp4")
        job.update_stage("ingest", StageStatus.COMPLETE)
        
        job.save(tmp_path)
        
        loaded = Job.load(tmp_path / "test_save")
        
        assert loaded.job_id == job.job_id
        assert loaded.stages["ingest"].status == StageStatus.COMPLETE

    def test_job_overall_status_running(self) -> None:
        """Test overall status is running when stage is running."""
        job = Job(job_id="test", input_file="test.mp4")
        job.update_stage("ingest", StageStatus.RUNNING)
        
        assert job.status == StageStatus.RUNNING

    def test_job_overall_status_failed(self) -> None:
        """Test overall status is failed when stage fails."""
        job = Job(job_id="test", input_file="test.mp4")
        job.update_stage("ingest", StageStatus.FAILED, error="Test error")
        
        assert job.status == StageStatus.FAILED

    def test_job_overall_status_waiting(self) -> None:
        """Test overall status is waiting when review is waiting."""
        job = Job(job_id="test", input_file="test.mp4")
        job.update_stage("ingest", StageStatus.COMPLETE)
        job.update_stage("transcribe", StageStatus.COMPLETE)
        job.update_stage("analyze", StageStatus.COMPLETE)
        job.update_stage("review", StageStatus.WAITING)
        
        assert job.status == StageStatus.WAITING


class TestMultiTrackAudioSupport:
    """Tests for multi-track audio transcription."""

    def test_detect_audio_tracks_empty(self, tmp_path: Path) -> None:
        """Test detecting audio tracks with no video."""
        from podcast_pipeline.stages.transcribe import TranscribeStage
        
        config = load_config()
        stage = TranscribeStage(config)
        
        # Non-existent video
        tracks = stage._detect_audio_tracks(tmp_path / "nonexistent.mp4")
        assert tracks == []

    @patch("podcast_pipeline.stages.transcribe.get_video_metadata")
    def test_detect_audio_tracks_single(self, mock_metadata: MagicMock, tmp_path: Path) -> None:
        """Test detecting single audio track."""
        from podcast_pipeline.stages.transcribe import TranscribeStage
        
        mock_metadata.return_value = {
            "streams": [
                {"codec_type": "video", "index": 0},
                {"codec_type": "audio", "index": 1, "channels": 2},
            ]
        }
        
        config = load_config()
        stage = TranscribeStage(config)
        
        tracks = stage._detect_audio_tracks(tmp_path / "video.mp4")
        
        assert len(tracks) == 1
        assert tracks[0]["channels"] == 2

    @patch("podcast_pipeline.stages.transcribe.get_video_metadata")
    def test_detect_audio_tracks_multiple(self, mock_metadata: MagicMock, tmp_path: Path) -> None:
        """Test detecting multiple audio tracks."""
        from podcast_pipeline.stages.transcribe import TranscribeStage
        
        mock_metadata.return_value = {
            "streams": [
                {"codec_type": "video", "index": 0},
                {"codec_type": "audio", "index": 1, "channels": 1, "codec_name": "aac"},
                {"codec_type": "audio", "index": 2, "channels": 1, "codec_name": "aac"},
            ]
        }
        
        config = load_config()
        stage = TranscribeStage(config)
        
        tracks = stage._detect_audio_tracks(tmp_path / "video.mp4")
        
        assert len(tracks) == 2

    def test_merge_transcripts(self) -> None:
        """Test merging multiple track transcripts."""
        from podcast_pipeline.stages.transcribe import TranscribeStage
        from podcast_pipeline.models.transcript import TranscriptResult, Segment
        
        config = load_config()
        stage = TranscribeStage(config)
        
        transcript1 = TranscriptResult(
            text="Speaker 1 text",
            segments=[
                Segment(start=0.0, end=5.0, text="Hello", speaker="Speaker 1"),
                Segment(start=10.0, end=15.0, text="How are you?", speaker="Speaker 1"),
            ],
            language="en",
            duration=20.0,
            speaker="Speaker 1",
            track_index=0,
        )
        
        transcript2 = TranscriptResult(
            text="Speaker 2 text",
            segments=[
                Segment(start=5.0, end=10.0, text="Hi there", speaker="Speaker 2"),
                Segment(start=15.0, end=20.0, text="I'm good", speaker="Speaker 2"),
            ],
            language="en",
            duration=20.0,
            speaker="Speaker 2",
            track_index=1,
        )
        
        merged = stage._merge_transcripts([transcript1, transcript2])
        
        assert len(merged.segments) == 4
        # Check segments are sorted by start time
        for i in range(len(merged.segments) - 1):
            assert merged.segments[i].start <= merged.segments[i + 1].start
        
        # Check merged text contains both speakers
        assert "[Speaker 1]" in merged.text
        assert "[Speaker 2]" in merged.text

    def test_generate_srt_with_speakers(self) -> None:
        """Test generating SRT with speaker labels."""
        from podcast_pipeline.stages.transcribe import TranscribeStage
        from podcast_pipeline.models.transcript import Segment
        
        config = load_config()
        stage = TranscribeStage(config)
        
        segments = [
            Segment(start=0.0, end=5.0, text="Hello", speaker="Speaker 1"),
            Segment(start=5.0, end=10.0, text="Hi there", speaker="Speaker 2"),
        ]
        
        srt = stage._generate_srt_with_speakers(segments)
        
        assert "[Speaker 1]" in srt
        assert "[Speaker 2]" in srt
        assert "Hello" in srt
        assert "Hi there" in srt


class TestErrorRecovery:
    """Tests for error recovery mechanisms."""

    def test_stage_result_with_partial_outputs(self) -> None:
        """Test stage result can have partial outputs on failure."""
        result = StageResult(
            success=False,
            error="Partial failure",
            outputs=["partial_output.txt"],
        )
        
        assert result.success is False
        assert len(result.outputs) == 1

    def test_job_error_tracking(self) -> None:
        """Test job tracks errors properly."""
        job = Job(job_id="test", input_file="test.mp4")
        job.update_stage("analyze", StageStatus.FAILED, error="API rate limit exceeded")
        
        assert job.stages["analyze"].error == "API rate limit exceeded"
        assert job.status == StageStatus.FAILED
