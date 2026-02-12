# All-Features Production Gap Report (Runtime Quality Focus)

Date: 2026-02-12
Updated: 2026-02-12 (heavy independent codebase review — 6 parallel deep-dive agents, full line-by-line audit)
Scope: production runtime behavior only (not release/signing/distribution process)

## 1. Executive Summary

The project is meaningfully implemented, but it is not yet production-grade across all features.  
Real execution exists for ingest/transcribe/analyze/review/render, but several high-impact gaps still prevent reliable, high-quality, intelligent outcomes in real-world use.

Most important reality:
- The system can run real pipelines today. All core stages (ingest/transcribe/analyze/review/render) are real implementations, not stubs.
- It does not yet guarantee production-quality results across all advertised features.
- Several UI/desktop workflows appear complete but are functionally partial.
- Data validation gaps in models allow impossible/degenerate data to flow through silently.
- AI provider failures silently degrade to empty outputs rather than failing explicitly.
- No job-level locking exists — concurrent pipeline runs on the same job can corrupt state.
- Render stage reports success even when some platform exports fail (partial failures hidden).
- Service API has zero authentication — any process on the machine can control all jobs.
- Kimi provider claims multimodal but is transcript-only; users get degraded analysis without warning when Gemini fails over.

## 2. Production Blockers (P0)

1. Bundled FFmpeg/FFprobe are not wired into execution paths.
   - Runtime shells call plain `ffmpeg`/`ffprobe` (`src/podcast_pipeline/utils/ffmpeg.py:41`, `src/podcast_pipeline/utils/ffmpeg.py:85`), while desktop sidecars are prepared with target-suffixed names (`desktop/scripts/prepare-sidecars.mjs:153`).
   - Result: packaged desktop can still fail unless system PATH has ffmpeg/ffprobe.

2. Resume flow resumes only one stage, not full continuation to completion.
   - `resume_job` invokes `pipeline.run(job, stage=resume_stage)` (`src/podcast_pipeline/service/routes/jobs.py:337`).
   - Result: “resume” can require repeated manual operations and may not match user expectation of full continuation.

3. Unknown stage values can return false success.
   - Unknown stage is only logged and skipped (`src/podcast_pipeline/pipeline.py:163`), so route can report success with zero work.

4. Desktop control panel does not wire job lifecycle into UI.
   - Backend client (`desktop/src/lib/backend.ts:160-196`) already has `createJob()`, `runJob()`, `getJob()` functions.
   - But `desktop/src/App.tsx` does not expose these through any UI controls - it remains monitor/recovery-only.
   - Result: the backend is ready but users have no way to create or run jobs from the desktop app.

5. Streamlit "Run Full Pipeline" action only runs ingest.
   - Quick action calls `run_stage_via_service(current_job, "ingest")` (`src/podcast_pipeline/ui/app.py:1141`).

6. AI provider parse failures silently degrade to empty analysis.
   - Gemini and Kimi return fallback empty structures on parse failure (`src/podcast_pipeline/providers/gemini.py:167`, `src/podcast_pipeline/providers/kimi.py:150`).
   - Result: pipeline appears "successful" with low-value outputs. `metadata.summary` is set to `"Analysis parsing failed"` but no error is raised.

7. Streamlit metadata path points to wrong directory.
   - Ingest stage writes metadata to `intermediate/metadata.json` (`src/podcast_pipeline/stages/ingest.py:70`).
   - Streamlit UI reads from `input/metadata.json` (`src/podcast_pipeline/ui/app.py:461`).
   - Result: timeline scrubber fails to load video duration and timestamps; preview is broken.

8. Edit plan and analysis models accept impossible/degenerate time ranges.
   - `FillerCutRange`, `ContentCutRange`, `ClipRange` in `src/podcast_pipeline/models/edit_plan.py` have zero validation.
   - Accepts `start_seconds > end_seconds`, negative values, ranges past video duration.
   - Render stage silently filters bad ranges (`src/podcast_pipeline/stages/render.py:420-423`), producing partial output without user awareness.

9. Streamlit quality controls are display-only.
   - "Video Quality" slider and "Normalize Audio" toggle (`src/podcast_pipeline/ui/app.py:961-973`) create Streamlit widgets but values are never captured or passed to the backend.
   - Result: users believe they control quality settings but render uses hardcoded platform specs from config.

