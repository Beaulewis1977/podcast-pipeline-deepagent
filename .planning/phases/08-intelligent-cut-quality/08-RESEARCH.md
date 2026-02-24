# Phase 8: Intelligent Cut Quality - Research (Refresh)

**Researched:** 2026-02-23
**Domain:** Filler-word triage + invisible cut rendering (VAD, RMS matching, optical flow, frame interpolation)
**Confidence:** HIGH (with one critical implementation correction for RIFE CLI contract)

## Summary

This refresh re-validated Phase 8 against current sources and the existing Phase 8 spec/plans (`08-01`..`08-06`). The architecture remains correct: keep semantically-aware filler triage and additive render-quality passes with strict fallback behavior. No redesign is required.

The biggest technical delta is now explicit: upstream `Practical-RIFE` `inference_img.py` does **not** accept `--output`; it writes to `./output/` relative to the process working directory. Current Phase 8 plan/code assumptions use `--output`, which can fail on real upstream scripts. This is the main blocker to eliminate before replanning.

Dependency guidance is stable but should be refreshed to current releases. As of 2026-02-23: `torch`/`torchaudio` are at `2.10.0`, `silero-vad` at `6.2.0`, `librosa` at `0.11.0`, and `opencv-python-headless` at `4.13.0.92`. The existing Phase 8 minima are still valid, but replanning should pin tested baselines and document upgrade policy.

**Primary recommendation:** Replan Phase 8 by keeping current behavior contracts, updating dependency baselines to current stable releases, and fixing the RIFE bridge contract to upstream `inference_img.py` semantics (no `--output`).

## Standard Stack

The established stack for this phase:

### Core

| Library / Tool | Version Baseline (2026-02-23) | Purpose | Why Standard |
|---|---|---|---|
| `google-genai` / `anthropic` | latest | LLM hedge-word triage calls | The existing pipeline has a provider pattern for these SDKs. |
| Triage model (`llm_triage_model`) | default `gemini-3-flash-lite` (or `claude-haiku-4-5`) | Cheap semantic keep/remove triage | Ultra-low latency, non-reasoning models perfect for structured output classification |
| `torch` | `2.10.x` | Runtime for VAD + RIFE workloads | Current stable release line; broad CUDA wheel coverage (`cu126/cu128/cu129/cu130`) |
| `torchaudio` | `2.10.x` | Audio I/O path used by Silero wrappers | Compatible with torch 2.10; migration changes finalized in torchaudio 2.10 release notes |

### Supporting

| Library / Tool | Version Baseline (2026-02-23) | Purpose | When to Use |
|---|---|---|---|
| `silero-vad` | `>=6.2,<7` | De-breathing boundary detection | Enable when `de_breathing_enabled=true` |
| `librosa` | `>=0.11,<1` | RMS delta measurement for noise-floor matching | Enable when `noise_floor_match_enabled=true` |
| `opencv-python-headless` | `>=4.13,<5` | Farneback optical-flow pose matching | Enable when `pose_match_enabled=true` |
| `Practical-RIFE` (git clone) | use upstream `main` + model `4.25` default | Bridge-frame interpolation when pose mismatch exceeds threshold | Enable when `rife_enabled=true` |
| `ffmpeg` filters (`acrossfade`, `xfade`) | modern FFmpeg with these filters present | Audio/video transition fallback and blending | Required for Phase 7/8 transition paths |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| `gemini-3-flash-lite` | `claude-haiku-4-5` | Both are explicitly designed as "lite" non-reasoning models for high-speed categorization. Keep configurable. |
| `Practical-RIFE` upstream script | `ECCV2022-RIFE` script | Similar CLI shape for `inference_img.py`; still no `--output` flag, so wrapper fix is needed either way |
| CUDA `cu128` baseline | `cu129` or `cu130` wheels | Newer runtime options exist; higher driver requirements and less conservative rollout |

**Installation (recommended baseline):**

```bash
uv sync --extra gpu
uv pip install "torch==2.10.*" "torchaudio==2.10.*" --index-url https://download.pytorch.org/whl/cu128
```

## Architecture Patterns

### Recommended Project Structure

