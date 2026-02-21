---
phase: 08-intelligent-cut-quality
plan: 06
subsystem: testing
tags: [integration-tests, legacy-compat, gpu, rife, smoke-test, docs, regression, phase8]

# Dependency graph
requires:
  - phase: 08-03
    provides: triage-aware editorial_action, _derive_editorial_action, _load_filler_triage_map, write_edit_plan
  - phase: 08-04
    provides: VAD breath detector (vad.py), noise-floor matcher (noise_match.py), render de-breathing + noise-floor passes
  - phase: 08-05
    provides: pose_match.py scan_best_frame_pair, rife_bridge.py RifeBridge.generate(--exp), render._apply_pose_match_pass
provides:
  - scripts/smoke_test_gpu_rife.py: standalone GPU smoke test verifying torch CUDA, opencv, RIFE frame generation; prints "RIFE OK"
  - tests/test_pipeline.py Phase 8 sections: legacy filler/edit_plan backward compat + triage->review chain editorial_action integration tests + Phase 8 disabled baseline tests
  - tests/test_render.py Phase 8 regression section: de-breathing/noise-floor/pose-match disabled guard tests + noise floor threshold semantics + Phase 7 config preservation
  - docs/phase8-operator-guide.md: 395-line operator guide covering all Phase 8 controls, GPU setup, RIFE installation, troubleshooting, and backward compat
affects:
  - Future operators deploying Phase 8 on RTX 5060 Ti hardware

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Standalone smoke test pattern: helper functions per check (_check_torch, _check_opencv, _resolve_rife_script) to stay under PLR0911 return-statement limit"
    - "ruff: noqa: T201 at file level to allow print() in CLI scripts"
    - "Integration test pattern: monkeypatch builtins.__import__ to simulate missing optional deps without uninstalling packages"

key-files:
  created:
    - scripts/smoke_test_gpu_rife.py
    - docs/phase8-operator-guide.md
  modified:
    - tests/test_pipeline.py
    - tests/test_render.py

key-decisions:
  - "Smoke test split into helper functions to avoid PLR0911 (too many returns in main())"
  - "Test for 'exactly at threshold = correction applied' (strict less-than semantics) renamed to test_noise_floor_exact_threshold_applies_correction to match actual code behavior"
  - "Pose match disabled test calls _apply_pose_match_pass(keep_ranges, join_kinds, video_path) with actual signature — not a hypothetical per-cut call signature"

patterns-established:
  - "Optional dep test pattern: monkeypatch builtins.__import__ to raise ImportError for specific module names"
  - "Phase 8 legacy compat test pattern: write legacy JSON without Phase 8 fields, validate model defaults are safe"

# Metrics
duration: 7min
completed: 2026-02-21
---

# Phase 8 Plan 06: Integration Tests and Operator Guide Summary

**GPU smoke test (prints "RIFE OK") + legacy/triage/disabled Phase 8 integration regressions + 395-line operator guide covering GPU setup, RIFE install, and all Phase 8 config knobs**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-02-21T08:52:42Z
- **Completed:** 2026-02-21T08:59:29Z
- **Tasks:** 2
- **Files modified:** 4 (2 new scripts/docs, 2 existing test files)

## Accomplishments

- `scripts/smoke_test_gpu_rife.py` verifies the full GPU + RIFE stack (torch CUDA, opencv-python-headless, RIFE frame generation), prints "RIFE OK" on success, exits non-zero on any failure; includes Blackwell sm_120 capability check
- 11 new integration tests in `tests/test_pipeline.py` across three test classes:
  - `TestPhase8LegacyCompatibility` (3 tests) — legacy `filler_cuts.json` and `edit_plan.json` without Phase 8 fields load and default safely
  - `TestPhase8TriageReviewChain` (4 tests) — end-to-end triage -> review chain produces correct editorial actions for disfluency, protected hedge, LLM-safe hedge, and LLM-review hedge
  - `TestPhase8RenderDisabledBaseline` (4 tests) — silero-vad, librosa, cv2 return safe sentinel values when their respective optional deps are absent
- 7 new regression tests in `tests/test_render.py` under `TestPhase8PassesDisabledRegression` — de-breathing, noise-floor, and pose-match are never called when disabled; noise floor strict less-than threshold semantics verified; Phase 7 config fields unchanged when Phase 8 disabled
- `docs/phase8-operator-guide.md` (395 lines) covers filler triage, audio/video quality passes, GPU setup, RIFE installation, smoke test, troubleshooting, and backward compat

