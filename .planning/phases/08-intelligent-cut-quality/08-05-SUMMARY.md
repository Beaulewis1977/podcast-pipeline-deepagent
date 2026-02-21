---
phase: 08-intelligent-cut-quality
plan: 05
subsystem: video-processing
tags: [pose-match, rife, optical-flow, farneback, frame-interpolation, opencv, subprocess, render]

# Dependency graph
requires:
  - phase: 08-intelligent-cut-quality
    provides: SmoothingConfig with pose_match_*, rife_* fields (08-04 plan)
  - phase: 08-intelligent-cut-quality
    provides: render._apply_de_breathing_pass() pipeline position (08-04 plan)
  - phase: 07-smooth-editing-filler-word-control
    provides: render._build_edit_plan_filter() content-cut join pipeline

provides:
  - utils/pose_match.py: pose_distance() via Farneback optical flow + scan_best_frame_pair() with clamped window
  - utils/rife_bridge.py: RifeBridge class with generate() using --exp flag, frames_to_exp(), and available()
  - render._apply_pose_match_pass(): content-join pose scan -> RIFE bridge -> xfade fallback pipeline
  - render._extract_frames(): FFmpeg frame extractor with graceful failure fallback
  - render._encode_bridge_frames(): PNG-to-MP4 concat-demuxer bridge clip encoder
  - tests/test_pose_match.py: 8 tests covering ImportError fallback, determinism, window clamping, minimum selection
  - tests/test_rife_bridge.py: 12 tests covering --exp correctness, --n/--cpu absence, failure paths, output sorting

affects:
  - 08-06-PLAN (integration tests exercise pose-match and RIFE paths)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Lazy optional import for cv2/numpy in pose_distance() with float('inf') fallback
    - subprocess.run() with --exp flag (NOT --n, NOT --cpu) for RIFE frame interpolation
    - CUDA_VISIBLE_DEVICES="" env pattern for CPU fallback instead of --cpu flag
    - TemporaryDirectory for frame extraction cleanup; stable_dir copy for bridge clips
    - FFmpeg concat demuxer for PNG sequence to MP4 bridge clip encoding

key-files:
  created:
    - src/podcast_pipeline/utils/pose_match.py
    - src/podcast_pipeline/utils/rife_bridge.py
    - tests/test_pose_match.py
    - tests/test_rife_bridge.py
  modified:
    - src/podcast_pipeline/stages/render.py

key-decisions:
  - "--exp flag used for RIFE (NOT --n which does not exist); confirmed from Phase 8 research corrections"
  - "No --cpu flag for RIFE; CPU fallback via CUDA_VISIBLE_DEVICES='' env var instead"
  - "RIFE disabled by default (rife_enabled=False) — requires manual RIFE installation"
  - "pose_match_enabled=True by default — degrades gracefully when cv2 unavailable (returns inf)"
  - "Audio-only jobs auto-skip pose matching with info-level log message"
  - "Bridge clips copied to stable_dir before TemporaryDirectory cleanup to survive tempdir lifecycle"
  - "scan_best_frame_pair clamps search window to min(window, available_frames) — no IndexError on short segments"

patterns-established:
  - "Optional dep pattern: try import cv2/numpy except ImportError: return float('inf')"
  - "RIFE subprocess always uses --exp <int> computed by frames_to_exp(num_frames)"
  - "Frame extraction via _extract_frames() silently degrades on FFmpegError — pose match skips join"
  - "Bridge clip pipeline: RIFE frames -> _encode_bridge_frames() -> copy to stable_dir -> filtergraph movie= source"

# Metrics
duration: 20min
completed: 2026-02-21
---

# Phase 8 Plan 05: Pose-Match and RIFE Frame Interpolation Summary

