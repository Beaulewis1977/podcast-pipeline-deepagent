# 🎙️ Podcast Pipeline

AI-powered podcast production pipeline for multi-platform content. Transform raw podcast recordings into optimized exports for YouTube, Spotify, TikTok, Instagram, LinkedIn, Twitter, and more.

## 🛡️ Phase 4 Hardening Highlights

- **Deterministic Runtime Safety**: Strict stage validation, per-job execution locks, and state reload boundaries prevent invalid or concurrent same-job mutation.
- **Typed Service Contracts**: `run`/`resume` now enforce stage-window validation and return explicit execution outcomes (`started`, `completed`, `rejected`).
- **Resume Through Completion**: `POST /jobs/{job_id}/resume` continues to `render` by default unless `until_stage` is set.
- **Service Security + Reliability**: Production API-key auth, sanitized 5xx errors, timeout-aware supervisor heartbeats, and reconciliation loops for stale/orphaned runs.
- **Truthful Render Semantics**: Per-platform result maps, ingest/render preflight checks, and output artifact verification remove false-success paths.
- **Provider Fallback Transparency**: Transcript-only fallback is persisted as `metadata.degraded_mode` in `analysis/analysis.json`.
- **Operator UX Completion**: Streamlit and desktop now expose full lifecycle controls (create/run/resume/delete/reconcile) plus runtime diagnostics.
- **Confidence Gates**: Runtime-critical regression suites expanded with stricter coverage thresholds for `providers`, `service`, and `stages`.

## ✨ Features

### Core Pipeline
- **Automated Transcription**: GPU-accelerated speech-to-text using faster-whisper
- **AI Analysis**: Content analysis using Gemini or Kimi AI for clips, cuts, and marketing
- **Filler Word Detection**: Automatic detection of "um", "uh", "like", etc.
- **Multi-Platform Export**: Optimized renders for 8+ platforms
- **Marketing Copy Generation**: AI-generated titles, descriptions, and hashtags

### Streamlit Web UI
- **Dashboard + Recovery**: Job overview with service-backed run/resume/delete/reconcile actions
- **Video Preview**: Timeline scrubbing and playback
- **Timeline Cut Editor**: Start/end/reason editing with validation and persisted `review/edit_plan.json`
- **Thumbnail Selector**: Grid view of candidate frames
- **Marketing Editor**: Interactive copy editing persisted in review artifacts
- **Runtime Diagnostics**: Active/stale/orphaned run visibility for operator recovery

### Platform Exports
| Platform | Format | Resolution | Max Duration | Features |
|----------|--------|------------|--------------|----------|
| YouTube | MP4 | 1920×1080 | Unlimited | H.264, AAC, faststart |
| Spotify | MP3 | Audio only | Unlimited | 320kbps, -16 LUFS |
| Apple Podcasts | M4A | Audio only | Unlimited | AAC 128kbps |
| TikTok | MP4 | 1080×1920 | 60s | 9:16 vertical, center crop |
| Instagram Reels | MP4 | 1080×1920 | 90s | 9:16 vertical |
| LinkedIn | MP4 | 1080×1080 | 10min | 1:1 square |
| Twitter/X | MP4 | 1280×720 | 2:20 | 16:9 landscape |
| Facebook | MP4 | 1920×1080 | 4hrs | 16:9 landscape |

### Video Podcast Publication Paths (Spotify + Apple)

Phase 5 adds artifact generation for video podcast workflows:

- `spotify_video`: compliant MP4 export artifact for Spotify ingest checks.
- `apple_video`: MP4 artifact for Apple RSS enclosure workflows.
- `apple_hls`: optional HLS VOD package (`master.m3u8`, variant playlists, and segments) for Apple provider-mediated hand-off.

Publication is still an operator workflow outside this repository:

- Spotify publication/replacement steps differ for hosted vs non-hosted shows and are completed in Spotify for Creators.
- Apple `apple_hls` publication is provider-mediated through Apple Podcasts Connect + eligible hosting providers.
- Apple subscriptions remain audio-only; video subscription automation is out of scope.

This pipeline intentionally produces compliant artifacts only. It does not perform direct platform upload automation.