10. Render stage returns `success=True` even when platform exports partially fail.
    - If YouTube export fails but Spotify succeeds, `StageResult(success=True, data={"errors": [...]})` is returned (`src/podcast_pipeline/stages/render.py:100-105`).
    - Result: user thinks render succeeded but YouTube output is missing. Errors buried in `data` dict, not surfaced.

11. No job-level locking — concurrent pipeline runs can corrupt state.
    - Job state is loaded once at pipeline start (`src/podcast_pipeline/pipeline.py:170-171`) and never reloaded between stages.
    - No file lock or mutex. Two simultaneous `pipeline.run()` calls on the same job will both execute.
    - Result: race condition on `state.json`, duplicate stage execution, corrupted outputs.

12. Kimi provider is transcript-only but registered as video analysis fallback.
    - Docstring claims "Native multimodal support" (`src/podcast_pipeline/providers/kimi.py:66`) but `analyze()` ignores `video_path` entirely (line 87-89).
    - When Gemini fails and Kimi is used as fallback, user gets text-only analysis without any warning that video visual analysis was skipped.
    - Result: viral clip scores, thumbnail suggestions, and visual content cuts are based on transcript text alone — unreliable.

13. Service API has no authentication or authorization.
    - No API key, bearer token, or CORS restrictions on any endpoint.
    - Any process on the machine can create, run, resume, or delete jobs.
    - Result: no audit trail; in shared environments, unintended job manipulation is possible.

## 3. Feature Readiness Matrix

| Feature | Current State | Production Gap | Required Outcome |
|---|---|---|---|
| Job orchestration | Real stage runner exists | Unknown-stage false success; no retries/backoff | Strict stage validation + retry policies |
| Recovery/resume | Reconcile + resumable list exists | Resume only runs one stage | Resume should continue from stage through completion |
| Ingest | Real FFprobe/FFmpeg extraction | No resilient fallback when binaries missing | Resolver-backed binary path + startup checks |
| Transcription | Real faster-whisper integration | Single ASR path, no fallback/provider diversity | Multi-provider ASR with quality/confidence controls |
| Filler removal | Real word-level cuts | Multi-word fillers declared but not implemented | Phrase/context-aware filler detection |
| AI analysis | Real provider calls | Parse fallback to empty payload; no strict re-try policy | Schema-enforced response + re-prompt on invalid output |
| YouTube research | Real YouTube API integration | Weak query derivation; formatting/quality issues | Transcript-driven topic extraction + robust ranking |
| Viral scoring | Real heuristic scoring | Heuristic-only approach, not calibrated | Stronger calibration + regression thresholds |
| Review workflow | Real review state/edit plan | UI is approval-focused, not deep editorial tooling | True timeline editing + preview-sync editing |
| Rendering | Real cross-platform exports | Limited enhancement chain (no real denoise/color pipeline) | High-quality audio/video enhancement pipeline |
| Thumbnails | AI suggests timestamps/text | No real thumbnail image extraction pipeline | Real thumbnail extraction/ranking/output assets |
| Marketing | AI-generated copy + editable UI | Research not looped back into generation quality | Research-informed regeneration with quality gates |
| Streamlit UX | Real operator surface | Several actions partial/misaligned with labels | Fully truthful controls and consistent file paths |
| Desktop UX | Backend connectivity + recovery | No full job lifecycle UX | Complete create/run/monitor/resume workflow |
| Data validation | Pydantic models exist | Edit plan/analysis models accept impossible ranges (negative, backwards, overlapping) | Field validators enforcing non-negative, start <= end, format checks |
| Service client | Typed HTTP client exists | Missing `background` param on resume; no OpenAI provider despite config declaring it | Complete typed client matching all backend capabilities |
| Supervisor | Background job execution works | No timeout/kill for hung jobs; `last_known_stage` never updated | Timeout policy, stage progress tracking, kill escalation |
| Concurrency | No locking | Concurrent runs on same job corrupt state; no file lock or mutex | Job-level file lock + state reload between stages |
| Auth/security | None | Zero authentication on service API; exception handling hardening is not centralized | API key or bearer token middleware; global error handler |
| Provider fallback | Gemini → Kimi chain | Kimi is text-only but presented as full fallback; no warning on degraded mode | Explicit degraded-mode flag; warn user when falling back to transcript-only |
| Test confidence | Suite passes | Runtime-critical modules still low coverage (render 24%, transcribe 24%); provider runtime paths are sparsely tested | Higher gates + real-media integration tests + provider unit tests |

