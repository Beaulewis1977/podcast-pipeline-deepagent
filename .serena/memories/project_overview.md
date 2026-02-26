# Project Overview

**podcast-pipeline** is an AI-powered podcast production pipeline that transforms raw video
recordings into polished, multi-platform content.

## Purpose

Processes raw podcast video/audio recordings through a multi-stage pipeline:
`ingest → transcribe → analyze → review → render`

Produces: edited video files, multi-platform clips (YouTube 16:9, TikTok 9:16, LinkedIn 1:1),
ASS captions burned in, branding overlays, normalized audio, transcripts, and AI-generated
titles/thumbnails/show notes.

## Tech Stack

- **Language**: Python 3.12+ (primary), TypeScript/Vue (desktop UI — future), Rust/Bash (scripts)
- **Package Manager**: `uv` with `pyproject.toml` + hatchling build backend
- **Audio/Video**: FFmpeg (system dep), faster-whisper, pyloudnorm, pydub, soundfile, scipy
- **AI Providers**: Google Gemini (primary), Kimi/Moonshot (fallback), OpenAI (fallback), Anthropic Claude
- **CLI**: Typer with Rich formatting
- **Config**: Pydantic v2 models, PyYAML, python-dotenv
- **Web UI**: Streamlit review interface
- **API Service**: FastAPI + Uvicorn (backend service)
- **Logging**: structlog (structured JSON logging)
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Linting**: Ruff (lint + format), mypy strict mode
- **GPU (optional)**: CUDA 12.8 (cu128), PyTorch, RIFE frame interpolation (RTX 5060 Ti sm_120)

## Entry Points

- CLI: `uv run podcast-pipeline --help` (Typer app in `src/podcast_pipeline/cli.py`)
- Streamlit UI: launched via CLI
- FastAPI service: `src/podcast_pipeline/service/app.py`
- MCP Server (dev-only): `src/podcast_pipeline/mcp/ffmpeg_server.py`

## Current Development Phase

**Phase 9: Branding, Captions & Sync** (`feat/phase9-branding-captions-sync`)
- Phase 9 adds: `utils/branding.py`, `utils/captions.py`, `utils/sync.py`
- `models/branding.py`: BrandingProfile with per-platform override support
- ASS caption engine with word-level highlight timing (16:9, 9:16, 1:1)
- Bounded cross-correlation audio sync estimator (clap detection + confidence scoring)
- MCP FFmpeg server with 14 Phase-9 media operations (dev-only tool)

## Milestone

`v1.0 — Streamlit-first release`
After v1.0: desktop distribution (Rust + Tauri v2) reusing the Python backend.

## Repository

https://github.com/Beaulewis1977/podcast-pipeline-deepagent
License: MIT
