# Smooth Editing & Filler Word Control — Technical Spec

**Date**: 2026-02-19
**Parent Doc**: [`2026-02-19-audio-video-enhancement-plan.md`](./2026-02-19-audio-video-enhancement-plan.md)
**Priority**: P0 — directly affects output quality today

---

## 1. Scope

This spec covers the two P0 features in detail:

1. **Smooth cuts** — crossfades, word-boundary snapping, pop prevention
2. **Filler word editorial control** — per-word keep/remove, categories, context preview

These are the most impactful changes because they fix problems that are **audible in every output** the pipeline produces today.

---

## 2. Current Behavior (How Cuts Work Today)

### 2.1 The Edit Filter Chain

`render.py:_build_edit_plan_filter()` (lines 910-961) works like this:

1. Collects all `filler_cuts` and `content_cuts` from `edit_plan.json`
2. Merges overlapping ranges into one unified cut list
3. Inverts the cut list to get "keep ranges" (the parts of the video to keep)
4. For each keep range, generates:
   ```
   [0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{n}]
   [0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{n}]
   ```
5. Concatenates all kept segments:
   ```
   [v0][a0][v1][a1]...concat=n={N}:v=1:a=1[outv][outa]
   ```

### 2.2 What's Wrong

- **No fade at segment edges** — audio cuts instantly, causing clicks/pops
- **No crossfade overlap** — segments butt up against each other with zero blending
- **No video transition** — visual jump cuts when speaker position shifts
- **Cut points are wherever the AI said** — no validation against word boundaries
- **All fillers auto-approved** — no per-word editorial control

---

## 3. Smooth Cuts — Detailed Design

### 3.1 Three Layers of Smoothing

We implement smoothing in three cumulative layers:

| Layer | What | When | Default |
|-------|------|------|---------|
| **Micro-fade** | 10-30ms fade-in/out at raw segment edges | Always | 30ms |
| **Audio crossfade** | 50-200ms acrossfade between segments | Content cuts | 150ms |
| **Video dissolve** | 100-500ms xfade dissolve | Content cuts only | 300ms |

Filler cuts (short removal of "um"/"uh") only get the micro-fade. Content cuts (longer removals of dead air, tangents, etc.) get all three layers.

### 3.2 Updated Filter Chain

#### Before (current):
```
# Segment N:
[0:v]trim=start=10:end=25,setpts=PTS-STARTPTS[v0];
[0:a]atrim=start=10:end=25,asetpts=PTS-STARTPTS[a0];

# Segment N+1:
[0:v]trim=start=30:end=45,setpts=PTS-STARTPTS[v1];
[0:a]atrim=start=30:end=45,asetpts=PTS-STARTPTS[a1];

# Hard concat:
[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]
```

#### After (with smoothing):
```
# Segment N (with micro-fade on edges):
[0:v]trim=start=10:end=25,setpts=PTS-STARTPTS[v0];
[0:a]atrim=start=10:end=25,asetpts=PTS-STARTPTS,
      afade=t=in:st=0:d=0.03,
      afade=t=out:st=14.97:d=0.03[a0];

# Segment N+1 (same micro-fades):
[0:v]trim=start=30:end=45,setpts=PTS-STARTPTS[v1];
[0:a]atrim=start=30:end=45,asetpts=PTS-STARTPTS,
      afade=t=in:st=0:d=0.03,
      afade=t=out:st=14.97:d=0.03[a1];

# Audio crossfade (for content cuts):
[a0][a1]acrossfade=d=0.15:c1=tri:c2=tri[outa];

# Video dissolve (for content cuts):
[v0][v1]xfade=transition=fade:duration=0.3:offset=14.7[outv];
```

### 3.3 How to Chain Multiple Segments

For N segments with content cut crossfades, the acrossfade and xfade must be chained iteratively:

```python
def _build_crossfade_chain(segments: list, crossfade_s: float, dissolve_s: float):
    """Build iterative crossfade/dissolve chain for N segments."""
    filters = []

    # First pair
    filters.append(f"[a0][a1]acrossfade=d={crossfade_s}:c1=tri:c2=tri[ax1]")
    filters.append(f"[v0][v1]xfade=transition=fade:duration={dissolve_s}"
                   f":offset={segments[0].duration - dissolve_s}[vx1]")

    # Subsequent pairs chain from previous output
    for i in range(2, len(segments)):
        prev_label = f"ax{i-1}"
        next_label = f"ax{i}"
        filters.append(f"[{prev_label}][a{i}]acrossfade=d={crossfade_s}:c1=tri:c2=tri[{next_label}]")

        prev_v_label = f"vx{i-1}"
        next_v_label = f"vx{i}"
        cumulative_offset = sum(s.duration for s in segments[:i]) - dissolve_s * (i)
        filters.append(f"[{prev_v_label}][v{i}]xfade=transition=fade:duration={dissolve_s}"
                       f":offset={cumulative_offset}[{next_v_label}]")

    return filters
```

### 3.4 Decision Tree: Which Smoothing to Apply

```
For each splice point between segment[n] and segment[n+1]:

Is segment[n+1] a filler cut?
  YES → Apply micro-fade only (30ms)
        - Filler cuts are 0.1-0.5s long
        - Video position barely changes
        - Crossfade would be longer than the cut itself
  NO  → Content cut — apply all three layers:
        1. Micro-fade (30ms) on segment edges
        2. Audio crossfade (150ms)
        3. Video dissolve (300ms) if enabled
```

### 3.5 Pop/Click Safety Net

After all cuts and crossfades, apply `adeclick` to the final audio output:

```
[outa]adeclick=threshold=10:window=50[outa_clean]
```

This catches any remaining click artifacts from imperfect cuts. Applied in `_build_audio_enhancement_filters()` at the end of the chain.

---

## 4. Word-Boundary Snapping — Detailed Design

### 4.1 The Problem

The AI (Gemini/Kimi) suggests cuts using time ranges like:
```json
{"start_seconds": 45.2, "end_seconds": 52.7, "reason": "off-topic tangent"}
```

The time `45.2` might land in the middle of the word "interesting" — resulting in:
```
"...that's really inter-[CUT]-...so anyway..."
```

### 4.2 The Solution

We already have **word-level timestamps** from faster-whisper. Every word has:
```json
{"word": "interesting", "start": 44.8, "end": 45.4, "confidence": 0.95}
```

Before applying any cut, we snap the cut boundaries to the nearest **inter-word silence gap**.

### 4.3 Algorithm

```python
# utils/editing.py

from dataclasses import dataclass

@dataclass
class WordBoundary:
    """A gap between two words where it's safe to cut."""
    time: float             # Midpoint of the gap
    gap_duration: float     # How long the silence is
    word_before: str        # The word ending before this gap
    word_after: str         # The word starting after this gap

def find_word_boundaries(words: list[dict]) -> list[WordBoundary]:
    """Extract all inter-word silence gaps from transcript words."""
    boundaries = []
    for i in range(len(words) - 1):
        gap_start = words[i]["end"]
        gap_end = words[i + 1]["start"]
        gap_duration = gap_end - gap_start
        if gap_duration > 0.01:  # At least 10ms gap
            boundaries.append(WordBoundary(
                time=(gap_start + gap_end) / 2,
                gap_duration=gap_duration,
                word_before=words[i]["word"],
                word_after=words[i + 1]["word"],
            ))
    return boundaries

def snap_to_word_boundary(
    cut_time: float,
    boundaries: list[WordBoundary],
    direction: str = "nearest",   # "nearest" | "before" | "after"
    max_shift_s: float = 0.3,     # Don't shift more than 300ms
    prefer_longer_gaps: bool = True,  # Prefer cutting in longer silences
) -> float:
    """Snap a cut time to the nearest inter-word silence gap.

    Args:
        cut_time: The raw cut time from the AI
        boundaries: Pre-computed word boundaries from transcript
        direction: Which direction to search
            - "nearest": Closest boundary in either direction
            - "before": Closest boundary before cut_time (for cut starts)
            - "after": Closest boundary after cut_time (for cut ends)
        max_shift_s: Maximum allowed shift from original time
        prefer_longer_gaps: If True, slightly prefer boundaries with
                           longer silence gaps (weighted distance)

    Returns:
        Snapped cut time, or original if no valid boundary found
    """
    candidates = []
    for b in boundaries:
        distance = abs(b.time - cut_time)
        if distance > max_shift_s:
            continue

        if direction == "before" and b.time > cut_time:
            continue
        if direction == "after" and b.time < cut_time:
            continue

        # Score: lower is better
        # Base: distance from desired cut point
        # Bonus: longer gaps are preferred (safer to cut in silence)
        score = distance
        if prefer_longer_gaps:
            gap_bonus = min(b.gap_duration * 0.1, 0.05)  # Up to 50ms bonus
            score -= gap_bonus

        candidates.append((score, b))

    if not candidates:
        return cut_time  # No valid boundary found, use original

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1].time


def snap_cut_range(
    start: float,
    end: float,
    boundaries: list[WordBoundary],
    max_shift_s: float = 0.3,
) -> tuple[float, float]:
    """Snap both ends of a cut range to word boundaries.

    The start snaps to the nearest boundary BEFORE the cut
    (so we don't lose the beginning of the first cut word).
    The end snaps to the nearest boundary AFTER the cut
    (so we don't lose the end of the last kept word).
    """
    snapped_start = snap_to_word_boundary(
        start, boundaries, direction="before", max_shift_s=max_shift_s
    )
    snapped_end = snap_to_word_boundary(
        end, boundaries, direction="after", max_shift_s=max_shift_s
    )

    # Ensure range is still valid after snapping
    if snapped_end <= snapped_start:
        return start, end  # Fall back to original

    return snapped_start, snapped_end
```

