"""ASS caption engine with word-level per-word highlight timing.

Generates Advanced SubStation Alpha (ASS) subtitle files from word-aligned
transcript data.  Three aspect-ratio templates are supported:

  * ``16:9``  — bottom-center, 16:9 landscape (YouTube, Twitter, LinkedIn …)
  * ``9:16``  — center-offset up from bottom (TikTok, Instagram Reels …)
                safe-zone positions text clear of the TikTok/Reels UI chrome
  * ``1:1``   — bottom-center, square (LinkedIn, Facebook …)

The generated ASS file uses per-word ``\\1c`` colour override tags to
highlight each word when it is spoken, then de-highlights it before the next
word begins.  The file is consumed by the FFmpeg ``ass=`` libass filter
during render burn-in.

Typical usage::

    words = load_word_alignment(job_dir / "transcribe" / "word_alignment.json")
    style = CaptionStyleConfig.from_branding(branding_profile)
    ass_path = generate_ass(words, style, output_path, aspect_ratio="9:16")
    # Then in FFmpeg:  -vf ass=<ass_path>

Format notes
------------
* Timestamps use centisecond precision: ``H:MM:SS.cc``.
* The ``[Script Info]`` section declares ``PlayResX`` / ``PlayResY`` per ratio.
* A single ``Default`` style block holds all the base styling parameters.
* Each dialogue event represents the *group of words* visible on screen;
  ``\\1c`` override tags inside the event text colour-animate word-by-word.
* The ``\\pos(x,y)`` ASS tag is used for deterministic positioning.
"""

from __future__ import annotations

import itertools
import json
import math
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum words shown in a single ASS dialogue event.
_MAX_WORDS_PER_LINE: int = 7

# Gap between caption groups — if gap between consecutive words exceeds this,
# start a new dialogue event.
_WORD_GAP_THRESHOLD_S: float = 1.5

# Minimum visible duration for a caption event (seconds).
_MIN_EVENT_DURATION_S: float = 0.25

# ASS centisecond precision helper.
_CS_PER_SECOND: int = 100

# Default colours in ASS BGR hex format (note: ASS uses AABBGGRR, we use
# &H00BBGGRR with alpha=0x00 = fully opaque).
_DEFAULT_TEXT_COLOUR_ASS: str = "&H00FFFFFF"  # white
_DEFAULT_HIGHLIGHT_COLOUR_ASS: str = "&H0000FFFF"  # yellow (BGRA: 00 FF FF 00)

# Fallback font name when no font_path is configured.
_DEFAULT_FONT_NAME: str = "Arial"

# ---------------------------------------------------------------------------
# Aspect-ratio safe-zone presets
# ---------------------------------------------------------------------------

# Playback resolution (virtual canvas dimensions used by ASS renderer).
# These are the reference dimensions; they do not match the final video
# resolution but drive all position/size calculations in the ASS file.
_PLAY_RES: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}

# (x_centre, y_bottom) of the text anchor inside the safe-zone, in virtual
# canvas units.  Values are expressed as fractions of the play-res dimensions
# and converted to integer pixel offsets at file-write time.
#
# 9:16 safe-zone: TikTok / Instagram Reels UI chrome occupies roughly the
# bottom 18 % of the screen.  We place text at ~82 % vertical to stay clear.
_SAFE_ZONE_POSITION_FRAC: dict[str, tuple[float, float]] = {
    "16:9": (0.50, 0.88),  # x=50 % (centred), y=88 % from top
    "9:16": (0.50, 0.82),  # x=50 % (centred), y=82 % from top (clears UI)
    "1:1": (0.50, 0.88),  # x=50 % (centred), y=88 % from top
}

# Font size multipliers per aspect ratio, relative to the base style size.
# 9:16 uses a slightly larger relative size since the video is taller.
_FONT_SIZE_MULTIPLIER: dict[str, float] = {
    "16:9": 1.0,
    "9:16": 1.15,
    "1:1": 1.0,
}

