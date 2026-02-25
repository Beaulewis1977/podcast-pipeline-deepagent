"""Tests for Pydantic models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from podcast_pipeline.config.settings import BrandingConfig, DuckingConfig, SoundKitConfig
from podcast_pipeline.models.analysis import (
    AnalysisResult,
    ContentCut,
    MarketingCopy,
    Metadata,
    ThumbnailCandidate,
    ViralClip,
)
from podcast_pipeline.models.branding import (
    BrandingProfile,
    CaptionStyle,
    PlatformBrandingOverride,
    ThumbnailBorder,
    _sanitize_brand_voice,
)
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.models.transcript import FillerCut, Segment, Word


class TestJob:
    """Tests for Job model."""

    def test_create_job(self):
        """Test creating a new job."""
        job = Job(
            job_id="test-001",
            input_file="/path/to/video.mp4",
        )
        assert job.job_id == "test-001"
        assert job.status == StageStatus.PENDING
        assert "ingest" in job.stages
        assert "transcribe" in job.stages

    def test_update_stage(self):
        """Test updating stage status."""
        job = Job(job_id="test-001", input_file="/test.mp4")
        job.update_stage("ingest", StageStatus.RUNNING)
        assert job.stages["ingest"].status == StageStatus.RUNNING
        assert job.stages["ingest"].started_at is not None

        job.update_stage("ingest", StageStatus.COMPLETE, outputs=["audio.wav"])
        assert job.stages["ingest"].status == StageStatus.COMPLETE
        assert job.stages["ingest"].completed_at is not None
        assert "audio.wav" in job.stages["ingest"].outputs

    def test_save_and_load(self, temp_dir: Path):
        """Test saving and loading job state."""
        job = Job(
            job_id="test-save-001",
            input_file="/path/to/video.mp4",
        )
        job.update_stage("ingest", StageStatus.COMPLETE)

        job.save(temp_dir)

        # Load and verify
        job_dir = temp_dir / "test-save-001"
        loaded = Job.load(job_dir)

        assert loaded.job_id == job.job_id
        assert loaded.stages["ingest"].status == StageStatus.COMPLETE


class TestTranscript:
    """Tests for transcript models."""

    def test_word_model(self):
        """Test Word model."""
        word = Word(word="hello", start=0.0, end=0.5, confidence=0.99)
        assert word.word == "hello"
        assert word.end - word.start == 0.5

    def test_segment_model(self):
        """Test Segment model."""
        segment = Segment(
            start=0.0,
            end=5.0,
            text="Hello world",
            words=[Word(word="Hello", start=0.0, end=0.3, confidence=0.99)],
        )
        assert len(segment.words) == 1

    def test_filler_cut_model(self):
        """Test FillerCut model."""
        cut = FillerCut(start=2.5, end=2.8, word="um", confidence=0.85)
        assert cut.word == "um"
        assert cut.end - cut.start == pytest.approx(0.3)

    def test_word_confidence_out_of_bounds_rejected(self):
        """Word confidence must stay within [0, 1]."""
        with pytest.raises(ValidationError):
            Word(word="oops", start=0.0, end=0.4, confidence=1.2)

        with pytest.raises(ValidationError):
            Word(word="oops", start=0.0, end=0.4, confidence=-0.1)

    def test_segment_backwards_range_rejected(self):
        """Segment end must be after start."""
        with pytest.raises(ValidationError):
            Segment(start=3.0, end=2.0, text="invalid")


class TestAnalysis:
    """Tests for analysis models."""

    def test_content_cut_model(self):
        """Test ContentCut model."""
        cut = ContentCut(
            start="02:15",
            end="02:45",
            start_seconds=135.0,
            end_seconds=165.0,
            reason="Off-topic tangent",
        )
        assert cut.end_seconds - cut.start_seconds == 30.0

    def test_viral_clip_model(self):
        """Test ViralClip model."""
        clip = ViralClip(
            start="15:30",
            end="16:00",
            start_seconds=930.0,
            end_seconds=960.0,
            description="Interesting moment",
            virality_score=8,
            suggested_hook="Must watch this!",
        )
        assert clip.virality_score == 8

    def test_content_cut_backwards_seconds_rejected(self):
        """Content cuts reject backwards seconds ranges."""
        with pytest.raises(ValidationError):
            ContentCut(
                start="02:45",
                end="02:15",
                start_seconds=165.0,
                end_seconds=135.0,
                reason="Invalid",
            )

    def test_viral_clip_string_seconds_mismatch_rejected(self):
        """Viral clips reject mismatched string and numeric timestamps."""
        with pytest.raises(ValidationError):
            ViralClip(
                start="01:00",
                end="01:30",
                start_seconds=0.0,
                end_seconds=90.0,
                description="Mismatch",
                virality_score=6,
            )

    def test_viral_clip_invalid_time_format_rejected(self):
        """Viral clips require MM:SS or HH:MM:SS time strings."""
        with pytest.raises(ValidationError):
            ViralClip(
                start="1m30s",
                end="2m00s",
                start_seconds=90.0,
                end_seconds=120.0,
                description="Bad format",
                virality_score=6,
            )

    def test_analysis_result_model(self):
        """Test full AnalysisResult model."""
        result = AnalysisResult(
            content_cuts=[],
            viral_clips=[],
            thumbnail_frames=[],
            marketing=MarketingCopy(),
            metadata=Metadata(summary="Test summary", topics=["AI"]),
        )
        assert result.metadata.summary == "Test summary"
        assert "AI" in result.metadata.topics

    def test_marketing_copy_platform_matrix_contract(self) -> None:
        """MarketingCopy should expose the full supported platform matrix."""
        expected_platforms = (
            "youtube",
            "spotify",
            "spotify_video",
            "apple",
            "apple_video",
            "tiktok",
            "instagram",
            "linkedin",
            "twitter",
            "facebook",
        )
        assert tuple(MarketingCopy.model_fields) == expected_platforms

    def test_marketing_copy_dump_load_round_trip_preserves_all_platform_keys(self) -> None:
        """Marketing payload should retain all platform keys through validation cycles."""
        payload = {
            "marketing": {
                "youtube": {
                    "titles": ["YouTube title"],
                    "description": "YouTube description",
                    "hashtags": ["#youtube"],
                },
                "spotify": {
                    "titles": ["Spotify title"],
                    "description": "Spotify description",
                    "hashtags": ["#spotify"],
                },
                "spotify_video": {
                    "titles": ["Spotify Video title"],
                    "description": "Spotify Video description",
                    "hashtags": ["#spotifyvideo"],
                },
                "apple": {
                    "titles": ["Apple title"],
                    "description": "Apple description",
                    "hashtags": ["#apple"],
                },
                "apple_video": {
                    "titles": ["Apple Video title"],
                    "description": "Apple Video description",
                    "hashtags": ["#applevideo"],
                },
                "tiktok": {
                    "titles": ["TikTok title"],
                    "description": "TikTok description",
                    "hashtags": ["#tiktok"],
                },
                "instagram": {
                    "titles": ["Instagram title"],
                    "description": "Instagram description",
                    "hashtags": ["#instagram"],
                },
                "linkedin": {
                    "titles": ["LinkedIn title"],
                    "description": "LinkedIn description",
                    "hashtags": ["#linkedin"],
                },
                "twitter": {
                    "titles": ["Twitter title"],
                    "description": "Twitter description",
                    "hashtags": ["#twitter"],
                },
                "facebook": {
                    "titles": ["Facebook title"],
                    "description": "Facebook description",
                    "hashtags": ["#facebook"],
                },
            }
        }

        validated = AnalysisResult.model_validate(payload)
        dumped = validated.model_dump()
        round_tripped = AnalysisResult.model_validate(dumped).model_dump()
        expected_keys = list(payload["marketing"])

        assert list(dumped["marketing"]) == expected_keys
        assert list(round_tripped["marketing"]) == expected_keys
        assert (
            round_tripped["marketing"]["spotify_video"]["description"]
            == "Spotify Video description"
        )
        assert round_tripped["marketing"]["apple_video"]["description"] == "Apple Video description"


class TestFillerCutPhase8:
    """Tests for Phase 8 FillerCut backward compat and new fields."""

    def test_filler_cut_backward_compat_no_new_fields(self) -> None:
        """Legacy filler_cuts.json payload without Phase 8 fields deserializes with safe defaults."""
        data = {"start": 1.0, "end": 1.5, "word": "um", "confidence": 0.9}
        cut = FillerCut.model_validate(data)
        assert cut.category == "disfluency"
        assert cut.pause_before_ms == 0.0
        assert cut.pause_after_ms == 0.0
        assert cut.context_before == ""
        assert cut.context_after == ""
        assert cut.protected is False

    def test_filler_cut_with_phase8_fields(self) -> None:
        """FillerCut with all Phase 8 fields present round-trips correctly."""
        data = {
            "start": 2.0,
            "end": 2.6,
            "word": "like",
            "confidence": 0.85,
            "category": "hedge",
            "pause_before_ms": 350.0,
            "pause_after_ms": 50.0,
            "context_before": "I think",
            "context_after": "it works",
            "protected": True,
        }
        cut = FillerCut.model_validate(data)
        assert cut.category == "hedge"
        assert cut.pause_before_ms == pytest.approx(350.0)
        assert cut.pause_after_ms == pytest.approx(50.0)
        assert cut.context_before == "I think"
        assert cut.context_after == "it works"
        assert cut.protected is True

        # Round-trip through dict serialization
        dumped = cut.model_dump()
        reloaded = FillerCut.model_validate(dumped)
        assert reloaded.category == "hedge"
        assert reloaded.protected is True
        assert reloaded.context_before == "I think"

    def test_filler_cut_invalid_category_rejected(self) -> None:
        """FillerCut rejects unrecognised category values."""
        with pytest.raises(ValidationError):
            FillerCut(start=1.0, end=1.5, word="um", confidence=0.9, category="unknown")

    def test_filler_cut_custom_category_accepted(self) -> None:
        """FillerCut accepts 'custom' as a valid category."""
        cut = FillerCut(
            start=1.0,
            end=1.5,
            word="literally",
            confidence=0.88,
            category="custom",
        )
        assert cut.category == "custom"


class TestThumbnailCandidate:
    """Tests for thumbnail candidate schema."""

    def test_thumbnailcandidate_accepts_virality_metadata(self):
        """ThumbnailCandidate should preserve bounded virality metadata fields."""
        candidate = ThumbnailCandidate(
            timestamp="00:30",
            timestamp_seconds=30.0,
            visual_description="Host reacting with surprise",
            suggested_text_overlay="This changed everything",
            emotion="surprise",
            virality_score=8.5,
            viral_style="reaction_closeup",
            virality_score_source="provider",
            recommendation_signal="high contrast facial expression",
        )

        assert candidate.virality_score == pytest.approx(8.5)
        assert candidate.viral_style == "reaction_closeup"
        assert candidate.virality_score_source == "provider"
        assert candidate.recommendation_signal == "high contrast facial expression"

    def test_thumbnailcandidate_virality_score_out_of_bounds_rejected(self):
        """ThumbnailCandidate virality score must stay in [0, 10]."""
        with pytest.raises(ValidationError):
            ThumbnailCandidate(
                timestamp="00:30",
                timestamp_seconds=30.0,
                virality_score=10.5,
            )

        with pytest.raises(ValidationError):
            ThumbnailCandidate(
                timestamp="00:30",
                timestamp_seconds=30.0,
                virality_score=-0.5,
            )

    def test_thumbnailcandidate_virality_defaults_are_safe(self):
        """ThumbnailCandidate should provide safe defaults for virality metadata."""
        candidate = ThumbnailCandidate(timestamp="00:30", timestamp_seconds=30.0)

        assert candidate.virality_score == 0.0
        assert candidate.viral_style == ""
        assert candidate.virality_score_source == "unspecified"
        assert candidate.recommendation_signal == ""


# ──────────────────────────────────────────────────────────────────────────────
# BrandingProfile model tests
# ──────────────────────────────────────────────────────────────────────────────


class TestBrandingProfile:
    """Tests for BrandingProfile model and sub-models."""

    def test_branding_profile_minimal_required_fields(self) -> None:
        """BrandingProfile with only profile_name should use safe defaults."""
        profile = BrandingProfile(profile_name="My Kit")
        assert profile.profile_name == "My Kit"
        assert profile.brand_voice == ""
        assert profile.logo_path is None
        assert profile.logo_placement == "top_right"
        assert profile.logo_opacity == pytest.approx(0.8)
        assert profile.highlight_color == "#FFFF00"
        assert profile.platform_overrides == {}

    def test_branding_profile_full_fields_round_trips(self) -> None:
        """BrandingProfile serialises and deserialises all fields without loss."""
        profile = BrandingProfile(
            profile_name="neon_viral",
            brand_voice="Bold, provocative Gen Z energy.",
            logo_placement="top_right",
            logo_opacity=0.9,
            caption_style=CaptionStyle(color="#FFFFFF", size=52, shadow=True),
            highlight_color="#FF4500",
            bg_padding="15%",
            thumbnail_border=ThumbnailBorder(color="#00FF00", width=20),
        )
        dumped = profile.model_dump()
        reloaded = BrandingProfile.model_validate(dumped)
        assert reloaded.profile_name == "neon_viral"
        assert reloaded.highlight_color == "#FF4500"
        assert reloaded.thumbnail_border.color == "#00FF00"
        assert reloaded.caption_style.size == 52

    def test_branding_profile_blank_name_rejected(self) -> None:
        """BrandingProfile rejects blank profile_name."""
        with pytest.raises(ValidationError):
            BrandingProfile(profile_name="   ")

    def test_branding_profile_invalid_hex_color_rejected(self) -> None:
        """BrandingProfile rejects malformed highlight_color."""
        with pytest.raises(ValidationError):
            BrandingProfile(profile_name="bad", highlight_color="red")

        with pytest.raises(ValidationError):
            BrandingProfile(profile_name="bad", highlight_color="#ZZZZZZ")

    def test_branding_profile_logo_opacity_out_of_range_rejected(self) -> None:
        """BrandingProfile rejects logo_opacity outside [0, 1]."""
        with pytest.raises(ValidationError):
            BrandingProfile(profile_name="bad", logo_opacity=1.5)

        with pytest.raises(ValidationError):
            BrandingProfile(profile_name="bad", logo_opacity=-0.1)


class TestBrandVoiceSanitization:
    """Tests for brand_voice sanitization: control char stripping and max length."""

    def test_sanitize_brand_voice_strips_control_chars(self) -> None:
        """Control characters must be removed from brand_voice."""
        raw = "Bold\x00Gen Z\x01Energy\x1f!"
        result = _sanitize_brand_voice(raw)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x1f" not in result
        assert "Bold" in result
        assert "Energy" in result

    def test_sanitize_brand_voice_truncates_at_max_length(self) -> None:
        """brand_voice must be capped at BRAND_VOICE_MAX_CHARS (2000)."""
        from podcast_pipeline.models.branding import BRAND_VOICE_MAX_CHARS

        long_text = "x" * (BRAND_VOICE_MAX_CHARS + 500)
        result = _sanitize_brand_voice(long_text)
        assert len(result) <= BRAND_VOICE_MAX_CHARS

    def test_sanitize_brand_voice_preserves_clean_text(self) -> None:
        """Normal printable text must be preserved by sanitization."""
        clean = "Professional, credible, audience-appropriate. Use data-driven storytelling."
        result = _sanitize_brand_voice(clean)
        assert result == clean

    def test_branding_profile_auto_sanitizes_brand_voice_on_construction(self) -> None:
        """BrandingProfile constructor sanitizes brand_voice automatically."""
        profile = BrandingProfile(
            profile_name="sanitize_test",
            brand_voice="Good text\x00with null bytes\x1b[31mANSI",
        )
        assert "\x00" not in profile.brand_voice
        assert "\x1b" not in profile.brand_voice
        assert "Good text" in profile.brand_voice


class TestPlatformOverrides:
    """Tests for BrandingProfile.platform_overrides and merge behaviour."""

    def _make_base_profile(self) -> BrandingProfile:
        return BrandingProfile(
            profile_name="base_profile",
            brand_voice="Professional tone.",
            logo_placement="top_right",
            logo_opacity=0.8,
            caption_style=CaptionStyle(color="#FFFFFF", size=48),
            highlight_color="#FFFF00",
            bg_padding="0%",
            thumbnail_border=ThumbnailBorder(color="#000000", width=5),
            platform_overrides={
                "tiktok": PlatformBrandingOverride(
                    logo_placement="bottom_left",
                    logo_opacity=0.6,
                    highlight_color="#FF0000",
                    bg_padding="15%",
                ),
            },
        )

    def test_platform_overrides_merge_applies_only_set_fields(self) -> None:
        """Merge must apply override fields but keep base defaults for unset fields."""
        profile = self._make_base_profile()
        resolved = profile.resolved_for_platform("tiktok")

        assert resolved.logo_placement == "bottom_left"
        assert resolved.logo_opacity == pytest.approx(0.6)
        assert resolved.highlight_color == "#FF0000"
        assert resolved.bg_padding == "15%"
        # Unset override fields preserve base values.
        assert resolved.caption_style.color == "#FFFFFF"
        assert resolved.thumbnail_border.color == "#000000"

    def test_platform_overrides_no_override_returns_base(self) -> None:
        """resolved_for_platform returns base values when no override exists."""
        profile = self._make_base_profile()
        resolved = profile.resolved_for_platform("youtube")

        assert resolved.logo_placement == "top_right"
        assert resolved.logo_opacity == pytest.approx(0.8)
        assert resolved.highlight_color == "#FFFF00"

    def test_platform_overrides_resolved_profile_has_empty_overrides(self) -> None:
        """Resolved profile should always have empty platform_overrides."""
        profile = self._make_base_profile()
        resolved = profile.resolved_for_platform("tiktok")
        assert resolved.platform_overrides == {}

    def test_platform_overrides_base_unchanged_after_resolve(self) -> None:
        """Resolving for a platform must not mutate the base profile."""
        profile = self._make_base_profile()
        _ = profile.resolved_for_platform("tiktok")

        assert profile.logo_placement == "top_right"
        assert "tiktok" in profile.platform_overrides

    def test_platform_overrides_caption_style_override_applied(self) -> None:
        """Caption style override merges onto base caption when present."""
        profile = BrandingProfile(
            profile_name="caption_test",
            caption_style=CaptionStyle(color="#FFFFFF", size=48),
            platform_overrides={
                "instagram": PlatformBrandingOverride(
                    caption_style=CaptionStyle(color="#FF4500", size=60, bold=True),
                ),
            },
        )
        resolved = profile.resolved_for_platform("instagram")
        assert resolved.caption_style.color == "#FF4500"
        assert resolved.caption_style.size == 60
        assert resolved.caption_style.bold is True

    def test_platform_overrides_empty_key_rejected(self) -> None:
        """platform_overrides with blank key strings must be rejected."""
        with pytest.raises(ValidationError):
            BrandingProfile(
                profile_name="bad_key",
                platform_overrides={"": PlatformBrandingOverride()},
            )


class TestBrandingProfileSerializationContract:
    """Tests for YAML-safe serialization round-trips."""

    def test_branding_profile_model_dump_produces_serialisable_types(self) -> None:
        """model_dump(mode='json') should produce JSON-serialisable types only."""
        import json

        profile = BrandingProfile(
            profile_name="serial_test",
            brand_voice="Test voice.",
            platform_overrides={
                "tiktok": PlatformBrandingOverride(logo_opacity=0.5),
            },
        )
        dumped = profile.model_dump(mode="json")
        # Should not raise.
        serialized = json.dumps(dumped)
        assert "serial_test" in serialized

    def test_branding_profile_with_logo_path_serializes_path(self) -> None:
        """BrandingProfile with logo_path serialises the Path to a string."""
        profile = BrandingProfile(
            profile_name="logo_test",
            logo_path=Path("branding/assets/logo.png"),
        )
        dumped = profile.model_dump(mode="json")
        assert dumped["logo_path"] == "branding/assets/logo.png"


class TestBrandingSoundKitConfig:
    """Tests for DuckingConfig and SoundKitConfig typed contracts (Phase 9.8)."""

    # ── DuckingConfig ────────────────────────────────────────────────────────

    def test_ducking_config_defaults_match_spec(self) -> None:
        """DuckingConfig must default to the spec-mandated podcasting values."""
        cfg = DuckingConfig()
        assert cfg.enabled is True
        assert cfg.attack_ms == 5.0
        assert cfg.release_ms == 200.0
        assert cfg.ratio == 4.0
        assert cfg.threshold_db == -30.0
        assert cfg.stinger_volume_db == -12.0

    def test_ducking_config_can_be_disabled(self) -> None:
        """Setting enabled=False must persist and be usable by audio_mix helpers."""
        cfg = DuckingConfig(enabled=False)
        assert cfg.enabled is False

    def test_ducking_config_rejects_ratio_below_one(self) -> None:
        """ratio < 1.0 is not a valid compression ratio."""
        with pytest.raises(ValidationError):
            DuckingConfig(ratio=0.5)

    def test_ducking_config_rejects_positive_threshold(self) -> None:
        """threshold_db must be <= 0 (positive threshold is nonsensical)."""
        with pytest.raises(ValidationError):
            DuckingConfig(threshold_db=1.0)

    def test_ducking_config_rejects_attack_below_minimum(self) -> None:
        """attack_ms must be >= 0.1 ms (0 ms is not physically realizable)."""
        with pytest.raises(ValidationError):
            DuckingConfig(attack_ms=0.0)

    def test_ducking_config_custom_values_round_trip(self) -> None:
        """Custom ducking values must survive a round-trip via model_dump."""
        cfg = DuckingConfig(attack_ms=10.0, release_ms=300.0, ratio=6.0, threshold_db=-25.0)
        dumped = cfg.model_dump()
        reloaded = DuckingConfig(**dumped)
        assert reloaded.attack_ms == 10.0
        assert reloaded.release_ms == 300.0
        assert reloaded.ratio == 6.0
        assert reloaded.threshold_db == -25.0

    # ── SoundKitConfig ───────────────────────────────────────────────────────

    def test_sound_kit_config_defaults_no_assets(self) -> None:
        """Default SoundKitConfig has no asset paths — all None."""
        kit = SoundKitConfig()
        assert kit.intro_path is None
        assert kit.transition_path is None
        assert kit.outro_path is None

    def test_sound_kit_config_default_normalization_policy(self) -> None:
        """Default normalization policy must be 48 kHz stereo fltp."""
        kit = SoundKitConfig()
        assert kit.canonical_sample_rate == 48000
        assert kit.canonical_channels == 2
        assert kit.canonical_sample_fmt == "fltp"

    def test_sound_kit_config_default_outro_trigger(self) -> None:
        """Default outro trigger window must be 5 seconds from end."""
        kit = SoundKitConfig()
        assert kit.outro_trigger_s == 5.0

    def test_sound_kit_config_carries_ducking_config(self) -> None:
        """SoundKitConfig must embed a DuckingConfig with spec defaults."""
        kit = SoundKitConfig()
        assert isinstance(kit.ducking, DuckingConfig)
        assert kit.ducking.attack_ms == 5.0
        assert kit.ducking.release_ms == 200.0

    def test_sound_kit_config_paths_accepted_as_path_objects(self) -> None:
        """Sound asset paths must be accepted as Path objects."""
        kit = SoundKitConfig(
            intro_path=Path("branding/sounds/intro_music.wav"),
            transition_path=Path("branding/sounds/whoosh.wav"),
            outro_path=Path("branding/sounds/outro.wav"),
        )
        assert kit.intro_path == Path("branding/sounds/intro_music.wav")
        assert kit.transition_path == Path("branding/sounds/whoosh.wav")
        assert kit.outro_path == Path("branding/sounds/outro.wav")

    def test_sound_kit_config_rejects_invalid_sample_fmt(self) -> None:
        """Unrecognised sample format strings must be rejected at config load."""
        with pytest.raises(ValidationError):
            SoundKitConfig(canonical_sample_fmt="invalid_fmt")

    def test_sound_kit_config_accepts_all_canonical_sample_fmts(self) -> None:
        """All FFmpeg canonical sample formats declared in the validator must be accepted."""
        valid_fmts = {"u8", "s16", "s32", "flt", "dbl", "u8p", "s16p", "s32p", "fltp", "dblp"}
        for fmt in valid_fmts:
            kit = SoundKitConfig(canonical_sample_fmt=fmt)
            assert kit.canonical_sample_fmt == fmt

    def test_sound_kit_config_rejects_outro_trigger_below_minimum(self) -> None:
        """outro_trigger_s must be >= 0.5 seconds."""
        with pytest.raises(ValidationError):
            SoundKitConfig(outro_trigger_s=0.0)

    def test_sound_kit_config_round_trip_with_all_assets(self) -> None:
        """Full SoundKitConfig with assets must survive a model_dump round-trip."""
        kit = SoundKitConfig(
            intro_path=Path("intro.wav"),
            transition_path=Path("whoosh.wav"),
            outro_path=Path("outro.wav"),
            canonical_sample_rate=44100,
            canonical_channels=1,
            canonical_sample_fmt="s16",
            outro_trigger_s=3.0,
            ducking=DuckingConfig(enabled=False),
        )
        dumped = kit.model_dump(mode="json")
        reloaded = SoundKitConfig(**dumped)
        assert reloaded.intro_path == Path("intro.wav")
        assert reloaded.canonical_sample_rate == 44100
        assert reloaded.canonical_channels == 1
        assert reloaded.canonical_sample_fmt == "s16"
        assert reloaded.outro_trigger_s == 3.0
        assert reloaded.ducking.enabled is False

    # ── BrandingConfig integration ───────────────────────────────────────────

    def test_branding_config_carries_sound_kit(self) -> None:
        """BrandingConfig must embed a SoundKitConfig with ducking defaults."""
        cfg = BrandingConfig()
        assert isinstance(cfg.sound_kit, SoundKitConfig)
        assert isinstance(cfg.sound_kit.ducking, DuckingConfig)

    def test_branding_config_sound_kit_ducking_defaults_match_spec(self) -> None:
        """BrandingConfig.sound_kit.ducking must default to spec values."""
        cfg = BrandingConfig()
        duck = cfg.sound_kit.ducking
        assert duck.attack_ms == 5.0
        assert duck.release_ms == 200.0
        assert duck.ratio == 4.0
        assert duck.threshold_db == -30.0

    # ── BrandingProfile sound fields ─────────────────────────────────────────

    def test_branding_profile_sound_fields_default_to_none(self) -> None:
        """Sound asset fields must default to None — no forced asset paths."""
        profile = BrandingProfile(profile_name="silent_brand")
        assert profile.intro_sound is None
        assert profile.transition_sound is None
        assert profile.outro_sound is None

    def test_branding_profile_has_sound_kit_false_when_no_sounds(self) -> None:
        """has_sound_kit must return False when all sound paths are None."""
        profile = BrandingProfile(profile_name="no_sounds")
        assert profile.has_sound_kit is False

    def test_branding_profile_has_sound_kit_true_with_intro(self) -> None:
        """has_sound_kit must return True if at least one sound path is set."""
        profile = BrandingProfile(
            profile_name="with_intro",
            intro_sound=Path("branding/sounds/intro_music.wav"),
        )
        assert profile.has_sound_kit is True

    def test_branding_profile_has_sound_kit_true_with_transition(self) -> None:
        """has_sound_kit must return True when only transition sound is set."""
        profile = BrandingProfile(
            profile_name="with_transition",
            transition_sound=Path("branding/sounds/whoosh.wav"),
        )
        assert profile.has_sound_kit is True

    def test_branding_profile_has_sound_kit_true_with_outro(self) -> None:
        """has_sound_kit must return True when only outro sound is set."""
        profile = BrandingProfile(
            profile_name="with_outro",
            outro_sound=Path("branding/sounds/outro.wav"),
        )
        assert profile.has_sound_kit is True

    def test_branding_profile_sound_fields_survive_resolved_for_platform(self) -> None:
        """Sound kit paths must be preserved after platform override resolution."""
        profile = BrandingProfile(
            profile_name="sound_platform_test",
            intro_sound=Path("intro.wav"),
            transition_sound=Path("whoosh.wav"),
            outro_sound=Path("outro.wav"),
            platform_overrides={
                "youtube": PlatformBrandingOverride(logo_placement="top_left"),
            },
        )
        resolved = profile.resolved_for_platform("youtube")
        assert resolved.intro_sound == Path("intro.wav")
        assert resolved.transition_sound == Path("whoosh.wav")
        assert resolved.outro_sound == Path("outro.wav")
        assert resolved.platform_overrides == {}

    def test_branding_profile_sound_fields_serialize_as_strings(self) -> None:
        """Sound asset Path fields must serialize to strings in JSON mode."""
        profile = BrandingProfile(
            profile_name="sound_serial",
            intro_sound=Path("branding/sounds/intro_music.wav"),
        )
        dumped = profile.model_dump(mode="json")
        assert dumped["intro_sound"] == "branding/sounds/intro_music.wav"
        assert dumped["transition_sound"] is None
        assert dumped["outro_sound"] is None

    def test_branding_profile_backward_compatible_without_sound_fields(self) -> None:
        """BrandingProfile constructed without sound fields must remain valid."""
        profile = BrandingProfile(
            profile_name="legacy_profile",
            brand_voice="Professional tone.",
            logo_placement="top_right",
        )
        assert profile.has_sound_kit is False
        assert profile.profile_name == "legacy_profile"