```text
src/podcast_pipeline/
├── stages/
│   ├── transcribe.py      # category + pause/context/protection extraction
│   ├── analyze.py         # batched LLM triage + filler_triage.json
│   ├── review.py          # editorial_action derivation + compatibility fallback
│   └── render.py          # de-breathing -> noise-floor -> pose-match -> RIFE/fallback
├── utils/
│   ├── vad.py             # silero wrapper (lazy import)
│   ├── noise_match.py     # librosa RMS + correction policy
│   ├── pose_match.py      # cv2 Farneback scanner
│   └── rife_bridge.py     # subprocess wrapper; upstream-compatible CLI contract
└── models/
    ├── transcript.py      # additive Phase 8 fields on FillerCut
    └── triage.py          # triage result contracts
```

### Pattern 1: Additive Contracts + Safe Defaults

**What:** Keep Phase 8 fields additive (`category`, `pause_*`, context, protection, triage fields) and default-safe for legacy artifacts.

**When to use:** Always; this is required by Phase 8 compatibility goals.

**Example:** Legacy `filler_cuts.json` and `edit_plan.json` deserialize with defaults, not migration failures.

### Pattern 2: Optional-Dependency Boundaries with Lazy Imports

**What:** GPU/CV/audio-enhancement dependencies stay optional and are imported only when corresponding features are enabled.

**When to use:** `silero-vad`, `librosa`, `cv2`, and RIFE subprocess paths.

**Example:**

```python
# Source: Silero README + existing Phase 8 pattern
try:
    from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
except ImportError:
    return 0.0
```

### Pattern 3: Upstream-Compatible RIFE Process Wrapper

**What:** Treat `inference_img.py` as a black-box script with fixed output behavior (`./output/`) and no `--output` flag.

**When to use:** Any RIFE bridge-frame generation.

**Example:**

```python
# Source: Practical-RIFE inference_img.py argparse + output behavior
exp = frames_to_exp(num_frames)
cmd = [
    "python",
    str(script_path),
    "--img",
    str(frame_a.resolve()),
    str(frame_b.resolve()),
    "--exp",
    str(exp),
]
result = subprocess.run(cmd, cwd=str(work_dir), capture_output=True, text=True, check=False)
if result.returncode != 0:
    return []
frames = sorted((work_dir / "output").glob("img*.png"))
```

### Pattern 4: Deterministic Fallback Chain

**What:** Keep fallback ordering explicit: protection gate and parse failure defaults remain conservative (`keep` / `safe_to_remove=False`), and render falls back to Phase 7-compatible paths.

**When to use:** All uncertain paths (LLM parse errors, missing deps, RIFE failure).

### Anti-Patterns to Avoid

- **Assuming `inference_img.py` supports `--output`:** upstream script does not; this is a real compatibility trap.
- **Installing RIFE requirements directly into the main app env:** upstream `requirements.txt` pins `numpy<=1.23.5` and `opencv-python`, which can conflict with current app stack.
- **Hard-coding one CUDA index without operational policy:** choose baseline (`cu128`) and document validated alternates.
- **Treating OpenAI realtime/audio preview deprecations as text-model deprecations:** these are separate model families.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Voice activity / breath boundary detection | Custom energy-threshold VAD | `silero-vad` | Better robustness on noisy/edge-case audio with stable API wrappers |
| RMS noise-floor estimation | Custom frame-energy code | `librosa.feature.rms` | Mature, tested implementation; keyword-only API is explicit in 0.11 |
| Dense optical flow | Custom motion estimation | `cv2.calcOpticalFlowFarneback` | Production-grade algorithm + stable API |
| Frame interpolation model | Custom interpolation network | Practical-RIFE subprocess | Mature open implementation and model ecosystem |
| LLM transport/retry layer | Custom ad-hoc HTTP retries | Existing Google/Anthropic provider abstraction | Lower operational risk and clearer migration path |

**Key insight:** Phase 8 quality work should stay orchestration-focused. The value is in reliable integration, not custom ML/CV primitives.

## Common Pitfalls

### Pitfall 1: RIFE CLI Contract Drift (Critical)

**What goes wrong:** Wrapper passes `--output` to `inference_img.py`; subprocess exits with unrecognized arguments.

**Why it happens:** `--output` exists in `inference_video.py` docs, not in `inference_img.py` argparse.

**How to avoid:** Remove `--output` from image-bridge invocations; run in controlled working dir and read `./output/img*.png`.

**Warning signs:** Non-zero subprocess exit; no generated bridge frames despite valid script path and model.

### Pitfall 2: RIFE Requirements Pollute Main Environment

**What goes wrong:** Installing upstream `requirements.txt` introduces old `numpy` constraints and GUI OpenCV package mismatch.