## Task Commits

1. **Task 1: Create GPU smoke test script and integration tests** - `e11f494` (feat)
2. **Task 2: Write Phase 8 operator guide** - `0b4330b` (docs)

## Files Created/Modified

- `scripts/smoke_test_gpu_rife.py` - Created: standalone GPU smoke test verifying torch CUDA, opencv, RIFE frame generation
- `tests/test_pipeline.py` - Modified: added 11 Phase 8 integration tests (3 legacy compat + 4 triage chain + 4 disabled baseline)
- `tests/test_render.py` - Modified: added 7 Phase 8 regression tests (disabled pass guards + noise floor threshold semantics + Phase 7 preservation)
- `docs/phase8-operator-guide.md` - Created: 395-line operator guide for all Phase 8 features

## Decisions Made

- Smoke test helper functions (`_check_torch`, `_check_opencv`, `_resolve_rife_script`) isolate each check and keep `main()` under the PLR0911 return-statement limit
- `ruff: noqa: T201` applied at file level in the smoke test — `print()` is intentional and appropriate for a CLI script
- `test_noise_floor_exact_threshold_applies_correction` assertion matches actual `< threshold_db` guard semantics (at exactly threshold, correction IS applied)
- Pose-match disabled test uses the actual `_apply_pose_match_pass(keep_ranges, join_kinds, video_path)` signature from the implementation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed incorrect noise floor threshold test assertion**
- **Found during:** Task 1 (first test run)
- **Issue:** Test `test_noise_floor_exact_threshold_no_correction` asserted `result is None` at exactly `threshold_db=3.0` dB. The actual guard is `if delta_db < threshold_db: return None` — at exactly 3.0 dB, the condition is `3.0 < 3.0 = False`, so correction IS applied. The test had the semantics backwards.
- **Fix:** Renamed test to `test_noise_floor_exact_threshold_applies_correction` and changed assertion to `assert result is not None`
- **Files modified:** `tests/test_render.py`
- **Verification:** Test passes; semantics match STATE.md decision "strict less-than: exact threshold = correction applied"
- **Committed in:** `e11f494` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed pose match test to use actual method signature**
- **Found during:** Task 1 (first test run)
- **Issue:** `test_render_skips_pose_match_when_disabled` called `_apply_pose_match_pass(video_path=..., cut=..., ...)` with a hypothetical per-cut signature. The actual signature is `_apply_pose_match_pass(keep_ranges, join_kinds, video_path)`.
- **Fix:** Updated test to call the method with `(keep_ranges, join_kinds, video_path)` and verify the returned `(keep_ranges, join_kinds, {})` tuple
- **Files modified:** `tests/test_render.py`
- **Verification:** Test passes; spy confirms `scan_best_frame_pair` is never called when disabled
- **Committed in:** `e11f494` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (Rule 1 — incorrect test assertions caught on first run)
**Impact on plan:** Both fixes corrected test logic to match actual implementation. No scope creep.

## Issues Encountered

- Ruff format reformatted three files after first commit attempt; re-staged and committed clean on second attempt (normal pre-commit behavior)

## User Setup Required

None — all tests run without external service configuration. RIFE and GPU hardware are required only for the GPU smoke test (not part of regular pytest suite).

## Next Phase Readiness

- Phase 8 complete: all 6 plans executed and locked with tests
- Full Phase 8 test coverage: 133 passing tests across test_pipeline.py and test_render.py (not integration mark)
- Operator guide provides clear GPU + RIFE setup instructions for production deployment
- All Phase 8 features backward-compatible with existing jobs

## Self-Check: PASSED

| Item | Status |
|------|--------|
| scripts/smoke_test_gpu_rife.py | FOUND (executable, ruff clean) |
| tests/test_pipeline.py Phase 8 sections | FOUND (11 new tests) |
| tests/test_render.py Phase 8 regression section | FOUND (7 new tests) |
| docs/phase8-operator-guide.md | FOUND (395 lines) |
| 133 tests passing (not integration) | CONFIRMED |
| Commit e11f494 (Task 1) | FOUND |
| Commit 0b4330b (Task 2) | FOUND |

---
*Phase: 08-intelligent-cut-quality*
*Completed: 2026-02-21*
