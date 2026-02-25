# Phase 09-11: Gemini Vision Model Pivot — Research

**Researched:** 2026-02-24
**Domain:** google.genai SDK — image generation and vision analysis with Gemini Vision models
**Confidence:** HIGH (model IDs verified via official docs; SDK API verified via introspection of installed google-genai==1.60.0)

---

## Summary

This research covers the exact google.genai SDK API needed to replace Imagen 4 GA and FLUX.1 Schnell in `thumbnails.py` with two Gemini Vision models. The models specified in the override document (`gemini-2.5-flash-image` and `gemini-3-pro-image-preview`) are **confirmed real model IDs** by official Google AI documentation.

The key finding is that the same `client.models.generate_content()` call is used for both image generation and vision analysis — the difference is only in the `config.response_modalities` and what content is passed in. For image generation, set `response_modalities=['TEXT', 'IMAGE']`. For vision analysis, no special config is needed (default text-only response). Image output arrives as `part.inline_data.data` (raw bytes) with `part.inline_data.mime_type`. The SDK's Gemini `Image` type has a `.save(path)` method that writes bytes directly without requiring PIL.

The existing project infrastructure (`google-genai>=1.0.0` already installed at 1.60.0, `genai.Client(api_key=...)` pattern already used in `gemini.py` provider) means this refactor is additive, not architectural.

**Primary recommendation:** Use `genai.Client(api_key=os.environ["GEMINI_API_KEY"])` + `client.models.generate_content(model=MODEL_ID, contents=[prompt], config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"], image_config=types.ImageConfig(aspect_ratio="16:9")))` for image generation; use `client.models.generate_content(model=MODEL_ID, contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), prompt_text])` for vision analysis.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-genai` | `>=1.0.0` (installed: 1.60.0) | Unified Gemini API client — image gen AND vision analysis | Already in core deps; SDK used elsewhere in this project |
| `tenacity` | `>=9.0.0` | Retry logic with exponential backoff for 429 rate-limit errors | Already used in `GeminiProvider`; do not hand-roll retry |
| `structlog` | `>=24.4.0` | Structured logging | Project standard |
| `pydantic` | `>=2.10.0` | Config models (`ThumbnailGenerationConfig`) | Project standard |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `Pillow` (PIL) | Optional | Only needed if using `part.as_image()` convenience method | Do NOT add as required dep — use `part.inline_data.data` bytes directly instead |
| `pathlib.Path` | stdlib | Writing image bytes to disk | Use `Path(location).write_bytes(img_bytes)` instead of PIL save |

### Alternatives Considered (REJECTED — do not use)

| Instead of | Could Use | Why Rejected |
|------------|-----------|--------------|
| `google-genai` | `google-cloud-aiplatform` | Vertex AI is being removed; google-genai is the unified SDK per project decision |
| `google-genai` | `diffusers` + FLUX.1 | Local GPU inference is being removed; Gemini API is cloud-only, no VRAM requirement |
| `part.as_image()` | PIL Image object | PIL is an optional dep not in core requirements; `inline_data.data` bytes are sufficient |

### Dependencies: Remove from pyproject.toml `[thumbnails]` group

```toml
# REMOVE these three:
"google-cloud-aiplatform>=1.70.0,<2"
"diffusers>=0.32.0,<1"
"optimum-quanto>=0.2.5,<1"
```

`google-genai` is already in `[project.dependencies]` (core), so `[thumbnails]` can be left empty or removed.

---

## Architecture Patterns

### Model Constants

```python
# Source: official Google AI docs (ai.google.dev/gemini-api/docs/models)
GEMINI_VISION_PRO = "gemini-3-pro-image-preview"   # Prompt generation, audit, compositional analysis
GEMINI_VISION_FLASH = "gemini-2.5-flash-image"     # Image generation, layout validation (fast)
```

Both model IDs are confirmed GA / Preview by official docs as of 2026-02-24.

- `gemini-2.5-flash-image` — Generally Available (GA). Codename "Nano Banana". Optimized for speed/cost.
- `gemini-3-pro-image-preview` — Preview. Codename "Nano Banana Pro". 4K output, reasoning core.

### ThumbnailBackend Enum — Replacement

Replace the dual `IMAGEN4 / FLUX` enum with a single `GEMINI` value:

```python
class ThumbnailBackend(str, Enum):
    GEMINI = "gemini"   # Replaces IMAGEN4 and FLUX
    NONE = "none"       # Kept: graceful degradation path