**Why it happens:** Upstream repo requirements target broad training/demo use, not this project’s headless pipeline constraints.

**How to avoid:** Isolate RIFE environment (venv/runner) or install minimal runtime deps for script-only usage.

### Pitfall 3: CUDA Wheel / Driver Mismatch

**What goes wrong:** CUDA unavailable or runtime kernel errors.

**Why it happens:** Wrong wheel index vs local driver/GPU capability.

**How to avoid:** Use pinned tested pair (`torch==2.10.*`, `torchaudio==2.10.*`, `cu128` baseline), verify `torch.cuda.is_available()` and capability.

### Pitfall 4: OpenCV + NumPy ABI Assumptions

**What goes wrong:** Import/runtime instability when dependency resolution drifts.

**Why it happens:** `opencv-python-headless` current metadata requires `numpy>=2` for Python >=3.9.

**How to avoid:** Keep explicit GPU-extra constraints and lockfile verification in replanning tasks.

### Pitfall 5: Silero Backend Assumptions

**What goes wrong:** Audio I/O failures in environments lacking backend support.

**Why it happens:** Silero uses torchaudio I/O path unless you explicitly implement ONNX-only wrappers.

**How to avoid:** Keep torchaudio in tested GPU stack and document backend prerequisites.

### Pitfall 6: Using Heavy Reasoning Models for Triage

**What goes wrong:** Triage stage takes hours and burns API credits.

**Why it happens:** Passing a model like `o1`, `gemini-3-pro-image-preview`, or `Claude 3.5 Sonnet` into the triage config. These models possess deep reasoning steps that drastically slow down response times.

**How to avoid:** Enforce lightweight, non-reasoning ("lite" / "haiku") models for this task.

## Code Examples

### Silero VAD Boundary Detection

```python
# Source: https://github.com/snakers4/silero-vad
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps

model = load_silero_vad()
audio = read_audio("audio.wav", sampling_rate=16000)
timestamps = get_speech_timestamps(audio, model, sampling_rate=16000, return_seconds=True)
```

### librosa RMS (keyword-only API)

```python
# Source: https://github.com/librosa/librosa/blob/main/librosa/feature/spectral.py
import librosa
import numpy as np

y, sr = librosa.load("segment.wav", sr=None, mono=True)
rms = librosa.feature.rms(y=y)[0].mean()  # y is keyword-only in current API
rms_db = float(20.0 * np.log10(max(rms, 1e-9)))
```

### RIFE Frame Bridge (Upstream-Compatible)

```python
# Source: https://github.com/hzwer/Practical-RIFE/blob/main/inference_img.py
import math
import subprocess
from pathlib import Path


def frames_to_exp(n: int) -> int:
    return max(1, math.ceil(math.log2(max(n, 1))))


def generate(script: Path, frame_a: Path, frame_b: Path, work_dir: Path, n: int = 4) -> list[Path]:
    cmd = ["python", str(script), "--img", str(frame_a), str(frame_b), "--exp", str(frames_to_exp(n))]
    res = subprocess.run(cmd, cwd=str(work_dir), capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return []
    return sorted((work_dir / "output").glob("img*.png"))
```

### CUDA Wheel Baseline Check

```bash
uv pip install "torch==2.10.*" "torchaudio==2.10.*" --index-url https://download.pytorch.org/whl/cu128
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_capability())"
```

## State of the Art

| Old Assumption | Current Verified State (2026-02-23) | When Changed | Impact |
|---|---|---|---|
| `torch>=2.7` is the primary target | `torch 2.10.0` / `torchaudio 2.10.0` are current stable | 2026-01-21 | Replans should pin newer tested baseline |
| CUDA choice centered on `cu128` only | Official wheels now available for `cu126`, `cu128`, `cu129`, `cu130` for 2.10 | 2025-2026 progression | Keep conservative baseline, but document alternatives |
| `silero-vad>=6.1` correction only | Latest is `6.2.0` with edge-case improvements | 2025-11-06 | Prefer `>=6.2,<7` |
| `opencv-python-headless>=4.9` floor | Latest is `4.13.0.92`, requires `numpy>=2` on py>=3.9 | 2026-02-05 | Lockfile/test matrix must account for NumPy 2 |
| “RIFE 4.26 does not exist” | RIFE 4.26 exists; README still recommends 4.25 by default | 2024-09 onward | Docs/plans should stop claiming non-existence |
| `inference_img.py --output` usable | Upstream `inference_img.py` has no `--output`; writes to `output/` | current upstream | Critical wrapper compatibility fix needed |

