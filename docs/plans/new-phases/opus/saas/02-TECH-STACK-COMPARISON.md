# Tech Stack Comparison

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Reference:** `00-SAAS-MASTER-PLAN.md`

---

## 1. Payments & Billing

### 1.1 Comparison Matrix

| Feature | **Stripe** ✅ | Paddle | Lemon Squeezy |
|---------|:----------:|:------:|:-------------:|
| **Python SDK** | `stripe>=11.2.0` (best docs) | `paddle-sdk-python>=2.1.0` | `lemonsqueezy-python>=1.4.0` |
| **Transaction Fee** | 2.9% + $0.30 | 5% + $0.50 (+2% intl) | 5% + $0.50 (+1.5% intl) |
| **Metered Billing** | ✅ Native (Meter Event API) | ❌ Workarounds | ❌ Workarounds |
| **Subscription Management** | ✅ Full (upgrade/downgrade/prorate/pause) | ✅ Full | ✅ Full |
| **Global Taxes/VAT** | ⚠️ Stripe Tax add-on (0.5%) or manual | ✅ Auto (Merchant of Record) | ✅ Auto (MoR, Stripe-backed) |
| **Annual Billing** | ✅ Native | ✅ Native | ✅ Native |
| **Coupons/Discounts** | ✅ Extensive | ✅ Basic | ✅ Basic |
| **Webhook Reliability** | ✅ Industry standard | ✅ Good | ✅ Good |
| **Cost at $5K MRR** | ~$150/mo (2.9%) | ~$275/mo (5%) | ~$275/mo (5%) |
| **Cost at $10K MRR** | ~$300/mo | ~$550/mo | ~$550/mo |

### 1.2 Recommendation: **Stripe**

**Why:** Native metered billing is critical for AI usage overages. The Python SDK is the most mature and best-documented. At $5–10K MRR, the 2.1% fee difference saves $125–$250/mo compared to Paddle/LS. For global taxes, add Stripe Tax ($25/mo + 0.5% per transaction) — still cheaper than the MoR fee premium.

**Trade-off acknowledged:** Paddle/LS handle taxes automatically as Merchant of Record. If you're a solo founder and don't want to deal with tax compliance at all, start with Lemon Squeezy and migrate to Stripe at $10K+ MRR.

### 1.3 Stripe Integration Pattern

```python
# billing/stripe_client.py

import stripe

class StripeManager:
    """Manages subscriptions, usage metering, and customer lifecycle."""

    def __init__(self, api_key: str) -> None:
        self._client = stripe.StripeClient(api_key)

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,  # e.g., "price_pro_monthly"
        trial_days: int = 14,
    ) -> stripe.Subscription:
        return self._client.v1.subscriptions.create(
            params={
                "customer": customer_id,
                "items": [{"price": price_id}],
                "trial_period_days": trial_days,
                "payment_behavior": "default_incomplete",
                "payment_settings": {
                    "save_default_payment_method": "on_subscription"
                },
                "expand": ["latest_invoice.payment_intent"],
            }
        )

    async def report_usage(
        self,
        customer_id: str,
        event_name: str,  # e.g., "ai_generation"
        value: int = 1,
    ) -> None:
        """Report metered usage for overage billing."""
        send_meter_event(
            {
                "event_name": event_name,
                "payload": {
                    "stripe_customer_id": customer_id,
                    "value": str(value),
                },
            },
            self._api_key,
        )
```

### 1.4 Stripe Price Configuration

```
Products in Stripe Dashboard:

1. STARTER ($19/mo)
   - price_starter_monthly: $19/mo recurring
   - price_starter_annual: $190/yr (~$15.83/mo)

2. PRO ($69/mo)
   - price_pro_monthly: $69/mo recurring
   - price_pro_annual: $588/yr (~$49/mo = 29% discount)

3. TEAM ($129/mo)
   - price_team_monthly: $129/mo recurring
   - price_team_annual: $1,068/yr (~$89/mo)

4. AI OVERAGE (metered)
   - price_ai_overage: $0.05/unit (1 unit = 1 AI generation)
   - Billed at end of billing cycle based on Meter events
```

---

## 2. Authentication

### 2.1 Comparison Matrix