```

### Recommended Project Structure (no changes to layout)

The existing `src/podcast_pipeline/utils/thumbnails.py` structure is preserved:
- Constants section → update model IDs, remove FLUX/Imagen constants
- Cache helpers → keep `compute_cache_key` and `_cache_path` unchanged
- Generation function → replace `_generate_imagen4` + `_generate_flux` with `_generate_gemini`
- Vision analysis function → new `_audit_with_gemini_pro` for compositional/prompt auditing
- Branding overlay → keep `_apply_branding_overlay` unchanged
- `ThumbnailService` class → update `_select_backend` and `_run_backend`

### Pattern 1: Image Generation (gemini-2.5-flash-image)

**What:** Generate thumbnail images from text prompts using `generate_content` with IMAGE modality.
**When to use:** Cache miss — no existing file for this prompt/model/dimension/seed combo.

```python
# Source: official Google AI docs (ai.google.dev/gemini-api/docs/image-generation) +
#         introspection of google-genai 1.60.0 types
from google import genai
from google.genai import types

def _generate_gemini(
    prompt: str,
    output_dir: Path,
    *,
    model: str,
    aspect_ratio: str,
    seed: int | None,
) -> list[tuple[Path, bool]]:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,       # e.g. "16:9" for 1280x720
            image_size="2K",                 # "1K", "2K", or "4K"
            output_mime_type="image/jpeg",   # optional; PNG is default
        ),
        seed=seed,  # int | None — deterministic generation when set
    )
    response = client.models.generate_content(
        model=model,          # "gemini-2.5-flash-image"
        contents=[prompt],
        config=config,
    )

    results: list[tuple[Path, bool]] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for part in response.parts:
        if part.inline_data is not None and part.inline_data.data:
            img_bytes: bytes = part.inline_data.data
            mime_type: str = part.inline_data.mime_type or "image/jpeg"
            ext = "png" if "png" in mime_type else "jpg"
            # Cache key computed externally; caller moves file to canonical path
            out_path = output_dir / f"generated_{len(results)}.{ext}"
            out_path.write_bytes(img_bytes)
            results.append((out_path, False))

    return results
```

### Pattern 2: Vision Analysis (gemini-3-pro-image-preview)

**What:** Analyze an existing image (e.g., extracted video frame) for compositional quality, face obstruction check, or prompt engineering.
**When to use:** Auditing branding overlays; generating refined thumbnail prompts from frame context.

```python
# Source: official Google AI docs (ai.google.dev/gemini-api/docs/vision) +
#         introspection of google-genai 1.60.0 types.Part.from_bytes
from google import genai
from google.genai import types

def _audit_with_gemini_pro(
    image_path: Path,
    audit_prompt: str,
    *,
    model: str = "gemini-3-pro-image-preview",
) -> str:
    """Analyze an image and return the model's text response."""
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    image_bytes = image_path.read_bytes()

    # Detect mime type from extension
    mime_type = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            audit_prompt,
        ],
    )
    return response.text or ""
```

### Pattern 3: Client Initialization (match existing project pattern)

The project already uses this pattern in `gemini.py`:

```python
# Source: src/podcast_pipeline/providers/gemini.py (existing pattern)
from google import genai

