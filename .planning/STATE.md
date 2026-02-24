# Project State: Podcast Pipeline

**Last updated:** 2026-02-24
**Current phase:** Phase 9.12 — Streamlit UI Gap Closure
**Overall progress:** Phase 9 complete (11/11 plans); 64 plans completed overall; Phase 9.12 plan 2/3 complete

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Turn raw podcast recording into multi-platform content without editing software or manual copywriting.
**Current focus:** Phase 9.12 — Streamlit UI Gap Closure (7 gaps identified; awaiting research + planning).

## Current Position

```text
Phase:    9.12 (Streamlit UI Gap Closure)
Plan:     02/03 complete — 09.12-02 Settings provider select + Production sidebar caption/sync controls
Status:   Executing — 2 plans done, 1 remaining
Last activity: 2026-02-24 - Completed 09.12-02-PLAN.md (GAP-1/GAP-3A/GAP-3B/GAP-4 UI closures)

Progress: [██████████████████████████████] 64/65 plans complete
```

**Current Phase:** Phase 9.12 — Streamlit UI Gap Closure (2/3 plans complete)

## Phase Status

| Phase | Name | Status | Plans | Progress |
|------:|------|--------|-------|----------|
| 1 | Wiring + Stability | Complete | 6/6 | 100% |
| 2 | Research + Viral Integration | Complete | 5/5 | 100% |
| 3 | Polishing + Desktop Distribution | Complete | 6/6 | 100% |
| 4 | Post-release hardening | Human verification needed | 10/10 | 100% |
| 5 | Video Podcast Platforms | Complete (verified) | 3/3 | 100% |
| 5.1 | Streamlit Video Platform UI | Complete (verified) | 3/3 | 100% |
| 6 | Audio/Video Enhancement & Podcast Video Platform | Complete (verified) | 3/3 | 100% |
| 6.1 | Video Marketing Copy Parity + Thumbnail Visual Selection MVP | Complete (verified) | 5/5 | 100% |
| 7 | Smooth Editing & Filler Word Control | Complete (verified 2026-02-21) | 4/4 | 100% |
| 8 | Intelligent Cut Quality | Complete (verified 2026-02-21) | 6/6 | 100% |
| 9 | Automated Branding, Captions, and Multi-Track Sync | Complete (verified 2026-02-24) | 11/11 | 100% |
| 9.12 | Streamlit UI Gap Closure | In progress | 2/3 | 67% |

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 64/65 |
| Requirements done | 35/83 (21 partial) |
| Phases complete | 9/9 |
| Estimated completion | All phases complete |

## Accumulated Context

