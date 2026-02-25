# Phase 10: Tauri Desktop Application Distribution - Research

**Researched:** 2026-02-25
**Domain:** Tauri v2 + Python FastAPI sidecar + PyInstaller + React desktop application
**Confidence:** MEDIUM-HIGH (Tauri v2 APIs verified against official docs; PyInstaller ML bundling pitfalls based on community evidence with known gaps)

---

## User Constraints

### Locked Decisions

1. **Coexistence:** Streamlit and Desktop app MUST both work simultaneously. Both are independent frontends consuming the same FastAPI backend. If the service is already running (started by CLI for Streamlit), the Desktop app must detect and connect to it. If not running, Tauri starts it via sidecar.
2. **Desktop Superset:** The Desktop app does everything Streamlit does AND MORE. It is a strict superset — every Streamlit feature must have a desktop equivalent, plus native-only features (drag-drop, waveform timeline, glassmorphism UI, batch queue, etc.).
3. **Shared Backend:** No UI-specific logic in FastAPI. Both frontends consume the exact same REST API. Desktop gets richer client-side features, not different endpoints.

### Port Conflict Implications

- FastAPI sidecar must handle "port already in use" gracefully — if 8787 is taken (by CLI-started service), the Tauri app should detect the existing instance and connect to it instead of crashing.
- Shutdown behavior: Tauri should NOT kill the sidecar if it didn't start it (another client may be using it).
- Health check pattern already in research works for both cases — poll until reachable, whether Tauri started it or it was already running.

---

## Summary

Phase 10 wraps the existing FastAPI service (`src/podcast_pipeline/service/`) into a Tauri v2 desktop application using the "sidecar" pattern. The Python backend is compiled to a standalone executable with PyInstaller and bundled inside the Tauri app via `bundle.externalBin`. Tauri spawns it at startup through `tauri-plugin-shell` and shuts it down via stdin signaling. The React/TypeScript frontend communicates with the FastAPI sidecar over localhost HTTP REST and WebSocket.

The biggest technical risk is PyInstaller bundling of the ML dependency chain (faster-whisper + ctranslate2 + torch + CUDA). CUDA-enabled torch bundles produce 2-4 GB executables; the standard mitigation is using `--onedir` mode instead of `--onefile` to avoid PyInstaller's extraction overhead on every launch. The ctranslate2/faster-whisper layer requires explicit `collect_dynamic_libs` in the spec file and correct CUDA DLL inclusion. A second major risk is the one-file PyInstaller bootloader limitation: Tauri only knows the PID of the bootloader process, not the actual Python child process, so `process.kill()` does not work; all shutdown must go through stdin signaling.

The frontend stack is React 19 + TypeScript + Vite + TailwindCSS v4 + shadcn/ui + Zustand (client state) + TanStack Query (server/API state). This is the established 2025 Tauri community stack, with multiple production templates demonstrating it. Wavesurfer.js v7 handles waveform visualization and has an experimental multitrack plugin. Distribution uses `tauri-apps/tauri-action@v0` GitHub Actions with matrix builds across Windows, macOS (ARM + Intel), and Linux.

**Primary recommendation:** Use `--onedir` PyInstaller mode (not `--onefile`) for the sidecar to avoid 5-10 second extraction delay on Windows. Ship the entire `dist/` directory as the Tauri sidecar "binary" entry. Implement a frontend health-check polling loop against `GET /health` (200ms interval, 30s timeout) before showing the main UI.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| tauri | 2.10.2 | Desktop application shell (Rust) | Stable v2 release; official sidecar, plugin, and IPC APIs |
| @tauri-apps/api | 2.10.1 | JavaScript API for Tauri features | Official, typed, maintained by core team |
| @tauri-apps/cli | 2.10.0 | Build/dev toolchain | Required for `tauri dev` and `tauri build` |
| tauri-plugin-shell | 2.x | Spawn/manage sidecar subprocess | Only official way to spawn external binaries in v2 |
| tauri-plugin-websocket | 2.x | Native WebSocket client | Required for ws:// connections in Tauri v2 (browser WS API not available) |
| React | 19.x | UI framework | Community default; official Tauri templates target React |
| TypeScript | 5.x | Type safety | Required for maintainable frontend codebase |
| Vite | 6.x | Frontend bundler | Tauri's official recommended build tool |
| TailwindCSS | 4.x | Utility-first CSS | v4 supports CSS-native config; Vite plugin integration |
| shadcn/ui | latest | Component library | Copy-owned components; pairs with Tailwind; dark mode first |
| Zustand | 5.x | Client-side state | Minimal boilerplate; 2025 ecosystem standard |
| TanStack Query | 5.x | Server state / API calls | Caching, polling, refetch on window focus; pairs with Zustand |
| PyInstaller | 6.19+ | Bundle Python+FastAPI into binary | Ecosystem standard for Tauri Python sidecar; most mature |
| wavesurfer.js | 7.x | Waveform visualization | Official React wrapper; has multitrack experiment |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @tauri-apps/plugin-fs | 2.x | File system access | Reading dropped files after getting paths from onDragDropEvent |
| glasscn-ui / shadcn-glass-ui | latest | Glassmorphism component overlays | For the deep dark glassmorphism aesthetic from spec |
| @wavesurfer/react | 7.x | React hook for wavesurfer | Official wrapper; use instead of raw wavesurfer in React |
| tauri-action | v0.6.1 | GitHub Actions build CI | Official action; handles matrix builds and release artifacts |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyInstaller | Nuitka | Nuitka compiles to C, potentially smaller output, but significantly harder to configure with binary ML dependencies; not community-standard for Tauri sidecar pattern |
| PyInstaller | PyOxidizer | Abandoned/unmaintained as of 2024; needs to build deps from source; worse ML support |
| shadcn/ui | Ant Design / MUI | Both work in Tauri; but shadcn is component-owned (no version lock-in) and is design-first for dark mode apps |
| TanStack Query | SWR | Both work; TanStack Query has better WebSocket integration story via cache invalidation pattern |
| React | Vue 3 | Both work equally well in Tauri; React has wider Tauri template/example ecosystem in 2025 |

### Installation

```bash
# Scaffold Tauri v2 + React + TypeScript + Vite
npm create tauri-app@latest -- --template react-ts

# Inside the new project:
npm install

# Add Tauri plugins
npm run tauri add shell
npm run tauri add websocket

# Frontend dependencies
npm install @tanstack/react-query zustand
npm install tailwindcss @tailwindcss/vite
npm install @wavesurfer/react wavesurfer.js

# shadcn/ui setup (run after tailwind configured)
npx shadcn@latest init
```

---

## Architecture Patterns

### Recommended Project Structure

```
podcast-pipeline-desktop/         # Tauri workspace root
├── src/                          # React frontend (TypeScript)
│   ├── main.tsx                  # React entry point
│   ├── App.tsx                   # Root component with QueryClient
│   ├── components/               # UI components
│   │   ├── ui/                   # shadcn/ui generated components
│   │   ├── waveform/             # Wavesurfer.js wrappers
│   │   └── layout/               # App shell, sidebar, nav
│   ├── views/                    # Page-level views (Dashboard, Studio, etc.)
│   ├── hooks/                    # TanStack Query hooks for FastAPI endpoints
│   ├── stores/                   # Zustand stores (UI state, theme, preferences)
│   ├── api/                      # API client (fetch wrappers for localhost:8787)
│   └── lib/                      # Utilities
├── src-tauri/                    # Tauri Rust shell
│   ├── src/
│   │   ├── lib.rs                # App setup, sidecar spawn, lifecycle
│   │   └── main.rs               # Entry point (calls lib.rs run())
│   ├── binaries/                 # Compiled Python sidecar goes here
│   │   └── podcast-pipeline-sidecar-x86_64-pc-windows-msvc.exe
│   ├── capabilities/
│   │   └── default.json          # Shell, WebSocket, FS permissions
│   └── tauri.conf.json           # Bundle config with externalBin
├── src-python/                   # Python sidecar entrypoint + spec
│   ├── sidecar_main.py           # FastAPI server startup script
│   └── sidecar.spec              # PyInstaller spec file
└── scripts/
    ├── build-sidecar-windows.sh
    ├── build-sidecar-macos.sh
    └── build-sidecar-linux.sh
```

### Pattern 1: Sidecar Lifecycle Management (Rust)

**What:** Rust spawns the PyInstaller binary at app startup, monitors stdout for readiness signal, and sends shutdown via stdin on window close.
**When to use:** Every Tauri + Python sidecar app.

```rust
// Source: https://v2.tauri.app/develop/sidecar/ + aiechoes.substack.com production guide
// src-tauri/src/lib.rs

use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_websocket::init())
        .setup(|app| {
            let sidecar_command = app.shell()
                .sidecar("podcast-pipeline-sidecar")?
                // CRITICAL: prevents Windows encoding crashes on emoji/special chars in logs
                .env("PYTHONUTF8", "1")
                .env("PYTHONIOENCODING", "utf-8");

            let (mut rx, child) = sidecar_command.spawn()?;

            // Store child handle for shutdown
            app.manage(std::sync::Mutex::new(Some(child)));

            // Pipe stdout/stderr to Tauri logs
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[sidecar] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[sidecar:err] {}", String::from_utf8_lossy(&line));
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // Send shutdown signal via stdin (process.kill() DOES NOT WORK for PyInstaller one-file)
                // For --onedir builds, you can attempt child.kill() but stdin signal is more reliable
                if let Some(child_guard) = window.app_handle().try_state::<std::sync::Mutex<Option<tauri_plugin_shell::process::CommandChild>>>() {
                    if let Ok(mut guard) = child_guard.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.write(b"shutdown\n");
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### Pattern 2: Tauri Configuration for Sidecar

**What:** `tauri.conf.json` bundle configuration for external binary packaging.
**When to use:** Every build.

```json
// Source: https://v2.tauri.app/develop/sidecar/
// src-tauri/tauri.conf.json
{
  "bundle": {
    "externalBin": [
      "binaries/podcast-pipeline-sidecar"
    ]
  }
}
```

Binary naming convention (REQUIRED):
```bash
# Find your target triple
rustc --print host-tuple
# Output example: x86_64-pc-windows-msvc

