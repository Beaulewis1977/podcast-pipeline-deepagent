# Podcast Pipeline - Design Document

> **Status:** Draft
> **Created:** 2026-01-29
> **Author:** Human + Claude

---

## 1. Overview

### What Is This?

A tool that takes a raw podcast recording and produces publication-ready content for multiple platforms. Input a video file, get back:

- Edited video (filler words removed, boring sections cut, audio/video enhanced)
- Audio-only exports for podcast platforms
- Short viral clips for social media
- Multiple thumbnail options
- Full transcript
- Platform-optimized marketing copy (titles, descriptions, hashtags)

### Who Is It For?

A 3-host podcast recorded in one room with a single iPhone camera and individual mics. Future support for remote guests and distributed recording.

### Design Principles

1. **Simple over clever** - No over-engineering, add complexity only when needed
2. **Resumable** - Pipeline can stop and resume from any stage
3. **Model-agnostic** - Easy to swap AI models (Gemini, Kimi, Claude, etc.)
4. **Platform-aware** - Each export meets specific platform requirements
5. **Human-in-the-loop** - Auto-remove filler words, but humans review content cuts

---

## 2. Features

### Core Features (v1)

| Feature | Description | Automation Level |
|---------|-------------|------------------|
| Filler removal | Detect and remove "um", "uh", "like", etc. | Automatic |
| Content cuts | Identify boring/dead sections | Human review |
| Audio enhancement | Normalize loudness, reduce noise | Automatic |
| Video enhancement | Basic color correction | Automatic |
| Transcription | Full text with timestamps | Automatic |
| Viral clips | Extract 3-5 high-engagement moments | Human review |
| Thumbnails | Extract 3-5 frame options with text suggestions | Human review |
| Marketing copy | Titles, descriptions per platform | Human review |
| Research | Analyze top-performing content in niche | Informs suggestions |

### Platform Exports (v1)

| Platform | Format | Specs |
|----------|--------|-------|
| YouTube | MP4 (H.264/AV1) | 1080p+, AAC stereo, -14 LUFS |
| Spotify | MP3 | 128-320kbps, -16 LUFS, ID3 tags |
| Apple Podcasts | M4A/MP3 | AAC 64-256kbps, -16 LUFS, chapters |
| TikTok/Reels/Shorts | MP4 | 9:16 vertical, <60s, -14 LUFS |
| LinkedIn | MP4 | 1:1 or 16:9, <10min |
| Twitter/X | MP4 | 16:9, <2:20 |

### Future Features (v2+)

- Multi-track audio support (separate mics)
- Remote guest video stitching
- Auto-upload to platforms via APIs
- Episode scheduling
- Analytics integration

---

## 3. Architecture

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           JOB MANAGER                               │
│       (orchestrates stages, tracks state, handles failures)        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
    ┌──────────┬──────────┬───────┴───────┬──────────┬──────────┐
    ▼          ▼          ▼               ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐     ┌────────┐ ┌────────┐ ┌────────┐
│ INGEST │ │TRANSCR-│ │ANALYZE │     │RESEARCH│ │ REVIEW │ │ RENDER │
│        │ │  IBE   │ │        │     │        │ │  (UI)  │ │        │
│FFprobe │ │Whisper │ │Gemini/ │     │Web API │ │Stream- │ │FFmpeg  │
│FFmpeg  │ │        │ │Kimi    │     │        │ │lit     │ │        │
└────────┘ └────────┘ └────────┘     └────────┘ └────────┘ └────────┘
    │          │          │               │          │          │
    └──────────┴──────────┴───────────────┴──────────┴──────────┘
                                  │
                      ┌───────────────────────┐
                      │  jobs/<job_id>/       │
                      │    state.json         │
                      │    transcript.json    │
                      │    analysis.json      │
                      │    research.json      │
                      │    ...                │
                      └───────────────────────┘
```

### Stage Dependencies

```
INGEST ──► TRANSCRIBE ──► ANALYZE ──┬──► RESEARCH ──► REVIEW ──► RENDER
                                    │                    ▲
                                    └────────────────────┘
                                    (research informs review)
