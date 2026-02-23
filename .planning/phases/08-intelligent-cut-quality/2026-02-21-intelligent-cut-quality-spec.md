# Phase 8: Intelligent Cut Quality — Context-Aware Filler Control & Invisible Edit Rendering

**Created:** 2026-02-21
**Author:** Engineering (Antigravity)
**Phase Slug:** `08-intelligent-cut-quality`
**Depends on:** Phase 7 (Smooth Editing & Filler Word Control)
**Status:** Spec — awaiting implementation

---

## 1. Problem Statement

Phase 7 delivered the infrastructure for smooth cuts (word-boundary snapping, micro-fade, acrossfade, xfade) and per-filler editorial decisions. However, two real-production gaps remain:

### Gap A — Filler categorisation is not automatic

The `FillerConfig.words` flat list treats `"um"` (a pure disfluency, nearly always removable) identically to `"like"` (a hedge word that is sometimes load-bearing). The transcribe stage writes `FillerCut` objects with no `category` field. Downstream, `FillerCutRange.category` always defaults to `""`, so the UI's category grouping is inert and every filler is implicitly auto-removed.

**Real-world harm:** Fillers around long dramatic pauses, or fillers used rhetorically ("I thought — like — isn't that wild?"), get auto-removed as aggressively as pure noise, degrading delivery and meaning.

### Gap B — Jump cuts are still visually perceptible

Even with a 300ms `xfade` dissolve, if the speaker moves between the left and right segment frames, the blend is physically wrong: you see the speaker teleport through the transition rather than smoothly land. Additionally, audio cuts at breath-sound edges remain subtly audible to trained listeners even after `acrossfade`.

**Real-world harm:** Content looks and sounds like it was edited, reducing authenticity and audience trust.

---

## 2. Phase 8 Goals

Deliver two first-class upgrades, each independently usable:

### Goal 1 — Intelligent Filler Triage

Auto-categorise every detected filler using rule-based signals and an optional LLM semantic check so:
- **Pure disfluencies** (`um`, `uh`, `hmm`, `er`, `ah`) that are surrounded by short pauses → auto-remove.
- **Hedge words / discourse markers** (`like`, `you know`, `basically`, `actually`, `so`) → default to review, with the LLM deciding safe-to-remove vs. rhetorically meaningful.
- **Any filler adjacent to a long deliberate pause** (≥ 300 ms) → protect, flag for human review.

### Goal 2 — Invisible Cut Rendering

Make every edit point undetectable:
1. **De-breathing** at cut boundaries (remove breath sounds that expose the join).
2. **Audio prosody / noise-floor matching** so the splice doesn't produce an audible room-tone bump.
3. **Cut-point pose matching** — pick the video frame where the speaker's pose best matches across the join before applying any dissolve, so the blend is physically continuous.
4. **AI frame interpolation (RIFE)** — generate synthetic bridge frames between cut endpoints, eliminating visible motion jumps entirely.

---

## 3. Background: Why These Signals Matter

### 3.1 Filler taxonomy

| Category | Examples | Default intent | Notable exception |
|---|---|---|---|
| **Disfluency** | `um`, `uh`, `hmm`, `er`, `ah` | Remove | If preceded by a 300ms+ pause (dramatic hesitation) |
| **Hedge / discourse** | `like`, `you know`, `basically`, `actually`, `so` | Review | When used factually ("I actually believe…") vs. as tic |
| **Custom** | Operator-defined per show | Configurable | Inherited from operator config |

### 3.2 Pause-duration semantics

| Pause before/after filler | Meaning | Action |
|---|---|---|
| < 150 ms | Normal connected speech | Safe to remove |
| 150–300 ms | Slight hesitation | Remove disfluency, review hedge |
| 300–600 ms | Deliberate thought pause | Protect — keep filler + pause |
| > 600 ms | Dramatic beat | Always protect — the silence IS the content |

### 3.3 Why crossfade alone isn't enough for video

`xfade=fade` blends pixel values between frame A and frame B linearly. If the speaker's head has moved 15° between the two frames, the blend produces ghosting — the viewer subconsciously notices the transparency artifact even at 300ms. The professional solution is:

1. **Pose-match selection** — scan ±200ms around the cut point for the frame pair with minimum optical flow distance.
2. **RIFE interpolation** — when pose-match isn't tight enough (Δ > threshold), generate 4–8 physically-plausible bridge frames using neural optical flow.

---

## 4. Technical Architecture

### 4.1 Layer Map

