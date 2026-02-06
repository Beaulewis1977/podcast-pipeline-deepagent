# Phase 03: Polishing + Desktop Distribution - Research

**Researched:** 2026-02-05
**Domain:** Tauri v2 desktop distribution with Python FastAPI sidecar backend
**Confidence:** MEDIUM

## Summary

Phase 03 should standardize on a sidecar architecture: keep the existing Python pipeline as the single job engine, expose it as a local FastAPI service, and run that service from a Tauri v2 desktop shell. This avoids duplicating pipeline logic in desktop code and lets Streamlit and Tauri use the same backend contract.

For packaging, the stable path is to build the Python service as a standalone executable (PyInstaller), register it as a Tauri sidecar (`bundle.externalBin`), and bundle desktop installers with Tauri’s platform bundle targets. Tauri v2 sidecar naming conventions and capabilities permissions are non-optional for reliable cross-platform launches.

Crash recovery should build on the project’s existing `jobs/<job_id>/state.json` model and add a small desktop-facing run journal (active jobs, PID, last heartbeat, restart intent). On app startup, Tauri can restore in-progress jobs by reading persisted state and reconnecting/restarting the backend sidecar.

**Primary recommendation:** Build a contract-first FastAPI job-runner service and ship it as a PyInstaller sidecar controlled by Tauri v2 `plugin-shell`, with durable state in app data and bundled installers via Tauri.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Tauri | v2 docs current (2026-01 docs update) | Cross-platform desktop shell + bundling | Official Tauri v2 supports sidecars, capabilities, and installer formats across Windows/macOS/Linux |
| `@tauri-apps/plugin-shell` + Tauri shell extension | v2 line | Launch/manage sidecar binaries | Officially documented path for external executable sidecars |
| FastAPI | 0.128.x docs line used in research | Local backend API for jobs | Clean async API layer, good lifecycle hooks, simple desktop local service model |
| Uvicorn | FastAPI standard ASGI server | Run local FastAPI sidecar server | Standard FastAPI runtime |
| PyInstaller | 6.14.x docs line used in research | Freeze Python service into standalone binary | Removes end-user Python dependency on clean machines |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@tauri-apps/api/path` | v2 | Resolve `appDataDir`/`appLocalDataDir` paths | Persist job metadata and crash-recovery pointers in OS-appropriate app dirs |
| `@tauri-apps/plugin-store` | v2 | Persistent key-value state across Rust/JS | Store desktop settings + restart/recovery metadata |
| Existing `podcast_pipeline.pipeline.Pipeline` + `Job` models | Current repo | Job orchestration + resumable stage state | Reuse as service core; do not rewrite in Rust/UI |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Tauri sidecar model | Electron + Python backend | Faster ecosystem familiarity for some teams, but heavier runtime and larger bundles |
| Packaged sidecar binary | Require system Python + pip deps | Easier dev setup, but fails “clean machine no manual setup” goal |
| Local HTTP backend | Pure invoke commands with full logic in Rust | Lower network surface, but duplicates mature Python pipeline logic |

**Installation:**
```bash
# Python service runtime/build
uv add fastapi uvicorn pyinstaller

# Tauri desktop side
pnpm add @tauri-apps/plugin-shell @tauri-apps/plugin-store @tauri-apps/api
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── podcast_pipeline/
│   ├── pipeline.py                 # Existing orchestrator (reuse)
│   ├── models/job.py               # Existing durable state (reuse)
│   └── service/                    # New FastAPI job-runner service
│       ├── app.py                  # FastAPI app + lifespan
│       ├── routes/jobs.py          # create/run/status/resume endpoints
│       └── supervisor.py           # sidecar-local process/job supervision
src-tauri/
├── src/main.rs                     # Sidecar lifecycle and app wiring
├── tauri.conf.json                 # externalBin and bundle config
├── capabilities/default.json       # shell permissions for sidecar
└── binaries/                       # sidecar binaries with target triples
```

### Pattern 1: Contract-First Job Runner Service
**What:** Expose pipeline actions (`create`, `run`, `status`, `resume`) as stable HTTP endpoints so both Streamlit and Tauri consume the same API contract.
**When to use:** Any feature currently implemented directly in UI logic.
**Example:**
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: create shared pipeline/service deps
    yield
    # shutdown: flush state, stop workers cleanly

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

### Pattern 2: Tauri Sidecar Binary with Capabilities
**What:** Package Python service as sidecar and launch via shell plugin with explicit capability rules.
**When to use:** Desktop startup and backend recovery/restart paths.
**Example:**
```json
{
  "bundle": {
    "externalBin": ["binaries/podcast-backend"]
  }
}
```
```typescript
import { Command } from "@tauri-apps/plugin-shell";

