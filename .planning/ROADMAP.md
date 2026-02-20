# Roadmap: Podcast Pipeline

**Created:** 2026-01-29
**Last Updated:** 2026-02-20
**Milestone:** v1.0 (Streamlit-first)
**Phases:** 6 + follow-ups 5.1 and 6.1

## Overview

The repository already contains a working pipeline skeleton (ingest → transcribe → analyze → review → render) plus a Streamlit UI. The roadmap now focuses on wiring the existing stages end-to-end, eliminating stubs, and producing real edited outputs. After a stable Streamlit release, we move to a desktop distribution target (Rust + Tauri v2) that reuses the same Python backend.

---

## Phases

### Phase 1: Wiring + Stability

**Goal:** End-to-end pipeline produces real edited outputs with multi-track transcription, applied cuts, and reliable job state.

**Dependencies:** None (uses existing skeleton)

**Scope / Requirements:**
- Fix Streamlit job creation to use a single job ID end-to-end
- Make multi-track transcription the default when multiple audio streams exist
- Merge per-track transcripts with speaker labels and a combined filler cut list
- Write `edit_plan.json` after review with approved filler/content cuts and clip ranges
- Implement FFmpeg trim/concat so render applies the edit plan (not full-length output)
- Generate both full-episode export and short-form clips from the edit plan
- Integrate research and viral scoring inside Analyze stage (write `research.json`, `viral_signals.json`)
- Surface research + viral insights in review UI
- Add progress reporting per stage for UI polling
- Align dependencies/config and remove unsafe parsing (`eval` in FFmpeg helpers)

**Success Criteria:**
1. A job runs ingest → render with outputs that reflect approved cuts and clips
2. Multi-track audio inputs produce speaker-labeled transcripts by default
3. Review decisions are persisted and applied in render
4. UI can show stage progress without blocking

**Plans:** 6 plans

Plans:
- [ ] 01-01-PLAN.md — Job creation + progress reporting
- [ ] 01-02-PLAN.md — Edit plan generation + research/viral UI
- [ ] 01-03-PLAN.md — Multi-track transcription default
- [ ] 01-04-PLAN.md — Config/deps alignment + safe FFmpeg parsing
- [ ] 01-05-PLAN.md — Edit-plan-driven render + clip exports
- [ ] 01-06-PLAN.md — Analyze stage research + viral artifacts

---

### Phase 2: Research + Viral Integration

**Goal:** Research signals materially improve title/thumbnail/clip recommendations.

**Dependencies:** Phase 1
**Status:** Code complete (verified 2026-02-04) — UAT in progress (see 02-UAT.md)

**Scope / Requirements:**
- Add engagement rate + velocity metrics to YouTube research output
- Add competition scoring + posting-pattern analysis
- Improve keyword extraction (weighted n-grams + stopword filtering)
- Populate `ResearchResult` with competition, engagement, and best posting times
- Re-rank AI viral clips using viral detector signals (cap score at 10)
- Add question/controversy/story-arc/quotable signals to viral scoring
- Cache research API calls to avoid quota spikes

**Success Criteria:**
1. Research artifacts are produced per job and visible in the UI
2. Viral clip ranking reflects combined AI + research signals

**Plans:** 5 plans

Plans:
- [x] 02-01-PLAN.md — Research metrics foundation (engagement/velocity/competition/posting)
- [x] 02-02-PLAN.md — Viral detector signal expansion + scoring updates
- [x] 02-03-PLAN.md — Weighted keyword extraction + YouTube API caching
- [x] 02-04-PLAN.md — Analyze-stage combined clip re-ranking
- [x] 02-05-PLAN.md — UI visibility for research and combined viral scoring

---

### Phase 3: Polishing + Desktop Distribution -- COMPLETE

**Goal:** Package the pipeline into a reliable desktop app (Rust + Tauri v2) with a Python backend service.

**Dependencies:** Phase 2

**Status:** Complete (2026-02-05)

**Scope / Requirements:**
- Build a backend job runner service reused by Streamlit and desktop
- Create Tauri v2 UI that talks to the backend via local IPC/HTTP
- Bundle FFmpeg and support optional model downloads
- Add crash recovery and job resume from saved state
- Provide Windows/macOS/Linux installers

**Success Criteria:**
1. Desktop app can run a full job with no manual setup on a clean machine
2. Job resume works after app restart

**Plans:** 6/6 complete

Plans:
- [x] 03-01-PLAN.md — Backend service contract + supervisor
- [x] 03-02-PLAN.md — Tauri shell + sidecar lifecycle
- [x] 03-03-PLAN.md — Streamlit migration to service client
- [x] 03-04-PLAN.md — FFmpeg/model asset packaging
- [x] 03-05-PLAN.md — Crash recovery + resume orchestration
- [x] 03-06-PLAN.md — Installer matrix + smoke validation

---

### Phase 4: Post-release hardening

