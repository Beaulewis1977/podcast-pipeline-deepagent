# Roadmap: Podcast Pipeline

**Created:** 2026-01-29
**Last Updated:** 2026-02-25
**Milestone:** v1.0 (Streamlit-first)
**Phases:** 8 + follow-ups 5.1 and 6.1

## Overview

The repository already contains a working pipeline skeleton (ingest -> transcribe -> analyze -> review -> render) plus a Streamlit UI. The roadmap now focuses on wiring the existing stages end-to-end, eliminating stubs, and producing real edited outputs. After a stable Streamlit release, we move to a desktop distribution target (Rust + Tauri v2) that reuses the same Python backend.

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
1. A job runs ingest -> render with outputs that reflect approved cuts and clips
2. Multi-track audio inputs produce speaker-labeled transcripts by default
3. Review decisions are persisted and applied in render
4. UI can show stage progress without blocking

**Plans:** 6 plans

Plans:
- [ ] 01-01-PLAN.md -- Job creation + progress reporting
- [ ] 01-02-PLAN.md -- Edit plan generation + research/viral UI
- [ ] 01-03-PLAN.md -- Multi-track transcription default
- [ ] 01-04-PLAN.md -- Config/deps alignment + safe FFmpeg parsing
- [ ] 01-05-PLAN.md -- Edit-plan-driven render + clip exports
- [ ] 01-06-PLAN.md -- Analyze stage research + viral artifacts

---

### Phase 2: Research + Viral Integration

**Goal:** Research signals materially improve title/thumbnail/clip recommendations.

**Dependencies:** Phase 1
**Status:** Code complete (verified 2026-02-04) -- UAT in progress (see 02-UAT.md)

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
- [x] 02-01-PLAN.md -- Research metrics foundation (engagement/velocity/competition/posting)
- [x] 02-02-PLAN.md -- Viral detector signal expansion + scoring updates
- [x] 02-03-PLAN.md -- Weighted keyword extraction + YouTube API caching
- [x] 02-04-PLAN.md -- Analyze-stage combined clip re-ranking
- [x] 02-05-PLAN.md -- UI visibility for research and combined viral scoring

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
- [x] 03-01-PLAN.md -- Backend service contract + supervisor
- [x] 03-02-PLAN.md -- Tauri shell + sidecar lifecycle
- [x] 03-03-PLAN.md -- Streamlit migration to service client
- [x] 03-04-PLAN.md -- FFmpeg/model asset packaging
- [x] 03-05-PLAN.md -- Crash recovery + resume orchestration
- [x] 03-06-PLAN.md -- Installer matrix + smoke validation

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
- [ ] 04-01-PLAN.md -- Runtime invariants: stage validation + job lock + state sync
- [ ] 04-02-PLAN.md -- Service run/resume contract parity + client hardening
- [ ] 04-03-PLAN.md -- Streamlit workflow truthfulness fixes
- [ ] 04-04-PLAN.md -- Model and config validation hardening
- [ ] 04-05-PLAN.md -- Provider reliability and degraded-mode semantics
- [ ] 04-06-PLAN.md -- Service security, supervisor timeout, and reconciliation hardening
- [ ] 04-07-PLAN.md -- Render truthfulness + quality-control wiring + preflight checks
- [ ] 04-08-PLAN.md -- Output quality backbone: enhancement, thumbnails, research cache/query
- [ ] 04-09-PLAN.md -- Desktop lifecycle controls + Streamlit timeline editing UX completion
- [ ] 04-10-PLAN.md -- Confidence gates: runtime-critical tests, coverage thresholds, docs alignment

**Details:**
Plans are ordered in 5 execution waves to prioritize P0 runtime correctness first, then reliability/security, then output quality and UX completion, and finally confidence gates.

---

### Phase 5: Video Podcast Platforms

**Goal:** Deliver publish-ready Spotify and Apple video podcast export artifacts (MP4 plus optional HLS packaging) with compliance validation and truthful operator workflow guidance.
**Depends on:** Phase 4
**Status:** Complete (verified 2026-02-19)
**Plans:** 3/3 complete

