# Phase 9: Brand Studio Operator Runbook

## Overview

Phase 9 adds automated branding, burned-in captions, multi-track sync, AI thumbnail generation, and sound kit (intro/transition/outro stingers with auto-ducking) to the podcast pipeline. This runbook covers setup, execution, troubleshooting, and operational boundaries.

## Prerequisites

### Required

- Python 3.12+ with `uv` package manager
- FFmpeg 6.1+ (system installation)
- Pipeline backend service running (`podcast-pipeline service`)
- Streamlit UI running (`streamlit run src/podcast_pipeline/ui/app.py`)

### Optional (GPU Features)

- NVIDIA GPU with CUDA 12.8+ for:
  - FLUX.1 Schnell local thumbnail generation
  - NVENC hardware encoding (HEVC/H.264)
  - RIFE frame interpolation (Phase 8)
- torch==2.10.* via pytorch-cu128 index
- RTX 5060 Ti (Blackwell sm_120) requires CUDA 12.8 specifically

### Optional (Cloud AI Features)

- Google Cloud Vertex AI credentials for Imagen 4 thumbnail generation
- Gemini API key for primary video analysis
- Anthropic API key for Claude provider (alternative)

## Setup

### 1. Create a Branding Profile

Navigate to the **Brand Studio** tab in the Streamlit UI.

1. Click **Create New Profile**
2. Enter a profile name (letters, digits, hyphens, underscores only)
3. Write your brand voice instructions (max 2000 characters)
4. Click **Save Profile**

Alternatively, create a YAML file directly in the `branding/` directory:

```yaml
profile_name: my-podcast-brand
brand_voice: >
  Energetic and conversational. Use active voice, short sentences,
  and relatable examples. Our audience is tech-forward professionals
  aged 25-40 who value practical insights over theory.
logo_path: branding/assets/logo.png
logo_placement: top_right
logo_opacity: 0.8
font_path: null
caption_style:
  color: "#FFFFFF"
  size: 48
  shadow: true
  bold: false
  italic: false
  font: ""
highlight_color: "#FFFF00"
intro_sound: branding/assets/intro.wav
transition_sound: branding/assets/whoosh.wav
outro_sound: branding/assets/outro.mp3
platform_overrides:
  tiktok:
    caption_style:
      color: "#FF5500"
      size: 72
      bold: true
```

### 2. Configure Sound Kit Assets

Sound kit paths are set per-profile in the Brand Studio or YAML:

| Field | Description | Supported Formats |
|-------|-------------|-------------------|
| `intro_sound` | Played at video start | WAV, FLAC, MP3 |
| `transition_sound` | Played at content-cut boundaries | WAV, FLAC, MP3 |
| `outro_sound` | Faded in during last 5 seconds | WAV, FLAC, MP3 |

Missing sound files degrade gracefully -- a warning is logged and the stinger is skipped.

### 3. Configure Caption Settings

In `config.yaml`:

```yaml
branding:
  active_profile: my-podcast-brand
  captions:
    enabled: true
    alignment_filename: word_alignment.json
    max_words_per_line: 7
    gap_threshold_s: 1.5
```

Or toggle in the editor sidebar **Production Controls** panel.

### 4. Enable AI Thumbnail Generation (Optional)

```yaml
branding:
  thumbnail_generation:
    enabled: true
    model: imagen-4.0-generate-001
    images_per_prompt: 1
    width: 1280
    height: 720
```

Toggle in editor sidebar: **AI Thumbnail Generation** checkbox.

## Execution Workflow

### Standard Production Run

1. **Upload video** via Dashboard > Create New Job
2. **Run ingest + transcribe + analyze** stages
3. Open the **Editor** page for the job
4. In the sidebar **Production Controls**:
   - Select your **Branding Profile**
   - Toggle **Enable Captions** for burned-in subtitles
   - Toggle **Enable Sound Kit** for intro/transition/outro stingers
   - Toggle **AI Thumbnail Generation** if you want AI-generated thumbnails
   - Adjust **Manual Sync Offset** if auto-sync confidence is low
5. Review content in the editor tabs (Timeline, Thumbnails, Marketing)
6. Click **Approve & Export** in the Export tab

### Brand Studio Workflow

1. Navigate to **Brand Studio** tab
2. Select an existing profile or create a new one
3. Edit brand voice, visual assets, caption style, sound kit
4. Click **Save Profile** to persist changes
5. Click **Set as Active** to assign the profile to the current job

### Multi-Job Production

When running multiple jobs concurrently:

