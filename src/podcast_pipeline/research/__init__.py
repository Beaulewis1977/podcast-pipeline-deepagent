"""Research module for YouTube and trend analysis."""

from podcast_pipeline.research.viral_detector import ViralClipDetector, ViralScore
from podcast_pipeline.research.youtube import ResearchResult, YouTubeResearcher

__all__ = ["ResearchResult", "ViralClipDetector", "ViralScore", "YouTubeResearcher"]