| Feature | **Supabase Auth** ✅ | Firebase Auth | Clerk | Auth0 |
|---------|:------------------:|:------------:|:-----:|:-----:|
| **Python SDK** | `supabase>=2.8.0` | `firebase-admin>=7.2.0` | `clerk-python-backend-sdk>=1.12.0` | `auth0-python>=4.5.0` |
| **PostgreSQL Integration** | ✅ Native RLS | ❌ Firestore-centric | ⚠️ Via webhooks | ⚠️ Custom |
| **Email/Password** | ✅ | ✅ | ✅ | ✅ |
| **Google OAuth** | ✅ | ✅ | ✅ | ✅ |
| **JWT Tokens** | ✅ (auto-issued) | ✅ (Firebase tokens) | ✅ | ✅ |
| **User Roles/Tiers** | ✅ Custom claims + app_metadata | ✅ Custom claims | ✅ Roles | ✅ RBAC |
| **Row Level Security** | ✅ Native Postgres RLS | ❌ | ❌ | ❌ |
| **Free Tier** | 50K MAU | 50K MAU | 10K MAU | 7.5K MAU |
| **FastAPI Fit** | ✅ Best (official examples) | ⚠️ Fair | ✅ Good | ⚠️ Verbose |
| **MFA** | ✅ TOTP | ✅ SMS/TOTP | ✅ | ✅ |

### 2.2 Recommendation: **Supabase Auth**

**Why:** Native PostgreSQL RLS eliminates manual data isolation code. The Python SDK integrates directly with FastAPI. Free tier (50K MAU) covers the first 500+ paid users easily. JWT tokens are auto-issued and verifiable with `pyjwt`. User metadata (tier, team_id) can be stored in `app_metadata` for instant JWT access.

### 2.3 Supabase Integration

```python
# auth/supabase_client.py

from supabase import create_client, Client

class AuthClient:
    def __init__(self, url: str, key: str) -> None:
        self._client: Client = create_client(url, key)

    async def sign_up(self, email: str, password: str) -> dict:
        response = self._client.auth.sign_up({
            "email": email,
            "password": password,
        })
        return {
            "user_id": response.user.id,
            "access_token": response.session.access_token,
        }

    async def sign_in(self, email: str, password: str) -> dict:
        response = self._client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        return {
            "user_id": response.user.id,
            "access_token": response.session.access_token,
            "expires_at": response.session.expires_at,
        }

    async def set_user_tier(self, user_id: str, tier: str) -> None:
        """Called from Stripe webhook when subscription changes."""
        self._client.auth.admin.update_user_by_id(
            user_id,
            {"app_metadata": {"tier": tier}},
        )
```

---

## 3. Feature Gates & Rate Limiting

### 3.1 Comparison

| Approach | Tool | Purpose |
|----------|------|---------|
| **Rate Limiting** | `slowapi>=0.1.9` + Redis | Per-user request rate limits |
| **Usage Counters** | `redis>=5.0.8` (INCR + TTL) | Monthly episode/AI-call caps |
| **Tier Gating** | Custom FastAPI `Depends` | Feature access by subscription tier |
| **API Key Auth** | Custom middleware | Team/Agency API access |

### 3.2 Recommended Stack

```python
# gates/rate_limiter.py

from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limits by tier (requests per minute)
TIER_RATE_LIMITS = {
    "free": "5/minute",
    "starter": "30/minute",
    "pro": "100/minute",
    "team": "500/minute",
}

def get_user_identifier(request: Request) -> str:
    """Use user_id from JWT for rate limiting, not IP."""
    user = getattr(request.state, "user", None)
    if user:
        return f"user:{user.user_id}"
    return get_remote_address(request)

limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri="redis://localhost:6379",
)
```

```python
# gates/usage_tracker.py

import redis.asyncio as redis

class UsageTracker:
    """Track per-user monthly usage with Redis counters."""

    LIMITS = {
        "free":    {"episodes": 3,   "ai_calls": 10,  "veo_gens": 0},
        "starter": {"episodes": 5,   "ai_calls": 50,  "veo_gens": 2},
        "pro":     {"episodes": 999, "ai_calls": 999, "veo_gens": 20},
        "team":    {"episodes": 999, "ai_calls": 999, "veo_gens": 50},
    }

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis = redis.from_url(redis_url)

    async def check_and_increment(
        self,
        user_id: str,
        tier: str,
        action: str,  # "episodes", "ai_calls", "veo_gens"
    ) -> UsageResult:
        key = f"usage:{user_id}:{action}:{self._current_month()}"
        current = int(await self._redis.get(key) or 0)
        limit = self.LIMITS[tier][action]

        if current >= limit and limit < 999:
            return UsageResult(
                allowed=False,
                current=current,
                limit=limit,
                overage=True,  # trigger metered billing
            )

        await self._redis.incr(key)
        # Set TTL to end of month (reset automatically)
        await self._redis.expireat(key, self._end_of_month())
        return UsageResult(allowed=True, current=current + 1, limit=limit)
```

