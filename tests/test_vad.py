"""Tests for VAD breath detector (utils/vad.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from podcast_pipeline.utils.vad import detect_breath_extension, reset_vad_model

# Sampling rate used across all tests
_SR = 16000
# 1-second mock audio at 16kHz — covers cut_out_seconds=1.0 exactly
_MOCK_AUDIO_LEN = _SR  # 1 second


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset the VAD model singleton between tests to ensure isolation."""
    reset_vad_model()


def _fake_silero_vad_module(
    speech_timestamps: list[dict[str, int]] | None = None,
) -> ModuleType:
    """Build a minimal fake silero_vad module.

    Parameters
    ----------
    speech_timestamps:
        Return value for get_speech_timestamps.  Defaults to [] (no speech).
    """
    if speech_timestamps is None:
        speech_timestamps = []

    module = ModuleType("silero_vad")

    def load_silero_vad() -> MagicMock:
        return MagicMock(name="vad_model")

    def read_audio(path: str, sampling_rate: int = _SR) -> list[float]:
        # Return _MOCK_AUDIO_LEN samples so cut_out_seconds=1.0 maps exactly to end
        return [0.0] * _MOCK_AUDIO_LEN

    captured = speech_timestamps

    def get_speech_timestamps(
        audio: list[float],
        model: object,
        sampling_rate: int = _SR,
    ) -> list[dict[str, int]]:
        return captured

    module.load_silero_vad = load_silero_vad  # type: ignore[attr-defined]
    module.read_audio = read_audio  # type: ignore[attr-defined]
    module.get_speech_timestamps = get_speech_timestamps  # type: ignore[attr-defined]
    return module


# ---------------------------------------------------------------------------
# Test: graceful fallback when silero-vad is not installed
# ---------------------------------------------------------------------------


def test_detect_breath_extension_returns_zero_no_silero(tmp_path: Path) -> None:
    """Returns 0.0 when silero_vad ImportError — de-breathing skipped gracefully."""
    audio_file = tmp_path / "audio.wav"
    audio_file.touch()

    with patch.dict(sys.modules, {"silero_vad": None}):
        result = detect_breath_extension(audio_file, cut_out_seconds=1.0)

    assert result == 0.0


# ---------------------------------------------------------------------------
# Test: trailing breath detected
# ---------------------------------------------------------------------------


def test_detect_breath_extension_detects_trailing_breath(tmp_path: Path) -> None:
    """Returns positive extension when speech ends before the window end."""
    audio_file = tmp_path / "audio.wav"
    audio_file.touch()

    # Use cut_out_seconds=1.0 so end_sample = _MOCK_AUDIO_LEN (fits in mock)
    # Window: 200ms → 3200 samples ending at sample 16000.
    window_ms = 200.0
    max_extend_ms = 150.0
    cut_out_seconds = 1.0

    window_samples = int((window_ms / 1000.0) * _SR)
    # Speech ends at 80% of the window — 20% (40ms) of trailing non-speech
    speech_end_sample = int(window_samples * 0.8)

    # get_speech_timestamps is called with the extracted segment (not full audio)
    # segment length = window_samples = 3200 samples
    timestamps = [{"start": 0, "end": speech_end_sample}]
    fake_module = _fake_silero_vad_module(speech_timestamps=timestamps)

    with patch.dict(sys.modules, {"silero_vad": fake_module}):
        result = detect_breath_extension(
            audio_file,
            cut_out_seconds=cut_out_seconds,
            window_ms=window_ms,
            max_extend_ms=max_extend_ms,
            sampling_rate=_SR,
        )

    # Trailing non-speech samples in segment = window_samples - speech_end_sample
    trailing_samples = window_samples - speech_end_sample
    expected_extension_s = trailing_samples / _SR  # ~0.04s (40ms)

    assert result == pytest.approx(expected_extension_s, rel=1e-3)
    assert 0.0 < result <= max_extend_ms / 1000.0


# ---------------------------------------------------------------------------
# Test: no breath detected (speech fills window)
# ---------------------------------------------------------------------------


def test_detect_breath_extension_no_breath_detected(tmp_path: Path) -> None:
    """Returns 0.0 when speech fills the entire analysis window."""
    audio_file = tmp_path / "audio.wav"
    audio_file.touch()

    window_ms = 200.0
    window_samples = int((window_ms / 1000.0) * _SR)

    # Speech spans the full window — no trailing breath
    timestamps = [{"start": 0, "end": window_samples}]
    fake_module = _fake_silero_vad_module(speech_timestamps=timestamps)

    with patch.dict(sys.modules, {"silero_vad": fake_module}):
        result = detect_breath_extension(
            audio_file,
            cut_out_seconds=1.0,
            window_ms=window_ms,
            sampling_rate=_SR,
        )

    assert result == 0.0


# ---------------------------------------------------------------------------
# Test: extension clamped to max_extend_ms
# ---------------------------------------------------------------------------


def test_detect_breath_extension_clamps_to_max(tmp_path: Path) -> None:
    """Extension is clamped to max_extend_ms even when trailing silence is longer."""
    audio_file = tmp_path / "audio.wav"
    audio_file.touch()

    window_ms = 200.0
    max_extend_ms = 50.0  # Very small max — forces clamping

    # Speech ends very early — trailing silence ~190ms >> max_extend_ms=50ms
    timestamps = [{"start": 0, "end": int(0.01 * _SR)}]
    fake_module = _fake_silero_vad_module(speech_timestamps=timestamps)

    with patch.dict(sys.modules, {"silero_vad": fake_module}):
        result = detect_breath_extension(
            audio_file,
            cut_out_seconds=1.0,
            window_ms=window_ms,
            max_extend_ms=max_extend_ms,
            sampling_rate=_SR,
        )

    assert result == pytest.approx(max_extend_ms / 1000.0, rel=1e-3)


# ---------------------------------------------------------------------------
# Test: no speech timestamps = whole window is silence/breath
# ---------------------------------------------------------------------------


def test_detect_breath_extension_empty_timestamps_whole_window(tmp_path: Path) -> None:
    """When no speech is detected at all, the whole window counts as trailing breath."""
    audio_file = tmp_path / "audio.wav"
    audio_file.touch()

    max_extend_ms = 150.0
    # Default: [] timestamps → no speech detected
    fake_module = _fake_silero_vad_module()

    with patch.dict(sys.modules, {"silero_vad": fake_module}):
        result = detect_breath_extension(
            audio_file,
            cut_out_seconds=1.0,
            max_extend_ms=max_extend_ms,
            sampling_rate=_SR,
        )

    # Whole window = breath; clamped to max_extend_ms
    assert result == pytest.approx(max_extend_ms / 1000.0, rel=1e-3)
