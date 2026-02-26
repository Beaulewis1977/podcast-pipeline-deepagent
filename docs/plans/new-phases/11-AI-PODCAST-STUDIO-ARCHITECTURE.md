# AI-First Podcast Studio: Master Architecture & EPCs

## 1. Executive Summary
The Podcast Pipeline evolves from a "cli-cutter" into the ultimate **all-in-one AI podcast studio**. By orchestrating raw multi-cam footage, B-roll, and audio into an intelligently directed, style-matched, fully branded, platform-ready workflow, we surpass industry standards (Descript, Riverside, OpusClip) through deep **Veo 3.1 & Gemini 3.1 Pro** integration and local **Practical-RIFE** smoothing.

## 2. Engineering Product Contracts (EPCs)

### 2.1 The Hybrid Application Model
**Constraint:** The application must run simultaneously as a web version (Streamlit/FastAPI) and a desktop version (Tauri/React) while sharing the same backend queue and state.
- **State Sync Layer:** The Python FastAPI backend operates as the single source of truth using a WebSocket broker or Polling (via TanStack Query/Zustand) to synchronize the review state, job queue, and timeline edits across Web and Desktop instances.
- **Compute Locality:** The Tauri Desktop app delegates heavy ML tasks (RIFE, FFmpeg rendering) to the local GPU, while the Steamlit Web app can connect to cloud-configured runners or local sidecars.

### 2.2 Transcript-First Editing Protocol
**Constraint:** The transcript is the primary editing medium. Media edits strictly follow transcript modifications.
- **Model:** A unified JSON edit plan is derived instantly from any transcript change (adds, deletes, rearrangements).
- **Media Binding:** The FFmpeg media toolkit translates text edits into a `filter_complex` pipeline linking audio trims, video cuts, and Practical-RIFE bridge insertions seamlessly, operating in near real-time.

### 2.3 The Gemini Co-Pilot Engine
**Constraint:** The user controls the suite via natural language (voice/text) alongside standard UI gestures.
- **Agentic Loop:** Gemini 3.1 Pro + Vision acts as an autonomous Director. It reads the transcript, analyzes video frames, understands B-roll context, and outputs a strict JSON configuration for FFmpeg.
- **Veo 3.1 Pipeline:** Missing B-roll or required scene extensions are generated via Google Veo 3.1 API. Reference images (extracted from the raw footage) ensure character, lighting, and set consistency.

### 2.4 Multi-Cam & B-Roll Unification
**Constraint:** The system handles `n` video angles and `m` B-roll clips seamlessly.
- **Sync Mechanism:** Expanding Phase 9 audio sync, all raw assets are bounded and aligned on a master virtual timeline relative to a primary synchronized timestamp.
- **Scene Switching:** FFmpeg `select` and `overlay` filters handle dynamic switching based on the Gemini Co-Pilot's JSON instructions.

---

## 3. Technology Stack & Additions
- **Backend & Orchestration:** Python 3.11+, FastAPI (WebSocket support added), FastMCP
- **Desktop Client:** Tauri v2, Rust, Zustand v5, TanStack Query v5, TailwindCSS v4, shadcn/ui
- **Web Client:** Streamlit, wavesurfer.js
- **Media Engine:** FFmpeg Toolkit, `scipy.signal.correlate` (audio sync), Practical-RIFE (frame interpolation)
- **AI Core:** `google-genai` SDK (Gemini 3.1 Pro + Vision model family, Veo 3.1 generation wrapper)
- **External Integration:** Playwright (headless browser for distribution uploads), OAuth2 client libraries

---

## 4. Phase Rollout Strategy
The implementation is broken down into four distinct, non-destructive phases added to the existing Roadmap:

- **Phase 11: Multi-Cam Core & B-Roll Engine** (Ingestion, Syncing, RIFE bridges, Multi-angle switching)
- **Phase 12: Gemini Co-Pilot & Veo 3.1 Studio** (Agentic JSON edits, Veo generation, smart B-roll context)
- **Phase 13: Hybrid UI/UX & Real-Time Editor** (Transcript-first UI, Voice chat floating panel, State sync)
- **Phase 14: Automated Publishing & MCP Expansion** (`upload_to_platform` logic, `smart_crop_subject`, platform brand kits)

*Detailed plans for each phase are available in the `new-phases` directory.*