### Desktop App (Tauri v2)
- **Cross-Platform**: Native installers for Windows (.msi), macOS (.dmg), and Linux (.deb/.AppImage)
- **Bundled Backend**: FastAPI service runs as a sidecar process -- no separate server setup
- **Full Job Lifecycle**: Create, run, run-to-stage, resume, inspect, delete, and reconcile jobs from desktop UI
- **Crash Recovery**: Detection and resume of interrupted jobs with runtime diagnostics
- **Offline-Ready**: FFmpeg and backend bundled; models downloaded on first use

### Advanced Features
- **YouTube Research**: Trend analysis, competitor research, keyword suggestions
- **Multi-Track Audio**: Per-speaker transcription with automatic track detection
- **Viral Clip Detection**: AI-powered scoring of clip viral potential
- **Aspect Ratio Conversion**: Automatic crop/letterbox for different platforms

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Beaulewis1977/podcast-pipeline.git
cd podcast-pipeline

# Install with pip
pip install -e ".[dev]"

# Or with uv (recommended)
uv sync
```

### GPU & Phase 8 Setup

Phase 8 introduces advanced GPU-accelerated video features (RIFE frame interpolation).

1. **Prerequisites**: RTX 5060 Ti (or other Blackwell GPU) requires CUDA 12.8.
1. **Install GPU Support**:
```bash
uv sync --extra gpu
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```
1. **Verify Installation**:
```bash
python scripts/smoke_test_gpu_rife.py
```
Expected output: `RIFE OK`.

For detailed configuration of filler triage and render passes, see **[Phase 8 Operator Guide](docs/phase8-operator-guide.md)**.

1. Configure `config.yaml` (tracked in this repo) for your environment:

- `paths.jobs_dir` for job/work artifact storage
- `models.provider` / `models.model` primary analysis provider
- `models.fallback_provider` / `models.fallback_model` transcript-only fallback behavior

2. Create a `.env` file with your API keys:
```bash
# Required - at least one AI provider
GEMINI_API_KEY=your_gemini_api_key

# Optional - fallback AI provider
KIMI_API_KEY=your_kimi_api_key

# Optional - for YouTube research feature
YOUTUBE_API_KEY=your_youtube_api_key
```

### Supported AI Models

#### Google Gemini (Primary Provider)
| Model | Description | Best For |
|-------|-------------|----------|
| `gemini-2.5-flash` | Best cost/performance balance | **Recommended default for video analysis** |
| `gemini-2.5-flash-latest` | Alias for latest 2.5 Flash release | Drop-in replacement for `gemini-2.5-flash` |
| `gemini-3-flash-preview` | Latest preview model with Agentic Vision | Cutting-edge video features |
| `gemini-3-pro-preview` | Most intelligent preview model | Complex analysis (higher cost) |
| `gemini-2.5-pro` | 2M token context window | Long-form video (>2 hours) |

> ⚠️ **Note:** `gemini-2.0-flash` is retiring in March 2026. Prefer `gemini-2.5-flash` or `gemini-2.5-flash-latest`.

#### Kimi K2.5 (Fallback Provider)
| Model | Description | Best For |
|-------|-------------|----------|
| `kimi-k2.5` | Latest multimodal model | **Recommended fallback** |
| `moonshot-v1-128k` | Legacy model | Backward compatibility |

Kimi uses "instant" mode (temperature 0.6) for faster responses. API: OpenAI-compatible.

### Basic Usage

```bash
# Create a new job from a video file
podcast-pipeline new /path/to/podcast.mp4 --name "episode-42"

# Run the full pipeline
podcast-pipeline run <job-id>

# Check job status
podcast-pipeline status <job-id>

# Review AI suggestions
podcast-pipeline review <job-id>

# Approve and export
podcast-pipeline approve <job-id> --platforms youtube,tiktok,spotify
```

### Web UI

Launch the Streamlit web interface:

```bash
# Using CLI
podcast-pipeline ui

