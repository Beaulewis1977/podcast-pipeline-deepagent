"""FastMCP developer server — exposes all 14 Phase 9 toolkit operations.

This module is DEV-ONLY. It must NOT be imported by production pipeline stages.
FastMCP is a dev dependency only; importing this module outside a dev environment
will raise ImportError with a clear diagnostic message.

Usage (stdio transport for Claude Code):
    uv run --group dev python -m podcast_pipeline.mcp.ffmpeg_server

Tool groups:
    Group 1 — Probe & Inspect:   probe_media, extract_frame, detect_hardware_encoders
    Group 2 — Encode & Transcode: transcode, normalize_loudness
    Group 3 — Filter & Overlay:  burn_captions, overlay_image, apply_filtergraph, denoise
    Group 4 — Edit & Assemble:   trim_segment, concat_segments, mix_audio, sync_tracks
    Group 5 — Package & Deliver: package_hls

Each MCP tool is a thin wrapper that:
1. Accepts JSON-serializable scalars (no raw Pydantic objects over the wire)
2. Constructs the typed toolkit request model
3. Delegates to the corresponding toolkit function
4. Returns a JSON-serializable dict from the result model

The lifespan context manager runs detect_hardware_encoders() once at startup
and caches the result for the server lifetime.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from fastmcp import FastMCP
except ImportError as _fastmcp_err:
    raise ImportError(
        "FastMCP is a dev-only dependency. "
        "Install it with: uv sync --group dev\n"
        f"Original error: {_fastmcp_err}"
    ) from _fastmcp_err

from podcast_pipeline.utils.ffmpeg_toolkit import (
    ApplyFiltergraphRequest,
    BurnCaptionsRequest,
    ConcatSegmentsRequest,
    DenoiseMethod,
    DenoiseRequest,
    DenoiseStrength,
    ExtractFrameRequest,
    FFmpegToolkitError,
    HardwareEncoderInfo,
    HlsVariant,
    HwAccel,
    MixAudioRequest,
    NormalizeLoudnessRequest,
    OverlayImageRequest,
    OverlayPosition,
    PackageHlsRequest,
    QualityPreset,
    SyncTracksRequest,
    TranscodeRequest,
    TransitionType,
    TrimSegmentRequest,
    VideoCodec,
    apply_filtergraph,
    burn_captions,
    concat_segments,
    denoise,
    detect_hardware_encoders,
    extract_frame,
    mix_audio,
    normalize_loudness,
    overlay_image,
    package_hls,
    probe_media,
    sync_tracks,
    transcode,
    trim_segment,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# ---------------------------------------------------------------------------
# Module-level hardware encoder cache (populated in lifespan)
# ---------------------------------------------------------------------------

_hw_info: HardwareEncoderInfo | None = None


# ---------------------------------------------------------------------------
# Lifespan: cache hardware encoders once at startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(mcp: FastMCP) -> AsyncGenerator[None, None]:
    """Populate hardware encoder cache at server startup."""
    global _hw_info  # noqa: PLW0603
    _hw_info = detect_hardware_encoders(use_cache=False)
    yield
    # No cleanup needed for this server


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "ffmpeg-server",
    instructions=(
        "FFmpeg toolkit MCP server for local developer automation. "
        "Exposes all 14 Phase 9 media operations as MCP tools. "
        "Dev-only — not available in production pipeline execution."
    ),
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Helper: convert toolkit result models to JSON-safe dicts
# ---------------------------------------------------------------------------


def _path_to_str(obj: Any) -> Any:
    """Recursively convert Path values to strings for JSON serialisation."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _path_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_path_to_str(i) for i in obj]
    return obj


def _result_dict(model: Any) -> dict[str, Any]:
    """Dump a Pydantic result model to a JSON-safe dict."""
    result: dict[str, Any] = _path_to_str(model.model_dump())
    return result


# ---------------------------------------------------------------------------
# Group 1: Probe & Inspect
# ---------------------------------------------------------------------------


