# AI-First Podcast Studio — Master Architecture & EPC Plan

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Research & Planning Only (No Implementation)
**Supersedes:** `11-AI-PODCAST-STUDIO-ARCHITECTURE.md`, Phases 12–15 skeleton docs

---

## 1. Executive Summary

This document defines the integrated architecture for transforming the existing podcast pipeline (Phases 1–10) into a full **AI-First Podcast Studio** — a hybrid web/desktop application with multi-cam editing, AI-generated B-roll, Gemini Co-Pilot voice/chat interface, Veo 3.1 video generation, and automated multi-platform publishing.

**What exists today (Phases 1–10, 67 plans executed):**
- Core pipeline: Ingest → Transcribe → Analyze → Review → Render
- Streamlit web UI (dashboard, review, editing, Brand Studio)
- Tauri v2 desktop app (4 views: Ingestion, Transcript, AudioSync, Branding)
- FastAPI backend with auth, CORS, health, supervisor
- FFmpeg toolkit (14 typed MCP tools)
- AI providers: Gemini 2.5 Flash, Kimi K2.5, Claude Sonnet 4
- Multi-track audio sync via cross-correlation (`sync.py`)
- RIFE frame interpolation bridge
- Branding profiles with per-platform overrides
- Platform exports: YouTube, Spotify, Apple, TikTok, Instagram, LinkedIn, Twitter, Facebook, YouTube Ultra (HEVC 10-bit 4K)

**What this plan adds:**
- Multi-cam video support (upload N camera angles, auto-sync, AI-driven switching)
- B-roll engine (upload clips + AI-generated via Veo 3.1 with style matching)
- Gemini Co-Pilot (chat + voice interface for natural-language video direction)
- Agentic "Auto-Edit" mode (Gemini analyzes transcript + video → produces complete edit)
- Transcript-first editing UI (click words → cut/keep, visual timeline sync)
- Real-time state sync (WebSocket hub connecting Streamlit + Tauri + future clients)
- Saved branding kits with auto-application per platform
- AI-generated titles, descriptions, viral thumbnails
- Automated publishing via `upload_to_platform` MCP tool
- Platform-specific output variants (YouTube Shorts, Reels, TikTok, audio-only)

---

## 2. Current State Audit

### 2.1 Completed Infrastructure (Leverage Points)

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| FFmpeg toolkit (14 ops) | `utils/ffmpeg_toolkit.py` | **Extend** — add `multi_cam_switch`, `overlay_video_timed` |
| Audio sync estimator | `utils/sync.py` | **Extend** — generalize from 2-track to N-track alignment |
| RIFE bridge | `utils/rife_bridge.py` | **Reuse as-is** — apply to all transitions including cam switches |
| Branding profiles | `models/branding.py` | **Extend** — add saved kit persistence + auto-apply logic |
| Caption engine | `utils/captions.py` | **Reuse as-is** — already handles 16:9, 9:16, 1:1 |
| Render stage | `stages/render.py` | **Extend** — add multi-cam + B-roll filter_complex paths |
| FastAPI service | `service/app.py` | **Extend** — add WebSocket hub + Co-Pilot endpoints |
| Gemini provider | `providers/gemini.py` | **Extend** — add Vision analysis + Veo 3.1 generation calls |
| Audio mix (stingers) | `utils/audio_mix.py` | **Reuse as-is** — stinger ducking works with multi-cam audio |
| Tauri desktop app | `desktop/` | **Extend** — add multi-cam view, Co-Pilot panel, transcript editor |
| Streamlit UI | `ui/` | **Extend** — add transcript-first editor, Co-Pilot sidebar |
| Config system | `config.yaml` | **Extend** — add multi_cam + copilot + veo sections |
| MCP dev server | `mcp/ffmpeg_server.py` | **Extend** — register new tools |

### 2.2 Gaps Requiring New Components

