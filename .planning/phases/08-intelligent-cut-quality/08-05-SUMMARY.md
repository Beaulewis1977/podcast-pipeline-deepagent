---
phase: 08-intelligent-cut-quality
plan: 05
subsystem: infra
tags: [rife, subprocess, frame-interpolation, rife-bridge, tests, pose-match]

# Dependency graph
requires:
  - phase: 08-intelligent-cut-quality
    provides: RifeBridge class with generate() method in rife_bridge.py

provides:
  - Fixed RifeBridge.generate() with upstream-compatible CLI contract (no --output flag)
  - subprocess.run called with cwd=work_dir so RIFE writes output to work_dir/output/
  - PYTHONPATH=rife_dir injected into subprocess env for model import resolution
  - Output collected from work_dir/output/img*.png (not work_dir/*.png)
  - Corrected docstring: "4.26 exists but 4.25 recommended" (not "4.26 does not exist")
  - Updated tests asserting --output absent, cwd kwarg present, output/img*.png collection
affects: [08-intelligent-cut-quality, render-pose-match, rife-bridge-consumers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RIFE subprocess uses cwd= to control output dir (inference_img.py writes to ./output/ relative to cwd)"
    - "PYTHONPATH injection for subprocess when cwd differs from module repo directory"

key-files:
  created: []
  modified:
    - src/podcast_pipeline/utils/rife_bridge.py
    - tests/test_rife_bridge.py

key-decisions:
  - "RIFE inference_img.py does NOT accept --output flag; output is written to ./output/ relative to cwd"
  - "subprocess.run must set cwd=work_dir (=output_dir) so RIFE output ends up in work_dir/output/"
  - "PYTHONPATH=rife_dir must be injected so RIFE relative model imports resolve when cwd is not the RIFE repo"
  - "script_path must be resolved (absolute) in cmd list so subprocess finds it when cwd differs from rife_dir"
  - "Glob pattern changed from output_dir.glob('*.png') to (work_dir/'output').glob('img*.png')"
  - "RIFE 4.26 does exist; docstring corrected to say 4.25 recommended rather than 4.26 does not exist"

patterns-established:
  - "Test RIFE subprocess contract: assert --output absent, assert cwd in kwargs, assert img prefix in output subdir"
  - "Create mock RIFE output in out_dir/output/img*.png (not out_dir/*.png) for subprocess success tests"

# Metrics
duration: 8min
completed: 2026-02-23
---

# Phase 8 Plan 05: RIFE Bridge --output Bug Fix Summary

**Fixed critical RIFE subprocess bug: removed --output flag, added cwd=work_dir, PYTHONPATH injection, and img*.png output collection from work_dir/output/ subdirectory**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-23T23:25:53Z
- **Completed:** 2026-02-23T23:35:00Z
- **Tasks:** 2 (1 code fix, 1 test update)
- **Files modified:** 2

## Accomplishments

- Removed `--output` flag from RIFE subprocess cmd — upstream `inference_img.py` does not accept this argument and would fail with "unrecognized arguments"
- Set `cwd=str(work_dir)` where `work_dir = output_dir` so RIFE writes to `./output/` relative to the process working directory
- Injected `PYTHONPATH=rife_dir` into subprocess env so RIFE's relative model imports (`from model.RIFE_HDv3 import device`) resolve correctly when `cwd` is `work_dir` (not the RIFE repo directory)
- Resolved `script_path` to absolute path in cmd so subprocess finds the script regardless of `cwd`
- Changed glob from `output_dir.glob("*.png")` to `(work_dir / "output").glob("img*.png")` matching actual RIFE output structure
- Corrected module docstring: RIFE 4.26 exists but 4.25 is recommended; removed false "4.26 does not exist" claim
- Updated tests: fixed existing test mock setup to use `out_dir/output/img*.png` structure; added `--output` absence and `cwd` kwarg assertions; added two new tests explicitly verifying the upstream contract

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix RIFE bridge --output bug and use cwd-based output collection** - `44dd4ca` (fix)
2. **Task 2: Update RIFE bridge tests for upstream-compatible CLI contract** - `b273c8a` (test)

**Plan metadata:** (created in final commit)

## Files Created/Modified

- `/home/kngpnn/dev/podcast-pipeline-deepagent/src/podcast_pipeline/utils/rife_bridge.py` - Removed --output flag, added cwd=work_dir, PYTHONPATH env injection, fixed glob pattern and docstring
- `/home/kngpnn/dev/podcast-pipeline-deepagent/tests/test_rife_bridge.py` - Fixed existing mock setup for output subdir structure; added --output absence + cwd assertions; added 2 new contract tests (14 total, all passing)

## Decisions Made

- rife_bridge.py was already partially fixed from the Phase 8 original execution but had the original `--output` bug. The re-execution fully replaced the subprocess invocation block per the research-verified pattern.
- render.py `_apply_pose_match_pass()` confirmed correct: it calls `rife.generate(frame_a, frame_b, bridge_dir, num_frames=...)` and uses the returned `list[Path]`. No changes needed since generate()'s return type is unchanged.

## Deviations from Plan

None - plan executed exactly as written. Task 1 applied the research-verified fix to rife_bridge.py. Task 2 updated tests to match the new output collection contract.

## Issues Encountered

`test_rife_bridge_subprocess_success_returns_sorted_pngs` was failing before this plan (1 of 12 tests failed) because it created PNGs directly in `out_dir` but the fixed implementation globs from `out_dir/output/img*.png`. This was the expected pre-existing failing test that this plan was designed to fix.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RIFE bridge now has upstream-compatible CLI contract; will not fail on real practical-RIFE installations
- render.py `_apply_pose_match_pass` continues to work unchanged (same generate() API)
- All 14 rife_bridge tests pass with the corrected subprocess behavior

---
*Phase: 08-intelligent-cut-quality*
*Completed: 2026-02-23*

## Self-Check: PASSED

- FOUND: src/podcast_pipeline/utils/rife_bridge.py
- FOUND: tests/test_rife_bridge.py
- FOUND: .planning/phases/08-intelligent-cut-quality/08-05-SUMMARY.md
- FOUND: commit 44dd4ca (fix: RIFE bridge --output bug fix)
- FOUND: commit b273c8a (test: RIFE bridge upstream contract tests)