@mcp.tool()
def mcp_probe_media(input_path: str) -> dict[str, Any]:
    """Probe a media file and return full metadata (streams, duration, format).

    Args:
        input_path: Absolute path to the media file.

    Returns:
        ProbeMediaResult as a dict with format_name, duration, size_bytes,
        bit_rate, streams list, video/audio convenience fields, and
        audio_track_count.
    """
    try:
        result = probe_media(Path(input_path))
        return _result_dict(result)
    except FFmpegToolkitError as exc:
        return {"error": str(exc), "operation": exc.operation}


@mcp.tool()
def mcp_extract_frame(
    input_path: str,
    timestamp_s: float,
    output_path: str,
) -> dict[str, Any]:
    """Extract a single PNG frame from a video at the given timestamp.

    Args:
        input_path: Path to the source video file.
        timestamp_s: Timestamp in seconds (>= 0.0) to extract the frame from.
        output_path: Destination path for the PNG output.

    Returns:
        Dict with output_path on success, or error/operation keys on failure.
    """
    try:
        req = ExtractFrameRequest(
            path=Path(input_path),
            timestamp_s=timestamp_s,
            output_path=Path(output_path),
        )
        result = extract_frame(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "extract_frame"}


@mcp.tool()
def mcp_detect_hardware_encoders(use_cache: bool = True) -> dict[str, Any]:
    """Detect available hardware and software encoders on this machine.

    Uses a cached result from server startup when use_cache=True (recommended).

    Args:
        use_cache: Return the startup-cached result (default True).
                   Set False to re-probe (slower, but always fresh).

    Returns:
        HardwareEncoderInfo as a dict with boolean flags for nvenc_h264,
        nvenc_hevc, nvenc_av1, quicksync_*, videotoolbox_*, software_h264,
        software_hevc, software_av1.
    """
    if use_cache and _hw_info is not None:
        return _result_dict(_hw_info)
    info = detect_hardware_encoders(use_cache=use_cache)
    return _result_dict(info)


# ---------------------------------------------------------------------------
# Group 2: Encode & Transcode
# ---------------------------------------------------------------------------


@mcp.tool()
def mcp_transcode(
    input_path: str,
    output_path: str,
    codec: str = "hevc",
    quality_preset: str = "medium",
    bit_depth: int = 10,
    film_grain: int = 0,
    hw_accel: str = "auto",
    timeout: int = 3600,
) -> dict[str, Any]:
    """High-fidelity video transcode with codec, hardware, and quality selection.

    Args:
        input_path: Source video path.
        output_path: Destination video path.
        codec: Target codec — "h264", "hevc" (default), or "av1".
        quality_preset: FFmpeg preset — "ultrafast", "fast", "medium" (default),
                        "slow", or "veryslow".
        bit_depth: Bit depth, 8 or 10 (default 10, HEVC/AV1 only).
        film_grain: AV1 film grain synthesis level 0-50 (0 = disabled).
        hw_accel: Hardware acceleration — "auto" (default), "nvenc", or "none".
        timeout: FFmpeg timeout in seconds (default 3600).

    Returns:
        Dict with output_path, size_bytes, encode_time_s on success,
        or error/operation on failure.
    """
    try:
        req = TranscodeRequest(
            input_path=Path(input_path),
            output_path=Path(output_path),
            codec=VideoCodec(codec),
            quality_preset=QualityPreset(quality_preset),
            bit_depth=bit_depth,
            film_grain=film_grain,
            hw_accel=HwAccel(hw_accel),
            timeout=timeout,
        )
        result = transcode(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "transcode"}


