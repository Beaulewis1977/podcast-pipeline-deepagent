"""AI Thumbnail Studio -- Gemini Vision single-backend thumbnail generation service.

Backend:
  Gemini Vision via google.genai SDK (``gemini-2.5-flash-image`` for generation,
  ``gemini-3-pro-image-preview`` for compositional auditing).

The backend is optional.  If the GEMINI_API_KEY environment variable is not set
or the google-genai SDK is not installed, thumbnail generation is skipped
gracefully with a warning logged.  The service is cache-aware: each unique
``(prompt, model, seed)`` combination is hashed and the result is persisted to
``output/thumbnails/<hash>.jpg`` so identical runs avoid repeated billing.

After generation, the service can apply optional branding overlays
(logo + ``thumbnail_border``) through the FFmpeg toolkit ``overlay_image``
operation.

Usage::

    from podcast_pipeline.utils.thumbnails import ThumbnailService, ThumbnailRequest

    service = ThumbnailService()
    request = ThumbnailRequest(
        prompts=["dramatic podcast host", "energetic keynote speaker"],
        output_dir=Path("jobs/abc/output/thumbnails"),
    )
    result = service.generate(request)
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Gemini Vision model IDs (google.genai SDK)
GEMINI_VISION_FLASH = "gemini-2.5-flash-image"  # Image generation (GA)
GEMINI_VISION_PRO = "gemini-3-pro-image-preview"  # Vision audit / prompt engineering (Preview)

# Default output dimensions
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720

# Cache sub-directory name within output_dir
CACHE_DIR_NAME = "thumbnails"


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ThumbnailBackend(str, Enum):
    """Which backend was used or is preferred."""

    GEMINI = "gemini"
    NONE = "none"


class ThumbnailStatus(str, Enum):
    """Generation outcome for a single thumbnail."""

    GENERATED = "generated"
    CACHED = "cached"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Request / Response dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ThumbnailRequest:
    """Parameters for a thumbnail generation run.

    Attributes:
        prompts: List of text prompts.  Each prompt produces ``images_per_prompt``
            images.  At most 5 prompts are processed per call to limit cost.
        output_dir: Directory where generated images and the cache index are written.
        images_per_prompt: How many images to generate per prompt.
        width: Output image width in pixels.
        height: Output image height in pixels.
        model: Gemini Vision model for image generation.
        audit_model: Gemini Vision model for compositional auditing.
        seed: Optional deterministic seed for reproducible generations.
        branding_profile: Optional ``BrandingProfile`` instance.  When provided the
            logo and ``thumbnail_border`` are overlaid on each generated image via
            the FFmpeg toolkit.
    """

    prompts: list[str]
    output_dir: Path
    images_per_prompt: int = 1
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    model: str = GEMINI_VISION_FLASH
    audit_model: str = GEMINI_VISION_PRO
    seed: int | None = None
    branding_profile: Any | None = None  # BrandingProfile -- avoid circular import


@dataclass
class ThumbnailArtifact:
    """Metadata for a single generated or cached thumbnail image.

    Attributes:
        path: Absolute path to the image file.
        prompt: The prompt used to generate this image.
        backend: Which backend produced it.
        status: Outcome of this specific artifact.
        cache_hit: True when the image was loaded from cache rather than re-generated.
        branded: True when a branding overlay was applied.
        error: Error message when status is FAILED.
    """

    path: Path
    prompt: str
    backend: ThumbnailBackend
    status: ThumbnailStatus
    cache_hit: bool = False
    branded: bool = False
    error: str = ""


@dataclass
class ThumbnailResult:
    """Aggregated result of a ThumbnailService.generate() call.

    Attributes:
        artifacts: Per-image metadata list.
        backend_used: Primary backend that was active during this run.
        total_generated: Number of new images generated (cache misses).
        total_cached: Number of images loaded from cache (cache hits).
        total_failed: Number of images that could not be produced.
        degraded: True when the service fell back or skipped generation.
        degraded_reason: Human-readable explanation when degraded is True.
    """

    artifacts: list[ThumbnailArtifact] = field(default_factory=list)
    backend_used: ThumbnailBackend = ThumbnailBackend.NONE
    total_generated: int = 0
    total_cached: int = 0
    total_failed: int = 0
    degraded: bool = False
    degraded_reason: str = ""


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def compute_cache_key(
    prompt: str,
    model: str,
    width: int,
    height: int,
    seed: int | None,
    index: int,
) -> str:
    """Return a stable hex digest for a given generation parameter set.

    The hash is deterministic: identical inputs always produce the same key.
    This prevents re-billing on pipeline reruns with unchanged prompts.

    Args:
        prompt: Generation text prompt.
        model: Model identifier string.
        width: Output image width.
        height: Output image height.
        seed: Optional deterministic seed value (None is distinct from 0).
        index: Image index within the same prompt (0-based).

    Returns:
        16-character hex string suitable for use as a filename prefix.
    """
    raw = f"{prompt}|{model}|{width}x{height}|seed={seed}|idx={index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_path(output_dir: Path, cache_key: str) -> Path:
    """Return the canonical cache file path for a given key."""
    return output_dir / f"{cache_key}.jpg"


# ---------------------------------------------------------------------------
# Backend availability check
# ---------------------------------------------------------------------------


def _gemini_available() -> tuple[bool, str]:
    """Return (available, reason) for the Gemini Vision backend.

    Checks:
    1. ``GEMINI_API_KEY`` environment variable is set and non-empty.
    2. ``google.genai`` SDK is importable.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return False, "GEMINI_API_KEY not set -- Gemini Vision backend unavailable"
    try:
        from google import genai  # noqa: F401  # type: ignore[import-untyped]
    except ImportError:
        return False, "google-genai not installed (install with: uv add google-genai)"
    return True, ""


