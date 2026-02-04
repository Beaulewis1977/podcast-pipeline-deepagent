"""FFmpeg wrapper utilities with proper error handling."""

import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)


class FFmpegError(Exception):
    """FFmpeg execution error."""

    def __init__(self, message: str, stderr: str = "", returncode: int = -1):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


def run_ffmpeg(
    args: list[str],
    timeout: int = 3600,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg with proper error handling.

    Args:
        args: FFmpeg arguments (without 'ffmpeg' prefix)
        timeout: Timeout in seconds
        check: Whether to raise on non-zero return code

    Returns:
        CompletedProcess result

    Raises:
        FFmpegError: If FFmpeg fails and check=True
    """
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    logger.debug("running_ffmpeg", cmd=" ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        if check and result.returncode != 0:
            raise FFmpegError(
                f"FFmpeg failed with return code {result.returncode}",
                stderr=result.stderr,
                returncode=result.returncode,
            )

        return result

    except subprocess.TimeoutExpired as e:
        raise FFmpegError(f"FFmpeg timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise FFmpegError("FFmpeg not found. Please install FFmpeg and ensure it's in PATH.") from e


def run_ffprobe(
    input_path: Path,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Run FFprobe and return JSON output.

    Args:
        input_path: Path to media file
        extra_args: Additional FFprobe arguments

    Returns:
        Parsed JSON output from FFprobe

    Raises:
        FFmpegError: If FFprobe fails
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        *(extra_args or []),
        str(input_path),
    ]
    logger.debug("running_ffprobe", cmd=" ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        if result.returncode != 0:
            raise FFmpegError(
                f"FFprobe failed with return code {result.returncode}",
                stderr=result.stderr,
                returncode=result.returncode,
            )

        return dict(json.loads(result.stdout))

    except subprocess.TimeoutExpired as e:
        raise FFmpegError("FFprobe timed out") from e
    except FileNotFoundError as e:
        raise FFmpegError(
            "FFprobe not found. Please install FFmpeg and ensure it's in PATH."
        ) from e
    except json.JSONDecodeError as e:
        raise FFmpegError(f"Failed to parse FFprobe output: {e}") from e


def _parse_fps(value: str | None) -> float:
    """Safely parse FPS from ffprobe r_frame_rate value."""
    if not value:
        return 0.0

    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        try:
            numerator, denominator = value.split("/", 1)
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else 0.0
        except Exception:
            return 0.0


def get_video_metadata(video_path: Path) -> dict[str, Any]:
    """Extract comprehensive metadata from a video file.

    Args:
        video_path: Path to video file

    Returns:
        Dictionary with video metadata
    """
    probe_data = run_ffprobe(video_path)

    metadata: dict[str, Any] = {
        "format": probe_data.get("format", {}).get("format_name", "unknown"),
        "duration": float(probe_data.get("format", {}).get("duration", 0)),
        "size_bytes": int(probe_data.get("format", {}).get("size", 0)),
        "bit_rate": int(probe_data.get("format", {}).get("bit_rate", 0)),
        "streams": [],
    }

    for stream in probe_data.get("streams", []):
        stream_info: dict[str, Any] = {
            "index": stream.get("index"),
            "codec_type": stream.get("codec_type"),
            "codec_name": stream.get("codec_name"),
        }

        if stream.get("codec_type") == "video":
            stream_info.update(
                {
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "fps": _parse_fps(stream.get("r_frame_rate")),
                    "pix_fmt": stream.get("pix_fmt"),
                }
            )
        elif stream.get("codec_type") == "audio":
            stream_info.update(
                {
                    "sample_rate": int(stream.get("sample_rate", 0)),
                    "channels": stream.get("channels"),
                    "channel_layout": stream.get("channel_layout"),
                }
            )

        metadata["streams"].append(stream_info)

    # Add convenience fields
    video_streams = [s for s in metadata["streams"] if s["codec_type"] == "video"]
    audio_streams = [s for s in metadata["streams"] if s["codec_type"] == "audio"]

    if video_streams:
        metadata["video"] = video_streams[0]
    if audio_streams:
        metadata["audio"] = audio_streams[0]
        metadata["audio_track_count"] = len(audio_streams)

    return metadata


def extract_audio(
    video_path: Path,
    output_path: Path,
    sample_rate: int = 16000,
    mono: bool = True,
) -> Path:
    """Extract audio from video file.

    Args:
        video_path: Path to video file
        output_path: Path for output audio file
        sample_rate: Sample rate for output (16000 for Whisper)
        mono: Whether to convert to mono

    Returns:
        Path to extracted audio file
    """
    args = [
        "-i",
        str(video_path),
        "-vn",  # No video
        "-acodec",
        "pcm_s16le",  # 16-bit PCM
        "-ar",
        str(sample_rate),
    ]

    if mono:
        args.extend(["-ac", "1"])

    args.append(str(output_path))

    run_ffmpeg(args)
    logger.info(
        "audio_extracted",
        input=str(video_path),
        output=str(output_path),
        sample_rate=sample_rate,
    )

    return output_path


def get_video_info(video_path: Path) -> dict[str, Any]:
    """Get basic video information (width, height, duration, fps).

    Args:
        video_path: Path to video file

    Returns:
        Dictionary with width, height, duration, fps
    """
    try:
        metadata = get_video_metadata(video_path)
        video_stream = metadata.get("video", {})

        return {
            "width": video_stream.get("width", 1920),
            "height": video_stream.get("height", 1080),
            "duration": metadata.get("duration", 0),
            "fps": video_stream.get("fps", 30),
        }
    except Exception as e:
        logger.warning("get_video_info_failed", error=str(e))
        return {"width": 1920, "height": 1080, "duration": 0, "fps": 30}


def create_proxy(
    video_path: Path,
    output_path: Path,
    resolution: str = "720",
    crf: int = 30,
) -> Path:
    """Create low-resolution proxy for AI analysis.

    Args:
        video_path: Path to video file
        output_path: Path for output proxy file
        resolution: Target height (width auto-calculated)
        crf: Quality setting (higher = lower quality, smaller file)

    Returns:
        Path to proxy file
    """
    args = [
        "-i",
        str(video_path),
        "-vf",
        f"scale=-2:{resolution}",
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-preset",
        "fast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output_path),
    ]

    run_ffmpeg(args)
    logger.info("proxy_created", input=str(video_path), output=str(output_path))

    return output_path
