"""Comprehensive tests for the FFmpeg toolkit (Phase 9 toolset).

Covers all 14 operations across 5 groups:
  Group 1: probe_media, extract_frame, detect_hardware_encoders
  Group 2: transcode, normalize_loudness
  Group 3: burn_captions, overlay_image, apply_filtergraph, denoise
  Group 4: trim_segment, concat_segments, mix_audio, sync_tracks
  Group 5: package_hls
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from podcast_pipeline.utils.ffmpeg import FFmpegError
from podcast_pipeline.utils.ffmpeg_toolkit import (
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
    StreamInfo,
    SyncTracksRequest,
    TranscodeRequest,
    TransitionType,
    TrimSegmentRequest,
    VideoCodec,
    _wrap_ffmpeg_error,
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

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_FAKE_PATH = Path("/fake/input.mp4")
_FAKE_OUT = Path("/fake/output.mp4")
_FAKE_ASS = Path("/fake/subs.ass")
_FAKE_IMG = Path("/fake/logo.png")


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    """Return a mock CompletedProcess."""
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.stdout = stdout
    cp.stderr = stderr
    cp.returncode = returncode
    return cp


def _ffmpeg_error(msg: str = "fail", stderr: str = "err detail", rc: int = 1) -> FFmpegError:
    return FFmpegError(msg, stderr=stderr, returncode=rc)


# ---------------------------------------------------------------------------
# FFmpegToolkitError — structured error
# ---------------------------------------------------------------------------


def test_ffmpeg_toolkit_error_stores_fields() -> None:
    err = FFmpegToolkitError(
        "something broke",
        operation="transcode",
        cmd_args=["-i", "in.mp4"],
        stderr_excerpt="codec not found",
        returncode=1,
    )
    assert err.operation == "transcode"
    assert err.cmd_args == ["-i", "in.mp4"]
    assert err.stderr_excerpt == "codec not found"
    assert err.returncode == 1


def test_ffmpeg_toolkit_error_str_includes_all_parts() -> None:
    err = FFmpegToolkitError(
        "encode failed",
        operation="transcode",
        stderr_excerpt="stderr snippet",
        returncode=2,
    )
    s = str(err)
    assert "transcode" in s
    assert "returncode=2" in s
    assert "stderr snippet" in s


def test_ffmpeg_toolkit_error_defaults() -> None:
    err = FFmpegToolkitError("bare error")
    assert err.operation == ""
    assert err.cmd_args == []
    assert err.stderr_excerpt == ""
    assert err.returncode == -1
    # __str__ should not include returncode=-1
    assert "returncode" not in str(err)


def test_wrap_ffmpeg_error_converts_fields() -> None:
    source = FFmpegError("original", stderr="long stderr text" * 100, returncode=42)
    wrapped = _wrap_ffmpeg_error(source, "probe_media", ["ffprobe", "file.mp4"])
    assert wrapped.operation == "probe_media"
    assert wrapped.cmd_args == ["ffprobe", "file.mp4"]
    assert wrapped.returncode == 42
    # Excerpt must be capped at 500 chars
    assert len(wrapped.stderr_excerpt) <= 500


def test_wrap_ffmpeg_error_empty_stderr() -> None:
    source = FFmpegError("no stderr", stderr="", returncode=1)
    wrapped = _wrap_ffmpeg_error(source, "op", [])
    assert wrapped.stderr_excerpt == ""


# ---------------------------------------------------------------------------
# Model validation — ExtractFrameRequest
# ---------------------------------------------------------------------------


def test_extract_frame_request_valid() -> None:
    req = ExtractFrameRequest(path=_FAKE_PATH, timestamp_s=5.0, output_path=_FAKE_OUT)
    assert req.timestamp_s == 5.0


def test_extract_frame_request_zero_timestamp_valid() -> None:
    req = ExtractFrameRequest(path=_FAKE_PATH, timestamp_s=0.0, output_path=_FAKE_OUT)
    assert req.timestamp_s == 0.0


def test_extract_frame_request_negative_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtractFrameRequest(path=_FAKE_PATH, timestamp_s=-1.0, output_path=_FAKE_OUT)


# ---------------------------------------------------------------------------
# Model validation — TranscodeRequest
# ---------------------------------------------------------------------------


def test_transcode_request_valid_defaults() -> None:
    req = TranscodeRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT)
    assert req.codec == VideoCodec.HEVC
    assert req.bit_depth == 10
    assert req.hw_accel == HwAccel.AUTO


def test_transcode_request_bit_depth_9_rejected() -> None:
    with pytest.raises(ValidationError):
        TranscodeRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT, bit_depth=9)


def test_transcode_request_bit_depth_11_rejected() -> None:
    with pytest.raises(ValidationError):
        TranscodeRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT, bit_depth=11)


def test_transcode_request_bit_depth_8_accepted() -> None:
    req = TranscodeRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT, bit_depth=8)
    assert req.bit_depth == 8


def test_transcode_request_film_grain_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        TranscodeRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT, film_grain=51)


def test_transcode_request_timeout_ge1() -> None:
    with pytest.raises(ValidationError):
        TranscodeRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT, timeout=0)


# ---------------------------------------------------------------------------
# Model validation — NormalizeLoudnessRequest
# ---------------------------------------------------------------------------


def test_normalize_loudness_positive_lufs_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizeLoudnessRequest(
            input_path=_FAKE_PATH,
            output_path=_FAKE_OUT,
            target_lufs=1.0,
        )


def test_normalize_loudness_slightly_positive_lufs_rejected() -> None:
    # le=0.0 means 0.0 is the boundary; positive values like +0.1 must fail.
    with pytest.raises(ValidationError):
        NormalizeLoudnessRequest(
            input_path=_FAKE_PATH,
            output_path=_FAKE_OUT,
            target_lufs=0.1,
        )


def test_normalize_loudness_valid_negative_lufs() -> None:
    req = NormalizeLoudnessRequest(
        input_path=_FAKE_PATH, output_path=_FAKE_OUT, target_lufs=-23.0, true_peak_dbtp=-2.0
    )
    assert req.target_lufs == -23.0


# ---------------------------------------------------------------------------
# Model validation — OverlayImageRequest
# ---------------------------------------------------------------------------


def test_overlay_image_opacity_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        OverlayImageRequest(
            video_path=_FAKE_PATH,
            image_path=_FAKE_IMG,
            output_path=_FAKE_OUT,
            opacity=1.5,
        )


def test_overlay_image_scale_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        OverlayImageRequest(
            video_path=_FAKE_PATH,
            image_path=_FAKE_IMG,
            output_path=_FAKE_OUT,
            scale=0.0,
        )


# ---------------------------------------------------------------------------
# Model validation — ConcatSegmentsRequest
# ---------------------------------------------------------------------------


def test_concat_segments_empty_list_rejected() -> None:
    with pytest.raises(ValidationError):
        ConcatSegmentsRequest(segments=[], output_path=_FAKE_OUT)


def test_concat_segments_valid_single_segment() -> None:
    req = ConcatSegmentsRequest(segments=[_FAKE_PATH], output_path=_FAKE_OUT)
    assert len(req.segments) == 1


def test_concat_segments_negative_transition_duration_rejected() -> None:
    with pytest.raises(ValidationError):
        ConcatSegmentsRequest(
            segments=[_FAKE_PATH],
            output_path=_FAKE_OUT,
            transition_duration_s=-0.1,
        )


# ---------------------------------------------------------------------------
# Model validation — PackageHlsRequest / HlsVariant
# ---------------------------------------------------------------------------


def test_hls_variant_zero_bitrate_rejected() -> None:
    with pytest.raises(ValidationError):
        HlsVariant(bitrate_kbps=0, width=1280, height=720)


def test_hls_variant_zero_dimension_rejected() -> None:
    with pytest.raises(ValidationError):
        HlsVariant(bitrate_kbps=2000, width=0, height=720)


def test_package_hls_empty_variants_rejected() -> None:
    with pytest.raises(ValidationError):
        PackageHlsRequest(
            input_path=_FAKE_PATH,
            output_dir=Path("/fake/out"),
            variants=[],
        )


def test_package_hls_segment_duration_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        PackageHlsRequest(
            input_path=_FAKE_PATH,
            output_dir=Path("/fake/out"),
            variants=[HlsVariant(bitrate_kbps=2000, width=1280, height=720)],
            segment_duration=0,
        )


# ---------------------------------------------------------------------------
# Model validation — SyncTracksRequest
# ---------------------------------------------------------------------------


def test_sync_tracks_search_window_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        SyncTracksRequest(
            reference_path=_FAKE_PATH,
            external_path=Path("/fake/ext.wav"),
            output_path=_FAKE_OUT,
            search_window_s=0.0,
        )


# ---------------------------------------------------------------------------
# StreamInfo — model direct construction
# ---------------------------------------------------------------------------


def test_stream_info_video_defaults() -> None:
    s = StreamInfo(index=0, codec_type="video", codec_name="h264", width=1920, height=1080)
    assert s.is_hdr is False
    assert s.sample_rate is None


def test_stream_info_audio_defaults() -> None:
    s = StreamInfo(index=1, codec_type="audio", codec_name="aac", sample_rate=48000, channels=2)
    assert s.width is None
    assert s.fps is None


# ---------------------------------------------------------------------------
# detect_hardware_encoders — mock run_ffmpeg
# ---------------------------------------------------------------------------

_ENCODER_OUTPUT_NVENC = (
    " V....D h264_nvenc           NVIDIA NVENC H.264 encoder\n"
    " V....D hevc_nvenc           NVIDIA NVENC HEVC encoder\n"
    " V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
    " V....D libx265              libx265 H.265 / HEVC\n"
)

_ENCODER_OUTPUT_SOFTWARE_ONLY = (
    " V....D libx264              libx264 H.264 / AVC\n"
    " V....D libx265              libx265 H.265 / HEVC\n"
    " V....D libsvtav1            SVT-AV1 encoder\n"
)


def test_detect_hardware_encoders_nvenc_detected() -> None:
    cp = _completed(stdout=_ENCODER_OUTPUT_NVENC)
    with (
        patch("podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=cp),
        patch("podcast_pipeline.utils.ffmpeg_toolkit._HW_ENCODER_CACHE", None),
    ):
        info = detect_hardware_encoders(use_cache=False)

    assert info.nvenc_h264 is True
    assert info.nvenc_hevc is True
    assert info.nvenc_av1 is False
    assert info.software_h264 is True
    assert info.software_hevc is True


def test_detect_hardware_encoders_software_only() -> None:
    cp = _completed(stdout=_ENCODER_OUTPUT_SOFTWARE_ONLY)
    with (
        patch("podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=cp),
        patch("podcast_pipeline.utils.ffmpeg_toolkit._HW_ENCODER_CACHE", None),
    ):
        info = detect_hardware_encoders(use_cache=False)

    assert info.nvenc_h264 is False
    assert info.nvenc_hevc is False
    assert info.software_h264 is True
    assert info.software_hevc is True
    assert info.software_av1 is True


def test_detect_hardware_encoders_ffmpeg_not_found_returns_defaults() -> None:
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=FFmpegError("FFmpeg not found"),
        ),
        patch("podcast_pipeline.utils.ffmpeg_toolkit._HW_ENCODER_CACHE", None),
    ):
        info = detect_hardware_encoders(use_cache=False)

    assert info.nvenc_h264 is False
    assert isinstance(info, HardwareEncoderInfo)


def test_detect_hardware_encoders_timeout_returns_defaults() -> None:
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=FFmpegError("FFmpeg timed out"),
        ),
        patch("podcast_pipeline.utils.ffmpeg_toolkit._HW_ENCODER_CACHE", None),
    ):
        info = detect_hardware_encoders(use_cache=False)

    assert info.nvenc_h264 is False


# ---------------------------------------------------------------------------
# probe_media — command shape and stream parsing
# ---------------------------------------------------------------------------

_PROBE_VIDEO_AUDIO = {
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "120.5",
        "size": "500000000",
        "bit_rate": "30000000",
    },
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "hevc",
            "width": 3840,
            "height": 2160,
            "r_frame_rate": "60/1",
            "pix_fmt": "yuv420p10le",
            "color_space": "bt2020nc",
            "color_range": "tv",
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
            "bit_rate": "192000",
        },
    ],
}

_PROBE_AUDIO_ONLY = {
    "format": {
        "format_name": "wav",
        "duration": "60.0",
        "size": "10000000",
        "bit_rate": "1411200",
    },
    "streams": [
        {
            "index": 0,
            "codec_type": "audio",
            "codec_name": "pcm_s16le",
            "sample_rate": "44100",
            "channels": 1,
        }
    ],
}


def test_probe_media_video_and_audio_streams() -> None:
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffprobe", return_value=_PROBE_VIDEO_AUDIO
    ):
        result = probe_media(_FAKE_PATH)

    assert result.path == _FAKE_PATH
    assert result.format_name == "mov,mp4,m4a,3gp,3g2,mj2"
    assert result.duration == pytest.approx(120.5)
    assert result.size_bytes == 500000000
    assert result.video is not None
    assert result.video.codec_name == "hevc"
    assert result.video.width == 3840
    assert result.video.height == 2160
    assert result.video.fps == pytest.approx(60.0)
    assert result.video.is_hdr is True
    assert result.audio is not None
    assert result.audio.codec_name == "aac"
    assert result.audio.sample_rate == 48000
    assert result.audio.channels == 2
    assert result.audio_track_count == 1


def test_probe_media_audio_only() -> None:
    with patch("podcast_pipeline.utils.ffmpeg_toolkit.run_ffprobe", return_value=_PROBE_AUDIO_ONLY):
        result = probe_media(Path("/fake/audio.wav"))

    assert result.video is None
    assert result.audio is not None
    assert result.audio.codec_name == "pcm_s16le"
    assert result.audio_track_count == 1


def test_probe_media_non_hdr_video() -> None:
    probe_data = {
        "format": {"duration": "30.0", "size": "100000", "bit_rate": "5000000"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30000/1001",
                "pix_fmt": "yuv420p",
                "color_space": "bt709",
                "color_range": "tv",
            }
        ],
    }
    with patch("podcast_pipeline.utils.ffmpeg_toolkit.run_ffprobe", return_value=probe_data):
        result = probe_media(_FAKE_PATH)

    assert result.video is not None
    assert result.video.is_hdr is False
    assert result.video.fps == pytest.approx(30000 / 1001)


def test_probe_media_wraps_ffmpeg_error() -> None:
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffprobe",
            side_effect=_ffmpeg_error("probe failed", "ffprobe stderr", 1),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        probe_media(_FAKE_PATH)

    err = exc_info.value
    assert err.operation == "probe_media"
    assert "ffprobe stderr" in err.stderr_excerpt


def test_probe_media_multi_audio_track_count() -> None:
    probe_data = {
        "format": {"duration": "60.0", "size": "500000", "bit_rate": "2000000"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
            {"index": 1, "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
            {"index": 2, "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
        ],
    }
    with patch("podcast_pipeline.utils.ffmpeg_toolkit.run_ffprobe", return_value=probe_data):
        result = probe_media(_FAKE_PATH)

    assert result.audio_track_count == 2
    # video field points to first video stream
    assert result.video is not None
    assert result.video.index == 0


# ---------------------------------------------------------------------------
# extract_frame — command shape
# ---------------------------------------------------------------------------


def test_extract_frame_command_shape() -> None:
    req = ExtractFrameRequest(path=_FAKE_PATH, timestamp_s=12.5, output_path=_FAKE_OUT)
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = extract_frame(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-ss" in args_used
    assert "12.5" in args_used
    assert "-i" in args_used
    assert str(_FAKE_PATH) in args_used
    assert "-vframes" in args_used
    assert "1" in args_used
    assert str(_FAKE_OUT) in args_used
    assert result.output_path == _FAKE_OUT


def test_extract_frame_wraps_ffmpeg_error() -> None:
    req = ExtractFrameRequest(path=_FAKE_PATH, timestamp_s=5.0, output_path=_FAKE_OUT)
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("frame extract failed"),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        extract_frame(req)

    assert exc_info.value.operation == "extract_frame"


# ---------------------------------------------------------------------------
# transcode — encoder selection and argument construction
# ---------------------------------------------------------------------------


def test_transcode_software_hevc_default_args(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    out.write_bytes(b"fake")
    req = TranscodeRequest(
        input_path=_FAKE_PATH,
        output_path=out,
        codec=VideoCodec.HEVC,
        hw_accel=HwAccel.NONE,
        bit_depth=10,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = transcode(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-c:v" in args_used
    idx = args_used.index("-c:v")
    assert args_used[idx + 1] == "libx265"
    assert "yuv420p10le" in args_used  # 10-bit pix_fmt for libx265 (not p010le which is NV12)
    assert "-c:a" in args_used
    assert "copy" in args_used
    assert result.output_path == out


def test_transcode_software_hevc_8bit_pix_fmt(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    out.write_bytes(b"fake")
    req = TranscodeRequest(
        input_path=_FAKE_PATH,
        output_path=out,
        codec=VideoCodec.HEVC,
        hw_accel=HwAccel.NONE,
        bit_depth=8,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        transcode(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "yuv420p" in args_used
    assert "p010le" not in args_used


def test_transcode_nvenc_hevc_selected_when_available(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    out.write_bytes(b"fake")
    req = TranscodeRequest(
        input_path=_FAKE_PATH,
        output_path=out,
        codec=VideoCodec.HEVC,
        hw_accel=HwAccel.NVENC,
        bit_depth=10,
    )
    nvenc_info = HardwareEncoderInfo(nvenc_hevc=True)
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.detect_hardware_encoders",
            return_value=nvenc_info,
        ),
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
        ) as mock_ffmpeg,
    ):
        transcode(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    idx = args_used.index("-c:v")
    assert args_used[idx + 1] == "hevc_nvenc"
    # NVENC preset format p1-p7
    assert "-preset:v" in args_used


def test_transcode_h264_nvenc_selected_when_available(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    out.write_bytes(b"fake")
    req = TranscodeRequest(
        input_path=_FAKE_PATH,
        output_path=out,
        codec=VideoCodec.H264,
        hw_accel=HwAccel.AUTO,
    )
    nvenc_info = HardwareEncoderInfo(nvenc_h264=True)
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.detect_hardware_encoders",
            return_value=nvenc_info,
        ),
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
        ) as mock_ffmpeg,
    ):
        transcode(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    idx = args_used.index("-c:v")
    assert args_used[idx + 1] == "h264_nvenc"


def test_transcode_av1_uses_libsvtav1(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    out.write_bytes(b"fake")
    req = TranscodeRequest(
        input_path=_FAKE_PATH,
        output_path=out,
        codec=VideoCodec.AV1,
        hw_accel=HwAccel.NONE,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        transcode(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    idx = args_used.index("-c:v")
    assert args_used[idx + 1] == "libsvtav1"


def test_transcode_av1_film_grain_appended(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    out.write_bytes(b"fake")
    req = TranscodeRequest(
        input_path=_FAKE_PATH,
        output_path=out,
        codec=VideoCodec.AV1,
        hw_accel=HwAccel.NONE,
        film_grain=10,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        transcode(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-svtav1-params" in args_used
    idx = args_used.index("-svtav1-params")
    assert "film-grain=10" in args_used[idx + 1]


def test_transcode_film_grain_non_av1_raises() -> None:
    req = TranscodeRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        codec=VideoCodec.H264,
        hw_accel=HwAccel.NONE,
        film_grain=5,
    )
    with pytest.raises(FFmpegToolkitError) as exc_info:
        transcode(req)

    assert exc_info.value.operation == "transcode"


def test_transcode_wraps_ffmpeg_error() -> None:
    req = TranscodeRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        codec=VideoCodec.HEVC,
        hw_accel=HwAccel.NONE,
    )
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("encode fail", "codec error output", 1),
        ),
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.detect_hardware_encoders",
            return_value=HardwareEncoderInfo(),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        transcode(req)

    assert exc_info.value.operation == "transcode"
    assert exc_info.value.returncode == 1


# ---------------------------------------------------------------------------
# normalize_loudness — two-pass argument construction
# ---------------------------------------------------------------------------


def test_normalize_loudness_two_pass_calls(tmp_path: Path) -> None:
    out = tmp_path / "normalized.mp4"
    req = NormalizeLoudnessRequest(
        input_path=_FAKE_PATH,
        output_path=out,
        target_lufs=-14.0,
        true_peak_dbtp=-1.0,
    )
    pass1_result = _completed(stderr='{"input_i": "-18.5", "input_tp": "-3.2", "input_lra": "7.5"}')
    pass2_result = _completed()

    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
        side_effect=[pass1_result, pass2_result],
    ) as mock_ffmpeg:
        result = normalize_loudness(req)

    assert mock_ffmpeg.call_count == 2
    # Pass 1: ends with null output
    pass1_args: list[str] = mock_ffmpeg.call_args_list[0][0][0]
    assert "-f" in pass1_args
    assert "null" in pass1_args
    assert "loudnorm" in " ".join(pass1_args)
    assert "print_format=json" in " ".join(pass1_args)
    # Pass 2: actual output file
    pass2_args: list[str] = mock_ffmpeg.call_args_list[1][0][0]
    assert str(out) in pass2_args
    assert "linear=true" in " ".join(pass2_args)
    # Measured LUFS parsed from stderr
    assert result.input_lufs == pytest.approx(-18.5)
    assert result.output_lufs == pytest.approx(-14.0)


def test_normalize_loudness_missing_json_defaults_to_zero(tmp_path: Path) -> None:
    out = tmp_path / "normalized.mp4"
    req = NormalizeLoudnessRequest(input_path=_FAKE_PATH, output_path=out)
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
        side_effect=[_completed(stderr="no json here"), _completed()],
    ):
        result = normalize_loudness(req)

    assert result.input_lufs == 0.0


def test_normalize_loudness_wraps_ffmpeg_error_pass1() -> None:
    req = NormalizeLoudnessRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT)
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("measure fail", "loudnorm err", 1),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        normalize_loudness(req)

    assert exc_info.value.operation == "normalize_loudness"


# ---------------------------------------------------------------------------
# burn_captions — filter argument construction
# ---------------------------------------------------------------------------


def test_burn_captions_basic_vf_arg() -> None:
    req = BurnCaptionsRequest(
        video_path=_FAKE_PATH,
        ass_path=_FAKE_ASS,
        output_path=_FAKE_OUT,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = burn_captions(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-vf" in args_used
    vf_idx = args_used.index("-vf")
    vf_val = args_used[vf_idx + 1]
    assert "ass=" in vf_val
    assert "-c:a" in args_used
    assert "copy" in args_used
    assert result.output_path == _FAKE_OUT


def test_burn_captions_force_style_included() -> None:
    req = BurnCaptionsRequest(
        video_path=_FAKE_PATH,
        ass_path=_FAKE_ASS,
        output_path=_FAKE_OUT,
        force_style="FontSize=24,Alignment=2",
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        burn_captions(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    vf_idx = args_used.index("-vf")
    vf_val = args_used[vf_idx + 1]
    assert "force_style=" in vf_val


def test_burn_captions_wraps_ffmpeg_error() -> None:
    req = BurnCaptionsRequest(
        video_path=_FAKE_PATH,
        ass_path=_FAKE_ASS,
        output_path=_FAKE_OUT,
    )
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("burn fail", "libass error", 1),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        burn_captions(req)

    assert exc_info.value.operation == "burn_captions"


# ---------------------------------------------------------------------------
# overlay_image — filter_complex argument construction
# ---------------------------------------------------------------------------


def test_overlay_image_top_right_position() -> None:
    req = OverlayImageRequest(
        video_path=_FAKE_PATH,
        image_path=_FAKE_IMG,
        output_path=_FAKE_OUT,
        position=OverlayPosition.TOP_RIGHT,
        opacity=0.7,
        scale=0.5,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = overlay_image(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-filter_complex" in args_used
    fc_idx = args_used.index("-filter_complex")
    fc_val = args_used[fc_idx + 1]
    assert "overlay" in fc_val
    assert "colorchannelmixer" in fc_val
    assert "scale=" in fc_val
    assert str(_FAKE_PATH) in args_used
    assert str(_FAKE_IMG) in args_used
    assert result.output_path == _FAKE_OUT


def test_overlay_image_center_position_uses_division_expr() -> None:
    req = OverlayImageRequest(
        video_path=_FAKE_PATH,
        image_path=_FAKE_IMG,
        output_path=_FAKE_OUT,
        position=OverlayPosition.CENTER,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        overlay_image(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    fc_idx = args_used.index("-filter_complex")
    fc_val = args_used[fc_idx + 1]
    # Center uses division expression
    assert "/2" in fc_val


def test_overlay_image_opacity_reflected_in_colorchannelmixer() -> None:
    req = OverlayImageRequest(
        video_path=_FAKE_PATH,
        image_path=_FAKE_IMG,
        output_path=_FAKE_OUT,
        opacity=0.4,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        overlay_image(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    fc_idx = args_used.index("-filter_complex")
    fc_val = args_used[fc_idx + 1]
    assert "aa=0.4" in fc_val


def test_overlay_image_wraps_ffmpeg_error() -> None:
    req = OverlayImageRequest(
        video_path=_FAKE_PATH,
        image_path=_FAKE_IMG,
        output_path=_FAKE_OUT,
    )
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("overlay fail"),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        overlay_image(req)

    assert exc_info.value.operation == "overlay_image"


# ---------------------------------------------------------------------------
# concat_segments — demuxer path vs xfade path
# ---------------------------------------------------------------------------


def test_concat_segments_demuxer_path_uses_f_concat(tmp_path: Path) -> None:
    seg1 = tmp_path / "seg1.mp4"
    seg2 = tmp_path / "seg2.mp4"
    seg1.write_bytes(b"a")
    seg2.write_bytes(b"b")
    out = tmp_path / "out.mp4"
    req = ConcatSegmentsRequest(
        segments=[seg1, seg2],
        output_path=out,
        transition=TransitionType.NONE,
    )
    probe_result = {"format": {"duration": "20.0"}}
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
        ) as mock_ffmpeg,
        patch("podcast_pipeline.utils.ffmpeg_toolkit.run_ffprobe", return_value=probe_result),
    ):
        concat_segments(req)

    # First call is demuxer concat
    first_call_args: list[str] = mock_ffmpeg.call_args_list[0][0][0]
    assert "-f" in first_call_args
    assert "concat" in first_call_args
    assert "-safe" in first_call_args
    assert "0" in first_call_args
    assert "-c" in first_call_args
    assert "copy" in first_call_args


def test_concat_segments_xfade_path_uses_filter_complex(tmp_path: Path) -> None:
    seg1 = tmp_path / "seg1.mp4"
    seg2 = tmp_path / "seg2.mp4"
    seg1.write_bytes(b"a")
    seg2.write_bytes(b"b")
    out = tmp_path / "out.mp4"
    req = ConcatSegmentsRequest(
        segments=[seg1, seg2],
        output_path=out,
        transition=TransitionType.CROSSFADE,
        transition_duration_s=1.0,
    )
    probe_result = {"format": {"duration": "10.0"}}
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
        ) as mock_ffmpeg,
        patch("podcast_pipeline.utils.ffmpeg_toolkit.run_ffprobe", return_value=probe_result),
    ):
        concat_segments(req)

    # xfade path uses filter_complex
    xfade_call_args: list[str] = mock_ffmpeg.call_args_list[0][0][0]
    assert "-filter_complex" in xfade_call_args
    fc_idx = xfade_call_args.index("-filter_complex")
    fc_val = xfade_call_args[fc_idx + 1]
    assert "xfade" in fc_val


def test_concat_segments_wraps_ffmpeg_error_demuxer(tmp_path: Path) -> None:
    seg = tmp_path / "seg.mp4"
    seg.write_bytes(b"x")
    out = tmp_path / "out.mp4"
    req = ConcatSegmentsRequest(segments=[seg], output_path=out, transition=TransitionType.NONE)
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("concat fail", "demux error", 1),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        concat_segments(req)

    assert exc_info.value.operation == "concat_segments"


# ---------------------------------------------------------------------------
# trim_segment — argument construction and validation
# ---------------------------------------------------------------------------


def test_trim_segment_copy_codec_args() -> None:
    req = TrimSegmentRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        start_s=5.0,
        end_s=15.0,
        copy_codec=True,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = trim_segment(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-ss" in args_used
    assert "5.0" in args_used
    assert "-t" in args_used  # duration = 10.0
    assert "10.0" in args_used
    assert "-c" in args_used
    assert "copy" in args_used
    assert result.actual_start_s == 5.0
    assert result.actual_end_s == 15.0


def test_trim_segment_end_before_start_raises() -> None:
    req = TrimSegmentRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        start_s=10.0,
        end_s=5.0,
    )
    with pytest.raises(FFmpegToolkitError) as exc_info:
        trim_segment(req)

    assert exc_info.value.operation == "trim_segment"


def test_trim_segment_no_end_no_duration_arg() -> None:
    req = TrimSegmentRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        start_s=5.0,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        trim_segment(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-t" not in args_used


def test_trim_segment_wraps_ffmpeg_error() -> None:
    req = TrimSegmentRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT, start_s=0.0)
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("trim fail"),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        trim_segment(req)

    assert exc_info.value.operation == "trim_segment"


# ---------------------------------------------------------------------------
# sync_tracks — offset calculation and mux args
# ---------------------------------------------------------------------------


def test_sync_tracks_positive_offset_uses_itsoffset_on_external(tmp_path: Path) -> None:
    """Positive offset: external track delayed via -itsoffset with explicit -map."""
    ref = tmp_path / "ref.wav"
    ext = tmp_path / "ext.wav"
    out = tmp_path / "synced.mp4"
    ref.write_bytes(b"r")
    ext.write_bytes(b"e")

    req = SyncTracksRequest(
        reference_path=ref,
        external_path=ext,
        output_path=out,
        search_window_s=10.0,
    )

    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
        ) as mock_ffmpeg,
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit._correlate_audio",
            return_value=(250.0, 0.9),
        ),
    ):
        result = sync_tracks(req)

    assert result.offset_ms == pytest.approx(250.0)
    assert result.confidence == pytest.approx(0.9)
    mux_call_args: list[str] = mock_ffmpeg.call_args_list[-1][0][0]
    assert "-itsoffset" in mux_call_args
    assert "0.25" in mux_call_args  # 250ms -> 0.25s
    assert str(ext) in mux_call_args
    assert str(ref) in mux_call_args
    # Explicit stream mapping must be present
    assert "-map" in mux_call_args
    assert "0:v?" in mux_call_args
    assert "1:a:0?" in mux_call_args


def test_sync_tracks_negative_offset_uses_external_path(tmp_path: Path) -> None:
    """Negative offset: external_path is still the audio source, offset is negative."""
    ref = tmp_path / "ref.wav"
    ext = tmp_path / "ext.wav"
    out = tmp_path / "synced.mp4"
    ref.write_bytes(b"r")
    ext.write_bytes(b"e")

    req = SyncTracksRequest(reference_path=ref, external_path=ext, output_path=out)

    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
        ) as mock_ffmpeg,
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit._correlate_audio",
            return_value=(-500.0, 0.75),
        ),
    ):
        result = sync_tracks(req)

    assert result.offset_ms == pytest.approx(-500.0)
    mux_call_args: list[str] = mock_ffmpeg.call_args_list[-1][0][0]
    assert "-itsoffset" in mux_call_args
    assert "-0.5" in mux_call_args  # -500ms -> -0.5s (negative passed directly)
    # Both reference and external must be in the command
    assert str(ref) in mux_call_args
    assert str(ext) in mux_call_args
    # Explicit stream mapping
    assert "-map" in mux_call_args
    assert "0:v?" in mux_call_args
    assert "1:a:0?" in mux_call_args


def test_sync_tracks_wraps_ffmpeg_error_on_mux(tmp_path: Path) -> None:
    ref = tmp_path / "ref.wav"
    ext = tmp_path / "ext.wav"
    out = tmp_path / "synced.mp4"
    ref.write_bytes(b"r")
    ext.write_bytes(b"e")

    req = SyncTracksRequest(reference_path=ref, external_path=ext, output_path=out)

    extract_result = _completed()
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=[extract_result, extract_result, _ffmpeg_error("mux fail", "mux error", 1)],
        ),
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit._correlate_audio",
            return_value=(0.0, 0.5),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        sync_tracks(req)

    assert exc_info.value.operation == "sync_tracks"


# ---------------------------------------------------------------------------
# package_hls — variant ladder argument construction
# ---------------------------------------------------------------------------


def test_package_hls_variant_ladder_args(tmp_path: Path) -> None:
    out_dir = tmp_path / "hls"
    variants = [
        HlsVariant(bitrate_kbps=4000, width=1920, height=1080, audio_bitrate_kbps=128),
        HlsVariant(bitrate_kbps=1500, width=1280, height=720, audio_bitrate_kbps=96),
        HlsVariant(bitrate_kbps=600, width=854, height=480, audio_bitrate_kbps=64),
    ]
    req = PackageHlsRequest(
        input_path=_FAKE_PATH,
        output_dir=out_dir,
        segment_duration=6,
        variants=variants,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = package_hls(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]

    # Should have filter_complex for split
    assert "-filter_complex" in args_used
    fc_idx = args_used.index("-filter_complex")
    fc_val = args_used[fc_idx + 1]
    assert "split=3" in fc_val
    # Each variant should scale to its dimensions
    assert "scale=1920:1080" in fc_val
    assert "scale=1280:720" in fc_val
    assert "scale=854:480" in fc_val

    # Should have hls output for each variant
    assert args_used.count("-f") == 3
    assert "4000k" in args_used
    assert "1500k" in args_used
    assert "600k" in args_used
    assert args_used.count("hls") == 3

    # Master playlist should be written
    assert result.master_playlist_path == out_dir / "master.m3u8"
    master_content = result.master_playlist_path.read_text()
    assert "#EXTM3U" in master_content
    assert "BANDWIDTH=4128000" in master_content  # 4000k + 128k
    assert "RESOLUTION=1920x1080" in master_content


def test_package_hls_segment_duration_passed(tmp_path: Path) -> None:
    out_dir = tmp_path / "hls"
    req = PackageHlsRequest(
        input_path=_FAKE_PATH,
        output_dir=out_dir,
        segment_duration=4,
        variants=[HlsVariant(bitrate_kbps=2000, width=1280, height=720)],
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        package_hls(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-hls_time" in args_used
    idx = args_used.index("-hls_time")
    assert args_used[idx + 1] == "4"


def test_package_hls_wraps_ffmpeg_error(tmp_path: Path) -> None:
    out_dir = tmp_path / "hls"
    req = PackageHlsRequest(
        input_path=_FAKE_PATH,
        output_dir=out_dir,
        variants=[HlsVariant(bitrate_kbps=2000, width=1280, height=720)],
    )
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("hls fail", "hls segment error", 1),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        package_hls(req)

    assert exc_info.value.operation == "package_hls"


# ---------------------------------------------------------------------------
# denoise — filter selection by method and strength
# ---------------------------------------------------------------------------


def test_denoise_hqdn3d_medium_filter() -> None:
    req = DenoiseRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        method=DenoiseMethod.HQDN3D,
        strength=DenoiseStrength.MEDIUM,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = denoise(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-vf" in args_used
    vf_idx = args_used.index("-vf")
    vf_val = args_used[vf_idx + 1]
    assert vf_val == "hqdn3d=4:3:6:4.5"
    assert result.output_path == _FAKE_OUT


def test_denoise_nlmeans_heavy_filter() -> None:
    req = DenoiseRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        method=DenoiseMethod.NLMEANS,
        strength=DenoiseStrength.HEAVY,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        denoise(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    vf_idx = args_used.index("-vf")
    vf_val = args_used[vf_idx + 1]
    assert vf_val == "nlmeans=s=6.0:p=7:r=15"


def test_denoise_wraps_ffmpeg_error() -> None:
    req = DenoiseRequest(input_path=_FAKE_PATH, output_path=_FAKE_OUT)
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("denoise fail"),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        denoise(req)

    assert exc_info.value.operation == "denoise"


# ---------------------------------------------------------------------------
# mix_audio — filter construction with and without ducking
# ---------------------------------------------------------------------------


def test_mix_audio_without_ducking_uses_amix() -> None:
    req = MixAudioRequest(
        speech_path=_FAKE_PATH,
        music_path=Path("/fake/music.mp3"),
        output_path=_FAKE_OUT,
        music_volume_db=-12.0,
        duck_enabled=False,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = mix_audio(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    assert "-filter_complex" in args_used
    fc_idx = args_used.index("-filter_complex")
    fc_val = args_used[fc_idx + 1]
    assert "amix" in fc_val
    assert "sidechaincompress" not in fc_val
    assert result.output_path == _FAKE_OUT


def test_mix_audio_with_ducking_uses_sidechaincompress() -> None:
    req = MixAudioRequest(
        speech_path=_FAKE_PATH,
        music_path=Path("/fake/music.mp3"),
        output_path=_FAKE_OUT,
        duck_enabled=True,
        duck_ratio=4.0,
        duck_threshold_db=-30.0,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        mix_audio(req)

    args_used: list[str] = mock_ffmpeg.call_args[0][0]
    fc_idx = args_used.index("-filter_complex")
    fc_val = args_used[fc_idx + 1]
    assert "sidechaincompress" in fc_val
    assert "ratio=4.0" in fc_val


def test_mix_audio_wraps_ffmpeg_error() -> None:
    req = MixAudioRequest(
        speech_path=_FAKE_PATH,
        music_path=Path("/fake/music.mp3"),
        output_path=_FAKE_OUT,
    )
    with (
        patch(
            "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg",
            side_effect=_ffmpeg_error("mix fail"),
        ),
        pytest.raises(FFmpegToolkitError) as exc_info,
    ):
        mix_audio(req)

    assert exc_info.value.operation == "mix_audio"


# ---------------------------------------------------------------------------
# apply_filtergraph — validation dry-run and main run
# ---------------------------------------------------------------------------


def test_apply_filtergraph_empty_string_rejected() -> None:
    from podcast_pipeline.utils.ffmpeg_toolkit import ApplyFiltergraphRequest

    with pytest.raises(ValidationError):
        ApplyFiltergraphRequest(
            input_path=_FAKE_PATH,
            output_path=_FAKE_OUT,
            filtergraph="   ",
        )


def test_apply_filtergraph_makes_two_calls_when_validate_true() -> None:
    from podcast_pipeline.utils.ffmpeg_toolkit import ApplyFiltergraphRequest, apply_filtergraph

    req = ApplyFiltergraphRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        filtergraph="eq=brightness=0.1",
        validate_first=True,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        apply_filtergraph(req)

    # validate call + real call
    assert mock_ffmpeg.call_count == 2
    validate_args: list[str] = mock_ffmpeg.call_args_list[0][0][0]
    assert "-frames:v" in validate_args
    assert "1" in validate_args


def test_apply_filtergraph_single_call_when_validate_false() -> None:
    from podcast_pipeline.utils.ffmpeg_toolkit import ApplyFiltergraphRequest, apply_filtergraph

    req = ApplyFiltergraphRequest(
        input_path=_FAKE_PATH,
        output_path=_FAKE_OUT,
        filtergraph="eq=brightness=0.1",
        validate_first=False,
    )
    with patch(
        "podcast_pipeline.utils.ffmpeg_toolkit.run_ffmpeg", return_value=_completed()
    ) as mock_ffmpeg:
        result = apply_filtergraph(req)

    assert mock_ffmpeg.call_count == 1
    assert result.output_path == _FAKE_OUT
    assert "eq" in result.applied_filters
