"""Regression tests for Streamlit UI workflow helpers."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_ui_app_metadata_prefers_intermediate_path(tmp_path: Path) -> None:
    """Canonical ingest metadata should be loaded from intermediate/metadata.json."""
    from podcast_pipeline.ui.app import _load_ingest_metadata

    canonical = tmp_path / "intermediate" / "metadata.json"
    legacy = tmp_path / "input" / "metadata.json"
    _write_json(canonical, {"duration": 91.2, "source": "canonical"})
    _write_json(legacy, {"duration": 10.0, "source": "legacy"})

    loaded = _load_ingest_metadata(tmp_path)

    assert loaded is not None
    assert loaded["duration"] == 91.2
    assert loaded["source"] == "canonical"


def test_ui_app_metadata_legacy_fallback_is_logged(tmp_path: Path) -> None:
    """Legacy metadata path should still work but emit a fallback warning."""
    from podcast_pipeline.ui.app import _load_ingest_metadata

    legacy = tmp_path / "input" / "metadata.json"
    _write_json(legacy, {"duration": 33.0, "source": "legacy"})

    with patch("podcast_pipeline.ui.app.logger.warning") as warning:
        loaded = _load_ingest_metadata(tmp_path)

    assert loaded is not None
    assert loaded["source"] == "legacy"
    warning.assert_called_with(
        "ingest_metadata_legacy_fallback",
        path=str(legacy),
        canonical_exists=False,
    )


def test_ui_app_preview_metadata_duration_drives_slider(tmp_path: Path) -> None:
    """Preview scrubber range should use canonical ingest metadata duration."""
    from podcast_pipeline.ui.app import render_video_preview

    _write_json(tmp_path / "intermediate" / "metadata.json", {"duration": 47.5})
    proxy = tmp_path / "intermediate" / "proxy.mp4"
    proxy.parent.mkdir(parents=True, exist_ok=True)
    proxy.write_bytes(b"video")

    mock_st = MagicMock()
    mock_st.slider.return_value = 0.0

    with patch("podcast_pipeline.ui.app.st", mock_st):
        render_video_preview("job-123", tmp_path)

    assert mock_st.video.called
    assert mock_st.slider.call_args.kwargs["max_value"] == 47.5


def test_ui_app_timeline_reads_metadata_for_duration_caption(tmp_path: Path) -> None:
    """Timeline should surface source duration from ingest metadata."""
    from podcast_pipeline.ui.app import render_timeline_editor

    _write_json(tmp_path / "intermediate" / "metadata.json", {"duration": 120.0})
    _write_json(tmp_path / "analysis" / "analysis.json", {"content_cuts": []})

    mock_st = MagicMock()
    mock_st.button.return_value = False
    mock_st.checkbox.return_value = False

    with patch("podcast_pipeline.ui.app.st", mock_st):
        render_timeline_editor("job-abc", tmp_path)

    mock_st.caption.assert_any_call("Source duration: 120.0s")
