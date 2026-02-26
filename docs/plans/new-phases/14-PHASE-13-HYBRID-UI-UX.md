# Phase 13: Hybrid UI/UX & Real-Time Editor

## 1. Goal
Transition the user experience into a fully interactive "Transcript-First Editor" backed by the Gemini Co-Pilot. Establish seamless state synchronization between the Streamlit Web app and the Tauri Desktop app, giving users a unified and dynamic podcasting interface.

**Depends on:** Phase 12

## 2. Scope / Requirements

### 2.1 Transcript-First Editor UI
- Overhaul the current Streamlit Transcript view and Tauri's React `Transcript Timeline` component.
- Display visual markers representing active camera angles (e.g., [Guest Cam], [Wide Shot]) directly inline with the text.
- Allow users to highlight, type over, or delete text — triggering a real-time update to the underlying `edit_plan.json`.
- Provide undo/redo functionality mapping directly to the tracked history on the Python Backend.
- Add "B-roll drop zones" indicating where clips are overlaid within the text.

### 2.2 Gemini Co-Pilot Floating Panel
- Add a floating UI panel in Tauri (using shadcn/ui slide-overs or popovers) and Streamlit (custom components/sidebar) for the Gemini chat interaction.
- Incorporate a microphone toggle utilizing the Web Speech API (or native Tauri audio capture) for speech-to-text prompt transcription: `"Make a cut here and zoom in."`
- Display context-aware responses and immediate visual plan updates in the application.

### 2.3 Hybrid State Synchronization
- Upgrade the FastAPI backend with a WebSocket broker (`starlette.websockets`).
- Implement real-time publish-subscribe updates from the backend to both React (Tauri) and Streamlit clients.
- If a transcript word is trimmed on Streamlit, the Tauri instance updates instantly (and vice-versa), preserving session state correctly.

## 3. Tech Stack Requirements
- WebSockets (`fastapi.WebSocket`) natively attached to the backend Service.
- UI Libraries: React `wavesurfer.js`, `Zustand` real-time store adapters.
- Streamlit Custom Component (`streamlit-webrtc` or standard WebSockets integration) for live updates.
- Tauri Native APIs for microphone and GPU-rendered accelerated previews.

## 4. Success Criteria
1. Web UI and Desktop UI modifying the same job ID reflect updates to the Transcript simultaneously.
2. Deleting a sentence in the Transcript Editor visually creates a "Cut" marker and updates the `edit_plan.json`.
3. Speech-to-text correctly transcribes a voice command within the floating Co-Pilot panel, which edits the timeline appropriately.
4. Preview features (toggling RIFE off/on, multi-cam angles) are extremely responsive and handled via the backend/sidecar smoothly.
