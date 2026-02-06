---
phase: 03-polishing-+-desktop-distribution
plan: 04
subsystem: infra
tags: [tauri, sidecar, ffmpeg, pyinstaller, asset-resolution, model-warmup, fastapi]

# Dependency graph
requires:
  - phase: 03-polishing-+-desktop-distribution/01
    provides: FastAPI service with lifespan, routes, and supervisor
  - phase: 03-polishing-+-desktop-distribution/02
    provides: Tauri v2 desktop shell with sidecar lifecycle and externalBin config
provides:
  - Target-triple sidecar preparation script for cross-platform binary naming
  - Build-time validation of required sidecar binaries (build.rs)
  - Runtime asset resolver for binaries and model caches (assets.py)
  - System endpoints for asset readiness, binary checks, and model warmup
  - Job recovery module with reconciliation and resumable job detection
  - 59 regression tests covering asset resolution and recovery flows
affects: [03-05, 03-06, desktop-bundling, installer-builds]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tiered binary resolution: env override -> sidecar dir -> system PATH"
    - "Tiered model resolution: env -> app_data -> project -> HF cache"
    - "Build-time sidecar validation with SKIP_SIDECAR_CHECK escape hatch"
    - "Async model warmup with in-memory download task tracking"

key-files:
  created:
    - desktop/scripts/prepare-sidecars.mjs
    - desktop/src-tauri/build.rs
    - desktop/src-tauri/binaries/.gitkeep
    - src/podcast_pipeline/service/assets.py
    - src/podcast_pipeline/service/routes/system.py
    - src/podcast_pipeline/service/recovery.py
    - tests/test_asset_resolution.py
    - tests/test_job_recovery.py
  modified:
    - desktop/src-tauri/tauri.conf.json
    - src/podcast_pipeline/service/app.py
    - src/podcast_pipeline/service/routes/jobs.py
    - src/podcast_pipeline/service/schemas.py
    - src/podcast_pipeline/clients/service_client.py

key-decisions:
  - "Tiered binary resolution (env/sidecar/PATH) avoids hardcoded OS paths"
  - "SKIP_SIDECAR_CHECK env var for dev iteration without requiring all binaries"
  - "In-memory download task tracking for model warmup status (no persistent queue needed)"
  - "Recovery module with conservative reconciliation (never touch completed stages)"

patterns-established:
  - "Asset resolution: env -> sidecar -> PATH for binaries"
  - "Model cache: env -> app_data -> project -> HF hub for model artifacts"
  - "Build validation: build.rs checks binaries before Tauri bundle, prepare-sidecars.mjs names them"

# Metrics
duration: 4min
completed: 2026-02-05
---

# Phase 03 Plan 04: Asset Packaging and Runtime Resolution Summary

**Deterministic sidecar preparation with target-triple naming, tiered asset resolver for binaries and models, and system readiness endpoints with 59 regression tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-05T21:00:31Z
- **Completed:** 2026-02-05T21:04:16Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments
- Build-time sidecar naming script that maps Node.js platform/arch to Rust target triples and copies/renames binaries for Tauri bundles
- Rust build.rs validation that fails early with actionable errors when required sidecars are missing before bundle
- Runtime asset resolver with tiered search (env vars, sidecar dir, system PATH for binaries; env, app_data, project, HF cache for models)
- System endpoints for combined readiness check, individual binary checks, model cache queries, and async model warmup/download
- 31 regression tests for asset resolution edge cases and 28 for job recovery flows

## Task Commits

Each task was committed atomically:

1. **Task 1: Add deterministic sidecar preparation for platform binaries** - `1815b47` (feat)
2. **Task 2: Implement runtime asset resolver in backend service** - `a99411e` (feat)
3. **Task 3: Add regression tests for asset and model readiness flows** - `65e1249` (test)

## Files Created/Modified
- `desktop/scripts/prepare-sidecars.mjs` - Target-triple naming script for sidecar binaries (230 lines)
- `desktop/src-tauri/build.rs` - Build-time validation of required sidecar binaries (98 lines)
- `desktop/src-tauri/binaries/.gitkeep` - Placeholder for sidecar binaries directory
- `desktop/src-tauri/tauri.conf.json` - Updated externalBin entries for podcast-backend, ffmpeg, ffprobe
- `src/podcast_pipeline/service/assets.py` - Runtime binary/model path resolution helpers (305 lines)
- `src/podcast_pipeline/service/routes/system.py` - System readiness and warmup endpoints (252 lines)
- `src/podcast_pipeline/service/recovery.py` - Job reconciliation and resumable detection (270 lines)
- `src/podcast_pipeline/service/app.py` - Wired system router into app factory
- `src/podcast_pipeline/service/routes/jobs.py` - Added resumable and reconcile endpoints
- `src/podcast_pipeline/service/schemas.py` - Added ResumableJobItem and ResumableJobsResponse
- `src/podcast_pipeline/clients/service_client.py` - Added resumable/reconcile client methods
- `tests/test_asset_resolution.py` - 31 asset resolution regression tests
- `tests/test_job_recovery.py` - 28 job recovery regression tests

## Decisions Made
- **Tiered resolution strategy**: Binary lookup follows env override -> sidecar directory -> system PATH. This avoids hardcoded paths and supports dev mode (PATH) and bundled mode (sidecar) transparently.
- **SKIP_SIDECAR_CHECK escape hatch**: Build.rs validation can be skipped via env var during development iteration without requiring all sidecar binaries to be present.
- **In-memory download tracking**: Model warmup uses a simple dict for tracking download status rather than a persistent queue, since downloads are ephemeral and restart-safe.
- **Conservative reconciliation**: Recovery module never modifies completed stages, only corrects stale "running" states to "failed" or "interrupted".

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added recovery module for crash-recovery logic**
- **Found during:** Task 2
- **Issue:** The system endpoints and jobs router needed crash-recovery reconciliation logic that wasn't explicitly in the plan but is required for correct resumable job identification and service-startup state correction.
- **Fix:** Created `recovery.py` with reconcile_job, reconcile_all_jobs, list_resumable_jobs, and prepare_resume functions. Added resumable/reconcile routes to jobs router.
- **Files modified:** src/podcast_pipeline/service/recovery.py, src/podcast_pipeline/service/routes/jobs.py, src/podcast_pipeline/service/schemas.py, src/podcast_pipeline/clients/service_client.py
- **Verification:** 28 tests in test_job_recovery.py pass
- **Committed in:** a99411e (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Recovery module is essential for correct job resumability detection used by system readiness checks. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Asset resolution infrastructure is complete for desktop bundling
- System endpoints ready for Tauri frontend to check readiness before starting jobs
- Model warmup can be triggered from desktop UI during first-run experience
- Recovery module enables crash-safe job resumption on app restart

---
*Phase: 03-polishing-+-desktop-distribution*
*Completed: 2026-02-05*
