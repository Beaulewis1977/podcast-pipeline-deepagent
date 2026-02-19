# Phase 05: Video Podcast Platforms - Research

**Researched:** 2026-02-19 (re-verified)
**Domain:** Spotify/Apple video podcast export requirements and FFmpeg implementation constraints
**Confidence:** HIGH

## Summary

Phase 05 should continue to prioritize compliant export artifacts and truthful operator workflow constraints, not upload automation. Apple now has two active video paths that must be handled explicitly: (1) RSS video enclosures using documented MP4/M4V/MOV requirements, and (2) a newer HLS-integrated path that is provider-mediated through Apple Podcasts Connect API keys and eligible hosting partners. Apple also states subscriptions remain audio-only.

Spotify guidance is also explicit and implementation-relevant: one video track + one audio track, equal track duration, EDL unsupported, and concrete container/codec/resolution/keyframe guidance. For shows not hosted with Spotify, the workflow remains dashboard-driven in Spotify for Creators web (upload on web, optionally publish draft from mobile) and does not expose a direct in-repo upload API path.

For this repository, the safest plan remains: (1) dedicated `spotify_video` and `apple_video` MP4 profiles, (2) render-time profile/level and topology validation via ffprobe, and (3) optional `apple_hls` packaging as a provider hand-off artifact with clear documentation that publishing is still host/dashboard mediated.

**Primary recommendation:** Ship a mezzanine-first implementation with strict post-render compliance checks and explicit workflow guardrails for Apple HLS and Spotify non-hosted publishing.

## Standard Stack

The established libraries/tools for this domain:

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FFmpeg CLI | Local runtime: 6.1.1; current stable branch observed in FFmpeg release index: 8.0.x (8.0.1 listed) | Encoding and HLS packaging | Required for codec/profile control and HLS muxer options (`var_stream_map`, `master_pl_name`, `hls_segment_filename`, `hls_playlist_type`) |
| ffprobe | Local runtime: 6.1.1 | Post-render compliance checks | Deterministic stream/container inspection for platform rules (track count, duration parity, codec/profile metadata) |
| Pydantic v2 | `>=2.10.0` (project) | Typed config/schema validation | Existing project pattern for failing early on invalid platform specs |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | project dev dependency | Regression coverage for config/render behavior | Every new platform/export path and compliance check |
| structlog | `>=24.4.0` | Structured operator diagnostics | Surface actionable publish/compliance failures |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Always encoding Spotify to H.264 only | Optional HEVC/H.265 support behind explicit config | Spotify supports both in current specs, but H.264 remains the safest default for compatibility |
| Treating Apple HLS as default output | RSS MP4/MOV-only path | Simpler operationally, but misses new Apple integrated video workflow |
| Treating all Spotify doc pages as equally strict | Enforce conservative superset (prefer MP4, honor full video-spec topology rules) | Avoids publish failures when summary/help pages lag detailed spec pages |

**Installation:**
```bash
# No new mandatory Python dependencies for Phase 05 baseline.
# Existing FFmpeg/ffprobe + Python stack is sufficient.
```

## Architecture Patterns

### Recommended Project Structure
```text
src/podcast_pipeline/
├── config/settings.py         # platform schema expansion (profile/level + HLS config)
├── stages/render.py           # MP4 profile wiring, HLS output path, compliance checks
└── ui/app.py                  # export target selection + workflow caveats
tests/
└── test_render.py             # config + render contract regression coverage
```

### Pattern 1: Dual Apple Paths (RSS MP4 + HLS Hand-Off)
**What:** Keep `apple_video` (RSS-friendly MP4) separate from `apple_hls` (provider hand-off package).
**When to use:** Any workflow that must support both broad RSS distribution and Apple HLS partner pipelines.
**Example:**
```bash
# Source: podcasters.apple.com/support/3567-podcast-requirements
ffmpeg -i input.mov \
  -c:v libx264 -profile:v high -level:v 4.0 -pix_fmt yuv420p -b:v 5000k \
  -c:a aac -b:a 160k -ac 2 \
  -movflags +faststart apple_video.mp4
```

### Pattern 2: Spotify Compliance Envelope + ffprobe Validation
**What:** Enforce Spotify topology and timing constraints after render.
**When to use:** Every `spotify_video` render before reporting stage success.
**Example:**
```bash
# Source: support.spotify.com/us/creators/article/video-specs/
ffprobe -v error -show_streams -show_format -of json output.mp4
```

