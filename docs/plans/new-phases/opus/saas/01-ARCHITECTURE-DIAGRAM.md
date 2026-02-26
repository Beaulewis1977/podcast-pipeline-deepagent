# SaaS Architecture Diagram

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Reference:** `00-SAAS-MASTER-PLAN.md`

---

## 1. High-Level SaaS Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI PODCAST STUDIO — SaaS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────────┐                 │
│  │  Streamlit   │   │  Tauri v2    │   │  Public API      │                 │
│  │  Web Client  │   │  Desktop    │   │  (Team/Agency)   │                 │
│  │  (Browser)   │   │  (Local GPU)│   │  REST + Webhooks │                 │
│  └──────┬───────┘   └──────┬──────┘   └────────┬─────────┘                 │
│         │                  │                    │                           │
│         └──────────────────┼────────────────────┘                           │
│                            │                                                │
│                     ┌──────▼──────┐                                         │
│                     │  API Gateway │                                        │
│                     │  (FastAPI)   │                                        │
│                     │             │                                         │
│                     │ ┌─────────┐ │                                         │
│                     │ │ Auth MW │ │ ← JWT verification (every request)     │
│                     │ └─────────┘ │                                         │
│                     │ ┌─────────┐ │                                         │
│                     │ │ Tier    │ │ ← Feature gate enforcement              │
│                     │ │ Gate MW │ │                                         │
│                     │ └─────────┘ │                                         │
│                     │ ┌─────────┐ │                                         │
│                     │ │ Rate    │ │ ← Per-user rate limiting (Redis)        │
│                     │ │ Limiter │ │                                         │
│                     │ └─────────┘ │                                         │
│                     └──────┬──────┘                                         │
│                            │                                                │
│         ┌──────────────────┼──────────────────┐                             │
│         │                  │                  │                              │
│  ┌──────▼──────┐  ┌───────▼───────┐  ┌──────▼──────┐                      │
│  │  Pipeline    │  │  AI Proxy     │  │  Publishing │                      │
│  │  Engine      │  │  Service      │  │  Service    │                      │
│  │             │  │              │  │             │                         │
│  │ • Ingest    │  │ • Gemini     │  │ • YouTube   │                        │
│  │ • Transcribe│  │ • Veo 3.1   │  │ • Spotify   │                        │
│  │ • Analyze   │  │ • Co-Pilot   │  │ • TikTok    │                        │
│  │ • Review    │  │              │  │ • Instagram │                        │
│  │ • Render    │  │ Usage ↓      │  │             │                        │
│  └──────┬──────┘  └───────┬──────┘  └──────┬──────┘                        │
│         │                 │                 │                               │
│  ┌──────▼─────────────────▼─────────────────▼──────┐                       │
│  │              BACKGROUND WORKERS                   │                     │
│  │              (Celery + Redis Queue)                │                     │
│  │                                                   │                     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │                     │
│  │  │ Render   │  │ AI       │  │ Publish      │   │                     │
│  │  │ Worker   │  │ Worker   │  │ Worker       │   │                     │
│  │  │ (GPU)    │  │ (API)    │  │ (Upload)     │   │                     │
│  │  └──────────┘  └──────────┘  └──────────────┘   │                     │
│  └──────────────────────────────────────────────────┘                      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                           DATA LAYER                                        │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  PostgreSQL   │  │  Redis        │  │  Object Store │  │  Sentry       │ │
│  │  (Supabase)   │  │  (Upstash)    │  │  (S3/R2)      │  │  (Monitoring) │ │
│  │              │  │              │  │              │  │               │  │
│  │ • users      │  │ • sessions   │  │ • job assets │  │ • crashes     │  │
│  │ • subs       │  │ • rate limits│  │ • exports    │  │ • breadcrumbs │  │
│  │ • usage_logs │  │ • usage cntrs│  │ • b-roll     │  │ • alerts      │  │
│  │ • jobs       │  │ • celery     │  │ • thumbnails │  │               │  │
│  │ • profiles   │  │ • cache      │  │ • branding   │  │               │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐                                        │
│  │  Stripe       │  │  PostHog      │                                       │
│  │  (Payments)   │  │  (Analytics)  │                                       │
│  │              │  │              │                                          │
│  │ • subs       │  │ • events     │                                         │
│  │ • invoices   │  │ • funnels    │                                         │
│  │ • metered    │  │ • cohorts    │                                         │
│  │ • webhooks   │  │ • retention  │                                         │
│  └──────────────┘  └──────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Authentication & Authorization Flow

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Client       │      │  FastAPI      │      │  Supabase     │
│  (Web/Desktop)│      │  Backend      │      │  Auth + DB    │
└──────┬───────┘      └──────┬───────┘      └──────┬───────┘
       │                     │                      │
       │  1. Sign Up/Login   │                      │
       │  (email+pass or     │                      │
       │   Google OAuth)     │                      │
       │─────────────────────┼─────────────────────→│
       │                     │                      │
       │  2. JWT + Refresh   │                      │
       │←────────────────────┼──────────────────────│
       │                     │                      │
       │  3. API Request     │                      │
       │  + Bearer JWT       │                      │
       │────────────────────→│                      │
       │                     │                      │
       │                     │  4. Verify JWT       │
       │                     │  (pyjwt + secret)    │
       │                     │                      │
       │                     │  5. Extract user_id, │
       │                     │  tier from claims     │
       │                     │                      │
       │                     │  6. Check tier gate   │
       │                     │  + rate limit (Redis) │
       │                     │                      │
       │                     │  7. Execute request   │
       │                     │  (if authorized)      │
       │                     │                      │
       │  8. Response        │                      │
       │←────────────────────│                      │
