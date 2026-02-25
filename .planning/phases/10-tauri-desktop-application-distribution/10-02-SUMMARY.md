---
phase: 10-tauri-desktop-application-distribution
plan: "02"
subsystem: desktop-frontend-toolchain
tags:
  - tauri
  - frontend
  - tailwindcss
  - tanstack-query
  - shadcn-ui
  - ci
dependency_graph:
  requires:
    - 10-01 (Tauri project scaffold)
  provides:
    - Frontend toolchain for all UI plans (10-03, 10-04, 10-05)
    - CI --onedir artifact pipeline for backend sidecar
    - Tailwind v4 utility classes
    - TanStack Query v5 global context
    - shadcn/ui component library
  affects:
    - .github/workflows/desktop-release.yml
    - desktop/src-tauri/tauri.conf.json
    - desktop/src-tauri/capabilities/default.json
    - desktop/src-tauri/build.rs
    - desktop/package.json
    - desktop/vite.config.ts
    - desktop/src/styles.css
    - desktop/src/main.tsx
    - desktop/scripts/prepare-sidecars.mjs
tech_stack:
  added:
    - "@tanstack/react-query v5.90.21"
    - "zustand v5.0.11"
    - "wavesurfer.js v7.12.1"
    - "@wavesurfer/react v1.0.12"
    - "tailwindcss v4.2.1"
    - "@tailwindcss/vite v4.2.1"
    - "class-variance-authority v0.7.1"
    - "clsx v2.1.1"
    - "tailwind-merge v3.5.0"
    - "lucide-react v0.575.0"
    - "@radix-ui/react-slot v1.2.4"
    - "@radix-ui/react-tabs v1.1.13"
    - "@radix-ui/react-progress v1.1.8"
    - "@radix-ui/react-separator v1.1.8"
    - "@radix-ui/react-scroll-area v1.2.10"
  patterns:
    - "Tailwind v4 CSS-first config (no tailwind.config.js, uses @theme block)"
    - "@tailwindcss/vite plugin instead of PostCSS"
    - "shadcn/ui components installed manually (no interactive init)"
    - "@/* path alias for clean component imports"
    - "TanStack Query with QueryClientProvider wrapping React tree"
    - "PyInstaller --onedir with _internal/ bundled via bundle.resources"
key_files:
  created:
    - desktop/components.json
    - desktop/src/lib/utils.ts
    - desktop/src/components/ui/button.tsx
    - desktop/src/components/ui/card.tsx
    - desktop/src/components/ui/tabs.tsx
    - desktop/src/components/ui/progress.tsx
    - desktop/src/components/ui/badge.tsx
    - desktop/src/components/ui/separator.tsx
    - desktop/src/components/ui/scroll-area.tsx
  modified:
    - .github/workflows/desktop-release.yml
    - desktop/src-tauri/tauri.conf.json
    - desktop/src-tauri/capabilities/default.json
    - desktop/src-tauri/build.rs
    - desktop/package.json
    - desktop/vite.config.ts
    - desktop/src/styles.css
    - desktop/src/main.tsx
    - desktop/tsconfig.json
    - desktop/scripts/prepare-sidecars.mjs
decisions:
  - "Used @radix-ui/react-badge does not exist so badge component uses CVA only (no radix primitive needed for badge)"
  - "Installed shadcn/ui components manually instead of running interactive npx shadcn init"
  - "Added @/* path alias to both tsconfig.json and vite.config.ts for consistent resolution"
  - "bundle.resources entry added for _internal/**/* to ensure Python dep tree is bundled in production"
  - "prepare-sidecars.mjs updated to detect --onedir via _internal/ sibling directory presence"
metrics:
  duration: "5m 27s"
  completed: "2026-02-25"
  tasks_completed: 2
  tasks_total: 2
  files_created: 10
  files_modified: 10
---

# Phase 10 Plan 02: Frontend Toolchain Setup Summary

**One-liner:** PyInstaller migrated to --onedir with _internal/ bundling, full frontend toolchain installed (TailwindCSS v4, TanStack Query v5, Zustand v5, wavesurfer.js v7, shadcn/ui), pnpm build succeeds.

## What Was Built

### Task 1: CI + Tauri Config + Sidecar Infrastructure