const cmd = Command.sidecar("binaries/podcast-backend", ["--port", "8787"]);
await cmd.spawn();
```

### Pattern 3: Durable Resume State in App Data
**What:** Keep job truth in `state.json`; store desktop runtime pointers (active job IDs, last heartbeat, backend port/PID metadata) in app-local data/store.
**When to use:** App restart, crash recovery, and “resume after restart” flows.
**Example:**
```typescript
import { appLocalDataDir, join } from "@tauri-apps/api/path";

const base = await appLocalDataDir();
const resumeFile = await join(base, "resume-index.json");
```

### Anti-Patterns to Avoid
- **UI-owned pipeline logic:** Causes behavior drift between Streamlit and desktop.
- **Unpinned sidecar naming:** Missing target-triple suffix breaks packaged launches.
- **No capability config:** Sidecar launch blocked by Tauri v2 permission model.
- **State only in memory:** Makes crash recovery impossible.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-platform installer generation | Custom per-OS scripting pipeline | Tauri bundle targets | Official formats and signing flows are already supported |
| Sidecar process permission model | Ad-hoc execution exceptions | Tauri capabilities (`shell:allow-execute`/`allow-spawn`) | Safer and aligned with v2 security model |
| Python runtime shipping | Manual venv copying | PyInstaller binary packaging | Reliable clean-machine experience |
| Desktop settings persistence | Custom JSON sync glue across Rust/JS | `@tauri-apps/plugin-store` | Shared Rust + JS access model already solved |
| Whisper model acquisition | Custom download protocol first | Built-in model pull from Hugging Face via `WhisperModel("...")` | Existing behavior already supported by faster-whisper |

**Key insight:** Keep the custom work focused on your job orchestration contract and recovery semantics, not on packaging primitives that Tauri/PyInstaller already solve.

## Common Pitfalls

### Pitfall 1: Sidecar Launch Works in Dev but Fails in Bundle
**What goes wrong:** Binary starts in `tauri dev` but is missing/badly named in packaged app.
**Why it happens:** `externalBin` path or target-triple naming is wrong.
**How to avoid:** Add a build step that renames binaries with host target triple and validates expected files before bundle.
**Warning signs:** `Command.sidecar(...)` works locally, fails only from installer build.

### Pitfall 2: Multiple Backend Instances and Port Collisions
**What goes wrong:** UI spawns duplicate service processes; status polling becomes inconsistent.
**Why it happens:** No single ownership for process lifecycle and health checks.
**How to avoid:** Centralize lifecycle in Tauri Rust layer with health probe + singleton lock behavior.
**Warning signs:** Random “address already in use” and stale job status.

### Pitfall 3: Resume Metadata and Job Truth Drift
**What goes wrong:** App “thinks” job is running while `state.json` says failed/stopped.
**Why it happens:** Recovery index is not reconciled against canonical job state.
**How to avoid:** Reconcile desktop runtime metadata with `jobs/<job_id>/state.json` at startup before marking resumable jobs.
**Warning signs:** Resume button appears but restart fails immediately.

### Pitfall 4: Unsafe FFmpeg Invocation Surface
**What goes wrong:** User-controlled arguments create command-injection risk or non-portable behavior.
**Why it happens:** Building command strings directly instead of validated argument arrays.
**How to avoid:** Structured argument builders + explicit allowlists + Tauri shell capabilities.
**Warning signs:** Raw shell string interpolation and unvalidated file paths.

## Code Examples

Verified patterns from official sources:

### Sidecar Configuration (Tauri v2)
```json
{
  "bundle": {
    "externalBin": ["binaries/podcast-backend"]
  }
}
```

### Sidecar Execution from Frontend
```typescript
import { Command } from "@tauri-apps/plugin-shell";

