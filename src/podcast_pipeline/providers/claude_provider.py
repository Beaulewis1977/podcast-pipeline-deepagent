"""Claude (Anthropic) provider for transcript-only analysis.

Claude Model Info (as of Feb 2026):
- Model name: claude-sonnet-4-6 (RECOMMENDED — best cost/performance balance)
- Alternative: claude-haiku-4-5 (faster, cheaper, lower quality)
- Alternative: claude-opus-4-6 (most intelligent, highest cost)
- API endpoint: https://api.anthropic.com
- Context window: 200K tokens
- Pricing: https://www.anthropic.com/pricing

Claude API integration uses structured output via tool_use to enforce a
strict JSON schema on responses. Free-form JSON-in-prose parsing is NOT
used as the primary contract — schema guarantees are enforced by the SDK.

Key properties:
- supports_video = False (Anthropic API does not accept video files)
- Auth via ANTHROPIC_API_KEY environment variable
- Graceful degradation when API key is absent (is_available returns False)

See: https://docs.anthropic.com/en/api/messages
"""

import json
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
    QuotaExceededError,
    RateLimitError,
)
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# Supported Claude models — keys accepted by ModelConfig
SUPPORTED_CLAUDE_MODELS = {
    "claude-sonnet-4-6",  # Best cost/performance (RECOMMENDED)
    "claude-haiku-4-5",  # Fast, cheaper
    "claude-opus-4-6",  # Most intelligent, highest cost
}

# Default model
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"

# Maximum token budget for analysis responses (generous to avoid truncation)
CLAUDE_MAX_TOKENS = 4096

# Tool name used for structured output
_ANALYSIS_TOOL_NAME = "provide_analysis"

# JSON Schema for the structured output tool — mirrors the BaseProvider prompt schema
_ANALYSIS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content_cuts": {
            "type": "array",
            "description": "Sections to cut from the episode",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "MM:SS timestamp"},
                    "end": {"type": "string", "description": "MM:SS timestamp"},
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "start_seconds", "end_seconds", "reason"],
            },
        },
        "viral_clips": {
            "type": "array",
            "description": "Most engaging 30-60 second clip candidates",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                    "description": {"type": "string"},
                    "virality_score": {"type": "number"},
                    "suggested_hook": {"type": "string"},
                },
                "required": [
                    "start",
                    "end",
                    "start_seconds",
                    "end_seconds",
                    "description",
                    "virality_score",
                    "suggested_hook",
                ],
            },
        },
        "thumbnail_frames": {
            "type": "array",
            "description": "Thumbnail frame candidates with virality metadata",
            "items": {
                "type": "object",
                "properties": {
                    "timestamp": {"type": "string"},
                    "timestamp_seconds": {"type": "number"},
                    "visual_description": {"type": "string"},
                    "suggested_text_overlay": {"type": "string"},
                    "emotion": {"type": "string"},
                    "virality_score": {"type": "number"},
                    "viral_style": {"type": "string"},
                    "virality_score_source": {"type": "string"},
                    "recommendation_signal": {"type": "string"},
                },
                "required": [
                    "timestamp",
                    "timestamp_seconds",
                    "visual_description",
                    "suggested_text_overlay",
                    "emotion",
                    "virality_score",
                    "viral_style",
                    "virality_score_source",
                    "recommendation_signal",
                ],
            },
        },
        "marketing": {
            "type": "object",
            "description": "Platform-specific marketing copy",
            "properties": {
                "youtube": {"$ref": "#/$defs/platform_copy"},
                "spotify": {"$ref": "#/$defs/platform_copy"},
                "spotify_video": {"$ref": "#/$defs/platform_copy"},
                "apple": {"$ref": "#/$defs/platform_copy"},
                "apple_video": {"$ref": "#/$defs/platform_copy"},
                "tiktok": {"$ref": "#/$defs/platform_copy"},
                "instagram": {"$ref": "#/$defs/platform_copy"},
                "linkedin": {"$ref": "#/$defs/platform_copy"},
                "twitter": {"$ref": "#/$defs/platform_copy"},
                "facebook": {"$ref": "#/$defs/platform_copy"},
            },
            "required": [
                "youtube",
                "spotify",
                "spotify_video",
                "apple",
                "apple_video",
                "tiktok",
                "instagram",
                "linkedin",
                "twitter",
                "facebook",
            ],
        },
        "metadata": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "topics": {"type": "array", "items": {"type": "string"}},
                "mood": {"type": "string"},
                "guest_names": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "topics"],
        },
    },
    "required": ["content_cuts", "viral_clips", "thumbnail_frames", "marketing", "metadata"],
    "$defs": {
        "platform_copy": {
            "type": "object",
            "properties": {
                "titles": {"type": "array", "items": {"type": "string"}},
                "description": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["titles", "description", "hashtags"],
        }
    },
}


