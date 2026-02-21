"""Review and export-target normalization tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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


def test_normalize_export_platforms_empty_input_uses_defaults() -> None:
    """Missing platform input should resolve to stable default targets."""
    assert normalize_export_platforms(None) == list(DEFAULT_EXPORT_PLATFORMS)
    assert normalize_export_platforms([]) == list(DEFAULT_EXPORT_PLATFORMS)


def test_normalize_export_platforms_invalid_only_falls_back_to_defaults() -> None:
    """Invalid-only inputs should not leak unsupported keys into review artifacts."""
    normalized, invalid = normalize_export_platforms(
        ["invalid", "also-invalid", "INVALID"],
        include_invalid=True,
    )

    assert normalized == list(DEFAULT_EXPORT_PLATFORMS)
    assert invalid == ["invalid", "also-invalid"]


def test_review_decisions_legacy_unknown_export_keys_preserved_for_render() -> None:
    """Unknown platform keys in stored review_state are preserved so the render stage
    can surface them as explicit unsupported-platform failures rather than silently
    substituting defaults."""
    decisions = ReviewDecisions.model_validate(
        {"export_platforms": ["unknown", "mystery"], "review_complete": False}
    )

    assert decisions.export_platforms == ["unknown", "mystery"]


def test_review_decisions_preserves_video_export_keys() -> None:
    """Video podcast keys should survive ReviewDecisions normalization untouched."""
    decisions = ReviewDecisions.model_validate(
        {
            "export_platforms": [
                "spotify_video",
                " apple_video ",
                "apple_hls",
                "spotify_video",
            ]
        }
    )

    assert decisions.export_platforms == ["spotify_video", "apple_video", "apple_hls"]


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


def test_approve_review_none_platforms_fallback_to_defaults(tmp_path: Path) -> None:
    """Omitted explicit platform list should keep canonical default targets."""
    _seed_review_inputs(tmp_path)

    decisions = approve_review(tmp_path, None)
    assert decisions.export_platforms == list(DEFAULT_EXPORT_PLATFORMS)


def test_review_decisions_selected_thumbnail_hydrates_selected_thumbnails() -> None:
    """Legacy scalar thumbnail payloads should hydrate new list-based selection state."""
    decisions = ReviewDecisions.model_validate({"selected_thumbnail": 2})

    assert decisions.selected_thumbnail == 2
    assert decisions.selected_thumbnails == [2]


def test_review_decisions_selected_thumbnails_populates_primary_mirror() -> None:
    """Multi-select payloads should map primary thumbnail to legacy mirror field."""
    decisions = ReviewDecisions.model_validate({"selected_thumbnails": [4, 1, 3]})

    assert decisions.selected_thumbnails == [4, 1, 3]
    assert decisions.selected_thumbnail == 4


def test_review_decisions_selected_thumbnail_overrides_primary_rank_when_present() -> None:
    """Scalar selection should be treated as canonical primary when both forms are provided."""
    decisions = ReviewDecisions.model_validate(
        {"selected_thumbnail": 5, "selected_thumbnails": [1, 2]}
    )

    assert decisions.selected_thumbnail == 5
    assert decisions.selected_thumbnails == [5, 1, 2]


def test_review_decisions_selected_thumbnails_reject_duplicates() -> None:
    """selected_thumbnails should enforce unique ranking indices."""
    with pytest.raises(ValidationError):
        ReviewDecisions.model_validate({"selected_thumbnails": [1, 1, 2]})


def test_review_decisions_selected_thumbnails_reject_more_than_three() -> None:
    """selected_thumbnails should cap ranked selections to 3 entries."""
    with pytest.raises(ValidationError):
        ReviewDecisions.model_validate({"selected_thumbnails": [0, 1, 2, 3]})
