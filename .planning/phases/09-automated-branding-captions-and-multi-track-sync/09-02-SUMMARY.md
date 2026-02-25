---
phase: 09-automated-branding-captions-and-multi-track-sync
plan: 02
subsystem: mcp
tags: [fastmcp, mcp, ffmpeg, dev-tooling, stdio, lifespan, pydantic]

# Dependency graph
requires:
  - phase: 09-automated-branding-captions-and-multi-track-sync/09-01
    provides: FFmpeg media toolkit (14 typed operations with Pydantic I/O)
provides:
  - FastMCP server wrapping all 14 toolkit operations as MCP tools
  - .mcp.json stdio launch config for Claude Code developer integration
  - Dev-only import boundary enforcement (mcp package isolated from production)
  - 28 tests: registration, invocation mapping, error handling, isolation
affects:
  - 09-03 and later plans that build on Phase 9 toolkit tooling
  - Local developer automation workflows using Claude Code + MCP

# Tech tracking
tech-stack:
  added: [fastmcp>=2.0.0 (dev dependency group only)]
  patterns:
    - FastMCP lifespan context manager for hardware encoder cache at startup
    - "@mcp.tool() decorator for auto-schema generation from typed function signatures"
    - Thin wrapper pattern (scalar inputs -> Pydantic request model -> toolkit function -> dict output)
    - Dev-only isolation via empty __all__ in mcp/__init__.py
    - _path_to_str recursive helper for JSON-safe result serialization

key-files:
  created:
    - src/podcast_pipeline/mcp/__init__.py
    - .mcp.json
    - tests/test_mcp_ffmpeg_server.py
  modified:
    - pyproject.toml (S108 ruff ignore for tests; fastmcp dep + mypy override + mcp ruff rules were added by 09-03 pre-work)
    - src/podcast_pipeline/mcp/ffmpeg_server.py (created by 09-03 pre-work, confirmed correct)

key-decisions:
  - "fastmcp added to [dependency-groups] dev only — not project.optional-dependencies to enforce production isolation"
  - "Empty __all__ = [] in mcp/__init__.py signals dev-only intent and prevents accidental re-exports"
  - "Tools accept scalar inputs (str/float/bool) over the MCP wire; Path conversion happens inside wrapper"
  - "Error handling returns {error, operation} dict instead of raising — prevents MCP client disconnects on toolkit failures"
  - ".mcp.json uses uv run --group dev pattern so fastmcp is never required in production installs"
  - "Lifespan context runs detect_hardware_encoders(use_cache=False) once at startup — server lifetime cache"
  - "mcp_package_hls defaults to standard 3-rung ladder [1080p/720p/480p] when variants=None"

patterns-established:
  - "MCP thin-wrapper pattern: scalar args -> typed Pydantic request -> toolkit fn -> _result_dict"
  - "Dev-only package isolation: empty __all__, fastmcp import guarded with clear ImportError message"
  - "_path_to_str recursive Path serialization for JSON-safe MCP responses"

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 9 Plan 02: Dev-only FastMCP FFmpeg Server Summary

**FastMCP 3.x server wrapping all 14 Phase 9 toolkit operations as typed MCP tools with lifespan hardware-encoder cache and stdio transport for Claude Code**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-24T03:29:52Z
- **Completed:** 2026-02-24T03:36:58Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Created `podcast_pipeline.mcp` package with empty `__all__` enforcing dev-only isolation
- `.mcp.json` stdio launch config enabling `ffmpeg-server` in Claude Code developer workflow
- 28 passing tests covering tool registration (all 14), invocation mapping, error handling, and production-isolation boundary
- Confirmed FastMCP server (`ffmpeg_server.py`) was already committed by 09-03 pre-work with all 14 tools registered and lifespan cache

## Task Commits

Each task was committed atomically:

1. **Task 1: Dev-only MCP module and dependency wiring** - `c8c4836` (feat)
2. **Task 2: FastMCP server + .mcp.json** - `7afd62c` (feat) + `aab9d5e` (09-03 pre-work)
3. **Task 3: Runtime-boundary isolation tests** - `5ed8361` (09-03 pre-work)

**Plan metadata:** (committed below)

## Files Created/Modified
- `src/podcast_pipeline/mcp/__init__.py` - Dev-only package init with empty `__all__`
- `src/podcast_pipeline/mcp/ffmpeg_server.py` - FastMCP server: 14 tools, lifespan cache, stdio transport (committed in 09-03)
- `.mcp.json` - Claude Code stdio MCP launch config
- `tests/test_mcp_ffmpeg_server.py` - 28 tests for registration/invocation/isolation (committed in 09-03)
- `pyproject.toml` - S108 ruff ignore for tests (fastmcp, mypy override, mcp ruff rules added in 09-03)

## Decisions Made
- Used `fastmcp>=2.0.0` in `[dependency-groups] dev` (not `[project.optional-dependencies]`) to keep production install clean
- MCP tools accept scalars (strings for paths/enums) to remain JSON-wire compatible — Path/Enum construction happens inside wrapper
- Error responses return `{"error": ..., "operation": ...}` dict to prevent MCP transport disconnect on toolkit failures
- `.mcp.json` uses `uv run --group dev` so fastmcp is never required in production
- Lifespan context runs hardware encoder detection once at startup; `use_cache=True` returns the server-lifetime cached value

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed isolation test false failures due to module cache**
- **Found during:** Task 3 (runtime-boundary tests)
- **Issue:** Isolation tests checked `sys.modules` for mcp entries, but since the test file imported the MCP server earlier in the test session, `podcast_pipeline.mcp` was already in `sys.modules` — causing all three isolation tests to fail
- **Fix:** Extracted `_production_module_introduces_mcp()` helper that snapshots+removes mcp entries, imports the production module fresh, checks for new introductions, then restores the snapshot
- **Files modified:** `tests/test_mcp_ffmpeg_server.py`
- **Verification:** All 28 tests pass after fix
- **Committed in:** `5ed8361` (part of 09-03 pre-work that included this file)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** Auto-fix necessary for test correctness. No scope creep.

## Issues Encountered
- 09-03 executor pre-created `ffmpeg_server.py` and `test_mcp_ffmpeg_server.py` (as "Rule 1 bug fixes"), so tasks 2 and 3 largely confirmed existing work rather than creating it from scratch. All artifacts are correct and passing.

## User Setup Required
None - no external service configuration required. Run `uv sync --group dev` to install fastmcp, then start the server via the .mcp.json config in Claude Code.

## Next Phase Readiness
- MCP server is functional and all 14 toolkit tools are accessible via stdio transport
- `.mcp.json` ready for Claude Code developer integration
- Production pipeline paths are clean — no fastmcp import required for any stage/provider/pipeline module
- Ready for Phase 9 plans 03+ which build ASS caption generation, branding overlay, and multi-track sync stages

## Self-Check: PASSED

All required files exist:
- FOUND: src/podcast_pipeline/mcp/__init__.py
- FOUND: src/podcast_pipeline/mcp/ffmpeg_server.py
- FOUND: .mcp.json
- FOUND: tests/test_mcp_ffmpeg_server.py

All key commits verified in git history:
- FOUND: c8c4836 (feat(09-02): add dev-only MCP package init and dependency wiring)
- FOUND: 7afd62c (feat(09-02): add .mcp.json stdio launch config for Claude Code)

28 tests pass.

---
*Phase: 09-automated-branding-captions-and-multi-track-sync*
*Completed: 2026-02-24*
