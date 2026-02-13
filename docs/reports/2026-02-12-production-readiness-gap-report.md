# Production Readiness Gap Report

Date: 2026-02-12
Scope reviewed: full repository + `docs/plans/2026-01-29-podcast-pipeline-design.md`

## Executive Summary

The project is substantially implemented, but not yet production-ready for the target outcome (fully real end-to-end pipeline with no placeholder behavior and reliable desktop distribution).

Primary blockers:
- Desktop frontend/backend API contract mismatches
- Desktop backend build path points to a missing file
- Design-stage mismatch (`research` stage exists in design but not as a first-class pipeline stage)
- Placeholder behavior remains in Streamlit UI
- Critical runtime paths are under-tested for production confidence

---

## What Needs To Be Fixed

### 1. Desktop API Contract Breakages (P0)

Files:
- `desktop/src/lib/backend.ts`
- `desktop/src/App.tsx`
- `src/podcast_pipeline/service/app.py`
- `src/podcast_pipeline/service/routes/jobs.py`
- `src/podcast_pipeline/service/schemas.py`

Issues:
- Desktop expects `GET /health` response with `version`; backend returns only `{ "status": "ok" }`.
- Desktop expects `GET /jobs` to return an array; backend returns `{ "jobs": [...] }`.
- Desktop sends `input_path` to `POST /jobs`; backend expects `video_path`.
- Desktop `runJob()` sends no JSON body; backend route currently requires request body model.
- Desktop UI renders `current_stage` and `created_at` fields not returned by backend job list schema.

Required fix:
- Unify desktop TypeScript client and FastAPI schemas to one contract and enforce it with cross-stack tests.

### 2. Desktop Release Build Entry Path Is Broken (P0)

Files:
- `README.md`
- `docs/desktop-distribution.md`
- `.github/workflows/desktop-release.yml`

Issue:
- Build commands reference `src/podcast_pipeline/service/cli.py`, which does not exist.

Required fix:
- Either add the missing backend entry file, or update all build commands/workflows/docs to the real entrypoint.

### 3. Streamlit Placeholder Behavior (P1)

File:
- `src/podcast_pipeline/ui/app.py`

Issue:
- Marketing regenerate action is placeholder text: `"This would call AI in production"`.

Required fix:
- Wire a real regeneration call path (provider-backed), including error handling and persistence.

### 4. Filler Data Shape Mismatch in UI (P1)

Files:
- `src/podcast_pipeline/ui/app.py`
- `src/podcast_pipeline/stages/transcribe.py`
- `src/podcast_pipeline/models/transcript.py`

Issue:
- UI reads `transcript["filler_words"]`; pipeline writes `filler_cuts` artifacts.

Required fix:
- Align UI with actual model/artifact shape and ensure review state updates use approved filler cut indices correctly.

---

## What Needs To Be Changed

### 1. Pipeline Architecture vs Design Doc (P1)

Files:
- `src/podcast_pipeline/pipeline.py`
- `src/podcast_pipeline/models/job.py`
- `docs/plans/2026-01-29-podcast-pipeline-design.md`

Issue:
- Design specifies a dedicated `research` stage between analyze and review, but runtime stage order is:
  - `ingest -> transcribe -> analyze -> review -> render`
- Research currently runs only as optional logic inside analyze.

Required change:
- Choose one of:
  - Implement a first-class `research` stage (recommended for traceability and resume semantics), or
  - Officially revise design doc/state schema to match current architecture.

### 2. Failure Semantics for Provider Parse Errors (P1)

Files:
- `src/podcast_pipeline/providers/gemini.py`
- `src/podcast_pipeline/providers/kimi.py`

Issue:
- JSON parse failure currently falls back to empty but valid structures, which can mask real provider failure.

Required change:
- Shift to explicit failure signaling (or clearly labeled degraded mode) so runs do not appear successful with empty AI outputs.

---

## What Needs To Be Updated

### 1. Documentation Drift (P0/P1)

Files:
- `README.md`
- `docs/desktop-distribution.md`
- `docs/plans/2026-01-29-podcast-pipeline-design.md`

Required updates:
- Correct backend build/packaging entrypoint references.
- Update desktop/backend API examples to real current schemas.
- Resolve design-vs-implementation mismatch around `research` stage and output artifacts.

### 2. Quality Gates / Coverage Expectations (P1)

File:
- `pyproject.toml`

Issue:
- Coverage gate is set to `38`, while production-critical modules remain lightly covered.

Required updates:
- Raise coverage expectations and/or add per-module minimums for:
  - `stages/render.py`
  - `stages/transcribe.py`
  - `providers/gemini.py`
  - `providers/kimi.py`
  - `ui/app.py`

---

## What Needs To Be Added

### 1. Cross-Stack Contract Tests for Desktop <-> FastAPI (P0)

Add tests that validate:
- Exact `/health` response shape
- Exact `/jobs` response shape
- `POST /jobs` request body contract (`video_path` etc.)
- `POST /jobs/{id}/run` body requirements and defaults

Recommended new files:
- `tests/test_desktop_api_contract.py` (Python-side contract fixtures)
- Desktop-side API schema assertions under `desktop/src/lib/` test setup (if TS test harness is added)

### 2. Real E2E Smoke Paths (P1)

Add integration coverage for:
- Create -> ingest -> transcribe -> analyze -> review -> render with sample media
- Service mode and desktop-side recovery resume flow
- Render outputs for selected target platforms

---

## What Needs To Be Implemented

### 1. Missing/Partial Output Artifacts from Design (P1)

Files:
- `src/podcast_pipeline/stages/render.py`
- `src/podcast_pipeline/stages/review.py`
- `src/podcast_pipeline/ui/app.py`

Implement (or explicitly de-scope in design/docs):
- Apple chapters file export
- Platform metadata files where required
- Thumbnail asset workflow parity with design expectations

### 2. First-Class Research Stage (if design is kept as source of truth) (P1)

Files:
- `src/podcast_pipeline/stages/` (new `research.py`)
- `src/podcast_pipeline/pipeline.py`
- `src/podcast_pipeline/models/job.py`
- `src/podcast_pipeline/cli.py`
- `src/podcast_pipeline/service/routes/jobs.py` (if stage routing exposed)

Implement:
- Stage lifecycle/state/status for research
- Resume semantics and outputs tracking at stage level
- Clear dependency ordering and failure behavior

---

## Priority Plan

### P0 (Do First)
- Fix desktop/backend API contract mismatches
- Fix desktop backend binary build entrypoint references (docs + CI/workflow + local build instructions)
- Add contract tests to prevent re-breakage

### P1 (Next)
- Remove UI placeholder behavior and wire real marketing regeneration
- Resolve filler data shape mismatch
- Decide and enforce `research` stage architecture (implement or de-scope)
- Raise test depth in critical runtime modules

### P2 (Then)
- Expand artifact parity with full design output set
- Improve degraded-mode observability and operator visibility for AI-provider failures

---

## Verification Evidence Snapshot

Commands run during audit:
- `uv run pytest -q` (passed)
- `uv run pytest --collect-only` (223 tests collected)
- `uv run pytest --cov=src/podcast_pipeline --cov-report=term-missing -q` (54.41% total coverage)
- direct API probes confirming:
  - `/health` keys: `["status"]`
  - `/jobs` top-level shape: object with `jobs`
  - `/jobs/{id}/run` no-body request returns `422`, empty JSON body accepted