# ASS alignment codes: 2 = bottom-centre, which is used for all ratios.
# We override position with \pos so alignment mainly affects anchor semantics.
_ASS_ALIGNMENT: int = 2  # bottom-centre

# Supported aspect-ratio keys.
SUPPORTED_ASPECT_RATIOS: frozenset[str] = frozenset({"16:9", "9:16", "1:1"})

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WordEntry:
    """A single word with precise timing from transcript alignment data."""

    word: str
    start: float  # seconds
    end: float  # seconds


@dataclass
class CaptionStyleConfig:
    """Brand-driven style parameters for ASS caption generation.

    Maps ``BrandingProfile.caption_style`` and ``highlight_color`` into the
    set of values the ASS generator needs.
    """

    text_color_hex: str = "#FFFFFF"
    highlight_color_hex: str = "#FFFF00"
    font_size: int = 48
    bold: bool = False
    italic: bool = False
    shadow: bool = True
    font_name: str = _DEFAULT_FONT_NAME

    @classmethod
    def from_branding(cls, branding: Any) -> CaptionStyleConfig:
        """Build config from a BrandingProfile (or object with same attributes).

        Falls back to safe defaults when ``branding`` is ``None``.
        """
        if branding is None:
            return cls()

        caption = getattr(branding, "caption_style", None)
        highlight_hex = getattr(branding, "highlight_color", "#FFFF00")
        font_path = getattr(branding, "font_path", None)

        # Derive font name from path stem; fall back to default.
        font_name = _DEFAULT_FONT_NAME
        if font_path is not None:
            stem = Path(font_path).stem
            if stem:
                font_name = stem

        text_color_hex = "#FFFFFF"
        font_size = 48
        bold = False
        italic = False
        shadow = True

        if caption is not None:
            text_color_hex = getattr(caption, "color", "#FFFFFF")
            font_size = getattr(caption, "size", 48)
            bold = getattr(caption, "bold", False)
            italic = getattr(caption, "italic", False)
            shadow = getattr(caption, "shadow", True)
            caption_font = getattr(caption, "font", "")
            if caption_font:
                font_name = caption_font

        return cls(
            text_color_hex=text_color_hex,
            highlight_color_hex=highlight_hex,
            font_size=font_size,
            bold=bold,
            italic=italic,
            shadow=shadow,
            font_name=font_name,
        )


# ---------------------------------------------------------------------------
# Colour conversion helpers
# ---------------------------------------------------------------------------


def _css_hex_to_ass_bgr(css_hex: str) -> str:
    """Convert CSS ``#RRGGBB`` or ``#RGB`` hex string to ASS ``&H00BBGGRR``.

    ASS uses little-endian BGR channel ordering (reverse of CSS RGB) with a
    leading alpha byte ``00`` for fully opaque.

    >>> _css_hex_to_ass_bgr("#FFFF00")
    '&H0000FFFF'
    >>> _css_hex_to_ass_bgr("#FFF")
    '&H00FFFFFF'
    """
    stripped = css_hex.strip().lstrip("#")
    if len(stripped) == 3:
        stripped = "".join(c * 2 for c in stripped)
    if len(stripped) != 6:
        return _DEFAULT_TEXT_COLOUR_ASS
    try:
        rr = stripped[0:2]
        gg = stripped[2:4]
        bb = stripped[4:6]
        return f"&H00{bb}{gg}{rr}".upper()
    except (IndexError, ValueError):
        return _DEFAULT_TEXT_COLOUR_ASS


# ---------------------------------------------------------------------------
# Timestamp formatting
# ---------------------------------------------------------------------------


def _seconds_to_ass_timestamp(seconds: float) -> str:
    """Format a float seconds value as ``H:MM:SS.cc`` for ASS events.

    ASS uses centisecond precision in the format ``H:MM:SS.cc``.

    >>> _seconds_to_ass_timestamp(75.5)
    '0:01:15.50'
    >>> _seconds_to_ass_timestamp(0.0)
    '0:00:00.00'
    """
    safe = max(seconds, 0.0)
    total_cs = math.floor(safe * _CS_PER_SECOND + 0.5)  # round to nearest cs
    cs = total_cs % _CS_PER_SECOND
    total_s = total_cs // _CS_PER_SECOND
    secs = total_s % 60
    total_m = total_s // 60
    mins = total_m % 60
    hours = total_m // 60
    return f"{hours}:{mins:02d}:{secs:02d}.{cs:02d}"


