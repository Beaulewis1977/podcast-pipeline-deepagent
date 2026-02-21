"""Validation edge cases for edit plan models."""

import pytest
from pydantic import ValidationError

from podcast_pipeline.models.edit_plan import (
    ClipRange,
    ContentCutRange,
    EditPlan,
    FillerCutRange,
)


class TestEditPlanRangeValidation:
    """Boundary validation for time ranges and confidence values."""

    def test_filler_cut_rejects_negative_start(self):
        """Negative timestamps are rejected at model boundaries."""
        with pytest.raises(ValidationError):
            FillerCutRange(start_seconds=-0.1, end_seconds=0.2, word="um", confidence=0.8)

    def test_filler_cut_rejects_backward_range(self):
        """End time must be after start time."""
        with pytest.raises(ValidationError):
            FillerCutRange(start_seconds=1.2, end_seconds=1.0, word="uh", confidence=0.9)

    def test_filler_cut_rejects_invalid_confidence(self):
        """Confidence values must remain in [0, 1]."""
        with pytest.raises(ValidationError):
            FillerCutRange(start_seconds=1.0, end_seconds=1.2, word="um", confidence=-0.01)

        with pytest.raises(ValidationError):
            FillerCutRange(start_seconds=1.0, end_seconds=1.2, word="um", confidence=1.01)

    def test_content_cut_rejects_zero_duration(self):
        """Zero-duration content cuts are invalid."""
        with pytest.raises(ValidationError):
            ContentCutRange(start_seconds=12.0, end_seconds=12.0, reason="degenerate")

    def test_clip_range_rejects_zero_duration(self):
        """Zero-duration clips are invalid."""
        with pytest.raises(ValidationError):
            ClipRange(start_seconds=25.0, end_seconds=25.0, description="empty clip")

    def test_clip_range_rejects_negative_score(self):
        """Clip scores cannot be negative."""
        with pytest.raises(ValidationError):
            ClipRange(start_seconds=25.0, end_seconds=26.0, score=-1)

    def test_edit_plan_accepts_adjacent_non_overlapping_ranges(self):
        """Adjacent cuts are valid when ranges do not overlap."""
        plan = EditPlan(
            filler_cuts=[
                FillerCutRange(start_seconds=0.0, end_seconds=0.3, word="um", confidence=0.9),
                FillerCutRange(start_seconds=0.3, end_seconds=0.6, word="uh", confidence=0.8),
            ],
            content_cuts=[
                ContentCutRange(start_seconds=10.0, end_seconds=12.0, reason="tangent"),
                ContentCutRange(start_seconds=12.0, end_seconds=14.0, reason="duplicate"),
            ],
            clip_ranges=[
                ClipRange(start_seconds=30.0, end_seconds=45.0, description="main clip"),
            ],
        )

        assert len(plan.filler_cuts) == 2
        assert len(plan.content_cuts) == 2
        assert len(plan.clip_ranges) == 1

    def test_edit_plan_rejects_overlapping_filler_cuts(self):
        """Overlapping filler cuts are rejected explicitly."""
        with pytest.raises(ValidationError):
            EditPlan(
                filler_cuts=[
                    FillerCutRange(
                        start_seconds=0.0,
                        end_seconds=1.0,
                        word="um",
                        confidence=0.9,
                    ),
                    FillerCutRange(
                        start_seconds=0.5,
                        end_seconds=1.2,
                        word="uh",
                        confidence=0.85,
                    ),
                ]
            )

    def test_edit_plan_rejects_overlapping_content_cuts(self):
        """Overlapping content cuts are rejected explicitly."""
        with pytest.raises(ValidationError):
            EditPlan(
                content_cuts=[
                    ContentCutRange(start_seconds=20.0, end_seconds=30.0, reason="off topic"),
                    ContentCutRange(start_seconds=29.0, end_seconds=35.0, reason="repeated"),
                ]
            )

    def test_edit_plan_sorts_ranges_before_overlap_check(self):
        """Overlap detection is order-independent."""
        with pytest.raises(ValidationError):
            EditPlan(
                content_cuts=[
                    ContentCutRange(start_seconds=40.0, end_seconds=45.0, reason="later"),
                    ContentCutRange(start_seconds=35.0, end_seconds=41.0, reason="earlier"),
                ]
            )

    def test_edit_plan_allows_overlapping_clip_exports(self):
        """Clip overlaps are allowed for alternate social cut variants."""
        plan = EditPlan(
            clip_ranges=[
                ClipRange(start_seconds=60.0, end_seconds=80.0, description="teaser"),
                ClipRange(start_seconds=75.0, end_seconds=95.0, description="deep dive"),
            ]
        )

        assert [clip.description for clip in plan.clip_ranges] == ["teaser", "deep dive"]

    def test_filler_cut_supports_phase7_editorial_metadata_round_trip(self):
        """Additive metadata fields should serialize/deserialize without contract breakage."""
        cut = FillerCutRange(
            start_seconds=10.0,
            end_seconds=10.3,
            word="um",
            confidence=0.92,
            category="disfluency",
            context_before="so we were",
            context_after="thinking about",
            editorial_action="remove",
            editorial_note="remove repeated hesitation",
            snapped=True,
            original_start=9.95,
            original_end=10.34,
            smoothing="micro_fade",
            smoothing_audio_ms=30.0,
        )

        payload = cut.model_dump()
        hydrated = FillerCutRange.model_validate(payload)

        assert hydrated.category == "disfluency"
        assert hydrated.context_before == "so we were"
        assert hydrated.context_after == "thinking about"
        assert hydrated.editorial_action == "remove"
        assert hydrated.snapped is True
        assert hydrated.original_start == pytest.approx(9.95)
        assert hydrated.original_end == pytest.approx(10.34)
        assert hydrated.smoothing == "micro_fade"
        assert hydrated.smoothing_audio_ms == pytest.approx(30.0)

    def test_content_cut_supports_smoothing_metadata_round_trip(self):
        """Content cuts should keep optional smoothing overrides and snap metadata."""
        cut = ContentCutRange(
            start_seconds=40.0,
            end_seconds=48.0,
            reason="off-topic tangent",
            editorial_action="remove",
            snapped=True,
            original_start=39.84,
            original_end=48.16,
            smoothing="dissolve",
            smoothing_audio_ms=150.0,
            smoothing_video_ms=300.0,
        )

        payload = cut.model_dump()
        hydrated = ContentCutRange.model_validate(payload)

        assert hydrated.reason == "off-topic tangent"
        assert hydrated.editorial_action == "remove"
        assert hydrated.snapped is True
        assert hydrated.original_start == pytest.approx(39.84)
        assert hydrated.original_end == pytest.approx(48.16)
        assert hydrated.smoothing == "dissolve"
        assert hydrated.smoothing_audio_ms == pytest.approx(150.0)
        assert hydrated.smoothing_video_ms == pytest.approx(300.0)

    def test_legacy_edit_plan_payload_still_validates_without_new_fields(self):
        """Legacy payloads without Phase 7 metadata should remain valid."""
        payload = {
            "filler_cuts": [
                {
                    "start_seconds": 1.0,
                    "end_seconds": 1.3,
                    "word": "uh",
                    "confidence": 0.8,
                }
            ],
            "content_cuts": [
                {
                    "start_seconds": 12.0,
                    "end_seconds": 13.1,
                    "reason": "repeat",
                }
            ],
            "clip_ranges": [{"start_seconds": 22.0, "end_seconds": 27.0, "description": "clip"}],
        }

        plan = EditPlan.model_validate(payload)

        assert len(plan.filler_cuts) == 1
        assert len(plan.content_cuts) == 1
        assert plan.filler_cuts[0].category == ""
        assert plan.filler_cuts[0].editorial_action == "remove"
        assert plan.content_cuts[0].smoothing == "crossfade"
        assert plan.content_cuts[0].original_start is None

    def test_original_range_metadata_requires_both_start_and_end(self):
        """Partial original range metadata should fail fast for both cut types."""
        with pytest.raises(ValidationError):
            FillerCutRange(
                start_seconds=2.0,
                end_seconds=2.2,
                word="um",
                original_start=1.9,
            )

        with pytest.raises(ValidationError):
            ContentCutRange(
                start_seconds=6.0,
                end_seconds=6.8,
                reason="pause",
                original_end=6.9,
            )