```text
┌─────────────────────────────────────────────────────────────────────┐
│  TRANSCRIBE STAGE                                                    │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │ _detect_     │───▶│ FillerCut (+ category + pause_before_ms  │  │
│  │  fillers()   │    │            + pause_after_ms + context)   │  │
│  └──────────────┘    └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
             │ filler_cuts.json (enriched)
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ANALYZE STAGE (new: semantic check sub-stage)                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ _triage_fillers()  →  LLM call per hedge filler            │   │
│  │   Input: word + 5-word context before/after                │   │
│  │   Output: safe_to_remove (bool) + reason (str)             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  Writes: analysis/filler_triage.json                                │
└──────────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  REVIEW STAGE                                                        │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  FillerCutRange.category  populated from FillerCut           │  │
│  │  FillerCutRange.default_action  set from triage result       │  │
│  │  UI groups by category; LLM-flagged hedges shown in review   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  RENDER STAGE (new: invisible-cut engine)                            │
│  ┌───────────────────────────────────┐  ┌───────────────────────┐  │
│  │  1. De-breathing detector         │  │  3. Pose-match scan   │  │
│  │     (silero-vad)                  │  │     (opencv-python)   │  │
│  │  2. Noise-floor match             │  │  4. RIFE bridge gen.  │  │
│  │     (librosa RMS δ)               │  │     (practical-RIFE)  │  │
│  └───────────────────────────────────┘  └───────────────────────┘  │
│  Policy: run (1)+(2) always; (3)+(4) when pose Δ > threshold        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. Gap A: Intelligent Filler Triage

### 5.1 FillerConfig restructure

**File:** `src/podcast_pipeline/config/settings.py`

Replace the flat `words` list with typed sub-lists while keeping `words` as a backward-compatible fallback treated as additional disfluencies:

```python
class FillerConfig(BaseModel):
    """Filler word detection and triage configuration."""

    # Categorised word lists
    disfluencies: list[str] = Field(
        default_factory=lambda: ["um", "uh", "hmm", "er", "ah"]
    )
    hedge_words: list[str] = Field(
        default_factory=lambda: ["like", "you know", "basically", "actually", "so"]
    )
    custom_words: list[str] = Field(default_factory=list)

    # Backward-compat flat list — treated as extra disfluencies
    words: list[str] = Field(default_factory=list)

    # Detection thresholds
    min_confidence: float = 0.5
    min_duration_ms: int = 150
    padding_ms: int = 50

    # Pause-based protection gate
    protect_pause_threshold_ms: float = Field(default=300.0, ge=0.0)

    # LLM semantic triage (hedge words only)
    enable_llm_triage: bool = True
    llm_triage_model: str = "gemini-3-flash-lite"   # cheap + fast; overridable (or claude-haiku-4-5)
    llm_triage_max_context_words: int = 5    # words before/after to include
```

**config.yaml** additions:
```yaml
fillers:
  disfluencies: ["um", "uh", "hmm", "er", "ah"]
  hedge_words: ["like", "you know", "basically", "actually", "so"]
  custom_words: []
  min_confidence: 0.5
  min_duration_ms: 150
  padding_ms: 50
  protect_pause_threshold_ms: 300
  enable_llm_triage: true
  llm_triage_model: "gemini-3-flash-lite"
  llm_triage_max_context_words: 5
```

### 5.2 FillerCut model enrichment

**File:** `src/podcast_pipeline/models/transcript.py`

Add fields that the transcribe stage will now populate:

```python
class FillerCut(BaseModel):
    """A detected filler word to potentially remove."""

    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    word: str
    confidence: float = Field(ge=0.0, le=1.0)

    # Phase 8 additions — all optional/defaulted for backward compat
    category: Literal["disfluency", "hedge", "custom"] = "disfluency"
    pause_before_ms: float = 0.0   # silence gap preceding this filler
    pause_after_ms: float = 0.0    # silence gap following this filler
    context_before: str = ""       # N words before the filler
    context_after: str = ""        # N words after the filler
    protected: bool = False        # True when pause gate fired
```

### 5.3 _detect_fillers() upgrade

**File:** `src/podcast_pipeline/stages/transcribe.py`

The existing detection loop already iterates over transcript words. Add:

1. **Category lookup** — build three sets from config: `disfluency_set`, `hedge_set`, `custom_set`.
2. **Pause measurement** — use adjacent word timings to compute `pause_before_ms` and `pause_after_ms`.
3. **Context extraction** — slice up to N words before and after from the segment word list.
4. **Pause gate** — if either pause exceeds `protect_pause_threshold_ms`, set `protected=True`.

```python
# Pseudocode — see implementation plan for exact code

