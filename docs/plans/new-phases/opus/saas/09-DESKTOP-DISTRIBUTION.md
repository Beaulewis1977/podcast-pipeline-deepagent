# Desktop Distribution — Windows & macOS Install, Signing, and Auto-Update

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Reference:** `00-SAAS-MASTER-PLAN.md`, `.planning/phases/10-tauri-desktop-application-distribution/10-RESEARCH.md`
**Prerequisites:** Phase 10 base complete (Tauri v2 + sidecar lifecycle working)

---

## 1. Executive Summary

The desktop app (Tauri v2 + PyInstaller sidecar) must install and run cleanly on **Windows 10/11** and **macOS 12+ (Monterey/Ventura/Sonoma/Sequoia)**, including both Intel and Apple Silicon Macs. This document covers:

- Installer formats and configuration
- Code signing and notarization (eliminates "unknown publisher" / "damaged app" warnings)
- Auto-update for frictionless patching
- FFmpeg bundling and licensing compliance
- Binary size optimization
- Platform-specific quirks (SmartScreen, GateKeeper, antivirus false positives, CUDA drivers)
- Cost breakdown and timeline

### What Already Exists

| Component | Status | Reference |
|-----------|--------|-----------|
| Tauri v2 project with sidecar lifecycle | ✅ Complete | `desktop/src-tauri/` |
| CI/CD pipeline (4-target build matrix) | ✅ Complete | `.github/workflows/desktop-release.yml` |
| PyInstaller `--onedir` build step | ✅ Complete | CI line 79 |
| Code signing secrets (macOS + Windows) | ✅ Wired in CI | CI lines 198–207 |
| Smoke tests (Linux/macOS/Windows) | ✅ Complete | `desktop/scripts/smoke-test-*` |
| `build.rs` sidecar validation | ✅ Complete | `desktop/src-tauri/build.rs` |
| `prepare-sidecars.mjs` | ✅ Complete | `desktop/scripts/prepare-sidecars.mjs` |

### What This Document Adds

| Component | Purpose |
|-----------|---------|
| Code signing certificate procurement | Eliminate SmartScreen/GateKeeper warnings |
| Apple notarization configuration | Required for macOS distribution |
| Auto-updater plugin setup | Seamless in-app updates |
| FFmpeg legal compliance | LGPL license handling |
| Installer customization (NSIS/DMG) | Professional install experience |
| Windows Store / Mac App Store guidance | Optional additional distribution |
| GPU/CUDA driver handling | Graceful fallback for Windows |

---

## 2. Windows Distribution

### 2.1 Installer Format: NSIS (Recommended)

The CI already builds NSIS installers (`.exe` setup) and MSI. **NSIS is preferred** because it:
- Supports per-user install (no admin elevation required)
- Cross-compiles from Linux/macOS CI runners
- Smaller installer size than MSI
- Custom install UI possible

**Tauri NSIS Configuration:**

```jsonc
// desktop/src-tauri/tauri.conf.json — add to "bundle"
{
  "bundle": {
    "active": true,
    "targets": ["nsis", "msi"],
    "windows": {
      "nsis": {
        "installMode": "both",           // User can choose per-user or system-wide
        "displayLanguageSelector": false,
        "compression": "lzma",           // Best compression for large bundles
        "headerImage": "icons/installer-header.bmp",  // 150x57 banner
        "sidebarImage": "icons/installer-sidebar.bmp"  // 164x314 sidebar
      },
      "wix": {
        "language": "en-US"
      }
    }
  }
}
```

### 2.2 Code Signing (Windows)

**Problem:** Unsigned Windows apps trigger SmartScreen "Unknown publisher" warning. Users must click "More info → Run anyway" — this kills conversion rates.

**Solution:** Purchase an OV or EV code signing certificate.

