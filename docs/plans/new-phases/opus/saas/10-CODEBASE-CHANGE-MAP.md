# Codebase Change Map — Existing Files That Must Be Modified

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Not Yet Implemented
**Scope:** Every existing file that must change for SaaS + Desktop features to work.
**Rule:** NEW files (new modules, new routes, new services) are documented in other plans. This document covers ONLY modifications to files that already exist today.

---

## How to Read This Document

Each entry follows this format:

```
### File: `relative/path/to/file.py`
- **Lines of code today:** N
- **Change type:** Additive | Breaking | Structural
- **Needed for:** SaaS | Desktop | Both

#### Change 1: Short description
- **Target:** `ClassName.method_name()` (line N)
- **What:** Detailed description of modification
- **Why:** Rationale / what breaks without it
- **Dependencies:** Other changes that must happen first or alongside
```

**Change types:**
- **Additive** = new code added, existing behavior unchanged (backward-compatible)
- **Breaking** = existing behavior changes; old clients/tests may fail
- **Structural** = file reorganization, import changes, signature changes

---

## Priority Order

Changes are grouped by implementation order. Groups must be completed sequentially; changes within a group can be parallelized.

| Group | Description | Prerequisite |
|:-----:|-------------|:------------:|
| **A** | Auth infrastructure (JWT, user context) | None |
| **B** | Data model changes (Job, schemas) | A |
| **C** | Pipeline + route scoping (user isolation) | A + B |
| **D** | Feature gates + billing enforcement | A + B + C |
| **E** | Desktop-specific (updater, entitlements, CI) | None (parallel to A–D) |
| **F** | Frontend API client updates | B + C |

---

## Group A — Auth Infrastructure

### File: `src/podcast_pipeline/service/app.py`

- **Lines of code today:** 280
- **Change type:** Structural + Breaking
- **Needed for:** SaaS

#### A1: Evolve `ServiceAuthPolicy` → dual-mode auth (API key + JWT)

- **Target:** `ServiceAuthPolicy` class (lines 86–105)
- **What:** The current auth system supports a single shared API key. For SaaS, it must also accept Supabase JWTs with per-user identity. Keep the API key path for CLI/self-hosted/backward compat. Add a `mode: Literal["api_key", "jwt", "both"]` field.
- **Why:** Without this, there's no way to identify *which user* is making a request — all requests look identical.
- **Dependencies:** New `service/auth.py` module (Supabase JWT validator) must be created first.

#### A2: Modify `require_service_auth()` dependency (lines 134–149)

- **Target:** `require_service_auth()` function
- **What:** Currently validates `X-API-Key` header only. Must be extended to also accept `Authorization: Bearer <jwt>` header. When JWT is present, decode it via Supabase, extract `user_id`, `team_id`, and `tier` from claims, and attach them to `request.state.user`. When API key is present (CLI/self-hosted), attach a synthetic "local" user.
- **Why:** Every downstream route handler needs `request.state.user` to scope data access by user.
- **Dependencies:** A1

```python
# Current signature (preserving backward compat):
async def require_service_auth(
    request: Request,
    x_api_key: ... = None,
    authorization: Annotated[str | None, Header()] = None,  # ← ADD THIS
) -> None:
    # If JWT present → decode, verify, set request.state.user
    # Elif API key present → existing logic + set request.state.user = LocalUser
    # Else → 401
```

#### A3: Extend `lifespan()` to initialize SaaS clients (lines 152–192)

- **Target:** `lifespan()` async context manager
- **What:** Add initialization of:
  - `app.state.supabase_client` — Supabase client for JWT verification
  - `app.state.redis` — Redis connection for usage counters + rate limiting (if `saas.enabled`)
  - `app.state.stripe_client` — Stripe client (if `saas.enabled`)
  - `app.state.feature_gate` — feature gate registry keyed by tier
- **Why:** These are long-lived connections that must be created once at startup and shared across requests. The existing pattern already does this for `pipeline`, `supervisor`, and `auth_policy`.
- **Dependencies:** New `config/settings.py` SaaS section (B5)

```python
# Add AFTER line 167 (after service_auth_policy):
if config.saas.enabled:
    app.state.supabase_client = create_supabase_client(config.saas.supabase_url, ...)
    app.state.redis = await aioredis.from_url(config.saas.redis_url)
    app.state.feature_gate = FeatureGate(config.saas.tiers)
```