disfluency_set  = {normalize(w) for w in config.fillers.disfluencies}
hedge_set       = {normalize(w) for w in config.fillers.hedge_words}
custom_set      = {normalize(w) for w in config.fillers.custom_words}
# backward compat
disfluency_set |= {normalize(w) for w in config.fillers.words}

# In detection loop, for each matched filler word at index i:
prev_word = words[i - 1] if i > 0 else None
next_word = words[i + 1] if i + 1 < len(words) else None

pause_before_ms = (word.start - prev_word.end) * 1000 if prev_word else 0.0
pause_after_ms  = (next_word.start - word.end) * 1000 if next_word else 0.0

context_before = " ".join(
    w.word for w in words[max(0, i - N):i]
)
context_after = " ".join(
    w.word for w in words[i + 1:i + N + 1]
)

if word_text in hedge_set:
    category = "hedge"
elif word_text in custom_set:
    category = "custom"
else:
    category = "disfluency"

protected = (
    pause_before_ms >= config.fillers.protect_pause_threshold_ms
    or pause_after_ms >= config.fillers.protect_pause_threshold_ms
)

filler_cuts.append(FillerCut(
    start=start, end=end, word=word.word, confidence=word.confidence,
    category=category,
    pause_before_ms=pause_before_ms,
    pause_after_ms=pause_after_ms,
    context_before=context_before,
    context_after=context_after,
    protected=protected,
))
```

### 5.4 LLM semantic triage sub-stage

**File:** `src/podcast_pipeline/stages/analyze.py` (new helper: `_triage_fillers`)

After detection, for every hedge filler that is **not** already `protected`, call the LLM with a compact prompt:

```text
SYSTEM: You are an audio editor deciding whether a filler word can be safely removed.
USER:
Transcript excerpt: "{context_before} [{FILLER}] {context_after}"
Filler word: "{word}"
Pause before: {pause_before_ms:.0f}ms  Pause after: {pause_after_ms:.0f}ms

Can this filler be SAFELY removed without changing the meaning, tone, or rhetorical
intent of the sentence? Removing it is safe if it is purely a verbal tick with no
expressive or semantic function.

Reply with exactly:
SAFE or REVIEW
reason: <one sentence>
```

- Calls are **batched** (max 20 per LLM call using the existing provider infrastructure) to minimise latency.
- Response is parsed into `FillerTriage` objects and written to `analysis/filler_triage.json`.
- Cost estimate: ~$0.001 per 20 fillers at gemini-3-flash-lite pricing.
- Disabled when `enable_llm_triage: false` — triage defaults to `REVIEW` for all hedges.

```python
# Output artifact schema
class FillerTriage(BaseModel):
    filler_index: int
    word: str
    category: str
    safe_to_remove: bool         # True = SAFE, False = REVIEW
    reason: str
    llm_model: str
    triaged_at: str              # ISO timestamp
```

### 5.5 Review stage: populate FillerCutRange from enriched data

**File:** `src/podcast_pipeline/stages/review.py`

When building `FillerCutRange` list from `filler_cuts.json` + `filler_triage.json`:

```python
# For each filler_cut:
triage = triage_map.get(idx)

# default_action logic:
if filler_cut.protected:
    default_action = "keep"        # pause gate fired
elif filler_cut.category == "disfluency":
    default_action = "remove"      # pure noise
elif triage and triage.safe_to_remove:
    default_action = "remove"      # LLM cleared it
else:
    default_action = "review"      # hedge or LLM uncertain

FillerCutRange(
    ...
    category=filler_cut.category,
    context_before=filler_cut.context_before,
    context_after=filler_cut.context_after,
    editorial_action=default_action,
    editorial_note=triage.reason if triage else "",
    ...
)
```

### 5.6 UI enrichment

**File:** `src/podcast_pipeline/ui/app.py`

The existing category-grouped UI already handles `category` grouping. New additions:

- Show `context_before … [FILLER] … context_after` inline under each filler chip.
- Show `pause_before` / `pause_after` badges (e.g. `||300ms||`) so editors understand why something is flagged.
- Show LLM `reason` as a tooltip or collapsed detail.
- Protected fillers show a 🔒 badge and default to `"keep"` with an override option.

---

## 6. Gap B: Invisible Cut Rendering

### 6.1 De-breathing at cut points

**Mechanism:** Voice Activity Detection (VAD) is used to classify every 10ms frame around a cut point. Breath sounds fall in the non-speech class with a characteristic energy envelope. If a breath is detected in the 0–200ms window immediately preceding the cut-out point or following the return point, the trim is extended to swallow it.

**Package:** `silero-vad 5.x` — ultra-lightweight, runs on CPU in < 1ms/frame, no GPU required.

```python
# pip install silero-vad
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps

