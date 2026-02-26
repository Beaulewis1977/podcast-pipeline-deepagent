# Cost Estimate & Financial Projections

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Reference:** `00-SAAS-MASTER-PLAN.md`, `02-TECH-STACK-COMPARISON.md`

---

## 1. Initial Monthly Infrastructure Costs (Pre-Revenue)

| Service | Provider | Plan | Monthly Cost |
|---------|----------|------|-------------|
| **Backend Hosting** | Render | Web service (Starter) | $7 |
| **Background Worker** | Render | Worker (Starter) | $7 |
| **PostgreSQL** | Supabase | Free tier (500MB, 50K MAU) | $0 |
| **Redis** | Upstash | Free tier (10K cmds/day) | $0 |
| **Object Storage** | Cloudflare R2 | 10GB free, then $0.015/GB | $0–$5 |
| **Authentication** | Supabase Auth | Free tier (50K MAU) | $0 |
| **Payments** | Stripe | 2.9% + $0.30/txn (no monthly fee) | $0 |
| **Analytics** | PostHog Cloud | Free (1M events/mo) | $0 |
| **Error Monitoring** | Sentry | Free (5K errors/mo) | $0 |
| **DNS/SSL** | Cloudflare | Free tier | $0 |
| **Domain** | Registrar | .com domain | $1 |
| **Email (transactional)** | Resend | Free (100/day) | $0 |
| **Landing Page** | Framer | Starter plan | $5 |
| **Affiliate Program** | Rewardful | Starter | $49 |
| | | **Total (Pre-Revenue)** | **~$69–$74/mo** |

---

## 2. Scaling Cost Projections

### Phase 1: 0–50 Users ($0–$3K MRR)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Render (Web + Worker) | $14 | Starter plans |
| Supabase | $0 | Free tier |
| Upstash Redis | $10 | Pro (25K cmds/day) |
| R2 Storage (100GB) | $1.50 | $0.015/GB |
| GPU compute (on-demand) | $50–100 | ~30–60 hrs × $1.50/hr |
| Stripe fees (at $3K MRR) | $87 | 2.9% |
| Rewardful | $49 | Affiliate program |
| **Total** | **$210–$260/mo** | |

### Phase 2: 50–200 Users ($3K–$10K MRR)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Render (Web + 2 Workers) | $50 | Standard plans |
| Supabase Pro | $25 | 100K MAU, 8GB DB |
| Upstash Redis Pro | $30 | 100K cmds/day |
| R2 Storage (1TB) | $15 | $0.015/GB |
| GPU compute (dedicated) | $200–400 | Reserved GPU worker |
| Sentry Team | $26 | More error quota |
| Stripe fees (at $10K MRR) | $290 | 2.9% |
| Stripe Tax | $75 | 0.5% + $25 base |
| Rewardful | $49 | Affiliate program |
| PostHog Scale | $50 | 5M events/mo |
| **Total** | **$810–$1,010/mo** | |

### Phase 3: 200–500 Users ($10K–$25K MRR)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| AWS (EC2 + ECS + ALB) | $400–600 | Migration from Render |
| AWS RDS PostgreSQL | $50 | db.t3.micro reserved |
| AWS ElastiCache Redis | $30 | cache.t3.micro |
| R2/S3 Storage (5TB) | $75 | $0.015/GB |
| GPU instances (2x) | $500–800 | g5.xlarge reserved |
| Sentry Business | $80 | Performance tracing |
| Stripe fees (at $25K MRR) | $725 | 2.9% |
| Rewardful Growth | $99 | More affiliates |
| PostHog Scale | $100 | 20M events/mo |
| **Total** | **$2,060–$2,660/mo** | |

---

## 3. Revenue Projections

### Conservative Scenario (Organic Growth Only)

| Month | Free Users | Starter ($19) | Pro ($69) | Team ($129) | MRR | Costs | Profit |
|-------|-----------|:-------------:|:---------:|:----------:|-----|-------|--------|
| 1 | 50 | 3 | 2 | 0 | $195 | $200 | -$5 |
| 2 | 100 | 8 | 5 | 0 | $497 | $220 | $277 |
| 3 | 200 | 15 | 10 | 1 | $1,104 | $280 | $824 |
| 6 | 500 | 30 | 40 | 5 | $3,975 | $600 | $3,375 |
| 9 | 800 | 40 | 70 | 10 | $6,880 | $800 | $6,080 |
| 12 | 1,200 | 50 | 100 | 15 | $9,785 | $1,000 | **$8,785** |

