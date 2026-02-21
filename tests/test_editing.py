"""Tests for boundary-snapping editing helpers."""

import pytest

from podcast_pipeline.utils.editing import (
    WordBoundary,
    find_word_boundaries,
    snap_cut_range,
    snap_to_word_boundary,
)


def test_find_word_boundaries_extracts_gaps_from_start_end_keys() -> None:
    """Inter-word gaps should be converted into boundary midpoints."""
    words = [
        {"word": "hello", "start": 0.0, "end": 0.3},
        {"word": "world", "start": 0.42, "end": 0.7},
        {"word": "again", "start": 0.9, "end": 1.1},
    ]

    boundaries = find_word_boundaries(words)

    assert len(boundaries) == 2
    assert boundaries[0].time == 0.36
    assert boundaries[0].gap_duration == 0.12
    assert boundaries[0].word_before == "hello"
    assert boundaries[0].word_after == "world"
    assert boundaries[1].time == 0.8


def test_find_word_boundaries_supports_seconds_key_variants() -> None:
    """Extractor should read start_seconds/end_seconds fallback keys."""
    words = [
        {"word": "one", "start_seconds": 2.0, "end_seconds": 2.2},
        {"word": "two", "start_seconds": 2.5, "end_seconds": 2.8},
    ]

    boundaries = find_word_boundaries(words)

    assert len(boundaries) == 1
    assert boundaries[0].time == 2.35
    assert boundaries[0].gap_duration == pytest.approx(0.3)


def test_find_word_boundaries_ignores_invalid_or_non_forward_entries() -> None:
    """Malformed word rows should be ignored instead of raising."""
    words = [
        {"word": "bad", "start": "x", "end": 0.1},
        {"word": "reverse", "start": 0.4, "end": 0.2},
        {"word": "valid", "start": 1.0, "end": 1.2},
        {"word": "next", "start": 1.4, "end": 1.6},
    ]

    boundaries = find_word_boundaries(words)

    assert len(boundaries) == 1
    assert boundaries[0].word_before == "valid"
    assert boundaries[0].word_after == "next"


def test_snap_to_word_boundary_uses_nearest_direction_by_default() -> None:
    """Nearest mode should snap to the closest candidate within max shift."""
    boundaries = [
        WordBoundary(time=9.8, gap_duration=0.04, word_before="a", word_after="b"),
        WordBoundary(time=10.1, gap_duration=0.02, word_before="b", word_after="c"),
    ]

    snapped = snap_to_word_boundary(10.0, boundaries, max_shift_seconds=0.3)

    assert snapped == 10.1


def test_snap_to_word_boundary_before_and_after_constraints() -> None:
    """Directional mode should only choose candidates on the requested side."""
    boundaries = [
        WordBoundary(time=9.7, gap_duration=0.03, word_before="a", word_after="b"),
        WordBoundary(time=10.2, gap_duration=0.03, word_before="c", word_after="d"),
    ]

    snapped_before = snap_to_word_boundary(
        10.0,
        boundaries,
        direction="before",
        max_shift_seconds=0.4,
    )
    snapped_after = snap_to_word_boundary(
        10.0,
        boundaries,
        direction="after",
        max_shift_seconds=0.4,
    )

    assert snapped_before == 9.7
    assert snapped_after == 10.2


def test_snap_to_word_boundary_respects_max_shift() -> None:
    """When no candidate is in range, the original cut time should remain unchanged."""
    boundaries = [WordBoundary(time=8.9, gap_duration=0.1, word_before="a", word_after="b")]

    snapped = snap_to_word_boundary(10.0, boundaries, max_shift_seconds=0.2)

    assert snapped == 10.0


def test_snap_to_word_boundary_prefers_longer_gap_when_scores_tie() -> None:
    """Weighted scoring should prefer longer silence gaps when equally distant."""
    boundaries = [
        WordBoundary(time=9.9, gap_duration=0.01, word_before="a", word_after="b"),
        WordBoundary(time=10.1, gap_duration=0.6, word_before="c", word_after="d"),
    ]

    snapped = snap_to_word_boundary(
        10.0,
        boundaries,
        max_shift_seconds=0.2,
        prefer_longer_gaps=True,
    )

    assert snapped == 10.1


def test_snap_cut_range_snaps_start_before_and_end_after() -> None:
    """Range snapping should preserve directional intent for start/end."""
    boundaries = [
        WordBoundary(time=2.9, gap_duration=0.2, word_before="a", word_after="b"),
        WordBoundary(time=5.2, gap_duration=0.2, word_before="b", word_after="c"),
    ]

    snapped = snap_cut_range(3.0, 5.0, boundaries, max_shift_seconds=0.3)

    assert snapped == (2.9, 5.2)


def test_snap_cut_range_leaves_side_unchanged_when_no_directional_match() -> None:
    """Each side should independently fallback when no directional boundary exists."""
    boundaries = [WordBoundary(time=3.1, gap_duration=0.2, word_before="a", word_after="b")]

    snapped = snap_cut_range(3.12, 3.13, boundaries, max_shift_seconds=0.3)

    assert snapped == (3.1, 3.13)


def test_snap_cut_range_returns_original_for_non_forward_input() -> None:
    """Degenerate input ranges should be unchanged."""
    boundaries = [WordBoundary(time=5.0, gap_duration=0.2, word_before="a", word_after="b")]

    snapped = snap_cut_range(4.0, 4.0, boundaries)

    assert snapped == (4.0, 4.0)