Plans:
- [x] 05-01-PLAN.md -- Research-led platform schema defaults and fail-fast validation for `spotify_video`/`apple_video`
- [x] 05-02-PLAN.md -- Render compliance wiring with ffprobe topology/timing checks and truthful failure contracts
- [x] 05-03-PLAN.md -- Optional `apple_hls` hand-off packaging plus Apple/Spotify workflow-boundary documentation

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
- [x] 05.1-01-PLAN.md -- Canonical export target registry + review-state normalization contract
- [x] 05.1-02-PLAN.md -- Streamlit export UI wiring for video targets + persistence round-trip safeguards
- [x] 05.1-03-PLAN.md -- CLI approval parity + invalid-key error contracts + regression coverage

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
- [x] 06-01-PLAN.md -- Enhancement config contract + FFmpeg capability preflight + scope guardrails
- [x] 06-02-PLAN.md -- Audio enhancement chain (FFmpeg-native de-esser + optional noisereduce dereverb)
- [x] 06-03-PLAN.md -- Optional video color correction chain + canonical-filter regression coverage

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
- [x] 06.1-01-PLAN.md -- Full-platform marketing contract: model + provider prompt quality/trend wiring + regression locking
- [x] 06.1-02-PLAN.md -- Marketing surfaces parity: full-platform render/UI coverage + trend-aware workflow regressions
- [x] 06.1-03-PLAN.md -- Thumbnail data contracts: virality schema + ranked selection state + compatibility
- [x] 06.1-04-PLAN.md -- Thumbnail MVP UX: analyze-time frame extraction + Streamlit visual ranked multi-select
- [x] 06.1-05-PLAN.md -- Thumbnail export contract: per-target compliance enforcement + fail-fast diagnostics + docs

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
- [x] 07-01-PLAN.md -- Foundation contracts: boundary snapping utilities, additive edit-plan metadata, and per-filler decision compatibility.
- [x] 07-02-PLAN.md -- Render smoothing engine: typed policy config, snapped cuts, selective micro-fade/crossfade/xfade with short-segment guardrails.
- [x] 07-03-PLAN.md -- Streamlit/editorial UX: category-grouped filler review, bulk actions, and deterministic decision persistence.
- [x] 07-04-PLAN.md -- Integration hardening: end-to-end regression coverage, legacy artifact compatibility, and operator documentation.

---

### Phase 8: Intelligent Cut Quality -- Context-Aware Filler Control & Invisible Edit Rendering (REPLAN)

**Goal:** Deliver semantically-aware filler word triage (category-based auto-remove vs. LLM-checked review vs. pause-protected keep) and invisible video cut rendering (de-breathing, noise-floor matching, pose-match frame selection, RIFE AI bridge frames) without breaking existing Phase 7 smoothing contracts.
**Depends on:** Phase 7
**Status:** Replanned (2026-02-23) -- fixes RIFE --output bug, model default, and dependency versions identified by post-execution research refresh
**Plans:** 6 plans

**Scope / Requirements:**

- Restructure `FillerConfig` into typed `disfluencies`, `hedge_words`, `custom_words` sub-lists with backward-compatible `words` fallback
- Enrich `FillerCut` transcript model with `category`, `pause_before_ms`, `pause_after_ms`, `context_before`, `context_after`, `protected` fields
- Add pause-gate protection logic: fillers adjacent to >= 300ms pauses are `protected` and default to keep
- Add LLM semantic triage sub-stage in `AnalyzeStage` for hedge fillers (batched, cheap gemini-2.5-flash-lite calls)
- Write `analysis/filler_triage.json` with per-filler `safe_to_remove` verdicts and LLM reasons
- Wire triage results into review stage `FillerCutRange.default_action` (disfluency -> remove, protected -> keep, LLM-safe hedge -> remove, LLM-review hedge -> review)
- Update Streamlit filler cards with context snippet, pause badges (ms display), protection lock, and LLM reason
- Add `silero-vad` de-breathing pass extending cut boundaries past trailing breath sounds
- Add `librosa` RMS noise-floor mismatch detection with FFmpeg gain-ramp correction
- Add `opencv-python` Farneback optical-flow pose-match scanner for optimal cut-point frame selection
- Add `practical-RIFE` GPU frame interpolation for content joins where pose distance exceeds threshold
- Support RTX 5060 Ti 16 GB via PyTorch CUDA 12.x wheels
- All new render passes independently enable/disable via `SmoothingConfig`
- Full backward compatibility: legacy artifacts (no new fields) load with safe defaults

