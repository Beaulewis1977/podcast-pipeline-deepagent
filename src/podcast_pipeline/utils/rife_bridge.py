"""RIFE AI frame interpolation subprocess bridge.

Wraps the practical-RIFE ``inference_img.py`` script via ``subprocess.run``
to generate synthetic bridge frames between two images at a content-cut join.

Implementation notes:
- Use ``--exp`` flag (NOT ``--n`` — ``--n`` does not exist in RIFE).
- Pass ``--output <path>`` to control where frames are written.
- Pass ``--model <path>`` with absolute path to the ``train_log/`` directory
  containing model weights (``flownet.pkl``).
- Do NOT pass ``--cpu`` flag — it does not exist.  For CPU-only execution,
  set ``CUDA_VISIBLE_DEVICES=""`` in the subprocess environment instead.
- Default model: RIFE 4.25 (recommended; 4.26 exists but may produce artifacts
  on some content).
- RIFE generates 2^exp intermediate frames between the two input images.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class RifeBridge:
    """Subprocess wrapper for practical-RIFE frame interpolation.

    Usage::

        bridge = RifeBridge(script_path="/path/to/inference_img.py")
        if bridge.available():
            frames = bridge.generate(frame_a, frame_b, output_dir, num_frames=4)
        # frames is [] if RIFE unavailable or call fails.
    """

    def __init__(self, script_path: str = "") -> None:
        """Initialise with path to RIFE ``inference_img.py`` script.

        Parameters
        ----------
        script_path:
            Absolute path to the RIFE ``inference_img.py`` script.  An empty
            string or missing path causes ``available()`` to return False and
            ``generate()`` to return an empty list.
        """
        self.script_path: Path = Path(script_path) if script_path else Path("")

    def available(self) -> bool:
        """Return True if the RIFE inference script exists and is a file.

        This is a lightweight filesystem check — it does not validate that
        Python or RIFE dependencies are installed.
        """
        return self.script_path != Path("") and self.script_path.is_file()

    @staticmethod
    def frames_to_exp(num_frames: int) -> int:
        """Convert a desired intermediate frame count to the RIFE ``--exp`` value.

        RIFE generates ``2^exp`` frames between the two input images.  This
        method rounds *up* to the next power of two, so you always get at
        least ``num_frames`` interpolated frames.

        Examples
        --------
        >>> RifeBridge.frames_to_exp(1)
        1
        >>> RifeBridge.frames_to_exp(4)
        2
        >>> RifeBridge.frames_to_exp(8)
        3
        >>> RifeBridge.frames_to_exp(16)
        4

        Parameters
        ----------
        num_frames:
            Desired number of bridge frames (>= 1).

        Returns
        -------
        int
            ``--exp`` value such that ``2^exp >= num_frames``.  Minimum is 1.
        """
        clamped = max(num_frames, 1)
        return max(1, math.ceil(math.log2(clamped)))

    def generate(
        self,
        frame_a: Path,
        frame_b: Path,
        output_dir: Path,
        num_frames: int = 4,
    ) -> list[Path]:
        """Generate RIFE bridge frames between ``frame_a`` and ``frame_b``.

        Calls the RIFE ``inference_img.py`` script via ``subprocess.run``
        with the ``--exp`` flag.  Returns the sorted list of generated PNG
        files on success, or an empty list on any failure.

        Parameters
        ----------
        frame_a:
            Path to the left (outgoing) reference frame image.
        frame_b:
            Path to the right (incoming) reference frame image.
        output_dir:
            Directory where RIFE writes output PNG files.  Created if absent.
        num_frames:
            Desired number of bridge frames (default 4 → ``--exp 2``).

        Returns
        -------
        list[Path]
            Sorted list of generated ``.png`` files.  Empty list when RIFE is
            unavailable, the subprocess fails, or no output files are found.
        """
        if not self.available():
            logger.warning("rife_not_available", script_path=str(self.script_path))
            return []

        exp = self.frames_to_exp(num_frames)  # e.g. num_frames=4 → exp=2 (2^2=4 frames)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Run subprocess with cwd=rife_dir so that:
        # 1. Python relative imports work (from model.RIFE_HDv2, from train_log.RIFE_HDv3)
        # 2. Default --model "train_log" resolves to rife_dir/train_log/flownet.pkl
        rife_dir = self.script_path.parent
        model_dir = rife_dir / "train_log"

        cmd = [
            "python",
            str(self.script_path.resolve()),
            "--img",
            str(frame_a.resolve()),
            str(frame_b.resolve()),
            "--exp",
            str(exp),
            "--model",
            str(model_dir.resolve()),
            "--output",
            str(output_dir.resolve()),
        ]
        # NOTE: No --cpu flag (does not exist). For CPU: set CUDA_VISIBLE_DEVICES="" in env.

        logger.info(
            "rife_generating",
            exp=exp,
            num_frames=num_frames,
            frame_a=str(frame_a),
            frame_b=str(frame_b),
            output_dir=str(output_dir),
        )

        result = subprocess.run(cmd, cwd=str(rife_dir), capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(
                "rife_failed",
                returncode=result.returncode,
                stderr=result.stderr[:500],
                stdout=result.stdout[:200],
            )
            return []

        # RIFE writes img*.png into the --output directory
        generated = sorted(output_dir.glob("img*.png"))
        logger.info("rife_generated", count=len(generated), output_dir=str(output_dir))
        return generated
