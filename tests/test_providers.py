"""Provider runtime behavior tests for parse, retry, fallback, and caching."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from tenacity import stop_after_attempt, wait_none

from podcast_pipeline.config import Config
from podcast_pipeline.models.analysis import AnalysisResult
from podcast_pipeline.models.job import Job
from podcast_pipeline.providers.base import (
    BaseProvider,
    ProviderError,
    ProviderParseError,
    RateLimitError,
)
from podcast_pipeline.providers.claude_provider import (
    _ANALYSIS_TOOL_NAME,
    SUPPORTED_CLAUDE_MODELS,
    ClaudeProvider,
)
from podcast_pipeline.providers.gemini import GeminiProvider
from podcast_pipeline.providers.kimi import KIMI_API_URL, KimiProvider
from podcast_pipeline.stages.analyze import AnalyzeStage

REQUIRED_MARKETING_PLATFORMS = (
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
)


def _valid_analysis_payload() -> dict[str, Any]:
    """Return minimal valid analysis payload."""
    return {
        "content_cuts": [],
        "viral_clips": [],
        "thumbnail_frames": [],
        "metadata": {
            "summary": "Valid provider response",
            "topics": ["podcast"],
        },
    }


def _configure_fast_retry(monkeypatch: pytest.MonkeyPatch, provider: Any, attempts: int) -> None:
    """Force immediate retries in provider tests."""
    monkeypatch.setattr(provider.analyze.retry, "wait", wait_none())
    monkeypatch.setattr(provider.analyze.retry, "stop", stop_after_attempt(attempts))


class _StatusCodeError(Exception):
    """Exception with structured status code for retry classification tests."""

    def __init__(self, status_code: int):
        super().__init__(f"status={status_code}")
        self.status_code = status_code


class _FakeGeminiModels:
    """Fake Gemini model endpoint."""

    def __init__(self, events: list[Any]):
        self._events = list(events)
        self.call_count = 0

    def generate_content(self, **_: Any) -> Any:
        """Return queued responses or raise queued exceptions."""
        self.call_count += 1
        event = self._events.pop(0)
        if isinstance(event, Exception):
            raise event
        return SimpleNamespace(text=event)


class _FakeGeminiFiles:
    """Fake Gemini files endpoint with upload/get tracking."""

    def __init__(self, *, upload_error: Exception | None = None):
        self.upload_error = upload_error
        self.upload_calls = 0
        self.get_calls = 0
        self._uploaded: dict[str, Any] = {}

    def upload(self, file: Path) -> Any:
        """Upload and return fake ACTIVE file."""
        self.upload_calls += 1
        if self.upload_error is not None:
            raise self.upload_error

        upload_name = f"upload-{self.upload_calls}-{file.name}"
        uploaded = SimpleNamespace(
            name=upload_name,
            state=SimpleNamespace(name="ACTIVE"),
        )
        self._uploaded[upload_name] = uploaded
        return uploaded

    def get(self, name: str) -> Any:
        """Return uploaded file by name."""
        self.get_calls += 1
        if name not in self._uploaded:
            raise RuntimeError(f"missing upload {name}")
        return self._uploaded[name]


class _FakeGeminiClient:
    """Fake Gemini client composed from fake files/models."""

    def __init__(self, files: _FakeGeminiFiles, models: _FakeGeminiModels):
        self.files = files
        self.models = models


class _FakeKimiResponse:
    """Fake Kimi HTTP response wrapper."""

    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        """Raise HTTP status errors like httpx.Response."""
        if self.status_code < 400:
            return
        request = httpx.Request("POST", KIMI_API_URL)
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("request failed", request=request, response=response)

    def json(self) -> dict[str, Any]:
        """Return fake JSON payload."""
        return self._payload


class _PromptTestProvider(BaseProvider):
    """Concrete provider for prompt-contract tests."""

    name = "prompt-test"
    model = "prompt-model"
    supports_video = False

    def analyze(self, video_path: Path, transcript: dict[str, Any]) -> AnalysisResult:
        return AnalysisResult.model_validate(_valid_analysis_payload())

    def is_available(self) -> bool:
        return True


def test_provider_prompt_schema_covers_full_marketing_platform_matrix() -> None:
    """Prompt JSON schema should include every required marketing platform key."""
    provider = _PromptTestProvider()
    prompt = provider._build_prompt({"text": "A transcript excerpt"})
    for platform_key in REQUIRED_MARKETING_PLATFORMS:
        assert f'"{platform_key}": {{' in prompt


def test_provider_prompt_includes_viral_professional_quality_directives() -> None:
    """Prompt should enforce viral-impact copy without losing professional standards."""
    provider = _PromptTestProvider()
    prompt = provider._build_prompt({"text": "A transcript excerpt"})

    assert "high-impact and viral-ready without spammy clickbait" in prompt
    assert "Keep tone professional, credible, and audience-appropriate." in prompt
    assert "Tailor language to each platform format" in prompt


def test_provider_prompt_includes_trend_context_when_available() -> None:
    """Prompt should embed optional trend context payload for copy generation."""
    provider = _PromptTestProvider()
    prompt = provider._build_prompt(
        {"text": "A transcript excerpt"},
        trend_context={
            "keywords": ["growth loop", "creator workflow"],
            "trending_hooks": ["contrarian retention take"],
            "competitive_angle": "Medium competition; differentiation via workflow framing.",
            "momentum_signals": ["avg_velocity_per_hour=12.50"],
        },
    )

    assert '"keywords": ["growth loop", "creator workflow"]' in prompt
    assert '"trending_hooks": ["contrarian retention take"]' in prompt
    assert (
        '"competitive_angle": "Medium competition; differentiation via workflow framing."' in prompt
    )
    assert '"momentum_signals": ["avg_velocity_per_hour=12.50"]' in prompt


def test_provider_thumbnail_schema_includes_virality_metadata_fields() -> None:
    """Provider prompt should request virality metadata for each thumbnail candidate."""
    provider = _PromptTestProvider()
    prompt = provider._build_prompt({"text": "A transcript excerpt"})

    assert '"virality_score": 0.0' in prompt
    assert '"viral_style": "reaction/story/mystery/etc"' in prompt
    assert '"virality_score_source": "provider/heuristic"' in prompt
    assert '"recommendation_signal": "Specific recommendation reason"' in prompt


def test_provider_thumbnail_contract_requires_recommendation_signal() -> None:
    """Provider prompt should require at least one strong thumbnail recommendation signal."""
    provider = _PromptTestProvider()
    prompt = provider._build_prompt({"text": "A transcript excerpt"})

    assert (
        "When thumbnail candidates are present, include at least one strong recommendation_signal"
        in prompt
    )


def test_provider_parse_accepts_thumbnail_virality_metadata_fields() -> None:
    """Provider parse path should preserve thumbnail virality metadata fields."""
    payload = _valid_analysis_payload()
    payload["thumbnail_frames"] = [
        {
            "timestamp": "00:12",
            "timestamp_seconds": 12.0,
            "visual_description": "Host leaning in",
            "suggested_text_overlay": "Don't miss this",
            "emotion": "surprise",
            "virality_score": 9.0,
            "viral_style": "reaction_closeup",
            "virality_score_source": "provider",
            "recommendation_signal": "high emotional expression",
        }
    ]

    result = AnalysisResult.model_validate(payload)
    thumbnail = result.thumbnail_frames[0]

    assert thumbnail.virality_score == pytest.approx(9.0)
    assert thumbnail.viral_style == "reaction_closeup"
    assert thumbnail.virality_score_source == "provider"
    assert thumbnail.recommendation_signal == "high emotional expression"


def test_gemini_parse_failure_raises_provider_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini malformed JSON must fail explicitly."""
    provider = GeminiProvider(api_key="test-key")
    files = _FakeGeminiFiles()
    models = _FakeGeminiModels(events=["not-json"])
    fake_client = _FakeGeminiClient(files=files, models=models)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    with pytest.raises(ProviderParseError, match="invalid JSON"):
        provider.analyze(Path("jobs/job-1/intermediate/proxy.mp4"), {"text": "test transcript"})

    assert models.call_count == 1