```

### JWT Claims Structure

```json
{
  "sub": "user-uuid-from-supabase",
  "email": "user@example.com",
  "tier": "pro",
  "role": "owner",
  "team_id": "team-uuid-or-null",
  "iat": 1740000000,
  "exp": 1740003600
}
```

### Tier Verification in FastAPI

```python
# auth/middleware.py

from fastapi import Depends, HTTPException, Request
from pyjwt import decode as jwt_decode

async def get_current_user(request: Request) -> UserProfile:
    """Extract and verify user from JWT Bearer token."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Missing authentication token")

    payload = jwt_decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"])
    return UserProfile(
        user_id=payload["sub"],
        email=payload["email"],
        tier=UserTier(payload.get("tier", "free")),
        team_id=payload.get("team_id"),
    )

def require_tier(minimum: UserTier):
    """Dependency that enforces minimum subscription tier."""
    async def _check(user: UserProfile = Depends(get_current_user)):
        if user.tier.value < minimum.value:
            raise HTTPException(
                403,
                f"This feature requires {minimum.name} tier. "
                f"Current tier: {user.tier.name}. Upgrade at /billing"
            )
        return user
    return _check

# Usage in routes:
@router.post("/copilot/auto-edit")
async def auto_edit(
    job_id: str,
    user: UserProfile = Depends(require_tier(UserTier.PRO)),
):
    """Auto-Edit requires Pro tier."""
    ...
```

---

## 3. Multi-Tenancy Data Isolation

```
┌─────────────────────────────────────────────────┐
│                 PostgreSQL (Supabase)             │
├─────────────────────────────────────────────────┤
│                                                   │
│  users (auth.users — managed by Supabase Auth)   │
│  ├── id (UUID)                                    │
│  ├── email                                        │
│  ├── created_at                                   │
│  └── (managed by Supabase)                       │
│                                                   │
│  profiles (public.profiles)                      │
│  ├── user_id (FK → auth.users.id)                │
│  ├── display_name                                 │
│  ├── tier (enum: free, starter, pro, team)       │
│  ├── stripe_customer_id                           │
│  ├── stripe_subscription_id                       │
│  ├── team_id (FK → teams.id, nullable)           │
│  ├── usage_reset_date (timestamp)                 │
│  └── created_at                                   │
│                                                   │
│  teams (public.teams)                            │
│  ├── id (UUID)                                    │
│  ├── name                                         │
│  ├── owner_id (FK → auth.users.id)               │
│  ├── tier (enum: team, agency)                    │
│  ├── max_seats (int)                              │
│  └── white_label_enabled (bool)                  │
│                                                   │
│  jobs (public.jobs)                              │
│  ├── id (UUID)                                    │
│  ├── user_id (FK → auth.users.id)          ← RLS │
│  ├── team_id (FK → teams.id, nullable)     ← RLS │
│  ├── name                                         │
│  ├── status                                       │
│  ├── assets_path (S3 prefix)                     │
│  └── created_at                                   │
│                                                   │
│  usage_logs (public.usage_logs)                  │
│  ├── id                                           │
│  ├── user_id (FK → auth.users.id)          ← RLS │
│  ├── action (enum: ai_call, veo_gen, render, ...) │
│  ├── units (int)                                  │
│  ├── metadata (JSONB)                             │
│  └── created_at                                   │
│                                                   │
│  RLS POLICIES:                                    │
│  • users see only their own jobs                 │
│  • team members see team jobs                    │
│  • usage_logs scoped to user                     │
│  • profiles readable by same user only           │
│                                                   │
└─────────────────────────────────────────────────┘
```

### Row Level Security (Supabase RLS)

```sql
-- Users can only see their own jobs
CREATE POLICY "Users see own jobs"
ON public.jobs FOR SELECT
USING (
    auth.uid() = user_id
    OR team_id IN (
        SELECT team_id FROM profiles WHERE user_id = auth.uid()
    )
);

-- Users can only insert their own jobs
CREATE POLICY "Users create own jobs"
ON public.jobs FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- Usage logs scoped to user
CREATE POLICY "Users see own usage"
ON public.usage_logs FOR SELECT
USING (auth.uid() = user_id);
```

---

## 4. Object Storage Layout

```
s3://podcast-studio-assets/
├── users/
│   └── {user_id}/
│       ├── jobs/
│       │   └── {job_id}/
│       │       ├── raw/               # Original uploads
│       │       │   ├── cam_main.mp4
│       │       │   ├── cam_guest.mp4
│       │       │   └── broll_city.mp4
│       │       ├── intermediate/      # Processed intermediates
│       │       │   ├── audio_16k.wav
│       │       │   └── proxy_720p.mp4
│       │       ├── output/            # Final exports
│       │       │   ├── youtube.mp4
│       │       │   ├── spotify.mp3
│       │       │   └── tiktok.mp4
│       │       └── analysis/          # AI artifacts
│       │           ├── transcript.json
│       │           └── analysis.json
│       └── branding/
│           ├── logos/
│           ├── fonts/
│           └── kits.json
└── shared/                            # White-label templates, etc.
```

---

## 5. Request Flow (End-to-End)

```
User clicks "Run Pipeline" in Streamlit/Tauri
    │
    ▼
POST /jobs/{job_id}/run
    │
    ├── 1. Auth Middleware: Verify JWT → extract user_id, tier
    │
    ├── 2. Tier Gate: Check user.tier >= required tier
    │       └── Free tier: max 5 episodes/month → check usage counter
    │
    ├── 3. Rate Limiter: Check per-user rate limit (Redis)
    │       └── slowapi: 10 req/min for free, 100 req/min for pro
    │
    ├── 4. Usage Tracker: Increment episode counter
    │       └── Redis INCR user:{id}:episodes:2026-02
    │
    ├── 5. Enqueue job to Celery worker
    │       └── Redis queue: pipeline.run(job_id, user_id, tier)
    │
    ├── 6. Return 202 Accepted + job tracking URL
    │
    ▼
Celery Worker picks up job
    │
    ├── Ingest → Transcribe → Analyze → Review → Render
    │
    ├── At each AI call (Gemini, Veo):
    │   ├── Check remaining AI quota for user/tier
    │   ├── If exceeded → metered billing event to Stripe
    │   └── Increment usage counter in Redis
    │
    ├── Render stage:
    │   ├── Free tier → add watermark overlay
    │   └── Pro/Team → clean render
    │
    ├── Upload outputs to S3 under user prefix
    │
    └── Notify client via WebSocket: {type: "job_complete", payload: {...}}
```

---

## 6. Hybrid Desktop + Cloud Sync

```
┌─────────────────────────┐         ┌─────────────────────────┐
│  Tauri Desktop           │         │  Cloud Backend           │
│  (Local GPU / Offline)   │         │  (Render/AWS)            │
│                          │         │                          │
│  ┌─────────────────┐    │   WS    │  ┌─────────────────┐    │
│  │ Local Pipeline   │    │ ◄────► │  │ Cloud Pipeline   │    │
│  │ (offline basics) │    │  Sync   │  │ (full features)  │    │
│  └─────────────────┘    │         │  └─────────────────┘    │
│                          │         │                          │
│  Capabilities:           │         │  Capabilities:           │
│  ✅ Transcription (GPU)  │         │  ✅ Everything            │
│  ✅ Basic editing         │         │  ✅ Co-Pilot (Gemini)    │
│  ✅ Local render          │         │  ✅ Veo 3.1 B-roll       │
│  ❌ Co-Pilot (needs API) │         │  ✅ Multi-platform pub   │
│  ❌ Veo 3.1 (needs API)  │         │  ✅ Usage tracking       │
│  ❌ Publishing (needs net)│         │  ✅ Analytics            │
│                          │         │                          │
│  On reconnect:           │         │                          │
│  → Sync local job state  │         │                          │
│  → Upload pending assets │         │                          │
│  → Verify subscription   │         │                          │
└─────────────────────────┘         └─────────────────────────┘
```

### Offline Mode Logic

```python
# gates/tier_gate.py

class TierGate:
    """Checks user tier for feature access.
    Supports offline mode for Tauri desktop."""

    def check_feature(
        self,
        user: UserProfile,
        feature: str,
        offline: bool = False,
    ) -> GateResult:
        if offline:
            # Offline: allow only local-capable features
            if feature in OFFLINE_FEATURES:
                return GateResult(allowed=True)
            return GateResult(
                allowed=False,
                reason="This feature requires an internet connection",
            )

        # Online: check tier
        required = FEATURE_TIER_MAP.get(feature, UserTier.FREE)
        if user.tier.value >= required.value:
            return GateResult(allowed=True)
        return GateResult(
            allowed=False,
            reason=f"Requires {required.name} tier",
            upgrade_url="/billing/upgrade",
        )

OFFLINE_FEATURES = {
    "transcribe", "basic_edit", "local_render",
    "filler_detection", "view_transcript",
}

FEATURE_TIER_MAP = {
    "transcribe": UserTier.FREE,
    "basic_edit": UserTier.FREE,
    "local_render": UserTier.FREE,
    "multi_cam": UserTier.STARTER,
    "broll_upload": UserTier.STARTER,
    "copilot_chat": UserTier.PRO,
    "copilot_auto_edit": UserTier.PRO,
    "veo_generate": UserTier.PRO,
    "publish_youtube": UserTier.PRO,
    "publish_all": UserTier.PRO,
    "smart_crop": UserTier.PRO,
    "api_access": UserTier.TEAM,
    "white_label": UserTier.TEAM,
    "team_seats": UserTier.TEAM,
}
```

---

## 7. WebSocket Sync (SaaS Extension)

The existing WebSocket hub (`service/ws_hub.py` from Phase 13) is extended with auth:

```python
# service/ws_hub.py — SaaS extension

@router.websocket("/ws/jobs/{job_id}")
async def job_ws(websocket: WebSocket, job_id: str):
    # 1. Authenticate via token query param
    token = websocket.query_params.get("token")
    user = verify_jwt(token)  # raises if invalid

    # 2. Verify user owns this job
    if not user_owns_job(user.user_id, job_id):
        await websocket.close(code=4003, reason="Forbidden")
        return

    # 3. Connect to room
    await hub.connect(job_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Broadcast to other clients in same room
            await hub.broadcast(job_id, data, exclude=websocket)
    except WebSocketDisconnect:
        await hub.disconnect(job_id, websocket)
```

---

*This document is a planning artifact. No implementation changes should be made without explicit user approval.*
