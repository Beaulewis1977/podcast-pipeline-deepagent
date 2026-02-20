# Project State: Podcast Pipeline

**Last updated:** 2026-02-20
**Current phase:** Phase 6 complete (verified)
**Overall progress:** 100.0% (36/36 plans complete)

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Turn raw podcast recording into multi-platform content without editing software or manual copywriting.
**Current focus:** Phase 6 is complete and verified; v1.0 milestone is ready for audit/closeout.

## Current Position

```text
Phase:    6 complete (all planned phases complete)
Plan:     3/3 complete in Phase 6; 36 completed overall
Status:   Phase 6 execution + verification complete
Last activity: 2026-02-20 - Verified Phase 6 (9/9 must-haves passed)

Progress: [█████████████████████████] 100.0% (36/36 plans complete)
```

**Next Phase:** None (roadmap phases complete; proceed to milestone audit)

## Phase Status

| Phase | Name | Status | Plans | Progress |
|------:|------|--------|-------|----------|
| 1 | Wiring + Stability | Complete | 6/6 | 100% |
| 2 | Research + Viral Integration | Complete | 5/5 | 100% |
| 3 | Polishing + Desktop Distribution | Complete | 6/6 | 100% |
| 4 | Post-release hardening | Human verification needed | 10/10 | 100% |
| 5 | Video Podcast Platforms | Complete (verified) | 3/3 | 100% |
| 5.1 | Streamlit Video Platform UI | Complete (verified) | 3/3 | 100% |
| 6 | Audio/Video Enhancement & Podcast Video Platform | Complete (verified) | 3/3 | 100% |

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 36/36 |
| Requirements done | 35/83 (21 partial) |
| Phases complete | 6/6 |
| Estimated completion | In progress |

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
| Use stdlib O_EXCL lock files for job-scoped run exclusivity | Avoids new dependencies while enforcing deterministic same-job concurrency guardrails | 2026-02-13 |
| Validate stage names in job mutation APIs | Prevents invalid stage keys from corrupting canonical state transitions | 2026-02-13 |
| Reload job state from disk before each stage dispatch | Prevents stale in-memory state from overwriting newer persisted job state | 2026-02-13 |
| Reject zero-duration/overlapping filler-content cuts at model boundary | Prevents render-time silent cleanup and forces malformed edit plans to fail early | 2026-02-13 |
| Enforce string↔seconds timestamp consistency in analysis models with 1s tolerance | Stops contradictory clip/cut timestamps from propagating into downstream ranking/render logic | 2026-02-13 |
| Validate provider-model compatibility and safe service host/port in config models | Prevents invalid runtime configuration from reaching service/client startup paths | 2026-02-13 |
| Run/resume schemas enforce typed stage windows with explicit started/completed/rejected outcomes | Keeps API responses truthful and invalid stage inputs as structured 422 errors | 2026-02-13 |
| Resume defaults to continuation through final stage unless until_stage is provided | Aligns operational behavior with user expectation for one-call recovery continuation | 2026-02-13 |
| Service client uses persistent HTTPX client plus endpoint-specific run/resume timeouts and typed HTTP status exceptions | Preserves backend parity while improving resilience for long-running pipeline requests | 2026-02-13 |
| Provider parse/schema failures raise explicit typed errors with structured details | Prevents silent empty-analysis "success" payloads and preserves actionable diagnostics | 2026-02-13 |
| Analyze outputs embed metadata.degraded_mode for transcript-only provider execution | Makes fallback degradation explicit to operators and downstream artifact consumers | 2026-02-13 |
| Gemini upload IDs are reused per proxy path with structured 429 classification | Reduces repeated upload overhead and keeps retry semantics deterministic/testable | 2026-02-13 |
| Production mode enforces API key auth on /jobs endpoints with explicit development bypass controls | Protects job-control surface in production while preserving local developer ergonomics | 2026-02-13 |
| Global exception handlers sanitize unhandled and HTTP 5xx responses to internal_error payloads | Prevents stack traces and internal error strings from leaking to API clients | 2026-02-13 |
| Supervisor runtime metadata records timeout state and infers last_known_stage from persisted job state | Makes hung/background progression observable and recoverable from runtime journal data | 2026-02-13 |
| Lifespan-managed periodic reconciliation plus /system/runtime diagnostics monitor stale/orphaned runs | Provides proactive correction and operator visibility between manual recovery calls | 2026-02-13 |
| Persist uploads in jobs/_uploads before service create_job | Keeps pipeline/service as source of truth for job directory lifecycle and removes orphan pre-job directories | 2026-02-13 |
| Streamlit preview/timeline metadata source is intermediate/metadata.json with logged legacy fallback | Aligns UI duration/timestamp reads with ingest outputs while preserving backward compatibility | 2026-02-13 |
| Marketing save/regenerate persists via review_state and analyze→review regeneration | Preserves review-governed editorial audit trail and avoids direct analysis.json mutation | 2026-02-13 |
| Render stage now reports explicit degraded/failed outcomes with per-platform status maps | Prevents hidden partial export failures from being reported as generic success | 2026-02-13 |
| Quality controls flow through run payload schemas into persisted job config and render runtime settings | Converts Streamlit quality widgets from display-only state into effective encoding behavior | 2026-02-13 |
| Ingest/render now enforce disk preflight and post-FFmpeg output existence checks | Fails early on low-capacity conditions and loudly on missing/empty artifacts | 2026-02-13 |
| Render enhancement chain is FFmpeg-native with explicit loudnorm fallback behavior | Keeps output quality deterministic even when optional normalization dependencies are unavailable | 2026-02-13 |
| Research query derivation uses deterministic metadata+transcript weighting with explicit fallback source labels | Prevents weak filename defaults from silently driving research quality | 2026-02-13 |
| YouTube API cache persistence is opt-in via cache_path with TTL pruning on load/lookup | Reduces repeated quota spikes across restarts without forcing global cache side effects | 2026-02-13 |
| Desktop lifecycle controls route through typed backend methods including service-backed delete actions | Converts desktop from monitor-only surface into full operator control plane | 2026-02-13 |
| Streamlit timeline edits persist as validated range edits into regenerated review/edit_plan artifacts | Enables true editorial timeline control instead of checkbox-only cut approvals | 2026-02-13 |
| Recovery UX surfaces /system/runtime diagnostics with on-demand /jobs/reconcile actions across desktop and Streamlit | Makes stale/orphaned runtime state visible and operator-actionable without filesystem inspection | 2026-02-13 |
| Coverage gates now require 45% overall plus providers/service/stages module thresholds | Strengthens runtime regression protection while keeping thresholds realistic for fixture-heavy media paths | 2026-02-13 |
| Operator docs now codify service auth headers, resume-through-completion, degraded-mode, and quality-control contracts | Keeps desktop/Streamlit/API behavior truthful for manual operations and incident response | 2026-02-13 |
| Review/CLI/UI export target keys are normalized from one canonical registry with default fallback safeguards | Prevents cross-surface platform key drift and malformed review-state payloads from silently changing render behavior | 2026-02-20 |
| Explicit CLI platform-key errors fail fast before review mutation while omitted input keeps stable defaults | Preserves operator safety for explicit input and backward compatibility for legacy default approve flows | 2026-02-20 |
| Enhancement defaults keep deesser enabled with conservative tuning while dereverb/color stay opt-in | Improves baseline quality without forcing heavyweight dependencies or surprising output changes | 2026-02-20 |
| Render preflight derives required FFmpeg filters from enabled enhancement toggles | Fails fast with actionable diagnostics before expensive render runs | 2026-02-20 |
| Dereverb preprocessing uses optional noisereduce with policy-driven warn-skip/fail fallback | Keeps baseline installs stable while supporting opt-in enhancement depth | 2026-02-20 |
| Color correction is limited to canonical normalize/grayworld/optional-eq filters | Avoids undocumented FFmpeg filter drift and keeps enhancement scope additive | 2026-02-20 |

