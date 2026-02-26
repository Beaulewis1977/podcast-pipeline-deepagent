# Implementation Roadmap

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Reference:** `00-SAAS-MASTER-PLAN.md`, `02-TECH-STACK-COMPARISON.md`
**Prerequisites:** Phases 11–14 complete

---

## 1. Timeline Overview

**Total Duration:** 8 weeks (after Phases 11–14)
**Parallel Tracks:** Backend SaaS Layer + Frontend Integration + Launch Prep

```
Week 1  ██████████ Auth + Database Schema
Week 2  ██████████ Payments (Stripe) + Billing
Week 3  ██████████ Feature Gates + Rate Limiting + Usage Tracking
Week 4  ██████████ Analytics + Monitoring + Crash Reporting
Week 5  ██████████ Frontend Integration (Subscribe buttons, tier UI)
Week 6  ██████████ Multi-Tenancy + Data Isolation + Object Storage
Week 7  ██████████ Landing Page + Beta Program + Marketing Prep
Week 8  ██████████ Load Testing + Security Audit + Soft Launch
```

---

## 2. Week 1: Authentication & Database Schema

### Objective
Stand up user identity, PostgreSQL schema, and JWT verification across the entire backend.

### Deliverables

| Task | Est. Hours | Dependencies |
|------|-----------|-------------|
| Set up Supabase project (Auth + Postgres) | 2 | None |
| Create database schema (profiles, teams, jobs, usage_logs) | 3 | Supabase project |
| Implement RLS policies (user isolation, team access) | 2 | Schema |
| Create `auth/supabase_client.py` — sign up, sign in, OAuth | 3 | Supabase project |
| Create `auth/middleware.py` — JWT verification FastAPI dependency | 3 | supabase_client |
| Create `auth/models.py` — UserProfile, UserTier enums | 1 | None |
| Add auth middleware to `service/app.py` | 1 | middleware.py |
| Create `service/routes/auth.py` — sign up/in/out endpoints | 3 | All above |
| Write tests for auth flow (sign up → JWT → protected route) | 2 | All above |
| **Total** | **20 hrs** | |

### Success Criteria
- [ ] Users can sign up with email/password and Google OAuth
- [ ] JWT tokens issued on login, verified on every API request
- [ ] Protected routes return 401 for unauthenticated requests
- [ ] RLS policies prevent cross-user data access
- [ ] Existing unauthenticated dev mode still works (local development)

### Config Addition
```yaml
# config.yaml
saas:
  enabled: false  # Toggle SaaS features on/off
  supabase_url: ${SUPABASE_URL}
  supabase_key: ${SUPABASE_ANON_KEY}
  jwt_secret: ${SUPABASE_JWT_SECRET}
  require_auth: false  # false = dev mode, true = production
```

---

## 3. Week 2: Payments & Billing (Stripe)

### Objective
Accept subscriptions, handle upgrades/downgrades, and meter AI usage for overage billing.

### Deliverables

| Task | Est. Hours | Dependencies |
|------|-----------|-------------|
| Set up Stripe account + create Products/Prices (Starter, Pro, Team) | 2 | None |
| Create metered price for AI overages in Stripe Dashboard | 1 | Stripe account |
| Create `billing/stripe_client.py` — subscription CRUD | 4 | Stripe account |
| Create `billing/webhooks.py` — handle Stripe webhooks | 4 | stripe_client |
| Create `billing/usage.py` — meter event reporting | 2 | stripe_client |
| Create `billing/models.py` — Subscription, Invoice Pydantic models | 1 | None |
| Create `service/routes/billing.py` — checkout, portal, webhook endpoints | 4 | All above |
| Integrate webhook → update user tier in Supabase | 2 | Week 1 auth |
| Test subscription lifecycle (create → upgrade → cancel) | 2 | All above |
| **Total** | **22 hrs** | |

### Stripe Webhook Events to Handle

