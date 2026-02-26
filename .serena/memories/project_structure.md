# Project Structure

```
podcast-pipeline/
├── src/
│   └── podcast_pipeline/              # Main Python package
│       ├── __init__.py
│       ├── cli.py                     # Typer CLI entry point (podcast-pipeline cmd)
│       ├── pipeline.py                # Core pipeline orchestration (Pipeline class)
│       ├── export_targets.py          # Export format definitions
│       ├── py.typed                   # PEP 561 marker
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py            # Pydantic config models (all settings)
│       │
│       ├── models/                    # Data models (Pydantic)
│       │   ├── __init__.py
│       │   ├── job.py                 # Job, JobStage, StageStatus models
│       │   ├── analysis.py            # Analysis result models
│       │   ├── transcript.py          # Transcript/segment models
│       │   ├── edit_plan.py           # Edit plan (cuts, clips) models
│       │   ├── branding.py            # BrandingProfile + per-platform overrides
│       │   └── triage.py              # Triage/content classification models
│       │
│       ├── providers/                 # AI provider abstractions
│       │   ├── base.py                # AnalysisProvider protocol/base
│       │   ├── gemini.py              # Google Gemini provider (primary)
│       │   ├── kimi.py                # Kimi/Moonshot provider (fallback)
│       │   └── claude_provider.py     # Anthropic Claude provider
│       │
│       ├── stages/                    # Pipeline processing stages
│       │   ├── base.py                # Stage base class
│       │   ├── ingest.py              # Raw input ingestion
│       │   ├── transcribe.py          # Audio transcription (faster-whisper)
│       │   ├── analyze.py             # AI-powered content analysis
│       │   ├── review.py              # Human review stage
│       │   └── render.py              # Final output rendering (FFmpeg)
│       │
│       ├── utils/                     # Utility modules
│       │   ├── __init__.py
│       │   ├── ffmpeg.py              # Low-level FFmpeg subprocess wrapper
│       │   ├── ffmpeg_toolkit.py      # High-level FFmpeg toolkit (14+ operations)
│       │   ├── branding.py            # Branding profile CRUD (load/save/resolve)
│       │   ├── captions.py            # ASS caption engine (word-level highlights)
│       │   ├── sync.py                # Audio sync estimator (cross-correlation)
│       │   ├── audio_mix.py           # Audio mixing utilities
│       │   ├── thumbnails.py          # Thumbnail generation
│       │   ├── rife_bridge.py         # RIFE GPU frame interpolation bridge
│       │   ├── editing.py             # Editing utilities
│       │   ├── pose_match.py          # Pose matching for B-roll cuts
│       │   ├── noise_match.py         # Background noise matching
│       │   ├── vad.py                 # Voice activity detection
│       │   ├── locks.py               # Job file locking
│       │   ├── logging.py             # structlog setup
│       │   └── time.py                # Timestamp utilities
│       │
│       ├── clients/                   # External service clients
│       ├── research/                  # Research + trend analysis
│       ├── service/                   # FastAPI backend service
│       │   ├── app.py                 # FastAPI app factory + auth policy
│       │   ├── supervisor.py          # Pipeline supervisor (job management)
│       │   ├── schemas.py             # Request/response Pydantic schemas
│       │   ├── recovery.py            # Job recovery logic
│       │   ├── assets.py              # Asset resolution
│       │   └── routes/
│       │       ├── jobs.py            # /jobs API routes
│       │       └── system.py          # /system API routes
│       │
│       ├── ui/
│       │   └── app.py                 # Streamlit review UI
│       │
│       └── mcp/
│           └── ffmpeg_server.py       # MCP server — 14 FFmpeg tools (dev-only)
│
├── tests/                             # pytest test suite (~42 test files)
│   ├── conftest.py                    # Shared fixtures
│   ├── test_captions.py               # Caption engine tests
│   ├── test_sync.py                   # Audio sync tests
│   ├── test_ffmpeg_toolkit.py         # FFmpeg toolkit tests
│   ├── test_mcp_ffmpeg_server.py      # MCP server tests
│   ├── test_supervisor.py             # Supervisor/service tests
│   └── test_*.py                      # All other test modules
│
├── branding/                          # Branding profiles (YAML) + assets/
│   └── assets/                        # Logo images, sound kits, etc.
│
├── scripts/                           # Utility scripts
│   └── smoke_test_gpu_rife.py         # GPU + RIFE smoke test
│
├── .planning/                         # Project planning docs (reference only)
│   ├── PROJECT.md                     # Project definition
│   ├── ROADMAP.md                     # Milestone roadmap (v1.0 phases 1–9+)
│   ├── STATE.md                       # Current state tracker
│   ├── REQUIREMENTS.md                # Requirements
│   ├── DESIGN-REFERENCE.md            # Design reference
│   ├── phases/                        # Per-phase PLAN.md files
│   ├── codebase/                      # Codebase analysis docs
│   └── research/                      # Research docs
│
├── desktop/                           # Future Tauri desktop app
├── docs/                              # User documentation
├── .github/                           # GitHub Actions CI/CD
├── .serena/                           # Serena project config + memories
├── .claude/                           # Claude Code config
├── jobs/                              # Job output directory (gitignored)
├── pyproject.toml                     # Project config (deps, ruff, mypy, pytest)
├── config.yaml                        # Runtime pipeline config
└── .pre-commit-config.yaml            # Pre-commit hook definitions
```

## Key Files Quick Reference

| File | Purpose |
|------|---------|
| `src/podcast_pipeline/cli.py` | CLI entry point — `podcast-pipeline` command |
| `src/podcast_pipeline/pipeline.py` | Core Pipeline class and orchestration |
| `src/podcast_pipeline/config/settings.py` | All Pydantic config models |
| `src/podcast_pipeline/providers/base.py` | AnalysisProvider protocol |
| `src/podcast_pipeline/stages/base.py` | Stage base class |
| `src/podcast_pipeline/service/app.py` | FastAPI app factory |
| `src/podcast_pipeline/utils/ffmpeg_toolkit.py` | 14+ FFmpeg operation classes |
| `src/podcast_pipeline/utils/branding.py` | Branding profile CRUD functions |
| `src/podcast_pipeline/utils/captions.py` | ASS caption generation |
| `src/podcast_pipeline/utils/sync.py` | SyncEstimator (cross-correlation) |
| `src/podcast_pipeline/mcp/ffmpeg_server.py` | MCP FFmpeg server (dev only) |
| `src/podcast_pipeline/models/branding.py` | BrandingProfile Pydantic model |
| `pyproject.toml` | Deps, ruff rules, mypy config, pytest markers |
| `config.yaml` | Runtime pipeline configuration |
