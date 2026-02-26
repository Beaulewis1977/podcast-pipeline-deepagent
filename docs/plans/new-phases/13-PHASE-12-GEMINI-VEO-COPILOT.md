# Phase 12: Gemini Co-Pilot & Veo 3.1 Studio

## 1. Goal
Integrate an intelligent AI assistant capable of understanding context, acting upon natural-language video direction, and generating stylistically matching B-roll and extended scenes via Veo 3.1. It analyzes the full transcript, multiple camera inputs, and user commands to produce strict, rendering-ready JSON edit instructions.

**Depends on:** Phase 11

## 2. Scope / Requirements

### 2.1 The Gemini Auto-Edit API Wrapper
- Extend `base_provider.py` or introduce a dedicated `AgenticDirector` subclass leveraging the `google-genai` SDK.
- Prompting instructions will be: "You are a professional video director. Read the transcript tokens, timestamps, and B-roll inventory. Output a `camera_plan.json` optimizing engagement and pacing."
- The agent chooses between wide, close-up, and B-roll views autonomously if set to "Full Auto."

### 2.2 Veo 3.1 Video Generation & Extension
- Support the Veo 3.1 API (via Google API/Vertex endpoints).
- Implement reference-image capture logic: the backend extracts sample frames of hosts (clothing, background) from `primary_video`.
- Send these reference images plus a Gemini-generated textual prompt into the Veo 3.1 generator to produce "Ingredients to Video" and "Video Extension" outputs.
- Ensures the generated `.mp4` files seamlessly integrate onto the Master Timeline with native audio generation settings tuned.

### 2.3 Co-Pilot Memory & Edit Revision
- Expose a conversational/chat module enabling continuous prompting (`"Switch to guest cam during the Q&A"`, `"Extend the outro by 20 seconds using our podcast background"`).
- Persist the history of textual requests within the `JobManifest` so the system can undo/redo changes, maintaining edit versions securely.

## 3. Tech Stack Requirements
- Google GenAI SDK (`google-genai>=1.0.0`)
- Veo 3.1 endpoint configurations (Vertex AI or Gemini API standard wrapper)
- Re-architected `prompt_schema.json` containing the "Professional Editor/Director" guidelines and constraints.
- Real-time fallback logic ensuring generated content adheres strictly to branding kits (colors/fonts) supplied in Phase 9.

## 4. Success Criteria
1. Gemini Vision analyzes primary and B-roll footage to output an intelligent JSON structure with valid FFmpeg timestamps.
2. Direct conversational commands successfully manipulate the `edit_plan.json` / `camera_plan.json`.
3. Veo 3.1 successfully generates a 5–15 second test B-roll clip matching the lighting/set of reference images automatically captured from the primary video.
4. "Full Auto" successfully produces a finalized podcast from raw multi-cam inputs + uploaded B-rolls, handling everything out of the box.
