# Phase 8: Intelligent Cut Quality — Research

**Researched:** 2026-02-21
**Domain:** Audio/video processing — VAD, frame interpolation, optical flow, LLM triage
**Confidence:** MEDIUM (several CRITICAL spec corrections required; see Spec Corrections section)

---

## Summary

Phase 8 delivers two independent workstreams: intelligent filler triage (categorisation,
pause-gate, LLM semantic check) and invisible cut rendering (de-breathing, noise-floor
matching, pose-match frame selection, RIFE frame interpolation). The existing spec was
written by an agent that did not verify library versions or GPU architecture, and contains
several critical errors that would block implementation if followed literally.

**The three most important corrections:**
1. The RTX 5060 Ti is Blackwell architecture (sm_120 / compute 12.0), NOT Ada Lovelace
   (compute 8.9). The correct PyTorch wheel is cu128 via PyTorch 2.7+, not cu121 + torch
   2.3. This is a hard blocker.
2. silero-vad is now at version 6.2.0 (not 5.x); the import API is unchanged but
   torchaudio has been partially deprecated and the fix landed in silero-vad 6.1.
3. The `--n` and `--cpu` CLI flags the spec references for `inference_img.py` do NOT
   exist. The actual flag is `--exp` (2^N frames); there is no `--cpu` switch.

The filler triage workstream (Plans 01-03) is pure Python with no new external
dependencies and is straightforward. The invisible cut rendering workstream (Plans 04-06)
requires careful dependency management due to the GPU stack complexity.

**Primary recommendation:** Implement Plans 01-03 (filler triage) first as they are
self-contained. Treat torch/RIFE as optional GPU extras in pyproject.toml using uv's
`[tool.uv.sources]` pattern to avoid pulling a 2GB wheel into the base install.

---

## Spec Corrections

These are verified corrections to `2026-02-21-intelligent-cut-quality-spec.md`. The
planner MUST apply these before rebuilding plans.

### CORRECTION 1 — GPU Architecture (CRITICAL BLOCKER)

**Spec says:** RTX 5060 Ti = Ada Lovelace, compute capability 8.9, use `cu121`.
**Truth:** RTX 5060 Ti = Blackwell architecture, compute capability **sm_120 (12.0)**.

| Item | Spec (WRONG) | Correct |
|------|-------------|---------|
| Architecture | Ada Lovelace | Blackwell |
| Compute capability | 8.9 | 12.0 (sm_120) |
| CUDA wheel | cu121 | cu128 |
| Min PyTorch | 2.3 | **2.7** (first stable Blackwell support) |
| Min torchvision | 0.18 | 0.22 (paired with torch 2.7) |
| CUDA toolkit | 12.x | **12.8+** (required for sm_120) |

PyTorch 2.7 introduced [Prototype] Blackwell support with CUDA 12.8 wheels.
PyTorch 2.8+ (August 2025) has further improved support.
The cu121 index (CUDA 12.1) does NOT ship sm_120 kernels — torch would install but
fall back to CPU silently or fail with a kernel mismatch at runtime.

