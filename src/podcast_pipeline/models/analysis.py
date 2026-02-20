"""Analysis result models."""

from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

TIMESTAMP_TOLERANCE_SECONDS = 1.0


def _parse_timestamp(label: str) -> float:
    """Parse MM:SS or HH:MM:SS timestamp values to seconds."""
    normalized = label.strip()
    parts = normalized.split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("Timestamp must be MM:SS or HH:MM:SS")

    try:
        numeric = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError("Timestamp must contain only numeric values") from exc

    if any(value < 0 for value in numeric):
        raise ValueError("Timestamp values cannot be negative")

    if len(parts) == 2:
        minutes, seconds = numeric
        if seconds >= 60:
            raise ValueError("MM:SS timestamp seconds must be < 60")
        return (minutes * 60) + seconds

    hours, minutes, seconds = numeric
    if minutes >= 60 or seconds >= 60:
        raise ValueError("HH:MM:SS timestamp minutes/seconds must be < 60")
    return (hours * 3600) + (minutes * 60) + seconds


def _validate_time_consistency(
    start_label: str,
    end_label: str,
    start_seconds: float,
    end_seconds: float,
    model_label: str,
) -> None:
    """Validate forward ranges and cross-field consistency for time values."""
    parsed_start = _parse_timestamp(start_label)
    parsed_end = _parse_timestamp(end_label)

    if parsed_end <= parsed_start:
        raise ValueError(
            f"{model_label} end timestamp must be after start timestamp "
            f"(got start={start_label}, end={end_label})"
        )

    if end_seconds <= start_seconds:
        raise ValueError(
            f"{model_label} end_seconds must be greater than start_seconds "
            f"(got start={start_seconds}, end={end_seconds})"
        )

    if abs(parsed_start - start_seconds) > TIMESTAMP_TOLERANCE_SECONDS:
        raise ValueError(
            f"{model_label} start mismatch between '{start_label}' and {start_seconds} seconds"
        )
    if abs(parsed_end - end_seconds) > TIMESTAMP_TOLERANCE_SECONDS:
        raise ValueError(
            f"{model_label} end mismatch between '{end_label}' and {end_seconds} seconds"
        )


class _TimeRangeModel(BaseModel):
    """Shared range validation for models that store string + seconds time fields."""

    start: str
    end: str
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)

    @field_validator("start", "end")
    @classmethod
    def validate_timestamp_format(cls, value: str) -> str:
        """Ensure timestamp labels are parseable."""
        _parse_timestamp(value)
        return value

    @model_validator(mode="after")
    def validate_range_consistency(self) -> Self:
        """Ensure string and seconds time fields are internally consistent."""
        _validate_time_consistency(
            self.start,
            self.end,
            self.start_seconds,
            self.end_seconds,
            self.__class__.__name__,
        )
        return self


class ContentCut(_TimeRangeModel):
    """A suggested section to cut from the video."""

    reason: str


class ViralClip(_TimeRangeModel):
    """A potential viral clip candidate."""

    description: str = ""
    virality_score: int = Field(ge=1, le=10, default=5)
    suggested_hook: str = ""


class ThumbnailCandidate(BaseModel):
    """A potential thumbnail frame."""

    timestamp: str
    timestamp_seconds: float = Field(default=0.0, ge=0.0)
    visual_description: str = ""
    suggested_text_overlay: str = ""
    emotion: str = ""
    virality_score: float = Field(default=0.0, ge=0.0, le=10.0)
    viral_style: str = ""
    virality_score_source: str = "unspecified"
    recommendation_signal: str = ""
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_label: str | None = None

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        """Ensure thumbnail timestamp strings are parseable."""
        _parse_timestamp(value)
        return value

    @model_validator(mode="after")
    def validate_timestamp_consistency(self) -> Self:
        """Ensure string and seconds thumbnail timestamps match."""
        parsed = _parse_timestamp(self.timestamp)
        if abs(parsed - self.timestamp_seconds) > TIMESTAMP_TOLERANCE_SECONDS:
            raise ValueError(
                "ThumbnailCandidate timestamp mismatch between "
                f"'{self.timestamp}' and {self.timestamp_seconds} seconds"
            )
        return self


class PlatformMarketing(BaseModel):
    """Marketing copy for a specific platform."""

    titles: list[str] = Field(default_factory=list)
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)


class MarketingCopy(BaseModel):
    """All marketing copy across platforms."""

    youtube: PlatformMarketing = Field(default_factory=PlatformMarketing)
    spotify: PlatformMarketing = Field(default_factory=PlatformMarketing)
    spotify_video: PlatformMarketing = Field(default_factory=PlatformMarketing)
    apple: PlatformMarketing = Field(default_factory=PlatformMarketing)
    apple_video: PlatformMarketing = Field(default_factory=PlatformMarketing)
    tiktok: PlatformMarketing = Field(default_factory=PlatformMarketing)
    instagram: PlatformMarketing = Field(default_factory=PlatformMarketing)
    linkedin: PlatformMarketing = Field(default_factory=PlatformMarketing)
    twitter: PlatformMarketing = Field(default_factory=PlatformMarketing)
    facebook: PlatformMarketing = Field(default_factory=PlatformMarketing)


class Metadata(BaseModel):
    """Episode metadata."""

    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    mood: str = ""
    guest_names: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Complete AI analysis result."""

    content_cuts: list[ContentCut] = Field(default_factory=list)
    viral_clips: list[ViralClip] = Field(default_factory=list)
    thumbnail_frames: list[ThumbnailCandidate] = Field(default_factory=list)
    marketing: MarketingCopy = Field(default_factory=MarketingCopy)
    metadata: Metadata = Field(default_factory=Metadata)