| Gap | New Component | Rationale |
|-----|---------------|-----------|
| Multi-cam video switching | `utils/multicam.py` | FFmpeg filter_complex concat/trim for N-source switching |
| B-roll overlay engine | `utils/broll.py` | Timed overlay with setpts delay + enable expressions |
| Veo 3.1 video generation | `providers/veo.py` | `google.genai` SDK `generate_videos` endpoint |
| Gemini Co-Pilot | `copilot/engine.py` | Structured edit instruction generation from NL commands |
| WebSocket state sync | `service/ws_hub.py` | Real-time bidirectional state between all clients |
| Platform uploaders | `uploaders/` | YouTube, Spotify RSS, TikTok, Playwright fallback |
| Transcript-first editor | UI components | Click-to-edit word-level transcript with visual timeline |
| Voice command interface | Browser + Tauri | Web Speech API → Co-Pilot text pipeline |

### 2.3 Redundancy Analysis (Gemini Skeleton Docs)

The existing docs in `docs/plans/new-phases/` (files 12–15) are **high-level outlines** that this document supersedes. Specific redundancies:

| Existing Doc | Issue | Resolution |
|-------------|-------|------------|
| `12-PHASE-11-MULTI-CAM-BROLL.md` | Describes sync requirements but ignores existing `sync.py` | **Superseded** — this plan extends sync.py |
| `13-PHASE-12-GEMINI-VEO-COPILOT.md` | References "Gemini 3.1 Pro + Vision" without API specifics | **Superseded** — this plan uses verified Veo 3.1 API |
| `14-PHASE-13-HYBRID-UI-UX.md` | Ignores existing Tauri views + Streamlit pages from Phase 10 | **Superseded** — this plan extends existing UI |
| `15-PHASE-14-MCP-DISTRIBUTION.md` | Partially overlaps with `11-research.md` upload_to_platform | **Superseded** — this plan references verified research |
| `11-AI-PODCAST-STUDIO-ARCHITECTURE.md` | Generic rollout without implementation detail | **Superseded** by this document |

**Features to NOT implement (over-engineering risk):**
- Real-time collaborative editing (multiple users editing same transcript simultaneously) — defer to v2
- Custom AI model training/fine-tuning — use Gemini/Veo as-is
- Live streaming integration — out of scope for production pipeline
- Mobile app — Tauri desktop + Streamlit web covers all use cases

---

## 3. Integrated System Architecture