### Assumptions
- 5% free → paid conversion rate (industry: 3–8%)
- 5% monthly churn on paid plans (industry: 5–7%)
- 20% annual discount adoption (reduces effective MRR ~3%)
- Growth: 50% month-over-month for first 3 months, 20% thereafter
- No paid advertising until Month 4

### Additional Revenue Streams (Not in MRR Projection)

| Stream | Est. Monthly at Scale | Notes |
|--------|----------------------|-------|
| AI overage metering | $200–$500 | Pro users exceeding Veo/Gemini limits |
| Custom setup ($99 one-time) | $100–$300 | 1–3 setups/month |
| Affiliate commissions earned | -$150 (cost) | 15% recurring to affiliates |
| Annual plan prepayments | Cash flow boost | 15% discount = higher retention |

---

## 4. Break-Even Analysis

| Metric | Value |
|--------|-------|
| **Fixed monthly costs** | ~$200/mo (Phase 1) |
| **Variable cost per user** | ~$2/mo (storage, compute share) |
| **Average Revenue Per User (ARPU)** | $55/mo (weighted across tiers) |
| **Break-even users** | ~5 paid users |
| **Break-even MRR** | ~$275 |
| **Time to break-even** | Month 1–2 (with 5+ paid users) |

### Unit Economics

| Metric | Target | Notes |
|--------|--------|-------|
| **CAC (Customer Acquisition Cost)** | < $150 | Organic channels (Reddit, PH, content) |
| **LTV (Lifetime Value)** | > $900 | $69 × 13 months avg retention |
| **LTV:CAC Ratio** | > 6:1 | Healthy (target > 3:1) |
| **Payback Period** | < 3 months | CAC recovered in ~2.2 months at $69/mo |
| **Gross Margin** | > 85% | Low COGS (SaaS infrastructure) |

---

## 5. GPU Cost Optimization

GPU compute is the largest variable cost. Strategies:

| Strategy | Savings | Implementation |
|----------|---------|----------------|
| **On-demand GPU only** | 40–60% vs reserved | Celery spins up GPU workers when jobs arrive |
| **Batch rendering** | 20–30% | Queue jobs, process in batches during off-peak |
| **Local GPU for desktop** | 100% (for those users) | Tauri users render locally, no cloud GPU cost |
| **Draft-first preview** | 50% per render | Free/Starter get 720p draft → Pro gets 4K final |
| **Cache AI results** | 30–40% on AI costs | Same transcript = reuse analysis (Redis cache) |
| **Veo 720p previews** | 60% vs 4K | Generate at 720p for preview, 4K only on final |

### Estimated GPU Cost Per Job

| Job Type | GPU Minutes | Cost (On-Demand) |
|----------|-----------|-----------------|
| 30min podcast (basic render) | 2–5 min | $0.05–$0.13 |
| 30min podcast (multi-cam + B-roll) | 10–20 min | $0.25–$0.50 |
| 60min podcast (full pipeline) | 20–40 min | $0.50–$1.00 |
| Veo 3.1 B-roll generation (1 clip) | N/A (API call) | $0.10–$0.50 |

**At 100 Pro users × 4 jobs/month = 400 jobs → ~$100–$200/mo GPU cost**

---

## 6. One-Time Setup Costs

| Item | Cost | When |
|------|------|------|
| Domain registration | $12/yr | Week 7 |
| Stripe account verification | $0 | Week 2 |
| Supabase project setup | $0 | Week 1 |
| Google Cloud (Gemini API) credentials | $0 (pay per use) | Already done |
| Apple Developer account (if Mac App Store) | $99/yr | Post-launch |
| Termly privacy policy | $0–$20/mo | Week 7 |
| **Total one-time** | **~$110** | |

---

## 7. Annual Cost Summary

| MRR Level | Annual Revenue | Annual Costs | Annual Profit | Margin |
|-----------|---------------|-------------|--------------|--------|
| $1,000 | $12,000 | $3,000 | $9,000 | 75% |
| $5,000 | $60,000 | $9,600 | $50,400 | 84% |
| $10,000 | $120,000 | $14,400 | $105,600 | 88% |
| $25,000 | $300,000 | $31,200 | $268,800 | **90%** |

---

*All costs are estimates based on February 2026 pricing. Actual costs may vary based on usage patterns. Update quarterly.*
