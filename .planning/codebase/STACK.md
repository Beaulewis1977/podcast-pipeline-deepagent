# Technology Stack

**Analysis Date:** 2026-02-04

## Languages

**Primary:**
- Python 3.11+ - Core pipeline, CLI, UI, tests (`src/podcast_pipeline/*`, `tests/*`)

**Secondary:**
- YAML - Runtime configuration (`config.yaml`)
- TOML - Build/lint/test config (`pyproject.toml`)
- Markdown - Docs and reports (`README.md`, `codex/APP_RESEARCH_REPORT.md`, `.planning/*`)

## Runtime

**Environment:**
- CPython 3.11+ (project requires `>=3.11` in `pyproject.toml`)

**Package Manager:**
- uv (recommended) - lockfile: `uv.lock`
- pip (supported) - build metadata in `pyproject.toml`

## Frameworks

**Core:**
- Streamlit - Web UI (`src/podcast_pipeline/ui/app.py`)
- Typer - CLI (`src/podcast_pipeline/cli.py`)
- Pydantic v2 - Config + models (`src/podcast_pipeline/config/settings.py`, `src/podcast_pipeline/models/*`)

**Testing:**
- pytest - Test runner (`pyproject.toml`, `tests/*`)
- pytest-asyncio - Async support (`pyproject.toml`)

**Build/Dev:**
- Ruff - Lint + format (`pyproject.toml`)
- MyPy - Type checking (`pyproject.toml`)
- Hatchling - Build backend (`pyproject.toml`)

## Key Dependencies

**Critical:**
- `faster-whisper` - Transcription engine (`src/podcast_pipeline/stages/transcribe.py`)
- `google-genai` - Gemini API client (`src/podcast_pipeline/providers/gemini.py`)
- `httpx` - Kimi + YouTube API calls (`src/podcast_pipeline/providers/kimi.py`, `src/podcast_pipeline/research/youtube.py`)
- `ffmpeg` / `ffprobe` (external binaries) - Media processing (`src/podcast_pipeline/utils/ffmpeg.py`)

**Infrastructure:**
- `pyloudnorm` - Loudness normalization (`src/podcast_pipeline/stages/render.py`)
- `pydub` - Audio utilities (declared in `pyproject.toml`)
- `structlog` - Structured logging (`src/podcast_pipeline/utils/logging.py`)
- `tenacity` - Retry logic for providers (`src/podcast_pipeline/providers/gemini.py`, `src/podcast_pipeline/providers/kimi.py`)

## Configuration

**Environment:**
- API keys loaded from `.env` via `python-dotenv` (`src/podcast_pipeline/config/settings.py`)
- Key env vars: `GEMINI_API_KEY`, `KIMI_API_KEY`, `YOUTUBE_API_KEY`, `OPENAI_API_KEY` (declared)

**Build:**
- Config defaults + lint/test tooling in `pyproject.toml`
- Runtime defaults in `config.yaml` and `src/podcast_pipeline/config/settings.py`

## Platform Requirements

**Development:**
- Python 3.11+
- FFmpeg/FFprobe installed and available on PATH
- Optional CUDA GPU for faster transcription (Whisper)
- API keys for AI providers (Gemini/Kimi)

**Production:**
- Local filesystem for jobs and artifacts (`jobs/`)
- Same FFmpeg + API key requirements as development

---

*Stack analysis: 2026-02-04*
