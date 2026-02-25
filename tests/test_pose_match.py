"""Tests for pose_match optical-flow frame selection utilities."""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_png(path: Path, width: int = 4, height: int = 4, value: int = 128) -> None:
    """Write a minimal synthetic PNG image using numpy + cv2 when available.

    Falls back to writing PNG magic bytes (non-decodable) when cv2 is absent.
    """
    try:
        import cv2
        import numpy as np

        img = np.full((height, width, 3), value, dtype=np.uint8)
        cv2.imwrite(str(path), img)
    except ImportError:
        path.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes stub


# ---------------------------------------------------------------------------
# pose_distance tests
# ---------------------------------------------------------------------------


class TestPoseDistance:
    """Unit tests for pose_distance()."""

    def test_pose_distance_returns_inf_no_opencv(self, tmp_path: Path) -> None:
        """pose_distance returns float('inf') when cv2 import fails."""
        import importlib

        import podcast_pipeline.utils.pose_match as pm

        frame_a = tmp_path / "a.png"
        frame_b = tmp_path / "b.png"
        frame_a.write_bytes(b"fake")
        frame_b.write_bytes(b"fake")

        original_import = builtins.__import__

        def _failing_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name in ("cv2", "numpy"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=_failing_import):
            importlib.reload(pm)
            result = pm.pose_distance(frame_a, frame_b)

        # Reload to restore real import state for subsequent tests.
        importlib.reload(pm)

        assert result == float("inf")

    def test_pose_distance_missing_file_returns_inf(self, tmp_path: Path) -> None:
        """pose_distance returns float('inf') when image files are missing."""
        try:
            import cv2  # noqa: F401
        except ImportError:
            pytest.skip("cv2 not installed")

        from podcast_pipeline.utils.pose_match import pose_distance

        result = pose_distance(tmp_path / "missing_a.png", tmp_path / "missing_b.png")
        assert result == float("inf")

    def test_pose_distance_identical_frames(self, tmp_path: Path) -> None:
        """Identical images produce a near-zero optical-flow distance."""
        try:
            import cv2  # noqa: F401
        except ImportError:
            pytest.skip("cv2 not installed")

        from podcast_pipeline.utils.pose_match import pose_distance

        frame = tmp_path / "frame.png"
        _write_png(frame, width=16, height=16, value=100)
        result = pose_distance(frame, frame)
        assert result < 1.0, f"Expected near-zero distance for identical frames, got {result}"

    def test_pose_distance_deterministic(self, tmp_path: Path) -> None:
        """Calling pose_distance twice with the same frames returns the same result."""
        try:
            import cv2  # noqa: F401
        except ImportError:
            pytest.skip("cv2 not installed")

        from podcast_pipeline.utils.pose_match import pose_distance

        frame_a = tmp_path / "a.png"
        frame_b = tmp_path / "b.png"
        _write_png(frame_a, value=60)
        _write_png(frame_b, value=180)

        result1 = pose_distance(frame_a, frame_b)
        result2 = pose_distance(frame_a, frame_b)
        assert result1 == result2, "pose_distance must be deterministic"


# ---------------------------------------------------------------------------
# scan_best_frame_pair tests
# ---------------------------------------------------------------------------


class TestScanBestFramePair:
    """Unit tests for scan_best_frame_pair()."""

    def test_scan_best_frame_pair_empty_lists(self) -> None:
        """Empty frame lists return (0, 0, inf)."""
        from podcast_pipeline.utils.pose_match import scan_best_frame_pair

        left_idx, right_idx, dist = scan_best_frame_pair([], [])
        assert left_idx == 0
        assert right_idx == 0
        assert dist == float("inf")

    def test_scan_best_frame_pair_single_frame_each(self, tmp_path: Path) -> None:
        """Single frame on each side returns (0, 0, distance)."""
        try:
            import cv2  # noqa: F401
        except ImportError:
            pytest.skip("cv2 not installed")

        from podcast_pipeline.utils.pose_match import scan_best_frame_pair

        frame_l = tmp_path / "l0.png"
        frame_r = tmp_path / "r0.png"
        _write_png(frame_l, value=100)
        _write_png(frame_r, value=100)

        left_idx, right_idx, dist = scan_best_frame_pair([frame_l], [frame_r], search_window=1)
        assert left_idx == 0
        assert right_idx == 0
        assert dist != float("inf")

    def test_scan_best_frame_pair_clamps_window(self, tmp_path: Path) -> None:
        """search_window larger than available frames does not raise IndexError."""
        from podcast_pipeline.utils.pose_match import scan_best_frame_pair

        # 3 frames available but search_window=10
        frames = []
        for i in range(3):
            f = tmp_path / f"frame_{i}.png"
            f.write_bytes(b"dummy")
            frames.append(f)

        # Should not raise — returns inf because dummy files fail imread
        left_idx, right_idx, dist = scan_best_frame_pair(frames, frames, search_window=10)
        assert 0 <= left_idx < len(frames)
        assert 0 <= right_idx < len(frames)
        assert dist == float("inf")  # dummy files → inf distance

    def test_scan_best_frame_pair_finds_minimum(self, tmp_path: Path) -> None:
        """Returns the pair with the lowest pose distance."""
        try:
            import cv2
            import numpy as np
        except ImportError:
            pytest.skip("cv2/numpy not installed")

        from podcast_pipeline.utils.pose_match import scan_best_frame_pair

        # Create gradient images with horizontal shifts.  Optical flow can
        # distinguish spatial patterns (unlike uniform solid-color images).
        # The "matching" pair shares the exact same pattern → flow ≈ 0.
        size = 64

        def _write_gradient(path: Path, shift: int) -> None:
            """Write a gradient image shifted horizontally by `shift` pixels."""
            row = np.arange(size, dtype=np.uint8)
            row = np.roll(row, shift)
            img = np.tile(row, (size, 1))
            img = np.stack([img, img, img], axis=-1)
            cv2.imwrite(str(path), img)

        # 4 left frames with different shifts; l2 has shift=20
        left_frames = []
        for i, shift in enumerate([0, 10, 20, 40]):
            p = tmp_path / f"l{i}.png"
            _write_gradient(p, shift)
            left_frames.append(p)

        # 4 right frames; r1 has shift=20 (identical to l2)
        right_frames = []
        for i, shift in enumerate([5, 20, 35, 50]):
            p = tmp_path / f"r{i}.png"
            _write_gradient(p, shift)
            right_frames.append(p)

        best_l, best_r, best_dist = scan_best_frame_pair(left_frames, right_frames, search_window=4)

        # The identical pair (l2, r1) should have minimum distance.
        assert best_l == 2, f"Expected best_left=2, got {best_l}"
        assert best_r == 1, f"Expected best_right=1, got {best_r}"
        assert best_dist < 1.0, f"Expected near-zero distance for identical pair, got {best_dist}"