| Certificate Type | Cost | Validation Time | SmartScreen Behavior |
|-----------------|------|----------------|---------------------|
| **OV (Organization Validation)** | $100–$200/year | 1–3 days | Warning initially → builds reputation over 100+ downloads |
| **EV (Extended Validation)** | $300–$500/year | 5–10 days | **Immediate SmartScreen trust** — no "Unknown publisher" |

**Recommended:** Start with **OV** ($100–$200/year) to keep costs low. Upgrade to EV when you hit $5K+ MRR and need instant trust.

**Providers:**
- DigiCert OV: ~$200/year (best reputation)
- Sectigo OV: ~$100/year (budget, still works)
- SSL.com OV: ~$120/year

**Process:**
1. Purchase OV cert from DigiCert/Sectigo
2. Complete organization verification (business registration proof)
3. Receive `.pfx` file with private key
4. Add to GitHub Secrets:
   - `WINDOWS_CERTIFICATE`: Base64-encoded `.pfx`
   - `WINDOWS_CERTIFICATE_PASSWORD`: PFX password
5. CI already uses these secrets (line 206–207 of `desktop-release.yml`)

**Build SmartScreen Reputation:**
- Sign consistently with the same certificate
- Host installers on HTTPS (GitHub Releases ✅)
- Encourage 100+ organic downloads in first month
- Full green reputation takes 1–3 months with OV cert

### 2.3 Windows-Specific Issues

#### Antivirus False Positives

**Problem:** PyInstaller `--onedir` bundles sometimes trigger Windows Defender and third-party antivirus (Avast, Norton) false positives because the packed executable pattern matches heuristic malware signatures.

**Mitigations:**

| Action | Effect |
|--------|--------|
| Code sign with OV/EV certificate | Reduces false positives by 80%+ |
| Submit to Microsoft Defender (via Partner Center) | Whitelist the binary hash |
| Submit to VirusTotal after each release | Check all 70+ AV engines; address any hits |
| Use `--onedir` (not `--onefile`) | Lower false positive rate (no self-extracting archive) |
| Avoid UPX compression | UPX triggers more AV heuristics than it saves |
| Add exclude instructions in install docs | Fallback for stubborn AV |

#### WebView2 Runtime

**Situation:** Tauri v2 on Windows requires the Edge WebView2 runtime, which is pre-installed on Windows 10 21H2+ and all Windows 11. For older systems:

```jsonc
// tauri.conf.json — WebView2 strategy
{
  "bundle": {
    "windows": {
      "webviewInstallMode": {
        "type": "downloadBootstrapper"  // Downloads WebView2 if missing (~1.5MB bootstrapper)
        // Alternative: "type": "offlineInstaller" — bundles full runtime (+100MB)
        // Alternative: "type": "skip" — assumes WebView2 present (Windows 11 only)
      }
    }
  }
}
```

**Recommendation:** Use `downloadBootstrapper` — adds only 1.5MB to installer and handles edge cases where WebView2 was manually removed.

#### GPU/CUDA Driver Handling

**Problem:** `faster-whisper` with CUDA requires NVIDIA drivers and cuBLAS/cuDNN runtimes.

**Solution:** CPU-first with optional GPU acceleration.

```python
# In service/cli.py — already decided in Phase 10 research
# GPU is opt-in, NOT bundled in base installer

def detect_gpu() -> bool:
    """Check for CUDA-capable GPU without requiring torch at import time."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

# Display in system tray or settings:
# "GPU detected: NVIDIA RTX 4090 — Transcription will use GPU acceleration"
# "No GPU detected — Transcription will use CPU (slower but works)"
```

**User guidance:** Include in app settings → "GPU Setup" link to NVIDIA driver download page.

---

## 3. macOS Distribution

### 3.1 Installer Format: DMG

Tauri v2 generates `.dmg` disk images by default on macOS. This is the standard for direct distribution.

```jsonc
// tauri.conf.json — macOS bundle options
{
  "bundle": {
    "macOS": {
      "minimumSystemVersion": "12.0",    // macOS Monterey
      "frameworks": [],
      "entitlements": "entitlements.plist",
      "exceptionDomain": "localhost",
      "signingIdentity": null             // Auto-detected from environment
    }
  }
}
```

