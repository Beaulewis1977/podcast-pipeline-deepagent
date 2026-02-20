# Phase 6: Audio/Video Enhancement & Podcast Video Platform - Research

**Researched:** 2026-02-20
**Domain:** FFmpeg-native audio/video enhancement and podcast video delivery compliance
**Confidence:** HIGH (core stack), MEDIUM (advanced dereverb quality deltas)

## Summary

Phase 6 should stay **FFmpeg-native by default** and avoid new heavy DSP/ML dependencies unless there is a measured quality win on your real podcast corpus. The current codebase already has strong render/compliance scaffolding from Phase 5/5.1, so this phase should focus on quality-safe filtergraph improvements: word-boundary snapping, cut smoothing, de-essing, conservative dereverb, and color normalization.

The prior plan has two stale assumptions: `autowhite` and `autolevels` are not canonical FFmpeg filters. The stable replacements are `grayworld` (white balance style correction) plus `normalize` (histogram/contrast normalization), both documented in FFmpeg filters docs.

For platform output, keep current Spotify/Apple profile/compliance behavior and avoid building upload workflows. Spotify specs emphasize H.264/AAC/stereo constraints and single A/V track layout. Apple now prefers HLS video via supported hosting providers/API-key workflows, while RSS video (MOV/MP4/M4V) remains available.

**Primary recommendation:** Implement Phase 6 as a **single render pipeline upgrade** on top of existing FFmpeg filtergraph architecture, with **FFmpeg built-ins first** and optional Python DSP dependencies gated behind explicit config flags.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FFmpeg CLI + ffprobe | 8.0.1 stable branch (latest stable as of 2026-02-20) | Trim/concat, transitions, audio/video filters, HLS muxing, validation probes | Existing project backbone; richest stable filtergraph toolchain |
| faster-whisper | 1.2.1 | Word-level timestamps for cut-boundary snapping | Already in project; supports `word_timestamps=True` directly |
| Pydantic settings/models | 2.x | Strong config/schema safety for new filter knobs | Already used pervasively; minimizes runtime config regressions |
| Streamlit UI (existing) | 1.42+ in project constraints | Editorial controls for filler keep/remove | Existing UX layer and persistence path already in place |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| noisereduce | 3.0.3 | Optional spectral-gating denoise/dereverb pre-pass | Only when FFmpeg-only chain leaves room echo/noise artifacts |
| Apple Media Streaming Validator | Current Apple tooling | HLS playlist/segment validation for Apple-facing artifacts | When `apple_hls` output is enabled |
| Spotify publishing/video specs docs | Current help-center docs | Compliance guardrails for container/codec/layout targets | During schema and post-render checks |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FFmpeg built-in `deesser` | `pedalboard` custom sidechain chain | More complexity and GPLv3 licensing implications; no clear need for default path |
| Lightweight optional denoise (`noisereduce`) | Demucs-based dereverb | `facebookresearch/demucs` repo is archived/not maintained; higher integration risk |
| `grayworld` + `normalize` | Hand-rolled color heuristics | Reinvents mature filters and increases bug surface |

**Installation:**
```bash
# Optional only (do not make required baseline deps)
pip install noisereduce==3.0.3
```

## Architecture Patterns

### Recommended Project Structure
```text
src/podcast_pipeline/
├── stages/render.py          # Main orchestration and filtergraph generation
├── utils/editing.py          # New: word-boundary snapping + cut utilities
├── stages/review.py          # Filler decision model + edit plan writing
├── ui/app.py                 # Per-filler keep/remove UX and bulk actions
└── config/settings.py        # Typed config for smoothing/deesser/dereverb/color
```

### Pattern 1: Edit Graph Builder With Segment Metadata
**What:** Build explicit keep-segments with metadata (`duration`, `cut_type`, `boundary_confidence`) before generating filtergraph text.
**When to use:** Any edit-plan application path (full episode and clip exports).
**Example:**
```python
# Source: https://ffmpeg.org/ffmpeg-filters.html (trim/atrim/setpts/asetpts, afade, acrossfade, xfade)
segments = build_keep_segments(edit_plan, duration)
segments = snap_segments_to_word_boundaries(segments, transcript_words)
filters = build_transition_filtergraph(segments, cfg.audio.crossfade, cfg.video.transitions)
```

### Pattern 2: Two-Tier Transition Policy (Filler vs Content)
**What:** Always apply micro `afade` on joins; apply longer `acrossfade`/`xfade` only for content cuts.
**When to use:** Mixed cut streams where filler edits are short and content edits are long.
**Example:**
```bash
[a0]afade=t=in:st=0:d=0.03,afade=t=out:st=14.97:d=0.03[a0f];
[a1]afade=t=in:st=0:d=0.03,afade=t=out:st=11.97:d=0.03[a1f];
[a0f][a1f]acrossfade=d=0.15:c1=tri:c2=tri[aout]
```

