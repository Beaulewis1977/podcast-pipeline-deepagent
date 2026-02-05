---
phase: 03-polishing-+-desktop-distribution
plan: 01
subsystem: api
tags: [fastapi, uvicorn, service, sidecar, asyncio, pydantic]

# Dependency graph
requires:
  - phase: existing-core
    provides: Pipeline orchestrator, Job state model, CLI entrypoint
provides:
  - FastAPI service module with job lifecycle HTTP endpoints
  - Background run supervisor with heartbeat metadata
  - CLI service command for sidecar/desktop startup
  - Typed request/response schemas for stable client contract
affects: [03-02, 03-03, 03-04, streamlit-ui, tauri-desktop]

# Tech tracking
tech-stack:
  added: [fastapi, uvicorn]
  patterns: [lifespan-pattern, factory-app, supervisor-heartbeat, runtime-metadata]

key-files:
  created:
    - src/podcast_pipeline/service/__init__.py
    - src/podcast_pipeline/service/app.py
    - src/podcast_pipeline/service/schemas.py
    - src/podcast_pipeline/service/supervisor.py
    - src/podcast_pipeline/service/routes/__init__.py
    - src/podcast_pipeline/service/routes/jobs.py
    - tests/test_service_api.py
  modified:
    - src/podcast_pipeline/cli.py
    - pyproject.toml
    - tests/test_cli.py

key-decisions:
  - "Factory pattern for FastAPI app creation (uvicorn factory=True compatible)"
  - "Supervisor uses asyncio.create_task with run_in_executor for non-blocking pipeline execution"
  - "Runtime metadata persisted as runtime.json alongside state.json for crash recovery"
  - "Duplicate run guard via in-memory task registry with 409 conflict response"
  - "Default service port 8787 to avoid collisions with Streamlit (8501)"

patterns-established:
  - "Lifespan pattern: shared Pipeline/Config/Supervisor on app.state"
  - "Route handler pattern: delegate to Pipeline/Job, translate HTTP concerns only"
  - "Background execution: Supervisor wraps blocking Pipeline.run in executor thread"
  - "Atomic file writes for runtime.json (write tmp then rename)"

# Metrics
duration: 9min
completed: 2026-02-05
---

# Phase 3 Plan 1: FastAPI Job Runner Service Summary

**FastAPI service with job lifecycle endpoints, asyncio background supervision, heartbeat metadata, and CLI sidecar command on port 8787**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-05T20:06:55Z
- **Completed:** 2026-02-05T20:15:34Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments
- Full HTTP API surface for job create/run/status/list/resume with typed Pydantic schemas
- Background run supervision with asyncio tasks, heartbeat persistence, and duplicate run guard
- CLI `service` command suitable for desktop sidecar startup (headless, no interactive prompts)
- 25 passing tests (14 service API + 11 CLI) covering all endpoint contracts

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement FastAPI service surface for job lifecycle** - `cc2ee9e` (feat)
2. **Task 2: Add background run supervision and runtime metadata** - `365c2e2` (feat)
3. **Task 3: Wire CLI entrypoint for backend service mode** - `e29dbfe` (feat)

## Files Created/Modified
- `src/podcast_pipeline/service/__init__.py` - Service package init
- `src/podcast_pipeline/service/app.py` - FastAPI app with lifespan wiring and factory pattern
- `src/podcast_pipeline/service/schemas.py` - Typed request/response models for all endpoints
- `src/podcast_pipeline/service/supervisor.py` - Background run orchestration with heartbeat/crash detection
- `src/podcast_pipeline/service/routes/__init__.py` - Routes package init
- `src/podcast_pipeline/service/routes/jobs.py` - Job lifecycle HTTP handlers (create/run/status/list/resume/background)
- `tests/test_service_api.py` - Contract tests for all service endpoints
- `src/podcast_pipeline/cli.py` - Added `service` command with --host/--port
- `tests/test_cli.py` - Added service help test
- `pyproject.toml` - Added fastapi/uvicorn deps, ruff/mypy config for service module

## Decisions Made
- **Factory pattern for app creation:** Allows uvicorn to instantiate the app via import string with `factory=True`, which is the standard pattern for production ASGI deployment
- **asyncio.create_task + run_in_executor for background runs:** Pipeline.run is synchronous/blocking, so it runs in a thread pool via executor while the async supervisor manages heartbeats
- **runtime.json for crash recovery metadata:** Separate from state.json to avoid coupling pipeline state with process lifecycle data; includes PID, heartbeat timestamp, and status
- **409 Conflict for duplicate runs:** Deterministic HTTP status for clients to detect already-running jobs, with clear error message
- **Port 8787 as default:** Avoids collision with Streamlit default (8501) and common dev server ports

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TestClient fixture override ordering**
- **Found during:** Task 1 (test_jobs_contract_list_empty failure)
- **Issue:** Fixture set app.state before entering TestClient context; lifespan then overwrote with real config pointing to ./jobs directory
- **Fix:** Moved state override to after `with TestClient(app)` context entry so lifespan runs first, then is overridden
- **Files modified:** tests/test_service_api.py
- **Verification:** test_jobs_contract_list_empty passes
- **Committed in:** cc2ee9e (Task 1 commit)

**2. [Rule 3 - Blocking] Fixed mypy type annotation on app.state attribute**
- **Found during:** Task 1 (pre-commit hook failure)
- **Issue:** `app.state.active_runs: dict[str, Any] = {}` is invalid -- cannot declare type on non-self attribute assignment
- **Fix:** Used intermediate local variable with type annotation, then assigned to app.state
- **Files modified:** src/podcast_pipeline/service/app.py
- **Verification:** mypy passes clean
- **Committed in:** cc2ee9e (Task 1 commit)

**3. [Rule 3 - Blocking] Removed unused type: ignore comment**
- **Found during:** Task 1 (pre-commit hook failure)
- **Issue:** `# type: ignore[assignment]` on Pipeline retrieval from app.state was unnecessary
- **Fix:** Removed the comment
- **Files modified:** src/podcast_pipeline/service/routes/jobs.py
- **Verification:** mypy passes clean
- **Committed in:** cc2ee9e (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (1 bug, 2 blocking)
**Impact on plan:** All auto-fixes necessary for correctness and build compliance. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Service module is ready for Streamlit and Tauri integration
- Supervisor heartbeat mechanism ready for crash/restart reconciliation in desktop app
- CLI service command can be used directly by Tauri sidecar launcher
- API contract is stable and documented via FastAPI auto-generated OpenAPI schema at /docs

---
*Phase: 03-polishing-+-desktop-distribution*
*Completed: 2026-02-05*
