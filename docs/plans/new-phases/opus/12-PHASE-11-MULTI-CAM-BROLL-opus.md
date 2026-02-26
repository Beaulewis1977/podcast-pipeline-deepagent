# Phase 11: Multi-Cam Core & B-Roll Engine — Detailed EPC

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Research & Planning Only
**Supersedes:** `12-PHASE-11-MULTI-CAM-BROLL.md` (skeleton)
**Depends on:** Phase 10 complete (Tauri desktop app + FastAPI service)
**Reference:** `11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md` (EPC-1 + EPC-2)

---

## 1. Goal

Implement a production-quality multi-camera processing engine and B-roll insertion system. This phase enables:

1. **N-camera ingestion** — drag-and-drop upload of 2–4 camera angles + separate audio tracks
2. **Universal auto-synchronization** — extend existing `sync.py` from 2-track to N-track alignment
3. **Camera switch planning** — JSON-driven camera switching via `camera_plan.json`
4. **FFmpeg multi-cam rendering** — `filter_complex` with `trim`/`setpts`/`concat` for dynamic switching
5. **B-roll overlay** — timed insertion of uploaded B-roll clips with `overlay` + `enable` expressions
6. **RIFE transitions** — smooth frame interpolation at all switch points and B-roll boundaries

---

## 2. Current State Analysis

### 2.1 What Already Exists (Leverage)

| Component | File | Current Capability | Extension Needed |
|-----------|------|-------------------|-----------------|
| Audio sync | `utils/sync.py` | 2-track cross-correlation, 8kHz mono, clap detection, SyncResult model | Generalize to N-track; accept `list[Path]` → `list[SyncResult]` |
| FFmpeg toolkit | `utils/ffmpeg_toolkit.py` | 14 typed operations (probe, transcode, trim, concat, overlay, etc.) | Add `multi_cam_switch` and `overlay_video_timed` operations |
| RIFE bridge | `utils/rife_bridge.py` | Frame pair interpolation via `inference_img.py` subprocess | Apply at camera switch points (already works for 2-frame transitions) |
| Render stage | `stages/render.py` | Single-input `filter_complex` with edit-plan cuts, transitions, branding | Add multi-input filter_complex path when `camera_plan.json` exists |
| Ingest stage | `stages/ingest.py` | Single video + optional audio track ingestion | Extend to accept named multi-cam inputs via job manifest |
| Job model | `models/job.py` | Job config dict with stage state tracking | Add `asset_registry` to job config for multi-cam metadata |
| Config | `config.yaml` | Platform specs, smoothing, enhancements | Add `multi_cam` section |
| Tauri Ingestion | `desktop/src/views/IngestionView.tsx` | Drag-drop single file + platform pipeline status | Add multi-file drop zones with asset type assignment |

### 2.2 What Doesn't Exist Yet (New)

| Component | Purpose |
|-----------|---------|
| `utils/multicam.py` | Asset registry model, N-track sync orchestrator, camera switch plan builder |
| `utils/broll.py` | B-roll inventory, timed overlay insertion, style metadata |
| `models/camera_plan.py` | Typed `CameraPlan` / `CamSegment` / `BrollInsert` Pydantic models |
| MCP tool: `multi_cam_switch` | FFmpeg filter_complex for N-source camera switching |
| MCP tool: `overlay_video_timed` | FFmpeg overlay with `setpts` delay + `enable` expression |

---

## 3. Architecture

### 3.1 Asset Registry

Every multi-cam job maintains an `AssetRegistry` in the job config:

```python
# models/camera_plan.py

class AssetEntry(BaseModel):
    """Single media asset in a multi-cam project."""
    asset_id: str                    # unique ID (e.g., "cam_1", "broll_city")
    asset_type: Literal["primary", "angle", "broll", "audio_only"]
    file_path: str                   # relative to job_dir/intermediate/
    original_filename: str           # user's original filename
    fps: float                       # detected frame rate
    width: int                       # frame width
    height: int                      # frame height
    duration_s: float                # duration in seconds
    has_audio: bool                  # whether the asset contains an audio stream
    sync_offset_ms: float = 0.0     # offset relative to primary (from auto-sync)
    sync_confidence: float = 0.0    # correlation confidence [0,1]

class AssetRegistry(BaseModel):
    """Registry of all media assets in a multi-cam job."""
    primary: AssetEntry              # the reference camera (sync anchor)
    angles: list[AssetEntry] = []    # additional camera angles
    broll: list[AssetEntry] = []     # B-roll clips
    audio_tracks: list[AssetEntry] = []  # separate audio sources
    project_fps: float = 30.0       # unified project frame rate
    project_resolution: tuple[int, int] = (1920, 1080)
```

### 3.2 N-Track Sync Extension

The existing `SyncEstimator.estimate()` takes `(reference_path, external_path)` → `SyncResult`. For multi-cam, we add:

```python
# utils/multicam.py

class MultiCamSyncResult(BaseModel):
    """Results of N-track synchronization."""
    reference_id: str
    track_offsets: dict[str, SyncResult]  # asset_id → SyncResult
    warnings: list[str] = []
    all_confident: bool = True             # False if any track has low_confidence

def sync_all_tracks(
    primary: Path,
    secondaries: dict[str, Path],  # asset_id → file_path
    search_window_s: float = 60.0,
) -> MultiCamSyncResult:
    """Synchronize N tracks against a primary reference.

    Runs SyncEstimator.estimate() for each secondary track against the
    primary. All offsets are relative to the primary's timeline zero.
    """
    estimator = SyncEstimator(search_window_s=search_window_s)
    offsets: dict[str, SyncResult] = {}
    warnings: list[str] = []
    all_confident = True

    for asset_id, path in secondaries.items():
        result = estimator.estimate(primary, path)
        offsets[asset_id] = result
        if result.low_confidence:
            all_confident = False
            warnings.append(
                f"Track '{asset_id}' has low sync confidence "
                f"({result.confidence:.3f}). Manual offset may be needed."
            )

    return MultiCamSyncResult(
        reference_id="primary",
        track_offsets=offsets,
        warnings=warnings,
        all_confident=all_confident,
    )
```

**Key design:** This does NOT modify `sync.py`. It wraps the existing `SyncEstimator` in a loop. Each track sync is independent — no multi-signal correlation complexity.

### 3.3 Camera Switch Plan

```python
# models/camera_plan.py

class CamSegment(BaseModel):
    """A segment where a specific camera angle is active."""
    start_s: float           # start time in project timeline
    end_s: float             # end time in project timeline
    cam_id: str              # asset_id from AssetRegistry (e.g., "primary", "cam_2")
    transition: Literal["cut", "dissolve", "rife"] = "cut"
    transition_duration_ms: int = 0  # only for dissolve/rife

class BrollInsert(BaseModel):
    """A B-roll clip overlaid at a specific time range."""
    start_s: float           # when B-roll starts in project timeline
    end_s: float             # when B-roll ends
    broll_id: str            # asset_id from AssetRegistry
    audio_mode: Literal["main_only", "mixed", "replace"] = "main_only"
    secondary_audio_volume: float = 0.3  # only used when audio_mode="mixed"

class CameraPlan(BaseModel):
    """Complete camera switching and B-roll insertion plan."""
    segments: list[CamSegment]       # ordered, non-overlapping cam segments
    broll_inserts: list[BrollInsert] = []  # can overlap with segments (overlaid on top)
    audio_source: Literal["primary", "mixed", "external"] = "primary"
    external_audio_id: str | None = None  # asset_id for external audio track

    def validate_continuity(self) -> list[str]:
        """Check that segments cover the timeline without gaps."""
        issues: list[str] = []
        for i in range(len(self.segments) - 1):
            curr = self.segments[i]
            next_seg = self.segments[i + 1]
            gap = next_seg.start_s - curr.end_s
            if abs(gap) > 0.001:
                issues.append(
                    f"Gap/overlap between segments {i} and {i+1}: "
                    f"{curr.end_s:.3f}s → {next_seg.start_s:.3f}s (delta={gap:.3f}s)"
                )
        return issues
```

