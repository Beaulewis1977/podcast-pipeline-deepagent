# Podcast Pipeline App Research Report

**Date:** 2026-02-03
**Scope:** Evaluate current repository, identify gaps vs. required end-to-end functionality, and propose a working app architecture (fully wired, no stubs). Provide a delivery recommendation (web first, desktop later) and a path to a polished product while preserving useful existing work.

## Executive Summary
The current project already has a solid pipeline skeleton (ingest → transcribe → analyze → review → render), a Streamlit UI, and modular provider integrations. However, several critical behaviors are either not wired into the pipeline or are stubbed in the render stage. The “research” and “viral” modules exist but are not connected to the pipeline or UI. Multi-track transcription exists but is not used by default. Rendering does not apply cuts or filler removals.

To reach a fully working app that outputs polished, near‑final audio/video, the immediate focus should be on wiring the pipeline end‑to‑end, implementing real cut/render behavior, and integrating multi‑track audio into the default flow. After that, refine research and viral analysis to drive marketing outputs. We will **ship a Streamlit-first version**, then **move to a desktop app** that is stable, fast, and not huge. **Desktop target: Rust + Tauri v2**, with a Python backend service running the pipeline.

## Current State (What Exists)
**Pipeline Core:**
- Orchestrated stage flow in `src/podcast_pipeline/pipeline.py`
- Stage state management in `src/podcast_pipeline/stages/base.py`
- Job state persistence in `src/podcast_pipeline/models/job.py`

**Ingest/Transcribe:**
- FFmpeg/FFprobe ingestion and proxy creation: `src/podcast_pipeline/stages/ingest.py`
- Faster‑whisper transcription + filler detection: `src/podcast_pipeline/stages/transcribe.py`
- Multi‑track transcription logic exists but is not used by default.

**Analyze:**
- AI provider integration (Gemini/Kimi): `src/podcast_pipeline/providers/*`
- Outputs structured analysis results: `src/podcast_pipeline/models/analysis.py`

**Review/UI:**
- Streamlit UI scaffolding: `src/podcast_pipeline/ui/app.py`
- Review state and approvals: `src/podcast_pipeline/stages/review.py`

**Render:**
- Platform exports with aspect ratio conversion and loudness normalization: `src/podcast_pipeline/stages/render.py`

**Research/Viral Modules:**
- Viral clip detector: `src/podcast_pipeline/research/viral_detector.py`
- YouTube research client: `src/podcast_pipeline/research/youtube.py`
- These are not wired into pipeline or UI.

## Gaps vs. “Fully Wired, Working, No Stubs”
1. **Render does not apply edits or cuts.** `_build_cuts_filter` is a stub; output is full‑length video/audio.
2. **Multi‑track transcription is not default.** The pipeline always uses single‑track transcription.
3. **Research and viral modules are unused.** They do not influence analysis, review, or outputs.
4. **UI job creation mismatch.** Streamlit creates a job directory then calls `Pipeline.create_job`, which generates a new job ID and duplicates files.
5. **Dependency mismatch.** `RenderStage` imports `numpy` but `numpy` isn’t in dependencies.
6. **Unsafe frame rate parsing.** `eval()` is used in `utils/ffmpeg.py`.
7. **Config inconsistency.** `config.yaml` references `gemini-2.5-flash`, while defaults use `gemini-2.5-flash-latest`.

## Requirements Restated (Based on Your Direction)
- Fully working end‑to‑end pipeline for video + audio podcast production.
- Multi‑track audio (3 microphones) is required.
- Automated transcription, filler removal, and content cuts.
- Video and audio quality improvements (normalization, basic enhancements).
- Marketing research: keywords, titles, viral indicators, trend analysis.
- Outputs must be polished and near‑final with minimal manual steps.
- No placeholders or stubs.

## Streamlit vs Desktop App: Research Findings (Updated Decision)
**Streamlit**
- Strength: rapid development, Python‑native UI for internal tools.
- Weakness: runs as a local web server; packaging into a true desktop app is awkward. The rerun model can be inefficient for heavy workflows.
- Best use: internal dashboards, early prototypes, or local power‑user tools.

**Desktop App (Tauri/Electron/PyQt/Flet)**
- Strength: real desktop distribution, offline installers, better UX for non‑technical users.
- Better control over background jobs, progress, and system integration.
- More engineering effort and UI complexity.

