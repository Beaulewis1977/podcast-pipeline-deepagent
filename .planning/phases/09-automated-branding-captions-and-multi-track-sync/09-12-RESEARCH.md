# Phase 09-12: Streamlit UI Gap Closure - Research

**Researched:** 2026-02-24
**Domain:** Streamlit UI state management, Pydantic model extension, render-stage wiring
**Confidence:** HIGH

---

## Summary

Phase 09-12 closes 7 post-audit gaps in the Streamlit UI and render pipeline. The gaps split cleanly into three categories: (1) pure config-file additions with no behavior change, (2) UI-only additions that persist to `review_state.json`, and (3) a critical backend wiring fix where three `ReviewDecisions` fields exist in both the model and JSON but are completely ignored by `render.py` at render time.

All seven gaps are solvable without introducing new dependencies. The project already has Streamlit 1.53.1, Pydantic v2, and a well-established `ReviewDecisions` + `save_review_decisions()` + `_load_review_decisions()` pattern. The standard approach for every UI gap is: add field to `ReviewDecisions` (with safe default) → add UI control → persist via `save_review_decisions()` → consume in render. For backward compatibility, Pydantic v2 `model_validate_json` silently uses field defaults for any key absent from an existing JSON file — no migration needed.

The most dangerous gap (GAP-7) is a logic error, not a missing feature: `_render_video()` already receives `decisions: ReviewDecisions` but does not pass it to `_burn_captions()` or `_mix_stingers()`, which read `self.config.branding.*` directly. The fix is surgical: gate `_mix_stingers` call on `decisions.sound_kit_enabled`, replace the `self.config.branding.captions.enabled` gate with `decisions.captions_enabled`, and resolve the active branding profile from `decisions.branding_profile_name` before any profile-dependent call.

**Primary recommendation:** Fix GAP-7 first (render wiring) — it makes every other gap meaningful. Then add `youtube_ultra` to EXPORT_TARGETS (5 lines), add Claude provider selectbox + Anthropic key status, add caption aspect ratio (new `ReviewDecisions` field + selectbox + render pass-through), extend sync slider + display artifact, split sound kit toggles, and finally add file uploaders for logo/font.

---

## User Constraints

No CONTEXT.md exists for this phase. All decisions are at Claude's discretion within the requirements stated in the objective context above:

- All 7 gaps must be closed
- No regressions to existing Phase 9 features
- Backward compatibility with existing `review_state.json` files (new fields must use safe defaults)
- `uv run pytest tests/ -q` must pass
- `uv run mypy src/` must pass
- `uv run ruff check .` must pass

---

## Standard Stack

### Core (already present — no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Streamlit | 1.53.1 | UI controls, session state, file upload | Already project dependency |
| Pydantic v2 | >=2.0 | `ReviewDecisions` model, safe defaults | Project-wide config/model layer |
| Python `pathlib.Path` | stdlib | File persistence for uploaded assets | Already used throughout |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `structlog` | project default | Logging in render/review stages | All backend logging |
| `json` stdlib | stdlib | `sync_artifact.json` parsing | Reading sync offset + confidence |

**Installation:** No new packages required.

---

## Architecture Patterns

### Pattern 1: ReviewDecisions Extension (for GAP-4, GAP-5A)

**What:** Add optional field with safe default to `ReviewDecisions`. Pydantic v2 `model_validate_json` uses the default for missing keys, so old `review_state.json` files load without error.

**When to use:** Every time a new UI control needs to persist a decision for the render stage.

**Source:** Verified in `src/podcast_pipeline/stages/review.py` (existing fields all use `Field(default=...)` or `Field(default_factory=...)`). Backward compat confirmed: `_load_review_decisions()` calls `ReviewDecisions.model_validate_json()` and returns `ReviewDecisions()` on failure.

```python
# In ReviewDecisions (stages/review.py):
# Add after existing Phase 9 fields at ~line 82:

# Phase 09-12: Caption aspect ratio for ASS burn-in safe-zone selection.
# None means "infer from platform spec aspect_ratio".
# Set to "16:9", "9:16", or "1:1" for explicit override.
caption_aspect_ratio: str | None = None

# Phase 09-12: Independent auto-ducking toggle.
# When True, sidechaincompress ducking runs even if stingers are disabled.
auto_duck_enabled: bool = False
```