**Success Criteria:**

1. `um`/`uh`/`hmm`/`er`/`ah` auto-removed; `like`/`you know` sent to LLM for semantic check
2. Any filler adjacent to >= 300ms pause is protected (`default_action=keep`) in edit plan
3. LLM hedge triage produces `filler_triage.json` with one verdict per hedge filler; disabled flag respected
4. Streamlit filler card shows context snippet, pause timing badges, and LLM reason text
5. De-breathing extends cut boundaries to swallow trailing breath sounds
6. Noise-floor matching corrects > 3dB RMS mismatch across a join with a gain ramp
7. Pose-match scan selects frame pair with minimum optical-flow distance as actual cut point
8. RIFE generates bridge frames when pose score exceeds threshold; falls back to xfade on failure
9. GPU smoke test passes on RTX 5060 Ti: `scripts/smoke_test_gpu_rife.py` prints "RIFE OK"
10. Legacy `filler_cuts.json` and `edit_plan.json` without Phase 8 fields load and render correctly

Plans:

- [ ] 08-01-PLAN.md -- Fix llm_triage_model default (gpt-4o-mini -> gemini-2.5-flash-lite) + verify config fields
- [ ] 08-02-PLAN.md -- Audit triage code for hardcoded model names + add model-default regression guard
- [ ] 08-03-PLAN.md -- Verify review/UI editorial_action wiring + filler card Phase 8 display
- [ ] 08-04-PLAN.md -- Update GPU dependency version floors (silero-vad 6.2, librosa 0.11, opencv 4.13)
- [ ] 08-05-PLAN.md -- Fix RIFE --output bug + update tests for upstream-compatible CLI contract
- [ ] 08-06-PLAN.md -- Update smoke test/operator guide versions + integration tests + legacy compat regressions

**Details:**

Plans run in 4 execution waves:

- Wave 1: `08-01` (config fix) and `08-02` (triage code audit + regression test) in parallel -- no file overlap
- Wave 2: `08-03` (review/UI verification, depends on 01+02) and `08-04` (dependency version update, depends on 01) in parallel -- no file overlap
- Wave 3: `08-05` (RIFE --output fix, depends on 04)
- Wave 4: `08-06` (smoke test + operator guide + integration tests, depends on 03+05)

**New dependencies (optional `gpu` extras group):**

| Package | Version | Purpose | GPU required |
|---|---|---|---|
| `silero-vad` | >= 6.2, < 7 | Breath/VAD detection | No (CPU) |
| `librosa` | >= 0.11, < 1 | Audio RMS analysis | No |
| `opencv-python-headless` | >= 4.13, < 5 | Pose-match optical flow | No (CPU) |
| `torch` | 2.10.x (cu128 index) | RIFE + silero-vad runtime | Yes (RTX 5060 Ti Blackwell sm_120) |
| `torchaudio` | 2.10.x (cu128 index) | silero-vad audio I/O | Yes |
| `practical-RIFE` | git clone (model 4.25) | Frame interpolation subprocess | Yes |