### Pattern 3: HLS via FFmpeg Muxer (No Custom Manifest Logic)
**What:** Generate Apple hand-off HLS assets using FFmpeg muxer primitives.
**When to use:** `apple_hls` target only.
**Example:**
```bash
# Source: ffmpeg.org (verified via Context7)
ffmpeg -i in.ts -map 0:v -map 0:a -map 0:v -map 0:a -f hls \
  -var_stream_map "v:0,a:0 v:1,a:1" \
  -master_pl_name master.m3u8 \
  -hls_segment_filename 'file_%v_%03d.ts' \
  -hls_playlist_type VOD out_%v.m3u8
```

### Anti-Patterns to Avoid
- **Assuming Apple HLS is direct local upload:** official flow is hosting-provider mediated through Apple Podcasts Connect keys.
- **Assuming Spotify non-hosted shows can be uploaded from pipeline directly:** current flow is Spotify for Creators web actions.
- **Ignoring Spotify EDL constraint:** specs explicitly mark edit lists as unsupported.
- **Using stale Apple support IDs/URLs:** Apple moved key pages (`3567`, `904`, `partner-search`).

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stream topology validation | Custom probe/parsing logic | `ffprobe -show_streams -show_format -of json` | Reliable for one-audio/one-video and duration parity checks |
| HLS manifest/segment generation | Custom `.m3u8`/segment emitters | FFmpeg HLS muxer | Handles variant maps and playlist typing correctly |
| Platform policy encoding in code comments only | Informal assumptions | Versioned research + README workflow constraints | Policy pages change; documented verification point prevents regressions |

**Key insight:** Most failures in this phase come from workflow/policy mismatches and stream topology mistakes, not from FFmpeg command syntax.

## Common Pitfalls

### Pitfall 1: Apple RSS and Apple HLS treated as one requirement set
**What goes wrong:** Team encodes one output and assumes both Apple paths accept it identically.
**Why it happens:** Mixing RSS enclosure requirements with HLS provider workflow rules.
**How to avoid:** Maintain explicit `apple_video` and `apple_hls` targets with separate validation.
**Warning signs:** One "apple" target with no distinction between RSS and HLS artifacts.

### Pitfall 2: Spotify non-hosted publish path over-promised
**What goes wrong:** Implementation claims direct publish automation for external hosts.
**Why it happens:** Ignoring Spotify's documented non-hosted replacement workflow in dashboard UI.
**How to avoid:** Document that uploads/replacements occur in Spotify for Creators web after RSS setup.
**Warning signs:** No manual step docs for episodes not hosted with Spotify.

### Pitfall 3: Stream topology or edit-list incompatibility
**What goes wrong:** Files render locally but fail or degrade in ingest/transcode.
**Why it happens:** Missing checks for one-video/one-audio, duration parity, EDL unsupported constraints.
**How to avoid:** Add ffprobe checks and fail render stage on violations.
**Warning signs:** Unexpected ingest warnings despite successful local playback.

### Pitfall 4: Keyframe and timing constraints ignored
**What goes wrong:** Slow seeks or processing issues after ingest.
**Why it happens:** No keyframe cadence targets and no first-frame timing check.
**How to avoid:** Encode with predictable GOP and validate keyframe/timestamp expectations.
**Warning signs:** Spotify processing delays or playback jumpiness on seek.

### Pitfall 5: Apple region/provider availability assumed universal
**What goes wrong:** Team ships HLS path that operators cannot use in their region/provider setup.
**Why it happens:** Skipping `availability` and partner capability checks.
**How to avoid:** Treat provider eligibility and feature availability as release gates.
**Warning signs:** Correct HLS artifacts but blocked publish workflow.

## Code Examples

Verified patterns from official sources:

### Spotify-Oriented MP4 Baseline
```bash
# Source-aligned adaptation from support.spotify.com + ffmpeg.org
ffmpeg -i input.mov \
  -c:v libx264 -profile:v high -level:v 4.1 -pix_fmt yuv420p \
  -g 30 -keyint_min 30 \
  -c:a aac -b:a 192k -ac 2 \
  -movflags +faststart spotify_video.mp4
```

