"""Edit plan schema for render and clip exports."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class FillerCutRange(BaseModel):
    """Approved filler cut range in seconds."""

    start_seconds: float
    end_seconds: float
    word: str = ""
    confidence: float | None = None


class ContentCutRange(BaseModel):
    """Approved content cut range in seconds."""

    start_seconds: float
    end_seconds: float
    reason: str = ""


class ClipRange(BaseModel):
    """Approved clip export range in seconds."""

    start_seconds: float
    end_seconds: float
    description: str = ""
    score: int | None = None


class EditPlan(BaseModel):
    """Serialized edit plan produced after review."""

    version: str = "1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    filler_cuts: list[FillerCutRange] = Field(default_factory=list)
    content_cuts: list[ContentCutRange] = Field(default_factory=list)
    clip_ranges: list[ClipRange] = Field(default_factory=list)
