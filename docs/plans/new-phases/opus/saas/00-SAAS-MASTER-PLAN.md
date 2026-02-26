# SaaS Transformation — Master Plan

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Prerequisites:** Phases 11–14 complete (Multi-Cam, Gemini Co-Pilot, Hybrid UI, Publishing)
**Target:** $5K–$10K MRR within 6–12 months of SaaS launch

---

## 1. Executive Summary

This document set defines the complete strategy for transforming the AI Podcast Studio (after Phases 11–14 are implemented) into a **multi-tenant SaaS product** with recurring subscription revenue.

### What Already Exists (Post Phase 14)

- Full podcast production pipeline: Ingest → Transcribe → Analyze → Review → Render → Publish
- Multi-cam switching + B-roll overlay engine
- Gemini Co-Pilot (NL editing) + Veo 3.1 AI B-roll generation
- Hybrid UI: Streamlit (web) + Tauri v2 (desktop) with WebSocket sync
- One-click publishing: YouTube, Spotify, TikTok, Instagram
- FastAPI backend with auth, CORS, supervisor, health checks
- 21 MCP tools, 1041+ tests, strict typing (mypy, ruff)

### What This Plan Adds (SaaS Layer)

| Layer | Component | Purpose |
|-------|-----------|---------|
| **Identity** | Supabase Auth + JWT | User accounts, sessions, OAuth |
| **Billing** | Stripe Subscriptions + Metered Billing | Recurring revenue, usage-based overages |
| **Gating** | Redis-backed tier enforcement | Feature gates, usage caps, rate limits |
| **Multi-Tenancy** | Per-user data isolation | Private jobs, assets, branding kits |
| **Analytics** | PostHog | User behavior, funnel, retention |
| **Monitoring** | Sentry | Crash reporting across Python/TS/Rust |
| **Infrastructure** | Render/AWS + Celery + Redis | GPU compute, background jobs, scaling |

### Revenue Model

| Tier | Price (Monthly) | Price (Annual) | Features |
|------|----------------|----------------|----------|
| **Starter** | $0–$19/mo | — | 3–5 episodes/mo, basic features, watermarked exports |
| **Pro** | $59–$79/mo | $49–$69/mo | Unlimited episodes, full AI suite, all exports, priority render |
| **Team/Agency** | $99–$149/mo | $89–$129/mo | Multi-user seats, white-label, API access, priority support |

**Additional Revenue:**
- Metered overages: $0.01–$0.20 per extra AI generation beyond tier limits
- Affiliate program: 10–20% recurring commissions via Rewardful
- One-time add-ons: Custom setup ($99), white-label branding ($199)
- Annual discount: ~15% off monthly pricing

### ROI Target

- **Month 3:** 20 paid users → ~$1,200 MRR
- **Month 6:** 75 paid users → ~$4,500 MRR
- **Month 12:** 150 paid users → ~$9,000 MRR
- **Break-even:** ~$500/mo infrastructure → ~10 Pro users

---

## 2. Document Index

| # | Document | Purpose |
|---|----------|---------|
| **00** | `00-SAAS-MASTER-PLAN.md` (this file) | Executive summary, strategy, document index |
| **01** | `01-ARCHITECTURE-DIAGRAM.md` | High-level SaaS architecture, client-server flow, multi-tenancy |
| **02** | `02-TECH-STACK-COMPARISON.md` | Detailed pros/cons/costs for every tool choice |
| **03** | `03-IMPLEMENTATION-ROADMAP.md` | Phased weekly roadmap (8 weeks total) |
| **04** | `04-COST-ESTIMATE.md` | Monthly ops costs, scaling projections, break-even |
| **05** | `05-SECURITY-COMPLIANCE.md` | GDPR/CCPA, data isolation, API security, encryption |
| **06** | `06-MARKETING-LAUNCH-PLAN.md` | Launch timeline, channels, budget, copy/content |
| **07** | `07-RISK-ANALYSIS.md` | Technical + business risks with mitigations |
| **08** | `08-MONETIZATION-ENGINE.md` | Payments, billing, tier enforcement, feature gates, rate limits |
| **09** | `09-DESKTOP-DISTRIBUTION.md` | Windows/macOS install, code signing, auto-update, FFmpeg licensing |
| **10** | `10-CODEBASE-CHANGE-MAP.md` | Line-level audit of every existing file that must change for SaaS + Desktop |

---

## 3. Strategic Principles

### 3.1 Incremental, Not Rewrite

The SaaS layer is **additive**. No existing pipeline code is refactored. Instead:

- Auth middleware wraps existing FastAPI routes
- Stripe webhook handler writes tier info to PostgreSQL
- Feature gates are `if` checks reading user tier from auth context
- Usage counters are Redis `INCR` calls at existing AI proxy points