### Pattern 2: Production Sidebar UI Control + Persist (for GAP-1, GAP-3A, GAP-3B, GAP-4, GAP-5A, GAP-6A)

**What:** Add `st.selectbox` / `st.slider` / `st.checkbox` / `st.file_uploader` near an existing control in the Production sidebar or Brand Studio. Read current value from `decisions.<field>`. Compare new value to current, call `save_review_decisions()` if changed.

**When to use:** Every UI gap that needs to persist a user decision.

**Source:** Verified pattern from `app.py` lines 2625-2646 (existing persist-if-changed block).

```python
# Existing persist-if-changed pattern (verified, app.py ~line 2625):
needs_save = False
if new_profile_name != decisions.branding_profile_name:
    decisions.branding_profile_name = new_profile_name
    needs_save = True
# ... more field comparisons ...
if needs_save:
    save_review_decisions(job_dir, decisions)
```

**For new fields added to ReviewDecisions, extend the same block:**
```python
if caption_aspect_ratio != decisions.caption_aspect_ratio:
    decisions.caption_aspect_ratio = caption_aspect_ratio
    needs_save = True
if auto_duck_enabled != decisions.auto_duck_enabled:
    decisions.auto_duck_enabled = auto_duck_enabled
    needs_save = True
```

### Pattern 3: Render Stage Wiring (for GAP-7, GAP-4)

**What:** In `_render_video()`, read decision fields before calling sub-methods. Gate sub-method calls on boolean decision fields. Pass string decision fields as parameters to sub-methods instead of reading from `self.config`.

**When to use:** Whenever a UI-controlled decision must override a config-file default.

**Source:** Verified from `render.py` lines 1767-1984. `decisions: ReviewDecisions` is already a parameter of `_render_video()`.

```python
# GAP-7 fix — in _render_video() at ~line 1942:

# Resolve effective branding profile: decisions takes precedence over config.yaml
effective_profile_name: str | None = (
    decisions.branding_profile_name
    if decisions.branding_profile_name is not None
    else self.config.branding.active_profile
)

# Gate sound kit on decisions toggle (not unconditional)
if decisions.sound_kit_enabled:
    output_file = self._mix_stingers(
        video_path=output_file,
        output_dir=output_dir,
        platform=platform,
        edit_plan=edit_plan,
        src_duration=src_duration,
        profile_name_override=effective_profile_name,   # NEW param
    )

# Gate captions on decisions toggle (replaces self.config.branding.captions.enabled check)
if decisions.captions_enabled:
    captioned = self._burn_captions(
        video_path=output_file,
        output_dir=output_dir,
        job_dir=output_dir.parent.parent,
        platform=platform,
        spec=spec,
        aspect_ratio_override=decisions.caption_aspect_ratio,   # NEW param
        profile_name_override=effective_profile_name,           # NEW param
    )
```

**Sub-method signature additions:**
```python
def _burn_captions(
    self,
    video_path: Path,
    output_dir: Path,
    job_dir: Path,
    platform: str,
    spec: PlatformSpec,
    *,
    aspect_ratio_override: str | None = None,   # NEW - from decisions
    profile_name_override: str | None = None,   # NEW - from decisions
) -> Path | None:
    ...
    # Use override if provided, else fall back to spec-derived ratio
    aspect_ratio = (
        aspect_ratio_override
        if aspect_ratio_override is not None
        else (spec.aspect_ratio or "16:9").strip()
    )
    # Use override for profile loading instead of self.config.branding.active_profile
    active_profile_name = (
        profile_name_override
        if profile_name_override is not None
        else self.config.branding.active_profile
    )
    ...

def _mix_stingers(
    self,
    video_path: Path,
    output_dir: Path,
    platform: str,
    edit_plan: EditPlan | None,
    src_duration: float,
    *,
    profile_name_override: str | None = None,   # NEW - from decisions
) -> Path:
    ...
    # Use override instead of branding_cfg.active_profile
    active_profile_name = (
        profile_name_override
        if profile_name_override is not None
        else branding_cfg.active_profile
    )
```

### Pattern 4: ExportTarget Registration (for GAP-2)

**What:** Add one `ExportTarget(...)` entry to the `EXPORT_TARGETS` tuple in `src/podcast_pipeline/export_targets.py`. The `_get_platform_spec()` method in render.py already uses `getattr(self.config.platforms, platform, None)` — `youtube_ultra` is already defined in `PlatformSpecs`, so registration in `EXPORT_TARGETS` is the only missing piece.