**Recommendation (Accepted)**
- **Short term (fast path):** Keep Streamlit to finish wiring, improve reliability, and validate workflow. This gives a working product quickly.
- **Medium term (polish/distribution):** Move to a desktop app that is stable, fast, and not huge using **Rust + Tauri v2**. The Python pipeline runs as a local backend service invoked by the Tauri UI.

## Target End‑to‑End Flow (Wired)
1. **Ingest:** Copy input, extract metadata, generate proxy, extract audio.
2. **Transcribe (multi‑track default):** Detect tracks, transcribe each, merge into labeled transcript.
3. **Analyze (integrated research):** AI analysis + viral detection + research insights.
4. **Review:** Human approves fillers, cuts, clips, and marketing copy.
5. **Render:** Apply approved edits, generate platform exports, normalize audio, generate final marketing assets.
6. **Deliverables:** Platform‑ready video/audio, transcripts, thumbnails, marketing doc.

## Key Workstreams to Achieve “Fully Wired”
**1) Multi‑Track Audio as Default**
- Promote `transcribe_multi_track()` to be used when multiple tracks exist.
- Merge transcripts with speaker labels.
- Ensure filler detection works per track and in merged output.

**2) Real Cut/Remove Edits in Render**
- Implement FFmpeg trim/concat pipeline to apply:
  - Filler cuts
  - Content cuts
  - Optional manual clip extraction
- Generate both “clean” full episode and short‑form clips.

**3) Research + Viral Integration (inside Analyze)**
- Extend analyze to run research and viral scoring alongside AI results.
- Write unified artifacts (`analysis.json`, `research.json`, `viral_signals.json`) for UI use.
- Use viral detector as a secondary scoring model to complement AI suggestions.

**4) Robust Job Tracking + Progress**
- Long‑running tasks should emit progress updates for UI.
- Consider a job queue + worker model so UI never blocks.

**5) Packaging & Offline Support**
- Bundle FFmpeg and ensure runtime path discovery.
- Add model downloads / caching for Whisper.
- Optionally include an offline mode if no API keys.

## Recommended Architecture (Local, Wired, Polished)
- **Core pipeline** remains Python modules and CLI.
- **Job queue + worker threads/processes** for long tasks.
- **UI layer** calls into a backend service or queues jobs.
- **State storage** remains JSON, or move to SQLite if job history grows.

## Design Notes (Web‑First)
### Delivery Strategy
Streamlit remains the short‑term UI to validate end‑to‑end behavior. It should trigger background jobs, then poll and render progress and artifacts without re‑executing heavy steps. This keeps UI responsive and lets the backend evolve without UI rewrites.

### Wiring Plan (No Stubs)
The pipeline is the single source of truth. The UI should never implement pipeline logic. It should only read/write job state and invoke pipeline steps. This avoids drift and ensures the later desktop UI can reuse the same backend.

### Multi‑Track + Edit Plan
Multi‑track transcription should be the default when multiple audio streams are detected. After review, a single `edit_plan.json` should be produced that captures all approved edits (filler cuts, content cuts, clip ranges). Render must apply the edit plan using FFmpeg trim/concat filters so that outputs are true to review decisions.

### Research + Viral (Integrated in Analyze)
Research runs inside analyze. It should write `research.json` and `viral_signals.json` artifacts. The review UI shows these alongside AI analysis so users can pick clips and marketing copy with data‑grounded context. Viral detection should be a secondary scoring layer that re‑ranks AI clips rather than replacing them.

## Desktop Migration Strategy (Chosen: Rust + Tauri v2)
Desktop should follow after Streamlit validates the pipeline. The target is **Rust + Tauri v2** for a stable, fast, and small installer. The desktop UI should connect to the same job runner used by Streamlit, running the Python pipeline as a local backend service. Packaging should bundle FFmpeg and keep Whisper models as optional downloads to reduce installer size.

## Tauri v2 Integration Notes (High‑Level)
- **Backend model:** Run the Python pipeline as a local service (HTTP or IPC) started by the Tauri app on launch.
- **Job API:** Expose endpoints for job creation, stage execution, progress polling, and artifact retrieval.
- **File access:** Use Tauri’s filesystem APIs for secure file pickers and save locations.
- **Background work:** Keep heavy processing in the Python backend; Tauri UI only polls status and renders results.
- **Crash recovery:** Persist job state in `jobs/<job_id>/state.json` so the UI can resume if the app closes.
- **Packaging:** Bundle FFmpeg and expose its path to the backend at runtime. Keep Whisper models as optional downloads to reduce installer size.

