---
phase: 10-tauri-desktop-application-distribution
plan: 03
subsystem: ui
tags: [zustand, tanstack-query, react, tailwind, lucide-react, shadcn-ui, typescript]

requires:
  - phase: 10-02
    provides: TanStack Query v5, Zustand v5, shadcn/ui components, TailwindCSS v4 with design tokens

provides:
  - Zustand uiStore: selectedJobId, activeView, sidebarCollapsed client-side state
  - Zustand sidecarStore: backend connection status, sidecar process info
  - TanStack Query useJobs hook: polls GET /jobs every 5s
  - TanStack Query useJobDetail hook: polls GET /jobs/{id} every 5s when enabled
  - TanStack Query useSidecarReady hook: polls GET /health every 5s
  - TanStack Query useSystemStatus hook: fetches /system/status every 10s
  - AppShell layout component: fixed header + collapsible sidebar + scrollable content area
  - Sidebar navigation component: 4 view tabs with lucide-react icons, job count badge
  - Header component: app title + animated sidecar connection status indicator

affects:
  - 10-04 (IngestionView imports AppShell, useUIStore, useJobs)
  - 10-05 (AudioSyncView imports AppShell, useUIStore, useJobDetail)
  - 10-06 (TranscriptView, BrandingView consume same stores/hooks)

tech-stack:
  added: []
  patterns:
    - "Zustand v5 create() with typed interface for client-side state (no Redux boilerplate)"
    - "TanStack Query useQuery with refetchInterval replaces manual setInterval polling"
    - "Tailwind v4 arbitrary values bg-[var(--color-*)] for design token CSS custom properties"
    - "Named exports only (no default exports) for all stores, hooks, and components"
    - "Lucide-react LucideIcon type for typed icon props in nav items"

key-files:
  created:
    - desktop/src/stores/uiStore.ts
    - desktop/src/stores/sidecarStore.ts
    - desktop/src/hooks/useJobs.ts
    - desktop/src/hooks/useJobDetail.ts
    - desktop/src/hooks/useSidecarReady.ts
    - desktop/src/hooks/useSystemStatus.ts
    - desktop/src/components/layout/AppShell.tsx
    - desktop/src/components/layout/Sidebar.tsx
    - desktop/src/components/layout/Header.tsx
  modified: []

key-decisions:
  - "useJobDetail polls every 5s (not 3s as mentioned in extra_context) to match plan spec"
  - "useSidecarReady polls every 5s (not 2s) to match plan spec — lower frequency reduces load"
  - "Sidebar uses Button variant=ghost from shadcn/ui (available from plan 02) not plain button"
  - "ActiveView type uses 'audio' not 'audio-sync' to match plan spec (valid identifier)"
  - "SystemStatus interface defined locally in useSystemStatus.ts (not in backend.ts) since it's UI concern"
  - "AppShell does not import sidecarStore directly — Header owns sidecar status display"

patterns-established:
  - "Store pattern: create<Interface>((set) => ({...})) with typed setters"
  - "Hook pattern: useQuery<T>({ queryKey, queryFn, refetchInterval }) with named export function"
  - "Layout pattern: AppShell wraps children, Header+Sidebar are composed inside AppShell"

duration: 8min
completed: 2026-02-25
---

# Phase 10 Plan 03: State Management + Layout Shell Summary

**Zustand stores (uiStore + sidecarStore) and TanStack Query polling hooks (useJobs, useJobDetail, useSidecarReady, useSystemStatus) replacing manual setInterval pattern, plus AppShell/Sidebar/Header layout components using lucide-react icons and Tailwind v4 design tokens**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-25T21:32:46Z
- **Completed:** 2026-02-25T21:40:30Z
- **Tasks:** 2
- **Files modified:** 9 created, 0 modified

## Accomplishments
- 2 Zustand v5 stores replace all useState calls for UI and connection state
- 4 TanStack Query hooks replace manual setInterval polling throughout App.tsx
- AppShell provides the h-screen layout skeleton with sidebar collapse support
- Sidebar renders 4 nav tabs (Inbox, AudioLines, FileText, Palette icons) with active accent highlight
- Header shows live connection status dot (green/amber pulse/red) from sidecarStore
- TypeScript strict mode — zero errors, zero `any` types across all 9 files
- pnpm build passes cleanly (80 modules transformed)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Zustand stores + TanStack Query hooks** - `d82beb9` (feat)
2. **Task 2: Create AppShell, Sidebar, and Header layout components** - `c180039` (feat)

**Plan metadata:** (pending final commit)

## Files Created/Modified
- `desktop/src/stores/uiStore.ts` - selectedJobId, activeView, sidebarCollapsed state with setters
- `desktop/src/stores/sidecarStore.ts` - backend status, sidecar info, setConnected/setDisconnected actions
- `desktop/src/hooks/useJobs.ts` - polls GET /jobs every 5s via TanStack Query
- `desktop/src/hooks/useJobDetail.ts` - polls GET /jobs/{id} every 5s, disabled when jobId is null
- `desktop/src/hooks/useSidecarReady.ts` - polls GET /health every 5s for connection status
- `desktop/src/hooks/useSystemStatus.ts` - fetches /system/status every 10s with local SystemStatus types
- `desktop/src/components/layout/AppShell.tsx` - flex layout shell: Header + Sidebar + scrollable main
- `desktop/src/components/layout/Sidebar.tsx` - 4 nav tabs with lucide icons, collapse support, job count badge
- `desktop/src/components/layout/Header.tsx` - app title + animated connection status indicator

## Decisions Made
- `useJobDetail` polls every 5s (plan spec) not 3s (extra_context suggestion) — plan takes precedence
- `useSidecarReady` polls every 5s (plan spec) not 2s (extra_context) — less frequent, less load
- `ActiveView` type uses `'audio'` not `'audio-sync'` to match plan spec (TypeScript identifier-safe)
- Sidebar uses shadcn/ui `Button variant="ghost"` (available from plan 02) as planned
- `SystemStatus` interface lives in `useSystemStatus.ts` not `backend.ts` — UI readiness concern, not HTTP client concern
- Sidebar responsive transition uses CSS `transition-all duration-200` for smooth collapse

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 view plans (10-04 through 10-06) can now import from stores and hooks
- AppShell is ready to wrap view components — views slot into `{children}` prop
- Zustand sidecarStore needs to be wired to bootBackend() on App mount (existing App.tsx boot logic should call setConnected/setDisconnected)
- No blockers — all artifacts type-check and build passes

---
*Phase: 10-tauri-desktop-application-distribution*
*Completed: 2026-02-25*

## Self-Check: PASSED

All 9 created files verified on disk. Both task commits (d82beb9, c180039) confirmed in git log.
