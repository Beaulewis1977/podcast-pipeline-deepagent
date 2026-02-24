"""AI Thumbnail Studio — dual-backend thumbnail generation service.

Backends (in priority order):
  1. Imagen 4 GA via Vertex AI (``imagen-4.0-generate-001`` family)
  2. Local FLUX.1 Schnell (FP8/INT8 quantised, 16 GB VRAM)

Both backends are optional.  If neither is available thumbnail generation
is skipped gracefully with a warning logged.  The service is cache-aware:
each unique ``(prompt, model, seed)`` combination is hashed and the result
is persisted to ``output/thumbnails/<hash>.jpg`` so identical runs avoid
repeated billing / model-load overhead.

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
import importlib
import importlib.util
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

# Imagen 4 GA model IDs (Vertex AI)
IMAGEN4_MODEL_STANDARD = "imagen-4.0-generate-001"
IMAGEN4_MODEL_FAST = "imagen-4.0-fast-generate-001"
IMAGEN4_MODEL_ULTRA = "imagen-4.0-ultra-generate-001"

# FLUX.1 Schnell HuggingFace model ID
FLUX_SCHNELL_MODEL_ID = "black-forest-labs/FLUX.1-schnell"

# VRAM preflight: require at least this many GiB free before loading FLUX
FLUX_MIN_FREE_VRAM_GIB = 14.0

# Default number of inference steps for FLUX Schnell (4 = <10s generation)
FLUX_DEFAULT_STEPS = 4

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

    IMAGEN4 = "imagen4"
    FLUX = "flux"
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
        model: Imagen 4 model variant.  Ignored when using FLUX fallback.
        seed: Optional deterministic seed for reproducible generations.
        branding_profile: Optional ``BrandingProfile`` instance.  When provided the
            logo and ``thumbnail_border`` are overlaid on each generated image via
            the FFmpeg toolkit.
        project_id: Google Cloud project ID required for Vertex AI.  Falls back to
            ``GOOGLE_CLOUD_PROJECT`` environment variable.
        location: Vertex AI region (default: ``us-central1``).
    """

    prompts: list[str]
    output_dir: Path
    images_per_prompt: int = 1
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    model: str = IMAGEN4_MODEL_STANDARD
    seed: int | None = None
    branding_profile: Any | None = None  # BrandingProfile — avoid circular import
    project_id: str | None = None
    location: str = "us-central1"


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
        degraded: True when the service fell back to an inferior backend or skipped.
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
# VRAM preflight
# ---------------------------------------------------------------------------


def _free_vram_gib() -> float | None:
    """Return free VRAM in GiB on the default CUDA device, or None if unavailable.

    Returns ``None`` when:
    - torch is not installed
    - CUDA is unavailable on this machine
    - Any torch error occurs during the query
    """
    try:
        import torch  # type: ignore[import-not-found]

        if not torch.cuda.is_available():
            return None
        mem_info: tuple[int, int] = torch.cuda.mem_get_info(device=0)
        free_bytes = mem_info[0]
        return float(free_bytes) / (1024**3)
    except Exception:
        return None


def check_vram_preflight(min_free_gib: float = FLUX_MIN_FREE_VRAM_GIB) -> tuple[bool, str]:
    """Verify that sufficient VRAM is available before loading FLUX.

    Args:
        min_free_gib: Minimum required free VRAM in GiB.

    Returns:
        Tuple of (ok: bool, message: str).  ``ok`` is True when VRAM is
        sufficient.  ``message`` is an empty string on success or describes
        the shortfall on failure.
    """
    free = _free_vram_gib()
    if free is None:
        return (
            False,
            "CUDA not available or torch not installed — cannot verify VRAM for FLUX",
        )
    if free < min_free_gib:
        return (
            False,
            f"Insufficient VRAM for FLUX: {free:.1f} GiB free, {min_free_gib:.0f} GiB required",
        )
    return True, ""


# ---------------------------------------------------------------------------
# Backend availability checks
# ---------------------------------------------------------------------------


def _imagen4_available(project_id: str | None, location: str) -> tuple[bool, str]:
    """Return (available, reason) for the Imagen 4 / Vertex AI backend.

    Checks:
    1. ``google-cloud-aiplatform`` package is importable.
    2. A GCP project ID is resolvable (parameter or ``GOOGLE_CLOUD_PROJECT`` env).
    3. ``GOOGLE_APPLICATION_CREDENTIALS`` or Application Default Credentials are set
       (we only check for the env-var here; runtime auth errors are caught per-call).
    """
    try:
        import google.cloud.aiplatform  # noqa: F401  # type: ignore[import-untyped]
    except ImportError:
        return False, "google-cloud-aiplatform not installed (install [thumbnails] extra)"

    resolved_project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not resolved_project:
        return (
            False,
            ("GOOGLE_CLOUD_PROJECT env var or project_id not set — Imagen 4 backend unavailable"),
        )

    return True, ""


