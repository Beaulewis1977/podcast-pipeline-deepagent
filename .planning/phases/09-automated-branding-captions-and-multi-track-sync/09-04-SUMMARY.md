---
phase: 09-automated-branding-captions-and-multi-track-sync
plan: 04
subsystem: video-codec
tags: [hevc, nvenc, av1, libx265, libx264, pix_fmt, rife, encoder-fallback, hardware-detection]

# Dependency graph
requires:
  - phase: 09-01
    provides: detect_hardware_encoders and HardwareEncoderInfo from ffmpeg_toolkit
  - phase: 08-05
    provides: RifeBridge for RIFE frame interpolation
provides:
  - "PlatformSpec HEVC 10-bit validation (hevc_nvenc + main10 + p010le/p7, RTX artifact guard)"
  - "AV1 explicit opt-in gate via av1_experimental field on PlatformSpec"
  - "youtube_ultra PlatformSpec — NVENC HEVC 10-bit 4K export profile"
  - "SmoothingConfig.force_60fps_shortform flag for RIFE 30->60fps uplift gating"
  - "RenderStage._resolve_video_encoder — NVENC/software fallback chain at render time"
  - "RenderStage._is_shortform_vertical — gates uplift to 9:16 targets only"
  - "RenderStage._apply_shortform_60fps_rife — runs BEFORE branding/caption burn-in"
  - "24 regression tests covering encoder selection, RIFE gating, and legacy platform isolation"
affects: [render, config, codec-selection, short-form-exports, rife, branding]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hardware-first encoder selection with explicit software fallback at render time"
    - "AV1 is always opt-in via av1_experimental flag — never silently activated"
    - "force_60fps_shortform RIFE uplift gates on aspect_ratio='9:16' — longform exports never affected"
    - "pix_fmt p010le translates to yuv420p10le on libx265 fallback"
    - "RTX 5060 Ti artifact guard: hevc_nvenc + p010le rejects uhq/hq presets, requires p7"

key-files:
  created: []
  modified:
    - "src/podcast_pipeline/config/settings.py — PlatformSpec AV1 gate, HEVC validation, youtube_ultra profile, SmoothingConfig.force_60fps_shortform"
    - "config.yaml — force_60fps_shortform=false and youtube_ultra HEVC 10-bit profile"
    - "src/podcast_pipeline/stages/render.py — _resolve_video_encoder, _is_shortform_vertical, _apply_shortform_60fps_rife, HardwareEncoderInfo at startup"
    - "src/podcast_pipeline/utils/rife_bridge.py — uplift_fps stub (graceful NotImplementedError)"
    - "tests/test_render.py — 152 total tests (24 new regression tests for Phase 9)"

key-decisions:
  - "hevc_nvenc is the preferred codec for youtube_ultra; libx265 is the runtime fallback when NVENC is absent"
  - "p010le (NVENC 10-bit) translates to yuv420p10le for libx265 software fallback"
  - "AV1 requires av1_experimental=True on PlatformSpec; any AV1 codec without this flag raises ValueError at config load"
  - "hevc_nvenc + p010le + uhq or hq preset is forbidden — RTX artifact regression guard requires p7 instead"
  - "force_60fps_shortform gates on config.smoothing.force_60fps_shortform AND rife_enabled AND aspect_ratio in SHORT_FORM_ASPECT_RATIOS"
  - "RIFE 30->60fps uplift runs before any filtergraph construction so interpolated frames are the base for overlays"
  - "RifeBridge.uplift_fps raises NotImplementedError (whole-video uplift not yet implemented); _apply_shortform_60fps_rife catches and falls back gracefully"

patterns-established:
  - "Pattern: Hardware-first codec dispatch — spec.video_codec is the PREFERRED encoder, not the final encoder"
  - "Pattern: Explicit AV1 opt-in — av1_experimental must be True at config layer before AV1 can appear in FFmpeg args"
  - "Pattern: Shortform gating — _is_shortform_vertical checks aspect_ratio against SHORT_FORM_ASPECT_RATIOS set"

# Metrics
duration: 6min
completed: 2026-02-24
---

# Phase 9 Plan 04: HEVC 10-bit and AV1 Experimental Codec Strategy Summary

**HEVC 10-bit NVENC/x265 fallback chain plus explicit AV1 opt-in gate with deterministic short-form RIFE gating**

