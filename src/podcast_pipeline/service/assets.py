"""Runtime asset resolution for packaged desktop and development environments.

This module provides helpers to locate bundled binaries (FFmpeg, podcast-backend)
and model cache directories using environment variables, Tauri app-data paths,
and platform-appropriate fallback logic.

The resolver order for each binary is:

1. Explicit environment variable override (``FFMPEG_PATH``, etc.)
2. Tauri sidecar directory (``<exe_dir>/`` for bundled apps)
3. System PATH lookup (development mode)

For model caches:

1. ``WHISPER_MODEL_DIR`` env override
2. ``<app_data>/models/`` (Tauri app data directory)
3. Project ``./models/`` relative to CWD
4. faster-whisper default (~/.cache/huggingface/hub)
"""

from __future__ import annotations

import os
import shutil
import sys
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)


class AssetStatus(str, Enum):
    """Readiness status for a runtime asset."""

    READY = "ready"
    MISSING = "missing"
    DOWNLOADING = "downloading"
    ERROR = "error"


class BinaryInfo(BaseModel):
    """Resolved binary location and status."""

    name: str
    path: str | None = None
    status: AssetStatus = AssetStatus.MISSING
    version: str | None = None
    source: str = Field(
        default="unknown",
        description="How the binary was found: env, sidecar, path, or missing",
    )


class ModelInfo(BaseModel):
    """Resolved model location and status."""

    name: str
    path: str | None = None
    status: AssetStatus = AssetStatus.MISSING
    size_bytes: int | None = None
    source: str = Field(
        default="unknown",
        description="How the model was found: env, app_data, project, cache, or missing",
    )


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------

# Map of binary name -> (env_var, executable_name)
_BINARY_REGISTRY: dict[str, tuple[str, str]] = {
    "ffmpeg": ("FFMPEG_PATH", "ffmpeg"),
    "ffprobe": ("FFPROBE_PATH", "ffprobe"),
    "podcast-backend": ("BACKEND_BIN", "podcast-backend"),
}


def _exe_dir() -> Path:
    """Directory containing the running executable (or script)."""
    if getattr(sys, "frozen", False):
        # PyInstaller / frozen binary
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _resolve_from_env(env_var: str) -> Path | None:
    """Check an environment variable for an explicit binary path."""
    value = os.environ.get(env_var)
    if value:
        p = Path(value)
        if p.is_file():
            return p
        logger.warning("env_binary_not_found", env_var=env_var, path=value)
    return None


def _resolve_from_sidecar(exe_name: str) -> Path | None:
    """Check the Tauri sidecar directory (next to the running executable)."""
    exe_dir = _exe_dir()
    candidate = exe_dir / exe_name
    if candidate.is_file():
        return candidate
    # Also check with .exe suffix on Windows
    if sys.platform == "win32":
        candidate_exe = exe_dir / f"{exe_name}.exe"
        if candidate_exe.is_file():
            return candidate_exe
    return None


def _resolve_from_path(exe_name: str) -> Path | None:
    """Fall back to system PATH lookup."""
    result = shutil.which(exe_name)
    if result:
        return Path(result)
    return None


def resolve_binary(name: str) -> BinaryInfo:
    """Resolve a binary by name using the standard search order.

    Args:
        name: Logical binary name (e.g. ``"ffmpeg"``, ``"podcast-backend"``).

    Returns:
        :class:`BinaryInfo` with resolved path and status.
    """
    if name not in _BINARY_REGISTRY:
        return BinaryInfo(name=name, status=AssetStatus.ERROR, source="unknown_binary")

    env_var, exe_name = _BINARY_REGISTRY[name]

    # 1. Explicit env var
    path = _resolve_from_env(env_var)
    if path:
        logger.debug("binary_resolved", name=name, source="env", path=str(path))
        return BinaryInfo(name=name, path=str(path), status=AssetStatus.READY, source="env")

    # 2. Sidecar directory
    path = _resolve_from_sidecar(exe_name)
    if path:
        logger.debug("binary_resolved", name=name, source="sidecar", path=str(path))
        return BinaryInfo(name=name, path=str(path), status=AssetStatus.READY, source="sidecar")

    # 3. System PATH
    path = _resolve_from_path(exe_name)
    if path:
        logger.debug("binary_resolved", name=name, source="path", path=str(path))
        return BinaryInfo(name=name, path=str(path), status=AssetStatus.READY, source="path")

    logger.warning("binary_not_found", name=name)
    return BinaryInfo(name=name, status=AssetStatus.MISSING, source="missing")


