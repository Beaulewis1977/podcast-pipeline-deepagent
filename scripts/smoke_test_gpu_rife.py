#!/usr/bin/env python3
# ruff: noqa: T201  (print() is intentional — this is a CLI smoke test script)
"""GPU smoke test for RIFE frame interpolation on RTX 5060 Ti.

Run: python scripts/smoke_test_gpu_rife.py
Expected: prints "RIFE OK" on success, exits non-zero on failure.

Requirements: torch>=2.7 with cu128, practical-RIFE cloned with model weights,
opencv-python-headless>=4.9.

GPU note: RTX 5060 Ti is Blackwell sm_120.  Requires CUDA 12.8 (cu128 torch wheel),
NOT cu121.  See docs/phase8-operator-guide.md for setup instructions.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def _check_torch() -> bool:
    """Return True if torch + CUDA are available."""
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        print("FAIL: torch not installed")
        print(
            "      Install: uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128"
        )
        return False

    if not torch.cuda.is_available():
        print("FAIL: CUDA not available")
        print("      Ensure torch was installed with the cu128 index (NOT cu121):")
        print(
            "      uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128"
        )
        return False

    cap = torch.cuda.get_device_capability()
    name = torch.cuda.get_device_name(0)
    cuda_version = torch.version.cuda or "unknown"
    print(f"GPU: {name}, capability: {cap[0]}.{cap[1]}, CUDA: {cuda_version}")

    # Warn if not Blackwell sm_120 (RTX 5060 Ti target)
    if cap[0] < 12:
        print(
            f"WARNING: Expected compute capability >= 12.0 for RTX 5060 Ti (sm_120), got {cap[0]}.{cap[1]}"
        )
        print(
            "         For Blackwell GPUs use cu128 torch wheel to avoid 'no kernel image' errors."
        )

    return True


def _check_opencv() -> bool:
    """Return True if opencv-python-headless is available."""
    try:
        import cv2  # noqa: PLC0415,F401
        import numpy  # noqa: PLC0415,F401
    except ImportError:
        print("FAIL: opencv-python-headless not installed")
        print("      Install: uv sync --extra gpu")
        return False
    return True


def _write_test_frames(tmp: Path) -> tuple[Path, Path]:
    """Write two synthetic 720p frames to tmp/ and return their paths."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    frame_a = tmp / "frame_a.png"
    frame_b = tmp / "frame_b.png"
    rng = np.random.default_rng(seed=42)
    cv2.imwrite(str(frame_a), (rng.random((720, 1280, 3)) * 255).astype(np.uint8))
    cv2.imwrite(str(frame_b), (rng.random((720, 1280, 3)) * 255).astype(np.uint8))
    return frame_a, frame_b


def _resolve_rife_script() -> str | None:
    """Resolve the RIFE script path from config or default installation location."""
    from podcast_pipeline.config.settings import SmoothingConfig  # noqa: PLC0415

    config = SmoothingConfig()
    if config.rife_script_path:
        return config.rife_script_path

    default = Path("/opt/practical-rife/inference_img.py")
    if default.exists():
        return str(default)

    print("FAIL: RIFE script not found.")
    print("      Set 'smoothing.rife_script_path' in config.yaml, or clone practical-RIFE:")
    print("      git clone https://github.com/hzwer/ECCV2022-RIFE /opt/practical-rife")
    print("      Download RIFE 4.25 model weights and place in /opt/practical-rife/train_log/")
    return None


def main() -> int:
    """Run the GPU + RIFE smoke test.

    Returns 0 on success, 1 on any failure.
    """
    # Step 1: Verify torch + CUDA availability
    if not _check_torch():
        return 1

    # Step 2: Verify opencv-python-headless is available
    if not _check_opencv():
        return 1

    # Step 3: Resolve RIFE script path
    script_path_str = _resolve_rife_script()
    if script_path_str is None:
        return 1

    # Step 4: Run RIFE with synthetic frames
    from podcast_pipeline.utils.rife_bridge import RifeBridge  # noqa: PLC0415

    bridge = RifeBridge(script_path=script_path_str)
    if not bridge.available():
        print(f"FAIL: RIFE script not found at {script_path_str}")
        print("      Ensure 'rife_script_path' points to a valid inference_img.py file.")
        return 1

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        frame_a, frame_b = _write_test_frames(tmp)

        output_dir = tmp / "rife_out"
        frames = bridge.generate(frame_a, frame_b, output_dir, num_frames=4)

        if not frames:
            print("FAIL: RIFE generated no frames")
            print("      Check that RIFE model weights exist in train_log/ and CUDA is available.")
            return 1

        print(f"RIFE generated {len(frames)} bridge frames in {output_dir}")

    print("RIFE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
