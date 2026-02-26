# CLAUDE.md - Claude Code Guidelines for podcast-pipeline

## Project Overview

This is an AI-powered podcast production pipeline that transforms raw video recordings into multi-platform content. Built with Python 3.12+, it processes audio/video with FFmpeg, transcribes with faster-whisper, and uses AI (Gemini/Kimi/OpenAI) for content analysis and suggestions.

## Quick Start

```bash
# Install dependencies
uv sync

# Run linting
uv run ruff check .
uv run ruff format --check .

# Run type checking
uv run mypy src/

# Run tests
uv run pytest tests/

# Run the CLI (once implemented)
uv run podcast-pipeline --help
```

## Project Structure

```
podcast-pipeline/
├── src/
│   └── podcast_pipeline/     # Main package
│       ├── __init__.py
│       ├── cli.py            # Typer CLI entry point
│       ├── config/           # Pydantic config models
│       ├── providers/        # AI provider abstractions
│       ├── processors/       # Audio/video processing
│       └── ui/               # Streamlit review UI
├── tests/                    # pytest test files
├── .planning/                # Project planning docs (reference only)
├── docs/                     # User documentation
└── jobs/                     # Job output directory (gitignored)
```

## Code Style

- **Formatting**: Ruff (line-length: 100)
- **Linting**: Ruff with pycodestyle, flake8-bugbear, bandit security rules
- **Type checking**: mypy strict mode
- **Imports**: isort via Ruff, first-party = `podcast_pipeline`

## Key Conventions

### Type Annotations
All public functions require type annotations:
```python
def process_audio(input_path: Path, output_path: Path) -> ProcessResult:
    ...
```

### Error Handling
Use specific exceptions, not bare `except`:
```python
try:
    result = await provider.analyze(video_path)
except ProviderAPIError as e:
    logger.error("API failed", error=str(e))
    raise
```

### Logging
Use structlog for structured JSON logging:
```python
import structlog
logger = structlog.get_logger()
logger.info("processing_started", job_id=job.id, stage="transcribe")
```

### Configuration
Use Pydantic models for all config:
```python
from pydantic import BaseModel, Field

class JobConfig(BaseModel):
    filler_removal: bool = Field(default=True)
    target_loudness_lufs: float = Field(default=-14.0)
```

### AI Provider Pattern
Implement the provider protocol for new AI integrations:
```python
class AnalysisProvider(Protocol):
    async def analyze(self, video_path: Path, transcript: dict) -> AnalysisResult: ...
```

## Testing

- Test files: `tests/test_*.py`
- Use pytest fixtures for common setup
- Mark slow tests: `@pytest.mark.slow`
- Mark integration tests: `@pytest.mark.integration`
- Coverage target: 80%

Run specific test types:
```bash
uv run pytest tests/ -m "not slow"        # Skip slow tests
uv run pytest tests/ -m "not integration" # Skip integration tests
```

## Dependencies

- **FFmpeg**: Required system dependency for audio/video processing
- **GPU (optional)**: faster-whisper benefits from CUDA for transcription. **Phase 8 GPU features (RIFE)** require RTX 5060 Ti (sm_120) with CUDA 12.8 (`cu128`).
- **GPU Smoke Test**: Run `python scripts/smoke_test_gpu_rife.py` to verify the GPU + RIFE stack.
- **API Keys**: See `.env.example` for required environment variables

## Common Tasks

### Add a new CLI command
Edit `src/podcast_pipeline/cli.py` using Typer:
```python
@app.command()
def new_command(arg: str = typer.Argument(..., help="Description")):
    """Command description."""
    ...
```

### Add a new AI provider
1. Create `src/podcast_pipeline/providers/new_provider.py`
2. Implement `AnalysisProvider` protocol
3. Register in provider factory

### Add a new export format
1. Create `src/podcast_pipeline/exporters/new_format.py`
2. Implement export logic with FFmpeg
3. Add to export registry

## Git Workflow

### Branch Structure

