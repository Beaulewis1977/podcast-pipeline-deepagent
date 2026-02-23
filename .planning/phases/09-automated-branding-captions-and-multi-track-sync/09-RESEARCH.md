# Phase 9: Automated Branding, Captions, and Multi-Track Sync - Research

**Researched:** 2026-02-23
**Domain:** Deterministic FFmpeg media orchestration for branding, captions, sync, and thumbnail generation
**Confidence:** HIGH (core stack and APIs), MEDIUM (hardware-specific encode quality and local FLUX performance variability)

## Summary

Phase 9 should be implemented as a deterministic media pipeline with strict separation between analysis-time AI and execution-time media transforms. The right architecture is: typed Python toolkit functions for all media actions, explicit render orchestration in `RenderStage`, and a dev-only FastMCP adapter over the same toolkit for local testing. Do not let any LLM generate production FFmpeg commands at runtime.

The current ecosystem is favorable for this phase. Official docs now clearly support the planned stack: FFmpeg 8.0.1 stable is current, ASS and subtitles filter behavior is documented, `sidechaincompress` is mature, SciPy/librosa cover bounded sync math, Imagen 4 GA model IDs are stable, and Anthropic Python SDK supports direct structured `messages.create` workflows. FastMCP is actively maintained and its server-first pattern (`FastMCP`, `@mcp.tool`, `mcp.run()`) matches the thin-wrapper design in the phase spec.

Version floors in roadmap/spec remain valid, but planning should target latest stable package releases where no compatibility conflict exists. Use minimum constraints for compatibility, but test and lock against current stable builds in this phase branch.

**Primary recommendation:** Build Phase 9 as a typed, test-first deterministic media core (`ffmpeg_toolkit.py`) with explicit boundaries: AI decides *what*, Python/FFmpeg decides *how*.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version (latest stable checked 2026-02-23) | Purpose | Why Standard |
|---------|---------------------------------------------|---------|--------------|
| FFmpeg CLI + ffprobe | 8.0.1 stable branch | All encode/filter/edit/package operations | Canonical media toolkit with required filters (`ass`, `subtitles`, `sidechaincompress`) |
| Pydantic | 2.12.5 | Typed I/O models and validation for 14-tool media toolkit | Existing project standard for config/schema contracts |
| SciPy | 1.17.1 | Cross-correlation (`signal.correlate`, `correlation_lags`) for sync offset detection | Standard scientific signal-processing primitive |
| librosa | 0.11.0 | Fast bounded downsample/resample front-end before correlation | Practical pre-processing layer around resampling workflows |
| Anthropic Python SDK | 0.83.0 | Claude provider implementation for analysis-stage JSON outputs | Official supported Python client with sync/async/streaming and retries |
| FastMCP | 3.0.2 | Dev-only MCP server wrapper over toolkit functions | Thin decorator-driven tool exposure with active maintenance |

### Supporting
| Library | Version (latest stable checked 2026-02-23) | Purpose | When to Use |
|---------|---------------------------------------------|---------|-------------|
| google-genai | 1.64.0 | Programmatic Imagen image generation calls | Preferred when using Vertex-backed Imagen 4 from Python |
| google-cloud-aiplatform | 1.138.0 | Vertex AI client stack and ImageGenerationModel APIs | Needed for existing Vertex integrations and enterprise auth flows |
| diffusers | 0.36.0 | Local FLUX pipelines | Local thumbnail fallback and offline generation |
| optimum-quanto | 0.2.7 | Quantized local model loading | FLUX VRAM fit and faster local inference |
| torch | 2.10.0 | Runtime for local diffusion/quantization | Required backend for local FLUX inference |
| streamlit | 1.54.0 | Brand Studio and Production control surfaces | Existing UI stack in this codebase |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastMCP wrapper | Low-level MCP SDK | More boilerplate and manual schema work with no Phase 9 benefit |
| `ass` filter for ASS files | `subtitles` filter for all subtitle formats | `subtitles` handles broader formats but adds libavcodec/libavformat dependency; for ASS-first pipeline, `ass` is simpler |
| SciPy correlation | Pure NumPy ad-hoc correlation loops | Reinvents validated primitives and increases risk of indexing/lag errors |
| Deterministic toolkit orchestration | Agentic FFmpeg command generation | Higher failure surface, nondeterminism, and harder regression control |

