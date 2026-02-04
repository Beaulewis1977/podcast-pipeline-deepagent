# Phase 1: Wiring + Stability - Research

**Researched:** 2026-02-04
**Domain:** End-to-end pipeline wiring (multi-track transcription, edit plan, render cuts, research integration, UI wiring)
**Confidence:** HIGH

## Summary

This phase is about wiring the existing stage-based pipeline so that artifacts and review decisions actually drive outputs. The codebase already has a well-defined stage architecture (`Stage` + `Pipeline`), Pydantic models for artifacts, and a Streamlit UI that loads `analysis.json` and `review_state.json`. The highest-leverage work is to make multi-track transcription the default when multiple audio streams exist, produce a canonical `edit_plan.json` after review, and apply that edit plan in render using FFmpeg trim/concat so outputs reflect approved cuts and clips.

Research and viral modules already exist (`research/youtube.py`, `research/viral_detector.py`) but are not wired into `AnalyzeStage` or the UI. The standard approach is to run research and viral scoring in the analyze stage, persist artifacts alongside `analysis.json`, and surface those artifacts in the review UI for decision-making. Progress reporting should be added to job stage state (or a parallel progress file) so Streamlit can poll without blocking.

**Primary recommendation:** Treat `edit_plan.json` as the single source of truth for cuts/clips, wire multi-track transcription into the default transcribe stage, and make render consume edit_plan (not raw input) for both full-length and short-form outputs.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FFmpeg / FFprobe | external | Media processing and trimming | Industry standard CLI; already wrapped in `utils/ffmpeg.py` |
| faster-whisper | >=1.1.0 | Transcription | Current engine used in `TranscribeStage` |
| Streamlit | >=1.42.0 | Review UI | Existing UI runtime |
| Pydantic v2 | >=2.10.0 | Models + JSON serialization | Standardized artifact schema |
| Typer | >=0.15.0 | CLI entry points | Existing CLI pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | >=0.28.0 | YouTube API + provider calls | Research + provider integration |
| google-genai | >=1.0.0 | Gemini provider | Analysis stage |
| structlog | >=24.4.0 | Logging | Stage logs and debugging |
| tenacity | >=9.0.0 | Retries | Provider robustness |
| pyloudnorm | >=0.1.1 | Loudness normalization | Render audio normalization |
| pydub | >=0.25.1 | Audio utilities | Audio prep utilities |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FFmpeg CLI wrappers | moviepy / python-ffmpeg | Slower, adds complexity; project explicitly avoids these |
| faster-whisper | original whisper | Slower, heavier dependencies; project explicitly avoids |
| provider abstractions | langchain | Overhead and not aligned with current stack |

**Installation:**
```bash
pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```
src/podcast_pipeline/
├── stages/        # ingest/transcribe/analyze/review/render
├── models/        # Pydantic job + artifact models
├── research/      # YouTube + viral scoring
├── ui/            # Streamlit UI
└── utils/         # FFmpeg/logging helpers
```

### Pattern 1: Stage Artifacts as JSON
**What:** Each stage writes structured artifacts under `jobs/<job_id>/...` and returns outputs via `StageResult`.
**When to use:** For any new artifact (e.g., `edit_plan.json`, `research.json`, `viral_signals.json`).
**Example:**
```python
# Source: src/podcast_pipeline/stages/transcribe.py
transcript_path = analysis_dir / "transcript.json"
transcript_path.write_text(result.model_dump_json(indent=2))
```

### Pattern 2: Stage Orchestration via Pipeline
**What:** `Pipeline.run()` advances stages in `STAGE_ORDER` and persists job state.
**When to use:** For default end-to-end execution or incremental stage runs.
**Example:**
```python
# Source: src/podcast_pipeline/pipeline.py
for stage_name in stages_to_run:
    result = stage_impl.execute(job, job_dir)
