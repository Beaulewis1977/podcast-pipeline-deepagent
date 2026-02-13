"""Transcript models."""

from typing import Self

from pydantic import BaseModel, Field, model_validator


def _validate_forward_range(start: float, end: float, label: str) -> None:
    """Validate non-negative, forward-moving ranges."""
    if end <= start:
        raise ValueError(f"{label} end must be greater than start (got start={start}, end={end})")


class Word(BaseModel):
    """A single word with timestamp and confidence."""

    word: str
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Ensure words have valid forward timestamps."""
        _validate_forward_range(self.start, self.end, "Word")
        return self


class Segment(BaseModel):
    """A segment of transcript text."""

    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    text: str
    words: list[Word] = Field(default_factory=list)
    speaker: str | None = None  # Speaker identification

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Ensure segments are forward and contain in-range words."""
        _validate_forward_range(self.start, self.end, "Segment")

        for word in self.words:
            if word.start < self.start:
                raise ValueError(
                    f"Segment word start ({word.start}) precedes segment start ({self.start})"
                )
            if word.end > self.end:
                raise ValueError(f"Segment word end ({word.end}) exceeds segment end ({self.end})")

        return self


class FillerCut(BaseModel):
    """A detected filler word to potentially remove."""

    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    word: str
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Ensure filler cuts are forward ranges."""
        _validate_forward_range(self.start, self.end, "FillerCut")
        return self


class TranscriptResult(BaseModel):
    """Complete transcription result."""

    text: str
    segments: list[Segment] = Field(default_factory=list)
    filler_cuts: list[FillerCut] = Field(default_factory=list)
    language: str = "en"
    duration: float = Field(default=0.0, ge=0.0)
    speaker: str | None = None  # For multi-track: speaker identifier
    track_index: int = 0  # Audio track index (-1 for merged)

    @model_validator(mode="after")
    def validate_duration_bounds(self) -> Self:
        """Ensure segment/cut bounds do not exceed declared duration."""
        if self.duration <= 0:
            return self

        max_segment_end = max((segment.end for segment in self.segments), default=0.0)
        if max_segment_end > self.duration:
            raise ValueError(
                f"TranscriptResult duration ({self.duration}) is less than max segment end "
                f"({max_segment_end})"
            )

        max_cut_end = max((cut.end for cut in self.filler_cuts), default=0.0)
        if max_cut_end > self.duration:
            raise ValueError(
                f"TranscriptResult duration ({self.duration}) is less than max filler cut end "
                f"({max_cut_end})"
            )

        return self
