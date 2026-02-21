"""Edit plan schema for render and clip exports."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


def _validate_forward_range(start_seconds: float, end_seconds: float, label: str) -> None:
    """Validate a non-negative, forward-moving time range."""
    if end_seconds <= start_seconds:
        raise ValueError(
            f"{label} must have end_seconds greater than start_seconds "
            f"(got start={start_seconds}, end={end_seconds})"
        )


class FillerCutRange(BaseModel):
    """Approved filler cut range in seconds."""

    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    word: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    category: str = ""
    context_before: str = ""
    context_after: str = ""
    editorial_action: Literal["remove", "keep"] = "remove"
    editorial_note: str = ""
    snapped: bool = False
    original_start: float | None = Field(default=None, ge=0.0)
    original_end: float | None = Field(default=None, ge=0.0)
    smoothing: Literal["micro_fade", "crossfade"] = "micro_fade"
    smoothing_audio_ms: float | None = Field(default=None, ge=0.0)
    smoothing_video_ms: float | None = Field(default=None, ge=0.0)

    # Phase 8: enriched triage fields — all optional/defaulted for backward compat
    protected: bool = False
    pause_before_ms: float = 0.0
    pause_after_ms: float = 0.0
    llm_safe_to_remove: bool | None = None  # None = not triaged
    llm_reason: str = ""

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Ensure filler cuts are non-empty forward ranges."""
        _validate_forward_range(self.start_seconds, self.end_seconds, "FillerCutRange")
        if (self.original_start is None) != (self.original_end is None):
            raise ValueError(
                "FillerCutRange original_start/original_end must both be set or both be null"
            )
        if self.original_start is not None and self.original_end is not None:
            _validate_forward_range(
                self.original_start, self.original_end, "FillerCutRange original"
            )
        return self


class ContentCutRange(BaseModel):
    """Approved content cut range in seconds."""

    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    reason: str = ""
    editorial_action: Literal["remove", "keep"] = "remove"
    snapped: bool = False
    original_start: float | None = Field(default=None, ge=0.0)
    original_end: float | None = Field(default=None, ge=0.0)
    smoothing: Literal["micro_fade", "crossfade", "dissolve"] = "crossfade"
    smoothing_audio_ms: float | None = Field(default=None, ge=0.0)
    smoothing_video_ms: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Ensure content cuts are non-empty forward ranges."""
        _validate_forward_range(self.start_seconds, self.end_seconds, "ContentCutRange")
        if (self.original_start is None) != (self.original_end is None):
            raise ValueError(
                "ContentCutRange original_start/original_end must both be set or both be null"
            )
        if self.original_start is not None and self.original_end is not None:
            _validate_forward_range(
                self.original_start, self.original_end, "ContentCutRange original"
            )
        return self


class ClipRange(BaseModel):
    """Approved clip export range in seconds."""

    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    description: str = ""
    score: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Ensure clip ranges are non-empty forward ranges."""
        _validate_forward_range(self.start_seconds, self.end_seconds, "ClipRange")
        return self


class EditPlan(BaseModel):
    """Serialized edit plan produced after review."""

    version: str = "1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    filler_cuts: list[FillerCutRange] = Field(default_factory=list)
    content_cuts: list[ContentCutRange] = Field(default_factory=list)
    clip_ranges: list[ClipRange] = Field(default_factory=list)

    @staticmethod
    def _validate_non_overlapping_ranges(
        ranges: Sequence[FillerCutRange | ContentCutRange],
        label: str,
    ) -> None:
        """Reject overlapping cut ranges to prevent silent merge behavior."""
        if len(ranges) < 2:
            return

        ordered = sorted(ranges, key=lambda item: item.start_seconds)
        previous = ordered[0]
        for current in ordered[1:]:
            if current.start_seconds < previous.end_seconds:
                raise ValueError(
                    f"{label} ranges overlap: "
                    f"({previous.start_seconds}, {previous.end_seconds}) "
                    f"and ({current.start_seconds}, {current.end_seconds})"
                )
            previous = current

    @model_validator(mode="after")
    def validate_non_overlapping_cuts(self) -> Self:
        """Ensure filler/content cuts do not overlap."""
        self._validate_non_overlapping_ranges(self.filler_cuts, "filler_cuts")
        self._validate_non_overlapping_ranges(self.content_cuts, "content_cuts")
        return self
