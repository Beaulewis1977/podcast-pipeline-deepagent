"""Transcript models."""

from pydantic import BaseModel, Field


class Word(BaseModel):
    """A single word with timestamp and confidence."""

    word: str
    start: float
    end: float
    confidence: float


class Segment(BaseModel):
    """A segment of transcript text."""

    start: float
    end: float
    text: str
    words: list[Word] = Field(default_factory=list)
    speaker: str | None = None  # Speaker identification


class FillerCut(BaseModel):
    """A detected filler word to potentially remove."""

    start: float
    end: float
    word: str
    confidence: float


class TranscriptResult(BaseModel):
    """Complete transcription result."""

    text: str
    segments: list[Segment] = Field(default_factory=list)
    filler_cuts: list[FillerCut] = Field(default_factory=list)
    language: str = "en"
    duration: float = 0.0
    speaker: str | None = None  # For multi-track: speaker identifier
    track_index: int = 0  # Audio track index (-1 for merged)
