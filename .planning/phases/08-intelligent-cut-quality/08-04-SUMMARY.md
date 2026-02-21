---
phase: 08-intelligent-cut-quality
plan: 04
subsystem: audio-processing
tags: [vad, silero-vad, librosa, noise-floor, de-breathing, render, optional-deps, gpu]

# Dependency graph
requires:
  - phase: 08-intelligent-cut-quality
    provides: SmoothingConfig with de_breathing_* and noise_floor_match_* fields (08-01 plan)
  - phase: 07-smooth-editing-filler-word-control
    provides: render._build_edit_plan_filter() with word-boundary snapping pipeline

provides:
  - utils/vad.py: detect_breath_extension() with silero-vad lazy import and 0.0 fallback
  - utils/noise_match.py: measure_rms_db() and compute_noise_floor_correction() with librosa lazy import
  - render._apply_de_breathing_pass(): extends cut boundaries to swallow trailing breaths
  - render._compute_noise_floor_corrections(): per-join RMS delta + volume filter injection
  - pyproject.toml gpu extras: silero-vad>=6.1, librosa>=0.10, opencv-python-headless>=4.9
  - uv.sources torch/torchaudio via pytorch-cu128 index (Blackwell sm_120 / RTX 5060 Ti)
  - 14 passing tests in test_vad.py (5) and test_noise_match.py (9)

affects:
  - 08-05-PLAN (pose matching / RIFE interpolation builds on same render pipeline)
  - 08-06-PLAN (integration tests exercise de-breathing and noise-floor passes)

# Tech tracking
tech-stack:
  added:
    - silero-vad>=6.1 (optional gpu extra — lazy import, graceful fallback)
    - librosa>=0.10 (optional gpu extra — lazy import, graceful fallback)
    - opencv-python-headless>=4.9 (optional gpu extra — headless, WSL/server safe)
    - torch/torchaudio via pytorch-cu128 uv.sources (Blackwell CUDA 12.8)
  patterns:
    - Module-level VAD singleton loaded on first use; reset_vad_model() for test isolation
    - Lazy optional import in try/except ImportError block returning safe fallback value
    - mypy overrides with ignore_missing_imports=true for silero_vad, librosa, cv2 modules
    - Per-join RMS measurement at boundary: tail of left segment + head of right segment
    - FFmpeg volume filter with eval=frame for in-stream per-sample gain correction
    - De-breathing pass after word-boundary snapping, before merge/invert

key-files:
  created:
    - src/podcast_pipeline/utils/vad.py
    - src/podcast_pipeline/utils/noise_match.py
    - tests/test_vad.py
    - tests/test_noise_match.py
  modified:
    - pyproject.toml
    - src/podcast_pipeline/config/settings.py
    - src/podcast_pipeline/stages/render.py

key-decisions:
  - "silero-vad>=6.1 (NOT >=5.0) — version 6.x fixes torchaudio deprecation issues in batch process"
  - "opencv-python-headless (NOT opencv-python) — avoids Qt/display dependency failures on WSL/server"
  - "torchvision NOT included — RIFE does not require it (confirmed in 08-RESEARCH.md Correction 6)"
  - "torch/torchaudio via uv.sources cu128 index — Blackwell sm_120 (RTX 5060 Ti) requires CUDA 12.8"
  - "compute_noise_floor_correction uses strict less-than (<) threshold: exactly at threshold IS corrected"
  - "De-breathing pass runs after word-boundary snapping but before merge/invert for correct ordering"
  - "read_audio() uses positional sampling_rate arg; get_speech_timestamps() uses keyword sampling_rate"

patterns-established:
  - "Optional dep pattern: try import X except ImportError: return safe_default"
  - "VAD singleton: _vad_model module global with reset_vad_model() for test hygiene"
  - "Noise-floor window: 100ms tail of left + 100ms head of right; offset_s pinpoints exact boundary"
  - "Volume filter: volume={gain_linear:.6f}:eval=frame — per-sample correction without second pass"

# Metrics
duration: 45min
completed: 2026-02-21
---

# Phase 8 Plan 04: De-breathing and Noise-Floor Matching Summary

**Silero-VAD breath detection at cut boundaries + librosa RMS noise-floor matching with FFmpeg volume correction, both with lazy optional imports and graceful fallback when GPU deps are absent**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-02-21T07:43:00Z
- **Completed:** 2026-02-21T08:27:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- `pyproject.toml` extended with `gpu` optional dependency group (`silero-vad>=6.1`, `librosa>=0.10`, `opencv-python-headless>=4.9`) and `uv.sources` routing torch/torchaudio to the `pytorch-cu128` index for Blackwell (RTX 5060 Ti / sm_120) CUDA support
- `SmoothingConfig` received all Phase 8 fields: `de_breathing_*`, `noise_floor_match_*`, `pose_match_*`, and `rife_*` — all with safe, production-appropriate defaults (de-breathing/noise-match enabled, RIFE disabled)
- `utils/vad.py` implements `detect_breath_extension()`: lazy silero-vad import, module-level model singleton, audio extraction at cut boundary, VAD timestamp analysis, trailing non-speech measurement clamped to `max_extend_ms`, and 0.0 fallback when unavailable
- `utils/noise_match.py` implements `measure_rms_db()` and `compute_noise_floor_correction()`: lazy librosa import with -120.0 fallback, head/tail/offset window modes, and FFmpeg `volume=X:eval=frame` filter generation
- `render._build_edit_plan_filter()` wired with de-breathing pass (after word-boundary snapping, before merge) and noise-floor corrections (per join, applied as audio chain suffix)
- 14 tests: 5 in `test_vad.py` (ImportError fallback, trailing breath detection, full-window speech, clamping, empty timestamps) and 9 in `test_noise_match.py` (ImportError fallback, threshold semantics, gain formula, attenuation, load error fallback)