### 3.1 High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI-First Podcast Studio                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│  │ Camera 1 │  │ Camera 2 │  │ Camera N │  ← Multi-Cam Input  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                     │
│       │              │              │                           │
│       └──────────────┼──────────────┘                           │
│                      ▼                                          │
│  ┌─────────────────────────────────────┐                       │
│  │     INGEST + AUTO-SYNC ENGINE       │                       │
│  │  • N-track cross-correlation        │                       │
│  │  • Clap detection alignment         │                       │
│  │  • Timecode extraction (if present) │                       │
│  └──────────────┬──────────────────────┘                       │
│                 ▼                                               │
│  ┌─────────────────────────────────────┐                       │
│  │     TRANSCRIBE (faster-whisper)     │                       │
│  │  • Word-level alignment             │                       │
│  │  • Speaker diarization              │                       │
│  └──────────────┬──────────────────────┘                       │
│                 ▼                                               │
│  ┌─────────────────────────────────────┐                       │
│  │     ANALYZE (Gemini Vision)         │  ┌──────────────────┐ │
│  │  • Transcript + video analysis      │  │  GEMINI CO-PILOT │ │
│  │  • Multi-cam switch points          │←→│  • Chat / Voice  │ │
│  │  • B-roll insertion suggestions     │  │  • Edit commands  │ │
│  │  • Viral clip detection             │  │  • Auto-Edit mode│ │
│  └──────────────┬──────────────────────┘  └──────────────────┘ │
│                 ▼                                               │
│  ┌─────────────────────────────────────┐                       │
│  │     REVIEW (Transcript-First UI)    │                       │
│  │  • Click-to-cut word editor         │                       │
│  │  • Visual multi-cam timeline        │                       │
│  │  • B-roll placement preview         │                       │
│  │  • Branding kit selection           │                       │
│  └──────────────┬──────────────────────┘                       │
│                 ▼                                               │
│  ┌─────────────────────────────────────┐                       │
│  │     RENDER (Extended)               │  ┌──────────────────┐ │
│  │  • Multi-cam filter_complex         │  │   VEO 3.1        │ │
│  │  • B-roll overlay + timed inserts   │←→│  • AI B-roll gen │ │
│  │  • RIFE smooth transitions          │  │  • Style matching│ │
│  │  • Per-platform branding auto-apply │  │  • Video extend  │ │
│  │  • Caption burn-in                  │  └──────────────────┘ │
│  └──────────────┬──────────────────────┘                       │
│                 ▼                                               │
│  ┌─────────────────────────────────────┐                       │
│  │     DISTRIBUTE                      │                       │
│  │  • YouTube (resumable upload API)   │                       │
│  │  • Spotify (RSS feed generation)    │                       │
│  │  • TikTok (Content Posting API)     │                       │
│  │  • Instagram (Playwright fallback)  │                       │
│  └─────────────────────────────────────┘                       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              HYBRID UI LAYER                                ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────────┐ ││
│  │  │  Streamlit   │  │   Tauri v2  │  │  FastAPI + WS Hub  │ ││
│  │  │  (Web UI)    │←→│  (Desktop)  │←→│  (Backend/Sync)    │ ││
│  │  └─────────────┘  └─────────────┘  └────────────────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 WebSocket State Sync Architecture

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Streamlit   │     │   Tauri v2    │     │  Future CLI   │
│   Client      │     │   Client      │     │   Client      │
└──────┬────────┘     └──────┬────────┘     └──────┬────────┘
       │                     │                      │
       │    WebSocket        │    WebSocket          │
       └─────────┬───────────┴──────────────────────┘
                 │
       ┌─────────▼─────────┐
       │   FastAPI WS Hub  │
       │                   │
       │  • Room per job   │
       │  • Broadcast edits│
       │  • Conflict merge │
       │  • Event log      │
       └───────────────────┘
```

**Sync Protocol:**
- Each client connects to `ws://{host}:{port}/ws/jobs/{job_id}`
- Edit operations are JSON messages: `{type: "edit", payload: {action, target, ...}}`
- Hub broadcasts to all other connected clients
- Last-write-wins for non-conflicting edits; timestamp-based merge for conflicts
- Streamlit integration via `streamlit-ws-connection` custom component or polling fallback

---

## 4. Technology Stack

### 4.1 Current Stack (Confirmed Working)

| Layer | Technology | Version | Status |
|-------|-----------|---------|--------|
| Runtime | Python | ≥3.11 | ✅ Stable |
| Transcription | faster-whisper | ≥1.1.0 | ✅ Stable |
| AI Analysis | google-genai | ≥1.0.0 | ✅ Stable |
| AI Fallback | anthropic | ≥0.80.0 | ✅ Stable |
| Media Engine | FFmpeg (system) | 6.x/7.x | ✅ Stable |
| Backend | FastAPI + uvicorn | ≥0.128.2 | ✅ Stable |
| Web UI | Streamlit | ≥1.42.0 | ✅ Stable |
| Desktop | Tauri v2 + React | v2.x | ✅ Stable |
| Frame Interp | Practical-RIFE | 4.25 | ✅ Stable |
| Face Detection | OpenCV YuNet | 4.13.0 | ✅ Installed (gpu extra) |
| GPU | CUDA 12.8 / torch 2.10 | Blackwell | ✅ Stable |

### 4.2 New Dependencies Required