**Source:** Verified — `export_targets.py` tuple controls which platforms appear in the UI toggle list. `render.py:1324` uses `getattr(self.config.platforms, platform, None)`, and `config.platforms.youtube_ultra` exists.

```python
# In EXPORT_TARGETS tuple (export_targets.py, after the 'facebook' entry):
ExportTarget(
    "youtube_ultra",
    "YouTube Ultra (HEVC 10-bit)",
    "video",
    "4K HEVC 10-bit @ 12 Mbps — NVENC GPU or libx265 CPU fallback",
),
```

### Pattern 5: File Uploader + Path Persistence (for GAP-6A)

**What:** Add `st.file_uploader` alongside (not replacing) the existing text input. When a file is uploaded, persist the bytes to `branding_dir / "assets" / filename`, set the text input's value to the saved path. Reuse the existing `_persist_uploaded_video()` pattern — same `getvalue()` → `write_bytes()` approach.

**Source:** `_persist_uploaded_video()` (app.py line 226) is the established template. `st.file_uploader` returns `UploadedFile | None`; `UploadedFile.getvalue()` returns `bytes`.

```python
# In _render_brand_studio_editor(), Visual Assets expander (~line 2376):

assets_dir = branding_dir / "assets"
assets_dir.mkdir(parents=True, exist_ok=True)

logo_upload = st.file_uploader(
    "Upload Logo",
    type=["png", "svg", "jpg", "jpeg"],
    key="brand_studio_logo_upload",
    help="Upload a logo file. Path field below will update automatically.",
)
if logo_upload is not None:
    dest = assets_dir / logo_upload.name
    dest.write_bytes(logo_upload.getvalue())
    logo_path = str(dest)   # overwrite the text_input default value

logo_path = st.text_input(
    "Logo Path",
    value=logo_path,   # now pre-filled by upload if one was provided
    key="brand_studio_logo",
    help="Path to logo image file (PNG/SVG). Leave empty for no logo.",
)
```

### Pattern 6: Sync Artifact Display (for GAP-3A)

**What:** Read `intermediate/sync_artifact.json` using the existing `_read_metadata_json()` helper (already in app.py). Display `offset_ms` and `confidence` as `st.metric()` or `st.info()`. Show above the manual override slider.

**Source:** `sync.py` line 101 shows the JSON keys: `offset_ms`, `confidence`, `low_confidence`. `_read_metadata_json()` (app.py line 249) handles parse errors gracefully.

```python
# In the Production sidebar, above the manual sync offset slider (~line 2613):
sync_artifact_path = job_dir / "intermediate" / "sync_artifact.json"
if sync_artifact_path.exists():
    artifact = _read_metadata_json(sync_artifact_path)
    if artifact:
        detected_ms = artifact.get("offset_ms", 0.0)
        confidence = artifact.get("confidence", 0.0)
        low_conf = artifact.get("low_confidence", False)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Auto-detected Offset", f"{detected_ms:+.0f} ms")
        with col2:
            conf_label = f"{confidence:.0%}"
            st.metric("Sync Confidence", conf_label)
        if low_conf:
            st.warning("Low confidence sync — consider setting manual offset below.")
```

### Pattern 7: Provider Selectbox in Settings (for GAP-1)

**What:** Replace the disabled text input for "Provider" in the AI Models expander with a `st.selectbox`. Persist the selection by mutating `st.session_state.config.models.provider` — the config is already cached in session state via `get_config()`. Add `ANTHROPIC_API_KEY` status line in the API Keys expander.

**Source:** `SUPPORTED_MODEL_PROVIDERS` is `{"gemini", "kimi", "claude"}` in `settings.py:13`. `get_config()` stores the mutable Config in `st.session_state.config`. `config.api_keys.anthropic` is already populated from `ANTHROPIC_API_KEY` env var (settings.py:899,909).

**Important constraint:** Provider selection in the Settings page mutates the in-memory `config.models.provider` for the current session. This does not persist to `config.yaml` — the operator must re-select on each session start, or edit `config.yaml` manually. This is intentional: the app does not write config files.

