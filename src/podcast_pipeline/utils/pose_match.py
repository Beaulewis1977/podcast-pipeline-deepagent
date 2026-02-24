"""Pose-match frame selection using OpenCV Farneback optical flow.

Scans a search window of frames around a content-cut join and selects the
frame pair (one from the tail of the left segment, one from the head of the
right segment) with the minimum optical-flow magnitude — i.e. the most
visually similar pair.

Uses opencv-python-headless with lazy import and graceful fallback when the
package is not installed (returns float('inf') for all distances).
"""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def pose_distance(frame_a_path: Path, frame_b_path: Path) -> float:
    """Compute mean optical-flow magnitude between two frames.

    Uses Farneback dense optical flow on greyscale images.

    Parameters
    ----------
    frame_a_path:
        Path to the first frame image (PNG/JPG).
    frame_b_path:
        Path to the second frame image (PNG/JPG).

    Returns
    -------
    float
        Mean flow magnitude across all pixels.  Returns ``float('inf')`` when
        opencv is unavailable, the images cannot be loaded, or the images have
        incompatible shapes.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return float("inf")

    frame_a = cv2.imread(str(frame_a_path))
    frame_b = cv2.imread(str(frame_b_path))
    if frame_a is None or frame_b is None:
        return float("inf")

    # Resize frame_b to match frame_a dimensions if needed (handles edge cases).
    if frame_a.shape != frame_b.shape:
        frame_b = cv2.resize(frame_b, (frame_a.shape[1], frame_a.shape[0]))

    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        gray_a,
        gray_b,
        np.zeros((*gray_a.shape, 2), dtype=np.float32),
        pyr_scale=0.5,
        levels=3,
        winsize=15,
        iterations=3,
        poly_n=5,
        poly_sigma=1.2,
        flags=0,
    )
    magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    result: float = float(np.mean(magnitude))
    return result


def scan_best_frame_pair(
    left_frames: list[Path],
    right_frames: list[Path],
    search_window: int = 6,  # ~200ms at 30fps
) -> tuple[int, int, float]:
    """Scan for the frame pair with minimum optical-flow distance.

    Examines the last ``search_window`` frames of ``left_frames`` against the
    first ``search_window`` frames of ``right_frames`` and returns the pair
    with the lowest pose distance.

    The search window is clamped to the number of available frames in each
    list so no ``IndexError`` is raised when fewer frames are available.

    Parameters
    ----------
    left_frames:
        Ordered list of frame image paths from the left (outgoing) segment.
        The scan uses the *last* ``search_window`` frames (tail).
    right_frames:
        Ordered list of frame image paths from the right (incoming) segment.
        The scan uses the *first* ``search_window`` frames (head).
    search_window:
        Maximum number of frames to examine from each side.

    Returns
    -------
    tuple[int, int, float]
        ``(left_idx, right_idx, distance)`` where ``left_idx`` is an index into
        ``left_frames`` and ``right_idx`` is an index into ``right_frames``.
        Returns ``(0, 0, float('inf'))`` when either list is empty.
    """
    if not left_frames or not right_frames:
        return 0, 0, float("inf")
    if search_window <= 0:
        return 0, 0, float("inf")

    # Clamp window to available frame counts.
    left_n = min(search_window, len(left_frames))
    right_n = min(search_window, len(right_frames))

    best_left: int = len(left_frames) - left_n
    best_right: int = 0
    best_dist: float = float("inf")

    left_start = len(left_frames) - left_n
    for li in range(left_start, len(left_frames)):
        for ri in range(right_n):
            dist = pose_distance(left_frames[li], right_frames[ri])
            if dist < best_dist:
                best_left, best_right, best_dist = li, ri, dist

    logger.debug(
        "pose_match_scan_complete",
        left_idx=best_left,
        right_idx=best_right,
        distance=round(best_dist, 4) if best_dist != float("inf") else "inf",
        left_window=left_n,
        right_window=right_n,
    )
    return best_left, best_right, best_dist
