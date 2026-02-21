"""Base provider protocol and error types."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from podcast_pipeline.models.analysis import AnalysisResult


class ProviderError(Exception):
    """Base error for AI providers."""

    def __init__(
        self,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.details = details or {}


class RateLimitError(ProviderError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, retryable=True, details=details)
        self.retry_after = retry_after


class ProviderParseError(ProviderError):
    """Provider response could not be parsed or validated."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, retryable=False, details=details)


class QuotaExceededError(ProviderError):
    """API quota exceeded."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


@runtime_checkable
class AnalysisProvider(Protocol):
    """Protocol for video analysis providers."""

    name: str
    model: str
    supports_video: bool

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
    model: str = "unknown"
    supports_video: bool = True

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

    def _build_prompt(
        self,
        transcript: dict[str, Any],
        trend_context: dict[str, Any] | None = None,
    ) -> str:
        """Build the analysis prompt."""
        transcript_text = str(transcript.get("text", ""))[:10000]  # Limit length
        resolved_trend_context = trend_context
        if resolved_trend_context is None:
            raw_context = transcript.get("trend_context")
            if isinstance(raw_context, dict):
                resolved_trend_context = raw_context
        trend_context_block = self._build_trend_context_block(resolved_trend_context)

        return f"""You are a professional podcast editor and marketing strategist.

Analyze this podcast video and transcript to provide editing suggestions and marketing content.

TRANSCRIPT:
{transcript_text}

TREND CONTEXT:
{trend_context_block}

Marketing copy requirements (strict):
- Generate original copy for EVERY marketing platform key: youtube, spotify, spotify_video, apple, apple_video, tiktok, instagram, linkedin, twitter, facebook.
- Style must be high-impact and viral-ready without spammy clickbait or fabricated claims.
- Keep tone professional, credible, and audience-appropriate.
- Tailor language to each platform format instead of duplicating one generic description.
- Use trend context (keywords, hooks, competitive angle) when relevant and grounded in transcript evidence.
- For each platform, always provide titles, description, and hashtags fields in the JSON schema.

Thumbnail requirements (strict):
- Include virality metadata for every thumbnail candidate: virality_score, viral_style, virality_score_source, recommendation_signal.
- When thumbnail candidates are present, include at least one strong recommendation_signal that explains why that frame should be prioritized.

Platform-specific expectations:
- youtube: title options optimized for discovery and a detailed long-form description.
- spotify: concise audio-episode title + description for podcast listeners.
- spotify_video: video-podcast title/description emphasizing visual value and watch intent.
- apple: polished audio-episode title + description for Apple Podcasts listeners.
- apple_video: video-podcast title/description for Apple Podcasts video consumption.
- tiktok: short hook-forward caption and hashtag set.
- instagram: reel-friendly caption with concise hook and hashtags.
- linkedin: professional narrative emphasizing insight/value.
- twitter: concise post-length copy suitable for X audiences.
- facebook: conversational social copy optimized for feed engagement.

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
      "emotion": "joy/surprise/etc",
      "virality_score": 0.0,
      "viral_style": "reaction/story/mystery/etc",
      "virality_score_source": "provider/heuristic",
      "recommendation_signal": "Specific recommendation reason"
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
    "spotify_video": {{
      "titles": ["Episode title for Spotify Video"],
      "description": "Spotify Video description focused on visual moments and chapters",
      "hashtags": []
    }},
    "apple": {{
      "titles": ["Episode title"],
      "description": "Apple Podcasts description",
      "hashtags": []
    }},
    "apple_video": {{
      "titles": ["Episode title for Apple Podcasts Video"],
      "description": "Apple Podcasts Video description emphasizing watchability and key moments",
      "hashtags": []
    }},
    "tiktok": {{
      "titles": [],
      "description": "TikTok caption",
      "hashtags": ["#fyp", "#podcast"]
    }},
    "instagram": {{
      "titles": [],
      "description": "Instagram Reel caption",
      "hashtags": ["#reels", "#podcast"]
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
    "facebook": {{
      "titles": [],
      "description": "Facebook post copy",
      "hashtags": ["#podcast"]
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
4. Platform-specific marketing copy for ALL listed platform keys

Return ONLY valid JSON, no other text."""

    @staticmethod
    def _build_trend_context_block(trend_context: dict[str, Any] | None) -> str:
        """Build a stable trend-context block for prompt injection."""
        if not trend_context:
            return (
                '- "keywords": []\n'
                '- "trending_hooks": []\n'
                '- "competitive_angle": ""\n'
                '- "momentum_signals": []\n'
                "(No external artifacts were available; infer from transcript only.)"
            )

        keywords = BaseProvider._coerce_string_list(trend_context.get("keywords"))
        hooks = BaseProvider._coerce_string_list(trend_context.get("trending_hooks"))
        momentum = BaseProvider._coerce_string_list(trend_context.get("momentum_signals"))
        competitive_angle = trend_context.get("competitive_angle", "")
        if not isinstance(competitive_angle, str):
            competitive_angle = str(competitive_angle)

        return (
            f'- "keywords": {json.dumps(keywords)}\n'
            f'- "trending_hooks": {json.dumps(hooks)}\n'
            f'- "competitive_angle": {json.dumps(competitive_angle)}\n'
            f'- "momentum_signals": {json.dumps(momentum)}'
        )

    @staticmethod
    def _coerce_string_list(value: Any) -> list[str]:
        """Normalize potentially mixed values into prompt-safe string lists."""
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
