"""Advanced viral clip detection using engagement pattern analysis."""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EngagementSignal:
    """A detected engagement signal in the content."""

    timestamp_seconds: float
    signal_type: str  # hook, question, controversy, story_arc, quotable, etc.
    strength: float  # 0.0 to 1.0
    description: str
    keywords: list[str]


class ViralScore(BaseModel):
    """Viral potential score for a clip."""

    overall_score: float = Field(ge=0, le=10)
    hook_score: float = Field(ge=0, le=10)
    emotional_score: float = Field(ge=0, le=10)
    shareability_score: float = Field(ge=0, le=10)
    engagement_density_score: float = Field(ge=0, le=10)
    engagement_signals: list[dict[str, Any]] = Field(default_factory=list)
    optimal_length_seconds: int = 45
    suggested_start_adjustment: float = 0.0
    suggested_end_adjustment: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class ViralClipDetector:
    """Advanced viral clip detection using NLP and engagement patterns."""

    # Patterns that indicate high engagement potential
    HOOK_PATTERNS = [
        r"(?:here's|this is)\s+(?:the|why|how|what)",
        r"nobody\s+(?:talks about|knows|expected)",
        r"the (?:truth|secret|real reason)",
        r"you (?:won't|wouldn't) believe",
        r"this (?:changed|blew|shocked)",
        r"(?:unpopular|hot) (?:take|opinion)",
        r"stop (?:doing|saying|believing)",
        r"why (?:everyone|most people)",
        r"the (?:biggest|worst|best) (?:mistake|secret|tip)",
    ]

    EMOTIONAL_WORDS = {
        "high_positive": [
            "amazing",
            "incredible",
            "breakthrough",
            "revolutionary",
            "life-changing",
            "mind-blowing",
        ],
        "high_negative": ["terrible", "disaster", "worst", "horrible", "shocking", "outrageous"],
        "controversy": ["controversial", "debate", "unpopular", "disagree", "wrong", "myth"],
        "curiosity": ["secret", "hidden", "unknown", "discover", "reveal", "truth"],
        "urgency": ["now", "immediately", "urgent", "critical", "must", "need"],
    }

    PUNCHLINE_INDICATORS = [
        "and that's",
        "the point is",
        "bottom line",
        "here's the thing",
        "the takeaway",
        "what this means",
        "so basically",
        "in other words",
    ]

    QUESTION_OPENERS = {"why", "how", "what", "when", "who", "which", "should", "can", "could"}
    CONTROVERSY_TERMS = {
        "controversial",
        "debate",
        "disagree",
        "myth",
        "wrong",
        "hot take",
        "unpopular",
        "argument",
        "critics",
        "vs",
    }
    STORY_ARC_CUES = {
        "setup": {"at first", "initially", "in the beginning", "we started", "once"},
        "tension": {"but then", "however", "tension", "problem", "struggle", "conflict"},
        "resolution": {"finally", "in the end", "resolved", "we learned", "therefore"},
    }

    def __init__(self) -> None:
        """Initialize the viral detector."""
        self._compiled_hook_patterns = [re.compile(p, re.IGNORECASE) for p in self.HOOK_PATTERNS]

    def analyze_transcript(
        self,
        transcript_data: dict[str, Any],
    ) -> list[EngagementSignal]:
        """Analyze transcript for engagement signals.

        Args:
            transcript_data: Transcript with segments

        Returns:
            List of engagement signals
        """
        signals: list[EngagementSignal] = []

        segments = transcript_data.get("segments", [])

        for segment in segments:
            text = segment.get("text", "")
            start = segment.get("start", 0)
            text_lower = text.lower()

            # Check for hook patterns
            for pattern in self._compiled_hook_patterns:
                if pattern.search(text):
                    signals.append(
                        EngagementSignal(
                            timestamp_seconds=start,
                            signal_type="hook",
                            strength=0.8,
                            description=f"Strong hook detected: '{text[:50]}...'",
                            keywords=pattern.findall(text),
                        )
                    )
                    break

            # Check for question hooks
            if self._is_question_signal(text):
                leading_word = text_lower.strip().split(" ", 1)[0].strip(" ,.!?\"'")
                signals.append(
                    EngagementSignal(
                        timestamp_seconds=start,
                        signal_type="question",
                        strength=0.78,
                        description=f"Question hook detected: '{text[:60]}...'",
                        keywords=[leading_word if leading_word in self.QUESTION_OPENERS else "?"],
                    )
                )

            # Check for controversy language
            matched_controversy = [
                term for term in self.CONTROVERSY_TERMS if re.search(rf"\b{re.escape(term)}\b", text_lower)
            ]
            if matched_controversy:
                signals.append(
                    EngagementSignal(
                        timestamp_seconds=start,
                        signal_type="controversy",
                        strength=0.8,
                        description=f"Controversy cue: {', '.join(matched_controversy[:2])}",
                        keywords=matched_controversy[:3],
                    )
                )

            # Check story arc progression cues
            story_arc_signals = self._detect_story_arc_signals(text_lower)
            for stage, cue in story_arc_signals:
                signals.append(
                    EngagementSignal(
                        timestamp_seconds=start,
                        signal_type="story_arc",
                        strength=0.72,
                        description=f"Story arc ({stage}) cue: '{cue}'",
                        keywords=[stage, cue],
                    )
                )

            # Check for quotable one-liners
            if self._is_quotable_signal(text):
                signals.append(
                    EngagementSignal(
                        timestamp_seconds=start,
                        signal_type="quotable",
                        strength=0.74,
                        description=f"Quotable line candidate: '{text[:60]}...'",
                        keywords=self._extract_keywords(text_lower),
                    )
                )

            # Check for emotional words
            for emotion_type, words in self.EMOTIONAL_WORDS.items():
                for word in words:
                    if word in text_lower:
                        strength = (
                            0.9 if emotion_type in ["high_positive", "high_negative"] else 0.7
                        )
                        signals.append(
                            EngagementSignal(
                                timestamp_seconds=start,
                                signal_type="emotional_peak",
                                strength=strength,
                                description=f"{emotion_type}: '{word}' detected",
                                keywords=[word],
                            )
                        )

            # Check for punchline indicators
            for indicator in self.PUNCHLINE_INDICATORS:
                if indicator in text_lower:
                    signals.append(
                        EngagementSignal(
                            timestamp_seconds=start,
                            signal_type="punchline",
                            strength=0.75,
                            description=f"Punchline indicator: '{indicator}'",
                            keywords=[indicator],
                        )
                    )

        # Analyze speech patterns (pauses, emphasis)
        signals.extend(self._analyze_speech_patterns(segments))

        # Sort by timestamp
        signals.sort(key=lambda x: x.timestamp_seconds)

        return signals

    def _is_question_signal(self, text: str) -> bool:
        """Check if segment likely acts as an interrogative hook."""
        stripped = text.strip()
        if not stripped:
            return False

        if stripped.endswith("?"):
            return True

        first_word = stripped.lower().split(" ", 1)[0].strip(" ,.!?\"'")
        return first_word in self.QUESTION_OPENERS

    def _detect_story_arc_signals(self, text_lower: str) -> list[tuple[str, str]]:
        """Detect setup/tension/resolution cues within a segment."""
        found: list[tuple[str, str]] = []
        for stage, cues in self.STORY_ARC_CUES.items():
            for cue in cues:
                if cue in text_lower:
                    found.append((stage, cue))
                    break
        return found

    def _is_quotable_signal(self, text: str) -> bool:
        """Heuristic for concise lines likely to be quote-worthy."""
        stripped = text.strip()
        if not stripped:
            return False
        word_count = len(re.findall(r"[A-Za-z']+", stripped))
        if word_count < 6 or word_count > 22:
            return False
        if stripped.endswith("?"):
            return False
        # Quotables often contain imperative/definitive phrasing.
        return bool(
            re.search(
                r"\b(you|we|i)\b.*\b(should|must|need|can't|cannot|don't|do not|will|is|are)\b",
                stripped.lower(),
            )
        )

    def _extract_keywords(self, text_lower: str, limit: int = 4) -> list[str]:
        """Extract lightweight keywords for signal explanation."""
        candidates = re.findall(r"[a-z']+", text_lower)
        filtered = [word for word in candidates if len(word) > 3]
        deduped: list[str] = []
        for word in filtered:
            if word not in deduped:
                deduped.append(word)
            if len(deduped) >= limit:
                break
        return deduped

    def _analyze_speech_patterns(
        self,
        segments: list[dict[str, Any]],
    ) -> list[EngagementSignal]:
        """Analyze speech patterns for engagement signals.

        Args:
            segments: Transcript segments with timing

        Returns:
            Additional engagement signals
        """
        signals: list[EngagementSignal] = []

        for i, segment in enumerate(segments[:-1]):
            # Check for dramatic pauses (gaps between segments)
            current_end = segment.get("end", 0)
            next_start = segments[i + 1].get("start", 0)
            gap = next_start - current_end

            if gap > 1.5:  # More than 1.5 second pause
                signals.append(
                    EngagementSignal(
                        timestamp_seconds=current_end,
                        signal_type="dramatic_pause",
                        strength=min(gap / 3.0, 1.0),  # Scale by pause length
                        description=f"Dramatic pause ({gap:.1f}s) for emphasis",
                        keywords=["pause", "emphasis"],
                    )
                )

        return signals

    def score_clip(
        self,
        clip_data: dict[str, Any],
        transcript_data: dict[str, Any],
        signals: list[EngagementSignal] | None = None,
    ) -> ViralScore:
        """Score a clip's viral potential.

        Args:
            clip_data: Clip with start/end times
            transcript_data: Full transcript data
            signals: Pre-analyzed signals (optional)

        Returns:
            Viral score for the clip
        """
        start = clip_data.get("start_seconds", 0)
        end = clip_data.get("end_seconds", 60)
        duration = end - start

        if signals is None:
            signals = self.analyze_transcript(transcript_data)

        # Filter signals within clip range
        clip_signals = [s for s in signals if start <= s.timestamp_seconds <= end]

        # Calculate component scores
        hook_score = self._calculate_hook_score(clip_signals, start)
        emotional_score = self._calculate_emotional_score(clip_signals)
        shareability_score = self._calculate_shareability_score(clip_data, duration)
        engagement_density_score = self._calculate_engagement_density_score(clip_signals, duration)

        # Calculate overall score with explicit engagement-density contribution.
        overall_score = (
            hook_score * 0.30
            + emotional_score * 0.25
            + shareability_score * 0.20
            + engagement_density_score * 0.25
        )
        overall_score = min(max(overall_score, 0.0), 10.0)

        # Determine optimal length
        optimal_length = self._get_optimal_length(clip_signals, duration)

        # Get adjustment suggestions
        start_adj, end_adj = self._suggest_adjustments(clip_signals, start, end)

        reasons = self._generate_reasons(
            hook_score,
            emotional_score,
            shareability_score,
            clip_signals,
            engagement_density_score=engagement_density_score,
        )

        return ViralScore(
            overall_score=round(overall_score, 1),
            hook_score=round(hook_score, 1),
            emotional_score=round(emotional_score, 1),
            shareability_score=round(shareability_score, 1),
            engagement_density_score=round(engagement_density_score, 1),
            engagement_signals=[
                {
                    "timestamp": s.timestamp_seconds,
                    "type": s.signal_type,
                    "strength": s.strength,
                    "description": s.description,
                }
                for s in clip_signals
            ],
            optimal_length_seconds=optimal_length,
            suggested_start_adjustment=start_adj,
            suggested_end_adjustment=end_adj,
            reasons=reasons,
        )

    def _calculate_hook_score(
        self,
        signals: list[EngagementSignal],
        clip_start: float,
    ) -> float:
        """Calculate hook strength score."""
        # Look for hooks in the first 10 seconds
        early_hooks = [
            s for s in signals if s.signal_type == "hook" and s.timestamp_seconds - clip_start < 10
        ]

        if not early_hooks:
            return 4.0  # Baseline

        max_strength = max(s.strength for s in early_hooks)
        return min(4.0 + max_strength * 6.0, 10.0)

    def _calculate_emotional_score(
        self,
        signals: list[EngagementSignal],
    ) -> float:
        """Calculate emotional intensity score."""
        emotional_signals = [
            s for s in signals if s.signal_type in ["emotional_peak", "dramatic_pause"]
        ]

        if not emotional_signals:
            return 4.0  # Baseline

        avg_strength = sum(s.strength for s in emotional_signals) / len(emotional_signals)
        density_bonus = min(len(emotional_signals) * 0.5, 2.0)

        return min(4.0 + avg_strength * 4.0 + density_bonus, 10.0)

    def _calculate_shareability_score(
        self,
        clip_data: dict[str, Any],
        duration: float,
    ) -> float:
        """Calculate shareability score based on clip properties."""
        score = 5.0  # Baseline

        # Optimal duration (15-60 seconds is ideal)
        if 15 <= duration <= 60:
            score += 2.0
        elif 60 < duration <= 90:
            score += 1.0
        elif duration < 15:
            score -= 1.0
        elif duration > 120:
            score -= 2.0

        # Has a clear description/topic
        if clip_data.get("description"):
            score += 1.0

        # Has a suggested hook
        if clip_data.get("suggested_hook"):
            score += 1.5

        return min(max(score, 0.0), 10.0)

    def _calculate_engagement_density_score(
        self,
        signals: list[EngagementSignal],
        duration: float,
    ) -> float:
        """Calculate weighted signal density per minute."""
        if duration <= 0:
            return 0.0

        minutes = max(duration / 60.0, 0.25)
        weighted_signal_strength = sum(signal.strength for signal in signals)
        density = weighted_signal_strength / minutes
        unique_types = len({signal.signal_type for signal in signals})
        diversity_bonus = min(unique_types * 0.25, 1.0)

        score = 3.5 + density * 0.9 + diversity_bonus
        return min(max(score, 0.0), 10.0)

    def _get_optimal_length(
        self,
        signals: list[EngagementSignal],
        current_duration: float,
    ) -> int:
        """Determine optimal clip length."""
        # Find punchlines
        punchlines = [s for s in signals if s.signal_type == "punchline"]

        if punchlines:
            # End shortly after the last punchline
            last_punchline = max(s.timestamp_seconds for s in punchlines)
            return min(int(last_punchline + 5), 90)

        # Default optimal lengths by platform
        if current_duration <= 60:
            return 45  # TikTok optimal
        elif current_duration <= 90:
            return 60  # Instagram Reels
        else:
            return 90  # YouTube Shorts max

    def _suggest_adjustments(
        self,
        signals: list[EngagementSignal],
        start: float,
        end: float,
    ) -> tuple[float, float]:
        """Suggest start/end time adjustments for better engagement."""
        start_adj = 0.0
        end_adj = 0.0

        # Find first hook - start just before it
        hooks = [s for s in signals if s.signal_type == "hook"]
        if hooks:
            first_hook = min(s.timestamp_seconds for s in hooks)
            if first_hook - start > 5:  # Hook is more than 5s in
                start_adj = first_hook - start - 2  # Start 2s before hook

        # Find last punchline - end shortly after
        punchlines = [s for s in signals if s.signal_type == "punchline"]
        if punchlines:
            last_punchline = max(s.timestamp_seconds for s in punchlines)
            if end - last_punchline > 10:  # Too much content after punchline
                end_adj = -(end - last_punchline - 5)  # End 5s after punchline

        return start_adj, end_adj

    def _generate_reasons(
        self,
        hook_score: float,
        emotional_score: float,
        shareability_score: float,
        signals: list[EngagementSignal],
        engagement_density_score: float = 5.0,
    ) -> list[str]:
        """Generate human-readable reasons for the score."""
        reasons = []

        if hook_score >= 7:
            reasons.append("Strong opening hook captures attention immediately")
        elif hook_score < 5:
            reasons.append("Consider adding a stronger hook in the first 10 seconds")

        if emotional_score >= 7:
            reasons.append("High emotional engagement throughout the clip")
        elif emotional_score < 5:
            reasons.append("Could benefit from more emotional moments or emphasis")

        if shareability_score >= 7:
            reasons.append("Good length and structure for social sharing")
        elif shareability_score < 5:
            reasons.append("Consider trimming for better social media fit")

        if engagement_density_score >= 7:
            reasons.append("Dense concentration of engagement cues throughout the clip")
        elif engagement_density_score < 5:
            reasons.append("Signal density is light; strengthen setup, tension, and payoff")

        # Specific signal-based reasons
        hook_count = len([s for s in signals if s.signal_type == "hook"])
        if hook_count > 1:
            reasons.append(f"Multiple attention hooks ({hook_count}) maintain viewer interest")

        punchline_count = len([s for s in signals if s.signal_type == "punchline"])
        if punchline_count > 0:
            reasons.append(f"Clear punchline/conclusion ({punchline_count} found)")

        question_count = len([s for s in signals if s.signal_type == "question"])
        if question_count > 0:
            reasons.append(f"Interrogative hooks ({question_count}) invite audience response")

        controversy_count = len([s for s in signals if s.signal_type == "controversy"])
        if controversy_count > 0:
            reasons.append(f"Controversy cues ({controversy_count}) increase comment potential")

        story_arc_count = len([s for s in signals if s.signal_type == "story_arc"])
        if story_arc_count > 0:
            reasons.append(f"Story arc progression signals ({story_arc_count}) improve retention")

        quotable_count = len([s for s in signals if s.signal_type == "quotable"])
        if quotable_count > 0:
            reasons.append(f"Quotable moments ({quotable_count}) support shareability")

        return reasons

    def suggest_clips(
        self,
        transcript_data: dict[str, Any],
        min_duration: int = 15,
        max_duration: int = 90,
        min_score: float = 6.0,
        max_clips: int = 5,
    ) -> list[dict[str, Any]]:
        """Automatically suggest viral clip candidates from transcript.

        Args:
            transcript_data: Full transcript data
            min_duration: Minimum clip duration in seconds
            max_duration: Maximum clip duration in seconds
            min_score: Minimum viral score to include
            max_clips: Maximum number of clips to return

        Returns:
            List of suggested clip candidates with scores
        """
        signals = self.analyze_transcript(transcript_data)

        if not signals:
            return []

        # Group signals into potential clips
        candidates: list[dict[str, Any]] = []

        # Use hooks as clip start points
        hooks = [s for s in signals if s.signal_type == "hook"]

        for hook in hooks:
            start = max(0, hook.timestamp_seconds - 2)  # Start 2s before hook

            # Find good end point (punchline or natural break)
            punchlines_after = [
                s for s in signals if s.signal_type == "punchline" and s.timestamp_seconds > start
            ]

            if punchlines_after:
                # End after nearest punchline within range
                for p in sorted(punchlines_after, key=lambda x: x.timestamp_seconds):
                    duration = p.timestamp_seconds - start + 3
                    if min_duration <= duration <= max_duration:
                        end = p.timestamp_seconds + 3
                        break
                else:
                    end = start + max_duration
            else:
                # Default to max duration
                end = start + max_duration

            clip_data = {
                "start_seconds": start,
                "end_seconds": end,
                "description": hook.description,
                "suggested_hook": hook.keywords[0] if hook.keywords else "",
            }

            score = self.score_clip(clip_data, transcript_data, signals)

            if score.overall_score >= min_score:
                candidates.append(
                    {
                        "start": self._format_timestamp(start),
                        "end": self._format_timestamp(end),
                        "start_seconds": start,
                        "end_seconds": end,
                        "description": hook.description,
                        "viral_score": score.overall_score,
                        "score_details": score.model_dump(),
                    }
                )

        # Sort by score and return top clips
        candidates.sort(key=lambda x: x["viral_score"], reverse=True)

        # Remove overlapping clips (keep highest scored)
        final_clips: list[dict[str, Any]] = []
        for candidate in candidates:
            if not any(self._clips_overlap(candidate, existing) for existing in final_clips):
                final_clips.append(candidate)
                if len(final_clips) >= max_clips:
                    break

        return final_clips

    def _clips_overlap(
        self,
        clip1: dict[str, Any],
        clip2: dict[str, Any],
        threshold: float = 0.5,
    ) -> bool:
        """Check if two clips overlap significantly."""
        start1 = float(clip1["start_seconds"])
        end1 = float(clip1["end_seconds"])
        start2 = float(clip2["start_seconds"])
        end2 = float(clip2["end_seconds"])

        overlap_start = max(start1, start2)
        overlap_end = min(end1, end2)

        if overlap_start >= overlap_end:
            return False

        overlap_duration = overlap_end - overlap_start
        min_duration = min(end1 - start1, end2 - start2)

        return bool(overlap_duration / min_duration > threshold)

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as MM:SS."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"