#### A4: Add `app.state.user` cleanup on shutdown

- **Target:** `lifespan()` — shutdown block (lines 187–192)
- **What:** Close Redis connection, clean up Supabase client on shutdown.
- **Why:** Proper resource cleanup prevents connection leaks.
- **Dependencies:** A3

---

## Group B — Data Model Changes

### File: `src/podcast_pipeline/models/job.py`

- **Lines of code today:** 225
- **Change type:** Structural (backward-compat migration required)
- **Needed for:** SaaS

#### B1: Add `user_id` and `team_id` fields to `Job` model (line 64–71)

- **Target:** `Job` class fields
- **What:** Add two new optional fields:
  ```python
  user_id: str | None = Field(None, description="Owner user ID (SaaS mode)")
  team_id: str | None = Field(None, description="Team/org ID (SaaS mode)")
  ```
- **Why:** Without `user_id`, every user sees every job. Multi-tenancy is impossible.
- **Dependencies:** None
- **Migration:** Fields default to `None` so existing `state.json` files deserialize without error. Self-hosted (no SaaS) continues to work with `user_id=None`.

#### B2: Add `tier` metadata to job config (line 71)

- **Target:** `Job.config` dict field
- **What:** When a SaaS user creates a job, persist `{"tier": "pro", "max_quality": "ultra"}` in `job.config` so the render stage knows the user's tier at execution time (decoupled from request context).
- **Why:** Background jobs run asynchronously via the Supervisor — they don't have access to `request.state.user`. The tier must be persisted at creation time.
- **Dependencies:** B1

#### B3: Scope `Job.save()` and `Job.load()` (lines 126–143)

- **Target:** `Job.save()` and `Job.load()` class methods
- **What:** Currently saves to `{jobs_dir}/{job_id}/state.json`. For SaaS, needs optional per-user subdirectory: `{jobs_dir}/{user_id}/{job_id}/state.json`. Add `user_dir: Path | None` parameter.
- **Why:** Filesystem-level isolation prevents user A from guessing user B's job_id and loading their state.
- **Dependencies:** B1
- **Alternative:** Keep flat directory, enforce user check in route handlers. Simpler but less defense-in-depth.

### File: `src/podcast_pipeline/service/schemas.py`

- **Lines of code today:** 260
- **Change type:** Additive
- **Needed for:** SaaS

#### B4a: Add `user_id` to response schemas

- **Target:** `JobDetailResponse` (line 134), `JobSummary` (line 151), `CreateJobResponse` (line 53)
- **What:** Add `user_id: str | None = None` to all response models. Self-hosted returns `None`; SaaS returns the user ID.
- **Why:** The frontend needs to know who owns a job for display and access control.
- **Dependencies:** B1

#### B4b: Add SaaS-specific schemas

- **Target:** New schemas at end of file
- **What:** Add: `UserProfile`, `TierInfo`, `UsageResponse`, `FeatureGateResponse`
- **Why:** New SaaS endpoints need typed request/response models.
- **Dependencies:** None (additive)

### File: `src/podcast_pipeline/config/settings.py`

- **Lines of code today:** 1134
- **Change type:** Additive
- **Needed for:** SaaS

#### B5: Add `SaaSConfig` section to `Config`

- **Target:** End of file, new Pydantic model class
- **What:** Add a new config section:
  ```python
  class SaaSConfig(BaseModel):
      enabled: bool = False
      supabase_url: str = ""
      supabase_anon_key: str = ""
      stripe_secret_key: str = ""
      stripe_webhook_secret: str = ""
      redis_url: str = "redis://localhost:6379"
      tiers: dict[str, TierConfig] = Field(default_factory=dict)
  ```
- **Why:** All SaaS behavior is gated behind `config.saas.enabled = True`. When `False`, the system works exactly as it does today. Zero behavior change for self-hosted.
- **Dependencies:** None

#### B5b: Add `SaaSConfig` to `Config` root model

- **Target:** `Config` class (find in settings.py — has fields like `paths`, `model`, `transcription`, etc.)
- **What:** Add: `saas: SaaSConfig = Field(default_factory=SaaSConfig)`
- **Dependencies:** B5

#### B5c: Export `SaaSConfig` from `config/__init__.py`

- **Target:** `src/podcast_pipeline/config/__init__.py` (line 3–17)
- **What:** Add `SaaSConfig` to imports and `__all__`
- **Dependencies:** B5

---

