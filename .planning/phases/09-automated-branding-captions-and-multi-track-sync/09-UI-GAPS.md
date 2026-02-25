# Phase 9 Streamlit UI Coverage Gaps

**Audited:** 2026-02-24
**Auditor:** Claude Code (Explore agent, post-verification)
**Source:** `src/podcast_pipeline/ui/app.py`
**Purpose:** Input for research + gap-closure planning

---

## Summary

Phase 9 delivered 11 backend plans successfully. Post-execution UI audit identified 2 fully missing UI
surfaces, 4 partial UI gaps, and 1 critical backend wiring gap where UI controls save data but render
ignores it entirely. Existing Phase 9 features that work correctly in UI are also noted.

---

## MISSING — Completely Inaccessible

### GAP-1: Claude Provider Selection

**Feature:** Phase 9 added `providers/claude_provider.py` and registered it in `SUPPORTED_MODEL_PROVIDERS`.
**Problem:** The Settings page (`render_settings()`) displays provider config in read-only `disabled=True`
text inputs. There is no dropdown, radio button, or any interactive control to select "claude" as the
analysis provider at runtime. Users must hand-edit `config.yaml` or environment variables.

Additionally, the API Keys expander shows status for Gemini, Kimi, and YouTube — but not for
`ANTHROPIC_API_KEY`, so users have no visual feedback that their Claude key is configured correctly.

**Affected file:** `src/podcast_pipeline/ui/app.py` — Settings page, AI Models expander (~line 2760)
**Backend ready:** Yes — `ClaudeProvider` is fully implemented and tested (09-03-PLAN.md)
**Fix scope:**
- Add provider selectbox (`gemini` / `kimi` / `claude`) to Settings or job creation flow
- Show `ANTHROPIC_API_KEY` status in the API Keys expander alongside Gemini/Kimi keys
- Persist provider selection through review state or config mutation

---

### GAP-2: `youtube_ultra` / HEVC 10-bit Export Target

**Feature:** Phase 9 added a `youtube_ultra` PlatformSpec in `config/settings.py` with `hevc_nvenc`,
`main10` 10-bit profile, 4K resolution at 12 Mbps, with software `libx265` fallback.
**Problem:** `youtube_ultra` is not registered in the `EXPORT_TARGETS` registry
(`src/podcast_pipeline/config/export_targets.py`). The export panel's platform toggles are driven
entirely by that registry. Since `youtube_ultra` is absent, no toggle ever appears for it.

The export panel's Quality Settings slider (`draft / standard / high / ultra`) is unrelated — "ultra"
there maps to FFmpeg preset `veryslow` (encoding speed), not to the HEVC 10-bit profile.

No codec or bit-depth selector exists anywhere in the export panel.

**Affected files:**
- `src/podcast_pipeline/config/export_targets.py` — missing `youtube_ultra` entry
- `src/podcast_pipeline/ui/app.py` — export panel (~line 1981)
**Backend ready:** Yes — PlatformSpec, NVENC detection, and fallback chain implemented (09-04-PLAN.md)
**Fix scope:**
- Register `youtube_ultra` in `EXPORT_TARGETS` with correct label, description, and icon
- Optionally: surface which encoder was actually used (NVENC vs libx265) in the render output panel

---

## PARTIAL — Exists but Incomplete

### GAP-3: Audio Sync — Missing Offset Display + Slider Range

**Feature:** Phase 9 added bounded cross-correlation audio sync (`utils/sync.py`). Manual override
slider was added to the Production sidebar.

**Sub-gap A — Auto-detected offset not displayed:**
The manual sync offset slider (`st.slider`, lines 2615-2623) says "0 = use auto-detected value" in
its help text, but the auto-detected offset computed by `utils/sync.py` and written to
`intermediate/sync_artifact.json` is never read and displayed to the user. Operators cannot see
what offset was detected or how confident the detection was, making it impossible to judge
whether a manual override is warranted.

**Sub-gap B — Slider range mismatch:**
The feature spec (09-07-PLAN.md) states "±5000 ms manual fallback slider." The actual slider in
`app.py` is `min_value=-2000.0, max_value=2000.0` — half the specified range. For multi-camera
setups or longer audio drift, ±2000ms may be insufficient.

**Affected file:** `src/podcast_pipeline/ui/app.py` — Production sidebar (~line 2615)
**Fix scope:**
- Read `intermediate/sync_artifact.json` and display detected offset + confidence score
- Extend slider range to ±5000ms per spec

---

### GAP-4: ASS Captions — No Aspect Ratio Selector

**Feature:** Phase 9 added `utils/captions.py` with three aspect-ratio safe-zone templates:
`"16:9"` (landscape), `"9:16"` (vertical/Reels), `"1:1"` (square/Instagram). The `generate_ass()`
function accepts `aspect_ratio` as a parameter and selects the appropriate safe zone.

