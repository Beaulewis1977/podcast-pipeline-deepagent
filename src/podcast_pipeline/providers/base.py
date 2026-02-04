"""Base provider protocol and error types."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from podcast_pipeline.models.analysis import AnalysisResult


class ProviderError(Exception):
    """Base error for AI providers."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class RateLimitError(ProviderError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message, retryable=True)
        self.retry_after = retry_after


class QuotaExceededError(ProviderError):
    """API quota exceeded."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


@runtime_checkable
class AnalysisProvider(Protocol):
    """Protocol for video analysis providers."""

    name: str

    def analyze(
        self,
        video_path: Path,
        transcript: dict[str, Any],
    ) -> AnalysisResult:
        """Analyze video content.

        Args:
            video_path: Path to video file (proxy)
            transcript: Transcript data from transcribe stage

        Returns:
            AnalysisResult with cuts, clips, thumbnails, marketing
        """
        ...

    def is_available(self) -> bool:
        """Check if provider is available (has API key)."""
        ...


class BaseProvider(ABC):
    """Base implementation for providers with common functionality."""

    name: str = "base"

    @abstractmethod
    def analyze(
        self,
        video_path: Path,
        transcript: dict[str, Any],
    ) -> AnalysisResult:
        """Analyze video content."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        ...

    def _build_prompt(self, transcript: dict[str, Any]) -> str:
        """Build the analysis prompt."""
        transcript_text = transcript.get("text", "")[:10000]  # Limit length

        return f'''You are a professional podcast editor and marketing strategist.

Analyze this podcast video and transcript to provide editing suggestions and marketing content.

TRANSCRIPT:
{transcript_text}

Provide your analysis as JSON with this exact structure:
{{
  "content_cuts": [
    {{
      "start": "MM:SS",
      "end": "MM:SS",
      "start_seconds": 0.0,
      "end_seconds": 0.0,
      "reason": "Why to cut this section"
    }}
  ],
  "viral_clips": [
    {{
      "start": "MM:SS",
      "end": "MM:SS",
      "start_seconds": 0.0,
      "end_seconds": 0.0,
      "description": "What makes this clip engaging",
      "virality_score": 8,
      "suggested_hook": "Text to hook viewers"
    }}
  ],
  "thumbnail_frames": [
    {{
      "timestamp": "MM:SS",
      "timestamp_seconds": 0.0,
      "visual_description": "What's in the frame",
      "suggested_text_overlay": "Text for thumbnail",
      "emotion": "joy/surprise/etc"
    }}
  ],
  "marketing": {{
    "youtube": {{
      "titles": ["Title 1 (<70 chars)", "Title 2", "Title 3"],
      "description": "Full YouTube description with timestamps",
      "hashtags": ["#podcast", "#topic"]
    }},
    "spotify": {{
      "titles": ["Episode title"],
      "description": "Spotify description",
      "hashtags": []
    }},
    "tiktok": {{
      "titles": [],
      "description": "TikTok caption",
      "hashtags": ["#fyp", "#podcast"]
    }},
    "linkedin": {{
      "titles": [],
      "description": "Professional LinkedIn post",
      "hashtags": ["#professional"]
    }},
    "twitter": {{
      "titles": [],
      "description": "Tweet (<280 chars)",
      "hashtags": []
    }},
    "apple": {{
      "titles": ["Episode title"],
      "description": "Apple Podcasts description",
      "hashtags": []
    }}
  }},
  "metadata": {{
    "summary": "2-3 sentence episode summary",
    "topics": ["topic1", "topic2"],
    "mood": "energetic/calm/thoughtful/etc",
    "guest_names": []
  }}
}}

Identify:
1. 2-4 content cuts (boring/off-topic sections to remove)
2. 3-5 viral clip candidates (most engaging 30-60 second moments)
3. 3-5 thumbnail frame timestamps
4. Platform-specific marketing copy

Return ONLY valid JSON, no other text.'''