# ---------------------------------------------------------------------------
# Word entry loading
# ---------------------------------------------------------------------------


def load_word_alignment(path: Path) -> list[WordEntry]:
    """Load word timing from a ``word_alignment.json`` artifact.

    The file may contain:
    - A top-level ``words`` list of ``{word, start, end}`` dicts.
    - A top-level ``segments`` list, each containing a ``words`` list.
    - Inline word-level objects at the top level (list of word dicts).

    Returns an empty list and logs a warning on parse failure.  Silently
    skips entries with missing or invalid timing fields.

    Args:
        path: Absolute path to ``word_alignment.json``.

    Returns:
        Sorted list of :class:`WordEntry` objects.
    """
    if not path.exists():
        logger.warning("word_alignment_missing", path=str(path))
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("word_alignment_load_failed", path=str(path), error=str(exc))
        return []

    entries: list[WordEntry] = []

    def _add(obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        word = str(obj.get("word") or "").strip()
        if not word:
            return
        try:
            start = float(obj["start"])
            end = float(obj["end"])
        except (KeyError, TypeError, ValueError):
            return
        if end <= start or start < 0:
            return
        entries.append(WordEntry(word=word, start=start, end=end))

    if isinstance(raw, list):
        for item in raw:
            _add(item)
    elif isinstance(raw, dict):
        top_words = raw.get("words")
        if isinstance(top_words, list):
            for item in top_words:
                _add(item)

        segments = raw.get("segments")
        if isinstance(segments, list):
            for segment in segments:
                if isinstance(segment, dict):
                    seg_words = segment.get("words")
                    if isinstance(seg_words, list):
                        for item in seg_words:
                            _add(item)

    entries.sort(key=lambda e: e.start)
    return entries


# ---------------------------------------------------------------------------
# Word grouping
# ---------------------------------------------------------------------------


def _group_words_into_events(
    words: list[WordEntry],
    max_words_per_line: int = _MAX_WORDS_PER_LINE,
    gap_threshold_s: float = _WORD_GAP_THRESHOLD_S,
) -> list[list[WordEntry]]:
    """Partition word entries into groups that form individual ASS dialogue events.

    A new group starts when:
    - ``max_words_per_line`` words have been accumulated, or
    - the gap between consecutive words exceeds ``gap_threshold_s``.

    Returns a list of word groups (each group is a list of WordEntry).

    >>> from podcast_pipeline.utils.captions import WordEntry, _group_words_into_events
    >>> words = [WordEntry("hello", 0.0, 0.5), WordEntry("world", 0.6, 1.0)]
    >>> groups = _group_words_into_events(words, max_words_per_line=3)
    >>> len(groups) == 1 and groups[0][0].word == "hello"
    True
    """
    if not words:
        return []

    groups: list[list[WordEntry]] = []
    current: list[WordEntry] = [words[0]]

    for prev, curr in itertools.pairwise(words):
        gap = curr.start - prev.end
        if len(current) >= max_words_per_line or gap >= gap_threshold_s:
            groups.append(current)
            current = [curr]
        else:
            current.append(curr)

    if current:
        groups.append(current)

    return groups


# ---------------------------------------------------------------------------
# ASS header builders
# ---------------------------------------------------------------------------


def _build_script_info(play_res_x: int, play_res_y: int) -> str:
    """Return the ``[Script Info]`` section as a string."""
    return textwrap.dedent(
        f"""\
        [Script Info]
        ScriptType: v4.00+
        PlayResX: {play_res_x}
        PlayResY: {play_res_y}
        WrapStyle: 0
        ScaledBorderAndShadow: yes
        YCbCr Matrix: None
        """
    )


def _build_styles_section(
    style: CaptionStyleConfig,
    aspect_ratio: str,
) -> str:
    """Return the ``[V4+ Styles]`` section for the given style config."""
    play_res_x, play_res_y = _PLAY_RES.get(aspect_ratio, (1920, 1080))
    font_size_multiplier = _FONT_SIZE_MULTIPLIER.get(aspect_ratio, 1.0)
    effective_font_size = round(style.font_size * font_size_multiplier)

    text_ass = _css_hex_to_ass_bgr(style.text_color_hex)

    bold_flag = "-1" if style.bold else "0"
    italic_flag = "-1" if style.italic else "0"
    shadow_depth = "2" if style.shadow else "0"
    outline_depth = "2" if style.shadow else "1"

    # ASS format field: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,
    # OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,
    # ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow,
    # Alignment, MarginL, MarginR, MarginV, Encoding
    style_line = (
        f"Style: Default,{style.font_name},{effective_font_size},"
        f"{text_ass},&H000000FF,&H00000000,&H80000000,"
        f"{bold_flag},{italic_flag},0,0,"
        f"100,100,0,0,1,{outline_depth},{shadow_depth},"
        f"{_ASS_ALIGNMENT},10,10,10,1"
    )
    _ = play_res_x, play_res_y  # used for size calc above; suppress unused warning
    return (
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        + style_line
        + "\n"
    )


# ---------------------------------------------------------------------------
# Per-word highlight tag builder
# ---------------------------------------------------------------------------


def _build_dialogue_text(
    group: list[WordEntry],
    text_ass_color: str,
    highlight_ass_color: str,
) -> str:
    r"""Build the ASS dialogue text body with per-word highlight colour tags.

    For each word in ``group``:
    - Highlight colour (``\1c``) is applied at the word's start using an
      ``{\t(...)}`` timing transform.
    - Text colour is restored after the word's end using a second ``{\t}``.

    Because we use a single dialogue event that covers the group's full
    duration, we use ``{\t(start_cs, end_cs, \\1c&HCOLOUR&)}`` to trigger
    exact-start colour transitions.

    The resulting text looks like::

        {\1c&Htext&}word1 {\t(150,150,\1c&Hhighlight&)}word2 ...

    All timings are relative to the event start (offset 0 = event start).
    """
    if not group:
        return ""

    event_start = group[0].start
    parts: list[str] = []

    for i, entry in enumerate(group):
        word_start_cs = math.floor((entry.start - event_start) * _CS_PER_SECOND)
        word_end_cs = math.floor((entry.end - event_start) * _CS_PER_SECOND)
        # Clamp to non-negative
        word_start_cs = max(word_start_cs, 0)
        word_end_cs = max(word_end_cs, word_start_cs + 1)

        # At word start: switch to highlight colour instantly (duration=0 transform)
        highlight_tag = f"{{\\t({word_start_cs},{word_start_cs},\\1c{highlight_ass_color})}}"
        # After word ends: revert to text colour instantly
        revert_tag = f"{{\\t({word_end_cs},{word_end_cs},\\1c{text_ass_color})}}"

        if i == 0:
            # First word starts pre-highlighted
            parts.append(f"{{\\1c{highlight_ass_color}}}{highlight_tag}{entry.word}{revert_tag}")
        else:
            parts.append(f"{highlight_tag}{entry.word}{revert_tag}")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Dialogue event builder
# ---------------------------------------------------------------------------


def _build_events_section(
    word_groups: list[list[WordEntry]],
    style: CaptionStyleConfig,
    aspect_ratio: str,
) -> str:
    """Build the ``[Events]`` section from word groups.

    Each group becomes one ``Dialogue`` line.  Position is derived from the
    safe-zone preset for the given aspect ratio.
    """
    play_res_x, play_res_y = _PLAY_RES.get(aspect_ratio, (1920, 1080))
    pos_frac_x, pos_frac_y = _SAFE_ZONE_POSITION_FRAC.get(aspect_ratio, (0.50, 0.88))
    pos_x = round(play_res_x * pos_frac_x)
    pos_y = round(play_res_y * pos_frac_y)

    text_ass = _css_hex_to_ass_bgr(style.text_color_hex)
    highlight_ass = _css_hex_to_ass_bgr(style.highlight_color_hex)

    lines: list[str] = [
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for group in word_groups:
        if not group:
            continue

        event_start = group[0].start
        event_end = max(group[-1].end, event_start + _MIN_EVENT_DURATION_S)

        start_ts = _seconds_to_ass_timestamp(event_start)
        end_ts = _seconds_to_ass_timestamp(event_end)

        body = _build_dialogue_text(group, text_ass, highlight_ass)
        pos_tag = f"{{\\an{_ASS_ALIGNMENT}\\pos({pos_x},{pos_y})}}"
        text = f"{pos_tag}{body}"

        lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_ass(
    words: list[WordEntry],
    style: CaptionStyleConfig,
    output_path: Path,
    *,
    aspect_ratio: str = "16:9",
    max_words_per_line: int = _MAX_WORDS_PER_LINE,
    gap_threshold_s: float = _WORD_GAP_THRESHOLD_S,
) -> Path:
    """Generate an ASS caption file from word alignment data.

    Creates a syntactically valid ASS subtitle file with per-word colour
    highlight animation, positioned within the safe zone for the target
    aspect ratio.

    Args:
        words: Sorted list of :class:`WordEntry` objects from the transcript
            alignment.  Pass the output of :func:`load_word_alignment`.
        style: Caption style configuration.  Use
            :meth:`CaptionStyleConfig.from_branding` to derive from a
            ``BrandingProfile``.
        output_path: Destination path for the generated ``.ass`` file.
            Parent directories are created automatically.
        aspect_ratio: Target aspect ratio.  Must be one of
            :data:`SUPPORTED_ASPECT_RATIOS`.  Defaults to ``"16:9"``.
        max_words_per_line: Maximum words per dialogue event.
        gap_threshold_s: Speech gap (seconds) that triggers a new event.

    Returns:
        Resolved path to the written ``.ass`` file.

    Raises:
        ValueError: If ``aspect_ratio`` is not supported.
        OSError: If the output file cannot be written.
    """
    if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
        supported = ", ".join(sorted(SUPPORTED_ASPECT_RATIOS))
        raise ValueError(f"Unsupported aspect_ratio '{aspect_ratio}'. Expected one of: {supported}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    play_res_x, play_res_y = _PLAY_RES[aspect_ratio]

    if not words:
        logger.warning(
            "generate_ass_no_words",
            output=str(output_path),
            aspect_ratio=aspect_ratio,
        )
        # Write an empty-but-valid ASS file so burn-in doesn't fail.
        _write_empty_ass(output_path, play_res_x, play_res_y, style, aspect_ratio)
        return output_path.resolve()

    # Validate and clamp overlapping word timings.
    validated = _validate_and_clamp_words(words)
    if not validated:
        logger.warning(
            "generate_ass_all_words_invalid",
            output=str(output_path),
            aspect_ratio=aspect_ratio,
        )
        _write_empty_ass(output_path, play_res_x, play_res_y, style, aspect_ratio)
        return output_path.resolve()

    groups = _group_words_into_events(
        validated,
        max_words_per_line=max_words_per_line,
        gap_threshold_s=gap_threshold_s,
    )

    script_info = _build_script_info(play_res_x, play_res_y)
    styles_section = _build_styles_section(style, aspect_ratio)
    events_section = _build_events_section(groups, style, aspect_ratio)

    ass_content = "\n".join([script_info, styles_section, events_section])

    output_path.write_text(ass_content, encoding="utf-8-sig")  # UTF-8 BOM for libass compat

    logger.info(
        "generate_ass_complete",
        output=str(output_path),
        aspect_ratio=aspect_ratio,
        word_count=len(validated),
        event_count=len(groups),
    )
    return output_path.resolve()


def generate_ass_from_json(
    alignment_path: Path,
    style: CaptionStyleConfig,
    output_path: Path,
    *,
    aspect_ratio: str = "16:9",
) -> Path:
    """Convenience wrapper: load word alignment JSON then call :func:`generate_ass`.

    Args:
        alignment_path: Path to ``word_alignment.json``.
        style: Caption style configuration.
        output_path: Output ``.ass`` file path.
        aspect_ratio: Target aspect ratio key.

    Returns:
        Resolved path to the generated ``.ass`` file.
    """
    words = load_word_alignment(alignment_path)
    return generate_ass(words, style, output_path, aspect_ratio=aspect_ratio)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_and_clamp_words(words: list[WordEntry]) -> list[WordEntry]:
    """Filter out invalid entries and clamp overlapping timings.

    Rules:
    - Skip entries where ``end <= start`` (zero/negative duration).
    - Skip entries where ``start < 0``.
    - If a word's start overlaps with the previous word's end, clamp its
      start to the previous word's end (maintains ordering).

    Returns a new sorted list of clamped, valid WordEntry objects.
    """
    valid: list[WordEntry] = []
    prev_end: float = 0.0

    for entry in sorted(words, key=lambda e: e.start):
        if entry.start < 0 or entry.end <= entry.start:
            continue
        clamped_start = max(entry.start, prev_end)
        if clamped_start >= entry.end:
            # After clamping, duration becomes zero — skip this word.
            continue
        valid.append(WordEntry(word=entry.word, start=clamped_start, end=entry.end))
        prev_end = entry.end

    return valid


def _write_empty_ass(
    output_path: Path,
    play_res_x: int,
    play_res_y: int,
    style: CaptionStyleConfig,
    aspect_ratio: str,
) -> None:
    """Write a valid but empty ASS file (no dialogue events)."""
    script_info = _build_script_info(play_res_x, play_res_y)
    styles_section = _build_styles_section(style, aspect_ratio)
    events_section = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    ass_content = "\n".join([script_info, styles_section, events_section])
    output_path.write_text(ass_content, encoding="utf-8-sig")


def validate_ass_syntax(ass_text: str) -> list[str]:
    """Perform basic structural validation on an ASS file string.

    Checks for the presence of required sections and that dialogue event
    timestamps are well-formed.  Returns a list of error descriptions (empty
    means valid).

    This function is used in tests and can be called on the file content
    before passing to FFmpeg.

    Args:
        ass_text: Full ASS file content as a string.

    Returns:
        List of error strings.  Empty list means no errors found.
    """
    errors: list[str] = []

    required_sections = ["[Script Info]", "[V4+ Styles]", "[Events]"]
    for section in required_sections:
        if section not in ass_text:
            errors.append(f"Missing required section: {section}")

    # Validate timestamp format in Dialogue lines.
    dialogue_re = re.compile(
        r"^Dialogue:\s*\d+,"
        r"(\d+:\d{2}:\d{2}\.\d{2}),"  # start
        r"(\d+:\d{2}:\d{2}\.\d{2}),",  # end
        re.MULTILINE,
    )
    for match in dialogue_re.finditer(ass_text):
        start_ts = match.group(1)
        end_ts = match.group(2)
        start_s = _ass_timestamp_to_seconds(start_ts)
        end_s = _ass_timestamp_to_seconds(end_ts)
        if start_s is None:
            errors.append(f"Invalid start timestamp in Dialogue: {start_ts}")
        if end_s is None:
            errors.append(f"Invalid end timestamp in Dialogue: {end_ts}")
        if start_s is not None and end_s is not None and end_s <= start_s:
            errors.append(f"Dialogue event end ({end_ts}) is not after start ({start_ts})")

    return errors


def _ass_timestamp_to_seconds(ts: str) -> float | None:
    """Parse ``H:MM:SS.cc`` into float seconds, or ``None`` on failure."""
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2})\.(\d{2})", ts.strip())
    if not match:
        return None
    h, m, s, cs = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
    return h * 3600.0 + m * 60.0 + s + cs / 100.0