```

### Anti-Patterns to Avoid
- **Writing stage outputs outside `jobs/<job_id>`:** breaks UI + pipeline expectations.
- **Manual JSON without Pydantic models:** inconsistent artifacts and validation gaps.
- **UI creating separate job IDs:** causes duplication and broken state links.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| FFmpeg invocation | Custom subprocess wrappers | `utils/ffmpeg.run_ffmpeg` | Centralized logging + error handling |
| Artifact serialization | ad-hoc JSON | `model_dump_json` on Pydantic models | Consistent schemas |
| Provider retries | manual loops | `tenacity` (already used) | Standardized retry behavior |

**Key insight:** Keep all artifacts and state updates in the pipeline/stage layer; UI should only read/write existing artifacts and state.

## Common Pitfalls

### Pitfall 1: Job ID Mismatch Between UI and Pipeline
**What goes wrong:** UI creates a job directory, then `Pipeline.create_job` generates a different job ID, resulting in duplicate jobs and broken state.
**Why it happens:** Two sources of truth for job creation.
**How to avoid:** Make UI call a single job-creation path that returns the canonical job ID and uses the same directory.
**Warning signs:** Job list shows duplicates; inputs and outputs split across directories.

### Pitfall 2: Multi-Track Transcription Not Default
**What goes wrong:** Single-track transcription runs even when multiple audio streams exist, losing speaker separation.
**Why it happens:** `TranscribeStage.run` is called without track detection.
**How to avoid:** Detect audio tracks early and route to `transcribe_multi_track` when count > 1.
**Warning signs:** No `transcript_track_*.json` outputs for multi-track inputs.

### Pitfall 3: Review Decisions Not Applied in Render
**What goes wrong:** Render exports full-length video/audio ignoring cut approvals.
**Why it happens:** `_build_cuts_filter` is stubbed and no `edit_plan.json` is produced.
**How to avoid:** Generate `edit_plan.json` after review and consume it in render via FFmpeg trim/concat.
**Warning signs:** Output duration matches original input even with cuts approved.

### Pitfall 4: Unsafe Metadata Parsing
**What goes wrong:** `eval()` used on FPS strings from FFprobe.
**Why it happens:** Quick parsing shortcut in `utils/ffmpeg.py`.
**How to avoid:** Replace with safe fraction parsing (`fractions.Fraction`).
**Warning signs:** Security audit flags, or unexpected FPS values.

## Code Examples

### Multi-Track Transcription Path
```python
# Source: src/podcast_pipeline/stages/transcribe.py
tracks = self._detect_audio_tracks(video_path)
if len(tracks) <= 1:
    return self.run(job, job_dir)
return self.transcribe_multi_track(job, job_dir)
```

### Stage Outputs and Job Updates
```python
# Source: src/podcast_pipeline/stages/base.py
job.update_stage(self.name, StageStatus.RUNNING)
job.save(self.config.paths.jobs_dir)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Full-length render always | Edit-plan-driven trim/concat render | Phase 1 | Outputs reflect approved cuts |
| Single-track default | Multi-track default when available | Phase 1 | Speaker labels + cleaner edits |
| Analysis only | Analysis + research + viral signals | Phase 1 | Better clip/title decisions |

**Deprecated/outdated:**
- `_build_cuts_filter` stub in render; must be replaced with real trim/concat logic.

## Open Questions

1. **Edit plan schema details**
   - What we know: needs approved filler cuts, content cuts, and clip ranges.
   - What's unclear: whether clip ranges are absolute timeline or post-cut timeline.
   - Recommendation: keep clip ranges in absolute input timeline to avoid ambiguity.

2. **Progress reporting format**
   - What we know: UI needs stage progress without blocking.
   - What's unclear: whether to store progress in `state.json` vs separate `progress.json`.
   - Recommendation: add progress fields to `JobStage` for simplicity unless UI polling requires a separate file.

## Sources

### Primary (HIGH confidence)
- Local codebase: `src/podcast_pipeline/stages/*`, `src/podcast_pipeline/models/*`, `src/podcast_pipeline/ui/app.py`
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STACK.md`, `.planning/codebase/CONVENTIONS.md`

### Secondary (MEDIUM confidence)
- `codex/APP_RESEARCH_REPORT.md` for gap identification and wiring priorities

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - from `pyproject.toml` and codebase
- Architecture: HIGH - from codebase + architecture map
- Pitfalls: HIGH - directly observed in code + research report

**Research date:** 2026-02-04
**Valid until:** 2026-03-05