def test_kimi_parse_failure_raises_provider_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kimi malformed JSON must fail explicitly."""
    provider = KimiProvider(api_key="test-key")
    payload = {"choices": [{"message": {"content": "invalid-json"}}]}
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _FakeKimiResponse(200, payload))

    with pytest.raises(ProviderParseError, match="invalid JSON"):
        provider.analyze(Path("proxy.mp4"), {"text": "test transcript"})


def test_gemini_retry_retries_on_rate_limit_status_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini retries once and succeeds when first response is structured 429."""
    provider = GeminiProvider(api_key="test-key")
    _configure_fast_retry(monkeypatch, provider, attempts=2)

    files = _FakeGeminiFiles()
    models = _FakeGeminiModels(
        events=[
            _StatusCodeError(status_code=429),
            json.dumps(_valid_analysis_payload()),
        ]
    )
    fake_client = _FakeGeminiClient(files=files, models=models)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    result = provider.analyze(Path("jobs/job-1/intermediate/proxy.mp4"), {"text": "retry test"})

    assert result.metadata.summary == "Valid provider response"
    assert models.call_count == 2
    assert files.upload_calls == 1
    assert files.get_calls >= 1


def test_gemini_rate_limit_error_preserves_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini structured 429 responses preserve retry-after metadata."""
    provider = GeminiProvider(api_key="test-key")
    _configure_fast_retry(monkeypatch, provider, attempts=1)

    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models")
    response = httpx.Response(429, headers={"retry-after": "17"}, request=request)
    rate_limit_error = httpx.HTTPStatusError(
        "rate limited",
        request=request,
        response=response,
    )

    files = _FakeGeminiFiles()
    models = _FakeGeminiModels(events=[rate_limit_error])
    fake_client = _FakeGeminiClient(files=files, models=models)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    with pytest.raises(RateLimitError) as exc_info:
        provider.analyze(Path("jobs/job-1/intermediate/proxy.mp4"), {"text": "retry-after test"})

    assert exc_info.value.retry_after == 17
    assert models.call_count == 1


def test_gemini_upload_cache_reuses_file_id_between_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini should reuse cached upload IDs for repeated analysis on the same proxy."""
    provider = GeminiProvider(api_key="test-key")
    files = _FakeGeminiFiles()
    models = _FakeGeminiModels(
        events=[
            json.dumps(_valid_analysis_payload()),
            json.dumps(_valid_analysis_payload()),
        ]
    )
    fake_client = _FakeGeminiClient(files=files, models=models)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    proxy_path = Path("jobs/job-42/intermediate/proxy.mp4")
    provider.analyze(proxy_path, {"text": "first"})
    provider.analyze(proxy_path, {"text": "second"})

    cache_key = provider._upload_cache_key(proxy_path)
    assert cache_key in provider._upload_cache
    assert files.upload_calls == 1
    assert files.get_calls >= 1


