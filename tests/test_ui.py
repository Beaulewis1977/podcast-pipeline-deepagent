"""Tests for Streamlit UI components."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestUIHelpers:
    """Tests for UI helper functions."""

    def test_format_timestamp_with_datetime(self) -> None:
        """Test timestamp formatting with datetime."""
        from datetime import datetime, timezone
        from podcast_pipeline.ui.app import format_timestamp
        
        dt = datetime(2025, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        result = format_timestamp(dt)
        assert "2025-01-15" in result
        assert "10:30" in result

    def test_format_timestamp_with_none(self) -> None:
        """Test timestamp formatting with None."""
        from podcast_pipeline.ui.app import format_timestamp
        
        result = format_timestamp(None)
        assert result == "-"

    def test_status_badge_complete(self) -> None:
        """Test status badge for complete status."""
        from podcast_pipeline.ui.app import status_badge
        
        result = status_badge("complete")
        assert "🟢" in result
        assert "Complete" in result

    def test_status_badge_running(self) -> None:
        """Test status badge for running status."""
        from podcast_pipeline.ui.app import status_badge
        
        result = status_badge("running")
        assert "🔵" in result

    def test_status_badge_failed(self) -> None:
        """Test status badge for failed status."""
        from podcast_pipeline.ui.app import status_badge
        
        result = status_badge("failed")
        assert "🔴" in result


class TestUIConfig:
    """Tests for UI configuration loading."""

    def test_load_config_directly(self) -> None:
        """Test that config can be loaded directly."""
        from podcast_pipeline.config import load_config
        
        config = load_config()
        assert config is not None
        assert hasattr(config, "paths")
        assert hasattr(config, "platforms")

    def test_pipeline_can_be_created(self) -> None:
        """Test that Pipeline can be created with config."""
        from podcast_pipeline.config import load_config
        from podcast_pipeline.pipeline import Pipeline
        
        config = load_config()
        pipeline = Pipeline(config)
        assert pipeline is not None


class TestReviewDecisionsUpdate:
    """Tests for review decisions updates."""

    def test_update_thumbnail_selection(self, tmp_path: Path) -> None:
        """Test updating thumbnail selection."""
        from podcast_pipeline.ui.app import update_thumbnail_selection
        from podcast_pipeline.stages.review import ReviewDecisions
        
        # Create review directory
        review_dir = tmp_path / "review"
        review_dir.mkdir()
        
        # Initial state
        initial = ReviewDecisions(selected_thumbnail=0)
        (review_dir / "review_state.json").write_text(initial.model_dump_json())
        
        # Update selection
        update_thumbnail_selection(tmp_path, 5)
        
        # Verify
        review_path = review_dir / "review_state.json"
        updated = ReviewDecisions.model_validate_json(review_path.read_text())
        assert updated.selected_thumbnail == 5

    def test_update_export_platforms(self, tmp_path: Path) -> None:
        """Test updating export platforms."""
        from podcast_pipeline.ui.app import update_export_platforms
        from podcast_pipeline.stages.review import ReviewDecisions
        
        # Create review directory
        review_dir = tmp_path / "review"
        review_dir.mkdir()
        
        # Initial state
        initial = ReviewDecisions(export_platforms=["youtube"])
        (review_dir / "review_state.json").write_text(initial.model_dump_json())
        
        # Update platforms
        new_platforms = ["youtube", "tiktok", "instagram"]
        update_export_platforms(tmp_path, new_platforms)
        
        # Verify
        review_path = review_dir / "review_state.json"
        updated = ReviewDecisions.model_validate_json(review_path.read_text())
        assert set(updated.export_platforms) == set(new_platforms)