### 3.2 Code Signing + Notarization (Required)

**Problem:** Unsigned macOS apps are blocked by GateKeeper with a "damaged" or "unidentified developer" dialog. Since macOS 10.15+, **notarization is also required** — signing alone is insufficient.

**Process:**

```
1. SIGN     ─── codesign with Developer ID Application cert
2. NOTARIZE ─── Submit to Apple for automated security scan
3. STAPLE   ─── Attach notarization ticket to the DMG
4. DISTRIBUTE ─ Users download and install without warnings
```

**Requirements:**
- **Apple Developer Program**: $99/year (enroll at developer.apple.com)
- **Developer ID Application** certificate (not Mac App Store certificate)
- **Xcode** (for `notarytool` and `stapler`)

**Setup for CI:**

The CI already has these secrets wired (lines 199–204):

| Secret | Purpose | How to Obtain |
|--------|---------|---------------|
| `APPLE_CERTIFICATE` | Base64 encoded `.p12` export of Developer ID Application cert | Xcode → Certificates → Export |
| `APPLE_CERTIFICATE_PASSWORD` | Password for the `.p12` file | Set during export |
| `APPLE_SIGNING_IDENTITY` | e.g., `"Developer ID Application: Your Name (TEAMID)"` | Keychain Access |
| `APPLE_ID` | Apple ID email used for notarization | developer.apple.com |
| `APPLE_PASSWORD` | App-specific password (not your Apple ID password!) | appleid.apple.com → Security → App-Specific Passwords |
| `APPLE_TEAM_ID` | 10-char team ID | developer.apple.com → Membership |

**Tauri handles notarization automatically** when these secrets are present — `tauri-action@v0` invokes `notarytool submit` and `stapler staple` as part of the build process.

### 3.3 Universal Binary (Intel + Apple Silicon)

**Situation:** ~50% of Macs in 2026 use Apple Silicon (M1/M2/M3/M4). The CI already builds both architectures:

| CI Runner | Target Triple | Arch |
|-----------|---------------|------|
| `macos-latest` | `aarch64-apple-darwin` | Apple Silicon (M1+) |
| `macos-15-intel` | `x86_64-apple-darwin` | Intel |

**Options:**

| Approach | Pros | Cons |
|----------|------|------|
| **Two separate DMGs** (current) | Simpler, smaller downloads | Users must pick correct version |
| **Universal binary** (lipo merge) | Single download works everywhere | 2× binary size, complex CI |

**Recommendation:** Keep **two separate DMGs** for now. Label downloads clearly:
- `PodcastPipeline-v1.0.0-mac-silicon.dmg` (M1/M2/M3/M4)
- `PodcastPipeline-v1.0.0-mac-intel.dmg` (Intel Macs)

The download page auto-detects architecture via JavaScript `navigator.userAgentData.architecture` and recommends the correct DMG.

**Apple Silicon note:** The PyInstaller sidecar must ALSO be built for the correct architecture. The CI matrix already handles this — each macOS runner builds the Python sidecar natively for its arch.

### 3.4 macOS Entitlements

```xml
<!-- desktop/src-tauri/entitlements.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Required for notarization with hardened runtime -->
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <!-- Required for PyInstaller sidecar (spawns subprocess) -->
    <key>com.apple.security.cs.allow-dyld-environment-variables</key>
    <true/>
    <!-- Required for FFmpeg/sidecar subprocess execution -->
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
    <!-- Network access for backend API + AI calls -->
    <key>com.apple.security.network.client</key>
    <true/>
    <!-- Localhost server (sidecar binds to 127.0.0.1) -->
    <key>com.apple.security.network.server</key>
    <true/>
    <!-- File access for podcast media files -->
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>
    <!-- Microphone access for voice Co-Pilot (Phase 12) -->
    <key>com.apple.security.device.audio-input</key>
    <true/>
</dict>
</plist>
```

