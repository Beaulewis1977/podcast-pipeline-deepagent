# Features Research: Podcast Production Pipeline

**Researched:** 2026-02-04
**Sources:** `codex/APP_RESEARCH_REPORT.md`, `src/podcast_pipeline/*`, `.planning/REQUIREMENTS.md`
**Confidence:** MEDIUM (internal sources only; no external verification)

## Table Stakes (Must-Have)

### Ingest + Transcription
- Ingest video, extract audio, create proxy video
- Word-level transcript (TXT, SRT, VTT)
- Filler word detection with reviewable cut list
- Multi-track transcription with merged, speaker-labeled transcript

### Analysis + Review
- AI suggestions for content cuts, clips, thumbnails, marketing copy
- Human-in-the-loop review with persisted decisions

### Render + Export
- Platform-specific exports (YouTube, Spotify, Apple, TikTok, Instagram, LinkedIn, Twitter/X, Facebook)
- Loudness normalization per platform
- Marketing copy document output

## Differentiators

### Research-Informed Recommendations
- Use YouTube research signals to improve titles, thumbnails, and clip ranking
- Viral scoring re-ranking based on engagement signals

### Workflow Reliability
- Resumable pipeline with job state persisted after every stage
- Clear artifact outputs for review and reprocessing

### Multi-Track Control
- Per-track transcription and combined timeline
- Speaker labels surfaced in transcript and review

## Anti-Features (Explicitly Avoid)

- Real-time recording or live streaming
- Collaborative editing
- Auto-upload to platforms in v1
- Full AI thumbnail generation in v1

## Priority (Aligned to Roadmap)

### Phase 1: Wiring + Stability (Now)
- End-to-end wiring with real edits applied in render
- Multi-track default transcription
- Edit plan written after review and used by render
- Short-form clip export from approved ranges
- Streamlit job creation consistency

### Phase 2: Research + Viral Integration
- YouTube research integrated into Analyze
- Enhanced viral scoring + keyword extraction
- Cached research outputs

### Phase 3: Desktop Distribution
- Tauri v2 UI with Python backend service
- Packaging + offline support

## Feature Dependencies (High-Level)

```
Ingest → Transcribe → Analyze → Review → Render
                        ↑
                    Research (feeds Analyze/Review)
```

