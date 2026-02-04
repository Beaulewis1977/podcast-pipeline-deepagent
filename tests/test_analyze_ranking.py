"""Tests for analyze-stage combined clip re-ranking."""

import json

from podcast_pipeline.config import load_config
from podcast_pipeline.models.analysis import AnalysisResult, ViralClip
from podcast_pipeline.research.viral_detector import ViralClipDetector, ViralScore
from podcast_pipeline.stages.analyze import AnalyzeStage


def test_analyze_stage_ranks_clips_by_combined_score(tmp_path, monkeypatch) -> None:
    """Analyze stage should sort clip scores by combined AI + detector values."""
    stage = AnalyzeStage(load_config())
    analysis_result = AnalysisResult(
        viral_clips=[
            ViralClip(
                start="00:00",
                end="00:20",
                start_seconds=0,
                end_seconds=20,
                description="Clip A",
                virality_score=9,
            ),
            ViralClip(
                start="00:30",
                end="00:50",
                start_seconds=30,
                end_seconds=50,
                description="Clip B",
                virality_score=3,
            ),
            ViralClip(
                start="01:00",
                end="01:20",
                start_seconds=60,
                end_seconds=80,
                description="Clip C",
                virality_score=6,
            ),
        ]
    )
    transcript = {"segments": []}

    detector_scores = {0: 4.0, 30: 9.5, 60: 6.0}

    monkeypatch.setattr(ViralClipDetector, "analyze_transcript", lambda self, data: [])

    def fake_score_clip(self, clip_data, transcript_data, signals=None):  # type: ignore[no-untyped-def]
        score_value = detector_scores[int(clip_data["start_seconds"])]
        return ViralScore(
            overall_score=score_value,
            hook_score=score_value,
            emotional_score=score_value,
            shareability_score=score_value,
            engagement_density_score=score_value,
            reasons=[f"detector={score_value}"],
        )

    monkeypatch.setattr(ViralClipDetector, "score_clip", fake_score_clip)

    output = stage._run_viral_signals(analysis_result, transcript, tmp_path)
    assert output == "analysis/viral_signals.json"

    payload = json.loads((tmp_path / "analysis" / "viral_signals.json").read_text())
    clip_scores = payload["clip_scores"]

    assert [item["clip"]["start_seconds"] for item in clip_scores] == [30, 0, 60]
    assert all(0 <= item["combined_score"] <= 10 for item in clip_scores)
    assert all("reasons" in item for item in clip_scores)


def test_analyze_stage_caps_combined_score_at_ten(tmp_path, monkeypatch) -> None:
    """Even exaggerated input scores should remain capped at 10."""
    stage = AnalyzeStage(load_config())
    analysis_result = AnalysisResult(
        viral_clips=[
            ViralClip(
                start="00:00",
                end="00:20",
                start_seconds=0,
                end_seconds=20,
                description="Cap test clip",
                virality_score=10,
            )
        ]
    )
    transcript = {"segments": []}

    monkeypatch.setattr(ViralClipDetector, "analyze_transcript", lambda self, data: [])

    def fake_score_clip(self, clip_data, transcript_data, signals=None):  # type: ignore[no-untyped-def]
        return ViralScore(
            overall_score=10.0,
            hook_score=10.0,
            emotional_score=10.0,
            shareability_score=10.0,
            engagement_density_score=10.0,
            reasons=["high confidence"],
        )

    monkeypatch.setattr(ViralClipDetector, "score_clip", fake_score_clip)

    stage._run_viral_signals(analysis_result, transcript, tmp_path)
    payload = json.loads((tmp_path / "analysis" / "viral_signals.json").read_text())
    score_row = payload["clip_scores"][0]

    assert score_row["combined_score"] == 10.0
    assert score_row["ai_score"] == 10.0
    assert score_row["detector_score"] == 10.0


def test_analyze_stage_falls_back_when_scores_are_missing(tmp_path, monkeypatch) -> None:
    """Missing provider or detector scores should use safe defaults."""
    stage = AnalyzeStage(load_config())

    class DummyAnalysisResult:
        def model_dump(self):  # type: ignore[no-untyped-def]
            return {
                "viral_clips": [
                    {
                        "start": "00:00",
                        "end": "00:15",
                        "start_seconds": 0,
                        "end_seconds": 15,
                        "description": "Missing score clip",
                    },
                    {
                        "start": "00:20",
                        "end": "00:40",
                        "start_seconds": 20,
                        "end_seconds": 40,
                        "description": "Normal score clip",
                        "virality_score": 8,
                    },
                ]
            }

    class DummyScore:
        def __init__(self, overall_score, reasons):  # type: ignore[no-untyped-def]
            self.overall_score = overall_score
            self._reasons = reasons

        def model_dump(self):  # type: ignore[no-untyped-def]
            return {
                "overall_score": self.overall_score,
                "hook_score": 0,
                "emotional_score": 0,
                "shareability_score": 0,
                "engagement_density_score": 0,
                "reasons": self._reasons,
            }

    monkeypatch.setattr(ViralClipDetector, "analyze_transcript", lambda self, data: [])

    def fake_score_clip(self, clip_data, transcript_data, signals=None):  # type: ignore[no-untyped-def]
        if clip_data["start_seconds"] == 0:
            return DummyScore(None, ["missing detector score"])
        return DummyScore(7.0, ["detector score present"])

    monkeypatch.setattr(ViralClipDetector, "score_clip", fake_score_clip)

    stage._run_viral_signals(DummyAnalysisResult(), {"segments": []}, tmp_path)
    payload = json.loads((tmp_path / "analysis" / "viral_signals.json").read_text())
    rows = {item["clip"]["start_seconds"]: item for item in payload["clip_scores"]}

    assert rows[0]["ai_score"] == 5.0
    assert rows[0]["detector_score"] == 0.0
    assert rows[0]["combined_score"] == 2.25
    assert rows[20]["ai_score"] == 8.0
    assert rows[20]["detector_score"] == 7.0