## Deliverable Options (Reframed)
### Option A: Streamlit‑First (Approved)
- Finish wiring pipeline.
- Improve UI to support multi‑track info, review decisions, progress tracking.
- Provide installation instructions (Python + FFmpeg).

### Option B: Desktop Follow‑Up (Chosen: Rust + Tauri v2)
- Wrap pipeline in a local Python backend service with background jobs.
- UI built in Tauri v2 (Rust core + web UI).
- Bundle FFmpeg and make models optional downloads to keep installer size down.

## Risks and Mitigations
- **Large files and GPU load:** Use background workers and progress updates.
- **API cost/limits:** Cache results and allow offline‑only workflows.
- **Complex render filters:** Keep a clear, testable FFmpeg pipeline and add automated tests.
- **Desktop size constraints:** Bundle FFmpeg but make ML models optional downloads; avoid shipping multiple large models by default.

## High‑Level Phase Plan
**Phase 1: Wiring + Stability**
- Fix UI job creation.
- Make multi‑track transcription default.
- Implement actual cut/render logic.
- Eliminate stubs and mismatched dependencies.

**Phase 2: Research + Viral Integration**
- Wire YouTube research into analyze stage.
- Add viral scoring enhancements and ranking.
- Expose research insights in review UI.

**Phase 3: Polishing & Distribution**
- Build desktop app (Rust + Tauri v2).
- Add install + packaging support.
- Improve UI/UX and error handling.

## Phase 1 Checklist (Wiring + Stability)
1. Fix Streamlit job creation so a single job ID is used end‑to‑end.
2. Make multi‑track transcription the default when multiple audio streams are detected.
3. Produce a merged transcript with speaker tags and a single ordered filler‑cut list.
4. Create an `edit_plan.json` artifact after review that includes all approved cuts and clip ranges.
5. Implement FFmpeg trim/concat rendering so edits are actually applied in outputs.
6. Generate both a cleaned full‑episode export and approved short‑form clips from the edit plan.
7. Integrate research into analyze and write `research.json` and `viral_signals.json` artifacts.
8. Expose research + viral insights in the review UI alongside AI suggestions.
9. Add progress reporting per stage so UI can show status without blocking.
10. Align dependencies and config defaults, and remove unsafe parsing (`eval`) in FFmpeg helpers.

## Phase 2 Checklist (Research + Viral Integration)
1. Add engagement rate and velocity metrics to YouTube video stats.
2. Add competition scoring and posting‑pattern analysis outputs.
3. Improve keyword extraction with weighted n‑grams and stopword filtering.
4. Populate `ResearchResult` with competition, engagement, and best posting times.
5. Re‑rank AI viral clips using viral detector signals and show combined scores.
6. Add question, controversy, story‑arc, hook timing, and quotable detection signals.
7. Add engagement density to viral scoring and cap overall scores at 10.
8. Cache research API calls to avoid quota spikes and repeated queries.
9. Ensure research outputs are stored as artifacts for UI display and later reuse.

## Phase 3 Checklist (Polishing + Desktop Distribution)
1. Finalize desktop target (Rust + Tauri v2).
2. Create a dedicated backend runner service for jobs (reused by UI).
3. Package FFmpeg and verify offline operation on clean machines.
4. Make ML models optional downloads to keep installer size down.
5. Add robust crash recovery and job resume from saved state.
6. Provide performance tuning settings (model size, GPU/CPU, proxy resolution).
7. Add installer build pipeline for Windows/macOS/Linux.
8. Validate UI responsiveness with long running jobs and large files.

## Reuse Impact Summary
**High reuse (keep and extend):**
- Pipeline orchestration and stage state management.
- Ingest and transcription logic (including multi‑track support).
- AI provider integrations and analysis models.
- Review state management.
- Render platform specs and FFmpeg helpers.
- Streamlit UI foundation.

**Medium reuse (modify):**
- Render stage: add real cut/concat logic but keep structure.
- Research + viral modules: wire into analyze, enhance outputs.

**Fix‑only items:**
- Streamlit job creation mismatch.
- Dependency alignment and unsafe parsing in FFmpeg helpers.

## Open Questions
- How important is offline operation if API keys are missing (fallback to transcript‑only workflows)?
- Do you want a single “master export” plus platform variations, or fully separate render passes for each platform?

---
**Note:** This report is based on code inspection and targeted research via `saas ask` queries on deployment and architecture patterns. No code changes were made.
