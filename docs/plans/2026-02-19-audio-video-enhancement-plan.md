# Audio/Video Enhancement & Podcast Video Platform Plan

**Date**: 2026-02-19
**Scope**: All missing audio/video processing features, platform video podcast support, smooth editing, and editorial filler control
**Status**: Planning — no code changes yet
**Companion Doc**: [`2026-02-19-smooth-editing-and-filler-control-spec.md`](./2026-02-19-smooth-editing-and-filler-control-spec.md)

---

## 1. Executive Summary

This plan covers **six major gaps** identified in the deep review:

| # | Gap | Priority | Effort |
|---|-----|----------|--------|
| 1 | **Smooth cuts & crossfades** at edit boundaries | P0 | Medium |
| 2 | **Filler word editorial control** (keep/remove per word) | P0 | Medium |
| 3 | **Spotify Video Podcast** output | P1 | Small |
| 4 | **Apple Video Podcast** output (MP4 + HLS) | P1 | Medium |
| 5 | **De-essing & reverb reduction** | P2 | Medium |
| 6 | **Video color correction** | P2 | Small |

Each section below covers: what we want, why, how to implement it, what tech/libraries/filters to use, and which files to change.

---

## 2. Smooth Cuts & Crossfades (P0)

### 2.1 Problem

The current render stage (`render.py:910-961`) uses FFmpeg `trim`/`atrim` + `concat` to physically remove segments. Each kept segment gets `PTS-STARTPTS` but there is:

- **No audio crossfade** at splice points → pops, clicks, abrupt volume jumps
- **No video transition** → visual jump cuts (speaker position changes instantly)
- **No word-boundary awareness** → cuts can land mid-word or mid-syllable
- **No fade envelope** around cuts → harsh audio edges

### 2.2 What We Want