**Installation:**
```bash
# Core additions for Phase 9
uv add anthropic scipy

# Dev-only MCP server
uv add --group dev fastmcp

# Thumbnail extras
uv add --optional thumbnails google-cloud-aiplatform google-genai diffusers optimum-quanto
```

## Architecture Patterns

### Recommended Project Structure
```text
src/podcast_pipeline/
├── models/branding.py            # BrandingProfile, platform overrides, validation
├── utils/ffmpeg_toolkit.py       # 14 typed deterministic media tools
├── utils/captions.py             # word_alignment -> ASS generators (per aspect ratio)
├── utils/sync.py                 # bounded resample + correlation + confidence scoring
├── utils/thumbnails.py           # Imagen 4 + local FLUX backend selection/cache
├── providers/claude_provider.py  # AnalysisProvider implementation via anthropic SDK
├── mcp/ffmpeg_server.py          # Dev-only FastMCP wrappers over toolkit
├── stages/render.py              # Orchestration only; no agentic FFmpeg graph synthesis
└── ui/app.py                     # Brand Studio + Production controls (manual sync fallback)
```

### Pattern 1: Deterministic Media Core + Thin Adapters
**What:** Implement every media operation once in `ffmpeg_toolkit.py`, then expose it via two adapters:
1. Production: direct Python calls from stages
2. Dev: FastMCP wrappers in `mcp/ffmpeg_server.py`

**When to use:** All 14 planned tools.

**Example:**
```python
# Source: https://github.com/PrefectHQ/fastmcp/blob/main/README.md
from fastmcp import FastMCP
from podcast_pipeline.utils import ffmpeg_toolkit as tk

mcp = FastMCP("ffmpeg-toolkit")

@mcp.tool
def probe_media(path: str) -> dict:
    return tk.probe_media(path).model_dump()
```

### Pattern 2: Branding Resolution Pipeline (Base -> Platform Override -> Render)
**What:** Load a base `BrandingProfile`, merge platform override if present, pass resolved style into:
1. Prompt-building (`brand_voice`)
2. Caption generation
3. Overlay and thumbnail post-processing

**When to use:** Every target export path.

**Example:**
```python
resolved = base_profile
if platform in base_profile.platform_overrides:
    resolved = base_profile.merge_override(platform)
```

### Pattern 3: Two-Step Caption Pipeline (Compile ASS then Burn)
**What:** Keep caption generation separate from render invocation:
1. Build ASS from word alignment + style templates
2. Burn with FFmpeg `ass=` filter in render

**When to use:** Burned-in social captions with word highlighting.

**Example:**
```bash
# Source: https://ffmpeg.org/ffmpeg-filters.html#ass
ffmpeg -i input.mp4 -vf "ass=temp.ass" -c:v libx264 -c:a copy output.mp4
```

### Pattern 4: Bounded Sync Pipeline with Confidence + Manual Fallback
**What:** Sync with bounded compute:
1. Downsample bounded head window
2. Correlate and compute lag
3. Emit confidence and apply offset
4. Expose UI slider fallback for low-confidence cases

**When to use:** Separate recorder + camera track alignment.

**Example:**
```python
# Source: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html
# Source: https://librosa.org/doc/main/generated/librosa.resample.html
corr = signal.correlate(ref_window, ext_window, mode="full", method="auto")
lags = signal.correlation_lags(ref_window.size, ext_window.size, mode="full")
offset_samples = int(lags[corr.argmax()])
```

### Pattern 5: Provider Strategy for Thumbnails (Imagen First, Local FLUX Fallback)
**What:** Try Imagen 4 GA first when credentials and quota are available; otherwise route to local FLUX backend with quantized profile and VRAM preflight.

