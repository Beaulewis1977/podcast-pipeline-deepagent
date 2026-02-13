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
        self._upload_cache: dict[str, str] = {}

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

        cache_key = self._upload_cache_key(video_path)
        try:
            video_file = self._get_cached_or_upload_file(
                client=client,
                cache_key=cache_key,
                video_path=video_path,
            )

            # Wait for processing
            while video_file.state.name == "PROCESSING":
                logger.debug("waiting_for_processing")
                time.sleep(5)
                video_file = client.files.get(name=video_file.name)

            if video_file.state.name == "FAILED":
                self._upload_cache.pop(cache_key, None)
                raise ProviderError(
                    "Gemini video processing failed",
                    details={
                        "provider": self.name,
                        "model": self.model,
                        "video_path": str(video_path),
                        "video_state": str(video_file.state),
                    },
                )

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
            try:
                return AnalysisResult.model_validate(analysis_data)
            except ValidationError as error:
                raise ProviderParseError(
                    "Gemini returned an invalid analysis schema",
                    details={
                        "provider": self.name,
                        "model": self.model,
                        "validation_error": str(error),
                        "video_path": str(video_path),
                    },
                ) from error
        except ProviderError:
            raise
        except Exception as error:
            classified = self._classify_retryable_error(error)
            if classified is not None:
                raise classified from error
            raise ProviderError(
                "Gemini analysis failed",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "error_type": type(error).__name__,
                    "video_path": str(video_path),
                },
            ) from error

    def _upload_cache_key(self, video_path: Path) -> str:
        """Build cache key for reusing uploaded files across analyze attempts."""
        return str(video_path.resolve(strict=False))

    def _get_cached_or_upload_file(
        self,
        client: Any,
        cache_key: str,
        video_path: Path,
    ) -> Any:
        """Get cached upload when possible, otherwise upload and cache."""
        cached_upload_name = self._upload_cache.get(cache_key)
        if cached_upload_name:
            try:
                cached_file = client.files.get(name=cached_upload_name)
                logger.info(
                    "gemini_upload_cache_hit",
                    model=self.model,
                    video=str(video_path),
                    upload_name=cached_upload_name,
                )
                return cached_file
            except Exception as error:
                self._upload_cache.pop(cache_key, None)
                logger.warning(
                    "gemini_upload_cache_stale",
                    model=self.model,
                    video=str(video_path),
                    upload_name=cached_upload_name,
                    error=str(error),
                )

        logger.info(
            "gemini_upload_cache_miss",
            model=self.model,
            video=str(video_path),
        )
        logger.info("uploading_video", path=str(video_path))
        try:
            uploaded_file = client.files.upload(file=video_path)
        except Exception as error:
            classified = self._classify_retryable_error(error)
            if classified is not None:
                raise classified from error
            raise ProviderError(
                "Gemini video upload failed",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "video_path": str(video_path),
                    "error_type": type(error).__name__,
                },
            ) from error

        upload_name = getattr(uploaded_file, "name", None)
        if not isinstance(upload_name, str) or not upload_name:
            self._upload_cache.pop(cache_key, None)
            raise ProviderError(
                "Gemini upload did not return a valid file identifier",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "video_path": str(video_path),
                    "upload_name": upload_name,
                },
            )

        self._upload_cache[cache_key] = upload_name
        return uploaded_file

    def _classify_retryable_error(self, error: Exception) -> RateLimitError | None:
        """Classify retryable provider failures from structured status metadata."""
        status_code = self._extract_status_code(error)
        if status_code != 429:
            return None

        return RateLimitError(
            "Gemini rate limit exceeded",
            retry_after=self._extract_retry_after(error),
            details={
                "provider": self.name,
                "model": self.model,
                "status_code": status_code,
                "error_type": type(error).__name__,
            },
        )

    @staticmethod
    def _extract_status_code(error: Exception) -> int | None:
        """Extract status code from provider exceptions."""
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code

        response = getattr(error, "response", None)
        response_status_code = getattr(response, "status_code", None)
        if isinstance(response_status_code, int):
            return response_status_code

        code = getattr(error, "code", None)
        if isinstance(code, int):
            return code
        return None

    @staticmethod
    def _extract_retry_after(error: Exception) -> int | None:
        """Extract retry-after seconds from provider exceptions when present."""
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        header_value = headers.get("retry-after")
        try:
            return int(header_value) if header_value is not None else None
        except (TypeError, ValueError):
            return None

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
            parsed = json.loads(json_str)
        except json.JSONDecodeError as error:
            logger.warning(
                "json_parse_failed",
                provider=self.name,
                model=self.model,
                error=str(error),
                response=response_text[:200],
            )
            raise ProviderParseError(
                "Gemini returned invalid JSON",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "json_error": str(error),
                    "response_excerpt": response_text[:200],
                },
            ) from error

        if not isinstance(parsed, dict):
            raise ProviderParseError(
                "Gemini response JSON must be an object",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "payload_type": type(parsed).__name__,
                    "response_excerpt": response_text[:200],
                },
            )

        return dict(parsed)
