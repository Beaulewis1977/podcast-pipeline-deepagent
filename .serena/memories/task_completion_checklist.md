# Task Completion Checklist

When a coding task is completed, run the following checks in order:

## 1. Formatting

```bash
uv run ruff format .
```

## 2. Linting

```bash
uv run ruff check .
# Fix auto-fixable issues:
uv run ruff check --fix .
```

## 3. Type Checking

```bash
uv run mypy src/
```

## 4. Testing

```bash
# Run all tests (skip slow/integration if not relevant)
uv run pytest tests/ -m "not slow and not integration"

# If changes affect specific areas, run targeted tests:
uv run pytest tests/test_<relevant>.py -v

# Run with coverage to verify no regression
uv run pytest tests/ --cov
```

## 5. Verify No Secrets Committed

- Check `.env` files are gitignored
- No API keys in source code
- gitleaks pre-commit hook will catch this automatically

## 6. Git Workflow Check

- Ensure you are on a feature branch (NOT main or develop)
- Branch name follows conventions: `feat/`, `fix/`, `docs/`, etc.
- PR targets `develop` (NOT main)

## Notes

- Coverage target: 45% overall (fail_under in pyproject.toml)
- Pre-commit hooks run automatically: ruff lint/format, mypy, gitleaks
- Pre-push hooks run automatically: pytest, pip-audit
- CodeRabbit reviews PRs automatically — address all findings before merging