**OpenCV Farneback optical-flow frame selection and RIFE AI bridge frame generation for invisible content-cut joins, with lazy cv2 import, --exp subprocess flag, and xfade fallback**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-02-21T08:42:24Z
- **Completed:** 2026-02-21T08:47:42Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `utils/pose_match.py` implements `pose_distance()` using Farneback dense optical flow and `scan_best_frame_pair()` with clamped search window — both with lazy `cv2`/`numpy` import and `float('inf')` fallback when opencv is absent
- `utils/rife_bridge.py` implements `RifeBridge` class with `generate()` using `--exp` flag (corrected per Phase 8 research, NOT `--n`), `frames_to_exp()` converter (rounds up to next power-of-two), and `available()` filesystem check
- `render._apply_pose_match_pass()` wires the full pipeline: extracts frames via FFmpeg at each content-cut join, calls `scan_best_frame_pair()`, optionally generates RIFE bridge clips, copies them to a stable directory, and falls back to Phase 7 xfade when RIFE fails or is disabled
- `render._extract_frames()` and `render._encode_bridge_frames()` added as helpers with graceful FFmpegError fallback
- 20 tests total: 8 in `test_pose_match.py` (cv2-skip aware) and 12 in `test_rife_bridge.py` (pure mock/subprocess)

## Task Commits

1. **Task 1: Create pose-match scanner and RIFE bridge utilities** - `7a9418a` (feat — pre-existing from session start)
2. **Task 2: Wire pose-match and RIFE into render + tests** - `4b203bb` (feat)

## Files Created/Modified

- `src/podcast_pipeline/utils/pose_match.py` - Created: `pose_distance()` + `scan_best_frame_pair()` with lazy cv2 import
- `src/podcast_pipeline/utils/rife_bridge.py` - Created: `RifeBridge` class with `generate(--exp)`, `frames_to_exp()`, `available()`
- `src/podcast_pipeline/stages/render.py` - Added `_apply_pose_match_pass()`, `_extract_frames()`, `_encode_bridge_frames()`
- `tests/test_pose_match.py` - Created: 8 tests (ImportError fallback, determinism, window clamping, minimum pair selection)
- `tests/test_rife_bridge.py` - Created: 12 tests (frames_to_exp, availability, --exp correctness, failure/success paths)

## Decisions Made

- `--exp` flag is the correct RIFE CLI flag (NOT `--n` which doesn't exist) — confirmed from Phase 8 research Correction 3
- No `--cpu` flag in RIFE — CPU fallback should be via `CUDA_VISIBLE_DEVICES=""` in subprocess env (not yet wired but documented)
- `rife_enabled=False` default keeps baseline render behavior unchanged; RIFE is opt-in
- `pose_match_enabled=True` with graceful cv2 fallback: safe to enable without requiring opencv install
- Bridge clips are copied to `jobs/<job>/render/bridge_clips/` before the TemporaryDirectory is cleaned up, ensuring they survive the context manager lifetime
- Audio-only jobs detected via `video_path is None` and skip pose matching with an info log

## Deviations from Plan

None — plan executed exactly as written. Both utility files were pre-created (`7a9418a`) at session start; this plan's Task 2 added the render integration and tests.

## Issues Encountered

- Pre-commit hook applied `ruff format` reformatting on first commit attempt; re-staged and committed clean on second attempt
- `type: ignore[import-not-found]` comments in test file were flagged as unused by mypy (cv2 override in pyproject.toml already handles this globally) — removed the comments

## User Setup Required

None — no external service configuration required. Pose matching degrades gracefully without opencv installed. RIFE requires manual setup of `inference_img.py` and setting `smoothing.rife_script_path` + `smoothing.rife_enabled=true` in config.yaml.

## Next Phase Readiness

- Plan 06 (integration tests) can now exercise the full Phase 8 render pipeline including pose-match and RIFE fallback paths
- RIFE is wired and tested — users can activate it by pointing `rife_script_path` to a practical-RIFE installation and setting `rife_enabled: true`

## Self-Check: PASSED

Files present and commits verified:
- `src/podcast_pipeline/utils/pose_match.py` — FOUND (pose_distance, scan_best_frame_pair)
- `src/podcast_pipeline/utils/rife_bridge.py` — FOUND (RifeBridge, frames_to_exp, generate with --exp)
- `src/podcast_pipeline/stages/render.py` — FOUND (_apply_pose_match_pass, _extract_frames, _encode_bridge_frames)
- `tests/test_pose_match.py` — FOUND (8 tests)
- `tests/test_rife_bridge.py` — FOUND (12 tests)
- Commit `7a9418a` (Task 1: pose_match + rife_bridge utilities) — FOUND
- Commit `4b203bb` (Task 2: render integration + tests) — FOUND

---
*Phase: 08-intelligent-cut-quality*
*Completed: 2026-02-21*