```

### Job State Machine

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ PENDING  │───►│ RUNNING  │───►│ WAITING  │───►│ COMPLETE │
└──────────┘    └──────────┘    │ (review) │    └──────────┘
                    │           └──────────┘
                    ▼
               ┌──────────┐
               │  FAILED  │
               └──────────┘
```

---

## 4. Pipeline Stages (Detailed)

### Stage 1: INGEST

**Purpose:** Extract metadata, audio, and create analysis proxy.

**Inputs:**
- Raw video file (MP4, MOV, MKV)

**Outputs:**
- `metadata.json` - Duration, resolution, codec, audio channels
- `audio.wav` - Extracted audio (PCM 16-bit, 16kHz mono for Whisper)
- `proxy.mp4` - Low-res proxy for AI analysis (720p, CRF 30)

**Tech:**
- FFprobe for metadata
- FFmpeg for extraction

**Code:**
```python
class IngestStage:
    def run(self, video_path: Path) -> IngestResult:
        metadata = self._probe(video_path)
        audio_path = self._extract_audio(video_path)
        proxy_path = self._create_proxy(video_path)
        return IngestResult(metadata, audio_path, proxy_path)
```

---

### Stage 2: TRANSCRIBE

**Purpose:** Convert speech to text with word-level timestamps, detect filler words.

**Inputs:**
- `audio.wav` from Ingest

**Outputs:**
- `transcript.json` - Full transcript with word timestamps
- `filler_cuts.json` - Detected filler words with timestamps

**Tech:**
- faster-whisper (large-v3, CUDA, float16)

**Filler Detection Config:**
```yaml
fillers:
  words: ["um", "uh", "hmm", "er", "ah", "like", "you know", "basically", "actually"]
  min_confidence: 0.5
  min_duration_ms: 150
  padding_before_ms: 50
  padding_after_ms: 50
```

**Output Schema:**
```json
{
  "transcript": {
    "text": "Full transcript text...",
    "segments": [
      {
        "start": 0.0,
        "end": 5.2,
        "text": "Welcome to the show",
        "words": [
          {"word": "Welcome", "start": 0.0, "end": 0.4, "confidence": 0.98},
          {"word": "to", "start": 0.4, "end": 0.5, "confidence": 0.99}
        ]
      }
    ]
  },
  "filler_cuts": [
    {"start": 12.3, "end": 12.8, "word": "um", "confidence": 0.87}
  ]
}
```

---

### Stage 3: ANALYZE

**Purpose:** AI analyzes video content to identify cuts, clips, thumbnails, and generate marketing.

**Inputs:**
- `proxy.mp4` from Ingest
- `transcript.json` from Transcribe

**Outputs:**
- `analysis.json` - Complete analysis result

**Tech:**
- Primary: Gemini 3 Pro (gemini-3-pro-image-preview)
- Fallback: Kimi K2.5, Claude, GPT-4o

**Provider Abstraction:**
```python
class AnalysisProvider:
    def analyze(self, video_path: Path, transcript: dict) -> AnalysisResult:
        raise NotImplementedError

class GeminiProvider(AnalysisProvider):
    def __init__(self, model: str = "gemini-3-pro-image-preview"):
        self.model = genai.GenerativeModel(model)

    def analyze(self, video_path: Path, transcript: dict) -> AnalysisResult:
        # Upload video, send prompt, parse response
        ...

class KimiProvider(AnalysisProvider):
    def __init__(self, model: str = "k2.5"):
        ...
```

