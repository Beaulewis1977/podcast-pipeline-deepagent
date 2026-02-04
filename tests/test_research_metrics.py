"""Tests for YouTube research metric enrichment helpers."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from podcast_pipeline.research.youtube import YouTubeResearcher


@patch("httpx.Client.get")
def test_search_videos_enriches_engagement_metrics(mock_get: MagicMock) -> None:
    """Search results include engagement and velocity metrics."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "items": [
            {
                "id": {"videoId": "abc123"},
                "snippet": {
                    "title": "Metrics Test",
                    "description": "desc",
                    "channelTitle": "Channel",
                    "channelId": "UC123",
                    "publishedAt": "2026-01-02T00:00:00Z",
                    "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
                },
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    researcher = YouTubeResearcher(api_key="test-key")
    with patch.object(researcher, "_get_video_stats") as mock_stats:
        mock_stats.return_value = {"abc123": {"view_count": 1200, "like_count": 120, "comment_count": 30}}
        videos = researcher.search_videos("ai", max_results=1)

    assert len(videos) == 1
    assert "engagement_rate" in videos[0]
    assert "velocity_per_hour" in videos[0]
    assert videos[0]["engagement_rate"] == 0.125


def test_enrich_video_metrics_handles_invalid_publish_timestamp() -> None:
    """Metric enrichment should degrade gracefully for invalid publish timestamps."""
    researcher = YouTubeResearcher()
    enriched = researcher._enrich_video_metrics(
        {
            "view_count": 500,
            "like_count": 25,
            "comment_count": 5,
            "published_at": "not-a-date",
        },
        reference_time=datetime(2026, 1, 10, 0, 0, tzinfo=UTC),
    )

    assert enriched["published_at_valid"] is False
    assert enriched["hours_since_publish"] == 0.0
    assert enriched["velocity_per_hour"] == 0.0
    assert enriched["engagement_rate"] == 0.06


def test_enrich_video_metrics_computes_velocity_from_publish_age() -> None:
    """Velocity should be derived from elapsed publish age in hours."""
    researcher = YouTubeResearcher()
    enriched = researcher._enrich_video_metrics(
        {
            "view_count": 2400,
            "like_count": 180,
            "comment_count": 60,
            "published_at": "2026-01-09T00:00:00Z",
        },
        reference_time=datetime(2026, 1, 10, 0, 0, tzinfo=UTC),
    )

    assert enriched["published_at_valid"] is True
    assert enriched["hours_since_publish"] == 24.0
    assert enriched["velocity_per_hour"] == 100.0
    assert enriched["engagement_rate"] == 0.1


def test_generate_insights_includes_competition_and_posting_outputs() -> None:
    """Insight payload should expose phase-2 competition and posting analytics."""
    researcher = YouTubeResearcher()
    videos = [
        {
            "title": "AI Workflow Playbook",
            "view_count": 40_000,
            "like_count": 2_600,
            "comment_count": 210,
            "engagement_rate": 0.0703,
            "velocity_per_hour": 500.0,
            "published_at": "2026-01-05T15:20:00Z",
            "published_at_valid": True,
        },
        {
            "title": "Podcast Growth Tactics",
            "view_count": 22_000,
            "like_count": 1_100,
            "comment_count": 95,
            "engagement_rate": 0.0543,
            "velocity_per_hour": 410.0,
            "published_at": "2026-01-06T15:05:00Z",
            "published_at_valid": True,
        },
        {
            "title": "Hook Framework for Creators",
            "view_count": 15_000,
            "like_count": 750,
            "comment_count": 60,
            "engagement_rate": 0.054,
            "velocity_per_hour": 320.0,
            "published_at": "2026-01-07T09:10:00Z",
            "published_at_valid": True,
        },
    ]
    competitors = [
        {"title": "Channel A", "subscriber_count": 300_000},
        {"title": "Channel B", "subscriber_count": 150_000},
        {"title": "Channel C", "subscriber_count": 75_000},
    ]

    insights = researcher._generate_insights(videos, competitors)

    assert 0.0 <= insights["competition_score"] <= 100.0
    assert insights["competition_tier"] in {"low", "medium", "high"}
    assert "engagement_benchmarks" in insights
    assert "best_posting_windows" in insights
    assert insights["engagement_benchmarks"]["avg_engagement_rate"] > 0

    posting_windows = insights["best_posting_windows"]
    assert posting_windows
    assert posting_windows[0]["window"].endswith("UTC")
    assert posting_windows[0]["videos_published"] >= posting_windows[-1]["videos_published"]

    posting_patterns = insights["posting_patterns"]
    assert posting_patterns["total_videos_with_publish_time"] == len(videos)
    assert posting_patterns["top_weekdays"]


def test_generate_insights_bounds_competition_score_for_extreme_inputs() -> None:
    """Competition score remains bounded even with very large channels and views."""
    researcher = YouTubeResearcher()
    videos = [
        {
            "title": "Massive topic",
            "view_count": 5_000_000,
            "like_count": 400_000,
            "comment_count": 90_000,
            "engagement_rate": 0.098,
            "velocity_per_hour": 50_000,
            "published_at": "2026-01-08T20:00:00Z",
            "published_at_valid": True,
        }
    ]
    competitors = [{"title": "Top creator", "subscriber_count": 15_000_000}] * 12

    insights = researcher._generate_insights(videos, competitors)
    assert 0.0 <= insights["competition_score"] <= 100.0
