"""System endpoints for asset readiness, model warmup, and download status.

These endpoints allow the desktop frontend to check whether runtime assets
(FFmpeg, model files) are available before starting job runs, and to trigger
optional model download/warmup without blocking the job APIs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from podcast_pipeline.service.assets import (
    AssetStatus,
    BinaryInfo,
    ModelInfo,
    resolve_all_binaries,
    resolve_binary,
    resolve_model,
)
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SystemStatusResponse(BaseModel):
    """Combined readiness status for all runtime assets."""

    ready: bool = Field(description="True when all required assets are available")
    binaries: dict[str, BinaryInfo]
    model: ModelInfo
    issues: list[str] = Field(
        default_factory=list,
        description="Human-readable descriptions of missing/broken assets",
    )


class ModelWarmupRequest(BaseModel):
    """Request body for POST /system/models/warmup."""

    model_name: str | None = Field(
        None, description="Whisper model name (defaults to pipeline default)"
    )


class ModelWarmupResponse(BaseModel):
    """Response for model warmup/download trigger."""

    model_name: str
    status: str = Field(description="ready | downloading | error")
    message: str
    path: str | None = None


class BinaryCheckResponse(BaseModel):
    """Response for single binary readiness check."""

    name: str
    ready: bool
    path: str | None = None
    source: str = "unknown"
    message: str = ""


# ---------------------------------------------------------------------------
# Module-level download tracking
# ---------------------------------------------------------------------------

# Simple in-memory tracker for active model downloads.
# Key: model_name, Value: status string
_download_tasks: dict[str, str] = {}

# Strong references to background tasks to prevent garbage collection.
_background_tasks: set[asyncio.Task[None]] = set()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=SystemStatusResponse)
async def system_status() -> SystemStatusResponse:
    """Return combined readiness status for all runtime assets.

    Checks all registered binaries and the default whisper model.
    The ``ready`` flag is only True when all *required* binaries are
    present and the whisper model is cached locally.
    """
    binaries = resolve_all_binaries()
    model = resolve_model()

    issues: list[str] = []

    # Check required binaries
    for name, info in binaries.items():
        if info.status != AssetStatus.READY and name in ("ffmpeg", "podcast-backend"):
            issues.append(f"Required binary '{name}' is missing. Install or set env var.")

    if model.status != AssetStatus.READY:
        issues.append(
            f"Whisper model '{model.name}' not cached. "
            "Run warmup or let faster-whisper download on first use."
        )

    all_required_ready = all(
        info.status == AssetStatus.READY
        for name, info in binaries.items()
        if name in ("ffmpeg", "podcast-backend")
    )
    ready = all_required_ready and model.status == AssetStatus.READY

    return SystemStatusResponse(
        ready=ready,
        binaries=binaries,
        model=model,
        issues=issues,
    )


@router.get("/binaries/{name}", response_model=BinaryCheckResponse)
async def check_binary(name: str) -> BinaryCheckResponse:
    """Check readiness of a single binary by logical name.

    Valid names: ``ffmpeg``, ``ffprobe``, ``podcast-backend``.
    """
    info = resolve_binary(name)
    is_ready = info.status == AssetStatus.READY

    if info.source == "unknown_binary":
        message = f"Unknown binary name: {name}"
    elif is_ready:
        message = f"Found via {info.source}"
    else:
        message = f"Binary '{name}' not found in any search location"

    return BinaryCheckResponse(
        name=name,
        ready=is_ready,
        path=info.path,
        source=info.source,
        message=message,
    )


@router.get("/models/{model_name}", response_model=ModelInfo)
async def check_model(model_name: str) -> ModelInfo:
    """Check whether a specific whisper model is cached locally."""
    return resolve_model(model_name)


@router.post("/models/warmup", response_model=ModelWarmupResponse)
async def warmup_model(body: ModelWarmupRequest) -> ModelWarmupResponse:
    """Trigger model download/warmup if not already cached.

    If the model is already available locally, returns immediately
    with ``status: ready``. Otherwise, starts an async download task
    and returns ``status: downloading``.

    The download uses faster-whisper's built-in model fetching from
    Hugging Face, so no custom download logic is needed.
    """
    model_name = body.model_name or "large-v3"

    # Check if already cached
    info = resolve_model(model_name)
    if info.status == AssetStatus.READY:
        return ModelWarmupResponse(
            model_name=model_name,
            status="ready",
            message=f"Model '{model_name}' already cached at {info.path}",
            path=info.path,
        )

    # Check if download is already in progress
    if _download_tasks.get(model_name) == "downloading":
        return ModelWarmupResponse(
            model_name=model_name,
            status="downloading",
            message=f"Model '{model_name}' download already in progress",
        )

    # Start background download
    _download_tasks[model_name] = "downloading"
    task = asyncio.create_task(_download_model(model_name))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    logger.info("model_warmup_started", model_name=model_name)
    return ModelWarmupResponse(
        model_name=model_name,
        status="downloading",
        message=f"Started download of model '{model_name}'",
    )


@router.get("/models/warmup/status", response_model=dict[str, Any])
async def warmup_status() -> dict[str, Any]:
    """Return current status of all model download tasks."""
    result: dict[str, Any] = {}
    for model_name, status in _download_tasks.items():
        info = resolve_model(model_name)
        result[model_name] = {
            "download_status": status,
            "cached": info.status == AssetStatus.READY,
            "path": info.path,
        }
    return result


# ---------------------------------------------------------------------------
# Background download helper
# ---------------------------------------------------------------------------


async def _download_model(model_name: str) -> None:
    """Download a whisper model in the background via faster-whisper.

    This runs the model constructor in an executor thread since
    faster-whisper's download is blocking I/O.
    """
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _sync_download_model, model_name)
        _download_tasks[model_name] = "ready"
        logger.info("model_warmup_complete", model_name=model_name)
    except Exception:
        _download_tasks[model_name] = "error"
        logger.exception("model_warmup_failed", model_name=model_name)


def _sync_download_model(model_name: str) -> None:
    """Blocking model download using faster-whisper's built-in fetching.

    faster-whisper's ``WhisperModel(model_name)`` automatically downloads
    from Hugging Face if not cached. We instantiate the model to trigger
    the download, then discard the instance.
    """
    from faster_whisper import WhisperModel

    # This triggers download if not cached. Use CPU to avoid GPU memory
    # allocation during warmup-only invocation.
    _ = WhisperModel(model_name, device="cpu", compute_type="int8")