## 4. File-by-File Action Register

### Core Pipeline

- `src/podcast_pipeline/pipeline.py`
  - Enforce stage validation and return 4xx-compatible error path for unknown stages.
  - Add job-level retry/backoff policy and clear failure semantics.
  - Add file-based job lock to prevent concurrent `run()` calls on the same job (lines 170-171 load state once, never reload).
  - Reload job state before each stage to detect external modifications.

- `src/podcast_pipeline/stages/base.py`
  - Add structured stage error categories and optional retry hooks.
  - Persist richer progress details for long-running stages.

- `src/podcast_pipeline/models/job.py`
  - Expand stage metadata for attempt counts, retry timestamps, and degraded-mode flags.
  - `progress_percent` has no bounds — allows negative or >100 values. Add `Field(ge=0, le=100)`.
  - `job_id` accepts empty strings and dangerous characters. Add non-empty alphanumeric validation.
  - Model allows contradictory states: `status=COMPLETE` with `error` set, `progress_percent` set while `status=PENDING`. Add state-machine validators.

### Ingest / Transcribe / Analyze / Review / Render

- `src/podcast_pipeline/stages/ingest.py`
  - Use asset resolver-provided ffmpeg/ffprobe paths, not PATH assumptions.
  - Add output file verification after each FFmpeg operation (copy, extract audio, proxy creation).
  - No disk space check before copying large video files.

- `src/podcast_pipeline/stages/transcribe.py`
  - Implement ASR fallback path (secondary provider or CPU-safe fallback).
  - Add phrase-level filler detection (current note admits simplified logic at `src/podcast_pipeline/stages/transcribe.py:255`).
  - Add quality/confidence outputs and low-confidence warnings.

- `src/podcast_pipeline/stages/analyze.py`
  - Respect configured provider ordering rather than implicit key-based order only (`src/podcast_pipeline/stages/analyze.py:35`).
  - Replace weak research query fallback (`src/podcast_pipeline/stages/analyze.py:213`) with transcript-driven extraction.
  - Persist provider raw response snapshots on parse/validation failure.
  - Transcript JSON loading (line 77) has no try-except — corrupted `transcript.json` crashes the stage with unhandled `JSONDecodeError`.
  - `_normalize_score()` (line 221) silently coerces invalid values (e.g. string "eight") to default 5.0 — should warn.
  - Add explicit degraded-mode flag when Kimi fallback is used, since it provides transcript-only (not video) analysis.

- `src/podcast_pipeline/stages/review.py`
  - Extend review/edit plan to include thumbnail and marketing decision application in render phase.
  - Add cut conflict validation (overlaps/full-span destructive plans).
  - Review state and analysis JSON loading (lines 76-77, 80-84) can crash on corrupted files — no try-except around `json.loads()`.
  - Auto-approves all filler cuts by default (lines 117-133) without user confirmation — should require explicit opt-in.
  - Filler cut conversion uses dual-key fallback `get("start_seconds", get("start", 0.0))` (lines 215-216) — defaults silently to 0.0 on missing keys, producing 0s→0s no-op cuts.

- `src/podcast_pipeline/stages/render.py`
  - Implement actual enhancement chain: denoise, speech EQ, limiter/true-peak, color correction.
  - Implement thumbnail output generation (currently only marketing doc + platform media).
  - Wire platform-specific clip exports (not only generic `output/clips/clip_XX.mp4`).
  - Make UI quality options effective (currently no runtime wiring).
  - Fix partial-failure reporting: currently returns `success=True` when some platforms fail (lines 100-105). Should either return `success=False` or surface platform-level errors clearly.
  - Loudness normalization silently skipped if `pyloudnorm` not installed (lines 523-525, warning only). Should either make it a required dependency or inform user output is unnormalized.
  - Verify output files exist after FFmpeg operations — currently assumes success without checking.
  - `get_video_info()` returns silent defaults (1920x1080, 30fps) on failure (line 264) — can cause wrong aspect ratio conversions. Should propagate error.

### Providers / Research

