# Requirements: Podcast Pipeline

**Defined:** 2026-01-29
**Last Updated:** 2026-02-04
**Core Value:** Turn a raw podcast recording into multi-platform content without touching editing software or writing marketing copy manually.

**Status Legend:**
- [x] Implemented in codebase
- [~] Partial / stubbed / not wired end-to-end
- [ ] Not started

## v1 Requirements

### Audio Processing

- [x] **AUDIO-01**: Pipeline extracts audio from video input (`src/podcast_pipeline/stages/ingest.py`)
- [~] **AUDIO-02**: Pipeline handles multi-track audio (partial: per-track transcription exists but not default) (`src/podcast_pipeline/stages/transcribe.py`)
- [ ] **AUDIO-03**: Pipeline syncs separate audio tracks with video using waveform matching
- [x] **AUDIO-04**: Pipeline detects filler words (um, uh, like, you know, basically, actually) (`src/podcast_pipeline/stages/transcribe.py`)
- [ ] **AUDIO-05**: Pipeline auto-removes detected filler words with configurable padding (cuts not applied in render)
- [~] **AUDIO-06**: User can review and override filler word cuts (partial: review state supports it; UI is basic) (`src/podcast_pipeline/stages/review.py`, `src/podcast_pipeline/ui/app.py`)
- [~] **AUDIO-07**: Pipeline normalizes audio to platform-specific loudness (partial: logic exists; dependencies missing) (`src/podcast_pipeline/stages/render.py`)
- [ ] **AUDIO-08**: Pipeline applies noise reduction to remove background hum/AC noise
- [ ] **AUDIO-09**: Pipeline normalizes each track independently before mixing (for multi-track)

### Transcription

- [x] **TRANS-01**: Pipeline generates full transcript with word-level timestamps (`src/podcast_pipeline/stages/transcribe.py`)
- [x] **TRANS-02**: Transcript includes confidence scores per word (`src/podcast_pipeline/models/transcript.py`)
- [x] **TRANS-03**: Pipeline exports transcript as plain text (.txt) (`src/podcast_pipeline/stages/transcribe.py`)
- [x] **TRANS-04**: Pipeline exports transcript as SRT subtitles (`src/podcast_pipeline/stages/transcribe.py`)
- [x] **TRANS-05**: Pipeline exports transcript as VTT subtitles (`src/podcast_pipeline/stages/transcribe.py`)

### Video Processing

- [x] **VIDEO-01**: Pipeline extracts metadata (duration, resolution, codec, audio channels) (`src/podcast_pipeline/utils/ffmpeg.py`)
- [x] **VIDEO-02**: Pipeline creates low-res proxy for AI analysis (`src/podcast_pipeline/stages/ingest.py`)
- [ ] **VIDEO-03**: Pipeline applies basic auto color correction (white balance, exposure)
- [ ] **VIDEO-04**: Pipeline detects extended silences/dead air
- [ ] **VIDEO-05**: Pipeline removes dead air segments automatically
- [~] **VIDEO-06**: AI analyzes video to identify boring/tangent sections (partial: AI returns content cuts but no dedicated logic) (`src/podcast_pipeline/providers/*`)
- [~] **VIDEO-07**: User reviews and approves content cuts before application (partial: review state exists; render ignores cuts) (`src/podcast_pipeline/stages/review.py`, `src/podcast_pipeline/stages/render.py`)

### Captions & Graphics

- [ ] **GRAPH-01**: Pipeline generates burned-in captions with configurable styles
- [ ] **GRAPH-02**: User can customize caption appearance (font, size, color, position)
- [ ] **GRAPH-03**: Pipeline generates speaker name lower thirds
- [ ] **GRAPH-04**: User can configure lower third timing and style
- [ ] **GRAPH-05**: Pipeline generates episode title card graphics
- [ ] **GRAPH-06**: User can customize title card template

### AI Analysis