---

## 4. Analytics

### 4.1 Comparison Matrix

| Feature | **PostHog** ✅ | Mixpanel | Amplitude |
|---------|:------------:|:--------:|:---------:|
| **Python SDK** | `posthog>=4.5.0` | `mixpanel-python>=8.0.0` | `amplitude-python>=2.3.0` |
| **Self-Hosted** | ✅ Docker/K8s | ❌ Cloud-only | ❌ Cloud-only |
| **Event Tracking** | ✅ Autocapture + manual | ✅ Manual | ✅ Manual |
| **Funnels** | ✅ | ✅ | ✅ |
| **Cohorts** | ✅ | ✅ | ✅ |
| **Retention** | ✅ | ✅ | ✅ |
| **Session Recording** | ✅ | ❌ | ❌ |
| **Feature Flags** | ✅ | ❌ | ⚠️ Experiment |
| **Free Tier** | 1M events/mo (cloud) | 100K events/mo | 50K MTUs |
| **Pricing at Scale** | Self-host: $0 / Cloud: ~$50/mo | $100+/mo | $150+/mo |

### 4.2 Recommendation: **PostHog (Cloud → Self-Hosted)**

Start with PostHog Cloud (1M free events/mo covers ~1,000 users). Self-host on Render/Railway when scaling to save costs.

### 4.3 Key Events to Track (Start with 10)

```python
# analytics/events.py

EVENTS = {
    # Acquisition
    "user_signed_up": {"tier", "source"},
    "trial_started": {"tier", "trial_days"},

    # Activation
    "first_job_created": {"source_type"},
    "first_render_complete": {"platform", "tier"},

    # Engagement
    "copilot_command_used": {"command_type", "tier"},
    "veo_broll_generated": {"tier"},

    # Revenue
    "subscription_created": {"tier", "price", "annual"},
    "subscription_upgraded": {"from_tier", "to_tier"},
    "subscription_cancelled": {"tier", "reason"},

    # Retention
    "job_completed": {"tier", "duration_s"},
}
```

---

## 5. Crash Reporting & Monitoring

### 5.1 Comparison

| Feature | **Sentry** ✅ | Bugsnag |
|---------|:----------:|:-------:|
| **Python** | `sentry-sdk[fastapi]>=2.15.0` | `bugsnag-python>=5.19.0` |
| **TypeScript** | `@sentry/browser>=8.30.0` | `@bugsnag/js>=8.x` |
| **Rust (Tauri)** | `sentry-core>=0.9.0` | ❌ No native |
| **FastAPI Integration** | ✅ Auto-instrument | ⚠️ Manual |
| **Free Tier** | 5K errors/mo | 7.5K events/mo |
| **Paid (Team)** | $26/mo | $29/mo |
| **Release Tracking** | ✅ | ✅ |
| **Performance Tracing** | ✅ | ⚠️ Limited |

### 5.2 Recommendation: **Sentry**

Native support for all three languages in the stack (Python, TypeScript, Rust). FastAPI auto-instrumentation captures errors without code changes. Tauri WebView errors caught by the browser SDK.

```python
# In service/app.py — add 3 lines

import sentry_sdk
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    traces_sample_rate=0.1,  # 10% of requests traced
    environment=os.environ.get("ENVIRONMENT", "development"),
)
```

---

## 6. Hosting & Infrastructure

### 6.1 Comparison Matrix

