# Roadmap: Podcast Pipeline

**Created:** 2026-01-29
**Last Updated:** 2026-02-04
**Milestone:** v1.0 (Streamlit-first)
**Phases:** 3

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

### Phase 3: Polishing + Desktop Distribution

**Goal:** Package the pipeline into a reliable desktop app (Rust + Tauri v2) with a Python backend service.

**Dependencies:** Phase 2

**Scope / Requirements:**
- Build a backend job runner service reused by Streamlit and desktop
- Create Tauri v2 UI that talks to the backend via local IPC/HTTP
- Bundle FFmpeg and support optional model downloads
- Add crash recovery and job resume from saved state
- Provide Windows/macOS/Linux installers

**Success Criteria:**
1. Desktop app can run a full job with no manual setup on a clean machine
2. Job resume works after app restart

---

## Notes

- Streamlit remains the short-term UI for validation and rapid iteration.
- The pipeline is the single source of truth; UI must not implement pipeline logic.