- `src/podcast_pipeline/providers/gemini.py`
  - Replace empty fallback payload strategy with strict failure + retry/re-prompt.
  - Add JSON schema guardrails to output format.
  - Cache uploaded video file IDs per job — currently `client.files.upload()` (line 115) re-uploads the full video on every analyze call, wasting bandwidth and quota.
  - Rate limit detection uses fragile string matching on error messages (lines 147-151: checks for "rate" and "quota" in exception text). Should use specific exception types from google-genai library.
  - No validation that configured `model` is in `SUPPORTED_GEMINI_MODELS` list (line 40-46).
  - No max file size check before upload attempt.

- `src/podcast_pipeline/providers/kimi.py`
  - Same parse-fallback fix as Gemini.
  - Clarify and implement actual multimodal/video path or explicitly mark transcript-only mode.
  - Fix misleading docstring: claims "Native multimodal support" (line 66) but implementation is text-only.
  - Add explicit warning log when `video_path` is provided but ignored.

- `src/podcast_pipeline/providers/openai.py` *(does not exist)*
  - Config declares `openai` API key slot (`config/settings.py:254`) and reads `OPENAI_API_KEY` from env (line 263), but no OpenAI provider implementation exists.
  - Either implement an OpenAI-backed analysis provider or remove the config declaration to avoid misleading users.

- `src/podcast_pipeline/providers/base.py`
  - Add provider capability metadata (video support, transcript-only, max duration).
  - Add `model: str` property to `AnalysisProvider` protocol — analyze stage uses `getattr(provider, "model", "unknown")` (line 100) which violates protocol contract.
  - `_build_prompt()` hardcodes transcript truncation to 10,000 chars (line 81) with no configuration.

- `src/podcast_pipeline/research/youtube.py`
  - Fix `publishedAfter` formatting (`src/podcast_pipeline/research/youtube.py:240`).
  - Populate and use `topics` output consistently (currently largely empty).
  - Add stronger quality ranking (freshness, engagement momentum, channel relevance).
  - Cache is purely in-memory (`self._cache` dict, line 109) — lost on every service restart. Consider optional persistent cache for API quota protection.

- `src/podcast_pipeline/research/viral_detector.py`
  - Add calibration dataset/tests for score stability and false-positive rate.

### Runtime Assets / Service Backend

- `src/podcast_pipeline/utils/ffmpeg.py`
  - Support resolved binary paths and environment-based override at call site.
  - Add clearer recovery guidance in error payloads.

- `src/podcast_pipeline/service/assets.py`
  - Integrate resolved binary/model paths into active runtime configuration.
  - Ensure env var naming consistency across docs and runtime.
  - Binary existence check uses `is_file()` but doesn't verify executability (`os.access(p, os.X_OK)`) — could find a non-executable file named "ffmpeg".
  - Model integrity not verified — only checks marker files exist (model.bin, config.json), no checksum or size validation.

- `src/podcast_pipeline/service/app.py`
  - Add authentication middleware (API key or bearer token).
  - Add global exception handler to prevent stack trace leakage to clients.
  - Add request/response logging middleware for production observability.

- `src/podcast_pipeline/service/routes/jobs.py`
  - Resume should run from selected stage through completion by default.
  - Return explicit error for invalid stage inputs.
  - Add `until_stage` parameter to `ResumeJobRequest` schema (currently only `RunJobRequest` has it).
  - Resume "already complete" returns 200 — should return 204 or distinct status so client can tell if work was done.
  - Run failure response doesn't indicate how far the pipeline got before failure (line 187-193).

- `src/podcast_pipeline/service/routes/system.py`
  - Persist model warmup state across restarts (in-memory map currently volatile at `src/podcast_pipeline/service/routes/system.py:80`).
  - Make required binary policy environment-aware (dev service vs packaged sidecar).

- `src/podcast_pipeline/service/supervisor.py`
  - Persist `last_known_stage` updates during background runs.
  - Add timeout/kill/escalation policy for hung runs.

- `src/podcast_pipeline/service/recovery.py`
  - Resume preparation should support "continue to end" semantics, not only single-stage rerun.
  - Reconciliation runs at startup and on `GET /jobs/resumable` (line 128) and `POST /jobs/reconcile` (line 157), but not periodically in the background — a job that crashes between client API calls won't be reconciled until the next resumable check or restart.
  - `prepare_resume()` doesn't validate `from_stage` against `Pipeline.STAGE_ORDER` — an invalid stage name is passed directly to `job.update_stage()` (line 262), creating a non-standard stage entry rather than raising an error.
  - Stale heartbeat timeout hardcoded to 30s (line 49) — not configurable per environment.