client = genai.Client(api_key=self.api_key)
# api_key comes from GEMINI_API_KEY env var via config.api_keys.gemini
```

Do NOT use `genai.Client()` without an api_key (it will attempt ADC/Vertex AI auth which is being removed).

### Pattern 4: Availability Check (replaces _imagen4_available + _flux_available)

```python
def _gemini_available() -> tuple[bool, str]:
    """Return (available, reason) for Gemini Vision backend."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return False, "GEMINI_API_KEY environment variable not set"
    try:
        from google import genai  # noqa: F401
    except ImportError:
        return False, "google-genai not installed"
    return True, ""
```

### Anti-Patterns to Avoid

- **Do NOT pass `part.as_image()`** — this requires PIL. Access `part.inline_data.data` (raw bytes) directly and write with `Path.write_bytes()`.
- **Do NOT use `google.cloud.aiplatform`** — Vertex AI is removed. Use `google.genai` only.
- **Do NOT hand-roll retry logic** — use `tenacity` with `retry_if_exception_type` matching HTTP 429 errors (same as existing `GeminiProvider`).
- **Do NOT remove `response_modalities`** — for image generation, `["TEXT", "IMAGE"]` must be explicitly set; omitting it returns text-only responses.
- **Do NOT use `ImageConfig(imageSize="2K")`** — the Python SDK uses snake_case field names: `image_size="2K"` (confirmed via `types.ImageConfig.model_fields`).
- **Do NOT pass `aspect_ratio="16:9"` at 1280x720** — the API takes aspect ratio, not pixel dimensions; `"16:9"` is correct for YouTube thumbnails.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry on 429 rate-limit | Custom sleep/retry loop | `tenacity` with `retry_if_exception_type(RateLimitError)` | Handles jitter, max attempts, reraise — already used in `GeminiProvider` |
| Image bytes to disk | PIL open/save pipeline | `Path(out_path).write_bytes(part.inline_data.data)` | SDK delivers raw bytes; no decode/re-encode needed |
| Cache key hashing | Custom hash scheme | Existing `compute_cache_key()` in thumbnails.py | Already correct; just update `model` argument to use Gemini model ID |
| Image MIME detection | Extension parsing | `part.inline_data.mime_type` from response | API returns correct MIME type with image bytes |
| Prompt-hash cache | Any new mechanism | Existing `compute_cache_key` + `_cache_path` | No changes needed — model key changes from Imagen ID to Gemini ID |
| Branding overlay | Any new overlay | Existing `_apply_branding_overlay` (FFmpeg toolkit) | Unchanged — operates on file paths, not model-specific |

**Key insight:** The API surface change is narrow — only the generation function changes. The cache, branding, service orchestration, and retry layers are preserved with minimal modification.

---

## Common Pitfalls

### Pitfall 1: Missing `response_modalities`
**What goes wrong:** `generate_content` returns only text; no `inline_data` parts; loop produces zero images silently.
**Why it happens:** Default modality for Gemini models is text-only. Image generation is opt-in.
**How to avoid:** Always pass `config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])` when calling image generation models.
**Warning signs:** `len([p for p in response.parts if p.inline_data]) == 0` despite a generation model.

### Pitfall 2: Wrong `ImageConfig` Field Names
**What goes wrong:** Pydantic validation error or silently ignored parameters.
**Why it happens:** SDK uses `snake_case` aliases in Python (`image_size`, `aspect_ratio`) but docs may show camelCase (`imageSize`, `aspectRatio`).
**How to avoid:** Use `types.ImageConfig(image_size="2K", aspect_ratio="16:9")` — confirmed by `types.ImageConfig.model_fields` inspection.
**Warning signs:** `TypeError: unexpected keyword argument 'imageSize'`.

### Pitfall 3: `part.as_image()` requires PIL
**What goes wrong:** `ImportError: PIL/Pillow not installed` at runtime on image generation response.
**Why it happens:** `as_image()` internally creates a `PIL.Image` object.
**How to avoid:** Access raw bytes via `part.inline_data.data` and write with `Path.write_bytes()`. Do NOT use `as_image()`.
**Warning signs:** Test passes in environment with Pillow but fails in CI without it.

### Pitfall 4: Test Mocks — Wrong Patch Path
**What goes wrong:** Old tests patch `podcast_pipeline.utils.thumbnails._imagen4_available` or `_flux_available` which no longer exist.
**Why it happens:** The refactored module removes these private functions.
**How to avoid:** New tests patch `podcast_pipeline.utils.thumbnails._gemini_available` and mock `google.genai.Client.models.generate_content`.
**Warning signs:** `AttributeError: module 'podcast_pipeline.utils.thumbnails' has no attribute '_imagen4_available'`.

### Pitfall 5: Model ID Strings
**What goes wrong:** `404 model not found` or `invalid model` API error.
**Why it happens:** Incorrect model ID strings. There is no `gemini-2.5-flash-image-preview` (that's a different model); the correct IDs are exact as specified.
**How to avoid:** Use exactly:
  - `"gemini-2.5-flash-image"` — image generation (GA)
  - `"gemini-3-pro-image-preview"` — vision analysis + image generation (Preview)
**Warning signs:** `google.api_core.exceptions.NotFound: 404 models/...`.

### Pitfall 6: Seed Support
**What goes wrong:** Seed not supported or ignored for image generation.
**Why it happens:** `GenerateContentConfig` has a `seed` field but image models may not honor it the same way as Imagen.
**How to avoid:** Pass `config=types.GenerateContentConfig(seed=seed)` but do not rely on determinism for testing. Use mock patching instead.
**Warning signs:** Different images generated despite same seed across runs.

### Pitfall 7: Test Cache-Key Model Strings
**What goes wrong:** Existing tests that hardcode `"imagen-4.0-generate-001"` as the model for `compute_cache_key` break because `ThumbnailRequest.model` now defaults to `GEMINI_VISION_FLASH`.
**Why it happens:** Cache key is computed from `(prompt, model, width, height, seed, index)`. If model string changes, existing cached files no longer match.
**How to avoid:** Update test fixtures to use `GEMINI_VISION_FLASH` (`"gemini-2.5-flash-image"`) as the model string in `compute_cache_key` calls. This is intentional — old Imagen cache files are invalid for the new backend.

---

## Code Examples

Verified patterns from official docs and SDK introspection:

### Image Generation (full working example)

```python
# Source: ai.google.dev/gemini-api/docs/image-generation + google-genai 1.60.0 introspection
import os
from pathlib import Path
from google import genai
from google.genai import types

GEMINI_VISION_FLASH = "gemini-2.5-flash-image"

def _generate_gemini(
    prompt: str,
    output_dir: Path,
    *,
    model: str = GEMINI_VISION_FLASH,
    seed: int | None = None,
) -> list[tuple[Path, bool]]:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key)

    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio="16:9",        # YouTube thumbnail aspect ratio
            image_size="2K",            # 2048px — good for 1280x720 downscale
            output_mime_type="image/jpeg",
        ),
        seed=seed,
    )

    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=config,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[Path, bool]] = []

    for i, part in enumerate(response.parts):
        if part.inline_data is not None and part.inline_data.data:
            img_bytes = part.inline_data.data
            ext = "jpg" if (part.inline_data.mime_type or "").endswith("jpeg") else "png"
            out_path = output_dir / f"gen_{i}.{ext}"
            out_path.write_bytes(img_bytes)
            results.append((out_path, False))

    return results
```

### Vision Analysis (passing existing image to Gemini Pro)

```python
# Source: ai.google.dev/gemini-api/docs/vision + google-genai 1.60.0 introspection
from pathlib import Path
from google import genai
from google.genai import types

GEMINI_VISION_PRO = "gemini-3-pro-image-preview"

def _audit_thumbnail_composition(
    image_path: Path,
    audit_prompt: str,
) -> str:
    """Audit generated thumbnail for branding/composition issues."""
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    image_bytes = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    mime_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

    response = client.models.generate_content(
        model=GEMINI_VISION_PRO,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            audit_prompt,
        ],
    )
    return response.text or ""
```

### Availability Check (replaces _imagen4_available + _flux_available)

```python
import os

def _gemini_available() -> tuple[bool, str]:
    """Return (available, reason) for the Gemini Vision backend."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return False, "GEMINI_API_KEY not set — Gemini Vision backend unavailable"
    try:
        from google import genai  # noqa: F401
    except ImportError:
        return False, "google-genai not installed (install with: uv add google-genai)"
    return True, ""