```python
STRIPE_EVENTS = {
    "checkout.session.completed": "Create/update subscription in DB",
    "customer.subscription.updated": "Update tier on upgrade/downgrade",
    "customer.subscription.deleted": "Downgrade to free tier",
    "invoice.payment_succeeded": "Record payment, extend access",
    "invoice.payment_failed": "Flag account, send dunning email",
    "customer.subscription.trial_will_end": "Send trial ending email (3 days before)",
}
```

### Success Criteria
- [ ] Users can subscribe to Starter/Pro/Team via Stripe Checkout
- [ ] Upgrading mid-cycle prorates correctly
- [ ] Cancellation downgrades to free at period end
- [ ] AI overage events recorded and appear on invoice
- [ ] Webhook endpoint idempotent (can replay events safely)

---

## 4. Week 3: Feature Gates + Rate Limiting + Usage Tracking

### Objective
Enforce subscription tiers across all features: rate limits per user, usage caps with monthly resets, and feature access gates.

### Deliverables

| Task | Est. Hours | Dependencies |
|------|-----------|-------------|
| Set up Redis (Upstash or local) | 1 | None |
| Create `gates/tier_gate.py` — feature-tier mapping, gate check | 3 | Week 1 auth |
| Create `gates/rate_limiter.py` — slowapi config per tier | 2 | Redis |
| Create `gates/usage_tracker.py` — Redis counters with monthly TTL | 3 | Redis |
| Add tier checks to AI proxy endpoints (Gemini, Veo, Co-Pilot) | 2 | tier_gate |
| Add usage tracking to render stage (episode counter) | 1 | usage_tracker |
| Add usage tracking to AI calls (Gemini, Veo generations) | 2 | usage_tracker |
| Add watermark overlay for free-tier renders | 2 | tier_gate |
| Create `service/routes/usage.py` — usage dashboard endpoint | 2 | usage_tracker |
| UI: Grayed-out buttons with "Upgrade to Pro" tooltips | 2 | tier_gate |
| Write tests for gate/limit enforcement | 2 | All above |
| **Total** | **22 hrs** | |

### Feature-Tier Matrix

| Feature | Free | Starter | Pro | Team |
|---------|:----:|:-------:|:---:|:----:|
| Transcription | ✅ | ✅ | ✅ | ✅ |
| Basic editing | ✅ | ✅ | ✅ | ✅ |
| Local render | ✅ (watermark) | ✅ | ✅ | ✅ |
| Episodes/month | 3 | 5 | ∞ | ∞ |
| Multi-cam | ❌ | ✅ (2 cams) | ✅ (4 cams) | ✅ (4 cams) |
| B-roll upload | ❌ | ✅ | ✅ | ✅ |
| Co-Pilot chat | ❌ | ❌ | ✅ | ✅ |
| Co-Pilot Auto-Edit | ❌ | ❌ | ✅ | ✅ |
| Veo 3.1 B-roll | ❌ | ❌ | ✅ (20/mo) | ✅ (50/mo) |
| Multi-platform publish | ❌ | YouTube only | ✅ All | ✅ All |
| Smart crop | ❌ | ❌ | ✅ | ✅ |
| API access | ❌ | ❌ | ❌ | ✅ |
| White-label | ❌ | ❌ | ❌ | ✅ |
| Team seats | 1 | 1 | 1 | 5 |
| Priority support | ❌ | ❌ | ✅ Email | ✅ Priority |

### Success Criteria
- [ ] Free users blocked from Pro features with upgrade prompts
- [ ] Usage limits enforced (3 episodes/mo for free)
- [ ] Rate limiting active per tier (Redis-backed)
- [ ] Overage usage reports to Stripe for metered billing
- [ ] Monthly counters auto-reset via Redis TTL

---

## 5. Week 4: Analytics + Monitoring + Crash Reporting

### Objective
Instrument the app for user behavior tracking, error monitoring, and performance visibility.

### Deliverables

