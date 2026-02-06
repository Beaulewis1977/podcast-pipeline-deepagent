"""Tests for YouTube research caching and keyword extraction upgrades."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from podcast_pipeline.research.youtube import YouTubeResearcher


def _mock_search_response(video_id: str = "abc123") -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "items": [
            {
                "id": {"videoId": video_id},
                "snippet": {
                    "title": "AI creator workflow",
                    "description": "A practical walkthrough for content teams",
                    "channelTitle": "Channel",
                    "channelId": "UC123",
                    "publishedAt": "2026-01-10T12:00:00Z",
                    "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
                },
            }
        ]
    }
    response.raise_for_status = MagicMock()
    return response


@patch("httpx.Client.get")
def test_search_videos_cache_hit_for_normalized_equivalent_queries(mock_get: MagicMock) -> None:
    """Equivalent normalized query params should reuse cached response inside TTL."""
    mock_get.return_value = _mock_search_response()
    researcher = YouTubeResearcher(api_key="key", cache_ttl_seconds=300)

    with patch.object(researcher, "_get_video_stats") as mock_stats:
        mock_stats.return_value = {
            "abc123": {"view_count": 100, "like_count": 10, "comment_count": 2}
        }
        researcher.search_videos(" AI   creator workflow ", max_results=5, order="relevance")
        researcher.search_videos("ai creator workflow", max_results=5, order="relevance")

    assert mock_get.call_count == 1
    assert mock_stats.call_count == 1


@patch("httpx.Client.get")
def test_search_videos_cache_respects_ttl_expiry(mock_get: MagicMock) -> None:
    """TTL=0 should force misses so repeated calls hit the API each time."""
    mock_get.return_value = _mock_search_response()
    researcher = YouTubeResearcher(api_key="key", cache_ttl_seconds=0)

    with patch.object(researcher, "_get_video_stats") as mock_stats:
        mock_stats.return_value = {
            "abc123": {"view_count": 100, "like_count": 10, "comment_count": 2}
        }
        researcher.search_videos("podcast growth", max_results=5, order="date")
        researcher.search_videos("podcast growth", max_results=5, order="date")

    assert mock_get.call_count == 2
    assert mock_stats.call_count == 2


@patch("httpx.Client.get")
def test_search_videos_cache_expires_after_ttl_window(mock_get: MagicMock) -> None:
    """Expired entries should trigger a fresh upstream call after TTL window."""
    mock_get.return_value = _mock_search_response()
    researcher = YouTubeResearcher(api_key="key", cache_ttl_seconds=30)
    base_time = datetime(2026, 1, 12, 12, 0, tzinfo=UTC)

    with patch.object(researcher, "_get_video_stats") as mock_stats:
        mock_stats.return_value = {
            "abc123": {"view_count": 100, "like_count": 10, "comment_count": 2}
        }
        with patch.object(
            researcher,
            "_utcnow",
            side_effect=[
                base_time,  # first _cache_set
                base_time + timedelta(seconds=45),  # second _cache_get (expired)
                base_time + timedelta(seconds=45),  # second _cache_set
            ],
        ):
            researcher.search_videos("ttl boundary", max_results=3, order="date")
            researcher.search_videos("ttl boundary", max_results=3, order="date")

    assert mock_get.call_count == 2
    assert mock_stats.call_count == 2


def test_weighted_keyword_extraction_favors_multiword_recurring_phrases() -> None:
    """Recurring phrase n-grams should outrank weaker single-token noise."""
    researcher = YouTubeResearcher(api_key="key", cache_ttl_seconds=300)
    mock_videos = [
        {
            "title": "Growth loop blueprint for creator teams",
            "description": "This growth loop framework improves retention and conversion",
            "view_count": 90_000,
        },
        {
            "title": "Growth loop teardown with retention hooks",
            "description": "Repeatable growth loop tactics for podcast episodes",
            "view_count": 75_000,
        },
        {
            "title": "Creator workflow basics",
            "description": "Simple workflow setup with templates",
            "view_count": 8_000,
        },
    ]

    with patch.object(researcher, "search_videos", return_value=mock_videos):
        keywords = researcher.get_trending_keywords(["podcast growth"], max_keywords=10)

    assert "growth loop" in keywords[:3]
    assert "with" not in keywords
    assert "this" not in keywords
    assert "podcast" not in keywords