| Branch | Purpose | Protection |
|--------|---------|------------|
| **main** | Production releases | 🔒 Protected - only owner can merge |
| **develop** | Active development (origin) | Base for all work |
| **feat/*** | Feature branches | PR to develop |

### Branch Naming Conventions

| Prefix | Purpose | Example |
|--------|---------|--------|
| `feat/` | New features | `feat/audio-normalization` |
| `fix/` | Bug fixes | `fix/ffmpeg-path-error` |
| `docs/` | Documentation | `docs/api-reference` |
| `test/` | Test additions/fixes | `test/integration-coverage` |
| `refactor/` | Code refactoring | `refactor/provider-abstraction` |
| `chore/` | Maintenance tasks | `chore/update-dependencies` |
| `ci/` | CI/CD changes | `ci/add-security-scan` |

### Workflow

All work must be on branches off `develop` and merged via PR:
```bash
git checkout develop
git pull origin develop
git checkout -b feat/my-feature
# ... make changes, commit ...
git push -u origin feat/my-feature
# Create PR: feat/* → develop
# After review: develop → main for releases (owner only)
```

**Never commit directly to `main` or `develop`.**

## CI/CD

- **Pre-commit hooks**: ruff lint/format, mypy, gitleaks
- **Pre-push hooks**: pytest, pip-audit
- **GitHub Actions**: lint, typecheck, test, build, security scan
- **CodeRabbit**: Automated PR reviews

## External Dependencies (APIs)

| Service | Purpose | Required |
|---------|---------|----------|
| Google Gemini | Video analysis (primary) | Yes |
| Kimi (Moonshot) | Video analysis (fallback) | No |
| OpenAI | Text generation (fallback) | No |
| YouTube Data API | Trend research | No |

## Available CLI Tools

### saas CLI (`~/.local/share/pnpm/saas`)

- `saas ask "<query>"` - AI-powered questions via Perplexity (web search)
- `saas docs <library> "<query>"` - Documentation lookup via Context7

  ## Serena MCP (Global Plugin)

  Serena is available as a global MCP plugin (`mcp__plugin_serena_serena__*`) for symbolic code navigation and editing.
  Project config lives in `.serena/project.yml` with onboarded memories in `.serena/memories/`.

  - **Session start**: Call `mcp__plugin_serena_serena__initial_instructions` at the start of each session — this loads
  Serena's operating guidelines so you use its tools correctly
  - **Project is auto-detected**: No need to call `activate_project` — Serena detects the project from
  `.serena/project.yml` automatically (it's disabled in the claude-code context anyway)
  - **Symbolic tools**: `find_symbol`, `get_symbols_overview`, `replace_symbol_body`, `find_referencing_symbols` for
  precise code ops
  - **Memories**: Project knowledge persists across sessions — read with `read_memory`, write with `write_memory`
  - **Prefer symbolic edits** over file-level edits when modifying functions/classes
  - **First-time setup**: Run `/serena-init` once per project to onboard Serena and build the memory knowledge base

  This project has [Serena](https://github.com/oraios/serena) configured as an MCP plugin for semantic code
  intelligence. Config lives in `.serena/project.yml` (languages: TypeScript, Vue).

  **When to use Serena tools over standard tools:**

  - `get_symbols_overview` / `find_symbol` — navigate by symbol (class, function, type) instead of grepping
  - `find_referencing_symbols` — trace callers/usages of a symbol across the codebase
  - `replace_symbol_body` / `insert_after_symbol` / `insert_before_symbol` — edit at the symbol level for precise
  refactors
  - `rename_symbol` — rename with reference updates

  **When standard tools are still better:** file creation, glob/grep for string literals or config keys, reading full
  files, and any non-symbolic edits (e.g. changing a single line inside a large function — use `replace_content` or the
  Edit tool).

  **Workflow:** Call `initial_instructions` at session start. The symbol index is pre-built (`serena project index`).
  Re-index manually from the terminal after large structural changes (new modules, major refactors) — Claude cannot
  trigger this.


## Do Not

- Commit API keys or secrets (use `.env`)
- Use `print()` outside CLI - use structlog
- Use bare `except:` clauses
- Skip type annotations on public functions
- Modify files in `_archive/` (legacy code reference only)