- `src/podcast_pipeline/clients/service_client.py`
  - `resume_job()` (line 303) does not pass the `background` parameter that the backend `ResumeJobRequest` schema supports — callers cannot request non-blocking resume.
  - Add typed methods for system readiness/warmup and richer run options.
  - Creates new `httpx.Client` for every request (lines 191-198) — loses connection pooling. Should use persistent session.
  - 30-second timeout applies to all requests uniformly — long-running synchronous `run_job()` calls will timeout. Should use endpoint-specific timeouts.
  - Only generic `ServiceResponseError` — no typed exceptions for specific HTTP codes (404 JobNotFound, 409 AlreadyRunning).

### Streamlit UI

- `src/podcast_pipeline/ui/app.py`
  - Fix "Run Full Pipeline" action (currently ingest-only at `src/podcast_pipeline/ui/app.py:1141`).
  - Fix metadata path in preview (`src/podcast_pipeline/ui/app.py:461` points to wrong location for ingest metadata).
  - Remove orphan pre-job directory creation during upload (`src/podcast_pipeline/ui/app.py:323`).
  - Make quality controls functional (current settings are display-only).
  - Replace approval-only cut UX with real timeline editing controls if "visual cut editor" is claimed.
  - "Save Marketing Copy" (line 880) writes directly to `analysis.json` (line 887), bypassing the review workflow — edits should go through the edit plan.
  - "Regenerate Marketing Copy" (line 891) calls `resume_job(from_stage="analyze")` which only runs analyze, not analyze→review — user must manually re-review.

### Desktop App

- `desktop/src/App.tsx`
  - Add full lifecycle actions: create job, run job, run to stage, resume, view detail logs.

- `desktop/src/lib/backend.ts`
  - Expose full typed contract methods for create/run/resume/detail with robust error payloads.

- `desktop/src/lib/recovery.ts`
  - Add richer recovery controls and per-stage restart options.

- `desktop/src-tauri/src/lib.rs`
  - Add sidecar preflight checks + stderr/stdout capture + fallback guidance.
  - Improve “running” status to confirm actual health, not only PID presence.

- `desktop/src-tauri/src/recovery.rs`
  - Add stronger response parsing and explicit error mapping to UI.

- `desktop/scripts/prepare-sidecars.mjs`
  - Align generated binary names with backend runtime lookup strategy.

### Config / Models / Contracts

- `src/podcast_pipeline/config/settings.py`
  - Actually use `models_cache` in transcription/warmup paths.
  - Validate provider capability and selected model compatibility.
  - `noise_reduction` (AudioConfig) and `compute_type` (TranscriptionConfig) appear unused by any implementation.
  - No validation that `provider` field is one of the known set (`"gemini"`, `"kimi"`).
  - No port range validation on `ServiceConfig.port`, no host validation.

- `src/podcast_pipeline/models/analysis.py`
  - Add `field_validator` for `start_seconds >= 0`, `end_seconds >= start_seconds` on `ContentCut` and `ViralClip`.
  - Validate `start`/`end` strings match `MM:SS` or `HH:MM:SS` format.
  - Add cross-field `model_validator` ensuring string and float timestamp representations are consistent (within 1s tolerance).
  - Tighten validation constraints for production quality (length limits, required fields by platform).
  - `ViralClip.start_seconds` and `end_seconds` default to `0.0` which is indistinguishable from a parse failure — should be required fields or `Optional[float] = None`.
  - Dual time format hazard: both string (`start`/`end`) and float (`start_seconds`/`end_seconds`) representations exist with no consistency guarantee — the model allows contradictory values.

- `src/podcast_pipeline/models/transcript.py`
  - `Word.confidence` has no bounds — can be >1.0 or negative. Add `Field(ge=0.0, le=1.0)`.
  - `Word`, `Segment`, `FillerCut` all lack `start >= 0` and `end >= start` validators.
  - `TranscriptResult.duration` allows negative values.

