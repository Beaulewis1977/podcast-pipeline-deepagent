"""Tests for the dev-only FastMCP FFmpeg server.

Coverage areas:
1. Tool registration — all 14 toolkit operations are registered as MCP tools.
2. Invocation mapping — each tool constructs the correct toolkit request and
   returns a JSON-safe dict (toolkit calls are mocked to avoid FFmpeg I/O).
3. Dev-only import boundaries — production pipeline stages never import from
   the mcp package; missing fastmcp raises a clear ImportError.
4. Isolation — mcp package is absent from pipeline/stage __init__ imports.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from podcast_pipeline.utils.ffmpeg_toolkit import FFmpegToolkitError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_server() -> types.ModuleType:
    """Import the server module, bypassing module cache for isolation."""
    mod_name = "podcast_pipeline.mcp.ffmpeg_server"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# 1. Tool registration — all 14 tools must be registered
# ---------------------------------------------------------------------------


ALL_TOOL_NAMES = [
    "mcp_probe_media",
    "mcp_extract_frame",
    "mcp_detect_hardware_encoders",
    "mcp_transcode",
    "mcp_normalize_loudness",
    "mcp_burn_captions",
    "mcp_overlay_image",
    "mcp_apply_filtergraph",
    "mcp_denoise",
    "mcp_trim_segment",
    "mcp_concat_segments",
    "mcp_mix_audio",
    "mcp_sync_tracks",
    "mcp_package_hls",
]

TOOLKIT_GROUPS = {
    "probe_and_inspect": ["mcp_probe_media", "mcp_extract_frame", "mcp_detect_hardware_encoders"],
    "encode_and_transcode": ["mcp_transcode", "mcp_normalize_loudness"],
    "filter_and_overlay": [
        "mcp_burn_captions",
        "mcp_overlay_image",
        "mcp_apply_filtergraph",
        "mcp_denoise",
    ],
    "edit_and_assemble": [
        "mcp_trim_segment",
        "mcp_concat_segments",
        "mcp_mix_audio",
        "mcp_sync_tracks",
    ],
    "package_and_deliver": ["mcp_package_hls"],
}


@pytest.mark.asyncio
async def test_registration_all_14_tools() -> None:
    """All 14 toolkit operations must be registered as MCP tools."""
    server = _import_server()
    mcp = server.mcp
    tools = await mcp.list_tools()
    registered_names = {t.name for t in tools}
    assert len(registered_names) == 14, (
        f"Expected 14 tools, got {len(registered_names)}: {registered_names}"
    )
    for expected in ALL_TOOL_NAMES:
        assert expected in registered_names, f"Tool '{expected}' not registered"


@pytest.mark.asyncio
async def test_registration_each_group() -> None:
    """Tools from all 5 toolkit groups must be present."""
    server = _import_server()
    mcp = server.mcp
    tools = await mcp.list_tools()
    registered_names = {t.name for t in tools}

    for group, expected_tools in TOOLKIT_GROUPS.items():
        for tool_name in expected_tools:
            assert tool_name in registered_names, (
                f"Group '{group}' tool '{tool_name}' not registered"
            )


@pytest.mark.asyncio
async def test_registration_exact_count_no_duplicates() -> None:
    """No duplicate or extra tools beyond the required 14."""
    server = _import_server()
    mcp = server.mcp
    tools = await mcp.list_tools()
    names = [t.name for t in tools]
    assert len(names) == len(set(names)), f"Duplicate tools found: {names}"
    assert len(names) == 14


# ---------------------------------------------------------------------------
# 2. Invocation mapping — tools delegate to toolkit functions
# ---------------------------------------------------------------------------


def _mock_probe_result() -> MagicMock:
    """Return a mock ProbeMediaResult-like Pydantic model."""
    mock = MagicMock()
    mock.model_dump.return_value = {
        "path": "/tmp/test.mp4",
        "format_name": "mp4",
        "duration": 120.0,
        "size_bytes": 1024000,
        "bit_rate": 500000,
        "streams": [],
        "video": None,
        "audio": None,
        "audio_track_count": 0,
    }
    return mock


def _mock_path_result(output: str = "/tmp/out.mp4") -> MagicMock:
    """Return a mock result with only output_path."""
    mock = MagicMock()
    mock.model_dump.return_value = {"output_path": output}
    return mock


def _mock_transcode_result() -> MagicMock:
    mock = MagicMock()
    mock.model_dump.return_value = {
        "output_path": "/tmp/out.mp4",
        "size_bytes": 2048000,
        "encode_time_s": 15.3,
    }
    return mock


def _mock_loudness_result() -> MagicMock:
    mock = MagicMock()
    mock.model_dump.return_value = {
        "output_path": "/tmp/out.wav",
        "input_lufs": -18.2,
        "output_lufs": -14.0,
    }
    return mock


def _mock_filtergraph_result() -> MagicMock:
    mock = MagicMock()
    mock.model_dump.return_value = {
        "output_path": "/tmp/out.mp4",
        "applied_filters": ["eq"],
    }
    return mock


def _mock_concat_result() -> MagicMock:
    mock = MagicMock()
    mock.model_dump.return_value = {
        "output_path": "/tmp/out.mp4",
        "total_duration_s": 60.0,
    }
    return mock


def _mock_sync_result() -> MagicMock:
    mock = MagicMock()
    mock.model_dump.return_value = {
        "output_path": "/tmp/out.mp4",
        "offset_ms": 123.4,
        "confidence": 0.87,
    }
    return mock


def _mock_hls_result() -> MagicMock:
    mock = MagicMock()
    mock.model_dump.return_value = {
        "master_playlist_path": "/tmp/hls/master.m3u8",
        "segment_count": 12,
        "total_size_bytes": 8192000,
    }
    return mock


def _mock_hw_result() -> MagicMock:
    mock = MagicMock()
    mock.model_dump.return_value = {
        "nvenc_h264": True,
        "nvenc_hevc": True,
        "nvenc_av1": False,
        "quicksync_h264": False,
        "quicksync_hevc": False,
        "videotoolbox_h264": False,
        "videotoolbox_hevc": False,
        "software_h264": True,
        "software_hevc": True,
        "software_av1": False,
    }
    return mock


@patch("podcast_pipeline.mcp.ffmpeg_server.probe_media")
def test_tool_probe_media(mock_probe: MagicMock) -> None:
    """mcp_probe_media delegates to probe_media with correct Path argument."""
    mock_probe.return_value = _mock_probe_result()
    server = _import_server()

    result = server.mcp_probe_media(input_path="/tmp/test.mp4")
    mock_probe.assert_called_once_with(Path("/tmp/test.mp4"))
    assert result["format_name"] == "mp4"
    assert result["duration"] == 120.0


@patch("podcast_pipeline.mcp.ffmpeg_server.extract_frame")
def test_tool_extract_frame(mock_fn: MagicMock) -> None:
    """mcp_extract_frame delegates to extract_frame with correct request."""
    mock_fn.return_value = _mock_path_result("/tmp/frame.png")
    server = _import_server()

    result = server.mcp_extract_frame(
        input_path="/tmp/test.mp4",
        timestamp_s=10.5,
        output_path="/tmp/frame.png",
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.path == Path("/tmp/test.mp4")
    assert call_req.timestamp_s == 10.5
    assert result["output_path"] == "/tmp/frame.png"


@patch("podcast_pipeline.mcp.ffmpeg_server.detect_hardware_encoders")
def test_tool_detect_hardware_encoders_no_cache(mock_fn: MagicMock) -> None:
    """mcp_detect_hardware_encoders(use_cache=False) calls detect_hardware_encoders."""
    mock_fn.return_value = _mock_hw_result()
    server = _import_server()

    # Force use_cache=False so we go through detect_hardware_encoders
    result = server.mcp_detect_hardware_encoders(use_cache=False)
    mock_fn.assert_called_once_with(use_cache=False)
    assert result["nvenc_h264"] is True


def test_tool_detect_hardware_encoders_uses_cached_value() -> None:
    """mcp_detect_hardware_encoders(use_cache=True) returns _hw_info when populated."""
    server = _import_server()
    # Directly inject a fake cached value
    fake_hw = _mock_hw_result()
    original = server._hw_info
    try:
        server._hw_info = fake_hw
        result = server.mcp_detect_hardware_encoders(use_cache=True)
        assert result["nvenc_h264"] is True
    finally:
        server._hw_info = original


@patch("podcast_pipeline.mcp.ffmpeg_server.transcode")
def test_tool_transcode(mock_fn: MagicMock) -> None:
    """mcp_transcode delegates to transcode with correct request model."""
    mock_fn.return_value = _mock_transcode_result()
    server = _import_server()

    result = server.mcp_transcode(
        input_path="/tmp/in.mp4",
        output_path="/tmp/out.mp4",
        codec="h264",
        quality_preset="fast",
        bit_depth=8,
        hw_accel="none",
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.input_path == Path("/tmp/in.mp4")
    assert call_req.codec.value == "h264"
    assert call_req.quality_preset.value == "fast"
    assert call_req.bit_depth == 8
    assert call_req.hw_accel.value == "none"
    assert result["encode_time_s"] == 15.3


@patch("podcast_pipeline.mcp.ffmpeg_server.normalize_loudness")
def test_tool_normalize_loudness(mock_fn: MagicMock) -> None:
    """mcp_normalize_loudness delegates with correct LUFS targets."""
    mock_fn.return_value = _mock_loudness_result()
    server = _import_server()

    result = server.mcp_normalize_loudness(
        input_path="/tmp/in.wav",
        output_path="/tmp/out.wav",
        target_lufs=-16.0,
        true_peak_dbtp=-2.0,
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.target_lufs == -16.0
    assert call_req.true_peak_dbtp == -2.0
    assert result["input_lufs"] == -18.2


@patch("podcast_pipeline.mcp.ffmpeg_server.burn_captions")
def test_tool_burn_captions(mock_fn: MagicMock) -> None:
    """mcp_burn_captions delegates to burn_captions with correct paths."""
    mock_fn.return_value = _mock_path_result("/tmp/out.mp4")
    server = _import_server()

    result = server.mcp_burn_captions(
        video_path="/tmp/video.mp4",
        ass_path="/tmp/captions.ass",
        output_path="/tmp/out.mp4",
        force_style="FontSize=24",
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.video_path == Path("/tmp/video.mp4")
    assert call_req.ass_path == Path("/tmp/captions.ass")
    assert call_req.force_style == "FontSize=24"
    assert result["output_path"] == "/tmp/out.mp4"


@patch("podcast_pipeline.mcp.ffmpeg_server.overlay_image")
def test_tool_overlay_image(mock_fn: MagicMock) -> None:
    """mcp_overlay_image delegates with correct position enum."""
    mock_fn.return_value = _mock_path_result("/tmp/out.mp4")
    server = _import_server()

    result = server.mcp_overlay_image(
        video_path="/tmp/video.mp4",
        image_path="/tmp/logo.png",
        output_path="/tmp/out.mp4",
        position="bottom_right",
        opacity=0.6,
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.position.value == "bottom_right"
    assert call_req.opacity == 0.6
    assert result["output_path"] == "/tmp/out.mp4"


@patch("podcast_pipeline.mcp.ffmpeg_server.apply_filtergraph")
def test_tool_apply_filtergraph(mock_fn: MagicMock) -> None:
    """mcp_apply_filtergraph delegates with correct filtergraph string."""
    mock_fn.return_value = _mock_filtergraph_result()
    server = _import_server()

    result = server.mcp_apply_filtergraph(
        input_path="/tmp/in.mp4",
        output_path="/tmp/out.mp4",
        filtergraph="eq=brightness=0.1",
        validate_first=False,
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.filtergraph == "eq=brightness=0.1"
    assert call_req.validate_first is False
    assert result["applied_filters"] == ["eq"]


@patch("podcast_pipeline.mcp.ffmpeg_server.denoise")
def test_tool_denoise(mock_fn: MagicMock) -> None:
    """mcp_denoise delegates with correct method and strength enums."""
    mock_fn.return_value = _mock_path_result("/tmp/out.mp4")
    server = _import_server()

    result = server.mcp_denoise(
        input_path="/tmp/in.mp4",
        output_path="/tmp/out.mp4",
        method="nlmeans",
        strength="heavy",
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.method.value == "nlmeans"
    assert call_req.strength.value == "heavy"
    assert result["output_path"] == "/tmp/out.mp4"


@patch("podcast_pipeline.mcp.ffmpeg_server.trim_segment")
def test_tool_trim_segment(mock_fn: MagicMock) -> None:
    """mcp_trim_segment delegates with correct start/end times."""
    mock_trim = MagicMock()
    mock_trim.model_dump.return_value = {
        "output_path": "/tmp/clip.mp4",
        "actual_start_s": 10.0,
        "actual_end_s": 30.0,
    }
    mock_fn.return_value = mock_trim
    server = _import_server()

    result = server.mcp_trim_segment(
        input_path="/tmp/in.mp4",
        output_path="/tmp/clip.mp4",
        start_s=10.0,
        end_s=30.0,
        copy_codec=True,
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.start_s == 10.0
    assert call_req.end_s == 30.0
    assert call_req.copy_codec is True
    assert result["actual_start_s"] == 10.0


@patch("podcast_pipeline.mcp.ffmpeg_server.concat_segments")
def test_tool_concat_segments(mock_fn: MagicMock) -> None:
    """mcp_concat_segments converts string list to Path list in request."""
    mock_fn.return_value = _mock_concat_result()
    server = _import_server()

    result = server.mcp_concat_segments(
        segments=["/tmp/a.mp4", "/tmp/b.mp4"],
        output_path="/tmp/out.mp4",
        transition="crossfade",
        transition_duration_s=0.8,
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.segments == [Path("/tmp/a.mp4"), Path("/tmp/b.mp4")]
    assert call_req.transition.value == "crossfade"
    assert call_req.transition_duration_s == 0.8
    assert result["total_duration_s"] == 60.0


@patch("podcast_pipeline.mcp.ffmpeg_server.mix_audio")
def test_tool_mix_audio(mock_fn: MagicMock) -> None:
    """mcp_mix_audio delegates with correct ducking parameters."""
    mock_fn.return_value = _mock_path_result("/tmp/mixed.wav")
    server = _import_server()

    result = server.mcp_mix_audio(
        speech_path="/tmp/speech.mp4",
        music_path="/tmp/music.mp3",
        output_path="/tmp/mixed.wav",
        music_volume_db=-15.0,
        duck_enabled=True,
        duck_ratio=3.0,
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.music_volume_db == -15.0
    assert call_req.duck_ratio == 3.0
    assert result["output_path"] == "/tmp/mixed.wav"


@patch("podcast_pipeline.mcp.ffmpeg_server.sync_tracks")
def test_tool_sync_tracks(mock_fn: MagicMock) -> None:
    """mcp_sync_tracks delegates to sync_tracks with correct search window."""
    mock_fn.return_value = _mock_sync_result()
    server = _import_server()

    result = server.mcp_sync_tracks(
        reference_path="/tmp/ref.mp4",
        external_path="/tmp/mic.wav",
        output_path="/tmp/synced.mp4",
        search_window_s=30.0,
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert call_req.search_window_s == 30.0
    assert result["offset_ms"] == 123.4
    assert result["confidence"] == 0.87


@patch("podcast_pipeline.mcp.ffmpeg_server.package_hls")
def test_tool_package_hls_defaults(mock_fn: MagicMock) -> None:
    """mcp_package_hls uses default 3-rung variant ladder when variants=None."""
    mock_fn.return_value = _mock_hls_result()
    server = _import_server()

    result = server.mcp_package_hls(
        input_path="/tmp/in.mp4",
        output_dir="/tmp/hls",
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert len(call_req.variants) == 3
    bitrates = {v.bitrate_kbps for v in call_req.variants}
    assert bitrates == {4000, 2000, 800}
    assert result["segment_count"] == 12


@patch("podcast_pipeline.mcp.ffmpeg_server.package_hls")
def test_tool_package_hls_custom_variants(mock_fn: MagicMock) -> None:
    """mcp_package_hls accepts custom variant ladder via variants list."""
    mock_fn.return_value = _mock_hls_result()
    server = _import_server()

    result = server.mcp_package_hls(
        input_path="/tmp/in.mp4",
        output_dir="/tmp/hls",
        variants=[
            {"bitrate_kbps": 1000, "width": 640, "height": 360},
        ],
    )
    assert mock_fn.called
    call_req = mock_fn.call_args[0][0]
    assert len(call_req.variants) == 1
    assert call_req.variants[0].bitrate_kbps == 1000
    assert result["master_playlist_path"] == "/tmp/hls/master.m3u8"


# ---------------------------------------------------------------------------
# 3. Error handling — toolkit errors surface as dict with error/operation keys
# ---------------------------------------------------------------------------


@patch("podcast_pipeline.mcp.ffmpeg_server.probe_media")
def test_tool_error_returns_error_dict(mock_probe: MagicMock) -> None:
    """When toolkit raises FFmpegToolkitError, tool returns error/operation dict."""
    mock_probe.side_effect = FFmpegToolkitError(
        "ffprobe failed",
        operation="probe_media",
        returncode=1,
        stderr_excerpt="file not found",
    )
    server = _import_server()

    result = server.mcp_probe_media(input_path="/nonexistent.mp4")
    assert "error" in result
    assert result["operation"] == "probe_media"
    assert "ffprobe failed" in result["error"]


@patch("podcast_pipeline.mcp.ffmpeg_server.transcode")
def test_tool_invalid_enum_returns_error_dict(mock_fn: MagicMock) -> None:
    """Invalid enum value (e.g., bad codec) returns error dict without raising."""
    server = _import_server()
    result = server.mcp_transcode(
        input_path="/tmp/in.mp4",
        output_path="/tmp/out.mp4",
        codec="not_a_real_codec",
    )
    assert "error" in result
    mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Dev-only isolation — mcp package absent from production stage imports
# ---------------------------------------------------------------------------


def _production_module_introduces_mcp(module_name: str) -> list[str]:
    """Check whether importing a production module causes mcp modules to appear.

    Temporarily removes any existing mcp entries from sys.modules, imports the
    target production module fresh (clearing its cache entry first), then checks
    whether any new podcast_pipeline.mcp entries appeared. Restores sys.modules
    afterwards.
    """
    # Snapshot and temporarily remove all mcp-related modules
    mcp_snapshot: dict[str, Any] = {
        k: v for k, v in sys.modules.items() if "podcast_pipeline.mcp" in k
    }
    for k in mcp_snapshot:
        sys.modules.pop(k)

    # Also clear the target production module to force a fresh import
    prod_snapshot = sys.modules.pop(module_name, None)

    try:
        importlib.import_module(module_name)
        introduced = [k for k in sys.modules if "podcast_pipeline.mcp" in k]
    finally:
        # Restore mcp modules (so other tests continue to work)
        sys.modules.update(mcp_snapshot)
        # Restore the production module cache entry if it was present
        if prod_snapshot is not None:
            sys.modules[module_name] = prod_snapshot

    return introduced


def test_isolation_pipeline_does_not_import_mcp() -> None:
    """Importing podcast_pipeline.pipeline must not introduce mcp modules."""
    introduced = _production_module_introduces_mcp("podcast_pipeline.pipeline")
    assert introduced == [], f"Production pipeline imported mcp modules: {introduced}"


def test_isolation_stages_do_not_import_mcp() -> None:
    """Importing podcast_pipeline.stages must not introduce mcp modules."""
    introduced = _production_module_introduces_mcp("podcast_pipeline.stages")
    assert introduced == [], f"Stages imported mcp modules: {introduced}"


def test_isolation_providers_do_not_import_mcp() -> None:
    """Importing podcast_pipeline.providers must not introduce mcp modules."""
    introduced = _production_module_introduces_mcp("podcast_pipeline.providers")
    assert introduced == [], f"Providers imported mcp modules: {introduced}"


def test_dev_only_missing_fastmcp_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If fastmcp is missing, importing the server raises ImportError with guidance."""
    # Remove the server module from cache so we can re-import with mocked fastmcp
    mod_name = "podcast_pipeline.mcp.ffmpeg_server"
    original = sys.modules.pop(mod_name, None)

    # Simulate fastmcp being absent
    original_fastmcp = sys.modules.pop("fastmcp", None)
    monkeypatch.setitem(sys.modules, "fastmcp", None)  # type: ignore[arg-type]

    try:
        with pytest.raises(ImportError, match="dev-only dependency"):
            importlib.import_module(mod_name)
    finally:
        # Restore original state
        if original is not None:
            sys.modules[mod_name] = original
        if original_fastmcp is not None:
            sys.modules["fastmcp"] = original_fastmcp
        elif "fastmcp" in sys.modules:
            del sys.modules["fastmcp"]


