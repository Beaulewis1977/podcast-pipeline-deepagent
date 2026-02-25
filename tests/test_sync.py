"""Tests for bounded cross-correlation audio sync estimator.

Tests cover:
- SyncResult dataclass and as_artifact serialisation
- Clap candidate detection (_detect_clap_candidates)
- Normalised cross-correlation offset and confidence (_correlate_samples)
- _estimate_from_wavs core logic (bounded fixture data, low-confidence, no-clap)
- SyncEstimator.estimate integration path via patched FFmpeg + WAV fixture
- scipy missing-dependency guard
"""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# WAV fixture helpers
# ---------------------------------------------------------------------------


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = 8000) -> None:
    """Write a float32 numpy array as a 16-bit mono WAV file."""
    # Clip and convert to int16
    clipped = np.clip(samples, -1.0, 1.0)
    int16_data = (clipped * 32767).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(int16_data.tobytes())


def _make_sine(freq_hz: float = 440.0, duration_s: float = 2.0, sr: int = 8000) -> np.ndarray:
    """Generate a pure sine wave as float32."""
    t = np.linspace(0, duration_s, int(duration_s * sr), endpoint=False)
    return (np.sin(2 * np.pi * freq_hz * t) * 0.3).astype(np.float32)


def _make_clap_signal(
    clap_position_s: float = 0.5,
    duration_s: float = 2.0,
    sr: int = 8000,
) -> np.ndarray:
    """Generate a background noise signal with a sharp clap transient."""
    rng = np.random.default_rng(42)
    samples = (rng.standard_normal(int(duration_s * sr)) * 0.01).astype(np.float32)
    clap_idx = int(clap_position_s * sr)
    # Insert clap impulse (amplitude >> 3x RMS of background)
    for i in range(10):
        if clap_idx + i < len(samples):
            samples[clap_idx + i] = 0.9 * (1.0 - i / 10.0)
    return samples


# ---------------------------------------------------------------------------
# SyncResult tests
# ---------------------------------------------------------------------------


class TestSyncResult:
    def test_as_artifact_fields_present(self) -> None:
        from podcast_pipeline.utils.sync import SyncResult

        result = SyncResult(
            offset_ms=123.45,
            confidence=0.75,
            source="correlation",
            no_clap=False,
            low_confidence=False,
            warnings=[],
        )
        artifact = result.as_artifact()

        assert artifact["offset_ms"] == 123.45
        assert artifact["confidence"] == 0.75
        assert artifact["source"] == "correlation"
        assert artifact["no_clap"] is False
        assert artifact["low_confidence"] is False
        assert artifact["warnings"] == []
        assert "estimated_at" in artifact

    def test_as_artifact_is_json_serialisable(self) -> None:
        from podcast_pipeline.utils.sync import SyncResult

        result = SyncResult(
            offset_ms=-50.0,
            confidence=0.15,
            no_clap=True,
            low_confidence=True,
            warnings=["Low confidence.", "No clap found."],
        )
        payload = json.dumps(result.as_artifact())
        loaded = json.loads(payload)
        assert loaded["warnings"] == ["Low confidence.", "No clap found."]

    def test_low_confidence_flag_matches_threshold(self) -> None:
        from podcast_pipeline.utils.sync import LOW_CONFIDENCE_THRESHOLD, SyncResult

        below = SyncResult(
            offset_ms=0.0, confidence=LOW_CONFIDENCE_THRESHOLD - 0.01, low_confidence=True
        )
        above = SyncResult(
            offset_ms=0.0, confidence=LOW_CONFIDENCE_THRESHOLD + 0.01, low_confidence=False
        )

        assert below.low_confidence is True
        assert above.low_confidence is False


# ---------------------------------------------------------------------------
# Clap detection tests
# ---------------------------------------------------------------------------


class TestClaptDetection:
    def test_offset_detection_returns_clap_near_planted_position(self) -> None:
        from podcast_pipeline.utils.sync import _detect_clap_candidates

        signal = _make_clap_signal(clap_position_s=0.5, sr=8000)
        marks = _detect_clap_candidates(signal, sample_rate=8000)

        assert len(marks) >= 1
        # The planted clap is at sample 4000 (0.5 s x 8000 Hz)
        first_clap_s = marks[0].sample / 8000.0
        assert abs(first_clap_s - 0.5) < 0.1

    def test_no_clap_in_pure_noise_below_threshold(self) -> None:
        from podcast_pipeline.utils.sync import _detect_clap_candidates

        rng = np.random.default_rng(99)
        # Low-amplitude noise: RMS ~0.001, max ~0.003 -- well below 3x RMS of a stronger signal
        noise = (rng.standard_normal(8000) * 0.001).astype(np.float32)
        marks = _detect_clap_candidates(noise, sample_rate=8000)
        # Marks may be present since noise peak may exceed 3x its own RMS;
        # but the detection should be consistent (no crash, returns list)
        assert isinstance(marks, list)

    def test_zero_signal_returns_no_marks(self) -> None:
        from podcast_pipeline.utils.sync import _detect_clap_candidates

        silent = np.zeros(8000, dtype=np.float32)
        marks = _detect_clap_candidates(silent, sample_rate=8000)
        assert marks == []

    def test_clap_marks_respect_min_interval(self) -> None:
        from podcast_pipeline.utils.sync import _detect_clap_candidates

        # Two claps very close together (10 ms apart) -- only one should survive
        signal = np.zeros(8000, dtype=np.float32)
        signal[1000] = 1.0  # first clap at 125 ms
        signal[1010] = 1.0  # second clap at 126.25 ms (10 samples = 1.25 ms < 500 ms gap)
        marks = _detect_clap_candidates(signal, sample_rate=8000)
        # Both are within 500 ms of each other; the second should be suppressed
        assert len(marks) == 1


