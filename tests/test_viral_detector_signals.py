"""Tests for expanded viral detector signal taxonomy and scoring behavior."""

from podcast_pipeline.research.viral_detector import EngagementSignal, ViralClipDetector


def test_analyze_transcript_detects_question_controversy_story_and_quotable_signals() -> None:
    """Detector should emit the new phase-2 signal categories."""
    detector = ViralClipDetector()
    transcript = {
        "segments": [
            {"start": 0.0, "end": 4.0, "text": "Why are most creators still doing this the hard way?"},
            {
                "start": 5.0,
                "end": 10.0,
                "text": "This is a controversial take and plenty of people disagree with me.",
            },
            {
                "start": 11.0,
                "end": 18.0,
                "text": "At first we were stuck, then the tension spiked, and finally we resolved it.",
            },
            {
                "start": 19.0,
                "end": 23.0,
                "text": "If you cannot explain it clearly, you do not understand it.",
            },
        ]
    }

    signals = detector.analyze_transcript(transcript)
    signal_types = {signal.signal_type for signal in signals}

    assert "question" in signal_types
    assert "controversy" in signal_types
    assert "story_arc" in signal_types
    assert "quotable" in signal_types


def test_score_clip_adds_engagement_density_component() -> None:
    """High signal density should increase overall score in the same time window."""
    detector = ViralClipDetector()
    clip = {
        "start_seconds": 0,
        "end_seconds": 45,
        "description": "Clip with changing signal density",
        "suggested_hook": "why it matters",
    }
    transcript = {"segments": []}

    low_density_signals = [
        EngagementSignal(
            timestamp_seconds=2.0,
            signal_type="hook",
            strength=0.6,
            description="basic hook",
            keywords=["hook"],
        )
    ]
    high_density_signals = [
        EngagementSignal(2.0, "hook", 0.8, "hook", ["hook"]),
        EngagementSignal(5.0, "question", 0.8, "question", ["why"]),
        EngagementSignal(11.0, "controversy", 0.75, "controversy", ["debate"]),
        EngagementSignal(18.0, "story_arc", 0.72, "story", ["setup"]),
        EngagementSignal(23.0, "story_arc", 0.72, "story", ["resolution"]),
        EngagementSignal(31.0, "quotable", 0.78, "quote", ["clarity"]),
        EngagementSignal(37.0, "punchline", 0.8, "punchline", ["bottom line"]),
    ]

    low_score = detector.score_clip(clip, transcript, low_density_signals)
    high_score = detector.score_clip(clip, transcript, high_density_signals)

    assert high_score.engagement_density_score > low_score.engagement_density_score
    assert high_score.overall_score > low_score.overall_score
    assert 0 <= low_score.overall_score <= 10
    assert 0 <= high_score.overall_score <= 10


def test_score_clip_bounds_hold_for_short_and_long_clips() -> None:
    """Clip scoring remains in the 0-10 range regardless of duration extremes."""
    detector = ViralClipDetector()
    transcript = {"segments": []}
    dense_signals = [
        EngagementSignal(1.0, "hook", 1.0, "hook", ["hook"]),
        EngagementSignal(2.0, "question", 0.9, "question", ["why"]),
        EngagementSignal(3.0, "controversy", 0.9, "controversy", ["debate"]),
        EngagementSignal(4.0, "story_arc", 0.9, "story", ["tension"]),
        EngagementSignal(5.0, "quotable", 0.9, "quote", ["clarity"]),
    ]

    short_clip = {
        "start_seconds": 0,
        "end_seconds": 8,
        "description": "Very short clip",
        "suggested_hook": "stop doing this",
    }
    long_clip = {
        "start_seconds": 0,
        "end_seconds": 240,
        "description": "Very long clip",
        "suggested_hook": "here is why",
    }

    short_score = detector.score_clip(short_clip, transcript, dense_signals)
    long_score = detector.score_clip(long_clip, transcript, dense_signals)

    assert 0 <= short_score.overall_score <= 10
    assert 0 <= long_score.overall_score <= 10
    assert 0 <= short_score.engagement_density_score <= 10
    assert 0 <= long_score.engagement_density_score <= 10


def test_score_reasons_include_new_signal_categories() -> None:
    """Reason strings should mention new signal categories when present."""
    detector = ViralClipDetector()
    clip = {
        "start_seconds": 0,
        "end_seconds": 60,
        "description": "Reason coverage clip",
        "suggested_hook": "nobody talks about this",
    }
    transcript = {"segments": []}
    signals = [
        EngagementSignal(1.0, "question", 0.8, "question", ["why"]),
        EngagementSignal(8.0, "controversy", 0.8, "controversy", ["debate"]),
        EngagementSignal(15.0, "story_arc", 0.75, "story", ["setup"]),
        EngagementSignal(20.0, "quotable", 0.75, "quote", ["understand"]),
        EngagementSignal(30.0, "punchline", 0.75, "punchline", ["takeaway"]),
    ]

    score = detector.score_clip(clip, transcript, signals)
    reason_text = " ".join(score.reasons).lower()

    assert "interrogative" in reason_text
    assert "controversy" in reason_text
    assert "story arc" in reason_text
    assert "quotable" in reason_text