**When to use:** Thumbnail generation path in analyze/review workflows.

**Example:**
```python
# Source: https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images
image = client.models.generate_images(
    model="imagen-4.0-generate-001",
    prompt=prompt,
)
```

### Pattern 6: Render Orchestrator as Contract Enforcer
**What:** `RenderStage` should enforce sequence and artifact checks:
1. preflight
2. sync/caption/branding/audio mix
3. encode
4. compliance validation

**When to use:** Every platform export path.

### Anti-Patterns to Avoid
- **Agentic FFmpeg in production:** no dynamic LLM-generated filtergraphs at runtime.
- **Combining caption generation and burn in one ad-hoc command builder:** makes tests brittle.
- **Using MCP server in production execution path:** MCP is dev tooling only.
- **Unbounded correlation on full tracks:** high compute and false-match risk.
- **Hardcoding one codec path without capability check:** breaks GPU/CPU portability.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ASS rendering engine | Custom frame-by-frame subtitle compositor | FFmpeg `ass`/`subtitles` + libass | Existing engine already supports timing/layout/styling edge cases |
| Audio lag estimation | Manual nested-loop waveform matcher | SciPy `signal.correlate` + `correlation_lags` | Trusted implementation and clearer lag semantics |
| Resampling for sync prep | Custom downsample math | `librosa.resample` | Mature resampling options and defaults |
| Tool schema transport | Hand-written MCP schemas for each function | FastMCP `@mcp.tool` auto schema generation | Reduces maintenance and schema drift |
| Retry/timeouts for Claude requests | Custom retry wrappers around raw HTTP | Anthropic SDK `max_retries` and client options | Standardized error/retry semantics |
| Platform video rules parsing | New parser stack for every target | Existing render compliance checks + official specs | Keeps compliance deterministic and testable |

**Key insight:** The engineering risk in Phase 9 is orchestration complexity, not missing primitives. Reuse mature primitives aggressively and focus custom code on wiring and guarantees.

## Common Pitfalls

### Pitfall 1: Confusing `ass` vs `subtitles` filter behavior
**What goes wrong:** Missing dependencies or unexpected subtitle conversion paths.
**Why it happens:** `subtitles` requires libavcodec/libavformat for conversion to ASS; `ass` is ASS-only.
**How to avoid:** Use `ass=` for generated ASS files; reserve `subtitles=` for non-ASS inputs.
**Warning signs:** Runtime errors around filter availability or subtitle conversion.

### Pitfall 2: Sidechain ducking values copied without unit/context checks
**What goes wrong:** Over-compression or pumping.
**Why it happens:** `sidechaincompress` defaults are linear-domain values; users think only in dB.
**How to avoid:** Map config to explicit filter arguments and regression-test attack/release behavior with fixture audio.
**Warning signs:** Voice level collapses under stingers or audible pumping between phrases.

### Pitfall 3: Cross-correlation false positives on silence/music
**What goes wrong:** Wrong offset gets applied with high confidence.
**Why it happens:** Noisy or low-energy windows produce ambiguous peaks.
**How to avoid:** Pre-emphasis/bandpass voice band, bound search windows, and threshold confidence before auto-apply.
**Warning signs:** Large computed offsets on clips that sound visually close.

### Pitfall 4: HEVC path mismatch between declared profile/pixel format and encoder support
**What goes wrong:** Encode failures or silent fallback behavior.
**Why it happens:** `main10`/10-bit settings requested without compatible encoder/path.
**How to avoid:** Detect encoder capability up front and keep explicit `libx265` fallback.
**Warning signs:** FFmpeg errors about unsupported profile/pix_fmt.

### Pitfall 5: Local FLUX OOM due residual GPU allocations
**What goes wrong:** Thumbnail generation crashes intermittently.
**Why it happens:** Other models remain loaded; no VRAM preflight.
**How to avoid:** Unload prior GPU models before FLUX load and require free-memory threshold checks.
**Warning signs:** OOM only on second or later thumbnail attempts.