model = load_silero_vad()

# For each cut boundary (e.g. cut ends at t=10.250):
audio = read_audio("audio.wav", sampling_rate=16000)
timestamps = get_speech_timestamps(audio, model, sampling_rate=16000)

# Scan 200ms window before cut-out for trailing non-speech
# If found, extend end of cut by breath_duration_s
```

**Config additions:**
```yaml
smoothing:
  de_breathing_enabled: true
  de_breathing_window_ms: 200     # scan window before/after boundary
  de_breathing_max_extend_ms: 150 # maximum extension to swallow a breath
```

**Render integration:** Runs inside `_apply_word_boundary_snapping()` as a second pass — after boundary snapping, before keep-range inversion.

### 6.2 Noise-floor matching

**Mechanism:** Very short mismatch in room ambience between adjacent kept segments creates a subtle but perceptible bump at the join. This is independent of the crossfade — it's the *level* of background noise, not the waveform.

**Detection:** Compare the RMS energy of the 100ms window *just before the cut-out point* with the 100ms window *just after the cut-in point*. If they differ by more than a configurable threshold (default: 3dB), apply a short gain ramp (50ms) to one segment to match.

**Package:** `librosa` — already a natural dependency, used for audio analysis throughout the ecosystem.

```python
# pip install librosa
import librosa
import numpy as np

y_left, sr = librosa.load("segment_left.wav", sr=None)
y_right, _  = librosa.load("segment_right.wav", sr=None)

rms_left  = librosa.feature.rms(y=y_left[-int(sr * 0.1):])[0].mean()
rms_right = librosa.feature.rms(y=y_right[:int(sr * 0.1)])[0].mean()

delta_db = 20 * np.log10(rms_left / (rms_right + 1e-9))
if abs(delta_db) > config.smoothing.noise_floor_match_threshold_db:
    # Apply a 50ms gain ramp in FFmpeg using `volume` filter with eval=frame
```

**Config additions:**
```yaml
smoothing:
  noise_floor_match_enabled: true
  noise_floor_match_threshold_db: 3.0
  noise_floor_match_ramp_ms: 50
```

### 6.3 Cut-point pose matching (choose the best frame pair)

**Mechanism:** Instead of always cutting at exactly the word-boundary snap point, scan a ±200ms window around the snap point in both the left and right segments to find the frame pair where the speaker's *pose* (head orientation + body position) is most similar. The join then happens at those two frames, making the subsequent dissolve or hard cut physically continuous.

**Package:** `opencv-python` — standard computer vision package.

```python
# pip install opencv-python
import cv2
import numpy as np

def pose_distance(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """Optical flow magnitude between two frames in a region of interest (speaker head/torso)."""
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        gray_a, gray_b, None,
        pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2, flags=0
    )
    magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    return float(magnitude.mean())

# Scan left_frames[-search_n:] × right_frames[:search_n] for minimum pose_distance
# Use the pair (best_left_idx, best_right_idx) as the actual cut point
```

**Policy:**
- Default search window: ±200ms (configurable: `pose_match_search_window_ms`).
- Maximum allowed pose shift before triggering RIFE: `pose_match_rife_threshold` (default: 2.5 magnitude units).
- If the best pair found still exceeds threshold → pass to RIFE.
- Disabled when `pose_match_enabled: false` (e.g. audio-only workflows).

**Config additions:**
```yaml
smoothing:
  pose_match_enabled: true
  pose_match_search_window_ms: 200
  pose_match_rife_threshold: 2.5   # optical flow magnitude; higher = more tolerant
```

### 6.4 AI Frame Interpolation (RIFE)

**Mechanism:** When the pose-match score between the two best frames exceeds the threshold, RIFE generates 4–8 synthetic bridge frames using a trained neural optical-flow model. These bridge frames are spliced between the left and right segments, producing physically continuous motion through the cut.

**Model:** `practical-RIFE` (hzwer/Practical-RIFE) — the leading open-source frame interpolation model, supports GPU acceleration.

**GPU:** Your NVIDIA RTX 5060 Ti 16GB is ideal. RIFE runs in < 50ms per frame pair on a mid-range GPU.

```python
# Installation (see Section 9 for full setup)
# RIFE is loaded as a subprocess call into the render pipeline
# to avoid making torch a hard dependency of the main package.
# A thin wrapper `src/podcast_pipeline/utils/rife_bridge.py` handles this.