def test_gemini_upload_cache_stale_entry_reuploads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale Gemini cache entries should be evicted and replaced with a fresh upload."""
    provider = GeminiProvider(api_key="test-key")
    files = _FakeGeminiFiles()
    models = _FakeGeminiModels(
        events=[
            json.dumps(_valid_analysis_payload()),
            json.dumps(_valid_analysis_payload()),
        ]
    )
    fake_client = _FakeGeminiClient(files=files, models=models)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    proxy_path = Path("jobs/job-stale/intermediate/proxy.mp4")
    cache_key = provider._upload_cache_key(proxy_path)

    provider.analyze(proxy_path, {"text": "first pass"})
    provider._upload_cache[cache_key] = "stale-upload-id"
    provider.analyze(proxy_path, {"text": "second pass"})

    assert files.upload_calls == 2
    assert provider._upload_cache[cache_key] != "stale-upload-id"


def test_gemini_upload_cache_upload_failure_does_not_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed uploads should raise ProviderError and avoid stale cache entries."""
    provider = GeminiProvider(api_key="test-key")
    files = _FakeGeminiFiles(upload_error=RuntimeError("upload exploded"))
    models = _FakeGeminiModels(events=[json.dumps(_valid_analysis_payload())])
    fake_client = _FakeGeminiClient(files=files, models=models)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    proxy_path = Path("jobs/job-upload/intermediate/proxy.mp4")
    with pytest.raises(ProviderError, match="video upload failed"):
        provider.analyze(proxy_path, {"text": "upload failure"})

    assert provider._upload_cache_key(proxy_path) not in provider._upload_cache