### Key Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| Streamlit-first UI | Fastest path to validate workflow | 2026-02-03 |
| Desktop follow-up (Rust + Tauri v2) | Better distribution + performance | 2026-02-03 |
| Hide progress UI unless progress data exists | Avoid noisy empty UI when stages haven't reported progress | 2026-02-04 |
| Fallback to single-track transcription when only one stream exists | Prevents recursion and preserves current behavior | 2026-02-04 |
| Use Fraction-based FPS parsing to avoid eval | Removes unsafe eval in ffprobe metadata handling | 2026-02-04 |
| Derive research query from analysis topics, fallback to job name | Ensures research runs even when topics are sparse | 2026-02-04 |
| Use review/edit_plan.json as render input | Keeps render and clip exports aligned with review decisions | 2026-02-04 |
| Apply edit-plan cuts via trim/concat filter_complex | Ensures render output respects approved cuts | 2026-02-04 |
| Competition score bounded to 0-100 using normalized weighted factors | Keeps topic difficulty stable and comparable for ranking/UI consumers | 2026-02-04 |
| Posting recommendations emitted as UTC windows + weekday distributions | Deterministic structure for cross-timezone rendering and tests | 2026-02-04 |
| Engagement density uses weighted signal strength/minute with diversity bonus | Rewards clips with sustained multi-signal momentum instead of isolated spikes | 2026-02-04 |
| Detector reasons explicitly mention question/controversy/story-arc/quotable cues | Keeps clip ranking changes interpretable in artifacts and UI | 2026-02-04 |
| YouTube search/stat calls use normalized TTL cache keys | Reduces repeated quota consumption across identical analyze runs | 2026-02-04 |
| Keyword ranking is phrase-first (weighted n-grams) with stopword filtering | Surfaces reusable title/thumbnail phrases over weak unigram noise | 2026-02-04 |
| Analyze clip ranking blends AI (45%) and detector (55%) scores | Prioritizes transcript-level evidence while retaining provider signal | 2026-02-04 |
| Viral artifact rows remain backward-compatible via additive score fields | UI can adopt richer metrics incrementally without breaking old readers | 2026-02-04 |
| Insight panels use pure data transformers before rendering | Keeps schema handling testable and resilient to partial artifacts | 2026-02-04 |
| UI clip table always sorts by combined score with legacy fallbacks | Maintains ranking consistency across new and old artifact shapes | 2026-02-04 |
| Factory pattern for FastAPI app | uvicorn factory=True compatible, standard ASGI deployment | 2026-02-05 |
| asyncio supervisor for background runs | Pipeline.run is blocking; executor thread + async heartbeat | 2026-02-05 |
| runtime.json for crash recovery | Separate from state.json to decouple process lifecycle from pipeline state | 2026-02-05 |
| Port 8787 as default service port | Avoids collision with Streamlit (8501) and common dev ports | 2026-02-05 |
| httpx for typed service client | Sync + async, built-in retry transport, context-managed clients | 2026-02-05 |
| ServiceConfig in project Config | Single source of truth for backend connection shared by all frontends | 2026-02-05 |
| Display-only reads stay local FS | Streamlit and service share jobs/ dir; no redundant GET endpoints needed | 2026-02-05 |
| Tauri v2 with shell plugin for sidecar | Tauri v2 approach replaces v1 built-in sidecar API | 2026-02-05 |
| Mutex PID tracking in Rust | Thread-safe sidecar lifecycle with idempotent start | 2026-02-05 |
| Tiered binary resolution (env/sidecar/PATH) | Avoids hardcoded OS paths; supports dev and bundled modes transparently | 2026-02-05 |
| Conservative recovery reconciliation | Never touch completed stages; only correct stale running states | 2026-02-05 |
| Three-stage release workflow | build-backend -> build-desktop -> smoke-test for failure isolation | 2026-02-05 |
| PyInstaller for backend sidecar | Single-file cross-platform binary from Python service | 2026-02-05 |
| Graduated smoke severity | Blocking checks (artifact/size/sidecar) vs warnings (health/ffmpeg) | 2026-02-05 |
| Draft releases by default | Manual review before publishing to avoid broken releases | 2026-02-05 |
| Use stdlib O_EXCL lock files for job-scoped run exclusivity | Avoids new dependencies while enforcing deterministic same-job concurrency guardrails | 2026-02-13 |
| Validate stage names in job mutation APIs | Prevents invalid stage keys from corrupting canonical state transitions | 2026-02-13 |
| Reload job state from disk before each stage dispatch | Prevents stale in-memory state from overwriting newer persisted job state | 2026-02-13 |
| Reject zero-duration/overlapping filler-content cuts at model boundary | Prevents render-time silent cleanup and forces malformed edit plans to fail early | 2026-02-13 |
| Enforce string↔seconds timestamp consistency in analysis models with 1s tolerance | Stops contradictory clip/cut timestamps from propagating into downstream ranking/render logic | 2026-02-13 |
| Validate provider-model compatibility and safe service host/port in config models | Prevents invalid runtime configuration from reaching service/client startup paths | 2026-02-13 |
| Run/resume schemas enforce typed stage windows with explicit started/completed/rejected outcomes | Keeps API responses truthful and invalid stage inputs as structured 422 errors | 2026-02-13 |
| Resume defaults to continuation through final stage unless until_stage is provided | Aligns operational behavior with user expectation for one-call recovery continuation | 2026-02-13 |
| Service client uses persistent HTTPX client plus endpoint-specific run/resume timeouts and typed HTTP status exceptions | Preserves backend parity while improving resilience for long-running pipeline requests | 2026-02-13 |
| Provider parse/schema failures raise explicit typed errors with structured details | Prevents silent empty-analysis "success" payloads and preserves actionable diagnostics | 2026-02-13 |
| Analyze outputs embed metadata.degraded_mode for transcript-only provider execution | Makes fallback degradation explicit to operators and downstream artifact consumers | 2026-02-13 |
| Gemini upload IDs are reused per proxy path with structured 429 classification | Reduces repeated upload overhead and keeps retry semantics deterministic/testable | 2026-02-13 |
| Production mode enforces API key auth on /jobs endpoints with explicit development bypass controls | Protects job-control surface in production while preserving local developer ergonomics | 2026-02-13 |
| Global exception handlers sanitize unhandled and HTTP 5xx responses to internal_error payloads | Prevents stack traces and internal error strings from leaking to API clients | 2026-02-13 |
| Supervisor runtime metadata records timeout state and infers last_known_stage from persisted job state | Makes hung/background progression observable and recoverable from runtime journal data | 2026-02-13 |
| Lifespan-managed periodic reconciliation plus /system/runtime diagnostics monitor stale/orphaned runs | Provides proactive correction and operator visibility between manual recovery calls | 2026-02-13 |
| Persist uploads in jobs/_uploads before service create_job | Keeps pipeline/service as source of truth for job directory lifecycle and removes orphan pre-job directories | 2026-02-13 |
| Streamlit preview/timeline metadata source is intermediate/metadata.json with logged legacy fallback | Aligns UI duration/timestamp reads with ingest outputs while preserving backward compatibility | 2026-02-13 |
| Marketing save/regenerate persists via review_state and analyze→review regeneration | Preserves review-governed editorial audit trail and avoids direct analysis.json mutation | 2026-02-13 |
| Render stage now reports explicit degraded/failed outcomes with per-platform status maps | Prevents hidden partial export failures from being reported as generic success | 2026-02-13 |
| Quality controls flow through run payload schemas into persisted job config and render runtime settings | Converts Streamlit quality widgets from display-only state into effective encoding behavior | 2026-02-13 |
| Ingest/render now enforce disk preflight and post-FFmpeg output existence checks | Fails early on low-capacity conditions and loudly on missing/empty artifacts | 2026-02-13 |
| Render enhancement chain is FFmpeg-native with explicit loudnorm fallback behavior | Keeps output quality deterministic even when optional normalization dependencies are unavailable | 2026-02-13 |
| Research query derivation uses deterministic metadata+transcript weighting with explicit fallback source labels | Prevents weak filename defaults from silently driving research quality | 2026-02-13 |
| YouTube API cache persistence is opt-in via cache_path with TTL pruning on load/lookup | Reduces repeated quota spikes across restarts without forcing global cache side effects | 2026-02-13 |
| Desktop lifecycle controls route through typed backend methods including service-backed delete actions | Converts desktop from monitor-only surface into full operator control plane | 2026-02-13 |
| Streamlit timeline edits persist as validated range edits into regenerated review/edit_plan artifacts | Enables true editorial timeline control instead of checkbox-only cut approvals | 2026-02-13 |
| Recovery UX surfaces /system/runtime diagnostics with on-demand /jobs/reconcile actions across desktop and Streamlit | Makes stale/orphaned runtime state visible and operator-actionable without filesystem inspection | 2026-02-13 |
| Coverage gates now require 45% overall plus providers/service/stages module thresholds | Strengthens runtime regression protection while keeping thresholds realistic for fixture-heavy media paths | 2026-02-13 |
| Operator docs now codify service auth headers, resume-through-completion, degraded-mode, and quality-control contracts | Keeps desktop/Streamlit/API behavior truthful for manual operations and incident response | 2026-02-13 |
| Review/CLI/UI export target keys are normalized from one canonical registry with default fallback safeguards | Prevents cross-surface platform key drift and malformed review-state payloads from silently changing render behavior | 2026-02-20 |
| Explicit CLI platform-key errors fail fast before review mutation while omitted input keeps stable defaults | Preserves operator safety for explicit input and backward compatibility for legacy default approve flows | 2026-02-20 |
| Enhancement defaults keep deesser enabled with conservative tuning while dereverb/color stay opt-in | Improves baseline quality without forcing heavyweight dependencies or surprising output changes | 2026-02-20 |
| Render preflight derives required FFmpeg filters from enabled enhancement toggles | Fails fast with actionable diagnostics before expensive render runs | 2026-02-20 |
| Dereverb preprocessing uses optional noisereduce with policy-driven warn-skip/fail fallback | Keeps baseline installs stable while supporting opt-in enhancement depth | 2026-02-20 |
| Color correction is limited to canonical normalize/grayworld/optional-eq filters | Avoids undocumented FFmpeg filter drift and keeps enhancement scope additive | 2026-02-20 |
| MarketingCopy schema now includes full 10-platform matrix including spotify/apple video variants | Prevents provider/model drift from stripping platform keys before artifacts/UI consume them | 2026-02-20 |
| Provider prompt contract enforces viral-impact but professional, platform-tailored copy for all marketing keys | Raises baseline copy quality and blocks generic one-size output regressions | 2026-02-20 |
| Analyze prompt context now injects compact trend signals from existing research/viral artifacts when present | Enables trend-aware copy generation without breaking no-research execution paths | 2026-02-20 |
| Marketing render output now enforces deterministic full-platform section ordering with adjacent audio/video variants | Prevents silent section loss and keeps artifact parity stable with marketing schema keys | 2026-02-20 |
| Streamlit marketing editor behavior is now driven by a canonical per-platform spec map | Centralizes title modes, description limits, and guidance so full-platform editing stays consistent and testable | 2026-02-20 |
| ThumbnailCandidate now carries bounded virality metadata fields with safe defaults | Preserves backward compatibility while exposing explicit ranking/recommendation context for thumbnail selection | 2026-02-20 |
| Provider thumbnail prompt contract now requires virality metadata and at least one recommendation signal | Prevents underspecified thumbnail candidates and strengthens selection evidence quality | 2026-02-20 |
| Review decisions now support ranked selected_thumbnails with selected_thumbnail legacy mirroring | Enables 1..3 ordered thumbnail picks while keeping old review_state payloads valid | 2026-02-20 |
| Analyze stage now materializes thumbnail preview images and stores relative image_path metadata in analysis payloads | Enables Streamlit review UI to render visual thumbnails without on-demand extraction cost | 2026-02-20 |
| Streamlit thumbnail selector now uses ranked toggle state (max 3) with explicit primary/alternate semantics | Makes operator thumbnail intent deterministic while preserving ranked order across reruns | 2026-02-20 |
| Ranked thumbnail persistence normalizes selected_thumbnails and mirrors rank #1 into selected_thumbnail | Maintains backward compatibility for legacy scalar consumers while enabling multi-select UX | 2026-02-20 |
| Thumbnail constraints are now typed per target (`youtube`, `spotify_video`, `apple_video`) with explicit source/policy metadata | Makes compliance rules operator-visible and deterministic across environments | 2026-02-20 |
| Render now derives and validates target-specific thumbnail artifacts before success reporting | Prevents silent success when selected target thumbnail requirements are unsatisfied | 2026-02-20 |
| Thumbnail MVP boundary is documented as single primary + optional alternates with per-platform assignment deferred | Locks scope and avoids hidden UX assumptions beyond current phase deliverable | 2026-02-20 |
| Snapping uses directional semantics with max-shift bounds for deterministic cut safety | Avoids over-trimming spoken words while keeping behavior predictable | 2026-02-21 |
| Phase 7 edit-plan schema evolved via additive optional fields only | Preserves compatibility for existing review/edit_plan payloads | 2026-02-21 |
| Explicit filler decisions take precedence over legacy index lists with deterministic fallback | Enables richer editorial control while keeping old jobs executable | 2026-02-21 |
| Smoothing policy defaults remain conservative but enabled for additive rollout | Improves splice quality without destabilizing existing render behavior | 2026-02-21 |
| Content transitions degrade to concat fallback when optional FFmpeg filters are unavailable | Prevents hard render failures on environments lacking acrossfade/xfade | 2026-02-21 |
| Transition durations are clamped by adjacent keep-segment ratio | Prevents short-segment transition overrun artifacts and filter failures | 2026-02-21 |
| Filler review UX is category-grouped with bulk actions plus explicit per-item keep/remove controls | Speeds editorial review while keeping final decisions deterministic | 2026-02-21 |
| UI persistence writes both filler_decisions and legacy approved_filler_cuts | Preserves backward compatibility for existing review/edit-plan consumers | 2026-02-21 |
| Review/edit-plan filler wiring is regression-locked for explicit and legacy decision paths | Prevents drift between Streamlit review state and render-time cut behavior | 2026-02-21 |
| FillerConfig splits word lists into disfluencies/hedge_words/custom_words with legacy words field merging into disfluency set | Backward compat: old config.yaml with only words:[...] continues to work unchanged | 2026-02-21 |
| protect_pause_threshold_ms=300ms fires pause-gate protection with >= semantics; protected fillers excluded from LLM triage | Prevents removal of meaningful pauses embedded in speech cadence | 2026-02-21 |
| Pause measurement uses raw word timestamps before padding; cut start/end retain padding_ms for render-safe splices | Keeps cut timing accurate while preserving smooth render boundaries | 2026-02-21 |
| Category priority hedge > custom > disfluency prevents hedge words in multiple lists from being misclassified | Ensures hedge words always route to LLM triage regardless of other list membership | 2026-02-21 |
| llm_triage_max_context_words serves double duty as context window N for context_before/context_after extraction | Single config knob controls both context budget and context field population | 2026-02-21 |
| LLM triage batch size is 20 with '---' separator for multi-filler prompts per call | Balances latency and token cost for gpt-4o-mini; parse splits on same separator | 2026-02-21 |
| Parse errors and disabled-flag path both produce safe_to_remove=False (never auto-remove when uncertain) | Conservative default prevents accidental removal of semantically important hedge fillers | 2026-02-21 |
| _load_triage_candidates extracted as helper returning None-or-list to keep _triage_fillers within PLR0911 return-statement limit | Keeps stage code compliant with ruff rules without noqa suppressions | 2026-02-21 |
| write_edit_plan action comes from _materialize_filler_decisions directly — no secondary protected override needed | _derive_editorial_action already handles protection; duplicate gate removed for clarity | 2026-02-21 |
| _create_initial_review_state uses _derive_editorial_action for triage-aware defaults | Protected fillers default to keep; disfluencies remove; LLM-safe hedges remove; uncleared hedges keep for editor review | 2026-02-21 |
| _filler_card_data helper centralizes Phase 8 display field extraction | Makes UI rendering and tests independent of field-access code; returns typed display dict | 2026-02-21 |
| silero-vad>=6.1 selected (NOT >=5.0) and opencv-python-headless (NOT opencv-python) for GPU extras | v6.x fixes torchaudio deprecation; headless avoids Qt display failures on WSL/server | 2026-02-21 |
| torch/torchaudio routed via pytorch-cu128 uv.sources (NOT cu121) | RTX 5060 Ti is Blackwell sm_120 requiring CUDA 12.8; cu121 fails at runtime | 2026-02-21 |
| De-breathing pass runs after word-boundary snapping, before merge/invert | Ensures extended ranges participate in merge step to handle overlapping extensions | 2026-02-21 |
| compute_noise_floor_correction uses strict less-than: exact threshold = correction applied | delta_db < threshold_db means at exactly threshold, condition is False; correction proceeds | 2026-02-21 |
| --exp flag used for RIFE (NOT --n which does not exist) | Corrected per Phase 8 research; --n and --cpu flags do not exist in practical-RIFE | 2026-02-21 |
| RIFE disabled by default (rife_enabled=False); pose_match_enabled=True with graceful cv2 fallback | Keeps baseline render unchanged while enabling pose matching without requiring opencv install | 2026-02-21 |
| Bridge clips copied to stable_dir before TemporaryDirectory cleanup | Ensures RIFE bridge clips survive tempdir lifecycle for filtergraph use | 2026-02-21 |
| Smoke test split into helper functions (_check_torch/_check_opencv/_resolve_rife_script) | Avoids PLR0911 return-statement limit in main() while keeping early returns per check | 2026-02-21 |
| noise_floor_correction strict less-than: exact threshold = correction applied | delta_db < threshold_db guard — at exactly threshold the condition is False, so correction fires | 2026-02-21 |
| Phase 8 integration tests use monkeypatch builtins.__import__ to simulate missing optional deps | Avoids uninstalling packages; simulates ImportError for silero_vad/librosa/cv2 in test environment | 2026-02-21 |
| Triage transport is provider-aware: gemini models use google.genai, others use openai (legacy fallback) | Sending gemini model names to OpenAI API would 404; provider dispatch required for correct routing | 2026-02-23 |
| API key gate uses provider-specific key: api_keys.gemini for gemini models, api_keys.openai for others | Key gate must match the transport layer — checking openai key for a gemini model would skip triage incorrectly | 2026-02-23 |
| Regression test explicitly forbids gpt-4o-mini, o1, o3-mini and other reasoning/OpenAI defaults | Prevents silent drift back to OpenAI; llm_triage_model must be gemini-2.5-flash-lite | 2026-02-23 |
| GPU extras use floor + upper bound pattern (>=X.Y,<NEXT_MAJOR) | Prevents silent breaking API changes from major version releases while enforcing current stable baseline | 2026-02-23 |
| RIFE subprocess passes --output <path> and --model <path> with cwd=rife_dir; collects from output_dir/img*.png; E2E testing verified 5 frames generated with these flags | Whether Practical-RIFE inference_img.py registers --output in argparse vs accepts it via parse_known_args is upstream-version-dependent; current implementation is E2E-verified working | 2026-02-23 |
| torch==2.10.* pinned baseline in smoke test and operator guide (not >=2.7 unpinned) | Reproducible GPU installs; prevents silent torch major-version drift on Blackwell hardware | 2026-02-23 |
| Operator guide explicitly forbids reasoning/CoT models for LLM triage (o1, gemini-3-pro, etc.) | Per-filler classification needs sub-second batch responses; reasoning models are too slow/expensive | 2026-02-23 |
| RIFE 4.26 exists (corrected from "does not exist"); 4.25 is recommended default to avoid artifacts | Research-verified: 4.26 released but 4.25 more stable for podcast content type | 2026-02-23 |
| fastmcp added to [dependency-groups] dev only — not project.optional-dependencies | Enforces production isolation; fastmcp is never required for pipeline stages or providers | 2026-02-24 |
| Empty __all__ = [] in mcp/__init__.py signals dev-only intent and prevents accidental re-exports | Clean import boundary between production code and dev MCP tooling | 2026-02-24 |
| MCP tools accept scalar inputs (str/float/bool); Path/Enum construction in wrapper | JSON-wire compatible; prevents Pydantic objects from crossing MCP transport boundary | 2026-02-24 |
| MCP error handling returns {error, operation} dict instead of raising | Prevents MCP client disconnects on toolkit failures; keeps session alive for retries | 2026-02-24 |
| ClaudeProvider uses tool_use with forced tool_choice to enforce JSON schema contract — no prose JSON parsing | Schema-constrained output prevents silent parse failures and removes regex/JSON extraction coupling | 2026-02-24 |
| SUPPORTED_CLAUDE_MODELS = {claude-sonnet-4-6, claude-haiku-4-5, claude-opus-4-6} in settings.py | Explicit model registry enforces valid model selection at config validation time | 2026-02-24 |
| AnalyzeStage.__init__ dispatches on provider name string (gemini/kimi/claude) for primary + fallback | Provider-dispatch pattern scales to new providers without duplicating initialization logic | 2026-02-24 |
| Implicit Kimi fallback preserved when fallback_provider=None and primary_provider != 'kimi' and KIMI_API_KEY present | Maintains backward compatibility for existing configs that relied on automatic Kimi fallback | 2026-02-24 |
| BrandingProfile.resolved_for_platform() returns new instance with empty platform_overrides | Resolved profiles are flat and cannot be re-resolved; signals downstream consumers | 2026-02-24 |
| brand_voice sanitized twice: at BrandingProfile construction and at prompt boundary in BaseProvider | Defense in depth for user-supplied text injected into LLM prompts | 2026-02-24 |
| brand_voice injected via transcript["brand_voice"] dict key rather than direct provider method parameter | Keeps provider analyze() signatures unchanged across all provider types | 2026-02-24 |
| BRAND VOICE block positioned after role statement, before TRANSCRIPT section in provider prompt | Frames copy direction without competing with JSON schema at prompt end | 2026-02-24 |
| load_active_profile() returns None when profile is unconfigured or file missing | All stages treat None as no-branding gracefully without branching | 2026-02-24 |
| hevc_nvenc is preferred codec for youtube_ultra; render resolves actual encoder at runtime via _resolve_video_encoder using HardwareEncoderInfo | Separates intent (preferred codec) from capability (available encoder) — predictable cross-machine behavior | 2026-02-24 |
| p010le (NVENC 10-bit) translates to yuv420p10le on libx265 software fallback | NVENC and x265 use different pixel format naming conventions for 10-bit HEVC | 2026-02-24 |
| AV1 codec without av1_experimental=True on PlatformSpec raises ValueError at config load | Zero silent AV1 activation — always an explicit operator opt-in | 2026-02-24 |
| hevc_nvenc + p010le + uhq/hq preset is forbidden (RTX artifact guard) — p7 required for RTX 5060 Ti | Known artifact regression on 9th-gen NVENC; p7 achieves equivalent quality without artifacts | 2026-02-24 |
| force_60fps_shortform gates on smoothing.force_60fps_shortform AND rife_enabled AND aspect_ratio in SHORT_FORM_ASPECT_RATIOS | Three-condition gate prevents silent uplift; all conditions must be explicitly enabled | 2026-02-24 |
| RIFE 30->60fps uplift runs before filtergraph construction so interpolated frames are the render base | Ensures any branding/caption burn-in or color filters operate on the 60fps content | 2026-02-24 |
| RifeBridge.uplift_fps raises NotImplementedError; _apply_shortform_60fps_rife catches and returns None | Whole-video RIFE uplift deferred; render continues gracefully with original input | 2026-02-24 |
| GPULease uses threading.Semaphore(1) for cross-job GPU serialization | Simple, reliable single-GPU contention guard without external dependencies | 2026-02-24 |
| Production controls persist in ReviewDecisions rather than separate state file | Keeps review contract as single source of truth for all operator decisions | 2026-02-24 |
| Brand Studio is a top-level Streamlit navigation page | Matches operator mental model of profile management as separate activity from editing | 2026-02-24 |
| Phase 9 ReviewDecisions fields default to None/False | Pre-Phase 9 review payloads load without error; backward compatibility preserved | 2026-02-24 |
| delete_profile() added to branding utility for CRUD completeness | Brand Studio UI requires full create/read/update/delete lifecycle | 2026-02-24 |
| Single Gemini backend replaces dual Imagen 4 / FLUX.1 Schnell routing | Eliminates Vertex AI auth complexity, VRAM/GPU requirements, and 3 optional dependencies | 2026-02-24 |
| Image bytes via part.inline_data.data (not part.as_image) | Avoids PIL/Pillow dependency for raw image bytes access | 2026-02-24 |
| _audit_with_gemini_pro defined but not wired into generation flow | Supports future compositional auditing without scope creep in this plan | 2026-02-24 |
| decisions.captions_enabled replaces config.branding.captions.enabled as burn-in gate | UI decision takes precedence over config.yaml — prevents Production sidebar from being silently ignored | 2026-02-24 |
| decisions.sound_kit_enabled gates _mix_stingers unconditionally | Stingers skip when False regardless of configured sound files — consistent UI-as-source-of-truth | 2026-02-24 |
| effective_profile_name resolved once from decisions.branding_profile_name with config fallback | Single resolution point before both _burn_captions and _mix_stingers — avoids redundant override logic | 2026-02-24 |
| Provider selectbox mutates config.models.provider in session state only — no config.yaml write | App never writes config files; st.caption explains how to persist permanently via env var or config.yaml | 2026-02-24 |
| _ASPECT_RATIO_OPTIONS defined at module level (not inside render function) | Avoids Streamlit lambda closure issues on reruns; format_func lambda safely indexes module-level list | 2026-02-24 |
| Caption aspect ratio cleared to None when captions_enabled is False | Prevents stale override value from silently applying when captions are re-enabled — UI intent is always explicit | 2026-02-24 |

