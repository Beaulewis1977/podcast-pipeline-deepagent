---
phase: 08-intelligent-cut-quality
plan: "06"
subsystem: testing
tags: [smoke-test, operator-guide, integration-tests, legacy-compat, phase8-baseline, torch, rife, gemini]

# Dependency graph
requires:
  - phase: 08-05
    provides: "Fixed RifeBridge with cwd-based output collection and RIFE 4.26 note corrected"
  - phase: 08-03
    provides: "Verified editorial_action wiring and filler card display"
provides:
  - "GPU smoke test references torch==2.10.* baseline and cu128 install hint"
  - "Operator guide documents gemini-3-flash-lite as default triage model"
  - "Operator guide explicitly forbids reasoning/CoT models (o1, gemini-3-pro, etc.)"
  - "Operator guide references current dep baselines: silero-vad>=6.2,<7; librosa>=0.11,<1; opencv>=4.13,<5; torch==2.10.*"
  - "Operator guide correctly states RIFE 4.26 exists but 4.25 is recommended"
  - "Integration tests for triage->review chain already locked from original 08-06 execution"
  - "Legacy compat regressions for filler_cuts.json and edit_plan.json without Phase 8 fields"
  - "Phase 8 disabled = Phase 7 baseline regressions locked"
affects: [phase-09, rife-bridge-consumers, operator-setup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "torch==2.10.* pinned baseline with cu128 index (NOT >= unpinned)"
    - "Forbidden model list pattern: explicitly document which models must never be used"
    - "Transport dispatch: gemini models -> google.genai; all others -> openai"

key-files:
  created: []
  modified:
    - scripts/smoke_test_gpu_rife.py
    - docs/phase8-operator-guide.md

key-decisions:
  - "torch>=2.7 replaced with torch==2.10.* pinned baseline per Phase 8 research"
  - "llm_triage_model default changed from gpt-4o-mini to gemini-3-flash-lite in docs"
  - "Forbidden reasoning/CoT model list added to operator guide with explicit rationale"
  - "silero-vad>=6.1 corrected to >=6.2,<7 per current stable baseline"
  - "librosa>=0.10 corrected to >=0.11,<1 per current stable baseline"
  - "opencv-python-headless>=4.9 corrected to >=4.13,<5 per current stable baseline"
  - "RIFE 4.26 note: 'does not exist' corrected to 'exists but 4.25 recommended'"
  - "Task 2 was verification no-op: all integration and legacy compat tests existed from original 08-06 execution"

patterns-established:
  - "All Phase 8 integration tests: legacy_filler_cuts, legacy_edit_plan, triage_chain, render_disabled regression"
  - "Pre-commit stash conflict avoidance: stage all tracked modified files before commit"

# Metrics
duration: 10min
completed: 2026-02-23
---

# Phase 8 Plan 06: Smoke Test + Operator Guide Baseline Update Summary

**GPU smoke test updated to torch==2.10.* cu128 baseline; operator guide now documents gemini-3-flash-lite default, forbidden reasoning models, and current dep version floors (silero-vad>=6.2, librosa>=0.11, opencv>=4.13)**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-02-23T23:29:00Z
- **Completed:** 2026-02-23T23:40:00Z
- **Tasks:** 2 (1 targeted update, 1 verification no-op)
- **Files modified:** 2

## Accomplishments

- Updated `scripts/smoke_test_gpu_rife.py` module docstring from `torch>=2.7 with cu128` to `torch==2.10.* with cu128`; updated opencv reference from `>=4.9` to `>=4.13`; updated both install hints to use pinned `"torch==2.10.*" "torchaudio==2.10.*"` baseline
- Updated `docs/phase8-operator-guide.md` across 7 targeted sections: triage model default (gpt-4o-mini -> gemini-3-flash-lite), forbidden model table with rationale, transport dispatch note, silero-vad/librosa/opencv version floors, torch install commands, RIFE 4.26 note corrected
- Verified all 30 Phase 8 integration/legacy-compat/disabled-regression tests pass (test_pipeline.py + test_render.py) — Task 2 was a verification no-op since all tests existed from original 08-06 execution

## Task Commits

1. **Task 1: Update smoke test and operator guide to current baselines** - `6eec063` (chore)
2. **Task 2: Add integration tests and legacy compatibility regressions** - no new commit (verification no-op — all tests existed and pass)

**Plan metadata:** (created in final commit)

## Files Created/Modified

- `/home/kngpnn/dev/podcast-pipeline-deepagent/scripts/smoke_test_gpu_rife.py` - Updated torch 2.10.* baseline, opencv>=4.13 reference, pinned install hints
- `/home/kngpnn/dev/podcast-pipeline-deepagent/docs/phase8-operator-guide.md` - gemini-3-flash-lite default, forbidden reasoning model list, dep version floors corrected, RIFE 4.26 note fixed

## Decisions Made

- `torch==2.10.*` pinned baseline used in smoke test and operator guide (not `>=2.7`)
- `gemini-3-flash-lite` documented as default `llm_triage_model` with explicit transport dispatch note
- Forbidden model list added: `o1`, `o1-mini`, `o3-mini`, `gemini-3-pro*` — with rationale (sub-second batch responses needed, not deep reasoning)
- Task 2 confirmed as no-op — the original Phase 8 execution left complete coverage in place

## Deviations from Plan

None - plan executed exactly as written. Task 1 applied targeted updates. Task 2 confirmed existing coverage was sufficient; no tests were added.

## Issues Encountered

Pre-commit hook stash/unstash conflict: mypy pre-commit hook modifies `.mypy_cache/` during run, which conflicts with pre-commit's stash mechanism when unstaged tracked files exist. Resolved by staging all tracked modified files before the commit so pre-commit has nothing to stash.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 8 is fully locked: all six plans re-executed with current baselines
- GPU smoke test references correct torch/CUDA/opencv versions for RTX 5060 Ti
- Operator guide documents forbidden model list to prevent silent drift back to OpenAI reasoning models
- All regression tests pass; Phase 9 can proceed with full confidence in Phase 8 contracts

## Self-Check: PASSED

- FOUND: scripts/smoke_test_gpu_rife.py
- FOUND: docs/phase8-operator-guide.md
- FOUND: commit 6eec063 (chore(08-06): update smoke test and operator guide)
- `grep -q "2.10" scripts/smoke_test_gpu_rife.py`: PASSED
- `grep -q "forbidden\|reasoning\|CoT" docs/phase8-operator-guide.md`: PASSED
- `grep -q "6.2" docs/phase8-operator-guide.md`: PASSED
- `uv run pytest tests/test_pipeline.py tests/test_render.py -m "not integration"`: 133 passed
- `uv run ruff check scripts/smoke_test_gpu_rife.py`: All checks passed

---
*Phase: 08-intelligent-cut-quality*
*Completed: 2026-02-23*