def test_gemini_upload_without_identifier_raises_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini uploads must include a valid file identifier to seed cache reuse."""
    provider = GeminiProvider(api_key="test-key")

    class _InvalidUploadFiles(_FakeGeminiFiles):
        def upload(self, file: Path) -> Any:
            self.upload_calls += 1
            return SimpleNamespace(name=None, state=SimpleNamespace(name="ACTIVE"))

    files = _InvalidUploadFiles()
    models = _FakeGeminiModels(events=[json.dumps(_valid_analysis_payload())])
    fake_client = _FakeGeminiClient(files=files, models=models)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    proxy_path = Path("jobs/job-invalid-upload/intermediate/proxy.mp4")
    with pytest.raises(ProviderError, match="valid file identifier"):
        provider.analyze(proxy_path, {"text": "invalid upload id"})

    assert provider._upload_cache_key(proxy_path) not in provider._upload_cache
    assert models.call_count == 0


def test_kimi_rate_limit_raises_rate_limit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kimi 429 responses should raise RateLimitError for tenacity retry handling."""
    provider = KimiProvider(api_key="test-key")
    _configure_fast_retry(monkeypatch, provider, attempts=1)

    call_count = {"count": 0}

    def _fake_post(*args: Any, **kwargs: Any) -> _FakeKimiResponse:
        call_count["count"] += 1
        return _FakeKimiResponse(429, payload={})

    monkeypatch.setattr(httpx, "post", _fake_post)

    with pytest.raises(RateLimitError, match="rate limit"):
        provider.analyze(Path("proxy.mp4"), {"text": "test"})

    assert call_count["count"] == 1


def test_kimi_invalid_analysis_schema_raises_provider_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kimi JSON payloads with invalid analysis shape must fail explicitly."""
    provider = KimiProvider(api_key="test-key")
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "content_cuts": [
                                {
                                    "reason": "missing timestamps",
                                }
                            ]
                        }
                    )
                }
            }
        ]
    }
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _FakeKimiResponse(200, payload))

    with pytest.raises(ProviderParseError, match="invalid analysis schema"):
        provider.analyze(Path("proxy.mp4"), {"text": "test transcript"})


def test_analyze_fallback_sets_degraded_mode_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Analyze stage should flag degraded mode when transcript-only fallback provider is used."""

    class _FailingProvider:
        name = "gemini"
        model = "gemini-2.5-flash"
        supports_video = True

        def is_available(self) -> bool:
            return True

        def analyze(self, video_path: Path, transcript: dict[str, Any]) -> AnalysisResult:
            raise ProviderError("primary provider failed")

    class _TranscriptFallbackProvider:
        name = "kimi"
        model = "kimi-k2.5"
        supports_video = False

        def is_available(self) -> bool:
            return True

        def analyze(self, video_path: Path, transcript: dict[str, Any]) -> AnalysisResult:
            return AnalysisResult.model_validate(_valid_analysis_payload())

    config = Config()
    stage = AnalyzeStage(config)
    stage.providers = [_FailingProvider(), _TranscriptFallbackProvider()]  # type: ignore[assignment]
    monkeypatch.setattr(stage, "_run_research", lambda *args, **kwargs: None)
    monkeypatch.setattr(stage, "_run_viral_signals", lambda *args, **kwargs: None)

    job_dir = tmp_path / "job-1"
    (job_dir / "analysis").mkdir(parents=True, exist_ok=True)
    (job_dir / "analysis" / "transcript.json").write_text(json.dumps({"text": "hello"}))
    (job_dir / "intermediate").mkdir(parents=True, exist_ok=True)
    (job_dir / "intermediate" / "proxy.mp4").write_bytes(b"proxy")

    job = Job(job_id="job-1", input_file=str(job_dir / "input.mp4"))
    result = stage.run(job, job_dir)

    assert result.success is True
    assert result.data["provider"] == "kimi"
    assert result.data["degraded_mode"]["enabled"] is True
    assert result.data["degraded_mode"]["reason"] == "fallback_provider_transcript_only"

    analysis_payload = json.loads((job_dir / "analysis" / "analysis.json").read_text())
    degraded_mode = analysis_payload["metadata"]["degraded_mode"]
    assert degraded_mode["enabled"] is True
    assert degraded_mode["provider"] == "kimi"
    assert degraded_mode["reason"] == "fallback_provider_transcript_only"


