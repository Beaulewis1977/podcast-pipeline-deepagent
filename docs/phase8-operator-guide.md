# Phase 8 Operator Guide: Intelligent Cut Quality

This guide covers all Phase 8 controls for the podcast pipeline.

Phase 8 adds two categories of improvements:

1. **Filler triage** — classifies detected filler words into disfluencies vs. hedge
   words, applies a pause-based protection gate, and optionally runs an LLM semantic
   check on hedge words before any cut is committed.
2. **Invisible cut rendering** — four optional render passes (de-breathing, noise-floor
   matching, pose matching, and RIFE AI frame interpolation) that clean up the audio and
   video quality at every splice point.

All Phase 8 features are **additive and backward compatible**: existing jobs without
Phase 8 enrichment data load and render identically to Phase 7.

---

## Table of Contents

1. [Filler Triage Configuration](#1-filler-triage-configuration)
2. [Audio Quality Passes](#2-audio-quality-passes)
3. [Video Quality Passes](#3-video-quality-passes)
4. [GPU Setup for RTX 5060 Ti](#4-gpu-setup-for-rtx-5060-ti)
5. [RIFE Installation](#5-rife-installation)
6. [GPU Smoke Test](#6-gpu-smoke-test)
7. [Troubleshooting](#7-troubleshooting)
8. [Backward Compatibility](#8-backward-compatibility)

---

## 1. Filler Triage Configuration

Configure under the `fillers:` key in `config.yaml`.

### Word Lists

```yaml
fillers:
  # Words removed automatically (no LLM review).
  disfluencies:
    - um
    - uh
    - hmm
    - er
    - ah

  # Words sent to LLM for semantic review before any cut decision.
  hedge_words:
    - like
    - you know
    - basically
    - actually
    - so

  # Your own project-specific words (categorised as disfluencies by default).
  custom_words: []

  # Backward-compat flat list.  Treated as extra disfluencies when present.
  words: []
```

**Category priority:** `hedge > custom > disfluency`.  A word that appears in both
`hedge_words` and `disfluencies` is always routed to LLM triage, not auto-removed.

### Pause-Based Protection Gate

```yaml
fillers:
  # Fillers with a preceding pause >= this value are marked protected=True.
  # Protected fillers are never removed (skipped by LLM triage too).
  protect_pause_threshold_ms: 300  # default: 300ms
```

The pause is measured as the gap between the end of the preceding word and the start of
the filler word, using raw word timestamps (before padding).

When a filler is protected, the Streamlit review card shows a lock icon and the filler
defaults to `keep` action regardless of its category.

### LLM Semantic Triage

```yaml
fillers:
  enable_llm_triage: true                  # default: true
  llm_triage_model: gemini-3-flash-lite    # default: gemini-3-flash-lite (see below)
  llm_triage_max_context_words: 5          # N words before/after the filler
```

**Supported triage models:**

| Model | Transport | Notes |
|-------|-----------|-------|
| `gemini-3-flash-lite` | `google.genai` | **Default** — fast, cheap, correct routing |
| `claude-haiku-4-5` | Anthropic | Alternative fast model |

**Forbidden (reasoning/CoT) models — DO NOT USE:**

These models are too slow and expensive for per-filler classification.  The triage
stage needs sub-second responses per batch, not deep reasoning chains.

- `o1`, `o1-mini`, `o3-mini` (OpenAI reasoning)
- `gemini-3-pro`, `gemini-3-pro-preview`, `gemini-3-pro-image-preview` (Gemini reasoning)
- Any model with a visible chain-of-thought prefix in its name

Setting `llm_triage_model` to any of the above will cause triage to run orders of
magnitude slower and cost significantly more per job.

**Transport dispatch:** Gemini model names are routed via `google.genai`.  All other
model names fall back to the OpenAI-compatible transport.  Make sure the correct API
key is configured in your `.env` (`GOOGLE_API_KEY` for Gemini models).

LLM triage runs on unprotected hedge words only.  Disfluencies and protected words
are never sent to the LLM.

**Batching:** up to 20 fillers per LLM call, separated by `---`.

**Safety default:** if the LLM call fails or `enable_llm_triage: false`, the safe
outcome is `safe_to_remove: false` (never auto-remove when uncertain).

**Triage artifact:** results are written to `jobs/<job>/analysis/filler_triage.json`.

### Editorial Actions Derived from Triage

| Condition | Default action |
|-----------|---------------|
| Explicit user decision | Overrides all rules |
| `protected: true` | `keep` |
| `category: disfluency` | `remove` |
| `triage.safe_to_remove: true` | `remove` |
| All other hedge words | `keep` (editor reviews) |

---

## 2. Audio Quality Passes

Configure under the `smoothing:` key in `config.yaml`.  These passes run after
word-boundary snapping and before the FFmpeg concat step.

### De-breathing Pass

Detects trailing breath sounds at cut boundaries and extends the cut point to swallow
them.  Requires the `gpu` optional dependency group (`silero-vad>=6.2,<7`).

```yaml
smoothing:
  de_breathing_enabled: true       # default: true
  de_breathing_window_ms: 200      # look-back window before the cut (ms)
  de_breathing_max_extend_ms: 150  # maximum extension allowed (ms)
```

When `silero-vad` is not installed, this pass silently skips (returns 0ms extension).

**Optional dep install:**

```bash
uv sync --extra gpu
```

### Noise-Floor Matching Pass

Measures the RMS noise floor at each splice join (tail of left segment, head of right
segment).  When the mismatch exceeds the threshold, injects an FFmpeg `volume` filter
to equalise levels.  Requires `librosa>=0.11,<1`.

```yaml
smoothing:
  noise_floor_match_enabled: true   # default: true
  noise_floor_match_threshold_db: 3  # minimum dB delta to trigger correction
  noise_floor_match_ramp_ms: 50      # ramp duration (ms), for documentation only
```

**Threshold semantics:** strict less-than.  A delta of exactly `threshold_db` dB
applies the correction.  A delta below the threshold does not.

When `librosa` is not installed, `measure_rms_db` returns `-120.0` (sentinel) and no
correction is applied.

---

## 3. Video Quality Passes

Configure under the `smoothing:` key in `config.yaml`.

### Pose-Match Pass

Scans a search window of frames around each content-cut join and selects the frame
pair with the minimum Farneback optical-flow magnitude — the most visually similar
pair.  Requires `opencv-python-headless>=4.13,<5`.

```yaml
smoothing:
  pose_match_enabled: true            # default: true
  pose_match_search_window_ms: 200    # search window in ms (converted to frames at 30 fps)
  pose_match_rife_threshold: 2.5      # flow magnitude below which RIFE is triggered
```

When `cv2` is not installed, `pose_distance` returns `float('inf')` and the pass
degrades to the Phase 7 xfade fallback.

Audio-only jobs skip pose matching automatically.

### RIFE AI Frame Interpolation

RIFE generates AI bridge frames between the two selected frames at each content join,
producing smoother cuts.  Disabled by default — requires a manual installation step.

```yaml
smoothing:
  rife_enabled: false         # default: false — must opt in explicitly
  rife_num_bridge_frames: 4   # desired intermediate frames (rounded to 2^exp)
  rife_script_path: ""        # absolute path to inference_img.py
  rife_fallback_to_xfade: true  # fall back to Phase 7 xfade when RIFE fails
```

**Subprocess flag:** RIFE is called with `--exp <N>` (NOT `--n` — that flag does not
exist in practical-RIFE).  `--cpu` also does not exist; for CPU-only execution set
`CUDA_VISIBLE_DEVICES=""` in the subprocess environment.

**Model:** use RIFE 4.25 (recommended default). RIFE 4.26 does exist but may produce
artifacts on some content types; 4.25 is the stable recommended version.

---

## 4. GPU Setup for RTX 5060 Ti

The RTX 5060 Ti is a **Blackwell sm_120** GPU.  It requires CUDA 12.8 (`cu128`).

**IMPORTANT:** The default `cu121` torch wheel does NOT support Blackwell GPUs and will
fail at runtime with "no kernel image for this device" errors.

### Install the correct torch wheel

```bash
# Step 1: install GPU extras (silero-vad, librosa, opencv-python-headless)
uv sync --extra gpu

# Step 2: install torch 2.10.x with cu128 (Blackwell-compatible)
uv pip install "torch==2.10.*" "torchaudio==2.10.*" --index-url https://download.pytorch.org/whl/cu128
```

### Verify GPU availability

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_capability())"
```

**Expected output for RTX 5060 Ti:**

```
True (12, 0)
```

`(12, 0)` = compute capability 12.0 = Blackwell sm_120.

---

## 5. RIFE Installation

RIFE requires cloning the practical-RIFE repository and downloading model weights
separately.  It is not a Python package.

### Clone the repository

```bash
git clone https://github.com/hzwer/ECCV2022-RIFE /opt/practical-rife
cd /opt/practical-rife
pip install -r requirements.txt
```

### Download RIFE 4.25 model weights

Download `RIFE_4.25.pkl` from the practical-RIFE releases page and place the model
files in `/opt/practical-rife/train_log/`.

### Configure the script path

```yaml
# config.yaml
smoothing:
  rife_enabled: true
  rife_script_path: /opt/practical-rife/inference_img.py
```

### Directory layout expected

```
/opt/practical-rife/
├── inference_img.py      # <-- rife_script_path points here
├── train_log/
│   ├── RIFE_4.25.pkl     # model weights
│   └── ...
└── requirements.txt
```

---

## 6. GPU Smoke Test

A standalone smoke test script verifies the full GPU + RIFE stack:

```bash
python scripts/smoke_test_gpu_rife.py
```

**Expected output (success):**

```
GPU: NVIDIA GeForce RTX 5060 Ti, capability: 12.0, CUDA: 12.8
RIFE generated 4 bridge frames in /tmp/.../rife_out
RIFE OK
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | All checks passed |
| `1` | One or more checks failed (see output for details) |

The script performs these checks in order:

1. torch + CUDA available (fails with `FAIL: CUDA not available`)
2. Compute capability >= 12.0 warning for Blackwell (warning only, does not fail)
3. opencv-python-headless available
4. RIFE script found at `rife_script_path` or `/opt/practical-rife/`
5. RIFE generates frames from two synthetic 720p test frames

---

## 7. Troubleshooting

### "FAIL: CUDA not available"

Torch was installed with the wrong CUDA index.  Reinstall with cu128:

```bash
uv pip install "torch==2.10.*" "torchaudio==2.10.*" --index-url https://download.pytorch.org/whl/cu128
```

### "RuntimeError: no kernel image is available for execution on the device"

Same cause — cu121 torch does not support Blackwell sm_120.  Use cu128 as above.

### "FAIL: RIFE script not found"

Either `smoothing.rife_script_path` is not configured, or the path doesn't exist.

```bash
# Verify the path
ls /opt/practical-rife/inference_img.py

# Or set in config.yaml:
# smoothing:
#   rife_script_path: /your/path/to/inference_img.py
```

### "FAIL: RIFE generated no frames"

Model weights are missing or the RIFE call failed silently.  Check:

```bash
ls /opt/practical-rife/train_log/
# Expects: RIFE_4.25.pkl (or similar .pkl file)
```

Also verify that torch CUDA is available (see above).

### "FAIL: opencv-python-headless not installed"

```bash
uv sync --extra gpu
# or
uv pip install "opencv-python-headless>=4.13,<5"
```

Do NOT install `opencv-python` (non-headless variant) on WSL or server environments —
it requires a display and will fail with Qt errors.

### Phase 8 features don't activate

1. Verify `uv sync --extra gpu` completed successfully.
2. Verify `config.yaml` has the relevant `enabled: true` flags under `smoothing:`.
3. Run the smoke test: `python scripts/smoke_test_gpu_rife.py`.

### "silero_vad import error"

Use `silero-vad>=6.2,<7` (NOT 5.x or 6.0/6.1).  Version 6.2+ fixes a `torchaudio`
deprecation that causes silent import failures in v5, and the `<7` upper bound prevents
unexpected breaking API changes.

```bash
uv pip install "silero-vad>=6.2,<7"
```

---

## 8. Backward Compatibility

All Phase 8 features are additive.  Existing jobs and configurations without Phase 8
data remain fully functional:

- **Legacy `filler_cuts.json`** without `category`, `protected`, `pause_before_ms`,
  `pause_after_ms` fields: loads and renders correctly.  Missing fields default to
  safe values (`category=""`, `protected=False`, pauses `0.0ms`).
- **Legacy `edit_plan.json`** without `llm_safe_to_remove`, `llm_reason`, `protected`
  fields: the Pydantic `FillerCutRange` model provides safe defaults for all
  Phase 8 fields.
- **No `filler_triage.json`**: `_load_filler_triage_map` returns `{}`.  Editorial
  actions fall back to the pre-triage heuristics.
- **GPU extras not installed**: de-breathing (`silero-vad`), noise-floor matching
  (`librosa`), and pose matching (`opencv`) all degrade gracefully to no-ops.
- **RIFE not installed**: `rife_enabled: false` (default) keeps baseline render
  behavior identical to Phase 7.  Setting `rife_fallback_to_xfade: true` (default)
  ensures the xfade transition fires even if RIFE is enabled but fails.

---

*Phase 8 — Intelligent Cut Quality*
*Completed: 2026-02-21*
