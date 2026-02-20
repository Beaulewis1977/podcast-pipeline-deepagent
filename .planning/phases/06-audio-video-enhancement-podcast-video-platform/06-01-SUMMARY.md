---
phase: 06-audio-video-enhancement-podcast-video-platform
plan: 01
subsystem: render
tags: [ffmpeg, pydantic, config, preflight, testing]
requires:
  - phase: 05-video-podcast-platforms
    provides: strict render compliance wiring and truthful failure contracts
  - phase: 05.1-streamlit-video-platform-ui
    provides: normalized export target contracts shared across surfaces
provides:
  - typed enhancement config contract for deesser, dereverb, and color correction
  - ffmpeg capability preflight guard for enabled enhancement filters
  - phase 6 scope-boundary regression tests for enhancement-only behavior
affects: [06-02, 06-03, phase-verification]
tech-stack:
  added: []
  patterns:
    - config-first enhancement toggles with safe default policy
    - process-cached ffmpeg capability probing before render execution
key-files:
  created: []
  modified:
    - src/podcast_pipeline/config/settings.py
    - config.yaml
    - src/podcast_pipeline/stages/render.py
    - tests/test_render.py
key-decisions:
  - "Keep deesser enabled by default with conservative settings; keep dereverb and color correction opt-in."
  - "Fail fast in render when enabled enhancement filters are unavailable in local ffmpeg."
patterns-established:
  - "Enhancement capability requirements are derived from typed config, not hardcoded per platform."
  - "Scope boundary is enforced via tests that explicitly reject edit-core transition filter bleed."
duration: 3m
completed: 2026-02-20
---

# Phase 6 Plan 01: Enhancement Config + Capability Guardrails Summary

**Typed enhancement configuration now drives filter capability preflight so render fails early and clearly when enabled Phase 6 filters are unavailable.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-20T03:27:00Z
- **Completed:** 2026-02-20T03:30:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added typed enhancement settings (`deesser`, `dereverb`, `color_correction`) with explicit default policy.
- Added render preflight capability checks that derive required filters from enabled enhancement toggles and cache `ffmpeg -filters` results per process.
- Added regression tests to lock Phase 6 enhancement-only boundaries and optional-filter no-op behavior when disabled.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add typed enhancement config models with safe defaults** - `c54a5a1` (feat)
2. **Task 2: Add FFmpeg filter capability preflight for enabled enhancements** - `c29c51c` (feat)
3. **Task 3: Add regression tests for scope boundary and defaults** - `76da8f0` (test)

## Files Created/Modified
- `src/podcast_pipeline/config/settings.py` - typed enhancement models and validation.
- `config.yaml` - operator-visible enhancement defaults and toggles.
- `src/podcast_pipeline/stages/render.py` - filter capability derivation, probing, and fail-fast preflight.
- `tests/test_render.py` - config/preflight/boundary regression coverage.

## Decisions Made
- Defaulted `deesser` on with conservative values to establish a safe baseline while keeping heavier enhancements disabled.
- Required filters are checked only for enabled paths (`deesser`, `adeclick`, and color filters when color correction is enabled).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Pre-commit initially failed on lint constraints (`PLR0911`, `PLW0603`); resolved by reusing existing preflight return path and moving filter cache to class-level storage.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `06-02` can now integrate deesser/dereverb behavior against a stable, typed config contract.
- `06-03` can safely wire optional color correction using the same enhancement config boundary and preflight guardrail model.

---
*Phase: 06-audio-video-enhancement-podcast-video-platform*
*Completed: 2026-02-20*
