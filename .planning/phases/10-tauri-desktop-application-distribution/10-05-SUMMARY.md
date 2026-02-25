---
phase: 10-tauri-desktop-application-distribution
plan: 05
subsystem: ui
tags: [wavesurfer, tauri, react, tailwind, zustand, tanstack-query, typescript]

requires:
  - phase: 10-03
    provides: Zustand uiStore (selectedJobId), TanStack Query useJobDetail hook, AppShell layout
  - phase: 10-04
    provides: IngestionView pattern for how views consume stores/hooks

provides:
  - AudioSyncView: wavesurfer.js v7 waveform display with Tauri convertFileSrc audio loading
  - AudioSyncView: sync offset slider (-5000ms to +5000ms) with auto-detected offset display
  - AudioSyncView: playback controls (play/pause, current time, duration, zoom slider)
  - AudioSyncView: track info panel (input file, job status, duration, audio file path)
  - BrandingView: two-panel brand profile editor + export settings
  - BrandingView: brand identity (name, voice, visual identity, caption style)
  - BrandingView: export target checkboxes for 9 platform targets
  - BrandingView: thumbnail settings and sound kit configuration

affects:
  - 10-06 (TranscriptView — follows same view pattern established in 10-04 and 10-05)

tech-stack:
  added: []
  patterns:
    - "WaveSurfer.create() in useEffect with containerRef, destroyed on cleanup — NOT state"
    - "convertFileSrc() from @tauri-apps/api/core for all audio file paths (Tauri security)"
    - "Local form state (useState) for brand config where no REST endpoint exists yet"
    - "Sub-components (FormLabel, TextInput, SectionCard, Toggle) for DRY form layout"
    - "extractAudioPath() searches stage outputs by file extension to find audio files"

key-files:
  created:
    - desktop/src/views/AudioSyncView.tsx
    - desktop/src/views/BrandingView.tsx
  modified: []

key-decisions:
  - "WaveSurfer instance held in wsRef (not useState) to prevent re-render loops on every tick"
  - "convertFileSrc() used for all audio URLs — Tauri webview security model rejects raw file:// paths"
  - "extractAudioPath() derives audio path from ingest stage outputs array (no dedicated audio field in JobDetail)"
  - "BrandingView state is fully local — backend has no /branding/profiles REST endpoint yet"
  - "Apply Offset button deferred — logs offset value, backend mutation endpoint not yet available"
  - "autoOffset is null for now — reading sync_artifact.json requires extra backend fetch not in scope"

patterns-established:
  - "View pattern: import useUIStore + useJobDetail, derive data from job.stages[stageName].outputs"
  - "Empty state pattern: check !selectedJobId first, then isLoading, then isError, then data-specific conditions"
  - "Audio loading pattern: convertFileSrc(path) before ws.load() — always, no exceptions"

duration: 4min
completed: 2026-02-25
---

# Phase 10 Plan 05: Audio Sync Editor + Branding Studio Summary

**Wavesurfer.js v7 waveform editor with Tauri convertFileSrc audio loading and a two-panel brand profile/export configuration studio completing the 4-view desktop UI**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T21:39:56Z
- **Completed:** 2026-02-25T21:43:55Z
- **Tasks:** 2
- **Files modified:** 2 created, 0 modified

## Accomplishments
- AudioSyncView mounts wavesurfer.js v7 instance via useEffect with WaveSurfer.create(), proper cleanup via ws.destroy() on unmount
- Audio loaded via convertFileSrc() (converts absolute paths to tauri://localhost/path) — Tauri webview security requirement
- Sync offset slider provides -5000ms to +5000ms manual adjustment with formatMs() display; auto-detected offset display when available
- Playback controls (play/pause, current time / total duration, zoom slider) wired to wavesurfer instance events
- BrandingView two-panel layout: brand identity + visual identity + caption style (left) + export targets + thumbnail + sound kit (right)
- 9 export platform checkboxes (youtube, youtube_ultra, spotify, spotify_video, apple, apple_video, apple_hls, tiktok, instagram_reels) with format descriptions
- pnpm build passes cleanly (80 modules transformed)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Audio Sync Editor view with wavesurfer.js** - `390cf73` (feat)
2. **Task 2: Create Branding Studio view** - `17af6c7` (feat)

**Plan metadata:** (pending final commit)

## Files Created/Modified
- `desktop/src/views/AudioSyncView.tsx` - Waveform editor: WaveSurfer.create(), convertFileSrc audio loading, sync offset slider, playback controls, track info panel
- `desktop/src/views/BrandingView.tsx` - Brand profile form: brand identity, visual identity, caption style, export targets, thumbnail settings, sound kit

## Decisions Made
- WaveSurfer instance stored in `wsRef` (useRef), not useState — avoids infinite re-renders since wavesurfer fires events constantly
- `convertFileSrc()` wraps all audio paths before `ws.load()` — Tauri webview security model silently rejects raw `file://` or absolute paths
- `extractAudioPath()` scans `job.stages["ingest"].outputs` by file extension since `JobDetail` has no dedicated audio field
- BrandingView uses fully local state (`useState`) — backend has no `/branding/profiles` CRUD endpoint yet; save simulates success
- Apply Offset button is deferred (console.info) — backend sync offset mutation endpoint not yet available
- `autoOffset` returns null — reading `sync_artifact.json` would require an additional backend fetch not planned in this scope

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 views now exist: IngestionView (10-04), AudioSyncView (10-05), BrandingView (10-05) — TranscriptView planned for 10-06
- AudioSyncView and BrandingView follow the same store/hook patterns as IngestionView
- Apply Offset backend mutation can be wired once backend endpoint is available (no structural change needed)
- Brand profile CRUD can be connected once `/branding/profiles` endpoint is implemented

---
*Phase: 10-tauri-desktop-application-distribution*
*Completed: 2026-02-25*

## Self-Check: PASSED

All created files verified on disk. Both task commits (390cf73, 17af6c7) confirmed in git log.
