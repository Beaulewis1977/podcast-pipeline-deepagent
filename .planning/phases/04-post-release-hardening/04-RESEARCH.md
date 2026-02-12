# Phase 04: Post-release hardening - Research

**Researched:** 2026-02-12
**Domain:** Production hardening for runtime correctness, service security, data validation, and output reliability
**Confidence:** HIGH

## Summary

Phase 04 should prioritize runtime truthfulness and safety over feature expansion. The most important gap pattern is "silent success": operations can report success while partially failing, degrading output quality or integrity without clear operator signal. The hardening plan should enforce strict validation, explicit failure modes, and deterministic recovery semantics.

The current architecture already has strong foundations (stage pipeline, typed models, FastAPI service, desktop sidecar), so Phase 04 should use targeted corrective slices instead of rewrites. The recommended implementation order is: runtime correctness first, provider/service reliability second, quality/UX completion third, and confidence gates last.

For core stack choices, keep FastAPI + Pydantic v2 + HTTPX + tenacity and add stronger usage patterns: app-level dependencies/middleware/exception handlers in FastAPI, model-level range and cross-field validation in Pydantic v2, persistent `httpx.Client` reuse with explicit timeout policy, and explicit retry boundaries for AI provider failure classes.

**Primary recommendation:** Execute Phase 04 as a multi-wave hardening program that first removes false-success paths and concurrency risks, then strengthens reliability/security, and finally adds regression gates that prevent drift.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | `>=0.128.2` (project) | Service contract, middleware, exception boundaries | Existing service foundation; official dependency/decorator patterns for auth and global error handling |
| Pydantic | `>=2.10.0` (project) | Artifact and contract validation | `Field`, `field_validator`, `model_validator` support strict range/cross-field checks |
| HTTPX | `>=0.28.0` (project) | Provider/research/service HTTP transport | Supports pooled client reuse, granular timeout policy, typed exceptions |
| tenacity | `>=9.0.0` (project) | Targeted retry behavior for transient provider failures | Already in codebase and suitable for bounded retry policies |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | `>=24.4.0` | Structured runtime diagnostics | Correlation of degraded mode, partial export failures, retry cause |
| pytest + pytest-asyncio + pytest-cov | project dev deps | Confidence gates for runtime-critical paths | Add dedicated suites for providers, edit-plan validation, supervisor |
| file-based lock strategy | project-local implementation (or lightweight lock helper) | Prevent concurrent runs on same job | Needed where pipeline reads/writes shared job state |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| App-level API key dependency | Full OAuth/JWT auth stack | Better identity semantics but higher implementation and operational overhead for local-sidecar service |
| File lock dependency | Native platform-specific locks (`fcntl`/`msvcrt`) | No new package, but more cross-platform edge-case handling burden |
| Strict failure on partial export | Keep `success=true` with embedded errors | Easier compatibility but hides operator-critical failure states |

**Installation:**
```bash
# No mandatory new dependency for baseline hardening.
# Optional, if lock helper package is selected:
# uv add filelock
```

## Architecture Patterns

### Recommended Project Structure
```text
src/podcast_pipeline/
├── pipeline.py                    # stage validation + lock + resume semantics
├── service/
│   ├── app.py                     # auth + global exception middleware
│   ├── routes/jobs.py             # run/resume contract hardening
│   ├── recovery.py                # resume-through-completion prep + reconciliation
│   └── supervisor.py              # timeout/heartbeat/last-stage reliability
├── models/
│   ├── edit_plan.py               # strict time-range validation
│   ├── analysis.py                # strict clip/cut range consistency
│   └── transcript.py              # confidence and duration bounds
├── stages/
│   ├── analyze.py                 # JSON guardrails + provider degraded-mode flags
│   ├── review.py                  # JSON guardrails + review workflow consistency
│   └── render.py                  # partial-failure semantics + output verification
└── clients/service_client.py      # pooled client, timeouts, typed errors
```

### Pattern 1: Fail Fast on Invalid Runtime State
**What:** Reject unknown stage values, malformed artifacts, and impossible ranges immediately.
**When to use:** Pipeline entry, resume requests, artifact parsing, model instantiation.
**Example:**
```python
# Source: Context7 /pydantic/pydantic
from pydantic import BaseModel, Field, model_validator

class ClipRange(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def ensure_order(self):
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be >= start_seconds")
        return self
```

### Pattern 2: Explicit Degraded-Mode Contracts
**What:** If fallback provider or partial export occurs, expose explicit degraded flags/state instead of silently succeeding.
**When to use:** Analyze provider chain, render multi-platform exports.
**Example:**
```python
result["degraded_mode"] = {
    "enabled": True,
    "reason": "fallback_provider_transcript_only",
    "provider": provider_name,
}
```

### Pattern 3: Shared Client + Timeout Policy
**What:** Reuse `httpx.Client` and apply default + per-request timeout overrides.
**When to use:** Service client and provider outbound HTTP paths.
**Example:**
```python
# Source: Context7 /encode/httpx
import httpx

client = httpx.Client(timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0))
response = client.get(url, timeout=60.0)  # override for long request
response.raise_for_status()
```