### 3.2 Local-First, Cloud-Gated

- **Tauri desktop** works offline for basic operations (transcription, local render)
- **Advanced features** (AI Co-Pilot, Veo 3.1, multi-platform publish) require active subscription
- **Session sync** between desktop and web via existing WebSocket hub
- **Tier verification** on every backend API call (JWT claims + DB lookup)

### 3.3 Start Lean, Scale When Needed

- **Week 1–4:** Single Render instance ($20/mo) + Supabase free tier + Stripe
- **$5K MRR:** Add Celery worker + Redis queue for background jobs (~$100/mo)
- **$10K MRR:** Add GPU instances for compute-heavy rendering (~$300/mo)
- **$25K+ MRR:** Multi-region deployment, CDN, dedicated support

### 3.4 No Over-Engineering

These features are **explicitly deferred** until revenue justifies them:

| Deferred Feature | Reason | Trigger |
|-----------------|--------|---------|
| Real-time collaborative editing | Complex, low demand at launch | $15K+ MRR, user requests |
| Mobile app | Tauri + Streamlit covers all UX | $25K+ MRR |
| Custom AI model training | Use Gemini/Veo as-is | Enterprise contracts |
| Multi-region deployment | Single region sufficient to ~500 users | P95 latency > 500ms |
| SOC 2 compliance | Not required for indie/SMB market | Enterprise deals > $500/mo |
| Self-hosted option | SaaS-only initially | Open-source demand |

---

## 4. Integration with Existing Codebase

### 4.1 New Source Tree Additions

```
src/podcast_pipeline/
├── auth/                          # NEW — SaaS auth layer
│   ├── __init__.py
│   ├── middleware.py              # FastAPI auth middleware (JWT verification)
│   ├── supabase_client.py         # Supabase Auth client wrapper
│   └── models.py                  # UserProfile, UserTier enums
├── billing/                       # NEW — Payments & subscriptions
│   ├── __init__.py
│   ├── stripe_client.py           # Stripe subscription management
│   ├── webhooks.py                # Stripe webhook handler
│   ├── usage.py                   # Metered billing for AI overages
│   └── models.py                  # Subscription, Invoice models
├── gates/                         # NEW — Feature gating & rate limits
│   ├── __init__.py
│   ├── tier_gate.py               # Tier-based feature checks
│   ├── rate_limiter.py            # Redis-backed rate limiting
│   └── usage_tracker.py           # Monthly usage counters
├── service/
│   ├── routes/
│   │   ├── auth.py                # NEW — Auth endpoints
│   │   ├── billing.py             # NEW — Billing/subscription endpoints
│   │   └── usage.py               # NEW — Usage dashboard endpoints
│   └── middleware/
│       └── auth_middleware.py     # NEW — Request-level auth injection
```

### 4.2 Modified Files (Minimal Changes)

| File | Change | Impact |
|------|--------|--------|
| `service/app.py` | Add auth middleware, billing routes | 10–15 lines |
| `providers/gemini.py` | Add usage tracking calls | 3–5 lines per AI call |
| `providers/veo.py` | Add usage tracking + tier check | 5–8 lines |
| `stages/render.py` | Add watermark for free tier | 5–10 lines |
| `config.yaml` | Add `saas` section | 20 lines |
| `pyproject.toml` | Add `saas` optional deps | 5 lines |

### 4.3 New Dependencies (SaaS Optional Group)

```toml
[project.optional-dependencies]
saas = [
    "stripe>=11.2.0",
    "supabase>=2.8.0",
    "redis>=5.0.8",
    "slowapi>=0.1.9",
    "posthog>=4.5.0",
    "sentry-sdk[fastapi]>=2.15.0",
    "pyjwt>=2.9.0",
]
```

---

## 5. Decision Log

| Decision | Rationale |
|----------|-----------|
| Stripe over Paddle/Lemon Squeezy | Best Python SDK, native metered billing, 2.9% vs 5% fees, scales with us |
| Supabase Auth over Firebase/Clerk | Native PostgreSQL RLS, best Python/FastAPI integration, generous free tier |
| Redis for rate limiting + usage | Industry standard, fast, `slowapi` integration, already needed for Celery |
| PostHog over Mixpanel/Amplitude | Self-hosted option, free tier, best Python SDK, full funnel analytics |
| Sentry over Bugsnag | Native Tauri/Rust support, better Python integration, lower cost |
| Render over AWS initially | Managed GPU, auto-deploy, no DevOps overhead; migrate to AWS at scale |
| Rewardful for affiliates | Stripe-native, $49/mo, handles payouts + tracking |

---

*All documents in this set are planning artifacts. No implementation changes should be made without explicit user approval and sequential execution of the roadmap.*
