# Codebase Structure

**Analysis Date:** 2026-02-04

## Directory Layout

```
[project-root]/
├── src/podcast_pipeline/      # Application package
├── tests/                     # Pytest suite
├── jobs/                      # Job artifacts (runtime output)
├── config.yaml                # Runtime defaults
├── pyproject.toml             # Build + tool config
├── uv.lock                    # Dependency lockfile (uv)
├── README.md                  # Project overview
└── .planning/                 # Planning docs
```

## Directory Purposes

**src/podcast_pipeline/**
- Purpose: Core pipeline implementation
- Contains: CLI, UI, stages, providers, config, models, utils
- Key files: `src/podcast_pipeline/pipeline.py`, `src/podcast_pipeline/cli.py`, `src/podcast_pipeline/ui/app.py`

**src/podcast_pipeline/stages/**
- Purpose: Stage implementations
- Contains: `ingest.py`, `transcribe.py`, `analyze.py`, `review.py`, `render.py`
- Key files: `src/podcast_pipeline/stages/base.py`

**src/podcast_pipeline/providers/**
- Purpose: AI provider integrations
- Contains: `gemini.py`, `kimi.py`, `base.py`

**src/podcast_pipeline/models/**
- Purpose: Pydantic models and state
- Contains: `job.py`, `analysis.py`, `transcript.py`

**src/podcast_pipeline/research/**
- Purpose: Research utilities (YouTube, viral detection)
- Contains: `youtube.py`, `viral_detector.py`

**src/podcast_pipeline/utils/**
- Purpose: Helpers (FFmpeg, logging, time)
- Contains: `ffmpeg.py`, `logging.py`, `time.py`

**tests/**
- Purpose: Unit + integration tests
- Contains: `test_*.py`, `conftest.py`

**jobs/**
- Purpose: Runtime job outputs (not source)
- Contains: per-job folders with `state.json`, `analysis/`, `output/`

## Key File Locations

**Entry Points:**
- `src/podcast_pipeline/cli.py`: CLI commands
- `src/podcast_pipeline/ui/app.py`: Streamlit UI
- `src/podcast_pipeline/pipeline.py`: Pipeline orchestration

**Configuration:**
- `config.yaml`: Default runtime config
- `src/podcast_pipeline/config/settings.py`: Pydantic config models + env loading
- `.env`: API keys (optional)

**Core Logic:**
- `src/podcast_pipeline/stages/*`: Stage implementations
- `src/podcast_pipeline/providers/*`: AI provider logic
- `src/podcast_pipeline/models/*`: Data models

**Testing:**
- `tests/conftest.py`: Fixtures
- `tests/test_pipeline.py`: Pipeline tests
- `tests/test_render.py`: Render and platform specs tests

## Naming Conventions

**Files:**
- snake_case module names: `stages/transcribe.py`, `providers/gemini.py`
- Test files: `tests/test_*.py`

**Directories:**
- package-style: `providers/`, `stages/`, `models/`, `utils/`

## Where to Add New Code

**New Feature:**
- Primary code: `src/podcast_pipeline/` (choose submodule: `stages/`, `providers/`, `ui/`)
- Tests: `tests/test_<feature>.py`

**New Component/Module:**
- Implementation: `src/podcast_pipeline/<area>/<module>.py`

**Utilities:**
- Shared helpers: `src/podcast_pipeline/utils/<name>.py`

## Special Directories

**jobs/**
- Purpose: Runtime job outputs
- Generated: Yes
- Committed: Yes (folder exists; contents typically local)

**.planning/**
- Purpose: Project planning artifacts
- Generated: Yes (by planning workflows)
- Committed: Yes

---

*Structure analysis: 2026-02-04*