# Binary must be named:
# binaries/podcast-pipeline-sidecar-x86_64-pc-windows-msvc.exe  (Windows)
# binaries/podcast-pipeline-sidecar-x86_64-unknown-linux-gnu    (Linux)
# binaries/podcast-pipeline-sidecar-aarch64-apple-darwin        (macOS ARM)
```

### Pattern 3: Permissions Configuration

**What:** Capability file enabling shell spawn and WebSocket.
**When to use:** Required for sidecar and WebSocket to work.

```json
// Source: https://v2.tauri.app/develop/sidecar/ + https://v2.tauri.app/plugin/websocket/
// src-tauri/capabilities/default.json
{
  "identifier": "default",
  "description": "Default capabilities",
  "windows": ["main"],
  "permissions": [
    {
      "identifier": "shell:allow-execute",
      "allow": [{
        "name": "binaries/podcast-pipeline-sidecar",
        "sidecar": true
      }]
    },
    "websocket:default",
    "fs:allow-read-file",
    "fs:allow-write-file"
  ]
}
```

### Pattern 4: Sidecar-or-Attach Startup (Coexistence with Streamlit)

**What:** On startup, first check if FastAPI is already running (started by CLI for Streamlit). If yes, attach to it. If no, spawn sidecar. On shutdown, only kill sidecar if Tauri started it.
**When to use:** Every Tauri app startup. This is REQUIRED because Streamlit and Desktop must coexist.

```rust
// src-tauri/src/lib.rs — enhanced setup with attach-or-spawn logic
// The Rust side attempts to spawn sidecar. If port is already bound,
// it skips spawn and sets a flag so shutdown doesn't kill the service.

use std::sync::atomic::{AtomicBool, Ordering};

static TAURI_OWNS_SIDECAR: AtomicBool = AtomicBool::new(false);

// In setup:
// 1. Check if http://127.0.0.1:8787/health is reachable
// 2. If yes → set TAURI_OWNS_SIDECAR=false, skip spawn
// 3. If no → spawn sidecar, set TAURI_OWNS_SIDECAR=true

// In on_window_event CloseRequested:
// Only send shutdown signal if TAURI_OWNS_SIDECAR is true
```

```typescript
// Source: Community pattern, verified against TanStack Query docs
// src/hooks/useSidecarReady.ts
import { useQuery } from '@tanstack/react-query';

const API_BASE = 'http://127.0.0.1:8787';

export function useSidecarReady() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) throw new Error('Not ready');
      return res.json();
    },
    retry: 150,           // up to 30 seconds
    retryDelay: 200,      // 200ms between polls
    refetchInterval: false,
    staleTime: Infinity,
  });
}
```

### Pattern 5: Native File Drag-Drop (Tauri v2)

**What:** Get real OS file paths from drag-drop events. Browser File API does NOT give full paths in Tauri.
**When to use:** Project ingestion screen.

```typescript
// Source: https://v2.tauri.app/reference/javascript/api/namespacewebview/
import { getCurrentWebview } from "@tauri-apps/api/webview";

const unlisten = await getCurrentWebview().onDragDropEvent((event) => {
  if (event.payload.type === 'drop') {
    const filePaths: string[] = event.payload.paths;
    // filePaths contains full OS paths - send these to FastAPI /jobs endpoint
    console.log('Dropped files:', filePaths);
  }
});

// Cleanup on component unmount
return () => unlisten();
```

**Critical:** `app.window.dragDropEnabled` must be `true` in `tauri.conf.json` (it is by default). Do NOT use react-dropzone for getting file paths - it returns browser File objects without paths.

### Pattern 6: WebSocket Progress Feed (FastAPI → Frontend)

**What:** Connect to FastAPI WebSocket for job progress events.
**When to use:** Progress bars during pipeline execution.

```typescript
// Source: https://v2.tauri.app/plugin/websocket/
import WebSocket from '@tauri-apps/plugin-websocket';

const ws = await WebSocket.connect('ws://127.0.0.1:8787/jobs/{jobId}/ws');
const remove = ws.addListener((msg) => {
  // msg.data is the JSON progress event from FastAPI
  const event = JSON.parse(msg.data as string);
  // Update Zustand store with progress
});

// Disconnect when component unmounts or job completes
await ws.disconnect();
```

### Pattern 7: PyInstaller Spec File for FastAPI + ML Stack

**What:** PyInstaller spec file that correctly bundles ctranslate2, faster-whisper, and torch.
**When to use:** Building the sidecar binary.

```python
# Source: Verified against aiechoes.substack.com production guide + pyinstaller docs
# src-python/sidecar.spec

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# Collect binary DLLs for ML libraries that have native extensions
ct2_binaries = collect_dynamic_libs('ctranslate2')
ct2_datas = collect_data_files('ctranslate2')

faster_whisper_datas = collect_data_files('faster_whisper')

a = Analysis(
    ['sidecar_main.py'],
    pathex=[],
    binaries=ct2_binaries,
    datas=[
        *ct2_datas,
        *faster_whisper_datas,
        # Include tokenizer model files if needed
    ],
    hiddenimports=[
        'ctranslate2',
        'faster_whisper',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
    ],
    hookspath=[],
    excludes=[
        # Exclude test frameworks to reduce size
        'pytest', 'unittest', 'doctest',
        # Exclude GUI frameworks not needed
        'tkinter', 'wx', 'PyQt5',
        # Exclude streamlit (not needed in sidecar)
        'streamlit',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# Use COLLECT (--onedir mode) NOT EXE onefile -- avoids PyInstaller extraction
# overhead on every launch (critical for 1-4GB torch bundles)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # Keep binaries separate (onedir)
    name='podcast-pipeline-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX causes issues with CUDA DLLs
    console=True,            # Keep console for stdout/stderr sidecar comms
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='podcast-pipeline-sidecar',
)
```

**Build command:**
```bash
# From project root, with uv
uv run pyinstaller src-python/sidecar.spec --distpath src-tauri/binaries/
```

**CRITICAL (--onedir + Tauri):** Tauri's `externalBin` expects a single file. With `--onedir`, wrap the dist directory in a launcher script, or configure Tauri to point to the executable inside the dist folder. The community pattern is to copy the entire `dist/podcast-pipeline-sidecar/` directory to `src-tauri/binaries/` and set `externalBin` to `"binaries/podcast-pipeline-sidecar/podcast-pipeline-sidecar"`. The surrounding directory travels alongside the executable in the Tauri bundle.

### Pattern 8: sidecar_main.py Entrypoint (UTF-8 Fix)

```python
# Source: aiechoes.substack.com production guide - critical for Windows
# src-python/sidecar_main.py
import os
import sys

# MUST be set before any imports that output Unicode (structlog uses emoji)
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import uvicorn
from podcast_pipeline.service.app import create_app

if __name__ == '__main__':
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="info")
```

### Pattern 9: TailwindCSS v4 + Vite Configuration

```typescript
// Source: https://tailwindcss.com/docs/guides/vite
// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),   // v4 uses Vite plugin, NOT tailwind.config.js
  ],
  // Required for Tauri: prevents Vite from replacing undefined
  envPrefix: ['VITE_', 'TAURI_ENV_*'],
  build: {
    target: process.env.TAURI_ENV_PLATFORM == 'windows' ? 'chrome105' : 'safari13',
  },
});
```

```css
/* src/index.css */
@import "tailwindcss";