```python
# In render_settings(), AI Models expander (~line 2761):
from podcast_pipeline.config.settings import SUPPORTED_MODEL_PROVIDERS

config = get_config()
provider_options = sorted(SUPPORTED_MODEL_PROVIDERS)
current_provider_idx = (
    provider_options.index(config.models.provider)
    if config.models.provider in provider_options
    else 0
)
selected_provider = st.selectbox(
    "Provider",
    options=provider_options,
    index=current_provider_idx,
    key="settings_provider_select",
)
if selected_provider != config.models.provider:
    config.models.provider = selected_provider
    # Note: does NOT persist to config.yaml — session-only change

# In API Keys expander (~line 2776), add after YouTube line:
st.markdown(
    f"- Anthropic: {'✅ Configured' if config.api_keys.anthropic else '❌ Not set'}"
)
```

### Recommended Execution Order

1. `review.py` — add `caption_aspect_ratio` and `auto_duck_enabled` fields (backward-safe, required for all later changes)
2. `render.py` — fix GAP-7 wiring (`_render_video`, `_burn_captions`, `_mix_stingers`)
3. `export_targets.py` — add `youtube_ultra` entry (5 lines)
4. `app.py` — add Claude provider selectbox + Anthropic key status (GAP-1)
5. `app.py` — add caption aspect ratio selectbox + wire to ReviewDecisions (GAP-4)
6. `app.py` — extend sync slider range + add artifact display (GAP-3A, GAP-3B)
7. `app.py` — split sound kit into stingers + ducking checkboxes (GAP-5A)
8. `app.py` — add file uploaders for logo/font (GAP-6A)
9. Tests — render wiring tests (GAP-7), round-trip tests (GAP-4)

### Recommended Project Structure (unchanged)