## Group C — Pipeline & Route Scoping

### File: `src/podcast_pipeline/pipeline.py`

- **Lines of code today:** 286
- **Change type:** Structural
- **Needed for:** SaaS

#### C1: Add `user_id` parameter to `Pipeline.create_job()` (lines 37–78)

- **Target:** `Pipeline.create_job()` signature
- **What:** Add `user_id: str | None = None` parameter. When provided, set `job.user_id = user_id`. When `config.saas.enabled` and user_id is provided, save to `{jobs_dir}/{user_id}/{job_id}/`.
- **Why:** Jobs must be owned by a user in SaaS mode.
- **Dependencies:** B1

#### C2: Scope `Pipeline.list_jobs()` by user (lines 92–126)

- **Target:** `Pipeline.list_jobs()` method
- **What:** Add `user_id: str | None = None` parameter. When provided, only scan `{jobs_dir}/{user_id}/` instead of all directories. When `None` (CLI/self-hosted), scan everything (current behavior).
- **Why:** Without this, `GET /jobs` returns ALL users' jobs to everyone.
- **Dependencies:** B1, C1

#### C3: Scope `Pipeline.load_job()` with ownership check (lines 80–90)

- **Target:** `Pipeline.load_job()` method
- **What:** Add `user_id: str | None = None` parameter. After loading, verify `job.user_id == user_id` (when user_id is provided). Raise `PermissionError` if mismatch.
- **Why:** Prevents user A from loading user B's job by guessing job_id.
- **Dependencies:** B1

### File: `src/podcast_pipeline/service/routes/jobs.py`

- **Lines of code today:** 538
- **Change type:** Structural
- **Needed for:** SaaS

#### C4: Thread `user_id` through all route handlers

- **Target:** ALL route handlers (11 functions: `create_job`, `get_resumable_jobs`, `reconcile_jobs`, `run_job`, `run_job_background`, `get_job`, `delete_job`, `list_jobs`, `resume_job`, plus helpers `_get_pipeline`, `_load_job_or_404`)
- **What:** Each handler must extract `user = request.state.user` (set by auth middleware from Group A) and pass `user.user_id` to Pipeline methods.
- **Why:** Every data access operation must be scoped to the authenticated user.
- **Dependencies:** A2, C1, C2, C3

Specific changes per handler:

| Handler | Line | Change |
|---------|------|--------|
| `_load_job_or_404()` | 93 | Add `user_id` param, pass to `pipeline.load_job(job_id, user_id=user_id)` |
| `create_job()` | 154 | Pass `user.user_id` to `pipeline.create_job()` |
| `list_jobs()` | 395 | Pass `user.user_id` to `pipeline.list_jobs()` |
| `get_job()` | 318 | Pass `user.user_id` to `_load_job_or_404()` |
| `run_job()` | 229 | Pass `user.user_id` to `_load_job_or_404()` |
| `run_job_background()` | 280 | Pass `user.user_id` to `_load_job_or_404()` |
| `delete_job()` | 331 | Pass `user.user_id` to `_load_job_or_404()` |
| `resume_job()` | 418 | Pass `user.user_id` to `_load_job_or_404()` |
| `get_resumable_jobs()` | 182 | Scope `list_resumable_jobs()` by user |
| `reconcile_jobs()` | 213 | Scope `reconcile_all_jobs()` by user |

#### C5: Scope `_upload_is_referenced_by_other_job()` (lines 54–78)

- **Target:** `_upload_is_referenced_by_other_job()`
- **What:** Currently iterates ALL job directories. Must be scoped to user's directory only.
- **Dependencies:** C4

### File: `src/podcast_pipeline/service/recovery.py`

- **Lines of code today:** 328
- **Change type:** Structural
- **Needed for:** SaaS

#### C6: Scope reconciliation functions by user

- **Target:** `reconcile_all_jobs()` (line 131), `list_resumable_jobs()` (line 189), `startup_reconcile()` (line 310), `periodic_reconcile()` (line 154)
- **What:** Add `user_id: str | None = None` parameter to scope directory scanning. When `None`, reconcile everything (startup, CLI). When provided, only reconcile that user's jobs.
- **Why:** Background reconciliation touches all jobs — fine for self-hosted. For SaaS, per-user reconciliation prevents one user's corrupt state from affecting another user's requests.
- **Dependencies:** C1

### File: `src/podcast_pipeline/service/supervisor.py`