| Package | Version | Purpose | Install Group |
|---------|---------|---------|---------------|
| `google-genai` | ≥1.0.0 | Veo 3.1 `generate_videos` API | core (already installed) |
| `google-api-python-client` | ≥2.0 | YouTube Data API v3 upload | `publish` extra |
| `google-auth-oauthlib` | ≥1.0 | OAuth2 browser flow for YouTube | `publish` extra |
| `feedgen` | ≥0.9.0 | RSS feed generation for Spotify | `publish` extra |
| `playwright` | ≥1.49 | Browser automation fallback (Instagram) | `publish` extra |
| `websockets` | ≥14.0 | WebSocket support for FastAPI hub | core |

**Key insight:** Veo 3.1 uses the same `google-genai` SDK already in core deps. No new package needed for video generation — only new API calls (`client.models.generate_videos`).

### 4.3 Veo 3.1 API Interface (Verified Feb 2026)

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Text-to-video generation
operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt="Professional podcast B-roll: close-up of hands gesturing...",
    config=types.GenerateVideosConfig(
        number_of_videos=1,
        # Style matching via reference images (up to 3)
        reference_images=[
            types.Image(image_bytes=frame_bytes),  # extracted from main video
        ],
    ),
)

# Poll for completion
while not operation.done:
    time.sleep(10)
    operation = client.operations.get(operation)

# Download generated video
for video in operation.result.generated_videos:
    client.files.download(file=video.video)