**Replan corrections (from 08-RESEARCH.md 2026-02-23 refresh):**
- CRITICAL: RIFE `--output` flag removed from bridge wrapper (upstream inference_img.py does not accept it)
- HIGH: llm_triage_model default changed from gpt-4o-mini to gemini-2.5-flash-lite
- MEDIUM: Dependency version floors raised to current stable (silero-vad 6.2, librosa 0.11, opencv-headless 4.13)
- MEDIUM: torch/torchaudio baseline documented as 2.10.x (was >=2.7)
- LOW: RIFE 4.26 note corrected (exists but 4.25 remains recommended)
- LOW: Reasoning/CoT models explicitly forbidden for triage in operator guide

### Phase 9: Automated Branding, Captions, and Multi-Track Sync

**Goal:** Transform the pipeline from a "Cutter" into a "Fully Branded Production Suite" — delivering dynamic BrandingProfile data model + brand voice injection, automated ASS caption engine with word-level highlighting, bounded cross-correlation multi-track audio sync, production sound kits with auto-ducking, AI thumbnail studio (Gemini Vision), HEVC 10-bit NVENC export profiles, Claude as an analysis provider, FFmpeg media toolkit (14 tools), developer-mode FFmpeg MCP server, and Streamlit Brand Studio UI — without breaking existing Phase 7/8 smoothing and filler-control contracts.
**Depends on:** Phase 8
**Status:** Complete (verified 2026-02-24)
**Plans:** 11/11 complete

**Scope / Requirements:**
- Build FFmpeg media toolkit (`utils/ffmpeg_toolkit.py`) — 14 typed tools across 5 groups (Probe, Encode, Filter, Edit, Package) with Pydantic I/O models
- Add FastMCP developer server (`mcp/ffmpeg_server.py`) wrapping all 14 toolkit tools for Claude Code DX (dev-only, not imported by production)
- Add Claude as an analysis provider (`providers/claude_provider.py`) using `anthropic>=0.80.0` SDK + `ANTHROPIC_API_KEY`; `supports_video=False`; register in `SUPPORTED_MODEL_PROVIDERS`
- Add HEVC 10-bit NVENC default encode profiles to `PlatformSpec` with software `libx265` fallback and opt-in AV1 experimental toggle (`libsvtav1` only)
- Implement `BrandingProfile` Pydantic model (`models/branding.py`) with `brand_voice`, logo, font, caption style, platform overrides; serialised to `branding/<name>.yaml`; inject `brand_voice` into `BaseProvider._build_prompt()` as optional kwarg
- Create ASS caption generator (`utils/captions.py`) from `transcribe/word_alignment.json` with per-word color highlights and per-aspect-ratio safe-zone templates (16:9, 9:16, 1:1); burn-in via `libass`
- Implement bounded cross-correlation audio sync (`utils/sync.py`) — downsample to 8 kHz mono, 60 s window, `scipy.signal.correlate`, `librosa.resample`; write offset to job manifest; add Streamlit +-5000 ms manual fallback slider
- Implement production sound kits — intro/transition/outro stingers from `branding/sounds/`; FFmpeg `sidechaincompress` auto-ducking (attack 5 ms, release 200 ms, ratio 4:1, threshold -30 dB)
- Build AI Thumbnail Studio (`utils/thumbnails.py`) — Gemini Vision (`gemini-2.5-flash-image`) via google.genai SDK with prompt-hash cache; auto-branding overlay via `overlay_image` toolkit tool
- Add Streamlit "Brand Studio" tab (profile CRUD, logo/font upload, brand voice text area) and "Production" sidebar (caption stylist, thumbnail gallery, audio mixer with sync slider and auto-duck toggle)
- Add `scipy>=1.14.0` as core dep; `fastmcp>=2.0.0` as `[dev]`; `[thumbnails]` group emptied (google-genai is core dep)

