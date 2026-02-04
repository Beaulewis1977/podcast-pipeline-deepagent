"""YouTube Data API integration for research and trend analysis."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import median
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
                    video.update(self._enrich_video_metrics(video))

            # Always provide a complete metric payload, even if stats API is empty.
            for video in videos:
                if "engagement_rate" not in video:
                    video.update(self._enrich_video_metrics(video))

            return videos

        except httpx.HTTPError as e:
            logger.exception("youtube_search_failed", error=str(e))
            return []

    def _safe_int(self, value: Any) -> int:
        """Safely parse integer-like values and clamp to non-negative."""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return max(parsed, 0)

    def _parse_published_at(self, published_at: Any) -> datetime | None:
        """Parse YouTube publish timestamp safely."""
        if not isinstance(published_at, str):
            return None

        normalized = published_at.strip()
        if not normalized:
            return None

        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        return parsed.astimezone(UTC)

    def _enrich_video_metrics(
        self,
        video: dict[str, Any],
        reference_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Compute per-video engagement and momentum metrics."""
        now = reference_time or datetime.now(UTC)
        published_at = self._parse_published_at(video.get("published_at"))

        view_count = self._safe_int(video.get("view_count"))
        like_count = self._safe_int(video.get("like_count"))
        comment_count = self._safe_int(video.get("comment_count"))

        interactions = like_count + comment_count
        engagement_rate = round(interactions / view_count, 4) if view_count > 0 else 0.0

        hours_since_publish = 0.0
        velocity_per_hour = 0.0
        published_hour_utc: int | None = None
        published_weekday_utc: str | None = None

        if published_at is not None:
            elapsed_hours = max((now - published_at).total_seconds() / 3600, 0.0)
            hours_since_publish = round(elapsed_hours, 2)
            effective_hours = max(elapsed_hours, 1.0)
            velocity_per_hour = round(view_count / effective_hours, 4)
            published_hour_utc = published_at.hour
            published_weekday_utc = published_at.strftime("%A")

        return {
            "engagement_rate": engagement_rate,
            "hours_since_publish": hours_since_publish,
            "velocity_per_hour": velocity_per_hour,
            "published_at_valid": published_at is not None,
            "published_hour_utc": published_hour_utc,
            "published_weekday_utc": published_weekday_utc,
        }

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
        view_counts = [self._safe_int(v.get("view_count")) for v in videos]
        like_counts = [self._safe_int(v.get("like_count")) for v in videos]
        engagement_rates = [float(v.get("engagement_rate", 0.0) or 0.0) for v in videos]
        velocity_values = [float(v.get("velocity_per_hour", 0.0) or 0.0) for v in videos]

        avg_views = sum(view_counts) / len(view_counts) if view_counts else 0
        avg_likes = sum(like_counts) / len(like_counts) if like_counts else 0
        competition_score = self._calculate_competition_score(videos, competitors)
        posting_windows = self._best_posting_windows(videos)

        sorted_rates = sorted(engagement_rates)
        upper_quartile = (
            sorted_rates[max(int(len(sorted_rates) * 0.75) - 1, 0)] if sorted_rates else 0.0
        )
        avg_velocity = sum(velocity_values) / len(velocity_values) if velocity_values else 0.0

        # Find best performing videos
        sorted_by_views = sorted(videos, key=lambda x: x.get("view_count", 0), reverse=True)

        # Analyze title patterns
        title_lengths = [len(v.get("title", "")) for v in videos]
        avg_title_length = sum(title_lengths) / len(title_lengths) if title_lengths else 0

        engagement_benchmarks = {
            "avg_engagement_rate": round(sum(engagement_rates) / len(engagement_rates), 4)
            if engagement_rates
            else 0.0,
            "median_engagement_rate": round(median(engagement_rates), 4) if engagement_rates else 0.0,
            "top_quartile_engagement_rate": round(upper_quartile, 4),
            "avg_velocity_per_hour": round(avg_velocity, 4),
        }

        posting_patterns = {
            "total_videos_with_publish_time": sum(1 for v in videos if v.get("published_at_valid")),
            "best_posting_windows": posting_windows,
            "top_weekdays": self._top_posting_days(videos),
        }

        return {
            "avg_views": int(avg_views),
            "avg_likes": int(avg_likes),
            "avg_title_length": int(avg_title_length),
            "top_video_title": sorted_by_views[0].get("title") if sorted_by_views else None,
            "top_video_views": sorted_by_views[0].get("view_count") if sorted_by_views else 0,
            "total_videos_analyzed": len(videos),
            "total_competitors": len(competitors),
            "competition_score": competition_score,
            "competition_tier": self._competition_tier(competition_score),
            "engagement_benchmarks": engagement_benchmarks,
            "best_posting_windows": posting_windows,
            "posting_patterns": posting_patterns,
            "recommendation": self._get_recommendation(
                avg_views=avg_views,
                avg_title_length=avg_title_length,
                competition_score=competition_score,
                avg_engagement=engagement_benchmarks["avg_engagement_rate"],
            ),
        }

    def _calculate_competition_score(
        self,
        videos: list[dict[str, Any]],
        competitors: list[dict[str, Any]],
    ) -> float:
        """Estimate topic competition on a 0-100 scale."""
        if not videos:
            return 0.0

        avg_views = sum(self._safe_int(v.get("view_count")) for v in videos) / len(videos)
        max_views = max(self._safe_int(v.get("view_count")) for v in videos)
        avg_competitor_subscribers = (
            sum(self._safe_int(c.get("subscriber_count")) for c in competitors) / len(competitors)
            if competitors
            else 0.0
        )
        large_competitor_ratio = (
            sum(1 for c in competitors if self._safe_int(c.get("subscriber_count")) >= 100_000)
            / len(competitors)
            if competitors
            else 0.0
        )

        normalized_views = min(avg_views / 250_000, 1.0)
        normalized_competitor_count = min(len(competitors) / 10, 1.0)
        normalized_subscribers = min(avg_competitor_subscribers / 1_000_000, 1.0)
        normalized_top_video_ratio = min((max_views / max(avg_views, 1.0)) / 10, 1.0)

        weighted_score = (
            normalized_views * 0.35
            + normalized_competitor_count * 0.30
            + normalized_subscribers * 0.20
            + normalized_top_video_ratio * 0.10
            + large_competitor_ratio * 0.05
        )
        return round(min(max(weighted_score * 100, 0.0), 100.0), 2)

    def _competition_tier(self, competition_score: float) -> str:
        """Convert competition score to a stable label for UI display."""
        if competition_score >= 70:
            return "high"
        if competition_score >= 40:
            return "medium"
        return "low"

    def _best_posting_windows(
        self,
        videos: list[dict[str, Any]],
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return best UTC posting windows based on historical publish-time concentration."""
        parsed_times = [
            self._parse_published_at(video.get("published_at"))
            for video in videos
            if video.get("published_at")
        ]
        valid_times = [timestamp for timestamp in parsed_times if timestamp is not None]
        if not valid_times:
            return []

        total = len(valid_times)
        hour_counts = Counter(timestamp.hour for timestamp in valid_times)
        hour_weekday_counts: dict[int, Counter[str]] = {}
        for timestamp in valid_times:
            hour_weekday_counts.setdefault(timestamp.hour, Counter())[timestamp.strftime("%A")] += 1

        windows = []
        for hour, count in hour_counts.most_common(limit):
            weekday_counter = hour_weekday_counts.get(hour, Counter())
            strongest_weekday = weekday_counter.most_common(1)[0][0] if weekday_counter else "Any"

            windows.append(
                {
                    "window": f"{hour:02d}:00-{hour:02d}:59 UTC",
                    "hour_utc": hour,
                    "videos_published": count,
                    "share_of_posts": round(count / total, 4),
                    "strongest_weekday": strongest_weekday,
                }
            )

        return windows

    def _top_posting_days(
        self,
        videos: list[dict[str, Any]],
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return most common UTC weekdays for publish times."""
        weekdays: list[str] = []
        for video in videos:
            published_at = self._parse_published_at(video.get("published_at"))
            if published_at is not None:
                weekdays.append(published_at.strftime("%A"))

        if not weekdays:
            return []

        counts = Counter(weekdays)
        total = len(weekdays)
        return [
            {
                "weekday": weekday,
                "videos_published": count,
                "share_of_posts": round(count / total, 4),
            }
            for weekday, count in counts.most_common(limit)
        ]

    def _get_recommendation(
        self,
        avg_views: float,
        avg_title_length: float,
        competition_score: float,
        avg_engagement: float,
    ) -> str:
        """Generate a recommendation based on insights."""
        recommendations = []

        if competition_score >= 70:
            recommendations.append("This is a high-competition topic with viral potential.")
        elif competition_score >= 40:
            recommendations.append("Good engagement potential with moderate competition.")
        else:
            recommendations.append("Lower competition - good opportunity for growth.")

        if avg_engagement >= 0.08:
            recommendations.append("Engagement is strong; prioritize clips with explicit hooks.")
        elif avg_engagement < 0.03:
            recommendations.append("Engagement is low; sharpen intros and tighten pacing.")

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
