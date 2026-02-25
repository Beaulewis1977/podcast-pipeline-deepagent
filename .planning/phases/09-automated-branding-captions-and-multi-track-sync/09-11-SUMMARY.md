---
phase: 09-automated-branding-captions-and-multi-track-sync
plan: 11
subsystem: thumbnails
tags: [gemini-vision, google-genai, image-generation, thumbnails, ai-studio]

# Dependency graph
requires:
  - phase: 09-09
    provides: AI Thumbnail Studio dual-backend service with cache and branding overlay
provides:
  - Gemini Vision single-backend thumbnail generation via google.genai SDK
  - _audit_with_gemini_pro() function for future compositional auditing
  - Clean [thumbnails] optional-dependencies (no legacy packages)
affects: [thumbnail-generation, branding, analyze-stage, production-controls]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Gemini Vision image generation via generate_content with response_modalities=['TEXT','IMAGE']"
    - "Vision analysis via types.Part.from_bytes() for image input"
    - "Image bytes accessed via part.inline_data.data (no PIL dependency)"

key-files:
  created: []
  modified:
    - src/podcast_pipeline/utils/thumbnails.py
    - src/podcast_pipeline/config/settings.py
    - src/podcast_pipeline/ui/app.py
    - src/podcast_pipeline/service/supervisor.py
    - tests/test_thumbnails.py
    - tests/test_pipeline.py
    - tests/test_supervisor.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Single Gemini backend replaces dual Imagen 4 / FLUX.1 Schnell routing"
  - "gemini-2.5-flash-image for generation; gemini-3-pro-image-preview for future audit"
  - "Image bytes via part.inline_data.data -- no PIL/Pillow dependency"
  - "Field named model (not generation_model) to preserve analyze.py wiring"
  - "_audit_with_gemini_pro defined but not wired into generation flow in this plan"

patterns-established:
  - "Pattern 1: Gemini image generation via types.ImageConfig with aspect_ratio and output_mime_type"
  - "Pattern 2: Vision analysis via types.Part.from_bytes for image-to-text analysis"
  - "Pattern 3: _gemini_available() check for GEMINI_API_KEY + google.genai importability"

# Metrics
duration: 10min
completed: 2026-02-24
---

# Phase 9 Plan 11: Gemini Vision Model Pivot Summary

**Replaced Imagen 4 / FLUX.1 Schnell dual-backend with exclusive Gemini Vision thumbnail generation via google.genai SDK**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-24T17:17:24Z
- **Completed:** 2026-02-24T17:27:36Z
- **Tasks:** 4
- **Files modified:** 9

## Accomplishments
- Replaced all Imagen 4, FLUX.1 Schnell, Vertex AI, and VRAM preflight code with Gemini Vision
- Added _generate_gemini() using google.genai SDK with response_modalities=["TEXT","IMAGE"]
- Added _audit_with_gemini_pro() for future compositional auditing
- Cleaned [thumbnails] optional-dependencies (removed google-cloud-aiplatform, diffusers, optimum-quanto)
- All 1031 tests pass with zero failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor thumbnails.py and settings.py** - `bcd7a1e` (feat)
2. **Task 2: Clean up [thumbnails] dependencies** - `b4d5dbf` (chore)
3. **Task 3: Verify and fix analyze stage + UI wiring** - `b06f01a` (fix)
4. **Task 4: Overhaul test mocks and run full suite** - `05092e7` (test)
5. **Deviation: Remove stale FLUX references from supervisor** - `ef1ca1a` (fix)

## Files Created/Modified
- `src/podcast_pipeline/utils/thumbnails.py` - Gemini Vision single-backend thumbnail generation service
- `src/podcast_pipeline/config/settings.py` - ThumbnailGenerationConfig defaults to gemini-2.5-flash-image
- `src/podcast_pipeline/ui/app.py` - AI Thumbnail help text references Gemini Vision
- `src/podcast_pipeline/service/supervisor.py` - GPULease docstrings updated (removed FLUX references)
- `tests/test_thumbnails.py` - Gemini Vision endpoint mocks replacing all Imagen/FLUX mocks
- `tests/test_pipeline.py` - ThumbnailBackend.GEMINI references + GPU lease operation name
- `tests/test_supervisor.py` - GPU lease test operation names updated
- `pyproject.toml` - Empty [thumbnails] extras, cleaned mypy overrides
- `uv.lock` - Updated lockfile

## Decisions Made
- Single Gemini backend replaces dual Imagen 4 / FLUX.1 routing: simplifies architecture, removes Vertex AI auth complexity, eliminates VRAM/GPU requirements for thumbnails
- Kept field named `model` (not `generation_model`) to preserve analyze.py line 413 wiring: `model=gen_config.model`
- Image bytes accessed via `part.inline_data.data` (not `part.as_image()`) to avoid PIL dependency
- `_audit_with_gemini_pro()` defined but not wired into generation flow: supports future compositional auditing without scope creep
- Added `type: ignore[arg-type]` on vision analysis contents parameter: mypy list invariance issue with mixed Part/str union

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed stale FLUX references in supervisor docstrings and test operation names**
- **Found during:** Task 4 (holistic verification)
- **Issue:** GPULease docstrings and test operation strings still referenced "FLUX thumbnail generation" which is factually incorrect after the Gemini pivot
- **Fix:** Updated supervisor.py docstrings and example code; updated test_pipeline.py and test_supervisor.py operation name strings from "flux_thumbnail"/"flux" to "thumbnail_gen"
- **Files modified:** src/podcast_pipeline/service/supervisor.py, tests/test_pipeline.py, tests/test_supervisor.py
- **Verification:** grep -ri "FLUX|flux" src/ tests/ returns zero matches
- **Committed in:** ef1ca1a

**2. [Rule 1 - Bug] Fixed mypy type errors on google.genai contents parameter**
- **Found during:** Task 1 (mypy verification)
- **Issue:** `list[str]` passed to `contents` parameter triggers mypy list invariance error; mixed `list[Part | str]` also fails
- **Fix:** Changed image generation to pass `contents=prompt` (string directly); added `type: ignore[arg-type]` for vision analysis mixed-type list
- **Files modified:** src/podcast_pipeline/utils/thumbnails.py
- **Verification:** uv run mypy src/podcast_pipeline/utils/thumbnails.py passes
- **Committed in:** bcd7a1e (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None beyond the documented deviations.

## User Setup Required
None - no external service configuration required. GEMINI_API_KEY is already used by the existing Gemini provider.

## Next Phase Readiness
- Phase 9 is now complete (11/11 plans executed)
- Thumbnail generation is exclusively Gemini Vision-powered
- All existing Phase 9 features remain intact: FFmpeg toolkit, MCP server, Claude provider, codec profiles, branding, captions, sync, sound kits, Brand Studio UI
- _audit_with_gemini_pro() is ready for downstream compositional auditing when needed

---
## Self-Check: PASSED

All 7 files verified present. All 5 commits verified in git log.

---
*Phase: 09-automated-branding-captions-and-multi-track-sync*
*Completed: 2026-02-24*