**Success Criteria:**
1. All 14 FFmpeg toolkit tools pass unit tests; no regressions in existing `utils/ffmpeg.py` callers
2. MCP server starts and each tool is callable from Claude Code; `probe_media` returns valid metadata
3. `ClaudeProvider` passes existing `AnalysisProvider` test suite; falls back gracefully when API key is absent
4. 1080p test video encodes HEVC 10-bit via NVENC; software `libx265` fallback works; AV1 toggle produces valid file
5. `BrandingProfile` YAML loads, validates, and `brand_voice` appears in analysis prompt; platform overrides merge correctly
6. ASS file generated from test transcript; FFmpeg burns it onto video; word highlighting renders for all 3 aspect ratios
7. Two test audio tracks with clap sync within +-10 ms automatically; manual slider offsets correctly; low-confidence warning on missing clap
8. Rendered video has intro music with auto-ducking; transition whoosh at cut boundaries; outro fades correctly
9. Gemini Vision generates thumbnails from AI prompts (cached on rerun); branding applied
10. Brand Studio tab creates/saves/loads profiles; full pipeline demo: raw -> synced -> cut -> branded -> captioned -> multi-platform export

Plans:
- [x] 09-01-PLAN.md -- FFmpeg media toolkit (14 tools, 5 groups) + unit tests + existing-callers regression locking
- [x] 09-02-PLAN.md -- FastMCP developer server (all 14 tools, lifespan HW cache, stdio transport, `.mcp.json` config)
- [x] 09-03-PLAN.md -- Claude analysis provider (Anthropic SDK, protocol conformance, API key config, test suite parity)
- [x] 09-04-PLAN.md -- HEVC 10-bit NVENC profiles + software `libx265` fallback + AV1 experimental toggle + codec regressions
- [x] 09-05-PLAN.md -- BrandingProfile model + brand voice prompt injection + platform-override merge + config wiring
- [x] 09-06-PLAN.md -- ASS caption generator (word-level highlights, aspect-ratio safe-zone templates, libass burn-in regressions)
- [x] 09-07-PLAN.md -- Bounded cross-correlation audio sync + Streamlit manual offset slider + job-manifest offset persistence
- [x] 09-08-PLAN.md -- Production sound kits (stingers, auto-ducking sidechaincompress, branding/sounds/ library)
- [x] 09-09-PLAN.md -- AI Thumbnail Studio (Gemini Vision single-backend, prompt-hash cache, auto-branding overlay)
- [x] 09-10-PLAN.md -- Streamlit Brand Studio tab + Production sidebar + full end-to-end pipeline demo integration
- [x] 09-11-PLAN.md -- Gemini Vision model pivot: replace Imagen 4 / FLUX.1 with exclusive Gemini Vision thumbnail generation

**Details:**
Plans run in 6 execution waves:
- Wave 1: `09-01` (toolkit foundation) -- required by all subsequent plans
- Wave 2: `09-02` (MCP server) and `09-03` (Claude provider) in parallel -- both depend on `09-01` only
- Wave 3: `09-04` (codec profiles) and `09-05` (branding model) in parallel -- depend on `09-01`
- Wave 4: `09-06` (captions), `09-07` (sync), `09-08` (sound kits) in parallel -- depend on `09-05`
- Wave 5: `09-09` (thumbnail studio) and `09-10` (Streamlit UI) in parallel -- depend on Waves 3-4; `09-10` depends on all
- Wave 6: `09-11` (Gemini Vision pivot) -- replaces Imagen 4 / FLUX.1 with Gemini Vision models; depends on `09-09`

**Spec reference:** `docs/plans/2026-02-21-branding-automation-and-sync-spec_v4.md`

**New dependencies:**
| Package | Version | Extra | Purpose |
|---|---|---|---|
| `anthropic` | `>=0.80.0` | -- | Claude analysis provider |
| `scipy` | `>=1.14.0` | -- | Cross-correlation for audio sync |
| `fastmcp` | `>=2.0.0` | `[dev]` | MCP server for FFmpeg toolkit |
| `google-genai` | `>=1.0.0` | -- (core) | Gemini Vision thumbnail generation (already installed) |

---

### Phase 9.12: Streamlit UI Gap Closure