### 3.5 GateKeeper Behavior (Unsigned)

If certificates aren't set up yet (dev mode):

| Scenario | User Experience | Workaround |
|----------|----------------|------------|
| **Unsigned + not notarized** | "X is damaged and can't be opened" | `xattr -cr /Applications/Podcast\ Pipeline.app` |
| **Signed but not notarized** | "X can't be opened because Apple cannot check it for malicious software" | Right-click → Open → Open |
| **Signed + notarized** ✅ | Opens normally, no warnings | None needed |

---

## 4. Auto-Update System

### 4.1 Tauri v2 Updater Plugin

**Goal:** Users get seamless in-app updates without re-downloading from the website.

#### Setup

```bash
# 1. Install the plugin
cd desktop
pnpm run tauri add updater
```

```jsonc
// 2. tauri.conf.json — add updater config
{
  "plugins": {
    "updater": {
      "active": true,
      "dialog": true,
      "endpoints": [
        "https://github.com/Beaulewis1977/podcast-pipeline/releases/latest/download/latest.json"
      ],
      "pubkey": "YOUR_ED25519_PUBLIC_KEY_HERE"
    }
  }
}
```

```bash
# 3. Generate signing keypair (one-time)
pnpm tauri signer generate -w ~/.tauri/podcast-pipeline.key
# Outputs: private key at ~/.tauri/podcast-pipeline.key
#          public key printed to console (put in tauri.conf.json pubkey)
```

```yaml
# 4. Add to CI — pass signing key as secret
- name: Build Tauri application
  uses: tauri-apps/tauri-action@v0
  env:
    TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
    TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_KEY_PASSWORD }}
    # ... existing secrets ...
```

#### How It Works

```
1. App starts → checks endpoint for latest.json
2. latest.json contains version, download URL, signature
3. If server version > current version:
   → Show dialog: "Update available! v1.1.0 → Download?"
4. User clicks "Update" → downloads new installer
5. Verifies signature (Ed25519) → installs → restarts
```

#### latest.json Format (Auto-Generated by tauri-action)

```json
{
  "version": "1.1.0",
  "notes": "Bug fixes and performance improvements",
  "pub_date": "2026-03-15T00:00:00Z",
  "platforms": {
    "windows-x86_64": {
      "signature": "base64-ed25519-signature...",
      "url": "https://github.com/.../releases/download/v1.1.0/Podcast-Pipeline_1.1.0_x64-setup.nsis.zip"
    },
    "darwin-aarch64": {
      "signature": "base64-ed25519-signature...",
      "url": "https://github.com/.../releases/download/v1.1.0/Podcast-Pipeline_1.1.0_aarch64.app.tar.gz"
    },
    "darwin-x86_64": {
      "signature": "base64-ed25519-signature...",
      "url": "https://github.com/.../releases/download/v1.1.0/Podcast-Pipeline_1.1.0_x64.app.tar.gz"
    },
    "linux-x86_64": {
      "signature": "base64-ed25519-signature...",
      "url": "https://github.com/.../releases/download/v1.1.0/Podcast-Pipeline_1.1.0_amd64.AppImage.tar.gz"
    }
  }
}
```

### 4.2 Update Hosting: GitHub Releases (Free)

| Option | Cost | Pros | Cons |
|--------|------|------|------|
| **GitHub Releases** ✅ | $0 | Built-in, CDN-backed, CI-native | Public repo required for free |
| S3 + CloudFront | $5–20/mo | Full control, private | Setup overhead |
| Self-hosted (Render) | $7/mo | Custom update logic | More maintenance |

**Recommendation:** Use GitHub Releases. The CI already creates draft releases on tag push. The updater endpoint points to the `latest.json` file in the latest release.

---

## 5. FFmpeg Bundling & Legal Compliance

### 5.1 Current Setup

