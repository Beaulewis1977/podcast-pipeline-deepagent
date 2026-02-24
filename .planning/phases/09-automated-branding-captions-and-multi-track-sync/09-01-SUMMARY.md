---
status: complete
started: 2026-02-23
completed: 2026-02-24
---

# Summary: 09-01 — FFmpeg Media Toolkit

## What was built

A deterministic, typed FFmpeg media toolkit (`src/podcast_pipeline/utils/ffmpeg_toolkit.py`) providing 14 operations across 5 groups — the foundation for all Phase 9 features.

## Key files

### Created
- `src/podcast_pipeline/utils/ffmpeg_toolkit.py` — 1600+ lines, 14 typed operations with Pydantic I/O models
- `tests/test_ffmpeg_toolkit.py` — 80 tests covering all operations, model validation, error wrapping

### Modified
- None (existing `utils/ffmpeg.py` callers untouched)

## Operations implemented

| Group | Tools | Purpose |
|-------|-------|---------|
| Probe & Inspect | `probe_media`, `extract_frame`, `detect_hardware_encoders` | Metadata, screenshots, GPU detection |
| Encode & Transcode | `transcode`, `normalize_loudness` | HEVC/H264/AV1 encode, EBU R128 loudnorm |
| Filter & Overlay | `burn_captions`, `overlay_image`, `apply_filtergraph`, `denoise` | ASS burn-in, watermarks, raw filters, noise cleanup |
| Edit & Assemble | `trim_segment`, `concat_segments`, `mix_audio`, `sync_tracks` | Cuts, joins, audio mix, cross-correlation sync |
| Package & Deliver | `package_hls` | VOD HLS with variant ladder |

## Design decisions

| Decision | Rationale |
|----------|-----------|
| `cmd_args` attribute (not `args`) on FFmpegToolkitError | Avoids shadowing `Exception.args` tuple — fixes mypy strict mode |
| All tools take Pydantic request models, return Pydantic result models | Type safety + auto-validation + serialization for MCP server (plan 09-02) |
| Routes through existing `run_ffmpeg`/`run_ffprobe` | No breaking changes to existing callers; shared subprocess management |
| Hardware encoder detection with global cache | Single probe at startup, reused across all encode operations |
| `_concat_demuxer` / `_concat_xfade` helper extraction | Keeps `concat_segments` within PLR0912 branch limit |

## Self-Check: PASSED

- [x] All 14 toolkit tools implemented
- [x] Pydantic I/O models for every operation
- [x] Structured FFmpegToolkitError with operation context
- [x] 80 tests passing (0.10s)
- [x] ruff + mypy clean
- [x] Existing `test_utils.py` still passing (no regressions)
