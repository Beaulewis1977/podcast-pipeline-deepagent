# Architecture Research: Podcast Production Pipeline

**Researched:** 2026-02-04
**Sources:** `src/podcast_pipeline/*`, `codex/APP_RESEARCH_REPORT.md`
**Confidence:** MEDIUM (internal sources only; no external verification)

## System Overview

A staged pipeline processes a job directory on disk. Stages are run in order and write artifacts for downstream stages. The Streamlit UI and CLI both call the same pipeline.

```
Raw Video → INGEST → TRANSCRIBE → ANALYZE → REVIEW → RENDER → Outputs
                          ↑
                     Research (planned integration)
```

## Core Components

### Pipeline Orchestrator
- Purpose: Run stages in sequence, track state
- Implementation: `src/podcast_pipeline/pipeline.py`
- State: `jobs/<job_id>/state.json` (`src/podcast_pipeline/models/job.py`)

### Stages
- Ingest: Extract metadata, audio, proxy (`src/podcast_pipeline/stages/ingest.py`)
- Transcribe: Whisper transcription + filler detection (`src/podcast_pipeline/stages/transcribe.py`)
- Analyze: AI analysis with Gemini/Kimi (`src/podcast_pipeline/stages/analyze.py`)
- Review: Human approvals saved to `review_state.json` (`src/podcast_pipeline/stages/review.py`)
- Render: Platform exports and marketing doc (`src/podcast_pipeline/stages/render.py`)

### Providers
- Gemini + Kimi provider implementations under `src/podcast_pipeline/providers/*`

### UI + CLI
- Streamlit UI in `src/podcast_pipeline/ui/app.py`
- Typer CLI in `src/podcast_pipeline/cli.py`

## Data Flow (Actual Files)

```
jobs/<job_id>/
├── state.json
├── input/raw.*
├── intermediate/
│   ├── metadata.json
│   ├── audio.wav
│   └── proxy.mp4
├── analysis/
│   ├── transcript.json
│   ├── filler_cuts.json
│   └── analysis.json
├── review/review_state.json
└── output/
    ├── transcripts/
    ├── marketing/
    └── <platform>/
```

## Key Patterns

### Stage Execution
- `Stage.execute()` updates job status and saves state (`src/podcast_pipeline/stages/base.py`)
- `Stage.run()` performs the actual work

### Provider Abstraction
- `BaseProvider` + `AnalysisProvider` protocol (`src/podcast_pipeline/providers/base.py`)

### File-Backed State
- Job state and artifacts are persisted on disk for resumability

## Planned Extensions (From Research Report)

- Integrate research outputs into Analyze stage (`research.json`, `viral_signals.json`)
- Apply edit plans in render using FFmpeg trim/concat
- Background worker for long-running stages with progress polling
- Desktop UI (Tauri v2) consuming the same Python backend
