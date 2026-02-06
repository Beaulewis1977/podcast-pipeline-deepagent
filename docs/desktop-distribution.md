# Desktop Distribution Runbook

Release, signing, smoke validation, and troubleshooting guide for Podcast Pipeline desktop installers.

## Table of Contents

- [Overview](#overview)
- [Release Workflow](#release-workflow)
- [Installer Outputs](#installer-outputs)
- [Sidecar Preparation](#sidecar-preparation)
- [Signing and Notarization](#signing-and-notarization)
- [Smoke Validation](#smoke-validation)
- [Troubleshooting](#troubleshooting)
- [Manual Release Process](#manual-release-process)

---

## Overview

The desktop app bundles a Tauri v2 shell with three sidecar binaries:

| Sidecar | Purpose | Source |
|---------|---------|--------|
| `podcast-backend` | FastAPI job runner service | PyInstaller from `src/podcast_pipeline/service/cli.py` |
| `ffmpeg` | Media processing | System or pre-built static binary |
| `ffprobe` | Media info extraction | System or pre-built static binary |

All sidecars are renamed to target-triple format (e.g., `podcast-backend-x86_64-unknown-linux-gnu`) by `desktop/scripts/prepare-sidecars.mjs` so Tauri resolves them at runtime.

## Release Workflow

### Automated (GitHub Actions)

The `.github/workflows/desktop-release.yml` workflow runs on:

- **Tag push** matching `v*` (e.g., `v0.1.0`, `v1.0.0-beta.1`)
- **Manual dispatch** via GitHub Actions UI (with optional dry-run flag)

#### Workflow stages

```
1. build-backend    Build PyInstaller sidecar per platform (4 runners)
2. build-desktop    Build Tauri installer per platform (4 runners)
3. smoke-test       Validate installer artifacts per platform (3 runners)
```

#### Triggering a release

```bash
# Tag the release
git tag v0.2.0
git push origin v0.2.0

# Or trigger manually from GitHub Actions tab:
# Actions > Desktop Release > Run workflow
```

#### Platform matrix

| Runner | Target Triple | Backend | Installer Formats |
|--------|--------------|---------|-------------------|
| `ubuntu-22.04` | `x86_64-unknown-linux-gnu` | PyInstaller (Linux) | `.deb`, `.AppImage` |
| `macos-latest` | `aarch64-apple-darwin` | PyInstaller (macOS ARM) | `.dmg` |
| `macos-13` | `x86_64-apple-darwin` | PyInstaller (macOS Intel) | `.dmg` |
| `windows-latest` | `x86_64-pc-windows-msvc` | PyInstaller (Windows) | `.msi`, `.exe` (NSIS) |

## Installer Outputs

After a successful build, the following artifacts are produced:

### Linux
- **`.deb`** -- Debian/Ubuntu package, installable via `dpkg -i`
- **`.AppImage`** -- Portable executable, no installation required

### macOS
- **`.dmg`** -- Disk image with drag-to-Applications installer
- Separate builds for Apple Silicon (`aarch64`) and Intel (`x86_64`)

### Windows
- **`.msi`** -- Windows Installer package
- **`.exe`** -- NSIS installer (optional, depends on Tauri bundle config)

All artifacts are uploaded to the GitHub Release as draft assets and also stored as GitHub Actions artifacts for 7 days.

## Sidecar Preparation

The `desktop/scripts/prepare-sidecars.mjs` script handles binary naming:

```bash
# Prepare sidecars for the current platform
node desktop/scripts/prepare-sidecars.mjs

# Dry-run validation (check without copying)
node desktop/scripts/prepare-sidecars.mjs --check
```

### Environment variable overrides

| Variable | Purpose | Example |
|----------|---------|---------|
| `BACKEND_BIN` | Path to pre-built podcast-backend binary | `/opt/backend/podcast-backend` |
| `FFMPEG_BIN` | Path to ffmpeg binary | `/usr/local/bin/ffmpeg` |
| `FFPROBE_BIN` | Path to ffprobe binary | `/usr/local/bin/ffprobe` |
| `TAURI_TARGET_TRIPLE` | Override target triple detection | `x86_64-unknown-linux-gnu` |

### Target triple mapping

| OS | Arch | Target Triple |
|----|------|--------------|
| Linux | x64 | `x86_64-unknown-linux-gnu` |
| macOS | ARM64 | `aarch64-apple-darwin` |
| macOS | x64 | `x86_64-apple-darwin` |
| Windows | x64 | `x86_64-pc-windows-msvc` |

## Signing and Notarization

### macOS Code Signing

Required GitHub Secrets:

| Secret | Source | Purpose |
|--------|--------|---------|
| `APPLE_CERTIFICATE` | Base64-encoded `.p12` certificate | Code signing identity |
| `APPLE_CERTIFICATE_PASSWORD` | Certificate export password | Unlock certificate |
| `APPLE_SIGNING_IDENTITY` | e.g., `Developer ID Application: Name (TEAMID)` | Signing identity name |
| `APPLE_ID` | Apple Developer account email | Notarization submission |
| `APPLE_PASSWORD` | App-specific password | Notarization auth |
| `APPLE_TEAM_ID` | 10-character team identifier | Notarization team |

**Setup steps:**

1. Enroll in Apple Developer Program
2. Create a "Developer ID Application" certificate in Xcode or Apple Developer portal
3. Export as `.p12` with a password
4. Base64-encode: `base64 -i certificate.p12 | pbcopy`
5. Generate app-specific password at https://appleid.apple.com
6. Add all secrets to repository Settings > Secrets > Actions

**Without signing:** Unsigned builds will show Gatekeeper warnings on macOS. Users must right-click > Open to bypass.

### Windows Code Signing

Required GitHub Secrets:

| Secret | Source | Purpose |
|--------|--------|---------|
| `WINDOWS_CERTIFICATE` | Base64-encoded `.pfx` certificate | Code signing |
| `WINDOWS_CERTIFICATE_PASSWORD` | Certificate password | Unlock certificate |

**Setup steps:**

1. Obtain a code signing certificate (e.g., from DigiCert, Sectigo, or self-signed for testing)
2. Export as `.pfx` with a password
3. Base64-encode: `certutil -encode certificate.pfx certificate.b64` (or use `base64` on Linux/macOS)
4. Add secrets to repository Settings > Secrets > Actions

**Without signing:** Unsigned builds will trigger SmartScreen warnings. Users must click "More info" > "Run anyway".

### Linux

No code signing required. `.deb` packages can optionally be signed with GPG for apt repository distribution.

## Smoke Validation

Post-build smoke tests validate installer artifacts automatically in CI.

### What gets tested

| Check | Linux/macOS | Windows | Failure Impact |
|-------|-------------|---------|----------------|
| Artifact existence | Looks for `.AppImage`, `.deb`, `.dmg` | Looks for `.msi`, `.exe` | Blocks release |
| Installer size (>5 MB) | Yes | Yes | Blocks release |
| Sidecar presence | Extracts and searches for `podcast-backend` | MSI extraction or size heuristic | Blocks release |
| Backend health | Starts binary, polls `/health` | Same | Warning only |
| FFmpeg presence | Searches extracted content | Same | Warning only |

### Running smoke tests locally

```bash
# Linux/macOS
bash desktop/scripts/smoke-test-desktop.sh path/to/artifacts/

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File desktop/scripts/smoke-test-desktop.ps1 path/to/artifacts/
```

### Interpreting results

- `[OK]` -- Check passed
- `[FAIL]` -- Check failed, blocks release in CI
- `[WARN]` -- Non-blocking warning (e.g., FFmpeg not detected but may be PATH-resolved)

## Troubleshooting

### Missing sidecar binary

**Symptom:** `FATAL: Required sidecar binaries are missing` during `prepare-sidecars.mjs`

**Resolution:**
1. Ensure the backend binary is built: `uv run pyinstaller --onefile src/podcast_pipeline/service/cli.py`
2. Set the `BACKEND_BIN` environment variable to the built binary path
3. Ensure FFmpeg is installed or set `FFMPEG_BIN`

### Asset resolution failures at runtime

**Symptom:** App starts but backend cannot find FFmpeg or model files

**Resolution:**
The runtime asset resolver checks these locations in order:

For binaries:
1. Environment variable override (`FFMPEG_BIN`, etc.)
2. Sidecar directory (next to the app binary)
3. System PATH

For models:
1. `WHISPER_MODELS_DIR` environment variable
2. Platform app data directory (`~/.local/share/podcast-pipeline/models` on Linux)
3. Project-local `models/` directory
4. HuggingFace Hub cache

Check `GET /system/readiness` for a full status report.

### Resume issues after crash

**Symptom:** Job stuck in "running" state after app restart

**Resolution:**
The recovery system handles this automatically:

1. On startup, the backend reconciles all jobs (corrects stale "running" to "interrupted")
2. The desktop app checks for resumable jobs and shows a recovery banner
3. Click "Resume" to restart from the last completed stage

If automatic recovery fails:
```bash
# Manual reconciliation via API
curl -X POST http://127.0.0.1:8787/jobs/reconcile

# List resumable jobs
curl http://127.0.0.1:8787/jobs/resumable

# Resume a specific job
curl -X POST http://127.0.0.1:8787/jobs/{job_id}/resume
```

### Backend fails to start

**Symptom:** Desktop app shows "Connecting..." indefinitely

**Resolution:**
1. Check if port 8787 is already in use: `lsof -i :8787` (macOS/Linux) or `netstat -ano | findstr 8787` (Windows)
2. Check sidecar binary permissions: `ls -la desktop/src-tauri/binaries/`
3. Try running the backend directly: `./desktop/src-tauri/binaries/podcast-backend-<triple> --port 8787`
4. Check logs in the Tauri dev console (View > Developer Tools)

### Tauri build fails

**Symptom:** `cargo build` or `tauri build` fails during CI

**Resolution:**
1. Ensure all system dependencies are installed (see workflow for platform-specific packages)
2. Check `SKIP_SIDECAR_CHECK=1` is set in CI (build.rs validation is skipped since binaries are prepared separately)
3. Verify Rust toolchain is installed: `rustc --version`
4. Clear Rust build cache: `cargo clean` in `desktop/src-tauri/`

## Manual Release Process

For local testing or when CI is unavailable:

```bash
# 1. Build the backend sidecar
cd /path/to/podcast-pipeline
uv sync
uv pip install pyinstaller
uv run pyinstaller --name podcast-backend --onefile --console \
    --hidden-import podcast_pipeline \
    --hidden-import uvicorn \
    src/podcast_pipeline/service/cli.py

# 2. Prepare sidecar binaries
export BACKEND_BIN=dist/podcast-backend
cd desktop
node scripts/prepare-sidecars.mjs

# 3. Install frontend dependencies
pnpm install

# 4. Build the Tauri app
pnpm tauri build

# 5. Find installer output
ls src-tauri/target/release/bundle/
# Linux: deb/, appimage/
# macOS: dmg/, macos/
# Windows: msi/, nsis/

# 6. Run smoke test
cd ..
bash desktop/scripts/smoke-test-desktop.sh desktop/src-tauri/target/release/bundle/
```

---

*Last updated: 2026-02-05*
*Part of Phase 3: Polishing + Desktop Distribution*