### Roadmap Evolution

- Phase 4 added: Post-release hardening
- Phase 4 planned: research complete + 10 plan files created
- Phase 4 execution started: completed 04-01 runtime invariants hardening
- Phase 4 execution continued: completed 04-04 model/config validation hardening
- Phase 4 execution continued: completed 04-02 run/resume contract hardening
- Phase 4 execution continued: completed 04-05 provider reliability hardening
- Phase 4 execution continued: completed 04-06 service runtime hardening (auth gate + timeout heartbeats + reconciliation diagnostics)
- Phase 4 execution continued: completed 04-03 UI truthfulness hardening (full-run semantics + metadata path fix + review-governed marketing flow)
- Phase 4 execution continued: completed 04-07 render truthfulness and quality wiring hardening (platform failure contract + quality payload wiring + preflight/output checks)
- Phase 4 execution continued: completed 04-08 output quality backbone hardening (render enhancement + thumbnail artifacts + transcript-grounded research query/cache hardening)
- Phase 4 execution continued: completed 04-09 operator UX hardening (desktop full lifecycle controls, Streamlit timeline range editing, cross-surface recovery diagnostics + reconcile controls)
- Phase 4 execution completed: finished 04-10 confidence gates and docs alignment (provider reliability regressions, stronger coverage policy, runtime contract documentation)
- Phase 7 added: Smooth Editing & Filler Word Control
- Phase 5 added: Video Podcast Platforms
- Phase 5 execution started: completed 05-01 platform defaults and fail-fast schema validation for spotify/apple video targets
- Phase 5 execution continued: completed 05-02 render compliance wiring and truthful failure contracts
- Phase 5 execution completed: finished 05-03 apple_hls packaging and platform workflow-boundary documentation
- Phase 5 verified: 9/9 must-haves passed with no structural gaps
- Phase 5.1 execution started: completed 05.1-01 canonical export-target registry + review normalization contract
- Phase 5.1 execution continued: completed 05.1-02 Streamlit export UI wiring + normalized persistence/guidance coverage
- Phase 5.1 execution completed: finished 05.1-03 CLI approval parity + invalid-key diagnostics coverage
- Phase 5.1 verified: 9/9 must-haves passed with no structural gaps
- Phase 6 added: Audio/Video Enhancement & Podcast Video Platform
- Phase 6 researched: created `06-RESEARCH.md` with current stack/pitfalls and source-backed corrections (canonical FFmpeg color/de-esser filters, Demucs de-scoped)
- Phase 6 planned: created 3 execution plans (`06-01` config+preflight, `06-02` audio enhancements, `06-03` color correction) with enhancement-only boundary; crossfade/edit-core work deferred to future Phase 7
- Phase 6 execution started: completed 06-01 config contract + FFmpeg capability preflight + scope guardrails
- Phase 6 execution continued: completed 06-02 de-esser/adeclick integration + optional noisereduce dereverb path
- Phase 6 execution completed: finished 06-03 canonical color correction chain + safety boundary regressions
- Phase 6 verified: 9/9 must-haves passed with no structural gaps
- Phase 6.1 expanded: video marketing copy parity + thumbnail visual selection MVP (5 plans, 4 waves)
- Phase 6.1 execution started: completed 06.1-01 full-platform marketing schema/prompt contract lock with trend-context prompt wiring regressions
- Phase 6.1 execution continued: completed 06.1-02 full-platform marketing render/UI parity with trend-visible editing regressions
- Phase 6.1 execution continued: completed 06.1-03 thumbnail virality schema/prompt contract + ranked review-state selection compatibility
- Phase 6.1 execution continued: completed 06.1-04 analyze-stage thumbnail frame materialization + Streamlit visual ranked selector persistence
- Phase 6.1 execution completed: finished 06.1-05 per-target thumbnail compliance enforcement + MVP/deferred assignment docs
- Phase 6.1 verified: 7/7 must-haves passed with no structural gaps
- Phase 7 execution started: completed 07-01 foundation contracts (word-boundary snapping utils, additive edit-plan metadata, and per-filler decision fallback wiring)
- Phase 7 execution continued: completed 07-02 render smoothing integration (typed smoothing policy config, snapped cut handling, selective content transitions, and guardrail regressions)
- Phase 7 execution continued: completed 07-03 Streamlit editorial UX wiring (category-grouped filler controls, bulk actions, and review→edit-plan persistence regressions)
- Phase 7 execution completed: finished 07-04 integration hardening (cross-path compatibility regressions and Phase 7 operator runbook documentation)
- Phase 8 added: Intelligent Cut Quality
- Phase 8 execution started: completed 08-01-PLAN.md (FillerConfig typed category sub-lists, FillerCut Phase 8 enrichment fields, upgraded _detect_fillers)
- Phase 8 execution continued: completed 08-02-PLAN.md (FillerTriageResult model, _triage_fillers batched LLM triage helper, filler_triage.json artifact)
- Phase 8 execution continued: completed 08-03-PLAN.md (triage-aware editorial_action, _filler_card_data UI helper, Streamlit filler card Phase 8 display)
- Phase 8 execution continued: completed 08-04-PLAN.md (VAD breath detector, noise-floor matcher, render de-breathing + noise-floor passes, gpu optional deps)
- Phase 9 added: Automated Branding, Captions, and Multi-Track Sync (10 plans, 5 waves; spec v4 at docs/plans/2026-02-21-branding-automation-and-sync-spec_v4.md)
- Phase 9 execution started: completed 09-01-PLAN.md (FFmpeg media toolkit — 14 typed operations with Pydantic I/O across 5 groups)
- Phase 9 execution continued: completed 09-02-PLAN.md (FastMCP dev server: 14 tool wrappers, .mcp.json stdio config, 28 isolation/registration/invocation tests)