| Task | Est. Hours | Dependencies |
|------|-----------|-------------|
| Set up PostHog project (cloud) | 1 | None |
| Install `posthog` SDK, create analytics wrapper | 2 | PostHog project |
| Instrument 10 core events (sign up, job create, render, etc.) | 3 | analytics wrapper |
| Set up Sentry project | 1 | None |
| Install `sentry-sdk` in FastAPI (`service/app.py`) | 1 | Sentry project |
| Install `@sentry/browser` in Tauri React app | 1 | Sentry project |
| Configure Sentry alert rules (Slack/email) | 1 | Sentry project |
| Create admin usage dashboard endpoint | 2 | PostHog |
| Test: verify events flowing to PostHog | 1 | All above |
| Test: verify errors captured in Sentry | 1 | All above |
| **Total** | **14 hrs** | |

### Success Criteria
- [ ] Sign-up, job creation, and render events appear in PostHog
- [ ] Python exceptions auto-captured in Sentry with user context
- [ ] Tauri/React errors captured in Sentry
- [ ] Slack alert configured for > 10 errors/hour

---

## 6. Week 5: Frontend Integration

### Objective
Add subscribe buttons, billing portal, usage dashboard, and tier-aware UI to both Streamlit and Tauri.

### Deliverables

| Task | Est. Hours | Dependencies |
|------|-----------|-------------|
| Streamlit: Add login/signup page | 3 | Week 1 auth |
| Streamlit: Add "Subscribe" button → Stripe Checkout redirect | 2 | Week 2 billing |
| Streamlit: Add "Manage Subscription" → Stripe Customer Portal | 1 | Week 2 billing |
| Streamlit: Usage dashboard (episodes used, AI calls, limits) | 3 | Week 3 usage |
| Streamlit: Grayed-out features with upgrade prompts | 2 | Week 3 gates |
| Tauri: Add login view (email/password + Google OAuth) | 4 | Week 1 auth |
| Tauri: Add settings panel with subscription management | 2 | Week 2 billing |
| Tauri: Tier-aware feature visibility (menu items, buttons) | 2 | Week 3 gates |
| Tauri: Offline mode indicator + sync-on-connect | 2 | Week 1 auth |
| Both: "14-day free trial" banner for new signups | 1 | Week 2 billing |
| **Total** | **22 hrs** | |

### Success Criteria
- [ ] Users can sign up, subscribe, and manage billing from both web and desktop
- [ ] Free users see upgrade prompts on gated features
- [ ] Usage dashboard shows current period usage vs limits
- [ ] Trial banner shows days remaining

---

## 7. Week 6: Multi-Tenancy + Data Isolation + Object Storage

### Objective
Ensure complete per-user data isolation, set up cloud object storage for assets, and implement team functionality.

### Deliverables

