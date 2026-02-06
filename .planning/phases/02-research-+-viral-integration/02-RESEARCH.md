# Phase 2: Research + Viral Integration - Research

**Researched:** 2026-02-04
**Domain:** YouTube research enrichment, viral-signal scoring, and recommendation ranking quality
**Confidence:** HIGH

## Summary

Phase 2 should improve recommendation quality by upgrading the existing research and viral modules that were wired in Phase 1. The current pipeline already writes `analysis/research.json` and `analysis/viral_signals.json`, but research metrics are basic (views/likes/comments averages), keyword extraction is naive token splitting, and clip ranking in `analysis.json` is still mostly provider-authored rather than recomputed from detector signals.

The standard implementation approach is to keep research and viral computation in `AnalyzeStage`, enrich `ResearchResult` with explicit metrics (engagement rate, velocity, competition score, posting windows), and persist deterministic score inputs so UI and downstream stages can explain *why* a clip/title/keyword was ranked highly.

Quota control is a hard requirement. `search.list` requests are expensive (100 quota units each), so repeated topic queries must be cached with TTL and key normalization to avoid spikes from repeated runs against the same episode topic.

**Primary recommendation:** Keep the existing `YouTubeResearcher` and `ViralClipDetector` architecture, but add deterministic scoring layers, result caching, and enriched artifacts that drive re-ranking in `AnalyzeStage` and UI visibility.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | >=0.28.0 | YouTube API calls | Already in project; supports client reuse and query params |
| Pydantic v2 | >=2.10.0 | Artifact schema + serialization | Existing model layer for stage outputs |
| Python stdlib (`datetime`, `statistics`, `collections`, `hashlib`) | 3.11+ | Metric computation, n-gram weighting, cache keying | No extra dependency burden |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Streamlit | >=1.42.0 | Explain ranking signals in UI | Show research/viral score context in review panels |
| pytest | >=8.0.0 | Deterministic ranking/metric regression tests | Lock formulas and score bounds |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Local JSON/TTL cache | `cachetools.TTLCache` | Cleaner API, but new runtime dependency |
| Regex + weighted n-grams | NLP libs (spaCy, NLTK) | Better linguistics, but too heavy for current phase scope |

**Installation:**
```bash
pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```text
src/podcast_pipeline/
├── research/
│   ├── youtube.py          # query, cache, competition/velocity/posting metrics
│   └── viral_detector.py   # signal extraction + clip scoring
├── stages/
│   └── analyze.py          # combines research + viral into ranking artifacts
└── ui/
    └── app.py              # displays ranked outputs and score reasons