class RifeBridge:
    """Subprocess wrapper for RIFE frame interpolation."""

    def generate_bridge_frames(
        self,
        frame_a_path: Path,
        frame_b_path: Path,
        output_dir: Path,
        num_frames: int = 4,
        *,
        gpu: bool = True,
    ) -> list[Path]:
        """Call practical-RIFE CLI and return list of generated frame paths."""
        cmd = [
            "python", str(RIFE_INFERENCE_SCRIPT),
            "--img", str(frame_a_path), str(frame_b_path),
            "--output", str(output_dir),
            "--n", str(num_frames),
        ]
        if not gpu:
            cmd += ["--cpu"]
        subprocess.run(cmd, check=True, capture_output=True)
        return sorted(output_dir.glob("*.png"))
```

**Render integration:**

```text
For each content-join point:
1. Extract last N frames of left segment → frame_L*.png  (ffmpeg -frames:v N)
2. Extract first N frames of right segment → frame_R*.png
3. pose_match_scan() → pick best (frame_A, frame_B) pair
4. If pose_distance(frame_A, frame_B) > threshold:
     bridge_frames = rife_bridge.generate_bridge_frames(frame_A, frame_B, n=4)
     FFmpeg: [left_trimmed] + [bridge_video] + [right_trimmed]  (concat demuxer)
   Else:
     Normal xfade dissolve (Phase 7 path)
```

**Config additions:**
```yaml
smoothing:
  rife_enabled: true
  rife_num_bridge_frames: 4         # 4 = ~133ms at 30fps; 8 = ~267ms
  rife_gpu: true                    # false for CPU fallback
  rife_script_path: ""              # auto-detected if practical-RIFE is on PATH
  rife_fallback_to_xfade: true      # if RIFE fails, fall back to Phase 7 xfade
```

---

## 7. Model and Schema Changes Summary

### 7.1 `FillerCut` (transcript model) — additive

| Field | Type | Default | Description |
|---|---|---|---|
| `category` | `Literal["disfluency","hedge","custom"]` | `"disfluency"` | Assigned by detection |
| `pause_before_ms` | `float` | `0.0` | Silence gap before the filler starts |
| `pause_after_ms` | `float` | `0.0` | Silence gap after the filler ends |
| `context_before` | `str` | `""` | N words preceding the filler |
| `context_after` | `str` | `""` | N words following the filler |
| `protected` | `bool` | `False` | Pause gate fired — do not auto-remove |

### 7.2 `FillerTriage` (new analysis artifact model)

| Field | Type | Description |
|---|---|---|
| `filler_index` | `int` | Index in `filler_cuts.json` |
| `word` | `str` | The filler word |
| `category` | `str` | Inherited from FillerCut |
| `safe_to_remove` | `bool` | LLM verdict |
| `reason` | `str` | One-sentence explanation |
| `llm_model` | `str` | Model used for the call |
| `triaged_at` | `str` | ISO timestamp |

### 7.3 `FillerCutRange` (edit-plan model) — additive

| New Field | Type | Default | Description |
|---|---|---|---|
| `protected` | `bool` | `False` | Inherited from FillerCut |
| `pause_before_ms` | `float` | `0.0` | Surfaced in UI for editor awareness |
| `pause_after_ms` | `float` | `0.0` | Same |
| `llm_safe_to_remove` | `bool \| None` | `None` | LLM verdict (None = not triaged) |
| `llm_reason` | `str` | `""` | LLM explanation |

### 7.4 `SmoothingConfig` (settings model) — additive

New fields to be added:

```python
class SmoothingConfig(BaseModel):
    # Existing Phase 7 fields...

    # Phase 8: De-breathing
    de_breathing_enabled: bool = True
    de_breathing_window_ms: float = Field(default=200.0, ge=0.0, le=500.0)
    de_breathing_max_extend_ms: float = Field(default=150.0, ge=0.0, le=300.0)

    # Phase 8: Noise-floor matching
    noise_floor_match_enabled: bool = True
    noise_floor_match_threshold_db: float = Field(default=3.0, ge=0.0, le=20.0)
    noise_floor_match_ramp_ms: float = Field(default=50.0, ge=0.0, le=200.0)

    # Phase 8: Pose matching
    pose_match_enabled: bool = True
    pose_match_search_window_ms: float = Field(default=200.0, ge=0.0, le=500.0)
    pose_match_rife_threshold: float = Field(default=2.5, gt=0.0)

    # Phase 8: RIFE
    rife_enabled: bool = True
    rife_num_bridge_frames: int = Field(default=4, ge=1, le=16)
    rife_gpu: bool = True
    rife_script_path: str = ""   # auto-detect if empty
    rife_fallback_to_xfade: bool = True