### 4.4 Integration Point

In `render.py`, before building the edit filter:

```python
def _build_edit_plan_filter(self, edit_plan, src_duration, vf_filters, af_filters):
    # Load word timestamps from transcript
    transcript_path = self.job_dir / "analysis" / "transcript.json"
    words = []
    if transcript_path.exists():
        data = json.loads(transcript_path.read_text())
        words = data.get("words", [])

    boundaries = find_word_boundaries(words)

    # Snap all cut ranges to word boundaries
    for cut in edit_plan.filler_cuts + edit_plan.content_cuts:
        cut.start_seconds, cut.end_seconds = snap_cut_range(
            cut.start_seconds, cut.end_seconds, boundaries
        )

    # ... continue with existing filter building ...
```

### 4.5 Sentence-Aware Cuts (Future Enhancement)

For content cuts specifically, we could further validate that cuts don't land mid-sentence. This requires:

1. Sentence boundary detection from transcript text (using punctuation or NLP)
2. Prefer cutting at sentence boundaries when possible
3. If the AI's cut range starts/ends mid-sentence, expand to the nearest sentence boundary

This is a future enhancement, not part of the initial implementation.

---

## 5. Filler Word Editorial Control — Detailed Design

### 5.1 Current Flow

```
transcribe.py → filler_cuts.json → review.py (auto-approve ALL) → edit_plan.json → render.py
```

### 5.2 New Flow

```
transcribe.py → filler_cuts_enriched.json → review.py → filler_review_ui.py → edit_plan.json → render.py
                 (with context,                (apply category rules,
                  categories,                    present for review)
                  sentence position)
```

### 5.3 Enriched Filler Detection

Update `transcribe.py:_detect_fillers()` to produce:

```json
{
  "fillers": [
    {
      "index": 0,
      "word": "um",
      "start": 12.5,
      "end": 12.82,
      "confidence": 0.92,
      "category": "disfluency",
      "default_action": "remove",
      "context": {
        "before": ["and", "then", "I", "was", "thinking"],
        "after": ["about", "the", "whole", "situation"],
        "before_text": "and then I was thinking",
        "after_text": "about the whole situation"
      },
      "speaker": "Speaker 1",
      "sentence_position": "mid",
      "surrounding_pause_ms": 180
    },
    {
      "index": 1,
      "word": "like",
      "start": 28.1,
      "end": 28.35,
      "confidence": 0.76,
      "category": "hedge",
      "default_action": "review",
      "context": {
        "before": ["it", "was"],
        "after": ["a", "really", "big", "deal"],
        "before_text": "it was",
        "after_text": "a really big deal"
      },
      "speaker": "Speaker 1",
      "sentence_position": "mid",
      "surrounding_pause_ms": 50
    }
  ],
  "summary": {
    "total": 47,
    "by_category": {
      "disfluency": 32,
      "hedge": 15
    },
    "by_word": {
      "um": 18,
      "uh": 14,
      "like": 9,
      "you know": 6
    },
    "auto_remove_count": 32,
    "needs_review_count": 15
  }
}
```

### 5.4 Category Rules Engine

