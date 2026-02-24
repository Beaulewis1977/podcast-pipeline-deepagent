---
phase: 09-automated-branding-captions-and-multi-track-sync
plan: 05
subsystem: branding
tags: [pydantic, yaml, branding, brand-voice, prompt-injection, sanitization, platform-overrides]

# Dependency graph
requires:
  - phase: 09-automated-branding-captions-and-multi-track-sync/09-01
    provides: FFmpeg toolkit that downstream branding render stages will use
  - phase: 09-automated-branding-captions-and-multi-track-sync/09-03
    provides: Provider base class (_build_prompt) that brand_voice injection extends

provides:
  - BrandingProfile Pydantic model with brand_voice, visual assets, caption defaults, platform overrides
  - utils/branding.py load/save/resolve/load_active_profile helpers for branding/<name>.yaml
  - BrandingConfig in settings.py (active_profile + branding_dir fields) wired into Config
  - AnalyzeStage.resolve_branding_for_platform() and _resolve_brand_voice_for_analysis()
  - BaseProvider._build_prompt() brand_voice parameter with bounded BRAND VOICE block injection
  - Sanitized prompt injection: control char stripping + 2000-char truncation (double-gated)
  - 25+ regression tests covering profile CRUD, platform overrides, sanitization, prompt injection

affects:
  - 09-06 (caption burn-in — uses BrandingProfile caption_style)
  - 09-07 (thumbnail branding — uses BrandingProfile logo/border fields)
  - 09-08 (render pipeline — uses resolve_branding_for_platform)
  - future provider implementations (inherit _build_prompt brand_voice support)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - BrandingProfile as typed brand kit with deterministic merge: base then platform override
    - Secondary sanitization gate at prompt boundary (defense in depth beyond model validation)
    - load_active_profile() as None-safe entry point for pipeline stages
    - brand_voice injected via transcript dict key (provider-agnostic side channel)

key-files:
  created:
    - src/podcast_pipeline/models/branding.py
    - src/podcast_pipeline/utils/branding.py
  modified:
    - src/podcast_pipeline/models/__init__.py
    - src/podcast_pipeline/config/settings.py
    - src/podcast_pipeline/providers/base.py
    - src/podcast_pipeline/stages/analyze.py
    - tests/test_models.py
    - tests/test_providers.py
    - tests/test_pipeline.py

key-decisions:
  - "BrandingProfile.resolved_for_platform() returns new instance with empty platform_overrides — resolved profiles are flat and cannot be re-resolved"
  - "brand_voice sanitized twice: once at BrandingProfile construction (field_validator) and once in BaseProvider._sanitize_prompt_brand_voice() at prompt boundary"
  - "brand_voice injected via transcript['brand_voice'] dict key rather than direct provider method parameter — keeps provider API unchanged and works across all provider types"
  - "load_active_profile() returns None when profile is unconfigured or file missing — all stages treat None as no-branding without branching"
  - "BRAND VOICE block positioned after role statement, before TRANSCRIPT — frames copy direction without competing with JSON schema at prompt end"

patterns-established:
  - "Defense in depth for user-supplied prompt text: model validator + prompt-boundary sanitizer"
  - "None-safe branding resolution: load_active_profile returns None, callers branch on None"
  - "Platform override merge: explicit None-check on each override field, not model_fields_set"

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 9 Plan 05: BrandingProfile Model and Brand Voice Prompt Injection Summary

**Typed BrandingProfile model with YAML serialization, per-platform override merge, and double-sanitized brand_voice injection into BaseProvider._build_prompt()**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T03:52:11Z
- **Completed:** 2026-02-24T03:55:01Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- BrandingProfile Pydantic model (311 lines) with brand_voice, logo, caption, thumbnail border, and per-platform overrides; profiles serialize to `branding/<name>.yaml`
- Platform override merge: deterministic base-first order, only set override fields applied, resolved profiles have empty platform_overrides for clarity
- utils/branding.py (268 lines): load_profile, save_profile, resolve_profile, list_profiles, load_active_profile (None-safe pipeline entry point)
- BrandingConfig added to Config settings; AnalyzeStage resolves active profile at construction, injects brand_voice into provider transcript dict
- BaseProvider._build_prompt() extended with optional brand_voice: BRAND VOICE block injected between role statement and TRANSCRIPT, before JSON schema
- Double sanitization gate: control chars stripped and text truncated to 2000 chars at both model construction and prompt boundary
- 11 new regression tests for brand_voice injection (presence, absence, control char stripping, truncation, positioning, explicit-over-transcript priority)