**Analysis Prompt Structure:**
```
You are a professional podcast editor and marketing strategist.

INPUT:
- Video file attached
- Transcript: {transcript}

ANALYZE AND RETURN JSON:

1. CONTENT_CUTS: Sections to remove (boring, off-topic, dead air)
   - start_time, end_time, reason

2. VIRAL_CLIPS: 3-5 moments with high engagement potential
   - start_time, end_time, description, virality_score (1-10), suggested_hook

3. THUMBNAIL_FRAMES: 3-5 optimal frames for thumbnails
   - timestamp, visual_description, suggested_text_overlay, emotion

4. MARKETING:
   - youtube_title (3 options, <70 chars)
   - youtube_description (with timestamps)
   - spotify_description
   - apple_podcasts_description
   - linkedin_post
   - twitter_post
   - tiktok_caption
   - hashtags (platform-specific)
   - keywords (for SEO)

5. METADATA:
   - episode_summary (2-3 sentences)
   - topics_discussed (list)
   - guest_names (if mentioned)
   - mood/tone
```

**Output Schema:**
```json
{
  "content_cuts": [
    {
      "start": "02:15",
      "end": "02:45",
      "start_seconds": 135.0,
      "end_seconds": 165.0,
      "reason": "Off-topic tangent about weather"
    }
  ],
  "viral_clips": [
    {
      "start": "15:30",
      "end": "16:45",
      "start_seconds": 930.0,
      "end_seconds": 1005.0,
      "description": "Host shares controversial take on AI",
      "virality_score": 9,
      "suggested_hook": "Hot take: AI will replace podcasters in 5 years"
    }
  ],
  "thumbnail_frames": [
    {
      "timestamp": "23:15",
      "timestamp_seconds": 1395.0,
      "visual_description": "Host laughing, good lighting, expressive",
      "suggested_text_overlay": "We can't believe this happened",
      "emotion": "joy"
    }
  ],
  "marketing": {
    "youtube": {
      "titles": [
        "We Need to Talk About AI (This Changes Everything)",
        "The Truth About AI Nobody Wants to Hear",
        "AI Just Changed the Game Forever | Ep. 47"
      ],
      "description": "In this episode, we dive deep into..."
    },
    "spotify": {
      "description": "..."
    },
    "tiktok": {
      "captions": ["POV: When AI takes your job", "..."]
    },
    "hashtags": {
      "youtube": ["#podcast", "#AI", "#tech"],
      "tiktok": ["#podcastclips", "#fyp", "#AI"],
      "linkedin": ["#artificialintelligence", "#futureofwork"]
    }
  },
  "metadata": {
    "summary": "...",
    "topics": ["AI", "Future of work", "Technology"],
    "mood": "energetic, thought-provoking"
  }
}
```

---

### Stage 4: RESEARCH

**Purpose:** Search for top-performing content in the podcast's niche to inform marketing suggestions.

**Inputs:**
- `analysis.json` (topics, keywords)

**Outputs:**
- `research.json` - Trending content analysis

**Tech:**
- YouTube Data API (top videos in niche)
- Spotify API (top podcasts)
- SerpAPI or Perplexity (web search)

**Research Focus:**
```yaml
research:
  platforms:
    - youtube
    - spotify
    - tiktok
  filters:
    recency: 30_days          # Only content from last 30 days
    min_views: 10000          # YouTube minimum
    min_streams: 5000         # Spotify minimum
    top_n: 20                 # Analyze top 20 results
  extract:
    - title_patterns          # Common words, structures
    - thumbnail_styles        # Colors, text placement, faces
    - description_structure   # How they format descriptions
    - hashtag_trends          # What's working now
    - hook_patterns           # First 3 seconds of viral clips
```

**Output Schema:**
```json
{
  "youtube": {
    "top_videos": [
      {
        "title": "Example Top Video Title",
        "views": 1500000,
        "upload_date": "2026-01-15",
        "channel": "Popular Podcast",
        "thumbnail_url": "..."
      }
    ],
    "title_patterns": {
      "common_words": ["truth", "nobody", "actually", "changed"],
      "structures": ["Question format", "Number lists", "Controversy hooks"],
      "avg_length": 52
    },
    "thumbnail_patterns": {
      "has_face": "85%",
      "has_text": "92%",
      "dominant_colors": ["red", "yellow", "white"],
      "text_position": "center-right"
    }
  },
  "spotify": {
    "top_episodes": [...],
    "title_patterns": {...}
  },
  "tiktok": {
    "trending_sounds": [...],
    "hook_patterns": [...]
  },
  "recommendations": {
    "title_suggestions": [
      "Based on trends, consider: 'The [Topic] Truth Nobody Talks About'"
    ],
    "thumbnail_suggestions": [
      "Use a close-up face shot with surprised expression",
      "Add bold yellow text on right side"
    ]
  }
}
```