**Deprecated/outdated to remove from Phase 8 replans:**

- “RIFE 4.26 does not exist”
- `inference_img.py --output` assumptions
- Guidance pinned only to torch 2.7-era stability framing

## Plan Compatibility Audit (Phase 8 Plans)

### 08-01 / 08-02 / 08-03

Status: **Compatible**

- Filler taxonomy, pause protection, contextual triage, and review wiring remain valid.
- No ecosystem blockers found for these plans.

### 08-04

Status: **Needs version refresh only**

Required replan updates:

- Raise baseline recommendations to current stable (`silero-vad 6.2`, `librosa 0.11`, `opencv-headless 4.13`, `torch/torchaudio 2.10`).
- Keep existing optional-dependency and lazy-import architecture.

### 08-05

Status: **Critical correction required**

Required replan updates:

- Replace `--output` usage in RIFE image-bridge contract.
- Add explicit subprocess working-directory output collection (`./output`).
- Add compatibility tests against real upstream CLI behavior (not only mocked subprocess args).

### 08-06

Status: **Docs + smoke-test refresh required**

Required replan updates:

- Update operator guide and smoke-test instructions to current baseline versions.
- Clarify model selection constraints: explicitly forbid reasoning/CoT models for the triage phase. Stick to `gemini-3-flash-lite` or `claude-haiku-4-5`.

## Open Questions

1. **CUDA baseline policy (`cu128` vs `cu129`) for production default**
   - What we know: all are available for torch 2.10.
   - Unclear: your fleet driver baseline and rollout tolerance.
   - Recommendation: keep `cu128` default, add documented tested override path.

2. **RIFE runtime isolation strategy**
   - What we know: upstream requirements conflict with main app constraints.
   - Unclear: whether you want one environment or isolated subprocess env.
   - Recommendation: isolate RIFE runtime to reduce dependency coupling risk.

3. **Default triage model choice**
   - What we know: `gemini-3-flash-lite` and `claude-haiku-4-5` are the optimal non-reasoning tiers.
   - Unclear: your cost/latency/quality target vs. cloud provider preference.
   - Recommendation: keep configurable; start with `gemini-3-flash-lite`, A/B against `claude-haiku-4-5`.

## Sources

### Primary (HIGH confidence)

- Context7 `/pytorch/pytorch` (versioned docs lookup)
- Context7 `/websites/librosa_doc` (`librosa.feature.rms` usage)
- https://pypi.org/pypi/torch/json
- https://pypi.org/pypi/torchaudio/json
- https://pypi.org/pypi/silero-vad/json
- https://pypi.org/pypi/librosa/json
- https://pypi.org/pypi/opencv-python-headless/json
- https://pypi.org/pypi/openai/json
- https://download.pytorch.org/whl/cu128/torch/
- https://download.pytorch.org/whl/cu129/torch/
- https://download.pytorch.org/whl/cu130/torch/
- https://pytorch.org/blog/pytorch-2.10-release/
- https://pytorch.org/blog/pytorch-2-7/
- https://github.com/hzwer/Practical-RIFE/blob/main/inference_img.py
- https://github.com/hzwer/Practical-RIFE/blob/main/README.md
- https://raw.githubusercontent.com/hzwer/Practical-RIFE/main/requirements.txt
- https://github.com/snakers4/silero-vad/releases
- https://github.com/snakers4/silero-vad/blob/master/README.md
- https://github.com/librosa/librosa/blob/main/librosa/feature/spectral.py
- https://ffmpeg.org/ffmpeg-filters.html
- https://developers.openai.com/api/docs/deprecations/
- https://api.openai.com/v1/models (runtime-validated with configured API key)

### Secondary (MEDIUM confidence)

- https://pytorch.org/get-started/previous-versions/
- Perplexity discovery search for ecosystem drift and source triangulation

### Tertiary (LOW confidence)

- None used for authoritative claims in this refresh.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — verified with official package registries and upstream repos
- Architecture patterns: **MEDIUM** — strong evidence, but environment-specific runtime behavior must still be validated in your deployment environment
- Plan deltas/blockers: **HIGH** — directly verified against current spec/plans and upstream script contracts

**Research date:** 2026-02-23
**Valid until:** 2026-03-23 (30 days; GPU/runtime ecosystem is fast-moving)