```
src/podcast_pipeline/
├── stages/
│   ├── review.py          # Add caption_aspect_ratio, auto_duck_enabled fields
│   └── render.py          # Fix _render_video, _burn_captions, _mix_stingers
├── export_targets.py      # Add youtube_ultra ExportTarget entry
└── ui/
    └── app.py             # All UI gap fixes (7 UI changes)
tests/
├── test_render.py         # New render wiring tests (GAP-7)
└── test_ui_app.py         # New round-trip / persistence tests (GAP-4)
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File upload + path persistence | Custom multipart form / base64 encode | `st.file_uploader` + `UploadedFile.getvalue()` + `Path.write_bytes()` | Streamlit handles browser file transfer; `_persist_uploaded_video()` is the established pattern |
| Backward-compatible model extension | JSON schema migration scripts | Pydantic v2 field defaults | `model_validate_json` uses `default=` / `default_factory=` for absent keys; no migration needed |
| UI state across reruns | Custom `st.session_state` dicts | Streamlit widget `key=` parameter + `save_review_decisions()` | Keys give widgets stable identity across reruns; JSON file is the persistence layer |
| Config mutation for provider selection | Writing `config.yaml` from the UI | Mutate `st.session_state.config.models.provider` | Session-only mutation is appropriate; the app never writes config files |
| Sync offset display | Custom artifact polling / file watch | `_read_metadata_json(sync_artifact_path)` + `st.metric()` | `_read_metadata_json` already handles errors; Streamlit re-runs on interaction |

**Key insight:** All persistence in this app flows through one of two channels: (a) `save_review_decisions(job_dir, decisions)` for per-job UI decisions, or (b) `save_profile(profile, branding_dir)` for branding profiles. Never introduce a third channel.

---

## Common Pitfalls

### Pitfall 1: Adding ReviewDecisions field without a safe default
**What goes wrong:** New field with no default causes `ValidationError` when loading old `review_state.json` files (missing key is treated as required). Tests that construct `ReviewDecisions(review_complete=True)` without the new field also fail.
**Why it happens:** Pydantic v2 treats fields without defaults as required.
**How to avoid:** Always provide `Field(default=...)` or `Field(default_factory=...)`. For bool fields: `default=False`. For optional str: `default=None`. Never make a new ReviewDecisions field required.
**Warning signs:** `mypy` will not catch this; `pytest` on any existing `ReviewDecisions()` construction will fail at test time if the field is required.

### Pitfall 2: Gating caption burn-in on `self.config.branding.captions.enabled` instead of `decisions.captions_enabled`
**What goes wrong:** GAP-7 is not actually fixed — the UI checkbox has no effect, render still reads config YAML.
**Why it happens:** The existing code at render.py:1971 checks `self.config.branding.captions.enabled` which is `False` by default. After the fix, it must check `decisions.captions_enabled` instead (or in addition, with decisions taking precedence).
**How to avoid:** Replace the `if self.config.branding.captions.enabled:` guard entirely with `if decisions.captions_enabled:`. Do not AND them — that would require the operator to also set the YAML flag.
**Warning signs:** Caption integration test passes (YAML gate is False by default so captions are skipped) but a manual test with the UI checkbox enabled shows no captions.

### Pitfall 3: Calling `_mix_stingers` unconditionally after the fix
**What goes wrong:** `_mix_stingers` is called even when `decisions.sound_kit_enabled = False`. The method already has an early-out when no sound assets are configured, but operators who want to suppress stingers on a job with a configured profile cannot.
**Why it happens:** The call at render.py:1944 has no gate — it is always reached.
**How to avoid:** Wrap the `_mix_stingers` call in `if decisions.sound_kit_enabled:`. The method's internal `has_any_sound` guard becomes a secondary guard.

### Pitfall 4: Breaking existing `_burn_captions` and `_mix_stingers` signatures in tests
**What goes wrong:** Adding new `profile_name_override` and `aspect_ratio_override` parameters to `_burn_captions` and `_mix_stingers` without keyword-only markers (`*`) causes positional call-site breaks in tests.
**Why it happens:** Both methods are called directly in some tests that may pass positional args.
**How to avoid:** Add new parameters as keyword-only (after `*`) with defaults of `None`. Existing call sites that do not pass them will continue to work unchanged.

### Pitfall 5: Streamlit widget key collision when adding new controls
**What goes wrong:** Two widgets share the same `key=` string → Streamlit raises `DuplicateWidgetID` or silently uses the first widget's value for both.
**Why it happens:** The Production sidebar renders in a per-job context using `f"prod_*_{job_id}"` keys. New widgets must follow the same pattern.
**How to avoid:** Every new widget key must follow the `f"prod_{name}_{job_id}"` format (Production sidebar) or `f"brand_studio_{name}"` (Brand Studio). Check existing keys before adding.

### Pitfall 6: File uploader re-upload on every Streamlit rerun
**What goes wrong:** `st.file_uploader` returns the uploaded file on every rerun while the file is in the uploader. If the `write_bytes()` call happens unconditionally, the file is re-written repeatedly. This is harmless but noisy in logs.
**Why it happens:** Streamlit's execution model re-runs the whole script on any widget interaction.
**How to avoid:** The idiomatic pattern is `if logo_upload is not None: dest.write_bytes(...)` — this is fine because re-writing the same bytes to the same path is idempotent. No special guard needed.

### Pitfall 7: `youtube_ultra` appearing in export panel but failing in render due to audio_only check
**What goes wrong:** `youtube_ultra` is a video platform (`audio_only=False`, no `audio_only` field set), but `_render_platform` checks `spec.audio_only` and routes to `_render_audio_only()` if True. The youtube_ultra spec does NOT set `audio_only`, so it defaults to `False` — correct. The HLS branch checks `platform == "apple_hls" or spec.container == "hls"` — also not matched. So `youtube_ultra` routes to `_render_video()` correctly.
**Verification:** `PlatformSpec.audio_only` defaults to `False` (verified in settings.py). Container is `"mp4"`. No special guard needed.

### Pitfall 8: `SUPPORTED_EXPORT_PLATFORM_SET` not updated when adding to `EXPORT_TARGETS`
**What goes wrong:** Adding to `EXPORT_TARGETS` tuple automatically updates `SUPPORTED_EXPORT_PLATFORMS` and `SUPPORTED_EXPORT_PLATFORM_SET` (both are derived from the tuple). No separate update needed.
**Verification:** Lines 41-42 of `export_targets.py`:
```python
SUPPORTED_EXPORT_PLATFORMS: tuple[str, ...] = tuple(target.key for target in EXPORT_TARGETS)
SUPPORTED_EXPORT_PLATFORM_SET: frozenset[str] = frozenset(SUPPORTED_EXPORT_PLATFORMS)
```

---

## Code Examples

Verified patterns from codebase source:

### ReviewDecisions: safe new field (backward-compatible)
```python
# Source: src/podcast_pipeline/stages/review.py (existing field pattern)
# All new fields MUST have defaults — Pydantic v2 uses defaults for absent JSON keys