- `src/podcast_pipeline/models/edit_plan.py`
  - Add `field_validator` for non-negative times and `end_seconds >= start_seconds` on all range models.
  - Add overlap detection or at minimum a warning when ranges conflict.
  - Currently render.py works around this with defensive `max(0.0, ...)` and `if end > start` checks (lines 420-423) but users are never informed of malformed data.

### Test & Quality Gates

- `tests/test_integration.py`
  - Add true runtime path tests for transcribe/render outputs with realistic media fixtures.

- `tests/test_render.py`
  - Add end-to-end render command assertions, not only helper logic tests.

- `tests/test_analyze_ranking.py`
  - Reduce heavy monkeypatch dependency; validate real detector behavior with deterministic fixtures.

- `tests/test_research.py`
  - Use richer fixture payloads and validate full parse/ranking paths.

- `tests/test_streamlit_service_client.py`
  - Add tests for full-run action semantics and upload path correctness.

- `tests/test_providers.py` *(does not exist — must create)*
  - Provider init/config paths have incidental coverage, but no dedicated tests for core `analyze()` behavior.
  - Need unit tests for: `is_available()`, `analyze()` with mocked API, rate limit retry logic, malformed JSON response handling, file upload failure.
  - Need integration tests for: provider fallback chain (Gemini fails → Kimi), degraded-mode flag when text-only fallback used.

- `tests/test_edit_plan.py` *(does not exist — must create)*
  - Zero tests for edit plan validation edge cases.
  - Need tests for: negative time ranges, backwards ranges (end < start), overlapping cuts, zero-duration clips, cuts exceeding video duration.

- `tests/test_supervisor.py` *(does not exist — must create)*
  - Need tests for: `start_run()` prevents duplicate execution, heartbeat updates `runtime.json`, timeout/kill behavior, background task cleanup.

- `pyproject.toml`
  - Increase coverage threshold from 38% to at minimum 50% (current actual: 53.97%).
  - Add per-module minimums for runtime-critical code: `stages/` at 40%+, `providers/` at 60%+.
  - Consider splitting test tiers: `tests/unit/`, `tests/integration/`, `tests/slow/`.

## 5. What Needs To Be Fixed / Changed / Updated / Added / Implemented

### Fixed (must fix now)

- Runtime binary resolution mismatch between bundled sidecars and ffmpeg invocation.
- Resume semantics that only run one stage (service route and recovery module).
- Unknown stage inputs returning apparent success.
- Misleading UI actions (full-run button, metadata path bug, orphan upload path behavior).
- Edit plan / analysis / transcript model validation: reject negative times, backwards ranges, overlapping cuts, unbounded confidence values.
- Display-only quality controls in Streamlit (slider/toggle values never passed to backend).
- Service client `resume_job()` missing `background` parameter.
- Marketing "Save" bypasses review workflow (writes directly to analysis.json).
- Render partial-failure reporting: returns `success=True` when some platform exports fail.
- Job-level file locking to prevent concurrent `pipeline.run()` on the same job.
- Kimi provider misleading docstring ("Native multimodal") and missing degraded-mode warning on fallback.
- JSON load crash paths in analyze (line 77) and review (lines 76-77, 80-84) — no try-except guards.

### Changed

- Provider failure handling from silent-empty fallback to explicit failure with retry.
- Research query generation from filename fallback to transcript/topic extraction.
- Desktop from "monitor-only" to full operational control plane.
- Gemini provider should cache uploaded file IDs per job instead of re-uploading every call.
- Gemini rate limit detection from fragile string matching to specific exception types.
- Service client should use persistent httpx session instead of creating new client per request.
- Service client should use endpoint-specific timeouts (30s default too short for synchronous run).

### Updated

- Docs to match actual runtime endpoints and behavior (`README.md`, `docs/plans/2026-01-29-podcast-pipeline-design.md`, `docs/desktop-distribution.md`).
- Test strategy from mostly contract/mocked checks to real-media runtime confidence.
- YouTube research cache strategy: current in-memory dict lost on restart — add optional persistent layer for API quota protection.

### Added