- **Lines of code today:** 455
- **Change type:** Additive
- **Needed for:** SaaS

#### C7: Add user context to `RuntimeMeta`

- **Target:** `RuntimeMeta.__init__()` (line 209)
- **What:** Add optional `user_id: str | None = None` field so runtime journals record who launched the job.
- **Why:** The runtime diagnostics endpoint (`/system/runtime`) would leak other users' job PIDs without scoping.
- **Dependencies:** B1

---

## Group D — Feature Gates & Billing Enforcement

### File: `src/podcast_pipeline/service/routes/jobs.py`

- **Change type:** Additive
- **Needed for:** SaaS

#### D1: Add `Depends(require_feature("feature_name"))` to specific routes

- **Target:** Route decorators for `create_job`, `run_job`, `run_job_background`, `resume_job`
- **What:** Add a FastAPI dependency that checks the user's tier against the feature registry before allowing the endpoint to execute. Example:
  ```python
  @router.post("", dependencies=[Depends(require_feature("create_job"))])
  async def create_job(...):
  ```
- **Why:** Free-tier users should be blocked from exceeding their job count, using ultra quality, etc.
- **Dependencies:** A2 (user identity), new `service/feature_gate.py` module

#### D2: Add usage counter check to `create_job()`

- **Target:** `create_job()` handler (line 154)
- **What:** Before creating the job, check Redis counter: `jobs_this_month:{user_id}`. If >= tier limit, return HTTP 402. After successful creation, increment counter.
- **Why:** Free tier has limited monthly jobs (e.g., 5/month).
- **Dependencies:** A3 (Redis on `app.state`), D1

### File: `src/podcast_pipeline/stages/render.py`

- **Lines of code today:** 3970
- **Change type:** Additive
- **Needed for:** SaaS

#### D3: Enforce tier quality ceiling in `_resolve_quality_controls()` (lines 385–409)

- **Target:** `RenderStage._resolve_quality_controls()`
- **What:** After resolving quality from `job.config`, clamp it to the tier's max quality:
  ```python
  tier_max_quality = job.config.get("max_quality", "ultra")
  QUALITY_RANK = {"draft": 0, "standard": 1, "high": 2, "ultra": 3}
  if QUALITY_RANK.get(raw_quality, 0) > QUALITY_RANK.get(tier_max_quality, 3):
      raw_quality = tier_max_quality
      self.logger.info("quality_clamped_by_tier", requested=raw_quality, max=tier_max_quality)
  ```
- **Why:** Free users shouldn't be able to select "ultra" quality even if they manipulate the API request.
- **Dependencies:** B2 (tier persisted in `job.config`)

#### D4: Add watermark overlay for free-tier renders

- **Target:** `RenderStage._render_platform()` (main render method, after final FFmpeg export)
- **What:** If `job.config.get("tier") == "free"`, add a semi-transparent watermark overlay to the output video using an FFmpeg `overlay` filter:
  ```
  -vf "drawtext=text='Made with Podcast Pipeline':fontsize=24:fontcolor=white@0.3:x=(w-tw)/2:y=h-th-20"
  ```
- **Why:** Free-tier exports carry branding. Paid users get clean exports.
- **Dependencies:** B2
- **Location:** The `_render_platform()` method (find by searching for `def _render_platform`) builds the FFmpeg command. The watermark filter must be appended to the video filter chain AFTER all other processing.

### File: `src/podcast_pipeline/stages/base.py`

- **Lines of code today:** 137
- **Change type:** Additive
- **Needed for:** SaaS

#### D5: Add optional usage tracking hook to `Stage.execute()`

- **Target:** `Stage.execute()` (lines 61–122)
- **What:** After successful stage execution, emit a usage event that can be consumed by the billing system. Add an optional callback:
  ```python
  if self.config.saas.enabled and hasattr(self, 'usage_tracker'):
      self.usage_tracker.record_stage_completion(job.job_id, self.name, job.user_id)
  ```
- **Why:** Metered billing (transcription minutes, render count) needs per-stage usage data.
- **Dependencies:** B5 (SaaS config), A3 (Redis)

---

## Group E — Desktop Distribution (Parallel to A–D)

### File: `desktop/src-tauri/tauri.conf.json`

- **Lines of code today:** 51
- **Change type:** Additive
- **Needed for:** Desktop

#### E1: Add updater plugin configuration