---

### Stage 5: REVIEW (Web UI)

**Purpose:** Human reviews AI suggestions, accepts/rejects cuts, edits marketing copy.

**Tech:** Streamlit (keep it simple)

**UI Sections:**

1. **Video Preview**
   - Embedded player with timeline
   - Visual markers for proposed cuts (red) and viral clips (green)

2. **Cuts Review**
   - Filler cuts: Auto-approved, but can toggle off
   - Content cuts: Checkbox per cut, preview clip before/after
   - "Accept All Fillers" / "Review Content Cuts" workflow

3. **Viral Clips**
   - Preview each clip
   - Select which ones to export
   - Choose crop (16:9, 9:16, 1:1)

4. **Thumbnails**
   - Grid of 3-5 extracted frames
   - Click to select (can select multiple for A/B testing)
   - Edit text overlay suggestion

5. **Marketing Copy**
   - Tabs per platform (YouTube, Spotify, TikTok, etc.)
   - Editable text fields
   - Character count (warn if over limit)
   - Research insights shown as hints ("Top videos use X pattern")

6. **Export Settings**
   - Checkboxes for which platforms to export
   - Quality presets (draft/preview vs final)
   - Output directory

7. **Render Button**
   - Shows estimated time
   - Progress bar during render

**State Persistence:**
All changes saved to `review_state.json` so user can close browser and resume.

---

### Stage 6: RENDER

**Purpose:** Produce final exports for all selected platforms.

**Inputs:**
- Original video
- Approved cuts (filler + content)
- Selected clips
- Selected thumbnails
- Final marketing copy
- Export settings

**Outputs (per platform):**

| Platform | Files |
|----------|-------|
| YouTube | `youtube_final.mp4`, `youtube_thumbnail.jpg` |
| Spotify | `spotify_audio.mp3`, `spotify_metadata.json` |
| Apple | `apple_audio.m4a`, `apple_chapters.txt` |
| TikTok | `tiktok_clip_1.mp4`, `tiktok_clip_2.mp4`, ... |
| LinkedIn | `linkedin_clip.mp4` |
| Twitter | `twitter_clip.mp4` |
| Transcript | `transcript.txt`, `transcript.srt`, `transcript.vtt` |
| Marketing | `marketing_copy.md` |

**Video Processing Pipeline:**

```
Original Video
      │
      ▼
┌─────────────┐
│ Apply Cuts  │ ── Remove filler + content cuts
└─────────────┘
      │
      ▼
┌─────────────┐
│ Audio       │ ── Normalize to target LUFS
│ Enhancement │ ── Noise reduction (optional)
│             │ ── Compression/limiting
└─────────────┘
      │
      ▼
┌─────────────┐
│ Video       │ ── Color correction (auto or preset)
│ Enhancement │ ── Stabilization (if needed)
└─────────────┘
      │
      ▼
┌─────────────┐
│ Platform    │ ── Encode to platform specs
│ Encoding    │ ── Generate all formats
└─────────────┘
      │
      ▼
   Output Files
```

**Platform Encoding Specs:**