### 3.4 FFmpeg Multi-Cam Filter_Complex

The core rendering uses `trim` + `setpts` + `concat` for camera switching:

```python
# utils/multicam.py

def build_multicam_filtergraph(
    plan: CameraPlan,
    registry: AssetRegistry,
) -> tuple[str, list[str], str]:
    """Build FFmpeg filter_complex string for multi-cam switching.

    Returns:
        (filter_complex_string, input_args, output_video_label)

    FFmpeg pattern for 3-segment switch (cam_0, cam_1, cam_0):
        [0:v]trim=0:5,setpts=PTS-STARTPTS[seg0];
        [1:v]trim=5:12,setpts=PTS-STARTPTS[seg1];
        [0:v]trim=12:20,setpts=PTS-STARTPTS[seg2];
        [seg0][seg1][seg2]concat=n=3:v=1:a=0[vout]

    Each camera input uses itsoffset for sync alignment:
        -itsoffset {offset_s} -i cam_2.mp4
    """
    # Build input args with sync offsets
    input_args: list[str] = []
    cam_id_to_input_index: dict[str, int] = {}

    # Primary is always input 0
    input_args.extend(["-i", str(registry.primary.file_path)])
    cam_id_to_input_index[registry.primary.asset_id] = 0

    # Add angle inputs with itsoffset for sync
    for idx, angle in enumerate(registry.angles, start=1):
        offset_s = angle.sync_offset_ms / 1000.0
        if abs(offset_s) >= 0.001:
            input_args.extend(["-itsoffset", f"{offset_s:.3f}"])
        input_args.extend(["-i", str(angle.file_path)])
        cam_id_to_input_index[angle.asset_id] = idx

    # Build trim/setpts/concat chain
    filter_parts: list[str] = []
    seg_labels: list[str] = []

    for i, seg in enumerate(plan.segments):
        input_idx = cam_id_to_input_index[seg.cam_id]
        label = f"seg{i}"
        filter_parts.append(
            f"[{input_idx}:v]trim={seg.start_s:.3f}:{seg.end_s:.3f},"
            f"setpts=PTS-STARTPTS[{label}]"
        )
        seg_labels.append(f"[{label}]")

    n_segments = len(plan.segments)
    concat_input = "".join(seg_labels)
    filter_parts.append(
        f"{concat_input}concat=n={n_segments}:v=1:a=0[vout]"
    )

    filter_complex = ";\n".join(filter_parts)
    return filter_complex, input_args, "[vout]"
```

**Audio handling:** Primary camera audio is used by default (`-map 0:a`). When `audio_source="external"`, the external audio track is mapped instead. Mixed mode uses `amix` — same pattern as existing `audio_mix.py`.

### 3.5 B-Roll Overlay Integration

B-roll overlays are applied AFTER camera switching, as a second pass or extended filter_complex:

```python
# utils/broll.py

def build_broll_overlay_filter(
    broll_insert: BrollInsert,
    broll_input_index: int,
    base_video_label: str = "[vout]",
    output_label: str = "[vfinal]",
) -> str:
    """Build overlay filter for a single B-roll clip.

    Pattern (from 11-research.md, verified):
        [N:v]setpts=PTS-STARTPTS+{start_s}/TB[broll_delayed];
        [base][broll_delayed]overlay=enable='between(t,{start_s},{end_s})':x=0:y=0[vfinal]
    """
    start = broll_insert.start_s
    end = broll_insert.end_s
    broll_label = f"broll_{broll_input_index}"

    return (
        f"[{broll_input_index}:v]setpts=PTS-STARTPTS+{start:.3f}/TB[{broll_label}];\n"
        f"{base_video_label}[{broll_label}]overlay="
        f"enable='between(t,{start:.3f},{end:.3f})':x=0:y=0{output_label}"
    )
```

### 3.6 RIFE at Switch Points

Existing `RifeBridge.generate()` works for any two frames. At each camera switch point:

1. Extract the last frame of outgoing segment: `ffmpeg -ss {end_s - 0.033} -i cam_out.mp4 -frames:v 1 frame_a.png`
2. Extract the first frame of incoming segment: `ffmpeg -ss {start_s} -i cam_in.mp4 -frames:v 1 frame_b.png`
3. Call `RifeBridge.generate(frame_a, frame_b, output_dir, num_frames=4)`
4. Insert generated frames into the concat filter as crossfade images

**Gate:** RIFE only triggers when `transition == "rife"` in the `CamSegment`. Default is `"cut"` for zero-overhead rendering.

---

## 4. Config Extensions

```yaml
# config.yaml additions

multi_cam:
  enabled: false                    # master gate for multi-cam features
  max_cameras: 4                    # limit concurrent camera inputs
  auto_sync: true                   # run N-track sync on ingest
  sync_window_s: 60                 # seconds of audio head to analyze
  default_transition: cut           # cut | dissolve | rife
  dissolve_duration_ms: 300         # default dissolve duration
  project_fps: 30                   # unified output frame rate
  project_resolution: [1920, 1080]  # unified output resolution

broll:
  enabled: false                    # master gate for B-roll features
  default_audio_mode: main_only     # main_only | mixed | replace
  secondary_volume: 0.3            # volume for mixed audio mode
  veo_enabled: false               # gate for Veo 3.1 AI generation (Phase 12)
```

---

## 5. Data Flow

```
User uploads N files (drag-drop in Tauri or Streamlit)
        │
        ▼
┌──────────────────────────────┐
│  INGEST (extended)           │
│  • Probe each file (ffprobe) │
│  • Classify: primary/angle/  │
│    broll/audio_only          │
│  • Build AssetRegistry       │
│  • Persist to job config     │
└──────────┬───────────────────┘
           ▼
┌──────────────────────────────┐
│  AUTO-SYNC (new step)        │
│  • sync_all_tracks()         │
│  • Write offsets into        │
│    AssetRegistry             │
│  • Flag low-confidence       │
│    tracks for manual adjust  │
└──────────┬───────────────────┘
           ▼
┌──────────────────────────────┐
│  TRANSCRIBE (unchanged)      │
│  • faster-whisper on primary │
│  • Word-level alignment      │
└──────────┬───────────────────┘
           ▼
┌──────────────────────────────┐
│  ANALYZE (extended)          │
│  • Gemini Vision: suggest    │
│    camera switch points      │
│  • Suggest B-roll insertions │
│  • Generate camera_plan.json │
└──────────┬───────────────────┘
           ▼
┌──────────────────────────────┐
│  REVIEW (extended)           │
│  • Multi-cam timeline view   │
│  • Manual switch point edits │
│  • B-roll placement preview  │
│  • Visual cam selection      │
└──────────┬───────────────────┘
           ▼
┌──────────────────────────────┐
│  RENDER (extended)           │
│  • Load camera_plan.json     │
│  • Build multi-cam filter_   │
│    complex                   │
│  • Apply B-roll overlays     │
│  • RIFE at transition points │
│  • Per-platform exports      │
└──────────────────────────────┘
```

---

## 6. Artifact Schema: `camera_plan.json`

```json
{
  "version": "1.0",
  "generated_by": "analyze",
  "asset_registry": {
    "primary": {
      "asset_id": "cam_main",
      "asset_type": "primary",
      "file_path": "intermediate/cam_main.mp4",
      "fps": 30.0,
      "width": 1920,
      "height": 1080,
      "duration_s": 3600.0,
      "has_audio": true,
      "sync_offset_ms": 0.0,
      "sync_confidence": 1.0
    },
    "angles": [
      {
        "asset_id": "cam_guest",
        "asset_type": "angle",
        "file_path": "intermediate/cam_guest.mp4",
        "fps": 30.0,
        "width": 1920,
        "height": 1080,
        "duration_s": 3605.2,
        "has_audio": true,
        "sync_offset_ms": -127.5,
        "sync_confidence": 0.87
      }
    ],
    "broll": [
      {
        "asset_id": "broll_cityscape",
        "asset_type": "broll",
        "file_path": "intermediate/broll_cityscape.mp4",
        "fps": 24.0,
        "width": 3840,
        "height": 2160,
        "duration_s": 12.5,
        "has_audio": false,
        "sync_offset_ms": 0.0,
        "sync_confidence": 0.0
      }
    ]
  },
  "segments": [
    {"start_s": 0.0, "end_s": 45.2, "cam_id": "cam_main", "transition": "cut"},
    {"start_s": 45.2, "end_s": 92.8, "cam_id": "cam_guest", "transition": "dissolve", "transition_duration_ms": 300},
    {"start_s": 92.8, "end_s": 180.0, "cam_id": "cam_main", "transition": "rife", "transition_duration_ms": 0}
  ],
  "broll_inserts": [
    {
      "start_s": 120.0,
      "end_s": 127.5,
      "broll_id": "broll_cityscape",
      "audio_mode": "main_only"
    }
  ],
  "audio_source": "primary"
}
```