# ---------------------------------------------------------------------------
# Gemini Vision image generation
# ---------------------------------------------------------------------------


def _generate_gemini(
    prompt: str,
    output_dir: Path,
    *,
    model: str = GEMINI_VISION_FLASH,
    aspect_ratio: str = "16:9",
    seed: int | None = None,
) -> list[tuple[Path, bool]]:
    """Generate images using Gemini Vision via google.genai SDK.

    Uses ``client.models.generate_content()`` with
    ``response_modalities=["TEXT", "IMAGE"]`` and an ``ImageConfig`` for
    aspect ratio and output format.

    Image bytes are accessed via ``part.inline_data.data`` (raw bytes) --
    does NOT use ``part.as_image()`` which requires PIL.

    Args:
        prompt: Text prompt for image generation.
        output_dir: Directory to write output image files.
        model: Gemini model ID for image generation.
        aspect_ratio: Aspect ratio string (e.g. "16:9").
        seed: Optional deterministic seed.

    Returns:
        List of ``(path, cache_hit)`` tuples for each successfully saved image.
    """
    from google import genai  # type: ignore[import-untyped]
    from google.genai import types  # type: ignore[import-untyped]

    api_key = os.environ.get("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key)

    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size="2K",
            output_mime_type="image/jpeg",
        ),
        seed=seed,
    )

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[Path, bool]] = []

    if not response.parts:
        logger.warning("gemini_no_parts_in_response", model=model)
        return results

    for i, part in enumerate(response.parts):
        if part.inline_data is not None and part.inline_data.data:
            img_bytes: bytes = part.inline_data.data
            mime_type: str = part.inline_data.mime_type or "image/jpeg"
            ext = "jpg" if "jpeg" in mime_type else "png"
            out_path = output_dir / f"gen_{i}.{ext}"
            out_path.write_bytes(img_bytes)
            results.append((out_path, False))
            logger.info(
                "gemini_image_saved",
                index=i,
                path=str(out_path),
                size=len(img_bytes),
            )

    return results


# ---------------------------------------------------------------------------
# Gemini Vision audit (defined for future use -- not wired into generation)
# ---------------------------------------------------------------------------