**Problem:** No UI control exists to select the aspect ratio for caption burn-in. The aspect ratio
defaults to `"16:9"` in all cases. Users producing vertical short-form or square content cannot
select the correct safe zone, meaning captions will render in the wrong region for non-landscape
exports.

**Affected file:** `src/podcast_pipeline/ui/app.py` — Production sidebar (near caption toggle, ~line 2590)
**Fix scope:**
- Add `st.selectbox("Caption Aspect Ratio", ["16:9", "9:16", "1:1"])` near the caption enable toggle
- Wire selection into the render payload so `generate_ass()` receives the correct aspect_ratio arg

---

### GAP-5: Production Sound Kits — Indivisible Toggle + No Per-Job Stinger Picker

**Feature:** Phase 9 added production sound kits (intro/transition/outro stingers) with
`sidechaincompress` auto-ducking in `utils/audio_mix.py`.

**Sub-gap A — Auto-ducking not independently controllable:**
The "Enable Sound Kit" checkbox (line 2598) enables both stinger mixing AND auto-ducking together.
There is no separate toggle to enable ducking-only (useful when background music is provided by
the user but no stingers are needed) or stingers-without-ducking.

**Sub-gap B — No per-job stinger file override:**
Intro/transition/outro stinger paths are configured per-branding-profile in the Brand Studio
(`st.text_input` fields at lines 2448-2466 in the Sound Kit expander). There is no per-job
override in the Production sidebar. If a user wants to use a different stinger for one specific
job without changing their active profile, they cannot.

**Affected file:** `src/podcast_pipeline/ui/app.py` — Production sidebar (~line 2598) and Brand Studio (~line 2448)
**Fix scope:**
- Split sound kit checkbox into: "Enable Stingers" + "Enable Auto-Ducking" (separate checkboxes)
- Optionally: add per-job stinger path override fields in Production sidebar

---

### GAP-6: BrandingProfile — Logo/Font File Upload + Read-Only Platform Overrides

**Feature:** Phase 9 added full BrandingProfile CRUD in the Brand Studio tab.

**Sub-gap A — Logo and font are path-input only:**
Logo path (line 2378) and font path (line 2403) are plain `st.text_input` fields. There is no
`st.file_uploader` for either. Users must know the server-side absolute or relative path. This is
a significant usability barrier for non-technical operators who want to upload branding assets.

**Sub-gap B — Platform overrides are read-only:**
The Platform Overrides expander (lines 2468-2495) renders existing overrides as disabled text inputs
with the note "Edit the YAML file directly to add them." There is no UI to add, modify, or remove
platform override entries interactively.

**Affected file:** `src/podcast_pipeline/ui/app.py` — Brand Studio tab (~line 2378, ~line 2468)
**Fix scope:**
- Replace logo/font text inputs with `st.file_uploader` that saves to a known assets directory
  and populates the path field automatically
- Add "Add Override" form for platform overrides (platform selectbox + key/value fields)

---

---

## CRITICAL BACKEND WIRING GAP — UI Saves Data, Render Ignores It

### GAP-7: Production Sidebar Decisions Not Consumed by Render Stage

**Discovery:** Found during implementation investigation, not visible in UI-only audit.

**What is broken:** Three Phase 9 `ReviewDecisions` fields are persisted to `review_state.json`
by the Production sidebar UI but are **completely ignored by `render.py`** at render time:

| ReviewDecisions field | UI control | What render actually does |
|---|---|---|
| `captions_enabled` | "Enable Captions" checkbox (app.py ~line 2590) | Ignores this field. Gates caption burn-in on `self.config.branding.captions.enabled` (static config YAML only). |
| `sound_kit_enabled` | "Enable Sound Kit" checkbox (app.py ~line 2598) | Ignores this field. Always calls `_mix_stingers()` unconditionally — stingers run if sound files are configured, regardless of this toggle. |
| `branding_profile_name` | Branding Profile selectbox (app.py ~line 2580) | Ignores this field. Uses `self.config.branding.active_profile` (static config YAML only). |

**Root cause:** `_render_video()` receives `decisions` as a parameter but does not pass it to
`_burn_captions()` or `_mix_stingers()`. Both methods read `self.config.branding.*` directly.
The `captions_enabled` config check is at render.py line 1971; `_mix_stingers` is called
unconditionally at line 1944.

**Impact:**
- Checking "Enable Captions" in the sidebar has zero effect — captions only run if
  `config.branding.captions.enabled = true` in config.yaml.
- Unchecking "Enable Sound Kit" has zero effect — stingers still run if configured in the profile.
- Selecting a branding profile in the sidebar has zero effect on render — only the config.yaml
  `branding.active_profile` key controls which profile render uses.

