"""Kimi (Moonshot) provider for video analysis - fallback provider.

Kimi K2.5 Model Info (as of Feb 2026):
- Model name: kimi-k2.5
- API endpoint: https://api.moonshot.cn/v1 (OpenAI-compatible)
- Native multimodal support (vision + text)
- Context window: 256K tokens
- Pricing: $0.60/M input tokens, $3.00/M output tokens

Modes:
- "thinking" mode: temperature 1.0, use_thinking_code=true
- "instant" mode: temperature 0.6 (default for faster responses)

See: https://platform.moonshot.ai
"""

import json
import re
from pathlib import Path
from typing import Any

import httpx
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

# Kimi API endpoint (OpenAI-compatible)
KIMI_API_URL = "https://api.moonshot.cn/v1/chat/completions"

# Supported Kimi models
SUPPORTED_KIMI_MODELS = [
    "kimi-k2.5",  # Latest multimodal model (RECOMMENDED)
    "moonshot-v1-128k",  # Legacy model (for backward compatibility)
]

# Default model - kimi-k2.5 is the latest with native multimodal support
DEFAULT_KIMI_MODEL = "kimi-k2.5"

# Temperature for "instant" mode (faster responses)
# Use 1.0 for "thinking" mode with deeper reasoning
KIMI_INSTANT_TEMPERATURE = 0.6


class KimiProvider(BaseProvider):
    """Kimi (Moonshot) provider - text-based analysis fallback.

    Uses Kimi K2.5 with OpenAI-compatible API for transcript analysis.
    Note: Currently text-only, video analysis requires Gemini.

    Features:
    - 256K token context window
    - Fast "instant" mode (temperature 0.6)
    - Native multimodal support
    """

    name = "kimi"

    def __init__(self, api_key: str | None, model: str = DEFAULT_KIMI_MODEL):
        self.api_key = api_key
        self.model = model

    def is_available(self) -> bool:
        """Check if Kimi API key is available."""
        return bool(self.api_key)

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
        """Analyze using Kimi (transcript only, no video)."""
        if not self.is_available():
            raise ProviderError("Kimi API key not configured")

        prompt = self._build_prompt(transcript)

        logger.info(
            "kimi_analyzing",
            model=self.model,
        )

        try:
            response = httpx.post(
                KIMI_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a podcast editor and marketing expert. Analyze content and provide JSON responses.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    "temperature": KIMI_INSTANT_TEMPERATURE,  # 0.6 for "instant" mode
                },
                timeout=120.0,
            )

            if response.status_code == 429:
                raise RateLimitError("Kimi rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            result_text = data["choices"][0]["message"]["content"]
            analysis_data = self._parse_response(result_text)

            return AnalysisResult.model_validate(analysis_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(f"Kimi rate limit: {e}") from e
            raise ProviderError(f"Kimi API error: {e}") from e
        except Exception as e:
            raise ProviderError(f"Kimi analysis failed: {e}") from e

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """Parse JSON from Kimi response."""
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
        json_str = json_match.group(1).strip() if json_match else response_text.strip()

        try:
            return dict(json.loads(json_str))
        except json.JSONDecodeError:
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
