# Architecture

**Analysis Date:** 2026-02-04

## Pattern Overview

**Overall:** Stage-based pipeline with file-backed job state

**Key Characteristics:**
- Sequential stage orchestration via `Pipeline` (`src/podcast_pipeline/pipeline.py`)
- File-based artifacts per job (`jobs/<job_id>/...` in `src/podcast_pipeline/models/job.py`)
- Pluggable AI providers (`src/podcast_pipeline/providers/*`)

## Layers

**Entry/UI:**
- Purpose: Human interaction via CLI and Streamlit
- Location: `src/podcast_pipeline/cli.py`, `src/podcast_pipeline/ui/app.py`
- Contains: Command handlers, Streamlit pages, review UI helpers
- Depends on: Pipeline, job models, review helpers
- Used by: End users

**Pipeline Orchestration:**
- Purpose: Execute stages in order and manage job state
- Location: `src/podcast_pipeline/pipeline.py`
- Contains: `Pipeline`, `create_and_run_pipeline`
- Depends on: Stages, job models, config
- Used by: CLI, UI

**Stages:**
- Purpose: Implement ingest/transcribe/analyze/review/render
- Location: `src/podcast_pipeline/stages/*`
- Contains: `Stage` base + concrete stages
- Depends on: Config, models, utils, providers
- Used by: Pipeline

**Domain Models:**
- Purpose: Typed data for jobs, transcripts, analysis results
- Location: `src/podcast_pipeline/models/*`
- Contains: `Job`, `JobStage`, `AnalysisResult`, `TranscriptResult`, etc.
- Depends on: Pydantic
- Used by: Stages, providers, UI

**Providers:**
- Purpose: AI analysis integrations
- Location: `src/podcast_pipeline/providers/*`
- Contains: Gemini + Kimi provider implementations
- Depends on: external APIs, tenacity, httpx
- Used by: Analyze stage

**Research:**
- Purpose: YouTube trend/competitor research
- Location: `src/podcast_pipeline/research/*`
- Contains: `YouTubeResearcher`, `ViralDetector`
- Depends on: httpx, pydantic
- Used by: (not wired into pipeline yet)

**Utilities:**
- Purpose: Cross-cutting helpers (FFmpeg, logging, time)
- Location: `src/podcast_pipeline/utils/*`
- Contains: FFmpeg wrappers, logging setup, timestamp utilities
- Used by: Stages and providers

## Data Flow

**Pipeline Run (default order):**

1. **Ingest** (`src/podcast_pipeline/stages/ingest.py`)
   - Inputs: `job.input_file` (`src/podcast_pipeline/models/job.py`)
   - Outputs: `jobs/<job_id>/input/raw.*`, `jobs/<job_id>/intermediate/audio.wav`,
     `jobs/<job_id>/intermediate/proxy.mp4`, `jobs/<job_id>/intermediate/metadata.json`
2. **Transcribe** (`src/podcast_pipeline/stages/transcribe.py`)
   - Inputs: `jobs/<job_id>/intermediate/audio.wav`
   - Outputs: `jobs/<job_id>/analysis/transcript.json`, `jobs/<job_id>/analysis/filler_cuts.json`,
     `jobs/<job_id>/output/transcripts/transcript.{txt,srt,vtt}`
3. **Analyze** (`src/podcast_pipeline/stages/analyze.py`)
   - Inputs: `jobs/<job_id>/analysis/transcript.json`, `jobs/<job_id>/intermediate/proxy.mp4`
   - Outputs: `jobs/<job_id>/analysis/analysis.json`
4. **Review** (`src/podcast_pipeline/stages/review.py`)
   - Inputs: `jobs/<job_id>/analysis/analysis.json`, `jobs/<job_id>/analysis/filler_cuts.json`
   - Outputs: `jobs/<job_id>/review/review_state.json`
5. **Render** (`src/podcast_pipeline/stages/render.py`)
   - Inputs: `jobs/<job_id>/review/review_state.json`, `jobs/<job_id>/input/raw.*`
   - Outputs: `jobs/<job_id>/output/<platform>/*`, `jobs/<job_id>/output/marketing/copy.md`

**State Management:**
- Job state stored in `jobs/<job_id>/state.json` and updated per stage (`src/podcast_pipeline/models/job.py`)

## Key Abstractions

**Stage:**
- Purpose: Encapsulate stage execution with status updates
- Examples: `src/podcast_pipeline/stages/base.py`, `src/podcast_pipeline/stages/ingest.py`
- Pattern: `Stage.run()` implements logic; `Stage.execute()` handles job state

**Pipeline:**
- Purpose: Stage sequencing + orchestration
- Examples: `src/podcast_pipeline/pipeline.py`
- Pattern: `Pipeline.run()` iterates `STAGE_ORDER`

**Providers:**
- Purpose: AI analysis interfaces
- Examples: `src/podcast_pipeline/providers/gemini.py`, `src/podcast_pipeline/providers/kimi.py`
- Pattern: `BaseProvider.analyze()` returns `AnalysisResult`

## Entry Points

**CLI:**
- Location: `src/podcast_pipeline/cli.py`
- Triggers: `podcast-pipeline` console script (`pyproject.toml`)
- Responsibilities: Job creation, pipeline execution, review helpers

**Streamlit UI:**
- Location: `src/podcast_pipeline/ui/app.py`
- Triggers: `streamlit run ...` or `podcast-pipeline ui`
- Responsibilities: Job dashboard, review UI, approvals

## Error Handling

**Strategy:**
- Stage-level try/except with `StageResult` + job status updates

**Patterns:**
- `Stage.execute()` catches exceptions and marks stage failed (`src/podcast_pipeline/stages/base.py`)
- Providers raise `ProviderError` variants (`src/podcast_pipeline/providers/base.py`)

## Cross-Cutting Concerns

**Logging:** Structured logging via `structlog` (`src/podcast_pipeline/utils/logging.py`)
**Validation:** Pydantic models for config and artifacts (`src/podcast_pipeline/config/settings.py`)
**Authentication:** API keys loaded from environment (`src/podcast_pipeline/config/settings.py`)

---

*Architecture analysis: 2026-02-04*