class ClaudeProvider(BaseProvider):
    """Anthropic Claude provider for transcript-only analysis.

    Uses Claude Sonnet/Haiku/Opus with the Anthropic Python SDK.
    Structured output is enforced via tool_use (JSON schema contract).
    ``video_path`` is accepted for protocol conformance but is ignored
    — Claude API does not support direct video input.

    Features:
    - 200K token context window
    - Strict structured output via tool_use schema contract
    - Typed parse errors for malformed/schema-violating responses
    - Exponential backoff on rate limits (3 attempts)
    """

    name = "claude"
    supports_video = False

    def __init__(self, api_key: str | None, model: str = DEFAULT_CLAUDE_MODEL):
        self.api_key = api_key
        self.model = model

    def is_available(self) -> bool:
        """Check if Claude API key is present."""
        return bool(self.api_key)

    def _get_client(self) -> Any:
        """Lazily instantiate the Anthropic client.

        Raises:
            ProviderError: If the anthropic package is not installed.
        """
        try:
            import anthropic

            return anthropic.Anthropic(api_key=self.api_key)
        except ImportError as exc:
            raise ProviderError(
                "anthropic package is not installed; run: uv add anthropic",
                details={"provider": self.name, "import_error": str(exc)},
            ) from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=30, min=30, max=180),
        retry=retry_if_exception_type(RateLimitError),
        reraise=True,
    )
    def analyze(
        self,
        video_path: Path,
        transcript: dict[str, Any],
    ) -> AnalysisResult:
        """Analyze using Claude transcript-only mode.

        Args:
            video_path: Ignored — Claude API does not accept video files.
            transcript: Transcript data from transcribe stage.

        Returns:
            AnalysisResult with structured output from Claude.

        Raises:
            ProviderError: If the API key is missing or a non-retryable API
                error occurs.
            RateLimitError: On HTTP 429 responses (retried automatically).
            QuotaExceededError: If API quota is exhausted.
            ProviderParseError: If the tool_use response violates the schema
                contract or cannot be validated as an AnalysisResult.
        """
        if not self.is_available():
            raise ProviderError(
                "Claude API key not configured",
                details={"provider": self.name, "env_var": "ANTHROPIC_API_KEY"},
            )

        trend_context = transcript.get("trend_context")
        prompt = self._build_prompt(
            transcript,
            trend_context=trend_context if isinstance(trend_context, dict) else None,
        )

        logger.info("claude_analyzing", model=self.model)
        logger.warning(
            "claude_transcript_only_mode",
            model=self.model,
            ignored_video_path=str(video_path),
        )

        client = self._get_client()
        tool_def: dict[str, Any] = {
            "name": _ANALYSIS_TOOL_NAME,
            "description": (
                "Provide structured podcast analysis including content cuts, viral clips, "
                "thumbnail frames, marketing copy, and episode metadata."
            ),
            "input_schema": _ANALYSIS_INPUT_SCHEMA,
        }

        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=(
                    "You are a professional podcast editor and marketing strategist. "
                    "Analyze transcript content and call the provide_analysis tool exactly once "
                    "with your complete structured analysis. Do not emit free-form text."
                ),
                messages=[{"role": "user", "content": prompt}],
                tools=[tool_def],
                tool_choice={"type": "tool", "name": _ANALYSIS_TOOL_NAME},
            )
        except Exception as exc:
            raise self._classify_api_error(exc) from exc

        analysis_data = self._extract_tool_input(message)
        return self._validate_analysis(analysis_data)

    def _extract_tool_input(self, message: Any) -> dict[str, Any]:
        """Extract the tool_use input dict from a Claude messages response.

        Args:
            message: The Message object returned by client.messages.create.

        Returns:
            The ``input`` dict from the tool_use content block.

        Raises:
            ProviderParseError: If no tool_use block is present or the input
                is not a dict (schema contract violation).
        """
        content = getattr(message, "content", None)
        if not isinstance(content, list):
            raise ProviderParseError(
                "Claude response has no content list",
                details={"provider": self.name, "model": self.model},
            )

        for block in content:
            block_type = getattr(block, "type", None)
            if block_type == "tool_use":
                tool_input = getattr(block, "input", None)
                if not isinstance(tool_input, dict):
                    raise ProviderParseError(
                        "Claude tool_use block has non-dict input — schema contract violated",
                        details={
                            "provider": self.name,
                            "model": self.model,
                            "input_type": type(tool_input).__name__,
                        },
                    )
                return dict(tool_input)

        # Fallback: check for text block with embedded JSON (defensive path)
        for block in content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", "") or ""
                if text.strip():
                    return self._parse_json_fallback(text)

        raise ProviderParseError(
            "Claude response contains no tool_use block",
            details={
                "provider": self.name,
                "model": self.model,
                "stop_reason": getattr(message, "stop_reason", "unknown"),
            },
        )

    def _parse_json_fallback(self, text: str) -> dict[str, Any]:
        """Parse raw JSON from a text block as a defensive fallback.

        This path should not be reached when tool_choice forces tool_use,
        but guards against edge-case model behaviour.

        Raises:
            ProviderParseError: If text is not valid JSON or not a dict.
        """
        import re

        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        json_str = json_match.group(1).strip() if json_match else text.strip()

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as error:
            raise ProviderParseError(
                "Claude returned invalid JSON in text block",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "json_error": str(error),
                    "response_excerpt": text[:200],
                },
            ) from error

        if not isinstance(parsed, dict):
            raise ProviderParseError(
                "Claude text-block JSON must be an object",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "payload_type": type(parsed).__name__,
                },
            )
        return dict(parsed)

    def _validate_analysis(self, data: dict[str, Any]) -> AnalysisResult:
        """Validate analysis data dict against AnalysisResult schema.

        Raises:
            ProviderParseError: If Pydantic validation fails.
        """
        try:
            return AnalysisResult.model_validate(data)
        except ValidationError as error:
            raise ProviderParseError(
                "Claude returned an invalid analysis schema",
                details={
                    "provider": self.name,
                    "model": self.model,
                    "validation_error": str(error),
                },
            ) from error

    def _classify_api_error(self, exc: Exception) -> ProviderError:
        """Classify raw SDK/network exceptions into typed provider errors.

        Returns:
            An appropriate subclass of ProviderError.
        """
        exc_type = type(exc).__name__
        exc_module = type(exc).__module__ or ""

        # Anthropic rate limit error
        if "RateLimitError" in exc_type or (
            "anthropic" in exc_module and "rate_limit" in str(exc).lower()
        ):
            retry_after = self._extract_retry_after(exc)
            return RateLimitError(
                "Claude rate limit exceeded",
                retry_after=retry_after,
                details={
                    "provider": self.name,
                    "model": self.model,
                    "error_type": exc_type,
                },
            )

        # Quota / billing error
        if "PermissionDeniedError" in exc_type or (
            "anthropic" in exc_module
            and any(kw in str(exc).lower() for kw in ("quota", "billing", "credit"))
        ):
            return QuotaExceededError(
                f"Claude API quota/billing error: {exc}",
            )

        # Generic provider error
        return ProviderError(
            f"Claude analysis failed: {exc}",
            details={
                "provider": self.name,
                "model": self.model,
                "error_type": exc_type,
            },
        )

    @staticmethod
    def _extract_retry_after(exc: Exception) -> int | None:
        """Attempt to extract a Retry-After header value from the exception."""
        # Anthropic SDK attaches response headers via .response attribute
        response = getattr(exc, "response", None)
        if response is not None:
            headers = getattr(response, "headers", {}) or {}
            raw = headers.get("retry-after") or headers.get("Retry-After")
            if raw is not None:
                try:
                    return int(raw)
                except (ValueError, TypeError):
                    pass
        return None
