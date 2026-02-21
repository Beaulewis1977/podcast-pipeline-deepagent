# Roadmap: Podcast Pipeline

**Created:** 2026-01-29
**Last Updated:** 2026-02-21
**Milestone:** v1.0 (Streamlit-first)
**Phases:** 8 + follow-ups 5.1 and 6.1

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

### Phase 6.1: Video Marketing Copy Parity + Thumbnail Visual Selection MVP

**Goal:** Deliver trend-aware, LLM-generated cross-platform marketing copy coverage (including `spotify_video`, `apple_video`) and implement thumbnail visual-selection MVP (visual grid + ranked 1-3 selection + virality surfacing + per-target thumbnail compliance enforcement).
**Depends on:** Phase 6
**Status:** Complete (verified 2026-02-20)
**Plans:** 5/5 complete

**Scope / Requirements:**
- Add `spotify_video` and `apple_video` to analysis marketing schema so validated AI responses retain these keys
- Expand marketing contract to full platform matrix (`youtube`, `spotify`, `spotify_video`, `apple`, `apple_video`, `tiktok`, `instagram`, `linkedin`, `twitter`, `facebook`)
- Extend provider prompt schema so AI returns high-level viral-but-professional, platform-tailored copy generated by the LLM for all supported marketing platforms
- Inject trend context from research artifacts (`analysis/research.json`, `analysis/viral_signals.json`) into marketing prompt generation when available
- Extend marketing artifact generation to include full-platform sections in render output
- Extend Streamlit marketing editor platform list/controls to expose editable full-platform copy including video podcast variants
- Add regression tests covering model key retention, trend-context prompt wiring, and marketing-doc/render/UI full-platform parity
- Extend thumbnail candidate and provider contracts with virality metadata (`virality_score` + recommendation context)
- Add ordered 1-3 thumbnail selection contract (`selected_thumbnails`) with backward-compatible mirror to legacy `selected_thumbnail`
- Materialize thumbnail frames during analyze stage for visual UI rendering
- Replace text-only thumbnail selector with Streamlit visual grid and ranked multi-select UX
- Generate/export primary + alternate thumbnail artifacts from ranked selections
- Enforce thumbnail output compliance per selected export target during render (format/aspect/size constraints) with fail-fast errors for unsatisfied targets
- Defer explicit per-platform thumbnail assignment UX (different thumbnail per platform) until post-MVP follow-up

**Success Criteria:**
1. Full-platform marketing copy survives prompt -> model validation -> artifact generation -> UI edit flow, including `spotify_video` and `apple_video`
2. LLM marketing prompt contract enforces viral-but-professional copy quality with platform-tailored field expectations
3. Trend/research context is consumed by marketing prompt generation when available, with safe no-research fallback behavior
4. Thumbnail review UI renders visual frame previews and persists ranked 1-3 selections with backward-compatible review-state behavior
5. Render generates and validates per-target thumbnail outputs for selected export platforms before success is reported
6. Render fails fast with explicit target-level thumbnail compliance errors when constraints are unsatisfied
7. Per-platform custom thumbnail assignment UX remains explicitly deferred to follow-on scope

Plans:
- [x] 06.1-01-PLAN.md — Full-platform marketing contract: model + provider prompt quality/trend wiring + regression locking
- [x] 06.1-02-PLAN.md — Marketing surfaces parity: full-platform render/UI coverage + trend-aware workflow regressions
- [x] 06.1-03-PLAN.md — Thumbnail data contracts: virality schema + ranked selection state + compatibility
- [x] 06.1-04-PLAN.md — Thumbnail MVP UX: analyze-time frame extraction + Streamlit visual ranked multi-select
- [x] 06.1-05-PLAN.md — Thumbnail export contract: per-target compliance enforcement + fail-fast diagnostics + docs

**Details:**
Plans run in 4 waves:
- Wave 1: `06.1-01` establishes full-platform provider/model marketing contract parity plus trend-aware prompt wiring.
- Wave 2: `06.1-02` and `06.1-03` execute in parallel (render/UI marketing parity + thumbnail contract evolution).
- Wave 3: `06.1-04` implements analyze-time frame extraction and visual ranked selection UX.
- Wave 4: `06.1-05` enforces per-target thumbnail compliance and fail-fast render semantics.

### Phase 7: Smooth Editing & Filler Word Control

**Goal:** Deliver smoother spoken-word edits by snapping cuts to word boundaries, applying selective transition smoothing, and enabling explicit per-filler editorial control in review without breaking legacy workflows.
**Depends on:** Phase 6
**Status:** Complete (verified 2026-02-21)
**Plans:** 4 plans

Plans:
- [x] 07-01-PLAN.md — Foundation contracts: boundary snapping utilities, additive edit-plan metadata, and per-filler decision compatibility.
- [x] 07-02-PLAN.md — Render smoothing engine: typed policy config, snapped cuts, selective micro-fade/crossfade/xfade with short-segment guardrails.
- [x] 07-03-PLAN.md — Streamlit/editorial UX: category-grouped filler review, bulk actions, and deterministic decision persistence.
- [x] 07-04-PLAN.md — Integration hardening: end-to-end regression coverage, legacy artifact compatibility, and operator documentation.

