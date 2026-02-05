---
phase: 03-polishing-+-desktop-distribution
plan: 02
subsystem: ui
tags: [tauri, rust, react, vite, sidecar, desktop, typescript]

# Dependency graph
requires:
  - phase: 03-polishing-+-desktop-distribution
    plan: 01
    provides: FastAPI service module with CLI sidecar command on port 8787
provides:
  - Tauri v2 desktop workspace with React/Vite frontend
  - Rust sidecar lifecycle commands (start/stop/status) with Mutex-guarded PID tracking
  - Typed TypeScript backend client for health polling and job API calls
  - Desktop shell with backend readiness display and graceful sidecar shutdown
affects: [03-04, 03-05, 03-06, desktop-packaging, desktop-ui-features]

# Tech tracking
tech-stack:
  added: [tauri-v2, tauri-plugin-shell, react-19, vite-6, typescript-5.7, serde, libc]
  patterns: [sidecar-lifecycle, invoke-command, health-readiness-polling, boot-sequence-with-fallback]

key-files:
  created:
    - desktop/package.json
    - desktop/src-tauri/Cargo.toml
    - desktop/src-tauri/tauri.conf.json
    - desktop/src-tauri/capabilities/default.json
    - desktop/src-tauri/src/main.rs
    - desktop/src-tauri/src/lib.rs
    - desktop/src/lib/backend.ts
    - desktop/src/App.tsx
  modified:
    - .gitignore

key-decisions:
  - "Tauri v2 with shell plugin for sidecar management instead of Tauri v1 sidecar API"
  - "Mutex-guarded PID tracking in Rust for sidecar lifecycle state"
  - "CSP allows connect-src to 127.0.0.1:8787 for backend API calls"
  - "Boot sequence with fallback: try sidecar invoke first, fall back to direct health check for dev mode"
  - "externalBin binaries/podcast-backend maps to Python CLI service command"

patterns-established:
  - "Sidecar lifecycle: Rust manages start/stop/status with shared Mutex<Option<u32>> PID"
  - "Backend client pattern: typed TS module with invoke wrappers and fetch helpers"
  - "Boot sequence: startSidecar -> waitForReady (polling) -> connected state"
  - "Health polling: periodic checkHealth calls update React state for status display"

# Metrics
duration: 5min
completed: 2026-02-05
---

# Phase 3 Plan 2: Tauri v2 Desktop Shell Summary

**Tauri v2 desktop workspace with Rust sidecar lifecycle commands, typed TypeScript backend client, and React health-readiness shell on port 8787**

## Performance

- **Duration:** 5 min (finalization of pre-existing work)
- **Started:** 2026-02-05T20:52:37Z
- **Completed:** 2026-02-05T20:57:00Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- Tauri v2 desktop workspace scaffolded with React 19 + Vite 6 frontend and Rust backend
- Sidecar lifecycle control (start/stop/status) implemented in Rust with Mutex-guarded PID tracking and platform-specific termination (SIGTERM on Unix, taskkill on Windows)
- Typed TypeScript backend client with health readiness polling, job CRUD operations, and orchestrated boot sequence
- Desktop shell displays backend connection status, sidecar PID/port, version, and job list with retry/refresh controls

## Task Commits

Each task was committed atomically:

1. **Task 1 + Task 2: Scaffold Tauri workspace and implement sidecar lifecycle** - `1e1e510` (feat)
2. **Task 3: Wire frontend backend client and health handshake** - `098f9d6` (feat)

_Note: Tasks 1 and 2 were committed together as a single scaffold+lifecycle commit._

## Files Created/Modified
- `desktop/package.json` - Workspace config with React 19, Tauri API, shell plugin dependencies
- `desktop/src-tauri/Cargo.toml` - Rust crate with tauri, tauri-plugin-shell, serde, libc dependencies
- `desktop/src-tauri/tauri.conf.json` - App config with CSP, externalBin sidecar, shell plugin scope
- `desktop/src-tauri/capabilities/default.json` - Permissions for shell spawn/execute/kill and URL open
- `desktop/src-tauri/src/main.rs` - Entry point delegating to lib::run()
- `desktop/src-tauri/src/lib.rs` - Rust commands for start_sidecar/stop_sidecar/sidecar_status with shared state
- `desktop/src/lib/backend.ts` - Typed backend client: sidecar invoke, health polling, job API, boot orchestration
- `desktop/src/App.tsx` - React shell with status panel, sidecar display, job list, retry/refresh controls
- `.gitignore` - Scoped lib/ exclusion to root-only (/lib/) so desktop/src/lib/ is tracked

## Decisions Made
- **Tauri v2 with shell plugin:** Uses `tauri-plugin-shell` for sidecar management, which is the Tauri v2 approach replacing the v1 built-in sidecar API
- **Mutex PID tracking:** `Mutex<Option<u32>>` provides thread-safe sidecar PID tracking with idempotent start (returns existing status if already running)
- **CSP for backend calls:** `connect-src 'self' http://127.0.0.1:8787` explicitly permits fetch to local backend from Tauri webview
- **Boot fallback for dev mode:** When `invoke("start_sidecar")` fails (running outside Tauri context during development), falls back to direct health check against already-running backend
- **externalBin naming:** `binaries/podcast-backend` matches the CLI service command that the Python package provides via `uv run podcast-pipeline service`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Scoped .gitignore lib/ exclusion to root-only**
- **Found during:** Task 3 (backend.ts not tracked)
- **Issue:** Root `.gitignore` had `lib/` which matched `desktop/src/lib/`, preventing the new backend client from being tracked by git
- **Fix:** Changed `lib/` to `/lib/` and `lib64/` to `/lib64/` to scope exclusion to project root only
- **Files modified:** .gitignore
- **Verification:** `git add desktop/src/lib/backend.ts` succeeds
- **Committed in:** 098f9d6 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to allow git to track the new lib/ directory under desktop/src/. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviation above.

## User Setup Required
None - no external service configuration required. Desktop development requires pnpm and Rust toolchain (rustc, cargo) which are standard developer tools.

## Next Phase Readiness
- Desktop shell is functional and ready for additional UI features (job creation, pipeline monitoring)
- Sidecar lifecycle is wired and ready for bundled distribution testing
- Backend client provides typed API for all current service endpoints (health, jobs CRUD)
- externalBin configuration ready for platform-specific binary bundling in future packaging plan

---
*Phase: 03-polishing-+-desktop-distribution*
*Completed: 2026-02-05*
