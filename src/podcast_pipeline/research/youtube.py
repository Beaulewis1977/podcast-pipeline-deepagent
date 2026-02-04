"""YouTube Data API integration for research and trend analysis."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, Field

from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class TrendingTopic(BaseModel):
    """A trending topic with analysis."""

    topic: str
    search_volume: int = 0
    trending_videos: list[dict[str, Any]] = Field(default_factory=list)
    suggested_keywords: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    competitor_channels: list[dict[str, Any]] = Field(default_factory=list)


class ResearchResult(BaseModel):
    """Complete research result for a topic."""

    query: str
    topics: list[TrendingTopic] = Field(default_factory=list)
    trending_videos: list[dict[str, Any]] = Field(default_factory=list)
    suggested_keywords: list[str] = Field(default_factory=list)
    competitor_channels: list[dict[str, Any]] = Field(default_factory=list)
    insights: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class YouTubeResearcher:
    """YouTube Data API client for research and trend analysis."""

    def __init__(self, api_key: str | None = None):
        """Initialize YouTube researcher.

        Args:
            api_key: YouTube Data API key
        """
        self.api_key = api_key
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def is_available(self) -> bool:
        """Check if YouTube API is available."""
        return bool(self.api_key)

    def search_videos(
        self,
        query: str,
        max_results: int = 25,
        published_after: datetime | None = None,
        order: str = "relevance",
        video_duration: str = "any",
    ) -> list[dict[str, Any]]:
        """Search for videos on YouTube.

        Args:
            query: Search query
            max_results: Maximum number of results
            published_after: Only videos published after this date
            order: Order by (relevance, date, rating, viewCount)
            video_duration: Duration filter (any, short, medium, long)

        Returns:
            List of video items
        """
        if not self.api_key:
            logger.warning("youtube_api_not_configured")
            return []

        params: dict[str, str | int] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "order": order,
            "key": self.api_key,
        }

        if published_after:
            params["publishedAfter"] = published_after.isoformat() + "Z"

        if video_duration != "any":
            params["videoDuration"] = video_duration

        try:
            response = self.client.get(f"{YOUTUBE_API_BASE}/search", params=params)
            response.raise_for_status()
            data = response.json()

            videos = []
            video_ids = []

            for item in data.get("items", []):
                video_id = item.get("id", {}).get("videoId")
                if video_id:
                    video_ids.append(video_id)
                    videos.append(
                        {
                            "video_id": video_id,
                            "title": item.get("snippet", {}).get("title", ""),
                            "description": item.get("snippet", {}).get("description", ""),
                            "channel_title": item.get("snippet", {}).get("channelTitle", ""),
                            "channel_id": item.get("snippet", {}).get("channelId", ""),
                            "published_at": item.get("snippet", {}).get("publishedAt", ""),
                            "thumbnail": item.get("snippet", {})
                            .get("thumbnails", {})
                            .get("high", {})
                            .get("url", ""),
                        }
                    )

            # Get video statistics
            if video_ids:
                stats = self._get_video_stats(video_ids)
                for video in videos:
                    video_stats = stats.get(video["video_id"], {})
                    video.update(video_stats)

            return videos

        except httpx.HTTPError as e:
            logger.exception("youtube_search_failed", error=str(e))
            return []

    def _get_video_stats(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Get statistics for multiple videos.

        Args:
            video_ids: List of video IDs

        Returns:
            Dictionary mapping video_id to stats
        """
        if not self.api_key or not video_ids:
            return {}

        params = {
            "part": "statistics,contentDetails",
            "id": ",".join(video_ids[:50]),  # API limit
            "key": self.api_key,
        }

        try:
            response = self.client.get(f"{YOUTUBE_API_BASE}/videos", params=params)
            response.raise_for_status()
            data = response.json()

            stats = {}
            for item in data.get("items", []):
                video_id = item.get("id")
                statistics = item.get("statistics", {})
                content = item.get("contentDetails", {})

                stats[video_id] = {
                    "view_count": int(statistics.get("viewCount", 0)),
                    "like_count": int(statistics.get("likeCount", 0)),
                    "comment_count": int(statistics.get("commentCount", 0)),
                    "duration": content.get("duration", ""),
                }

            return stats

        except httpx.HTTPError as e:
            logger.exception("youtube_stats_failed", error=str(e))
            return {}

    def get_channel_info(self, channel_id: str) -> dict[str, Any] | None:
        """Get channel information.

        Args:
            channel_id: YouTube channel ID

        Returns:
            Channel info dictionary or None
        """
        if not self.api_key:
            return None

        params = {
            "part": "snippet,statistics,contentDetails",
            "id": channel_id,
            "key": self.api_key,
        }

        try:
            response = self.client.get(f"{YOUTUBE_API_BASE}/channels", params=params)
            response.raise_for_status()
            data = response.json()

            items = data.get("items", [])
            if not items:
                return None

            item = items[0]
            return {
                "channel_id": channel_id,
                "title": item.get("snippet", {}).get("title", ""),
                "description": item.get("snippet", {}).get("description", ""),
                "subscriber_count": int(item.get("statistics", {}).get("subscriberCount", 0)),
                "video_count": int(item.get("statistics", {}).get("videoCount", 0)),
                "view_count": int(item.get("statistics", {}).get("viewCount", 0)),
                "thumbnail": item.get("snippet", {})
                .get("thumbnails", {})
                .get("high", {})
                .get("url", ""),
            }

        except httpx.HTTPError as e:
            logger.exception("youtube_channel_failed", error=str(e))
            return None

    def analyze_competitors(
        self,
        topics: list[str],
        max_channels: int = 10,
    ) -> list[dict[str, Any]]:
        """Analyze competitor channels for given topics.

        Args:
            topics: List of topics to search
            max_channels: Maximum number of channels to return

        Returns:
            List of competitor channel info
        """
        channels: dict[str, dict[str, Any]] = {}

        for topic in topics:
            videos = self.search_videos(
                topic,
                max_results=20,
                order="viewCount",
                published_after=datetime.now(UTC) - timedelta(days=90),
            )

            for video in videos:
                channel_id = video.get("channel_id")
                if channel_id and channel_id not in channels:
                    channel_info = self.get_channel_info(channel_id)
                    if channel_info:
                        channels[channel_id] = channel_info

        # Sort by subscriber count and return top channels
        sorted_channels = sorted(
            channels.values(),
            key=lambda x: x.get("subscriber_count", 0),
            reverse=True,
        )

        return sorted_channels[:max_channels]

    def get_trending_keywords(
        self,
        seed_keywords: list[str],
        max_keywords: int = 20,
    ) -> list[str]:
        """Get trending keywords based on seed keywords.

        Args:
            seed_keywords: Initial keywords to expand
            max_keywords: Maximum keywords to return

        Returns:
            List of related trending keywords
        """
        keywords: set[str] = set()

        for seed in seed_keywords:
            videos = self.search_videos(
                seed,
                max_results=10,
                order="viewCount",
                published_after=datetime.now(UTC) - timedelta(days=30),
            )

            for video in videos:
                # Extract keywords from titles
                title = video.get("title", "")
                # Simple keyword extraction (could be enhanced with NLP)
                words = title.lower().split()
                for word in words:
                    word = word.strip(",.!?()[]\"'")
                    if len(word) > 3 and word not in seed.lower():
                        keywords.add(word)

                # Extract hashtags from description
                desc = video.get("description", "")
                hashtags = [w for w in desc.split() if w.startswith("#")]
                for tag in hashtags:
                    keywords.add(tag.strip("#"))

        return list(keywords)[:max_keywords]

    def research_topic(
        self,
        topic: str,
        related_topics: list[str] | None = None,
    ) -> ResearchResult:
        """Perform comprehensive research on a topic.

        Args:
            topic: Main topic to research
            related_topics: Additional related topics

        Returns:
            Complete research result
        """
        logger.info("researching_topic", topic=topic)

        all_topics = [topic] + (related_topics or [])

        # Get trending videos
        trending_videos = self.search_videos(
            topic,
            max_results=25,
            order="viewCount",
            published_after=datetime.now(UTC) - timedelta(days=7),
        )

        # Get recent videos
        recent_videos = self.search_videos(
            topic,
            max_results=25,
            order="date",
            published_after=datetime.now(UTC) - timedelta(days=3),
        )

        # Combine and deduplicate
        seen_ids = set()
        all_videos = []
        for video in trending_videos + recent_videos:
            if video["video_id"] not in seen_ids:
                seen_ids.add(video["video_id"])
                all_videos.append(video)

        # Analyze competitors
        competitors = self.analyze_competitors(all_topics[:3])

        # Get trending keywords
        keywords = self.get_trending_keywords(all_topics)

        # Generate insights
        insights = self._generate_insights(all_videos, competitors)

        return ResearchResult(
            query=topic,
            trending_videos=all_videos[:50],
            suggested_keywords=keywords,
            competitor_channels=competitors,
            insights=insights,
        )

    def _generate_insights(
        self,
        videos: list[dict[str, Any]],
        competitors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate insights from research data.

        Args:
            videos: List of videos
            competitors: List of competitor channels

        Returns:
            Dictionary of insights
        """
        if not videos:
            return {}

        # Calculate average metrics
        view_counts = [v.get("view_count", 0) for v in videos if v.get("view_count")]
        like_counts = [v.get("like_count", 0) for v in videos if v.get("like_count")]

        avg_views = sum(view_counts) / len(view_counts) if view_counts else 0
        avg_likes = sum(like_counts) / len(like_counts) if like_counts else 0

        # Find best performing videos
        sorted_by_views = sorted(videos, key=lambda x: x.get("view_count", 0), reverse=True)

        # Analyze title patterns
        title_lengths = [len(v.get("title", "")) for v in videos]
        avg_title_length = sum(title_lengths) / len(title_lengths) if title_lengths else 0

        return {
            "avg_views": int(avg_views),
            "avg_likes": int(avg_likes),
            "avg_title_length": int(avg_title_length),
            "top_video_title": sorted_by_views[0].get("title") if sorted_by_views else None,
            "top_video_views": sorted_by_views[0].get("view_count") if sorted_by_views else 0,
            "total_videos_analyzed": len(videos),
            "total_competitors": len(competitors),
            "recommendation": self._get_recommendation(avg_views, avg_title_length),
        }

    def _get_recommendation(self, avg_views: float, avg_title_length: float) -> str:
        """Generate a recommendation based on insights."""
        recommendations = []

        if avg_views > 100000:
            recommendations.append("This is a high-competition topic with viral potential.")
        elif avg_views > 10000:
            recommendations.append("Good engagement potential with moderate competition.")
        else:
            recommendations.append("Lower competition - good opportunity for growth.")

        if avg_title_length > 60:
            recommendations.append("Consider shorter, punchier titles (under 60 chars).")
        elif avg_title_length < 30:
            recommendations.append("Titles could be more descriptive to improve CTR.")

        return " ".join(recommendations)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