- **Target:** Root JSON object
- **What:** Add:
  ```json
  "plugins": {
    "updater": {
      "active": true,
      "dialog": true,
      "endpoints": ["https://github.com/.../releases/latest/download/latest.json"],
      "pubkey": "YOUR_ED25519_PUBLIC_KEY"
    }
  }
  ```
- **Why:** Enables in-app auto-update.
- **Dependencies:** Generate signing keypair (`pnpm tauri signer generate`)

#### E2: Add NSIS installer configuration

- **Target:** `"bundle"` section
- **What:** Add `"windows": { "nsis": { "installMode": "both", "compression": "lzma" } }`
- **Why:** Configures professional Windows installer with LZMA compression.
- **Dependencies:** None

#### E3: Add macOS minimum version and entitlements

- **Target:** `"bundle"` section
- **What:** Add `"macOS": { "minimumSystemVersion": "12.0", "entitlements": "entitlements.plist" }`
- **Why:** Ensures GateKeeper compatibility and declares required permissions.
- **Dependencies:** Create `entitlements.plist` (new file, documented in `09-DESKTOP-DISTRIBUTION.md`)

### File: `.github/workflows/desktop-release.yml`

- **Lines of code today:** 278
- **Change type:** Additive
- **Needed for:** Desktop

#### E4: Add Tauri signing key secrets to build step

- **Target:** `Build Tauri application` step (line 194)
- **What:** Add environment variables:
  ```yaml
  TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
  TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_KEY_PASSWORD }}
  ```
- **Why:** Signs update bundles so the auto-updater can verify authenticity.
- **Dependencies:** E1

#### E5: Add FFmpeg license bundling step

- **Target:** After `Prepare sidecar binaries` step (line 190)
- **What:** Add a step to copy `LICENSES/ffmpeg-LICENSE.txt` into the installer bundle.
- **Why:** LGPL compliance for distributed FFmpeg binaries.
- **Dependencies:** Create `LICENSES/ffmpeg-LICENSE.txt` (new file)

### File: `desktop/src-tauri/Cargo.toml`

- **Lines of code today:** 24
- **Change type:** Additive
- **Needed for:** Desktop

#### E6: Add updater plugin dependency

- **Target:** `[dependencies]` section
- **What:** Add `tauri-plugin-updater = "2"` and `tauri-plugin-dialog = "2"` (for update dialog).
- **Dependencies:** E1

### File: `desktop/package.json`

- **Lines of code today:** 174
- **Change type:** Additive
- **Needed for:** Desktop

#### E7: Add `@tauri-apps/plugin-updater` frontend dependency

- **Target:** `dependencies` section
- **What:** `pnpm add @tauri-apps/plugin-updater`
- **Dependencies:** E6

---

## Group F — Frontend API Client Updates

### File: `desktop/src/lib/backend.ts`

- **Lines of code today:** 536
- **Change type:** Structural
- **Needed for:** SaaS + Desktop

#### F1: Add auth header to all API requests

- **Target:** `requestJson()` function (lines 495–527)
- **What:** If a JWT is stored (from Supabase login), include `Authorization: Bearer ${token}` in every request. Store token in a module-level variable or Zustand store.
  ```typescript
  let authToken: string | null = null;
  export function setAuthToken(token: string | null) { authToken = token; }

  // Inside requestJson():
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  ```
- **Why:** Without auth headers, the SaaS backend rejects all requests from the desktop client.
- **Dependencies:** A2 (backend accepts JWT)

#### F2: Add `user_id` to TypeScript interfaces

- **Target:** `JobSummary`, `JobDetail`, `CreateJobResponse` interfaces
- **What:** Add `user_id?: string | null` to match updated backend schemas.
- **Dependencies:** B4a

#### F3: Add new SaaS API methods

- **Target:** End of file (new exports)
- **What:** Add typed client methods for:
  - `getProfile(): Promise<UserProfile>`
  - `getUsage(): Promise<UsageResponse>`
  - `getTierInfo(): Promise<TierInfo>`
  - `checkFeatureAccess(feature: string): Promise<boolean>`
- **Dependencies:** B4b (new schemas)

### File: `desktop/src/hooks/useJobs.ts`

- **Change type:** Additive
- **Needed for:** SaaS

#### F4: Include auth context in job queries

- **Target:** Job list query hook
- **What:** Ensure the query key includes the user identity so that switching users invalidates the cache.
- **Dependencies:** F1

### File: `desktop/src/stores/sidecarStore.ts`