```

### ThumbnailRequest — Config Changes

The `ThumbnailRequest` dataclass currently has `project_id` and `location` fields (Vertex AI) that must be removed. The new config:

```python
# Updated ThumbnailRequest — remove project_id, location, model field updated
@dataclass
class ThumbnailRequest:
    prompts: list[str]
    output_dir: Path
    images_per_prompt: int = 1
    width: int = DEFAULT_WIDTH    # 1280 — preserved for branding overlay sizing
    height: int = DEFAULT_HEIGHT  # 720 — preserved
    generation_model: str = GEMINI_VISION_FLASH    # image generation model
    audit_model: str = GEMINI_VISION_PRO           # compositional audit model
    seed: int | None = None
    branding_profile: Any | None = None
    # Removed: project_id, location (Vertex AI only)
```

### Mock Pattern for Tests

```python
# Replace old Imagen4/FLUX mocks with Gemini mock:
from unittest.mock import MagicMock, patch

def make_fake_genai_response(img_bytes: bytes = b"FAKEJPEG") -> MagicMock:
    """Create a fake google.genai generate_content response with one image part."""
    blob = MagicMock()
    blob.data = img_bytes
    blob.mime_type = "image/jpeg"

    part = MagicMock()
    part.inline_data = blob
    part.text = None

    response = MagicMock()
    response.parts = [part]
    return response

