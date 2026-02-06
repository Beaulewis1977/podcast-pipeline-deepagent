# Project State: Podcast Pipeline

**Last updated:** 2026-02-05
**Current phase:** All phases complete
**Overall progress:** 100%

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Turn raw podcast recording into multi-platform content without editing software or manual copywriting.
**Current focus:** All 3 phases complete. Milestone v1.0 ready to close.

## Current Position

```
Phase:    3 of 3 (all complete)
Plan:     17 of 17 total plans
Status:   All phases complete
Last activity: 2026-02-05 - Phase 3 complete, Gemini model fix

Progress: [████████████████████████] 100% (17/17 plans)
```

## Phase Status

| Phase | Name | Status | Plans | Progress |
|------:|------|--------|-------|----------|
| 1 | Wiring + Stability | Complete | 6/6 | 100% |
| 2 | Research + Viral Integration | Complete | 5/5 | 100% |
| 3 | Polishing + Desktop Distribution | Complete | 6/6 | 100% |

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 17 |
| Requirements done | 35/83 (21 partial) |
| Phases complete | 3/3 |
| Estimated completion | Complete |

## Accumulated Context

### Key Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| Streamlit-first UI | Fastest path to validate workflow | 2026-02-03 |
| Desktop follow-up (Rust + Tauri v2) | Better distribution + performance | 2026-02-03 |
| Hide progress UI unless progress data exists | Avoid noisy empty UI when stages haven't reported progress | 2026-02-04 |
| Fallback to single-track transcription when only one stream exists | Prevents recursion and preserves current behavior | 2026-02-04 |
| Use Fraction-based FPS parsing to avoid eval | Removes unsafe eval in ffprobe metadata handling | 2026-02-04 |
| Derive research query from analysis topics, fallback to job name | Ensures research runs even when topics are sparse | 2026-02-04 |
| Use review/edit_plan.json as render input | Keeps render and clip exports aligned with review decisions | 2026-02-04 |
| Apply edit-plan cuts via trim/concat filter_complex | Ensures render output respects approved cuts | 2026-02-04 |
| Competition score bounded to 0-100 using normalized weighted factors | Keeps topic difficulty stable and comparable for ranking/UI consumers | 2026-02-04 |
| Posting recommendations emitted as UTC windows + weekday distributions | Deterministic structure for cross-timezone rendering and tests | 2026-02-04 |
| Engagement density uses weighted signal strength/minute with diversity bonus | Rewards clips with sustained multi-signal momentum instead of isolated spikes | 2026-02-04 |
| Detector reasons explicitly mention question/controversy/story-arc/quotable cues | Keeps clip ranking changes interpretable in artifacts and UI | 2026-02-04 |
| YouTube search/stat calls use normalized TTL cache keys | Reduces repeated quota consumption across identical analyze runs | 2026-02-04 |
| Keyword ranking is phrase-first (weighted n-grams) with stopword filtering | Surfaces reusable title/thumbnail phrases over weak unigram noise | 2026-02-04 |
| Analyze clip ranking blends AI (45%) and detector (55%) scores | Prioritizes transcript-level evidence while retaining provider signal | 2026-02-04 |
| Viral artifact rows remain backward-compatible via additive score fields | UI can adopt richer metrics incrementally without breaking old readers | 2026-02-04 |
| Insight panels use pure data transformers before rendering | Keeps schema handling testable and resilient to partial artifacts | 2026-02-04 |
| UI clip table always sorts by combined score with legacy fallbacks | Maintains ranking consistency across new and old artifact shapes | 2026-02-04 |
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

- (None)

### Blockers

- (None)

## Recent Activity

- 2026-01-29: Project initialized, requirements defined, roadmap created
- 2026-02-03: App research report completed
- 2026-02-04: Codebase map refreshed and planning docs updated
- 2026-02-04: Completed Phase 2 plans 02-01 through 02-05
- 2026-02-04: Verified Phase 2 goal (10/10 must-haves passed)
- 2026-02-05: Completed 03-01 through 03-06 (Phase 3 complete)
- 2026-02-05: Fixed Gemini model name (gemini-2.5-flash-latest -> gemini-2.5-flash)
- 2026-02-05: End-to-end smoke test passed (ingest -> transcribe -> analyze -> review)

## Session Continuity

### Last session

Completed Phase 3, fixed Gemini model name, ran successful end-to-end smoke test through Streamlit UI. All 3 phases now complete.

### Stopped at

All phases complete. Milestone v1.0 ready to close or extend.

### Resume file

None

---

*State updated: 2026-02-05*