### Pattern 3: Enhancement Chain Ordering
**What:** Keep deterministic order: `dialog cleanup -> de-esser -> loudness/limiter fallback -> final click safety`.
**When to use:** All render targets with audio.
**Example:**
```python
# Source: https://ffmpeg.org/ffmpeg-filters.html (afftdn/anlmdn/deesser/adeclick)
audio_filters = [
    "afftdn=nf=-25",
    "deesser=i=0.2:m=0.5:f=0.5",
    "adeclick=window=55:overlap=75:arorder=2:threshold=2:burst=2:method=a",
]
```

### Pattern 4: Platform Compliance as Post-Render Gate
**What:** Keep strict ffprobe checks after encode (streams, codecs, profile/level, channels, GOP/keyframe policy).
**When to use:** `spotify_video`, `apple_video`, `apple_hls`.
**Example:**
```python
# Source: Spotify creator specs and existing render compliance functions
assert_stream_layout(video_streams=1, audio_streams=1)
assert_codec(video="h264", audio="aac")
assert_audio_channels(max_channels=2)
```

### Anti-Patterns to Avoid
- **Monolithic string-concatenated filtergraph logic without typed segment metadata:** hard to reason about offset math and crossfade edge cases.
- **Defaulting to heavy ML dereverb stack:** creates install/runtime blockers and unstable performance.
- **Assuming Apple HLS means direct upload from this app:** Apple’s current HLS workflow is hosting-provider/API-key mediated.
- **Using undocumented filters (`autowhite`, `autolevels`):** causes runtime FFmpeg failures.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| De-essing | Custom split-band sidechain DSP in Python | FFmpeg `deesser` filter | Native, documented, lower maintenance and fewer latency bugs |
| Cut smoothing | Custom sample stitching math | FFmpeg `afade` + `acrossfade` + `xfade` | Proven filter behavior with less artifact risk |
| Color “auto correction” | Bespoke histogram/white balance code | FFmpeg `normalize` + `grayworld` (+ optional `eq`) | Existing filters are stable and configurable |
| Word timing alignment | Rebuilding token alignment heuristics | faster-whisper word timestamps | Already available from current transcription stack |
| HLS compliance parsing | Custom parser from scratch | Apple tools + ffprobe checks + existing validators | Avoids fragile playlist/segment edge-case bugs |

**Key insight:** Phase 6 quality gains come from better composition of mature filters, not from introducing new custom DSP subsystems.

## Common Pitfalls

### Pitfall 1: Invalid xfade Input Compatibility
**What goes wrong:** `xfade` fails or produces glitches.
**Why it happens:** Inputs differ in resolution/pix_fmt/frame rate/timebase.
**How to avoid:** Normalize each segment’s video properties before xfade and enforce one encode profile per target.
**Warning signs:** FFmpeg filtergraph errors mentioning incompatible stream parameters.

### Pitfall 2: Crossfade Duration Longer Than Segment
**What goes wrong:** Negative offsets or collapse at short segments.
**Why it happens:** Fixed duration crossfades applied to very short filler segments.
**How to avoid:** Clamp fade duration to `min(segment_duration * 0.25, configured_max)`; disable long crossfade on filler-only cuts.
**Warning signs:** Runtime offset underflow, abrupt truncation at joins.

### Pitfall 3: Word-Boundary Snap Drift
**What goes wrong:** Content meaning shifts because cuts are moved too far.
**Why it happens:** Unbounded snapping window.
**How to avoid:** Strict max-shift (e.g., <= 200ms) and fallback to original timestamp when no safe boundary exists.
**Warning signs:** Review feedback that sentences feel unexpectedly clipped/dragged.

### Pitfall 4: Platform Spec Drift
**What goes wrong:** Encodes pass locally but are rejected by platform.
**Why it happens:** Hardcoded assumptions not tied to current docs.
**How to avoid:** Keep compliance checks tied to documented constraints and re-verify quarterly.
**Warning signs:** Upload rejection despite successful FFmpeg encode.

### Pitfall 5: Apple HLS Workflow Misinterpretation
**What goes wrong:** Building direct upload logic that cannot be used.
**Why it happens:** Assuming Apple HLS publishing works like simple RSS enclosure upload.
**How to avoid:** Treat `apple_hls` as artifact packaging only unless provider API integration is explicitly in scope.
**Warning signs:** Missing provider/API-key path during release workflow.

## Code Examples

Verified patterns from official sources:

### 1) Word-Level Timestamps for Cut Snapping
```python
# Source: https://pypi.org/project/faster-whisper/
from faster_whisper import WhisperModel

model = WhisperModel("large-v3", device="cuda", compute_type="float16")
segments, _ = model.transcribe("audio.mp3", word_timestamps=True)

words = []
for segment in segments:
    for word in segment.words:
        words.append({"start": word.start, "end": word.end, "text": word.word})
```

### 2) Audio Crossfade Between Kept Segments
```bash
# Source: https://ffmpeg.org/ffmpeg-filters.html (acrossfade)
ffmpeg -i first.wav -i second.wav \
  -filter_complex "acrossfade=d=0.15:c1=tri:c2=tri" \
  out.wav
```