```

---

## 8. New Files to Create

| File | Purpose |
|---|---|
| `src/podcast_pipeline/utils/vad.py` | Silero-VAD wrapper for breath detection |
| `src/podcast_pipeline/utils/rife_bridge.py` | RIFE subprocess wrapper |
| `src/podcast_pipeline/utils/pose_match.py` | OpenCV optical-flow pose distance + scan |
| `src/podcast_pipeline/utils/noise_match.py` | Librosa RMS delta + FFmpeg gain-ramp builder |
| `src/podcast_pipeline/models/triage.py` | `FillerTriage` Pydantic model |
| `tests/test_vad.py` | Breath detection unit + edge-case tests |
| `tests/test_rife_bridge.py` | RIFE subprocess call tests (with mocked subprocess) |
| `tests/test_pose_match.py` | Pose-scan and threshold tests |
| `tests/test_noise_match.py` | RMS delta tests |
| `tests/test_triage.py` | LLM triage model round-trip + prompt format tests |

---

## 9. Dependencies & Installation

### 9.1 System dependencies (must be installed once)

```bash
# CUDA Toolkit (for RTX 5060 Ti — CUDA 12.x)
# If not already present:
wget https://developer.download.nvidia.com/compute/cuda/12.6.0/local_installers/cuda_12.6.0_560.28.03_linux.run
sudo sh cuda_12.6.0_560.28.03_linux.run --toolkit --silent

# Verify GPU is visible
nvidia-smi
nvcc --version   # should show 12.x

# FFmpeg (if not at version >= 6.0)
# Ubuntu/Debian:
sudo apt install ffmpeg
ffmpeg -version   # must show >= 6.0 for all Phase 7/8 filters

# Python build deps for torch (if building from source — usually not needed)
sudo apt install python3-dev build-essential libssl-dev
```

### 9.2 Python package additions

Add to `pyproject.toml` / `uv.lock`:

```toml
[project.dependencies]
# Existing deps...

# Phase 8 additions
silero-vad = ">=5.0"           # breath/VAD detection — CPU only, tiny model
librosa = ">=0.10"             # audio analysis (noise-floor RMS measurement)
opencv-python = ">=4.9"        # pose-match optical flow
torch = ">=2.3"                # PyTorch for RIFE (GPU path uses CUDA)
torchvision = ">=0.18"         # required by RIFE
numpy = ">=1.26"               # already present, minimum version pin
soundfile = ">=0.12"           # audio I/O for librosa/silero
```

Install command:
```bash
uv add silero-vad librosa opencv-python "torch>=2.3" torchvision soundfile
```

For GPU-accelerated PyTorch (RTX 5060 Ti, CUDA 12.x):
```bash
# Uninstall CPU torch first if already installed, then:
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### 9.3 practical-RIFE setup

RIFE is not distributed as a pip package with pre-trained weights. Setup is done once:

```bash
# Clone the reference implementation
git clone https://github.com/hzwer/Practical-RIFE.git /opt/practical-rife
cd /opt/practical-rife

# Install Python deps (uses its own requirements)
pip install -r requirements.txt

# Download pre-trained model weights (RIFE 4.26 as of 2025)
# Weights are hosted on Google Drive — use gdown:
pip install gdown
gdown --folder https://drive.google.com/drive/folders/1tqs6wczjbDdKJSMgg26JkqWDJ_fVFQSN -O train_log
# Or download from HuggingFace mirror:
# huggingface-cli download hzwer/RIFE train_log/

# Verify GPU inference works
python inference_video.py --img test_frames/ --output test_out/ --n 4
# Should complete in < 200ms on RTX 5060 Ti
```

Set the path in `config.yaml`:
```yaml
smoothing:
  rife_script_path: "/opt/practical-rife/inference_img.py"
  rife_gpu: true
```

### 9.4 Silero-VAD model (auto-downloads on first use)

```python
# First run downloads ~2MB model to ~/.cache/torch/
from silero_vad import load_silero_vad
model = load_silero_vad()  # downloads once, then cached
```