```yaml
platforms:
  youtube:
    container: mp4
    video_codec: libx264  # or av1 for quality
    video_bitrate: 8M
    audio_codec: aac
    audio_bitrate: 256k
    audio_channels: stereo
    loudness: -14 LUFS
    resolution: source  # keep original

  spotify:
    container: mp3
    audio_bitrate: 320k
    audio_channels: stereo
    loudness: -16 LUFS
    sample_rate: 44100
    id3_tags: true

  apple_podcasts:
    container: m4a
    audio_codec: aac
    audio_bitrate: 128k
    loudness: -16 LUFS
    chapters: true

  tiktok:
    container: mp4
    video_codec: libx264
    resolution: 1080x1920  # 9:16 vertical
    duration_max: 60
    loudness: -14 LUFS
    crop_mode: center  # or face-track

  linkedin:
    container: mp4
    resolution: 1080x1080  # 1:1 square
    duration_max: 600  # 10 min

  twitter:
    container: mp4
    resolution: 1280x720
    duration_max: 140
    video_bitrate: 5M
```

**Thumbnail Generation:**

```yaml
thumbnails:
  formats:
    youtube: 1280x720 (16:9)
    spotify: 3000x3000 (1:1)
    apple: 3000x3000 (1:1)

  processing:
    - extract_frame
    - auto_enhance (brightness, contrast, saturation)
    - add_text_overlay (if selected)
    - export_multiple_formats
```

---

## 5. Data Structures

### Job Directory Structure

```
jobs/
└── 2026-01-29_episode-47/
    ├── state.json              # Job state machine
    ├── config.json             # Job-specific settings
    ├── input/
    │   └── raw_recording.mp4   # Original file (or symlink)
    ├── intermediate/
    │   ├── audio.wav           # Extracted audio
    │   ├── proxy.mp4           # Low-res proxy
    │   └── metadata.json       # FFprobe output
    ├── analysis/
    │   ├── transcript.json     # Whisper output
    │   ├── filler_cuts.json    # Detected fillers
    │   ├── analysis.json       # AI analysis
    │   └── research.json       # Trend research
    ├── review/
    │   └── review_state.json   # User selections
    └── output/
        ├── youtube/
        │   ├── final.mp4
        │   └── thumbnail.jpg
        ├── spotify/
        │   └── audio.mp3
        ├── clips/
        │   ├── clip_1_tiktok.mp4
        │   ├── clip_1_linkedin.mp4
        │   └── ...
        ├── transcripts/
        │   ├── transcript.txt
        │   ├── transcript.srt
        │   └── transcript.vtt
        └── marketing/
            └── copy.md
```

### State File Schema

```json
{
  "job_id": "2026-01-29_episode-47",
  "created_at": "2026-01-29T10:30:00Z",
  "updated_at": "2026-01-29T12:45:00Z",
  "status": "waiting_review",
  "stages": {
    "ingest": {
      "status": "complete",
      "started_at": "2026-01-29T10:30:00Z",
      "completed_at": "2026-01-29T10:32:00Z",
      "outputs": ["audio.wav", "proxy.mp4", "metadata.json"]
    },
    "transcribe": {
      "status": "complete",
      "started_at": "2026-01-29T10:32:00Z",
      "completed_at": "2026-01-29T10:40:00Z",
      "outputs": ["transcript.json", "filler_cuts.json"]
    },
    "analyze": {
      "status": "complete",
      "started_at": "2026-01-29T10:40:00Z",
      "completed_at": "2026-01-29T10:45:00Z",
      "provider": "gemini",
      "model": "gemini-3-pro-image-preview",
      "outputs": ["analysis.json"]
    },
    "research": {
      "status": "complete",
      "started_at": "2026-01-29T10:45:00Z",
      "completed_at": "2026-01-29T10:46:00Z",
      "outputs": ["research.json"]
    },
    "review": {
      "status": "waiting",
      "started_at": "2026-01-29T10:46:00Z"
    },
    "render": {
      "status": "pending"
    }
  },
  "error": null
}
```

---

## 6. Configuration

### Global Config (config.yaml)

