# Codebase Concerns

**Analysis Date:** 2026-02-04

## Tech Debt

**Render cuts not applied:**
- Issue: `_build_cuts_filter` returns empty string and render ignores approved cuts
- Files: `src/podcast_pipeline/stages/render.py`
- Impact: Final exports ignore filler/content cuts; outputs remain full-length
- Fix approach: Build trim/concat filter from `review_state.json` decisions and apply in `_render_video`

**Multi-track transcription not wired:**
- Issue: `transcribe_multi_track()` exists but pipeline always uses `TranscribeStage.run()`
- Files: `src/podcast_pipeline/stages/transcribe.py`, `src/podcast_pipeline/pipeline.py`
- Impact: Multi-track inputs get single-track transcription only
- Fix approach: Detect audio track count from ingest metadata and route to multi-track path

**UI job creation mismatch:**
- Issue: UI writes a job directory and then calls `Pipeline.create_job()` which creates a new job ID
- Files: `src/podcast_pipeline/ui/app.py`, `src/podcast_pipeline/pipeline.py`
- Impact: Duplicate job directories; UI job ID differs from pipeline job ID
- Fix approach: Add a pipeline method to create a job from an existing path + job_id

**Research modules not integrated:**
- Issue: Research code exists but isn’t called by pipeline or UI
- Files: `src/podcast_pipeline/research/youtube.py`, `src/podcast_pipeline/research/viral_detector.py`, `src/podcast_pipeline/stages/analyze.py`
- Impact: Research insights never surface in analysis or review
- Fix approach: Run research in Analyze stage and write `research.json` artifacts

## Known Bugs

**Missing dependency for render:**
- Symptoms: `ImportError: No module named 'numpy'` when render stage runs
- Files: `src/podcast_pipeline/stages/render.py`, `pyproject.toml`
- Trigger: Render stage imports `numpy` but dependency not listed
- Workaround: Install numpy manually

## Security Considerations

**Unsafe eval on FFprobe frame rate:**
- Risk: `eval()` on FFprobe output could be exploited if input is untrusted
- Files: `src/podcast_pipeline/utils/ffmpeg.py`
- Current mitigation: None
- Recommendations: Replace `eval()` with safe fraction parsing (e.g., `fractions.Fraction`)

## Performance Bottlenecks

**Synchronous long-running stages:**
- Problem: Transcription + render run in-process and block UI
- Files: `src/podcast_pipeline/ui/app.py`, `src/podcast_pipeline/stages/transcribe.py`
- Cause: No background worker/queue
- Improvement path: Add job runner process + progress polling

## Fragile Areas

**Filesystem-only job state:**
- Files: `src/podcast_pipeline/models/job.py`, `src/podcast_pipeline/pipeline.py`
- Why fragile: Corruption or partial writes can break job recovery
- Safe modification: Keep atomic writes; add validation before load
- Test coverage: Minimal for failure/restore scenarios

## Scaling Limits

**Single-machine execution:**
- Current capacity: One job at a time on local machine
- Limit: Large files + GPU workloads block UI and CLI
- Scaling path: Background worker pool + job queue

## Dependencies at Risk

**External binaries and APIs:**
- Risk: FFmpeg/FFprobe missing or incompatible
- Impact: Ingest/transcribe/render fail
- Migration plan: Bundle FFmpeg or validate at startup (`src/podcast_pipeline/utils/ffmpeg.py`)

**AI provider availability:**
- Risk: Gemini/Kimi API limits or key misconfig
- Impact: Analyze stage fails
- Migration plan: Add retry/backoff + fallback provider selection (`src/podcast_pipeline/stages/analyze.py`)

## Missing Critical Features

**Edit plan + cut rendering:**
- Problem: Review decisions are not applied in render
- Blocks: Producing edited outputs aligned with human review

**Research-driven analysis:**
- Problem: Research output never influences AI suggestions or UI
- Blocks: Title/thumbnail improvements based on competitive insights

## Test Coverage Gaps

**Stage integration:**
- What's not tested: End-to-end run with ingest → transcribe → analyze → render
- Files: `src/podcast_pipeline/stages/*`, `src/podcast_pipeline/pipeline.py`
- Risk: Stage contract mismatches go unnoticed
- Priority: High

**Render application of cuts:**
- What's not tested: Applying approved cuts to outputs
- Files: `src/podcast_pipeline/stages/render.py`
- Risk: Feature regresses or stays stubbed
- Priority: High

---

*Concerns audit: 2026-02-04*