@mcp.tool()
def mcp_normalize_loudness(
    input_path: str,
    output_path: str,
    target_lufs: float = -14.0,
    true_peak_dbtp: float = -1.0,
    timeout: int = 3600,
) -> dict[str, Any]:
    """EBU R128 two-pass loudness normalization.

    Args:
        input_path: Source audio/video path.
        output_path: Normalized output path.
        target_lufs: Target integrated loudness in LUFS (default -14.0, must be <= 0).
        true_peak_dbtp: True peak ceiling in dBTP (default -1.0, must be <= 0).
        timeout: FFmpeg timeout in seconds (default 3600).

    Returns:
        Dict with output_path, input_lufs, output_lufs on success,
        or error/operation on failure.
    """
    try:
        req = NormalizeLoudnessRequest(
            input_path=Path(input_path),
            output_path=Path(output_path),
            target_lufs=target_lufs,
            true_peak_dbtp=true_peak_dbtp,
            timeout=timeout,
        )
        result = normalize_loudness(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "normalize_loudness"}


# ---------------------------------------------------------------------------
# Group 3: Filter & Overlay
# ---------------------------------------------------------------------------


@mcp.tool()
def mcp_burn_captions(
    video_path: str,
    ass_path: str,
    output_path: str,
    force_style: str | None = None,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Burn ASS/SSA subtitle captions onto video using libass.

    Args:
        video_path: Source video path.
        ass_path: Path to the ASS subtitle file.
        output_path: Output video path with captions burned in.
        force_style: Optional ASS force_style override string
                     (e.g. "FontSize=24,PrimaryColour=&H00FFFFFF&").
        timeout: FFmpeg timeout in seconds (default 3600).

    Returns:
        Dict with output_path on success, or error/operation on failure.
    """
    try:
        req = BurnCaptionsRequest(
            video_path=Path(video_path),
            ass_path=Path(ass_path),
            output_path=Path(output_path),
            force_style=force_style,
            timeout=timeout,
        )
        result = burn_captions(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "burn_captions"}


@mcp.tool()
def mcp_overlay_image(
    video_path: str,
    image_path: str,
    output_path: str,
    position: str = "top_right",
    opacity: float = 0.8,
    fade_in_s: float = 0.0,
    fade_out_s: float = 0.0,
    scale: float = 1.0,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Composite a logo or watermark image onto video with opacity and fade.

    Args:
        video_path: Source video path.
        image_path: Path to the overlay image (PNG recommended for transparency).
        output_path: Output video path.
        position: Placement — "top_left", "top_right" (default), "bottom_left",
                  "bottom_right", or "center".
        opacity: Alpha transparency 0.0-1.0 (default 0.8).
        fade_in_s: Fade-in duration in seconds (default 0 = no fade).
        fade_out_s: Fade-out duration in seconds (default 0 = no fade).
        scale: Scale factor for the overlay image (default 1.0 = original size).
        timeout: FFmpeg timeout in seconds (default 3600).

    Returns:
        Dict with output_path on success, or error/operation on failure.
    """
    try:
        req = OverlayImageRequest(
            video_path=Path(video_path),
            image_path=Path(image_path),
            output_path=Path(output_path),
            position=OverlayPosition(position),
            opacity=opacity,
            fade_in_s=fade_in_s,
            fade_out_s=fade_out_s,
            scale=scale,
            timeout=timeout,
        )
        result = overlay_image(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "overlay_image"}


@mcp.tool()
def mcp_apply_filtergraph(
    input_path: str,
    output_path: str,
    filtergraph: str,
    validate_first: bool = True,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Apply a raw FFmpeg filtergraph with optional dry-run validation.

    Args:
        input_path: Source video/audio path.
        output_path: Filtered output path.
        filtergraph: FFmpeg -vf filtergraph expression (must not be empty).
        validate_first: Dry-run validate by encoding 1 frame before full run
                        (default True — recommended to catch syntax errors early).
        timeout: FFmpeg timeout in seconds (default 3600).

    Returns:
        Dict with output_path and applied_filters list on success,
        or error/operation on failure.
    """
    try:
        req = ApplyFiltergraphRequest(
            input_path=Path(input_path),
            output_path=Path(output_path),
            filtergraph=filtergraph,
            validate_first=validate_first,
            timeout=timeout,
        )
        result = apply_filtergraph(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "apply_filtergraph"}


@mcp.tool()
def mcp_denoise(
    input_path: str,
    output_path: str,
    method: str = "hqdn3d",
    strength: str = "medium",
    timeout: int = 3600,
) -> dict[str, Any]:
    """Apply video noise reduction (hqdn3d or nlmeans) at configurable strength.

    Args:
        input_path: Source video path.
        output_path: Denoised output video path.
        method: Denoising algorithm — "hqdn3d" (default, faster) or "nlmeans"
                (higher quality but slower).
        strength: Strength preset — "light", "medium" (default), or "heavy".
        timeout: FFmpeg timeout in seconds (default 3600).

    Returns:
        Dict with output_path on success, or error/operation on failure.
    """
    try:
        req = DenoiseRequest(
            input_path=Path(input_path),
            output_path=Path(output_path),
            method=DenoiseMethod(method),
            strength=DenoiseStrength(strength),
            timeout=timeout,
        )
        result = denoise(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "denoise"}


# ---------------------------------------------------------------------------
# Group 4: Edit & Assemble
# ---------------------------------------------------------------------------


@mcp.tool()
def mcp_trim_segment(
    input_path: str,
    output_path: str,
    start_s: float = 0.0,
    end_s: float | None = None,
    copy_codec: bool = True,
) -> dict[str, Any]:
    """Frame-accurate video segment cut between start and optional end timestamps.

    Args:
        input_path: Source video path.
        output_path: Trimmed segment output path.
        start_s: Start time in seconds (default 0.0, must be >= 0).
        end_s: End time in seconds (None = trim to end of file).
               Must be greater than start_s when provided.
        copy_codec: Use stream copy (faster, no re-encode) — default True.
                    Set False to allow filter-compatible output format.

    Returns:
        Dict with output_path, actual_start_s, actual_end_s on success,
        or error/operation on failure.
    """
    try:
        req = TrimSegmentRequest(
            input_path=Path(input_path),
            output_path=Path(output_path),
            start_s=start_s,
            end_s=end_s,
            copy_codec=copy_codec,
        )
        result = trim_segment(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "trim_segment"}


@mcp.tool()
def mcp_concat_segments(
    segments: list[str],
    output_path: str,
    transition: str = "none",
    transition_duration_s: float = 0.5,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Join multiple video/audio segments with an optional crossfade/dissolve transition.

    Args:
        segments: Ordered list of segment file paths (minimum 1).
        output_path: Concatenated output path.
        transition: Join transition — "none" (default, stream copy),
                    "crossfade", or "dissolve".
        transition_duration_s: Transition duration in seconds (default 0.5).
        timeout: FFmpeg timeout in seconds (default 3600).

    Returns:
        Dict with output_path and total_duration_s on success,
        or error/operation on failure.
    """
    try:
        req = ConcatSegmentsRequest(
            segments=[Path(s) for s in segments],
            output_path=Path(output_path),
            transition=TransitionType(transition),
            transition_duration_s=transition_duration_s,
            timeout=timeout,
        )
        result = concat_segments(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "concat_segments"}


@mcp.tool()
def mcp_mix_audio(
    speech_path: str,
    music_path: str,
    output_path: str,
    music_volume_db: float = -12.0,
    duck_enabled: bool = True,
    duck_threshold_db: float = -30.0,
    duck_ratio: float = 4.0,
    fade_in_s: float = 0.0,
    fade_out_s: float = 0.0,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Overlay background music with sidechain ducking when speech is present.

    Args:
        speech_path: Primary speech/video track path.
        music_path: Background music track path.
        output_path: Mixed audio output path.
        music_volume_db: Music volume adjustment in dB before ducking
                         (default -12.0).
        duck_enabled: Enable automatic sidechain ducking (default True).
        duck_threshold_db: Ducking activation threshold in dB (default -30.0).
        duck_ratio: Ducking compression ratio (default 4.0).
        fade_in_s: Music fade-in duration in seconds (default 0.0).
        fade_out_s: Music fade-out duration in seconds (default 0.0).
        timeout: FFmpeg timeout in seconds (default 3600).

    Returns:
        Dict with output_path on success, or error/operation on failure.
    """
    try:
        req = MixAudioRequest(
            speech_path=Path(speech_path),
            music_path=Path(music_path),
            output_path=Path(output_path),
            music_volume_db=music_volume_db,
            duck_enabled=duck_enabled,
            duck_threshold_db=duck_threshold_db,
            duck_ratio=duck_ratio,
            fade_in_s=fade_in_s,
            fade_out_s=fade_out_s,
            timeout=timeout,
        )
        result = mix_audio(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "mix_audio"}


@mcp.tool()
def mcp_sync_tracks(
    reference_path: str,
    external_path: str,
    output_path: str,
    search_window_s: float = 60.0,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Align an external audio track to a reference using cross-correlation.

    Uses a four-step algorithm: downsample to 8kHz mono, detect peak samples,
    scipy cross-correlation for sub-sample precision, then apply offset via
    FFmpeg -itsoffset flag.

    Args:
        reference_path: Reference audio/video path (primary track).
        external_path: External audio track path to align to reference.
        output_path: Muxed output path with aligned tracks.
        search_window_s: Maximum alignment search window in seconds
                         (default 60.0, capped at 60.0 internally).
        timeout: FFmpeg mux timeout in seconds (default 3600).

    Returns:
        Dict with output_path, offset_ms, confidence (0.0-1.0) on success,
        or error/operation on failure.
    """
    try:
        req = SyncTracksRequest(
            reference_path=Path(reference_path),
            external_path=Path(external_path),
            output_path=Path(output_path),
            search_window_s=search_window_s,
            timeout=timeout,
        )
        result = sync_tracks(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "sync_tracks"}


# ---------------------------------------------------------------------------
# Group 5: Package & Deliver
# ---------------------------------------------------------------------------


@mcp.tool()
def mcp_package_hls(
    input_path: str,
    output_dir: str,
    segment_duration: int = 6,
    variants: list[dict[str, int]] | None = None,
    timeout: int = 7200,
) -> dict[str, Any]:
    """Generate an HLS VOD package with a multi-bitrate adaptive variant ladder.

    Args:
        input_path: Source video path.
        output_dir: Output directory for HLS segments and playlists.
        segment_duration: HLS segment duration in seconds (default 6).
        variants: List of variant stream dicts, each with keys:
                  - bitrate_kbps (int, required): Video bitrate in kbps.
                  - width (int, required): Output width in pixels.
                  - height (int, required): Output height in pixels.
                  - audio_bitrate_kbps (int, optional, default 128): Audio bitrate.
                  Defaults to a standard 3-rung ladder:
                  [1080p@4000k, 720p@2000k, 480p@800k].
        timeout: FFmpeg timeout in seconds (default 7200).

    Returns:
        Dict with master_playlist_path, segment_count, total_size_bytes on
        success, or error/operation on failure.
    """
    if variants is None:
        variants = [
            {"bitrate_kbps": 4000, "width": 1920, "height": 1080},
            {"bitrate_kbps": 2000, "width": 1280, "height": 720},
            {"bitrate_kbps": 800, "width": 854, "height": 480},
        ]
    try:
        hls_variants = [HlsVariant(**v) for v in variants]
        req = PackageHlsRequest(
            input_path=Path(input_path),
            output_dir=Path(output_dir),
            segment_duration=segment_duration,
            variants=hls_variants,
            timeout=timeout,
        )
        result = package_hls(req)
        return _result_dict(result)
    except (FFmpegToolkitError, ValueError) as exc:
        return {"error": str(exc), "operation": "package_hls"}


# ---------------------------------------------------------------------------
# Entrypoint: stdio transport for Claude Code
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