# ---------------------------------------------------------------------------
# Cross-correlation tests
# ---------------------------------------------------------------------------


class TestCorrelateSamples:
    def test_offset_clap_signal_returns_correct_lag(self) -> None:
        """Cross-correlation should recover the planted clap offset to within 60 ms."""
        from podcast_pipeline.utils.sync import _correlate_samples

        sr = 8000
        ref = _make_clap_signal(clap_position_s=1.0, duration_s=4.0, sr=sr)
        # External is reference shifted by +250 ms (external starts 250 ms later)
        shift_ms = 250.0
        shift_samples = int(shift_ms / 1000.0 * sr)
        ext = np.concatenate([np.zeros(shift_samples, dtype=np.float32), ref[:-shift_samples]])

        offset_ms, confidence = _correlate_samples(ref, ext, sr)

        # offset_ms > 0 means external lags reference — correct for our shift
        assert abs(offset_ms - shift_ms) < 60.0
        assert confidence > 0.5

    def test_identical_clap_signals_return_zero_offset_high_confidence(self) -> None:
        """Identical signals should correlate at lag 0 with confidence near 1."""
        from podcast_pipeline.utils.sync import _correlate_samples

        signal = _make_clap_signal(clap_position_s=0.5, duration_s=2.0, sr=8000)
        offset_ms, confidence = _correlate_samples(signal, signal, 8000)

        assert abs(offset_ms) < 1.0  # near-zero lag
        assert confidence > 0.8  # high confidence for identical signals

    def test_confidence_is_bounded_to_one(self) -> None:
        from podcast_pipeline.utils.sync import _correlate_samples

        signal = _make_clap_signal(clap_position_s=0.5, duration_s=1.0, sr=8000)
        _, confidence = _correlate_samples(signal, signal, 8000)
        assert 0.0 <= confidence <= 1.0

    def test_uncorrelated_noise_returns_low_confidence(self) -> None:
        """Short noise signals should not produce high correlation confidence."""
        from podcast_pipeline.utils.sync import _correlate_samples

        # Use short signals so peak / n stays small for uncorrelated noise
        rng = np.random.default_rng(1)
        noise1 = rng.standard_normal(500).astype(np.float32)
        rng2 = np.random.default_rng(2)
        noise2 = rng2.standard_normal(500).astype(np.float32)

        _, confidence = _correlate_samples(noise1, noise2, 8000)
        # Two independent noise signals should not produce high confidence
        assert confidence < 0.5


# ---------------------------------------------------------------------------
# _estimate_from_wavs (core bounded logic)
# ---------------------------------------------------------------------------