def test_mcp_init_package_exports_nothing_to_production() -> None:
    """podcast_pipeline.mcp.__init__ must export an empty __all__."""
    import podcast_pipeline.mcp as mcp_pkg

    assert mcp_pkg.__all__ == []


# ---------------------------------------------------------------------------
# 5. _path_to_str helper — ensures Path serialisation is JSON-safe
# ---------------------------------------------------------------------------


def test_path_to_str_converts_paths() -> None:
    """_path_to_str recursively converts Path objects to strings."""
    server = _import_server()
    raw: dict[str, Any] = {
        "output_path": Path("/tmp/out.mp4"),
        "nested": {"sub_path": Path("/tmp/sub")},
        "items": [Path("/tmp/item1"), "/string"],
    }
    result = server._path_to_str(raw)
    assert result["output_path"] == "/tmp/out.mp4"
    assert result["nested"]["sub_path"] == "/tmp/sub"
    assert result["items"][0] == "/tmp/item1"
    assert result["items"][1] == "/string"


def test_path_to_str_leaves_non_paths_unchanged() -> None:
    """_path_to_str does not modify int, float, bool, or None values."""
    server = _import_server()
    raw: dict[str, Any] = {
        "count": 5,
        "ratio": 0.87,
        "enabled": True,
        "maybe": None,
    }
    result = server._path_to_str(raw)
    assert result == raw