- [~] **AI-01**: AI provider abstraction allows switching between Gemini, Kimi, OpenAI (partial: Gemini + Kimi implemented; OpenAI not) (`src/podcast_pipeline/providers/*`)
- [x] **AI-02**: Pipeline uses Gemini as primary analysis provider (model configurable; default in config) (`src/podcast_pipeline/providers/gemini.py`)
- [x] **AI-03**: Pipeline falls back to Kimi K2.5 on Gemini failure (`src/podcast_pipeline/stages/analyze.py`)
- [x] **AI-04**: AI identifies 3-5 viral clip candidates per episode (`src/podcast_pipeline/providers/base.py`)
- [x] **AI-05**: AI scores each clip candidate for virality (1-10) (`src/podcast_pipeline/models/analysis.py`)
- [x] **AI-06**: AI suggests hook text for each clip (`src/podcast_pipeline/models/analysis.py`)
- [x] **AI-07**: AI extracts 3-5 thumbnail frame candidates (`src/podcast_pipeline/models/analysis.py`)
- [x] **AI-08**: AI suggests text overlay for each thumbnail candidate (`src/podcast_pipeline/models/analysis.py`)
- [x] **AI-09**: AI generates 3 YouTube title options (under 70 chars) (`src/podcast_pipeline/providers/base.py`)
- [x] **AI-10**: AI generates platform-specific descriptions (`src/podcast_pipeline/providers/base.py`)
- [x] **AI-11**: AI generates platform-specific hashtags (`src/podcast_pipeline/providers/base.py`)
- [x] **AI-12**: AI extracts episode summary and topics (`src/podcast_pipeline/models/analysis.py`)

### Research

- [~] **RSRCH-01**: Pipeline queries YouTube Data API for top videos (partial: client exists, not wired) (`src/podcast_pipeline/research/youtube.py`)
- [ ] **RSRCH-02**: Pipeline analyzes title patterns in top-performing content
- [ ] **RSRCH-03**: Pipeline analyzes thumbnail patterns in top-performing content
- [ ] **RSRCH-04**: Pipeline surfaces research insights in review UI
- [ ] **RSRCH-05**: Research informs AI suggestions for titles and thumbnails

### Platform Exports

- [x] **EXPORT-01**: Pipeline exports YouTube video (MP4, H.264, faststart) (`src/podcast_pipeline/stages/render.py`)
- [ ] **EXPORT-02**: Pipeline exports YouTube thumbnail (1280x720)
- [~] **EXPORT-03**: Pipeline exports Spotify audio (MP3 320kbps, -16 LUFS) (partial: loudness normalize depends on missing deps) (`src/podcast_pipeline/stages/render.py`)
- [~] **EXPORT-04**: Pipeline exports Apple Podcasts audio (M4A AAC, -16 LUFS) (partial: loudness normalize depends on missing deps) (`src/podcast_pipeline/stages/render.py`)
- [~] **EXPORT-05**: Pipeline exports TikTok vertical clips (9:16, under 60s) (partial: full-video export only) (`src/podcast_pipeline/stages/render.py`)
- [~] **EXPORT-06**: Pipeline exports Instagram Reels vertical clips (9:16) (partial: full-video export only) (`src/podcast_pipeline/stages/render.py`)
- [ ] **EXPORT-07**: Pipeline exports YouTube Shorts vertical clips (9:16)
- [~] **EXPORT-08**: Pipeline exports LinkedIn clips (1:1 square, under 10 min) (partial: full-video export only) (`src/podcast_pipeline/stages/render.py`)
- [~] **EXPORT-09**: Pipeline exports Twitter/X clips (16:9, under 2:20) (partial: full-video export only) (`src/podcast_pipeline/stages/render.py`)
- [~] **EXPORT-10**: Pipeline exports Facebook clips (partial: full-video export only) (`src/podcast_pipeline/stages/render.py`)
- [x] **EXPORT-11**: User can select which platforms to export for each job (`src/podcast_pipeline/stages/review.py`)
- [x] **EXPORT-12**: Pipeline generates marketing copy document with all platform text (`src/podcast_pipeline/stages/render.py`)

### Review UI