```

**Capabilities:** 8s clips at up to 4K, native audio, reference-image style matching, video extension (up to 141s input → 7s extensions, repeatable 20x at 720p), portrait 9:16 mode.

**Pricing:** Pay-per-use via Gemini API (Vertex AI pricing); higher resolutions increase cost.

---

## 5. Epic Breakdown (EPCs)

### EPC-1: Multi-Cam Core Engine

**Goal:** Accept N camera angles, auto-sync all sources, enable manual + AI-driven camera switching.

**New files:**
- `src/podcast_pipeline/utils/multicam.py` — N-track sync + switch-point generation
- Extensions to `utils/sync.py` — generalize `estimate_offset()` for N sources
- Extensions to `stages/render.py` — multi-cam filter_complex path

**Implementation approach:**
1. Extend `sync.py` to accept `list[Path]` and return `list[SyncResult]` (all offsets relative to reference track)
2. Create `multicam.py` with `CamSwitchPlan` model: list of `(start_s, end_s, cam_index)` segments
3. Build FFmpeg filter_complex using `trim`+`setpts`+`concat` for sequential camera switching:
   ```
   [0:v]trim=0:5,setpts=PTS-STARTPTS[v0];
   [1:v]trim=5:12,setpts=PTS-STARTPTS[v1];
   [0:v]trim=12:20,setpts=PTS-STARTPTS[v2];
   [v0][v1][v2]concat=n=3:v=1:a=0[vout]
   ```
4. Audio always from reference (primary) track; secondary cam audio discarded unless mixing requested

**Success criteria:**
- 2-cam podcast syncs within 50ms accuracy
- N-cam (N≤4) switching renders without filter_complex errors
- RIFE transitions applied at all switch points

### EPC-2: B-Roll Engine

**Goal:** Accept uploaded B-roll clips + generate AI B-roll via Veo 3.1, insert at intelligent points.

**New files:**
- `src/podcast_pipeline/utils/broll.py` — B-roll inventory + placement logic
- `src/podcast_pipeline/providers/veo.py` — Veo 3.1 video generation wrapper

**Implementation approach:**
1. `broll.py` manages B-roll inventory: uploaded clips indexed by topic/keyword
2. Gemini Vision analyzes transcript + video → suggests insertion points with topic tags
3. Matching: uploaded B-roll matched to suggestions by keyword similarity
4. Gaps: where no uploaded B-roll matches, Veo 3.1 generates clips using reference frames for style matching
5. FFmpeg overlay: uses `overlay_video` pattern from `11-research.md` (setpts delay + enable expression)

**Success criteria:**
- Uploaded B-roll inserts at correct timestamps with smooth transitions
- Veo 3.1 generated clips visually match main video style (reference-image confirmed working)
- B-roll overlay preserves primary audio track

### EPC-3: Gemini Co-Pilot

**Goal:** Natural language chat + voice interface for directing video edits.

**New files:**
- `src/podcast_pipeline/copilot/engine.py` — NL command → structured edit instruction
- `src/podcast_pipeline/copilot/prompts.py` — system prompts + output schemas
- `src/podcast_pipeline/service/routes/copilot.py` — REST + WebSocket endpoints

**Implementation approach:**
1. Co-Pilot engine wraps Gemini with specialized system prompt that understands:
   - Current transcript + word timings
   - Available camera angles
   - B-roll inventory
   - Current edit plan state
2. NL commands like "Switch to camera 2 when Sarah starts talking" → JSON edit instruction:
   ```json
   {"action": "cam_switch", "trigger": "speaker_change", "speaker": "Sarah", "cam_index": 2}
   ```
3. "Auto-Edit" mode: Gemini receives full transcript + metadata → generates complete edit plan
4. Voice input: Web Speech API (`SpeechRecognition`) in browser → text → Co-Pilot endpoint
5. Streaming responses via WebSocket for real-time feedback

**Success criteria:**
- 5 core command types: cam_switch, insert_broll, cut_segment, keep_segment, apply_branding
- Auto-Edit produces coherent multi-cam edit plan from transcript
- Voice commands work in Chrome/Edge (Tauri WebView is Chromium-based)

### EPC-4: Transcript-First Editor UI

**Goal:** Word-level visual editor where clicking words controls the edit plan.

**Extensions to:**
- `desktop/src/views/TranscriptView.tsx` (Tauri)
- `src/podcast_pipeline/ui/` (Streamlit)

**Implementation approach:**
1. Each word rendered as clickable span with timing data from `word_alignment.json`
2. Click = toggle cut/keep; drag = select range
3. Filler words highlighted (existing filler detection data)
4. Speaker labels from diarization
5. Timeline bar below transcript syncs scroll position with playback
6. Multi-cam lane shows which camera is active per segment
7. B-roll lane shows overlay placement

### EPC-5: Automated Publishing

**Goal:** One-click publish to YouTube, Spotify, TikTok, Instagram with per-platform branding.

**New files:**
- `src/podcast_pipeline/uploaders/base.py` — `PlatformUploader` protocol
- `src/podcast_pipeline/uploaders/youtube.py` — YouTube Data API v3
- `src/podcast_pipeline/uploaders/spotify_rss.py` — RSS feed generation
- `src/podcast_pipeline/uploaders/tiktok.py` — TikTok Content Posting API
- `src/podcast_pipeline/uploaders/playwright_base.py` — browser automation fallback

**Implementation:** Already fully researched in `docs/plans/11-research.md`. Code examples verified.

### EPC-6: Real-Time State Sync

**Goal:** Edits made in Streamlit appear instantly in Tauri and vice versa.

**New files:**
- `src/podcast_pipeline/service/ws_hub.py` — WebSocket broadcast hub
- `desktop/src/hooks/useWebSocket.ts` — Tauri WebSocket client

**Implementation approach:**
1. FastAPI WebSocket endpoint at `/ws/jobs/{job_id}`
2. JSON message protocol: `{type, payload, timestamp, client_id}`
3. Hub maintains room per job_id, broadcasts to all connected clients
4. Streamlit: custom component with JS WebSocket or polling fallback (Streamlit's architecture makes true WebSocket integration complex)
5. Tauri: native WebSocket in React via `useWebSocket` hook

---

## 6. Phased Implementation Strategy

### Phase 11: Multi-Cam Core & B-Roll Engine (EPC-1 + EPC-2)
**Prerequisites:** Phase 10 complete
**Estimated plans:** 8–10
**Key deliverables:**
- N-track auto-sync extension
- Multi-cam filter_complex switching
- B-roll upload + inventory management
- B-roll overlay insertion
- RIFE transitions at all switch/insert points

### Phase 12: Gemini Co-Pilot & Veo 3.1 Studio (EPC-3 + partial EPC-2)
**Prerequisites:** Phase 11 complete (multi-cam + B-roll infrastructure)
**Estimated plans:** 6–8
**Key deliverables:**
- Co-Pilot chat engine with structured output
- Veo 3.1 integration for AI-generated B-roll
- Auto-Edit mode
- Voice command pipeline (Web Speech API → Co-Pilot)

### Phase 13: Hybrid UI/UX & Transcript Editor (EPC-4 + EPC-6)
**Prerequisites:** Phase 11 complete (data models for multi-cam/B-roll exist)
**Estimated plans:** 6–8
**Key deliverables:**
- Transcript-first editor (Streamlit + Tauri)
- Multi-cam timeline visualization
- B-roll placement preview
- WebSocket state sync hub
- Co-Pilot floating panel UI

### Phase 14: Automated Publishing & Distribution (EPC-5)
**Prerequisites:** Phase 11 render extensions complete
**Estimated plans:** 4–6
**Key deliverables:**
- YouTube OAuth2 + resumable upload
- Spotify RSS feed generation
- TikTok Content Posting API
- Playwright fallback for Instagram
- Saved branding kit auto-application per platform

---

## 7. MCP Tool Expansion

### Current Tools (14) — No Changes Needed
All 14 existing FFmpeg toolkit tools remain as-is.

### New Tools Required

| Tool | Module | Type | Priority |
|------|--------|------|----------|
| `multi_cam_sync` | `ffmpeg_toolkit.py` | Filter | Phase 11 |
| `multi_cam_switch` | `ffmpeg_toolkit.py` | Edit | Phase 11 |
| `overlay_video` | `ffmpeg_toolkit.py` | Filter | Phase 11 |
| `smart_crop_subject` | `ffmpeg_toolkit.py` | Filter | Phase 11 |
| `generate_video_veo` | `veo.py` (new) | AI | Phase 12 |
| `copilot_edit` | `copilot/engine.py` (new) | AI | Phase 12 |
| `upload_to_platform` | `uploaders/` (new) | Distribute | Phase 14 |

Total after expansion: **21 tools** (14 existing + 7 new)

---

## 8. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Veo 3.1 API rate limits / pricing | HIGH | MEDIUM | Cache generated clips; batch requests; preview mode uses lower resolution |
| Tauri v2 microphone bugs (Linux/macOS) | MEDIUM | HIGH | Voice commands degrade to text-only; document known platform limitations |
| Streamlit WebSocket limitations | MEDIUM | HIGH | Polling fallback (500ms) when true WS not feasible; Streamlit custom component |
| YouTube daily quota (6 uploads/day free) | MEDIUM | HIGH | Apply for quota increase; implement upload queue with scheduling |
| TikTok unaudited SELF_ONLY restriction | LOW | HIGH | Document limitation; start audit process early; Playwright fallback |
| FFmpeg filter_complex complexity for 4+ cams | MEDIUM | LOW | Limit to 4 concurrent cams; pre-validate filter syntax before render |
| Gemini Co-Pilot hallucinated edit instructions | HIGH | MEDIUM | Schema validation on all Co-Pilot output; reject non-conforming JSON |
| RIFE performance on long multi-cam videos | MEDIUM | MEDIUM | RIFE only at switch points (not whole video); GPU lease serialization |

---

## 9. Branding Kit Architecture

### 9.1 Extended BrandingProfile

The existing `BrandingProfile` model (`models/branding.py`) already supports:
- Logo, intro/outro images, watermark
- Hex colors (primary, secondary, accent)
- Caption style (font, size, colors, position)
- Sound kit (intro/outro/transition stingers)
- Per-platform overrides via `PlatformBrandingOverride`
- Brand voice (sanitized text for LLM prompt injection)

**Extensions needed:**
- `saved_kits: dict[str, BrandingProfile]` — named kit storage (e.g., "YouTube Main", "TikTok Shorts")
- `auto_apply_rules: list[AutoApplyRule]` — rules like "use 'YouTube Main' for all youtube exports"
- `thumbnail_template: Optional[Path]` — Canva-style template for AI thumbnail generation
- `font_files: list[Path]` — custom font files for caption burn-in

### 9.2 Auto-Apply Flow

```
render_for_platform("youtube") →
  resolve kit: decisions.branding_profile_name → config fallback → auto_apply_rules →
  resolved_profile = profile.resolved_for_platform("youtube") →
  apply: logo overlay + caption burn + loudness target + thumbnail compliance