```python
# config/settings.py

class FillerCategory(BaseModel):
    """Configuration for a category of filler words."""
    words: list[str]
    default_action: str = "review"  # "remove" | "keep" | "review"
    min_confidence: float = 0.5
    min_duration_ms: float = 100
    max_duration_ms: float = 2000

class FillerWordConfig(BaseModel):
    """Filler word detection and editorial configuration."""
    disfluencies: FillerCategory = FillerCategory(
        words=["um", "uh", "hmm", "er", "ah"],
        default_action="remove",
        min_confidence=0.5,
    )
    hedge_words: FillerCategory = FillerCategory(
        words=["like", "you know", "basically", "actually", "so", "right", "i mean"],
        default_action="review",
        min_confidence=0.7,
    )
    custom: FillerCategory = FillerCategory(
        words=[],
        default_action="review",
        min_confidence=0.6,
    )
    context_words: int = 5   # Number of words before/after to include
    padding_ms: float = 50   # Padding around filler for cut
```

### 5.5 Review Stage Changes

#### Updated ReviewDecisions Model

```python
class FillerDecision(BaseModel):
    """Per-filler keep/remove decision."""
    index: int
    action: str = "remove"     # "remove" | "keep"
    reason: str = ""           # Optional note

class ReviewDecisions(BaseModel):
    # Old: approved_filler_cuts: list[int]
    # New:
    filler_decisions: list[FillerDecision] = Field(default_factory=list)
    filler_bulk_rules: dict[str, str] = Field(default_factory=dict)
    # e.g. {"um": "remove_all", "like": "keep_all"}

    # ... rest unchanged ...
```

#### Auto-Approve Logic

Instead of approving ALL fillers, respect the category config:

```python
def _create_initial_review_state(self, job_dir: Path) -> None:
    """Create initial review state with category-aware defaults."""
    fillers = load_enriched_fillers(job_dir)

    decisions = ReviewDecisions()
    for filler in fillers:
        if filler["default_action"] == "remove":
            decisions.filler_decisions.append(
                FillerDecision(index=filler["index"], action="remove")
            )
        elif filler["default_action"] == "keep":
            decisions.filler_decisions.append(
                FillerDecision(index=filler["index"], action="keep")
            )
        # "review" → no decision yet, requires manual input
```

### 5.6 Streamlit UI for Filler Review

The filler review section shows:

```
┌─────────────────────────────────────────────────────┐
│ Filler Words Review                                 │
│                                                     │
│ ═══ Disfluencies (32 found — 32 auto-removed) ═══  │
│                                                     │
│ Bulk: [Remove All] [Keep All] [Review Each]         │
│                                                     │
│  ☑ #1  "um"  12.5s  │ "...I was thinking [UM]      │
│                      │  about the whole..."         │
│  ☑ #2  "uh"  18.3s  │ "...is that the [UH]         │
│                      │  right approach..."          │
│  ☑ #3  "um"  24.7s  │ "...we should [UM]           │
│                      │  probably consider..."       │
│                                                     │
│ ═══ Hedge Words (15 found — needs review) ═══════   │
│                                                     │
│ Bulk: [Remove All] [Keep All] [Review Each]         │
│                                                     │
│  ☐ #33 "like" 28.1s │ "...it was [LIKE] a          │
│                      │  really big deal..."         │
│     → Keep: may be intentional emphasis             │
│                                                     │
│  ☐ #34 "you know" 35.6s │ "...[YOU KNOW] when      │
│                          │  things get complicated"  │
│     → Review: could be rhetorical                   │
│                                                     │
│ [💾 Save Decisions]  [▶ Preview Audio]              │
└─────────────────────────────────────────────────────┘
```

**Key UI features**:
- Grouped by category (disfluencies vs hedge words)
- Checkbox per filler: checked = will be removed
- Context text shown inline with filler word highlighted
- Bulk actions per category
- Audio preview button (plays 3s around the filler word via Streamlit audio player)
- Count summary at the top

---

## 6. Edit Plan Model Updates

### 6.1 Enhanced FillerCutRange

```python
class FillerCutRange(BaseModel):
    """Approved filler cut range with editorial metadata."""

    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    word: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    # New fields
    category: str = "disfluency"       # "disfluency" | "hedge" | "custom"
    context_before: str = ""            # Words before the filler
    context_after: str = ""             # Words after the filler
    editorial_action: str = "remove"    # "remove" | "keep" (final decision)
    editorial_note: str = ""            # Podcaster's note
    snapped: bool = False               # Whether boundaries were word-snapped
    original_start: float | None = None # Pre-snap start time
    original_end: float | None = None   # Pre-snap end time

    # Smoothing hint for render stage
    smoothing: str = "micro_fade"       # "micro_fade" | "crossfade"
```

