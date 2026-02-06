---
phase: 03-polishing-+-desktop-distribution
plan: 05
subsystem: recovery
tags: [recovery, resume, reconciliation, crash-restart, sidecar]

# Dependency graph
requires:
  - phase: 03-01
    provides: FastAPI service, supervisor runtime metadata, job state model
  - phase: 03-02
    provides: Tauri desktop shell with sidecar lifecycle
  - phase: 03-03
    provides: Streamlit service client with resume_job/list_resumable_jobs
provides:
  - Backend reconciliation logic for runtime/canonical state drift
  - Resumable job identification from persisted stage state
  - Desktop startup recovery hooks with Tauri invoke commands
  - Frontend recovery status banner with per-job resume actions
  - Streamlit resume entrypoint on dashboard
affects: [03-06, desktop-release, streamlit-ui]

# Tech tracking
tech-stack:
  added: [reqwest]
  patterns: [reconcile-then-resume, invoke-with-fallback, recovery-banner]

key-files:
  created:
    - src/podcast_pipeline/service/recovery.py
    - desktop/src-tauri/src/recovery.rs
    - desktop/src/lib/recovery.ts
  modified:
    - src/podcast_pipeline/service/app.py
    - src/podcast_pipeline/service/routes/jobs.py
    - src/podcast_pipeline/service/schemas.py
    - desktop/src-tauri/src/lib.rs
    - desktop/src-tauri/Cargo.toml
    - desktop/src-tauri/tauri.conf.json
    - desktop/src/App.tsx
    - src/podcast_pipeline/ui/app.py
  tested:
    - tests/test_job_recovery.py
---

## Summary

Implemented crash recovery and resume orchestration across backend, desktop, and Streamlit.

### Task 1: Backend reconciliation and resume service logic

**Commit:** `9c952ff feat(03-05): add backend reconciliation and resume service logic`

Created `src/podcast_pipeline/service/recovery.py` with:
- `reconcile_job()` — corrects stale runtime metadata against canonical stage state
- `reconcile_all_jobs()` — batch reconciliation across all job directories
- `list_resumable_jobs()` — identifies jobs with failed/interrupted stages
- `prepare_resume()` — resets target stage to pending and cleans runtime state
- `startup_reconcile()` — integrated into FastAPI lifespan for automatic startup cleanup

Added background resume support to `POST /jobs/{id}/resume` with `background` field in request schema.

28 regression tests cover reconciliation, resumable identification, and resume preparation.

### Task 2: Desktop startup recovery and resume flow

**Commit:** `67f9a55 feat(03-05): add desktop startup recovery and resume flow`

Created `desktop/src-tauri/src/recovery.rs` with Tauri commands:
- `check_recovery` — calls POST /jobs/reconcile then GET /jobs/resumable
- `trigger_resume` — calls POST /jobs/{id}/resume with background=true

Created `desktop/src/lib/recovery.ts` with TypeScript client:
- `checkRecovery()` — invoke with direct HTTP fallback for dev mode
- `triggerResume()` — invoke with direct HTTP fallback
- Typed interfaces for RecoveryStatus, ResumableJob, ResumeResult

Updated `desktop/src/App.tsx` with:
- Recovery status state management
- Recovery banner showing interrupted jobs with resume buttons
- Post-resume job list refresh and banner update
- Dismiss recovery banner action

Fixed pre-existing Tauri v2 compilation issue: removed `pub` from commands in lib.rs per Tauri v2 macro limitation, removed invalid `app.title` from tauri.conf.json.

### Task 3: Streamlit resume entrypoint and regression coverage

**Commit:** `c460032 feat(03-05): expose Streamlit resume entrypoint and regression coverage`

Updated `src/podcast_pipeline/ui/app.py` with:
- `render_resumable_jobs()` — queries backend for interrupted jobs, shows warning banner
- `resume_job_via_service()` — triggers resume through ServiceClient
- Recovery section at top of dashboard with per-job resume stage info
- Error handling for backend unavailable and resume failures

## Decisions

| Decision | Rationale |
|----------|-----------|
| Reconcile-then-resume pattern | Run reconciliation before listing resumable jobs to ensure stale state is corrected first |
| Tauri invoke with HTTP fallback | Allows recovery module to work both inside Tauri context and in dev/browser mode |
| Non-pub commands in lib.rs | Tauri v2 macro limitation: commands defined in lib.rs cannot be `pub` |
| reqwest for Rust HTTP | Async HTTP client needed for recovery commands that call backend endpoints |

## Verification

- 28 backend recovery tests passing
- Rust compiles clean (`cargo check` succeeds)
- Ruff lint and mypy pass on all Python changes
