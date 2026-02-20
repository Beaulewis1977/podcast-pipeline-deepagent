"""Canonical export-target registry and normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, overload


@dataclass(frozen=True, slots=True)
class ExportTarget:
    """Metadata for a supported export target."""

    key: str
    label: str
    category: str
    description: str
    artifact_only: bool = False


EXPORT_TARGETS: tuple[ExportTarget, ...] = (
    ExportTarget("youtube", "YouTube", "video", "Long-form horizontal video"),
    ExportTarget("spotify", "Spotify", "audio", "Audio podcast (MP3)"),
    ExportTarget("apple", "Apple Podcasts", "audio", "Audio podcast (AAC)"),
    ExportTarget("spotify_video", "Spotify Video", "video", "Video podcast MP4 deliverable"),
    ExportTarget("apple_video", "Apple Video", "video", "Video podcast MP4 deliverable"),
    ExportTarget(
        "apple_hls",
        "Apple HLS",
        "package",
        "Provider hand-off HLS package artifacts",
        artifact_only=True,
    ),
    ExportTarget("tiktok", "TikTok", "video", "Vertical short-form video"),
    ExportTarget("instagram", "Instagram Reels", "video", "Vertical short-form video"),
    ExportTarget("linkedin", "LinkedIn", "video", "Square or landscape business video"),
    ExportTarget("twitter", "Twitter/X", "video", "Landscape short video"),
    ExportTarget("facebook", "Facebook", "video", "Landscape social video"),
)

SUPPORTED_EXPORT_PLATFORMS: tuple[str, ...] = tuple(target.key for target in EXPORT_TARGETS)
SUPPORTED_EXPORT_PLATFORM_SET: frozenset[str] = frozenset(SUPPORTED_EXPORT_PLATFORMS)
DEFAULT_EXPORT_PLATFORMS: tuple[str, str] = ("youtube", "spotify")


@overload
def normalize_export_platforms(
    platforms: Iterable[str] | None,
    *,
    fallback_to_default: bool = True,
    include_invalid: Literal[False] = False,
) -> list[str]: ...


@overload
def normalize_export_platforms(
    platforms: Iterable[str] | None,
    *,
    fallback_to_default: bool = True,
    include_invalid: Literal[True],
) -> tuple[list[str], list[str]]: ...


def normalize_export_platforms(
    platforms: Iterable[str] | None,
    *,
    fallback_to_default: bool = True,
    include_invalid: bool = False,
) -> list[str] | tuple[list[str], list[str]]:
    """Normalize export platform keys with deterministic ordering.

    Behavior:
    - trim + lowercase keys
    - deduplicate while preserving first-seen order
    - drop unsupported keys (optionally returning them)
    - return defaults when no valid keys remain (configurable)
    """

    normalized: list[str] = []
    invalid: list[str] = []
    seen_valid: set[str] = set()
    seen_invalid: set[str] = set()

    raw_values: list[object]
    if platforms is None:
        raw_values = []
    elif isinstance(platforms, str):
        raw_values = [platforms]
    else:
        raw_values = list(platforms)

    for raw in raw_values:
        if not isinstance(raw, str):
            text = str(raw)
            if text not in seen_invalid:
                invalid.append(text)
                seen_invalid.add(text)
            continue

        key = raw.strip().lower()
        if not key:
            continue

        if key in SUPPORTED_EXPORT_PLATFORM_SET:
            if key not in seen_valid:
                normalized.append(key)
                seen_valid.add(key)
            continue

        if key not in seen_invalid:
            invalid.append(key)
            seen_invalid.add(key)

    if not normalized and fallback_to_default:
        normalized = list(DEFAULT_EXPORT_PLATFORMS)

    if include_invalid:
        return normalized, invalid

    return normalized