### 6.2 Enhanced ContentCutRange

```python
class ContentCutRange(BaseModel):
    """Approved content cut range with smoothing metadata."""

    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    reason: str = ""

    # New fields
    snapped: bool = False
    original_start: float | None = None
    original_end: float | None = None
    smoothing: str = "crossfade"        # "crossfade" | "dissolve" | "micro_fade"
    crossfade_ms: float | None = None   # Override config default
    dissolve_ms: float | None = None    # Override config default
```

---

## 7. Test Plan

### 7.1 Word Boundary Snapping Tests

```python
# tests/test_editing.py

def test_snap_to_nearest_boundary():
    """Cut at 12.5s should snap to gap at 12.4s (between 'thinking' and 'about')."""

def test_snap_before():
    """Cut start should snap to boundary before the cut point."""

def test_snap_after():
    """Cut end should snap to boundary after the cut point."""

def test_snap_max_shift_respected():
    """Should not shift more than max_shift_s even if a better gap exists farther."""

def test_snap_no_valid_boundary():
    """If no boundary within max_shift, return original time."""

def test_snap_prefers_longer_gaps():
    """Between two equidistant boundaries, prefer the one with a longer silence gap."""

def test_snap_cut_range_preserves_validity():
    """Snapped range should still have end > start."""

def test_snap_cut_range_fallback():
    """If snapping would create invalid range, return original range."""
```

### 7.2 Crossfade Filter Tests

```python
# tests/test_render_crossfade.py

def test_micro_fade_applied_to_all_segments():
    """Every segment should have afade in/out at edges."""

def test_crossfade_applied_for_content_cuts():
    """acrossfade should appear between segments separated by content cuts."""

def test_no_crossfade_for_filler_cuts():
    """Filler cut segments should only get micro-fade, not acrossfade."""

def test_dissolve_applied_for_content_cuts():
    """xfade should appear between video segments at content cut points."""

def test_dissolve_disabled_when_zero():
    """When dissolve_ms = 0, no xfade filter should be generated."""

def test_adeclick_in_final_chain():
    """adeclick safety net should be in the audio enhancement chain."""
```

### 7.3 Filler Category Tests

```python
# tests/test_filler_categories.py

def test_disfluency_auto_removed():
    """Words in disfluency category should have default_action='remove'."""

def test_hedge_word_needs_review():
    """Words in hedge category should have default_action='review'."""

def test_custom_category_words():
    """Custom words should be detected with configured thresholds."""

def test_context_extraction():
    """Filler context should include N words before and after."""

def test_sentence_position_detection():
    """Filler at start/mid/end of sentence should be correctly labeled."""

def test_filler_decision_applied_to_edit_plan():
    """Only fillers with action='remove' should appear in edit_plan filler_cuts."""

def test_bulk_rule_overrides_individual():
    """Bulk rule 'keep_all' for 'like' should override individual remove decisions."""
```

---

## 8. Migration Notes

### 8.1 Backward Compatibility

- The `approved_filler_cuts: list[int]` field in `ReviewDecisions` should be kept for backward compat
- If `filler_decisions` is empty but `approved_filler_cuts` is populated, fall back to old behavior
- New fields on `FillerCutRange` and `ContentCutRange` all have defaults, so existing `edit_plan.json` files remain valid

### 8.2 Config Defaults

All new config sections have defaults that match current behavior:
- `crossfade.filler_cut_ms: 30` — minimal, barely noticeable
- `crossfade.content_cut_ms: 150` — subtle but effective
- `transitions.content_cut_dissolve_ms: 300` — gentle dissolve
- `transitions.filler_cut_dissolve_ms: 0` — no video dissolve for fillers (current behavior)
- `filler_words.disfluencies.default_action: "remove"` — current auto-approve-all behavior
- `filler_words.hedge_words.default_action: "review"` — **new**: these now pause for review

The only behavioral change from defaults is that **hedge words now require review** instead of being auto-removed. This is intentional — "like" and "you know" are often rhetorical.

---

*This spec is implementation-ready. All algorithms, filter chains, data structures, and test cases are defined. Phase A of the parent plan implements this spec.*
