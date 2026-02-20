"""Tests for Streamlit UI components."""

from datetime import UTC
from pathlib import Path


class TestUIHelpers:
    """Tests for UI helper functions."""

    def test_format_timestamp_with_datetime(self) -> None:
        """Test timestamp formatting with datetime."""
        from datetime import datetime

        from podcast_pipeline.ui.app import format_timestamp

        dt = datetime(2025, 1, 15, 10, 30, 45, tzinfo=UTC)
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
        from podcast_pipeline.stages.review import ReviewDecisions
        from podcast_pipeline.ui.app import update_thumbnail_selection

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
        """Test updating export platforms with canonical normalization."""
        from podcast_pipeline.stages.review import ReviewDecisions
        from podcast_pipeline.ui.app import update_export_platforms

        # Create review directory
        review_dir = tmp_path / "review"
        review_dir.mkdir()

        # Initial state
        initial = ReviewDecisions(export_platforms=["youtube"])
        (review_dir / "review_state.json").write_text(initial.model_dump_json())

        # Update platforms
        new_platforms = [" youtube ", "tiktok", "invalid", "instagram", "tiktok"]
        normalized, invalid = update_export_platforms(tmp_path, new_platforms)

        # Verify
        review_path = review_dir / "review_state.json"
        updated = ReviewDecisions.model_validate_json(review_path.read_text())
        assert normalized == ["youtube", "tiktok", "instagram"]
        assert invalid == ["invalid"]
        assert updated.export_platforms == ["youtube", "tiktok", "instagram"]


class TestMarketingEditorPlatformSpecs:
    """Tests for marketing editor platform coverage and limits."""

    def test_marketing_platform_matrix_includes_video_variants(self) -> None:
        """Marketing editor should expose all supported platform keys in stable order."""
        from podcast_pipeline.ui.app import _marketing_editor_platform_specs

        keys = [spec.key for spec in _marketing_editor_platform_specs()]

        assert keys == [
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
        ]

    def test_marketing_platform_video_title_modes_and_description_limits(self) -> None:
        """Video/audio podcast targets should keep platform-specific title and char guidance."""
        from podcast_pipeline.ui.app import _marketing_editor_platform_specs

        spec_by_key = {spec.key: spec for spec in _marketing_editor_platform_specs()}

        assert spec_by_key["youtube"].title_mode == "multi"
        assert spec_by_key["spotify"].title_mode == "single"
        assert spec_by_key["spotify_video"].title_mode == "single"
        assert spec_by_key["apple"].title_mode == "single"
        assert spec_by_key["apple_video"].title_mode == "single"
        assert spec_by_key["spotify_video"].max_description_chars == 4000
        assert spec_by_key["apple_video"].max_description_chars == 4000
        assert spec_by_key["tiktok"].max_description_chars == 150
        assert spec_by_key["twitter"].max_description_chars == 280


class TestMarketingReviewOverlay:
    """Tests for marketing overlay behavior used by editor flows."""

    def test_marketing_overlay_preserves_full_platform_edits_and_metadata(self) -> None:
        """Review edits should merge into base marketing without dropping video variants."""
        from podcast_pipeline.stages.review import ReviewDecisions
        from podcast_pipeline.ui.app import _apply_marketing_review_edits

        analysis = {
            "marketing": {
                "youtube": {"description": "base-youtube"},
                "spotify_video": {"description": "base-spotify-video"},
                "apple_video": {"description": "base-apple-video"},
            },
            "metadata": {"summary": "base-summary", "topics": ["base-topic"], "mood": "calm"},
        }
        decisions = ReviewDecisions(
            marketing_edits={
                "spotify_video": {"description": "edited-spotify-video"},
                "apple_video": {"description": "edited-apple-video"},
                "facebook": {"description": "new-facebook-copy"},
                "__metadata__": {"summary": "edited-summary", "topics": ["trend-a", "trend-b"]},
            }
        )

        marketing, metadata = _apply_marketing_review_edits(analysis, decisions)

        assert marketing["youtube"]["description"] == "base-youtube"
        assert marketing["spotify_video"]["description"] == "edited-spotify-video"
        assert marketing["apple_video"]["description"] == "edited-apple-video"
        assert marketing["facebook"]["description"] == "new-facebook-copy"
        assert metadata["summary"] == "edited-summary"
        assert metadata["topics"] == ["trend-a", "trend-b"]
