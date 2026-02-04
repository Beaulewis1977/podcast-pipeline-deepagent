"""Analysis result models."""

from pydantic import BaseModel, Field


class ContentCut(BaseModel):
    """A suggested section to cut from the video."""

    start: str  # MM:SS format
    end: str
    start_seconds: float
    end_seconds: float
    reason: str


class ViralClip(BaseModel):
    """A potential viral clip candidate."""

    start: str
    end: str
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    description: str = ""
    virality_score: int = Field(ge=1, le=10, default=5)
    suggested_hook: str = ""


class ThumbnailCandidate(BaseModel):
    """A potential thumbnail frame."""

    timestamp: str
    timestamp_seconds: float = 0.0
    visual_description: str = ""
    suggested_text_overlay: str = ""
    emotion: str = ""


class PlatformMarketing(BaseModel):
    """Marketing copy for a specific platform."""

    titles: list[str] = Field(default_factory=list)
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)


class MarketingCopy(BaseModel):
    """All marketing copy across platforms."""

    youtube: PlatformMarketing = Field(default_factory=PlatformMarketing)
    spotify: PlatformMarketing = Field(default_factory=PlatformMarketing)
    apple: PlatformMarketing = Field(default_factory=PlatformMarketing)
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
