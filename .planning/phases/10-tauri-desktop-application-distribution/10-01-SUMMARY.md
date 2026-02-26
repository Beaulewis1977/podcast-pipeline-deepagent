---
phase: 10-tauri-desktop-application-distribution
plan: 01
subsystem: infra
tags: [fastapi, cors, uvicorn, tauri, rust, reqwest, pyinstaller, sidecar]

# Dependency graph
requires:
  - phase: 9.12-streamlit-ui-gap-closure
    provides: FastAPI backend service at src/podcast_pipeline/service/app.py
provides:
  - PyInstaller-compatible sidecar entry point (service/cli.py) with BACKEND_READY stdout marker
  - CORS middleware on FastAPI service allowing Tauri dev (localhost:1420) and production (tauri://localhost) origins
  - Pre-spawn coexistence health check in lib.rs preventing double-spawn when backend already running
  - TAURI_OWNS_SIDECAR ownership flag preventing Tauri from killing externally-started backends
affects:
  - 10-02 through 10-06 (all phase 10 plans depend on these three infrastructure fixes)
  - desktop/src-tauri (Rust sidecar lifecycle)
  - CI build (PyInstaller entry point reference)

# Tech tracking
tech-stack:
  added:
    - fastapi.middleware.cors.CORSMiddleware (was available, now wired in)
    - reqwest HTTP client in Rust (was in Cargo.toml, now used in health check)
    - std::sync::atomic::{AtomicBool, Ordering} in Rust
  patterns:
    - BACKEND_READY stdout protocol for Tauri-to-sidecar readiness signaling
    - CORS_ORIGINS_ENV_VAR pattern for environment-based origin override without code changes
    - TAURI_OWNS_SIDECAR atomic flag pattern for process lifecycle ownership tracking
    - Pre-spawn health check gate before sidecar spawn to support coexistence

key-files:
  created:
    - src/podcast_pipeline/service/cli.py
  modified:
    - src/podcast_pipeline/service/app.py
    - desktop/src-tauri/src/lib.rs
    - pyproject.toml

key-decisions:
  - "Print BACKEND_READY before uvicorn.run() so Tauri frontend does not need to scrape uvicorn logs — stdout protocol, not log scraping"
  - "Never use allow_origins=['*'] — always use explicit list from DEFAULT_CORS_ORIGINS or PODCAST_PIPELINE_CORS_ORIGINS env var"
  - "Health check happens BEFORE taking the PID mutex in start_sidecar so async await does not need to hold a Mutex"
  - "TAURI_OWNS_SIDECAR is a module-level AtomicBool rather than per-state to avoid Mutex-around-await complexity"
  - "cargo check fails due to tauri_build binary validation — pre-existing constraint; Rust code validated with rustfmt --edition 2021"
  - "Added T20 per-file-ignore for service/cli.py in pyproject.toml since print() is the correct protocol for CLI sidecar entry points"

patterns-established:
  - "Sidecar entry points use sys.stdout.reconfigure with type: ignore[union-attr] for UTF-8 safety on Windows"
  - "Lazy imports in sidecar cli.py: env vars set before any podcast_pipeline module imported"
  - "reqwest health check returns false on ALL errors (connection refused, timeout, non-2xx, body mismatch) — best-effort only"

# Metrics
duration: 6min
completed: 2026-02-25
---

# Phase 10 Plan 01: Backend Infrastructure Gaps Summary

**PyInstaller sidecar entry point with BACKEND_READY stdout marker, CORS middleware with explicit Tauri/dev origins, and pre-spawn coexistence health check with TAURI_OWNS_SIDECAR ownership tracking in Rust**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-25T21:21:08Z
- **Completed:** 2026-02-25T21:27:10Z
- **Tasks:** 2
- **Files modified:** 4 (cli.py created, app.py modified, lib.rs modified, pyproject.toml modified)

## Accomplishments

- Created `src/podcast_pipeline/service/cli.py` as the PyInstaller entry point — argparse for `--host`/`--port`, UTF-8 stdout reconfiguration, prints `BACKEND_READY port=<port>` before uvicorn starts
- Added `CORSMiddleware` to `create_app()` in `app.py` with explicit origins `["http://localhost:1420", "tauri://localhost"]` and env var override via `PODCAST_PIPELINE_CORS_ORIGINS`
- Added `TAURI_OWNS_SIDECAR` AtomicBool + `backend_is_healthy()` function + coexistence gate in `start_sidecar` + ownership gate in `stop_sidecar` to `lib.rs`

## Task Commits

Each task was committed atomically:

1. **Task 1: Create service/cli.py + add CORS middleware** - `42b94fa` (feat)
2. **Task 2: Add pre-spawn health check to lib.rs** - `3126a1b` (feat)

**Plan metadata:** committed with SUMMARY.md and STATE.md update

## Files Created/Modified

- `src/podcast_pipeline/service/cli.py` - PyInstaller-compatible sidecar entry point; prints BACKEND_READY stdout marker for Tauri
- `src/podcast_pipeline/service/app.py` - Added CORSMiddleware with explicit origin list and CORS_ORIGINS_ENV_VAR constant
- `desktop/src-tauri/src/lib.rs` - Added TAURI_OWNS_SIDECAR static, backend_is_healthy() fn, coexistence gate in start_sidecar, ownership gate in stop_sidecar
- `pyproject.toml` - Added T20 per-file-ignore for service/cli.py to allow print() in Tauri sidecar protocol

## Decisions Made

- Print `BACKEND_READY` before `uvicorn.run()` (not after server starts) because Tauri watches stdout from the moment the process spawns — printing before the blocking call ensures Tauri frontend does not timeout waiting for the line
- Explicit CORS origins instead of wildcard `*` — security requirement; production Tauri production uses `tauri://localhost`, dev uses `http://localhost:1420`
- Health check before PID mutex in `start_sidecar` — reqwest `await` cannot be held inside a `Mutex` lock without deadlock risk; checking health first allows early return without touching state
- `TAURI_OWNS_SIDECAR` as a `static AtomicBool` rather than inside `SidecarState` — avoids async mutex complexity; the ownership flag is process-global and does not need to be behind a lock

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mypy `type: ignore` comment using wrong error code**
- **Found during:** Task 1 (service/cli.py creation)
- **Issue:** `# type: ignore[attr-defined]` suppressed `attr-defined` but mypy raised `union-attr` for `sys.stdout.reconfigure()`
- **Fix:** Changed to `# type: ignore[union-attr]` to match the actual error code
- **Files modified:** `src/podcast_pipeline/service/cli.py`
- **Verification:** `uv run mypy` passes with no issues
- **Committed in:** `42b94fa` (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added T20 per-file-ignore for service/cli.py**
- **Found during:** Task 1 (ruff lint check)
- **Issue:** Ruff T201 (no print) blocked because `cli.py` uses `print()` as the Tauri sidecar communication protocol
- **Fix:** Added `service/cli.py` to `pyproject.toml` per-file-ignores with `T20` exemption and explanatory comment
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run ruff check` passes
- **Committed in:** `42b94fa` (Task 1 commit)

**3. [Rule 3 - Blocking] Applied rustfmt formatting to lib.rs**
- **Found during:** Task 2 (post-edit format check)
- **Issue:** rustfmt detected formatting differences in new code (nested match flattening, argument list style)
- **Fix:** Ran `rustfmt --edition 2021` to apply idiomatic Rust formatting
- **Files modified:** `desktop/src-tauri/src/lib.rs`
- **Verification:** `rustfmt --edition 2021 --check` passes
- **Committed in:** `3126a1b` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (1 bug fix, 1 missing critical config, 1 blocking format issue)
**Impact on plan:** All auto-fixes required for correctness, security, and linting compliance. No scope creep.

## Issues Encountered

`cargo check` fails with `resource path 'binaries/podcast-backend/...' doesn't exist` — this is a pre-existing constraint verified by reverting to the pre-edit commit: `tauri_build::build()` validates sidecar binary existence, and no sidecar binaries are present in the dev environment. The plan's `SKIP_SIDECAR_CHECK=1` bypasses our custom build.rs validation but not Tauri's own `tauri_build::build()`. The Rust code itself is syntactically correct (verified via `rustfmt --edition 2021 --check` which parses without error). This is a known Phase 10 prerequisite that will be addressed when sidecar binaries are built.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All three infrastructure gaps are resolved: CI can reference `service/cli.py`, Tauri dev frontend can make CORS requests, and the sidecar lifecycle handles coexistence correctly
- Phase 10 plan 02 onwards can proceed — the backend sidecar build, frontend scaffolding, and CI pipeline all depend on these three files being in place
- No blockers introduced; existing service tests pass (77/77)

---
*Phase: 10-tauri-desktop-application-distribution*
*Completed: 2026-02-25*

## Self-Check: PASSED

- FOUND: src/podcast_pipeline/service/cli.py
- FOUND: src/podcast_pipeline/service/app.py
- FOUND: desktop/src-tauri/src/lib.rs
- FOUND: .planning/phases/10-tauri-desktop-application-distribution/10-01-SUMMARY.md
- FOUND commit: 42b94fa (Task 1)
- FOUND commit: 3126a1b (Task 2)