**Goal:** Close all UI and backend wiring gaps discovered post-Phase 9 execution so that every Phase 9 feature is fully accessible, controllable, and functional from the Streamlit interface.
**Depends on:** Phase 9
**Status:** Complete (verified 2026-02-24)
**Plans:** 3/3 complete

**Scope / Requirements:**

Seven gaps identified in `09-UI-GAPS.md`. Ordered by priority:

**P0 -- Critical (features broken or completely inaccessible):**
- GAP-7: Wire `ReviewDecisions.captions_enabled`, `sound_kit_enabled`, and `branding_profile_name` into `render.py` -- these fields are persisted by the UI but completely ignored by the render stage; all three Production sidebar controls silently have zero effect
- GAP-2: Register `youtube_ultra` in `EXPORT_TARGETS` so the HEVC 10-bit export target appears in the export panel
- GAP-1: Add Anthropic API key status to the Settings API Keys panel; add interactive provider selection so Claude can be selected without hand-editing `config.yaml`

**P1 -- Significant (features partially broken):**
- GAP-4: Add caption aspect ratio selector (`16:9` / `9:16` / `1:1`) to Production sidebar; add `caption_aspect_ratio` field to `ReviewDecisions`; thread into `_burn_captions()` so captions use the correct safe-zone template for the export target
- GAP-3: Display auto-detected sync offset and confidence from `intermediate/sync_artifact.json` above the manual slider; extend slider range from +-2000ms to +-5000ms per original spec

**P2 -- Minor (polish and completeness):**
- GAP-5: Split "Enable Sound Kit" checkbox into separate "Enable Stingers" and "Enable Auto-Ducking" controls; add `auto_duck_enabled` field to `ReviewDecisions`; wire both into `_mix_stingers()`

**P3 -- Nice-to-have (operator UX):**
- GAP-6: Replace logo/font path text inputs in Brand Studio with `st.file_uploader` widgets; add interactive "Add Override" form to Platform Overrides expander

**Success Criteria:**
1. `decisions.captions_enabled = True` in review_state causes captions to burn into render output; `False` skips them regardless of config.yaml setting
2. `decisions.sound_kit_enabled = True` in review_state triggers stinger mixing; `False` bypasses it regardless of configured sound files
3. `decisions.branding_profile_name` overrides `config.branding.active_profile` for that render run
4. `youtube_ultra` toggle appears in export panel and successfully routes to HEVC 10-bit PlatformSpec
5. Claude provider can be selected in Settings without touching config files; ANTHROPIC_API_KEY status visible
6. Caption aspect ratio persists through review_state and is used by `generate_ass()` at render time
7. Auto-detected sync offset value and confidence displayed next to slider
8. All tests pass -- no regressions in Phase 9 (09-01 through 09-11)

**Gap reference:** `.planning/phases/09-automated-branding-captions-and-multi-track-sync/09-UI-GAPS.md`

Plans:
- [x] 09-12-01-PLAN.md -- Render wiring fix (GAP-7) + youtube_ultra registration (GAP-2) + ReviewDecisions extension + regression tests
- [x] 09-12-02-PLAN.md -- Claude provider selectbox + Anthropic key status (GAP-1) + caption aspect ratio (GAP-4) + sync artifact display + slider range (GAP-3)
- [x] 09-12-03-PLAN.md -- Split sound kit checkboxes (GAP-5A) + logo/font file uploaders (GAP-6A) + optional P3 stretch goals

**Details:**
Plans run in 3 execution waves:
- Wave 1: `09-12-01` fixes the critical render wiring (GAP-7), extends ReviewDecisions with new fields, and registers youtube_ultra (GAP-2). This is the foundation all other UI changes depend on.
- Wave 2: `09-12-02` adds P0/P1 UI controls in Settings and Production sidebar (GAP-1, GAP-3, GAP-4). Depends on 09-12-01 for the new ReviewDecisions fields.
- Wave 3: `09-12-03` adds P2/P3 polish controls (GAP-5A, GAP-6A, optional stretch goals). Depends on 09-12-02.

