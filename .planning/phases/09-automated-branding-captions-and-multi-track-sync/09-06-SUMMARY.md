---
status: complete
started: 2026-02-24
completed: 2026-02-24
---

# Summary: 09-06 — ASS Caption Engine

## What was built

A word-level ASS caption generator (`src/podcast_pipeline/utils/captions.py`) with per-aspect-ratio safe-zone templates and render-stage burn-in integration.

## Key files

### Created
- `src/podcast_pipeline/utils/captions.py` — 730 lines: word-level ASS generation, 3 aspect-ratio templates (16:9, 9:16, 1:1), CaptionStyleConfig
- `tests/test_captions.py` — 71 tests covering ASS generation, safe zones, word highlighting, config validation

### Modified
- `src/podcast_pipeline/config/settings.py` — CaptionConfig, CaptionStyleConfig with validation bounds
- `src/podcast_pipeline/stages/render.py` — burn_captions integration via toolkit
- `tests/test_render.py` — caption burn-in regression tests

## Design decisions

| Decision | Rationale |
|----------|-----------|
| Word-level highlight timing from word_alignment.json | Preserves per-word sync from transcription stage |
| Per-aspect-ratio safe-zone templates | Prevents caption occlusion on vertical/square platforms |
| Independent from transcribe stage imports | Maintains clean dependency boundary |
| CaptionConfig nested under BrandingConfig | Operator controls caption styling through branding profile |

## Self-Check: PASSED

- [x] Word-aligned ASS captions generated for 16:9, 9:16, 1:1
- [x] Per-word highlight timing preserved
- [x] Render burns ASS via libass with deterministic error handling
- [x] 71 tests passing
- [x] ruff + mypy clean
