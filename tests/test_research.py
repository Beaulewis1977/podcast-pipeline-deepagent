"""Tests for YouTube research and viral clip detection."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from podcast_pipeline.research.viral_detector import EngagementSignal, ViralClipDetector, ViralScore
from podcast_pipeline.research.youtube import ResearchResult, YouTubeResearcher


class TestYouTubeResearcher:
    """Tests for YouTube Data API client."""

    def test_researcher_init_without_key(self) -> None:
        """Test researcher initialization without API key."""
        researcher = YouTubeResearcher()
        assert researcher.api_key is None
        assert researcher.is_available() is False

    def test_researcher_init_with_key(self) -> None:
        """Test researcher initialization with API key."""
        researcher = YouTubeResearcher(api_key="test_key")
        assert researcher.api_key == "test_key"
        assert researcher.is_available() is True

    def test_search_videos_without_api_key(self) -> None:
        """Test search returns empty when no API key."""
        researcher = YouTubeResearcher()
        results = researcher.search_videos("test query")
        assert results == []

    @patch("httpx.Client.get")
    def test_search_videos_success(self, mock_get: MagicMock) -> None:
        """Test successful video search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "abc123"},
                    "snippet": {
                        "title": "Test Video",
                        "description": "Test description",
                        "channelTitle": "Test Channel",
                        "channelId": "UCtest",
                        "publishedAt": "2025-01-15T00:00:00Z",
                        "thumbnails": {
                            "high": {"url": "https://i.ytimg.com/vi/JlmK_d7KDoQ/maxresdefault.jpg"}
                        },
                    },
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        researcher = YouTubeResearcher(api_key="test_key")

        # Mock the stats call
        with patch.object(researcher, "_get_video_stats") as mock_stats:
            mock_stats.return_value = {"abc123": {"view_count": 1000}}
            results = researcher.search_videos("test", max_results=1)

        assert len(results) == 1
        assert results[0]["video_id"] == "abc123"
        assert results[0]["title"] == "Test Video"

    def test_get_trending_keywords(self) -> None:
        """Test trending keyword extraction."""
        researcher = YouTubeResearcher(api_key="test_key")

        with patch.object(researcher, "search_videos") as mock_search:
            mock_search.return_value = [
                {
                    "title": "Amazing AI Technology Breakthrough",
                    "description": "Check out this #amazing #technology",
                },
                {
                    "title": "How to Use Machine Learning",
                    "description": "Learn #machinelearning basics",
                },
            ]

            keywords = researcher.get_trending_keywords(["AI"], max_keywords=10)

            assert isinstance(keywords, list)

    def test_generate_insights(self) -> None:
        """Test insight generation from video data."""
        researcher = YouTubeResearcher()

        videos = [
            {"title": "Short Title", "view_count": 10000, "like_count": 500},
            {"title": "A Much Longer Video Title Here", "view_count": 50000, "like_count": 2500},
            {"title": "Medium Title Here", "view_count": 25000, "like_count": 1000},
        ]

        insights = researcher._generate_insights(videos, [])

        assert "avg_views" in insights
        assert "avg_likes" in insights
        assert "avg_title_length" in insights
        assert insights["avg_views"] > 0

    def test_generate_insights_empty(self) -> None:
        """Test insight generation with empty data."""
        researcher = YouTubeResearcher()
        insights = researcher._generate_insights([], [])
        assert insights == {}

    @patch("httpx.Client.get")
    def test_cache_persist_reuses_results_after_restart(
        self,
        mock_get: MagicMock,
        tmp_path,
    ) -> None:
        """Persistent cache should survive researcher recreation when TTL is valid."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "abc123"},
                    "snippet": {
                        "title": "Persistent Test",
                        "description": "desc",
                        "channelTitle": "Channel",
                        "channelId": "UC1",
                        "publishedAt": "2026-01-10T00:00:00Z",
                        "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
                    },
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        cache_path = tmp_path / "youtube-cache.json"
        researcher = YouTubeResearcher(
            api_key="test-key",
            cache_ttl_seconds=300,
            cache_path=cache_path,
        )
        with patch.object(researcher, "_get_video_stats", return_value={"abc123": {"view_count": 5}}):
            researcher.search_videos("cache persist query", max_results=1)
        researcher.close()

        assert cache_path.exists()
        mock_get.reset_mock()

        restarted = YouTubeResearcher(
            api_key="test-key",
            cache_ttl_seconds=300,
            cache_path=cache_path,
        )
        with patch.object(restarted, "_get_video_stats") as restarted_stats:
            cached_results = restarted.search_videos("cache persist query", max_results=1)
        restarted.close()

        assert len(cached_results) == 1
        assert mock_get.call_count == 0
        restarted_stats.assert_not_called()

    @patch("httpx.Client.get")
    def test_cache_persist_ttl_expiry_forces_refresh_after_restart(
        self,
        mock_get: MagicMock,
        tmp_path,
    ) -> None:
        """Expired persisted entries should be evicted and refreshed after restart."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "abc123"},
                    "snippet": {
                        "title": "TTL Test",
                        "description": "desc",
                        "channelTitle": "Channel",
                        "channelId": "UC1",
                        "publishedAt": "2026-01-10T00:00:00Z",
                        "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
                    },
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        cache_path = tmp_path / "youtube-cache.json"
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)

        with patch.object(YouTubeResearcher, "_utcnow", return_value=base_time):
            researcher = YouTubeResearcher(
                api_key="test-key",
                cache_ttl_seconds=30,
                cache_path=cache_path,
            )
            with patch.object(researcher, "_get_video_stats", return_value={"abc123": {"view_count": 5}}):
                researcher.search_videos("cache ttl query", max_results=1)
            researcher.close()

        mock_get.reset_mock()
        with patch.object(YouTubeResearcher, "_utcnow", return_value=base_time + timedelta(seconds=45)):
            restarted = YouTubeResearcher(
                api_key="test-key",
                cache_ttl_seconds=30,
                cache_path=cache_path,
            )
            with patch.object(
                restarted, "_get_video_stats", return_value={"abc123": {"view_count": 5}}
            ) as restarted_stats:
                restarted.search_videos("cache ttl query", max_results=1)
            restarted.close()

        assert mock_get.call_count == 1
        assert restarted_stats.call_count == 1


