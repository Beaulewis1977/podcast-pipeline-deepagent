# Risk Analysis

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Reference:** `00-SAAS-MASTER-PLAN.md`

---

## 1. Risk Matrix

```
            LOW IMPACT                    HIGH IMPACT
           ┌─────────────────────────────────────────┐
HIGH       │  • Tauri mic bugs (R5)     • AI cost     │
LIKELIHOOD │  • TikTok SELF_ONLY (R9)     overruns    │
           │  • Streamlit WS limits       (R1)        │
           │    (R6)                     • Churn >     │
           │                              7% (R3)     │
           ├─────────────────────────────────────────┤
LOW        │  • Stripe outage (R10)     • Data breach │
LIKELIHOOD │  • Supabase limits (R11)     (R2)        │
           │                            • Single      │
           │                              founder     │
           │                              burnout     │
           │                              (R4)        │
           └─────────────────────────────────────────┘
```

---

## 2. Technical Risks

### R1: AI Cost Overruns ⚠️ HIGH

**Risk:** Gemini/Veo API costs exceed revenue from AI-heavy users. A single Pro user running 20 Veo generations ($10–$50 in API costs) against $69/mo subscription erodes margin.

**Impact:** HIGH — Can make Pro tier unprofitable
**Likelihood:** HIGH — Power users will max out AI features

**Mitigations:**
| Action | Effect |
|--------|--------|
| Per-tier Veo generation limits (Free: 0, Pro: 20/mo, Team: 50/mo) | Cap worst-case per user |
| Metered billing for overages ($0.05–$0.20/generation) | Pass excess cost to user |
| 720p default for Veo previews (4K only on final render) | Reduce generation cost 60% |
| Cache AI analysis results per transcript (Redis) | Avoid duplicate Gemini calls |
| Monitor per-user AI cost in PostHog dashboard | Spot cost anomalies early |
| BYOK option (user provides own Gemini API key) | Offload cost for power users |

**Residual Risk:** LOW (with limits + metered billing)

---

### R2: Data Breach ⚠️ HIGH IMPACT

**Risk:** Unauthorized access to user podcast recordings, transcripts, or payment information.

**Impact:** HIGH — Legal liability, user trust loss, potential GDPR fines
**Likelihood:** LOW — Supabase RLS + encryption reduce attack surface

**Mitigations:**
| Action | Effect |
|--------|--------|
| Supabase RLS on all user tables | Database-level isolation even if app code has bugs |
| Pre-signed URLs for S3 (no public bucket) | No direct file access without auth |
| JWT verification on every request (middleware) | No unauthenticated access |
| Stripe handles payment card data (PCI-compliant) | No card data on our servers |
| Sentry alert on auth errors > 10/hour | Early detection of attacks |
| Quarterly dependency audit (pip-audit in CI) | Patch vulnerable packages |
| Security headers (HSTS, CSP, X-Frame-Options) | Prevent XSS/clickjacking |

**Residual Risk:** LOW (with defense-in-depth)

---

### R3: High Churn Rate ⚠️ HIGH IMPACT

**Risk:** Monthly churn exceeds 7%, preventing MRR growth. Podcasters often churn after initial novelty wears off.

**Impact:** HIGH — Cannot reach $10K MRR if losing 7%+ monthly
**Likelihood:** MEDIUM — Industry average for B2C SaaS is 5–7%

**Mitigations:**
| Action | Effect | Timeline |
|--------|--------|----------|
| **Onboarding drip emails** (5-part series) | 30% reduction in week-1 churn | Week 5 |
| **Usage-based alerts** (low engagement → win-back email) | Catch at-risk users early | Month 2 |
| **Pause subscription option** (instead of cancel) | Reduce hard cancellation 20% | Week 2 |
| **Cancellation survey** (why are you leaving?) | Identify fixable reasons | Week 5 |
| **Annual plan discount** (15% off) | Higher commitment, lower churn | Week 2 |
| **"Downgrade to Starter" option** instead of cancel | Retain revenue at lower tier | Week 2 |
| **Feature usage reports** (monthly email) | Remind users of value delivered | Month 2 |

