"""Google Gemini provider for video analysis.

Supported Models (as of Feb 2026):
- gemini-2.5-flash / gemini-2.5-flash-latest: Best balance of cost and performance (RECOMMENDED)
- gemini-3-flash-preview: Latest model with Agentic Vision capabilities (preview)
- gemini-3-pro-preview: Most intelligent model, higher cost (preview)
- gemini-2.5-pro: Excellent video understanding, 2M token context

NOTE: gemini-2.0-flash is RETIRING on March 31, 2026 - DO NOT USE!

See: https://ai.google.dev/gemini-api/docs/models
"""

import json
import re
import time
from pathlib import Path
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from podcast_pipeline.models.analysis import AnalysisResult
from podcast_pipeline.providers.base import (
    BaseProvider,
    ProviderError,
    RateLimitError,
)
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# Supported Gemini models for video analysis
# Primary: gemini-2.5-flash - best cost/performance for video
# Alternative: gemini-3-flash-preview - latest with Agentic Vision
SUPPORTED_GEMINI_MODELS = [
    "gemini-2.5-flash",  # Recommended: best balance of cost and performance
    "gemini-2.5-flash-latest",  # Alias for latest 2.5-flash version
    "gemini-3-flash-preview",  # Latest model with Agentic Vision (preview)
    "gemini-3-pro-preview",  # Most intelligent, higher cost (preview)
    "gemini-2.5-pro",  # Excellent video understanding, 2M context
]

# Default model - gemini-2.5-flash is most cost-effective for video analysis
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class GeminiProvider(BaseProvider):
    """Google Gemini provider for video analysis.

    Uses Gemini's multimodal capabilities to analyze video content:
    - Video understanding with 1 FPS sampling
    - Audio and visual processing
    - Temporal reasoning for clip identification
    - Marketing copy generation

    Supports: MP4, MOV, AVI, WebM video formats.
    """

    name = "gemini"

    def __init__(self, api_key: str | None, model: str = DEFAULT_GEMINI_MODEL):
        self.api_key = api_key
        self.model = model
        self._client: Any = None

    def is_available(self) -> bool:
        """Check if Gemini API key is available."""
        return bool(self.api_key)

    def _get_client(self) -> Any:
        """Get or create Gemini client."""
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except ImportError as e:
                raise ProviderError(
                    "google-genai not installed. Run: pip install google-genai"
                ) from e
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=60, min=60, max=300),
        retry=retry_if_exception_type(RateLimitError),
        reraise=True,
    )
    def analyze(
        self,
        video_path: Path,
        transcript: dict[str, Any],
    ) -> AnalysisResult:
        """Analyze video using Gemini."""
        if not self.is_available():
            raise ProviderError("Gemini API key not configured")

        client = self._get_client()
        prompt = self._build_prompt(transcript)

        logger.info(
            "gemini_analyzing",
            model=self.model,
            video=str(video_path),
        )

        try:
            # Upload video file
            logger.info("uploading_video", path=str(video_path))
            video_file = client.files.upload(file=video_path)

            # Wait for processing
            while video_file.state.name == "PROCESSING":
                logger.debug("waiting_for_processing")
                time.sleep(5)
                video_file = client.files.get(name=video_file.name)

            if video_file.state.name == "FAILED":
                raise ProviderError(f"Video processing failed: {video_file.state}")

            # Generate content
            response = client.models.generate_content(
                model=self.model,
                contents=[video_file, prompt],
            )

            # Parse response
            result_text = response.text
            logger.debug("gemini_response", text=result_text[:500])

            # Extract JSON from response
            analysis_data = self._parse_response(result_text)

            # Clean up uploaded file
            try:
                client.files.delete(name=video_file.name)
            except Exception:
                pass  # Best effort cleanup

            return AnalysisResult.model_validate(analysis_data)

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "quota" in error_str or "429" in error_str:
                raise RateLimitError(f"Gemini rate limit: {e}") from e
            raise ProviderError(f"Gemini analysis failed: {e}") from e

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """Parse JSON from Gemini response."""
        # Try to extract JSON from response
        # Gemini sometimes wraps JSON in markdown code blocks
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try parsing the whole response as JSON
            json_str = response_text.strip()

        try:
            return dict(json.loads(json_str))
        except json.JSONDecodeError as e:
            logger.warning("json_parse_failed", error=str(e), response=response_text[:200])
            # Return minimal valid structure
            return {
                "content_cuts": [],
                "viral_clips": [],
                "thumbnail_frames": [],
                "marketing": {
                    "youtube": {"titles": [], "description": "", "hashtags": []},
                    "spotify": {"titles": [], "description": "", "hashtags": []},
                    "tiktok": {"titles": [], "description": "", "hashtags": []},
                    "linkedin": {"titles": [], "description": "", "hashtags": []},
                    "twitter": {"titles": [], "description": "", "hashtags": []},
                    "apple": {"titles": [], "description": "", "hashtags": []},
                },
                "metadata": {
                    "summary": "Analysis parsing failed",
                    "topics": [],
                    "mood": "unknown",
                    "guest_names": [],
                },
            }