caption_aspect_ratio: str | None = None   # None = infer from spec
auto_duck_enabled: bool = False            # False = off by default
```

### ExportTarget registration (GAP-2)
```python
# Source: src/podcast_pipeline/export_targets.py (verified structure)
ExportTarget(
    "youtube_ultra",
    "YouTube Ultra (HEVC 10-bit)",
    "video",
    "4K HEVC 10-bit @ 12 Mbps — NVENC GPU or libx265 CPU fallback",
),
```

### Render wiring: branding profile resolution (GAP-7)
```python
# Source: render.py pattern — decisions already available in _render_video()
# Precedence: decisions > config.yaml active_profile
effective_profile_name: str | None = (
    decisions.branding_profile_name
    if decisions.branding_profile_name is not None
    else self.config.branding.active_profile
)
```

### Render wiring: captions gate (GAP-7)
```python
# Source: render.py ~line 1971 (REPLACE the existing check)
# Before: if self.config.branding.captions.enabled:
# After:
if decisions.captions_enabled:
    captioned = self._burn_captions(
        video_path=output_file,
        output_dir=output_dir,
        job_dir=output_dir.parent.parent,
        platform=platform,
        spec=spec,
        aspect_ratio_override=decisions.caption_aspect_ratio,
        profile_name_override=effective_profile_name,
    )
```

### Render wiring: stinger gate (GAP-7)
```python
# Source: render.py ~line 1944 (WRAP existing call)
# Before: output_file = self._mix_stingers(...)  # unconditional
# After:
if decisions.sound_kit_enabled:
    output_file = self._mix_stingers(
        video_path=output_file,
        output_dir=output_dir,
        platform=platform,
        edit_plan=edit_plan,
        src_duration=src_duration,
        profile_name_override=effective_profile_name,
    )
```

### Caption aspect ratio selectbox (GAP-4)
```python
# Source: app.py pattern — follows existing controls in Production sidebar
ASPECT_RATIO_OPTIONS = ["16:9", "9:16", "1:1"]
current_ratio = decisions.caption_aspect_ratio or "16:9"
current_ratio_idx = ASPECT_RATIO_OPTIONS.index(current_ratio) if current_ratio in ASPECT_RATIO_OPTIONS else 0

caption_aspect_ratio = st.selectbox(
    "Caption Aspect Ratio",
    options=ASPECT_RATIO_OPTIONS,
    index=current_ratio_idx,
    key=f"prod_caption_aspect_ratio_{job_id}",
    help="Select safe-zone template for ASS caption burn-in.",
)
# Store None when "16:9" (default) to keep JSON compact; still valid
new_ratio = caption_aspect_ratio if caption_aspect_ratio != "16:9" else None
```

### Sync artifact display (GAP-3A)
```python
# Source: sync.py:101 shows keys; _read_metadata_json() at app.py:249 handles errors
sync_artifact_path = job_dir / "intermediate" / "sync_artifact.json"
if sync_artifact_path.exists():
    artifact = _read_metadata_json(sync_artifact_path)
    if artifact:
        col1, col2 = st.columns(2)
        col1.metric("Auto-detected Offset", f"{artifact.get('offset_ms', 0.0):+.0f} ms")
        col2.metric("Sync Confidence", f"{artifact.get('confidence', 0.0):.0%}")
        if artifact.get("low_confidence"):
            st.warning("Low confidence — consider setting manual override below.")
```

### File uploader pattern (GAP-6A)
```python
# Source: _persist_uploaded_video() at app.py:226 — same getvalue()/write_bytes() idiom
assets_dir = branding_dir / "assets"
assets_dir.mkdir(parents=True, exist_ok=True)

logo_upload = st.file_uploader(
    "Upload Logo",
    type=["png", "svg", "jpg", "jpeg"],
    key="brand_studio_logo_upload",
    help="Uploads save to the branding assets directory automatically.",
)
if logo_upload is not None:
    dest = assets_dir / logo_upload.name
    dest.write_bytes(logo_upload.getvalue())
    logo_path = str(dest)   # pre-fill the text_input below
