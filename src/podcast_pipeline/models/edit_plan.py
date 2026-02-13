"""Edit plan schema for render and clip exports."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Self

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

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Ensure filler cuts are non-empty forward ranges."""
        _validate_forward_range(self.start_seconds, self.end_seconds, "FillerCutRange")
        return self


class ContentCutRange(BaseModel):
    """Approved content cut range in seconds."""

    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    reason: str = ""

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Ensure content cuts are non-empty forward ranges."""
        _validate_forward_range(self.start_seconds, self.end_seconds, "ContentCutRange")
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