/* Dark mode via class strategy */
@custom-variant dark (&:where(.dark, .dark *));
```

### Anti-Patterns to Avoid

- **Using `process.kill()` for PyInstaller one-file sidecars:** Tauri only knows the bootloader PID, not the actual Python process. Use `--onedir` mode OR stdin signaling for shutdown.
- **Using browser WebSocket API (`new WebSocket()`) in Tauri:** This is not available in Tauri's webview context for localhost connections. Use `@tauri-apps/plugin-websocket` instead.
- **Using react-dropzone for file paths:** It provides browser `File` objects without full OS paths. Use `getCurrentWebview().onDragDropEvent()` to get `event.payload.paths`.
- **Importing streamlit or heavy dev deps in the sidecar entrypoint:** Bloats the bundle. Use `excludes` in the spec file.
- **Using `--onefile` PyInstaller mode with CUDA torch:** Produces 2-4 GB executable that extracts to temp on every launch (5-10 second delay). Use `--onedir` instead.
- **Hot-reloading Python changes during `tauri dev`:** PyInstaller binary must be manually recompiled after any Python change. No live reload for the sidecar.
- **Running `tauri build` before copying the sidecar binary:** Build will fail if `binaries/` doesn't contain the platform-specific binary. Always build sidecar first.
- **Forgetting UTF-8 environment variables:** Windows crashes when structlog or other libraries emit emoji/Unicode in logs. Set `PYTHONUTF8=1` in both the spec env and in `sidecar_main.py` before any imports.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Waveform visualization | Custom SVG/Canvas waveform renderer | wavesurfer.js v7 + @wavesurfer/react | Pre-decoded peaks, zoom, regions, pan; battle-tested |
| WebSocket client in Tauri | Raw WebSocket or EventSource | @tauri-apps/plugin-websocket | Browser WS not available; plugin handles native Rust WS |
| File drag-drop with OS paths | Browser drag-drop API (no paths) | getCurrentWebview().onDragDropEvent() | Only Tauri webview API returns full OS file paths |
| Progress/job polling | Manual setInterval fetch loop | TanStack Query refetchInterval or WS invalidation | Cache management, error states, retry logic already solved |
| Component system for dark glassmorphism | Custom CSS component library | shadcn/ui + glasscn-ui or shadcn-glass-ui | WCAG-compliant dark mode, React 19 + Tailwind v4 compatible |
| Cross-platform builds | Custom GitHub Actions matrix | tauri-apps/tauri-action@v0 | Handles codesigning, artifact upload, release creation |
| Auto-updater | Custom update mechanism | tauri-plugin-updater | Signature verification, rollback, GitHub releases hosting |
| State management for API data | useState + useEffect fetch patterns | TanStack Query | Background refetch, deduplication, optimistic updates |

**Key insight:** The Tauri + Python sidecar ecosystem has mature tooling. Custom solutions in every one of these areas introduce well-documented failure modes the libraries already handle.

---

## Common Pitfalls

### Pitfall 1: PyInstaller One-File with CUDA Torch

**What goes wrong:** `--onefile` produces a 2-4 GB exe that extracts to a temp directory on every launch. On Windows with CUDA torch, extraction takes 8-15 seconds every time the app opens, making it feel broken.
**Why it happens:** PyInstaller one-file mode packs everything into a self-extracting archive. CUDA runtime DLLs are enormous.
**How to avoid:** Use `--onedir` mode. Ship the sidecar as a directory. Tauri bundles the entire directory. First launch still takes longer (Python init + torch load), but there is no extraction step.
**Warning signs:** Sidecar takes >10 seconds to appear on health check poll. Temp folder grows to 2-4 GB on Windows (`%TEMP%\_{MEIXXXXXX}` directories accumulate if app crashes before cleanup).

### Pitfall 2: process.kill() Fails for One-File Sidecars

**What goes wrong:** `child.kill()` in Rust kills the PyInstaller bootloader process, but the actual Python interpreter (child of the bootloader) keeps running in the background. FastAPI continues to hold port 8787. On next app launch, sidecar fails to bind the port.
**Why it happens:** PyInstaller bootloader spawns a second process. Tauri only tracks the bootloader PID.
**How to avoid:** Use `--onedir` mode (process tree is simpler and `kill()` works) OR implement stdin shutdown signaling in the FastAPI sidecar (`sidecar_main.py` listens for a `shutdown\n` line on stdin and calls `sys.exit(0)`).
**Warning signs:** Port 8787 already in use error on second app launch. Orphan Python processes visible in Task Manager.

### Pitfall 3: ctranslate2 DLL Not Found on Windows

**What goes wrong:** Bundled sidecar runs but crashes with `ImportError: libctranslate2.dll not found` because PyInstaller didn't auto-detect the native DLLs.
**Why it happens:** ctranslate2 uses `ctypes`-based dynamic loading that PyInstaller's static analysis cannot follow.
**How to avoid:** In the spec file, explicitly call `collect_dynamic_libs('ctranslate2')` and add result to `binaries`. Also add `'ctranslate2'` to `hiddenimports`.
**Warning signs:** Sidecar exits immediately after spawn with code 1. stderr shows ImportError or DLL load failure.

### Pitfall 4: Missing Binary Before tauri build

**What goes wrong:** `npm run tauri build` fails with `external binary not found` because the PyInstaller step was skipped or the binary is in the wrong location/named incorrectly.
**Why it happens:** Tauri validates that all `externalBin` paths exist at build time.
**How to avoid:** Add a pre-build script in `package.json` that runs the PyInstaller build first. Enforce the exact naming convention: `<name>-<target-triple>(.exe)`. Always get the target triple from `rustc --print host-tuple`.
**Warning signs:** Error mentioning `externalBin` or `external binary` during `tauri build`. Missing file in `src-tauri/binaries/`.

### Pitfall 5: WebSocket Connection Fails in Tauri WebView

**What goes wrong:** Frontend code using `new WebSocket('ws://127.0.0.1:8787/...')` throws an error or silently fails in the packaged Tauri app.
**Why it happens:** Tauri's webview does not have the browser's native WebSocket API available for localhost ws:// connections in the same way a browser does.
**How to avoid:** Install and use `@tauri-apps/plugin-websocket`. Add `npm run tauri add websocket` to setup. Add `"websocket:default"` to capabilities.
**Warning signs:** WebSocket connects fine in `tauri dev` (which uses a browser-like context) but fails in production build.

### Pitfall 6: Sidecar Not Ready When Frontend Loads

**What goes wrong:** Frontend renders and immediately calls `/jobs` or other API endpoints, gets connection refused, shows error state permanently.
**Why it happens:** FastAPI sidecar + Python interpreter initialization takes 2-10 seconds. UI loads in ~200ms.
**How to avoid:** Implement a mandatory health-check polling gate in the React app root. Don't render job management UI until `GET /health` returns 200. Show a loading splash screen during sidecar startup.
**Warning signs:** "Connection refused" or "Failed to fetch" errors in console on first load. API calls fail on cold start but work after app has been open for a few seconds.

### Pitfall 7: CORS Errors in Development

**What goes wrong:** During `tauri dev`, the frontend runs at `localhost:1420` (Vite dev server). FastAPI rejects requests from this origin.
**Why it happens:** FastAPI's default CORS middleware blocks cross-origin requests. In production (packaged Tauri app), the frontend is served from `tauri://localhost` not a Vite port.
**How to avoid:** In development mode, configure FastAPI's CORSMiddleware with `allow_origins=["http://localhost:1420", "tauri://localhost"]`. In the existing `service/app.py`, add CORS middleware. Do NOT add `allow_origins=["*"]` in production.
**Warning signs:** Browser console shows CORS policy errors when calling the FastAPI API. Only happens in dev, not in packaged build (or vice versa).

### Pitfall 8: Tauri v1 API Used Instead of v2

**What goes wrong:** Community examples, blog posts, and Stack Overflow answers frequently reference Tauri v1 APIs (e.g., `tauri.window.fileDropEnabled` instead of `app.window.dragDropEnabled`; `@tauri-apps/api/tauri` import instead of `@tauri-apps/api`).
**Why it happens:** Tauri v2 was released October 2024; most content predates it.
**How to avoid:** Always check `v2.tauri.app` not `tauri.app` or `v1.tauri.app`. When reading community examples, verify the Tauri version being used.
**Warning signs:** TypeScript type errors on Tauri API imports. Configuration keys not recognized in `tauri.conf.json`.

---

## Code Examples

Verified patterns from official sources:

### Sidecar Spawn (Rust - Tauri v2)

```rust
// Source: https://v2.tauri.app/develop/sidecar/
use tauri_plugin_shell::ShellExt;

let sidecar_command = app.shell().sidecar("podcast-pipeline-sidecar").unwrap();
let (mut rx, mut child) = sidecar_command.spawn().expect("Failed to spawn sidecar");
```

### Sidecar Spawn via JavaScript (Alternative)

```typescript
// Source: https://v2.tauri.app/develop/sidecar/
import { Command } from '@tauri-apps/plugin-shell';

const command = Command.sidecar('binaries/podcast-pipeline-sidecar');
const output = await command.execute();
```

### Native File Drop

```typescript
// Source: https://v2.tauri.app/reference/javascript/api/namespacewebview/
import { getCurrentWebview } from "@tauri-apps/api/webview";

const unlisten = await getCurrentWebview().onDragDropEvent((event) => {
  if (event.payload.type === 'drop') {
    const paths: string[] = event.payload.paths; // Full OS paths
  }
});
```

### WebSocket Plugin

```typescript
// Source: https://v2.tauri.app/plugin/websocket/
import WebSocket from '@tauri-apps/plugin-websocket';

const ws = await WebSocket.connect('ws://127.0.0.1:8787/jobs/abc/ws');
const remove = ws.addListener((msg) => { /* handle event */ });
await ws.disconnect();
```

### Auto-Updater Config

```json
// Source: https://v2.tauri.app/plugin/updater/
// tauri.conf.json
{
  "bundle": {
    "createUpdaterArtifacts": true
  },
  "plugins": {
    "updater": {
      "pubkey": "CONTENT_FROM_PUBLICKEY.PEM",
      "endpoints": [
        "https://github.com/YOUR_ORG/podcast-pipeline-desktop/releases/latest/download/update-{{target}}-{{arch}}.json"
      ]
    }
  }
}
```

### GitHub Actions Cross-Platform Build

```yaml
# Source: https://v2.tauri.app/distribute/pipelines/github/
# tauri-action v0.6.1 (January 2026)
strategy:
  fail-fast: false
  matrix:
    include:
      - platform: 'macos-latest'
        args: '--target aarch64-apple-darwin'
      - platform: 'macos-latest'
        args: '--target x86_64-apple-darwin'
      - platform: 'ubuntu-22.04'
        args: ''
      - platform: 'windows-latest'
        args: ''

steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-node@v4
    with: { node-version: lts/* }
  - uses: dtolnay/rust-toolchain@stable
  - uses: swatinem/rust-cache@v2
  - name: Build Python sidecar
    run: scripts/build-sidecar-${{ matrix.platform }}.sh
  - uses: tauri-apps/tauri-action@v0
    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
    with:
      tagName: v__VERSION__
      releaseName: 'Podcast Pipeline v__VERSION__'
      args: ${{ matrix.args }}
```

**Ubuntu-specific (before tauri-action):**
```yaml
- name: Install Linux dependencies
  run: sudo apt-get install -y libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf
```

### Zustand + TanStack Query Pattern

