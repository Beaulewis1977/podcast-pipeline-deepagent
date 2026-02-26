# Phase 11: Multi-Cam Core & B-Roll Engine

## 1. Goal
Implement a robust multi-camera processing and switching engine. It handles an arbitrary number of video/audio inputs, auto-aligns them on a master virtual timeline, and introduces B-roll handling with frame-smoothed Practical-RIFE transitions.

**Depends on:** Phase 10

## 2. Scope / Requirements

### 2.1 Asset Ingestion & Organization
- Support dynamic drag-and-drop ingestion of `primary_video`, `angle_[n]_video`, `broll_[n]_clip`, and `audio_only_[n]` files.
- Extend the `JobManifest` to track an `AssetRegistry` listing start times, frame rates, and resolutions per asset.

### 2.2 Universal Auto-Synchronization
- Broaden the bounded cross-correlation sync (`utils/sync.py`) from twofold (video & audio) to `n`-fold synchronization.
- Establish a "Master Timeline Zero" where all drift correction and waveform alignments anchor dynamically.
- Gracefully handle distinct frame rates by interpolating to a synchronized project FPS (default 60 fps).

### 2.3 FFmpeg `filter_complex` Switching logic
- Write an FFmpeg MCP tool (`switch_cameras`) handling `concat` and `select` filters dynamically based on a synchronized JSON `camera_plan.json` outputted by the Co-Pilot.
- Support `timestamp` bounds for switching (e.g. `[0:v]trim=0:10[v0]; [1:v]trim=10:15[v1]...`).
- Implement B-roll insertion via the `overlay` filter layered atop primary footage.

### 2.4 Practical-RIFE Visual Polish
- Extend Phase 8 RIFE integration to automatically trigger during camera angle switches and B-roll inserts if scene differences warrant "buttery-smooth" motion.
- Provide a GPU offload configuration (Tauri desktop precedence) avoiding UI stall during complex renders.

## 3. Tech Stack Requirements
- FFmpeg 6.0+ (`filter_complex`, `concat`, `trim`, `setpts`)
- `scipy.signal.correlate` and `librosa.resample` (Expanded to N channels)
- `practical-RIFE` module (GPU/CUDA execution logic from Phase 8)
- Additional JSON schema: `camera_plan.json` encapsulating exact cut and B-roll points.

## 4. Success Criteria
1. Submitting 3 different camera angles and an external audio track outputs a synced, unified `edit_plan.json`.
2. A test `camera_plan` file successfully switches video inputs in FFmpeg while maintaining synchronized audio.
3. B-roll clips cleanly overlay over the primary video track, and native B-roll audio ducks automatically without affecting main voice tracks.
4. RIFE logic creates seamless bridge frames at user-specified switch points, eliminating harsh jump cuts.
