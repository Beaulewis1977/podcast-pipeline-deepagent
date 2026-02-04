# Coding Conventions

**Analysis Date:** 2026-02-04

## Naming Patterns

**Files:**
- snake_case modules: `stages/transcribe.py`, `providers/gemini.py`
- test files: `tests/test_*.py`

**Functions:**
- snake_case (e.g., `create_and_run_pipeline` in `src/podcast_pipeline/pipeline.py`)

**Variables:**
- snake_case (e.g., `analysis_dir` in `src/podcast_pipeline/stages/transcribe.py`)

**Types:**
- PascalCase classes (e.g., `AnalysisResult` in `src/podcast_pipeline/models/analysis.py`)

## Code Style

**Formatting:**
- Ruff formatter with double quotes and 100-char line length (`pyproject.toml`)

**Linting:**
- Ruff with broad rule set (pycodestyle, pyflakes, isort, bugbear, etc.) (`pyproject.toml`)
- Type checking via MyPy in strict mode (`pyproject.toml`)

## Import Organization

**Order:**
1. Standard library (`pathlib`, `json`, `typing`)
2. Third-party (`pydantic`, `streamlit`, `httpx`)
3. Local package (`podcast_pipeline.*`)

**Path Aliases:**
- None (use absolute imports from `podcast_pipeline`)

## Error Handling

**Patterns:**
- Stage execution wraps exceptions and returns `StageResult` (`src/podcast_pipeline/stages/base.py`)
- Provider errors derive from `ProviderError` (`src/podcast_pipeline/providers/base.py`)

## Logging

**Framework:** `structlog` (`src/podcast_pipeline/utils/logging.py`)

**Patterns:**
- Module-level logger: `logger = get_logger(__name__)`
- Structured events: `logger.info("event_name", key=value)` (`src/podcast_pipeline/stages/ingest.py`)

## Comments

**When to Comment:**
- File/module docstrings at top of most files (`src/podcast_pipeline/stages/*`)

**JSDoc/TSDoc:**
- Not applicable (Python project)

## Function Design

**Size:**
- Medium-sized methods that return `StageResult` and write artifacts (`src/podcast_pipeline/stages/*.py`)

**Parameters:**
- Strong typing with `Path`, `Config`, and Pydantic models (`src/podcast_pipeline/stages/base.py`)

**Return Values:**
- `StageResult` for stage methods; Pydantic models for data (`src/podcast_pipeline/models/*`)

## Module Design

**Exports:**
- Minimal `__init__.py` (version only) (`src/podcast_pipeline/__init__.py`)

**Barrel Files:**
- Not used

---

*Convention analysis: 2026-02-04*
