# Suggested Commands

## Development Commands

```bash
# Install/sync dependencies
uv sync

# Run the CLI
uv run podcast-pipeline --help

# Linting (check only)
uv run ruff check .

# Linting (auto-fix)
uv run ruff check --fix .

# Check formatting
uv run ruff format --check .

# Apply formatting
uv run ruff format .

# Type checking (strict mode)
uv run mypy src/

# Run all tests
uv run pytest tests/

# Run tests with coverage
uv run pytest tests/ --cov

# Skip slow tests
uv run pytest tests/ -m "not slow"

# Skip integration tests
uv run pytest tests/ -m "not integration"

# Run fast tests only (skip both)
uv run pytest tests/ -m "not slow and not integration"

# Run a specific test file
uv run pytest tests/test_captions.py -v

# Security audit
uv run pip-audit
```

## Git Workflow Commands

```bash
# Start new work (always from develop)
git checkout develop && git pull origin develop
git checkout -b feat/my-feature

# Push and open PR targeting develop
git push -u origin feat/my-feature
gh pr create --base develop --head feat/my-feature --title "feat: ..." --body "..."

# Check CI status
gh pr status
gh run list --limit 5
```

## System Utilities

```bash
git status
git diff
git log --oneline -20
ls -la
grep -r "pattern" src/
find . -name "*.py"
```

## GPU Smoke Test

```bash
python scripts/smoke_test_gpu_rife.py
```

## MCP Server (dev-only)

The MCP FFmpeg server is configured in `.mcp.json` and available as
`mcp__ffmpeg-server__*` tools in Claude Code. It exposes 14 media operations.