### Pitfall 6: Prompt injection surface in `brand_voice`
**What goes wrong:** User voice text breaks structural output requirements.
**Why it happens:** Free-text inserted without delimiting/sanitization.
**How to avoid:** Clamp length, strip control chars, and isolate `brand_voice` section from schema instructions.
**Warning signs:** Provider returns malformed JSON or drifts from required keys.

### Pitfall 7: Shipping dev MCP server as runtime dependency
**What goes wrong:** Production execution depends on local server process assumptions.
**Why it happens:** Missing architecture boundary in implementation.
**How to avoid:** Keep MCP module isolated and unreferenced by pipeline runtime paths.
**Warning signs:** Render path tries to call MCP transport or localhost.

## Code Examples

Verified patterns from official sources:

### 1) FastMCP tool exposure from typed functions
```python
# Source: https://github.com/PrefectHQ/fastmcp/blob/main/README.md
from fastmcp import FastMCP

mcp = FastMCP("Demo")

@mcp.tool
def add(a: int, b: int) -> int:
    return a + b

if __name__ == "__main__":
    mcp.run()
```

### 2) Anthropic provider request pattern
```python
# Source: https://github.com/anthropics/anthropic-sdk-python/blob/main/README.md
from anthropic import Anthropic

client = Anthropic()
message = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Analyze this transcript"}],
)
```

### 3) Bounded lag estimation with SciPy
```python
# Source: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html
from scipy import signal

corr = signal.correlate(ref_window, ext_window, mode="full", method="auto")
lags = signal.correlation_lags(len(ref_window), len(ext_window), mode="full")
offset = int(lags[corr.argmax()])
```

### 4) FFmpeg ASS burn-in
```bash
# Source: https://ffmpeg.org/ffmpeg-filters.html#ass
ffmpeg -i in.mp4 -vf "ass=captions.ass" -c:v libx264 -c:a copy out.mp4
```

### 5) FFmpeg sidechain ducking
```bash
# Source: https://ffmpeg.org/ffmpeg-filters.html#sidechaincompress
ffmpeg -i speech.wav -i stinger.wav \
  -filter_complex "[0:a][1:a]sidechaincompress=threshold=0.125:ratio=4:attack=5:release=200[out]" \
  -map "[out]" ducked.wav
```

### 6) Imagen 4 GA generation call
```python
# Source: https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images
image = client.models.generate_images(
    model="imagen-4.0-generate-001",
    prompt="Podcast thumbnail with high contrast lighting",
)
```