## Performance

- **Duration:** ~6 min (continuation of pre-committed Task 1 work)
- **Started:** 2026-02-24T03:51:23Z
- **Completed:** 2026-02-24T03:57:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Implemented `_resolve_video_encoder` with hevc_nvenc->libx265 and h264_nvenc->libx264 fallback chains at render time
- Added AV1 explicit opt-in gate via `av1_experimental` field on PlatformSpec — any AV1 codec without it fails at config load
- Added `force_60fps_shortform` flag to SmoothingConfig, gating RIFE 30->60fps uplift to 9:16 short-form vertical exports only
- RTX artifact guard: hevc_nvenc + p010le + uhq/hq preset raises ValueError — p7 required
- 24 new regression tests covering NVENC detection branches, x265 fallback, shortform gating, and legacy platform isolation

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend platform config schema for HEVC 10-bit and AV1 experimental mode** - `090f6ab` (feat)
2. **Task 2: Implement runtime encoder capability detection and fallback chain** - `036be9a` (feat)
3. **Task 3: Lock codec behavior with regression tests** - `274d1ff` (test)

## Files Created/Modified

- `src/podcast_pipeline/config/settings.py` — AV1 opt-in gate, HEVC profile validation, youtube_ultra PlatformSpec, force_60fps_shortform in SmoothingConfig, RTX artifact guard
- `config.yaml` — force_60fps_shortform=false, youtube_ultra HEVC 10-bit profile with p7 preset
- `src/podcast_pipeline/stages/render.py` — HardwareEncoderInfo at startup, `_resolve_video_encoder`, `_is_shortform_vertical`, `_apply_shortform_60fps_rife`, RIFE-before-overlays ordering
- `src/podcast_pipeline/utils/rife_bridge.py` — `uplift_fps` stub with NotImplementedError and graceful fallback
- `tests/test_render.py` — 152 total tests (24 new: TestEncoderCapabilityDetection, TestShortformVerticalDetection, TestForce60fpsShortformGating, TestLegacyPlatformUnaffectedByPhase9Options)

## Decisions Made

- hevc_nvenc is preferred codec for youtube_ultra; render stage resolves actual encoder via `_resolve_video_encoder` using cached HardwareEncoderInfo
- p010le (NVENC 10-bit) translates to yuv420p10le for libx265 software fallback — different pixel format conventions
- AV1 codec without `av1_experimental=True` raises ValueError at config load — zero silent AV1 activation
- RTX 5060 Ti artifact guard: hevc_nvenc + p010le + uhq/hq preset forbidden; p7 required
- RIFE uplift runs BEFORE any filtergraph/overlay construction so interpolated frames are the render base
- `RifeBridge.uplift_fps` raises NotImplementedError (whole-video uplift deferred); `_apply_shortform_60fps_rife` catches and returns None gracefully

## Deviations from Plan

None — plan executed as specified. Task 1 was already committed from a prior partial execution; Tasks 2 and 3 were executed in this session.

## Issues Encountered

None. The encoder capability tests and shortform gating tests all pass cleanly. Pre-existing full-suite test ordering failures are unrelated to this plan.

## Next Phase Readiness

- HEVC 10-bit codec strategy is validated and regression-locked
- AV1 opt-in gate prevents accidental activation in any platform profile
- Render encoder selection is deterministic across GPU and non-GPU machines
- Short-form RIFE uplift gating is in place; full uplift_fps implementation deferred to a future plan
- Ready for Phase 9 Plan 05 (BrandingProfile model and platform override merge)

---
*Phase: 09-automated-branding-captions-and-multi-track-sync*
*Completed: 2026-02-24*

## Self-Check: PASSED

- FOUND: `src/podcast_pipeline/config/settings.py` (980 lines, min 110)
- FOUND: `src/podcast_pipeline/stages/render.py` (3330 lines, min 120)
- FOUND: `tests/test_render.py` (3123 lines, min 140)
- FOUND: `config.yaml`
- FOUND: `.planning/phases/09-automated-branding-captions-and-multi-track-sync/09-04-SUMMARY.md`
- FOUND commit `090f6ab` — feat: extend platform config schema
- FOUND commit `036be9a` — feat: runtime encoder capability detection
- FOUND commit `274d1ff` — test: codec behavior regression tests