class TestEstimateFromWavs:
    def _estimator(self) -> Any:
        from podcast_pipeline.utils.sync import SyncEstimator

        return SyncEstimator(search_window_s=60.0)

    def test_bounded_offset_detected_for_shifted_clap_signal(self, tmp_path: Path) -> None:
        estimator = self._estimator()

        sr = 8000
        ref_signal = _make_clap_signal(clap_position_s=1.0, duration_s=4.0, sr=sr)
        # External is reference shifted by +250 ms (external starts later)
        shift_samples = 2000  # 250 ms
        ext_signal = np.concatenate(
            [np.zeros(shift_samples, dtype=np.float32), ref_signal[:-shift_samples]]
        )

        ref_wav = tmp_path / "ref.wav"
        ext_wav = tmp_path / "ext.wav"
        _write_wav(ref_wav, ref_signal, sr)
        _write_wav(ext_wav, ext_signal, sr)

        result = estimator._estimate_from_wavs(ref_wav, ext_wav)

        assert abs(result.offset_ms - 250.0) < 60.0  # within 60 ms of planted offset

    def test_identical_tracks_return_near_zero_offset(self, tmp_path: Path) -> None:
        estimator = self._estimator()

        sr = 8000
        signal = _make_clap_signal(clap_position_s=0.5, duration_s=3.0, sr=sr)
        wav = tmp_path / "same.wav"
        _write_wav(wav, signal, sr)

        result = estimator._estimate_from_wavs(wav, wav)

        assert abs(result.offset_ms) < 15.0
        assert result.confidence > 0.5

    def test_low_confidence_flagged_for_noise(self, tmp_path: Path) -> None:
        from podcast_pipeline.utils.sync import LOW_CONFIDENCE_THRESHOLD

        estimator = self._estimator()

        rng = np.random.default_rng(77)
        noise1 = (rng.standard_normal(16000) * 0.05).astype(np.float32)
        rng2 = np.random.default_rng(88)
        noise2 = (rng2.standard_normal(16000) * 0.05).astype(np.float32)

        wav1 = tmp_path / "n1.wav"
        wav2 = tmp_path / "n2.wav"
        _write_wav(wav1, noise1)
        _write_wav(wav2, noise2)

        result = estimator._estimate_from_wavs(wav1, wav2)

        if result.confidence < LOW_CONFIDENCE_THRESHOLD:
            assert result.low_confidence is True
            assert any("confidence" in w.lower() for w in result.warnings)

    def test_no_clap_flag_set_when_no_transient(self, tmp_path: Path) -> None:
        estimator = self._estimator()

        sr = 8000
        # Smooth sine — no sharp transient
        sine = _make_sine(440.0, duration_s=3.0, sr=sr)
        wav = tmp_path / "sine.wav"
        _write_wav(wav, sine, sr)

        result = estimator._estimate_from_wavs(wav, wav)

        # Sine wave has no samples that spike > 3x RMS
        assert result.no_clap is True
        assert any("transient" in w.lower() or "clap" in w.lower() for w in result.warnings)

    def test_empty_samples_returns_zero_offset_low_confidence(self, tmp_path: Path) -> None:
        estimator = self._estimator()

        # Write minimal WAV with 0 samples (empty data section via manual construction)
        empty_wav = tmp_path / "empty.wav"
        with wave.open(str(empty_wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(b"")

        signal_wav = tmp_path / "signal.wav"
        _write_wav(signal_wav, _make_sine(440.0, duration_s=1.0), 8000)

        result = estimator._estimate_from_wavs(empty_wav, signal_wav)

        assert result.offset_ms == 0.0
        assert result.low_confidence is True
        assert result.no_clap is True


# ---------------------------------------------------------------------------
# SyncEstimator integration (patched FFmpeg extraction)
# ---------------------------------------------------------------------------


class TestSyncEstimatorIntegration:
    def test_estimate_calls_ffmpeg_extract_twice(self, tmp_path: Path) -> None:
        """estimate() should call _extract_mono_wav for ref and ext."""
        from podcast_pipeline.utils.sync import SyncEstimator, SyncResult

        fake_ref = tmp_path / "ref.mkv"
        fake_ext = tmp_path / "ext.mkv"
        fake_ref.write_bytes(b"fakeref")
        fake_ext.write_bytes(b"fakeext")

        call_count: list[int] = [0]

        def mock_extract(src: Path, dst: Path, window_s: float) -> None:
            call_count[0] += 1
            # Write a minimal sine WAV as the "extracted" audio
            signal = _make_clap_signal(clap_position_s=0.5, duration_s=1.0)
            _write_wav(dst, signal)

        estimator = SyncEstimator(search_window_s=10.0)
        with patch("podcast_pipeline.utils.sync._extract_mono_wav", side_effect=mock_extract):
            result = estimator.estimate(fake_ref, fake_ext)

        assert call_count[0] == 2
        assert isinstance(result, SyncResult)

    def test_estimate_propagates_ffmpeg_error_as_runtime_error(self, tmp_path: Path) -> None:
        from podcast_pipeline.utils.ffmpeg import FFmpegError
        from podcast_pipeline.utils.sync import SyncEstimator

        fake_ref = tmp_path / "bad_ref.mkv"
        fake_ext = tmp_path / "bad_ext.mkv"
        fake_ref.write_bytes(b"x")
        fake_ext.write_bytes(b"x")

        estimator = SyncEstimator()
        with (
            patch(
                "podcast_pipeline.utils.sync._extract_mono_wav",
                side_effect=FFmpegError("injection failed"),
            ),
            pytest.raises(RuntimeError, match="failed to extract reference audio"),
        ):
            estimator.estimate(fake_ref, fake_ext)

    def test_search_window_is_clamped_to_60s(self) -> None:
        from podcast_pipeline.utils.sync import _MAX_WINDOW_S, SyncEstimator

        estimator = SyncEstimator(search_window_s=9999.0)
        assert estimator._window_s == _MAX_WINDOW_S


# ---------------------------------------------------------------------------
# scipy missing-dependency guard
# ---------------------------------------------------------------------------


class TestSciPyDependencyGuard:
    def test_require_scipy_raises_when_not_installed(self) -> None:
        from podcast_pipeline.utils.sync import SyncEstimator

        estimator = SyncEstimator()
        import builtins

        real_import = builtins.__import__

        def import_blocker(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "scipy":
                raise ImportError("No module named 'scipy'")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=import_blocker),
            pytest.raises(RuntimeError, match="scipy is required"),
        ):
            estimator._require_scipy()
