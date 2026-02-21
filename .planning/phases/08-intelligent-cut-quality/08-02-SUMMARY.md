---
phase: 08-intelligent-cut-quality
plan: 02
subsystem: analysis
tags: [openai, pydantic, llm-triage, filler-words, batch-llm]

# Dependency graph
requires:
  - phase: 08-01
    provides: enriched FillerCut model with category/pause_before_ms/pause_after_ms/context_before/context_after/protected fields
  - phase: 07-smooth-editing-filler-word-control
    provides: filler_cuts.json artifact from transcribe stage
provides:
  - FillerTriageResult Pydantic model at models/triage.py
  - _triage_fillers method on AnalyzeStage that loads filler_cuts.json, filters hedge+unprotected, calls OpenAI in batches, writes filler_triage.json
  - _run_triage orchestrator method integrated into AnalyzeStage.run()
  - analysis/filler_triage.json artifact with per-hedge-filler safe_to_remove verdict
affects:
  - 08-03 (review stage UI for displaying triage verdicts)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy openai import inside method body — keeps base install independent of LLM key presence"
    - "Candidates helper pattern — _load_triage_candidates returns None to signal skip; reduces return-statement count in main method"
    - "Batch prompt separator — '---\\n' separator for multi-filler batches; parsed by split('---') on response"
    - "Conservative default — parse errors and disabled flag both produce safe_to_remove=False"

key-files:
  created:
    - src/podcast_pipeline/models/triage.py
    - tests/test_triage.py
    - tests/test_analyze.py
  modified:
    - src/podcast_pipeline/stages/analyze.py

key-decisions:
  - "Batch size 20 — balances latency, token cost, and context window for gpt-4o-mini"
  - "Parse errors default to safe_to_remove=False — conservative: never auto-remove if uncertain"
  - "No-API-key path returns results with reason string — keeps downstream consumers consistent (always a list)"
  - "Disabled flag bypasses LLM entirely with deterministic fallback — enables test environments and cost control"
  - "_load_triage_candidates helper extracted to keep _triage_fillers under PLR0911 return-statement limit"

patterns-established:
  - "Triage result model: FillerTriageResult is the canonical output shape; filler_triage.json is a JSON array of serialized results"
  - "Prompt format: transcript excerpt with [WORD] bracketing + pause values + SAFE/REVIEW response contract"
  - "LLM call exception handling: catch Exception, log warning, produce safe_to_remove=False for all affected batch candidates"

# Metrics
duration: 6min
completed: 2026-02-21
---

# Phase 8 Plan 02: LLM Semantic Triage for Hedge Fillers Summary

**Batched OpenAI triage for hedge filler words using gpt-4o-mini: FillerTriageResult model, _triage_fillers helper writing analysis/filler_triage.json, and 25 passing tests.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-21T08:01:03Z
- **Completed:** 2026-02-21T08:06:40Z
- **Tasks:** 2
- **Files modified:** 3 (created 3 new)

## Accomplishments

- Created `FillerTriageResult` Pydantic model with filler_index, word, category, safe_to_remove, reason, llm_model, triaged_at fields
- Implemented `_triage_fillers` on AnalyzeStage: loads filler_cuts.json, filters to hedge+unprotected candidates, batches 20 per LLM call, parses SAFE/REVIEW verdicts
- Implemented `_run_triage` orchestrator and `_load_triage_candidates` helper — integrated at end of `AnalyzeStage.run()`
- Added 25 tests covering model round-trip, disabled flag, disfluency/protected filtering, prompt format, batch splitting at 20, parse errors, empty input, no-API-key path, and artifact serialization

## Task Commits

Each task was committed atomically:

1. **Task 1: Create FillerTriageResult model and _triage_fillers helper** - `297496b` (feat)
2. **Task 2: Add triage tests for model, prompt format, batching, and disabled path** - `f582cb3` (test)

## Files Created/Modified

- `src/podcast_pipeline/models/triage.py` - FillerTriageResult Pydantic model with safe defaults
- `src/podcast_pipeline/stages/analyze.py` - _run_triage, _triage_fillers, _load_triage_candidates, _build_triage_prompt, _parse_triage_batch_response, _parse_triage_block methods
- `tests/test_triage.py` - Model round-trip, defaults, safe_flag, filler_index validation (8 tests)
- `tests/test_analyze.py` - AnalyzeStage triage integration tests covering all paths (17 tests)

## Decisions Made

- Batch size 20: balances latency and cost for gpt-4o-mini token window
- Parse errors conservatively produce safe_to_remove=False — never auto-remove when verdict is uncertain
- No-API-key and disabled paths both return FillerTriageResult lists (not empty) so downstream consumers see a consistent shape
- Extracted `_load_triage_candidates` helper to keep `_triage_fillers` within ruff PLR0911 return-statement limit (6 max)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Refactored _triage_fillers to respect PLR0911 return-statement limit**
- **Found during:** Task 1 (ruff check)
- **Issue:** Initial implementation had 8 return statements; ruff PLR0911 limit is 6
- **Fix:** Extracted `_load_triage_candidates` helper that handles file-read + filtering, returning None on skip, so _triage_fillers has fewer return paths
- **Files modified:** src/podcast_pipeline/stages/analyze.py
- **Verification:** `uv run ruff check` passes cleanly
- **Committed in:** 297496b (Task 1 commit)

**2. [Rule 1 - Bug] Removed spurious noqa: PLC0415 from openai import**
- **Found during:** Task 1 (ruff check)
- **Issue:** `# noqa: PLC0415` was added but PLC0415 is already excluded for stages/* in pyproject.toml; ruff flagged it as RUF100 unused noqa directive
- **Fix:** Removed the noqa comment
- **Files modified:** src/podcast_pipeline/stages/analyze.py
- **Verification:** `uv run ruff check` passes cleanly
- **Committed in:** 297496b (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — linting/style bugs caught during Task 1 ruff check)
**Impact on plan:** Both fixes were minor style corrections caught immediately by ruff. No scope creep.

## Issues Encountered

None — implementation matched plan spec exactly after resolving the two lint issues above.

## User Setup Required

None — no external service configuration required. OpenAI API key is read from `OPENAI_API_KEY` env var; if absent, triage gracefully falls back with descriptive reason strings.

## Next Phase Readiness

- `analysis/filler_triage.json` artifact is ready for Plan 03 (review stage UI) to display per-filler safe_to_remove verdicts
- `FillerTriageResult` model is importable from `podcast_pipeline.models.triage`
- Triage is integrated into AnalyzeStage.run() at the end of the analysis pipeline

---
*Phase: 08-intelligent-cut-quality*
*Completed: 2026-02-21*

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/podcast_pipeline/models/triage.py | FOUND |
| src/podcast_pipeline/stages/analyze.py | FOUND |
| tests/test_triage.py | FOUND |
| tests/test_analyze.py | FOUND |
| .planning/phases/08-intelligent-cut-quality/08-02-SUMMARY.md | FOUND |
| Commit 297496b (Task 1) | FOUND |
| Commit f582cb3 (Task 2) | FOUND |