- Real thumbnail extraction/ranking/output pipeline.
- ASR fallback provider path and transcription quality metrics.
- Audio enhancement chain and video correction pipeline.
- Persistent warmup/download state and richer stage progress telemetry.
- OpenAI provider implementation or removal of dangling config declaration (`config/settings.py:254`).
- Disk space / output directory validation before render starts (currently no pre-flight checks).
- Supervisor timeout/kill policy for hung background jobs.
- Authentication middleware on service API (API key or bearer token at minimum).
- Global exception handler middleware to prevent stack trace leakage.
- Background periodic reconciliation (currently runs at startup + on-demand API calls, but not between calls).
- Provider test suite (current coverage is mostly incidental/import-init; core `analyze()`/retry/fallback paths need dedicated tests).
- Edit plan validation test suite (currently zero tests for time range edge cases).
- `until_stage` parameter on resume endpoint (parity with run endpoint).
- Typed HTTP status exceptions in service client (404, 409 instead of generic ServiceResponseError).

### Implemented (high-level target state)

- End-to-end, one-click run that truly executes ingest → transcribe → analyze → review → render with production-quality outputs.
- Real-world intelligent decisions backed by strict validation, retries, and measurable quality thresholds.
- Fully functional Streamlit and desktop surfaces that match what they claim.

## 6. Suggested Implementation Order (Phase 4 Waves)

**Wave 1 — Runtime correctness (P0 blockers)**
- FFmpeg binary resolution (utils/ffmpeg.py + ingest.py).
- Resume-through-completion semantics (pipeline.py, service/routes/jobs.py, recovery.py). Add `until_stage` to resume schema.
- Unknown-stage validation (pipeline.py → raise, not skip).
- Fix misleading UI actions: full-run button, metadata path, display-only quality controls.
- Model validation on edit_plan, analysis, and transcript time ranges + confidence bounds.
- Service client `resume_job()` `background` param + persistent session + endpoint-specific timeouts.
- Job-level file lock to prevent concurrent `pipeline.run()` corruption.
- Fix render partial-failure reporting (success=True when platforms fail).
- Fix JSON load crash paths in analyze (line 77) and review (lines 76-77).

**Wave 2 — Data integrity & provider reliability**
- Provider parse-failure handling: strict fail + retry/re-prompt (gemini.py, kimi.py).
- Gemini upload file ID caching per job.
- Gemini rate limit detection: replace string matching with specific exception types.
- Kimi: fix misleading multimodal docstring, add degraded-mode warning when used as fallback.
- Marketing save flow through review workflow instead of direct analysis.json write.
- OpenAI provider: implement or remove config declaration.
- Supervisor timeout/kill for hung background jobs, `last_known_stage` tracking.
- Authentication middleware on service API.
- Global exception handler middleware.

**Wave 3 — Output quality backbone**
- Audio enhancement chain: denoise, speech EQ, limiter/true-peak normalization.
- Real thumbnail extraction/ranking/output pipeline.
- Wire quality controls from UI into render (pass user settings to backend).
- Transcript-driven research query generation.
- Output file verification after FFmpeg operations.
- Disk space pre-flight checks before ingest copy and render.

**Wave 4 — UX completion**
- Desktop full lifecycle controls (create, run, resume, delete jobs from App.tsx).
- Streamlit timeline editing (real cut editor, not just approval toggles).
- YouTube research persistent cache.
- Background periodic reconciliation (currently runs at startup + on-demand API calls, but not between calls).
- Typed HTTP status exceptions in service client.

**Wave 5 — Confidence gates**
- Provider test suite (Gemini + Kimi: dedicated tests for `analyze()`/retry/fallback behavior are missing).
- Edit plan validation test suite.
- Supervisor async test suite.
- Real-media integration tests for transcribe/render paths.
- Per-module coverage minimums for runtime-critical code (`stages/` 40%+, `providers/` 60%+).
- Coverage gate increase from 38% to 50%+ overall.
- Provider response regression fixtures.
- Split test tiers: unit / integration / slow / e2e.

## 7. Evidence Snapshot

### Test Suite
- `uv run pytest --cov=src/podcast_pipeline --cov-report=term-missing -q` passed on 2026-02-12.
- All 223 tests pass. Model/config/util tests run real logic, but all runtime IO paths (FFmpeg, Whisper, API calls, file processing) are fully mocked — zero real-media integration tests exist.
- Coverage highlights:
  - `src/podcast_pipeline/stages/render.py`: 24%
  - `src/podcast_pipeline/stages/transcribe.py`: 24%
  - `src/podcast_pipeline/stages/analyze.py`: 44%
  - `src/podcast_pipeline/providers/gemini.py`: 29% (import/init paths covered; core `analyze()` with real API calls untested)
  - `src/podcast_pipeline/providers/kimi.py`: 42% (import/init paths covered; core `analyze()` with real API calls untested)
  - `src/podcast_pipeline/ui/app.py`: 14%
  - `src/podcast_pipeline/service/supervisor.py`: low (background run paths not exercised)
  - Total: 53.97% (gate currently 38% in `pyproject.toml`)