1. **Audio crossfade** (50-200ms) at every splice point to eliminate pops/clicks
2. **Optional video crossfade** (100-500ms dissolve) for content cuts (configurable, off by default for filler cuts since they're fast)
3. **Word-boundary snapping** — use existing Whisper word timestamps to ensure cuts land between words, not inside them
4. **Micro-fade envelope** — always apply a 10-30ms fade-out/fade-in at raw cut edges as a safety net

### 2.3 Implementation

#### 2.3.1 Audio Crossfade at Splices

**Tech**: FFmpeg `acrossfade` filter or manual `afade` envelopes.

For our use case (many small segments), the most practical approach is:

```bash
# For each kept segment, apply:
#   afade=t=in:st=0:d=0.05     (50ms fade-in at start)
#   afade=t=out:st={end-0.05}:d=0.05  (50ms fade-out at end)
# Then concat normally — the crossfade happens naturally
```

For content cuts (longer removals), use `acrossfade` with configurable duration:

```bash
[seg_n_audio][seg_n+1_audio]acrossfade=d=0.15:c1=tri:c2=tri
```

**Configuration** (`config.yaml`):
```yaml
audio:
  crossfade:
    filler_cut_ms: 30       # Micro-fade for filler word cuts (ms)
    content_cut_ms: 150     # Crossfade for content cuts (ms)
    curve: tri              # Crossfade curve: tri, log, exp, par
```

#### 2.3.2 Video Dissolve for Content Cuts

**Tech**: FFmpeg `xfade` filter.

```bash
[seg_n_video][seg_n+1_video]xfade=transition=fade:duration=0.3:offset={seg_n_duration - 0.3}
```

Only applied for **content cuts** (long removals where the speaker position changes). Filler cuts are too short for video crossfade — they stay as hard cuts (which is fine because the visual difference is minimal for a 0.3s removal).

**Configuration** (`config.yaml`):
```yaml
video:
  transitions:
    content_cut_dissolve_ms: 300   # Video dissolve for content cuts (0 = disabled)
    filler_cut_dissolve_ms: 0      # No dissolve for filler cuts (too short)
```

#### 2.3.3 Word-Boundary Snapping

**Approach**: We already have word-level timestamps from faster-whisper. Before applying cuts:

1. Load the transcript's word-level timestamps
2. For each cut boundary (start and end), find the nearest word boundary
3. Snap the cut point to the silence gap between words (the space between `word[n].end` and `word[n+1].start`)
4. Add the configured padding around the snapped point

**Implementation**: New utility function `snap_to_word_boundary()` in `utils/editing.py`:

```python
def snap_to_word_boundary(
    cut_time: float,
    words: list[dict],
    direction: str = "nearest",  # "nearest", "before", "after"
    max_shift_ms: float = 200,    # Don't shift more than 200ms
) -> float:
    """Snap a cut time to the nearest inter-word silence gap."""
```

#### 2.3.4 Pop/Click Prevention

**Tech**: FFmpeg `adeclick` filter as a safety net on the final output:

```bash
adeclick=threshold=10:window=50
```

This detects and removes remaining click artifacts after all cuts and crossfades.

### 2.4 Files to Change

| File | Change |
|------|--------|
| `stages/render.py` | `_build_edit_plan_filter()` — add `afade`/`acrossfade`/`xfade` to the filter chain |
| `stages/render.py` | `_build_audio_enhancement_filters()` — add `adeclick` safety net |
| `config/settings.py` | Add `CrossfadeConfig` and `TransitionConfig` models |
| `config.yaml` | Add `audio.crossfade` and `video.transitions` sections |
| `utils/editing.py` | **New file** — `snap_to_word_boundary()` and related helpers |
| `stages/render.py` | Call word-boundary snapping before building filter chain |

---

## 3. Filler Word Editorial Control (P0)

### 3.1 Problem

Currently, the review stage auto-approves **all** detected filler words for removal (`review.py:118-121`). The podcaster has no practical way to:

- See each filler word in context (what was being said around it)
- Keep specific fillers that are part of the speaker's rhetorical style
- Configure which filler words to detect at all (the list is hardcoded in `transcribe.py`)
- Set per-word thresholds (e.g., always remove "um" but keep "like" unless confidence > 0.8)

### 3.2 What We Want

1. **Configurable filler word list** via `config.yaml` (already partially exists but needs expansion)
2. **Per-word keep/remove decisions** in the review stage — each filler shown with surrounding context
3. **Bulk actions** — "remove all ums", "keep all likes", "remove all above 0.7 confidence"
4. **Context preview** — show 3-5 words before and after each filler so the podcaster can judge
5. **Filler word categories** — distinguish between true disfluencies ("um", "uh") and hedge words ("like", "you know", "basically") since hedge words are more often intentional

### 3.3 Implementation

#### 3.3.1 Enhanced Config

```yaml
audio:
  filler_words:
    # Category: always_remove — these are pure disfluencies
    disfluencies:
      words: ["um", "uh", "hmm", "er", "ah"]
      default_action: remove    # Auto-approve for removal
      min_confidence: 0.5

    # Category: hedge_words — these may be intentional
    hedge_words:
      words: ["like", "you know", "basically", "actually", "so", "right", "i mean"]
      default_action: review    # Require manual review
      min_confidence: 0.7

    # Category: custom — user-defined
    custom:
      words: []
      default_action: review
      min_confidence: 0.6
```

#### 3.3.2 Enhanced Filler Detection Output

Currently, `transcribe.py` outputs filler cuts as:
```json
{"word": "um", "start": 12.5, "end": 12.8, "confidence": 0.92}
```

Enhanced output adds context:
```json
{
  "word": "um",
  "start": 12.5,
  "end": 12.8,
  "confidence": 0.92,
  "category": "disfluency",
  "default_action": "remove",
  "context_before": "and then I was thinking",
  "context_after": "about the whole situation",
  "speaker": "Speaker 1",
  "sentence_position": "mid"   // start, mid, end
}
```

#### 3.3.3 Review Stage Enhancement

The `ReviewDecisions` model in `review.py` needs:

```python
class FillerDecision(BaseModel):
    """Per-filler keep/remove decision."""
    index: int
    action: str = "remove"   # "remove" | "keep"
    reason: str = ""         # Optional note from podcaster

class ReviewDecisions(BaseModel):
    # Replace simple index list with rich decisions
    filler_decisions: list[FillerDecision] = Field(default_factory=list)
    # Bulk rule overrides
    filler_bulk_rules: dict[str, str] = Field(default_factory=dict)
    # e.g. {"um": "remove_all", "like": "keep_all", "you know": "review"}
```

#### 3.3.4 Streamlit UI Enhancement

The Streamlit review tab shows:
- Filler words grouped by category (disfluencies vs. hedge words)
- Each filler shown with context: `"...I was thinking [um] about the whole..."`
- Toggle per-filler: keep/remove
- Bulk actions: "Remove all 'um'" / "Keep all 'like'"
- Filter by confidence, category, speaker
- Audio preview snippet (2-3 seconds around the filler)

### 3.4 Files to Change

| File | Change |
|------|--------|
| `config/settings.py` | Add `FillerWordConfig` with categories model |
| `config.yaml` | Add `audio.filler_words` section with categories |
| `stages/transcribe.py` | Enhance `_detect_fillers()` to add context, category, sentence position |
| `models/edit_plan.py` | Update `FillerCutRange` to include `category`, `default_action`, `context_before/after` |
| `stages/review.py` | Update `ReviewDecisions` with `FillerDecision` model; change auto-approve to respect `default_action` |
| `stages/review.py` | Update `write_edit_plan()` to filter based on `FillerDecision` actions |
| `ui/app.py` | Enhanced filler review UI with context, bulk actions, per-word toggles |

---

## 4. Spotify Video Podcast Output (P1)

### 4.1 Spotify's Exact Requirements

Source: [Spotify Creator Support](https://support.spotify.com/us/creators/article/publishing-videos/), [Video Specs](https://support.spotify.com/us/creators/article/video-specs/)

| Spec | Requirement |
|------|------------|
| Container | **MP4** (also MOV, MPG) |
| Video Codec | **H.264 High Profile** |
| Audio Codec | **AAC-LC** |
| Resolution | **1080p minimum** (up to 4K) |
| Aspect Ratio | **16:9 widescreen** |
| Frame Rate | Source native |
| Max Bitrate (1080p) | 25 Mbps |
| Max Bitrate (4K) | 35 Mbps |
| Audio Bitrate | **192 Kbps+ stereo** |
| Audio Channels | **Stereo only** (no surround) |
| File Structure | **1 video + 1 audio track** |
| Max Duration | 12 hours |
| Distribution | **Direct upload only** (RSS = audio-only) |

### 4.2 Implementation

#### 4.2.1 New Platform Config

```yaml
spotify_video:
  container: mp4
  video_codec: libx264
  video_bitrate: "8M"
  audio_codec: aac
  audio_bitrate: "192k"
  audio_channels: 2
  loudness_lufs: -16.0
  width: 1920
  height: 1080
  aspect_ratio: "16:9"
  preset: medium
  pix_fmt: yuv420p
  audio_only: false
```

#### 4.2.2 H.264 High Profile Flag

**This is the key missing piece.** Spotify requires H.264 **High Profile** specifically. The current `_render_video()` method never sets an H.264 profile — FFmpeg defaults to `main` or `baseline`.

Add to the FFmpeg args in `_render_video()`:
```python
if spec.video_codec == "libx264":
    args.extend(["-profile:v", "high", "-level:v", "4.1"])
```

Also needed in the `PlatformSpec` model:
```python
class PlatformSpec(BaseModel):
    # ... existing fields ...
    video_profile: str | None = None   # e.g. "high", "main", "baseline"
    video_level: str | None = None     # e.g. "4.1", "5.1"
```

#### 4.2.3 File Structure Enforcement

Spotify requires exactly 1 video + 1 audio track. Add an FFmpeg post-check:
```python
# After render, verify track count
metadata = get_video_metadata(output_path)
if metadata["nb_streams"] != 2:
    logger.warning("spotify_track_count_mismatch", streams=metadata["nb_streams"])
```

### 4.3 Files to Change

| File | Change |
|------|--------|
| `config/settings.py` | Add `spotify_video` to `PlatformSpecs`; add `video_profile`, `video_level` to `PlatformSpec` |
| `config.yaml` | Add `spotify_video` platform definition |
| `stages/render.py` | Add `-profile:v` and `-level:v` flags in `_render_video()` when configured |
| `stages/render.py` | Add post-render stream count validation for Spotify |
| `README.md` | Update platform export table |

---

## 5. Apple Video Podcast Output (P1)

### 5.1 Apple's Requirements

Source: [Apple Newsroom](https://www.apple.com/newsroom/2026/02/), [podcasters.apple.com](https://podcasters.apple.com/)

| Spec | Requirement |
|------|------------|
| Container (basic) | **MP4** |
| Container (advanced) | **HLS** (.m3u8 + .ts segments) |
| Video Codec | **H.264** or **H.265 (HEVC)** |
| Audio Codec | **AAC** |
| Resolution | Not strictly specified; 16:9 horizontal |
| Frame Rate | 24/30/60 fps |
| Advanced Features | Multicam, chapters, auto-captions, adaptive bitrate |
| Distribution | Apple Podcasts Connect / RSS with MP4 enclosures |

### 5.2 Implementation — Two Tiers

#### 5.2.1 Tier 1: MP4 Export (Simple)

Same as YouTube spec but with Apple-specific loudness (-16 LUFS) and optional HEVC:

```yaml
apple_video:
  container: mp4
  video_codec: libx264      # Safe default; libx265 optional
  video_bitrate: "8M"
  audio_codec: aac
  audio_bitrate: "256k"
  audio_channels: 2
  loudness_lufs: -16.0
  width: 1920
  height: 1080
  aspect_ratio: "16:9"
  fps: 30
  preset: medium
  pix_fmt: yuv420p
  audio_only: false
```

#### 5.2.2 Tier 2: HLS Adaptive Bitrate (Advanced)

For HLS output, we need FFmpeg's HLS muxer with multiple quality variants:

```bash
ffmpeg -i input.mp4 \
  -map 0:v -map 0:a -c:v libx264 -preset slow -crf 22 \
    -maxrate 5M -bufsize 10M -s 1920x1080 \
  -map 0:v -map 0:a -c:v libx264 -preset slow -crf 23 \
    -maxrate 3M -bufsize 6M -s 1280x720 \
  -map 0:v -map 0:a -c:v libx264 -preset slow -crf 25 \
    -maxrate 1M -bufsize 2M -s 640x360 \
  -c:a aac -b:a 128k \
  -f hls -hls_time 6 -hls_list_size 0 \
  -hls_segment_filename "stream_%v/segment_%03d.ts" \
  -master_pl_name master.m3u8 \
  -var_stream_map "v:0,a:0 v:1,a:0 v:2,a:0" \
  stream_%v.m3u8
```

This creates:
```text
output/apple_hls/
  master.m3u8           # Master playlist pointing to variants
  stream_0.m3u8         # 1080p variant playlist
  stream_0/segment_*.ts # 1080p segments (6s each)
  stream_1.m3u8         # 720p variant playlist
  stream_1/segment_*.ts # 720p segments
  stream_2.m3u8         # 360p variant playlist
  stream_2/segment_*.ts # 360p segments
```

**New render method**: `_render_hls()` in `render.py` — separate from `_render_video()` because HLS output is structurally different (directory of segments vs single file).

**Configuration**:
```yaml
apple_hls:
  container: hls
  video_codec: libx264
  audio_codec: aac
  audio_bitrate: "128k"
  loudness_lufs: -16.0
  aspect_ratio: "16:9"
  preset: slow
  pix_fmt: yuv420p
  audio_only: false
  hls:
    segment_duration: 6        # seconds per .ts segment
    variants:
      - { width: 1920, height: 1080, max_bitrate: "5M", crf: 22 }
      - { width: 1280, height: 720,  max_bitrate: "3M", crf: 23 }
      - { width: 640,  height: 360,  max_bitrate: "1M", crf: 25 }
```

### 5.3 Files to Change

| File | Change |
|------|--------|
| `config/settings.py` | Add `apple_video` and `apple_hls` to `PlatformSpecs`; add `HLSConfig` model with variants |
| `config.yaml` | Add `apple_video` and `apple_hls` platform definitions |
| `stages/render.py` | Add `_render_hls()` method for HLS output |
| `stages/render.py` | Update `_render_platform()` to route HLS platforms to `_render_hls()` |
| `README.md` | Update platform export table |

---

## 6. De-essing (P2)

### 6.1 Problem

Sibilance ("s", "sh", "ch" sounds) can be harsh in podcast audio, especially with condenser microphones close to the speaker. No de-essing is applied.

### 6.2 What We Want

An optional de-esser in the audio enhancement chain that reduces sibilance without dulling the overall sound.

### 6.3 Implementation

> **Updated 2026-02-19**: Phase 6 research confirmed FFmpeg has a native `deesser` filter. The original custom split-band sidechain approach is unnecessary.

**Tech**: FFmpeg built-in `deesser` filter (no new dependencies):

```bash
deesser=i=0.2:m=0.5:f=0.5
```

Parameters:
- `i` (intensity): 0.0–1.0, controls how aggressively sibilance is reduced
- `m` (amount): 0.0–1.0, controls the reduction amount
- `f` (frequency): 0.0–1.0, maps to the sibilance frequency band

This slots into the existing audio enhancement filter chain in `_build_audio_enhancement_filters()`, ordered as: `dialog cleanup → de-esser → loudness/limiter → click safety`.

### 6.4 Configuration

```yaml
audio:
  deesser:
    enabled: true               # true/false
    intensity: 0.2              # 0.0–1.0 aggressiveness
    amount: 0.5                 # 0.0–1.0 reduction amount
    frequency: 0.5              # 0.0–1.0 sibilance frequency band
```

### 6.5 Files to Change

| File | Change |
|------|--------|
| `stages/render.py` | Add `deesser` filter to `_build_audio_enhancement_filters()` chain |
| `config/settings.py` | Add `DeesserConfig` model |
| `config.yaml` | Add `audio.deesser` section |

---

## 7. Reverb Reduction (P2)

### 7.1 Problem

Many podcasters record in untreated rooms with audible echo/reverb. The current `afftdn` filter handles broadband noise but not reverb tails.

### 7.2 Implementation Options

#### Option A: FFmpeg Spectral Approach (Limited)

```bash
afftdn=nf=-25,highpass=f=200,lowpass=f=5000
```

This is what we already do with `afftdn`. It catches some reverb energy as noise, but it's not effective for reverb tails. **Not recommended as the primary solution.**

#### ~~Option B: Meta's Demucs~~ ❌ REMOVED

> **Updated 2026-02-19**: `facebookresearch/demucs` repository is **archived and unmaintained** as of Jan 2025. Dropped from recommendations.

#### Option B: noisereduce Library (Lightweight)

```python
import noisereduce as nr
reduced = nr.reduce_noise(y=audio, sr=sample_rate, prop_decrease=0.8)
```

**Pros**: Lightweight. Python-only. Fast.
**Cons**: Spectral gating only — handles stationary noise/reverb but not dynamic reverb tails.

### 7.3 Recommendation

Use `noisereduce` as the **sole optional** dereverb method. Applied as **pre-processing** before the FFmpeg render step (process audio in Python, write clean audio, feed to FFmpeg).

Ship as `enabled: false` by default — users with noisy rooms can opt in via config.

### 7.4 Configuration

```yaml
audio:
  dereverb:
    enabled: false              # Off by default (adds processing time)
    strength: 0.7               # 0.0 = no reduction, 1.0 = max reduction
```

### 7.5 Files to Change

| File | Change |
|------|--------|
| `stages/render.py` | Add `_apply_dereverb()` method; call before FFmpeg render |
| `config/settings.py` | Add `DereverbConfig` model |
| `config.yaml` | Add `audio.dereverb` section |
| `pyproject.toml` | Add `noisereduce` as optional dependency |

---

## 8. Video Color Correction (P2)

### 8.1 Problem

Webcam footage often has poor white balance, low contrast, and inconsistent exposure. No video correction is applied.

### 8.2 What We Want

A lightweight, automated color correction pass that normalizes webcam video without manual tuning.

### 8.3 Implementation

> **Updated 2026-02-19**: Phase 6 research found that `autowhite` and `autolevels` are **not valid canonical FFmpeg filters**. The correct replacements are `grayworld` (white balance) and `normalize` (histogram/contrast normalization).

**Tech**: FFmpeg video filters only (no new dependencies):

```bash
# Gray-world white balance correction
grayworld,
# Histogram-based contrast/levels normalization
normalize,
# Gentle contrast and saturation boost
eq=brightness=0.02:contrast=1.1:saturation=1.05:gamma=1.05
```

This is applied in `_build_video_filters()` alongside the existing aspect ratio/crop filters.

### 8.4 Configuration

```yaml
video:
  color_correction:
    enabled: false              # Off by default
    normalize: true             # Histogram-based contrast normalization
    grayworld: true             # Gray-world white balance correction
    brightness: 0.02            # Brightness adjustment (-1.0 to 1.0)
    contrast: 1.1               # Contrast multiplier
    saturation: 1.05            # Saturation multiplier
    gamma: 1.05                 # Gamma correction
```

### 8.5 Files to Change

| File | Change |
|------|--------|
| `stages/render.py` | Add `_build_color_correction_filters()` method using `grayworld` + `normalize` + `eq` |
| `stages/render.py` | Insert color correction in `_build_video_filters()` chain |
| `config/settings.py` | Add `ColorCorrectionConfig` model |
| `config.yaml` | Add `video.color_correction` section |

---

## 9. New Dependencies Summary

| Dependency | Purpose | Type | Size Impact |
|------------|---------|------|-------------|
| `noisereduce` | Optional reverb reduction (spectral gating) | Optional | ~2MB |

> **Updated 2026-02-19**: `pedalboard` removed (de-essing now uses FFmpeg built-in `deesser`). `demucs` removed (upstream archived/unmaintained).

All new dependencies are **optional** — the pipeline uses FFmpeg-only filters by default.

---

## 10. Config Schema Overview (All New Sections)

```yaml
audio:
  # Existing
  noise_reduction: moderate
  target_loudness: -16.0

  # New — Crossfade at edit points
  crossfade:
    filler_cut_ms: 30
    content_cut_ms: 150
    curve: tri

  # New — De-esser (FFmpeg built-in)
  deesser:
    enabled: true
    intensity: 0.2
    amount: 0.5
    frequency: 0.5

  # New — Reverb reduction (noisereduce only; Demucs dropped)
  dereverb:
    enabled: false
    strength: 0.7

  # New — Filler word categories
  filler_words:
    disfluencies:
      words: ["um", "uh", "hmm", "er", "ah"]
      default_action: remove
      min_confidence: 0.5
    hedge_words:
      words: ["like", "you know", "basically", "actually", "so", "right", "i mean"]
      default_action: review
      min_confidence: 0.7
    custom:
      words: []
      default_action: review
      min_confidence: 0.6

video:
  # New — Transitions at edit points
  transitions:
    content_cut_dissolve_ms: 300
    filler_cut_dissolve_ms: 0

  # New — Color correction (grayworld + normalize, not autowhite/autolevels)
  color_correction:
    enabled: false
    normalize: true
    grayworld: true
    brightness: 0.02
    contrast: 1.1
    saturation: 1.05
    gamma: 1.05

platforms:
  # Existing (unchanged)
  youtube: { ... }
  spotify: { ... }       # Audio-only stays
  apple: { ... }         # Audio-only stays

  # New video podcast platforms
  spotify_video:
    container: mp4
    video_codec: libx264
    video_bitrate: "8M"
    video_profile: high
    video_level: "4.1"
    audio_codec: aac
    audio_bitrate: "192k"
    audio_channels: 2
    loudness_lufs: -16.0
    width: 1920
    height: 1080
    aspect_ratio: "16:9"
    preset: medium
    pix_fmt: yuv420p
    audio_only: false

  apple_video:
    container: mp4
    video_codec: libx264
    video_bitrate: "8M"
    audio_codec: aac
    audio_bitrate: "256k"
    audio_channels: 2
    loudness_lufs: -16.0
    width: 1920
    height: 1080
    aspect_ratio: "16:9"
    fps: 30
    preset: medium
    pix_fmt: yuv420p
    audio_only: false

  apple_hls:
    container: hls
    video_codec: libx264
    audio_codec: aac
    audio_bitrate: "128k"
    loudness_lufs: -16.0
    aspect_ratio: "16:9"
    preset: slow
    pix_fmt: yuv420p
    audio_only: false
    hls:
      segment_duration: 6
      variants:
        - { width: 1920, height: 1080, max_bitrate: "5M", crf: 22 }
        - { width: 1280, height: 720,  max_bitrate: "3M", crf: 23 }
        - { width: 640,  height: 360,  max_bitrate: "1M", crf: 25 }
```

---

## 11. Phase Plan (Risk-Ordered)

> **Strategy**: Safest work first, riskiest last. Each phase is a separate commit/push.
> If Phase 7 (the risky crossfade rewrite) has issues, revert that push — Phases 5 and 6 remain live and working.
> Phase numbers continue from the project's existing Phase 4.

### Phase 5 — Video Podcast Platforms ⚡ Low Risk

**Goal**: Enable video export for Spotify and Apple Podcasts.
**Risk**: Low — mostly config additions and one FFmpeg flag. Doesn't touch existing render logic.
**Confidence**: ~95%

1. Add `video_profile` and `video_level` fields to `PlatformSpec` model
2. Add `spotify_video` and `apple_video` platform configs to `settings.py` and `config.yaml`
3. Update `_render_video()` to emit `-profile:v` and `-level:v` flags when configured
4. Implement `_render_hls()` method for Apple HLS output
5. Add `HLSConfig` model and `apple_hls` platform config
6. Add post-render validation (track count for Spotify, segment verification for HLS)
7. Update README platform table
8. Tests for profile flag emission, HLS output structure

### Phase 6 — Audio/Video Enhancement Filters ⚡ Low Risk

**Goal**: Improve raw audio/video quality with optional processing filters.
**Risk**: Low — additive filters on existing chain. All FFmpeg-native by default. Doesn't change core render logic.
**Confidence**: ~85% (code works; tuning defaults may need iteration)

1. Add FFmpeg built-in `deesser` filter to audio enhancement chain in `render.py`
2. Add `noisereduce` optional reverb reduction (pre-processing pass, `enabled: false` by default)
3. Add color correction filters (`grayworld` + `normalize` + `eq`) to video filter chain
4. Add config models: `DeesserConfig`, `DereverbConfig`, `ColorCorrectionConfig`
5. Add config sections to `config.yaml`
6. Add `noisereduce` as optional dependency in `pyproject.toml`
7. Add startup FFmpeg capability check (verify required filters available, fail-fast with upgrade message)
8. Tests for each enhancement filter chain generation
9. *(Future)* Apple HLS CI validation — add validator-backed smoke checks for `.m3u8`/`.ts` conformance when tooling is available in CI

### Phase 7 — Smooth Editing & Filler Word Control ⚠️ Higher Risk

**Goal**: Fix the editing quality gap — smooth crossfades at cut points and editorial control over filler words.
**Risk**: Medium-High — rewrites the core edit filter chain in `render.py`. FFmpeg `acrossfade`/`xfade` chaining across many segments is complex. Offset math for dissolves is cumulative and error-prone.
**Confidence**: ~65-70% on first pass (crossfades likely need 1-2 debugging rounds with real media)
**Safety net**: Keep current hard-cut path as fallback via `crossfade.enabled: false` in config.

1. Create `utils/editing.py` with word-boundary snapping algorithm
2. Add `CrossfadeConfig` and `TransitionConfig` models to `settings.py`
3. Update `_build_edit_plan_filter()` in `render.py` with:
   - Micro-fades (`afade`) on all segment edges
   - Audio crossfade (`acrossfade`) at content cut splices
   - Video dissolve (`xfade`) at content cut splices
   - Fallback to current hard-cut behavior when disabled
4. Add `adeclick` safety net to the audio enhancement chain
5. Enhance filler detection in `transcribe.py` with categories, context, and sentence position
6. Add `FillerWordConfig` with category-based rules to `config/settings.py`
7. Update `ReviewDecisions` model with `FillerDecision` for per-word keep/remove
8. Update `write_edit_plan()` to filter based on `FillerDecision` actions
9. Update Streamlit filler review UI with context display, bulk actions, per-word toggles
10. Add config sections for crossfade, transitions, and filler categories
11. Tests for word-boundary snapping, crossfade filter generation, filler categorization
12. **Manual QA**: Test with real podcast footage — listen to crossfade quality, verify no audio glitches

---

## 12. Complete File Change Registry

| File | Phase | Description |
|------|-------|-------------|
| `config/settings.py` | 5, 6, 7 | PlatformSpec additions (profile/level), HLSConfig, DeesserConfig, DereverbConfig, ColorCorrectionConfig, CrossfadeConfig, TransitionConfig, FillerWordConfig |
| `config.yaml` | 5, 6, 7 | All new config sections |
| `stages/render.py` | 5, 6, 7 | Profile flags + HLS render (Ph5), de-esser/dereverb/color filters (Ph6), crossfade/dissolve edit filter rewrite (Ph7) |
| `stages/transcribe.py` | 7 | Enhanced filler detection with categories, context, sentence position |
| `stages/review.py` | 7 | FillerDecision model, per-word review, category-aware auto-approve |
| `models/edit_plan.py` | 7 | Enhanced FillerCutRange with category, context, default_action |
| `utils/editing.py` | 7 | **New file** — word-boundary snapping utilities |
| `ui/app.py` | 7 | Enhanced filler review UI with context and bulk actions |
| `pyproject.toml` | 6 | Optional dependency (`noisereduce` only) |
| `README.md` | 5 | Updated platform export table |

---

*This document is a planning reference. See the companion spec for detailed technical specifications on the smooth editing and filler control systems.*
