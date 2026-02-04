# Testing Patterns

**Analysis Date:** 2026-02-04

## Test Framework

**Runner:**
- pytest (configured in `pyproject.toml`)
- Config: `pyproject.toml` `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest assertions

**Run Commands:**
```bash
pytest                 # Run all tests
pytest -m "not slow"   # Skip slow tests (marker defined in pyproject.toml)
pytest --cov=podcast_pipeline --cov-report=term-missing  # Coverage (pytest-cov)
```

## Test File Organization

**Location:**
- Centralized under `tests/`

**Naming:**
- `tests/test_*.py`

**Structure:**
```
tests/
├── conftest.py
├── test_pipeline.py
├── test_render.py
├── test_utils.py
└── ...
```

## Test Structure

**Suite Organization:**
```python
class TestPipeline:
    def test_create_pipeline(self, config: Config):
        pipeline = Pipeline(config)
        assert "ingest" in pipeline.stages
```

**Patterns:**
- Setup pattern: pytest fixtures in `tests/conftest.py`
- Teardown pattern: generator fixtures with cleanup (`tests/conftest.py`)
- Assertion pattern: direct `assert` statements

## Mocking

**Framework:** `unittest.mock`

**Patterns:**
```python
from unittest.mock import MagicMock, patch

with patch("podcast_pipeline.stages.render.run_ffmpeg") as run_ffmpeg:
    run_ffmpeg.return_value = MagicMock()
```

**What to Mock:**
- External processes (FFmpeg) and network calls

**What NOT to Mock:**
- Pure functions and small utilities (`src/podcast_pipeline/utils/time.py`)

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def sample_transcript() -> dict:
    return {"text": "Hello...", "segments": [], "filler_cuts": []}
```

**Location:**
- `tests/conftest.py`

## Coverage

**Requirements:**
- Minimum 40% coverage (`pyproject.toml` `[tool.coverage.report]`)

**View Coverage:**
```bash
pytest --cov=podcast_pipeline --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Most tests in `tests/test_*.py`

**Integration Tests:**
- Marker `integration` configured in `pyproject.toml`

**E2E Tests:**
- Not used

## Common Patterns

**Async Testing:**
- Marker `asyncio_mode = "auto"` configured in `pyproject.toml`

**Error Testing:**
```python
with pytest.raises(FileNotFoundError):
    pipeline.load_job("missing")
```

---

*Testing analysis: 2026-02-04*
