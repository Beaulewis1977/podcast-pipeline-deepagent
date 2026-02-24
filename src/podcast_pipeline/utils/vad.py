"""VAD breath detection wrapper using silero-vad with lazy import and graceful fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Module-level VAD model singleton — loaded on first use.
_vad_model: Any = None


def detect_breath_extension(
    audio_path: Path,
    cut_out_seconds: float,
    *,
    window_ms: float = 200.0,
    max_extend_ms: float = 150.0,
    sampling_rate: int = 16000,
) -> float:
    """Return extra seconds to trim at a cut boundary to swallow a trailing breath.

    Examines a short window ending at ``cut_out_seconds`` and measures how much
    non-speech (breath) follows the last detected speech segment.  Returns 0.0
    when silero-vad is not installed or when no trailing breath is detected.

    Parameters
    ----------
    audio_path:
        Path to the audio (or video) file.  ``read_audio`` handles format
        detection and resampling to ``sampling_rate``.
    cut_out_seconds:
        The current cut-out point in seconds.  The analysis window ends here.
    window_ms:
        Size of the look-back window in milliseconds (default 200ms).
    max_extend_ms:
        Maximum allowable extension in milliseconds.  The returned value is
        clamped to this ceiling (default 150ms).
    sampling_rate:
        Sampling rate for VAD processing (default 16 kHz — silero-vad native).

    Returns
    -------
    float
        Seconds to extend the cut boundary.  Always in [0, max_extend_ms/1000].
        Returns 0.0 when silero-vad is unavailable or no breath is detected.
    """
    global _vad_model  # noqa: PLW0603 — intentional module-level singleton

    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except ImportError:
        # silero-vad not installed — de-breathing pass is skipped gracefully.
        return 0.0

    if _vad_model is None:
        _vad_model = load_silero_vad()

    window_s = window_ms / 1000.0
    max_extend_s = max_extend_ms / 1000.0

    try:
        audio = read_audio(str(audio_path), sampling_rate=sampling_rate)
    except Exception as exc:
        logger.warning(
            "vad_read_audio_failed",
            audio_path=str(audio_path),
            error=str(exc),
        )
        return 0.0

    # Extract the window ending at the cut-out point.
    end_sample = int(cut_out_seconds * sampling_rate)
    start_sample = max(0, end_sample - int(window_s * sampling_rate))
    segment = audio[start_sample:end_sample]

    # Require at least 20ms of audio to run VAD (silero-vad minimum).
    min_samples = int(0.02 * sampling_rate)
    if len(segment) < min_samples:
        return 0.0

    try:
        timestamps = get_speech_timestamps(
            segment,
            _vad_model,
            sampling_rate=sampling_rate,
        )
    except Exception as exc:
        logger.warning(
            "vad_get_speech_timestamps_failed",
            cut_out_seconds=cut_out_seconds,
            error=str(exc),
        )
        return 0.0

    seg_len = len(segment)
    # If no speech detected at all, treat the whole window as trailing silence.
    last_speech_end_sample = timestamps[-1]["end"] if timestamps else 0
    trailing_non_speech_samples = seg_len - last_speech_end_sample
    trailing_s = trailing_non_speech_samples / sampling_rate

    extension_s = min(max(trailing_s, 0.0), max_extend_s)

    if extension_s > 0:
        logger.debug(
            "vad_breath_extension_detected",
            cut_out_seconds=cut_out_seconds,
            extension_ms=round(extension_s * 1000, 1),
        )

    return extension_s


def reset_vad_model() -> None:
    """Reset the cached VAD model singleton (primarily for testing)."""
    global _vad_model  # noqa: PLW0603
    _vad_model = None
