---
phase: 05-video-podcast-platforms
plan: 02
subsystem: render
tags: [ffmpeg, ffprobe, compliance, spotify-video, apple-video]
requires:
  - phase: 05-video-podcast-platforms
    provides: "Typed spotify_video/apple_video config defaults and compliance fields"
provides:
  - "Codec-compatible profile/level/GOP/keyframe render argument wiring"
  - "ffprobe-backed topology/duration/container compliance validation for spotify_video/apple_video"
  - "Truthful compliance failure status contracts in platform_results"
affects: [05-03-apple-hls, phase-verification]
tech-stack:
  added: []
  patterns:
    - "Post-render compliance gate before reporting platform success"
    - "Structured compliance diagnostics surfaced in stage result payloads"
key-files:
  created: []
  modified:
    - src/podcast_pipeline/stages/render.py
    - tests/test_render.py
key-decisions:
  - "Apply profile/level/keyframe flags only for codecs that support those controls"
  - "Treat topology/duration/container compliance failures as platform-level hard failures"
  - "Mark compliance failures with explicit error_type for truthful operator diagnostics"
patterns-established:
  - "Render validates outputs with ffprobe before success reporting"
  - "Compliance issues and warnings are returned as structured validation details"
duration: 6m
completed: 2026-02-19
---

# Phase 5 Plan 02: Render Compliance Summary

**Render now applies compliance-critical encoding flags and blocks non-compliant Spotify/Apple video outputs via ffprobe-backed validation with structured failure contracts**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-19T20:14:30Z
- **Completed:** 2026-02-19T20:20:42Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Wired `video_profile`, `video_level`, `gop`, and `keyint_min` into `_render_video()` for compatible codecs.
- Added post-render compliance checks for `spotify_video` and `apple_video` covering topology, duration parity, codec/pix_fmt/profile/level, and container compatibility.
- Preserved truthful render contracts by classifying compliance failures with explicit validation payloads in `platform_results`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire profile/level and cadence settings into `_render_video`** - `66d8afa` (feat)
2. **Task 2: Add ffprobe-backed Spotify/Apple post-render compliance checks** - `2587e55` (fix)
3. **Task 3: Preserve truthful status/error contracts under compliance failures** - `b490608` (fix)

## Files Created/Modified
- `src/podcast_pipeline/stages/render.py` - Added codec-aware ffmpeg arg wiring, ffprobe compliance validation, and compliance-error result contracts.
- `tests/test_render.py` - Added regression tests for flag wiring, topology/duration/container compliance behavior, and structured compliance failure reporting.

## Decisions Made
- Enforced `spotify_video` and `apple_video` checks as hard platform failures to prevent false-success render results.
- Used warning-only policy for EDL/keyframe-risk heuristics when ffprobe cannot deterministically prove failure.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Render has deterministic compliance gates for MP4 video targets.
- Ready for Plan 05-03 HLS artifact path + workflow-boundary documentation updates.

---
*Phase: 05-video-podcast-platforms*
*Completed: 2026-02-19*