**Affected files:**
- `src/podcast_pipeline/stages/render.py` — `_render_video()` (~line 1940-1981), `_burn_captions()`
  (~line 1986), `_mix_stingers()` (~line 3667)
- `src/podcast_pipeline/stages/review.py` — `ReviewDecisions` model (~line 33)

**Fix scope:**
- In `_render_video()`, gate `_mix_stingers()` call on `decisions.sound_kit_enabled`
- In `_render_video()`, gate caption burn-in on `decisions.captions_enabled` (in addition to or
  instead of the static config check — UI decision should take precedence)
- In `_render_video()`, resolve effective branding profile: use `decisions.branding_profile_name`
  when set, fall back to `self.config.branding.active_profile`
- Thread the effective profile name into `_burn_captions()` and `_mix_stingers()` as an override
  parameter, or temporarily update `self.config.branding.active_profile` before calling them
- Add `caption_aspect_ratio` field to `ReviewDecisions` (needed for GAP-4) and pass it to
  `_burn_captions()` to override the spec's default aspect ratio

**Note:** `decisions.ai_thumbnails_enabled` is correctly wired — it is consumed in
`stages/analyze.py` to gate AI thumbnail generation, not in render.

---

## EXISTS — Working Correctly

These Phase 9 UI features were verified as fully functional:

| Feature | Location | Notes |
|---|---|---|
| AI Thumbnail Generation toggle | Production sidebar ~line 2606 | Help text correctly says "Gemini Vision" |
| Thumbnail visual gallery + ranked selection | `render_thumbnail_selector()` ~line 1641 | 3-column grid, rank 1-3, virality scores shown |
| Brand Studio tab (top-level nav) | `_NAV_LABELS_BY_PAGE` line 56 | `🎨 Brand Studio` |
| Brand voice text area | Brand Studio ~line 2366 | 2000-char limit with counter |
| Caption style editor | Brand Studio ~line 2410 | Color, size, shadow, bold, italic, font |
| Caption enable toggle | Production sidebar ~line 2590 | Saved to review_state.json — but see GAP-7 |
| Sound kit enable toggle | Production sidebar ~line 2598 | Saved to review_state.json — but see GAP-7 |
| Manual sync offset slider | Production sidebar ~line 2615 | ±2000ms (range gap noted in GAP-3) |
| Active profile selector + Set as Active | Brand Studio ~line 2284 | Persists to review_state.json |
| Profile create / save / delete | Brand Studio ~line 2295 | Full CRUD lifecycle |

---

## Priority Order for Planning

| Priority | Gap | Effort | Impact |
|---|---|---|---|
| P0 | GAP-7: Production sidebar decisions not consumed by render | Medium — render.py wiring | Critical — captions/sound kit/branding profile UI controls have zero effect |
| P0 | GAP-2: youtube_ultra not in EXPORT_TARGETS | Low (1 file change + label) | High — feature completely unusable |
| P0 | GAP-1: Claude provider selection + Anthropic key status | Medium | High — can't use Claude without YAML edit |
| P1 | GAP-4: Caption aspect ratio selector (UI + ReviewDecisions field + render wire) | Low | Medium — breaks vertical/square exports |
| P1 | GAP-3A: Auto-detected sync offset not displayed | Low | Medium — UX clarity for multi-track |
| P2 | GAP-5A: Split sound kit into stingers + auto-duck toggles | Low | Low — workaround exists via profile |
| P2 | GAP-3B: Sync slider range ±2000ms vs ±5000ms | Trivial | Low — edge case |
| P3 | GAP-6A: Logo/font file uploader | Medium | Medium — UX friction for operators |
| P3 | GAP-5B: Per-job stinger path override | Low | Low — profile-level sufficient for most |
| P3 | GAP-6B: Platform overrides interactive edit | Medium | Low — power-user feature |

---

## Files Involved (for planning reference)

| File | Gaps |
|---|---|
| `src/podcast_pipeline/stages/render.py` | GAP-7 (main fix — decisions wiring in `_render_video`, `_burn_captions`, `_mix_stingers`) |
| `src/podcast_pipeline/stages/review.py` | GAP-7 (add `caption_aspect_ratio` field to `ReviewDecisions`), GAP-5A (add `auto_duck_enabled` field) |
| `src/podcast_pipeline/export_targets.py` | GAP-2 (add `youtube_ultra` entry) |
| `src/podcast_pipeline/ui/app.py` | GAP-1, GAP-3A, GAP-3B, GAP-4, GAP-5A, GAP-6A, GAP-6B (all UI changes) |
| `tests/test_pipeline.py` | GAP-7 (new render wiring tests), GAP-4 (caption_aspect_ratio round-trip) |
| `tests/test_ui_app.py` | GAP-1 (Anthropic key display), GAP-4 (aspect ratio persistence) |