```typescript
// Source: Community pattern - verified against TanStack Query v5 docs
// stores/uiStore.ts
import { create } from 'zustand';

interface UIStore {
  selectedJobId: string | null;
  setSelectedJob: (id: string | null) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  selectedJobId: null,
  setSelectedJob: (id) => set({ selectedJobId: id }),
}));

// hooks/useJobs.ts
import { useQuery } from '@tanstack/react-query';

export function useJobs() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: () => fetch('http://127.0.0.1:8787/jobs').then(r => r.json()),
    refetchInterval: 5000,  // poll every 5s for job status updates
  });
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tauri v1 allowlist (on/off toggles) | Tauri v2 capabilities + permissions (scoped, granular) | Oct 2024 (Tauri v2 stable) | All permission configs must use v2 format |
| `tauri.window.fileDropEnabled` | `app.window.dragDropEnabled` | Oct 2024 (v2) | Config key renamed; v1 examples are wrong |
| `@tauri-apps/api/tauri` imports | `@tauri-apps/api` flat imports | Oct 2024 (v2) | API surface reorganized; v1 import paths fail |
| Tauri shell built-in | `tauri-plugin-shell` (separate plugin) | Oct 2024 (v2) | Must explicitly install and register the plugin |
| TailwindCSS v3 (tailwind.config.js) | TailwindCSS v4 (@tailwindcss/vite Vite plugin) | Jan 2025 | No config file needed; CSS-native theming |
| Redux for React state | Zustand + TanStack Query | 2023-2024 | Redux considered overkill; Zustand usage 28%→41% |
| Wavesurfer.js v6 (class-based) | Wavesurfer.js v7 (TypeScript, Shadow DOM) | 2023 | Plugin arrays must be memoized in React |
| PyInstaller 5.x | PyInstaller 6.x (6.19 current) | 2024 | Better hooks for ML libraries |

**Deprecated/outdated:**
- PyOxidizer: Effectively abandoned; last meaningful activity 2022-2023. Do not use.
- Tauri v1 for new projects: v2 is stable since Oct 2024; v1 documentation will be deprecated.

---

## Open Questions

1. **PyInstaller --onedir Tauri Integration Mechanics**
   - What we know: --onedir produces a directory, not a single file. Tauri's `externalBin` expects a file path.
   - What's unclear: Exact configuration to point Tauri at the executable inside the dist directory while bundling the entire directory alongside it. Community examples use --onefile despite its downsides.
   - Recommendation: During subtask 10-02, test both modes. If --onefile startup is acceptable (<5 seconds without torch GPU init), use it for simplicity. If torch GPU init makes it unacceptable, investigate the --onedir + Tauri bundle directory inclusion pattern before finalizing.

2. **torch/CUDA Bundle Size for This Project**
   - What we know: CUDA-enabled torch bundles are 2-4 GB. The project uses torch for RIFE GPU features (RTX 5060 Ti, sm_120, CUDA 12.8).
   - What's unclear: Whether RIFE/torch must be included in the sidecar at all. The spec notes "optional: torch/torchvision (for RIFE GPU features)." If the sidecar can detect GPU availability at runtime and import torch lazily, the base bundle could be much smaller (100-300 MB without torch).
   - Recommendation: Design sidecar so torch is imported conditionally (runtime optional dependency). Offer two build modes: `build:sidecar-cpu` (no torch) and `build:sidecar-gpu` (with CUDA torch).

3. **Windows CUDA 12.8 (sm_120) PyInstaller Support**
   - What we know: RTX 5060 Ti uses CUDA compute capability sm_120. ctranslate2 requires CUDA 12 + cuDNN 9. CUDA 12.8 DLLs are large.
   - What's unclear: Whether PyInstaller correctly bundles all CUDA 12.8 runtime DLLs (cublas, cublasLt, cudnn, etc.) for sm_120 targets. CTranslate2 4.4.0 had breaking changes with certain CUDA versions (noted as breaking in Oct 2024).
   - Recommendation: Pin ctranslate2 version in PyInstaller build environment. Test the bundled sidecar on a clean Windows system without CUDA installed (confirms DLLs are self-contained). Use `pipreqs` or `pip-audit` to audit the dep tree before bundling.

4. **Wavesurfer.js Multitrack Status**
   - What we know: Wavesurfer.js v7 lists "Multi-track" under "Experiments" on the examples page. Not GA.
   - What's unclear: Whether the experimental multitrack API is stable enough for production use in subtask 10-06.
   - Recommendation: Evaluate the experimental multitrack plugin during 10-06. If unstable, implement multi-track visualization as multiple independent WaveSurfer instances synchronized via a shared AudioContext and playback offset — this is the documented community pattern for Soundcloud-like multi-track views.

5. **FastAPI CORS for Tauri Dev vs Production**
   - What we know: Dev mode serves from `http://localhost:1420`; production uses `tauri://localhost`. FastAPI needs different CORS origins for each.
   - What's unclear: The existing `service/app.py` does not have CORS middleware configured (inspected above). It will need to be added for Tauri integration.
   - Recommendation: Add CORS middleware to `app.py` in subtask 10-01 with env-var-controlled origins. Default dev: `["http://localhost:1420"]`. Production/packaged: `["tauri://localhost"]`.

---

## Sources

### Primary (HIGH confidence)