No additional setup required. Works on CPU only — no GPU needed for VAD.

### 9.5 Verification commands

After installation, verify the full stack:

```bash
# PyTorch + CUDA
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# Expected: True  NVIDIA GeForce RTX 5060 Ti

# RIFE end-to-end
uv run python -c "
import subprocess
result = subprocess.run(
    ['python', '/opt/practical-rife/inference_img.py', '--help'],
    capture_output=True, text=True
)
print('RIFE OK' if result.returncode == 0 else result.stderr)
"

# Silero-VAD
uv run python -c "from silero_vad import load_silero_vad; m = load_silero_vad(); print('VAD OK')"

# OpenCV GPU info
uv run python -c "import cv2; print(cv2.getBuildInformation())" | grep -i cuda

# Librosa
uv run python -c "import librosa; print('librosa', librosa.__version__)"
```

---

## 10. Test Plan

### 10.1 Unit tests (offline, no GPU required)

| Test | File | What it verifies |
|---|---|---|
| Filler category assignment | `tests/test_transcribe.py` | disfluency/hedge/custom sets; pause gate fires at ≥300ms |
| Pause gate protection | `tests/test_transcribe.py` | `protected=True` when pause_before ≥ threshold |
| Context extraction | `tests/test_transcribe.py` | Correct N-word window from segment word list |
| FillerCut backward compat | `tests/test_models.py` | Old `filler_cuts.json` without category loads as default disfluency |
| FillerTriage round-trip | `tests/test_triage.py` | Model serialises/deserialises; `safe_to_remove` values preserved |
| LLM triage prompt format | `tests/test_triage.py` | Prompt contains context_before, FILLER, context_after, pause values |
| LLM triage batch | `tests/test_triage.py` | 20+ fillers batched into one call; returns one result per input |
| LLM triage disabled | `tests/test_triage.py` | `enable_llm_triage=false` → all hedges get `safe_to_remove=False`, no LLM call |
| VAD breath detection | `tests/test_vad.py` | Synthetic breath waveform classified as non-speech |
| VAD no breath | `tests/test_vad.py` | Clean speech window returns no extension |
| VAD edge: silence | `tests/test_vad.py` | Full-silence window handled without exceptions |
| Noise-floor delta calc | `tests/test_noise_match.py` | Known RMS ratio → correct dB delta |
| Noise-floor below threshold | `tests/test_noise_match.py` | No gain ramp emitted when delta < 3dB |
| Pose distance deterministic | `tests/test_pose_match.py` | Same frame pair → identical score |
| Pose scan returns best pair | `tests/test_pose_match.py` | Minimum-distance pair selected from window |
| RIFE bridge (mocked) | `tests/test_rife_bridge.py` | Subprocess called with correct args; output paths returned |
| RIFE disabled | `tests/test_rife_bridge.py` | Falls back to xfade when `rife_enabled=false` |
| RIFE subprocess failure | `tests/test_rife_bridge.py` | `RuntimeError` raised when CRC fails + fallback fires if configured |

### 10.2 Integration tests

| Test | File | What it verifies |
|---|---|---|
| Filler triage flows into `FillerCutRange.default_action` | `tests/test_review.py` | Protected → keep; disfluency → remove; LLM SAFE hedge → remove; LLM REVIEW hedge → review |
| UI shows context/pause badges | `tests/test_ui_app.py` | Decision map includes `context_before`, `pause_before_ms` for each filler |
| Edit plan holds enriched FillerCutRange | `tests/test_pipeline.py` | `category`, `protected`, `llm_safe_to_remove` in serialised edit plan |
| De-breathing extends cut boundary | `tests/test_render.py` | Cut range extended by breath duration when VAD detects breath |
| Noise-floor match fires above threshold | `tests/test_render.py` | Gain ramp filter injected when RMS delta > 3dB |
| Pose-match selects shorter-distance pair | `tests/test_render.py` | Join frame pair differs from raw snap point |
| RIFE toggled by pose score | `tests/test_render.py` | RIFE called when pose distance > threshold; xfade used otherwise |
| Full pipeline with RIFE mocked | `tests/test_pipeline.py` | End-to-end review→render with RIFE subprocess mocked succeeds |
| Legacy `filler_cuts.json` (no category field) loads cleanly | `tests/test_pipeline.py` | Old artifacts treated as all-disfluency, no crash |

### 10.3 GPU smoke test (manual, requires RTX hardware)