```yaml
# Podcast Pipeline Configuration

# Directories
paths:
  jobs_dir: ./jobs
  models_cache: ./models

# AI Models
models:
  video_analysis:
    provider: gemini
    model: gemini-3-pro-image-preview
    fallback:
      - provider: kimi
        model: k2.5
      - provider: openai
        model: gpt-4o

  transcription:
    provider: whisper
    model: large-v3
    device: cuda
    compute_type: float16

# API Keys (from environment)
api_keys:
  gemini: ${GEMINI_API_KEY}
  kimi: ${KIMI_API_KEY}
  openai: ${OPENAI_API_KEY}
  youtube: ${YOUTUBE_API_KEY}
  spotify: ${SPOTIFY_CLIENT_ID}

# Filler Detection
fillers:
  words:
    - um
    - uh
    - hmm
    - er
    - ah
    - like
    - you know
    - basically
    - actually
    - so
  min_confidence: 0.5
  min_duration_ms: 150
  padding_ms: 50

# Audio Processing
audio:
  target_loudness:
    youtube: -14
    spotify: -16
    apple: -16
    tiktok: -14
  noise_reduction: auto  # auto, off, or threshold value

# Video Processing
video:
  color_correction: auto  # auto, off, or preset name
  stabilization: off      # off, auto

# Research
research:
  enabled: true
  platforms:
    - youtube
    - spotify
  recency_days: 30
  min_views: 10000
  top_n: 20

# Export Defaults
export:
  platforms:
    - youtube
    - spotify
    - apple
    - tiktok
  quality: final  # draft or final
```

### Environment Variables (.env)

```bash
# Required
GEMINI_API_KEY=your_key_here

# Optional (for model switching)
KIMI_API_KEY=
OPENAI_API_KEY=

# Optional (for research)
YOUTUBE_API_KEY=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SERPAPI_KEY=
```

---

## 7. Project Structure

```
podcast-pipeline/
├── pyproject.toml           # Dependencies, project metadata
├── config.yaml              # Global configuration
├── .env                     # API keys (git-ignored)
├── .env.example             # Template for .env
├── .gitignore
├── README.md
│
├── src/
│   └── podcast_pipeline/
│       ├── __init__.py
│       ├── cli.py           # Command-line interface
│       ├── job.py           # Job manager
│       ├── config.py        # Config loading
│       │
│       ├── stages/
│       │   ├── __init__.py
│       │   ├── base.py      # Base stage class
│       │   ├── ingest.py
│       │   ├── transcribe.py
│       │   ├── analyze.py
│       │   ├── research.py
│       │   └── render.py
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py      # Abstract provider
│       │   ├── gemini.py
│       │   ├── kimi.py
│       │   ├── openai.py
│       │   └── whisper.py
│       │
│       ├── platforms/
│       │   ├── __init__.py
│       │   ├── youtube.py   # YouTube export specs
│       │   ├── spotify.py
│       │   ├── apple.py
│       │   ├── tiktok.py
│       │   ├── linkedin.py
│       │   └── twitter.py
│       │
│       └── utils/
│           ├── __init__.py
│           ├── ffmpeg.py    # FFmpeg wrapper (subprocess, not os.system)
│           ├── time.py      # Time parsing utilities
│           └── logging.py   # Structured logging
│
├── ui/
│   ├── app.py               # Streamlit entry point
│   └── components/
│       ├── video_player.py
│       ├── cuts_review.py
│       ├── clips_review.py
│       ├── thumbnails.py
│       └── marketing.py
│
├── tests/
│   ├── conftest.py
│   ├── test_stages/
│   ├── test_providers/
│   └── test_utils/
│
├── jobs/                    # Job output directory (git-ignored)
│
└── docs/
    └── plans/
        └── 2026-01-29-podcast-pipeline-design.md
```

---

## 8. Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Language | Python 3.12+ | Existing codebase, AI library support |
| Package Manager | uv | Fast, modern Python tooling |
| CLI | Typer | Simple, modern CLI framework |
| Web UI | Streamlit | Already using, good for quick dashboards |
| Transcription | faster-whisper | Best local transcription, GPU support |
| Video Analysis | Gemini 3 Pro | Video understanding, good structured output |
| Video Processing | FFmpeg | Industry standard, GPU encoding support |
| Audio Processing | FFmpeg + pyloudnorm | Loudness normalization |
| Config | PyYAML + Pydantic | Type-safe configuration |
| Testing | pytest | Standard Python testing |
| Logging | structlog | Structured JSON logging |

