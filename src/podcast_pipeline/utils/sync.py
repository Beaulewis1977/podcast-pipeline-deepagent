"""Bounded cross-correlation audio sync estimator.

Implements the four-step algorithm from spec v4 Section 3:

  Step A - Downsample & Bound:
      Extract the first ``search_window_s`` seconds (<= 60 s) from both
      tracks as 8 kHz mono WAV via FFmpeg.  No librosa dependency needed;
      FFmpeg handles the resampling so the file runs in the base install.

  Step B - Peak Alignment (clap detection):
      Scan for transient samples exceeding 3x the window RMS.  Used to
      produce an initial coarse estimate and to detect whether a usable
      clap-like transient exists at all.

  Step C - Fine Sync:
      ``scipy.signal.correlate(mode='full')`` on the bounded chunks.
      Normalise the correlation before ``argmax`` so gain differences
      between a mic track and a camera track don't skew the result.

  Step D - Confidence Scoring & Warnings:
      Normalised peak-to-N ratio is mapped to a 0-1 confidence score.
      A ``low_confidence`` flag and ``no_clap`` flag are set when the
      evidence is weak so operators know when to reach for the manual
      offset slider.

Usage::

    from podcast_pipeline.utils.sync import SyncEstimator, SyncResult

    estimator = SyncEstimator()
    result: SyncResult = estimator.estimate(reference_path, external_path)
    # result.offset_ms  - positive = external starts AFTER reference
    # result.confidence - 0-1; < LOW_CONFIDENCE_THRESHOLD means unreliable
    # result.warnings   - list of human-readable diagnostic strings
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from podcast_pipeline.utils.ffmpeg import FFmpegError, run_ffmpeg
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TARGET_SR = 8_000  # 8 kHz mono for bounded correlation
_MAX_WINDOW_S = 60.0  # never analyse beyond 60 s
_PEAK_RMS_MULTIPLIER = 3.0  # samples exceeding N x RMS = "clap candidate"
_CLAP_MIN_INTERVAL_S = 0.5  # ignore claps within 500 ms of prior candidate
LOW_CONFIDENCE_THRESHOLD = 0.30  # public -- UI uses this to decide slider visibility


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SyncResult:
    """Result of a bounded cross-correlation sync estimation.

    Attributes:
        offset_ms: Estimated offset in milliseconds.
            Positive value means the *external* track should start
            ``offset_ms`` ms later than the reference track (i.e. apply
            ``-itsoffset offset_s -i external`` in FFmpeg).
            Negative value means the external track leads the reference.
        confidence: Normalised peak-correlation confidence in [0, 1].
            Values below ``LOW_CONFIDENCE_THRESHOLD`` (~0.30) indicate a
            weak or ambiguous match that should be flagged to the operator.
        source: How the estimate was produced -- ``"correlation"`` in all
            automatic paths.
        no_clap: True when no transient exceeding 3x RMS was found in either
            track.  The correlation result may still be usable, but the
            absence of a clap reduces confidence in typical use cases.
        low_confidence: True when ``confidence < LOW_CONFIDENCE_THRESHOLD``.
        warnings: Human-readable diagnostic strings for operator inspection
            and log output.
        estimated_at: UTC timestamp when the estimate was produced.
    """

    offset_ms: float
    confidence: float
    source: str = "correlation"
    no_clap: bool = False
    low_confidence: bool = False
    warnings: list[str] = field(default_factory=list)
    estimated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def as_artifact(self) -> dict[str, object]:
        """Serialise to a plain dict for JSON persistence."""
        return {
            "offset_ms": self.offset_ms,
            "confidence": self.confidence,
            "source": self.source,
            "no_clap": self.no_clap,
            "low_confidence": self.low_confidence,
            "warnings": list(self.warnings),
            "estimated_at": self.estimated_at,
        }


class _ClapMark(NamedTuple):
    """Sample position and amplitude of a detected transient."""

    sample: int
    amplitude: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_mono_wav(src: Path, dst: Path, window_s: float) -> None:
    """Use FFmpeg to extract a bounded mono 8 kHz WAV from *src* into *dst*.

    Args:
        src: Source audio/video file path.
        dst: Destination WAV file path.
        window_s: Duration of the head window to extract (seconds).

    Raises:
        FFmpegError: Propagated from run_ffmpeg on failure.
    """
    args = [
        "-ss",
        "0",
        "-t",
        str(window_s),
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        str(_TARGET_SR),
        "-vn",
        str(dst),
    ]
    run_ffmpeg(args, timeout=120)


def _detect_clap_candidates(
    samples: Any,
    sample_rate: int,
) -> list[_ClapMark]:
    """Scan *samples* for transient peaks above 3x RMS.

    Returns:
        List of ``_ClapMark`` instances sorted by sample position, with a
        minimum spacing of ``_CLAP_MIN_INTERVAL_S`` between consecutive marks
        to avoid counting the same transient twice.
    """
    import numpy as _np

    rms = float(_np.sqrt(_np.mean(samples**2)))
    threshold = rms * _PEAK_RMS_MULTIPLIER
    if threshold == 0.0:
        return []

    abs_samples = _np.abs(samples)
    candidates = _np.where(abs_samples > threshold)[0]
    if len(candidates) == 0:
        return []

    min_gap = int(_CLAP_MIN_INTERVAL_S * sample_rate)
    marks: list[_ClapMark] = []
    last_sample = -min_gap - 1
    for idx in candidates:
        if (int(idx) - last_sample) >= min_gap:
            marks.append(_ClapMark(sample=int(idx), amplitude=float(abs_samples[idx])))
            last_sample = int(idx)

    return marks


def _correlate_samples(
    ref: Any,
    ext: Any,
    sample_rate: int,
) -> tuple[float, float]:
    """Compute normalised cross-correlation offset and confidence.

    Sign convention:
        Positive ``offset_ms`` means the *external* track lags the reference
        (i.e. external starts later).  Apply ``-itsoffset offset_s`` to
        external in FFmpeg to realign.

    Confidence formula:
        ``min(1.0, peak_abs_corr / max_samples)`` where ``max_samples`` is
        the longer of the two signal lengths.  For identical unit-variance
        signals this approaches 1.0; for fully independent noise it is
        typically < 0.05.

    Args:
        ref: Reference audio samples (1-D float32 array).
        ext: External audio samples (1-D float32 array).
        sample_rate: Shared sample rate (Hz).

    Returns:
        Tuple of ``(offset_ms, confidence)`` where:
        - ``offset_ms`` is positive when external lags reference.
        - ``confidence`` is the normalised peak correlation in [0, 1].
    """
    import numpy as _np
    from scipy.signal import correlate, correlation_lags

    # Normalise to zero-mean unit-std to remove DC and gain bias
    def _normalise(x: Any) -> Any:
        std = float(_np.std(x))
        mean = float(_np.mean(x))
        if std < 1e-9:
            return x - mean
        return (x - mean) / std

    ref_n = _normalise(ref)
    ext_n = _normalise(ext)

    corr = correlate(ref_n, ext_n, mode="full")
    lags = correlation_lags(len(ref_n), len(ext_n), mode="full")

    # Peak lag in samples.
    # scipy convention: positive lag_samples means ext leads ref.
    # We negate so that offset_ms > 0 means "external starts after reference".
    peak_idx = int(_np.argmax(_np.abs(corr)))
    lag_samples = int(lags[peak_idx])
    offset_ms = -(lag_samples / sample_rate) * 1000.0

    # Confidence: peak normalised by max possible (N for unit-variance signals).
    # Identical signals -> ~1.0; independent noise -> ~1/sqrt(N).
    abs_corr = _np.abs(corr)
    n_max = max(len(ref_n), len(ext_n))
    confidence = round(min(1.0, float(_np.max(abs_corr)) / n_max), 4)

    return offset_ms, confidence


# ---------------------------------------------------------------------------
# Public estimator
# ---------------------------------------------------------------------------


class SyncEstimator:
    """Bounded cross-correlation sync estimator.

    Extracts audio head windows via FFmpeg (no librosa dependency),
    detects clap transients for diagnostic purposes, runs scipy full
    cross-correlation, and returns a :class:`SyncResult` with offset and
    confidence metadata.

    Args:
        search_window_s: Duration of audio head window to analyse.
            Clamped to ``_MAX_WINDOW_S`` (60 s) regardless of input.
    """

    def __init__(self, search_window_s: float = 60.0) -> None:
        self._window_s = min(float(search_window_s), _MAX_WINDOW_S)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def estimate(
        self,
        reference_path: Path,
        external_path: Path,
    ) -> SyncResult:
        """Estimate the sync offset between *reference_path* and *external_path*.

        Args:
            reference_path: Primary (reference) audio/video track.
            external_path: External (secondary) audio/video track to align.

        Returns:
            :class:`SyncResult` containing offset_ms, confidence, and
            diagnostic flags.

        Raises:
            RuntimeError: When scipy is not available or audio extraction fails.
        """
        self._require_scipy()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            ref_wav = tmp / "ref.wav"
            ext_wav = tmp / "ext.wav"

            try:
                _extract_mono_wav(reference_path, ref_wav, self._window_s)
            except FFmpegError as exc:
                raise RuntimeError(
                    f"sync_estimator: failed to extract reference audio: {exc}"
                ) from exc

            try:
                _extract_mono_wav(external_path, ext_wav, self._window_s)
            except FFmpegError as exc:
                raise RuntimeError(
                    f"sync_estimator: failed to extract external audio: {exc}"
                ) from exc

            return self._estimate_from_wavs(ref_wav, ext_wav)

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _estimate_from_wavs(self, ref_wav: Path, ext_wav: Path) -> SyncResult:
        """Perform correlation on already-extracted WAV files (testable core)."""
        import numpy as _np
        import soundfile as sf

        try:
            ref_data, _ = sf.read(str(ref_wav), dtype="float32")
            ext_data, _ = sf.read(str(ext_wav), dtype="float32")
        except Exception as exc:
            raise RuntimeError(f"sync_estimator: failed to read WAV files: {exc}") from exc

        ref_data = ref_data.flatten().astype(_np.float32)
        ext_data = ext_data.flatten().astype(_np.float32)

        if len(ref_data) == 0 or len(ext_data) == 0:
            return SyncResult(
                offset_ms=0.0,
                confidence=0.0,
                no_clap=True,
                low_confidence=True,
                warnings=["One or both audio tracks contain no samples."],
            )

        # Step B: Clap/transient detection for diagnostics
        ref_claps = _detect_clap_candidates(ref_data, _TARGET_SR)
        ext_claps = _detect_clap_candidates(ext_data, _TARGET_SR)
        no_clap = len(ref_claps) == 0 or len(ext_claps) == 0

        # Step C: Normalised cross-correlation
        offset_ms, confidence = _correlate_samples(ref_data, ext_data, _TARGET_SR)

        # Step D: Warnings and flags
        warnings: list[str] = []
        low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD

        if no_clap:
            warnings.append(
                "No sharp transient (clap) detected in one or both tracks. "
                "Correlation result may be less reliable."
            )

        if low_confidence:
            warnings.append(
                f"Low confidence ({confidence:.3f} < {LOW_CONFIDENCE_THRESHOLD}). "
                "Consider using the manual sync offset slider."
            )

        if abs(offset_ms) > 4000:
            warnings.append(
                f"Large estimated offset ({offset_ms:.1f} ms). "
                "Verify that both tracks overlap within the first 60 seconds."
            )

        logger.info(
            "sync_estimated",
            offset_ms=round(offset_ms, 2),
            confidence=confidence,
            no_clap=no_clap,
            low_confidence=low_confidence,
            ref_claps=len(ref_claps),
            ext_claps=len(ext_claps),
            warnings=warnings,
        )

        return SyncResult(
            offset_ms=round(offset_ms, 2),
            confidence=confidence,
            source="correlation",
            no_clap=no_clap,
            low_confidence=low_confidence,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Dependency guard
    # ------------------------------------------------------------------

    @staticmethod
    def _require_scipy() -> None:
        """Raise RuntimeError if scipy is not installed."""
        try:
            import scipy  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "scipy is required for audio sync estimation. Install it: uv add scipy>=1.14.0"
            ) from exc
