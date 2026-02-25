# Phase 10: Tauri Desktop Application Distribution - Research

**Researched:** 2026-02-25 (updated with existing codebase inventory)
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

**The sidecar lifecycle infrastructure is already complete.** The `desktop/` directory contains a fully working Tauri shell: Rust sidecar lifecycle commands (start/stop/status/PID tracking with cross-platform liveness checks), crash recovery (reconcile + resume via backend HTTP), a fully typed TypeScript API client (`backend.ts`), and dual-path recovery (`recovery.ts` — Tauri invoke with direct HTTP fallback). The CI/CD pipeline (`desktop-release.yml`) is fully written and handles PyInstaller per platform, Tauri builds, and smoke tests across 4 targets. What remains is the UI layer — the current `App.tsx` is a minimal "control panel" shell that must be replaced with the full NLE (Non-Linear Editor) UI per the spec.

The biggest technical risk is PyInstaller bundling of the ML dependency chain (faster-whisper + ctranslate2 + torch + CUDA). The existing CI uses `--onefile` mode, which contradicts the research recommendation of `--onedir`. This gap must be resolved during the PyInstaller subtask. A second gap: `service/cli.py` does not exist yet but the CI references it as the PyInstaller entry point — this file must be created.

**Primary recommendation:** Build the UI layer on top of the existing infrastructure. Don't rebuild what already works. The critical path is: (1) create `service/cli.py` PyInstaller entry point, (2) decide `--onefile` vs `--onedir` for the sidecar, (3) add TailwindCSS v4 + shadcn/ui to replace the existing plain CSS, (4) implement the 4 spec views as new components on top of `backend.ts` and `recovery.ts`.

---

## Existing Codebase Inventory

### Rust Layer (src-tauri/)