**Goal:** Harden runtime correctness, security, and output quality so production behavior is truthful, resilient, and operator-safe across Streamlit and desktop surfaces.
**Depends on:** Phase 3
**Plans:** 10 plans

**Scope / Requirements:**
- Enforce strict stage validation and deterministic run orchestration invariants
- Add job-level locking/state-sync boundaries to prevent concurrent mutation corruption
- Align run/resume contracts across service schemas, routes, and typed client behavior
- Fix Streamlit truthfulness gaps (full-run semantics, metadata path, marketing workflow persistence)
- Add strict model validation for edit-plan/analysis/transcript/job/config ranges and state bounds
- Harden provider behavior: explicit parse failures, bounded retries, degraded-mode signaling
- Add service auth and global exception handling plus supervisor timeout/reconciliation reliability
- Fix render truthfulness: partial failure semantics, output verification, and quality-control wiring
- Implement concrete output quality backbone work (enhancements, thumbnail artifacts, stronger research derivation/cache)
- Raise confidence gates with dedicated runtime-critical tests and stronger coverage thresholds

**Success Criteria:**
1. Job lifecycle operations fail fast and truthfully for invalid, concurrent, or degraded conditions
2. UI actions (Streamlit + desktop) accurately reflect backend behavior and persisted workflow state
3. Render/research/provider outputs are quality-hardened with explicit failure/degraded signaling
4. Runtime-critical behavior is protected by dedicated tests and stricter quality gates

Plans:
- [ ] 04-01-PLAN.md — Runtime invariants: stage validation + job lock + state sync
- [ ] 04-02-PLAN.md — Service run/resume contract parity + client hardening
- [ ] 04-03-PLAN.md — Streamlit workflow truthfulness fixes
- [ ] 04-04-PLAN.md — Model and config validation hardening
- [ ] 04-05-PLAN.md — Provider reliability and degraded-mode semantics
- [ ] 04-06-PLAN.md — Service security, supervisor timeout, and reconciliation hardening
- [ ] 04-07-PLAN.md — Render truthfulness + quality-control wiring + preflight checks
- [ ] 04-08-PLAN.md — Output quality backbone: enhancement, thumbnails, research cache/query
- [ ] 04-09-PLAN.md — Desktop lifecycle controls + Streamlit timeline editing UX completion
- [ ] 04-10-PLAN.md — Confidence gates: runtime-critical tests, coverage thresholds, docs alignment

**Details:**
Plans are ordered in 5 execution waves to prioritize P0 runtime correctness first, then reliability/security, then output quality and UX completion, and finally confidence gates.

---

### Phase 5: Video Podcast Platforms

**Goal:** Deliver publish-ready Spotify and Apple video podcast export artifacts (MP4 plus optional HLS packaging) with compliance validation and truthful operator workflow guidance.
**Depends on:** Phase 4
**Status:** Complete (verified 2026-02-19)
**Plans:** 3/3 complete

Plans:
- [x] 05-01-PLAN.md — Research-led platform schema defaults and fail-fast validation for `spotify_video`/`apple_video`
- [x] 05-02-PLAN.md — Render compliance wiring with ffprobe topology/timing checks and truthful failure contracts
- [x] 05-03-PLAN.md — Optional `apple_hls` hand-off packaging plus Apple/Spotify workflow-boundary documentation

**Details:**
Plans are sequenced in 3 waves:
- Wave 1 locks conservative mezzanine-first defaults and schema guardrails from Phase 05 research.
- Wave 2 enforces Spotify/Apple compliance behavior in render with deterministic post-render validation.
- Wave 3 adds optional Apple HLS artifacts and codifies provider/dashboard workflow constraints for operators.

---

### Phase 5.1: Streamlit Video Platform UI

**Goal:** Expose Phase 5 video podcast targets in Streamlit/CLI export workflows with backward-compatible review-state persistence, strict key validation, and truthful operator guidance for provider-mediated publishing boundaries.
**Depends on:** Phase 5
**Status:** Complete (verified 2026-02-20)
**Plans:** 3 plans

**Scope / Requirements:**
- Add a canonical export-target registry shared by review, Streamlit UI, and CLI approval paths
- Include `spotify_video`, `apple_video`, and `apple_hls` in Streamlit export selection UX
- Normalize persisted/exported platform keys with safe fallback defaults for legacy jobs
- Reject unknown platform keys in CLI approval flows with actionable validation errors
- Preserve `youtube,spotify` defaults when no valid explicit selection is provided
- Keep `apple_hls` guidance explicit as artifact packaging only (no direct upload automation)
- Add regression coverage for cross-surface key parity and review-state round trips

**Success Criteria:**
1. Streamlit export panel exposes all supported audio/video/package targets and persists valid selections
2. Review state and CLI approval paths share one validated platform-key contract
3. Unknown platform keys fail loudly in CLI and are handled safely for persisted review-state data
4. Operator-facing guidance remains truthful for Apple/Spotify publication boundaries

