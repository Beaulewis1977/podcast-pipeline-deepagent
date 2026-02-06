---
phase: 01-wiring-+-stability
verified: 2026-02-04T01:45:30Z
status: human_needed
score: 13/13 must-haves verified
human_verification:
  - test: "Run full pipeline on a multi-track job"
    expected: "Transcript outputs include speaker labels and filler_cuts.json aggregates tracks"
    why_human: "Requires executing pipeline with multi-track media"
  - test: "Complete review in Streamlit and save"
    expected: "review/edit_plan.json updates and Research & Viral Insights panel renders when artifacts exist"
    why_human: "UI flow and artifact presence require manual review"
  - test: "Render after review completion"
    expected: "Full export reflects approved cuts and output/clips contains clip_*.mp4"
    why_human: "Needs FFmpeg render output validation"
  - test: "Analyze stage with YOUTUBE_API_KEY set"
    expected: "analysis/research.json and analysis/viral_signals.json are written"
    why_human: "Depends on external API access"
---

# Phase 1: Wiring + Stability Verification Report

**Phase Goal:** End-to-end pipeline produces real edited outputs with multi-track transcription, applied cuts, and reliable job state.
**Verified:** 2026-02-04T01:45:30Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Creating a job from Streamlit yields one canonical job ID used by pipeline and filesystem. | ✓ VERIFIED | `app.py` uses `pipeline.create_job(..., job_id=...)` and job_dir uses same ID. |
| 2 | Stage progress is persisted in job state and visible in the UI stage status. | ✓ VERIFIED | `JobStage` has progress fields; UI renders them when present. |
| 3 | Review completion produces edit_plan.json that captures approved cuts and clip ranges. | ✓ VERIFIED | `ReviewStage` calls `write_edit_plan` on completion; edit plan schema exists. |
| 4 | Review UI surfaces research and viral artifacts when present. | ✓ VERIFIED | UI expander loads `research.json` and `viral_signals.json` with fallbacks. |
| 5 | Multi-track inputs produce merged, speaker-labeled transcripts by default. | ✓ VERIFIED | `TranscribeStage.run` routes multi-track jobs to `transcribe_multi_track`. |
| 6 | Combined filler cut list reflects all tracks. | ✓ VERIFIED | `transcribe_multi_track` merges filler cuts across tracks and sorts by time. |
| 7 | Config defaults are aligned between config.yaml and settings.py. | ✓ VERIFIED | Both use `gemini-2.5-flash-latest` defaults. |
| 8 | FFmpeg metadata parsing no longer uses eval for FPS. | ✓ VERIFIED | `_parse_fps` uses `Fraction` and `eval` removed. |
| 9 | Dependencies include all runtime imports used in render and research stages. | ✓ VERIFIED | `soundfile` declared; research uses `httpx` already in deps. |
| 10 | Render outputs reflect approved cuts from edit_plan.json (not full-length by default). | ✓ VERIFIED | Render builds edit-plan filter_complex and uses it when cuts exist. |
| 11 | Selected clip ranges are exported as short-form clips. | ✓ VERIFIED | `_export_clips` writes `output/clips/clip_*.mp4` from edit plan. |
| 12 | Analyze stage writes research.json when YouTube API key is configured. | ✓ VERIFIED | `_run_research` writes `analysis/research.json` when `YOUTUBE_API_KEY` exists. |
| 13 | Analyze stage writes viral_signals.json with per-clip viral scores. | ✓ VERIFIED | `_run_viral_signals` writes `analysis/viral_signals.json`. |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/podcast_pipeline/pipeline.py` | job_id override | ✓ VERIFIED | `create_job(..., job_id=...)` supported and used. |
| `src/podcast_pipeline/models/job.py` | progress fields + helper | ✓ VERIFIED | progress fields + `update_stage_progress`. |
| `src/podcast_pipeline/ui/app.py` | job creation + progress UI | ✓ VERIFIED | job_id passthrough + progress rendering. |
| `src/podcast_pipeline/models/edit_plan.py` | EditPlan model | ✓ VERIFIED | schema for cuts + clips. |
| `src/podcast_pipeline/stages/review.py` | edit plan generation | ✓ VERIFIED | `write_edit_plan` invoked on completion. |
| `src/podcast_pipeline/stages/transcribe.py` | multi-track default | ✓ VERIFIED | track count detection + routing. |
| `config.yaml` | aligned defaults | ✓ VERIFIED | defaults match settings. |
| `pyproject.toml` | runtime deps | ✓ VERIFIED | `soundfile` added. |
| `src/podcast_pipeline/utils/ffmpeg.py` | safe FPS parsing | ✓ VERIFIED | `Fraction` parser. |
| `src/podcast_pipeline/stages/render.py` | cut + clip exports | ✓ VERIFIED | filter_complex + clip loop. |
| `src/podcast_pipeline/stages/analyze.py` | research + viral output | ✓ VERIFIED | writes research/viral artifacts. |
| `src/podcast_pipeline/research/youtube.py` | YouTube researcher | ✓ VERIFIED | `YouTubeResearcher` used by analyze. |
| `src/podcast_pipeline/research/viral_detector.py` | viral scoring | ✓ VERIFIED | `ViralClipDetector` used by analyze. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `ui/app.py` | `Pipeline.create_job` | job_id passthrough | ✓ WIRED | `create_job(..., job_id=job_id)` present. |
| `stages/base.py` | `jobs/<job_id>/state.json` | job.save | ✓ WIRED | `job.save(self.config.paths.jobs_dir)` used. |
| `stages/review.py` | `review/edit_plan.json` | write_edit_plan | ✓ WIRED | edit plan written on completion. |
| `ui/app.py` | `write_edit_plan` | UI save | ✓ WIRED | `save_review_decisions` calls helper. |
| `stages/transcribe.py` | `transcribe_multi_track` | track count detection | ✓ WIRED | `_get_audio_track_count` routing. |
| `utils/ffmpeg.py` | `fractions.Fraction` | safe fps parse | ✓ WIRED | `_parse_fps` uses Fraction. |
| `stages/render.py` | `review/edit_plan.json` | edit plan load | ✓ WIRED | `_load_edit_plan` reads file. |
| `stages/render.py` | `output/clips` | clip export loop | ✓ WIRED | `_export_clips` writes to output/clips. |
| `stages/analyze.py` | `research/youtube.py` | YouTubeResearcher | ✓ WIRED | `_run_research` calls YouTubeResearcher. |
| `stages/analyze.py` | `research/viral_detector.py` | ViralClipDetector | ✓ WIRED | `_run_viral_signals` uses detector. |

### Requirements Coverage

No requirements are explicitly mapped to Phase 1 in `REQUIREMENTS.md`. Manual requirement status updates are still needed.

### Anti-Patterns Found

No blocker anti-patterns found. Empty list returns are intentional (e.g., no jobs, no clips).

### Human Verification Required

### 1. End-to-End Multi-Track Run

**Test:** Run ingest → render on a multi-track input.
**Expected:** speaker-labeled transcripts, combined filler cuts, and edit-plan-based outputs.
**Why human:** Requires running pipeline and inspecting generated media artifacts.

### 2. Review UI Save + Edit Plan

**Test:** In Streamlit, approve review and save edits.
**Expected:** `review/edit_plan.json` updates and insights panel renders when artifacts exist.
**Why human:** UI behavior needs manual confirmation.

### 3. Render Output Integrity

**Test:** Render after review completion.
**Expected:** full export reflects approved cuts; clips appear in `output/clips`.
**Why human:** Requires inspecting rendered media.

### 4. YouTube Research Integration

**Test:** Run analyze with `YOUTUBE_API_KEY` configured.
**Expected:** `analysis/research.json` and `analysis/viral_signals.json` created.
**Why human:** Depends on external API access.

### Gaps Summary

Automated checks passed. Manual verification is required to confirm runtime outputs and UI behavior.

---
_Verified: 2026-02-04T01:45:30Z_
_Verifier: Claude (gsd-verifier)_