# Or directly with Streamlit
streamlit run src/podcast_pipeline/ui/app.py
```

## 🔐 Service Runtime Contracts

### Authentication policy

Job-control routes (`/jobs/*`) are protected by a runtime auth policy:

- `PODCAST_PIPELINE_SERVICE_ENV=production` requires `PODCAST_PIPELINE_SERVICE_API_KEY`
- Clients must send `X-API-Key: <key>` for protected routes when auth is required
- Development mode can allow local bypass with `PODCAST_PIPELINE_SERVICE_ALLOW_UNAUTHENTICATED_DEV=true`

Example authenticated resume request:

```bash
curl -X POST http://127.0.0.1:8787/jobs/<job-id>/resume \
  -H "X-API-Key: $PODCAST_PIPELINE_SERVICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"from_stage":"analyze","background":false}'
```

### Run/Resume semantics

- `POST /jobs/{job_id}/run` supports `stage`, `until_stage`, and `quality_controls`
- `POST /jobs/{job_id}/resume` defaults to resume-through-completion (from the first incomplete stage through `render`)
- `resume` also accepts `from_stage`, `until_stage`, and `background` for explicit control
- run/resume responses include explicit `started`, `completed`, and `rejected` booleans
- invalid stage windows are rejected with schema-level `422` responses
- invalid persisted job state is surfaced as `409` (`Delete or repair this job`)
- Streamlit **Run Full Pipeline** triggers end-to-end execution semantics, not ingest-only behavior

### Lifecycle + recovery endpoints

- `DELETE /jobs/{job_id}` removes a job when no active background run exists
- `GET /jobs/resumable` returns interrupted jobs that can be resumed
- `POST /jobs/reconcile` repairs stale runtime metadata across all jobs
- `GET /system/runtime` reports `active_jobs`, `stale_jobs`, and `orphaned_jobs`

### Degraded-mode and quality controls

- Analyze writes provider fallback state to `analysis/analysis.json` at `metadata.degraded_mode`
- Render quality controls (`video_quality`, `audio_normalize`) are persisted on run and reused in render execution
- Supported `video_quality` profiles: `draft`, `standard`, `high`, `ultra`
- Use degraded-mode metadata in ops/debug workflows to distinguish full-video analysis from transcript-only fallback

Example run request with quality controls:

```bash
curl -X POST http://127.0.0.1:8787/jobs/<job-id>/run \
  -H "Content-Type: application/json" \
  -d '{"stage":"analyze","until_stage":"render","quality_controls":{"video_quality":"high","audio_normalize":true}}'
```

## 📋 Pipeline Stages

### 1. Ingest
- Validates input video
- Extracts audio (16kHz mono WAV for transcription)
- Creates proxy video (720p for AI analysis)
- Extracts video metadata
- Enforces preflight disk-capacity checks and output artifact existence checks

### 2. Transcribe
- GPU-accelerated transcription with faster-whisper
- Word-level timestamps
- Filler word detection
- Multi-track audio support
- Exports: JSON, TXT, SRT, VTT

### 3. Analyze
- AI analysis using Gemini or Kimi
- Content cut suggestions
- Viral clip identification
- Thumbnail frame recommendations
- Marketing copy generation
- Raises explicit parse failures and annotates transcript-only fallback with `metadata.degraded_mode`

### 4. Review
- Human review of AI suggestions
- Edit/approve cuts and clips with timeline range validation
- Select thumbnail
- Edit marketing copy
- Choose export platforms
- Persists review decisions through `review_state.json` and `review/edit_plan.json`

### 5. Render
- Platform-specific encoding
- Aspect ratio conversion
- Audio loudness normalization
- Marketing document generation
- Applies run-scoped quality controls, emits per-platform status map, and verifies non-empty outputs
- Generates concrete thumbnail artifacts and `output/thumbnails/manifest.json`
- Thumbnail MVP uses a **single primary** plus up to two ranked alternates from one shared selection set
- Per-target thumbnail compliance is enforced for selected `youtube`, `spotify_video`, and `apple_video` exports before success is reported
- Explicit **per-platform thumbnail assignment** is **deferred** beyond MVP scope

## 📦 Job Output Layout

For each job, artifacts are written under `jobs/<job_id>/`:

- `output/` — final platform exports (video/audio files)
- `output/thumbnails/` — generated thumbnail images + `manifest.json`
- `analysis/analysis.json` — analysis output and `metadata.degraded_mode`
- `review/review_state.json` — persisted review decisions and marketing edits
- `review/edit_plan.json` — validated timeline cuts/clips used by render

## ✂️ Phase 7 Editing Controls

### Filler decision semantics (review stage)

- `review/review_state.json` supports both:
- `filler_decisions` (explicit per-item `keep`/`remove`) and
- legacy `approved_filler_cuts` (index list).
- Render/edit-plan generation is explicit-first:
- if `filler_decisions` exists, it is authoritative.
- if absent, legacy `approved_filler_cuts` fallback is used.
- `reject_all_fillers: true` still hard-disables filler removals.
- Streamlit timeline editor also persists `filler_bulk_rules` for category-level intent (`remove_all`, `keep_all`, `review_each`).

### Smoothing controls (render stage)

Use `config.yaml` `smoothing` to tune splice behavior:

```yaml
smoothing:
  enabled: true
  micro_fade_ms: 30
  content_audio_crossfade_ms: 150
  content_video_dissolve_ms: 300
  max_snap_shift_ms: 250
  join_clamp_ratio: 0.35
  require_transition_filters: false
```

Runtime behavior:

- All kept segments receive short audio micro-fades when enabled.
- Content-cut joins may use `acrossfade` (audio) and `xfade` (video) when available.
- Filler-only joins stay on concat joins (no heavy transitions).
- Cut boundaries can snap to transcript word-gap boundaries when `analysis/transcript.json` provides word timings.
- Transition durations are clamped by `join_clamp_ratio` to avoid over-consuming short neighboring segments.

### Troubleshooting

- `xfade` mismatch errors:
- Cause: FFmpeg transition inputs must match key stream properties.
- Current render path normalizes transition branches (`fps`, format, timebase) before `xfade`, but custom edits can still break assumptions.
- If your FFmpeg build lacks transition filters, keep `smoothing.require_transition_filters: false` to auto-fallback to concat joins.
- Harsh artifacts around short cuts:
- Lower `content_audio_crossfade_ms` / `content_video_dissolve_ms`, or lower `join_clamp_ratio` for more conservative transitions.
- Snapping feels too aggressive:
- Lower `max_snap_shift_ms` or disable smoothing for exact cut boundaries.
- Streamlit state surprises after clicking:
- Button-like widgets are ephemeral across reruns; rely on persisted artifacts (`review_state.json`, `review/edit_plan.json`) and use **Save Timeline Changes** to commit edits before switching tabs/reloading.

### Backward compatibility expectations

- Existing legacy `review_state.json` and `edit_plan.json` artifacts remain executable.
- Mixed new+legacy review payloads are deterministic: explicit `filler_decisions` win over legacy index lists.
- `review/edit_plan.json` remains the render source of truth.

## 🔧 Configuration

### config.yaml

```yaml
# Directories
paths:
  jobs_dir: ./jobs
  models_cache: ./models

# AI Models
# See "Supported AI Models" section for available options
models:
  provider: gemini
  model: gemini-2.5-flash  # Best cost/performance for video
  fallback_provider: kimi
  fallback_model: kimi-k2.5  # Latest Kimi multimodal model

# Transcription
transcription:
  model: large-v3  # or small, medium
  device: cuda     # or cpu
  compute_type: float16

# Filler Detection
fillers:
  words: [um, uh, hmm, er, ah, like, you know]
  min_confidence: 0.5
  min_duration_ms: 150

# Platform Exports
platforms:
  youtube:
    video_bitrate: 8M
    loudness_lufs: -14.0
  tiktok:
    max_duration: 60
    crop_mode: center
  # ... see config.yaml for full options
```

## 📁 Project Structure

```
podcast-pipeline/
├── src/podcast_pipeline/
│   ├── cli.py              # Command-line interface
│   ├── pipeline.py         # Pipeline orchestration
│   ├── config/             # Configuration management
│   ├── models/             # Pydantic data models
│   ├── providers/          # AI provider integrations
│   ├── research/           # YouTube research & viral detection
│   ├── stages/             # Pipeline stages
│   │   ├── ingest.py
│   │   ├── transcribe.py
│   │   ├── analyze.py
│   │   ├── review.py
│   │   └── render.py
│   ├── ui/                 # Streamlit web interface
│   └── utils/              # Utilities (ffmpeg, logging, etc.)
├── tests/                  # Automated test suite
├── config.yaml             # Configuration file
└── pyproject.toml          # Project metadata
```

## 🧪 Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/podcast_pipeline --cov-report=html

# Runtime-critical coverage checks (Phase 4 hardening gates)
coverage report --include="src/podcast_pipeline/providers/*" --fail-under=78
coverage report --include="src/podcast_pipeline/service/*" --fail-under=75
coverage report --include="src/podcast_pipeline/stages/*" --fail-under=45

# Run specific test file
pytest tests/test_render.py -v
```

### Code Quality

```bash
# Format code
ruff format src tests

# Lint code
ruff check src tests

# Type check
mypy src
```

## 📊 YouTube Research Integration

The YouTube Research feature helps optimize your content strategy:

```python
from podcast_pipeline.research.youtube import YouTubeResearcher

researcher = YouTubeResearcher(api_key="your_key")

# Research a topic
result = researcher.research_topic(
    topic="AI podcasting",
    related_topics=["machine learning", "tech interviews"]
)

print(f"Average views: {result.insights['avg_views']}")
print(f"Suggested keywords: {result.suggested_keywords}")
print(f"Top competitors: {len(result.competitor_channels)}")
```

## 🎯 Viral Clip Detection

Score clips for viral potential:

```python
from podcast_pipeline.research.viral_detector import ViralClipDetector

detector = ViralClipDetector()

# Analyze transcript for engagement signals
signals = detector.analyze_transcript(transcript_data)

# Score a specific clip
score = detector.score_clip(clip_data, transcript_data)
print(f"Viral score: {score.overall_score}/10")
print(f"Reasons: {score.reasons}")

# Auto-suggest viral clips
suggestions = detector.suggest_clips(transcript_data, min_score=7.0)
```

## 🎧 Multi-Track Audio Support

For podcasts with separate audio tracks per speaker:

```bash
# The pipeline automatically detects multiple tracks
podcast-pipeline run <job-id>

# Output includes per-speaker transcripts:
# - analysis/transcript_track_0.json (Speaker 1)
# - analysis/transcript_track_1.json (Speaker 2)
# - analysis/transcript.json (merged with speaker labels)
```

## 📝 CLI Reference

```bash
# Job Management
podcast-pipeline new <video> [--name NAME]     # Create new job
podcast-pipeline list                          # List all jobs
podcast-pipeline status [JOB_ID]               # Show job status

# Pipeline Execution
podcast-pipeline run <job-id> [--stage STAGE]  # Run pipeline
podcast-pipeline run <job-id> --until STAGE    # Run up to stage

# Review & Export
podcast-pipeline review <job-id>               # View AI suggestions
podcast-pipeline approve <job-id> [--platforms LIST]  # Approve & export

# Web Interface
podcast-pipeline ui [--port 8501] [--host localhost]  # Launch UI
```

## 🖥️ Desktop Release

Pre-built desktop installers are available from the [Releases](https://github.com/Beaulewis1977/podcast-pipeline/releases) page.

| Platform | Installer | Requirements |
|----------|-----------|-------------|
| Windows | `.msi` or `.exe` (NSIS) | Windows 10+ (x64) |
| macOS (Apple Silicon) | `.dmg` | macOS 12+ (ARM) |
| macOS (Intel) | `.dmg` | macOS 12+ (x64) |
| Linux | `.deb` or `.AppImage` | Ubuntu 22.04+ / glibc 2.31+ |

### Building from source

```bash
# Build backend sidecar
uv run pyinstaller --name podcast-backend --onefile --console \
    --hidden-import podcast_pipeline --hidden-import uvicorn \
    src/podcast_pipeline/service/cli.py

# Prepare sidecars and build desktop app
cd desktop
export BACKEND_BIN=../dist/podcast-backend
node scripts/prepare-sidecars.mjs
pnpm install && pnpm tauri build
```

### Smoke testing installers

```bash
# Linux/macOS
bash desktop/scripts/smoke-test-desktop.sh path/to/artifacts/

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File desktop/scripts/smoke-test-desktop.ps1 path/to/artifacts/
```

For the full release and distribution runbook, see [docs/desktop-distribution.md](docs/desktop-distribution.md).

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - Fast speech recognition
- [Gemini](https://ai.google.dev/) - AI analysis
- [FFmpeg](https://ffmpeg.org/) - Media processing
- [Streamlit](https://streamlit.io/) - Web UI framework