```bash
# Run once on real hardware after RIFE setup to confirm GPU path
uv run python -c "
from src.podcast_pipeline.utils.rife_bridge import RifeBridge
from pathlib import Path
import cv2, numpy as np

# Generate two synthetic frames
a = (np.random.rand(720, 1280, 3) * 255).astype(np.uint8)
b = (np.random.rand(720, 1280, 3) * 255).astype(np.uint8)
cv2.imwrite('/tmp/frame_a.png', a)
cv2.imwrite('/tmp/frame_b.png', b)

bridge = RifeBridge(script_path='/opt/practical-rife/inference_img.py', gpu=True)
frames = bridge.generate_bridge_frames(
    Path('/tmp/frame_a.png'), Path('/tmp/frame_b.png'),
    Path('/tmp/rife_out'), num_frames=4
)
print(f'RIFE GPU OK: generated {len(frames)} bridge frames')
"
```

---

## 11. Execution Waves

| Wave | Plans | Parallel? | Rationale |
|---|---|---|---|
| **Wave 1** | `08-01` | — | Foundation: FillerConfig + FillerCut enrichment in transcribe, backward compat tests |
| **Wave 1** | `08-02` | ✅ with 08-01 | LLM triage sub-stage in analyze + FillerTriage model |
| **Wave 2** | `08-03` | — (after Wave 1) | Review + UI: wire triage results into FillerCutRange + edit plan; UI context/badge display |
| **Wave 3** | `08-04` | — (after Wave 2) | Render: de-breathing (VAD) + noise-floor matching (librosa) |
| **Wave 3** | `08-05` | ✅ with 08-04 | Render: pose-match (OpenCV) + RIFE bridge frames |
| **Wave 4** | `08-06` | — (after Wave 3) | Integration hardening: end-to-end tests, GPU smoke, operator docs, README update |

---

## 12. Backward Compatibility Guarantees

| Existing artifact | Behavior after Phase 8 |
|---|---|
| `filler_cuts.json` without `category` field | Loaded as all-disfluency; `protected=False` |
| `filler_cuts.json` without pause fields | Pause defaults to 0.0; pause gate does not fire |
| `edit_plan.json` without enriched FillerCutRange fields | All new fields have safe defaults; models load fine |
| Jobs with `rife_enabled: false` in config | RIFE path skipped; Phase 7 xfade used |
| Jobs with `pose_match_enabled: false` | Pose scan skipped; snap point used directly |
| Audio-only jobs (no video stream) | `pose_match_enabled` auto-disabled at render start |
| Jobs with `de_breathing_enabled: false` | VAD scan skipped; cut range unchanged |

---

## 13. Out of Scope for Phase 8

The following are explicitly **deferred** to a follow-on phase:

- **B-roll coverage** — cutting to a second camera angle or stock footage to cover edits. Requires a B-roll library integration.
- **Spectral morphing** across cut points (beyond RMS matching) — requires `pedalboard` convolution reverb estimation.
- **Automatic LLM-driven content cut identification** — Phase 8 covers filler triage only; content cuts remain human-driven.
- **Real-time preview** of cut points in the Streamlit UI — audio preview latency is outside the MVP scope of this phase.
- **RIFE model fine-tuning** on talking-head video — the pre-trained model is used as-is.
- **Multi-speaker pose matching** — Phase 8 assumes a single primary speaker in frame.

---

## 14. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| LLM triage adds latency to analyze stage | Medium | Batch calls (max 20/call); disable with `enable_llm_triage: false`; triage runs async after main analysis |
| RIFE `practical-RIFE` CLI changes between versions | Medium | Pin the commit hash in setup docs; subprocess wrapper catches non-zero exit codes |
| CUDA version mismatch between torch and driver | High | Verify with `nvcc --version` + `nvidia-smi` before uv install; document exact CUDA 12.x path |
| OpenCV GPU build not available in standard pip package | Low | Use `opencv-python` CPU build — optical flow runs on CPU, fast enough (< 50ms/frame) |
| RIFE on RTX 5060 Ti (Ada Lovelace) — driver compatibility | Low | RTX 5060 Ti uses CUDA 12.x compute capability 8.9; all torch 2.3+ wheels support this |
| silero-vad incorrect breath classification (false positive) | Medium | `de_breathing_max_extend_ms` cap (150ms default) limits over-trimming; configurable |
| Pose-match scan window extends past segment boundary | Low | Clamp search to `min(search_window_ms, segment_duration_ms / 2)` |

---

*Spec written: 2026-02-21*
*Author: Antigravity / Engineering*
*Phase: 08-intelligent-cut-quality*
