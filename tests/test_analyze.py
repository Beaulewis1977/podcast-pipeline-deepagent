"""Tests for AnalyzeStage triage integration (Phase 8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from podcast_pipeline.config import Config
from podcast_pipeline.config.settings import FillerConfig
from podcast_pipeline.models.triage import FillerTriageResult
from podcast_pipeline.stages.analyze import AnalyzeStage


def _make_stage(
    *,
    enable_llm_triage: bool = True,
    gemini_key: str | None = "gemini-test-key",
    llm_triage_model: str = "gemini-3-flash-lite",
) -> AnalyzeStage:
    """Build an AnalyzeStage with a minimal config for triage testing."""
    config = Config()
    config.fillers = FillerConfig(
        enable_llm_triage=enable_llm_triage,
        llm_triage_model=llm_triage_model,
    )
    config.api_keys.gemini = gemini_key
    return AnalyzeStage(config)


def _write_filler_cuts(job_dir: Path, cuts: list[dict[str, Any]]) -> None:
    """Write a filler_cuts.json fixture under analysis/."""
    analysis_dir = job_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "filler_cuts.json").write_text(json.dumps(cuts))


_HEDGE_CUT_DEFAULTS: dict[str, Any] = {
    "word": "like",
    "protected": False,
    "context_before": "I think",
    "context_after": "it works",
    "pause_before_ms": 50.0,
    "pause_after_ms": 30.0,
}


def _hedge_cut(index: int, **overrides: Any) -> dict[str, Any]:
    """Build a minimal hedge filler cut dict. Accepts keyword overrides of defaults."""
    params = {**_HEDGE_CUT_DEFAULTS, **overrides}
    return {
        "start": float(index),
        "end": float(index) + 0.3,
        "confidence": 0.9,
        "category": "hedge",
        **params,
    }


def _disfluency_cut(index: int, word: str = "um") -> dict[str, Any]:
    """Build a minimal disfluency filler cut dict."""
    return {
        "start": float(index),
        "end": float(index) + 0.2,
        "word": word,
        "confidence": 0.95,
        "category": "disfluency",
        "pause_before_ms": 0.0,
        "pause_after_ms": 0.0,
        "context_before": "",
        "context_after": "",
        "protected": False,
    }


def _make_mock_gemini_response(text: str) -> MagicMock:
    """Build a fake google.genai generate_content response."""
    resp = MagicMock()
    resp.text = text
    return resp


class TestTriageFillerDisabledPath:
    """When enable_llm_triage=False, no LLM calls are made."""

    def test_triage_fillers_disabled_no_llm_call(self, tmp_path: Path) -> None:
        """Disabled flag skips LLM entirely; all results have safe_to_remove=False."""
        _write_filler_cuts(tmp_path, [_hedge_cut(0), _hedge_cut(1)])
        stage = _make_stage(enable_llm_triage=False)

        with patch("google.genai.Client") as mock_genai_cls:
            results = stage._triage_fillers(tmp_path)
            mock_genai_cls.assert_not_called()

        assert len(results) == 2
        for r in results:
            assert r.safe_to_remove is False
            assert "disabled" in r.reason.lower()

    def test_triage_fillers_disabled_returns_all_candidates(self, tmp_path: Path) -> None:
        """Disabled triage returns one result per hedge candidate."""
        _write_filler_cuts(tmp_path, [_hedge_cut(0), _hedge_cut(1), _hedge_cut(2)])
        stage = _make_stage(enable_llm_triage=False)

        results = stage._triage_fillers(tmp_path)
        assert len(results) == 3
        assert all(isinstance(r, FillerTriageResult) for r in results)


class TestTriageFillerFiltering:
    """Only hedge + unprotected fillers are triaged."""

    def test_triage_fillers_skips_disfluencies_and_protected(self, tmp_path: Path) -> None:
        """Disfluencies and protected hedges are excluded; unprotected hedge is included."""
        _write_filler_cuts(
            tmp_path,
            [
                _disfluency_cut(0, word="um"),
                _hedge_cut(1, word="you know", protected=True),
                _hedge_cut(2, word="like", protected=False),
            ],
        )
        stage = _make_stage(enable_llm_triage=False)

        results = stage._triage_fillers(tmp_path)

        assert len(results) == 1
        assert results[0].word == "like"
        assert results[0].filler_index == 2

    def test_triage_fillers_all_disfluencies_yields_no_results(self, tmp_path: Path) -> None:
        """All disfluencies → no candidates → empty result list."""
        _write_filler_cuts(tmp_path, [_disfluency_cut(0), _disfluency_cut(1)])
        stage = _make_stage(enable_llm_triage=True)

        results = stage._triage_fillers(tmp_path)
        assert results == []

    def test_triage_fillers_all_protected_yields_no_results(self, tmp_path: Path) -> None:
        """All protected hedges → no candidates → empty result list."""
        _write_filler_cuts(
            tmp_path,
            [_hedge_cut(0, protected=True), _hedge_cut(1, protected=True)],
        )
        stage = _make_stage(enable_llm_triage=True)

        results = stage._triage_fillers(tmp_path)
        assert results == []


class TestTriageFillerPromptFormat:
    """The prompt sent to LLM contains the required context elements."""

    def test_triage_fillers_prompt_contains_context(self, tmp_path: Path) -> None:
        """Prompt contains context_before, word in brackets, context_after, pause values."""
        cut = _hedge_cut(
            0,
            word="basically",
            context_before="I mean",
            context_after="it was fine",
            pause_before_ms=120.0,
            pause_after_ms=80.0,
        )
        _write_filler_cuts(tmp_path, [cut])
        stage = _make_stage(enable_llm_triage=True)

        captured_contents: list[str] = []

        def fake_generate_content(model: str, contents: str) -> MagicMock:
            captured_contents.append(contents)
            return _make_mock_gemini_response("SAFE\nreason: No semantic function.")

        mock_client = MagicMock()
        mock_client.models.generate_content = fake_generate_content

        with patch("google.genai.Client", return_value=mock_client):
            stage._triage_fillers(tmp_path)

        assert captured_contents, "Expected at least one contents string to be captured"
        prompt_text = captured_contents[0]

        assert "I mean" in prompt_text
        assert "[BASICALLY]" in prompt_text
        assert "it was fine" in prompt_text
        assert "120ms" in prompt_text
        assert "80ms" in prompt_text

    def test_build_triage_prompt_format(self) -> None:
        """_build_triage_prompt output contains required structural elements."""
        stage = _make_stage()
        prompt = stage._build_triage_prompt(
            word="like",
            context_before="you know",
            context_after="it makes sense",
            pause_before_ms=200.0,
            pause_after_ms=50.0,
        )

        assert "[LIKE]" in prompt
        assert "you know" in prompt
        assert "it makes sense" in prompt
        assert "200ms" in prompt
        assert "50ms" in prompt
        assert "SAFE or REVIEW" in prompt
        assert "reason:" in prompt.lower()


class TestTriageFillerBatchSplitting:
    """LLM calls are batched at max 20 fillers per call."""

    def test_triage_fillers_batch_splitting(self, tmp_path: Path) -> None:
        """25 hedge fillers → exactly 2 LLM calls (batch of 20 + batch of 5)."""
        cuts = [_hedge_cut(i, word="like") for i in range(25)]
        _write_filler_cuts(tmp_path, cuts)
        stage = _make_stage(enable_llm_triage=True)

        call_count = 0

        def fake_generate_content(model: str, contents: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            # Return SAFE verdict for all fillers — one block per candidate in batch
            num_prompts = contents.count("SAFE or REVIEW")
            responses = "\n---\n".join(["SAFE\nreason: Verbal tick only."] * num_prompts)
            return _make_mock_gemini_response(responses)

        mock_client = MagicMock()
        mock_client.models.generate_content = fake_generate_content

        with patch("google.genai.Client", return_value=mock_client):
            results = stage._triage_fillers(tmp_path)

        assert call_count == 2
        assert len(results) == 25

    def test_triage_fillers_exactly_20_is_one_call(self, tmp_path: Path) -> None:
        """20 hedge fillers → exactly 1 LLM call."""
        cuts = [_hedge_cut(i) for i in range(20)]
        _write_filler_cuts(tmp_path, cuts)
        stage = _make_stage(enable_llm_triage=True)

        call_count = 0

        def fake_generate_content(model: str, contents: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return _make_mock_gemini_response("\n---\n".join(["SAFE\nreason: Tick."] * 20))

        mock_client = MagicMock()
        mock_client.models.generate_content = fake_generate_content

        with patch("google.genai.Client", return_value=mock_client):
            stage._triage_fillers(tmp_path)

        assert call_count == 1


class TestTriageFillerParseError:
    """Parse errors default to safe_to_remove=False with descriptive reason."""

    def test_triage_fillers_parse_error_defaults_to_review(self, tmp_path: Path) -> None:
        """Unparseable LLM response → safe_to_remove=False, reason mentions parse error."""
        _write_filler_cuts(tmp_path, [_hedge_cut(0)])
        stage = _make_stage(enable_llm_triage=True)

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_mock_gemini_response(
            "I cannot determine this. The filler seems contextual."
        )

        with patch("google.genai.Client", return_value=mock_client):
            results = stage._triage_fillers(tmp_path)

        assert len(results) == 1
        assert results[0].safe_to_remove is False
        assert "parse error" in results[0].reason.lower()

    def test_triage_fillers_llm_exception_defaults_to_review(self, tmp_path: Path) -> None:
        """LLM call exception → safe_to_remove=False for all affected fillers."""
        _write_filler_cuts(tmp_path, [_hedge_cut(0), _hedge_cut(1)])
        stage = _make_stage(enable_llm_triage=True)

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("API timeout")

        with patch("google.genai.Client", return_value=mock_client):
            results = stage._triage_fillers(tmp_path)

        assert len(results) == 2
        for r in results:
            assert r.safe_to_remove is False
            assert "LLM call failed" in r.reason


class TestTriageFillerEmptyInput:
    """Empty or missing filler_cuts.json produces empty results without LLM calls."""

    def test_triage_fillers_empty_filler_cuts(self, tmp_path: Path) -> None:
        """No filler_cuts.json → filler_triage.json written as empty array, no LLM calls."""
        stage = _make_stage(enable_llm_triage=True)

        with patch("google.genai.Client") as mock_genai_cls:
            results = stage._triage_fillers(tmp_path)
            mock_genai_cls.assert_not_called()

        assert results == []

    def test_run_triage_writes_empty_json_when_no_cuts(self, tmp_path: Path) -> None:
        """_run_triage writes an empty array to analysis/filler_triage.json."""
        stage = _make_stage(enable_llm_triage=True)

        output = stage._run_triage(tmp_path)

        assert output == "analysis/filler_triage.json"
        triage_path = tmp_path / "analysis" / "filler_triage.json"
        assert triage_path.exists()
        payload = json.loads(triage_path.read_text())
        assert payload == []

    def test_triage_fillers_empty_list_json(self, tmp_path: Path) -> None:
        """filler_cuts.json with empty list → no results, no LLM calls."""
        _write_filler_cuts(tmp_path, [])
        stage = _make_stage(enable_llm_triage=True)

        with patch("google.genai.Client") as mock_genai_cls:
            results = stage._triage_fillers(tmp_path)
            mock_genai_cls.assert_not_called()

        assert results == []


class TestTriageFillerNoApiKey:
    """Missing Gemini API key returns safe fallback results."""

    def test_triage_fillers_no_gemini_key(self, tmp_path: Path) -> None:
        """No Gemini API key → all hedge candidates get safe_to_remove=False with descriptive reason."""
        _write_filler_cuts(tmp_path, [_hedge_cut(0), _hedge_cut(1)])
        stage = _make_stage(enable_llm_triage=True, gemini_key=None)

        with patch("google.genai.Client") as mock_genai_cls:
            results = stage._triage_fillers(tmp_path)
            mock_genai_cls.assert_not_called()

        assert len(results) == 2
        for r in results:
            assert r.safe_to_remove is False
            assert "gemini api key" in r.reason.lower()


class TestTriageFillerArtifact:
    """filler_triage.json artifact is written correctly."""

    def test_run_triage_writes_serialized_results(self, tmp_path: Path) -> None:
        """_run_triage writes filler_triage.json with one object per result."""
        _write_filler_cuts(tmp_path, [_hedge_cut(0, word="basically")])
        stage = _make_stage(enable_llm_triage=False)

        output = stage._run_triage(tmp_path)

        assert output == "analysis/filler_triage.json"
        triage_path = tmp_path / "analysis" / "filler_triage.json"
        assert triage_path.exists()

        payload = json.loads(triage_path.read_text())
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["word"] == "basically"
        assert payload[0]["safe_to_remove"] is False
        assert payload[0]["category"] == "hedge"

    def test_run_triage_returns_relative_path(self, tmp_path: Path) -> None:
        """_run_triage returns a relative path string for StageResult outputs."""
        _write_filler_cuts(tmp_path, [_hedge_cut(0)])
        stage = _make_stage(enable_llm_triage=False)

        output = stage._run_triage(tmp_path)

        assert output == "analysis/filler_triage.json"
        assert not output.startswith("/")  # must be relative