### Anti-Patterns to Avoid
- **Silent parse fallback to empty payloads:** Hides provider/data quality failures.
- **Partial export reported as success:** Misleads operators and automation.
- **Display-only controls in UI:** Creates false UX promises.
- **Unbounded model fields:** Allows impossible values that fail later and indirectly.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request auth enforcement | Custom per-route copy/paste checks | FastAPI dependency/middleware | Centralized enforcement and less drift |
| Cross-field schema validation | Manual `if` checks across stages | Pydantic `model_validator` | Single source of truth at data boundary |
| HTTP timeout/exception handling | Ad-hoc `try/except Exception` blocks | HTTPX typed exceptions + timeout objects | Better observability and predictable retries |
| Retry policies | Unlimited retry loops | tenacity bounded retries by error class | Prevents runaway loops and hidden latency |

**Key insight:** Reliability in this phase comes from stronger boundaries and explicit contracts, not from adding more inference logic.

## Common Pitfalls

### Pitfall 1: "Succeeded" jobs with hidden partial failures
**What goes wrong:** Render succeeds despite one platform export failing.
**Why it happens:** Success boolean not coupled to platform-level results.
**How to avoid:** Return explicit failed status (or degraded status) when any required output target fails.
**Warning signs:** `errors` present in payload while top-level `success=true`.

### Pitfall 2: Resume semantics that only rerun one stage
**What goes wrong:** Users expect completion but get one-stage rerun.
**Why it happens:** Resume route forwards a single stage start without continuation policy.
**How to avoid:** Define resume contract as "from stage through completion" by default.
**Warning signs:** repeated manual resume actions required per stage.

### Pitfall 3: Invalid time ranges accepted and quietly filtered later
**What goes wrong:** malformed cuts/clips silently dropped in render.
**Why it happens:** no model-level bounds/order validation.
**How to avoid:** enforce non-negative and ordered timestamps in models.
**Warning signs:** zero-length or negative ranges in persisted JSON artifacts.

### Pitfall 4: Concurrent pipeline runs corrupting same job state
**What goes wrong:** state artifacts race; stage status becomes inconsistent.
**Why it happens:** no job-level lock + no state reload between long operations.
**How to avoid:** file lock per job and explicit state sync points.
**Warning signs:** duplicate stage execution or inconsistent `state.json` transitions.

## Code Examples

Verified patterns from official sources:

### FastAPI App-Level Dependency and Exception Handler
```python
# Source: Context7 /fastapi/fastapi
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

async def require_api_key():
    ...

app = FastAPI(dependencies=[Depends(require_api_key)])

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
```

### Pydantic Bounded Confidence Field
```python
# Source: Context7 /pydantic/pydantic
from pydantic import BaseModel, Field

class Word(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
```

### HTTPX Typed Error Handling
```python
# Source: Context7 /encode/httpx
import httpx

try:
    response = client.get(url)
    response.raise_for_status()
except httpx.TimeoutException:
    ...
except httpx.HTTPStatusError as exc:
    if exc.response.status_code == 429:
        ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Route-local ad-hoc security checks | App/router-level dependencies + middleware | Mature FastAPI patterns through current docs | Less auth drift and clearer policy ownership |
| Post-hoc data cleanup in stage code | Boundary validation in Pydantic models | Pydantic v2 validator model | Fewer latent runtime errors |
| New HTTP client per request | Pooled long-lived HTTPX client | Current HTTPX best-practice docs | Better performance and predictable timeout behavior |

**Deprecated/outdated:**
- Reporting success while embedding critical errors only in payload internals.
- Treating parse failures as equivalent to valid empty analysis outputs.

## Open Questions

1. **API auth model depth for local-only mode**
   - What we know: API key gating is required for baseline hardening.
   - What's unclear: whether local-only deployment should allow explicit no-auth dev mode.
   - Recommendation: implement required auth with an explicit dev override flag.

2. **Locking implementation choice**
   - What we know: job-level locking is mandatory.
   - What's unclear: standard-library-only lock vs dedicated lock helper package.
   - Recommendation: start with stdlib lock strategy if cross-platform behavior is validated in tests; otherwise adopt lightweight lock helper.

3. **OpenAI provider direction**
   - What we know: config exposes OpenAI key path but provider implementation is missing.
   - What's unclear: implement now vs remove config path in this phase.
   - Recommendation: make this an explicit plan decision with a hard acceptance outcome.

## Sources

### Primary (HIGH confidence)
- Context7 `/fastapi/fastapi` - app-level dependencies, middleware integration, exception handlers
- Context7 `/pydantic/pydantic` - `Field` constraints, `field_validator`, `model_validator`
- Context7 `/encode/httpx` - client reuse, timeout policy, typed exception handling
- Local audit: `docs/reports/2026-02-12-all-features-production-gap-report.md`

### Secondary (MEDIUM confidence)
- Perplexity Search: FastAPI production hardening ecosystem patterns (2025-2026 articles, mixed quality)
- Perplexity Search: file-locking approach discovery and references to official filelock docs

### Tertiary (LOW confidence)
- Blog/opinion summaries returned by web search without direct official-library corroboration

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - existing project dependencies plus Context7 verification.
- Architecture: HIGH - grounded in current codebase and gap report evidence.
- Pitfalls: HIGH - directly evidenced in local audited findings.

**Research date:** 2026-02-12
**Valid until:** 2026-03-14 (30 days; re-check external docs before implementation starts)
