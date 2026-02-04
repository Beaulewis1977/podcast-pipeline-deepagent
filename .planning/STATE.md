# Project State: Podcast Pipeline

**Last updated:** 2026-02-04
**Current phase:** Phase 2 execution (Research + Viral Integration)
**Overall progress:** 91%

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Turn raw podcast recording into multi-platform content without editing software or manual copywriting.
**Current focus:** Phase 2 execution (research + viral integration).

## Current Position

```
Phase:    [2 of 3] Research + Viral Integration
Plan:     [4 of 5] Completed 02-04-PLAN.md
Status:   In progress
Progress: [██████████████████░░] 91%
```

## Phase Status

| Phase | Name | Status | Plans | Progress |
|------:|------|--------|-------|----------|
| 1 | Wiring + Stability | Complete | 6/6 | 100% |
| 2 | Research + Viral Integration | In progress | 4/5 | 80% |
| 3 | Polishing + Desktop Distribution | Pending | 0/0 | 0% |

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 10 |
| Requirements done | 35/83 (21 partial) |
| Phases complete | 1/3 |
| Estimated completion | In progress |

## Accumulated Context

### Key Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| Streamlit-first UI | Fastest path to validate workflow | 2026-02-03 |
| Desktop follow-up (Rust + Tauri v2) | Better distribution + performance | 2026-02-03 |
| Competition score bounded to 0-100 using normalized weighted factors | Keeps topic difficulty stable and comparable for ranking/UI consumers | 2026-02-04 |
| Posting recommendations emitted as UTC windows + weekday distributions | Deterministic structure for cross-timezone rendering and tests | 2026-02-04 |
| Engagement density uses weighted signal strength/minute with diversity bonus | Rewards clips with sustained multi-signal momentum instead of isolated spikes | 2026-02-04 |
| Detector reasons explicitly mention question/controversy/story-arc/quotable cues | Keeps clip ranking changes interpretable in artifacts and UI | 2026-02-04 |
| YouTube search/stat calls use normalized TTL cache keys | Reduces repeated quota consumption across identical analyze runs | 2026-02-04 |
| Keyword ranking is phrase-first (weighted n-grams) with stopword filtering | Surfaces reusable title/thumbnail phrases over weak unigram noise | 2026-02-04 |
| Analyze clip ranking blends AI (45%) and detector (55%) scores | Prioritizes transcript-level evidence while retaining provider signal | 2026-02-04 |
| Viral artifact rows remain backward-compatible via additive score fields | UI can adopt richer metrics incrementally without breaking old readers | 2026-02-04 |

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

## Session Continuity

### Last session

Executed `02-04-PLAN.md`; added combined score re-ranking and explainable artifact output.

### Stopped at

Completed `02-04-PLAN.md`

### Resume file

None

### Files modified this session

- `src/podcast_pipeline/stages/analyze.py`
- `tests/test_analyze_ranking.py`
- `.planning/phases/02-research-+-viral-integration/02-04-SUMMARY.md`
- `.planning/STATE.md`

---

*State updated: 2026-02-04*
