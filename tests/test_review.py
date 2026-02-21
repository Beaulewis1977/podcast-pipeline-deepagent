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
from podcast_pipeline.stages.review import (
    FillerDecision,
    ReviewDecisions,
    approve_review,
    write_edit_plan,
)


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


def test_review_decisions_reject_duplicate_filler_decision_indices() -> None:
    """Per-filler decisions should remain deterministic by unique filler index."""
    with pytest.raises(ValidationError):
        ReviewDecisions.model_validate(
            {
                "filler_decisions": [
                    {"index": 1, "action": "remove"},
                    {"index": 1, "action": "keep"},
                ]
            }
        )


def test_write_edit_plan_prefers_filler_decisions_over_legacy_indices(tmp_path: Path) -> None:
    """Explicit filler decisions should drive edit-plan filler cuts when provided."""
    review_dir = tmp_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    filler_cuts = [
        {"start_seconds": 1.0, "end_seconds": 1.2, "word": "um", "confidence": 0.9},
        {"start_seconds": 2.0, "end_seconds": 2.3, "word": "like", "confidence": 0.8},
        {"start_seconds": 3.0, "end_seconds": 3.4, "word": "uh", "confidence": 0.85},
    ]
    decisions = ReviewDecisions(
        approved_filler_cuts=[0, 1, 2],
        filler_decisions=[
            FillerDecision(index=0, action="keep"),
            FillerDecision(index=1, action="remove"),
            FillerDecision(index=2, action="remove"),
        ],
    )

    edit_path = write_edit_plan(tmp_path, decisions, analysis={}, filler_cuts=filler_cuts)
    payload = json.loads(edit_path.read_text())
    exported_words = [item["word"] for item in payload["filler_cuts"]]

    assert exported_words == ["like", "uh"]


def test_write_edit_plan_falls_back_to_approved_filler_cuts_when_new_field_absent(
    tmp_path: Path,
) -> None:
    """Legacy approved_filler_cuts should still drive edit-plan generation."""
    filler_cuts = [
        {"start_seconds": 0.5, "end_seconds": 0.8, "word": "um"},
        {"start_seconds": 1.0, "end_seconds": 1.3, "word": "so"},
    ]
    decisions = ReviewDecisions(approved_filler_cuts=[1])

    edit_path = write_edit_plan(tmp_path, decisions, analysis={}, filler_cuts=filler_cuts)
    payload = json.loads(edit_path.read_text())

    assert len(payload["filler_cuts"]) == 1
    assert payload["filler_cuts"][0]["word"] == "so"


def test_write_edit_plan_defaults_to_all_fillers_when_no_decisions_present(tmp_path: Path) -> None:
    """Behavior should remain backward-compatible when review state has no filler selections."""
    filler_cuts = [
        {"start_seconds": 0.5, "end_seconds": 0.8, "word": "um"},
        {"start_seconds": 1.0, "end_seconds": 1.3, "word": "so"},
    ]
    decisions = ReviewDecisions()

    edit_path = write_edit_plan(tmp_path, decisions, analysis={}, filler_cuts=filler_cuts)
    payload = json.loads(edit_path.read_text())

    assert [cut["word"] for cut in payload["filler_cuts"]] == ["um", "so"]


def test_write_edit_plan_applies_category_bulk_rule_overrides(tmp_path: Path) -> None:
    """Category bulk rules should override per-item decisions deterministically."""
    filler_cuts = [
        {"start_seconds": 0.5, "end_seconds": 0.8, "word": "um", "category": "disfluency"},
        {"start_seconds": 1.0, "end_seconds": 1.3, "word": "like", "category": "hedge"},
        {"start_seconds": 1.5, "end_seconds": 1.8, "word": "uh", "category": "disfluency"},
    ]
    decisions = ReviewDecisions(
        filler_decisions=[
            FillerDecision(index=0, action="keep"),
            FillerDecision(index=1, action="remove"),
            FillerDecision(index=2, action="keep"),
        ],
        filler_bulk_rules={"disfluency": "remove_all"},
    )

    edit_path = write_edit_plan(tmp_path, decisions, analysis={}, filler_cuts=filler_cuts)
    payload = json.loads(edit_path.read_text())
    exported_words = [item["word"] for item in payload["filler_cuts"]]

    assert exported_words == ["um", "like", "uh"]


def test_write_edit_plan_emits_filler_ranges_in_index_order(tmp_path: Path) -> None:
    """Output ordering should stay deterministic even when decisions arrive unsorted."""
    filler_cuts = [
        {"start_seconds": 0.5, "end_seconds": 0.8, "word": "a"},
        {"start_seconds": 1.0, "end_seconds": 1.3, "word": "b"},
        {"start_seconds": 1.5, "end_seconds": 1.8, "word": "c"},
    ]
    decisions = ReviewDecisions(
        filler_decisions=[
            FillerDecision(index=2, action="remove"),
            FillerDecision(index=0, action="remove"),
            FillerDecision(index=1, action="keep"),
        ]
    )

    edit_path = write_edit_plan(tmp_path, decisions, analysis={}, filler_cuts=filler_cuts)
    payload = json.loads(edit_path.read_text())
    exported_words = [item["word"] for item in payload["filler_cuts"]]

    assert exported_words == ["a", "c"]
