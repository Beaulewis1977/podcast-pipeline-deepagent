"""Noise-floor RMS measurement and FFmpeg gain-ramp filter builder.

Uses librosa for accurate RMS measurement with lazy import and graceful fallback
when librosa is not installed.
"""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def measure_rms_db(
    audio_path: Path,
    window_ms: float = 100.0,
    *,
    tail: bool = True,
    offset_s: float | None = None,
) -> float:
    """Measure the RMS level in dBFS of a window within an audio file.

    Analyses a short ``window_ms`` window at the beginning or end of the file,
    or at a specific time offset when ``offset_s`` is provided.

    Parameters
    ----------
    audio_path:
        Path to the audio file.  librosa handles format detection and decoding.
    window_ms:
        Analysis window length in milliseconds (default 100ms).
    tail:
        When True (default) and ``offset_s`` is None, analyse the *last*
        ``window_ms`` of the file (tail of a left segment at a join).
        When False and ``offset_s`` is None, analyse the *first* ``window_ms``
        (head of a right segment at a join).
        Ignored when ``offset_s`` is provided.
    offset_s:
        If given, analyse the ``window_ms`` window starting at this position
        in seconds.  Takes priority over ``tail``.

    Returns
    -------
    float
        RMS level in dBFS.  Returns ``-120.0`` when librosa is unavailable,
        when the file cannot be read, or when the segment is too short.
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        # librosa not installed — noise-floor pass is skipped gracefully.
        return -120.0

    try:
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning(
            "noise_match_load_failed",
            audio_path=str(audio_path),
            error=str(exc),
        )
        return -120.0

    if len(y) == 0:
        return -120.0

    n_samples = max(int((window_ms / 1000.0) * sr), 1)

    if offset_s is not None:
        start_sample = max(int(offset_s * sr), 0)
        segment = y[start_sample : start_sample + n_samples]
    elif tail:
        segment = y[-n_samples:]
    else:
        segment = y[:n_samples]

    if len(segment) == 0:
        return -120.0

    # librosa.feature.rms returns shape (1, n_frames); y= is keyword-only in 0.11+.
    rms_frames = librosa.feature.rms(y=segment)[0]
    rms_mean = float(np.mean(rms_frames))
    rms_db = float(20.0 * np.log10(max(rms_mean, 1e-9)))

    return rms_db


def compute_noise_floor_correction(
    left_rms_db: float,
    right_rms_db: float,
    threshold_db: float = 3.0,
    ramp_ms: float = 50.0,
) -> str | None:
    """Return an FFmpeg volume filter expression to correct a noise-floor mismatch.

    When the absolute dB difference between the tail of the left segment and the
    head of the right segment exceeds ``threshold_db``, a gain correction is
    applied to the right segment to bring its noise floor in line with the left
    segment.

    The filter uses ``eval=frame`` so the gain is applied per-sample in-stream
    without an additional FFmpeg pass.

    Parameters
    ----------
    left_rms_db:
        RMS level (dBFS) of the tail of the left keep-segment.
    right_rms_db:
        RMS level (dBFS) of the head of the right keep-segment.
    threshold_db:
        Minimum dB mismatch required to apply correction (default 3.0 dB).
        Uses strict less-than for the no-op path: a delta of exactly
        ``threshold_db`` **is** corrected (threshold is inclusive).
    ramp_ms:
        Duration of the gain ramp in milliseconds (default 50ms).  Documented
        for reference; the actual ramp is managed by the caller's micro-fade
        filter chain.

    Returns
    -------
    str | None
        FFmpeg ``volume`` filter string (e.g. ``"volume=1.778000:eval=frame"``)
        or ``None`` when the delta is below the threshold and no correction is
        needed.
    """
    delta_db = abs(left_rms_db - right_rms_db)

    # Strict less-than: exactly at threshold → correction IS applied.
    if delta_db < threshold_db:
        return None

    # Compute linear gain factor to match the left segment's level.
    # Positive gain_db means right is quieter than left — boost it.
    gain_db = left_rms_db - right_rms_db
    gain_linear = 10.0 ** (gain_db / 20.0)

    # FFmpeg volume filter with eval=frame applies per-sample.
    filter_str = f"volume={gain_linear:.6f}:eval=frame"

    logger.debug(
        "noise_floor_correction_computed",
        left_rms_db=round(left_rms_db, 2),
        right_rms_db=round(right_rms_db, 2),
        delta_db=round(delta_db, 2),
        gain_db=round(gain_db, 2),
        gain_linear=round(gain_linear, 4),
        ramp_ms=ramp_ms,
        filter=filter_str,
    )

    return filter_str