### Roadmap Evolution

- Phase 4 added: Post-release hardening
- Phase 4 planned: research complete + 10 plan files created
- Phase 4 execution started: completed 04-01 runtime invariants hardening
- Phase 4 execution continued: completed 04-04 model/config validation hardening
- Phase 4 execution continued: completed 04-02 run/resume contract hardening
- Phase 4 execution continued: completed 04-05 provider reliability hardening
- Phase 4 execution continued: completed 04-06 service runtime hardening (auth gate + timeout heartbeats + reconciliation diagnostics)
- Phase 4 execution continued: completed 04-03 UI truthfulness hardening (full-run semantics + metadata path fix + review-governed marketing flow)
- Phase 4 execution continued: completed 04-07 render truthfulness and quality wiring hardening (platform failure contract + quality payload wiring + preflight/output checks)
- Phase 4 execution continued: completed 04-08 output quality backbone hardening (render enhancement + thumbnail artifacts + transcript-grounded research query/cache hardening)
- Phase 4 execution continued: completed 04-09 operator UX hardening (desktop full lifecycle controls, Streamlit timeline range editing, cross-surface recovery diagnostics + reconcile controls)
- Phase 4 execution completed: finished 04-10 confidence gates and docs alignment (provider reliability regressions, stronger coverage policy, runtime contract documentation)
- Phase 5 added: Video Podcast Platforms
- Phase 5 execution started: completed 05-01 platform defaults and fail-fast schema validation for spotify/apple video targets
- Phase 5 execution continued: completed 05-02 render compliance wiring and truthful failure contracts
- Phase 5 execution completed: finished 05-03 apple_hls packaging and platform workflow-boundary documentation
- Phase 5 verified: 9/9 must-haves passed with no structural gaps
- Phase 5.1 execution started: completed 05.1-01 canonical export-target registry + review normalization contract
- Phase 5.1 execution continued: completed 05.1-02 Streamlit export UI wiring + normalized persistence/guidance coverage
- Phase 5.1 execution completed: finished 05.1-03 CLI approval parity + invalid-key diagnostics coverage
- Phase 5.1 verified: 9/9 must-haves passed with no structural gaps
- Phase 6 added: Audio/Video Enhancement & Podcast Video Platform
- Phase 6 researched: created `06-RESEARCH.md` with current stack/pitfalls and source-backed corrections (canonical FFmpeg color/de-esser filters, Demucs de-scoped)
- Phase 6 planned: created 3 execution plans (`06-01` config+preflight, `06-02` audio enhancements, `06-03` color correction) with enhancement-only boundary; crossfade/edit-core work deferred to future Phase 7
- Phase 6 execution started: completed 06-01 config contract + FFmpeg capability preflight + scope guardrails
- Phase 6 execution continued: completed 06-02 de-esser/adeclick integration + optional noisereduce dereverb path
- Phase 6 execution completed: finished 06-03 canonical color correction chain + safety boundary regressions
- Phase 6 verified: 9/9 must-haves passed with no structural gaps

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
- 2026-02-12: Added Phase 4 (Post-release hardening) to roadmap
- 2026-02-12: Planned Phase 4 with integrated research and 10 execution plans
- 2026-02-13: Completed 04-01-PLAN.md (stage validation + per-job lock + state reload)
- 2026-02-13: Completed 04-04-PLAN.md (strict model/config invariants + dedicated validation suites)
- 2026-02-13: Completed 04-02-PLAN.md (typed run/resume contracts + continuation semantics + service client parity hardening)
- 2026-02-13: Completed 04-05-PLAN.md (provider parse failure hardening + degraded fallback signaling + Gemini upload/retry reliability tests)
- 2026-02-13: Completed 04-06-PLAN.md (production auth gate + sanitized errors + supervisor timeout heartbeat + periodic reconciliation diagnostics)
- 2026-02-13: Completed 04-03-PLAN.md (truthful full-run UI action, canonical metadata/timeline loading, review-governed marketing save/regenerate flow)
- 2026-02-13: Completed 04-07-PLAN.md (render truthful partial-failure semantics, quality-control run payload wiring, ingest/render preflight and artifact verification guardrails)
- 2026-02-13: Completed 04-08-PLAN.md (concrete render enhancement + thumbnail artifacts, transcript-grounded research query derivation, persistent TTL cache restart behavior)
- 2026-02-13: Completed 04-09-PLAN.md (desktop full lifecycle control plane, validated timeline edit persistence, runtime diagnostics/reconcile controls in desktop + Streamlit)
- 2026-02-13: Completed 04-10-PLAN.md (provider reliability regressions, raised coverage gates, and runtime contract docs alignment)
- 2026-02-19: Added Phase 5 (Video Podcast Platforms) to roadmap for upcoming planning/execution
- 2026-02-19: Completed 05-01-PLAN.md (video-target defaults, compliance schema validation, and regression coverage)
- 2026-02-19: Completed 05-02-PLAN.md (render profile/level wiring, ffprobe compliance gates, structured compliance status reporting)
- 2026-02-19: Completed 05-03-PLAN.md (typed apple_hls config, deterministic playlist/segment checks, and truthful Apple/Spotify workflow docs)
- 2026-02-19: Verified Phase 5 goal (05-video-podcast-platforms-VERIFICATION.md, status: passed)
- 2026-02-20: Completed 05.1-01-PLAN.md (canonical export target registry, review-state normalization, and fallback regression coverage)
- 2026-02-20: Completed 05.1-02-PLAN.md (registry-driven Streamlit export options, normalized review-state persistence, and apple_hls boundary guidance tests)
- 2026-02-20: Completed 05.1-03-PLAN.md (CLI platform-key normalization, explicit invalid-key error contracts, and parsing regressions)
- 2026-02-20: Verified Phase 5.1 goal (05.1-streamlit-video-platform-ui-VERIFICATION.md, status: passed)
- 2026-02-20: Researched Phase 6 implementation approach and captured findings in `06-RESEARCH.md`
- 2026-02-20: Planned Phase 6 into three executable plans (`06-01`..`06-03`) with strict enhancement-only scope
- 2026-02-20: Completed 06-01-PLAN.md (typed enhancement config, FFmpeg capability preflight, and scope-boundary guardrails)
- 2026-02-20: Completed 06-02-PLAN.md (FFmpeg-native de-esser/adeclick chain and optional noisereduce dereverb fallback path)
- 2026-02-20: Completed 06-03-PLAN.md (canonical normalize/grayworld color correction path with bounded config defaults and safety regressions)
- 2026-02-20: Verified Phase 6 goal (06-audio-video-enhancement-podcast-video-platform-VERIFICATION.md, status: passed)

## Session Continuity

### Last session

2026-02-20 03:39 UTC — Verified `06-audio-video-enhancement-podcast-video-platform` goal (passed, 9/9 must-haves).

### Stopped at

Completed `06-audio-video-enhancement-podcast-video-platform-VERIFICATION.md`; next action is milestone audit/closeout.

### Resume file

None

---

*State updated: 2026-02-20*
