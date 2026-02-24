---
status: complete
started: 2026-02-24
completed: 2026-02-24
---

# Summary: 09-08 — Production Sound Kits

## What was built

An audio mix utility (`src/podcast_pipeline/utils/audio_mix.py`) for stinger placement with sidechain ducking, integrated into the render stage with branding profile support.

## Key files

### Created
- `src/podcast_pipeline/utils/audio_mix.py` — 634 lines: stinger placement (intro/transition/outro), sidechaincompress auto-ducking, PCM normalization
- Tests in `tests/test_render.py` — 20 sound kit regression tests
- Tests in `tests/test_models.py` — branding model sound_kit extension tests

### Modified
- `src/podcast_pipeline/config/settings.py` — SoundKitConfig with ducking parameters
- `src/podcast_pipeline/models/branding.py` — sound_kit field on BrandingProfile
- `src/podcast_pipeline/stages/render.py` — _mix_stingers wiring before loudness normalization

## Design decisions

| Decision | Rationale |
|----------|-----------|
| PCM pre-normalization before ducking | Prevents VBR/container timing drift in sidechain compressor |
| Missing assets degrade gracefully | Base exports never blocked by absent optional sound files |
| Stinger mix runs before loudness normalization | Ensures final output meets EBU R128 target after all mixing |
| Parameters flow through SoundKitConfig + BrandingProfile | No hard-coded configuration in the utility |

## Self-Check: PASSED

- [x] Brand-linked sound kits configurable and applied during render
- [x] Voice intelligible under stingers via deterministic sidechain ducking
- [x] Missing assets degrade gracefully
- [x] 20+ tests passing
- [x] ruff + mypy clean
