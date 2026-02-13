"""Kimi (Moonshot) provider for transcript-only fallback analysis.

Kimi K2.5 Model Info (as of Feb 2026):
- Model name: kimi-k2.5
- API endpoint: https://api.moonshot.cn/v1 (OpenAI-compatible)
- Model supports multimodal inputs, but this integration sends transcript text only
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
from pydantic import ValidationError
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
    ProviderParseError,
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
    """Kimi (Moonshot) provider for transcript-only fallback analysis.

    Uses Kimi K2.5 with OpenAI-compatible API for transcript analysis.
    Note: `video_path` is currently ignored by design.

    Features:
    - 256K token context window
    - Fast "instant" mode (temperature 0.6)
    - Reliable transcript-only fallback behavior
    """

    name = "kimi"
    supports_video = False

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
        """Analyze using Kimi transcript-only mode."""
        if not self.is_available():
            raise ProviderError("Kimi API key not configured")

        prompt = self._build_prompt(transcript)

        logger.info(
            "kimi_analyzing",
            model=self.model,
        )
        logger.warning(
            "kimi_transcript_only_mode",
            model=self.model,
            ignored_video_path=str(video_path),
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
                raise RateLimitError(
                    "Kimi rate limit exceeded",
                    details={
                        "provider": self.name,
                        "model": self.model,
                        "status_code": response.status_code,
                    },
                )

            response.raise_for_status()
            data = response.json()

            result_text = data["choices"][0]["message"]["content"]
            analysis_data = self._parse_response(result_text)

            try:
                return AnalysisResult.model_validate(analysis_data)
            except ValidationError as error:
                raise ProviderParseError(
                    "Kimi returned an invalid analysis schema",
                    details={
                        "provider": self.name,
                        "model": self.model,
                        "validation_error": str(error),
                    },
                ) from error

        except ProviderError:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(
                    "Kimi rate limit exceeded",
                    details={
                        "provider": self.name,
                        "model": self.model,
                        "status_code": e.response.status_code,
                    },
                ) from e
            raise ProviderError(
                "Kimi API error",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "status_code": e.response.status_code,
                    "error_type": type(e).__name__,
                },
            ) from e
        except Exception as e:
            raise ProviderError(
                "Kimi analysis failed",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "error_type": type(e).__name__,
                },
            ) from e

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """Parse JSON from Kimi response."""
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
        json_str = json_match.group(1).strip() if json_match else response_text.strip()

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as error:
            raise ProviderParseError(
                "Kimi returned invalid JSON",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "json_error": str(error),
                    "response_excerpt": response_text[:200],
                },
            ) from error

        if not isinstance(parsed, dict):
            raise ProviderParseError(
                "Kimi response JSON must be an object",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "payload_type": type(parsed).__name__,
                    "response_excerpt": response_text[:200],
                },
            )
        return dict(parsed)
