---
phase: 10-tauri-desktop-application-distribution
plan: 06
subsystem: ui
tags: [react, zustand, tailwind, typescript, appshell, view-routing, sidecar, recovery]

requires:
  - phase: 10-03
    provides: AppShell/Sidebar/Header layout, useSidecarStore, useUIStore, TanStack Query hooks
  - phase: 10-04
    provides: IngestionView, TranscriptView, useJobMutations
  - phase: 10-05
    provides: AudioSyncView, BrandingView

provides:
  - Rebuilt App.tsx: AppShell + 4-view routing replacing 911-line monolith
  - BootScreen: animated spinner card shown during sidecar startup
  - ConnectionError: retry card shown when backend is unreachable
  - RecoveryBanner: dismissible banner listing interrupted jobs after reconnect
  - ViewRouter: switch statement routing ingestion/audio/transcript/branding views
  - Boot sequence wired to useSidecarStore (setStatus/setSidecar/setError)
  - beforeunload handler calling stopSidecar() on window close

affects: []

tech-stack:
  added: []
  patterns:
    - "Boot sequence: bootAttempted ref guard + async boot() + checkHealth() fallback for coexistence mode"
    - "Recovery: useEffect keyed on status='connected' triggers checkRecovery() once, stores in local state"
    - "View routing: switch statement in ViewRouter component (no router library) — 4 cases + default"
    - "Sidecar state: useSidecarStore replaces all local useState for status/error/sidecar"
    - "Tailwind-only render: no CSSProperties, no inline style objects anywhere in App.tsx"

key-files:
  created: []
  modified:
    - desktop/src/App.tsx

key-decisions:
  - "Recovery banner only shown when resumable_jobs.length > 0 or corrected > 0 — no noise for clean restarts"
  - "handleRetry uses checkHealth() directly (not bootBackend()) — avoids restarting an already-running sidecar"
  - "BootScreen shown for 'connecting' status only — not shown on reconnect (retry goes direct to error or connected)"
  - "RecoveryBanner rendered inside AppShell wrapper (mx-6 mt-4) to stay within the layout, above ViewRouter content"
  - "ViewRouter is a standalone pure component — no hooks, receives activeView as prop string"

patterns-established:
  - "App shell pattern: status guard (connecting → BootScreen, disconnected → ConnectionError, connected → AppShell)"
  - "Recovery pattern: single useEffect triggered by status change, stores RecoveryStatus locally for dismissal"

duration: 2min
completed: 2026-02-25
---

# Phase 10 Plan 06: App.tsx Integration (AppShell + 4-View Routing) Summary

**911-line monolithic App.tsx replaced with 277-line clean component: AppShell layout + ViewRouter switch routing 4 views via Zustand activeView, with preserved boot sequence wired to useSidecarStore and dismissible RecoveryBanner for interrupted jobs**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-25T21:48:27Z
- **Completed:** 2026-02-25T21:49:50Z
- **Tasks:** 1 of 2 (Task 2 pending human verification)
- **Files modified:** 1 modified

## Accomplishments
- App.tsx reduced from 911 lines to 277 lines (70% reduction)
- Boot sequence preserved and wired to useSidecarStore: `bootBackend()` on mount, `checkHealth()` fallback for coexistence mode, `bootAttempted` ref guard
- `beforeunload` handler preserved calling `stopSidecar()`
- Recovery check fires once when `status === 'connected'`, shows `RecoveryBanner` with dismissal
- `ViewRouter` component routes ingestion/audio/transcript/branding via switch statement
- All state moved from `useState` to `useSidecarStore` (status, error, sidecar)
- Zero inline CSS — all Tailwind classes using `var(--color-*)` design tokens
- `pnpm build` passes: 1813 modules transformed, 375 kB bundle, 1.81s
- TypeScript strict mode — zero errors (`npx tsc --noEmit` clean)

## Task Commits

1. **Task 1: Rebuild App.tsx with AppShell layout and view routing** - `9556532` (feat)
2. **Task 2: Visual verification** - pending human verification

**Plan metadata:** (pending final commit after human verification)

## Files Created/Modified
- `desktop/src/App.tsx` - Root component: boot sequence (useSidecarStore), BootScreen, ConnectionError, RecoveryBanner, ViewRouter (4 views), AppShell integration

## Decisions Made
- Recovery banner rendered inside AppShell layout area (mx-6 mt-4 padding) to remain within sidebar/header chrome
- `handleRetry` calls `checkHealth()` directly rather than re-running `bootBackend()` — avoids starting a duplicate sidecar process when backend is already running but temporarily unreachable
- `BootScreen` only shown for `status === 'connecting'` — reconnect attempts go directly to `ConnectionError` if they fail
- `ViewRouter` is a pure function component with no hooks, receiving `activeView: string` as prop (not `ActiveView` type) to keep it loosely coupled

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 10 is complete: all 6 plans executed
- App.tsx now wires all Phase 10 components into a complete navigable desktop UI
- Human verification (Task 2) required to confirm visual rendering before phase is fully closed
- No structural blockers — build passes, TypeScript clean

---
*Phase: 10-tauri-desktop-application-distribution*
*Completed: 2026-02-25*

## Self-Check: PASSED

- `desktop/src/App.tsx` verified on disk (277 lines)
- Task 1 commit `9556532` confirmed in git log
- `pnpm build` passed (1813 modules, 375 kB bundle)
- `npx tsc --noEmit` passed (zero errors)
- All 5 verification grep checks passed: AppShell, IngestionView, AudioSyncView, TranscriptView, BrandingView, bootBackend, useUIStore, useSidecarStore