| Feature | **Render** ✅ (Initial) | AWS EC2 (Scale) | Railway | DigitalOcean |
|---------|:-------------------:|:-----------:|:-------:|:------------:|
| **GPU Access** | ✅ H100 pods ($1.50/hr) | ✅ g5.xlarge ($1.20/hr) | ❌ None | ⚠️ GPU Droplets |
| **FastAPI Deploy** | ✅ Git push auto-deploy | ⚠️ Manual (ECS/EKS) | ✅ Auto-deploy | ⚠️ Manual |
| **Celery/Redis** | ✅ Background workers + Redis | ✅ Full control | ✅ Workers | ⚠️ Manual |
| **PostgreSQL** | ✅ Managed ($7/mo) | ✅ RDS ($30+/mo) | ✅ Managed | ✅ Managed |
| **SSL/HTTPS** | ✅ Auto | ⚠️ ACM + ALB | ✅ Auto | ⚠️ Manual |
| **Custom Domains** | ✅ | ✅ | ✅ | ✅ |
| **DevOps Burden** | ✅ Zero | ❌ High | ✅ Low | ⚠️ Medium |
| **Cost (Initial)** | ~$50–100/mo | ~$200+/mo | ~$50/mo (no GPU) | ~$80/mo |
| **Cost ($10K MRR)** | ~$300–600/mo | ~$800+/mo | N/A (no GPU) | ~$500/mo |

### 6.2 Recommendation: **Render (Start) → AWS (Scale)**

**Phase 1 ($0–$5K MRR):** Render
- Web service: $7/mo (FastAPI)
- Background worker: $7/mo (Celery)
- Redis: Upstash free tier → $10/mo
- PostgreSQL: Supabase free tier
- GPU: On-demand ($1.50/hr, ~$50/mo estimate)
- **Total: ~$75–150/mo**

**Phase 2 ($5K–$15K MRR):** Render + GPU scaling
- Scale workers horizontally
- Add dedicated GPU worker
- **Total: ~$300–600/mo**

**Phase 3 ($15K+ MRR):** Migrate to AWS for full control
- EC2 + ECS + ALB + RDS + ElastiCache
- Reserved instances for savings
- **Total: ~$800–1,500/mo**

### 6.3 Render Deployment Config

```yaml
# render.yaml

services:
  - type: web
    name: podcast-api
    runtime: python
    buildCommand: pip install -e ".[saas]"
    startCommand: uvicorn podcast_pipeline.service.app:app --host 0.0.0.0 --port 8787
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: STRIPE_SECRET_KEY
        sync: false
      - key: SENTRY_DSN
        sync: false
      - key: REDIS_URL
        fromService:
          type: redis
          name: podcast-redis
          property: connectionString

  - type: worker
    name: podcast-worker
    runtime: python
    buildCommand: pip install -e ".[saas]"
    startCommand: celery -A podcast_pipeline.workers worker --loglevel=info

  - type: redis
    name: podcast-redis
    plan: starter  # $10/mo
```

---

## 7. Affiliate Program

### 7.1 Comparison

| Tool | Price | Stripe Integration | Features |
|------|-------|-------------------|----------|
| **Rewardful** ✅ | $49/mo | ✅ Native | Auto-track, payouts, dashboard |
| FirstPromoter | $59/mo | ✅ Good | Viral loops, campaigns |
| PartnerStack | $500+/mo | ✅ | Enterprise, marketplace |

### 7.2 Recommendation: **Rewardful**

Stripe-native integration, $49/mo, handles affiliate tracking + payouts. Set up in 30 minutes.

**Commission Structure:**
- 15% recurring for 12 months (= $10.35/mo per Pro referral at $69/mo)
- 20% first month + 10% ongoing for top affiliates
- Cookie duration: 90 days
- Minimum payout: $50

---

## 8. Summary Decision Table

| Category | Selected | Package/Version | Monthly Cost |
|----------|----------|----------------|-------------|
| Payments | **Stripe** | `stripe>=11.2.0` | 2.9% + $0.30/txn |
| Auth | **Supabase Auth** | `supabase>=2.8.0` | $0 (free tier) |
| Rate Limiting | **slowapi + Redis** | `slowapi>=0.1.9`, `redis>=5.0.8` | $0–10 (Upstash) |
| Analytics | **PostHog** | `posthog>=4.5.0` | $0 (1M events free) |
| Monitoring | **Sentry** | `sentry-sdk[fastapi]>=2.15.0` | $0 (5K errors free) |
| Hosting | **Render** | N/A | ~$75–150/mo |
| Affiliates | **Rewardful** | N/A | $49/mo |
| Landing Page | **Framer** | N/A | $5–15/mo |
| Privacy Policy | **Termly** | N/A | $0–20/mo |

**Total Initial Monthly Cost: ~$130–250/mo** (before revenue)

---

*This document is a planning artifact. All versions and prices are current as of February 2026.*