---

### Phase 8: Intelligent Cut Quality — Context-Aware Filler Control & Invisible Edit Rendering

**Goal:** Deliver semantically-aware filler word triage (category-based auto-remove vs. LLM-checked review vs. pause-protected keep) and invisible video cut rendering (de-breathing, noise-floor matching, pose-match frame selection, RIFE AI bridge frames)  without breaking existing Phase 7 smoothing contracts.
**Depends on:** Phase 7
**Status:** Planning (spec complete 2026-02-21)
**Plans:** 6 plans

**Scope / Requirements:**

- Restructure `FillerConfig` into typed `disfluencies`, `hedge_words`, `custom_words` sub-lists with backward-compatible `words` fallback
- Enrich `FillerCut` transcript model with `category`, `pause_before_ms`, `pause_after_ms`, `context_before`, `context_after`, `protected` fields
- Add pause-gate protection logic: fillers adjacent to ≥ 300ms pauses are `protected` and default to keep
- Add LLM semantic triage sub-stage in `AnalyzeStage` for hedge fillers (batched, cheap gpt-4o-mini calls)
- Write `analysis/filler_triage.json` with per-filler `safe_to_remove` verdicts and LLM reasons
- Wire triage results into review stage `FillerCutRange.default_action` (disfluency → remove, protected → keep, LLM-safe hedge → remove, LLM-review hedge → review)
- Update Streamlit filler cards with context snippet, pause badges (ms display), 🔒 protection lock, and LLM reason
- Add `silero-vad` de-breathing pass extending cut boundaries past trailing breath sounds
- Add `librosa` RMS noise-floor mismatch detection with FFmpeg gain-ramp correction
- Add `opencv-python` Farneback optical-flow pose-match scanner for optimal cut-point frame selection
- Add `practical-RIFE` GPU frame interpolation for content joins where pose distance exceeds threshold
- Support RTX 5060 Ti 16 GB via PyTorch CUDA 12.x wheels
- All new render passes independently enable/disable via `SmoothingConfig`
- Full backward compatibility: legacy artifacts (no new fields) load with safe defaults

**Success Criteria:**

1. `um`/`uh`/`hmm`/`er`/`ah` auto-removed; `like`/`you know` sent to LLM for semantic check
2. Any filler adjacent to ≥ 300ms pause is protected (`default_action=keep`) in edit plan
3. LLM hedge triage produces `filler_triage.json` with one verdict per hedge filler; disabled flag respected
4. Streamlit filler card shows context snippet, pause timing badges, and LLM reason text
5. De-breathing extends cut boundaries to swallow trailing breath sounds
6. Noise-floor matching corrects > 3dB RMS mismatch across a join with a gain ramp
7. Pose-match scan selects frame pair with minimum optical-flow distance as actual cut point
8. RIFE generates bridge frames when pose score exceeds threshold; falls back to xfade on failure
9. GPU smoke test passes on RTX 5060 Ti: `scripts/smoke_test_gpu_rife.py` prints "RIFE OK"
10. Legacy `filler_cuts.json` and `edit_plan.json` without Phase 8 fields load and render correctly

Plans:

- [ ] 08-01-PLAN.md — FillerConfig restructure + FillerCut category/pause/context enrichment in transcribe
- [ ] 08-02-PLAN.md — LLM semantic triage sub-stage (AnalyzeStage) + FillerTriage model + artifact
- [ ] 08-03-PLAN.md — Review + UI wiring: triage → FillerCutRange default_action + context/badge UI
- [ ] 08-04-PLAN.md — Render: de-breathing (silero-vad) + noise-floor matching (librosa)
- [ ] 08-05-PLAN.md — Render: pose-match (opencv) + RIFE AI frame interpolation (practical-RIFE + GPU)
- [ ] 08-06-PLAN.md — Integration hardening: cross-path regressions, GPU smoke test, README operator docs

**Details:**

Plans run in 4 execution waves:

- Wave 1: `08-01` (FillerConfig + FillerCut) and `08-02` (LLM triage) in parallel — both are additive foundation work
- Wave 2: `08-03` (review/UI wiring) — requires Wave 1 enriched models
- Wave 3: `08-04` (de-breathing + noise-floor) and `08-05` (pose-match + RIFE) in parallel — both are independent render passes
- Wave 4: `08-06` (integration hardening + docs) — validates full stack

**New dependencies:**

| Package | Version | Purpose | GPU required |
|---|---|---|---|
| `silero-vad` | >= 5.0 | Breath/VAD detection | No |
| `librosa` | >= 0.10 | Audio RMS analysis | No |
| `soundfile` | >= 0.12 | Audio I/O for librosa | No |
| `opencv-python` | >= 4.9 | Pose-match optical flow | No (CPU) |
| `torch` | >= 2.3 (CUDA build) | RIFE inference | Yes (RTX 5060 Ti) |
| `torchvision` | >= 0.18 | RIFE dep | Yes |
| `practical-RIFE` | git clone | Frame interpolation | Yes |

---

## Notes

- Streamlit remains the short-term UI for validation and rapid iteration.
- The pipeline is the single source of truth; UI must not implement pipeline logic.
