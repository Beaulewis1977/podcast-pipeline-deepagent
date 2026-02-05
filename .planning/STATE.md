# Project State: Podcast Pipeline

**Last updated:** 2026-02-04
**Current phase:** Phase 3 planning (Polishing + Desktop Distribution)
**Overall progress:** 100%

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Turn raw podcast recording into multi-platform content without editing software or manual copywriting.
**Current focus:** Phase 2 verified complete; prepare Phase 3 planning.

## Current Position

```
Phase:    [3 of 3] Polishing + Desktop Distribution
Plan:     [0 of 0] Awaiting phase planning
Status:   Phase 2 complete (verified)
Progress: [████████████████████] 100%
```

## Phase Status

| Phase | Name | Status | Plans | Progress |
|------:|------|--------|-------|----------|
| 1 | Wiring + Stability | Complete | 6/6 | 100% |
| 2 | Research + Viral Integration | Complete | 5/5 | 100% |
| 3 | Polishing + Desktop Distribution | Pending | 0/0 | 0% |

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 11 |
| Requirements done | 35/83 (21 partial) |
| Phases complete | 2/3 |
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

### Technical Notes

- Recommended stack: FFmpeg, faster-whisper, Streamlit, Typer, Pydantic.
- Primary AI: Gemini (configurable; default gemini-2.5-flash) with Kimi K2.5 fallback.
- Avoid: moviepy, python-ffmpeg wrappers, original whisper, langchain.

### Open Questions

- (None)

### Blockers

- (None)

## Recent Activity

- 2026-02-04: Completed phase 2 plan 02-01 (research metrics foundation).
- 2026-02-04: Completed phase 2 plan 02-02 (viral detector expansion).
- 2026-02-04: Completed phase 2 plan 02-03 (cache + keyword extraction).
- 2026-02-04: Completed phase 2 plan 02-04 (analyze re-ranking + explainability).
- 2026-02-04: Completed phase 2 plan 02-05 (UI research + score visibility).
- 2026-02-04: Verified phase 2 goal (10/10 must-haves passed).

## Session Continuity

### Last session

Executed and verified all Phase 2 plans; created `02-VERIFICATION.md` with passed status.

### Stopped at

Phase 2 verified complete

### Resume file

None

### Files modified this session

- `src/podcast_pipeline/ui/app.py`
- `tests/test_ui_research_panel.py`
- `.planning/phases/02-research-+-viral-integration/02-05-SUMMARY.md`
- `.planning/phases/02-research-+-viral-integration/02-VERIFICATION.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`

---

*State updated: 2026-02-04*
