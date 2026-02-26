# Code Style and Conventions

## Formatting

- **Tool**: Ruff (line-length: 100)
- **Quote style**: Double quotes
- **Indent style**: Spaces (4)
- **Target Python**: 3.12+

## Linting

- **Tool**: Ruff with extensive rule set:
  pycodestyle (E/W), pyflakes (F), isort (I), flake8-bugbear (B),
  flake8-comprehensions (C4), pyupgrade (UP), bandit security (S),
  flake8-builtins (A), flake8-print (T20), flake8-pytest-style (PT),
  flake8-simplify (SIM), Ruff-specific (RUF), unused-args (ARG),
  datetimez (DTZ), eradicate (ERA), pylint (PL), tryceratops (TRY), flake8-async (ASYNC)
- **Per-file ignores**: Tests, CLI, providers, stages, UI, utils, service, and MCP modules have relaxed rules

## Type Checking

- **Tool**: mypy strict mode with pydantic plugin
- **All public functions** must have type annotations
- Tests have relaxed mypy settings

## Naming Conventions

- **Modules**: snake_case
- **Classes**: PascalCase
- **Functions/methods**: snake_case
- **Constants**: UPPER_SNAKE_CASE
- **Private helpers**: prefix with `_`
- **First-party imports**: `podcast_pipeline`

## Logging

```python
from podcast_pipeline.utils.logging import get_logger
logger = get_logger(__name__)
logger.info("event_name", key=value, another=value2)
```

- Use `structlog` (NEVER `print()` outside CLI)
- Event names are snake_case strings

## Configuration

```python
from pydantic import BaseModel, Field
class MyConfig(BaseModel):
    setting: str = Field(default="value", description="What it does")
```

## Error Handling

```python
try:
    result = await provider.analyze(video_path)
except ProviderAPIError as e:
    logger.error("api_failed", error=str(e))
    raise
```
- Specific exceptions only, never bare `except:`
- Catch → log with structlog → re-raise

## AI Provider Pattern

```python
class AnalysisProvider(Protocol):
    async def analyze(self, video_path: Path, transcript: dict) -> AnalysisResult: ...
```
Register new providers in provider factory.

## Imports

- isort managed by Ruff
- Known first-party: `podcast_pipeline`
- Lazy imports allowed in CLI, providers, stages, UI, utils, service, MCP modules

## Do Not

- Use `print()` outside CLI — use structlog
- Use bare `except:` clauses
- Skip type annotations on public functions
- Commit API keys or secrets (use `.env`)
- Modify files in `_archive/` (legacy reference only)