| Task | Est. Hours | Dependencies |
|------|-----------|-------------|
| Set up S3 bucket (or Cloudflare R2) with IAM policies | 2 | None |
| Create `storage/s3_client.py` — upload/download/presign | 3 | S3 bucket |
| Modify ingest stage to upload to user-scoped S3 prefix | 3 | s3_client |
| Modify render stage to upload outputs to S3 | 2 | s3_client |
| Create team management endpoints (create team, invite, remove) | 4 | Week 1 auth |
| Implement team-scoped job visibility (RLS + team_id) | 2 | Teams |
| White-label branding isolation (per-team branding kits) | 2 | Teams |
| BYOK (Bring Your Own API Key) — encrypted storage in DB | 3 | Week 1 auth |
| Write tests for data isolation (user A cannot see user B's jobs) | 2 | All above |
| **Total** | **23 hrs** | |

### Success Criteria
- [ ] All job assets stored in user-scoped S3 prefix
- [ ] Team members can see team jobs but not other teams' jobs
- [ ] White-label branding kits isolated per team
- [ ] BYOK keys encrypted at rest (AES-256 or Supabase Vault)

---

## 8. Week 7: Landing Page + Beta Program + Marketing Prep

### Objective
Create a professional landing page, set up the beta program, and prepare launch materials.

### Deliverables

| Task | Est. Hours | Dependencies |
|------|-----------|-------------|
| Build landing page in Framer (pricing, demo video, sign-up) | 6 | None |
| Record 60s demo video (screen capture of pipeline in action) | 3 | Working app |
| Set up Rewardful affiliate program | 2 | Stripe account |
| Draft 3 blog posts (Medium: "Building an AI Podcast SaaS") | 4 | None |
| Create Product Hunt ship page (coming soon) | 1 | Landing page |
| Prepare Reddit/Twitter/Facebook launch posts | 2 | Landing page |
| Set up email list (ConvertKit free tier or Buttondown) | 1 | Landing page |
| Recruit 20–50 beta testers from Reddit/Twitter/Discord | 3 | Email list |
| **Total** | **22 hrs** | |

### Success Criteria
- [ ] Landing page live with pricing, demo, and sign-up CTA
- [ ] Affiliate program active with referral links
- [ ] 20+ beta testers signed up
- [ ] Product Hunt ship page submitted

---

## 9. Week 8: Load Testing + Security Audit + Soft Launch

### Objective
Validate the system under load, audit security posture, and execute a soft launch to beta users.

### Deliverables

| Task | Est. Hours | Dependencies |
|------|-----------|-------------|
| Load test: 50 concurrent users, 10 simultaneous renders | 3 | All weeks |
| Stress test: rate limiting under burst (100 req/s) | 2 | Week 3 |
| Security audit: JWT verification, RLS policies, input validation | 3 | All weeks |
| GDPR compliance check (privacy policy, data deletion, consent) | 2 | Landing page |
| Stripe test mode → live mode migration | 1 | Week 2 |
| Deploy to production (Render) | 2 | All weeks |
| DNS + SSL configuration | 1 | Render |
| Invite beta users (20–50) | 1 | Email list |
| Monitor: first 48 hours of real usage | 4 | Launch |
| Fix critical bugs from beta feedback | 4 | Beta users |
| **Total** | **23 hrs** | |

### Success Criteria
- [ ] System handles 50 concurrent users without degradation
- [ ] Rate limits engage correctly under burst
- [ ] No SQL injection, XSS, or auth bypass vulnerabilities
- [ ] Privacy policy published and cookie consent active
- [ ] Stripe live mode accepting real payments
- [ ] 20+ beta users active, <2 critical bugs

---

## 10. Post-Launch Weekly Cadence (Weeks 9–16)

| Week | Focus | Key Action |
|------|-------|------------|
| 9 | Beta feedback | Prioritize top 3 user requests |
| 10 | Product Hunt launch | Full PH launch, Indie Hackers post |
| 11 | Content marketing | Publish 2 blog posts, 1 podcast guest spot |
| 12 | Paid ads test | $100 on Facebook/LinkedIn targeting podcasters |
| 13 | Churn analysis | Implement cancellation survey, win-back emails |
| 14 | Feature iteration | Ship top-requested feature from beta |
| 15 | Scaling prep | Add second Celery worker if needed |
| 16 | MRR review | Assess progress toward $5K MRR target |

---

## 11. Total Effort Summary

| Week | Focus | Hours | Cumulative |
|------|-------|-------|-----------|
| 1 | Auth + DB Schema | 20 | 20 |
| 2 | Payments (Stripe) | 22 | 42 |
| 3 | Gates + Rate Limits | 22 | 64 |
| 4 | Analytics + Monitoring | 14 | 78 |
| 5 | Frontend Integration | 22 | 100 |
| 6 | Multi-Tenancy + Storage | 23 | 123 |
| 7 | Landing Page + Marketing | 22 | 145 |
| 8 | Testing + Launch | 23 | **168 hrs** |

**168 hours ÷ 8 weeks = ~21 hrs/week** (half-time pace for a solo developer, or 1 week for a 2-person team)

---

*This roadmap assumes Phases 11–14 are implemented. All estimates include tests. No over-engineering: build only what's needed for launch, iterate based on user feedback.*