**Target:** < 5% monthly churn within 6 months

---

### R4: Solo Founder Burnout ⚠️ HIGH IMPACT

**Risk:** Single person managing development, support, marketing, and operations leads to burnout and project abandonment.

**Impact:** HIGH — Project dies
**Likelihood:** MEDIUM — Common in indie SaaS

**Mitigations:**
| Action | Effect |
|--------|--------|
| Automate everything possible (CI/CD, monitoring, billing) | Reduce manual ops |
| Use managed services (Supabase, Stripe, Render) | No server babysitting |
| Set strict work boundaries (no more than 40 hrs/week) | Prevent burnout |
| Hire first contractor at $5K MRR (customer support) | Offload repetitive work |
| Hire first engineer at $15K MRR (part-time) | Share development load |
| Join founder communities (Indie Hackers, SaaS Reddit) | Emotional support, accountability |

---

### R5: Tauri Microphone / Voice Issues

**Risk:** Voice commands (Web Speech API) don't work on Linux Tauri (WebKitGTK) or have intermittent failures.

**Impact:** MEDIUM — Degrades Co-Pilot UX on Linux
**Likelihood:** HIGH — WebKitGTK confirmed lacking SpeechRecognition API

**Mitigations:**
| Action | Effect |
|--------|--------|
| Text-only fallback with mic icon disabled | Functional on all platforms |
| Detect platform at runtime (`navigator.userAgent`) | Show appropriate UI |
| Document limitation in release notes | Manage user expectations |
| Prioritize Chrome/Edge for full voice support | Focus on majority use case |

**Residual Risk:** LOW (with text fallback)

---

### R6: Streamlit WebSocket Limitations

**Risk:** Streamlit's re-execution model prevents true WebSocket for real-time sync.

**Impact:** MEDIUM — Streamlit users get delayed sync vs Tauri users
**Likelihood:** HIGH — Confirmed architectural limitation

**Mitigations:**
| Action | Effect |
|--------|--------|
| 500ms polling fallback for Streamlit | Adequate for non-real-time edits |
| Custom Streamlit component with React WebSocket | True WS in future |
| Position Tauri as primary editing client | Better UX where it matters |

---

## 3. Business Risks

### R7: Competitor Launches Similar Features

**Risk:** Descript, Riverside, or a new competitor launches AI multi-cam editing, reducing our differentiation.

**Impact:** HIGH — Harder to acquire users
**Likelihood:** MEDIUM — AI editing is trending; competitors have larger teams

**Mitigations:**
| Action | Effect |
|--------|--------|
| **Speed to market** — launch before competitors add these features | First-mover advantage |
| **Desktop + offline** — unique differentiator vs cloud-only tools | Hard for competitors to replicate |
| **Voice Co-Pilot** — novel UX that competitors haven't explored | Unique selling point |
| **Niche focus** (podcasters) vs Descript (all video) | Better product-market fit |
| **Aggressive pricing** ($19–$69) vs Descript ($24–$33) | Price-competitive |

---

### R8: Low Free-to-Paid Conversion

**Risk:** Free users don't convert. 5% conversion target may be optimistic.

**Impact:** HIGH — Delays MRR growth
**Likelihood:** MEDIUM — Depends on value perception

**Mitigations:**
| Action | Effect |
|--------|--------|
| **Watermark on free exports** | Motivation to upgrade (removes with any paid plan) |
| **Generous trial** (14-day Pro access) | Users experience full value before decision |
| **Usage-gated tease** (show locked features as grayed-out) | FOMO on what they're missing |
| **Social proof** (testimonials, user count) on upgrade page | Trust signals |
| **Time-limited offer** (20% first-month discount) | Urgency |

**Fallback:** If conversion < 3%, reduce free tier further (1 episode/mo, 720p only, no branding) or eliminate free tier entirely (trial-only model).

---

### R9: TikTok API Restrictions

**Risk:** TikTok Content Posting API remains restricted to SELF_ONLY (videos invisible to public) until audit.

