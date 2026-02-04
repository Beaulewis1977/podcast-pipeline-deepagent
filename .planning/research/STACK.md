# Stack Research: Podcast Production Pipeline

**Researched:** 2026-02-04
**Sources:** `pyproject.toml`, `config.yaml`, `src/podcast_pipeline/*`, `codex/APP_RESEARCH_REPORT.md`
**Confidence:** MEDIUM (internal sources only; no external verification)

## Recommended Stack

### Runtime
- **Python** 3.11+ (project requires `>=3.11` in `pyproject.toml`)
- **Local filesystem** for job artifacts (`jobs/`)

### Media Processing
- **FFmpeg/FFprobe** (external binaries, subprocess wrapper)
  - Why: industry standard for audio/video transformation
  - Implementation: `src/podcast_pipeline/utils/ffmpeg.py`
- **pyloudnorm** 0.1.1+ for LUFS normalization
  - Used in `src/podcast_pipeline/stages/render.py`
- **pydub** 0.25.1+ (declared; currently light use)

### Transcription
- **faster-whisper** 1.1.0+ (CTranslate2-backed)
  - Word-level timestamps + VAD support
  - Used in `src/podcast_pipeline/stages/transcribe.py`
- **Model:** `large-v3` (default in `config.yaml` + `settings.py`)

### AI Analysis
- **Gemini** (primary) via `google-genai` 1.0+
  - Config default: `gemini-2.5-flash` (`config.yaml`)
  - Implementation: `src/podcast_pipeline/providers/gemini.py`
- **Kimi K2.5** (fallback) via `httpx` 0.28+
  - Config default: `kimi-k2.5`
  - Implementation: `src/podcast_pipeline/providers/kimi.py`

### UI + CLI
- **Streamlit** 1.42+ (review UI) `src/podcast_pipeline/ui/app.py`
- **Typer** 0.15+ (CLI) `src/podcast_pipeline/cli.py`

### Config + Validation
- **Pydantic** 2.10+ (`src/podcast_pipeline/config/settings.py`)
- **PyYAML** 6.0+ for `config.yaml`
- **python-dotenv** 1.0+ for env keys

### Logging + Reliability
- **structlog** 24.4+ for structured logs
- **tenacity** 9.0+ for retry/backoff in providers

### Testing
- **pytest** 8.x, `pytest-asyncio`, `pytest-cov` (in `pyproject.toml`)

### Desktop (Planned)
- **Rust + Tauri v2** UI
- **Python backend service** running the pipeline

## What NOT to Use

- **moviepy** or FFmpeg wrappers (`ffmpeg-python`, `python-ffmpeg`)
- **original whisper** (prefer faster-whisper)
- **langchain** (overkill for simple provider switching)

## Notes

- OpenAI keys are supported in config but no provider implementation exists.
- All stack recommendations are based on current repo + internal research report only.

