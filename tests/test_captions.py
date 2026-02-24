"""Tests for the ASS caption engine (src/podcast_pipeline/utils/captions.py)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from podcast_pipeline.utils.captions import (
    CaptionStyleConfig,
    WordEntry,
    _ass_timestamp_to_seconds,
    _build_dialogue_text,
    _build_events_section,
    _build_script_info,
    _build_styles_section,
    _css_hex_to_ass_bgr,
    _group_words_into_events,
    _seconds_to_ass_timestamp,
    _validate_and_clamp_words,
    generate_ass,
    generate_ass_from_json,
    load_word_alignment,
    validate_ass_syntax,
)


@pytest.fixture
def sample_words() -> list[WordEntry]:
    return [
        WordEntry("Hello", 0.0, 0.5),
        WordEntry("world", 0.6, 1.1),
        WordEntry("this", 1.2, 1.5),
        WordEntry("is", 1.6, 1.8),
        WordEntry("a", 1.9, 2.1),
        WordEntry("test", 2.2, 2.8),
    ]


@pytest.fixture
def default_style() -> CaptionStyleConfig:
    return CaptionStyleConfig()


class TestCssHexToAssBgr:
    def test_standard_yellow_converts_correctly(self) -> None:
        result = _css_hex_to_ass_bgr("#FFFF00")
        assert result == "&H0000FFFF"

    def test_white_converts_correctly(self) -> None:
        result = _css_hex_to_ass_bgr("#FFFFFF")
        assert result == "&H00FFFFFF"

    def test_red_converts_correctly(self) -> None:
        result = _css_hex_to_ass_bgr("#FF0000")
        assert result == "&H000000FF"

    def test_short_hex_expands_correctly(self) -> None:
        result = _css_hex_to_ass_bgr("#FFF")
        assert result == "&H00FFFFFF"

    def test_lowercase_input_handled(self) -> None:
        result = _css_hex_to_ass_bgr("#ffff00")
        assert result == "&H0000FFFF"

    def test_invalid_input_returns_default(self) -> None:
        result = _css_hex_to_ass_bgr("#ZZZ")
        assert result.startswith("&H")

    def test_result_is_uppercase(self) -> None:
        result = _css_hex_to_ass_bgr("#aabbcc")
        assert result == result.upper() or result.startswith("&H00")


class TestTimestampFormatting:
    def test_zero_seconds(self) -> None:
        assert _seconds_to_ass_timestamp(0.0) == "0:00:00.00"

    def test_one_minute_fifteen_point_five_seconds(self) -> None:
        assert _seconds_to_ass_timestamp(75.5) == "0:01:15.50"

    def test_over_one_hour(self) -> None:
        result = _seconds_to_ass_timestamp(3661.0)
        assert result == "1:01:01.00"

    def test_centisecond_rounding(self) -> None:
        result = _seconds_to_ass_timestamp(1.005)
        assert ":" in result

    def test_negative_clamped_to_zero(self) -> None:
        assert _seconds_to_ass_timestamp(-1.0) == "0:00:00.00"

    def test_roundtrip_via_parse(self) -> None:
        original = 125.75
        ts = _seconds_to_ass_timestamp(original)
        parsed = _ass_timestamp_to_seconds(ts)
        assert parsed is not None
        assert abs(parsed - original) < 0.015


class TestASSTimestampParse:
    def test_valid_timestamp(self) -> None:
        assert _ass_timestamp_to_seconds("0:01:15.50") == pytest.approx(75.5, abs=0.01)

    def test_invalid_format_returns_none(self) -> None:
        assert _ass_timestamp_to_seconds("invalid") is None

    def test_empty_string_returns_none(self) -> None:
        assert _ass_timestamp_to_seconds("") is None


class TestLoadWordAlignment:
    def test_loads_flat_word_list(self, tmp_path: Path) -> None:
        data = {
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.5},
                {"word": "world", "start": 0.6, "end": 1.0},
            ]
        }
        p = tmp_path / "word_alignment.json"
        p.write_text(json.dumps(data))
        words = load_word_alignment(p)
        assert len(words) == 2
        assert words[0].word == "hello"
        assert words[1].word == "world"

    def test_loads_segment_based_words(self, tmp_path: Path) -> None:
        data = {
            "segments": [
                {"words": [{"word": "hi", "start": 0.0, "end": 0.3}]},
                {"words": [{"word": "there", "start": 0.5, "end": 0.8}]},
            ]
        }
        p = tmp_path / "word_alignment.json"
        p.write_text(json.dumps(data))
        words = load_word_alignment(p)
        assert len(words) == 2

    def test_loads_bare_list_format(self, tmp_path: Path) -> None:
        data = [
            {"word": "a", "start": 0.0, "end": 0.2},
            {"word": "b", "start": 0.3, "end": 0.5},
        ]
        p = tmp_path / "word_alignment.json"
        p.write_text(json.dumps(data))
        words = load_word_alignment(p)
        assert len(words) == 2

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        words = load_word_alignment(tmp_path / "nonexistent.json")
        assert words == []

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not-json{{{")
        words = load_word_alignment(p)
        assert words == []

    def test_invalid_entries_skipped(self, tmp_path: Path) -> None:
        data = {
            "words": [
                {"word": "valid", "start": 0.0, "end": 0.5},
                {"word": "missing_end", "start": 0.6},
                {"word": "inverted", "start": 1.0, "end": 0.5},
                {},
            ]
        }
        p = tmp_path / "word_alignment.json"
        p.write_text(json.dumps(data))
        words = load_word_alignment(p)
        assert len(words) == 1
        assert words[0].word == "valid"

    def test_words_sorted_by_start(self, tmp_path: Path) -> None:
        data = {
            "words": [
                {"word": "second", "start": 1.0, "end": 1.5},
                {"word": "first", "start": 0.0, "end": 0.5},
            ]
        }
        p = tmp_path / "word_alignment.json"
        p.write_text(json.dumps(data))
        words = load_word_alignment(p)
        assert words[0].word == "first"
        assert words[1].word == "second"


class TestValidateAndClampWords:
    def test_valid_words_unchanged(self) -> None:
        words = [WordEntry("a", 0.0, 0.5), WordEntry("b", 0.6, 1.0)]
        result = _validate_and_clamp_words(words)
        assert len(result) == 2

    def test_overlapping_words_clamped(self) -> None:
        words = [WordEntry("a", 0.0, 1.0), WordEntry("b", 0.5, 1.5)]
        result = _validate_and_clamp_words(words)
        assert len(result) == 2
        assert result[1].start == pytest.approx(1.0)
        assert result[1].end == pytest.approx(1.5)

    def test_word_fully_within_prev_skipped(self) -> None:
        words = [WordEntry("a", 0.0, 2.0), WordEntry("b", 0.5, 1.0)]
        result = _validate_and_clamp_words(words)
        assert len(result) == 1
        assert result[0].word == "a"

    def test_empty_input(self) -> None:
        assert _validate_and_clamp_words([]) == []

    def test_negative_start_filtered(self) -> None:
        words = [WordEntry("bad", -0.5, 0.3), WordEntry("good", 0.5, 1.0)]
        result = _validate_and_clamp_words(words)
        assert len(result) == 1
        assert result[0].word == "good"


class TestGroupWordsIntoEvents:
    def test_basic_grouping(self) -> None:
        words = [
            WordEntry("a", 0.0, 0.3),
            WordEntry("b", 0.4, 0.7),
            WordEntry("c", 0.8, 1.1),
        ]
        groups = _group_words_into_events(words, max_words_per_line=5)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_max_words_triggers_new_group(self) -> None:
        words = [WordEntry(f"w{i}", float(i), float(i) + 0.4) for i in range(8)]
        groups = _group_words_into_events(words, max_words_per_line=3, gap_threshold_s=100.0)
        assert len(groups) == 3
        assert len(groups[0]) == 3
        assert len(groups[1]) == 3
        assert len(groups[2]) == 2

    def test_gap_triggers_new_group(self) -> None:
        words = [
            WordEntry("a", 0.0, 0.3),
            WordEntry("b", 2.0, 2.3),
        ]
        groups = _group_words_into_events(words, gap_threshold_s=1.0)
        assert len(groups) == 2

    def test_empty_input(self) -> None:
        assert _group_words_into_events([]) == []

    def test_single_word(self) -> None:
        words = [WordEntry("hello", 0.0, 0.5)]
        groups = _group_words_into_events(words)
        assert len(groups) == 1
        assert groups[0][0].word == "hello"


class TestASSSections:
    def test_script_info_contains_play_res(self) -> None:
        script = _build_script_info(1920, 1080)
        assert "PlayResX: 1920" in script
        assert "PlayResY: 1080" in script
        assert "[Script Info]" in script

    def test_styles_section_contains_style_marker(self) -> None:
        style = CaptionStyleConfig()
        section = _build_styles_section(style, "16:9")
        assert "[V4+ Styles]" in section
        assert "Style: Default" in section

    def test_styles_section_bold_flag(self) -> None:
        style = CaptionStyleConfig(bold=True)
        section = _build_styles_section(style, "16:9")
        assert "-1" in section

    def test_styles_section_font_name(self) -> None:
        style = CaptionStyleConfig(font_name="Montserrat")
        section = _build_styles_section(style, "16:9")
        assert "Montserrat" in section

    def test_safe_zone_9_16_different_from_16_9(self) -> None:
        """9:16 events section should use different position from 16:9."""
        style = CaptionStyleConfig()
        group = [WordEntry("test", 0.0, 0.5)]
        events_16_9 = _build_events_section([group], style, "16:9")
        events_9_16 = _build_events_section([group], style, "9:16")
        assert r"\pos(" in events_16_9
        assert r"\pos(" in events_9_16
        pos_16_9 = re.search(r"\\pos\((\d+),(\d+)\)", events_16_9)
        pos_9_16 = re.search(r"\\pos\((\d+),(\d+)\)", events_9_16)
        assert pos_16_9 is not None
        assert pos_9_16 is not None
        y_16_9 = int(pos_16_9.group(2))
        y_9_16 = int(pos_9_16.group(2))
        assert y_16_9 != y_9_16


class TestHighlightDialogueText:
    def test_single_word_contains_highlight_colour(self) -> None:
        group = [WordEntry("hello", 0.0, 0.5)]
        text = _build_dialogue_text(group, "&H00FFFFFF", "&H0000FFFF")
        assert "\\1c" in text
        assert "hello" in text

    def test_multiple_words_all_present(self) -> None:
        group = [
            WordEntry("hello", 0.0, 0.5),
            WordEntry("world", 0.6, 1.0),
        ]
        text = _build_dialogue_text(group, "&H00FFFFFF", "&H0000FFFF")
        assert "hello" in text
        assert "world" in text

    def test_timing_tags_are_relative_to_event_start(self) -> None:
        group = [
            WordEntry("a", 5.0, 5.4),
            WordEntry("b", 5.5, 5.9),
        ]
        text = _build_dialogue_text(group, "&H00FFFFFF", "&H0000FFFF")
        assert "50" in text

    def test_empty_group_returns_empty_string(self) -> None:
        assert _build_dialogue_text([], "&H00FFFFFF", "&H0000FFFF") == ""


class TestSafeZoneTemplates:
    """Verify safe-zone position tags for all three aspect ratios."""

    @pytest.mark.parametrize("ratio", ["16:9", "9:16", "1:1"])
    def test_ass_generation_produces_pos_tag(
        self, tmp_path: Path, sample_words: list[WordEntry], ratio: str
    ) -> None:
        style = CaptionStyleConfig()
        out = tmp_path / f"captions_{ratio.replace(':', '_')}.ass"
        generate_ass(sample_words, style, out, aspect_ratio=ratio)
        content = out.read_text(encoding="utf-8-sig")
        assert r"\pos(" in content

    @pytest.mark.parametrize("ratio", ["16:9", "9:16", "1:1"])
    def test_play_res_matches_ratio(
        self, tmp_path: Path, sample_words: list[WordEntry], ratio: str
    ) -> None:
        from podcast_pipeline.utils.captions import _PLAY_RES

        style = CaptionStyleConfig()
        out = tmp_path / f"captions_{ratio.replace(':', '_')}.ass"
        generate_ass(sample_words, style, out, aspect_ratio=ratio)
        content = out.read_text(encoding="utf-8-sig")
        expected_x, expected_y = _PLAY_RES[ratio]
        assert f"PlayResX: {expected_x}" in content
        assert f"PlayResY: {expected_y}" in content


class TestGenerateAss:
    def test_generates_valid_ass_file(self, tmp_path: Path, sample_words: list[WordEntry]) -> None:
        style = CaptionStyleConfig()
        out = tmp_path / "output.ass"
        result = generate_ass(sample_words, style, out)
        assert result.exists()
        content = out.read_text(encoding="utf-8-sig")
        errors = validate_ass_syntax(content)
        assert errors == [], f"ASS validation errors: {errors}"

    def test_output_path_returned(self, tmp_path: Path, sample_words: list[WordEntry]) -> None:
        style = CaptionStyleConfig()
        out = tmp_path / "output.ass"
        result = generate_ass(sample_words, style, out)
        assert result == out.resolve()

    def test_creates_parent_dirs(self, tmp_path: Path, sample_words: list[WordEntry]) -> None:
        style = CaptionStyleConfig()
        out = tmp_path / "nested" / "deep" / "output.ass"
        generate_ass(sample_words, style, out)
        assert out.exists()

    def test_unsupported_ratio_raises(self, tmp_path: Path, sample_words: list[WordEntry]) -> None:
        style = CaptionStyleConfig()
        with pytest.raises(ValueError, match="Unsupported aspect_ratio"):
            generate_ass(sample_words, style, tmp_path / "out.ass", aspect_ratio="4:3")

    def test_empty_words_writes_valid_file(self, tmp_path: Path) -> None:
        style = CaptionStyleConfig()
        out = tmp_path / "empty.ass"
        generate_ass([], style, out)
        assert out.exists()
        content = out.read_text(encoding="utf-8-sig")
        errors = validate_ass_syntax(content)
        assert errors == [], f"ASS validation errors: {errors}"

    def test_word_level_timing_preserved(self, tmp_path: Path) -> None:
        """Word timing relative offsets should appear in the dialogue text."""
        words = [
            WordEntry("first", 0.0, 0.4),
            WordEntry("second", 0.5, 0.9),
        ]
        style = CaptionStyleConfig()
        out = tmp_path / "timing.ass"
        generate_ass(words, style, out)
        content = out.read_text(encoding="utf-8-sig")
        assert "50" in content or "Dialogue" in content

    def test_all_three_ratios_produce_different_positions(
        self, tmp_path: Path, sample_words: list[WordEntry]
    ) -> None:
        """Each aspect ratio should produce a distinct pos value."""
        positions = {}
        for ratio in ["16:9", "9:16", "1:1"]:
            style = CaptionStyleConfig()
            out = tmp_path / f"{ratio.replace(':', '_')}.ass"
            generate_ass(sample_words, style, out, aspect_ratio=ratio)
            content = out.read_text(encoding="utf-8-sig")
            match = re.search(r"\\pos\((\d+),(\d+)\)", content)
            if match:
                positions[ratio] = (int(match.group(1)), int(match.group(2)))

        assert positions["9:16"] != positions["16:9"]

    def test_branding_style_applied(self, tmp_path: Path, sample_words: list[WordEntry]) -> None:
        """Custom brand colours should appear in the generated ASS."""
        style = CaptionStyleConfig(
            text_color_hex="#0000FF",
            highlight_color_hex="#FF0000",
        )
        out = tmp_path / "branded.ass"
        generate_ass(sample_words, style, out)
        content = out.read_text(encoding="utf-8-sig")
        assert "&H00FF0000" in content or "&H000000FF" in content

    def test_font_size_multiplier_applied_for_9_16(
        self, tmp_path: Path, sample_words: list[WordEntry]
    ) -> None:
        """9:16 font size should be larger than 16:9 due to multiplier."""
        style = CaptionStyleConfig(font_size=40)
        results = {}
        for ratio in ["16:9", "9:16"]:
            out = tmp_path / f"size_{ratio.replace(':', '_')}.ass"
            generate_ass(sample_words, style, out, aspect_ratio=ratio)
            content = out.read_text(encoding="utf-8-sig")
            match = re.search(r"Style: Default,[^,]+,(\d+),", content)
            if match:
                results[ratio] = int(match.group(1))

        assert results.get("9:16", 0) > results.get("16:9", 0)


class TestGenerateAssFromJson:
    def test_generates_valid_file_from_json(self, tmp_path: Path) -> None:
        data = {
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.5},
                {"word": "podcast", "start": 0.6, "end": 1.2},
            ]
        }
        alignment = tmp_path / "word_alignment.json"
        alignment.write_text(json.dumps(data))
        out = tmp_path / "output.ass"
        result = generate_ass_from_json(alignment, CaptionStyleConfig(), out)
        assert result.exists()
        content = out.read_text(encoding="utf-8-sig")
        errors = validate_ass_syntax(content)
        assert errors == []

    def test_missing_json_produces_empty_ass(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.ass"
        result = generate_ass_from_json(tmp_path / "nonexistent.json", CaptionStyleConfig(), out)
        assert result.exists()
        content = out.read_text(encoding="utf-8-sig")
        errors = validate_ass_syntax(content)
        assert errors == []


class TestCaptionStyleConfigFromBranding:
    def test_none_returns_defaults(self) -> None:
        style = CaptionStyleConfig.from_branding(None)
        assert style.text_color_hex == "#FFFFFF"
        assert style.highlight_color_hex == "#FFFF00"
        assert style.font_size == 48
        assert style.bold is False

    def test_branding_profile_values_applied(self) -> None:
        """Verify branding object with caption_style sub-object is consumed."""

        class _FakeCaptionStyle:
            color = "#FF0000"
            size = 56
            bold = True
            italic = False
            shadow = False
            font = "Impact"

        class _FakeBranding:
            caption_style = _FakeCaptionStyle()
            highlight_color = "#00FF00"
            font_path = None

        style = CaptionStyleConfig.from_branding(_FakeBranding())
        assert style.text_color_hex == "#FF0000"
        assert style.font_size == 56
        assert style.bold is True
        assert style.shadow is False
        assert style.font_name == "Impact"
        assert style.highlight_color_hex == "#00FF00"

    def test_font_path_stem_used_as_font_name(self) -> None:
        class _FakeBranding:
            caption_style = None
            highlight_color = "#FFFF00"
            font_path = Path("/some/dir/Montserrat-Bold.ttf")

        style = CaptionStyleConfig.from_branding(_FakeBranding())
        assert style.font_name == "Montserrat-Bold"


class TestValidateAssSyntax:
    def test_valid_file_returns_no_errors(
        self, tmp_path: Path, sample_words: list[WordEntry]
    ) -> None:
        out = tmp_path / "valid.ass"
        generate_ass(sample_words, CaptionStyleConfig(), out)
        content = out.read_text(encoding="utf-8-sig")
        assert validate_ass_syntax(content) == []

    def test_missing_script_info_section(self) -> None:
        errors = validate_ass_syntax("[V4+ Styles]\nStyle: Default\n[Events]\n")
        assert any("Script Info" in e for e in errors)

    def test_missing_events_section(self) -> None:
        errors = validate_ass_syntax("[Script Info]\nPlayResX: 1920\n[V4+ Styles]\n")
        assert any("Events" in e for e in errors)

    def test_inverted_timestamps_reported(self) -> None:
        content = (
            "[Script Info]\n[V4+ Styles]\n[Events]\n"
            "Dialogue: 0,0:00:05.00,0:00:01.00,Default,,0,0,0,,text\n"
        )
        errors = validate_ass_syntax(content)
        assert any("not after start" in e for e in errors)


class TestCaptionConfig:
    def test_default_disabled(self) -> None:
        from podcast_pipeline.config.settings import CaptionConfig

        config = CaptionConfig()
        assert config.enabled is False

    def test_max_words_per_line_bounds(self) -> None:
        from podcast_pipeline.config.settings import CaptionConfig

        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            CaptionConfig(max_words_per_line=0)
        with pytest.raises(ValidationError, match="less than or equal to 20"):
            CaptionConfig(max_words_per_line=21)

    def test_gap_threshold_bounds(self) -> None:
        from podcast_pipeline.config.settings import CaptionConfig

        with pytest.raises(ValidationError, match=r"greater than or equal to 0\.1"):
            CaptionConfig(gap_threshold_s=0.05)

    def test_caption_config_accessible_via_branding(self) -> None:
        from podcast_pipeline.config.settings import BrandingConfig

        branding = BrandingConfig()
        assert branding.captions.enabled is False
        assert branding.captions.max_words_per_line == 7

    def test_config_round_trips_yaml(self) -> None:
        """CaptionConfig should survive YAML serialization via BrandingConfig."""
        import yaml

        from podcast_pipeline.config.settings import BrandingConfig

        branding = BrandingConfig()
        raw = yaml.dump(branding.model_dump(mode="json"))
        reloaded = yaml.safe_load(raw)
        restored = BrandingConfig.model_validate(reloaded)
        assert restored.captions.enabled == branding.captions.enabled
        assert restored.captions.max_words_per_line == branding.captions.max_words_per_line


class TestCaptionRegressions:
    """Task 3 regression coverage: edge cases, style fallback, and backward compat."""

    def test_all_invalid_entries_produces_valid_empty_ass(self, tmp_path: Path) -> None:
        """Word alignment where all entries fail validation produces a valid empty ASS."""
        words = [
            WordEntry("bad", -1.0, 0.5),  # negative start
            WordEntry("zero", 1.0, 1.0),  # zero duration
            WordEntry("inverted", 2.0, 0.5),  # end < start
        ]
        out = tmp_path / "empty_fallback.ass"
        generate_ass(words, CaptionStyleConfig(), out)
        assert out.exists()
        content = out.read_text(encoding="utf-8-sig")
        errors = validate_ass_syntax(content)
        assert errors == [], f"Invalid ASS produced for all-invalid input: {errors}"
        # No dialogue events expected
        assert "Dialogue:" not in content

    def test_single_word_group_produces_one_dialogue_event(self, tmp_path: Path) -> None:
        """A single word should produce exactly one dialogue event."""
        words = [WordEntry("hello", 1.0, 1.5)]
        out = tmp_path / "single.ass"
        generate_ass(words, CaptionStyleConfig(), out)
        content = out.read_text(encoding="utf-8-sig")
        dialogue_count = content.count("Dialogue:")
        assert dialogue_count == 1

    def test_long_speech_gap_splits_into_multiple_events(self, tmp_path: Path) -> None:
        """Words separated by a gap >1.5s must be grouped into distinct events."""
        words = [
            WordEntry("first", 0.0, 0.5),
            WordEntry("second", 3.0, 3.5),  # 2.5s gap
        ]
        out = tmp_path / "split.ass"
        generate_ass(words, CaptionStyleConfig(), out)
        content = out.read_text(encoding="utf-8-sig")
        assert content.count("Dialogue:") == 2

    def test_overlapping_words_produce_valid_ass(self, tmp_path: Path) -> None:
        """Words with overlapping timestamps should clamp and still produce valid ASS."""
        words = [
            WordEntry("a", 0.0, 1.5),
            WordEntry("b", 0.8, 1.8),  # overlaps with a
            WordEntry("c", 1.0, 2.0),  # also overlaps
        ]
        out = tmp_path / "overlapping.ass"
        generate_ass(words, CaptionStyleConfig(), out)
        assert out.exists()
        content = out.read_text(encoding="utf-8-sig")
        errors = validate_ass_syntax(content)
        assert errors == [], f"Overlapping words produced invalid ASS: {errors}"

    def test_default_style_fallback_when_branding_has_no_caption_style(self) -> None:
        """Branding with no caption_style attribute falls back to CaptionStyleConfig defaults."""

        class _BrandingNoCaptionStyle:
            highlight_color = "#FF0000"
            font_path = None
            # no caption_style attribute at all

        style = CaptionStyleConfig.from_branding(_BrandingNoCaptionStyle())
        assert style.text_color_hex == "#FFFFFF"
        assert style.font_size == 48
        assert style.bold is False

    def test_generate_ass_max_words_per_line_respected(self, tmp_path: Path) -> None:
        """max_words_per_line=3 should produce ceil(N/3) events for N tightly spaced words."""
        words = [WordEntry(f"w{i}", float(i) * 0.3, float(i) * 0.3 + 0.2) for i in range(9)]
        out = tmp_path / "max_words.ass"
        generate_ass(words, CaptionStyleConfig(), out, max_words_per_line=3, gap_threshold_s=5.0)
        content = out.read_text(encoding="utf-8-sig")
        assert content.count("Dialogue:") == 3

    def test_unsupported_aspect_ratio_raises_value_error(self, tmp_path: Path) -> None:
        """Unsupported aspect ratios must raise ValueError with actionable message."""
        words = [WordEntry("hello", 0.0, 0.5)]
        with pytest.raises(ValueError, match="Unsupported aspect_ratio"):
            generate_ass(words, CaptionStyleConfig(), tmp_path / "out.ass", aspect_ratio="4:3")

    def test_each_supported_ratio_produces_distinct_play_res(self, tmp_path: Path) -> None:
        """Each supported aspect ratio should encode a different PlayResX/PlayResY pair."""
        from podcast_pipeline.utils.captions import _PLAY_RES

        words = [WordEntry("test", 0.0, 0.5)]
        play_res_seen: set[tuple[int, int]] = set()

        for ratio in ["16:9", "9:16", "1:1"]:
            out = tmp_path / f"ratio_{ratio.replace(':', '_')}.ass"
            generate_ass(words, CaptionStyleConfig(), out, aspect_ratio=ratio)
            content = out.read_text(encoding="utf-8-sig")
            expected = _PLAY_RES[ratio]
            play_res_seen.add(expected)
            assert f"PlayResX: {expected[0]}" in content
            assert f"PlayResY: {expected[1]}" in content

        # All three ratios should have different play-res pairs.
        assert len(play_res_seen) == 3

    def test_highlight_colour_tag_in_dialogue_body(self, tmp_path: Path) -> None:
        """Each dialogue event must contain the \\1c highlight tag for coloured words."""
        words = [WordEntry("colour", 0.0, 0.5), WordEntry("test", 0.6, 1.0)]
        style = CaptionStyleConfig(highlight_color_hex="#FF0000")
        out = tmp_path / "colour_check.ass"
        generate_ass(words, style, out)
        content = out.read_text(encoding="utf-8-sig")
        assert r"\1c" in content, "Dialogue body must contain \\1c colour tags"
        # Highlight color should be the red ASS BGR equivalent.
        assert "&H000000FF" in content

    def test_srt_timestamp_function_unaffected_by_ass_import(self) -> None:
        """Importing captions module must not break legacy SRT timestamp helpers."""
        # Importing captions should not shadow or break the SRT/VTT utility.
        from podcast_pipeline.utils.time import seconds_to_srt_timestamp, seconds_to_vtt_timestamp

        srt_ts = seconds_to_srt_timestamp(3661.0)
        vtt_ts = seconds_to_vtt_timestamp(3661.0)

        # SRT uses HH:MM:SS,mmm format
        assert "01:01:01" in srt_ts
        assert "," in srt_ts

        # VTT uses HH:MM:SS.mmm format
        assert "01:01:01" in vtt_ts
        assert "." in vtt_ts

    def test_caption_module_is_independent_of_transcribe_stage(self) -> None:
        """captions.py must not import from the transcribe stage (no circular dependency)."""
        import importlib
        import importlib.util

        # Load the captions module spec without executing it to inspect its source.
        spec = importlib.util.find_spec("podcast_pipeline.utils.captions")
        assert spec is not None
        assert spec.origin is not None

        with open(spec.origin) as f:
            source = f.read()
        # captions.py must not import stages.transcribe.
        assert "stages.transcribe" not in source, (
            "captions.py must remain independent of the transcribe stage"
        )

    def test_load_word_alignment_with_empty_word_string_skipped(self, tmp_path: Path) -> None:
        """Word entries with empty/whitespace-only word strings should be skipped."""
        data = {
            "words": [
                {"word": "  ", "start": 0.0, "end": 0.5},  # whitespace only
                {"word": "", "start": 0.6, "end": 1.0},  # empty
                {"word": "valid", "start": 1.1, "end": 1.5},
            ]
        }
        p = tmp_path / "alignment.json"
        p.write_text(json.dumps(data))
        words = load_word_alignment(p)
        assert len(words) == 1
        assert words[0].word == "valid"