- **Change type:** Additive
- **Needed for:** SaaS

#### F5: Add auth state management

- **Target:** Store definition
- **What:** Add `user: UserProfile | null`, `token: string | null`, `isAuthenticated: boolean`, `login()`, `logout()` to the store (or create a separate `authStore.ts`).
- **Dependencies:** F1

---

## Files That Need NO Changes

For completeness, these existing files do **NOT** need modification:

| File | Why No Change |
|------|--------------|
| `stages/ingest.py` | Media ingestion is tier-agnostic |
| `stages/transcribe.py` | Transcription config unchanged; usage metering is handled at `base.py` level |
| `stages/analyze.py` | Analysis logic is tier-agnostic |
| `stages/review.py` | Review decisions are user-scoped naturally (per job) |
| `utils/*.py` (all 16 files) | Pure utility functions, no auth/billing awareness needed |
| `models/analysis.py` | Data models, no user scoping needed |
| `models/branding.py` | Data models, no user scoping needed |
| `models/edit_plan.py` | Data models, no user scoping needed |
| `models/transcript.py` | Data models, no user scoping needed |
| `service/cli.py` | CLI entry point; unchanged for SaaS (only used in PyInstaller sidecar) |
| `service/assets.py` | Asset resolution; no auth awareness needed |
| `desktop/src-tauri/build.rs` | Build-time validation; already supports --onedir |
| `desktop/scripts/prepare-sidecars.mjs` | Build script; no runtime changes |
| `desktop/scripts/smoke-test-desktop.sh` | Test script; no SaaS logic |
| `desktop/src/views/*.tsx` | UI views render job data; they consume hooks, not raw API |

---

## Change Dependency Graph

```
                    ┌──────────────┐
                    │ B5: SaaSConfig│
                    │  (settings.py)│
                    └──────┬───────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
   ┌───────────────┐ ┌──────────────┐ ┌──────────────┐
   │ A1: AuthPolicy│ │ B1: Job.     │ │ B4: Schema   │
   │   (app.py)    │ │   user_id    │ │   updates    │
   └──────┬────────┘ └──────┬───────┘ └──────────────┘
          │                 │
          ▼                 ▼
   ┌───────────────┐ ┌──────────────┐
   │ A2: JWT auth  │ │ C1: Pipeline │
   │  middleware   │ │   .create_job│
   └──────┬────────┘ └──────┬───────┘
          │                 │
          ▼                 ▼
   ┌───────────────┐ ┌──────────────┐
   │ A3: Lifespan  │ │ C4: Route    │
   │  Redis/Stripe │ │   scoping    │
   └──────┬────────┘ └──────┬───────┘
          │                 │
          └────────┬────────┘
                   ▼
           ┌───────────────┐
           │ D1–D4: Feature│
           │  gates/billing│
           └───────────────┘

    (Group E is independent → runs in parallel)

   ┌────────────────┐
   │ E1–E7: Desktop │
   │  (Tauri config, │
   │   CI, updater)  │
   └────────────────┘
```

---

## Summary Statistics

| Metric | Count |
|--------|------:|
| **Existing files modified** | 16 |
| **Individual change items** | 31 |
| **Breaking changes** | 3 (A1, A2, C4 — auth evolution) |
| **Additive changes** | 22 |
| **Structural changes** | 6 |
| **Files explicitly NOT changed** | 22 |
| **New files required** (documented elsewhere) | ~8–12 (auth module, feature gate, billing routes, Stripe webhooks, etc.) |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| Auth migration breaks CLI users | Medium | High | Feature-flag the JWT path; API key continues to work when `saas.enabled=False` |
| `state.json` deserialization fails with new fields | Low | High | Use `Field(default=None)` — Pydantic ignores missing optional fields |
| Route scoping misses an endpoint | Medium | Critical | Add integration test: "user A cannot access user B's job" for every endpoint |
| Render watermark changes break platform compliance | Low | Medium | Apply watermark AFTER compliance checks, not before |
| Desktop updater misconfigured | Low | Medium | Test update cycle (v0.0.1 → v0.0.2) before real release |
| Redis unavailable at startup blocks all requests | Medium | High | Guard all Redis calls with `app.state.redis is not None`; SaaS features degrade gracefully |

---

*This document should be the implementation companion to documents 01–09. Each change item can be directly translated into a task in the implementation roadmap (doc 03). No existing file is modified without a corresponding entry here.*
