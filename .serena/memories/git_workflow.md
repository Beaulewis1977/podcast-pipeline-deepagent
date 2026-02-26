# Git Workflow

## Branch Structure

| Branch | Purpose | Protection |
|--------|---------|------------|
| **main** | Production releases | 🔒 LOCKED — only owner can push or merge |
| **develop** | Active development — this is `origin` (the default remote) | Base for ALL feature work |
| **feat/*** | Feature branches | PR to `develop` only |

> **Critical**: `develop` tracks `origin/develop`. When you clone or set up the repo,
> `develop` is the origin-default branch. `main` is protected and only the repo owner
> (Beaulewis1977) can push or merge into it.

## Branch Naming

| Prefix | Purpose | Example |
|--------|---------|---------|
| `feat/` | New features | `feat/audio-normalization` |
| `fix/` | Bug fixes | `fix/ffmpeg-path-error` |
| `docs/` | Documentation | `docs/api-reference` |
| `test/` | Test additions/fixes | `test/integration-coverage` |
| `refactor/` | Code refactoring | `refactor/provider-abstraction` |
| `chore/` | Maintenance | `chore/update-dependencies` |
| `ci/` | CI/CD changes | `ci/add-security-scan` |

Phases use: `feat/phase9-branding-captions-sync` pattern.

## Standard Workflow

```bash
# Always start from develop
git checkout develop
git pull origin develop

# Create feature branch
git checkout -b feat/my-feature

# Work, commit...
git push -u origin feat/my-feature

# Open PR → target: develop (NOT main)
gh pr create --base develop --head feat/my-feature
```

**Rules:**
- NEVER commit directly to `main` or `develop`
- All PRs target `develop`
- `develop` → `main` merges are done by the owner only, for releases
- CodeRabbit reviews every PR automatically

## Remote Configuration

```
origin  https://github.com/Beaulewis1977/podcast-pipeline-deepagent.git (fetch)
origin  https://github.com/Beaulewis1977/podcast-pipeline-deepagent.git (push)
```

## CI/CD Pipeline

- **Pre-commit hooks**: ruff lint/format, mypy, gitleaks (secret scanning)
- **Pre-push hooks**: pytest, pip-audit
- **GitHub Actions**: lint, typecheck, test, build, security scan
- **CodeRabbit**: Automated PR reviews on every PR

## Historical Branches (reference only, do not work on these)

Past feature branches visible: phase1–phase9 feat branches, backup branches, ci branches.
Current active work: `feat/phase9-branding-captions-sync`