- GPU-heavy operations (FLUX thumbnail generation and NVENC encoding) are serialized across jobs via a shared GPU lease
- Same-job stages always run sequentially
- Only cross-job GPU contention is gated by the lease
- If a GPU operation times out waiting for the lease, it degrades gracefully

## Production Controls Reference

| Control | Review State Field | Effect |
|---------|-------------------|--------|
| Branding Profile | `branding_profile_name` | Selects brand assets for render |
| Enable Captions | `captions_enabled` | Burns ASS captions into exports |
| Enable Sound Kit | `sound_kit_enabled` | Mixes stingers with auto-ducking |
| AI Thumbnails | `ai_thumbnails_enabled` | Generates AI thumbnails during analysis |
| Manual Sync Offset | `manual_sync_offset_ms` | Overrides auto-detected A/V sync |

All production controls persist through review state and are consumed by the render stage.

## Troubleshooting

### Brand Profile Not Loading

**Symptom:** "Failed to load profile" error in Brand Studio.

**Cause:** Invalid YAML syntax or field validation failure.

**Fix:**
1. Check YAML syntax: `python -c "import yaml; yaml.safe_load(open('branding/profile.yaml'))"`
2. Validate the profile: `python -c "from podcast_pipeline.models.branding import BrandingProfile; BrandingProfile.model_validate(yaml.safe_load(open('branding/profile.yaml')))"`
3. Common issues: hex colors must be `#RGB` or `#RRGGBB`, profile_name must be non-empty

### Captions Not Appearing in Export

**Symptom:** Exported video has no burned-in captions despite `captions_enabled=True`.

**Check:**
1. Verify `word_alignment.json` exists in `jobs/<job>/analysis/`
2. Confirm the transcription stage completed successfully
3. Check render logs for "caption" messages
4. Ensure FFmpeg has subtitle filter support (`ffmpeg -filters | grep ass`)

### Sound Kit Stingers Missing

**Symptom:** Exported video has no intro/transition/outro audio.

**Check:**
1. Verify sound file paths exist and are readable
2. Check render logs for "stinger" or "sound_kit" warnings
3. Ensure FFmpeg has the required audio codecs
4. Confirm `sound_kit_enabled=True` in production controls

### GPU Lease Timeout

**Symptom:** "GPU lease not acquired" error in logs.

**Cause:** Another job is holding the GPU lease for an extended period.

**Fix:**
1. Check active jobs: Dashboard > Runtime Journal
2. Wait for the blocking job to complete its GPU operation
3. If stuck, reconcile stale jobs via Dashboard > Reconcile Now

### AI Thumbnail Generation Fails

**Symptom:** No AI-generated thumbnails despite `ai_thumbnails_enabled=True`.

**Check:**
1. For Imagen 4: verify Google Cloud credentials and Vertex AI access
2. For FLUX: verify GPU availability and torch installation
3. Check analyze stage logs for thumbnail generation errors
4. Generation is optional -- pipeline continues without AI thumbnails

## Architecture Notes

### MCP Boundary (Dev-Only)

The FastMCP server (`src/podcast_pipeline/mcp/ffmpeg_server.py`) is a **development-only** tool for AI-assisted FFmpeg operations. It is:
- Installed only via `[dependency-groups] dev`
- Not available in production deployments
- Not required for any pipeline stage

### GPU Serialization Policy

The `GPULease` in the Supervisor uses a `threading.Semaphore(1)`:
- At most one GPU-heavy workload active across all jobs
- Same-job stages run sequentially (already the case)
- Cross-job FLUX and NVENC operations are serialized
- Prevents VRAM contention crashes on single-GPU machines

### Review State Contract

Production controls persist in `review/review_state.json`:
```json
{
  "branding_profile_name": "my-brand",
  "captions_enabled": true,
  "sound_kit_enabled": true,
  "ai_thumbnails_enabled": false,
  "manual_sync_offset_ms": null
}
```

The render stage reads these fields to determine:
- Which branding profile to apply
- Whether to burn-in captions
- Whether to mix sound kit stingers
- Whether to override auto-sync offset

### Platform Override Merge

When rendering for a specific platform (e.g., `tiktok`):
1. Base profile fields are loaded
2. Platform override fields are merged (only explicitly set fields)
3. Resolved profile has empty `platform_overrides` (signals resolution)
4. Downstream consumers use the flat resolved profile

## Version Compatibility

Phase 9 fields are additive and optional. Existing review state payloads from earlier phases load without errors -- all new fields default to `None` or `False`.