## Task Commits

Each task was committed atomically:

1. **Task 1: BrandingProfile model and YAML serialization contract** - `9c6ac1d` (feat)
2. **Task 2: Wire branding profile resolution into runtime configuration flow** - `34b30d0` (feat)
3. **Task 3: Inject sanitized brand voice into provider prompt path** - `de5d1a0` (feat)

## Files Created/Modified
- `src/podcast_pipeline/models/branding.py` - BrandingProfile, CaptionStyle, ThumbnailBorder, PlatformBrandingOverride with full validation and merge
- `src/podcast_pipeline/utils/branding.py` - load/save/resolve/list/load_active_profile helpers
- `src/podcast_pipeline/models/__init__.py` - Exports BrandingProfile, CaptionStyle, PlatformBrandingOverride, ThumbnailBorder
- `src/podcast_pipeline/config/settings.py` - BrandingConfig model + Config.branding field
- `src/podcast_pipeline/providers/base.py` - _build_prompt brand_voice param, _build_brand_voice_block, _sanitize_prompt_brand_voice
- `src/podcast_pipeline/stages/analyze.py` - load_active_profile at init, _resolve_brand_voice_for_analysis(), resolve_branding_for_platform()
- `tests/test_models.py` - TestBrandingProfile, TestBrandVoiceSanitization, TestPlatformOverrides, TestBrandingProfileSerializationContract (25 tests)
- `tests/test_providers.py` - 11 brand_voice injection regression tests added

## Decisions Made
- brand_voice is sanitized twice: at model construction (defense against stored malicious content) and at prompt boundary (defense against direct callers bypassing the model)
- brand_voice injected via transcript dict key `"brand_voice"` rather than a new provider method parameter — keeps all provider analyze() signatures unchanged
- BRAND VOICE block positioned after role statement and before TRANSCRIPT so it frames copy direction without competing with the strict JSON schema at prompt end
- Resolved profiles have empty platform_overrides — this signals "already resolved, do not re-resolve"
- load_active_profile returns None on any load failure (missing file, validation error) so all callers can treat None as no-branding gracefully

## Deviations from Plan

None - plan executed exactly as written. All three tasks were implemented and tests pass. The code was already partially in place from prior partial execution; Task 3 brand_voice tests were the primary gap filled.

## Issues Encountered

Pre-commit hook ruff format modified base.py (collapsed multi-line return into single f-string). Resolved by re-staging the reformatted file before final commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- BrandingProfile is the complete typed source of truth for 09-06 (caption burn-in), 09-07 (thumbnail overlay), and 09-08 (render wiring)
- brand_voice injection in providers is live; analysis results are already brand-voice-influenced when active_profile is configured
- All downstream consumers call resolve_branding_for_platform() on AnalyzeStage to get platform-specific resolved profiles

## Self-Check

**Files exist:**
- src/podcast_pipeline/models/branding.py: FOUND
- src/podcast_pipeline/utils/branding.py: FOUND
- src/podcast_pipeline/config/settings.py (BrandingConfig): FOUND

**Commits exist:**
- 9c6ac1d: FOUND (feat(09-05): BrandingProfile model with YAML serialization)
- 34b30d0: FOUND (feat(09-05): wire BrandingConfig into Config and AnalyzeStage)
- de5d1a0: FOUND (feat(09-05): inject sanitized brand_voice into provider prompt path)

**Test verification:**
- Task 1: 14 branding_profile/platform_overrides tests passing
- Task 2: 6 branding-resolve tests passing
- Task 3: 15 brand_voice/prompt tests passing (11 new + 4 existing)

## Self-Check: PASSED

---
*Phase: 09-automated-branding-captions-and-multi-track-sync*
*Completed: 2026-02-24*
