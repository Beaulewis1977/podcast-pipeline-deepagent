"""Tests for research/viral insight panel helper transformations."""

from podcast_pipeline.ui.app import _build_clip_score_rows, _build_research_panel_data


def test_build_research_panel_data_includes_enriched_metrics() -> None:
    """Enriched research payload should be transformed into display-ready values."""
    research_payload = {
        "query": "podcast growth",
        "suggested_keywords": ["growth loop", "retention hook", "creator workflow"],
        "insights": {
            "competition_score": 72.5,
            "engagement_benchmarks": {
                "avg_engagement_rate": 0.067,
                "avg_velocity_per_hour": 412.3,
            },
            "best_posting_windows": [
                {"window": "15:00-15:59 UTC", "videos_published": 8},
                {"window": "09:00-09:59 UTC", "videos_published": 5},
            ],
        },
    }

    panel = _build_research_panel_data(research_payload)

    assert panel["query"] == "podcast growth"
    assert panel["competition_score"] == 72.5
    assert panel["keywords"][0] == "growth loop"
    assert panel["posting_windows"][0] == "15:00-15:59 UTC (8 videos)"


def test_build_clip_score_rows_sorts_by_combined_score() -> None:
    """Rows should be sorted by combined score and include score breakdown columns."""
    viral_payload = {
        "clip_scores": [
            {
                "clip": {"start_seconds": 0, "end_seconds": 20, "description": "Clip A"},
                "ai_score": 9,
                "detector_score": 4,
                "combined_score": 6.25,
                "reasons": ["Strong hook", "Good pacing"],
            },
            {
                "clip": {"start_seconds": 30, "end_seconds": 50, "description": "Clip B"},
                "ai_score": 3,
                "detector_score": 9.5,
                "combined_score": 6.53,
                "reasons": ["High controversy"],
            },
        ]
    }

    rows = _build_clip_score_rows(viral_payload, limit=10)

    assert rows[0]["Start (s)"] == 30
    assert rows[0]["Combined Score"] == 6.53
    assert rows[0]["AI Score"] == 3.0
    assert rows[0]["Detector Score"] == 9.5
    assert "controversy" in rows[0]["Reasons"].lower()


def test_build_clip_score_rows_handles_legacy_shapes_with_missing_fields() -> None:
    """Legacy viral payloads should still render via fallback score extraction."""
    legacy_payload = {
        "clip_scores": [
            {
                "clip": {"start_seconds": 10, "end_seconds": 35, "description": "Legacy clip"},
                "score": {
                    "overall_score": 7.2,
                    "reasons": ["Legacy detector reason"],
                },
            }
        ]
    }

    rows = _build_clip_score_rows(legacy_payload, limit=10)

    assert rows[0]["AI Score"] == 0.0
    assert rows[0]["Detector Score"] == 7.2
    assert rows[0]["Combined Score"] == 3.96
    assert "legacy detector reason" in rows[0]["Reasons"].lower()


def test_build_research_panel_data_preserves_keyword_priority_and_window_visibility() -> None:
    """Trend keywords and posting windows should stay visible in deterministic order."""
    research_payload = {
        "query": "creator growth systems",
        "suggested_keywords": [f"keyword-{index}" for index in range(12)],
        "insights": {
            "competition_score": 55,
            "best_posting_windows": [
                {"window": "07:00-07:59 UTC"},
                {"window": "20:00-20:59 UTC", "videos_published": 3},
            ],
        },
    }

    panel = _build_research_panel_data(research_payload)

    assert panel["keywords"] == [f"keyword-{index}" for index in range(10)]
    assert panel["posting_windows"] == [
        "07:00-07:59 UTC",
        "20:00-20:59 UTC (3 videos)",
    ]
