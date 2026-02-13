# 🎙️ Podcast Pipeline

AI-powered podcast production pipeline for multi-platform content. Transform raw podcast recordings into optimized exports for YouTube, Spotify, TikTok, Instagram, LinkedIn, Twitter, and more.

## ✨ Features

### Core Pipeline
- **Automated Transcription**: GPU-accelerated speech-to-text using faster-whisper
- **AI Analysis**: Content analysis using Gemini or Kimi AI for clips, cuts, and marketing
- **Filler Word Detection**: Automatic detection of "um", "uh", "like", etc.
- **Multi-Platform Export**: Optimized renders for 8+ platforms
- **Marketing Copy Generation**: AI-generated titles, descriptions, and hashtags

### Streamlit Web UI
- **Dashboard**: Job overview with status tracking
- **Video Preview**: Timeline scrubbing and playback
- **Visual Cut Editor**: Drag timeline markers for editing
- **Thumbnail Selector**: Grid view of candidate frames
- **Marketing Editor**: Interactive copy editing for all platforms

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

### Desktop App (Tauri v2)
- **Cross-Platform**: Native installers for Windows (.msi), macOS (.dmg), and Linux (.deb/.AppImage)
- **Bundled Backend**: FastAPI service runs as a sidecar process -- no separate server setup
- **Crash Recovery**: Automatic detection and resume of interrupted jobs on restart
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

### Configuration

1. Copy the example config:
```bash
cp config.yaml.example config.yaml
```

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
| `gemini-2.5-flash-latest` | Best cost/performance balance | **Recommended for video analysis** |
| `gemini-3-flash` | Latest model with Agentic Vision | Cutting-edge video features |
| `gemini-3-pro` | Most intelligent model | Complex analysis (higher cost) |
| `gemini-2.5-pro` | 2M token context window | Long-form video (>2 hours) |

> ⚠️ **Note:** `gemini-2.0-flash` is **retiring March 3, 2026**. Use `gemini-2.5-flash-latest` instead.

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
- Streamlit **Run Full Pipeline** triggers end-to-end execution semantics, not ingest-only behavior

### Degraded-mode and quality controls

- Analyze writes provider fallback state to `analysis/analysis.json` at `metadata.degraded_mode`
- Render quality controls (`video_quality`, `audio_normalize`) are persisted on run and reused in render execution
- Use degraded-mode metadata in ops/debug workflows to distinguish full-video analysis from transcript-only fallback

## 📋 Pipeline Stages

### 1. Ingest
- Validates input video
- Extracts audio (16kHz mono WAV for transcription)
- Creates proxy video (720p for AI analysis)
- Extracts video metadata

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

### 4. Review
- Human review of AI suggestions
- Approve/modify cuts and clips
- Select thumbnail
- Edit marketing copy
- Choose export platforms

### 5. Render
- Platform-specific encoding
- Aspect ratio conversion
- Audio loudness normalization
- Marketing document generation

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
  model: gemini-2.5-flash-latest  # Best cost/performance for video
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
├── tests/                  # Test suite (102 tests)
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
