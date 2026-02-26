# Architecture Patterns

## Pipeline Orchestration

The core is a staged pipeline pattern:
```
IngestStage → TranscribeStage → AnalyzeStage → ReviewStage → RenderStage
```
- Each stage extends `stages/base.py` BaseStage
- Stage inputs/outputs written to `jobs/<job_id>/<stage>/` directories as JSON/media files
- `pipeline.py` `Pipeline` class orchestrates stage execution sequentially
- Render stage applies the `edit_plan.json` produced during review

## Job State Model

```python
# models/job.py
class StageStatus(StrEnum):  # pending | running | complete | failed
class JobStage(BaseModel):   # stage name + status + metadata
class Job(BaseModel):        # job_id + stages + input/output paths
```

Jobs are stored as JSON files in `jobs/<job_id>/job.json`. File locking via `utils/locks.py`
prevents concurrent writes. Recovery logic in `service/recovery.py`.

## AI Provider Protocol

```python
# providers/base.py
class AnalysisProvider(Protocol):
    async def analyze(self, video_path: Path, transcript: dict) -> AnalysisResult: ...
```

Providers: Gemini (primary) → Kimi (fallback) → OpenAI (fallback).
Register new providers in the provider factory.

## Service Architecture (FastAPI)

```
FastAPI app (service/app.py)
├── ServiceAuthPolicy — token-based auth (env vars)
├── lifespan — startup/shutdown lifecycle
└── Routes:
    ├── /jobs/*   (service/routes/jobs.py)
    └── /system/* (service/routes/system.py)

Supervisor (service/supervisor.py) — manages pipeline job execution
```

## Branding System (Phase 9)

```
models/branding.py        — BrandingProfile (Pydantic) with PlatformOverride
utils/branding.py         — load_profile / save_profile / resolve_for_platform
branding/<name>.yaml      — persisted profile files
```

`BrandingProfile` has per-platform overrides (tiktok, youtube, linkedin, instagram).
`resolve_for_platform()` merges base + platform-specific settings.

## Captions Engine (Phase 9)

```
utils/captions.py
  WordEntry              — single word with start/end timestamps
  CaptionStyleConfig     — font, color, size, shadow settings (from BrandingProfile)
  generate_ass()         — builds ASS subtitle file with word-level \\1c colour tags
  generate_ass_from_json() — convenience wrapper for JSON word alignment files
```

Three aspect ratio templates: 16:9 (YouTube), 9:16 (TikTok/Reels), 1:1 (LinkedIn).
ASS files are burned in at render via FFmpeg `ass=` libass filter.

## Audio Sync Estimator (Phase 9)

```
utils/sync.py
  SyncEstimator.estimate(reference_path, external_path) → SyncResult
  SyncResult.offset_ms  — positive = external starts AFTER reference
  SyncResult.confidence — 0-1 score; < LOW_CONFIDENCE_THRESHOLD (0.30) = unreliable
  SyncResult.warnings   — list of human-readable diagnostic strings
```

Four-step algorithm: downsample to 8 kHz → clap detection → cross-correlation → confidence scoring.

## MCP Server Pattern (Phase 9, dev-only)

```
mcp/ffmpeg_server.py — FastMCP server with 14 tools:
  mcp_probe_media, mcp_extract_frame, mcp_detect_hardware_encoders,
  mcp_transcode, mcp_normalize_loudness, mcp_burn_captions,
  mcp_overlay_image, mcp_apply_filtergraph, mcp_denoise,
  mcp_trim_segment, mcp_concat_segments, mcp_mix_audio,
  mcp_sync_tracks, mcp_package_hls
```

Each MCP tool delegates to `utils/ffmpeg_toolkit.py` operation classes.
Toolkit uses request/result Pydantic models (e.g., `TranscodeRequest`, `TranscodeResult`).

## Configuration Flow

```
.env → python-dotenv → settings.py Pydantic models
config.yaml → PyYAML → runtime config
```

## Data Flow Summary

```
raw_video.mp4
  ↓ IngestStage       → job.json, ingest/metadata.json
  ↓ TranscribeStage   → transcribe/word_alignment.json, transcript.json
  ↓ AnalyzeStage      → analyze/analysis.json, research.json, viral_signals.json
  ↓ ReviewStage       → review/edit_plan.json (human-approved cuts)
  ↓ RenderStage       → render/output_16x9.mp4, output_9x16.mp4, output_1x1.mp4
                         (with burned captions, branding overlays, normalized audio)
```
