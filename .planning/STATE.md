# Project State: Podcast Pipeline

**Last updated:** 2026-02-05
**Current phase:** Phase 3 (Polishing + Desktop Distribution) -- COMPLETE
**Overall progress:** 100% (Phases 1 + 3)

## Project Reference

See: .planning/PROJECT.md

**Core value:** Turn raw podcast recording into multi-platform content without editing software or manual copywriting
**Current focus:** Phase 3 complete. Phase 2 (Research + Viral Integration) pending.

## Current Position

```
Phase:    Phase 3 of 3 (Polishing + Desktop Distribution)
Plan:     6 of 6 in phase
Status:   Phase complete
Last activity: 2026-02-05 - Completed 03-06-PLAN.md

Progress: [████████████████████████] 100% (12/12 plans)
```

## Phase Status

| Phase | Name | Status | Plans | Progress |
|------:|------|--------|-------|----------|
| 1 | Wiring + Stability | Complete | 6/6 | 100% |
| 2 | Research + Viral Integration | Pending | 0/? | 0% |
| 3 | Polishing + Desktop Distribution | Complete | 6/6 | 100% |

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 12 |
| Requirements done | 35/83 (21 partial) |
| Phases complete | 2/3 |
| Estimated completion | Unknown |

## Accumulated Context

### Key Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| Streamlit-first UI | Fastest path to validate workflow | 2026-02-03 |
| Desktop follow-up (Rust + Tauri v2) | Better distribution + performance | 2026-02-03 |
| Factory pattern for FastAPI app | uvicorn factory=True compatible, standard ASGI deployment | 2026-02-05 |
| asyncio supervisor for background runs | Pipeline.run is blocking; executor thread + async heartbeat | 2026-02-05 |
| runtime.json for crash recovery | Separate from state.json to decouple process lifecycle from pipeline state | 2026-02-05 |
| Port 8787 as default service port | Avoids collision with Streamlit (8501) and common dev ports | 2026-02-05 |
| httpx for typed service client | Sync + async, built-in retry transport, context-managed clients | 2026-02-05 |
| ServiceConfig in project Config | Single source of truth for backend connection shared by all frontends | 2026-02-05 |
| Display-only reads stay local FS | Streamlit and service share jobs/ dir; no redundant GET endpoints needed | 2026-02-05 |
| Tauri v2 with shell plugin for sidecar | Tauri v2 approach replaces v1 built-in sidecar API | 2026-02-05 |
| Mutex PID tracking in Rust | Thread-safe sidecar lifecycle with idempotent start | 2026-02-05 |
| Tiered binary resolution (env/sidecar/PATH) | Avoids hardcoded OS paths; supports dev and bundled modes transparently | 2026-02-05 |
| Conservative recovery reconciliation | Never touch completed stages; only correct stale running states | 2026-02-05 |
| Three-stage release workflow | build-backend -> build-desktop -> smoke-test for failure isolation | 2026-02-05 |
| PyInstaller for backend sidecar | Single-file cross-platform binary from Python service | 2026-02-05 |
| Graduated smoke severity | Blocking checks (artifact/size/sidecar) vs warnings (health/ffmpeg) | 2026-02-05 |
| Draft releases by default | Manual review before publishing to avoid broken releases | 2026-02-05 |

### Technical Notes

- Recommended stack: FFmpeg, faster-whisper, Streamlit, Typer, Pydantic
- Primary AI: Gemini (configurable; default gemini-2.5-flash) with Kimi K2.5 fallback
- Avoid: moviepy, python-ffmpeg wrappers, original whisper, langchain
- FastAPI service: lifespan pattern with Pipeline/Config/Supervisor on app.state
- Background runs: Supervisor wraps Pipeline.run in asyncio executor thread
- Asset resolution: env -> sidecar dir -> system PATH for binaries
- Model cache: env -> app_data -> project -> HF hub for model artifacts
- Sidecar naming: prepare-sidecars.mjs maps Node.js platform/arch to Rust target triples
- Release workflow: tag-triggered with manual dispatch, 4 platform targets

### Open Questions

- (None yet)

### Blockers

- (None)

## Recent Activity

- 2026-01-29: Project initialized
- 2026-01-29: Requirements defined
- 2026-01-29: Roadmap created
- 2026-02-03: App research report completed
- 2026-02-04: Codebase map refreshed and planning docs updated
- 2026-02-05: Completed 03-01 - FastAPI job runner service
- 2026-02-05: Completed 03-02 - Tauri v2 desktop app scaffold
- 2026-02-05: Completed 03-03 - Streamlit service migration
- 2026-02-05: Completed 03-04 - Asset packaging and runtime resolution
- 2026-02-05: Completed 03-05 - Crash recovery and resume
- 2026-02-05: Completed 03-06 - Installer matrix and smoke validation (Phase 3 complete)

## Session Continuity

### Last Session Summary

Completed 03-06: Created cross-platform release workflow (GitHub Actions with Tauri action), smoke test scripts (bash + PowerShell) for post-build validation, and distribution runbook covering signing, troubleshooting, and manual release. Phase 3 is now fully complete.

### Next Session Entry Point

Phase 3 complete. Next step: plan Phase 2 (Research + Viral Integration) or complete milestone.

### Files Modified This Session

- .github/workflows/desktop-release.yml (release workflow)
- desktop/scripts/smoke-test-desktop.sh (Linux/macOS smoke test)
- desktop/scripts/smoke-test-desktop.ps1 (Windows smoke test)
- docs/desktop-distribution.md (distribution runbook)
- README.md (desktop distribution section)

---

*State updated: 2026-02-05*
