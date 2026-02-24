---
status: complete
started: 2026-02-24
completed: 2026-02-24
---

# Summary: 09-09 — AI Thumbnail Studio

## What was built

A dual-backend thumbnail service (`src/podcast_pipeline/utils/thumbnails.py`) with Imagen 4 GA primary path, FLUX.1 Schnell fallback, prompt-hash caching, VRAM preflight, and branding overlay support.

## Key files

### Created
- `src/podcast_pipeline/utils/thumbnails.py` — 894 lines: dual backend, cache-aware generation, VRAM preflight, branding overlay
- `tests/test_thumbnails.py` — 36 tests + 5 integration regressions (cache, failover, overlay continuity)

### Modified
- `src/podcast_pipeline/config/settings.py` — ThumbnailGenerationConfig with backend routing
- `src/podcast_pipeline/stages/analyze.py` — _generate_ai_thumbnails with cache-aware generation
- `pyproject.toml` — [thumbnails] optional dependency group (google-cloud-aiplatform, diffusers, optimum-quanto)
- `tests/test_pipeline.py` — 4 AI thumbnail generation tests

## Design decisions

| Decision | Rationale |
|----------|-----------|
| Imagen 4 GA primary, FLUX.1 Schnell fallback | Cloud-first reliability with local GPU fallback |
| Prompt-hash cache keys | Avoids duplicate generation for identical prompts |
| VRAM preflight before FLUX model load | Prevents OOM surprises on constrained GPUs |
| optimum-quanto>=0.2.5 (corrected from plan's >=0.3.0) | 0.3.0 not yet released; 0.2.5 is verified stable floor |
| Optional dependency group [thumbnails] | Keeps base install lightweight |

## Self-Check: PASSED

- [x] Imagen 4 and FLUX fallback pathways both execute with routing diagnostics
- [x] Prompt-hash cache avoids duplicate generation
- [x] Thumbnail artifacts compatible with UI/render consumers
- [x] VRAM preflight prevents OOM
- [x] 41 tests passing
- [x] ruff + mypy clean