const command = Command.sidecar("binaries/podcast-backend", ["--port", "8787"]);
await command.execute();
```

### FastAPI Lifespan for Service Initialization
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # initialize long-lived resources
    yield
    # cleanup

app = FastAPI(lifespan=lifespan)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Desktop wrappers that depend on system Python | Packaged Python sidecar executable | Became common in 2024-2026 Tauri/Python templates | Supports clean-machine installs |
| Tauri v1 allowlist model | Tauri v2 capabilities permissions | Tauri v2 era | More explicit sidecar security and command control |
| App-specific installer scripts | Built-in Tauri bundle targets | Ongoing Tauri v2 docs line | Faster cross-platform release workflows |

**Deprecated/outdated:**
- Running desktop backend by assuming user-installed Python + dependencies.
- Using UI process state alone as source of truth for resumable jobs.

## Open Questions

1. **Backend transport split (invoke vs HTTP)**
   - What we know: Local HTTP service is proven and reusable across Streamlit + Tauri.
   - What's unclear: Which operations should remain pure Tauri invoke commands vs HTTP endpoints.
   - Recommendation: Keep job control/data paths on HTTP; reserve invoke for desktop host operations.

2. **FFmpeg packaging strategy**
   - What we know: Sidecar/external binary packaging is officially supported in Tauri.
   - What's unclear: Whether to bundle FFmpeg as separate sidecar binaries or rely on alternative Python/packaged libs for selected stages.
   - Recommendation: Start with explicit sidecar binary packaging for deterministic behavior.

3. **Model artifact policy**
   - What we know: faster-whisper can auto-download model artifacts from Hugging Face.
   - What's unclear: Offline-first expectation vs first-run download UX and cache location policy.
   - Recommendation: Make model download optional but explicit with progress + retry/resume.

4. **`saas docs` tooling reliability**
   - What we know: Context7 key is present, but `saas docs` currently returns HTTP 400 for all queries.
   - What's unclear: CLI bug vs API compatibility issue.
   - Recommendation: Keep Context7 MCP + official-doc fallback in planning/execution until CLI behavior is fixed.

## Sources

### Primary (HIGH confidence)
- Context7 `/tauri-apps/tauri-docs` — sidecar config (`externalBin`), `Command.sidecar`, capabilities, target triple conventions.
- Context7 `/fastapi/fastapi/0.128.0` — lifespan pattern and deployment/runtime commands.
- Context7 `/pyinstaller/pyinstaller/v6.14.1` — `--onefile`, `--onedir`, `--add-binary`, `--add-data`.
- Tauri sidecar docs source: https://raw.githubusercontent.com/tauri-apps/tauri-docs/v2/src/content/docs/develop/sidecar.mdx
- Tauri distribute docs source: https://raw.githubusercontent.com/tauri-apps/tauri-docs/v2/src/content/docs/distribute/index.mdx
- Tauri plugin store docs: https://raw.githubusercontent.com/tauri-apps/plugins-workspace/v2/plugins/store/README.md
- faster-whisper README: https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/README.md

### Secondary (MEDIUM confidence)
- `saas ask` (Perplexity SONAR) outputs on:
  - Tauri v2 + Python sidecar architecture
  - crash recovery patterns for sidecar-managed jobs
  - FFmpeg bundling options in Tauri ecosystems

### Tertiary (LOW confidence)
- Mentions of third-party FFmpeg-specific Tauri plugins from SONAR output without full official validation in this research pass.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - based on official docs and Context7.
- Architecture: MEDIUM - core pattern is well-supported; exact process-supervisor details are project-specific.
- Pitfalls: MEDIUM - supported by docs + common failure patterns; some are operational inferences.

**Research date:** 2026-02-05
**Valid until:** 2026-03-07 (30 days; recheck Tauri/FastAPI/PyInstaller docs before implementation start)