def test_analyze_stage_injects_trend_context_when_artifacts_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Analyze stage should pass trend context from existing artifacts into provider prompt path."""

    class _CapturingProvider:
        name = "gemini"
        model = "gemini-2.5-flash"
        supports_video = True

        def __init__(self) -> None:
            self.captured_trend_context: dict[str, Any] | None = None

        def is_available(self) -> bool:
            return True

        def analyze(self, video_path: Path, transcript: dict[str, Any]) -> AnalysisResult:
            trend_context = transcript.get("trend_context")
            self.captured_trend_context = trend_context if isinstance(trend_context, dict) else None
            return AnalysisResult.model_validate(_valid_analysis_payload())

    config = Config()
    stage = AnalyzeStage(config)
    provider = _CapturingProvider()
    stage.providers = [provider]  # type: ignore[assignment]
    monkeypatch.setattr(stage, "_run_research", lambda *args, **kwargs: None)
    monkeypatch.setattr(stage, "_run_viral_signals", lambda *args, **kwargs: None)

    job_dir = tmp_path / "job-2"
    (job_dir / "analysis").mkdir(parents=True, exist_ok=True)
    (job_dir / "analysis" / "transcript.json").write_text(json.dumps({"text": "hello"}))
    (job_dir / "intermediate").mkdir(parents=True, exist_ok=True)
    (job_dir / "intermediate" / "proxy.mp4").write_bytes(b"proxy")

    (job_dir / "analysis" / "research.json").write_text(
        json.dumps(
            {
                "suggested_keywords": ["growth loop", "creator workflow"],
                "insights": {
                    "recommendation": "Lean into creator-retention differentiation.",
                    "engagement_benchmarks": {"avg_velocity_per_hour": 42.5},
                    "query_derivation": {
                        "query": "creator growth podcast",
                        "related_topics": ["retention hook"],
                    },
                },
            }
        )
    )
    (job_dir / "analysis" / "viral_signals.json").write_text(
        json.dumps(
            {
                "clip_scores": [
                    {
                        "rank": 1,
                        "combined_score": 9.1,
                        "reasons": ["Strong controversy framing"],
                        "clip": {"suggested_hook": "The retention hack no one uses"},
                    },
                    {
                        "rank": 2,
                        "combined_score": 8.4,
                        "reasons": ["High novelty framing"],
                        "clip": {"suggested_hook": "Why most creators plateau"},
                    },
                ]
            }
        )
    )

    job = Job(job_id="job-2", input_file=str(job_dir / "input.mp4"))
    result = stage.run(job, job_dir)

    assert result.success is True
    assert provider.captured_trend_context is not None
    trend_context = provider.captured_trend_context
    assert "growth loop" in trend_context["keywords"]
    assert "creator workflow" in trend_context["keywords"]
    assert trend_context["competitive_angle"] == "Lean into creator-retention differentiation."
    assert "The retention hack no one uses" in trend_context["trending_hooks"]
    assert "Strong controversy framing" in trend_context["trending_hooks"]
    assert "avg_velocity_per_hour=42.50" in trend_context["momentum_signals"]
    assert "clip_rank_1_combined_score=9.10" in trend_context["momentum_signals"]


# ---------------------------------------------------------------------------
# Claude provider helpers
# ---------------------------------------------------------------------------


def _make_fake_tool_use_message(payload: dict[str, Any]) -> Any:
    """Build a fake Anthropic Message with a tool_use content block."""
    tool_block = SimpleNamespace(
        type="tool_use",
        id="tu_fake123",
        name=_ANALYSIS_TOOL_NAME,
        input=payload,
    )
    return SimpleNamespace(
        content=[tool_block],
        stop_reason="tool_use",
        model="claude-sonnet-4-6",
    )


def _make_fake_text_message(text: str) -> Any:
    """Build a fake Anthropic Message with only a text content block."""
    text_block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(
        content=[text_block],
        stop_reason="end_turn",
        model="claude-sonnet-4-6",
    )


def _make_fake_empty_message() -> Any:
    """Build a fake Anthropic Message with no content blocks."""
    return SimpleNamespace(
        content=[],
        stop_reason="end_turn",
        model="claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# ClaudeProvider — availability
# ---------------------------------------------------------------------------


def test_claude_provider_is_available_with_key() -> None:
    """ClaudeProvider.is_available returns True when API key is present."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    assert provider.is_available() is True


