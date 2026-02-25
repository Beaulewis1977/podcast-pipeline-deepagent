"""BrandingProfile model — typed brand kit with per-platform override support."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

# Maximum length for brand_voice text injected into provider prompts.
BRAND_VOICE_MAX_CHARS = 2000

# Hex colour pattern for CSS-style colours (#RGB or #RRGGBB).
_HEX_COLOUR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# Allowed logo placement anchors.
LOGO_PLACEMENT_ANCHORS = frozenset(
    {
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
        "center",
    }
)

# Allowed caption style keys.
CAPTION_STYLE_KEYS = frozenset({"color", "size", "shadow", "bold", "italic", "font"})


# ──────────────────────────────────────────────────────────────
# Sub-models
# ──────────────────────────────────────────────────────────────


class ThumbnailBorder(BaseModel):
    """Rectangular border drawn around thumbnail frame previews."""

    color: str = "#000000"
    width: int = Field(default=10, ge=0, le=200)

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, value: str) -> str:
        """Ensure color is a valid CSS hex color string."""
        stripped = value.strip()
        if not _HEX_COLOUR_RE.fullmatch(stripped):
            raise ValueError(
                f"thumbnail_border.color must be a CSS hex color (#RGB or #RRGGBB), got: {value!r}"
            )
        return stripped


class CaptionStyle(BaseModel):
    """Caption text style parameters injected into ASS subtitle templates."""

    color: str = "#FFFFFF"
    size: int = Field(default=48, ge=8, le=256)
    shadow: bool = True
    bold: bool = False
    italic: bool = False
    font: str = ""

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, value: str) -> str:
        """Ensure color is a valid CSS hex color string."""
        stripped = value.strip()
        if not _HEX_COLOUR_RE.fullmatch(stripped):
            raise ValueError(
                f"caption_style.color must be a CSS hex color (#RGB or #RRGGBB), got: {value!r}"
            )
        return stripped


# ──────────────────────────────────────────────────────────────
# Platform override sub-model
# ──────────────────────────────────────────────────────────────


class PlatformBrandingOverride(BaseModel):
    """Partial branding overrides applied per export platform.

    Only fields present in the YAML override key are applied; absent fields
    default to the base profile value during merge.
    """

    logo_placement: str | None = None
    logo_opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    caption_style: CaptionStyle | None = None
    highlight_color: str | None = None
    bg_padding: str | None = None
    thumbnail_border: ThumbnailBorder | None = None

    @field_validator("logo_placement")
    @classmethod
    def validate_logo_placement(cls, value: str | None) -> str | None:
        """Accept anchor keywords or freeform coordinate strings."""
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("logo_placement cannot be an empty string")
        return stripped

    @field_validator("highlight_color")
    @classmethod
    def validate_hex_color(cls, value: str | None) -> str | None:
        """Ensure highlight_color is a valid CSS hex color when provided."""
        if value is None:
            return None
        stripped = value.strip()
        if not _HEX_COLOUR_RE.fullmatch(stripped):
            raise ValueError(
                f"highlight_color must be a CSS hex color (#RGB or #RRGGBB), got: {value!r}"
            )
        return stripped


# ──────────────────────────────────────────────────────────────
# Main BrandingProfile
# ──────────────────────────────────────────────────────────────


class BrandingProfile(BaseModel):
    """Reusable brand kit with visual asset references, copy voice, and per-platform overrides.

    Profiles are serialised to ``branding/<profile_name>.yaml`` and loaded
    by :func:`podcast_pipeline.utils.branding.load_profile`.

    The ``brand_voice`` field is injected as a bounded, sanitized System
    Instruction block in ``BaseProvider._build_prompt()``.  Control characters
    are stripped and the text is truncated to :data:`BRAND_VOICE_MAX_CHARS`.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    profile_name: str = Field(..., min_length=1, max_length=128)

    # ── Copy voice ──────────────────────────────────────────────────────────
    brand_voice: str = Field(
        default="",
        description=(
            "Free-text creative persona / tone instructions injected into provider prompts. "
            f"Sanitized and capped at {BRAND_VOICE_MAX_CHARS} characters."
        ),
    )

    # ── Visual assets ────────────────────────────────────────────────────────
    logo_path: Path | None = None
    logo_placement: str = "top_right"
    logo_opacity: float = Field(default=0.8, ge=0.0, le=1.0)
    font_path: Path | None = None

    # ── Caption styling ──────────────────────────────────────────────────────
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    highlight_color: str = "#FFFF00"

    # ── Layout ───────────────────────────────────────────────────────────────
    bg_padding: str = "0%"

    # ── Thumbnail framing ────────────────────────────────────────────────────
    thumbnail_border: ThumbnailBorder = Field(default_factory=ThumbnailBorder)

    # ── Per-platform overrides ───────────────────────────────────────────────
    platform_overrides: dict[str, PlatformBrandingOverride] = Field(default_factory=dict)

    # ── Sound kit ────────────────────────────────────────────────────────────
    # Optional: resolved sound kit paths for intro/transition/outro stingers.
    # When None the branding profile carries no sound assets; consumers check
    # before calling _mix_stingers().  Paths are stored as the profile YAML
    # author supplied them (relative to branding_dir or absolute) and are
    # resolved at render time by audio_mix helpers.
    intro_sound: Path | None = Field(
        default=None,
        description=(
            "Optional intro stinger audio file (WAV/FLAC/MP3). "
            "Played at the very start of the rendered video. "
            "Missing files degrade gracefully — a warning is logged and the stinger is skipped."
        ),
    )
    transition_sound: Path | None = Field(
        default=None,
        description=(
            "Optional transition whoosh audio file. "
            "Played at every content-cut boundary in the edit plan."
        ),
    )
    outro_sound: Path | None = Field(
        default=None,
        description=(
            "Optional outro theme audio file. "
            "Faded in during the last 5 seconds of the rendered video."
        ),
    )

    @property
    def has_sound_kit(self) -> bool:
        """Return True if at least one sound asset path is configured."""
        return any(
            p is not None for p in (self.intro_sound, self.transition_sound, self.outro_sound)
        )

    # ──────────────────────────────────────────────────────────────
    # Validators
    # ──────────────────────────────────────────────────────────────

    @field_validator("profile_name")
    @classmethod
    def validate_profile_name(cls, value: str) -> str:
        """Strip whitespace and reject empty names."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("profile_name cannot be blank")
        return stripped

    @field_validator("brand_voice")
    @classmethod
    def sanitize_brand_voice(cls, value: str) -> str:
        """Strip control characters and enforce max length.

        Rationale: brand_voice is user-supplied text injected verbatim into
        LLM prompts. We must ensure it cannot embed prompt-injection vectors
        via control characters or bleed past the prompt boundary by being
        excessively long.
        """
        return _sanitize_brand_voice(value)

    @field_validator("logo_placement")
    @classmethod
    def validate_logo_placement(cls, value: str) -> str:
        """Accept anchor keywords or coordinate strings like 'x=10, y=20'."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("logo_placement cannot be an empty string")
        return stripped

    @field_validator("highlight_color")
    @classmethod
    def validate_hex_color(cls, value: str) -> str:
        """Ensure highlight_color is a valid CSS hex color string."""
        stripped = value.strip()
        if not _HEX_COLOUR_RE.fullmatch(stripped):
            raise ValueError(
                f"highlight_color must be a CSS hex color (#RGB or #RRGGBB), got: {value!r}"
            )
        return stripped

    @model_validator(mode="after")
    def validate_platform_override_keys(self) -> BrandingProfile:
        """Reject empty platform key strings in platform_overrides."""
        for key in self.platform_overrides:
            if not key.strip():
                raise ValueError("platform_overrides keys must be non-empty platform name strings")
        return self

    # ──────────────────────────────────────────────────────────────
    # Merge helpers
    # ──────────────────────────────────────────────────────────────

    def resolved_for_platform(self, platform: str) -> BrandingProfile:
        """Return a new profile with the named platform's overrides applied.

        Merge order: base profile fields first, then per-platform override
        fields (only fields explicitly present in the override are applied).
        Fields absent from the override retain base-profile defaults.

        Args:
            platform: Export platform name (e.g. ``"youtube"``, ``"tiktok"``).
                      If no override exists for this platform the base profile
                      is returned unchanged.

        Returns:
            A new ``BrandingProfile`` instance.  The returned profile always
            has an empty ``platform_overrides`` dict — it is a "resolved" flat
            profile ready for downstream consumers.
        """
        override = self.platform_overrides.get(platform)
        if override is None:
            # Return a copy without nested overrides to signal resolution.
            return self.model_copy(update={"platform_overrides": {}})

        # Start from base field values.
        update: dict[str, Any] = {}
        if override.logo_placement is not None:
            update["logo_placement"] = override.logo_placement
        if override.logo_opacity is not None:
            update["logo_opacity"] = override.logo_opacity
        if override.caption_style is not None:
            update["caption_style"] = override.caption_style
        if override.highlight_color is not None:
            update["highlight_color"] = override.highlight_color
        if override.bg_padding is not None:
            update["bg_padding"] = override.bg_padding
        if override.thumbnail_border is not None:
            update["thumbnail_border"] = override.thumbnail_border

        # Overrides applied; resolved profiles carry no further overrides.
        update["platform_overrides"] = {}

        return self.model_copy(update=update)

    def sanitized_brand_voice(self) -> str:
        """Return the sanitized brand_voice string ready for prompt injection.

        Always returns the already-sanitized value stored in ``brand_voice``.
        Provided as a named method for explicitness at call sites.
        """
        return self.brand_voice


# ──────────────────────────────────────────────────────────────
# Module-level sanitization helper
# ──────────────────────────────────────────────────────────────


def _sanitize_brand_voice(text: str) -> str:
    """Strip control characters and truncate to BRAND_VOICE_MAX_CHARS.

    Removes all Unicode control characters (categories Cc and Cs) while
    preserving printable text.  This prevents prompt-injection vectors
    embedded as invisible control bytes from reaching the LLM.

    Args:
        text: Raw brand_voice string.

    Returns:
        Sanitized, truncated string.
    """
    cleaned_chars: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category in {"Cc", "Cs"}:
            # Skip control characters and surrogates; replace with a space
            # only if there is not already a trailing space.
            if cleaned_chars and cleaned_chars[-1] != " ":
                cleaned_chars.append(" ")
        else:
            cleaned_chars.append(char)

    cleaned = "".join(cleaned_chars).strip()
    return cleaned[:BRAND_VOICE_MAX_CHARS]