- [x] **UI-01**: Web UI displays video preview with timeline (`src/podcast_pipeline/ui/app.py`)
- [~] **UI-02**: Web UI shows visual markers for proposed cuts (partial: list/checkboxes, not graphical markers) (`src/podcast_pipeline/ui/app.py`)
- [~] **UI-03**: Web UI allows reviewing and approving filler cuts (basic checklist) (`src/podcast_pipeline/ui/app.py`)
- [~] **UI-04**: Web UI allows reviewing and approving content cuts (basic checklist) (`src/podcast_pipeline/ui/app.py`)
- [ ] **UI-05**: Web UI allows previewing clips before/after cuts
- [ ] **UI-06**: Web UI displays viral clip candidates for selection
- [ ] **UI-07**: User can select which clips to export
- [ ] **UI-08**: User can choose crop ratio per clip (16:9, 9:16, 1:1)
- [x] **UI-09**: Web UI displays thumbnail candidates in grid (`src/podcast_pipeline/ui/app.py`)
- [~] **UI-10**: User can select thumbnails (partial: single selection only) (`src/podcast_pipeline/ui/app.py`)
- [ ] **UI-11**: User can edit thumbnail text overlay suggestions
- [x] **UI-12**: Web UI has tabs for each platform's marketing copy (`src/podcast_pipeline/ui/app.py`)
- [~] **UI-13**: User can edit marketing copy (partial: no character count warnings) (`src/podcast_pipeline/ui/app.py`)
- [ ] **UI-14**: Web UI shows research insights as hints
- [x] **UI-15**: Web UI has export settings panel (`src/podcast_pipeline/ui/app.py`)
- [~] **UI-16**: Web UI shows render progress (partial: stage runner exists, limited progress) (`src/podcast_pipeline/ui/app.py`)
- [x] **UI-17**: Web UI persists review state (`src/podcast_pipeline/stages/review.py`)
- [ ] **UI-18**: Web UI works on mobile (responsive design)

### CLI & Workflow

- [x] **CLI-01**: CLI command to create new job from video file (`src/podcast_pipeline/cli.py`)
- [x] **CLI-02**: CLI command to run pipeline stages (`src/podcast_pipeline/cli.py`)
- [x] **CLI-03**: CLI command to check job status (`src/podcast_pipeline/cli.py`)
- [x] **CLI-04**: CLI command to launch review UI (`src/podcast_pipeline/cli.py`)
- [x] **CLI-05**: Pipeline is resumable from any stage (skips completed stages) (`src/podcast_pipeline/pipeline.py`)
- [x] **CLI-06**: Pipeline writes state after each stage completion (`src/podcast_pipeline/stages/base.py`)
- [ ] **CLI-07**: User can toggle features on/off per job (captions, graphics, cuts)
- [~] **CLI-08**: Pipeline has configurable retry logic for API failures (partial: retries are hard-coded) (`src/podcast_pipeline/providers/*`)
- [x] **CLI-09**: Pipeline logs all operations (structured JSON logging available) (`src/podcast_pipeline/utils/logging.py`)

## v2 Requirements (Deferred)

### Thumbnails
- **THUMB-01**: AI generates full thumbnails from scratch (not just frame extraction)
- **THUMB-02**: AI creates text overlays with proper design (not just suggestions)

### B-Roll
- **BROLL-01**: Pipeline integrates stock video API
- **BROLL-02**: AI identifies where to insert B-roll
- **BROLL-03**: Pipeline automatically inserts B-roll at marked positions

### Upload
- **UPLOAD-01**: Pipeline uploads directly to YouTube via API
- **UPLOAD-02**: Pipeline uploads to Spotify via RSS feed update
- **UPLOAD-03**: Pipeline uploads to TikTok via API
- **UPLOAD-04**: Pipeline schedules uploads for optimal times

### Advanced
- **ADV-01**: Multi-camera support (switching between angles)
- **ADV-02**: Speaker diarization (who said what)
- **ADV-03**: Analytics integration (track performance)

## Out of Scope

Explicitly excluded to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Live recording | Use Riverside/Zoom for recording, we do post-production |
| Real-time editing preview | Computationally expensive, unnecessary for workflow |
| Collaborative editing | Single-user tool for now, adds complexity |
| Social media scheduling | Use Buffer/Later, don't reinvent |
| AI voice cloning | Ethical concerns, not needed |
| Music/sound effects library | Use separate tools, licensing complexity |
| Video effects/transitions | Keep it simple, focus on cleanup not creative editing |

## Phase Alignment (High-Level)

- **Phase 1 (Wiring + Stability):** Core pipeline wiring, multi-track default, edit plan + render cuts, UI job consistency
- **Phase 2 (Research + Viral):** Research insights, enhanced scoring, caching
- **Phase 3 (Desktop + Packaging):** Backend service + Tauri distribution