class TestResearchQueryDerivation:
    """Tests for transcript-driven research query derivation."""

    def test_query_derivation_uses_metadata_topics_with_transcript_context(self) -> None:
        """Metadata topics should remain primary when transcript evidence is present."""
        transcript = {
            "text": (
                "This episode explains creator retention framework design and "
                "podcast growth loops with practical examples."
            ),
            "segments": [
                {"text": "creator retention framework in action"},
                {"text": "podcast growth loops and repeatable hooks"},
            ],
        }

        query, related_topics, source = YouTubeResearcher.derive_query_terms(
            transcript_data=transcript,
            metadata_topics=["Creator Retention Framework", "Podcast Growth Loops"],
            fallback_query="episode_42",
        )

        assert query == "creator retention framework"
        assert source in {"metadata_topics", "metadata+transcript"}
        assert "podcast growth loops" in related_topics

    def test_query_derivation_extracts_transcript_topics_when_metadata_missing(self) -> None:
        """Transcript token/phrase weighting should provide deterministic topic queries."""
        transcript = {
            "text": (
                "customer retention loop customer retention loop customer retention loop "
                "for subscription podcasts"
            ),
            "segments": [{"text": "customer retention loop strategy for subscription podcasts"}],
        }

        query, related_topics, source = YouTubeResearcher.derive_query_terms(
            transcript_data=transcript,
            metadata_topics=[],
            fallback_query="job-991",
        )

        assert source == "transcript_topics"
        assert "customer" in query
        assert "retention" in query
        assert related_topics

    def test_query_derivation_returns_labeled_fallback_for_sparse_transcript(self) -> None:
        """Sparse transcript evidence should produce explicit fallback labels."""
        query, related_topics, source = YouTubeResearcher.derive_query_terms(
            transcript_data={"text": "uh um", "segments": [{"text": "uh"}]},
            metadata_topics=[],
            fallback_query="Episode-77_Final",
        )

        assert query == "episode 77 final"
        assert related_topics == []
        assert source.startswith("fallback_")