```

This flow already exists in render.py for the basic case. Extension adds the saved-kit lookup layer.

---

## 10. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Extend existing sync.py rather than new sync engine | sync.py is battle-tested for 2-track; N-track is algorithmic extension, not rewrite |
| Veo 3.1 via google-genai (not Vertex AI) | Already have google-genai in core deps; Vertex AI adds auth complexity |
| Web Speech API for voice (not whisper-in-browser) | Zero latency, no model loading, works in Chromium (Tauri+Chrome) |
| WebSocket hub in FastAPI (not separate service) | Single deployment; FastAPI already has WebSocket support |
| Polling fallback for Streamlit sync | Streamlit's execution model makes true WebSocket unreliable |
| Reference-image style matching for Veo B-roll | Verified working in Veo 3.1 API; ensures visual consistency |
| filter_complex concat for cam switching (not xfade) | concat is reliable for N segments; xfade only works for 2 inputs |
| Uploaders as separate module tree (not MCP-only) | MCP tools wrap uploaders; uploaders also callable from render stage |

---

## 11. File Structure (New Components)

```
src/podcast_pipeline/
├── copilot/
│   ├── __init__.py
│   ├── engine.py          # NL → structured edit instruction
│   └── prompts.py         # System prompts + output schemas
├── uploaders/
│   ├── __init__.py
│   ├── base.py            # PlatformUploader protocol
│   ├── youtube.py         # YouTube Data API v3
│   ├── spotify_rss.py     # RSS feed generation
│   ├── tiktok.py          # TikTok Content Posting API
│   └── playwright_base.py # Browser automation fallback
├── providers/
│   └── veo.py             # Veo 3.1 video generation (NEW)
├── utils/
│   ├── multicam.py        # N-track sync + switch plan (NEW)
│   └── broll.py           # B-roll inventory + placement (NEW)
├── service/
│   ├── ws_hub.py          # WebSocket broadcast hub (NEW)
│   └── routes/
│       └── copilot.py     # Co-Pilot REST + WS endpoints (NEW)
desktop/src/
├── views/
│   ├── MultiCamView.tsx   # Multi-cam timeline + switching (NEW)
│   └── CoPilotPanel.tsx   # Floating chat + voice panel (NEW)
├── hooks/
│   └── useWebSocket.ts    # Real-time sync hook (NEW)
```

---

## 12. Success Criteria (Overall)

| Metric | Target |
|--------|--------|
| Multi-cam sync accuracy | ≤50ms offset for 2 cameras, ≤100ms for 4 cameras |
| B-roll insertion | Correct timestamps, smooth RIFE transitions |
| Veo 3.1 style match | Generated clips visually consistent with main footage |
| Co-Pilot accuracy | ≥80% of NL commands produce valid edit instructions |
| Auto-Edit quality | Produces edit plan equivalent to 30min manual editing |
| Publishing success | YouTube + TikTok upload succeeds on first attempt |
| State sync latency | ≤500ms edit propagation between clients |
| All existing tests | No regressions (1041+ tests continue to pass) |

---

*This document is a research and planning artifact. No implementation changes should be made based on this document without explicit user approval and per-phase plan creation.*