| File | What It Does | State | Phase 10 Changes Needed |
|------|-------------|-------|------------------------|
| `desktop/src-tauri/src/main.rs` | Entry point, calls `lib.run()` | Complete | None |
| `desktop/src-tauri/src/lib.rs` | Three Tauri commands: `start_sidecar`, `stop_sidecar`, `sidecar_status`. Uses `SidecarState` (PID tracking with cross-platform liveness checks using libc/tasklist). Registers recovery commands. | Complete | Consider adding attach-or-connect logic for coexistence with CLI-started service (current code always tries to spawn) |
| `desktop/src-tauri/src/recovery.rs` | `check_recovery` (reconcile + list resumable), `trigger_resume`. Makes HTTP calls to backend using `reqwest`. | Complete | None |
| `desktop/src-tauri/Cargo.toml` | tauri 2.x, tauri-plugin-shell 2.x, serde, serde_json, reqwest 0.12 (json feature), libc (unix-only) | Complete | Add `tauri-plugin-websocket` when WebSocket progress feed is implemented |
| `desktop/src-tauri/tauri.conf.json` | Product name "Podcast Pipeline", devUrl localhost:1420, externalBin: `["binaries/podcast-backend", "binaries/ffmpeg", "binaries/ffprobe"]`, CSP allows connect-src to 127.0.0.1:8787 | Complete | Update CSP when adding WebSocket: add `ws://127.0.0.1:8787` to connect-src |
| `desktop/src-tauri/capabilities/default.json` | `core:default`, `shell:allow-spawn`, `shell:allow-execute`, `shell:allow-kill`, `shell:allow-stdin-write`, `shell:allow-open` (https://**) | Complete | Add `websocket:default` when WebSocket plugin is added; add drag-drop permissions |
| `desktop/src-tauri/build.rs` | Validates required sidecar binaries (podcast-backend required, ffmpeg required, ffprobe optional) at build time. Panics with actionable error if missing. Respects `SKIP_SIDECAR_CHECK` env var. | Complete | None |

**Key observation about lib.rs:** The current `start_sidecar` always attempts to spawn the sidecar and only returns early if a tracked PID is still alive. It does NOT implement the attach-or-connect pattern (check if port 8787 is reachable before spawning). If Streamlit already started the service, `start_sidecar` will attempt to spawn a second instance. The coexistence requirement requires adding a pre-spawn health check.

### TypeScript Layer (src/)

| File | What It Does | State | Phase 10 Changes Needed |
|------|-------------|-------|------------------------|
| `desktop/src/lib/backend.ts` | Full typed API client. Constants: `BACKEND_PORT=8787`, `HEALTH_POLL_INTERVAL_MS=5000`. Functions: `startSidecar`, `stopSidecar`, `getSidecarStatus`, `checkHealth`, `waitForReady` (15s timeout, 500ms probe), `bootBackend` (orchestrates start + wait), `listJobs`, `createJob`, `runJob` (background + foreground), `resumeJob`, `getJob`, `deleteJob`, `reconcileJobs`, `getRuntimeDiagnostics`. Typed interfaces for all API shapes. | Complete | Add file upload endpoint wrapper when drag-drop ingestion is implemented. Add WebSocket connection helper. |
| `desktop/src/lib/recovery.ts` | `checkRecovery` (Tauri invoke → direct HTTP fallback), `triggerResume` (Tauri invoke → direct HTTP fallback), `reconcileNow`, `getRuntimeDiagnostics`. Dual-path pattern: tries `@tauri-apps/api/core` invoke first, falls back to direct fetch for dev/browser context. | Complete | None |
| `desktop/src/App.tsx` | Minimal "control panel" shell. Implements: boot sequence, health polling, job list with Run/Resume/Delete/Stage controls, recovery banner, runtime diagnostics panel, job detail view. Uses only plain React state (no TanStack Query, no Zustand). CSS via `styles.css`. | Partial — functional but not spec UI | Replace/extend with 4 spec views: Ingestion Dashboard, Audio Sync Editor, Transcript Timeline, Branding Studio. Keep boot/recovery logic, replace the render layer. |
| `desktop/src/main.tsx` | React entry point, wraps App in StrictMode. | Complete | Add QueryClientProvider when TanStack Query is added |
| `desktop/src/styles.css` | Dark CSS custom properties (`--bg-primary: #1a1a2e`, `--accent: #e94560`). Plain CSS classes for status dots, job list, buttons. No Tailwind. | Partial — needs replacement | Replace with TailwindCSS v4 + shadcn/ui (keep the color tokens as Tailwind CSS variables) |

### Build/Script Layer

| File | What It Does | State | Phase 10 Changes Needed |
|------|-------------|-------|------------------------|
| `desktop/package.json` | Dependencies: react 19, react-dom 19, @tauri-apps/api ^2.10.1, @tauri-apps/plugin-shell ^2.3.5. devDeps: @tauri-apps/cli ^2.10.0, TypeScript ~5.7.0, Vite ^6.0.0 | Partial — missing UI libraries | Add: `@tanstack/react-query`, `zustand`, `tailwindcss`, `@tailwindcss/vite`, `wavesurfer.js`, `@wavesurfer/react`, `@tauri-apps/plugin-websocket`; add shadcn/ui via CLI |
| `desktop/vite.config.ts` | Standard Tauri Vite config (port 1420, strictPort, TAURI_DEV_HOST support). No TailwindCSS plugin. | Partial — needs Tailwind | Add `tailwindcss()` Vite plugin import |
| `desktop/tsconfig.json` | Strict TypeScript (ES2020, noUnusedLocals, noUnusedParameters, noFallthroughCasesInSwitch). | Complete | None |
| `desktop/scripts/prepare-sidecars.mjs` | Resolves target triple (TAURI_TARGET_TRIPLE env or os.platform/arch mapping), copies podcast-backend + ffmpeg + ffprobe to `src-tauri/binaries/<name>-<triple>` convention. Required=true for podcast-backend + ffmpeg, optional for ffprobe. Supports `--check` dry-run. | Complete | None |
| `desktop/scripts/smoke-test-desktop.sh` | Validates installer artifact (size check), extracts AppImage/deb/dmg, verifies podcast-backend sidecar presence, runs backend health check, checks ffmpeg presence. | Complete | None |
| `desktop/scripts/run-tests.mjs` | Runs `tests/test_desktop_backend.ts` via Node `--experimental-strip-types --test`. | Complete | None |

### CI/CD Layer

| File | What It Does | State | Phase 10 Changes Needed |
|------|-------------|-------|------------------------|
| `.github/workflows/desktop-release.yml` | 3-job workflow: (1) build-backend: PyInstaller per platform (4 matrix targets), (2) build-desktop: downloads backend artifact + prepare-sidecars + tauri-action@v0 with codesigning, (3) smoke-test: runs smoke scripts. Triggers on git tags + workflow_dispatch. | Complete | Fix PyInstaller mode: currently uses `--onefile` per research recommendation vs `--onedir`; create `service/cli.py` (currently referenced but doesn't exist); add `PYTHONUTF8=1` env to PyInstaller step |

### FastAPI Service Layer

| File | What It Does | State | Phase 10 Changes Needed |
|------|-------------|-------|------------------------|
| `src/podcast_pipeline/service/app.py` | FastAPI app factory. Lifespan: loads config, Pipeline, Supervisor, auth policy, starts reconcile task. Auth: `ServiceAuthPolicy` (production requires API key; development bypasses with env var). Routes: `/health`, `/jobs/*`, `/system/*`. **No CORS middleware.** | Complete as backend; missing CORS | Add `CORSMiddleware` for Tauri dev (`http://localhost:1420`) and production (`tauri://localhost`) |
| `src/podcast_pipeline/service/routes/jobs.py` | All job lifecycle endpoints: POST /jobs, GET /jobs, GET /jobs/{id}, DELETE /jobs/{id}, POST /jobs/{id}/run, POST /jobs/{id}/run/background, POST /jobs/{id}/resume, GET /jobs/resumable, POST /jobs/reconcile | Complete | None |
| `src/podcast_pipeline/service/routes/system.py` | Asset readiness: GET /system/status (binaries + model check), GET /system/binaries/{name}, GET /system/models/{name}, POST /system/models/warmup, GET /system/runtime (stale/orphaned job diagnostics) | Complete | None — frontend needs to call these for readiness UI |
| `src/podcast_pipeline/service/schemas.py` | All request/response Pydantic models. StageName literal: `("ingest", "transcribe", "analyze", "review", "render")` | Complete | None |
| `src/podcast_pipeline/service/supervisor.py` | Supervisor with GPULease, heartbeat tracking, background asyncio tasks. RuntimeMeta persisted to runtime.json per job. | Complete | None |
| `src/podcast_pipeline/service/cli.py` | **DOES NOT EXIST.** The CI workflow at line 83 runs `src/podcast_pipeline/service/cli.py` as the PyInstaller entry point. This file must be created. | Missing | Create: uvicorn server startup script with UTF-8 env setup, --port argument, stdout readiness signal |
| `src/podcast_pipeline/service/assets.py` | Asset resolution (ffmpeg, ffprobe, podcast-backend binaries; whisper model cache detection) | Complete | None |

---

## Standard Stack

### Core (existing installation status)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| tauri | 2.x | Desktop application shell (Rust) | INSTALLED (Cargo.toml) |
| @tauri-apps/api | ^2.10.1 | JavaScript API for Tauri features | INSTALLED (package.json) |
| @tauri-apps/cli | ^2.10.0 | Build/dev toolchain | INSTALLED (package.json devDep) |
| tauri-plugin-shell | 2.x (Rust) / ^2.3.5 (JS) | Spawn/manage sidecar subprocess | INSTALLED (both) |
| tauri-plugin-websocket | 2.x | Native WebSocket client | NOT INSTALLED — needed for job progress feed |
| React | ^19.0.0 | UI framework | INSTALLED |
| TypeScript | ~5.7.0 | Type safety | INSTALLED |
| Vite | ^6.0.0 | Frontend bundler | INSTALLED |
| TailwindCSS | 4.x | Utility-first CSS | NOT INSTALLED — needed to replace styles.css |
| shadcn/ui | latest | Component library | NOT INSTALLED — needed for glassmorphism spec UI |
| Zustand | 5.x | Client-side state | NOT INSTALLED — App.tsx uses raw useState |
| TanStack Query | 5.x | Server state / API calls | NOT INSTALLED — App.tsx uses raw useEffect fetch |
| PyInstaller | 6.19+ | Bundle Python+FastAPI into binary | NOT IN REPO (installed per-build in CI) |
| wavesurfer.js | 7.x | Waveform visualization | NOT INSTALLED — needed for audio sync view |
| reqwest | 0.12 | HTTP client in Rust (for recovery) | INSTALLED (Cargo.toml) |
| libc | 0.2 | Unix signal/process operations | INSTALLED (Cargo.toml, unix-only) |

### Supporting

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| @tauri-apps/plugin-fs | 2.x | File system access after drag-drop | NOT INSTALLED — may be needed for file reading post-drop |
| @wavesurfer/react | 7.x | React hook for wavesurfer | NOT INSTALLED |
| tauri-action | v0 | GitHub Actions build CI | INSTALLED (workflow uses tauri-apps/tauri-action@v0) |

### Installation Commands for Missing Libraries

```bash
# Inside desktop/ directory:
cd desktop

# Frontend UI stack
pnpm add @tanstack/react-query zustand
pnpm add tailwindcss @tailwindcss/vite
pnpm add wavesurfer.js @wavesurfer/react

# Tauri WebSocket plugin
pnpm run tauri add websocket

# shadcn/ui (after tailwind configured)
npx shadcn@latest init
```

---

## Architecture Patterns

### Actual Project Structure (What Exists)

```
desktop/                             # Tauri project root (exists)
├── src/                             # React frontend (exists)
│   ├── main.tsx                     # React entry (complete)
│   ├── App.tsx                      # Control panel shell (partial - needs UI rebuild)
│   ├── styles.css                   # Plain CSS (partial - replace with Tailwind)
│   └── lib/
│       ├── backend.ts               # Full typed API client (complete)
│       └── recovery.ts              # Dual-path recovery (complete)
├── src-tauri/                       # Tauri Rust shell (exists)
│   ├── src/
│   │   ├── main.rs                  # Entry point (complete)
│   │   ├── lib.rs                   # Sidecar lifecycle commands (complete)
│   │   └── recovery.rs              # Recovery Tauri commands (complete)
│   ├── binaries/                    # Sidecar binaries (gitignored, built in CI)
│   ├── capabilities/
│   │   └── default.json             # Shell permissions (complete - needs websocket)
│   ├── tauri.conf.json              # Bundle config (complete - needs CSP update for WS)
│   └── build.rs                    # Sidecar binary validation (complete)
├── scripts/
│   ├── prepare-sidecars.mjs         # Binary naming/copy helper (complete)
│   ├── run-tests.mjs                # Test runner (complete)
│   ├── smoke-test-desktop.sh        # Linux/macOS smoke test (complete)
│   └── smoke-test-desktop.ps1       # Windows smoke test (complete)
├── package.json                     # Deps (partial - missing UI libraries)
├── vite.config.ts                   # Vite config (partial - missing Tailwind plugin)
└── tsconfig.json                    # TypeScript config (complete)
```

### Target Project Structure (What Needs to Be Added)

```
desktop/src/
├── main.tsx                         # Add: QueryClientProvider wrapper
├── App.tsx                          # Replace render: add view routing
├── styles.css                       # Replace with Tailwind @import "tailwindcss"
├── lib/
│   ├── backend.ts                   # Extend: add upload, WebSocket helpers
│   └── recovery.ts                  # Keep as-is
├── components/
│   ├── ui/                          # shadcn/ui generated components (new)
│   ├── waveform/                    # Wavesurfer.js wrappers (new)
│   └── layout/                      # App shell, sidebar, nav (new)
├── views/                           # Four spec views (all new)
│   ├── IngestionView.tsx            # Drag-drop + pipeline dashboard
│   ├── AudioSyncView.tsx            # Multi-track waveform timeline
│   ├── TranscriptView.tsx           # Scrolling transcript + filler toggle
│   └── BrandingView.tsx             # Branding CRUD + export settings
├── hooks/                           # TanStack Query hooks (new)
│   ├── useJobs.ts
│   ├── useSidecarReady.ts
│   └── useSystemStatus.ts
└── stores/                          # Zustand stores (new)
    ├── uiStore.ts                   # selectedJobId, activeView, theme
    └── sidecarStore.ts              # sidecar status, backend connection
```

### Pattern 1: Sidecar Lifecycle — Extend Existing (Not Rebuild)

**What exists:** `lib.rs` has `start_sidecar`, `stop_sidecar`, `sidecar_status` commands with cross-platform PID liveness checking. `backend.ts` has `bootBackend()`, `waitForReady()`, `startSidecar()`, `stopSidecar()`.

**Gap:** `start_sidecar` always spawns — it does NOT implement the coexistence check (attach if already running). For Streamlit coexistence, the app must check health BEFORE spawning.

**Extension needed in `lib.rs`:**
```rust
// Add pre-spawn health check in start_sidecar
// Before attempting spawn, check if http://127.0.0.1:8787/health responds.
// If yes — set a flag (TAURI_OWNS_SIDECAR=false), skip spawn.
// If no — spawn sidecar, set TAURI_OWNS_SIDECAR=true.
// In stop_sidecar — only kill if TAURI_OWNS_SIDECAR=true.
use std::sync::atomic::{AtomicBool, Ordering};
static TAURI_OWNS_SIDECAR: AtomicBool = AtomicBool::new(false);
```

**Extension needed in `App.tsx` boot sequence:**
```typescript
// The existing boot sequence already handles the fallback correctly:
// If startSidecar() throws (port in use), it falls through to checkHealth().
// This partially works for coexistence but should be made explicit.
// Current code (App.tsx line ~403):
const healthy = await checkHealth();
if (healthy !== null) {
  setStatus("connected");
  markInfo("Connected to an already-running backend service.");
}
```

### Pattern 2: TailwindCSS v4 + Vite — Add to Existing Config

**What exists:** `vite.config.ts` has React plugin only. `styles.css` has custom properties.

**How to extend `vite.config.ts`:**
```typescript
// Source: https://tailwindcss.com/docs/guides/vite
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(async () => ({
  plugins: [
    react(),
    tailwindcss(),   // Add this
  ],
  // ... rest of existing config unchanged
}));
```

**Replace `styles.css` header:**
```css
/* Replace the :root block with Tailwind v4 import + CSS variables */
@import "tailwindcss";

/* Keep existing color tokens as CSS custom properties */
:root {
  --bg-primary: #1a1a2e;
  --bg-secondary: #16213e;
  --bg-card: #0f3460;
  /* ... etc */
}

/* Dark mode via class strategy */
@custom-variant dark (&:where(.dark, .dark *));
```

### Pattern 3: Add TanStack Query to Existing App

**What exists:** `App.tsx` uses raw `useState` + `useEffect` + `setInterval` for polling. Works but doesn't handle deduplication, cache, or background refetch well.

**Add QueryClientProvider in `main.tsx`:**
```typescript
// Source: Verified against TanStack Query v5 docs
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
```

**Convert existing job polling to a hook:**
```typescript
// src/hooks/useJobs.ts - replaces App.tsx manual interval logic
import { useQuery } from '@tanstack/react-query';
import { listJobs } from '../lib/backend';

export function useJobs() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    refetchInterval: 5000,  // matches existing HEALTH_POLL_INTERVAL_MS
  });
}
```

### Pattern 4: Sidecar Entry Point — Create service/cli.py

**What exists:** Nothing. CI references `src/podcast_pipeline/service/cli.py` at line 83 of `desktop-release.yml`.

**What must be created:**
```python
# src/podcast_pipeline/service/cli.py
# PyInstaller sidecar entry point
import os
import sys

# MUST be set before any imports that output Unicode (structlog uses emoji)
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import argparse
import uvicorn

def main() -> None:
    parser = argparse.ArgumentParser(description="Podcast Pipeline Backend Service")
    parser.add_argument("--port", type=int, default=8787, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    # Signal readiness to Tauri sidecar listener on stdout
    print(f"BACKEND_READY port={args.port}", flush=True)

    from podcast_pipeline.service.app import create_app
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")

if __name__ == "__main__":
    main()
```

### Pattern 5: Native File Drag-Drop (New Work)

**What exists:** No drag-drop in current App.tsx. The spec requires it for the Ingestion View.

```typescript
// Source: https://v2.tauri.app/reference/javascript/api/namespacewebview/
import { getCurrentWebview } from "@tauri-apps/api/webview";

// In IngestionView.tsx
useEffect(() => {
  let unlisten: (() => void) | null = null;
  getCurrentWebview().onDragDropEvent((event) => {
    if (event.payload.type === 'drop') {
      const filePaths: string[] = event.payload.paths;
      // Send full OS paths to backend POST /jobs
      for (const path of filePaths) {
        void createJob(path);
      }
    }
  }).then((fn) => { unlisten = fn; });
  return () => unlisten?.();
}, []);
```

**Critical:** Do NOT use react-dropzone for getting file paths — it returns browser File objects without full OS paths.

### Pattern 6: WebSocket Progress Feed (New Work)

**What exists:** No WebSocket in current frontend. No WebSocket endpoints in FastAPI. No `tauri-plugin-websocket` installed.

**Two-step implementation:**
1. Add WebSocket endpoint to FastAPI (`service/routes/jobs.py`)
2. Connect from frontend using `@tauri-apps/plugin-websocket`

```typescript
// Source: https://v2.tauri.app/plugin/websocket/
// After: npm run tauri add websocket
import WebSocket from '@tauri-apps/plugin-websocket';

const ws = await WebSocket.connect('ws://127.0.0.1:8787/jobs/{jobId}/ws');
const remove = ws.addListener((msg) => {
  const event = JSON.parse(msg.data as string);
  // Invalidate TanStack Query cache for this job
  queryClient.invalidateQueries({ queryKey: ['jobs', jobId] });
});
await ws.disconnect();
```

**Note:** Update `tauri.conf.json` CSP when adding WebSocket:
```json
"csp": "default-src 'self'; connect-src 'self' http://127.0.0.1:8787 ws://127.0.0.1:8787; style-src 'self' 'unsafe-inline'"
```

### Pattern 7: PyInstaller Spec for FastAPI + ML Stack

**Current CI approach (must be evaluated):**
```bash
# From desktop-release.yml (lines 77-83)
uv run pyinstaller \
  --name podcast-backend \
  --onefile \                    # ← CONFLICTS with research recommendation
  --console \
  --hidden-import podcast_pipeline \
  --hidden-import uvicorn \
  src/podcast_pipeline/service/cli.py   # ← FILE DOESN'T EXIST YET
```

**Recommended approach (--onedir with spec file):**
```python
# src-python/sidecar.spec
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ct2_binaries = collect_dynamic_libs('ctranslate2')
ct2_datas = collect_data_files('ctranslate2')
faster_whisper_datas = collect_data_files('faster_whisper')

a = Analysis(
    ['src/podcast_pipeline/service/cli.py'],
    binaries=ct2_binaries,
    datas=[*ct2_datas, *faster_whisper_datas],
    hiddenimports=[
        'ctranslate2', 'faster_whisper',
        'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on',
    ],
    excludes=['pytest', 'unittest', 'tkinter', 'wx', 'PyQt5', 'streamlit'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='podcast-backend', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='podcast-backend')
```

### Anti-Patterns to Avoid

- **Rebuilding sidecar lifecycle:** `lib.rs` + `backend.ts` + `recovery.ts` already implement it. Extend don't replace.
- **Rebuilding health polling:** `waitForReady()` and `checkHealth()` in `backend.ts` already handle timeouts and intervals.
- **Using `process.kill()` for PyInstaller one-file sidecars:** Tauri only knows the bootloader PID. Use `--onedir` mode OR stdin signaling.
- **Using browser WebSocket API:** Not available for localhost ws:// in Tauri webview. Use `@tauri-apps/plugin-websocket`.
- **Using react-dropzone for file paths:** Returns browser File objects without OS paths. Use `getCurrentWebview().onDragDropEvent()`.
- **Committing PyInstaller binaries:** `src-tauri/binaries/` is gitignored and built in CI per-platform.
- **Forgetting UTF-8 env before structlog imports:** Windows crashes on emoji/Unicode in logs.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Status |
|---------|-------------|-------------|--------|
| Sidecar lifecycle (start/stop/status) | Custom process management | Existing `lib.rs` + `backend.ts` | ALREADY DONE |
| Health polling with timeout | Manual setInterval | Existing `waitForReady()` in `backend.ts` | ALREADY DONE |
| Crash recovery (reconcile + resume) | Custom recovery logic | Existing `recovery.ts` + `recovery.rs` | ALREADY DONE |
| Typed API client for all backend endpoints | Raw fetch calls | Existing `backend.ts` | ALREADY DONE |
| Cross-platform sidecar binary preparation | Custom shell scripts | Existing `prepare-sidecars.mjs` | ALREADY DONE |
| Cross-platform CI build + codesigning | Custom Actions matrix | Existing `desktop-release.yml` | ALREADY DONE |
| Waveform visualization | Custom SVG/Canvas renderer | wavesurfer.js v7 + @wavesurfer/react | NOT DONE — add |
| WebSocket client in Tauri | Raw WebSocket | @tauri-apps/plugin-websocket | NOT DONE — add |
| File drag-drop with OS paths | Browser drag-drop API | `getCurrentWebview().onDragDropEvent()` | NOT DONE — add |
| Progress/job polling | Manual setInterval fetch | TanStack Query `refetchInterval` | NOT DONE — add |
| Component system for glassmorphism | Custom CSS components | shadcn/ui + Tailwind v4 | NOT DONE — add |
| Auto-updater | Custom update mechanism | tauri-plugin-updater | NOT DONE — future work |

**Key insight:** The infrastructure layer is complete. All remaining work is UI/UX.

---

## Gap Analysis (Existing → Target)

| Feature | Spec Requirement | Current State | Gap | Effort |
|---------|-----------------|---------------|-----|--------|
| Sidecar lifecycle | Start/stop/status + PID tracking | `lib.rs` + `backend.ts` — complete | NONE | 0 |
| Coexistence with Streamlit | Attach to existing service if running | `start_sidecar` always spawns; `App.tsx` has fallback checkHealth on error | Partial — needs pre-spawn health check in `lib.rs` | S |
| Crash recovery | Reconcile + resume after crash | `recovery.rs` + `recovery.ts` — complete | NONE | 0 |
| PyInstaller entry point | `service/cli.py` to build sidecar | `service/cli.py` does NOT exist | Critical blocker for CI | S |
| `--onefile` vs `--onedir` | Research: `--onedir` preferred | CI uses `--onefile` | Must decide and update CI | S |
| CORS middleware | FastAPI allows Tauri dev + prod origins | No CORS in `app.py` | Blocks `tauri dev` (CORS errors) | S |
| WebSocket job progress | FastAPI WS endpoint + Tauri WS plugin | No WS in FastAPI; no plugin installed | Missing both backend and frontend | M |
| TailwindCSS v4 | Dark glassmorphism spec UI | Plain CSS in `styles.css` | Config + class migration | S |
| shadcn/ui components | Design-first component library | None installed | Setup + add to UI | M |
| Zustand stores | Client UI state management | Raw useState in App.tsx | Add stores, migrate state | M |
| TanStack Query | Server state + polling | Raw useEffect in App.tsx | Add provider, migrate fetches | M |
| View 1: Ingestion Dashboard | Drag-drop batch queue + pipeline progress | Text input + basic job list | New view, replace create section | L |
| View 2: Audio Sync Editor | Multi-track wavesurfer.js timeline | Nothing | New view (wavesurfer.js install required) | L |
| View 3: Transcript Timeline | Scrolling transcript + filler toggle | Nothing | New view (requires transcript data from backend) | L |
| View 4: Branding Studio | Color/font/thumbnail/export controls | Nothing | New view (requires brand profile API) | L |
| Native drag-drop | OS file paths via Tauri webview event | Text input for file path | Add onDragDropEvent listener | M |
| Window sizing | NLE-grade wide layout (1440+ min) | 1024x768 in tauri.conf.json | Update window dimensions | XS |
| Asset readiness UI | Show binary/model status before first run | Nothing | Use existing `/system/status` endpoint | S |
| Auto-updater | In-app update mechanism | Not implemented | Needs tauri-plugin-updater | L (future) |

**Effort key:** XS (<2h) / S (2-4h) / M (4-8h) / L (1-2 days)

---

## Common Pitfalls

### Pitfall 1: PyInstaller One-File with CUDA Torch

**What goes wrong:** `--onefile` produces a 2-4 GB exe that extracts to a temp directory on every launch. On Windows with CUDA torch, extraction takes 8-15 seconds every time the app opens, making it feel broken.
**Why it happens:** PyInstaller one-file mode packs everything into a self-extracting archive. CUDA runtime DLLs are enormous.
**How to avoid:** Use `--onedir` mode. Ship the sidecar as a directory. Tauri bundles the entire directory. First launch still takes longer (Python init + torch load), but there is no extraction step.
**Warning signs:** Sidecar takes >10 seconds to appear on health check poll. Temp folder grows to 2-4 GB on Windows (`%TEMP%\_MEIXXXXXX` directories accumulate if app crashes before cleanup).

### Pitfall 2: CI Uses --onefile but Research Recommends --onedir

**What goes wrong:** The existing `desktop-release.yml` uses `pyinstaller --onefile`. This contradicts the research recommendation and introduces the extraction-delay problem (Pitfall 1) plus the PID tracking problem (Pitfall 2). If torch/CUDA is included, the binary will be 2-4 GB and extract on every launch.
**Why it happens:** The CI workflow was written before the PyInstaller research was complete. `--onefile` is simpler to integrate with Tauri's `externalBin` (single file path); `--onedir` requires pointing Tauri at the executable inside a directory while bundling the directory alongside.
**Migration path:**
1. Evaluate if startup delay is acceptable without CUDA torch (base bundle without torch may be small enough for `--onefile`)
2. If torch must be included, switch to `--onedir`: set `externalBin` to `"binaries/podcast-backend/podcast-backend"`, copy entire dist directory to `src-tauri/binaries/podcast-backend/`
3. Update `prepare-sidecars.mjs` to handle the directory case
**Warning signs:** App feels sluggish on open. `%TEMP%` fills up with `_MEI*` directories. Startup health check times out during extraction.

### Pitfall 3: service/cli.py Missing — CI Will Fail

**What goes wrong:** The CI workflow at line 83 of `desktop-release.yml` runs `src/podcast_pipeline/service/cli.py` as the PyInstaller entry point. This file does not exist. Every CI build will fail until it is created.
**Why it happens:** The CI was scaffolded ahead of the file being created.
**How to avoid:** Create `service/cli.py` as the first task of Phase 10. It must parse `--port`, set UTF-8 env vars, print readiness signal, and start uvicorn.
**Warning signs:** CI fails immediately at the PyInstaller step with `ModuleNotFoundError` or `FileNotFoundError`.

### Pitfall 4: No CORS Middleware in service/app.py

**What goes wrong:** `tauri dev` runs the Vite frontend at `http://localhost:1420`. The FastAPI backend at `http://127.0.0.1:8787` has no CORS middleware. Every API call from the dev frontend will fail with "CORS policy" errors.
**Why it happens:** The existing `app.py` was written for Streamlit (same-process) and CLI use, not cross-origin browser clients. Confirmed by code inspection: no `CORSMiddleware` import or `app.add_middleware(CORSMiddleware, ...)` call anywhere in the service directory.
**How to avoid:** Add `CORSMiddleware` to `app.py` before first `tauri dev` run. Control allowed origins via env var (`PODCAST_PIPELINE_CORS_ORIGINS`). Default: `["http://localhost:1420", "tauri://localhost"]`. Never use `allow_origins=["*"]` in production.
**Warning signs:** Browser console shows "blocked by CORS policy" for every API call. Works fine when running service via CLI alone but breaks under `tauri dev`.

### Pitfall 5: No stdin Shutdown Handler in Sidecar

**What goes wrong:** The current `lib.rs` uses `taskkill /PID /F` (Windows) and `libc::kill(pid, SIGTERM)` (Unix) to stop the sidecar. For PyInstaller `--onefile`, this kills the bootloader but not the actual Python process (the port stays bound). For `--onedir`, SIGTERM works correctly.
**Why it happens:** With `--onefile`, PyInstaller spawns a child process for the actual Python code. The tracked PID is the bootloader parent, not the Python child.
**How to avoid:** If using `--onefile`, implement stdin shutdown in `service/cli.py` that listens for a `shutdown\n` line and calls `sys.exit(0)`. The Rust `stop_sidecar` would need to write to stdin before sending the signal. If using `--onedir`, SIGTERM via the existing `stop_sidecar` implementation works correctly.
**Warning signs:** Port 8787 remains bound after `stop_sidecar`. Second app launch fails to start sidecar. Orphan Python processes visible in Task Manager.

### Pitfall 6: process.kill() Fails for One-File Sidecars

**What goes wrong:** `child.kill()` in Rust kills the PyInstaller bootloader process, but the actual Python interpreter (child of the bootloader) keeps running in the background. FastAPI continues to hold port 8787.
**Why it happens:** PyInstaller bootloader spawns a second process. Tauri only tracks the bootloader PID.
**How to avoid:** Use `--onedir` mode (process tree is simpler and `kill()` works) OR implement stdin shutdown signaling in the FastAPI sidecar.
**Warning signs:** Port 8787 already in use error on second app launch. Orphan Python processes visible in Task Manager.

### Pitfall 7: ctranslate2 DLL Not Found on Windows

**What goes wrong:** Bundled sidecar runs but crashes with `ImportError: libctranslate2.dll not found` because PyInstaller didn't auto-detect the native DLLs.
**Why it happens:** ctranslate2 uses `ctypes`-based dynamic loading that PyInstaller's static analysis cannot follow.
**How to avoid:** In the spec file, explicitly call `collect_dynamic_libs('ctranslate2')` and add result to `binaries`. Also add `'ctranslate2'` to `hiddenimports`.
**Warning signs:** Sidecar exits immediately after spawn with code 1. stderr shows ImportError or DLL load failure.

### Pitfall 8: Missing Binary Before tauri build

**What goes wrong:** `pnpm tauri build` fails with `external binary not found` because the PyInstaller step was skipped or the binary is in the wrong location.
**Why it happens:** Tauri validates that all `externalBin` paths exist at build time. The existing `build.rs` will panic with an actionable error if binaries are missing (unless `SKIP_SIDECAR_CHECK=1`).
**How to avoid:** Always run `node scripts/prepare-sidecars.mjs` before `tauri build`. In CI, `SKIP_SIDECAR_CHECK=1` is set — the binary must still be present (just not validated by build.rs). The CI downloads the artifact from the previous job step.
**Warning signs:** Panic from `build.rs` mentioning missing sidecar. Or (in CI with skip): tauri-action fails with missing externalBin error.

### Pitfall 9: WebSocket Connection Fails in Tauri WebView

**What goes wrong:** Frontend code using `new WebSocket('ws://127.0.0.1:8787/...')` throws an error or silently fails in the packaged Tauri app.
**Why it happens:** Tauri's webview does not have the browser's native WebSocket API available for localhost ws:// connections.
**How to avoid:** Install and use `@tauri-apps/plugin-websocket`. Run `pnpm run tauri add websocket`. Add `"websocket:default"` to capabilities. Update CSP in `tauri.conf.json` to include `ws://127.0.0.1:8787`.
**Warning signs:** WebSocket connects fine in `tauri dev` but fails in production build.

### Pitfall 10: Sidecar Not Ready When Frontend Loads

**What goes wrong:** Frontend renders and immediately calls API endpoints, gets connection refused.
**Why it happens:** FastAPI + Python initialization takes 2-10 seconds. The existing `waitForReady()` in `backend.ts` handles this (15s timeout, 500ms probe), and `App.tsx` gates the UI on connection. Preserve this gate in the new UI.
**Warning signs:** "Connection refused" in console. Happens on cold start but not after app warms up.

### Pitfall 11: Tauri v1 API Used Instead of v2

**What goes wrong:** Community examples frequently reference v1 APIs (e.g., `tauri.window.fileDropEnabled` instead of `app.window.dragDropEnabled`).
**How to avoid:** Always check `v2.tauri.app`. When reading community examples, verify the Tauri version.
**Warning signs:** TypeScript type errors on Tauri API imports. Configuration keys not recognized in `tauri.conf.json`.

---

## Code Examples

Verified patterns from official sources and existing codebase:

### Existing: Boot Sequence (from backend.ts)

```typescript
// Source: desktop/src/lib/backend.ts - already implemented
export async function bootBackend(): Promise<{
  sidecar: SidecarStatus;
  health: HealthResponse | null;
}> {
  const sidecar = await startSidecar();
  const health = await waitForReady();  // 15s timeout, 500ms probe interval
  return { sidecar, health };
}
```

### Existing: Dual-Path Recovery (from recovery.ts)

```typescript
// Source: desktop/src/lib/recovery.ts - already implemented
export async function checkRecovery(): Promise<RecoveryStatus> {
  try {
    return await tauriInvoke<RecoveryStatus>("check_recovery");
  } catch {
    // Outside Tauri context -- fall back to direct HTTP
    return checkRecoveryDirect();
  }
}
```

### New: TailwindCSS v4 in vite.config.ts

```typescript
// Source: https://tailwindcss.com/docs/guides/vite
// Extend existing desktop/vite.config.ts
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(async () => ({
  plugins: [
    react(),
    tailwindcss(),   // v4 uses Vite plugin, NOT tailwind.config.js
  ],
  // ... existing server config unchanged
  build: {
    // Add: Tauri platform targets
    target: process.env.TAURI_ENV_PLATFORM == 'windows' ? 'chrome105' : 'safari13',
  },
}));
```

### New: Native File Drop

```typescript
// Source: https://v2.tauri.app/reference/javascript/api/namespacewebview/
import { getCurrentWebview } from "@tauri-apps/api/webview";

const unlisten = await getCurrentWebview().onDragDropEvent((event) => {
  if (event.payload.type === 'drop') {
    const paths: string[] = event.payload.paths; // Full OS paths
    for (const videoPath of paths) {
      void createJob(videoPath);  // from existing backend.ts
    }
  }
});
return () => unlisten();
```

### New: WebSocket Plugin

```typescript
// Source: https://v2.tauri.app/plugin/websocket/
// After: pnpm run tauri add websocket
import WebSocket from '@tauri-apps/plugin-websocket';

const ws = await WebSocket.connect('ws://127.0.0.1:8787/jobs/abc/ws');
const remove = ws.addListener((msg) => { /* handle progress event */ });
await ws.disconnect();
```

### New: TanStack Query Job Hook

```typescript
// Source: Verified against TanStack Query v5 docs
// Replaces manual setInterval in App.tsx
import { useQuery } from '@tanstack/react-query';
import { listJobs } from '../lib/backend';

export function useJobs() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    refetchInterval: 5000,  // matches existing HEALTH_POLL_INTERVAL_MS
  });
}
```

### New: Zustand UI Store

```typescript
// Source: Verified against Zustand v5 docs
import { create } from 'zustand';

interface UIStore {
  selectedJobId: string | null;
  activeView: 'ingestion' | 'audio' | 'transcript' | 'branding';
  setSelectedJob: (id: string | null) => void;
  setActiveView: (view: UIStore['activeView']) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  selectedJobId: null,
  activeView: 'ingestion',
  setSelectedJob: (id) => set({ selectedJobId: id }),
  setActiveView: (view) => set({ activeView: view }),
}));
```

### New: service/cli.py (Must Create)

```python
# Source: Pattern 4 above + aiechoes.substack.com production guide
# src/podcast_pipeline/service/cli.py
import os, sys

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import argparse
import uvicorn

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"BACKEND_READY port={args.port}", flush=True)
    from podcast_pipeline.service.app import create_app
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")

if __name__ == "__main__":
    main()
```

### Existing GitHub Actions CI (already working)

```yaml
# Source: .github/workflows/desktop-release.yml - complete and working
# PyInstaller step (needs service/cli.py to exist first):
- name: Build backend binary with PyInstaller
  run: |
    uv run pyinstaller \
      --name podcast-backend \
      --onefile \          # ← evaluate: change to --onedir for large bundles
      --console \
      --hidden-import podcast_pipeline \
      --hidden-import uvicorn \
      src/podcast_pipeline/service/cli.py
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tauri v1 allowlist | Tauri v2 capabilities + permissions | Oct 2024 (v2 stable) | All permission configs must use v2 format |
| `tauri.window.fileDropEnabled` | `app.window.dragDropEnabled` | Oct 2024 (v2) | Config key renamed |
| `@tauri-apps/api/tauri` imports | `@tauri-apps/api` flat imports | Oct 2024 (v2) | Import paths reorganized |
| Tauri shell built-in | `tauri-plugin-shell` (separate plugin) | Oct 2024 (v2) | Already installed in this project |
| TailwindCSS v3 (tailwind.config.js) | TailwindCSS v4 (@tailwindcss/vite Vite plugin) | Jan 2025 | No config file needed; CSS-native theming |
| Redux for React state | Zustand + TanStack Query | 2023-2024 | Redux overkill; Zustand is simpler |
| Wavesurfer.js v6 (class-based) | Wavesurfer.js v7 (TypeScript, Shadow DOM) | 2023 | Plugin arrays must be memoized in React |
| PyInstaller 5.x | PyInstaller 6.x (6.19 current) | 2024 | Better hooks for ML libraries |

**Deprecated/outdated:**
- PyOxidizer: Effectively abandoned as of 2022-2023. Do not use.
- Tauri v1: v2 is stable since Oct 2024; existing project correctly uses v2.

---

## Open Questions

1. **PyInstaller --onefile vs --onedir Decision**
   - What we know: CI uses `--onefile`. Research recommends `--onedir`. The decision depends on bundle size.
   - What's unclear: Whether this project will include CUDA torch in the sidecar at all. The `--onedir` + Tauri exact configuration (how to point externalBin at executable inside a directory) needs empirical testing.
   - Recommendation: During subtask 10-02, test both. If bundle without torch is <200 MB, `--onefile` is acceptable. If torch must be included, switch to `--onedir`.

2. **torch/CUDA Bundle Size**
   - What we know: CUDA torch bundles are 2-4 GB. Project uses torch for RIFE GPU (Phase 8). The `service/cli.py` will import the full pipeline.
   - What's unclear: Whether torch can be made optional (lazy import) so base bundle is 100-300 MB.
   - Recommendation: Design `service/cli.py` so torch is NOT imported at module level. Let pipeline stages import it on demand. Offer `build:sidecar-cpu` vs `build:sidecar-gpu` CI variants.

3. **WebSocket Endpoint Design**
   - What we know: FastAPI service has no WebSocket endpoints. The frontend has `backend.ts` ready to call them. Tauri v2 needs `@tauri-apps/plugin-websocket`.
   - What's unclear: Whether WebSocket progress is essential for Phase 10 or can be added later (polling via TanStack Query may suffice for MVP).
   - Recommendation: Implement polling-first (TanStack Query refetchInterval), add WebSocket as enhancement once core views work.

4. **Coexistence Pre-Spawn Health Check Scope**
   - What we know: `App.tsx` boot sequence catches the spawn error and falls back to `checkHealth()` — this partially implements coexistence. The `lib.rs` `start_sidecar` command does not do a pre-spawn check.
   - What's unclear: Whether the current error-fallback approach is sufficient or whether a clean pre-spawn check is needed.
   - Recommendation: Add explicit pre-spawn HTTP health check in `start_sidecar` Rust command. Return a flag indicating whether sidecar was spawned or attached. Use this flag to gate shutdown behavior.

5. **Transcript/Filler Toggle API**
   - What we know: The spec requires a View 3 transcript timeline where operators can toggle filler words. The existing `service/routes/jobs.py` has no transcript-editing endpoints.
   - What's unclear: Whether the transcript data (filler words, timestamps) needs a new REST endpoint or can be derived from existing job stage outputs.
   - Recommendation: Map this gap during subtask 10-06. The analyze stage likely produces transcript JSON; the frontend may be able to read it from job outputs without a new API endpoint.

---

## Sources

### Primary (HIGH confidence)

- [Tauri v2 Sidecar Official Docs](https://v2.tauri.app/develop/sidecar/) - externalBin config, Rust spawn API, permissions, naming convention
- [Tauri v2 WebSocket Plugin](https://v2.tauri.app/plugin/websocket/) - Installation, connect API, permissions
- [Tauri v2 Webview API](https://v2.tauri.app/reference/javascript/api/namespacewebview/) - onDragDropEvent, DragDropEvent payload structure
- [Tauri v2 Updater Plugin](https://v2.tauri.app/plugin/updater/) - Auto-update config, key generation
- [Tauri GitHub Actions Pipeline](https://v2.tauri.app/distribute/pipelines/github/) - CI/CD matrix workflow
- [TailwindCSS v4 Vite Guide](https://tailwindcss.com/docs/guides/vite) - @tailwindcss/vite plugin
- Direct codebase inspection: `desktop/` directory — all source files read and documented above

### Secondary (MEDIUM confidence)

- [Building Production-Ready Desktop LLM Apps: Tauri, FastAPI, PyInstaller](https://aiechoes.substack.com/p/building-production-ready-desktop) - Production PyInstaller spec, UTF-8 fix, sidecar config
- [example-tauri-v2-python-server-sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar) - process.kill() limitation for PyInstaller one-file, stdin/stdout pattern
- [Tauri Core Ecosystem Releases](https://v2.tauri.app/release/) - Version 2.10.2 confirmed as latest stable

### Tertiary (LOW confidence - needs validation)

- Community WebSearch findings about PyInstaller CUDA bundle sizes (2-4 GB claim) — multiple sources agree but no 2025 benchmarks for this exact dep set
- Wavesurfer.js multitrack "experiments" status — confirmed via examples page listing, stability unverified
- ctranslate2 + PyInstaller Windows DLL collection — based on similar ML library patterns, not faster-whisper specific. **Must validate** during subtask 10-02.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Tauri v2 APIs verified against official docs; existing package.json confirms all installed versions
- Architecture (sidecar spawn/shutdown): HIGH — verified against existing working code; patterns documented from actual source files
- PyInstaller ML bundling: MEDIUM — general pattern verified; `--onefile` vs `--onedir` gap and faster-whisper/ctranslate2 specific DLL collection needs empirical validation
- Distribution CI/CD: HIGH — existing `desktop-release.yml` is complete and working
- Gap analysis: HIGH — based on direct codebase inspection of all source files

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (30 days; Tauri releases frequently but v2.x APIs are stable)

---