FFmpeg is listed in `externalBin` in `tauri.conf.json`:
```json
"externalBin": [
    "binaries/podcast-backend/podcast-backend",
    "binaries/ffmpeg",
    "binaries/ffprobe"
]
```

The CI installs FFmpeg per-platform (brew/apt/choco) and the `prepare-sidecars.mjs` script copies the binaries.

### 5.2 Licensing Compliance (LGPL)

FFmpeg is licensed under **LGPL 2.1+** (or GPL 2+ if compiled with certain options like `--enable-gpl`).

**Our situation:** We bundle pre-compiled FFmpeg binaries as separate executables invoked via subprocess. This is the **safest legal approach** — we are NOT linking FFmpeg into our code.

**Required compliance actions:**

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Include FFmpeg license text | Ship `LICENSES/ffmpeg-LICENSE.txt` in installer | TODO |
| Acknowledge FFmpeg in about/credits | "This product includes FFmpeg. See ffmpeg.org" | TODO |
| Do NOT modify FFmpeg source | We use stock builds | ✅ |
| Include build config of bundled FFmpeg | Ship `ffmpeg -buildconf` output in `LICENSES/` | TODO |
| Provide FFmpeg source or link | Link to ffmpeg.org/download.html in docs | TODO |

**Template:**

```text
# LICENSES/ffmpeg-LICENSE.txt

This software includes FFmpeg (https://ffmpeg.org/).
FFmpeg is licensed under the GNU Lesser General Public License (LGPL) version 2.1.

FFmpeg source code is available at: https://ffmpeg.org/download.html

The FFmpeg binaries bundled with this application were obtained from:
- macOS: Homebrew (brew install ffmpeg)
- Windows: Chocolatey (choco install ffmpeg)
- Linux: System package (apt install ffmpeg)

The full LGPL 2.1 license text is available at:
https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
```

### 5.3 FFmpeg Source Strategy

| Approach | Pros | Cons | Recommended |
|----------|------|------|:-----------:|
| **Bundle system FFmpeg** (current) | No licensing headaches, always up-to-date | Varies per system build | ✅ For CI builds |
| BtbN static builds (GitHub) | Consistent, pre-built, well-tested | Extra download step | Alternative |
| Custom compiled FFmpeg | Full control over codecs/licensing | Build complexity, maintenance | ❌ Not needed |
| Require user install | Zero legal risk | Terrible UX, support burden | ❌ |

---

## 6. Binary Size Optimization

### 6.1 Current Expected Sizes

| Component | Estimated Size | Notes |
|-----------|---------------|-------|
| Tauri app (Rust + WebView) | 5–10 MB | Minimal overhead |
| React frontend (dist/) | 2–5 MB | Vite tree-shakes well |
| PyInstaller sidecar (CPU-only) | 150–300 MB | Python + FastAPI + faster-whisper + ctranslate2 |
| FFmpeg binary | 20–40 MB | Static build |
| FFprobe binary | 10–15 MB | Subset of FFmpeg |
| **Total installer** | **~200–370 MB** | Compressed: ~120–200 MB |

### 6.2 Optimization Techniques

| Technique | Savings | Implementation |
|-----------|---------|----------------|
| **PyInstaller `--exclude-module`** | 20–50 MB | Exclude: `tkinter, unittest, pytest, streamlit, test, setuptools` |
| **NSIS LZMA compression** | 40–50% | Already configured in Section 2.1 |
| **CPU-only base bundle** | 300+ MB | Don't bundle CUDA/torch in base — GPU is opt-in |
| **Strip debug symbols** | 5–10% | PyInstaller `--strip` flag (Linux/macOS) |
| **Prune unused ctranslate2 models** | 50–100 MB | Only ship the quantization types you use |
| **Separate GPU download** | N/A | "Download GPU acceleration" button in settings (post-install) |

### 6.3 PyInstaller Spec File (Updated for Size)