---

## 7. UI Integration

### 7.1 Tauri — IngestionView Extension

The existing `IngestionView.tsx` has drag-drop for a single file. Extend to:

- **Multi-file drop zone** with asset type assignment (Primary / Camera 2 / Camera 3 / B-Roll / Audio Only)
- **Asset list table** showing filename, type, resolution, FPS, sync status
- **Sync status indicator** (green = confident, yellow = low confidence, red = failed)
- **Manual offset slider** per track (reuse existing AudioSyncView pattern)

### 7.2 Tauri — New MultiCamView (Phase 13)

Full timeline UI is deferred to Phase 13 (EPC-4). Phase 11 focuses on the engine layer only. The review/edit UI in Phase 11 uses existing Streamlit patterns.

### 7.3 Streamlit Extension

- **Upload multiple files** using `st.file_uploader(accept_multiple_files=True)` with asset type selectbox per file
- **Sync results table** showing offset_ms, confidence per track
- **Camera plan editor** — basic table UI for adjusting switch points (similar to existing filler review UI)
- **B-roll timeline** — visual bar showing B-roll placement on main timeline

---

## 8. Estimated Plan Breakdown

| Plan | Scope | Dependencies |
|------|-------|-------------|
| **11-01** | `models/camera_plan.py` — typed models (AssetEntry, AssetRegistry, CamSegment, BrollInsert, CameraPlan) with validation | None |
| **11-02** | `utils/multicam.py` — `sync_all_tracks()`, N-track sync orchestrator wrapping existing SyncEstimator | 11-01 |
| **11-03** | Ingest stage extension — multi-file ingestion, asset classification, AssetRegistry persistence | 11-01, 11-02 |
| **11-04** | `utils/multicam.py` — `build_multicam_filtergraph()`, FFmpeg filter_complex construction for N-cam switching | 11-01 |
| **11-05** | `utils/broll.py` — B-roll inventory, `build_broll_overlay_filter()`, timed overlay construction | 11-01 |
| **11-06** | Render stage extension — multi-cam + B-roll filter_complex path, RIFE at switch points | 11-04, 11-05 |
| **11-07** | MCP tool registration — `multi_cam_switch` + `overlay_video_timed` in ffmpeg_server.py | 11-04, 11-05 |
| **11-08** | Config extension — `multi_cam` + `broll` yaml sections, validation, defaults | 11-01 |
| **11-09** | Streamlit UI — multi-file upload, sync results, basic camera plan editor | 11-03, 11-06 |
| **11-10** | Integration tests — 2-cam sync + render, B-roll overlay, RIFE transitions, regression suite | All above |

---

## 9. Success Criteria

| # | Criterion | Measurement |
|---|-----------|-------------|
| 1 | 2-camera podcast syncs within ≤50ms accuracy | Automated test with known-offset test files |
| 2 | 4-camera ingestion completes without error | Ingest 4 video files → valid AssetRegistry |
| 3 | Camera switch renders produce continuous output | `camera_plan.json` → FFmpeg → valid output.mp4 with no dropped frames |
| 4 | B-roll overlays at correct timestamps | Overlay appears at specified `start_s`, disappears at `end_s` |
| 5 | B-roll preserves primary audio | Output audio matches primary; no B-roll audio bleed in `main_only` mode |
| 6 | RIFE creates smooth transitions at switch points | 4 interpolated frames between outgoing/incoming cameras |
| 7 | All existing tests pass (1041+) | Zero regressions |
| 8 | Low-confidence sync flagged to operator | SyncResult.low_confidence = True → UI warning displayed |