# In test:
with patch("google.genai.Client") as MockClient:
    mock_client = MockClient.return_value
    mock_client.models.generate_content.return_value = make_fake_genai_response()
    # ... run service ...
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Imagen 4 via Vertex AI (`google-cloud-aiplatform`) | `gemini-2.5-flash-image` via `google-genai` SDK | Phase 09-11 | Removes Vertex AI auth complexity; single SDK for all Gemini tasks |
| FLUX.1 Schnell local GPU fallback | No local fallback — Gemini API only | Phase 09-11 | Removes VRAM dependency; requires internet + API key |
| Dual-backend routing (IMAGEN4 / FLUX) | Single backend (GEMINI) | Phase 09-11 | Simpler routing logic; fewer failure modes |
| `generate_images()` Imagen-specific call | `generate_content()` with `response_modalities=["IMAGE"]` | Always was Gemini's approach | Unified call for generation AND analysis |

**Deprecated/outdated (remove all references):**
- `google-cloud-aiplatform`: No longer needed; remove from `[thumbnails]` extras
- `diffusers`: No longer needed; remove from `[thumbnails]` extras
- `optimum-quanto`: No longer needed; remove from `[thumbnails]` extras
- `ThumbnailBackend.IMAGEN4`: Replace with `ThumbnailBackend.GEMINI`
- `ThumbnailBackend.FLUX`: Remove
- `_imagen4_available()`: Remove; replace with `_gemini_available()`
- `_flux_available()`: Remove entirely
- `check_vram_preflight()`: Remove entirely (VRAM irrelevant for cloud API)
- `_free_vram_gib()`: Remove entirely
- `_generate_imagen4()`: Remove; replace with `_generate_gemini()`
- `_generate_flux()`: Remove entirely
- `_unload_gpu_models()`: Remove entirely
- `IMAGEN4_MODEL_*` constants: Remove; replace with `GEMINI_VISION_PRO`, `GEMINI_VISION_FLASH`
- `FLUX_*` constants: Remove entirely
- `ThumbnailRequest.project_id`: Remove (Vertex AI field)
- `ThumbnailRequest.location`: Remove (Vertex AI field)
- `ThumbnailGenerationConfig.model` default: Change from `"imagen-4.0-generate-001"` to `"gemini-2.5-flash-image"`

---

## Pricing and Rate Limits

**Source:** ai.google.dev/pricing (confirmed 2026-02-24)

### gemini-2.5-flash-image

- **Free tier:** Not available for image generation
- **Paid standard:**
  - Input: $0.30/1M tokens (text/image input)
  - Output: **$0.039 per image** (up to 1024x1024px = 1290 output tokens)
- **Batch pricing:** $0.0195 per image

### gemini-3-pro-image-preview

- **Free tier:** Not available
- **Paid standard:**
  - Input: $2.00/1M tokens
  - Output (1K/2K image): **$0.134 per image**
  - Output (4K image): **$0.24 per image**
- Cost driver: Use sparingly — this model is ~3-6x more expensive than Flash for image output

