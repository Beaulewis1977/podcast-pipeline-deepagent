"""Review and export-target normalization tests."""

import json
from pathlib import Path

from podcast_pipeline.export_targets import (
    DEFAULT_EXPORT_PLATFORMS,
    SUPPORTED_EXPORT_PLATFORMS,
    normalize_export_platforms,
)
from podcast_pipeline.stages.review import ReviewDecisions, approve_review


def test_supported_export_platforms_include_video_targets() -> None:
    """Canonical supported-platform registry includes video podcast targets."""
    assert "spotify_video" in SUPPORTED_EXPORT_PLATFORMS
    assert "apple_video" in SUPPORTED_EXPORT_PLATFORMS
    assert "apple_hls" in SUPPORTED_EXPORT_PLATFORMS
    assert tuple(DEFAULT_EXPORT_PLATFORMS) == ("youtube", "spotify")


def test_normalize_export_platforms_trims_dedupes_and_filters() -> None:
    """Normalization should trim, lowercase, dedupe, and drop invalid keys."""
    normalized, invalid = normalize_export_platforms(
        [" youtube ", "spotify", "YouTube", "apple_video", "unknown", ""],
        include_invalid=True,
    )

    assert normalized == ["youtube", "spotify", "apple_video"]
    assert invalid == ["unknown"]


def _seed_review_inputs(job_dir: Path) -> None:
    analysis_dir = job_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "analysis.json").write_text(
        json.dumps(
            {
                "content_cuts": [],
                "viral_clips": [],
                "thumbnail_frames": [],
                "marketing": {},
                "metadata": {},
            }
        )
    )
    (analysis_dir / "filler_cuts.json").write_text("[]")


def test_approve_review_normalizes_export_platforms(tmp_path: Path) -> None:
    """approve_review should persist normalized, deduplicated export keys."""
    _seed_review_inputs(tmp_path)

    decisions = approve_review(
        tmp_path,
        [" spotify_video ", "invalid", "apple_video", "spotify_video"],
    )

    assert decisions.export_platforms == ["spotify_video", "apple_video"]
    review_state = ReviewDecisions.model_validate_json(
        (tmp_path / "review" / "review_state.json").read_text()
    )
    assert review_state.export_platforms == ["spotify_video", "apple_video"]


def test_approve_review_invalid_export_platforms_fallback_to_defaults(tmp_path: Path) -> None:
    """approve_review should fallback to canonical defaults when no valid keys are provided."""
    _seed_review_inputs(tmp_path)

    decisions = approve_review(tmp_path, ["invalid", "unknown"])
    assert decisions.export_platforms == list(DEFAULT_EXPORT_PLATFORMS)
