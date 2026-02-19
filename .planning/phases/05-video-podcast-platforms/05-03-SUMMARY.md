---
phase: 05-video-podcast-platforms
plan: 03
subsystem: render
tags: [apple-hls, ffmpeg-hls, provider-workflow, documentation, platform-exports]
requires:
  - phase: 05-video-podcast-platforms
    provides: "Video-target config defaults and compliance-validated MP4 render paths"
provides:
  - "Typed apple_hls platform schema and conservative VOD defaults"
  - "Dedicated _render_hls path with deterministic master/variant/segment validation"
  - "Operator docs clarifying Spotify hosted/non-hosted and Apple provider-mediated boundaries"
affects: [phase-verification, operator-docs, release-readiness]
tech-stack:
  added: []
  patterns:
    - "Artifact generation separated from provider dashboard publication steps"
    - "Render success gated by playlist/segment integrity checks"
key-files:
  created: []
  modified:
    - src/podcast_pipeline/config/settings.py
    - src/podcast_pipeline/config/__init__.py
    - config.yaml
    - src/podcast_pipeline/stages/render.py
    - tests/test_render.py
    - README.md
key-decisions:
  - "Represent Apple HLS as a dedicated platform target rather than overloading apple_video"
  - "Fail HLS render if master/variant/segment artifacts are incomplete"
  - "Document publication boundaries explicitly to avoid overpromising upload automation"
patterns-established:
  - "HLS playlist integrity is verified before stage success"
  - "README documents platform workflow constraints alongside generated artifacts"
duration: 8m
completed: 2026-02-19
---

# Phase 5 Plan 03: Apple HLS + Workflow Boundaries Summary

**Implemented typed `apple_hls` packaging with deterministic playlist/segment validation and documented Apple/Spotify publication boundaries without claiming direct upload automation**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-19T20:17:00Z
- **Completed:** 2026-02-19T20:24:58Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Added typed HLS config (`HLSConfig`) and default `apple_hls` platform settings in both schema and `config.yaml`.
- Added `_render_hls()` with FFmpeg HLS muxer options (`var_stream_map`, `master_pl_name`, `hls_segment_filename`, VOD playlist type) and strict artifact validation.
- Updated README to separate artifact generation from dashboard/provider publication workflows, including Spotify hosted/non-hosted and Apple provider-mediated constraints.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add typed HLS platform config models and defaults** - `d10650f` (feat)
2. **Task 2: Implement HLS render routing and artifact validation** - `9476804` (feat)
3. **Task 3: Update workflow docs with platform constraints and operator steps** - `6c7604b` (docs)

## Files Created/Modified
- `src/podcast_pipeline/config/settings.py` - Added `HLSConfig`, `apple_hls` defaults, and HLS config validators.
- `src/podcast_pipeline/config/__init__.py` - Exported `HLSConfig`.
- `config.yaml` - Added `apple_hls` target and HLS defaults.
- `src/podcast_pipeline/stages/render.py` - Added HLS routing, ffmpeg HLS muxer invocation, and playlist/segment integrity checks.
- `tests/test_render.py` - Added HLS config/render/documentation regression tests.
- `README.md` - Added Apple/Spotify workflow boundary section (`apple_video`, `apple_hls`, hosted/non-hosted, provider-mediated constraints).

## Decisions Made
- Kept HLS packaging optional and operator-facing (artifact hand-off), not direct publish automation.
- Treated missing variant playlists or segments as hard render failures to keep success signals truthful.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

External provider accounts remain required for publication workflows (Apple Podcasts Connect, eligible host integrations, Spotify for Creators dashboard actions).

## Next Phase Readiness
- All Phase 5 plans are implemented with summaries.
- Ready for phase-level verification (`05-video-podcast-platforms-VERIFICATION.md`).

---
*Phase: 05-video-podcast-platforms*
*Completed: 2026-02-19*
