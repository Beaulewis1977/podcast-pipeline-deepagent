---
phase: 08-intelligent-cut-quality
plan: 01
subsystem: transcription
tags: [filler-detection, pydantic, transcript, phase8, pause-gate, context-window]

# Dependency graph
requires:
  - phase: 07-smooth-editing-filler-word-control
    provides: FillerCut model, _detect_fillers() filler detection pipeline, FillerConfig baseline
provides:
  - FillerConfig with disfluencies/hedge_words/custom_words typed sub-lists and backward-compat words field
  - protect_pause_threshold_ms, enable_llm_triage, llm_triage_model, llm_triage_max_context_words config fields
  - FillerCut.category (disfluency/hedge/custom Literal), pause_before_ms, pause_after_ms, context_before, context_after, protected fields
  - Upgraded _detect_fillers() populating all enriched fields with pause gate protection
  - test_transcribe.py with 16 filler enrichment tests
  - Phase 8 FillerCut backward-compat and new-field tests in test_models.py
affects:
  - 08-02-PLAN (LLM triage reads category=hedge and context fields)
  - 08-03-PLAN (review UI grouping reads category; protected flag controls filler display)
  - 08-04-PLAN (downstream rendering reads protected flag)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Typed Literal union for category discriminant in Pydantic model
    - Category priority: hedge > custom > disfluency during set-based filler matching
    - Raw word timestamps for pause measurement; padded timestamps for cut start/end
    - Backward-compat via optional fields with safe defaults (category="disfluency", protected=False)
    - N-word context window controlled by llm_triage_max_context_words config

key-files:
  created:
    - tests/test_transcribe.py
  modified:
    - src/podcast_pipeline/config/settings.py
    - src/podcast_pipeline/models/transcript.py
    - src/podcast_pipeline/stages/transcribe.py
    - tests/test_models.py

key-decisions:
  - "FillerConfig splits word lists into disfluencies/hedge_words/custom_words with legacy words field merging into disfluency set for backward compat"
  - "protect_pause_threshold_ms defaults to 300ms; fillers adjacent to silences >= threshold are marked protected=True and excluded from LLM triage"
  - "Pause measurement uses raw word timestamps before padding; cut start/end retain padding for smooth render splices"
  - "Category priority hedge > custom > disfluency ensures hedge and custom words are never misclassified as disfluencies"
  - "llm_triage_max_context_words=5 is also the context window N for context_before/context_after extraction"

patterns-established:
  - "Category sets: build disfluency_set | hedge_set | custom_set unions before matching, then resolve category from priority order"
  - "Pause gate: compute pause_before/after_ms from raw timestamps, set protected=True if either >= threshold"
  - "Context window: words[max(0, i-N):i] for before, words[i+phrase_len:i+phrase_len+N] for after"

# Metrics
duration: 20min
completed: 2026-02-21
---

# Phase 8 Plan 01: FillerConfig Restructure + FillerCut Enrichment Summary

**Typed disfluency/hedge/custom filler categories with pause-gate protection, context windows, and backward-compatible FillerCut model enrichment**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-02-21T07:43:00Z
- **Completed:** 2026-02-21T08:03:50Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `FillerConfig` restructured with typed `disfluencies`/`hedge_words`/`custom_words` sub-lists plus backward-compat `words` field — legacy configs with only `words: [...]` continue to work
- `FillerCut` model enriched with 6 new Phase 8 fields (`category`, `pause_before_ms`, `pause_after_ms`, `context_before`, `context_after`, `protected`) — all optional/defaulted so legacy `filler_cuts.json` files deserialize cleanly
- `_detect_fillers()` fully upgraded: builds three category sets, determines per-filler category with hedge > custom > disfluency priority, computes raw pause timing, extracts N-word context window, and fires pause-gate protection for fillers adjacent to silence >= `protect_pause_threshold_ms`
- 21 new tests covering all enrichment paths: category assignment (disfluency/hedge/custom/multi-word), backward-compat `words` field, pause gate fire/no-fire/boundary conditions, context extraction at boundaries and window limits, raw-vs-padded timestamp behavior, min-confidence and min-duration gating

## Task Commits

1. **Task 1: Restructure FillerConfig with typed word category sub-lists** - `3a12499` (feat)
2. **Task 2: Enrich FillerCut model and upgrade _detect_fillers** (source) - `8f11e4c` (feat)
3. **Task 2: Add filler enrichment tests** (tests) - `56540c4` (test)

## Files Created/Modified

- `src/podcast_pipeline/config/settings.py` - Added disfluencies/hedge_words/custom_words/protect_pause_threshold_ms/enable_llm_triage/llm_triage_model/llm_triage_max_context_words to FillerConfig
- `src/podcast_pipeline/models/transcript.py` - Added category/pause_before_ms/pause_after_ms/context_before/context_after/protected fields to FillerCut with safe defaults
- `src/podcast_pipeline/stages/transcribe.py` - Upgraded _detect_fillers() with category sets, pause timing, context window, pause gate; added _filler_category() helper
- `tests/test_transcribe.py` - Created with 16 tests: category assignment, backward compat, pause gate, context extraction, padding behavior, min gates
- `tests/test_models.py` - Added 5 Phase 8 FillerCut tests: backward-compat no-new-fields, all fields round-trip, invalid category rejected, custom category accepted

## Decisions Made

- `words` field default changed from full word list to `[]`; when non-empty (legacy configs), entries merge into the disfluency set at detection time
- Category priority established: hedge > custom > disfluency — prevents hedge words also present in disfluency defaults from being misclassified
- Pause measurement strictly uses raw word timestamps (`word.start`, `word.end`) before padding is applied; `FillerCut.start`/`end` retain padding for render-safe splices
- `protect_pause_threshold_ms` uses `>=` semantics at threshold boundary (e.g., exactly 300ms pause = protected)
- `llm_triage_max_context_words` serves double duty: controls both LLM context word count (Plan 02) and context window N for `context_before`/`context_after` extraction

## Deviations from Plan

None - plan executed exactly as written. All source code changes (FillerConfig, FillerCut, _detect_fillers) were already partially in place on the branch from prior research work; tests were created fresh as specified.

## Issues Encountered

- Pre-commit hook reformatted `transcribe.py` on first commit attempt (ruff line-length adjustment on a long inline comment); resolved by restaging and recommitting.
- Unused `FillerCut` import in test_transcribe.py caught by ruff `F401`; removed and auto-fixed.
- Pre-existing mypy errors in `TestJob.test_save_and_load` in test_models.py (non-overlapping equality check, missing return annotation); not introduced by this plan, not fixed (out of scope).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 02 (LLM triage for hedge words) can now read `category`, `context_before`, `context_after`, and `protected` from every FillerCut
- Plan 03 (review UI) can group fillers by category and visually mark protected fillers
- All fields have safe defaults so the pipeline runs end-to-end without Phase 02/03 changes

## Self-Check: PASSED

All files present and all commits verified:
- `src/podcast_pipeline/config/settings.py` — FOUND
- `src/podcast_pipeline/models/transcript.py` — FOUND
- `src/podcast_pipeline/stages/transcribe.py` — FOUND
- `tests/test_transcribe.py` — FOUND
- `tests/test_models.py` — FOUND
- Commit `3a12499` (FillerConfig restructure) — FOUND
- Commit `8f11e4c` (FillerCut enrichment + _detect_fillers) — FOUND
- Commit `56540c4` (tests) — FOUND

---
*Phase: 08-intelligent-cut-quality*
*Completed: 2026-02-21*
