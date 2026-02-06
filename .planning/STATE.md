# Project State: Podcast Pipeline

**Last updated:** 2026-02-05
**Current phase:** Phase 3 (Polishing + Desktop Distribution)
**Overall progress:** 83%

## Project Reference

See: .planning/PROJECT.md

**Core value:** Turn raw podcast recording into multi-platform content without editing software or manual copywriting
**Current focus:** Phase 3 - Polishing + Desktop Distribution

## Current Position

```
Phase:    Phase 3 of 3 (Polishing + Desktop Distribution)
Plan:     5 of 6 in phase
Status:   In progress
Last activity: 2026-02-05 - Completed 03-05-PLAN.md

Progress: [██████████████████████░░] 92% (11/12 plans)
```

## Phase Status

| Phase | Name | Status | Plans | Progress |
|------:|------|--------|-------|----------|
| 1 | Wiring + Stability | Complete | 6/6 | 100% |
| 2 | Research + Viral Integration | Pending | 0/? | 0% |
| 3 | Polishing + Desktop Distribution | In progress | 5/6 | 83% |

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 11 |
| Requirements done | 35/83 (21 partial) |
| Phases complete | 1/3 |
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
| Boot fallback for dev mode | invoke fails outside Tauri context; fall back to direct health check | 2026-02-05 |
| Tiered binary resolution (env/sidecar/PATH) | Avoids hardcoded OS paths; supports dev and bundled modes transparently | 2026-02-05 |
| SKIP_SIDECAR_CHECK for dev iteration | Build.rs validation escape hatch during development | 2026-02-05 |
| In-memory model download tracking | Ephemeral warmup status; no persistent queue needed | 2026-02-05 |
| Conservative recovery reconciliation | Never touch completed stages; only correct stale running states | 2026-02-05 |

### Technical Notes

- Recommended stack: FFmpeg, faster-whisper, Streamlit, Typer, Pydantic
- Primary AI: Gemini (configurable; default gemini-2.5-flash) with Kimi K2.5 fallback
- Avoid: moviepy, python-ffmpeg wrappers, original whisper, langchain
- FastAPI service: lifespan pattern with Pipeline/Config/Supervisor on app.state
- Background runs: Supervisor wraps Pipeline.run in asyncio executor thread
- Asset resolution: env -> sidecar dir -> system PATH for binaries
- Model cache: env -> app_data -> project -> HF hub for model artifacts
- Sidecar naming: prepare-sidecars.mjs maps Node.js platform/arch to Rust target triples

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
- 2026-02-05: Completed 03-01 - FastAPI job runner service with background supervision and CLI entrypoint
- 2026-02-05: Completed 03-02 - Tauri v2 desktop app scaffold with sidecar lifecycle
- 2026-02-05: Completed 03-03 - Streamlit service migration with typed service client and regression tests
- 2026-02-05: Completed 03-04 - Asset packaging with sidecar preparation, runtime resolver, and system endpoints
- 2026-02-05: Completed 03-05 - Crash recovery and resume across backend, desktop, and Streamlit

## Session Continuity

### Last Session Summary

Completed 03-05: Implemented crash recovery with backend reconciliation, desktop startup recovery hooks (Rust + TypeScript), and Streamlit resume entrypoint. Fixed Tauri v2 compilation issue (pub commands in lib.rs).

### Next Session Entry Point

Execute 03-06-PLAN.md (final plan in Phase 3 - release workflow).

### Files Modified This Session

- src/podcast_pipeline/service/recovery.py (reconciliation logic)
- desktop/src-tauri/src/recovery.rs (Tauri recovery commands)
- desktop/src/lib/recovery.ts (frontend recovery client)
- desktop/src/App.tsx (recovery banner UI)
- desktop/src-tauri/src/lib.rs (fixed pub commands, added recovery module)
- desktop/src-tauri/Cargo.toml (added reqwest, fixed crate-type)
- desktop/src-tauri/tauri.conf.json (removed invalid app.title)
- src/podcast_pipeline/ui/app.py (Streamlit resume entrypoint)
- tests/test_job_recovery.py (28 recovery regression tests)

---

*State updated: 2026-02-05*