def resolve_all_binaries() -> dict[str, BinaryInfo]:
    """Resolve all registered binaries and return a status dict."""
    return {name: resolve_binary(name) for name in _BINARY_REGISTRY}


# ---------------------------------------------------------------------------
# Model cache resolution
# ---------------------------------------------------------------------------

# Default faster-whisper model name used by the pipeline
DEFAULT_WHISPER_MODEL = "large-v3"

# Known model directory names that faster-whisper downloads
_WHISPER_MODEL_DIRS: dict[str, str] = {
    "tiny": "models--Systran--faster-whisper-tiny",
    "base": "models--Systran--faster-whisper-base",
    "small": "models--Systran--faster-whisper-small",
    "medium": "models--Systran--faster-whisper-medium",
    "large-v2": "models--Systran--faster-whisper-large-v2",
    "large-v3": "models--Systran--faster-whisper-large-v3",
}


def _model_cache_search_paths() -> list[tuple[str, Path]]:
    """Return an ordered list of (source_label, directory) to search for models."""
    paths: list[tuple[str, Path]] = []

    # 1. Explicit env override
    env_dir = os.environ.get("WHISPER_MODEL_DIR")
    if env_dir:
        paths.append(("env", Path(env_dir)))

    # 2. App data dir (Tauri convention)
    app_data = os.environ.get("PODCAST_PIPELINE_DATA_DIR")
    if app_data:
        paths.append(("app_data", Path(app_data) / "models"))

    # 3. Project-relative models dir
    paths.append(("project", Path.cwd() / "models"))

    # 4. Default HuggingFace cache
    hf_cache = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface" / "hub"))
    paths.append(("cache", Path(hf_cache)))

    return paths


def resolve_model(model_name: str | None = None) -> ModelInfo:
    """Check whether a whisper model is available in any cache location.

    Args:
        model_name: Model name (e.g. ``"large-v3"``). Defaults to pipeline default.

    Returns:
        :class:`ModelInfo` with resolved path and status.
    """
    name = model_name or DEFAULT_WHISPER_MODEL
    hub_dir_name = _WHISPER_MODEL_DIRS.get(name)

    for source, base_path in _model_cache_search_paths():
        if not base_path.is_dir():
            continue

        # Check for the model directory directly (e.g. copied model)
        direct = base_path / name
        if direct.is_dir() and _dir_has_model_files(direct):
            size = _dir_size(direct)
            logger.debug("model_resolved", name=name, source=source, path=str(direct))
            return ModelInfo(
                name=name,
                path=str(direct),
                status=AssetStatus.READY,
                size_bytes=size,
                source=source,
            )

        # Check for HuggingFace hub layout
        if hub_dir_name:
            hf_path = base_path / hub_dir_name
            if hf_path.is_dir():
                # Check snapshots dir for actual model files
                snapshots = hf_path / "snapshots"
                if snapshots.is_dir():
                    for snapshot in sorted(snapshots.iterdir(), reverse=True):
                        if snapshot.is_dir() and _dir_has_model_files(snapshot):
                            size = _dir_size(snapshot)
                            logger.debug(
                                "model_resolved",
                                name=name,
                                source=source,
                                path=str(snapshot),
                            )
                            return ModelInfo(
                                name=name,
                                path=str(snapshot),
                                status=AssetStatus.READY,
                                size_bytes=size,
                                source=source,
                            )

    logger.info("model_not_found", name=name)
    return ModelInfo(name=name, status=AssetStatus.MISSING, source="missing")


def _dir_has_model_files(path: Path) -> bool:
    """Check whether a directory contains faster-whisper model artifacts."""
    # faster-whisper CTranslate2 models contain a model.bin file
    required_files = ["model.bin", "config.json"]
    return all((path / f).is_file() for f in required_files)


def _dir_size(path: Path) -> int:
    """Recursively compute directory size in bytes."""
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass  # Gracefully handle permission/access errors during size calculation
    return total


def get_model_cache_dir() -> Path:
    """Return the preferred writable directory for model downloads.

    Priority:
    1. ``WHISPER_MODEL_DIR`` env var
    2. ``PODCAST_PIPELINE_DATA_DIR/models`` (Tauri app data)
    3. ``./models`` (project-relative)
    """
    env_dir = os.environ.get("WHISPER_MODEL_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    app_data = os.environ.get("PODCAST_PIPELINE_DATA_DIR")
    if app_data:
        p = Path(app_data) / "models"
        p.mkdir(parents=True, exist_ok=True)
        return p

    p = Path.cwd() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p