- No `test_providers.py` exists — provider init/config paths have incidental coverage, but no dedicated tests for `analyze()`, parse failure, retry, or fallback behavior.
- No `test_edit_plan.py` exists — zero tests for time range validation edge cases.
- No `test_supervisor.py` exists — async background execution untested.
- Runtime-critical IO paths (~3,400 LOC in stages/providers) have low meaningful coverage — line coverage numbers are inflated by import/init/model paths.

### Independent Review Findings (confirmed against source)
- No `src/podcast_pipeline/providers/openai.py` file exists despite config declaring it (`config/settings.py:254`).
- `service_client.resume_job()` omits `background` param present in backend `ResumeJobRequest` schema.
- Gemini `client.files.upload()` called on every analysis with no file ID reuse (line 115).
- YouTube research cache is in-memory only (`self._cache` dict, line 109).
- Streamlit marketing save writes directly to `analysis.json` bypassing review (line 887).
- Kimi docstring claims "Native multimodal support" (line 66) but `analyze()` ignores `video_path` entirely.
- Gemini rate limit detection uses fragile string matching on error messages (lines 147-151).
- Kimi has identical tenacity retry decorator to Gemini (line 79-84) — both retry on `RateLimitError`.
- Render returns `success=True` when partial platform exports fail (lines 100-105).
- No job-level locking — concurrent `pipeline.run()` calls can corrupt `state.json`.
- `pipeline.py` loads job state once at start, never reloads between stages (lines 170-171).
- Analyze stage transcript loading has no try-except — crashes on corrupted JSON (line 77).
- Review stage JSON loading can crash on corrupted files (lines 76-77, 80-84).
- Recovery reconciliation runs at startup + on-demand via `GET /jobs/resumable` and `POST /jobs/reconcile` — but no periodic background task between client calls.
- `prepare_resume()` doesn't validate `from_stage` against `Pipeline.STAGE_ORDER` — invalid stage is passed directly to `job.update_stage()` (line 262), creating a non-standard stage entry.
- Service API has zero authentication — no API key, bearer token, or CORS restrictions.
- `get_video_info()` returns silent default dimensions (1920x1080) instead of propagating errors.
- `loudnorm` silently skipped if pyloudnorm not installed (warning only, line 523-525).
- `_build_prompt()` hardcodes transcript truncation to 10,000 chars with no configuration (base.py line 81).
- `progress_percent` in job model has no bounds validation — accepts negative and >100.

### What IS Production-Quality (code quality solid, gaps are additive not correctness issues)
- CLI (`cli.py`): all commands, error handling, output formatting — no code-level bugs.
- Service entry point (`service/app.py`): factory pattern, lifespan, router wiring are correct — gaps are missing middleware (auth, error handler) not broken code.
- Service schemas (`service/schemas.py`): 11 well-structured Pydantic models — gap is missing `until_stage` on resume schema, not broken schemas.
- Job persistence (`job.py` save/load): atomic writes via temp file + rename.
- Recovery PID liveness checks (`recovery.py`): correct signal(0) + PermissionError handling.
- Desktop sidecar management (`lib.rs`): PID tracking, graceful shutdown, Windows support.
- Desktop recovery module (`recovery.ts`): Tauri invoke with HTTP fallback.
- Time utilities (`utils/time.py`): multiple format support, defensive parsing.
- Logging setup (`utils/logging.py`): structlog with JSON/console toggle.
- Viral clip detector (`viral_detector.py`): sophisticated 9-pattern scoring with 4 weighted dimensions — more capable than a simple heuristic.
- YouTube research (`youtube.py`): comprehensive API integration with TTL caching, keyword scoring, competition analysis.

---

This report is intentionally runtime-focused and excludes release/signing/distribution process concerns.

Review methodology: 6 parallel deep-dive agents (core pipeline, AI providers, service backend, UI/desktop, models/config, tests) with full line-by-line source examination. All findings verified against source code with specific line numbers.