def test_claude_provider_is_not_available_without_key() -> None:
    """ClaudeProvider.is_available returns False when API key is absent."""
    provider = ClaudeProvider(api_key=None)
    assert provider.is_available() is False


def test_claude_provider_is_not_available_with_empty_string() -> None:
    """ClaudeProvider.is_available returns False for empty-string key."""
    provider = ClaudeProvider(api_key="")
    assert provider.is_available() is False


# ---------------------------------------------------------------------------
# ClaudeProvider — protocol conformance
# ---------------------------------------------------------------------------


def test_claude_provider_name_is_claude() -> None:
    """ClaudeProvider.name is 'claude'."""
    provider = ClaudeProvider(api_key="test")
    assert provider.name == "claude"


def test_claude_provider_supports_video_is_false() -> None:
    """ClaudeProvider.supports_video is False (transcript-only)."""
    provider = ClaudeProvider(api_key="test")
    assert provider.supports_video is False


def test_claude_provider_default_model_is_sonnet() -> None:
    """ClaudeProvider default model is claude-sonnet-4-6."""
    provider = ClaudeProvider(api_key="test")
    assert provider.model == "claude-sonnet-4-6"


def test_claude_provider_model_override() -> None:
    """ClaudeProvider accepts model override at construction."""
    provider = ClaudeProvider(api_key="test", model="claude-haiku-4-5")
    assert provider.model == "claude-haiku-4-5"


def test_claude_supported_models_contains_three_models() -> None:
    """SUPPORTED_CLAUDE_MODELS contains the three expected models."""
    assert "claude-sonnet-4-6" in SUPPORTED_CLAUDE_MODELS
    assert "claude-haiku-4-5" in SUPPORTED_CLAUDE_MODELS
    assert "claude-opus-4-6" in SUPPORTED_CLAUDE_MODELS
    assert len(SUPPORTED_CLAUDE_MODELS) == 3


# ---------------------------------------------------------------------------
# ClaudeProvider — structured output contract (parse paths)
# ---------------------------------------------------------------------------


def test_claude_analyze_returns_valid_result_from_tool_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ClaudeProvider.analyze returns AnalysisResult from valid tool_use response."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    payload = _valid_analysis_payload()
    fake_message = _make_fake_tool_use_message(payload)

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kwargs: fake_message,
        )
    )
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    result = provider.analyze(Path("proxy.mp4"), {"text": "transcript"})
    assert isinstance(result, AnalysisResult)
    assert result.metadata.summary == "Valid provider response"


def test_claude_analyze_no_key_raises_provider_error() -> None:
    """analyze raises ProviderError immediately when no API key is present."""
    provider = ClaudeProvider(api_key=None)
    with pytest.raises(ProviderError, match="API key not configured"):
        provider.analyze(Path("proxy.mp4"), {"text": "transcript"})


def test_claude_parse_no_tool_use_block_raises_provider_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No tool_use block in response must raise ProviderParseError."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    fake_message = _make_fake_empty_message()

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: fake_message))
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    with pytest.raises(ProviderParseError, match="no tool_use block"):
        provider.analyze(Path("proxy.mp4"), {"text": "transcript"})