---

## 10. Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Multi-signal synchronization | Custom multi-channel correlation matrix | Loop existing `SyncEstimator` per track (simpler, proven) |
| Video frame rate normalization | Custom frame interpolation for FPS matching | FFmpeg `fps` filter (`-vf fps=30`) — handles all FPS conversions |
| Complex filter_complex validation | Custom parser for FFmpeg filter syntax | Build the string programmatically + let FFmpeg validate on execution |
| B-roll timing precision | Frame-counting based placement | FFmpeg `setpts=PTS-STARTPTS+{start_s}/TB` — timestamp-based, codec-independent |
| Segment gap detection | Manual timestamp arithmetic | `CameraPlan.validate_continuity()` method with tolerance |

---

## 11. Common Pitfalls

### Pitfall 16: itsoffset Sign Convention

**What goes wrong:** Camera sync offsets applied with wrong sign cause tracks to drift further apart.
**Why:** `SyncResult.offset_ms > 0` means external starts AFTER reference. FFmpeg `-itsoffset` delays the input — so the offset value should be applied directly (not negated).
**How to avoid:** `ffmpeg -itsoffset {offset_ms / 1000.0} -i external.mp4` — positive delays external, negative advances it.

### Pitfall 17: setpts Reset After trim

**What goes wrong:** After `trim`, timestamps don't start at 0, causing `concat` filter to produce black frames or duplicate the first frame.
**Why:** `trim` preserves original PTS values. Without `setpts=PTS-STARTPTS`, the concat filter sees non-zero starting timestamps and pads with silence/black.
**How to avoid:** Always chain `trim=X:Y,setpts=PTS-STARTPTS` — never `trim` without `setpts`.

### Pitfall 18: B-Roll Resolution Mismatch

**What goes wrong:** B-roll clip has different resolution than primary video; overlay silently crops or offsets.
**Why:** `overlay` filter positions based on pixel coordinates. A 4K B-roll on a 1080p base extends beyond frame boundaries.
**How to avoid:** Scale B-roll to match primary resolution before overlay: `[N:v]scale={target_w}:{target_h},setpts=...`

### Pitfall 19: Audio Drift in Long Multi-Cam Sessions

**What goes wrong:** Cameras at slightly different sample rates (e.g., 48000 vs 47999 Hz) drift apart over hours.
**Why:** Consumer cameras often have clock imprecision. Over 3 hours, even 1 Hz difference causes ~0.2s drift.
**How to avoid:** Sync.py estimates offset from the first 60s. For recordings >30min, implement a segment-based re-sync: correlate in 5-minute windows and apply per-segment correction. **Note:** This is an advanced feature for Phase 11+; initial release uses single-window sync.

---

## 12. Open Questions

1. **Max cameras in filter_complex** — FFmpeg `concat` has no documented input limit, but filter_complex complexity grows linearly with segments × inputs. Testing needed for >50 segments with 4 inputs.

2. **B-roll audio ducking precision** — When `audio_mode="mixed"`, the `amix` filter applies a flat volume reduction. Per-word ducking (duck only when B-roll overlaps speech) would require VAD analysis of the B-roll placement region. Deferred unless user requests.

3. **FPS unification cost** — Converting 24fps B-roll to 30fps project rate via FFmpeg `fps` filter adds ~5% encoding time. Consider whether to allow mixed-FPS and handle in concat (FFmpeg handles it, but with potential frame judder).

4. **Timecode extraction** — Some professional cameras embed SMPTE timecode in metadata. If available, this provides zero-compute sync. Worth checking `ffprobe -show_entries format_tags=timecode` as a fast path before cross-correlation.

---

*This document is a research and planning artifact. No implementation changes should be made based on this document without explicit user approval and per-phase plan creation.*
