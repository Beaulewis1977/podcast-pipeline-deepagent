# Podcast Pipeline

## What This Is

An AI-powered production pipeline for a multi-host education podcast. It takes raw video recordings with multi-track audio and produces publication-ready content for YouTube, Spotify, Apple Podcasts, TikTok, Instagram Reels, LinkedIn, Twitter/X, and Facebook. AI handles transcription, cut suggestions, and marketing copy; humans make final decisions in a Streamlit review UI.

## Core Value

Turn a raw podcast recording into multi-platform content without touching editing software or writing marketing copy manually.

## Current Focus

**Phase 1: Wiring + Stability** — connect existing stages end-to-end, apply real edits in render, and make multi-track transcription the default.

## Requirements (Active)

- End-to-end pipeline outputs reflect approved edits (no stubs)
- Multi-track transcription with speaker-labeled merged transcript
- Edit plan saved after review and applied in render
- Short-form clip exports generated from approved ranges
- Streamlit UI drives the pipeline without duplicating job IDs
- Research + viral signals integrated into analysis and UI

## Out of Scope (v1)

- Full AI thumbnail generation (frame extraction only)
- Auto-upload to platforms
- Multi-camera switching
- Live recording

## Context

**Podcast:**
- 3 hosts (education-focused)
- Single camera + multi-track audio
- Semi-scripted discussion format

**Target Platforms:**
- YouTube (full episodes)
- Spotify / Apple Podcasts (audio)
- TikTok / Instagram Reels / YouTube Shorts (vertical clips)
- LinkedIn / Twitter/X / Facebook (clips)

**Design Philosophy:**
- AI suggests, humans decide
- Research-informed recommendations
- Pipeline is the single source of truth
- Resumable and local-first

## Technical Environment

- Python 3.11+
- FFmpeg/FFprobe for media processing
- faster-whisper for transcription
- Gemini (primary) + Kimi (fallback) for analysis
- Streamlit for review UI (short term)
- Tauri v2 + Python backend service (medium term)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Streamlit-first UI | Fastest path to a working product | Approved |
| Desktop follow-up (Rust + Tauri v2) | Stable distribution without heavy Electron footprint | Planned |
| Pipeline owns all logic | Prevents UI drift and enables reuse across UIs | Approved |
| Multi-track default | 3-host setup requires per-track control | In progress |

---
*Last updated: 2026-02-04*