**Impact:** LOW — TikTok is one of 5+ supported platforms
**Likelihood:** HIGH — Audit process is slow

**Mitigations:**
| Action | Effect |
|--------|--------|
| Playwright browser automation fallback | Upload via web UI |
| Start API audit process immediately | Unblock eventually |
| Document limitation clearly for users | Manage expectations |
| Priority: YouTube + Spotify first (higher value) | Focus on platforms that work |

---

### R10: Stripe Service Outage

**Risk:** Stripe outage prevents billing, potentially losing transactions.

**Impact:** MEDIUM — Users can't subscribe; existing subs unaffected
**Likelihood:** LOW — Stripe has 99.99% uptime

**Mitigations:**
| Action | Effect |
|--------|--------|
| Webhook retry logic (idempotent handlers) | No lost events |
| Local tier cache in Redis (TTL: 1 hour) | Auth works during outage |
| Status page monitoring (Stripe status → Slack alert) | Awareness |

---

### R11: Supabase Free Tier Limitations

**Risk:** Outgrow Supabase free tier (500MB DB, 50K MAU) faster than expected.

**Impact:** LOW — Predictable upgrade path
**Likelihood:** LOW — 50K MAU would mean massive success

**Mitigations:**
| Action | Effect |
|--------|--------|
| Monitor DB size monthly | Predict upgrade timing |
| Supabase Pro ($25/mo) at 80% capacity | Seamless upgrade |
| Usage logs summarized monthly, raw deleted | Reduce DB growth |

---

## 4. Risk Response Summary

| Risk | Severity | Response Type | Owner | Status |
|------|----------|--------------|-------|--------|
| R1: AI cost overruns | HIGH | Mitigate (limits + metering) | Backend | Planned |
| R2: Data breach | CRITICAL | Prevent (RLS + encryption) | Security | Planned |
| R3: High churn | HIGH | Mitigate (onboarding + alerts) | Product | Planned |
| R4: Founder burnout | HIGH | Mitigate (automation + hiring) | Operations | Ongoing |
| R5: Tauri mic issues | MEDIUM | Accept (text fallback) | Frontend | Accepted |
| R6: Streamlit WS | MEDIUM | Accept (polling fallback) | Frontend | Accepted |
| R7: Competitors | HIGH | Mitigate (speed + differentiation) | Strategy | Ongoing |
| R8: Low conversion | HIGH | Mitigate (trials + tease + pricing) | Growth | Planned |
| R9: TikTok API | LOW | Accept + workaround | Publishing | Accepted |
| R10: Stripe outage | LOW | Accept (cache + retry) | Billing | Accepted |
| R11: Supabase limits | LOW | Monitor + upgrade plan | Infrastructure | Monitored |

---

## 5. Contingency Plans

### If MRR < $2K at Month 6:

1. **Re-evaluate pricing:** Consider $9/mo Starter, $39/mo Pro
2. **Pivot to B2B:** Target podcast agencies directly (cold outreach)
3. **Add lifetime deal:** AppSumo-style one-time purchase ($199 for Pro forever)
4. **Reduce scope:** Focus on YouTube auto-publish only (narrower value prop)
5. **Open-source core:** Release pipeline engine as FOSS, monetize cloud features

### If AI Costs > 30% of Revenue:

1. **Increase metered billing rates** ($0.10 → $0.25/generation)
2. **Reduce Veo tier limits** (Pro: 20 → 10/mo)
3. **Require BYOK for high-volume users**
4. **Negotiate volume discount with Google** (at 1,000+ calls/mo)
5. **Cache aggressively** (same prompt → same result for 24 hours)

### If Churn > 10% Monthly:

1. **Implement "pause subscription"** (3 months max)
2. **Offer quarterly billing** (stronger commitment)
3. **Add cancellation flow with counter-offers** (discount, downgrade, pause)
4. **Survey ALL churned users** (automated, 3-question email)
5. **Ship top 3 requested features within 2 weeks**

---

*Review this risk analysis monthly. Add new risks as discovered. Remove risks that have been fully mitigated. The goal is zero Critical risks before launch.*
