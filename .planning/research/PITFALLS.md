# Pitfalls Research: Podcast Production Pipeline

**Researched:** 2026-02-04
**Sources:** `src/podcast_pipeline/*`, `.planning/codebase/CONCERNS.md`, `codex/APP_RESEARCH_REPORT.md`
**Confidence:** MEDIUM (internal sources only; no external verification)

## Critical Pitfalls

### 1. Edits Not Applied in Render
- **The mistake**: Review decisions exist but render ignores cuts and clips
- **Why it happens**: `_build_cuts_filter` is stubbed and not applied
- **Warning signs**: Outputs are full-length despite approved cuts
- **Prevention**: Build trim/concat filter from `review_state.json` and apply in render
- **Where**: `src/podcast_pipeline/stages/render.py`

### 2. Multi-Track Transcription Not Wired
- **The mistake**: Multi-track logic exists but is never used by pipeline
- **Why it happens**: `Pipeline` always calls `TranscribeStage.run()`
- **Warning signs**: Multi-track files produce single-track transcripts only
- **Prevention**: Detect audio track count and route to `transcribe_multi_track()`
- **Where**: `src/podcast_pipeline/stages/transcribe.py`, `src/podcast_pipeline/pipeline.py`

### 3. UI Job ID Mismatch
- **The mistake**: UI saves a job folder then `Pipeline.create_job()` creates a new job ID
- **Why it happens**: UI and pipeline both create jobs independently
- **Warning signs**: Duplicate job folders; UI job disappears
- **Prevention**: Add pipeline method to create job from existing path or allow provided job_id
- **Where**: `src/podcast_pipeline/ui/app.py`, `src/podcast_pipeline/pipeline.py`

### 4. Unsafe FFprobe FPS Parsing
- **The mistake**: Using `eval()` on FFprobe output
- **Why it happens**: `r_frame_rate` comes back as a fraction string
- **Warning signs**: Security scanners flag `eval`
- **Prevention**: Use `fractions.Fraction` for safe parsing
- **Where**: `src/podcast_pipeline/utils/ffmpeg.py`

### 5. Missing Render Dependencies
- **The mistake**: `numpy` imported in render but not in dependencies
- **Why it happens**: Dependency list not synced with implementation
- **Warning signs**: ImportError at render stage
- **Prevention**: Add `numpy` or remove unused import
- **Where**: `src/podcast_pipeline/stages/render.py`, `pyproject.toml`

## Medium-Risk Pitfalls

### 6. Long-Running Stages Block UI
- **The mistake**: Streamlit runs heavy processing in the UI thread
- **Warning signs**: UI freezes during transcription or render
- **Prevention**: Background worker + progress polling
- **Where**: `src/podcast_pipeline/ui/app.py`

### 7. API Rate Limits Kill Analyze Stage
- **The mistake**: No user-visible retry/backoff feedback
- **Prevention**: Tenacity retries + clear logging + fallback provider
- **Where**: `src/podcast_pipeline/providers/gemini.py`, `src/podcast_pipeline/providers/kimi.py`

### 8. Loudness Normalization Fails Silently
- **The mistake**: Missing optional dependencies lead to skipped normalization
- **Prevention**: Validate dependencies at startup, surface warnings in UI
- **Where**: `src/podcast_pipeline/stages/render.py`

## General Pipeline Pitfalls

- **Non-resumable state**: Avoid in-memory-only state; always write `state.json`
- **Transcript drift**: Long files require VAD and careful segmentation
- **Platform spec drift**: Keep specs in config, not hardcoded