```

### Pattern 1: Compute Per-Video Metrics First, Aggregate Second
**What:** Add normalized metrics (`engagement_rate`, `velocity_score`) per video, then derive topic-level competition and posting recommendations from those enriched rows.
**When to use:** Any new research metric that influences ranking.
**Example:**
```python
# Source: src/podcast_pipeline/research/youtube.py
engagement_rate = ((like_count + comment_count) / max(view_count, 1)) * 100
velocity_per_hour = view_count / max(hours_since_publish, 1)
```

### Pattern 2: Deterministic Re-Ranking in AnalyzeStage
**What:** Keep provider clip proposals, but recompute final ranking with detector signals and bounded score composition.
**When to use:** When combining AI suggestions with post-analysis signals.
**Example:**
```python
# Source: src/podcast_pipeline/stages/analyze.py
score = detector.score_clip(clip, transcript_data, signals)
combined = min(10.0, round((ai_score * 0.45) + (score.overall_score * 0.55), 1))
```

### Anti-Patterns to Avoid
- **Averaging without publish-time normalization:** biases old videos over current momentum.
- **Opaque score overrides:** replacing provider score without storing components.
- **Uncached repeated search queries:** rapidly consumes quota with little value.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP request lifecycle | ad-hoc requests per call | persistent `httpx.Client` | connection reuse and centralized timeouts |
| Artifact serialization | manual JSON dict glue | `model_dump` / `model_dump_json` | schema consistency across stages |
| Score clipping | scattered `if score > 10` checks | single bounded helper (`min/max`) | prevents drift and off-by-one bugs |

**Key insight:** keep scoring formulas and cache policy in one place (`research/youtube.py`, `research/viral_detector.py`) so `AnalyzeStage` only orchestrates.

## Common Pitfalls

### Pitfall 1: Treating `search.list` as cheap
**What goes wrong:** Frequent topic queries burn quota unexpectedly.
**Why it happens:** `search.list` has high quota cost.
**How to avoid:** Cache by normalized `(query, order, window, max_results)` with TTL.
**Warning signs:** Quota exhausted during local iteration.

### Pitfall 2: Velocity computed without age normalization
**What goes wrong:** Long-lived videos dominate regardless of recent performance.
**Why it happens:** Raw views used as momentum proxy.
**How to avoid:** Compute velocity from `view_count / hours_since_publish` and aggregate percentiles.
**Warning signs:** Best posting-time recommendations don't change across datasets.

### Pitfall 3: Added signals never affect final clip order
**What goes wrong:** New detector output is written but ranking remains unchanged.
**Why it happens:** Missing re-rank step in analyze artifact generation.
**How to avoid:** Write and sort by explicit `combined_score`, then persist reason breakdown.
**Warning signs:** UI clip order equals provider order even with strong detector deltas.

### Pitfall 4: Keyword extraction polluted by filler tokens
**What goes wrong:** Suggestions include weak words and punctuation fragments.
**Why it happens:** naive `split()` and no stopword filtering.
**How to avoid:** Regex tokenization + stopword list + weighted bigram/trigram scoring.
**Warning signs:** top keywords include words like "this", "with", "really".

## Code Examples

Verified patterns from sources and current code:

### HTTP query params + client reuse
```python
# Source: /encode/httpx (Context7) + src/podcast_pipeline/research/youtube.py
client = httpx.Client(timeout=30.0)
response = client.get(
    "https://www.googleapis.com/youtube/v3/search",
    params={"q": query, "maxResults": 25, "order": "viewCount", "key": api_key},
)
```

### Pydantic artifact serialization
```python
# Source: /pydantic/pydantic (Context7) + src/podcast_pipeline/stages/analyze.py
research_path.write_text(research_result.model_dump_json(indent=2))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw view-based topic quality | Engagement + velocity + competition blended scores | Phase 2 | Better relevance for recommendation ranking |
| Unweighted unigram keywords | Weighted n-grams with stopword filtering | Phase 2 | Stronger title/thumbnail seed terms |
| Detector scores stored separately | Combined AI + detector clip ranking | Phase 2 | Viral list aligns with observed signals |

**Deprecated/outdated:**
- Keyword extraction based on whitespace splitting only.
- Ranking clips purely by provider-assigned `virality_score` without detector-based recomposition.

## Open Questions

1. **Cache scope and persistence target**
   - What we know: caching is required to reduce quota spikes.
   - What's unclear: should cache live per-job, per-workspace, or globally across jobs.
   - Recommendation: start with workspace-level cache directory under `jobs/.cache/youtube` and configurable TTL.

2. **Engagement formula when `likeCount` is hidden**
   - What we know: some videos hide likes, resulting in sparse fields.
   - What's unclear: fallback weighting strategy.
   - Recommendation: degrade gracefully to comment/view and annotate confidence in insights.

3. **Best posting time granularity**
   - What we know: `publishedAt` supports weekday/hour analysis.
   - What's unclear: whether to return UTC slots or local-time slots.
   - Recommendation: store UTC in artifact and let UI optionally localize.

## Sources

### Primary (HIGH confidence)
- Local codebase:
  - `src/podcast_pipeline/research/youtube.py`
  - `src/podcast_pipeline/research/viral_detector.py`
  - `src/podcast_pipeline/stages/analyze.py`
  - `src/podcast_pipeline/ui/app.py`
- Context7:
  - `/encode/httpx` (client reuse, timeout, params)
  - `/pydantic/pydantic` (`model_dump`, `model_dump_json`)
- Official docs:
  - https://developers.google.com/youtube/v3/docs/search/list (search.list quota cost and params)
  - https://developers.google.com/youtube/v3/docs/videos/list (statistics fields)
  - https://developers.google.com/youtube/v3/determine_quota_cost (quota budgeting)

### Secondary (MEDIUM confidence)
- `codex/APP_RESEARCH_REPORT.md` (phase-specific integration checklist and priority ordering)

### Tertiary (LOW confidence)
- `saas ask` ecosystem synthesis on velocity/competition formulations (used only after cross-checking official quota/stats docs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - existing dependencies + Context7 validation
- Architecture: HIGH - consistent with current stage/artifact design
- Pitfalls: HIGH - directly observed in current code and roadmap requirements

**Research date:** 2026-02-04
**Valid until:** 2026-03-06