```python
# desktop/sidecar.spec

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Collect ctranslate2 native libraries
ct2_binaries = collect_dynamic_libs('ctranslate2')
ct2_datas = collect_data_files('ctranslate2')
fw_datas = collect_data_files('faster_whisper')

a = Analysis(
    ['src/podcast_pipeline/service/cli.py'],
    binaries=ct2_binaries,
    datas=[*ct2_datas, *fw_datas],
    hiddenimports=[
        'ctranslate2', 'faster_whisper',
        'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto', 'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'podcast_pipeline',
    ],
    excludes=[
        'pytest', 'unittest', 'tkinter', 'wx', 'PyQt5', 'PyQt6',
        'streamlit', 'test', 'setuptools', 'pip', 'wheel',
        'IPython', 'jupyter', 'notebook', 'sphinx',
    ],
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='podcast-backend',
    console=True,      # Needed for sidecar stdout signaling
    strip=True,        # Strip debug symbols
    upx=False,         # UPX causes AV false positives — don't use
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    name='podcast-backend',
)
```

---

## 7. First-Run Experience

### 7.1 Windows First-Run

```
1. User downloads PodcastPipeline-v1.0.0-x64-setup.exe
2. Windows SmartScreen:
   ├── Signed (OV cert): "Publisher: Podcast Pipeline LLC" → Install
   ├── Signed (EV cert): No warning at all → Install
   └── Unsigned: "Unknown publisher" → "More info" → "Run anyway"
3. NSIS installer:
   ├── "Install for current user" (no admin) ← default
   └── "Install for all users" (requires admin)
4. App installed to:
   ├── Per-user: %LOCALAPPDATA%\Podcast Pipeline\
   └── System: C:\Program Files\Podcast Pipeline\
5. Desktop shortcut + Start Menu entry created
6. First launch:
   ├── Sidecar (podcast-backend) starts automatically
   ├── Health check polls until ready (5-15 seconds)
   ├── If GPU detected: "GPU acceleration available ✅"
   └── Main window opens
```

### 7.2 macOS First-Run

```
1. User downloads PodcastPipeline-v1.0.0-mac-silicon.dmg
2. Opens DMG → drag app to /Applications
3. GateKeeper check:
   ├── Signed + notarized: Opens normally ✅
   ├── Signed only: "Can't be opened" → Right-click → Open → Open
   └── Unsigned: "Damaged" → Need xattr -cr command
4. First launch:
   ├── macOS permissions dialog: "Podcast Pipeline wants to access files" → Allow
   ├── If microphone used later: "Podcast Pipeline wants to access the microphone" → Allow
   ├── Sidecar starts, health check polls
   └── Main window opens
5. Subsequent launches: No dialogs
```

---

## 8. App Store Distribution (Optional / Deferred)

### 8.1 Mac App Store

| Factor | Assessment |
|--------|-----------|
| **Revenue share** | 30% commission (15% for small developers < $1M/year) |
| **Sandboxing requirement** | BLOCKS subprocess execution (PyInstaller sidecar) |
| **Verdict** | ❌ **Not viable** — sandboxing prevents sidecar pattern |

**Alternative:** Direct distribution via website + auto-updater. This is what Descript, Figma, and most creative tools do.

### 8.2 Microsoft Store

| Factor | Assessment |
|--------|-----------|
| **Revenue share** | 15% commission (games: 12%) |
| **Account cost** | $19 one-time (individuals) / $99 (companies) |
| **Requirements** | MSIX package, Partner Center certification, privacy policy |
| **Verdict** | ⚠️ **Possible but not priority** — extra packaging work |

**Recommendation:** Defer both app stores. Direct distribution with auto-updater is simpler, cheaper, and standard for SaaS desktop tools.

---

## 9. Cost Summary

### One-Time Costs

| Item | Cost | When |
|------|------|------|
| Apple Developer Program | $99/year | Before first macOS release |
| Windows OV code signing cert | $100–$200/year | Before first Windows release |
| Tauri signing key generation | $0 (CLI tool) | Before first release |
| **Total one-time** | **$199–$299/year** | |

