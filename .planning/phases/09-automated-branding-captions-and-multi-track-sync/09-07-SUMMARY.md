---
status: complete
started: 2026-02-24
completed: 2026-02-24
---

# Summary: 09-07 — Multi-Track Audio Sync

## What was built

A bounded cross-correlation sync utility (`src/podcast_pipeline/utils/sync.py`) with confidence scoring, integrated into ingest and render stages with manual override support.

## Key files

### Created
- `src/podcast_pipeline/utils/sync.py` — 401 lines: 8kHz mono cross-correlation, 60s search window, confidence scoring
- Tests in `tests/test_pipeline.py` — 11 sync regression tests

### Modified
- `src/podcast_pipeline/stages/ingest.py` — auto-sync on 2+ audio tracks, stream WAV extraction
- `src/podcast_pipeline/stages/render.py` — _resolve_sync_offset (manual > auto priority), _apply_sync_offset (-itsoffset re-mux)
- `src/podcast_pipeline/stages/review.py` — manual_sync_offset_ms in ReviewDecisions

## Design decisions

| Decision | Rationale |
|----------|-----------|
| Bounded 60s search window at 8kHz mono | Prevents memory explosion on long recordings |
| scipy.signal.correlate for offset detection | Sub-sample precision without external dependencies |
| Manual override takes priority over auto | Low-confidence detections can be corrected by operator |
| Sync artifact persisted in StageResult.data | Downstream stages consume without re-computing |

## Self-Check: PASSED

- [x] Cross-correlation with confidence scoring implemented
- [x] Sync offset persisted and consumed by downstream stages
- [x] Manual override via ReviewDecisions
- [x] 11 regression tests passing
- [x] ruff + mypy clean