---

## 9. Error Handling

### Retry Strategy

```python
@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 60.0  # seconds
    exponential: bool = True
    retryable_errors: list = field(default_factory=lambda: [
        "rate_limit",
        "quota_exceeded",
        "timeout",
        "connection_error"
    ])
```

### Error Recovery

| Error Type | Action |
|------------|--------|
| API rate limit | Exponential backoff (60s, 120s, 180s) |
| API quota exceeded | Switch to fallback provider |
| FFmpeg failure | Log error, mark stage failed, allow retry |
| Disk full | Stop immediately, alert user |
| Invalid video | Fail fast with clear message |

### Logging

All operations logged to `jobs/<job_id>/logs/pipeline.log`:

```json
{"timestamp": "2026-01-29T10:32:00Z", "level": "INFO", "stage": "ingest", "message": "Extracting audio", "video": "raw.mp4"}
{"timestamp": "2026-01-29T10:32:15Z", "level": "INFO", "stage": "ingest", "message": "Audio extracted", "duration_ms": 15000, "output": "audio.wav"}
{"timestamp": "2026-01-29T10:40:00Z", "level": "ERROR", "stage": "analyze", "message": "API rate limit", "provider": "gemini", "retry_in": 60}
```

---

## 10. Implementation Phases

### Phase 1: Foundation (Fix & Restructure)
- [ ] Rotate API key, add .env to .gitignore
- [ ] Create new project structure (src/, ui/, tests/)
- [ ] Implement Job manager with state file
- [ ] Port existing code to new structure
- [ ] Add proper error handling (no bare except)
- [ ] Replace os.system with subprocess
- [ ] Add basic logging

### Phase 2: Pipeline Stages
- [ ] Implement IngestStage (extract audio, probe, proxy)
- [ ] Implement TranscribeStage (Whisper + filler detection)
- [ ] Implement AnalyzeStage (Gemini with provider abstraction)
- [ ] Implement RenderStage (FFmpeg with platform specs)
- [ ] CLI to run pipeline: `podcast-pipeline run input.mp4`

### Phase 3: Review UI
- [ ] Redesign Streamlit UI with new sections
- [ ] Video preview with cut markers
- [ ] Cuts review (filler auto-approve, content review)
- [ ] Thumbnail selection
- [ ] Marketing copy editing
- [ ] Persist review state

### Phase 4: Research Feature
- [ ] YouTube Data API integration
- [ ] Spotify API integration
- [ ] Trend analysis and pattern extraction
- [ ] Surface insights in Review UI

### Phase 5: Platform Exports
- [ ] YouTube export (video + thumbnail)
- [ ] Spotify export (MP3 + metadata)
- [ ] Apple Podcasts export (M4A + chapters)
- [ ] TikTok/Reels vertical clips
- [ ] LinkedIn/Twitter clips
- [ ] Transcript formats (TXT, SRT, VTT)

### Phase 6: Polish
- [ ] Audio enhancement (noise reduction)
- [ ] Video enhancement (color correction)
- [ ] Model switching (add Kimi, OpenAI)
- [ ] Tests for critical functions
- [ ] README with setup instructions

---

## 11. Open Questions

1. **Multi-track audio:** If you get a mixer, how should we handle separate tracks per person?
2. **Face tracking for vertical crops:** Worth adding for TikTok clips?
3. **Upload automation:** Auto-upload to platforms, or just prepare the files?
4. **Episode numbering:** Should the tool track episode numbers across jobs?
5. **Templates:** Pre-made marketing templates per episode type?

---

## 12. Success Criteria

The tool is "done" when you can:

1. Drop a raw podcast video in a folder
2. Run one command
3. Wait for processing (see progress)
4. Open web UI, review cuts in 5-10 minutes
5. Click render
6. Get all files ready for upload to YouTube, Spotify, Apple, TikTok
7. Copy/paste the generated marketing copy

No manual FFmpeg commands. No editing software. No copywriting.