### 3) Video Crossfade for Content Joins
```bash
# Source: https://ffmpeg.org/ffmpeg-filters.html (xfade)
ffmpeg -i first.mp4 -i second.mp4 \
  -filter_complex "xfade=transition=fade:duration=0.3:offset=5" \
  out.mp4
```

### 4) HLS Packaging With Variant Mapping
```bash
# Source: https://ffmpeg.org/ffmpeg-all.html (hls muxer options)
ffmpeg -i in.mp4 \
  -f hls -hls_time 6 \
  -master_pl_name master.m3u8 \
  -var_stream_map "v:0,a:0" \
  -hls_segment_filename "segment_%v_%03d.ts" \
  variant_%v.m3u8
```

### 5) Native FFmpeg De-essing
```bash
# Source: https://ffmpeg.org/ffmpeg-filters.html (deesser)
ffmpeg -i in.wav -af "deesser=i=0.2:m=0.5:f=0.5" out.wav
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hard trim+concat only | Trim+concat with micro-fades and selective crossfades | Ongoing best practice; current FFmpeg docs | Reduced click/pop artifacts and less perceptual discontinuity |
| Custom de-esser chains | Native FFmpeg `deesser` | Present in current FFmpeg filters docs | Lower implementation complexity and risk |
| `autowhite`/`autolevels` assumptions | `grayworld` + `normalize` | Verified against current FFmpeg docs | Prevents invalid-filter runtime failures |
| Demucs as likely dereverb default | Demucs marked archived; use optional lightweight alternatives first | Repo archived Jan 1, 2025 | Avoids adopting unmaintained heavy dependency |
| Apple video as MP4-only mental model | Apple prefers HLS workflow via hosting providers/API key; RSS video still available | Apple creator docs for iOS 26.4 era | Requires explicit workflow boundary docs and artifact-first implementation |

**Deprecated/outdated:**
- `autowhite` and `autolevels` filter names in plan notes: not found in current FFmpeg filters docs.
- Demucs as default dereverb dependency: upstream `facebookresearch/demucs` repository is archived and explicitly not maintained.

## Open Questions

1. **Minimum FFmpeg version floor for production deployments**
   - What we know: Latest stable is 8.0.1; docs confirm required filters/options.
   - What's unclear: Oldest deployed FFmpeg version across all target environments.
   - Recommendation: Add startup capability check (`ffmpeg -filters` + probe smoke) and fail-fast with actionable upgrade message.

2. **Dereverb quality vs runtime budget**
   - What we know: `noisereduce` is lightweight; Demucs upstream archived.
   - What's unclear: Whether optional Python pre-pass materially improves real episodes over FFmpeg-only chain.
   - Recommendation: Keep dereverb optional and benchmark on representative noisy-room samples before default-on.

3. **Apple HLS validation depth in CI**
   - What we know: Apple provides streaming docs and validator tooling; `apple_hls` already packaged.
   - What's unclear: Whether current CI has enough HLS conformance checks beyond file existence/topology.
   - Recommendation: Add validator-backed smoke checks for at least one fixture if tooling can run in CI environment.

## Sources

### Primary (HIGH confidence)
- FFmpeg filters documentation (afade, acrossfade, adeclick, deesser, grayworld, normalize, xfade): https://ffmpeg.org/ffmpeg-filters.html
- FFmpeg all documentation (HLS muxer options `hls_time`, `master_pl_name`, `var_stream_map`, `hls_segment_filename`): https://ffmpeg.org/ffmpeg-all.html
- FFmpeg releases/download page (latest stable branch/version): https://www.ffmpeg.org/download.html
- Spotify video specs: https://support.spotify.com/us/creators/article/video-specs/
- Spotify publishing videos recommendations: https://support.spotify.com/us/creators/article/publishing-videos/
- Apple video podcasts using RSS: https://podcasters.apple.com/support/3684-video-podcasts
- Apple “How to publish video” (HLS/provider/API workflow): https://podcasters.apple.com/support/5593-how-to-publish-video
- Apple HLS streaming overview/resources: https://developer.apple.com/streaming/
- faster-whisper package docs (word timestamps + latest package metadata): https://pypi.org/project/faster-whisper/
- faster-whisper release metadata: https://github.com/SYSTRAN/faster-whisper/releases

### Secondary (MEDIUM confidence)
- noisereduce package metadata/releases: https://pypi.org/project/noisereduce/
- noisereduce GitHub releases: https://github.com/timsainb/noisereduce/releases
- pedalboard package metadata/license/version: https://pypi.org/project/pedalboard/
- pedalboard releases: https://github.com/spotify/pedalboard/releases
- Demucs archive/maintenance status: https://github.com/facebookresearch/demucs

### Tertiary (LOW confidence)
- None required for core recommendations.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - based on official FFmpeg/Spotify/Apple/faster-whisper sources.
- Architecture: HIGH - aligns with existing codebase structure and verified filter capabilities.
- Pitfalls: MEDIUM - some are implementation-derived risk patterns, though grounded in documented constraints.

**Research date:** 2026-02-20
**Valid until:** 2026-03-22 (re-verify platform specs and package releases monthly)
