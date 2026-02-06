---
phase: 03-polishing-+-desktop-distribution
plan: 06
subsystem: infra
tags: [tauri, github-actions, ci-cd, installer, smoke-test, pyinstaller, cross-platform]

# Dependency graph
requires:
  - phase: 03-04
    provides: Sidecar preparation script, build.rs validation, runtime asset resolver
  - phase: 03-05
    provides: Crash recovery, resume orchestration, reconciliation endpoints
provides:
  - Cross-platform GitHub Actions release workflow (Linux, macOS x2, Windows)
  - Post-build smoke test scripts for installer validation (bash + PowerShell)
  - Distribution runbook with signing, troubleshooting, and manual release guide
  - README desktop distribution section
affects: [releases, distribution, onboarding]

# Tech tracking
tech-stack:
  added: [pyinstaller, tauri-action]
  patterns:
    - "Split CI pipeline: build-backend -> build-desktop -> smoke-test"
    - "Target-triple artifact naming for cross-platform sidecar binaries"
    - "Smoke test validation with graduated severity (FAIL blocks, WARN advisory)"

key-files:
  created:
    - .github/workflows/desktop-release.yml
    - desktop/scripts/smoke-test-desktop.sh
    - desktop/scripts/smoke-test-desktop.ps1
    - docs/desktop-distribution.md
  modified:
    - README.md

key-decisions:
  - "Three-stage workflow (build-backend, build-desktop, smoke-test) for clear failure isolation"
  - "PyInstaller for backend sidecar packaging (single-file, cross-platform)"
  - "Smoke tests use graduated severity: artifact/size/sidecar checks are blocking, health/ffmpeg are warnings"
  - "Draft releases by default to allow manual review before publishing"

patterns-established:
  - "Release workflow: tag-triggered with manual dispatch option"
  - "Smoke validation: extract-then-inspect pattern for installer content verification"
  - "Distribution docs: runbook format with troubleshooting decision tree"

# Metrics
duration: 4min
completed: 2026-02-05
---

# Phase 03 Plan 06: Installer Matrix and Smoke Validation Summary

**Cross-platform GitHub Actions release workflow with PyInstaller backend sidecar, post-build smoke tests (bash + PowerShell), and distribution runbook covering signing, troubleshooting, and manual release**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-06T00:15:12Z
- **Completed:** 2026-02-06T00:19:25Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- GitHub Actions workflow builds backend sidecar (PyInstaller) and desktop installers (Tauri) across 4 platform targets (Linux x86_64, macOS ARM64, macOS x86_64, Windows x86_64)
- Smoke test scripts for Linux/macOS (bash) and Windows (PowerShell) validate artifact existence, size, sidecar presence, backend health, and FFmpeg inclusion
- Distribution runbook documents release workflow, code signing setup (macOS/Windows), smoke test interpretation, and troubleshooting for common issues (missing sidecar, asset resolution, resume after crash)
- README updated with desktop app features section and release/smoke-test instructions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add cross-platform desktop release workflow** - `2381687` (feat)
2. **Task 2: Add clean-machine smoke test scripts** - `b241b0e` (feat)
3. **Task 3: Document release/distribution runbook** - `bbd6147` (docs)

## Files Created/Modified
- `.github/workflows/desktop-release.yml` - 289-line release workflow with platform matrix, sidecar build, Tauri action, and smoke test jobs
- `desktop/scripts/smoke-test-desktop.sh` - 291-line Linux/macOS smoke validation (AppImage/deb/dmg inspection)
- `desktop/scripts/smoke-test-desktop.ps1` - 262-line Windows smoke validation (MSI/EXE inspection)
- `docs/desktop-distribution.md` - 306-line distribution runbook (signing, troubleshooting, manual release)
- `README.md` - Added Desktop App features section and Desktop Release section with build/smoke instructions

## Decisions Made
- **Three-stage workflow architecture**: Separated backend build, desktop build, and smoke test into independent jobs for clear failure isolation and parallelism. Backend artifacts are passed between jobs via GitHub Actions artifacts.
- **PyInstaller for backend binary**: Uses `--onefile --console` mode with hidden imports for podcast_pipeline and uvicorn, producing a standalone executable per platform.
- **Graduated smoke severity**: Artifact existence, size, and sidecar presence checks are blocking (fail the release). Health endpoint and FFmpeg checks are advisory warnings since they may not be runnable in all CI contexts.
- **Draft releases by default**: The Tauri action creates draft GitHub releases, allowing manual review before publishing to avoid accidentally releasing broken builds.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

External services require manual configuration for code signing. See plan frontmatter `user_setup` for:
- **Apple code signing**: `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID` (and related secrets) required for notarized macOS builds
- **Windows code signing**: `WINDOWS_CERTIFICATE`, `WINDOWS_CERTIFICATE_PASSWORD` required for signed Windows installers

These are optional -- unsigned builds work but show OS security warnings.

## Next Phase Readiness
- Phase 3 is now complete: all 6 plans executed
- Desktop distribution pipeline is fully defined: build, validate, and release
- Code signing secrets need to be configured for production-signed releases
- Phase 2 (Research + Viral Integration) remains unplanned

---
*Phase: 03-polishing-+-desktop-distribution*
*Completed: 2026-02-05*
