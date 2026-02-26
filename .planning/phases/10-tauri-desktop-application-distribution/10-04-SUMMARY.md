---
phase: 10-tauri-desktop-application-distribution
plan: 04
subsystem: ui
tags: [react, tanstack-query, zustand, tauri, tailwind, typescript, drag-drop]

requires:
  - phase: 10-03
    provides: Zustand uiStore/sidecarStore, TanStack Query hooks (useJobs, useJobDetail, useSystemStatus), AppShell/Sidebar/Header layout, shadcn/ui components

provides:
  - useJobMutations.ts: TanStack Query useMutation hooks for createJob, runJob, resumeJob, deleteJob (all invalidate ['jobs'] on success)
  - IngestionView.tsx: native Tauri v2 drag-drop via onDragDropEvent, system readiness banner, job list with pipeline stage progress bars, selected job detail panel
  - TranscriptView.tsx: scrollable transcript with speaker labels, filler word toggle (highlight/opacity/strikethrough), category filter, stats footer, graceful fallback

affects:
  - 10-05 (AudioSyncView can import useJobMutations for job actions)
  - 10-06 (BrandingView can use same mutation hook pattern)

tech-stack:
  added: []
  patterns:
    - "useMutation with onSuccess invalidateQueries(['jobs']) for cache invalidation after job lifecycle actions"
    - "Dynamic Tauri import in useEffect with try/catch fallback: sets showManualInput when not in Tauri context"
    - "Tauri v2 DragDropEvent uses enter/over/drop/leave (not hover/cancel as described in some docs)"
    - "Pipeline stage progress bar: 5 segments per STAGE_ORDER, colored by stage status with animate-pulse for running"
    - "Speaker label color derived from hash of speaker string, cycling through 6 color classes"
    - "Transcript data loaded from backend outputs endpoint with structured fallback to outputs list display"

key-files:
  created:
    - desktop/src/hooks/useJobMutations.ts
    - desktop/src/views/IngestionView.tsx
    - desktop/src/views/TranscriptView.tsx
  modified: []

key-decisions:
  - "Tauri v2 DragDropEvent types are enter/over/drop/leave (not hover/cancel from plan spec) — fixed per actual @tauri-apps/api/webview type definitions"
  - "useJobDetail in JobDetailPanel is called per-card for selected job — no additional state needed"
  - "Transcript load attempts backend /jobs/{id}/outputs/transcribe/transcript.json endpoint; falls back to showing outputs list if unavailable"
  - "Manual path input shown by default when not in Tauri context (showManualInput fallback), hidden in Tauri context (drag-drop primary)"
  - "Delete job mutation uses removeQueries for the specific job's detail query in addition to invalidating the list"

patterns-established:
  - "View pattern: named export function (no default), reads selectedJobId from useUIStore, uses TanStack Query hooks"
  - "Mutation hook pattern: useMutation<ReturnType, Error, VariablesType> with typed mutationFn and onSuccess cache invalidation"
  - "Graceful Tauri fallback: dynamic import in useEffect with empty catch block + setShowManualInput(true)"

duration: 5min
completed: 2026-02-25
---

# Phase 10 Plan 04: Ingestion Dashboard + Transcript Timeline Summary

**Tauri v2 native drag-drop ingestion view with pipeline stage progress bars, system readiness banner, and scrollable transcript view with filler word toggle and speaker labels**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-25T21:39:22Z
- **Completed:** 2026-02-25T21:43:54Z
- **Tasks:** 2
- **Files modified:** 3 created, 0 modified

## Accomplishments
- IngestionView provides native OS file drag-drop via `getCurrentWebview().onDragDropEvent()` with graceful fallback to manual path input in browser dev mode
- Pipeline stage progress bar: 5 segments (ingest/transcribe/analyze/review/render) with color-coded status (green/amber-pulse/red/gray)
- System readiness banner consumes `useSystemStatus()` — amber warning for not-ready, green indicator for all-clear with binary/model details
- TranscriptView renders scrollable transcript with per-speaker colored badges, mm:ss timestamps, and filler word highlighting
- Filler word toggle: amber highlight when visible, opacity-30 strikethrough when hidden; category dropdown filter when categories present
- Stats footer: total duration, word count, speaker count, filler percentage
- All 3 files type-check cleanly; pnpm build passes (80 modules, 242.83 kB bundle)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create job mutation hooks + Ingestion Dashboard view** - `d6ccef8` (feat)
2. **Task 2: Create Transcript Timeline view** - `78e1768` (feat)

**Plan metadata:** (pending final commit)

## Files Created/Modified
- `desktop/src/hooks/useJobMutations.ts` - useCreateJob, useRunJob, useResumeJob, useDeleteJob mutations with cache invalidation
- `desktop/src/views/IngestionView.tsx` - drag-drop zone, system readiness banner, job cards with pipeline progress, detail panel (606 lines)
- `desktop/src/views/TranscriptView.tsx` - scrollable transcript, filler toggle, speaker labels, stats footer (632 lines)

## Decisions Made
- Tauri v2 `DragDropEvent` types are `enter/over/drop/leave` — the plan spec mentioned `hover/cancel` which are not valid type values in the actual `@tauri-apps/api/webview` package. Fixed per type compiler error.
- `TranscriptView` attempts to fetch transcript JSON from backend; falls back to listing the stage's output file paths with a message explaining when live preview will be available.
- `useDeleteJob` calls both `invalidateQueries(['jobs'])` and `removeQueries(['jobs', jobId])` to avoid stale detail cache after deletion.
- Manual input in IngestionView is always shown once triggered — non-destructive; does not hide the drop zone.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Tauri v2 DragDropEvent type values**
- **Found during:** Task 1 (IngestionView implementation)
- **Issue:** Plan specified `event.payload.type === 'hover'` and `'cancel'` but actual Tauri v2 types are `'enter' | 'over' | 'drop' | 'leave'` — TypeScript error TS2367 "comparison appears unintentional"
- **Fix:** Changed drag-over trigger to `enter || over`, drag-cancel to `leave`, matching actual `@tauri-apps/api/webview` DragDropEvent union type
- **Files modified:** `desktop/src/views/IngestionView.tsx`
- **Verification:** `npx tsc --noEmit` passes cleanly
- **Committed in:** d6ccef8 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - type bug)
**Impact on plan:** Fix was necessary for TypeScript correctness; functionally equivalent — drag enter/over both trigger the visual drag-over state.

## Issues Encountered
None beyond the Tauri v2 type correction above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- IngestionView and TranscriptView are ready to be wired into AppShell's view router (replacing placeholder content area in App.tsx)
- useJobMutations is available for AudioSyncView (10-05) and BrandingView (10-06) to use for job actions
- Both views degrade gracefully when no job is selected or backend data is unavailable
- pnpm build passes cleanly — no blocking issues for 10-05

---
*Phase: 10-tauri-desktop-application-distribution*
*Completed: 2026-02-25*

## Self-Check: PASSED

All 3 created files verified on disk. Both task commits (d6ccef8, 78e1768) confirmed present.