### 7) FLUX schnell parameter shape
```python
# Source: https://raw.githubusercontent.com/huggingface/diffusers/main/docs/source/en/api/pipelines/flux.md
image = pipe(
    prompt=prompt,
    guidance_scale=0.0,
    num_inference_steps=4,
).images[0]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded styling constants | `BrandingProfile` + platform override merge | Phase 9 design baseline | Enables repeatable multi-brand output without code edits |
| Static subtitle overlays | ASS-driven word-level highlighting with libass | Current FFmpeg guidance | Better engagement and style control |
| Full-track sync attempts | Bounded-window correlation + confidence + manual override | Current practical pipeline pattern | More predictable compute and safer auto-sync behavior |
| H.264-only assumptions | HEVC main10 default with explicit fallback paths | Current platform support norms | Better quality/size tradeoff where supported |
| LLM-driven media command generation | Deterministic typed media toolkit + AI analysis only | Phase 9 spec constraint | Stronger reliability, testability, and security |
| MCP as runtime bridge | MCP as dev-only wrapper over same toolkit | FastMCP ecosystem maturity | Faster developer iteration without runtime coupling |

**Deprecated/outdated:**
- Treating FastMCP `>=2.0.0` as "current enough" without explicit migration checks. Latest stable is 3.0.2; plan should validate v2->v3 differences if older examples are copied.
- Treating Imagen 4 preview model IDs as permanent. Vertex docs now explicitly call out migration to current GA model IDs.

## Open Questions

1. **Minimum supported FFmpeg runtime version for deployment**
   - What we know: 8.0.1 is current stable; this environment currently reports FFmpeg 6.1.1.
   - What's unclear: Lowest deployed version across all production-like environments.
   - Recommendation: Add startup capability checks for required filters/encoders and fail fast with upgrade guidance.

2. **Claude model-ID policy for config defaults**
   - What we know: Anthropic SDK examples use dated model IDs; phase spec proposes alias-style IDs.
   - What's unclear: Whether codebase should pin dated IDs or allow moving aliases by default.
   - Recommendation: Use config-driven model IDs with tests for supported defaults and documented override behavior.

3. **Local FLUX quantization backend default (`torchao` vs `optimum-quanto`)**
   - What we know: Diffusers docs support both pathways; hardware benefits vary by GPU and precision.
   - What's unclear: Best quality/perf tradeoff on your exact 16 GB GPU workload.
   - Recommendation: Benchmark both on fixed prompts and lock one backend for Phase 9 initial rollout.

4. **Auto-sync confidence gating threshold**
   - What we know: Correlation peak can be converted to confidence metric.
   - What's unclear: Threshold that minimizes false auto-alignments on real episodes.
   - Recommendation: Calibrate on fixture set and define policy for auto-apply vs manual-only.

## Sources

### Primary (HIGH confidence)
- FFmpeg stable releases/download page (8.0.1 latest stable): https://ffmpeg.org/download.html
- FFmpeg filters docs (`ass`, `subtitles`, `sidechaincompress`, `grayworld`, `normalize`): https://ffmpeg.org/ffmpeg-filters.html
- FFmpeg codecs docs (`libsvtav1`, `libx265`): https://ffmpeg.org/ffmpeg-codecs.html
- SciPy correlate API: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html
- librosa resample API: https://librosa.org/doc/main/generated/librosa.resample.html
- Vertex Imagen generation docs (Imagen 4 GA model IDs and SDK usage): https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images
- Anthropic Python SDK README: https://github.com/anthropics/anthropic-sdk-python
- FastMCP README: https://github.com/PrefectHQ/fastmcp
- FastMCP docs bundle (`llms-full.txt`): https://gofastmcp.com/llms-full.txt
- Diffusers FLUX docs: https://raw.githubusercontent.com/huggingface/diffusers/main/docs/source/en/api/pipelines/flux.md
- Diffusers torchao quantization docs: https://raw.githubusercontent.com/huggingface/diffusers/main/docs/source/en/quantization/torchao.md
- Diffusers quanto docs: https://raw.githubusercontent.com/huggingface/diffusers/main/docs/source/en/quantization/quanto.md
- Spotify video specs (container/codec/layout recommendations): https://support.spotify.com/us/creators/article/video-specs/
- Apple video podcasts using RSS: https://podcasters.apple.com/support/3684-video-podcasts
- Apple HLS publish workflow: https://podcasters.apple.com/support/5593-how-to-publish-video
- PyPI package metadata (latest stable versions used in this research): https://pypi.org/

### Secondary (MEDIUM confidence)
- Local runtime encoder capability checks (`ffmpeg -h encoder=hevc_nvenc`) and local FFmpeg version observations from current dev environment.

### Tertiary (LOW confidence)
- Perplexity ecosystem scan surfaced non-authoritative community pages; not used for critical technical decisions:
  - https://risegravity.com/projects/ai-short-studio
  - https://mcpmarket.com/tools/skills/ffmpeg-kinetic-captions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official docs and package metadata confirm APIs and current versions.
- Architecture: HIGH - Derived directly from official APIs plus locked Phase 9 constraints.
- Pitfalls: MEDIUM - Most are source-backed; some hardware/performance items require local benchmarking.

**Research date:** 2026-02-23
**Valid until:** 2026-03-25 (re-check versions/models before implementation start if delayed)
