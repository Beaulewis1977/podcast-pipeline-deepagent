# GSD Key=Value Migration Checklist

- Audit time: `2026-02-12 17:24:03`
- Codex root scanned: `/home/kngpnn/.codex`
- GSD files scanned: **144**
- Files with issues: **0**
- Total checklist items: **0**

## Issue Summary

- No positional usage detected.

## Canonical Command Forms

| Command | Key=Value Form |
|---|---|
| `/gsd:add-phase` | `description="<text>"` |
| `/gsd:add-todo` | `description="<text>"` |
| `/gsd:audit-milestone` | `version="<milestone-version>"` |
| `/gsd:check-todos` | `area=<filter>` |
| `/gsd:complete-milestone` | `version=<milestone-version>` |
| `/gsd:debug` | `issue="<description>"` |
| `/gsd:discuss-phase` | `phase=<number>` |
| `/gsd:execute-phase` | `phase=<number> [--gaps-only]` |
| `/gsd:insert-phase` | `after=<phase-number> description="<text>"` |
| `/gsd:list-phase-assumptions` | `phase=<number>` |
| `/gsd:map-codebase` | `focus=<tech|arch|quality|concerns>` |
| `/gsd:new-milestone` | `name="<milestone name>"` |
| `/gsd:plan-phase` | `phase=<number> [--research] [--skip-research] [--gaps] [--skip-verify]` |
| `/gsd:remove-phase` | `phase=<number>` |
| `/gsd:research-phase` | `phase=<number>` |
| `/gsd:verify-work` | `phase=<number>` |

## Global Checklist

- [ ] Update all `argument-hint:` entries that are still positional.
- [ ] Update all command examples that pass bare values (e.g. `... 4`).
- [ ] Update all routing/"next command" snippets to key=value form.
- [ ] Re-run this mapper and confirm `Total checklist items: 0`.

## Hotspots (Fix First)

| File | Items |
|---|---:|

## File Checklist

- [x] No file-level changes required.
