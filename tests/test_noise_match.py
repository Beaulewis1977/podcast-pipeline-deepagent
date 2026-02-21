"""Tests for noise-floor RMS measurement and correction (utils/noise_match.py)."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from podcast_pipeline.utils.noise_match import compute_noise_floor_correction, measure_rms_db


def _fake_librosa_module(rms_value: float = 0.01) -> ModuleType:
    """Build a minimal fake librosa module returning a fixed RMS value."""
    module = ModuleType("librosa")
    feature_module = ModuleType("librosa.feature")

    def load(path: str, *, sr: object = None, mono: bool = True) -> tuple[object, int]:
        # Return a dummy array-like and sample rate
        fake_y = MagicMock(name="y")
        fake_y.__len__ = lambda _: 4410  # 100ms at 44100Hz
        return fake_y, 44100

    captured_rms = rms_value

    def rms(*, y: object) -> list[list[float]]:
        # Return shape (1, n_frames) with the configured RMS value
        return [[captured_rms, captured_rms, captured_rms]]

    feature_module.rms = rms  # type: ignore[attr-defined]
    module.load = load  # type: ignore[attr-defined]
    module.feature = feature_module  # type: ignore[attr-defined]
    return module


# ---------------------------------------------------------------------------
# Test: graceful fallback when librosa is not installed
# ---------------------------------------------------------------------------


def test_measure_rms_db_returns_fallback_no_librosa(tmp_path: Path) -> None:
    """Returns -120.0 when librosa ImportError — noise-floor pass skipped gracefully."""
    audio_file = tmp_path / "audio.wav"
    audio_file.touch()

    with patch.dict(sys.modules, {"librosa": None}):
        result = measure_rms_db(audio_file)

    assert result == -120.0


# ---------------------------------------------------------------------------
# Tests: compute_noise_floor_correction threshold logic
# ---------------------------------------------------------------------------


def test_compute_noise_floor_correction_below_threshold() -> None:
    """Returns None when delta is strictly below threshold (no correction needed)."""
    # 2dB delta, 3dB threshold — 2 < 3 → should return None
    result = compute_noise_floor_correction(-30.0, -32.0, threshold_db=3.0, ramp_ms=50.0)
    assert result is None


def test_compute_noise_floor_correction_above_threshold() -> None:
    """Returns FFmpeg volume filter string when delta exceeds threshold."""
    # 5dB delta, 3dB threshold — 5 > 3 → should return a correction filter
    result = compute_noise_floor_correction(-30.0, -35.0, threshold_db=3.0, ramp_ms=50.0)

    assert result is not None
    assert result.startswith("volume=")
    assert "eval=frame" in result


def test_compute_noise_floor_correction_exact_threshold() -> None:
    """At exactly the threshold, strict less-than means correction IS applied.

    The condition is ``if delta_db < threshold_db: return None``.
    When delta_db == threshold_db, the condition is False and correction proceeds.
    """
    # Exactly 3.0dB delta at 3.0dB threshold — 3.0 < 3.0 is False → filter returned
    result = compute_noise_floor_correction(-30.0, -33.0, threshold_db=3.0, ramp_ms=50.0)
    assert result is not None
    assert result.startswith("volume=")


def test_compute_noise_floor_correction_strictly_below_threshold() -> None:
    """Correction is NOT applied when delta is strictly below threshold."""
    # 2.99dB delta, 3dB threshold — should return None
    result = compute_noise_floor_correction(-30.0, -32.99, threshold_db=3.0, ramp_ms=50.0)
    assert result is None


def test_compute_noise_floor_correction_gain_value() -> None:
    """Gain factor in filter string matches expected 10^(gain_db/20) formula."""
    left_rms_db = -30.0
    right_rms_db = -35.0
    result = compute_noise_floor_correction(left_rms_db, right_rms_db, threshold_db=3.0)

    assert result is not None
    # Expected gain: 10^(5/20) ≈ 1.778
    gain_db = left_rms_db - right_rms_db  # = 5.0
    expected_gain = 10.0 ** (gain_db / 20.0)
    gain_str = result.split("=")[1].split(":")[0]
    actual_gain = float(gain_str)
    assert actual_gain == pytest.approx(expected_gain, rel=1e-4)


def test_compute_noise_floor_correction_right_louder_than_left() -> None:
    """When right segment is louder than left, gain < 1 (attenuation applied)."""
    # right is 5dB louder than left
    result = compute_noise_floor_correction(-35.0, -30.0, threshold_db=3.0)

    assert result is not None
    gain_str = result.split("=")[1].split(":")[0]
    actual_gain = float(gain_str)
    # gain_db = -35 - -30 = -5 → 10^(-5/20) ≈ 0.562
    assert actual_gain < 1.0


# ---------------------------------------------------------------------------
# Test: measure_rms_db with mocked librosa
# ---------------------------------------------------------------------------


def test_measure_rms_db_returns_db_value(tmp_path: Path) -> None:
    """measure_rms_db returns a finite dBFS value when librosa is available."""
    audio_file = tmp_path / "audio.wav"
    audio_file.touch()

    rms_linear = 0.01  # RMS amplitude (linear)

    fake_librosa = _fake_librosa_module(rms_value=rms_linear)

    with patch.dict(sys.modules, {"librosa": fake_librosa}):
        result = measure_rms_db(audio_file)

    assert isinstance(result, float)
    assert math.isfinite(result)
    # RMS dB should be negative for sub-unity amplitude
    assert result < 0.0


def test_measure_rms_db_fallback_on_load_error(tmp_path: Path) -> None:
    """Returns -120.0 when librosa.load raises an exception."""
    audio_file = tmp_path / "audio.wav"
    audio_file.touch()

    fake_librosa = _fake_librosa_module()

    def failing_load(path: str, **kwargs: object) -> None:
        raise RuntimeError("Simulated load failure")

    fake_librosa.load = failing_load  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"librosa": fake_librosa}):
        result = measure_rms_db(audio_file)

    assert result == -120.0