## Task Commits

1. **Task 1: GPU extras + SmoothingConfig Phase 8 fields** - `f834f16` (feat)
2. **Task 2: VAD breath detector, noise-floor matcher, render integration + tests** - `3eff524` (feat)

## Files Created/Modified

- `pyproject.toml` - Added gpu extras group, uv.sources cu128, mypy overrides for silero_vad/librosa/cv2
- `src/podcast_pipeline/config/settings.py` - Added all Phase 8 SmoothingConfig fields
- `src/podcast_pipeline/utils/vad.py` - Created: detect_breath_extension() with silero-vad lazy import
- `src/podcast_pipeline/utils/noise_match.py` - Created: measure_rms_db() and compute_noise_floor_correction()
- `src/podcast_pipeline/stages/render.py` - Wired _apply_de_breathing_pass() and _compute_noise_floor_corrections() into filter pipeline
- `tests/test_vad.py` - Created: 5 VAD behavior tests with mock silero-vad module
- `tests/test_noise_match.py` - Created: 9 noise-floor tests with mock librosa module

## Decisions Made

- `silero-vad>=6.1` (NOT >=5.0): version 6.x fixes torchaudio deprecation issues present in 5.x
- `opencv-python-headless` instead of `opencv-python`: avoids Qt/display dependencies on WSL/server environments
- `torchvision` NOT included: RIFE does not require it (confirmed in 08-RESEARCH.md)
- `torch/torchaudio` via `pytorch-cu128` uv.sources: RTX 5060 Ti is Blackwell sm_120 architecture requiring CUDA 12.8
- Strict less-than comparison in `compute_noise_floor_correction`: `delta_db < threshold_db` means exactly at threshold IS corrected (edge case documented in tests)
- De-breathing runs after word-boundary snapping and before merge to allow correctly merged extended ranges

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added mypy ignore_missing_imports overrides for optional GPU deps**
- **Found during:** Task 2 commit (pre-commit hook failure)
- **Issue:** mypy `import-not-found` errors for `silero_vad` and `librosa` blocked commit
- **Fix:** Added `[[tool.mypy.overrides]]` entries for silero_vad, silero_vad.*, librosa, librosa.*, cv2, cv2.* with `ignore_missing_imports = true`
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run mypy src/` passes on all 47 source files
- **Committed in:** `f834f16` (Task 1 commit)

**2. [Rule 3 - Blocking] Committed leftover 08-03 work before proceeding**
- **Found during:** Pre-task 2 setup (git status review)
- **Issue:** Staged changes to review.py, test_review.py, app.py, test_ui_app.py from incomplete 08-03 plan blocked clean commits
- **Fix:** Committed 08-03 leftover work in two commits (`3a10803`, `75c0ea7`) before proceeding with 08-04 Task 2
- **Files modified:** `src/podcast_pipeline/stages/review.py`, `src/podcast_pipeline/ui/app.py`, `tests/test_review.py`, `tests/test_ui_app.py`
- **Verification:** All existing tests pass; ruff/mypy clean
- **Committed in:** `3a10803`, `75c0ea7` (08-03 residuals)

---

**Total deviations:** 2 auto-fixed (1 blocking pre-commit, 1 blocking leftovers)
**Impact on plan:** Both fixes necessary to unblock commits. No scope creep.

## Issues Encountered

- Pre-commit hook stash/restore mechanism made it tricky to commit with optional deps (silero_vad, librosa) and vad.py/noise_match.py files at the same time — needed mypy overrides staged alongside the new files in a single commit
- `silero_vad` `ignore_missing_imports` override worked correctly when checking package via `mypy src/` but not via individual file path — mypy's module pattern matching requires package context
- Test mocking for VAD required careful attention to `cut_out_seconds` parameter: must be within the mock audio duration (1 second) to avoid empty segment extraction

## User Setup Required

None - no external service configuration required. GPU deps (silero-vad, librosa, torch) are installed via `uv sync --extras gpu` but are fully optional.

## Next Phase Readiness

- Plan 05 (pose matching / OpenCV frame selection) can now build on the same render pipeline with similar optional-dep pattern
- Plan 06 (integration tests) can validate de-breathing and noise-floor passes with mock audio files
- All SmoothingConfig Phase 8 fields (including pose_match_* and rife_*) are ready for Plan 05

## Self-Check: PASSED

All files present and all commits verified:
- `src/podcast_pipeline/utils/vad.py` — FOUND
- `src/podcast_pipeline/utils/noise_match.py` — FOUND
- `src/podcast_pipeline/stages/render.py` — FOUND (contains _apply_de_breathing_pass, _compute_noise_floor_corrections)
- `tests/test_vad.py` — FOUND (5 tests)
- `tests/test_noise_match.py` — FOUND (9 tests)
- `pyproject.toml` — FOUND (gpu extras, uv.sources, mypy overrides)
- `src/podcast_pipeline/config/settings.py` — FOUND (all Phase 8 SmoothingConfig fields)
- Commit `f834f16` (Task 1: gpu extras + SmoothingConfig) — FOUND
- Commit `3eff524` (Task 2: VAD + noise match + render + tests) — FOUND

---
*Phase: 08-intelligent-cut-quality*
*Completed: 2026-02-21*
