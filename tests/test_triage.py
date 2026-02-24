"""Tests for the FillerTriageResult model (Phase 8)."""

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from podcast_pipeline.models.triage import FillerTriageResult


class TestFillerTriageResultRoundTrip:
    """Round-trip serialization tests for FillerTriageResult."""

    def test_filler_triage_result_round_trip(self) -> None:
        """Create FillerTriageResult with all fields, serialize to JSON, deserialize back."""
        original = FillerTriageResult(
            filler_index=3,
            word="like",
            category="hedge",
            safe_to_remove=True,
            reason="Purely a verbal tick with no semantic function.",
            llm_model="gpt-4o-mini",
            triaged_at="2026-02-21T08:00:00+00:00",
        )

        serialized = original.model_dump_json()
        restored = FillerTriageResult.model_validate_json(serialized)

        assert restored.filler_index == original.filler_index
        assert restored.word == original.word
        assert restored.category == original.category
        assert restored.safe_to_remove == original.safe_to_remove
        assert restored.reason == original.reason
        assert restored.llm_model == original.llm_model
        assert restored.triaged_at == original.triaged_at

    def test_filler_triage_result_round_trip_via_dict(self) -> None:
        """Serialization round-trip via model_dump/model_validate."""
        original = FillerTriageResult(
            filler_index=0,
            word="basically",
            category="hedge",
            safe_to_remove=False,
            reason="Used for rhetorical emphasis.",
            llm_model="gpt-4o-mini",
        )

        dumped = original.model_dump()
        restored = FillerTriageResult.model_validate(dumped)

        assert restored.filler_index == 0
        assert restored.word == "basically"
        assert restored.safe_to_remove is False
        assert restored.reason == "Used for rhetorical emphasis."

    def test_filler_triage_result_json_contains_all_fields(self) -> None:
        """Serialized JSON has all expected keys."""
        result = FillerTriageResult(
            filler_index=1,
            word="you know",
            category="hedge",
            safe_to_remove=True,
            reason="No semantic load in context.",
            llm_model="gpt-4o-mini",
        )

        payload = json.loads(result.model_dump_json())
        expected_keys = {
            "filler_index",
            "word",
            "category",
            "safe_to_remove",
            "reason",
            "llm_model",
            "triaged_at",
        }
        assert expected_keys.issubset(payload.keys())


class TestFillerTriageResultDefaults:
    """Default value tests for FillerTriageResult."""

    def test_filler_triage_result_defaults(self) -> None:
        """Minimal construction uses safe defaults."""
        result = FillerTriageResult(filler_index=0, word="so", category="hedge")

        assert result.safe_to_remove is False
        assert result.reason == ""
        assert result.llm_model == ""
        assert isinstance(result.triaged_at, str)
        assert len(result.triaged_at) > 0

    def test_filler_triage_result_triaged_at_is_iso_string(self) -> None:
        """triaged_at is a valid ISO-format datetime string."""
        result = FillerTriageResult(filler_index=0, word="actually", category="hedge")

        parsed = datetime.fromisoformat(result.triaged_at)
        assert parsed.year >= 2024

    def test_filler_triage_result_safe_to_remove_false_by_default(self) -> None:
        """safe_to_remove defaults to False — conservative sentinel."""
        result = FillerTriageResult(filler_index=5, word="like", category="hedge")
        assert result.safe_to_remove is False

    def test_filler_triage_result_filler_index_ge_zero(self) -> None:
        """filler_index must be >= 0."""
        with pytest.raises(ValidationError):
            FillerTriageResult(filler_index=-1, word="like", category="hedge")

    def test_filler_triage_result_safe_flag_true(self) -> None:
        """Create with safe_to_remove=True — assert serialized value is True."""
        result = FillerTriageResult(
            filler_index=2,
            word="like",
            category="hedge",
            safe_to_remove=True,
        )
        assert result.safe_to_remove is True

        payload = json.loads(result.model_dump_json())
        assert payload["safe_to_remove"] is True


class TestFillerConfigTriageModelRegression:
    """Regression guard: triage model default must not drift to OpenAI or reasoning models."""

    def test_filler_config_triage_model_not_openai(self) -> None:
        """Triage model default must NOT be an OpenAI or reasoning model.

        Spec requires gemini-2.5-flash-lite or claude-haiku-4-5 — lightweight, non-reasoning,
        non-OpenAI models. This test prevents silent drift back to gpt-4o-mini or similar.
        """
        from podcast_pipeline.config.settings import FillerConfig

        config = FillerConfig()
        # Must be gemini-2.5-flash-lite or claude-haiku-4-5 per spec
        assert config.llm_triage_model in ("gemini-2.5-flash-lite", "claude-haiku-4-5"), (
            f"Triage model must be a lightweight non-reasoning model, got '{config.llm_triage_model}'"
        )
        # Explicitly forbidden: reasoning/CoT models are too slow/expensive for triage
        forbidden = {
            "gpt-4o-mini",
            "gpt-4o",
            "o1",
            "o1-mini",
            "o3-mini",
            "gemini-3-pro",
            "gemini-3-pro-preview",
            "gemini-3-pro-image-preview",
            "claude-3.5-sonnet",
            "claude-opus-4-6",
        }
        assert config.llm_triage_model not in forbidden, (
            f"Triage model '{config.llm_triage_model}' is forbidden"
            " -- use non-reasoning lite models"
        )

    def test_filler_config_triage_model_starts_with_gemini_or_claude(self) -> None:
        """Default triage model must use Gemini or Claude (not OpenAI) as provider."""
        from podcast_pipeline.config.settings import FillerConfig

        config = FillerConfig()
        assert config.llm_triage_model.startswith(("gemini", "claude")), (
            f"Triage model '{config.llm_triage_model}' must start with 'gemini' or 'claude'"
            " — OpenAI models are not the primary provider and must not be the default"
        )