def test_claude_parse_invalid_schema_raises_provider_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tool_use input that fails AnalysisResult validation raises ProviderParseError."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    # Malformed payload: content_cuts items missing required fields
    bad_payload: dict[str, Any] = {
        "content_cuts": [{"reason": "missing timestamps"}],
        "viral_clips": [],
        "thumbnail_frames": [],
        "metadata": {"summary": "s", "topics": []},
    }
    fake_message = _make_fake_tool_use_message(bad_payload)

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: fake_message))
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    with pytest.raises(ProviderParseError, match="invalid analysis schema"):
        provider.analyze(Path("proxy.mp4"), {"text": "transcript"})


def test_claude_parse_non_dict_tool_input_raises_provider_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tool_use block with non-dict input raises ProviderParseError."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    bad_block = SimpleNamespace(
        type="tool_use", id="x", name=_ANALYSIS_TOOL_NAME, input="not-a-dict"
    )
    fake_message = SimpleNamespace(content=[bad_block], stop_reason="tool_use")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: fake_message))
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    with pytest.raises(ProviderParseError, match="non-dict input"):
        provider.analyze(Path("proxy.mp4"), {"text": "transcript"})


def test_claude_parse_text_block_json_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text-block JSON fallback path produces valid AnalysisResult."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    payload = _valid_analysis_payload()
    fake_message = _make_fake_text_message(json.dumps(payload))

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: fake_message))
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    result = provider.analyze(Path("proxy.mp4"), {"text": "transcript"})
    assert isinstance(result, AnalysisResult)


def test_claude_parse_text_block_invalid_json_raises_provider_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text-block fallback with invalid JSON raises ProviderParseError."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    fake_message = _make_fake_text_message("not valid JSON {{{")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: fake_message))
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    with pytest.raises(ProviderParseError, match="invalid JSON"):
        provider.analyze(Path("proxy.mp4"), {"text": "transcript"})


# ---------------------------------------------------------------------------
# ClaudeProvider — retry and error classification
# ---------------------------------------------------------------------------


def test_claude_rate_limit_error_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RateLimitError from Claude is retryable (retryable=True)."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    monkeypatch.setattr(provider.analyze.retry, "wait", wait_none())  # type: ignore[attr-defined]
    monkeypatch.setattr(provider.analyze.retry, "stop", stop_after_attempt(1))  # type: ignore[attr-defined]

    class _FakeRateLimitError(Exception):
        """Simulates anthropic.RateLimitError."""

        pass

    _FakeRateLimitError.__name__ = "RateLimitError"
    _FakeRateLimitError.__qualname__ = "RateLimitError"

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(_FakeRateLimitError("rate limit hit"))
        )
    )
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    with pytest.raises(RateLimitError) as exc_info:
        provider.analyze(Path("proxy.mp4"), {"text": "transcript"})

    assert exc_info.value.retryable is True


def test_claude_generic_api_error_wraps_to_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-rate-limit API errors are wrapped as ProviderError."""
    provider = ClaudeProvider(api_key="sk-ant-test")

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("network down"))
        )
    )
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    with pytest.raises(ProviderError):
        provider.analyze(Path("proxy.mp4"), {"text": "transcript"})


def test_claude_analyze_passes_trend_context_to_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude analyze injects trend_context from transcript into the prompt."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    captured: dict[str, Any] = {}

    def _fake_create(**kwargs: Any) -> Any:
        captured["messages"] = kwargs.get("messages", [])
        return _make_fake_tool_use_message(_valid_analysis_payload())

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=_fake_create))
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    trend_context = {
        "keywords": ["ai tools"],
        "trending_hooks": ["Best AI hook"],
        "competitive_angle": "Differentiate on speed.",
        "momentum_signals": ["avg_velocity=12.0"],
    }
    provider.analyze(Path("proxy.mp4"), {"text": "test", "trend_context": trend_context})

    user_content = captured["messages"][0]["content"]
    assert "ai tools" in user_content
    assert "Best AI hook" in user_content