```

---

## State of the Art

| Old Approach | Current Approach | Impact for 09-12 |
|--------------|-----------------|-----------------|
| Read `self.config.branding.*` directly in render sub-methods | Pass `profile_name_override` as keyword-only param | Required for GAP-7: sub-methods become testable with mock decisions |
| `captions.enabled` in config YAML gates burn-in | `decisions.captions_enabled` gates burn-in | Required for GAP-7: UI checkbox becomes meaningful |
| Unconditional `_mix_stingers()` call | Gate on `decisions.sound_kit_enabled` | Required for GAP-7: UI checkbox becomes meaningful |
| `EXPORT_TARGETS` has 11 entries | 12 entries (adding `youtube_ultra`) | Required for GAP-2: toggle appears in export panel |

---

## Open Questions

1. **Should `caption_aspect_ratio = None` mean "infer from spec" or "always 16:9"?**
   - What we know: `_burn_captions()` currently uses `(spec.aspect_ratio or "16:9").strip()` — spec-derived.
   - Recommendation: `None` means "use spec-derived aspect ratio" (preserves current behavior). Only override when operator explicitly selects a different ratio. Store `None` in `ReviewDecisions` for the "16:9 / default" case to keep JSON compact.

2. **Should the provider selectbox in Settings persist to config.yaml?**
   - What we know: The app never writes `config.yaml`. The config is cached in `st.session_state.config`.
   - Recommendation: Session-only mutation (`config.models.provider = selected_provider`). Add a visible note in the UI: "This change is session-only. Edit config.yaml to make it permanent."

3. **GAP-5B (per-job stinger path override) — in or out of 09-12?**
   - Priority is P3 (lowest). The context states it's in scope but lowest priority.
   - Recommendation: Include if time permits, but treat as optional stretch goal. The fix is adding `override_intro_path`, `override_transition_path`, `override_outro_path` to `ReviewDecisions` and text inputs in the Production sidebar. Not included in P0/P1/P2 planning.

4. **GAP-6B (platform override interactive edit) — in or out?**
   - Also P3. Complex form (platform selectbox + dynamic key/value pairs).
   - Recommendation: Out of scope for 09-12 unless explicitly requested. The existing "Edit YAML directly" note is acceptable for power users.

---

## Sources

### Primary (HIGH confidence)
- `src/podcast_pipeline/stages/review.py` — `ReviewDecisions` model, field defaults, Pydantic v2 behavior
- `src/podcast_pipeline/stages/render.py` — `_render_video()`, `_burn_captions()`, `_mix_stingers()`, exact line numbers verified
- `src/podcast_pipeline/export_targets.py` — `EXPORT_TARGETS` tuple, derivation of `SUPPORTED_EXPORT_PLATFORM_SET`
- `src/podcast_pipeline/config/settings.py` — `PlatformSpecs.youtube_ultra`, `APIKeysConfig.anthropic`, `SUPPORTED_MODEL_PROVIDERS`, `DuckingConfig`
- `src/podcast_pipeline/ui/app.py` — Production sidebar pattern, `save_review_decisions()`, `_persist_uploaded_video()`, `_read_metadata_json()`, session state patterns, key naming conventions
- `src/podcast_pipeline/utils/sync.py` — `SyncResult` fields (`offset_ms`, `confidence`, `low_confidence`, `no_clap`)
- Streamlit 1.53.1 `help(st.file_uploader)` — confirmed `UploadedFile.getvalue()` returns `bytes`, `UploadedFile` is a `BytesIO` subclass

### Secondary (MEDIUM confidence)
- `.planning/phases/09-automated-branding-captions-and-multi-track-sync/09-UI-GAPS.md` — gap definitions, line number estimates, root cause analysis

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project, versions verified
- Architecture patterns: HIGH — all patterns verified directly in source code
- Pitfalls: HIGH — all pitfalls derived from direct code inspection, not inferred
- Render wiring fix: HIGH — root cause at exact lines confirmed (render.py:1944, 1971, _burn_captions:2021, _mix_stingers:3700-3726)
- ExportTarget fix: HIGH — mechanism verified (`_get_platform_spec` uses `getattr`, `youtube_ultra` exists in `PlatformSpecs`)
- Backward compatibility: HIGH — Pydantic v2 `model_validate_json` with field defaults verified as the existing pattern used by all Phase 9 fields

**Research date:** 2026-02-24
**Valid until:** 2026-03-10 (stable internal codebase; no external library changes needed)