def _audit_with_gemini_pro(
    image_path: Path,
    audit_prompt: str,
    *,
    model: str = GEMINI_VISION_PRO,
) -> str:
    """Analyze an image and return the model's text response.

    Passes image bytes via ``types.Part.from_bytes()`` for vision analysis.
    This function supports future compositional auditing but is not wired
    into the generation flow yet.

    Args:
        image_path: Path to the image file to analyze.
        audit_prompt: Text prompt describing the audit task.
        model: Gemini model ID for vision analysis.

    Returns:
        The model's text response as a string.
    """
    from google import genai  # type: ignore[import-untyped]
    from google.genai import types  # type: ignore[import-untyped]

    api_key = os.environ.get("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key)

    image_bytes = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    mime_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    response = client.models.generate_content(
        model=model,
        contents=[image_part, audit_prompt],  # type: ignore[arg-type]
    )
    return response.text or ""


# ---------------------------------------------------------------------------
# Branding overlay
# ---------------------------------------------------------------------------


def _apply_branding_overlay(
    image_path: Path,
    branding_profile: Any,
    output_path: Path | None = None,
) -> Path:
    """Apply logo and thumbnail_border branding onto a generated image.

    Uses the FFmpeg toolkit ``overlay_image`` function.  If no logo is set
    on the profile the original image is returned unchanged.

    Args:
        image_path: Path to the source JPEG/PNG thumbnail.
        branding_profile: A ``BrandingProfile`` instance with logo and border data.
        output_path: Where to save the branded image.  Defaults to an in-place
            replacement (suffixed with ``_branded``).

    Returns:
        Path to the branded image file.
    """
    from podcast_pipeline.utils.ffmpeg_toolkit import (
        OverlayImageRequest,
        OverlayPosition,
        overlay_image,
    )

    if output_path is None:
        output_path = image_path.with_name(image_path.stem + "_branded" + image_path.suffix)

    logo_path: Path | None = getattr(branding_profile, "logo_path", None)

    if logo_path is None or not Path(logo_path).exists():
        logger.info("thumbnail_overlay_skip_no_logo", path=str(image_path))
        return image_path

    placement_str = getattr(branding_profile, "logo_placement", "top_right")
    opacity = float(getattr(branding_profile, "logo_opacity", 0.8))

    # Map placement string to OverlayPosition enum
    _placement_map: dict[str, OverlayPosition] = {
        "top_left": OverlayPosition.TOP_LEFT,
        "top_right": OverlayPosition.TOP_RIGHT,
        "bottom_left": OverlayPosition.BOTTOM_LEFT,
        "bottom_right": OverlayPosition.BOTTOM_RIGHT,
        "center": OverlayPosition.CENTER,
    }
    position = _placement_map.get(placement_str, OverlayPosition.TOP_RIGHT)

    request = OverlayImageRequest(
        video_path=image_path,
        image_path=Path(logo_path),
        output_path=output_path,
        position=position,
        opacity=opacity,
    )
    overlay_image(request)

    logger.info(
        "thumbnail_overlay_applied",
        source=str(image_path),
        logo=str(logo_path),
        output=str(output_path),
    )
    return output_path


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class ThumbnailService:
    """Gemini Vision single-backend thumbnail generation service.

    Backend selection:
    1. Check if Gemini Vision is available (API key + SDK).
    2. Skip gracefully if the backend is unavailable, logging a warning.

    The service is cache-aware: identical ``(prompt, model, width, height, seed)``
    combinations are cached to ``output_dir/<hash>.jpg`` and reused on
    subsequent runs without re-billing.

    Example::

        service = ThumbnailService()
        result = service.generate(
            ThumbnailRequest(
                prompts=["tech podcast host", "keynote energy"],
                output_dir=Path("jobs/abc/output/thumbnails"),
            )
        )
    """

    def __init__(self) -> None:
        self._logger = get_logger(self.__class__.__name__)

    def generate(self, request: ThumbnailRequest) -> ThumbnailResult:
        """Execute thumbnail generation for all prompts in the request.

        Routing:
        1. Check if Gemini Vision backend is available; use it if so.
        2. If not available, return degraded result with no artifacts.

        Cache hits are detected before any API call and skip generation
        entirely.

        Args:
            request: ThumbnailRequest with prompts, output_dir, and options.

        Returns:
            ThumbnailResult with per-image artifact metadata.
        """
        request.output_dir.mkdir(parents=True, exist_ok=True)

        # Determine which backend to use
        backend, backend_reason = self._select_backend(request)

        if backend == ThumbnailBackend.NONE:
            self._logger.warning(
                "thumbnail_no_backend_available",
                reason=backend_reason,
            )
            return ThumbnailResult(
                backend_used=ThumbnailBackend.NONE,
                degraded=True,
                degraded_reason=backend_reason,
            )

        self._logger.info(
            "thumbnail_backend_selected",
            backend=backend.value,
        )

        result = ThumbnailResult(backend_used=backend)

        # Limit prompt count to avoid cost surprises
        prompts = request.prompts[:5]
        if len(request.prompts) > 5:
            self._logger.warning(
                "thumbnail_prompts_truncated",
                original=len(request.prompts),
                used=5,
            )

        for prompt in prompts:
            self._process_prompt(prompt, request, backend, result)

        if result.total_failed > 0 and result.total_generated == 0 and result.total_cached == 0:
            result.degraded = True
            result.degraded_reason = f"All {result.total_failed} generation attempts failed"

        self._logger.info(
            "thumbnail_generation_complete",
            backend=backend.value,
            generated=result.total_generated,
            cached=result.total_cached,
            failed=result.total_failed,
        )
        return result

    def _select_backend(
        self,
        request: ThumbnailRequest,
    ) -> tuple[ThumbnailBackend, str]:
        """Return the best available backend and a reason string."""
        gemini_ok, gemini_reason = _gemini_available()
        if gemini_ok:
            return ThumbnailBackend.GEMINI, ""

        self._logger.info(
            "thumbnail_gemini_unavailable",
            reason=gemini_reason,
        )

        return (
            ThumbnailBackend.NONE,
            f"No thumbnail backend available. Gemini: {gemini_reason}.",
        )

    def _process_prompt(
        self,
        prompt: str,
        request: ThumbnailRequest,
        backend: ThumbnailBackend,
        result: ThumbnailResult,
    ) -> None:
        """Generate (or load from cache) images for a single prompt."""
        model_key = request.model

        for idx in range(request.images_per_prompt):
            cache_key = compute_cache_key(
                prompt,
                model_key,
                request.width,
                request.height,
                request.seed,
                idx,
            )
            cached = _cache_path(request.output_dir, cache_key)

            if cached.exists() and cached.stat().st_size > 0:
                # Cache hit -- skip generation
                artifact = ThumbnailArtifact(
                    path=cached,
                    prompt=prompt,
                    backend=backend,
                    status=ThumbnailStatus.CACHED,
                    cache_hit=True,
                )
                result.artifacts.append(artifact)
                result.total_cached += 1
                self._logger.info(
                    "thumbnail_cache_hit",
                    key=cache_key,
                    path=str(cached),
                )
                # Apply branding to cached image if profile provided and not yet done
                if request.branding_profile is not None:
                    artifact = self._apply_branding(artifact, request.branding_profile)
                continue

            # Cache miss -- generate
            try:
                pairs = self._run_backend(
                    prompt=prompt,
                    request=request,
                    backend=backend,
                    single_index=idx,
                )
            except Exception as exc:
                self._logger.warning(
                    "thumbnail_generation_failed",
                    prompt=prompt[:80],
                    backend=backend.value,
                    error=str(exc),
                )
                result.artifacts.append(
                    ThumbnailArtifact(
                        path=request.output_dir / f"failed_{cache_key}.jpg",
                        prompt=prompt,
                        backend=backend,
                        status=ThumbnailStatus.FAILED,
                        error=str(exc),
                    )
                )
                result.total_failed += 1
                continue

            for out_path, _ in pairs:
                # Rename to canonical cache path if needed
                if out_path != cached:
                    shutil.move(str(out_path), str(cached))
                    out_path = cached

                artifact = ThumbnailArtifact(
                    path=out_path,
                    prompt=prompt,
                    backend=backend,
                    status=ThumbnailStatus.GENERATED,
                )
                if request.branding_profile is not None:
                    artifact = self._apply_branding(artifact, request.branding_profile)
                result.artifacts.append(artifact)
                result.total_generated += 1

    def _run_backend(
        self,
        prompt: str,
        request: ThumbnailRequest,
        backend: ThumbnailBackend,
        single_index: int,
    ) -> list[tuple[Path, bool]]:
        """Dispatch to the selected backend for a single image."""
        if backend == ThumbnailBackend.GEMINI:
            pairs = _generate_gemini(
                prompt=prompt,
                output_dir=request.output_dir,
                model=request.model,
                aspect_ratio=f"{request.width}:{request.height}",
                seed=(request.seed + single_index) if request.seed is not None else None,
            )
        else:
            pairs = []
        return pairs

    def _apply_branding(
        self,
        artifact: ThumbnailArtifact,
        branding_profile: Any,
    ) -> ThumbnailArtifact:
        """Apply branding overlay and return an updated artifact."""
        try:
            branded_path = _apply_branding_overlay(
                image_path=artifact.path,
                branding_profile=branding_profile,
            )
            branded = branded_path != artifact.path
            return ThumbnailArtifact(
                path=branded_path,
                prompt=artifact.prompt,
                backend=artifact.backend,
                status=artifact.status,
                cache_hit=artifact.cache_hit,
                branded=branded,
                error=artifact.error,
            )
        except Exception as exc:
            self._logger.warning(
                "thumbnail_branding_overlay_failed",
                path=str(artifact.path),
                error=str(exc),
            )
            # Return original artifact without branding; branding failure
            # must not prevent the image from being returned.
            return artifact