### Technical Notes

- Recommended stack: FFmpeg, faster-whisper, Streamlit, Typer, Pydantic
- Primary AI: Gemini (configurable; default gemini-2.5-flash) with Kimi K2.5 fallback
- Avoid: moviepy, python-ffmpeg wrappers, original whisper, langchain
- FastAPI service: lifespan pattern with Pipeline/Config/Supervisor on app.state
- Background runs: Supervisor wraps Pipeline.run in asyncio executor thread
- Asset resolution: env -> sidecar dir -> system PATH for binaries
- Model cache: env -> app_data -> project -> HF hub for model artifacts
- Sidecar naming: prepare-sidecars.mjs maps Node.js platform/arch to Rust target triples
- Release workflow: tag-triggered with manual dispatch, 4 platform targets
- GPU extras: `uv sync --extras gpu` installs silero-vad>=6.2,<7, librosa>=0.11,<1, opencv-python-headless>=4.13,<5
- torch/torchaudio: torch==2.10.* baseline via pytorch-cu128 index (CUDA 12.8 for Blackwell sm_120 / RTX 5060 Ti)
- LLM triage model: default gemini-2.5-flash-lite (google.genai transport); FORBIDDEN: o1, o1-mini, o3-mini, gemini-3-pro (reasoning/CoT too slow for per-filler batches)