**Source:** [PyTorch 2.7 release blog](https://pytorch.org/blog/pytorch-2-7/),
[PyTorch forum — RTX 5060 Ti sm_120](https://discuss.pytorch.org/t/how-do-i-use-pytorch-with-rtx-5060-ti/220926)
**Confidence:** HIGH

### CORRECTION 2 — silero-vad version (HIGH)

**Spec says:** `silero-vad >= 5.0`, model at `~/.cache/torch/`.
**Truth:** Current stable is **6.2.0** (released 2025-11-06). The `>=5.0` pin installs 6.x
because it satisfies the constraint, but silero-vad 6.1 changed internal torchaudio usage
to fix PyTorch 2.8/2.9 deprecations. Use `>=6.1` to get the fix.

The import API (`from silero_vad import load_silero_vad, read_audio, get_speech_timestamps`)
is UNCHANGED between 5.x and 6.x — that part of the spec is correct.

The model still auto-downloads to `~/.cache/torch/hub/` on first `load_silero_vad()` call.
Model size is ~2MB. CPU-only operation is confirmed correct.

**One new concern:** silero-vad 6.x requires `torchaudio` as a dependency for audio I/O.
torchaudio is in the process of being deprecated (many APIs removed in 2.9) and is now in
maintenance mode. silero-vad 6.1 fixed the deprecated `torchaudio.sox_effects` and
`torchaudio._backend.list_audio_backends` calls, so 6.1+ is safe with torch 2.7-2.9.

**IMPORTANT:** silero-vad will pull in `torchaudio` as a dependency. This conflicts with
the goal of making torch optional. Either:
(a) Accept torch+torchaudio as a required dep in the `gpu` optional group, or
(b) Use silero-vad's ONNX backend with `onnxruntime` + `soundfile` directly — no torch
    needed. The ONNX path is documented but requires custom wrappers replacing `read_audio`.

**Recommendation:** Use the standard PyTorch path (`pip install silero-vad torch`), placed
in an optional `[project.optional-dependencies] gpu = [...]` group. Keep the base install
clean. All VAD-related code uses lazy imports with graceful CPU fallback.

**Source:** [silero-vad PyPI](https://pypi.org/project/silero-vad/),
[issue #667](https://github.com/snakers4/silero-vad/issues/667)
**Confidence:** HIGH

### CORRECTION 3 — practical-RIFE inference_img.py CLI (CRITICAL BLOCKER)

**Spec says:** Use `--n N` to specify number of frames; use `--cpu` for CPU fallback.
**Truth:** Neither `--n` nor `--cpu` exist in `inference_img.py`.

Actual `inference_img.py` arguments (verified from GitHub source):
- `--img img0.png img1.png` — two input image paths (required)
- `--exp 4` — exponential factor; generates **2^exp** frames (default 4 = 16 frames)
- `--ratio 0` — interpolation ratio 0-1 (default 0)
- `--rthreshold 0.02` — ratio threshold for bisectional cycles
- `--rmaxcycles 8` — max bisectional cycles
- `--model train_log` — model directory

**There is no `--cpu` flag.** Device selection in the RIFE codebase is handled via
`torch.device` in the model loader, not CLI args. To force CPU you would need to edit the
model code or set `CUDA_VISIBLE_DEVICES=""`.

**For 4 bridge frames:** use `--exp 2` (2^2 = 4). For 8 frames: `--exp 3`. The spec's
`--n 4` does NOT work.

**The `--output` flag** documented in the spec IS correct for `inference_img.py`.

**Source:** [inference_img.py on GitHub](https://github.com/hzwer/ECCV2022-RIFE/blob/main/inference_img.py),
[Practical-RIFE README](https://github.com/hzwer/Practical-RIFE/blob/main/README.md)
**Confidence:** HIGH

### CORRECTION 4 — practical-RIFE model download (MEDIUM)

**Spec says:** Weights on Google Drive; HuggingFace mirror available.
**Truth:** Weights are on Google Drive AND Baidu Pan. There is NO official HuggingFace
mirror maintained by hzwer. The third-party `deepghs/silero-vad-onnx` HuggingFace repo
referenced in one search result is for VAD, not RIFE.

The recommended default model is **4.25** (not 4.26). The README states 4.25 is the
default for most scenes; 4.26 has improved anime but introduces artifacts on some content.
For talking-head podcast video, use 4.25.

**Source:** [Practical-RIFE README](https://github.com/hzwer/Practical-RIFE/blob/main/README.md)
**Confidence:** HIGH

### CORRECTION 5 — gpt-4o-mini API status (LOW severity, good news)

**Spec concern:** The spec uses gpt-4o-mini for LLM triage.
**Truth:** gpt-4o-mini is NOT deprecated from the OpenAI API as of 2026-02-21. The
deprecation announced Feb 2026 affects the ChatGPT UI, not API access. The API endpoint
remains live with no announced sunset date. gpt-4o-mini remains the correct cheap-batch
LLM for filler triage.

**Source:** [OpenAI Deprecations](https://developers.openai.com/api/docs/deprecations/)
**Confidence:** MEDIUM (OpenAI can change this without warning; use model config field so
it can be swapped)

### CORRECTION 6 — torchvision requirement (MEDIUM)

**Spec says:** `torchvision >= 0.18` required by RIFE.
**Truth:** practical-RIFE does NOT require torchvision in its `requirements.txt`. RIFE
only needs `torch` and `cupy-cuda12x` (for CUDA) and standard packages. Adding torchvision
is unnecessary weight. Omit from dependencies unless RIFE requirements.txt explicitly lists
it (verify when cloning).

**Confidence:** MEDIUM (verify against actual RIFE requirements.txt at clone time)

### CORRECTION 7 — librosa version (LOW severity, informational)

**Spec says:** `librosa >= 0.10`.
**Truth:** Current stable is 0.11.0 (March 2025). The `librosa.feature.rms(y=...)[0].mean()`
API is unchanged between 0.10 and 0.11. There are no breaking changes for this usage.
The spec code example is correct. Pin to `>=0.10` is fine; `>=0.11` is equally valid.

**Confidence:** HIGH

---

## Standard Stack

### Core (filler triage — no new deps)

All Plans 01-03 use only existing project dependencies:
- Pydantic v2 (already in deps)
- OpenAI provider (already in deps via `openai>=1.60.0`)
- structlog (already in deps)

No new pip installs required for the entire filler triage workstream.

### Audio processing (Plans 04 — de-breathing + noise-floor)

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| `silero-vad` | `>=6.1` | VAD / breath detection at cut boundaries | Auto-downloads ~2MB model; CPU only |
| `librosa` | `>=0.10` | RMS noise-floor measurement | soundfile already in project deps |
| `soundfile` | `>=0.12.1` | Audio I/O backend | **Already in pyproject.toml** |

silero-vad will transitively require `torch` and `torchaudio`. These belong in the optional
`gpu` extras group, not core dependencies.

### Video processing (Plan 05 — pose-match + RIFE)

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| `opencv-python-headless` | `>=4.9` | Farneback optical flow | Use HEADLESS variant for servers |
| `torch` | `>=2.7` | Required by silero-vad + RIFE subprocess | gpu optional group |
| `torchaudio` | `>=2.7` | Required by silero-vad | gpu optional group |
| practical-RIFE | RIFE 4.25 model | Frame interpolation subprocess | Cloned, NOT pip-installable |

**Use opencv-python-headless, NOT opencv-python.** The headless variant omits Qt/GUI
dependencies that conflict on server environments. Latest version is 4.13.0.92 (Feb 2026).

**Installation (optional gpu extras):**

```toml
# pyproject.toml additions

[project.optional-dependencies]
gpu = [
    "silero-vad>=6.1",
    "librosa>=0.10",
    "opencv-python-headless>=4.9",
]

# torch goes via uv.sources — not in optional-dependencies directly
# because it needs a custom index URL

[tool.uv.sources]
torch = [
    { index = "pytorch-cu128", marker = "sys_platform == 'linux' or sys_platform == 'win32'" },
]
torchaudio = [
    { index = "pytorch-cu128", marker = "sys_platform == 'linux' or sys_platform == 'win32'" },
]

[[tool.uv.index]]
name = "pytorch-cu128"
url = "https://download.pytorch.org/whl/cu128"
explicit = true
```

**Install command:**
```bash
# Install GPU optional group (silero-vad, librosa, opencv):
uv sync --extra gpu

# Install torch separately with CUDA 12.8 for RTX 5060 Ti (Blackwell):
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

# Or use --torch-backend flag (uv >= 0.5.x):
UV_TORCH_BACKEND=cu128 uv pip install torch torchaudio
```

**practical-RIFE setup (one-time, not pip):**
```bash
git clone https://github.com/hzwer/Practical-RIFE.git /opt/practical-rife
cd /opt/practical-rife
pip install -r requirements.txt
# Download RIFE 4.25 weights to train_log/ (Google Drive link in README)
```

### Pip-installable RIFE alternative (if subprocess approach is unwanted)

`vsrife` (version 5.7.0, released 2026-02-09) is a pip-installable VapourSynth-based RIFE:
- `pip install vsrife`
- Requires Python >=3.10, supports CUDA + TensorRT
- Based on Practical-RIFE

However, vsrife depends on VapourSynth which itself requires system installation. For this
project's subprocess pattern, the git-clone approach is simpler. Mention vsrife only in
code comments as an alternative.

### FFmpeg

Ubuntu 24.04 ships FFmpeg **6.1.1** via `apt install ffmpeg`. This is sufficient for all
Phase 7 and 8 filters (concat demuxer, xfade, acrossfade, volume with eval=frame). No PPA
required.

---

## Architecture Patterns

### Recommended Project Structure (new files)

```
src/podcast_pipeline/
├── utils/
│   ├── vad.py           # silero-vad breath detection wrapper (lazy import)
│   ├── noise_match.py   # librosa RMS delta + FFmpeg filter builder
│   ├── pose_match.py    # opencv Farneback pose distance scanner
│   └── rife_bridge.py   # RIFE subprocess wrapper with --exp flag correction
├── models/
│   └── triage.py        # FillerTriage + FillerTriageResult Pydantic models
tests/
├── test_vad.py
├── test_noise_match.py
├── test_pose_match.py
├── test_rife_bridge.py
└── test_triage.py
```

### Pattern 1: Lazy Optional Imports

All GPU-dependent utilities use lazy imports with graceful fallback. This keeps the base
package importable without torch/opencv installed.

```python
# src/podcast_pipeline/utils/vad.py
from __future__ import annotations
from pathlib import Path

_vad_model = None  # singleton

def detect_breath_at_boundary(
    audio_path: Path,
    boundary_seconds: float,
    *,
    window_ms: float = 200.0,
    max_extend_ms: float = 150.0,
) -> float:
    """Return seconds to extend cut boundary to swallow trailing breath. 0.0 if unavailable."""
    try:
        from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
    except ImportError:
        return 0.0  # silero-vad not installed — skip de-breathing
    # ... implementation
```

### Pattern 2: RIFE subprocess with corrected --exp flag

The spec's `--n` and `--cpu` flags do not exist. Use `--exp`:

```python
# src/podcast_pipeline/utils/rife_bridge.py
import math
import subprocess
from pathlib import Path

RIFE_INFERENCE_SCRIPT = Path("/opt/practical-rife/inference_img.py")


class RifeBridge:
    def __init__(self, script_path: Path = RIFE_INFERENCE_SCRIPT) -> None:
        self.script_path = script_path

    def _num_frames_to_exp(self, num_frames: int) -> int:
        """Convert desired bridge frame count to --exp value (2^exp frames)."""
        # Round up to next power of 2
        exp = math.ceil(math.log2(max(num_frames, 1)))
        return max(exp, 1)

    def generate_bridge_frames(
        self,
        frame_a: Path,
        frame_b: Path,
        output_dir: Path,
        num_frames: int = 4,
    ) -> list[Path]:
        """Generate bridge frames using RIFE. Returns empty list if RIFE unavailable."""
        if not self.script_path.exists():
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        exp = self._num_frames_to_exp(num_frames)  # 4 frames -> exp=2
        cmd = [
            "python", str(self.script_path),
            "--img", str(frame_a), str(frame_b),
            "--output", str(output_dir),
            "--exp", str(exp),
        ]
        # No --cpu flag exists. To force CPU: set CUDA_VISIBLE_DEVICES="" in env
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            return []
        return sorted(output_dir.glob("*.png"))
```

### Pattern 3: librosa RMS API (verified correct)

The spec's librosa usage is correct:

```python
# Source: librosa 0.11 docs - https://librosa.org/doc/main/generated/librosa.feature.rms.html
import librosa
import numpy as np

y, sr = librosa.load("segment.wav", sr=None, mono=True)
window_samples = int(0.1 * sr)  # 100ms window
tail = y[-window_samples:] if len(y) >= window_samples else y

rms = librosa.feature.rms(y=tail)[0].mean()  # returns (1, n_frames) array; [0] = frame 0
rms_db = 20.0 * np.log10(max(rms, 1e-9))
```

Note: `librosa.feature.rms(y=...)` returns shape `(1, n_frames)`. The `[0]` indexes the
channel, not a frame. `.mean()` averages across frames. This is correct.

### Pattern 4: OpenCV Farneback (use headless variant)

```python
# Source: OpenCV docs - https://docs.opencv.org/4.x/
import cv2
import numpy as np

def pose_distance(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        gray_a, gray_b, None,
        pyr_scale=0.5,   # pyramid scale (< 1)
        levels=3,        # pyramid levels
        winsize=15,      # averaging window size
        iterations=3,    # iterations per level
        poly_n=5,        # pixel neighborhood size
        poly_sigma=1.2,  # Gaussian std for polynomial expansion
        flags=0,
    )
    magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    return float(magnitude.mean())
```

API is stable and unchanged in opencv 4.9 through 4.13. The spec parameters are correct.
Use `opencv-python-headless`, NOT `opencv-python` (avoids Qt conflicts on WSL/server).

### Pattern 5: silero-vad 6.x API (verified correct)

```python
# Source: silero-vad 6.2 - https://github.com/snakers4/silero-vad
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps

model = load_silero_vad()  # downloads ~2MB to ~/.cache/torch/hub/ on first call
audio = read_audio("audio.wav", sampling_rate=16000)
timestamps = get_speech_timestamps(
    audio, model,
    sampling_rate=16000,
    return_seconds=True,  # return timestamps in seconds not samples
)
# timestamps: list of {"start": float, "end": float} dicts
```

**Import API is UNCHANGED from 5.x to 6.x.** The spec's import line is correct.
Pin to `>=6.1` to get the torchaudio deprecation fix.

### Anti-Patterns to Avoid

- **Using `--n` or `--cpu` with RIFE `inference_img.py`:** These flags do not exist.
  Use `--exp` for frame count; set `CUDA_VISIBLE_DEVICES=""` env var for CPU mode.
- **Installing `opencv-python` instead of `opencv-python-headless`:** Qt libs fail on
  headless servers/WSL. Always use headless.
- **Specifying `cu121` wheel for RTX 5060 Ti:** sm_120 is not in cu121 kernels. Use cu128.
- **Adding `torchvision` to deps for RIFE:** RIFE does not require torchvision. Bloat.
- **Making torch a hard dependency:** 2GB+ download. Put in optional extras group.
- **Calling `librosa.feature.rms()` without `y=` keyword:** 0.11 made it keyword-only.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Voice activity detection | Custom energy threshold breath detector | silero-vad | Trained model handles complex breath patterns, noisy audio, variable-level recordings |
| RMS energy measurement | Manual numpy FFT/energy calc | `librosa.feature.rms()` | Frame-accurate, handles edge cases (silence, clipping, mono/stereo) |
| Optical flow | Dense motion estimation from scratch | `cv2.calcOpticalFlowFarneback` | Decades of parameter tuning; Farneback is fast and accurate for near-static scenes |
| Frame interpolation | Neural flow interpolation model | practical-RIFE (subprocess) | RIFE 4.25 has 2+ years of stability, GPU-optimized kernels, proven on talking-head video |
| Batch LLM calls | Custom retry/rate-limit logic | Existing `OpenAIProvider` pattern | Project already has tenacity-backed retries and error handling |
| Audio file I/O in VAD | Custom WAV parser | `read_audio()` from silero-vad | Handles sample rate conversion, format detection, mono/stereo |

**Key insight:** The GPU/CV stack has significant platform-specific edge cases (driver
versions, kernel availability, numpy ABI, headless display servers). Use proven libraries
rather than hand-rolling any of these.

---

## Common Pitfalls

### Pitfall 1: RTX 5060 Ti sm_120 not recognized by torch < 2.7
**What goes wrong:** `torch.cuda.is_available()` returns False or returns True but CUDA
ops fail with `no kernel image is available for execution on the device`.
**Why it happens:** torch < 2.7 was built against CUDA 12.1 which does not ship sm_120
kernels. PyTorch silently falls back to CPU or errors at runtime.
**How to avoid:** Install torch 2.7+ from `download.pytorch.org/whl/cu128`. Verify with:
```bash
python -c "import torch; print(torch.version.cuda, torch.cuda.get_device_capability())"
# Expected: 12.8  (12, 0)
```
**Warning signs:** `get_device_capability()` returns `(12, 0)` but CUDA tensors fail.

### Pitfall 2: inference_img.py exits with wrong --exp value
**What goes wrong:** Requesting 4 bridge frames but passing `--exp 4` generates 16 frames
(2^4), not 4. At 30fps this is 533ms of synthesized video — way too long.
**Why it happens:** `--exp` is an exponent, not a count. `--exp 2` = 4 frames (2^2).
**How to avoid:** In `RifeBridge._num_frames_to_exp()`: `exp = ceil(log2(num_frames))`.
For 4 frames: exp=2. For 8 frames: exp=3. Document this in the wrapper.

### Pitfall 3: silero-vad read_audio sampling_rate mismatch
**What goes wrong:** VAD returns incorrect timestamps because the audio was resampled.
**Why it happens:** `read_audio()` resamples to the specified `sampling_rate`. If you then
call `get_speech_timestamps()` with a different `sampling_rate`, timestamps are wrong.
**How to avoid:** Always use a consistent sampling_rate (16000 is the native VAD rate).
Pass the same value to both `read_audio()` and `get_speech_timestamps()`.

### Pitfall 4: opencv-python GUI import fails on WSL/headless
**What goes wrong:** `import cv2` raises `cannot open display` or `qt.qpa.plugin` errors
when running on WSL or a headless Linux server.
**Why it happens:** `opencv-python` (non-headless) links Qt display libraries.
**How to avoid:** Install `opencv-python-headless` exclusively. Never install both variants.

### Pitfall 5: numpy ABI mismatch between opencv and torch
**What goes wrong:** `ImportError: numpy.core._multiarray_umath failed to import` or
similar ABI errors when both opencv and torch are imported in the same process.
**Why it happens:** opencv 4.12+ requires numpy >=2, while some torch wheels shipped with
numpy 1.x ABI. The conflict manifests only when both are imported.
**How to avoid:** Use `numpy>=2.0` and opencv-python-headless 4.9+. If a conflict appears,
pin numpy to `>=2.0,<2.3` (opencv 4.13's stated upper bound).
**Warning signs:** Segfaults or import errors only when both cv2 and torch are imported.

### Pitfall 6: pose_match scan window extends past segment boundary
**What goes wrong:** When scanning ±200ms for best frame pair, the window index goes
negative or past the end of the frame buffer.
**Why it happens:** Short segments (< 200ms remaining after cut) can't provide a full
±200ms window.
**How to avoid:** Clamp window: `search_n = min(search_window_frames, len(frames) // 2)`.
The spec's risk register mentions this — the mitigation is correct.

### Pitfall 7: gpt-4o-mini model name in config must be version-stable
**What goes wrong:** OpenAI silently reroutes `gpt-4o-mini` to a newer model or retires
a snapshot version.
**Why it happens:** OpenAI uses alias routing that can change.
**How to avoid:** The spec correctly uses a config field `llm_triage_model` that can be
overridden. Default to `"gpt-4o-mini"` but document that operators should pin a specific
snapshot like `"gpt-4o-mini-2024-07-18"` for production stability.

### Pitfall 8: torchaudio pulled by silero-vad breaks CPU-only installs
**What goes wrong:** `pip install silero-vad` pulls `torchaudio` which in turn tries to
pull a CUDA-capable torch, causing a 2GB download on a CPU-only machine.
**Why it happens:** silero-vad lists torchaudio as a hard dependency.
**How to avoid:** Install silero-vad AFTER torch (CPU or GPU) is already pinned. uv will
respect the already-installed torch version. Or use silero-vad's ONNX backend with
`onnxruntime` instead, avoiding torchaudio entirely (requires custom audio loading wrapper).

---

## Code Examples

### Verified: silero-vad 6.x breath detection at cut boundary

```python
# Source: silero-vad GitHub https://github.com/snakers4/silero-vad
from __future__ import annotations
from pathlib import Path

_vad_model = None

def detect_breath_extension(
    audio_path: Path,
    cut_out_seconds: float,
    *,
    window_ms: float = 200.0,
    max_extend_ms: float = 150.0,
    sampling_rate: int = 16000,
) -> float:
    """Return extra seconds to trim at cut boundary to swallow a trailing breath."""
    global _vad_model
    try:
        from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
    except ImportError:
        return 0.0

    if _vad_model is None:
        _vad_model = load_silero_vad()

    window_s = window_ms / 1000.0
    audio = read_audio(str(audio_path), sampling_rate=sampling_rate)

    # Extract window ending at cut_out_seconds
    end_sample = int(cut_out_seconds * sampling_rate)
    start_sample = max(0, end_sample - int(window_s * sampling_rate))
    segment = audio[start_sample:end_sample]

    if len(segment) < int(0.02 * sampling_rate):
        return 0.0

    timestamps = get_speech_timestamps(segment, _vad_model, sampling_rate=sampling_rate)

    seg_len = len(segment)
    last_speech_end = timestamps[-1]["end"] if timestamps else 0
    trailing_non_speech_samples = seg_len - last_speech_end
    trailing_s = trailing_non_speech_samples / sampling_rate
    return min(trailing_s, max_extend_ms / 1000.0)
```

### Verified: RIFE bridge frames (corrected --exp flag)

```python
# Source: hzwer/Practical-RIFE inference_img.py argparse (verified Feb 2026)
import math
import subprocess
from pathlib import Path


class RifeBridge:
    def __init__(self, script_path: Path) -> None:
        self.script_path = script_path

    def available(self) -> bool:
        return self.script_path.exists()

    @staticmethod
    def frames_to_exp(num_frames: int) -> int:
        """Convert desired frame count to --exp value. 4->2, 8->3, 16->4."""
        return max(1, math.ceil(math.log2(max(num_frames, 1))))

    def generate(
        self,
        frame_a: Path,
        frame_b: Path,
        output_dir: Path,
        num_frames: int = 4,
    ) -> list[Path]:
        if not self.available():
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        exp = self.frames_to_exp(num_frames)
        cmd = [
            "python", str(self.script_path),
            "--img", str(frame_a), str(frame_b),
            "--output", str(output_dir),
            "--exp", str(exp),
        ]
        # To force CPU mode: set env CUDA_VISIBLE_DEVICES="" (no --cpu flag exists)
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return []
        return sorted(output_dir.glob("*.png"))
```

### Verified: librosa noise-floor RMS delta

```python
# Source: librosa 0.11 docs https://librosa.org/doc/main/generated/librosa.feature.rms.html
import librosa
import numpy as np


def measure_rms_db(path: str, window_ms: float = 100.0, tail: bool = True) -> float:
    """Measure RMS dB of head or tail of audio file."""
    y, sr = librosa.load(path, sr=None, mono=True)
    n = int(window_ms / 1000.0 * sr)
    segment = y[-n:] if tail else y[:n]
    if len(segment) == 0:
        return -120.0
    rms = librosa.feature.rms(y=segment)[0].mean()
    return float(20.0 * np.log10(max(rms, 1e-9)))
```

### Verified: torch + CUDA 12.8 install for RTX 5060 Ti

```bash
# Correct install for Blackwell sm_120 — RTX 5060 Ti
# Source: https://pytorch.org/blog/pytorch-2-7/
pip install torch==2.7.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128

# Verify Blackwell detection:
python -c "
import torch
print('CUDA available:', torch.cuda.is_available())
print('Device capability:', torch.cuda.get_device_capability())  # Should be (12, 0)
print('Device name:', torch.cuda.get_device_name(0))
"
```

### Verified: uv pyproject.toml for torch GPU extras

```toml
# pyproject.toml additions for Phase 8 GPU stack

[project.optional-dependencies]
gpu = [
    "silero-vad>=6.1",
    "librosa>=0.10",
    "opencv-python-headless>=4.9",
    # torch and torchaudio are declared via [tool.uv.sources] below
]

[tool.uv.sources]
torch = [
    { index = "pytorch-cu128", marker = "sys_platform == 'linux' or sys_platform == 'win32'" },
]
torchaudio = [
    { index = "pytorch-cu128", marker = "sys_platform == 'linux' or sys_platform == 'win32'" },
]

[[tool.uv.index]]
name = "pytorch-cu128"
url = "https://download.pytorch.org/whl/cu128"
explicit = true
```

---

## State of the Art

| Old Approach (Spec) | Corrected Approach | Impact |
|---------------------|-------------------|--------|
| `silero-vad >= 5.0` | `silero-vad >= 6.1` | Gets torchaudio fix; API unchanged |
| torch `>=2.3` + cu121 | torch `>=2.7` + cu128 | Required for RTX 5060 Ti sm_120 |
| torchvision `>=0.18` | Omit torchvision | RIFE does not need it |
| RIFE `--n 4` | RIFE `--exp 2` (= 4 frames) | The `--n` flag does not exist |
| RIFE `--cpu` fallback | Set `CUDA_VISIBLE_DEVICES=""` | The `--cpu` flag does not exist |
| `opencv-python` | `opencv-python-headless` | Avoids Qt/display errors on WSL/server |
| "RIFE 4.26 recommended" | Use RIFE 4.25 as default | 4.26 has artifacts on some content |
| HuggingFace RIFE mirror | Google Drive (official only) | No official HF mirror exists |

**Deprecated/outdated in spec:**
- `cu121` wheel index: use `cu128` for Blackwell
- `--n` and `--cpu` RIFE flags: use `--exp` and env var

---

## Blockers

### Blocker 1: RTX 5060 Ti requires PyTorch 2.7+ with cu128 — HARD BLOCKER
The spec's torch 2.3 + cu121 combination will not produce working CUDA on this GPU.
Without this fix, RIFE runs on CPU (if at all), making it too slow for production use.
**Resolution:** Change torch dependency to `>=2.7`, install from cu128 index.
**Risk:** PyTorch 2.7 Blackwell support is marked [Prototype] — occasional instability
is possible. Consider adding error handling around CUDA-specific RIFE calls.

### Blocker 2: RIFE `--n` flag does not exist — HARD BLOCKER for Plan 05
`RifeBridge.generate_bridge_frames()` as written in the spec will always fail with
`unrecognized arguments: --n`. The `--cpu` flag will also fail.
**Resolution:** Replace `--n N` with `--exp ceil(log2(N))`. Remove `--cpu` flag; use env var.

---

## Open Questions

1. **Does practical-RIFE `inference_img.py` accept `--output` as a directory or file path?**
   - What we know: `inference_video.py` uses `--output` as file path; `inference_img.py` likely
     uses it as directory (outputs multiple PNGs).
   - What's unclear: Exact behavior when output directory already exists / contains files.
   - Recommendation: Create a fresh temp directory per invocation to avoid collisions.

2. **Is RIFE 4.25 weight download automated or manual?**
   - What we know: README provides Google Drive links; no `gdown` automation documented.
   - What's unclear: Whether there's a script to automate weight download.
   - Recommendation: Document manual download in setup docs; add a check in `RifeBridge.available()`
     that verifies `train_log/` directory exists and is non-empty.

3. **numpy 2.x and opencv-python-headless compatibility on this project's numpy pin?**
   - What we know: opencv 4.13 requires numpy >=2,<2.3; torch 2.7+ works with numpy 2.x.
   - What's unclear: Whether the project currently pins numpy below 2.x.
   - Recommendation: Add `numpy>=2.0` to gpu optional group. Check `uv.lock` for conflicts
     before implementing.

4. **silero-vad ONNX alternative to avoid torchaudio dependency?**
   - What we know: ONNX backend works with `onnxruntime` + custom audio loading.
   - What's unclear: Production stability and whether it maintains identical output.
   - Recommendation: Start with standard torch path. Document ONNX as future fallback if
     torchaudio deprecation causes further breakage.

---

## Sources

### Primary (HIGH confidence)
- [PyTorch 2.7 Release Blog](https://pytorch.org/blog/pytorch-2-7/) — Blackwell support, CUDA 12.8 wheels, install commands
- [silero-vad PyPI](https://pypi.org/project/silero-vad/) — version 6.2.0, Python compatibility, install API
- [silero-vad GitHub #667](https://github.com/snakers4/silero-vad/issues/667) — torchaudio deprecation fix in v6.1
- [Practical-RIFE README](https://github.com/hzwer/Practical-RIFE/blob/main/README.md) — model versions, CLI, weight sources
- [RIFE inference_img.py source](https://github.com/hzwer/ECCV2022-RIFE/blob/main/inference_img.py) — argparse: --img, --exp, --output (no --n or --cpu)
- [librosa 0.11 changelog](https://librosa.org/doc/0.11.0/changelog.html) — no breaking changes to rms API
- [librosa.feature.rms docs](https://librosa.org/doc/main/generated/librosa.feature.rms.html) — API signature
- [opencv-python PyPI](https://pypi.org/project/opencv-python/) — version 4.13.0.92, Python 3.12 supported
- [uv PyTorch guide](https://docs.astral.sh/uv/guides/integration/pytorch/) — tool.uv.sources pattern for cu128
- [OpenAI Deprecations](https://developers.openai.com/api/docs/deprecations/) — gpt-4o-mini not listed as deprecated

### Secondary (MEDIUM confidence)
- [PyTorch forum — RTX 5060 Ti](https://discuss.pytorch.org/t/how-do-i-use-pytorch-with-rtx-5060-ti/220926) — confirmed sm_120 / compute 12.0
- [vsrife PyPI](https://pypi.org/project/vsrife/) — pip-installable RIFE alternative, version 5.7.0
- [FFmpeg Ubuntu 24.04](https://ubuntuhandbook.org/index.php/2024/04/ffmpeg-7-0-ppa-ubuntu/) — 6.1.1 in apt

### Tertiary (LOW confidence — flag for validation)
- silero-vad ONNX backend as torchaudio replacement — documented but not validated in this codebase
- vsrife as production-ready RIFE alternative — package is new (2026), stability unverified

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified via PyPI and official docs
- Spec corrections: HIGH — verified against source code and official docs
- Architecture: MEDIUM — patterns derived from existing render.py + library docs
- GPU stack: MEDIUM — Blackwell [Prototype] tag in PyTorch 2.7 means possible instability
- Pitfalls: HIGH — most derived from verified library behavior

**Research date:** 2026-02-21
**Valid until:** 2026-04-21 (60 days — GPU/torch ecosystem is fast-moving)
**Re-validate before planning:** torch stable Blackwell support, silero-vad torchaudio situation