### Phase 10: Tauri Desktop Application Distribution

**Goal:** Build the Tauri v2 desktop application UI layer on top of the existing sidecar infrastructure -- shipping a production-quality NLE-grade desktop app that is a strict superset of the Streamlit UI.
**Depends on:** Phase 9
**Plans:** 6 plans

**Scope / Requirements:**
- Create missing PyInstaller entry point (`service/cli.py`) that CI references
- Add CORS middleware to FastAPI backend for Tauri dev/production origins
- Add pre-spawn coexistence health check to Tauri sidecar lifecycle (detect and attach to already-running backends)
- Migrate CI PyInstaller from `--onefile` to `--onedir` mode
- Install and configure frontend toolchain: TailwindCSS v4, TanStack Query v5, Zustand v5, wavesurfer.js v7, shadcn/ui
- Build state management layer: Zustand stores (UI state, sidecar state) + TanStack Query hooks (jobs, health, system status)
- Build layout components: AppShell, Sidebar, Header with 4-view navigation
- Build 4 desktop views: Ingestion Dashboard (drag-drop + job list + system readiness), Audio Sync Editor (wavesurfer.js waveform + sync offset), Transcript Timeline (scrolling transcript + filler toggle), Branding Studio (brand profiles + export targets)
- Replace monolithic App.tsx with AppShell + view routing while preserving boot/recovery logic

**Success Criteria:**
1. CI can build PyInstaller sidecar binary (cli.py exists, --onedir mode works)
2. Tauri dev frontend can reach backend without CORS errors
3. Desktop app detects and attaches to already-running backend (coexistence with Streamlit)
4. All 4 views render and are navigable via sidebar tabs
5. Drag-drop creates jobs from OS file paths (not browser File objects)
6. Job list shows pipeline stage progress with colored indicators
7. Waveform visualization works for job audio (wavesurfer.js)
8. Frontend compiles and `pnpm build` succeeds

Plans:
- [ ] 10-01-PLAN.md -- Critical infrastructure: service/cli.py entry point + CORS middleware + lib.rs coexistence check
- [ ] 10-02-PLAN.md -- Frontend toolchain: CI --onedir migration + dependency installation + Tailwind v4 + QueryClientProvider + shadcn/ui
- [ ] 10-03-PLAN.md -- State layer: Zustand stores + TanStack Query hooks + AppShell/Sidebar/Header layout
- [ ] 10-04-PLAN.md -- Views 1+3: Ingestion Dashboard (drag-drop + job list + system readiness) + Transcript Timeline (filler toggle)
- [ ] 10-05-PLAN.md -- Views 2+4: Audio Sync Editor (wavesurfer.js waveform + offset slider) + Branding Studio (profiles + export config)
- [ ] 10-06-PLAN.md -- Integration: App.tsx rebuild with AppShell + 4-view routing + boot sequence preservation + human verification

**Details:**
Plans run in 4 execution waves:
- Wave 1: `10-01` (backend infra gaps) and `10-02` (frontend toolchain) in parallel -- no file overlap
- Wave 2: `10-03` (state layer + layout) depends on `10-02` for installed dependencies
- Wave 3: `10-04` (Ingestion + Transcript views) and `10-05` (Audio + Branding views) in parallel -- both depend on `10-03`
- Wave 4: `10-06` (App.tsx integration + human verification) depends on `10-04` and `10-05`

**Tech stack (locked):**
| Library | Version | Purpose |
|---|---|---|
| TailwindCSS | v4 | Utility-first CSS (Vite plugin, no config file) |
| shadcn/ui | latest | Component library |
| TanStack Query | v5 | Server state + polling |
| Zustand | v5 | Client-side state |
| wavesurfer.js | v7 | Waveform visualization |
| PyInstaller | latest | Backend sidecar binary (`--onedir` mode) |

---

## Notes

- Streamlit remains the short-term UI for validation and rapid iteration.
- The pipeline is the single source of truth; UI must not implement pipeline logic.
