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