### Open Questions

- (None)

### Blockers

- (None)

## Recent Activity

- 2026-01-29: Project initialized, requirements defined, roadmap created
- 2026-02-03: App research report completed
- 2026-02-04: Codebase map refreshed and planning docs updated
- 2026-02-04: Completed Phase 2 plans 02-01 through 02-05
- 2026-02-04: Verified Phase 2 goal (10/10 must-haves passed)
- 2026-02-05: Completed 03-01 through 03-06 (Phase 3 complete)
- 2026-02-05: Fixed Gemini model name (gemini-2.5-flash-latest -> gemini-2.5-flash)
- 2026-02-05: End-to-end smoke test passed (ingest -> transcribe -> analyze -> review)
- 2026-02-12: Added Phase 4 (Post-release hardening) to roadmap
- 2026-02-12: Planned Phase 4 with integrated research and 10 execution plans
- 2026-02-13: Completed 04-01-PLAN.md (stage validation + per-job lock + state reload)
- 2026-02-13: Completed 04-04-PLAN.md (strict model/config invariants + dedicated validation suites)
- 2026-02-13: Completed 04-02-PLAN.md (typed run/resume contracts + continuation semantics + service client parity hardening)
- 2026-02-13: Completed 04-05-PLAN.md (provider parse failure hardening + degraded fallback signaling + Gemini upload/retry reliability tests)
- 2026-02-13: Completed 04-06-PLAN.md (production auth gate + sanitized errors + supervisor timeout heartbeat + periodic reconciliation diagnostics)
- 2026-02-13: Completed 04-03-PLAN.md (truthful full-run UI action, canonical metadata/timeline loading, review-governed marketing save/regenerate flow)
- 2026-02-13: Completed 04-07-PLAN.md (render truthful partial-failure semantics, quality-control run payload wiring, ingest/render preflight and artifact verification guardrails)
- 2026-02-13: Completed 04-08-PLAN.md (concrete render enhancement + thumbnail artifacts, transcript-grounded research query derivation, persistent TTL cache restart behavior)
- 2026-02-13: Completed 04-09-PLAN.md (desktop full lifecycle control plane, validated timeline edit persistence, runtime diagnostics/reconcile controls in desktop + Streamlit)
- 2026-02-13: Completed 04-10-PLAN.md (provider reliability regressions, raised coverage gates, and runtime contract docs alignment)
- 2026-02-19: Added Phase 5 (Video Podcast Platforms) to roadmap for upcoming planning/execution
- 2026-02-19: Completed 05-01-PLAN.md (video-target defaults, compliance schema validation, and regression coverage)
- 2026-02-19: Completed 05-02-PLAN.md (render profile/level wiring, ffprobe compliance gates, structured compliance status reporting)
- 2026-02-19: Completed 05-03-PLAN.md (typed apple_hls config, deterministic playlist/segment checks, and truthful Apple/Spotify workflow docs)
- 2026-02-19: Verified Phase 5 goal (05-video-podcast-platforms-VERIFICATION.md, status: passed)
- 2026-02-20: Completed 05.1-01-PLAN.md (canonical export target registry, review-state normalization, and fallback regression coverage)
- 2026-02-20: Completed 05.1-02-PLAN.md (registry-driven Streamlit export options, normalized review-state persistence, and apple_hls boundary guidance tests)
- 2026-02-20: Completed 05.1-03-PLAN.md (CLI platform-key normalization, explicit invalid-key error contracts, and parsing regressions)
- 2026-02-20: Verified Phase 5.1 goal (05.1-streamlit-video-platform-ui-VERIFICATION.md, status: passed)
- 2026-02-20: Researched Phase 6 implementation approach and captured findings in `06-RESEARCH.md`
- 2026-02-20: Planned Phase 6 into three executable plans (`06-01`..`06-03`) with strict enhancement-only scope
- 2026-02-20: Completed 06-01-PLAN.md (typed enhancement config, FFmpeg capability preflight, and scope-boundary guardrails)
- 2026-02-20: Completed 06-02-PLAN.md (FFmpeg-native de-esser/adeclick chain and optional noisereduce dereverb fallback path)
- 2026-02-20: Completed 06-03-PLAN.md (canonical normalize/grayworld color correction path with bounded config defaults and safety regressions)
- 2026-02-20: Verified Phase 6 goal (06-audio-video-enhancement-podcast-video-platform-VERIFICATION.md, status: passed)
- 2026-02-20: Expanded Phase 6.1 plans to executable thumbnail MVP scope (`06.1-01`..`06.1-05`) with explicit per-target thumbnail compliance and deferred per-platform assignment UX
- 2026-02-20: Tightened Phase 6.1 marketing plans to require full-platform, trend-aware, viral-professional LLM copy generation with regression guardrails
- 2026-02-20: Completed 06.1-01-PLAN.md (full marketing platform matrix in model + provider prompt contract with viral-professional directives + analyze trend-context artifact injection + regressions)
- 2026-02-20: Completed 06.1-02-PLAN.md (render marketing doc full-matrix parity, canonical Streamlit marketing editor platform specs/limits, and trend-visible regression coverage across render/UI helpers)
- 2026-02-20: Completed 06.1-03-PLAN.md (thumbnail virality metadata contract in models/providers plus ranked 1..3 review-state selection with legacy selected_thumbnail mirroring)
- 2026-02-20: Completed 06.1-04-PLAN.md (analyze-stage thumbnail frame materialization, Streamlit visual ranked selector UX, and deterministic selected_thumbnail(s) persistence regressions)
- 2026-02-20: Completed 06.1-05-PLAN.md (typed per-target thumbnail specs, render compliance fail-fast validation, and explicit deferred per-platform thumbnail assignment docs)
- 2026-02-20: Verified 06.1 phase goal (`06.1-video-marketing-copy-thumbnail-visual-selection-VERIFICATION.md`, status: passed)
- 2026-02-21: Completed 07-01-PLAN.md (boundary snapping helpers, additive edit-plan metadata, and explicit per-filler decision fallback wiring)
- 2026-02-21: Completed 07-02-PLAN.md (typed smoothing config, transition-aware snapped edit filtergraph, and phase-compatibility transition regressions)
- 2026-02-21: Completed 07-03-PLAN.md (category-grouped filler review UI, bulk action semantics, and review-state/edit-plan wiring regressions)
- 2026-02-21: Completed 07-04-PLAN.md (integration regressions for review/edit-plan/render compatibility plus Phase 7 operator docs updates)
- 2026-02-21: Completed 08-01-PLAN.md (FillerConfig typed category sub-lists, FillerCut Phase 8 enrichment fields, upgraded _detect_fillers with category/pause/context/protection gate)
- 2026-02-21: Completed 08-02-PLAN.md (FillerTriageResult model, _triage_fillers batched LLM triage helper, filler_triage.json artifact, 25 passing tests)
- 2026-02-21: Completed 08-03-PLAN.md (triage-aware editorial_action in review stage, _filler_card_data UI helper, Streamlit filler card Phase 8 display)
- 2026-02-21: Completed 08-04-PLAN.md (VAD breath detector, noise-floor matcher, render de-breathing + noise-floor passes, 14 tests, gpu optional deps)
- 2026-02-21: Completed 08-05-PLAN.md (pose-match scanner via Farneback optical flow, RIFE bridge with --exp flag, render _apply_pose_match_pass + xfade fallback, 20 tests)
- 2026-02-21: Completed 08-06-PLAN.md (GPU smoke test, legacy compat regressions, triage-chain integration tests, Phase 8 disabled baseline regressions, operator guide)
- 2026-02-23: Re-executed 08-02-PLAN.md (triage Gemini transport fix — google.genai routing, provider-aware API key gate, model-drift regression guard)
- 2026-02-23: Re-executed 08-03-PLAN.md (review/UI wiring verification — all editorial_action paths and filler card display confirmed passing, no-op plan)
- 2026-02-23: Re-executed 08-04-PLAN.md (GPU extras version floors updated: silero-vad>=6.2,<7; librosa>=0.11,<1; opencv-python-headless>=4.13,<5; torch/torchaudio uv.sources routing verified correct)
- 2026-02-23: Re-executed 08-05-PLAN.md (RIFE bridge --output bug fix: removed --output flag, added cwd=work_dir + PYTHONPATH injection, changed glob to work_dir/output/img*.png; updated tests to verify upstream contract)
- 2026-02-23: Re-executed 08-06-PLAN.md (smoke test torch 2.10.x baseline; operator guide gemini-2.5-flash-lite default + forbidden reasoning model list + dep version floors; integration tests verified no-op — all 133 tests pass)
- 2026-02-24: Completed 09-01-PLAN.md (FFmpeg media toolkit — 14 typed operations, 5 operation groups, structured error model, HLS packaging)
- 2026-02-24: Completed 09-02-PLAN.md (FastMCP dev server: 14 MCP tools, lifespan hardware-encoder cache, .mcp.json stdio config, 28 tests)
- 2026-02-24: Completed 09-03-PLAN.md (Claude provider: tool_use schema contract, config wiring, analyze-stage dispatch, 44 regression tests)
- 2026-02-24: Completed 09-04-PLAN.md (HEVC 10-bit/NVENC youtube_ultra spec, AV1 experimental gating, force_60fps_shortform toggle, runtime encoder fallback chain + RIFE uplift stub in render)
- 2026-02-24: Completed 09-05-PLAN.md (BrandingProfile typed model, YAML serialization, platform override merge, BrandingConfig wired into Config, brand_voice prompt injection in BaseProvider)
- 2026-02-24: Re-executed 09-04-PLAN.md (completed Tasks 2+3: runtime encoder fallback chain in render, 24 new regression tests for NVENC detection, x265 fallback, shortform RIFE gating, legacy platform isolation; 152 total render tests)
- 2026-02-24: Completed 09-05-PLAN.md (BrandingProfile typed model, YAML serialization, platform override merge, BrandingConfig in settings, brand_voice prompt injection with double sanitization, 126 tests)
- 2026-02-24: Completed 09-10-PLAN.md (Brand Studio Streamlit tab, production sidebar controls, GPULease cross-job GPU serialization, 21 new tests, 260-line operator runbook)
- 2026-02-24: Phase 9 complete (10/10 plans executed, 1039 total tests passing)
- 2026-02-24: Completed 09-11-PLAN.md (Gemini Vision model pivot: replaced Imagen 4 / FLUX.1 with exclusive Gemini Vision thumbnail generation via google.genai SDK; 1031 tests passing)
- 2026-02-24: Post-Phase 9 UI audit completed — 7 gaps identified and documented in 09-UI-GAPS.md (2 missing, 4 partial UI gaps + 1 critical render wiring gap where Production sidebar decisions are saved but never consumed by render.py)
- 2026-02-24: Phase 9.12 added — Streamlit UI Gap Closure (closes all 7 gaps; awaiting planning)
- 2026-02-24: Completed 09.12-01-PLAN.md (GAP-7 render wiring: decisions.captions_enabled/sound_kit_enabled/branding_profile_name now gate render passes; youtube_ultra registered; caption_aspect_ratio and auto_duck_enabled fields added; 6 regression tests)
- 2026-02-24: Completed 09.12-02-PLAN.md (GAP-1/3A/3B/4: Settings provider selectbox for Claude/Gemini/Kimi; Anthropic API key status in Settings; caption aspect ratio selectbox in Production sidebar; sync artifact offset+confidence metrics display; slider range +/-5000ms; 1034 tests passing)

## Session Continuity

### Last session

2026-02-24 — Phase 9.12 execution continued. Completed 09.12-02 (GAP-1/3A/3B/4 UI closures: Settings provider select + Production sidebar caption/sync controls).

### Stopped at

Completed 09.12-02-PLAN.md — next step is 09.12-03 (sound kit UI wiring + auto-duck toggle).

### Resume file

None

---

*State updated: 2026-02-24 (09.12-01 executed -- GAP-7 render wiring fix; Phase 9.12 1/3 plans; 63/65 overall)*
