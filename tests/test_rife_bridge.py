"""Tests for rife_bridge subprocess RIFE frame interpolation wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from podcast_pipeline.utils.rife_bridge import RifeBridge

# ---------------------------------------------------------------------------
# frames_to_exp conversion tests
# ---------------------------------------------------------------------------


class TestFramesToExp:
    """Unit tests for RifeBridge.frames_to_exp()."""

    def test_frames_to_exp_conversion(self) -> None:
        """Verify canonical conversion values from the plan spec."""
        assert RifeBridge.frames_to_exp(1) == 1, "1 frame → exp=1 (2^1=2 ≥ 1)"
        assert RifeBridge.frames_to_exp(2) == 1, "2 frames → exp=1 (2^1=2)"
        assert RifeBridge.frames_to_exp(4) == 2, "4 frames → exp=2 (2^2=4)"
        assert RifeBridge.frames_to_exp(8) == 3, "8 frames → exp=3 (2^3=8)"
        assert RifeBridge.frames_to_exp(16) == 4, "16 frames → exp=4 (2^4=16)"

    def test_frames_to_exp_rounds_up(self) -> None:
        """Non-power-of-two counts round up to the next power of two."""
        # 3 → needs 2^2=4 → exp=2
        assert RifeBridge.frames_to_exp(3) == 2
        # 5 → needs 2^3=8 → exp=3
        assert RifeBridge.frames_to_exp(5) == 3
        # 9 → needs 2^4=16 → exp=4
        assert RifeBridge.frames_to_exp(9) == 4

    def test_frames_to_exp_minimum_is_one(self) -> None:
        """frames_to_exp always returns at least 1."""
        assert RifeBridge.frames_to_exp(0) == 1
        assert RifeBridge.frames_to_exp(-5) == 1


# ---------------------------------------------------------------------------
# available() / generate() — no real RIFE installed
# ---------------------------------------------------------------------------


class TestRifeBridgeAvailability:
    """Tests for RifeBridge.available() and generate() when RIFE is absent."""

    def test_rife_bridge_not_available_empty_path(self) -> None:
        """Empty script_path → available() is False."""
        bridge = RifeBridge(script_path="")
        assert bridge.available() is False

    def test_rife_bridge_not_available_missing_file(self, tmp_path: Path) -> None:
        """Non-existent script file → available() is False."""
        bridge = RifeBridge(script_path=str(tmp_path / "no_inference_img.py"))
        assert bridge.available() is False

    def test_rife_bridge_available_existing_file(self, tmp_path: Path) -> None:
        """Existing script file → available() is True."""
        script = tmp_path / "inference_img.py"
        script.write_text("# stub\n")
        bridge = RifeBridge(script_path=str(script))
        assert bridge.available() is True

    def test_rife_bridge_generate_returns_empty_when_not_available(self, tmp_path: Path) -> None:
        """generate() returns empty list when RIFE script is absent."""
        bridge = RifeBridge(script_path=str(tmp_path / "missing.py"))
        result = bridge.generate(
            tmp_path / "a.png",
            tmp_path / "b.png",
            tmp_path / "out",
        )
        assert result == []


# ---------------------------------------------------------------------------
# Subprocess argument correctness tests (--exp, not --n, not --cpu)
# ---------------------------------------------------------------------------


class TestRifeBridgeSubprocessArgs:
    """Tests that verify the subprocess command uses --exp, --model, --output (not --n or --cpu)."""

    def test_rife_bridge_subprocess_args_use_exp_not_n(self, tmp_path: Path) -> None:
        """subprocess.run receives --exp, --model, --output; --n and --cpu are NOT present."""
        script = tmp_path / "inference_img.py"
        script.write_text("# stub\n")
        # Create train_log dir that rife_bridge expects next to the script
        (tmp_path / "train_log").mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        # RIFE writes img*.png into the --output directory
        (out_dir / "img001.png").write_bytes(b"PNG")
        (out_dir / "img002.png").write_bytes(b"PNG")

        captured_cmd: list[str] = []
        captured_kwargs: dict[str, object] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            captured_cmd.extend(cmd)
            captured_kwargs.update(kwargs)
            mock_result = MagicMock()
            mock_result.returncode = 0
            return mock_result

        bridge = RifeBridge(script_path=str(script))
        frame_a = tmp_path / "a.png"
        frame_a.write_bytes(b"PNG")
        frame_b = tmp_path / "b.png"
        frame_b.write_bytes(b"PNG")

        with patch("subprocess.run", side_effect=fake_run):
            bridge.generate(frame_a, frame_b, out_dir, num_frames=4)

        assert "--exp" in captured_cmd, "--exp flag must be present in subprocess args"
        # exp value for num_frames=4 is 2 (2^2=4)
        exp_idx = captured_cmd.index("--exp")
        assert captured_cmd[exp_idx + 1] == "2", "exp value must be 2 for num_frames=4"
        assert "--n" not in captured_cmd, "--n flag must NOT be used (it does not exist in RIFE)"
        assert "--cpu" not in captured_cmd, (
            "--cpu flag must NOT be used (it does not exist in RIFE)"
        )
        assert "--output" in captured_cmd, "--output flag must be passed to control output dir"
        assert "--model" in captured_cmd, "--model flag must be passed for model weight path"
        assert "cwd" in captured_kwargs, "subprocess.run must receive cwd kwarg"

    def test_rife_bridge_exp_value_matches_frames_to_exp(self, tmp_path: Path) -> None:
        """The --exp argument value matches frames_to_exp(num_frames)."""
        script = tmp_path / "inference_img.py"
        script.write_text("# stub\n")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "001.png").write_bytes(b"PNG")

        bridge = RifeBridge(script_path=str(script))
        frame_a = tmp_path / "a.png"
        frame_a.write_bytes(b"PNG")
        frame_b = tmp_path / "b.png"
        frame_b.write_bytes(b"PNG")

        for num_frames in (1, 4, 8, 16):
            expected_exp = str(RifeBridge.frames_to_exp(num_frames))
            captured: list[str] = []

            # Capture must be inside inner scope via nonlocal to avoid B023
            def make_fake_run(acc: list[str]) -> object:
                def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
                    acc.extend(cmd)
                    mock = MagicMock()
                    mock.returncode = 0
                    return mock

                return fake_run

            with patch("subprocess.run", side_effect=make_fake_run(captured)):
                bridge.generate(frame_a, frame_b, out_dir, num_frames=num_frames)

            exp_idx = captured.index("--exp") if "--exp" in captured else -1
            assert exp_idx != -1, f"--exp missing for num_frames={num_frames}"
            actual_exp = captured[exp_idx + 1]
            assert actual_exp == expected_exp, (
                f"For num_frames={num_frames}: expected --exp {expected_exp}, got {actual_exp}"
            )


# ---------------------------------------------------------------------------
# Subprocess failure / success path tests
# ---------------------------------------------------------------------------


class TestRifeBridgeSubprocessOutcomes:
    """Tests for subprocess success/failure handling in generate()."""

    def test_rife_bridge_subprocess_failure_returns_empty(self, tmp_path: Path) -> None:
        """Non-zero subprocess returncode → generate() returns empty list."""
        script = tmp_path / "inference_img.py"
        script.write_text("# stub\n")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        bridge = RifeBridge(script_path=str(script))

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "CUDA error: device not found\n"
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = bridge.generate(
                tmp_path / "a.png",
                tmp_path / "b.png",
                out_dir,
            )

        assert result == []

    def test_rife_bridge_subprocess_success_returns_sorted_pngs(self, tmp_path: Path) -> None:
        """Successful subprocess → generate() returns sorted list of PNG files from output_dir."""
        script = tmp_path / "inference_img.py"
        script.write_text("# stub\n")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # RIFE writes img*.png into the --output directory.
        # Create dummy PNG output files in unsorted order to verify sorting.
        (out_dir / "img003.png").write_bytes(b"PNG")
        (out_dir / "img001.png").write_bytes(b"PNG")
        (out_dir / "img002.png").write_bytes(b"PNG")

        # Input frames must exist (validation gate).
        frame_a = tmp_path / "a.png"
        frame_b = tmp_path / "b.png"
        frame_a.write_bytes(b"PNG")
        frame_b.write_bytes(b"PNG")

        bridge = RifeBridge(script_path=str(script))

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = bridge.generate(frame_a, frame_b, out_dir)

        assert len(result) == 3
        names = [p.name for p in result]
        assert names == sorted(names), "Returned frames must be sorted"
        assert all(p.suffix == ".png" for p in result)
        # All frames should be from output_dir directly with img prefix
        assert all(p.parent == out_dir for p in result), "Frames must come from output_dir"
        assert all(p.name.startswith("img") for p in result), "Frame names must use img prefix"

    def test_rife_bridge_output_dir_created_if_absent(self, tmp_path: Path) -> None:
        """generate() creates output_dir when it does not exist."""
        script = tmp_path / "inference_img.py"
        script.write_text("# stub\n")
        out_dir = tmp_path / "new_subdir" / "out"

        assert not out_dir.exists()

        # Input frames must exist (validation gate).
        frame_a = tmp_path / "a.png"
        frame_b = tmp_path / "b.png"
        frame_a.write_bytes(b"PNG")
        frame_b.write_bytes(b"PNG")

        mock_result = MagicMock()
        mock_result.returncode = 1  # Fail so no PNGs needed
        mock_result.stderr = "error\n"
        mock_result.stdout = ""

        bridge = RifeBridge(script_path=str(script))
        with patch("subprocess.run", return_value=mock_result):
            bridge.generate(frame_a, frame_b, out_dir)

        assert out_dir.exists(), "output_dir should be created before subprocess call"


# ---------------------------------------------------------------------------
# Upstream CLI contract tests (--output, --model, cwd kwarg present)
# ---------------------------------------------------------------------------


class TestRifeBridgeUpstreamContract:
    """Tests that verify the upstream-compatible CLI contract for inference_img.py."""

    def test_rife_bridge_subprocess_has_output_and_model_flags(self, tmp_path: Path) -> None:
        """generate() must pass --output and --model to subprocess."""
        script = tmp_path / "inference_img.py"
        script.write_text("# stub\n")
        # Create train_log dir next to script (where rife_bridge expects it)
        train_log = tmp_path / "train_log"
        train_log.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "img001.png").write_bytes(b"PNG")

        captured_cmd: list[str] = []
        captured_kwargs: dict[str, object] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            captured_cmd.extend(cmd)
            captured_kwargs.update(kwargs)
            mock = MagicMock()
            mock.returncode = 0
            return mock

        bridge = RifeBridge(script_path=str(script))
        frame_a = tmp_path / "a.png"
        frame_a.write_bytes(b"PNG")
        frame_b = tmp_path / "b.png"
        frame_b.write_bytes(b"PNG")

        with patch("subprocess.run", side_effect=fake_run):
            bridge.generate(frame_a, frame_b, out_dir, num_frames=4)

        assert "--output" in captured_cmd, (
            "--output must be passed to control where RIFE writes frames"
        )
        out_idx = captured_cmd.index("--output")
        assert captured_cmd[out_idx + 1] == str(out_dir.resolve()), (
            "--output value must be the resolved output_dir path"
        )
        assert "--model" in captured_cmd, "--model must be passed with absolute path to train_log/"
        model_idx = captured_cmd.index("--model")
        assert captured_cmd[model_idx + 1] == str(train_log.resolve()), (
            "--model value must be resolved path to rife_dir/train_log"
        )
        assert "cwd" in captured_kwargs, (
            "subprocess.run must be called with cwd kwarg for RIFE Python imports"
        )

    def test_rife_bridge_collects_from_output_dir_directly(self, tmp_path: Path) -> None:
        """generate() collects frames from output_dir/img*.png directly."""
        script = tmp_path / "inference_img.py"
        script.write_text("# stub\n")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # Create frames directly in output_dir (where --output points)
        (out_dir / "img001.png").write_bytes(b"PNG")
        (out_dir / "img002.png").write_bytes(b"PNG")

        # Create a decoy PNG without img prefix — must NOT be collected
        (out_dir / "decoy.png").write_bytes(b"PNG")

        # Input frames must exist (validation gate).
        frame_a = tmp_path / "a.png"
        frame_b = tmp_path / "b.png"
        frame_a.write_bytes(b"PNG")
        frame_b.write_bytes(b"PNG")

        bridge = RifeBridge(script_path=str(script))

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = bridge.generate(frame_a, frame_b, out_dir)

        assert len(result) == 2, f"Expected 2 img*.png frames, got {len(result)}"
        assert all(p.parent == out_dir for p in result), "Frames must be from output_dir directly"
        assert all(p.name.startswith("img") for p in result), (
            "Frame names must use img prefix (img*.png glob pattern)"
        )
        # Decoy without img prefix must not be included
        collected_names = [p.name for p in result]
        assert "decoy.png" not in collected_names, "Non-img-prefixed PNG must not be collected"
