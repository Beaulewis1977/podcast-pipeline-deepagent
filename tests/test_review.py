"""Review and export-target normalization tests."""

from podcast_pipeline.export_targets import (
    DEFAULT_EXPORT_PLATFORMS,
    SUPPORTED_EXPORT_PLATFORMS,
    normalize_export_platforms,
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
