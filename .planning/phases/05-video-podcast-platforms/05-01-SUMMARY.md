---
phase: 05-video-podcast-platforms
plan: 01
subsystem: config
tags: [pydantic, platform-specs, spotify-video, apple-video, validation]
requires:
  - phase: 04-post-release-hardening
    provides: "truthful render contracts and strict runtime validation baseline"
provides:
  - "Dedicated spotify_video and apple_video platform defaults"
  - "Fail-fast schema validation for profile/level/pix_fmt/keyframe fields"
  - "Regression tests for new video targets and legacy audio-only compatibility"
affects: [05-02-render-compliance, 05-03-apple-hls]
tech-stack:
  added: []
  patterns:
    - "Dedicated platform target split (audio-only vs video-specific)"
    - "Codec-aware schema validation at config-load boundary"
key-files:
  created: []
  modified:
    - src/podcast_pipeline/config/settings.py
    - config.yaml
    - tests/test_render.py
key-decisions:
  - "Keep existing spotify/apple audio-only targets unchanged and introduce separate spotify_video/apple_video targets"
  - "Enforce profile/level/pix_fmt/keyframe constraints during config parsing instead of render-time failure"
patterns-established:
  - "Platform target naming distinguishes workflow/output intent explicitly"
  - "Validation errors include target context for operator-actionable diagnostics"
duration: 9m
completed: 2026-02-19
---

# Phase 5 Plan 01: Research-led Platform Defaults Summary

**Dedicated spotify/apple video platform specs with fail-fast codec/profile/pix_fmt/keyframe validation while preserving legacy audio-only exports**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-19T20:06:00Z
- **Completed:** 2026-02-19T20:15:13Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Added `spotify_video` and `apple_video` defaults in typed config and `config.yaml` with conservative MP4/H.264 mezzanine settings.
- Added codec-aware schema guardrails for `video_profile`, `video_level`, `pix_fmt`, `gop`, and `keyint_min`.
- Added regression tests covering new defaults plus backward compatibility for existing `spotify` and `apple` audio-only targets.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dedicated Spotify/Apple video target defaults** - `3894d20` (feat)
2. **Task 2: Add fail-fast schema validation for compliance-critical fields** - `37e3e7b` (fix)
3. **Task 3: Add regression coverage for defaults and backward compatibility** - `a5cfafb` (test)

## Files Created/Modified
- `src/podcast_pipeline/config/settings.py` - Added video target defaults and schema validators for compliance-critical fields.
- `config.yaml` - Added conservative `spotify_video` and `apple_video` platform defaults.
- `tests/test_render.py` - Added defaults + validation + backward-compatibility regression coverage.

## Decisions Made
- Split audio and video publication concerns into separate platform targets to avoid mutating legacy behavior.
- Kept H.265 out of defaults and explicit-opt-in only through schema-controlled settings.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-commit lint gate (`PT011`) required explicit `match=` patterns in `pytest.raises`; tests were updated and re-verified.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Render now has typed and validated platform inputs for Spotify/Apple video compliance wiring in Plan 05-02.
- No blockers identified.

---
*Phase: 05-video-podcast-platforms*
*Completed: 2026-02-19*