### HLS Playlist Type VOD
```bash
# Source: ffmpeg.org
ffmpeg -re -i in.ts -f hls -hls_playlist_type VOD output.m3u8
```

### HLS Master + Variant Generation
```bash
# Source: ffmpeg.org (verified via Context7)
ffmpeg -i in.ts -b:v:0 1000k -b:v:1 256k -b:a:0 64k -b:a:1 32k \
  -map 0:v -map 0:a -map 0:v -map 0:a -f hls \
  -var_stream_map "v:0,a:0 v:1,a:1" \
  -master_pl_name master.m3u8 \
  -hls_segment_filename 'file_%v_%03d.ts' out_%v.m3u8
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Apple video modeled as RSS-only | Apple adds provider-mediated HLS-integrated video while retaining RSS video support | Apple newsroom announcement: 2026-02-18 | Planning must support two Apple delivery paths and explicit provider/API-key workflow gates |
| Spotify guidance focused on basic H.264 upload tips | Spotify video specs now publish detailed container/topology/timing/color constraints and include H.265 compatibility | Current creator support docs (verified 2026-02-19) | Enables deterministic compliance validation instead of best-effort uploads |

**Deprecated/outdated assumptions:**
- "Apple video requirements are only in old RSS guidance."
- "Spotify video can be treated as any MP4 if it plays locally."
- "The old non-hosted Spotify article URL is canonical."

## Open Questions

1. **Should `spotify_video` default stay on H.264 or expose H.265 first-class now?**
   - What we know: Spotify currently lists both H.264 and H.265 as recommended codecs.
   - What's unclear: Downstream compatibility and operator expectations across all distribution touchpoints.
   - Recommendation: Keep H.264 default, allow H.265 opt-in with explicit tests.

2. **Do we hard-fail on suspected edit lists (EDL) or only warn?**
   - What we know: Spotify marks EDL unsupported.
   - What's unclear: Best deterministic detection strategy with ffprobe-only checks.
   - Recommendation: Start with strict warning + telemetry, then promote to fail once detection is reliable.

3. **Minimum FFmpeg version gate for team environments**
   - What we know: Local runtime is 6.1.1; documented options used in this phase are available.
   - What's unclear: Lowest version we should officially support across all developer machines/CI.
   - Recommendation: Add runtime version reporting and fail/warn below tested baseline.

## Sources

### Primary (HIGH confidence)
- Context7 `/websites/ffmpeg_ffmpeg-all` - HLS muxer options (`var_stream_map`, `master_pl_name`, `hls_segment_filename`, `hls_playlist_type`) and encoding examples
- FFmpeg documentation: https://ffmpeg.org/ffmpeg-all.html
- FFmpeg formats documentation: https://ffmpeg.org/ffmpeg-formats.html
- FFmpeg releases/download index: https://ffmpeg.org/download.html
- Spotify video specs: https://support.spotify.com/us/creators/article/video-specs/
- Spotify publishing videos: https://support.spotify.com/us/creators/article/publishing-videos/
- Spotify non-hosted workflow (current slug): https://support.spotify.com/us/creators/article/video-episodes-for-shows-not-hosted-with-spotify/
- Apple podcast requirements (canonical): https://podcasters.apple.com/support/3567-podcast-requirements
- Apple video podcasts support (RSS path): https://podcasters.apple.com/support/3684-video-podcasts
- Apple publish video (HLS/provider workflow): https://podcasters.apple.com/support/5593-how-to-publish-video
- Apple feature availability (canonical): https://podcasters.apple.com/support/904-availability-of-apple-podcasts-features
- Apple hosting partner directory: https://podcasters.apple.com/partner-search
- Apple newsroom announcement (2026-02-18): https://www.apple.com/newsroom/2026/02/apple-introduces-a-new-video-podcast-experience-on-apple-podcasts/

### Secondary (MEDIUM confidence)
- Perplexity search/ask used for discovery and contradiction checks only; planning decisions retained only when verified against primary sources above.

### Tertiary (LOW confidence)
- None retained for implementation-critical decisions.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - grounded in FFmpeg docs + local runtime audit.
- Architecture: HIGH - based on current codebase constraints and official platform workflow docs.
- Pitfalls: HIGH - directly supported by Apple/Spotify requirement and workflow pages.

**Research date:** 2026-02-19
**Valid until:** 2026-03-21 (re-check Apple/Spotify support pages before coding if execution starts later)
