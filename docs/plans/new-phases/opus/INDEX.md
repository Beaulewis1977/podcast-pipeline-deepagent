# Opus Planning Documents — Master Index

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only (No Implementation)

---

## Overview

This directory contains all production-quality planning documents authored by Opus for the podcast pipeline project's future phases. Documents are organized into three tracks:

| Track | Scope | Documents |
|-------|-------|:---------:|
| [**New Features**](#track-1--new-features-phases-1114) | AI Studio, Multi-Cam, Gemini, UI/UX, Publishing | 5 |
| [**SaaS Transformation**](#track-2--saas-transformation) | Auth, billing, tiers, monetization, compliance | 11 |
| [**Codebase Integration**](#cross-cutting--codebase-change-map) | Existing file modifications for all tracks | 1 |

**Total: 17 documents, ~260KB of planning material.**

---

## Track 1 — New Features (Phases 11–14)

These documents define the AI Podcast Studio capabilities that must be built before SaaS launch. Each phase has a skeleton doc (in `../`) and a detailed Opus EPC (in this directory).

| # | File | Title | Size | Depends On | Summary |
|:-:|------|-------|-----:|:----------:|---------|
| 11 | [`11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md`](./11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md) | **Master Architecture & EPC Plan** | 30KB | Phases 1–10 | Top-level architecture for the AI Podcast Studio. Defines 6 EPCs, unified data flow (multi-cam, B-roll, Co-Pilot, UI, publishing), integration points with existing pipeline, and system-wide non-functionals. This is the root document for all feature planning. |
| 12 | [`12-PHASE-11-MULTI-CAM-BROLL-opus.md`](./12-PHASE-11-MULTI-CAM-BROLL-opus.md) | **Multi-Cam Core & B-Roll Engine** | 24KB | Phase 10 | N-camera ingestion (2–4 angles), universal auto-sync extending `sync.py`, JSON-driven camera switch plans (`camera_plan.json`), FFmpeg `filter_complex` multi-cam rendering, B-roll overlay insertion, and RIFE transitions at all switch/overlay boundaries. |
| 13 | [`13-PHASE-12-GEMINI-VEO-COPILOT-opus.md`](./13-PHASE-12-GEMINI-VEO-COPILOT-opus.md) | **Gemini Co-Pilot & Veo 3.1 Studio** | 21KB | Phase 11 | Gemini-powered NL editing assistant (chat + voice), structured edit instructions (NL → typed JSON), agentic Auto-Edit mode, Veo 3.1 AI B-roll generation with style matching, video extension (7s → 141s), Web Speech API voice commands. |
| 14 | [`14-PHASE-13-HYBRID-UI-UX-opus.md`](./14-PHASE-13-HYBRID-UI-UX-opus.md) | **Hybrid UI/UX & Transcript-First Editor** | 15KB | Phase 11 | Transcript-first word-level editor, multi-cam lane-based timeline, floating Co-Pilot panel, WebSocket bidirectional state sync between Streamlit and Tauri, in-browser preview playback with timeline scrubbing. |
| 15 | [`15-PHASE-14-MCP-DISTRIBUTION-opus.md`](./15-PHASE-14-MCP-DISTRIBUTION-opus.md) | **Automated Publishing & MCP Distribution** | 19KB | Phase 11 | One-click publishing to YouTube (OAuth2 resumable upload), Spotify (RSS feed), TikTok (Content Posting API), Instagram (Playwright automation), AI-generated per-platform metadata, and automatic branding kit application. |

### Feature Track Dependency Chain

```
Phase 10 (Desktop App — DONE)
    │
    ▼
Phase 11: Multi-Cam & B-Roll (doc 12)
    │
    ├──────────────────┐
    ▼                  ▼
Phase 12: Gemini/Veo  Phase 13: Hybrid UI
  (doc 13)              (doc 14)
    │                  │
    └────────┬─────────┘
             ▼
Phase 14: Publishing (doc 15)
             │
             ▼
     SaaS Transformation
```

---

## Track 2 — SaaS Transformation

These documents define the strategy for converting the AI Podcast Studio into a multi-tenant SaaS product with recurring subscription revenue. All SaaS docs live in the [`saas/`](./saas/) subdirectory.

| # | File | Title | Size | Summary |
|:-:|------|-------|-----:|---------|
| 00 | [`saas/00-SAAS-MASTER-PLAN.md`](./saas/00-SAAS-MASTER-PLAN.md) | **SaaS Master Plan** | 9KB | Executive summary, revenue model (Free → Pro → Team tiers), ROI projections ($5K–$10K MRR in 6–12 months), strategic principles, decision log, source tree additions, new dependencies. Root document for the SaaS track. |
| 01 | [`saas/01-ARCHITECTURE-DIAGRAM.md`](./saas/01-ARCHITECTURE-DIAGRAM.md) | **Architecture Diagram** | 25KB | High-level SaaS architecture showing client ↔ server flow, multi-tenancy model, auth flow (Supabase JWT), data isolation strategy, infrastructure topology (Render + Supabase + Stripe + Redis). |
| 02 | [`saas/02-TECH-STACK-COMPARISON.md`](./saas/02-TECH-STACK-COMPARISON.md) | **Tech Stack Comparison** | 15KB | Detailed pros/cons/cost analysis for every technology choice: auth providers (Supabase vs Firebase vs Clerk), payment processors (Stripe vs Paddle vs Lemon Squeezy), hosting (Render vs AWS vs Railway), analytics, monitoring. |
| 03 | [`saas/03-IMPLEMENTATION-ROADMAP.md`](./saas/03-IMPLEMENTATION-ROADMAP.md) | **Implementation Roadmap** | 14KB | Phased 8-week implementation timeline with weekly milestones, team allocation, and deliverables. Covers auth (weeks 1–2), billing (weeks 2–3), feature gates (weeks 3–4), frontend (weeks 4–5), polish + launch (weeks 6–8). |
| 04 | [`saas/04-COST-ESTIMATE.md`](./saas/04-COST-ESTIMATE.md) | **Cost Estimate** | 7KB | Monthly ops costs at different scale points ($50/mo at launch → $500/mo at $10K MRR), break-even analysis (~10 Pro users), per-service cost breakdowns (Supabase, Stripe fees, Render, Redis, Sentry, PostHog). |
| 05 | [`saas/05-SECURITY-COMPLIANCE.md`](./saas/05-SECURITY-COMPLIANCE.md) | **Security & Compliance** | 13KB | GDPR/CCPA compliance plan, data isolation model (RLS + filesystem), API security (rate limiting, input validation, CORS), encryption at rest/transit, incident response, user data export/deletion. |
| 06 | [`saas/06-MARKETING-LAUNCH-PLAN.md`](./saas/06-MARKETING-LAUNCH-PLAN.md) | **Marketing & Launch Plan** | 12KB | Launch timeline (beta → public), marketing channels (Product Hunt, Reddit, Twitter/X, YouTube), content calendar, budget allocation ($500 launch budget), email sequences, landing page design, community building. |
| 07 | [`saas/07-RISK-ANALYSIS.md`](./saas/07-RISK-ANALYSIS.md) | **Risk Analysis** | 12KB | Technical risks (GPU scaling, vendor lock-in, AI API costs) and business risks (market timing, pricing, churn) with likelihood/impact matrices and concrete mitigations for each. |
| 08 | [`saas/08-MONETIZATION-ENGINE.md`](./saas/08-MONETIZATION-ENGINE.md) | **Monetization Engine** | 27KB | Stripe integration plan, subscription lifecycle (trial → paid → cancel), metered billing for AI usage overages, FastAPI feature gate implementation with `Depends()` pattern, Redis usage counters, tier enforcement matrix. |
| 09 | [`saas/09-DESKTOP-DISTRIBUTION.md`](./saas/09-DESKTOP-DISTRIBUTION.md) | **Desktop Distribution** | 27KB | Windows NSIS installer + macOS DMG configuration, code signing (OV cert + Apple Developer ID), notarization, Tauri v2 auto-updater with Ed25519 signing, FFmpeg LGPL bundling compliance, binary size optimization (<150MB), first-run UX, App Store assessment. |
| 10 | [`saas/10-CODEBASE-CHANGE-MAP.md`](./saas/10-CODEBASE-CHANGE-MAP.md) | **Codebase Change Map** | 26KB | Line-level audit of ALL 16 existing files that must be modified for SaaS + Desktop. 31 change items with exact function names, line numbers, change type (additive/breaking/structural), dependency ordering, and a graph showing implementation sequence. |

---

## Cross-Cutting — Codebase Change Map

The **Codebase Change Map** (`saas/10-CODEBASE-CHANGE-MAP.md`) bridges both tracks by documenting every modification to files that exist today. Key stats:

| Metric | Count |
|--------|------:|
| Existing files that need modification | 16 |
| Individual change items | 31 |
| Breaking changes (auth evolution) | 3 |
| Additive changes (backward-compatible) | 22 |
| Files explicitly confirmed as unchanged | 22 |
| Implementation groups (A → F) | 6 |

---

## Reading Order

### For Understanding the Vision

1. `11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md` — start here for the big picture
2. `saas/00-SAAS-MASTER-PLAN.md` — business strategy and revenue model
3. `saas/01-ARCHITECTURE-DIAGRAM.md` — how it all fits together technically

### For Starting Implementation

1. `saas/10-CODEBASE-CHANGE-MAP.md` — what existing files change and in what order
2. `saas/03-IMPLEMENTATION-ROADMAP.md` — week-by-week execution plan
3. `12-PHASE-11-MULTI-CAM-BROLL-opus.md` — first feature phase to implement

### For Evaluating Feasibility

1. `saas/04-COST-ESTIMATE.md` — operational costs
2. `saas/07-RISK-ANALYSIS.md` — what could go wrong
3. `saas/02-TECH-STACK-COMPARISON.md` — technology choices and alternatives

---

## Document Relationships

```
┌──────────────────────────────────────────────────────────────────┐
│                    FEATURE TRACK (Phases 11–14)                  │
│                                                                  │
│  ┌─────────────┐                                                 │
│  │Doc 11       │ ─── Master Architecture ──────────────────────┐ │
│  │(Architecture)│                                               │ │
│  └──────┬──────┘                                               │ │
│         │ defines EPCs for                                     │ │
│    ┌────┼────────┬──────────┐                                  │ │
│    ▼    ▼        ▼          ▼                                  │ │
│  Doc 12  Doc 13  Doc 14  Doc 15                                │ │
│  Multi-  Gemini/ Hybrid  Publish                               │ │
│  Cam     Veo     UI/UX                                         │ │
│                                                                │ │
└────────────────────────────────────────────────────────────────┘ │
                                                                   │
    prerequisite for                                               │
         │                                                         │
         ▼                                                         │
┌──────────────────────────────────────────────────────────────────┐
│                       SAAS TRACK                                 │
│                                                                  │
│  ┌───────────┐    ┌───────────┐    ┌────────────┐               │
│  │Doc 00     │    │Doc 01     │    │Doc 02      │               │
│  │Master Plan│───▶│Architecture│───▶│Tech Stack  │               │
│  └─────┬─────┘    └───────────┘    └────────────┘               │
│        │                                                         │
│        ├─────┬──────┬──────┬───────┬───────┐                    │
│        ▼     ▼      ▼      ▼       ▼       ▼                    │
│     Doc 03 Doc 04 Doc 05 Doc 06 Doc 07  Doc 08                  │
│     Roadmap Costs  Secur  Mktg   Risk   Monetize                │
│        │                                   │                     │
│        ▼                                   ▼                     │
│     Doc 09 ◀── Desktop Distribution        │                     │
│        │                                   │                     │
│        └──────────────┬────────────────────┘                     │
│                       ▼                                          │
│                   Doc 10                                         │
│              Codebase Change Map                                 │
│         (bridges both tracks to code)                            │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Skeleton Docs (Superseded)

The following skeleton documents in the parent directory (`../`) were the initial outlines that the Opus detailed EPCs supersede:

| Skeleton File | Superseded By |
|---------------|---------------|
| `11-AI-PODCAST-STUDIO-ARCHITECTURE.md` | `opus/11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md` |
| `12-PHASE-11-MULTI-CAM-BROLL.md` | `opus/12-PHASE-11-MULTI-CAM-BROLL-opus.md` |
| `13-PHASE-12-GEMINI-VEO-COPILOT.md` | `opus/13-PHASE-12-GEMINI-VEO-COPILOT-opus.md` |
| `14-PHASE-13-HYBRID-UI-UX.md` | `opus/14-PHASE-13-HYBRID-UI-UX-opus.md` |
| `15-PHASE-14-MCP-DISTRIBUTION.md` | `opus/15-PHASE-14-MCP-DISTRIBUTION-opus.md` |

The skeletons are kept for historical reference but should not be used for implementation decisions.

---

*This index is the authoritative entry point for all Opus planning documents. Start here, then follow the reading order above based on your goal.*