def _flux_available() -> tuple[bool, str]:
    """Return (available, reason) for the local FLUX.1 Schnell backend.

    Checks that ``diffusers`` and at least one quantisation package
    (``optimum-quanto`` or ``torchao``) are importable.
    VRAM availability is checked separately in check_vram_preflight().
    """
    # Check diffusers
    diffusers_spec = importlib.util.find_spec("diffusers")
    if diffusers_spec is None:
        return False, "diffusers not installed (install [thumbnails] extra)"

    # Check quantisation library availability (optimum-quanto or torchao)
    quanto_spec = importlib.util.find_spec("optimum.quanto")
    torchao_spec = importlib.util.find_spec("torchao")
    if quanto_spec is None and torchao_spec is None:
        return (
            False,
            (
                "Neither optimum-quanto nor torchao is installed "
                "— FLUX quantised inference unavailable"
            ),
        )

    return True, ""


# ---------------------------------------------------------------------------
# Imagen 4 generation
# ---------------------------------------------------------------------------


def _generate_imagen4(
    prompt: str,
    output_dir: Path,
    *,
    model: str,
    images_per_prompt: int,
    width: int,
    height: int,
    seed: int | None,
    project_id: str,
    location: str,
) -> list[tuple[Path, bool]]:
    """Generate images using Imagen 4 via Vertex AI.

    Args:
        prompt: Text prompt.
        output_dir: Directory to write output JPEG files.
        model: Imagen 4 model variant.
        images_per_prompt: How many images to request.
        width: Target width.
        height: Target height.
        seed: Optional seed for determinism.
        project_id: GCP project.
        location: Vertex AI region.

    Returns:
        List of ``(path, cache_hit)`` tuples for each successfully saved image.
    """
    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=location)

    # Build the Vertex AI prediction service endpoint for Imagen
    endpoint = f"projects/{project_id}/locations/{location}/publishers/google/models/{model}"
    client = aiplatform.gapic.PredictionServiceClient(
        client_options={"api_endpoint": f"{location}-aiplatform.googleapis.com"}
    )

    instances = [{"prompt": prompt}]
    parameters: dict[str, Any] = {
        "sampleCount": images_per_prompt,
        "aspectRatio": f"{width}:{height}",
    }
    if seed is not None:
        parameters["seed"] = seed

    import json as _json

    from google.protobuf import (
        json_format,
        struct_pb2,
    )

    instances_pb = [json_format.ParseDict(inst, struct_pb2.Value()) for inst in instances]
    parameters_pb = json_format.ParseDict(parameters, struct_pb2.Value())

    response = client.predict(
        endpoint=endpoint,
        instances=instances_pb,
        parameters=parameters_pb,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[Path, bool]] = []

    predictions = list(response.predictions)
    for idx, prediction in enumerate(predictions):
        pred_dict = _json.loads(
            json_format.MessageToJson(prediction, preserving_proto_field_name=True)
        )
        b64_data = pred_dict.get("bytesBase64Encoded") or pred_dict.get("imageBytes", "")
        if not b64_data:
            logger.warning("imagen4_empty_prediction", index=idx)
            continue

        import base64

        img_bytes = base64.b64decode(b64_data)
        key = compute_cache_key(prompt, model, width, height, seed, idx)
        out_path = _cache_path(output_dir, key)
        out_path.write_bytes(img_bytes)
        results.append((out_path, False))
        logger.info("imagen4_image_saved", index=idx, path=str(out_path), size=len(img_bytes))

    return results


# ---------------------------------------------------------------------------
# FLUX.1 Schnell generation
# ---------------------------------------------------------------------------


def _unload_gpu_models() -> None:
    """Release cached CUDA tensors to free VRAM before loading FLUX.

    Calls ``torch.cuda.empty_cache()`` which returns memory held by the
    PyTorch caching allocator.  Models must be explicitly deleted by callers
    before this is meaningful.
    """
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("flux_gpu_cache_cleared")
    except Exception as exc:
        logger.warning("flux_gpu_cache_clear_failed", error=str(exc))


