---
phase: 03-polishing-+-desktop-distribution
plan: 03
subsystem: ui
tags: [streamlit, httpx, pydantic, service-client, regression-tests]

# Dependency graph
requires:
  - phase: 03-polishing-+-desktop-distribution/01
    provides: FastAPI service with job lifecycle endpoints and typed schemas
provides:
  - Typed HTTP service client for Streamlit, desktop, and test consumers
  - Streamlit UI actions routed through ServiceClient instead of direct Pipeline calls
  - ServiceConfig in project settings for configurable backend connection
  - Regression test suite covering success, failure, and backend-unavailable paths
affects: [03-04, 03-05, 03-06, tauri-desktop, streamlit-ui]

# Tech tracking
tech-stack:
  added: [httpx]
  patterns: [typed-client-per-service, transport-backed-test-client, session-state-cached-client]

key-files:
  created:
    - src/podcast_pipeline/clients/__init__.py
    - src/podcast_pipeline/clients/service_client.py
    - tests/test_streamlit_service_client.py
  modified:
    - src/podcast_pipeline/config/settings.py
    - src/podcast_pipeline/config/__init__.py
    - src/podcast_pipeline/ui/app.py
    - pyproject.toml

key-decisions:
  - "httpx with retry transport for typed HTTP client (sync, short-lived per request)"
  - "ServiceConfig added to Config model for single source of backend connection settings"
  - "Streamlit caches ServiceClient in session_state, constructed from Config.service"
  - "Display-only operations (analysis/review files) still read local filesystem directly"

patterns-established:
  - "Typed client pattern: Pydantic response models mirror backend schemas, typed exceptions for transport vs contract errors"
  - "Test transport bridging: monkey-patch ServiceClient._client to use ASGI TestClient transport for zero-network tests"
  - "Service error hierarchy: ServiceError > ServiceUnavailableError (transport) / ServiceResponseError (HTTP status)"

# Metrics
duration: ~12min
completed: 2026-02-05
---

# Phase 3 Plan 3: Streamlit Service Migration Summary

**Typed httpx service client with Pydantic response models routing all Streamlit job actions through the FastAPI backend, with 28 regression tests covering contract, retry, and UI helper paths**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-02-05
- **Completed:** 2026-02-05
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- Typed HTTP client (`ServiceClient`) covering full job lifecycle: health, create, get, list, run, run/background, resume
- Streamlit UI completely decoupled from direct `Pipeline` import -- all job operations route through `ServiceClient`
- `ServiceConfig` model added to project `Config` with host/port/timeout/retries and computed `base_url` property
- 28 regression tests: 11 client contract tests, 4 retry/unavailable behavior tests, 4 ServiceConfig integration tests, 9 Streamlit action helper tests including a source-level assertion that Pipeline is not directly imported

## Task Commits

Each task was committed atomically:

1. **Task 1: Add typed Streamlit backend service client** - `568bd24` (feat)
2. **Task 2: Refactor Streamlit actions to use service client** - `bf8976a` (feat)
3. **Task 3: Add service-mode compatibility and regression tests** - `f43ba7f` (test)

## Files Created/Modified
- `src/podcast_pipeline/clients/__init__.py` - Clients package init
- `src/podcast_pipeline/clients/service_client.py` - Typed HTTP client with Pydantic response models, retry transport, and typed exception hierarchy
- `src/podcast_pipeline/config/settings.py` - Added `ServiceConfig` model and wired into root `Config`
- `src/podcast_pipeline/config/__init__.py` - Re-exported `ServiceConfig` from config package
- `src/podcast_pipeline/ui/app.py` - Refactored all job operations (create, run, list, status, stage execution) to use `ServiceClient`; removed direct Pipeline import; added service status indicator and backend-unavailable error messages
- `tests/test_streamlit_service_client.py` - Full regression suite: client contract, retry behavior, config integration, and Streamlit action helper tests
- `pyproject.toml` - Added httpx dependency

## Decisions Made
- **httpx with short-lived clients:** Each request creates a fresh `httpx.Client` with configured timeout and retry transport. Avoids connection pooling complexity for the low-request-volume Streamlit use case while keeping retries deterministic.
- **ServiceConfig on root Config:** Single source of truth for backend connection settings, shared by Streamlit and desktop. Avoids scattered hardcoded URLs.
- **Display-only reads remain local:** Streamlit and the backend share the same `jobs/` directory on the local machine, so reading analysis/review JSON files directly avoids unnecessary round-trips through the API for read-only display data.
- **Source-level import assertion in tests:** `test_streamlit_actions_no_direct_pipeline_import` inspects the module source to enforce the architectural constraint that the UI layer must not directly import Pipeline.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Service client is ready for Tauri desktop frontend to reuse the same typed API
- Streamlit and desktop now share identical backend contract, enabling simultaneous development
- `ServiceConfig` is configurable via `config.yaml` for non-default host/port deployments
- Regression suite provides safety net for future service contract changes

---
*Phase: 03-polishing-+-desktop-distribution*
*Completed: 2026-02-05*