Plans:
- [x] 05.1-01-PLAN.md — Canonical export target registry + review-state normalization contract
- [x] 05.1-02-PLAN.md — Streamlit export UI wiring for video targets + persistence round-trip safeguards
- [x] 05.1-03-PLAN.md — CLI approval parity + invalid-key error contracts + regression coverage

**Details:**
Plans run in 2 execution waves:
- Wave 1 defines canonical platform contracts and normalization.
- Wave 2 executes Streamlit UI wiring and CLI parity in parallel using shared contracts.

---

### Phase 6: Audio/Video Enhancement & Podcast Video Platform

**Goal:** Improve baseline audio/video output quality with additive, enhancement-only filters (de-esser, optional dereverb, optional color correction) while preserving existing render-core editing behavior.
**Depends on:** Phase 5
**Status:** Complete (verified 2026-02-20)
**Plans:** 3/3 complete

**Scope / Requirements:**
- Add typed config sections for `deesser`, `dereverb`, and `color_correction` with safe defaults
- Add FFmpeg capability preflight checks for enabled filters (`deesser`, `grayworld`, `normalize`, `adeclick`, etc.) with actionable fail-fast errors
- Implement FFmpeg-native de-esser path in render audio enhancement chain
- Add optional lightweight dereverb path (`noisereduce`) behind config gating and dependency-aware fallback behavior
- Implement optional video color correction using canonical FFmpeg filters (`normalize`, `grayworld`, optional `eq`)
- Preserve existing render output behavior when enhancements are disabled
- Add regression coverage for enabled/disabled paths and scope-boundary guardrails

**Success Criteria:**
1. Enhancement config loads with typed validation and default-disabled behavior that preserves existing outputs
2. Render fails fast with clear diagnostics when required enabled filters are unavailable in local FFmpeg
3. Audio de-esser and optional dereverb paths are configurable, deterministic, and non-breaking when disabled
4. Video color correction uses only canonical FFmpeg filters and remains opt-in
5. No crossfade/word-boundary/filler-control render-core rewrites land in Phase 6

Plans:
- [x] 06-01-PLAN.md — Enhancement config contract + FFmpeg capability preflight + scope guardrails
- [x] 06-02-PLAN.md — Audio enhancement chain (FFmpeg-native de-esser + optional noisereduce dereverb)
- [x] 06-03-PLAN.md — Optional video color correction chain + canonical-filter regression coverage

**Details:**
Plans run in 2 execution waves:
- Wave 1: `06-01` establishes typed config and fail-fast preflight guardrails.
- Wave 2: `06-02` and `06-03` execute in parallel on top of Wave 1.

Scope boundary note:
- Smooth cut transitions, word-boundary snapping, and filler editorial control are intentionally deferred to a future Phase 7 to keep Phase 6 low-risk and additive.

---

### Phase 6.1: Video Marketing Copy Parity + Thumbnail Visual Selection Research

**Goal:** Close video-platform marketing-copy parity gaps (`spotify_video`, `apple_video`) and produce implementation-ready research for a visual thumbnail-selection UX with multi-select and viral-candidate surfacing.
**Depends on:** Phase 6
**Status:** Planned (2026-02-20)
**Plans:** 2 plans

**Scope / Requirements:**
- Add `spotify_video` and `apple_video` to analysis marketing schema so validated AI responses retain these keys
- Extend provider prompt schema so AI returns video-specific marketing payloads for Spotify/Apple video variants
- Extend marketing artifact generation to include video-platform sections in render output
- Extend Streamlit marketing editor platform list to expose editable video-platform copy
- Add regression tests covering model key retention and marketing-doc rendering for new video keys
- Research and document a complete approach for thumbnail frame extraction + visual-grid selection UX
- Define 1-3 thumbnail selection data-contract changes and render artifact naming strategy
- Define viral-thumbnail criteria/scoring recommendations and a file-level implementation impact map

**Success Criteria:**
1. `spotify_video`/`apple_video` marketing copy survives prompt -> model validation -> artifact generation -> UI edit flow
2. Regression tests lock marketing parity behavior for both new video platform keys
3. `research/thumbnail-ui-visual-selection.md` exists with concrete FFmpeg, Streamlit, schema, virality, and phasing recommendations
4. Phase 6.1 output is ready for direct execution planning of thumbnail visual UX implementation

Plans:
- [ ] 06.1-01-PLAN.md — Video-platform marketing copy parity across models/providers/render/UI + regressions
- [ ] 06.1-02-PLAN.md — Thumbnail visual selection research (frame extraction, multi-select UX, viral scoring, impact map)

**Details:**
Plans run in 2 waves:
- Wave 1 executes the concrete marketing-copy parity fix with tests.
- Wave 2 produces implementation-ready thumbnail visual selection research on top of the updated platform/copy baseline.

---

## Notes

- Streamlit remains the short-term UI for validation and rapid iteration.
- The pipeline is the single source of truth; UI must not implement pipeline logic.
