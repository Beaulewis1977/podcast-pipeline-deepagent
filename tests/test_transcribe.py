"""Tests for TranscribeStage — Phase 8 filler enrichment."""

from __future__ import annotations

import pytest

from podcast_pipeline.config import Config
from podcast_pipeline.config.settings import FillerConfig
from podcast_pipeline.models.transcript import Segment, Word
from podcast_pipeline.stages.transcribe import TranscribeStage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_stage(filler_cfg: FillerConfig | None = None) -> TranscribeStage:
    """Build a TranscribeStage with an optionally customised FillerConfig."""
    config = Config()
    if filler_cfg is not None:
        config.fillers = filler_cfg
    return TranscribeStage(config)


def make_segment(words: list[tuple[str, float, float, float]]) -> Segment:
    """Build a Segment from a list of (word, start, end, confidence) tuples.

    Segment start/end are derived from the first/last word.
    """
    word_objs = [Word(word=w, start=s, end=e, confidence=c) for w, s, e, c in words]
    return Segment(
        start=word_objs[0].start,
        end=word_objs[-1].end,
        text=" ".join(w.word for w in word_objs),
        words=word_objs,
    )


# ---------------------------------------------------------------------------
# Category assignment tests
# ---------------------------------------------------------------------------


class TestFillerCategoryAssignment:
    """Verify category field is set correctly for each filler type."""

    def test_detect_fillers_assigns_disfluency_category(self) -> None:
        """Words in the disfluencies list produce category='disfluency'."""
        stage = make_stage()
        segment = make_segment(
            [
                ("Hello", 0.0, 0.5, 0.99),
                ("um", 0.6, 0.9, 0.85),  # long enough: 300ms
                ("there", 1.0, 1.5, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        assert any(c.word == "um" and c.category == "disfluency" for c in cuts), (
            f"Expected a disfluency cut for 'um'; got {cuts}"
        )

    def test_detect_fillers_assigns_hedge_category(self) -> None:
        """Words in the hedge_words list produce category='hedge'."""
        stage = make_stage()
        segment = make_segment(
            [
                ("I", 0.0, 0.2, 0.99),
                ("like", 0.3, 0.7, 0.85),  # 400ms — long enough
                ("that", 0.8, 1.2, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        assert any(c.word == "like" and c.category == "hedge" for c in cuts), (
            f"Expected a hedge cut for 'like'; got {cuts}"
        )

    def test_detect_fillers_assigns_custom_category(self) -> None:
        """Words in custom_words produce category='custom'."""
        cfg = FillerConfig(custom_words=["literally"], disfluencies=[], hedge_words=[])
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("It's", 0.0, 0.4, 0.99),
                ("literally", 0.5, 0.9, 0.90),  # 400ms
                ("amazing", 1.0, 1.5, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        assert any(c.word == "literally" and c.category == "custom" for c in cuts), (
            f"Expected a custom cut for 'literally'; got {cuts}"
        )

    def test_detect_fillers_assigns_hedge_category_multi_word(self) -> None:
        """Multi-word hedge phrase 'you know' produces category='hedge'."""
        stage = make_stage()
        segment = make_segment(
            [
                ("So", 0.0, 0.3, 0.99),
                ("you", 0.4, 0.7, 0.88),
                ("know", 0.7, 1.1, 0.88),  # combined 700ms
                ("right", 1.2, 1.6, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        hedge_cuts = [c for c in cuts if c.word == "you know"]
        assert hedge_cuts, f"Expected multi-word hedge cut; got {cuts}"
        assert hedge_cuts[0].category == "hedge"


# ---------------------------------------------------------------------------
# Backward-compat: words field merges into disfluency set
# ---------------------------------------------------------------------------


class TestBackwardCompatWordsField:
    """Legacy configs using words=[...] still detect fillers correctly."""

    def test_detect_fillers_backward_compat_words_merge(self) -> None:
        """Config with only words=[...] detects fillers; words treated as extra disfluencies."""
        # 'um' is in words -> detected as disfluency (not in default hedge_words)
        cfg = FillerConfig(
            disfluencies=[],
            hedge_words=[],
            custom_words=[],
            words=["um", "like"],
        )
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("Well", 0.0, 0.4, 0.99),
                ("um", 0.5, 0.9, 0.85),  # 400ms
                ("okay", 1.0, 1.4, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        assert any(c.word == "um" for c in cuts), (
            f"'um' via words field should still be detected; got {cuts}"
        )

    def test_detect_fillers_backward_compat_like_in_words_detected_as_disfluency(
        self,
    ) -> None:
        """'like' in words-only config gets disfluency category (no default hedge list)."""
        cfg = FillerConfig(
            disfluencies=[],
            hedge_words=[],
            custom_words=[],
            words=["like"],
        )
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("I", 0.0, 0.2, 0.99),
                ("like", 0.3, 0.7, 0.85),  # 400ms
                ("this", 0.8, 1.2, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        # 'like' is only in words (disfluency bucket), hedge_words is empty
        assert any(c.word == "like" and c.category == "disfluency" for c in cuts), (
            f"'like' from words-only config should be disfluency; got {cuts}"
        )


# ---------------------------------------------------------------------------
# Pause gate tests
# ---------------------------------------------------------------------------


class TestPauseGate:
    """Verify pause-gate protection fires and doesn't fire correctly."""

    def test_detect_fillers_pause_gate_fires(self) -> None:
        """Filler with >=300ms silence before it is marked protected=True."""
        # previous word ends at 0.5, filler starts at 0.9 -> gap = 400ms >= 300ms
        cfg = FillerConfig(protect_pause_threshold_ms=300.0)
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("Hello", 0.0, 0.5, 0.99),
                ("uh", 0.9, 1.2, 0.85),  # 300ms duration; 400ms pause before
                ("world", 1.3, 1.8, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        uh_cuts = [c for c in cuts if c.word == "uh"]
        assert uh_cuts, f"Expected 'uh' cut; got {cuts}"
        cut = uh_cuts[0]
        assert cut.protected is True, f"Expected protected=True; got {cut}"
        assert cut.pause_before_ms >= 300.0, (
            f"Expected pause_before_ms>=300; got {cut.pause_before_ms}"
        )

    def test_detect_fillers_pause_gate_fires_after(self) -> None:
        """Filler with >=300ms silence after it is also marked protected=True."""
        cfg = FillerConfig(protect_pause_threshold_ms=300.0)
        stage = make_stage(cfg)
        # filler ends at 1.1, next word starts at 1.5 -> gap = 400ms
        segment = make_segment(
            [
                ("Hello", 0.0, 0.5, 0.99),
                ("um", 0.6, 1.1, 0.85),  # 500ms duration
                ("world", 1.5, 2.0, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        um_cuts = [c for c in cuts if c.word == "um"]
        assert um_cuts, f"Expected 'um' cut; got {cuts}"
        cut = um_cuts[0]
        assert cut.protected is True
        assert cut.pause_after_ms >= 300.0

    def test_detect_fillers_pause_gate_does_not_fire(self) -> None:
        """Filler with <300ms silence on both sides is not protected."""
        cfg = FillerConfig(protect_pause_threshold_ms=300.0)
        stage = make_stage(cfg)
        # previous word ends 0.45, filler starts 0.5 -> gap = 50ms; next ends 0.9, next starts 0.95 -> gap = 50ms
        segment = make_segment(
            [
                ("Hello", 0.0, 0.45, 0.99),
                ("um", 0.5, 0.85, 0.85),  # 350ms duration; 50ms pause before and after
                ("world", 0.9, 1.5, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        um_cuts = [c for c in cuts if c.word == "um"]
        assert um_cuts, f"Expected 'um' cut; got {cuts}"
        cut = um_cuts[0]
        assert cut.protected is False, f"Expected protected=False; got {cut}"
        assert cut.pause_before_ms < 300.0
        assert cut.pause_after_ms < 300.0

    def test_detect_fillers_pause_gate_boundary_exactly_at_threshold(self) -> None:
        """Filler with exactly threshold pause is protected (>=)."""
        cfg = FillerConfig(protect_pause_threshold_ms=300.0)
        stage = make_stage(cfg)
        # previous word ends 0.5, filler starts 0.8 -> gap = exactly 300ms
        segment = make_segment(
            [
                ("Hey", 0.0, 0.5, 0.99),
                ("uh", 0.8, 1.1, 0.85),  # 300ms; pause_before exactly 300ms
                ("so", 1.2, 1.7, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        uh_cuts = [c for c in cuts if c.word == "uh"]
        assert uh_cuts
        assert uh_cuts[0].protected is True


# ---------------------------------------------------------------------------
# Context extraction tests
# ---------------------------------------------------------------------------


class TestContextExtraction:
    """Verify context_before and context_after fields are populated correctly."""

    def test_detect_fillers_context_extraction(self) -> None:
        """context_before and context_after contain the N words around the filler."""
        cfg = FillerConfig(llm_triage_max_context_words=2)
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("This", 0.0, 0.3, 0.99),
                ("is", 0.3, 0.5, 0.99),
                ("um", 0.6, 0.9, 0.85),  # 300ms
                ("very", 1.0, 1.3, 0.99),
                ("good", 1.3, 1.6, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        um_cuts = [c for c in cuts if c.word == "um"]
        assert um_cuts, f"Expected 'um' cut; got {cuts}"
        cut = um_cuts[0]
        # context_before: last 2 words before filler
        assert cut.context_before == "This is", f"Expected 'This is', got: {cut.context_before!r}"
        assert cut.context_after == "very good", f"Expected 'very good', got: {cut.context_after!r}"

    def test_detect_fillers_context_at_boundaries_first_word(self) -> None:
        """First word in segment has empty context_before."""
        stage = make_stage()
        segment = make_segment(
            [
                ("um", 0.0, 0.5, 0.85),  # 500ms; first word
                ("so", 0.6, 0.9, 0.99),
                ("yeah", 1.0, 1.4, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        um_cuts = [c for c in cuts if c.word == "um"]
        assert um_cuts, f"Expected 'um' cut; got {cuts}"
        assert um_cuts[0].context_before == "", (
            f"First word should have empty context_before; got {um_cuts[0].context_before!r}"
        )
        assert um_cuts[0].pause_before_ms == 0.0, (
            f"First word should have pause_before_ms=0.0; got {um_cuts[0].pause_before_ms}"
        )

    def test_detect_fillers_context_at_boundaries_last_word(self) -> None:
        """Last word in segment has empty context_after."""
        stage = make_stage()
        segment = make_segment(
            [
                ("Well", 0.0, 0.4, 0.99),
                ("okay", 0.5, 0.9, 0.99),
                ("um", 1.0, 1.5, 0.85),  # 500ms; last word
            ]
        )
        cuts = stage._detect_fillers([segment])
        um_cuts = [c for c in cuts if c.word == "um"]
        assert um_cuts, f"Expected 'um' cut; got {cuts}"
        assert um_cuts[0].context_after == "", (
            f"Last word should have empty context_after; got {um_cuts[0].context_after!r}"
        )
        assert um_cuts[0].pause_after_ms == 0.0, (
            f"Last word should have pause_after_ms=0.0; got {um_cuts[0].pause_after_ms}"
        )

    def test_detect_fillers_context_respects_n_window(self) -> None:
        """context_before contains at most N words even when more are available."""
        cfg = FillerConfig(llm_triage_max_context_words=2)
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("a", 0.0, 0.2, 0.99),
                ("b", 0.2, 0.4, 0.99),
                ("c", 0.4, 0.6, 0.99),
                ("um", 0.7, 1.0, 0.85),  # 300ms
                ("d", 1.1, 1.3, 0.99),
                ("e", 1.3, 1.5, 0.99),
                ("f", 1.5, 1.7, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        um_cuts = [c for c in cuts if c.word == "um"]
        assert um_cuts
        cut = um_cuts[0]
        # With N=2, context_before should be "b c" (last 2 words), not "a b c"
        before_words = cut.context_before.split()
        after_words = cut.context_after.split()
        assert len(before_words) <= 2, f"context_before exceeds N=2: {cut.context_before!r}"
        assert len(after_words) <= 2, f"context_after exceeds N=2: {cut.context_after!r}"


# ---------------------------------------------------------------------------
# Padding vs raw timestamp tests
# ---------------------------------------------------------------------------


class TestPaddingVsRawTimestamps:
    """Verify padding affects start/end but pause timing uses raw word timestamps."""

    def test_padding_applied_to_cut_times(self) -> None:
        """FillerCut start/end include padding_ms; pause timing uses raw times."""
        cfg = FillerConfig(padding_ms=50, protect_pause_threshold_ms=300.0)
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("Hello", 0.0, 0.45, 0.99),
                ("um", 0.5, 0.85, 0.85),  # raw start=0.5, raw end=0.85
                ("world", 0.9, 1.5, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        um_cuts = [c for c in cuts if c.word == "um"]
        assert um_cuts
        cut = um_cuts[0]
        # start should be raw 0.5 - 0.05 = 0.45
        assert cut.start == pytest.approx(0.45, abs=0.01)
        # end should be raw 0.85 + 0.05 = 0.90
        assert cut.end == pytest.approx(0.90, abs=0.01)
        # pause_before uses raw: 0.5 - 0.45 = 50ms -> not protected
        assert cut.pause_before_ms == pytest.approx(50.0, abs=1.0)
        assert cut.protected is False


# ---------------------------------------------------------------------------
# Minimum confidence and duration gating
# ---------------------------------------------------------------------------


class TestMinimumGates:
    """Filler words below confidence or duration thresholds are not emitted."""

    def test_low_confidence_filler_not_detected(self) -> None:
        """Words below min_confidence are ignored."""
        cfg = FillerConfig(min_confidence=0.8)
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("um", 0.0, 0.5, 0.5),  # confidence 0.5 < 0.8
                ("hello", 0.6, 1.0, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        assert not any(c.word == "um" for c in cuts)

    def test_short_filler_not_detected(self) -> None:
        """Words below min_duration_ms are ignored."""
        cfg = FillerConfig(min_duration_ms=200)
        stage = make_stage(cfg)
        segment = make_segment(
            [
                ("um", 0.0, 0.1, 0.9),  # only 100ms < 200ms
                ("hello", 0.2, 0.8, 0.99),
            ]
        )
        cuts = stage._detect_fillers([segment])
        assert not any(c.word == "um" for c in cuts)