- [Tauri v2 Sidecar Official Docs](https://v2.tauri.app/develop/sidecar/) - externalBin config, Rust spawn API, permissions, naming convention
- [Tauri v2 WebSocket Plugin](https://v2.tauri.app/plugin/websocket/) - Installation, connect API, permissions
- [Tauri v2 Webview API](https://v2.tauri.app/reference/javascript/api/namespacewebview/) - onDragDropEvent, DragDropEvent payload structure
- [Tauri v2 Updater Plugin](https://v2.tauri.app/plugin/updater/) - Auto-update config, key generation, endpoint format
- [Tauri GitHub Actions Pipeline](https://v2.tauri.app/distribute/pipelines/github/) - Complete CI/CD matrix workflow
- [tauri-action v0.6.1](https://github.com/tauri-apps/tauri-action) - Latest action version, matrix strategy

### Secondary (MEDIUM confidence)

- [Building Production-Ready Desktop LLM Apps: Tauri, FastAPI, PyInstaller](https://aiechoes.substack.com/p/building-production-ready-desktop) - Production PyInstaller spec pattern, UTF-8 fix, Tauri sidecar config, bundle metrics
- [example-tauri-v2-python-server-sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar) - process.kill() limitation for PyInstaller one-file, stdin/stdout shutdown pattern
- [tauri-fastapi-full-stack-template](https://github.com/fudanglp/tauri-fastapi-full-stack-template) - React + TanStack Query + shadcn/ui + Tauri architecture; HTTP REST for primary comms
- [TailwindCSS v4 Vite Guide](https://tailwindcss.com/docs/guides/vite) - @tailwindcss/vite plugin, no config file needed
- [Tauri 2.0 Stable Release Blog](https://v2.tauri.app/blog/tauri-20/) - Release date (Oct 2, 2024), v2 API changes
- [Tauri Core Ecosystem Releases](https://v2.tauri.app/release/) - Version 2.10.2 confirmed as latest stable

### Tertiary (LOW confidence - needs validation)

- Community WebSearch findings about PyInstaller CUDA bundle sizes (2-4 GB claim) - multiple sources agree but no 2025 benchmarks for this exact dep set
- Wavesurfer.js multitrack "experiments" status - confirmed via examples page listing, but stability for production use is unverified
- ctranslate2 + PyInstaller Windows DLL collection pattern - based on similar ML library patterns (llama-cpp-python), not faster-whisper specific. **Must validate** during subtask 10-02.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Tauri v2 APIs verified against official v2.tauri.app docs; React+Vite+Tailwind v4 pattern verified against official guides and multiple community templates
- Architecture (sidecar spawn/shutdown): MEDIUM-HIGH — Tauri v2 official docs + production community guide verified; one-file PID limitation confirmed by official example repo
- PyInstaller ML bundling: MEDIUM — General pattern verified; faster-whisper/ctranslate2 specific DLL collection needs empirical validation during implementation
- Distribution CI/CD: HIGH — Official tauri-action@v0.6.1 workflow verified against official docs

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (30 days; Tauri releases frequently but v2.x APIs are stable; PyInstaller ML ecosystem changes slowly)

---

---

## Future MCP Server Tools Research

**Researched:** 2026-02-25
**Domain:** FFmpeg dynamic crop, video overlay filter_complex, platform upload APIs (YouTube, Spotify, TikTok)
**Confidence:** MEDIUM (FFmpeg filter syntax verified against official docs; platform API flows verified against official developer portals; OpenCV capabilities verified against installed package 4.13.0)

### Summary

This section covers implementation specifications for three tools to be added to `src/podcast_pipeline/mcp/ffmpeg_server.py` and `src/podcast_pipeline/utils/ffmpeg_toolkit.py`. All three follow the existing pattern: typed Pydantic request model, FFmpeg command construction (or API call), result model returned as JSON-safe dict via `_result_dict()`.

**Tool 1 (`smart_crop_subject`):** OpenCV `FaceDetectorYN` (YuNet, already installed as `opencv-python-headless 4.13.0`) detects face bounding boxes frame-by-frame. Smoothed crop coordinates are written to an FFmpeg `sendcmd` file. FFmpeg then executes a single pass using `sendcmd=f={file}` to drive a named `crop@cam` filter with dynamically updating x/y values. This is the correct bridging pattern — FFmpeg cannot read CSV natively but can consume a sendcmd file that was generated by any external tool. OpenCV does NOT need to decode/encode video frames directly; FFmpeg handles all I/O.

**Tool 2 (`overlay_video`):** Uses FFmpeg `filter_complex` with the `overlay` filter (for video) and `amix` (for audio). The B-roll overlay approach uses `enable='between(t,START,END)'` to constrain when the overlay appears. For Picture-in-Picture, the secondary stream is scaled and positioned in a corner. Audio has two modes: main-only (single `-map 0:a`) or mixed (`amix=inputs=2:weights=1 0.3`).

**Tool 3 (`upload_to_platform`):** YouTube uses the official `google-api-python-client` + `google-auth-oauthlib` with a resumable upload to `videos.insert`. Spotify has no upload API; the standard approach is RSS feed generation via `feedgen`, which Spotify ingests automatically. TikTok has an official Content Posting API (`video.publish` scope) that supports direct file upload. For platforms without APIs (Instagram Direct), the fallback is Playwright browser automation.

**Primary recommendation:** Implement tools in this order: `overlay_video` first (pure FFmpeg, no new dependencies), then `smart_crop_subject` (uses installed OpenCV, needs YuNet model download at first run), then `upload_to_platform` (requires new library installs and OAuth setup).

---

## Standard Stack (MCP Tools)

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| opencv-python-headless | 4.13.0 (INSTALLED) | Face detection and frame analysis | Already in `gpu` extra; `FaceDetectorYN` and `TrackerMIL_create` confirmed available |
| google-api-python-client | 2.x | YouTube Data API v3 upload | Official Google client; required by Google Developer docs for `videos.insert` |
| google-auth-oauthlib | 1.x | OAuth2 flow for YouTube | `InstalledAppFlow` for desktop/headless credential management; tokens storable as JSON |
| google-auth | 2.48.0 (INSTALLED) | OAuth2 credential management | Already installed; provides `Credentials` refresh logic |
| feedgen | 0.9.0+ | RSS feed generation for Spotify | Standard library for podcast RSS with Apple Podcasts + Spotify spec support |
| playwright | 1.x | Browser automation fallback | Required for TikTok (if not using API) or Instagram; headless Chromium-based |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | already installed (scipy dep) | Smoothing face bounding box trajectories | Required for Gaussian/exponential smoothing of crop x/y coordinates |
| httpx | 0.28.0 (INSTALLED) | TikTok Content Posting API HTTP calls | Already in core deps; use for direct TikTok API calls (no official Python SDK) |

### New Dependencies Required

```bash
# For YouTube upload
uv add google-api-python-client google-auth-oauthlib

# For Spotify RSS feed generation
uv add feedgen

# For TikTok/Instagram browser automation fallback
uv add playwright
uv run playwright install chromium
```

**Note:** `opencv-python-headless 4.13.0` is already installed under the `gpu` extra. The `smart_crop_subject` tool must guard its import with a try/except and return a clear error if the `gpu` extra is not installed.

---

## Architecture Patterns (MCP Tools)

### Pattern 10: smart_crop_subject — Two-Pass Architecture

**What:** Pass 1 (analysis): OpenCV reads video frames, detects faces with YuNet, writes smoothed crop coordinates to a sendcmd file. Pass 2 (render): FFmpeg reads the sendcmd file and performs the actual crop+encode in a single pass.
**When to use:** Converting 16:9 landscape footage to 9:16 vertical TikTok/Short format with dynamic speaker tracking.

**Why two passes instead of OpenCV writing frames directly:**
- FFmpeg handles codec, bitrate, hardware encoding, and all output format concerns. Piping decoded frames through OpenCV and back into FFmpeg is complex, slow, and loses hardware acceleration.
- The sendcmd approach delegates all encoding to FFmpeg while OpenCV provides only the coordinate time-series.
- Verified: FFmpeg's `crop` filter supports `x` and `y` commands via `sendcmd`. The crop filter explicitly documents: "The command accepts the same syntax of the corresponding option."

**Face Detection Tool:** Use `cv2.FaceDetectorYN` (YuNet). Confirmed available in installed `opencv-python-headless 4.13.0`. Requires downloading `face_detection_yunet_2023mar.onnx` from the OpenCV model zoo at first run.

**Tracker for between-detection frames:** Use `cv2.TrackerMIL_create()`. Confirmed available in 4.13.0. No model file required. Initialize with the face bounding box from YuNet, then update each frame. Re-detect with YuNet every N frames to correct drift.

**Smoothing algorithm:** Exponential moving average (EMA) on the crop center x/y coordinates. EMA prevents sudden jumps when a face moves. Deadzone threshold (e.g., 20px) prevents jitter from micro-movements.

**Output crop dimensions for 9:16:** Input is 16:9 (e.g., 1920x1080). Output crop width = `1080 * 9/16 = 607px`. Output height = `1080px`. The crop window slides horizontally only (y is fixed at 0 for podcast use case where speakers are at full height).

**sendcmd file format** (verified against FFmpeg filter docs):
```
# Generated sendcmd file — one entry per second or per keyframe
# Format: START[-END] [enter] FILTER_NAME COMMAND VALUE;
0.000 crop@cam x 656;
0.033 crop@cam x 658;
0.067 crop@cam x 659;
...
```

**FFmpeg command for pass 2:**
```bash
# Source: FFmpeg filters docs (https://ffmpeg.org/ffmpeg-filters.html) + sendcmd filter docs
ffmpeg -i input_16x9.mp4 \
  -filter_complex "
    [0:v]crop@cam=w=607:h=1080:x=656:y=0,
    sendcmd=f=/tmp/crop_commands.txt[v_out]
  " \
  -map "[v_out]" \
  -map 0:a \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac \
  output_9x16.mp4
```

**Important:** The `sendcmd` filter must appear AFTER the `crop@cam` filter in the chain — sendcmd sends commands TO crop, it does not replace it.

**Performance profile:**
- YuNet detection: ~1.6ms per frame at 320x320 on modern i7 CPU (~30-50 FPS detection throughput). For 30 FPS video, detection is real-time on CPU.
- Pass 1 (OpenCV analysis only, no re-encode): Processes 1080p at approximately 5-15x real-time speed on CPU (OpenCV reads frames via VideoCapture without decoding to display).
- Pass 2 (FFmpeg encode with sendcmd): Normal FFmpeg encode speed (hardware-accelerated where available).
- Total overhead vs. static crop: Approximately 10-30 seconds of pre-processing for a 60-minute video.

### Pattern 11: overlay_video — filter_complex Graphs

**What:** FFmpeg `filter_complex` with timed overlay using `enable='between(t,START,END)'`.
**When to use:** B-roll cutaway, Picture-in-Picture remote guest.

**B-roll cutaway (full-frame replacement, timed):**
```bash
# Source: FFmpeg official docs overlay filter + community-verified pattern
# Video B overlays Video A for a window of time. Audio is from A (primary).
ffmpeg -i main_video.mp4 -i broll_video.mp4 \
  -filter_complex "
    [1:v]setpts=PTS-STARTPTS+{start_s}/TB[broll_delayed];
    [0:v][broll_delayed]overlay=enable='between(t,{start_s},{end_s})':x=0:y=0[v_out]
  " \
  -map "[v_out]" \
  -map 0:a \
  -c:v libx264 -preset fast -crf 23 \
  -c:a copy \
  output.mp4
```

**Key detail:** `setpts=PTS-STARTPTS+{start_s}/TB` delays B-roll so it starts playing at `start_s` in the output timeline. Without this, B-roll would show frame 0 of B at time 0 of A, making the overlay always show the beginning of B-roll content regardless of where it's placed.

**Picture-in-Picture (PiP), corner position with audio mix:**
```bash
# Source: FFmpeg official docs overlay + amix filters
ffmpeg -i main_video.mp4 -i guest_video.mp4 \
  -filter_complex "
    [1:v]scale=iw/4:ih/4[pip_scaled];
    [0:v][pip_scaled]overlay=x=main_w-overlay_w-20:y=20[v_out];
    [0:a][1:a]amix=inputs=2:weights=1 0.3[a_out]
  " \
  -map "[v_out]" \
  -map "[a_out]" \
  -c:v libx264 -preset fast \
  output_pip.mp4
```

**Audio modes for overlay_video:**
- `main_only`: `-map 0:a -c:a copy` — take audio from input 0 entirely; simplest, fastest
- `mixed`: `amix=inputs=2:weights=1 {secondary_vol}` — blend both audio streams (weights: `1` = 100% main, `0.3` = 30% secondary)
- `replace`: `-map 1:a` — take audio from B-roll/secondary only (uncommon)

**Critical:** When B-roll has its own audio that should duck under main audio during PiP, use `amix` with `weights=1 0.15` (85% reduction of secondary audio) rather than silence.

### Pattern 12: upload_to_platform — Per-Platform Architecture

**YouTube Data API v3 (HIGH confidence — official docs verified)**

Authentication flow for installed/desktop app:
1. Create OAuth2 client credentials in Google Cloud Console (Desktop app type)
2. Download `client_secrets.json`
3. First run: `InstalledAppFlow.from_client_secrets_file()` opens browser for user consent
4. Store `credentials.json` (contains refresh token) after first authorization
5. Subsequent runs: load from `credentials.json` and auto-refresh with `google.auth.transport.requests.Request()`

Required scope: `https://www.googleapis.com/auth/youtube.upload`

Upload endpoint: `POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`

Resumable upload (for large video files — mandatory for files >5MB):
- Send initial POST with video metadata JSON + `X-Upload-Content-Length` header
- Receive `Location` header with session URI
- PUT chunks to session URI with `Content-Range` header
- Chunks must be multiples of 256KB
- On 308 response: resume from position in `Range` response header
- On 201 response: upload complete

Quota: `videos.insert` costs 1,600 units. Default daily quota is 10,000 units. This means only 6 video uploads per day on the free quota. **Apply for quota increase** in Google Cloud Console for production use.

**Spotify (VERIFIED — no upload API exists)**

Spotify does NOT have a public API for uploading podcast episodes. This is confirmed by the official Spotify developer community and has not changed as of 2026. The standard integration path is RSS:

1. Host the audio file (MP3/AAC) on any web-accessible storage (S3, GCS, R2, self-hosted)
2. Generate/update a podcast RSS feed using `feedgen` library
3. The RSS feed was previously submitted to Spotify for Podcasters (podcasters.spotify.com) — Spotify polls it automatically
4. New episodes appear on Spotify within minutes to hours of the RSS feed update

The `upload_to_platform` tool for Spotify should: upload the audio file to configured storage, update the RSS feed XML, and push the updated feed to its hosting location. Spotify ingests automatically.

**TikTok Content Posting API (MEDIUM confidence — official docs verified, but requires app audit)**

TikTok has an official Content Posting API at `https://open.tiktokapis.com/v2/`:
- Scope required: `video.publish`
- App must be registered at developers.tiktok.com
- Before audit: content restricted to `SELF_ONLY` visibility; maximum 5 uploads per 24h
- After audit: public posting enabled

Upload flow (File Upload method):
1. `POST /v2/post/publish/creator_info/query/` — get creator info and posting constraints
2. `POST /v2/post/publish/video/init/` — with video_size_bytes, chunk_size, total_chunk_count, title, privacy_level
3. `PUT {upload_url}` — upload video file in chunks (URL valid for 1 hour)
4. `POST /v2/post/publish/status/fetch/` — poll until `PUBLISH_COMPLETE`

OAuth: Standard OAuth 2.0 authorization code flow. Access token expires in 24h but can be refreshed.

**Instagram / Platforms Without Upload API (Playwright fallback)**

For platforms with no upload API or where API access is not feasible, use `playwright` for browser automation:
- Playwright is available as a Python library (`pip install playwright`)
- Use `playwright install chromium` for the browser binary
- Authentication: persist browser storage state (cookies + localStorage) after first manual login via `context.storage_state(path="session.json")`; subsequent runs load the saved state
- Headless mode: `browser = await playwright.chromium.launch(headless=True)`
- Anti-bot detection: Playwright is detectable by sophisticated platforms; use `playwright-stealth` plugin or run non-headless for sensitive platforms

**Architecture for upload_to_platform MCP tool:**

The tool accepts a `platform` parameter and dispatches to the appropriate uploader class. Each uploader is a separate module under `src/podcast_pipeline/uploaders/`:
```
src/podcast_pipeline/uploaders/
├── __init__.py
├── base.py          # PlatformUploader protocol
├── youtube.py       # YouTubeUploader (google-api-python-client)
├── spotify_rss.py   # SpotifyRSSUploader (feedgen + storage upload)
├── tiktok.py        # TikTokUploader (httpx REST calls)
└── playwright_base.py  # PlaywrightUploader base for browser-based platforms
```

---

## Don't Hand-Roll (MCP Tools)

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Face detection algorithm | Custom Haar cascade or DNN wrapper | `cv2.FaceDetectorYN` (YuNet, already installed) | YuNet achieves 30-50 FPS on CPU; 75k parameters; millisecond latency; bundled with OpenCV |
| Object tracker between detections | Custom optical flow tracker | `cv2.TrackerMIL_create()` (no model file needed) | MIL tracker is model-free, CPU-only, and available in installed OpenCV 4.13.0 |
| RSS feed XML generation | Custom XML string assembly | `feedgen` library | Handles all podcast namespace prefixes, enclosure tags, iTunes/Spotify extensions, XML escaping |
| YouTube upload chunking + retry | Custom multipart HTTP uploader | `google-api-python-client` + `MediaFileUpload(resumable=True)` | Handles 308 Resume Incomplete, exponential backoff, chunk sizing automatically |
| OAuth2 browser flow + token storage | Custom OAuth2 implementation | `google-auth-oauthlib` + `InstalledAppFlow` | Handles PKCE, token refresh, credential JSON serialization |
| TikTok API HTTP client | Custom requests wrapper | `httpx` (already installed) | Already a core dependency; handles chunked PUT uploads, timeout, retries |
| Platform browser automation | Selenium or custom WebDriver | `playwright` | Playwright is faster, more reliable, auto-waits for network idle, better cookie persistence |
| Smooth pan interpolation | Custom linear interpolation | numpy EMA (exponential moving average) | `alpha * new_val + (1 - alpha) * prev_val` is 1 line; numpy already installed as scipy transitive dep |

**Key insight:** The critical "don't hand-roll" for `smart_crop_subject` is the face detection itself. Haar cascades (the built-in `haarcascade_frontalface_default.xml`) are significantly less accurate and slower than YuNet for this use case. YuNet detects side-facing and partially occluded faces, which Haar cascades miss — critical for two-speaker podcast footage where one speaker may turn their head.

---

## Common Pitfalls (MCP Tools)

### Pitfall 9: sendcmd Crop Filter Ordering

**What goes wrong:** `sendcmd` is placed BEFORE `crop@cam` in the filtergraph chain. The sendcmd filter has no target to send commands to, and crop ignores runtime updates entirely.
**Why it happens:** Confusion about data flow direction. `sendcmd` is a SOURCE of commands, not a filter transformation — it must appear downstream of the filter it controls in the chain, or in a separate filter node connected to the same filtergraph.
**How to avoid:** Always place `sendcmd` AFTER the filter it controls: `crop@cam=..., sendcmd=f={file}` or use the `[0:v]sendcmd=f={file}[cmd]; [0:v]crop@cam[v]` pattern with proper input routing.
**Warning signs:** FFmpeg runs without error but crop position never changes. Output video is a static crop at the initial x/y values.

### Pitfall 10: YuNet Model File Not Bundled

**What goes wrong:** `smart_crop_subject` is called on a machine that does not have `face_detection_yunet_2023mar.onnx` present at the expected path. `cv2.FaceDetectorYN.create()` raises a cryptic OpenCV error about the model file.
**Why it happens:** YuNet requires a downloaded ONNX model file (not bundled with `opencv-python-headless`). The model must be downloaded separately from the opencv_zoo repository.
**How to avoid:** In the toolkit function, check for the model file at a configurable path (default: `~/.cache/podcast-pipeline/models/face_detection_yunet_2023mar.onnx`). If absent, download it automatically from `https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx` on first run. Log the download clearly.
**Warning signs:** `cv2.error: (-215:Assertion failed)` or `Error reading model file`. File not found at the model path.

### Pitfall 11: setpts Missing in B-roll Overlay

**What goes wrong:** B-roll is overlaid but always shows its first frame (or first few seconds) at the wrong point in the main video. The B-roll does not appear at the specified `start_s` position in the output.
**Why it happens:** Without `setpts=PTS-STARTPTS+{start_s}/TB`, the B-roll's timestamps are relative to its own start (0.0). FFmpeg merges frames by timestamp, so B-roll frame at t=0 overlays main video at t=0, regardless of the `enable` expression.
**How to avoid:** Always apply `[1:v]setpts=PTS-STARTPTS+{start_s}/TB[delayed_broll]` before the overlay filter when B-roll has a specific placement time.
**Warning signs:** B-roll appears at the correct enable/disable time window but shows the wrong content (first few seconds of B-roll instead of the middle).

### Pitfall 12: YouTube Quota Exhaustion

**What goes wrong:** The `upload_to_platform` tool succeeds for a few uploads, then starts receiving 403 quota exceeded errors. All YouTube API operations fail until the next day's quota reset.
**Why it happens:** `videos.insert` costs 1,600 units. The default quota is 10,000 units/day. After 6 successful video uploads in a day, the quota is exhausted. Other API calls also consume units.
**How to avoid:** Cache the quota cost in tool documentation. Implement pre-upload quota checking via `youtube.channels().list()` if a quota monitoring endpoint is available. Instruct users to apply for quota increase in Google Cloud Console. Add a per-day upload counter in the MCP tool's response metadata.
**Warning signs:** HTTP 403 with `quotaExceeded` in the error body. First uploads succeed, then all fail.

### Pitfall 13: TikTok Unaudited Client Restrictions

**What goes wrong:** TikTok upload appears successful (201 response) but the video is only visible to the authenticating account itself (`SELF_ONLY` privacy). The video never appears publicly.
**Why it happens:** TikTok's Content Posting API enforces private-only mode for all clients that have not completed the audit process. Even if `privacy_level=PUBLIC_TO_EVERYONE` is requested, it is silently overridden to `SELF_ONLY` for unaudited apps.
**How to avoid:** Document this limitation clearly in the MCP tool's docstring. After completing the basic integration and testing with self-only content, submit the app for TikTok audit at developers.tiktok.com to lift the restriction. Rate limit: 5 uploads per 24h per user for unaudited apps.
**Warning signs:** Upload returns 200/201 but the video is invisible to other users. Status endpoint shows `PUBLISH_COMPLETE` but privacy is `SELF_ONLY` even when `PUBLIC_TO_EVERYONE` was requested.

### Pitfall 14: Spotify RSS Feed URL Stability

**What goes wrong:** The Spotify RSS feed connection is broken when the hosting URL for the RSS XML file changes (e.g., migration from one S3 bucket to another). Episodes stop appearing on Spotify.
**Why it happens:** Spotify caches the original RSS feed URL submitted during initial setup. Changing the URL requires a feed redirect update in Spotify for Podcasters settings, which takes several days to propagate.
**How to avoid:** Use a stable URL for the RSS feed (custom domain with redirect, not a bucket URL directly). Store the feed URL in project configuration. Never change it without updating Spotify for Podcasters.
**Warning signs:** New episodes are uploaded to storage and the RSS XML is updated, but episodes do not appear on Spotify. The Spotify for Podcasters dashboard shows the old feed URL.

### Pitfall 15: OpenCV VideoCapture Memory for Long Videos

**What goes wrong:** Processing a 2-hour podcast video with OpenCV `VideoCapture` consumes multiple GB of memory or is extremely slow because OpenCV attempts to seek to specific frame numbers rather than reading sequentially.
**Why it happens:** `cv2.VideoCapture.set(cv2.CAP_PROP_POS_FRAMES, N)` for large N performs a slow seek. Sequential `cap.read()` in a loop is the correct pattern for face detection across all frames.
**How to avoid:** Always read frames sequentially. For memory: process 1 frame at a time, never accumulate raw frames in a list. For skipping frames (e.g., detect every 5th frame): call `cap.read()` to advance but discard the frame, rather than `set(CAP_PROP_POS_FRAMES)`. Write smoothed crop coordinates to the sendcmd file incrementally.
**Warning signs:** Memory usage grows linearly with video duration. Analysis pass takes 10+ minutes for a 1-hour video.

---

## Code Examples (MCP Tools)

Verified patterns from official sources and installed package inspection:

### smart_crop_subject: Pass 1 — YuNet Face Detection + EMA Smoothing

```python
# Source: OpenCV official docs (docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html)
# + transloadit.com YuNet tutorial (verified)
# Installed package: opencv-python-headless 4.13.0 (confirmed FaceDetectorYN available)

import cv2
import numpy as np
from pathlib import Path

def detect_and_smooth_face_centers(
    video_path: Path,
    model_path: Path,
    output_crop_width: int = 607,   # 1080 * 9/16 for 9:16 from 1080p source
    output_crop_height: int = 1080,
    detection_interval_frames: int = 5,  # Re-detect every 5 frames; track in between
    ema_alpha: float = 0.15,             # Lower = smoother but laggier
    deadzone_px: int = 20,              # Ignore movements smaller than this
) -> list[tuple[float, int]]:           # [(timestamp_s, crop_x), ...]
    """Pass 1: analyse video, return per-frame smoothed crop x positions."""
    detector = cv2.FaceDetectorYN.create(
        str(model_path),
        "",
        (320, 320),
        score_threshold=0.9,
        nms_threshold=0.3,
        top_k=5000,
    )
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    # Maximum x range for the crop window
    max_crop_x = frame_w - output_crop_width

    # Initialize EMA at center
    smoothed_x = float(frame_w // 2 - output_crop_width // 2)
    tracker = cv2.TrackerMIL_create()
    tracker_initialized = False
    results: list[tuple[float, int]] = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp_s = frame_idx / fps

        if frame_idx % detection_interval_frames == 0 or not tracker_initialized:
            # YuNet detection pass
            detector.setInputSize((frame.shape[1], frame.shape[0]))
            _, faces = detector.detect(frame)
            if faces is not None and len(faces) > 0:
                # Use the highest-confidence face (first result after NMS)
                x, y, w, h = faces[0][0:4].astype(int)
                face_center_x = x + w // 2
                # Re-init tracker on the detected face
                tracker = cv2.TrackerMIL_create()
                tracker.init(frame, (x, y, w, h))
                tracker_initialized = True
                # Desired crop: center the face horizontally
                desired_x = float(face_center_x - output_crop_width // 2)
                desired_x = max(0.0, min(float(max_crop_x), desired_x))
                # EMA smoothing with deadzone
                delta = desired_x - smoothed_x
                if abs(delta) > deadzone_px:
                    smoothed_x = ema_alpha * desired_x + (1 - ema_alpha) * smoothed_x
        elif tracker_initialized:
            # Between detections: use tracker to update bounding box
            success, bbox = tracker.update(frame)
            if success:
                tx, ty, tw, th = [int(v) for v in bbox]
                face_center_x = tx + tw // 2
                desired_x = float(face_center_x - output_crop_width // 2)
                desired_x = max(0.0, min(float(max_crop_x), desired_x))
                delta = desired_x - smoothed_x
                if abs(delta) > deadzone_px:
                    smoothed_x = ema_alpha * desired_x + (1 - ema_alpha) * smoothed_x

        results.append((timestamp_s, int(smoothed_x)))
        frame_idx += 1

    cap.release()
    return results


def write_sendcmd_file(
    crop_positions: list[tuple[float, int]],
    output_path: Path,
) -> None:
    """Write FFmpeg sendcmd file from per-frame crop x positions."""
    # Source: FFmpeg sendcmd filter docs (ayosec.github.io/ffmpeg-filters-docs/7.0/)
    # Format: START crop@cam x VALUE;
    with output_path.open("w") as f:
        for timestamp_s, crop_x in crop_positions:
            f.write(f"{timestamp_s:.3f} crop@cam x {crop_x};\n")
```

### smart_crop_subject: Pass 2 — FFmpeg sendcmd Render

```python
# Source: FFmpeg filter_complex docs + sendcmd filter docs
# Verified: crop filter supports 'x' command via sendcmd (crop.html #commands)

def build_smart_crop_ffmpeg_args(
    input_path: Path,
    output_path: Path,
    sendcmd_path: Path,
    crop_width: int,
    crop_height: int,
    initial_x: int,
    timeout: int,
) -> list[str]:
    """Build FFmpeg args for the smart crop render pass."""
    return [
        "-i", str(input_path),
        "-vf", (
            f"crop@cam=w={crop_width}:h={crop_height}:x={initial_x}:y=0,"
            f"sendcmd=f={sendcmd_path}"
        ),
        "-map", "0:v",
        "-map", "0:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-y",
        str(output_path),
    ]
```

### overlay_video: B-Roll filter_complex

```python
# Source: FFmpeg overlay filter docs + dev.to/oskarahl verified community pattern
# setpts delay pattern confirmed correct for B-roll placement

def build_broll_overlay_args(
    main_path: Path,
    broll_path: Path,
    output_path: Path,
    start_s: float,
    end_s: float,
    audio_mode: str = "main_only",  # "main_only" | "mixed" | "replace"
    secondary_audio_volume: float = 0.3,
    timeout: int = 3600,
) -> list[str]:
    """Build FFmpeg args for B-roll overlay."""
    # setpts delay so B-roll frame 0 aligns with start_s in the output
    filter_graph = (
        f"[1:v]setpts=PTS-STARTPTS+{start_s}/TB[broll_delayed];"
        f"[0:v][broll_delayed]overlay=enable='between(t,{start_s},{end_s})':x=0:y=0[v_out]"
    )
    args = ["-i", str(main_path), "-i", str(broll_path),
            "-filter_complex", filter_graph,
            "-map", "[v_out]"]

    if audio_mode == "main_only":
        args += ["-map", "0:a", "-c:a", "copy"]
    elif audio_mode == "mixed":
        # Modify filter_graph to include amix — requires rebuilding
        # (simplified here; actual impl amends filter_graph string)
        args += ["-filter_complex",
                 filter_graph.rstrip("'") + (
                     f";[0:a][1:a]amix=inputs=2:"
                     f"weights=1 {secondary_audio_volume}[a_out]"
                 ),
                 "-map", "[a_out]"]
    elif audio_mode == "replace":
        args += ["-map", "1:a", "-c:a", "aac"]

    args += ["-c:v", "libx264", "-preset", "fast", "-y", str(output_path)]
    return args
```

### overlay_video: Picture-in-Picture

```python
# Source: FFmpeg overlay + scale filter docs; oodlestechnologies.com PiP blog (verified)

def build_pip_overlay_args(
    main_path: Path,
    pip_path: Path,
    output_path: Path,
    pip_scale: float = 0.25,       # PiP is 25% of main video width
    position: str = "top_right",   # "top_right" | "top_left" | "bottom_right" | "bottom_left"
    margin_px: int = 20,
    audio_mode: str = "mixed",
    secondary_audio_volume: float = 0.3,
) -> list[str]:
    """Build FFmpeg args for Picture-in-Picture overlay."""
    # Position expressions using FFmpeg overlay filter variables
    positions = {
        "top_right":    f"main_w-overlay_w-{margin_px}:{margin_px}",
        "top_left":     f"{margin_px}:{margin_px}",
        "bottom_right": f"main_w-overlay_w-{margin_px}:main_h-overlay_h-{margin_px}",
        "bottom_left":  f"{margin_px}:main_h-overlay_h-{margin_px}",
    }
    pos_expr = positions[position]
    scale_filter = f"scale=iw*{pip_scale}:ih*{pip_scale}"

    filter_complex = (
        f"[1:v]{scale_filter}[pip_scaled];"
        f"[0:v][pip_scaled]overlay={pos_expr}[v_out];"
        f"[0:a][1:a]amix=inputs=2:weights=1 {secondary_audio_volume}[a_out]"
    )
    return [
        "-i", str(main_path),
        "-i", str(pip_path),
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-c:v", "libx264", "-preset", "fast",
        "-y", str(output_path),
    ]
```

### upload_to_platform: YouTube OAuth2 + Resumable Upload

```python
# Source: developers.google.com/youtube/v3/guides/uploading_a_video (official)
# + googleapis.github.io/google-api-python-client/docs/oauth-installed.html (official)
# Requires: google-api-python-client, google-auth-oauthlib (not yet in pyproject.toml)

from pathlib import Path
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_youtube_credentials(
    client_secrets_path: Path,
    token_path: Path,
) -> Credentials:
    """Load stored credentials or run OAuth2 browser flow on first use."""
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # First run: opens browser for user consent
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_path), YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Persist credentials for next run
        token_path.write_text(creds.to_json())
    return creds


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    privacy_status: str = "private",  # "private" | "unlisted" | "public"
    category_id: str = "22",           # 22 = People & Blogs
    client_secrets_path: Path = Path("client_secrets.json"),
    token_path: Path = Path("~/.cache/podcast-pipeline/youtube_token.json"),
) -> dict:
    """Upload a video to YouTube using resumable upload. Returns video ID and URL."""
    creds = get_youtube_credentials(client_secrets_path, token_path.expanduser())
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }

    # chunksize=-1 sends the entire file in one request (simpler for local files)
    # Use a positive chunksize (multiple of 256KB) for very large files or slow networks
    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )

    response = None
    while response is None:
        status, response = insert_request.next_chunk()

    video_id = response["id"]
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "privacy_status": privacy_status,
    }
```

### upload_to_platform: Spotify RSS Feed Update

```python
# Source: feedgen PyPI (pypi.org/project/feedgen/) + Spotify RSS support confirmation
# Spotify has no upload API — RSS is the only integration path (verified 2026-02-25)

from feedgen.feed import FeedGenerator
from pathlib import Path
from datetime import datetime, timezone


def update_podcast_rss_feed(
    feed_path: Path,
    podcast_title: str,
    podcast_description: str,
    podcast_link: str,         # https://yourpodcast.com
    new_episode_title: str,
    new_episode_description: str,
    audio_url: str,            # https://storage.example.com/episode.mp3
    audio_length_bytes: int,
    audio_duration_s: int,
    episode_number: int | None = None,
) -> None:
    """Append a new episode to the podcast RSS feed XML file.

    After calling this, push the updated feed_path to its hosting location.
    Spotify will pick up the new episode automatically (typically within 1 hour).
    """
    fg = FeedGenerator()
    fg.load_extension("podcast")

    # Feed-level metadata
    fg.id(podcast_link)
    fg.title(podcast_title)
    fg.description(podcast_description)
    fg.link(href=podcast_link, rel="alternate")
    fg.language("en")

    # New episode entry
    fe = fg.add_entry()
    fe.id(audio_url)  # GUID must be unique and stable
    fe.title(new_episode_title)
    fe.description(new_episode_description)
    fe.published(datetime.now(tz=timezone.utc))
    fe.enclosure(audio_url, str(audio_length_bytes), "audio/mpeg")
    fe.podcast.itunes_duration(str(audio_duration_s))
    if episode_number:
        fe.podcast.itunes_episode(str(episode_number))

    fg.rss_file(str(feed_path), pretty=True)
```

### upload_to_platform: TikTok File Upload

```python
# Source: developers.tiktok.com/doc/content-posting-api-reference-upload-video (official)
# + developers.tiktok.com/doc/content-posting-api-get-started (official)
# Uses httpx (already in core deps at 0.28.0)
# Requires user access token with video.publish scope

import httpx
from pathlib import Path

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
TIKTOK_UPLOAD_BASE = "https://open-upload.tiktokapis.com"


def upload_to_tiktok(
    video_path: Path,
    title: str,
    access_token: str,
    privacy_level: str = "SELF_ONLY",  # "SELF_ONLY" until audit; then "PUBLIC_TO_EVERYONE"
) -> dict:
    """Upload a video to TikTok via Content Posting API.

    WARNING: Until the TikTok app passes their audit process, all content
    will be forced to SELF_ONLY regardless of the privacy_level parameter.
    Rate limit: 6 requests per minute per access_token.
    Unaudited limit: 5 uploads per 24 hours per user.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    video_size = video_path.stat().st_size
    chunk_size = min(10 * 1024 * 1024, video_size)  # 10MB chunks max

    # Step 1: Initialize upload session
    init_resp = httpx.post(
        f"{TIKTOK_API_BASE}/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": (video_size + chunk_size - 1) // chunk_size,
            },
        },
        timeout=30.0,
    )
    init_resp.raise_for_status()
    data = init_resp.json()["data"]
    publish_id = data["publish_id"]
    upload_url = data["upload_url"]

    # Step 2: Upload file chunks via PUT
    with video_path.open("rb") as f:
        chunk_index = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            start = chunk_index * chunk_size
            end = start + len(chunk) - 1
            httpx.put(
                upload_url,
                content=chunk,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{video_size}",
                    "Content-Length": str(len(chunk)),
                    "Content-Type": "video/mp4",
                },
                timeout=300.0,
            ).raise_for_status()
            chunk_index += 1

    # Step 3: Return publish_id for status polling
    return {"publish_id": publish_id, "status": "PROCESSING"}
```

---

## State of the Art (MCP Tools)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Haar cascade face detection | YuNet (FaceDetectorYN) via OpenCV DNN module | OpenCV 4.5.4 (2021), stable in 4.8+ | YuNet handles profile faces and partial occlusion; Haar cascades miss ~40% of faces in podcast footage |
| opencv-contrib TrackerCSRT | cv2.TrackerMIL_create() (base OpenCV) | OpenCV 4.5+ (base module reorganization) | TrackerCSRT moved out of base; TrackerMIL is the no-model-file option in base OpenCV |
| oauth2client (deprecated) | google-auth + google-auth-oauthlib | 2019 (Google deprecated oauth2client) | All Google developer docs now use google-auth; oauth2client raises deprecation warnings |
| YouTube simple upload | YouTube resumable upload (uploadType=resumable) | 2015, standard since | Required for files >5MB; handles network interruption; exponential backoff built in |
| Manual RSS XML editing | feedgen library | N/A (RSS still the standard) | feedgen handles namespace declarations, escaping, validation, iTunes/Spotify extensions |
| TikTok Selenium automation | TikTok Content Posting API (official) | 2022 (API launched) | Official API is more reliable; Selenium/Playwright still needed for unaudited use cases |

**Deprecated/outdated for MCP tools:**
- `oauth2client`: Deprecated by Google in 2019. All existing code using it should be migrated to `google-auth`.
- Haar cascade (`haarcascade_frontalface_default.xml`) for podcast face detection: Accurate only for frontal faces. YuNet is superior for all use cases involving real video footage.
- TikTok Selenium automation as primary approach: TikTok actively detects Selenium. The official Content Posting API is the correct path; Playwright automation is only the fallback for unaudited apps that cannot wait for the audit.

---

## Open Questions (MCP Tools)

1. **YuNet Model Versioning and Auto-Download**
   - What we know: The current model is `face_detection_yunet_2023mar.onnx`. OpenCV zoo is updated periodically.
   - What's unclear: Whether newer models (2024 or 2025 vintage) are available and whether they break the `FaceDetectorYN` API.
   - Recommendation: Pin the model filename in config. Download from the raw GitHub URL for the specific commit SHA, not from `main` branch (which may change). Store SHA in config for reproducibility.

2. **sendcmd Performance for Very Long Videos**
   - What we know: Pass 1 (OpenCV analysis) runs at approximately 5-15x real-time. A 3-hour podcast would take 12-36 minutes to analyze.
   - What's unclear: Whether FFmpeg's sendcmd file parsing has performance degradation for files with hundreds of thousands of lines (one per frame at 30 FPS over 3 hours = ~324,000 lines).
   - Recommendation: During implementation, test with a large sendcmd file. If slow, reduce to 1 entry per unique x position change (delta-encode: only write a new sendcmd line when crop_x changes by more than 1px). This reduces a 324,000-line file to potentially a few hundred lines.

3. **TikTok Content Posting API Audit Timeline**
   - What we know: Unaudited apps are restricted to SELF_ONLY, 5 uploads/day. The audit process is required for public posting.
   - What's unclear: Typical audit approval timeline. TikTok documentation does not specify SLAs.
   - Recommendation: Implement the tool with SELF_ONLY as the default and documented limitation. Register the app immediately to start the audit process. Until audit approval, offer the Playwright browser automation fallback as an alternative code path.

4. **Spotify Video Podcast Support via RSS**
   - What we know: Spotify documented support for video via RSS was mentioned in a January 2026 announcement for the Partner Program, but is limited to partner hosting platforms. Standard RSS only supports audio.
   - What's unclear: Whether a self-hosted RSS feed with video enclosures is accepted by Spotify for non-partner accounts.
   - Recommendation: Implement Spotify upload as audio-only RSS for now. For video podcast distribution to Spotify, defer to the YouTube upload (which Spotify also indexes via YouTube partnership) or wait for Spotify's video RSS spec to be publicly documented.

5. **google-api-python-client vs Direct HTTPS for YouTube**
   - What we know: The `google-api-python-client` library adds ~15MB to the bundle and pulls in several transitive dependencies. Direct HTTPS with `httpx` is technically possible using the raw resumable upload protocol.
   - What's unclear: Whether the maintenance burden of implementing exponential backoff, chunk retry, and 308-resume-incomplete handling manually is worth the reduced dependency footprint.
   - Recommendation: Use `google-api-python-client` + `google-auth-oauthlib`. The library handles all edge cases that are painful to implement correctly (chunk retry, 308 resume, exponential backoff). The added dependency weight is acceptable for a tool that is dev/optional anyway.

---

## Sources (MCP Tools)

### Primary (HIGH confidence)

- [FFmpeg crop filter commands](https://ayosec.github.io/ffmpeg-filters-docs/8.0/Filters/Video/crop.html) - `x`, `y`, `w`, `h` sendcmd support confirmed in FFmpeg 8.0 docs
- [FFmpeg sendcmd filter](https://ayosec.github.io/ffmpeg-filters-docs/7.0/Filters/Multimedia/sendcmd.html) - time interval format, TARGET COMMAND ARG syntax
- [OpenCV DNN Face Detection Tutorial](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html) - FaceDetectorYN API, bounding box format [x, y, w, h, landmarks...]
- [YouTube Data API v3 Uploading a Video](https://developers.google.com/youtube/v3/guides/uploading_a_video) - videos.insert, MediaFileUpload, OAuth2 scope
- [YouTube Data API v3 Resumable Upload](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol) - endpoint, headers, chunk requirements, response codes
- [TikTok Content Posting API Overview](https://developers.tiktok.com/products/content-posting-api/) - official API existence and capabilities
- [TikTok Content Posting API Get Started](https://developers.tiktok.com/doc/content-posting-api-get-started) - video.publish scope, audit requirements, SELF_ONLY restriction
- [TikTok Content Posting API Upload Video](https://developers.tiktok.com/doc/content-posting-api-reference-upload-video) - init endpoint, upload_url, chunk parameters, 1-hour expiry
- [google-auth-oauthlib InstalledAppFlow](https://googleapis.github.io/google-api-python-client/docs/oauth-installed.html) - from_client_secrets_file, run_local_server, credential persistence
- Installed package verification: `opencv-python-headless 4.13.0` — `FaceDetectorYN`, `TrackerMIL_create`, `TrackerDaSiamRPN`, `TrackerNano`, `TrackerVit` confirmed present via direct Python import inspection

### Secondary (MEDIUM confidence)

- [Transloadit YuNet Real-time face detection tutorial](https://transloadit.com/devtips/real-time-face-detection-with-opencv-s-yunet/) - FaceDetectorYN.create() code pattern, face bounding box extraction, score threshold defaults
- [FFmpeg overlay filter B-roll timing](https://dev.to/oskarahl/ffmpeg-overlay-a-video-on-a-video-after-x-seconds-4fc9) - `setpts=PTS-STARTPTS+N/TB` pattern for B-roll delay, `enable='between(t,start,end)'`
- [Spotify developer community - no upload API](https://community.spotify.com/t5/Spotify-for-Developers/Request-for-Access-to-Upload-Podcasts-to-Spotify-from-External/td-p/7044523) - confirmed Spotify has no public upload API (multiple threads, consistent)
- [feedgen PyPI](https://pypi.org/project/feedgen/) - podcast RSS generation, Spotify delivery spec tags
- [motion-tracking-video-crop GitHub](https://github.com/raspi/motion-tracking-video-crop) - smoothing algorithm pattern (deadzone, EMA), sendcmd generation approach
- [YuNet performance benchmarks](https://www.researchgate.net/publication/370122920_YuNet_A_Tiny_Millisecond-level_Face_Detector) - 1.6ms at 320x320, 75k parameters, CPU performance data

### Tertiary (LOW confidence - needs validation)

- YuNet 30-50 FPS CPU performance claim for 1080p — sourced from multiple community articles but not benchmarked on this project's specific hardware (WSL2 + i7). Actual throughput should be measured during implementation.
- sendcmd file scale with hundreds of thousands of lines — no official FFmpeg documentation on performance limits. The delta-encoding mitigation is a precaution, not a confirmed requirement.
- TikTok audit approval timeline — not documented by TikTok; based on community reports of weeks to months.
- Spotify video RSS acceptance — January 2026 Spotify announcement was ambiguous about self-hosted RSS feeds vs. partner-only. Needs direct testing with a Spotify for Podcasters account.

---

## Metadata (MCP Tools)

**Confidence breakdown:**
- smart_crop_subject (OpenCV + sendcmd): MEDIUM-HIGH — OpenCV API verified against installed package; sendcmd + crop filter commands verified against FFmpeg 8.0 official docs; smoothing algorithm is standard signal processing; performance estimates from published benchmarks
- overlay_video (filter_complex): HIGH — FFmpeg overlay, setpts, amix filters are stable, well-documented; `enable='between(t,S,E)'` pattern is official FFmpeg syntax
- upload_to_platform — YouTube: HIGH — Official Google developer documentation verified; all code patterns from official Python quickstart
- upload_to_platform — Spotify: HIGH (for the "no API" finding) — Multiple official sources confirm no upload API exists; RSS approach is official guidance
- upload_to_platform — TikTok: MEDIUM — Official TikTok developer documentation verified for API existence and scope; audit restrictions confirmed; full upload flow needs end-to-end testing with a registered app
- upload_to_platform — Playwright fallback: MEDIUM — Playwright Python library existence confirmed; TikTok-specific headless detection is a known community concern; needs testing

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (FFmpeg filter syntax: stable, valid indefinitely; Platform APIs: 30 days, TikTok API changes frequently; OpenCV: stable until major version)