### Ongoing Costs

| Item | Cost | Notes |
|------|------|-------|
| Apple Developer renewal | $99/year | Required to maintain notarization |
| Windows cert renewal | $100–$200/year | Required to keep signing |
| GitHub Releases (update hosting) | $0 | Free for public repos |
| **Total annual** | **$199–$299/year** | |

### Upgrade Path (If Needed)

| Trigger | Upgrade | Cost |
|---------|---------|------|
| Still getting SmartScreen warnings after 3 months | Windows EV cert | +$200–$300/year |
| Want Mac App Store presence | Mac App Store account (already have) | $0 (already in Developer Program) |
| Want Windows Store presence | Microsoft Partner Center | $19–$99 one-time |
| Need private update hosting | S3 + CloudFront | ~$10–$20/month |

---

## 10. Implementation Checklist

### Pre-Release (Do Once)

- [ ] Enroll in Apple Developer Program ($99/year)
- [ ] Create Developer ID Application certificate
- [ ] Export certificate as `.p12`, base64 encode, add to GitHub Secrets
- [ ] Generate app-specific password for notarization
- [ ] Add all `APPLE_*` secrets to GitHub repo
- [ ] Purchase Windows OV code signing cert ($100–$200/year)
- [ ] Export as `.pfx`, base64 encode, add to GitHub Secrets as `WINDOWS_CERTIFICATE`
- [ ] Generate Tauri update signing keypair (`pnpm tauri signer generate`)
- [ ] Add `TAURI_SIGNING_PRIVATE_KEY` to GitHub Secrets
- [ ] Add updater public key to `tauri.conf.json`
- [ ] Install `@tauri-apps/plugin-updater`
- [ ] Create `entitlements.plist` for macOS
- [ ] Create `LICENSES/ffmpeg-LICENSE.txt`
- [ ] Add installer images (header: 150×57, sidebar: 164×314 BMP)

### Per-Release (Automated by CI)

- [ ] Tag version (`git tag v1.0.0 && git push --tags`)
- [ ] CI builds 4 targets (Linux, macOS ARM, macOS Intel, Windows)
- [ ] CI signs Windows installer with OV cert
- [ ] CI signs + notarizes + staples macOS DMG
- [ ] CI generates `latest.json` for auto-updater
- [ ] CI creates draft GitHub Release with all artifacts
- [ ] Review release notes → publish

### Post-First-Release

- [ ] Submit Windows installer to Microsoft Defender (reduce false positives)
- [ ] Upload `.exe` to VirusTotal — check for false positives
- [ ] Monitor SmartScreen reputation (check after 100+ downloads)
- [ ] Test auto-update cycle: v1.0.0 → v1.0.1
- [ ] Verify both macOS architectures install and run correctly
- [ ] Verify Windows per-user install works without admin

---

## 11. Testing Matrix

| Platform | Test | Pass Criteria |
|----------|------|--------------|
| Windows 11 (x64) | Install NSIS per-user | Installs without admin, sidecar starts |
| Windows 11 (x64) | SmartScreen with OV cert | Shows publisher name, not "Unknown" |
| Windows 10 (x64) | Install + run | WebView2 bootstrapper installs if needed |
| macOS 14 (Apple Silicon) | Install DMG | No GateKeeper warnings, sidecar starts |
| macOS 14 (Intel) | Install DMG | Rosetta not required (native Intel build) |
| macOS 12 (min supported) | Install DMG | Minimum OS version check works |
| All platforms | Auto-update v1 → v2 | Update dialog appears, installs, restarts |
| All platforms | Sidecar coexistence | Detects existing backend, doesn't spawn duplicate |
| Windows | Uninstall | Clean removal, no orphan processes/files |
| macOS | Delete from Applications | Clean removal |

---

*This document complements the Phase 10 research and the SaaS master plan. The CI pipeline is already structurally complete — this doc covers the certificate procurement, configuration, and testing needed to ship a professional installer.*