**Cost mitigation:** The existing `compute_cache_key` + `_cache_path` caching is the primary cost guard. Identical prompt/model/dimension/seed combinations skip generation entirely. This must be preserved.

**Rate limits:** IPM (images per minute) limit exists but exact values not published in docs. If hitting limits, the `tenacity` retry wrapper with 60s exponential backoff (existing pattern) is sufficient.

---

## Open Questions

1. **Does `gemini-3-pro-image-preview` support text-only responses (for prompt engineering)?**
   - What we know: It is documented as a vision + reasoning model. The existing `gemini.py` pattern for text generation uses `generate_content()` without `response_modalities` override.
   - What's unclear: Whether omitting `response_modalities` on the image-preview model defaults to text-only or mixed output.
   - Recommendation: When using `gemini-3-pro-image-preview` for audit/prompt-engineering (text only), do NOT include `response_modalities=["IMAGE"]` in config. This should produce text responses. If images appear unexpectedly, add `response_modalities=["TEXT"]` explicitly.

2. **`seed` determinism for image generation**
   - What we know: `GenerateContentConfig.seed` field exists in the SDK.
   - What's unclear: Whether image generation models honor the seed for truly reproducible output.
   - Recommendation: Pass seed when provided, but test mocks should not depend on deterministic output. Cache-based determinism is more reliable.

3. **`output_mime_type` in `ImageConfig`**
   - What we know: Field exists (`output_mime_type: Optional[str]`).
   - What's unclear: Whether `"image/jpeg"` is reliably honored or if PNG is always returned.
   - Recommendation: Check `part.inline_data.mime_type` in response to determine actual format; do not assume JPEG. Use `.jpg` extension only when mime type confirms JPEG.

---

## Sources

### Primary (HIGH confidence)

- Official Google AI image generation docs — `ai.google.dev/gemini-api/docs/image-generation` — Python examples, model IDs, ImageConfig, response_modalities
- Official Google AI models page — `ai.google.dev/gemini-api/docs/models` — Confirmed `gemini-2.5-flash-image` (GA) and `gemini-3-pro-image-preview` (Preview)
- Official Google AI vision docs — `ai.google.dev/gemini-api/docs/vision` — `types.Part.from_bytes()` pattern for existing-image analysis
- Official Google AI pricing page — `ai.google.dev/pricing` — Per-image cost confirmed
- SDK introspection (google-genai 1.60.0 installed) — `types.ImageConfig.model_fields`, `types.GenerateContentConfig.model_fields`, `types.Part.from_bytes`, `types.Blob.data`, `types.Part.inline_data`, `genai.types.Image.save()` source — All confirmed against installed SDK

### Secondary (MEDIUM confidence)

- Perplexity AI search (2026-02-24) — Cross-verified model IDs, confirmed `gemini-2.5-flash-image` exists and `gemini-2.5-flash-image-preview` is a different/older ID. Confirmed no PIL requirement for raw bytes access.
- Existing `src/podcast_pipeline/providers/gemini.py` — Established `genai.Client(api_key=...)` + `client.models.generate_content()` pattern already in use in this project

### Tertiary (LOW confidence — flagged)

- Perplexity AI search on seed determinism — Could not verify from official docs. Treat as LOW confidence.
- `output_mime_type` behavior — SDK field exists but actual model behavior not confirmed without a live API test.

---

## Metadata

**Confidence breakdown:**
- Model IDs (`gemini-2.5-flash-image`, `gemini-3-pro-image-preview`): HIGH — confirmed by official Google AI docs
- SDK API (generate_content, response_modalities, ImageConfig, Part.from_bytes): HIGH — confirmed by docs + introspection of installed google-genai 1.60.0
- Image output format (inline_data.data bytes, mime_type): HIGH — confirmed by SDK source inspection
- Pricing: HIGH — confirmed from official pricing page
- Rate limits (exact IPM): LOW — not published in documentation; use existing tenacity retry pattern
- Seed determinism: LOW — field exists but behavior unconfirmed

**Research date:** 2026-02-24
**Valid until:** 2026-04-01 (preview models may GA; pricing subject to change; re-verify in 30 days)
