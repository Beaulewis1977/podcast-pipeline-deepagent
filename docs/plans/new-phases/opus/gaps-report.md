# AI Podcast Studio (Opus) Architecture Gaps Report

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Feedback and Optimization Report
**Scope:** Gaps and architectural risks identified in the core Opus project plans (Phases 11-14).

---

## 1. Asynchronous Workflows: Veo 3.1 Latency and Job Blocking

### The Observation
Phase 12 details the Gemini Co-Pilot and Veo 3.1 B-roll generation capabilities. The Co-Pilot acts as a natural language interface to trigger these AI tools.

### The Problem
Video generation via Veo 3.1 is relatively slow and computationally intensive. If the Co-Pilot triggers a workflow that generates multiple B-roll clips (e.g., 10 localized clips based on the transcript), and the system waits for them to complete synchronously before giving the user feedback, the UI will feel broken, unresponsive, or experience connection timeouts (especially under Streamlit WebSocket limitations or regular HTTP timeouts).

### Proposed Mitigation
- **Asynchronous Task Dispatch:** Mandate that all AI video generation tasks (Veo or heavy image/video operations) are dispatched to the Celery background worker asynchronously.
- **Placeholder Implementation:** The backend should immediately return a "placeholder" clip or a "generating" status to the timeline upon triggering a Veo task.
- **Event-Driven UI Updates:** The WebSocket hub (introduced in Phase 13) must emit a `clip_ready` event once the Celery worker finishes the Veo generation. The frontend (Streamlit or Tauri) should listen to this event and replace the placeholder with the completed asset in real-time.
- **Update EPC:** Ensure that `13-PHASE-12-GEMINI-VEO-COPILOT-opus.md` contains specific architectural directives for Celery task dispatching and placeholder resource states.

---

## 2. UI Architecture: Streamlit Limitations vs. React/Tauri

### The Observation
`14-PHASE-13-HYBRID-UI-UX-opus.md` mentions utilizing Streamlit for the Web UI and React for the Tauri desktop UI, while attempting to bridge gaps utilizing WebSockets.

### The Problem
Streamlit’s top-to-bottom re-execution model is fundamentally hostile to true real-time collaborative editing or complex audio/video timeline scrubbing. Relying on polling as a fallback for the web app (as proposed in the plans) will severely degrade the Web SaaS experience compared to the responsive Desktop app, creating a bifurcated user experience.

### Proposed Mitigation
- **Unified Frontend Strategy:** Since the Desktop app already forces the team to build the Video Timeline and Co-Pilot UI in React (for Tauri), consider dropping Streamlit for the Web App sooner rather than later.
- **React SPA Deployment:** The React dashboard built for Tauri can be deployed directly to Vercel, Render, or any static host as a standard Single Page Application (SPA). This SPA can talk directly to the FastAPI cloud backend.
- **Benefits:** This unification completely bypasses Streamlit limitations, halves the frontend maintenance burden, and ensures feature parity and identical UX across local desktop and cloud web environments.

---

## 3. Security: FFmpeg Shell Injection via Natural Language Prompts

### The Observation
The Gemini Co-Pilot translates natural language instructions into concrete edit instructions, including FFmpeg switch commands and `filter_complex` graphs.

### The Problem
If the LLM hallucinates, or if a malicious user intentionally crafts a prompt designed to execute a shell injection via the Co-Pilot chat interface (e.g., `"trim=start=0:end=10; rm -rf /"`), passing this output blindly to the FFmpeg execution builder is extremely dangerous.

### Proposed Mitigation
- **Absolute Parameterization:** Ensure all generated FFmpeg parameters and `--filter_complex` arguments are strictly validated against a known-safe Domain Specific Language (DSL) or highly restrictive regex before execution.
- **Safe Subprocess Execution:** Never execute FFmpeg using `shell=True` in Python's `subprocess` module. Always pass arguments as a structured list to avoid shell evaluation.
- **Command Whitelisting:** Implement a validator class that parsing the returned LLM commands and only allows a whitelist of FFmpeg filters (`trim`, `concat`, `overlay`, `scale`, etc.).
- **Update EPC:** Add these specific AI-prompt security measures into the core `11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md` and Phase 12 documentation.

---

## 4. Desktop Distribution: FFmpeg License Compliance & Dependencies

### The Observation
Research for Phase 10 and Desktop Distribution correctly identifies FFmpeg as LGPL 2.1+ and plans to bundle it externally to avoid virally infecting the proprietary Python codebase.

### The Problem
If the pipeline heavily utilizes advanced AI tools (like RIFE for frame interpolation, YOLO variants, or specific CUDA hardware acceleration libraries) that require custom FFmpeg builds compiled with GPL flags (e.g., `--enable-gpl`, `--enable-libx264`), the generated FFmpeg binary inherits the strict GPL license, rather than LGPL.

### Proposed Mitigation
- **Compilation Audit:** Add a line to the licensing plan to meticulously audit the exact compilation flags of the FFmpeg binary bundled in the final PyInstaller sidecar.
- **Source Code Availability:** While invoking a GPL FFmpeg via an external subprocess is generally considered safe and doesn't infect the caller's codebase, distributing a GPL-compiled FFmpeg binary *requires* that you provide the exact source code (or a written offer to provide it) for that specific build configuration.
- **Actionable Step:** Ensure the `LICENSES/` folder contains not just the LGPL/GPL text, but the exact `ffmpeg -buildconf` output, and a link/script to replicate the exact FFmpeg build if a custom compilation was used.

---

## 5. Hardware Capabilities Checklist & Graceful Degradation

### The Observation
Phase 11 and 12 plans detail extensive local AI processing, utilizing faster-whisper and RIFE integration, and mention utilizing CUDA optimizations.

### The Problem
End users will likely download the desktop version of this application on highly varied hardware (e.g., older Intel Macs without Apple Silicon, standard Windows laptops lacking dedicated NVIDIA GPUs). If the Local UI blindly tries to run memory-intensive multi-cam sync logic, RIFE processing, or 4K rendering locally without enough VRAM (or RAM), the application could hard-crash or lock up the entire machine out-of-memory.

### Proposed Mitigation
- **Pre-Flight Hardware Check:** Implement a unified `DiagnosticsService` endpoint that systematically interrogates the machine's GPU availability (CUDA, DirectML, Metal), VRAM limits, and available system RAM *before* launching a job.
- **Graceful Feature Degradation:** In the React UI, strictly lock or disable 4K, heavily interpolated RIFE exports, or 8-camera multi-cam tasks if local hardware doesn't meet minimum requirements. Display an alert recommending Cloud Rendering instead.
- **Dynamic Chunking:** For transcription or localized processing, adjust batch size/chunk length based on available hardware memory (e.g., lower `faster-whisper` beam sizes and precision on constrained systems).
