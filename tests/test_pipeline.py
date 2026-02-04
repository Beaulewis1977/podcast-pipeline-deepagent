"""Tests for pipeline orchestration."""

import json
from pathlib import Path

import pytest

from podcast_pipeline.config import Config
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.pipeline import Pipeline


class TestPipeline:
    """Tests for Pipeline class."""

    def test_create_pipeline(self, config: Config):
        """Test creating a pipeline."""
        pipeline = Pipeline(config)
        assert "ingest" in pipeline.stages
        assert "transcribe" in pipeline.stages
        assert "analyze" in pipeline.stages
        assert "review" in pipeline.stages
        assert "render" in pipeline.stages

    def test_list_empty_jobs(self, config: Config):
        """Test listing jobs when none exist."""
        pipeline = Pipeline(config)
        jobs = pipeline.list_jobs()
        assert jobs == []

    def test_stage_order(self, config: Config):
        """Test pipeline stage order."""
        pipeline = Pipeline(config)
        expected = ["ingest", "transcribe", "analyze", "review", "render"]
        assert pipeline.STAGE_ORDER == expected


class TestReviewStage:
    """Tests for review stage functionality."""

    def test_approve_review(self, config: Config, temp_dir: Path):
        """Test approving a review."""
        from podcast_pipeline.stages.review import ReviewDecisions, approve_review

        # Create job directory structure
        job_dir = temp_dir / "test-job"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True)

        # Create mock analysis file
        analysis = {
            "content_cuts": [{"start": "00:10", "end": "00:20", "start_seconds": 10, "end_seconds": 20, "reason": "test"}],
            "viral_clips": [{"start": "00:30", "end": "01:00", "start_seconds": 30, "end_seconds": 60, "description": "test", "virality_score": 8, "suggested_hook": "watch"}],
            "thumbnail_frames": [{"timestamp": "00:15", "timestamp_seconds": 15, "visual_description": "test", "suggested_text_overlay": "text", "emotion": "joy"}],
            "marketing": {},
            "metadata": {},
        }
        (analysis_dir / "analysis.json").write_text(json.dumps(analysis))

        # Create mock filler cuts
        fillers = [{"start": 2.5, "end": 2.8, "word": "um", "confidence": 0.85}]
        (analysis_dir / "filler_cuts.json").write_text(json.dumps(fillers))

        # Approve review
        decisions = approve_review(job_dir, ["youtube", "spotify"])

        assert decisions.review_complete
        assert len(decisions.approved_filler_cuts) == 1
        assert len(decisions.approved_content_cuts) == 1
        assert len(decisions.selected_clips) == 1
        assert decisions.selected_thumbnail == 0
        assert "youtube" in decisions.export_platforms