class TestViralClipDetector:
    """Tests for viral clip detection."""

    def test_detector_init(self) -> None:
        """Test detector initialization."""
        detector = ViralClipDetector()
        assert detector is not None
        assert len(detector._compiled_hook_patterns) > 0

    def test_analyze_transcript_empty(self) -> None:
        """Test analyzing empty transcript."""
        detector = ViralClipDetector()
        signals = detector.analyze_transcript({"segments": [], "text": ""})
        assert signals == []

    def test_analyze_transcript_with_hook(self) -> None:
        """Test detecting hooks in transcript."""
        detector = ViralClipDetector()

        transcript = {
            "segments": [
                {
                    "text": "Here's why nobody talks about this secret technique",
                    "start": 0.0,
                    "end": 5.0,
                },
            ],
            "text": "Here's why nobody talks about this secret technique",
        }

        signals = detector.analyze_transcript(transcript)

        # Should detect hook patterns
        hook_signals = [s for s in signals if s.signal_type == "hook"]
        assert len(hook_signals) > 0

    def test_analyze_transcript_with_emotional_words(self) -> None:
        """Test detecting emotional words."""
        detector = ViralClipDetector()

        transcript = {
            "segments": [
                {
                    "text": "This is absolutely amazing and incredible breakthrough",
                    "start": 10.0,
                    "end": 15.0,
                },
            ],
            "text": "This is absolutely amazing and incredible breakthrough",
        }

        signals = detector.analyze_transcript(transcript)

        emotional_signals = [s for s in signals if s.signal_type == "emotional_peak"]
        assert len(emotional_signals) > 0

    def test_analyze_speech_patterns_dramatic_pause(self) -> None:
        """Test detecting dramatic pauses."""
        detector = ViralClipDetector()

        segments = [
            {"text": "Something important", "start": 0.0, "end": 3.0},
            {"text": "Then the reveal", "start": 6.0, "end": 9.0},  # 3 second gap
        ]

        signals = detector._analyze_speech_patterns(segments)

        pause_signals = [s for s in signals if s.signal_type == "dramatic_pause"]
        assert len(pause_signals) >= 1

    def test_score_clip_basic(self) -> None:
        """Test basic clip scoring."""
        detector = ViralClipDetector()

        clip_data = {
            "start_seconds": 0,
            "end_seconds": 45,
            "description": "Test clip",
            "suggested_hook": "Here's why",
        }

        transcript = {
            "segments": [
                {
                    "text": "Here's why this is important",
                    "start": 0.0,
                    "end": 5.0,
                },
            ],
            "text": "Here's why this is important",
        }

        score = detector.score_clip(clip_data, transcript)

        assert isinstance(score, ViralScore)
        assert 0 <= score.overall_score <= 10
        assert 0 <= score.hook_score <= 10
        assert 0 <= score.emotional_score <= 10
        assert 0 <= score.shareability_score <= 10

    def test_calculate_hook_score_with_early_hook(self) -> None:
        """Test hook score with early hook."""
        detector = ViralClipDetector()

        signals = [
            EngagementSignal(
                timestamp_seconds=5.0,
                signal_type="hook",
                strength=0.9,
                description="Strong hook",
                keywords=["hook"],
            )
        ]

        score = detector._calculate_hook_score(signals, clip_start=0.0)
        assert score >= 7.0  # Should be high with strong early hook

    def test_calculate_hook_score_no_hook(self) -> None:
        """Test hook score without hooks."""
        detector = ViralClipDetector()
        score = detector._calculate_hook_score([], clip_start=0.0)
        assert score == 4.0  # Baseline score

    def test_optimal_length_calculation(self) -> None:
        """Test optimal clip length calculation."""
        detector = ViralClipDetector()

        signals = [
            EngagementSignal(
                timestamp_seconds=30.0,
                signal_type="punchline",
                strength=0.8,
                description="Conclusion",
                keywords=["conclusion"],
            )
        ]

        optimal = detector._get_optimal_length(signals, current_duration=60)

        # Should suggest ending shortly after the punchline
        assert optimal <= 60
        assert optimal >= 30

    def test_suggest_clips_empty_transcript(self) -> None:
        """Test suggesting clips from empty transcript."""
        detector = ViralClipDetector()

        clips = detector.suggest_clips({"segments": [], "text": ""})
        assert clips == []

    def test_clips_overlap_detection(self) -> None:
        """Test overlap detection between clips."""
        detector = ViralClipDetector()

        # High overlap - 20 seconds overlap out of 30 = 66%
        clip1 = {"start_seconds": 0, "end_seconds": 30}
        clip2 = {"start_seconds": 10, "end_seconds": 40}
        clip3 = {"start_seconds": 60, "end_seconds": 90}

        assert detector._clips_overlap(clip1, clip2) is True  # 66% overlap > 50% threshold
        assert detector._clips_overlap(clip1, clip3) is False  # No overlap

    def test_format_timestamp(self) -> None:
        """Test timestamp formatting."""
        detector = ViralClipDetector()

        assert detector._format_timestamp(0) == "00:00"
        assert detector._format_timestamp(65) == "01:05"
        assert detector._format_timestamp(3661) == "61:01"

    def test_generate_reasons(self) -> None:
        """Test reason generation."""
        detector = ViralClipDetector()

        reasons = detector._generate_reasons(
            hook_score=8.0,
            emotional_score=7.5,
            shareability_score=6.0,
            signals=[],
        )

        assert isinstance(reasons, list)
        assert len(reasons) > 0


class TestResearchResult:
    """Tests for ResearchResult model."""

    def test_research_result_defaults(self) -> None:
        """Test ResearchResult default values."""
        result = ResearchResult(query="test")

        assert result.query == "test"
        assert result.topics == []
        assert result.trending_videos == []
        assert result.suggested_keywords == []
        assert result.insights == {}

    def test_research_result_with_data(self) -> None:
        """Test ResearchResult with data."""
        result = ResearchResult(
            query="AI podcast",
            trending_videos=[{"video_id": "abc123", "title": "Test"}],
            suggested_keywords=["artificial", "intelligence"],
            insights={"avg_views": 10000},
        )

        assert len(result.trending_videos) == 1
        assert len(result.suggested_keywords) == 2
        assert result.insights["avg_views"] == 10000
