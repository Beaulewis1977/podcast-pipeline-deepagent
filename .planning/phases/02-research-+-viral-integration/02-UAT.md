---
status: testing
phase: 02-research-+-viral-integration
source:
  - .planning/phases/02-research-+-viral-integration/02-01-SUMMARY.md
  - .planning/phases/02-research-+-viral-integration/02-02-SUMMARY.md
  - .planning/phases/02-research-+-viral-integration/02-03-SUMMARY.md
  - .planning/phases/02-research-+-viral-integration/02-04-SUMMARY.md
  - .planning/phases/02-research-+-viral-integration/02-05-SUMMARY.md
started: 2026-02-04T05:49:22Z
updated: 2026-02-04T06:04:10Z
---

## Current Test

number: 2
name: Create a job and reach Marketing tab
expected: |
  From the UI:
  - Dashboard shows a "Create New Job" expander.
  - After uploading a video and creating a job, clicking "Open" takes you to the editor.
  - The editor shows the tab set including "📝 Marketing".
  - If the job auto-runs the pipeline, transcription should complete (or gracefully fall back to CPU) so the job can proceed to analyze/review.
awaiting: user response

## Tests

### 1. Research panel shows enriched metrics
expected: In the Streamlit Review page, opening "Research & Viral Insights" shows competition/tier, engagement benchmarks, weighted keywords, and UTC posting windows from `analysis/research.json`.
result: issue
reported: "theres no job and ui dont have a video for it. i dont see a marketing tab or research and viral insights. i see a dashboard, editor, settings, a deplot, a refresh, rerun, settings, print, record a screncast, and clear cache."
severity: major

### 2. Create a job and reach Marketing tab
expected: From the UI, create a new job from an uploaded video and open it so the editor shows the "📝 Marketing" tab.
result: issue
reported: "Job created and pipeline started, but transcribe stage failed with: RuntimeError: Library libcublas.so.12 is not found or cannot be loaded (faster-whisper on device=cuda)."
severity: major

### 3. UI gracefully handles legacy artifact shapes
expected: When older `viral_signals.json` or `research.json` fields are missing, the review panel still renders without crashing and uses fallback values where needed.
result: pending

### 4. Analyze artifact contains explainable combined ranking
expected: `analysis/viral_signals.json` contains `ai_score`, `detector_score`, `combined_score`, `rank`, and `score_weights` per run; no `combined_score` exceeds 10.
result: pending

### 5. Research artifact includes new metrics and posting guidance
expected: `analysis/research.json` includes engagement/velocity metrics and insight fields such as `competition_score`, `competition_tier`, and `best_posting_windows`.
result: pending

### 6. Equivalent research queries avoid duplicate upstream calls
expected: Re-running equivalent normalized YouTube queries within TTL uses cache behavior (no duplicate API fetch for same normalized request during cache window).
result: pending

## Summary

total: 6
passed: 0
issues: 2
pending: 4
skipped: 0

## Gaps

- truth: "In the Streamlit Review page, opening \"Research & Viral Insights\" shows competition/tier, engagement benchmarks, weighted keywords, and UTC posting windows from analysis/research.json."
  status: failed
  reason: "User reported: theres no job and ui dont have a video for it. i dont see a marketing tab or research and viral insights. i see a dashboard, editor, settings, a deplot, a refresh, rerun, settings, print, record a screncast, and clear cache."
  severity: major
  test: 1
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "Creating a job in the UI can proceed through transcription so the job can reach analyze/review outputs."
  status: failed
  reason: "Pipeline failed at transcribe due to CUDA runtime missing (libcublas.so.12). Default config uses transcription.device=cuda."
  severity: major
  test: 2
  root_cause: ""
  artifacts:
    - src/podcast_pipeline/stages/transcribe.py
    - config.yaml
  missing:
    - "Graceful CPU fallback (or clearer UI guidance) when CUDA libraries are unavailable"
    - "Documented CPU-only config for transcription (device=cpu, compute_type=int8)"
  debug_session: ""
