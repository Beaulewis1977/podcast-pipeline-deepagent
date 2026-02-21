"""Helpers for boundary-safe cut placement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

SnapDirection = Literal["nearest", "before", "after"]


@dataclass(frozen=True, slots=True)
class WordBoundary:
    """Safe cut point between two adjacent words."""

    time: float
    gap_duration: float
    word_before: str
    word_after: str


def _coerce_seconds(value: Any) -> float | None:
    """Convert raw timestamp values into non-negative seconds."""
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def _coerce_word_entry(entry: Mapping[str, Any]) -> tuple[float, float, str] | None:
    """Normalize transcript word entries across known key variants."""
    start = _coerce_seconds(entry.get("start"))
    if start is None:
        start = _coerce_seconds(entry.get("start_seconds"))
    end = _coerce_seconds(entry.get("end"))
    if end is None:
        end = _coerce_seconds(entry.get("end_seconds"))
    if start is None or end is None or end <= start:
        return None
    return (start, end, str(entry.get("word", "")).strip())


def find_word_boundaries(
    words: Sequence[Mapping[str, Any]],
    *,
    min_gap_seconds: float = 0.01,
) -> list[WordBoundary]:
    """Extract inter-word silence boundaries from transcript word timings."""
    if min_gap_seconds < 0:
        raise ValueError("min_gap_seconds must be >= 0")

    normalized: list[tuple[float, float, str]] = []
    for raw in words:
        parsed = _coerce_word_entry(raw)
        if parsed is None:
            continue
        normalized.append(parsed)

    if len(normalized) < 2:
        return []

    ordered = sorted(normalized, key=lambda item: item[0])
    boundaries: list[WordBoundary] = []
    for index in range(len(ordered) - 1):
        current_start, current_end, current_word = ordered[index]
        del current_start
        next_start, _, next_word = ordered[index + 1]
        gap = next_start - current_end
        if gap < min_gap_seconds:
            continue
        boundaries.append(
            WordBoundary(
                time=(current_end + next_start) / 2.0,
                gap_duration=gap,
                word_before=current_word,
                word_after=next_word,
            )
        )
    return boundaries


def snap_to_word_boundary(
    cut_time: float,
    boundaries: Sequence[WordBoundary],
    *,
    direction: SnapDirection = "nearest",
    max_shift_seconds: float = 0.3,
    prefer_longer_gaps: bool = True,
) -> float:
    """Snap a cut timestamp to the nearest valid word boundary."""
    if direction not in {"nearest", "before", "after"}:
        raise ValueError("direction must be one of: nearest, before, after")
    if max_shift_seconds < 0:
        raise ValueError("max_shift_seconds must be >= 0")

    candidates: list[tuple[float, float, WordBoundary]] = []
    for boundary in boundaries:
        delta = boundary.time - cut_time
        distance = abs(delta)
        if distance > max_shift_seconds:
            continue
        if direction == "before" and delta > 0:
            continue
        if direction == "after" and delta < 0:
            continue

        score = distance
        if prefer_longer_gaps:
            score -= min(boundary.gap_duration * 0.1, 0.05)
        candidates.append((score, distance, boundary))

    if not candidates:
        return cut_time

    chosen = min(
        candidates,
        key=lambda row: (
            row[0],
            row[1],
            row[2].time,
        ),
    )
    return chosen[2].time


def snap_cut_range(
    start_seconds: float,
    end_seconds: float,
    boundaries: Sequence[WordBoundary],
    *,
    max_shift_seconds: float = 0.3,
) -> tuple[float, float]:
    """Snap both cut endpoints while preserving a valid forward range."""
    if end_seconds <= start_seconds:
        return start_seconds, end_seconds

    snapped_start = snap_to_word_boundary(
        start_seconds,
        boundaries,
        direction="before",
        max_shift_seconds=max_shift_seconds,
    )
    snapped_end = snap_to_word_boundary(
        end_seconds,
        boundaries,
        direction="after",
        max_shift_seconds=max_shift_seconds,
    )

    if snapped_end <= snapped_start:
        return start_seconds, end_seconds

    return snapped_start, snapped_end
