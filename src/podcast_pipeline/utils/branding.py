"""Branding profile load/save/resolve utilities.

Profiles are stored as YAML files under a configurable branding directory,
defaulting to ``branding/<profile_name>.yaml`` relative to the working
directory.

Typical usage::

    profile = load_profile("neon_viral", branding_dir=Path("branding"))
    resolved = resolve_for_platform(profile, "tiktok")
    save_profile(profile, branding_dir=Path("branding"))
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from podcast_pipeline.models.branding import BrandingProfile
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

# Default branding directory name relative to project root.
DEFAULT_BRANDING_DIR = Path("branding")

# Safe profile name pattern: letters, digits, hyphens, underscores.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


# ──────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────


def _profile_path(profile_name: str, branding_dir: Path) -> Path:
    """Return the canonical YAML path for ``profile_name`` under ``branding_dir``.

    Args:
        profile_name: Profile name.  Must contain only safe filename characters.
        branding_dir: Directory that holds profile YAML files.

    Returns:
        ``branding_dir / "<profile_name>.yaml"``

    Raises:
        ValueError: If ``profile_name`` contains path-unsafe characters.
    """
    # Normalise for path safety.
    safe_name = profile_name.strip()
    if not safe_name:
        raise ValueError("profile_name must not be blank")
    if not _SAFE_NAME_RE.fullmatch(safe_name):
        raise ValueError(
            f"profile_name '{profile_name}' contains unsafe characters. "
            "Only letters, digits, hyphens, and underscores are allowed."
        )
    return branding_dir / f"{safe_name}.yaml"


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    """Read a YAML file and return its top-level mapping.

    Args:
        path: Path to YAML file.

    Returns:
        Parsed YAML as a dict (empty dict if file is empty).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the YAML does not parse to a mapping.
        OSError: On read failure.
    """
    if not path.exists():
        raise FileNotFoundError(f"Branding profile not found: {path}")

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected YAML mapping at {path}, got {type(data).__name__}")
    return data


def _profile_to_serialisable(profile: BrandingProfile) -> dict[str, Any]:
    """Convert a BrandingProfile to a YAML-serialisable dict.

    Path objects are converted to strings so that yaml.dump produces
    portable paths rather than Python Path objects.
    """
    data = profile.model_dump(mode="json")

    # Convert Path fields to strings for YAML portability.
    for field_name in ("logo_path", "font_path"):
        value = data.get(field_name)
        if value is not None:
            data[field_name] = str(value)

    return data


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────


def load_profile(
    profile_name: str,
    branding_dir: Path | None = None,
) -> BrandingProfile:
    """Load a BrandingProfile from ``branding/<profile_name>.yaml``.

    Args:
        profile_name: Name of the profile to load (without extension).
        branding_dir: Directory that holds profile YAML files.  Defaults to
            :data:`DEFAULT_BRANDING_DIR`.

    Returns:
        Validated :class:`BrandingProfile` instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If the YAML does not parse to a valid profile.
        pydantic.ValidationError: If field values are invalid.
    """
    resolved_dir = branding_dir if branding_dir is not None else DEFAULT_BRANDING_DIR
    path = _profile_path(profile_name, resolved_dir)

    logger.debug("branding_profile_load", profile_name=profile_name, path=str(path))

    data = _load_yaml_dict(path)

    try:
        profile = BrandingProfile.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Branding profile '{profile_name}' failed validation: {exc}") from exc

    logger.info("branding_profile_loaded", profile_name=profile.profile_name)
    return profile


def save_profile(
    profile: BrandingProfile,
    branding_dir: Path | None = None,
    *,
    overwrite: bool = True,
) -> Path:
    """Serialise ``profile`` to ``branding/<profile_name>.yaml``.

    Args:
        profile: Profile to save.
        branding_dir: Target directory.  Defaults to :data:`DEFAULT_BRANDING_DIR`.
        overwrite: If ``False``, raise :class:`FileExistsError` when the
            target file already exists.  Defaults to ``True``.

    Returns:
        Absolute path to the written YAML file.

    Raises:
        FileExistsError: If the file exists and ``overwrite=False``.
        OSError: On write failure.
    """
    resolved_dir = branding_dir if branding_dir is not None else DEFAULT_BRANDING_DIR
    # Use sanitised profile_name for the path.
    path = _profile_path(profile.profile_name, resolved_dir)

    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Branding profile already exists at {path}. Pass overwrite=True to replace it."
        )

    resolved_dir.mkdir(parents=True, exist_ok=True)

    data = _profile_to_serialisable(profile)
    yaml_text = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=True)

    path.write_text(yaml_text, encoding="utf-8")

    logger.info("branding_profile_saved", profile_name=profile.profile_name, path=str(path))
    return path.resolve()


def resolve_profile(
    profile: BrandingProfile,
    platform: str,
) -> BrandingProfile:
    """Return a flat, resolved profile for ``platform``.

    Applies any matching entry in ``profile.platform_overrides`` onto the
    base profile fields.  The result has an empty ``platform_overrides`` dict
    (it is "resolved" and should not be resolved again).

    If ``platform`` has no override entry the base profile is returned as-is
    (with ``platform_overrides`` cleared for downstream clarity).

    Args:
        profile: Source branding profile.
        platform: Export platform name (e.g. ``"tiktok"``, ``"youtube"``).

    Returns:
        Resolved :class:`BrandingProfile` instance.
    """
    resolved = profile.resolved_for_platform(platform)
    logger.debug(
        "branding_profile_resolved",
        profile_name=profile.profile_name,
        platform=platform,
        had_override=platform in profile.platform_overrides,
    )
    return resolved


def list_profiles(branding_dir: Path | None = None) -> list[str]:
    """Return profile names available in ``branding_dir``.

    Args:
        branding_dir: Directory to scan.  Defaults to :data:`DEFAULT_BRANDING_DIR`.

    Returns:
        Sorted list of profile names (YAML stem filenames).  Empty list when
        the directory does not exist.
    """
    resolved_dir = branding_dir if branding_dir is not None else DEFAULT_BRANDING_DIR
    if not resolved_dir.is_dir():
        return []
    return sorted(p.stem for p in resolved_dir.glob("*.yaml"))


def delete_profile(
    profile_name: str,
    branding_dir: Path | None = None,
) -> bool:
    """Delete a branding profile YAML file.

    Args:
        profile_name: Name of the profile to delete (without extension).
        branding_dir: Directory that holds profile YAML files.  Defaults to
            :data:`DEFAULT_BRANDING_DIR`.

    Returns:
        ``True`` if the file was deleted, ``False`` if it did not exist.

    Raises:
        ValueError: If ``profile_name`` contains unsafe characters.
        OSError: On file system errors.
    """
    resolved_dir = branding_dir if branding_dir is not None else DEFAULT_BRANDING_DIR
    path = _profile_path(profile_name, resolved_dir)

    if not path.exists():
        logger.warning("branding_profile_delete_not_found", profile_name=profile_name)
        return False

    path.unlink()
    logger.info("branding_profile_deleted", profile_name=profile_name, path=str(path))
    return True


def load_active_profile(
    active_profile_name: str | None,
    branding_dir: Path | None = None,
) -> BrandingProfile | None:
    """Load the active profile by name, returning ``None`` when unconfigured.

    This is the preferred entry point for pipeline stages.  When
    ``active_profile_name`` is ``None`` or an empty string the function
    returns ``None`` so callers can treat branding as optional.

    Args:
        active_profile_name: Name from ``BrandingConfig.active_profile``.
        branding_dir: Directory that holds profile YAML files.

    Returns:
        :class:`BrandingProfile` or ``None``.
    """
    if not active_profile_name:
        return None

    try:
        return load_profile(active_profile_name, branding_dir=branding_dir)
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.warning(
            "branding_active_profile_load_failed",
            profile_name=active_profile_name,
            error=str(exc),
        )
        return None