**CI workflow (`.github/workflows/desktop-release.yml`):**
- Changed `--onefile` to `--onedir` in PyInstaller build step
- Updated artifact copy step to `cp -r dist/podcast-backend backend-dist/podcast-backend-${{ matrix.target }}`
- Updated `BACKEND_BIN` env to point to binary inside the directory: `src-tauri/binaries/podcast-backend-${{ matrix.settings.target }}/podcast-backend${{ matrix.settings.ext }}`

**tauri.conf.json:**
- Window: `width: 1440, height: 900, minWidth: 1024, minHeight: 700`
- CSP extended: `img-src 'self' data: blob:; media-src 'self' blob: tauri://localhost`
- externalBin: `binaries/podcast-backend/podcast-backend` (directory-based path)
- bundle.resources: `binaries/podcast-backend/_internal/**/*` (Python dep tree)

**capabilities/default.json:**
- Added `core:window:allow-set-title`
- Added `core:webview:allow-print`
- Drag-drop works via existing `core:default` (no additional permission needed in Tauri v2)

**prepare-sidecars.mjs:**
- Detects `--onedir` layout by checking for `_internal/` sibling directory
- When `--onedir` detected: copies entire directory to `binaries/podcast-backend/`, renames binary to include target triple suffix
- Falls back to single-file copy for `--onefile` or plain binaries (backward compatible)
- ffmpeg/ffprobe: unchanged single-file copy logic

**build.rs:**
- Updated `SIDECARS` array to include `subpath_prefix` field
- `podcast-backend` now checked at `binaries/podcast-backend/podcast-backend-{triple}{ext}`
- ffmpeg/ffprobe: unchanged flat path check

### Task 2: Frontend Dependencies + Toolchain

**Dependencies installed:**
- Production: `@tanstack/react-query`, `zustand`, `wavesurfer.js`, `@wavesurfer/react`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, radix-ui primitives (slot, tabs, progress, separator, scroll-area)
- Dev: `tailwindcss v4`, `@tailwindcss/vite`

**vite.config.ts:** Added `tailwindcss()` plugin and `@/*` path alias via `resolve.alias`

**styles.css:** Replaced all custom CSS with Tailwind v4 `@import "tailwindcss"` + `@theme` block with dark glassmorphism color tokens

**main.tsx:** Wrapped `<App />` in `<QueryClientProvider>` with `staleTime: 5000, refetchInterval: 5000`

**tsconfig.json:** Added `baseUrl: "."` and `paths: { "@/*": ["./src/*"] }`

**shadcn/ui components:** Created manually in `src/components/ui/`:
- `button.tsx` (CVA variants: default, destructive, outline, secondary, ghost, link)
- `card.tsx` (Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter)
- `tabs.tsx` (Tabs, TabsList, TabsTrigger, TabsContent via Radix Tabs)
- `progress.tsx` (Progress via Radix Progress)
- `badge.tsx` (Badge with CVA variants)
- `separator.tsx` (Separator via Radix Separator, horizontal/vertical)
- `scroll-area.tsx` (ScrollArea + ScrollBar via Radix ScrollArea)
- `src/lib/utils.ts` (cn() helper combining clsx + tailwind-merge)

## Commits

| Hash | Message |
|------|---------|
| `8520e9f` | `chore(10-02): migrate CI to --onedir + update Tauri config + capabilities` |
| `c16de52` | `feat(10-02): install frontend deps, configure Tailwind v4, QueryClientProvider, shadcn/ui` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added @radix-ui packages for shadcn/ui components**
- **Found during:** Task 2 - shadcn/ui component creation
- **Issue:** Plan said "install shadcn/ui dependencies manually" but didn't list all Radix UI primitives needed
- **Fix:** Installed `@radix-ui/react-slot`, `@radix-ui/react-tabs`, `@radix-ui/react-progress`, `@radix-ui/react-separator`, `@radix-ui/react-scroll-area`
- **Note:** `@radix-ui/react-badge` does NOT exist on npm - badge component uses CVA only (no Radix primitive needed)

**2. [Rule 1 - Bug] Added @/* path alias to Vite config**
- **Found during:** Task 2 - first build attempt
- **Issue:** tsconfig.json path alias alone isn't sufficient; Vite also needs the alias configured for runtime module resolution
- **Fix:** Added `resolve.alias: { "@": resolve(__dirname, "./src") }` to vite.config.ts; imported `resolve` from `"path"`

## Self-Check: PASSED

All 19 key files verified present. Both task commits (8520e9f, c16de52) confirmed in git log.
