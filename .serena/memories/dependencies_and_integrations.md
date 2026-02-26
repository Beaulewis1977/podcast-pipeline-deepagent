# Dependencies and Integrations

## Core Python Dependencies

| Package | Purpose |
|---------|---------|
| `typer` | CLI framework with Rich formatting |
| `pydantic v2` | Data validation and config models |
| `pyyaml` | YAML config file parsing |
| `python-dotenv` | .env loading |
| `structlog` | Structured JSON logging |
| `fastapi` + `uvicorn` | Backend API service |
| `streamlit` | Web review UI |
| `faster-whisper` | GPU-accelerated speech transcription |
| `pyloudnorm` | EBU R128 loudness normalization |
| `pydub` | Audio manipulation |
| `soundfile` | Audio file I/O |
| `scipy` | Cross-correlation for audio sync |
| `mcp[cli]` | MCP server framework (FastMCP) |

## System Dependencies

- **FFmpeg**: Required for all audio/video processing — must be in PATH
- **CUDA 12.8** (optional): For faster-whisper GPU acceleration and RIFE
- **Python 3.12+**: Minimum required version

## AI Provider Integrations

| Service | Purpose | Required |
|---------|---------|----------|
| Google Gemini | Video analysis (primary) | Yes |
| Kimi/Moonshot | Video analysis (fallback) | No |
| OpenAI | Text generation (fallback) | No |
| Anthropic Claude | Alternative analysis | No |
| YouTube Data API | Trend research | No |

## Environment Variables (see .env.example)

```
GOOGLE_API_KEY=          # Gemini
OPENAI_API_KEY=          # OpenAI fallback
MOONSHOT_API_KEY=        # Kimi fallback
ANTHROPIC_API_KEY=       # Claude
YOUTUBE_API_KEY=         # YouTube Data API
SERVICE_API_TOKEN=       # FastAPI auth token
```

## External Tools

- `saas` CLI (`~/.local/share/pnpm/saas`): AI-powered questions via Perplexity (`saas ask`), docs via Context7 (`saas docs`)
- Serena MCP: Global plugin for symbolic code navigation (`.serena/`)
- CodeRabbit: Automated PR reviews via `.coderabbit.yaml`
- gitleaks: Secret scanning in pre-commit hooks (`.gitleaks.toml`)

## Build System

- `uv` — fast Python package manager replacing pip/venv
- `hatchling` — build backend (`pyproject.toml`)
- `ruff` — linter + formatter (replaces black, isort, flake8)
- `mypy` — strict type checking with pydantic plugin

## CI/CD

- GitHub Actions: `.github/workflows/` — lint, typecheck, test, build, security scan
- Pre-commit: `.pre-commit-config.yaml` — ruff, mypy, gitleaks
- Pre-push: pytest, pip-audit