def _generate_flux(
    prompt: str,
    output_dir: Path,
    *,
    images_per_prompt: int,
    width: int,
    height: int,
    seed: int | None,
    num_inference_steps: int = FLUX_DEFAULT_STEPS,
) -> list[tuple[Path, bool]]:
    """Generate images using local FLUX.1 Schnell with FP8/INT8 quantisation.

    VRAM preflight must be called before this function.

    Args:
        prompt: Text prompt.
        output_dir: Directory to write output JPEG files.
        images_per_prompt: How many images to generate.
        width: Target width.
        height: Target height.
        seed: Optional deterministic seed.
        num_inference_steps: Inference steps (default: 4 for Schnell).

    Returns:
        List of ``(path, cache_hit)`` tuples for each saved image.
    """
    import torch  # type: ignore[import-not-found]
    from diffusers import FluxPipeline  # type: ignore[import-not-found]

    # Attempt FP8/INT8 quantisation — prefer optimum-quanto, fall back to torchao
    quantisation_applied = False
    try:
        from optimum.quanto import (  # type: ignore[import-not-found]
            freeze,
            qfloat8,
            quantize,
        )

        _quanto_available = True
    except ImportError:
        _quanto_available = False

    logger.info(
        "flux_loading_pipeline",
        model=FLUX_SCHNELL_MODEL_ID,
        quantisation="fp8/int8" if _quanto_available else "none",
    )

    pipe = FluxPipeline.from_pretrained(
        FLUX_SCHNELL_MODEL_ID,
        torch_dtype=torch.bfloat16,
    )

    if _quanto_available:
        # Quantise transformer and text encoder to FP8 to fit in 16 GB VRAM
        from optimum.quanto import (  # type: ignore[import-not-found]
            freeze,
            qfloat8,
            quantize,
        )

        quantize(pipe.transformer, weights=qfloat8)
        freeze(pipe.transformer)
        quantisation_applied = True

    pipe = pipe.to("cuda")
    logger.info(
        "flux_pipeline_loaded",
        quantised=quantisation_applied,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[Path, bool]] = []

    model_key = f"flux_schnell_{num_inference_steps}steps"

    try:
        for idx in range(images_per_prompt):
            generator = None
            if seed is not None:
                generator = torch.Generator("cuda").manual_seed(seed + idx)

            image = pipe(
                prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=0.0,  # Schnell uses guidance_scale=0
                generator=generator,
                width=width,
                height=height,
            ).images[0]

            key = compute_cache_key(prompt, model_key, width, height, seed, idx)
            out_path = _cache_path(output_dir, key)
            image.save(str(out_path), format="JPEG", quality=95)
            results.append((out_path, False))
            logger.info("flux_image_saved", index=idx, path=str(out_path))
    finally:
        # Always unload the pipeline to release VRAM regardless of success/failure
        del pipe
        _unload_gpu_models()
        logger.info("flux_pipeline_unloaded")

    return results


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
    """Dual-backend thumbnail generation service.

    Backend selection:
    1. Try Imagen 4 GA via Vertex AI.
    2. Fall back to local FLUX.1 Schnell when Vertex AI is unavailable.
    3. Skip gracefully if neither backend is available, logging a warning.

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
        1. Check if Imagen 4 backend is available; use it if so.
        2. If not, check FLUX availability + VRAM preflight; use it if ok.
        3. If neither available, return degraded result with no artifacts.

        Cache hits are detected before any API/model call and skip generation
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
        # Try Imagen 4 first
        resolved_project = request.project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        imagen_ok, imagen_reason = _imagen4_available(resolved_project, request.location)
        if imagen_ok:
            return ThumbnailBackend.IMAGEN4, ""

        self._logger.info(
            "thumbnail_imagen4_unavailable",
            reason=imagen_reason,
        )

        # Try FLUX fallback
        flux_ok, flux_reason = _flux_available()
        if flux_ok:
            # Check VRAM before committing to FLUX
            vram_ok, vram_reason = check_vram_preflight()
            if vram_ok:
                return ThumbnailBackend.FLUX, ""
            self._logger.warning("thumbnail_flux_vram_insufficient", reason=vram_reason)
            return (
                ThumbnailBackend.NONE,
                f"FLUX unavailable (VRAM): {vram_reason}",
            )

        self._logger.info(
            "thumbnail_flux_unavailable",
            reason=flux_reason,
        )

        return (
            ThumbnailBackend.NONE,
            f"No thumbnail backend available. Imagen4: {imagen_reason}. FLUX: {flux_reason}.",
        )

    def _process_prompt(
        self,
        prompt: str,
        request: ThumbnailRequest,
        backend: ThumbnailBackend,
        result: ThumbnailResult,
    ) -> None:
        """Generate (or load from cache) images for a single prompt."""
        model_key = request.model if backend == ThumbnailBackend.IMAGEN4 else "flux_schnell"

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
                # Cache hit — skip generation
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

            # Cache miss — generate
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
        if backend == ThumbnailBackend.IMAGEN4:
            resolved_project = request.project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
            pairs = _generate_imagen4(
                prompt=prompt,
                output_dir=request.output_dir,
                model=request.model,
                images_per_prompt=1,
                width=request.width,
                height=request.height,
                seed=(request.seed + single_index) if request.seed is not None else None,
                project_id=resolved_project,
                location=request.location,
            )
        elif backend == ThumbnailBackend.FLUX:
            pairs = _generate_flux(
                prompt=prompt,
                output_dir=request.output_dir,
                images_per_prompt=1,
                width=request.width,
                height=request.height,
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
