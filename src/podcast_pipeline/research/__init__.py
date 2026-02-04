"""Research module for YouTube and trend analysis."""

from podcast_pipeline.research.youtube import YouTubeResearcher, ResearchResult
from podcast_pipeline.research.viral_detector import ViralClipDetector, ViralScore

__all__ = ["YouTubeResearcher", "ResearchResult", "ViralClipDetector", "ViralScore"]
