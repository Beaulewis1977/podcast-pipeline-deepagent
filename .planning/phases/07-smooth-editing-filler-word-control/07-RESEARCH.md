# Phase 7: Smooth Editing & Filler Word Control - Research

**Researched:** 2026-02-21
**Domain:** FFmpeg edit-graph smoothing + faster-whisper boundary alignment + Streamlit editorial control
**Confidence:** HIGH (core stack/patterns), MEDIUM (UI ergonomics and threshold tuning)

## Summary

Phase 7 should be implemented as an **incremental extension of the existing edit-plan pipeline**, not a render-core rewrite. The current code already has the right primitives: `edit_plan.json` as the source of truth, `trim/atrim + concat` wiring in render, and review-state persistence in Streamlit. The correct approach is to add transition-aware segment metadata, boundary snapping before filtergraph generation, and richer filler decisions while preserving backward compatibility.

For smoothing, the standard FFmpeg pattern is: (1) keep `trim/atrim` segment extraction, (2) reset timestamps with `setpts/asetpts`, (3) apply micro fades to all segment edges, and (4) selectively apply `acrossfade`/`xfade` for content cuts only. `xfade` remains two-input and strict about matching video properties, so multi-segment transitions must be chained iteratively and normalized first.

For filler control, keep faster-whisper as the transcription source and use existing word timestamps for cut-boundary snapping. In review UX, use Streamlit keyed widgets + `st.session_state` callbacks for deterministic per-item updates and avoid post-instantiation widget-state mutation patterns that Streamlit forbids.

**Primary recommendation:** Keep FFmpeg + faster-whisper + Streamlit as the standard stack, implement boundary snapping + tiered smoothing + per-filler decisions in additive steps, and gate rollout with filtergraph capability checks and regression tests for short-segment edge cases.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FFmpeg / ffprobe | 8.0.1 latest stable source release (local runtime validated on 6.1.1 with required filters) | Segment trims, fades, crossfades, filtergraph execution | Canonical, production-grade edit graph tool with documented filters and constraints |
| faster-whisper | 1.2.1 | Word-level timestamps and VAD-assisted segmentation | Already used in pipeline; direct `word_timestamps=True` support and stable API |
| Streamlit | 1.54.0 | Human review UI for filler keep/remove decisions | Already integrated; supports `st.data_editor` + callback-driven state updates |
| Pydantic | 2.x | Typed edit-plan/review/config models | Existing schema backbone; safest way to add metadata fields without silent drift |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python stdlib `bisect`/`dataclasses` | Python 3.11+ | Efficient nearest-boundary lookup and typed boundary objects | Boundary snapping implementation |
| Existing Stage 6 enhancement filters (`deesser`, `adeclick`) | Current repo config | Post-cut audio cleanup | Keep enabled after splice operations (do not replace) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FFmpeg filtergraph transitions | MoviePy / custom NumPy DSP transitions | More dependency/latency risk and less deterministic behavior at scale |
| faster-whisper word timestamps | External forced-alignment service | More infra complexity and failure modes for limited gain in this phase |
| Streamlit native widgets | Custom JS component timeline editor | Higher maintenance and slower delivery; unnecessary for current scope |

**Installation:**
```bash
# No mandatory new dependency for this phase if current lockfile satisfies project minimums.
# Optional pin refresh if needed:
pip install "faster-whisper>=1.2.1" "streamlit>=1.54.0"
```

## Architecture Patterns

### Recommended Project Structure
```text
src/podcast_pipeline/
├── stages/render.py           # Extend edit filter builder + transition policy
├── utils/editing.py           # New: word-boundary extraction/snap helpers
├── models/edit_plan.py        # Add optional metadata fields (snapped/original/smoothing)
├── stages/review.py           # Add per-filler decision model + backward compat mapping
└── ui/app.py                  # Category/grouped filler review controls + bulk actions
```

### Pattern 1: Boundary Snap Before Filtergraph Build
**What:** Normalize cut ranges against transcript word gaps before constructing FFmpeg graph.
**When to use:** Every filler/content cut in render path.
**Example:**
```python
# Source: faster-whisper word timestamps API + existing transcript schema
words = flatten_transcript_words(transcript_segments)
boundaries = find_inter_word_boundaries(words)
for cut in cuts:
    cut.start_seconds, cut.end_seconds = snap_cut_range(
        cut.start_seconds,
        cut.end_seconds,
        boundaries,
        max_shift_s=0.25,
    )
```

### Pattern 2: Tiered Smoothing Policy
**What:** Apply micro fades to all joins; use longer crossfades/dissolves only for content cuts.
**When to use:** Mixed filler/content cut plans.
**Example:**
```bash
# Source: FFmpeg filters docs (afade/acrossfade/xfade)
# micro fade (all)
afade=t=in:st=0:d=0.03,afade=t=out:st={end_minus_0_03}:d=0.03
# content-only audio blend
acrossfade=d=0.15:c1=tri:c2=tri
# content-only video blend
xfade=transition=fade:duration=0.30:offset={splice_offset}
```

### Pattern 3: Normalize Video Properties Before xfade
**What:** Force matching resolution/pixel format/fps/timebase upstream of any `xfade` operation.
**When to use:** Any xfade chain with multiple segments.
**Example:**
```bash
[v]fps=30,scale=1280:720,format=yuv420p,settb=AVTB[vnorm]
```

### Pattern 4: Backward-Compatible Review Decision Upgrade
**What:** Add `filler_decisions` while preserving legacy `approved_filler_cuts` behavior.
**When to use:** Loading old `review_state.json` and writing new edit plans.
**Example:**
```python
if decisions.filler_decisions:
    selected = [d.index for d in decisions.filler_decisions if d.action == "remove"]
else:
    selected = decisions.approved_filler_cuts or list(range(len(fillers)))
```

### Anti-Patterns to Avoid
- **Global one-size crossfade durations:** short segments can collapse or disappear.
- **Applying `xfade` without normalization:** FFmpeg fails on mismatched size/timebase.
- **Mutating widget state after widget instantiation in Streamlit:** throws `StreamlitAPIException` patterns.
- **Replacing Stage 6 enhancement chain while adding Phase 7 smoothing:** risks regression in already-verified quality behavior.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Audio transition DSP | Custom sample interpolation/click removal code | FFmpeg `afade` + `acrossfade` + `adeclick` | Mature implementations with known behavior and tunable params |
| Video dissolve compositor | Custom OpenCV blend loop | FFmpeg `xfade` | Native graph integration and fewer sync bugs |
| Word timing aligner | Token-to-waveform aligner from scratch | faster-whisper `word_timestamps=True` output | Already available from current transcription stack |
| Stateful review persistence | Bespoke in-memory diff engine | `st.session_state` + keyed widgets + callbacks | Streamlit-native lifecycle and predictable rerun behavior |

**Key insight:** The risk in this phase is not missing libraries; it is incorrect composition and boundary logic across already-available tools.

## Common Pitfalls

### Pitfall 1: Missing Timestamp Reset After trim/atrim
**What goes wrong:** concat/transition timing drifts or misaligns.
**Why it happens:** `trim`/`atrim` do not reset timestamps automatically.
**How to avoid:** Always apply `setpts=PTS-STARTPTS` and `asetpts=PTS-STARTPTS` on each kept segment.
**Warning signs:** Unexpected offsets and transition start mismatches.

### Pitfall 2: xfade Input Mismatch
**What goes wrong:** FFmpeg filtergraph errors (`Invalid argument`) and empty output.
**Why it happens:** Inputs differ in resolution, frame rate, or timebase.
**How to avoid:** Normalize all xfade inputs (`fps/scale/format/settb`) before chaining.
**Warning signs:** Errors mentioning non-matching main/xfade link parameters.

### Pitfall 3: Overlong acrossfade on Very Short Segments
**What goes wrong:** Segment audio can collapse to near-empty output without a clear hard error.
**Why it happens:** Crossfade duration exceeds practical segment length.
**How to avoid:** Clamp crossfade duration per splice using minimum adjacent segment duration (for example <=25-40%).
**Warning signs:** Tiny/empty audio artifacts on short filler-adjacent segments.

### Pitfall 4: Word-Snap Overcorrection
**What goes wrong:** Semantic timing drifts too far from intended cut window.
**Why it happens:** Snapping window is unbounded or prefers distant gaps.
**How to avoid:** Enforce max shift (e.g., 200-300ms) and fallback to original cut if invalid.
**Warning signs:** Reviewer feedback that cuts feel late/early despite “snapped” boundaries.

### Pitfall 5: Streamlit State Misuse in Editable Tables
**What goes wrong:** Edits appear to “revert” or require multiple interactions.
**Why it happens:** Incorrect session-state update flow around `st.data_editor` reruns.
**How to avoid:** Use explicit `key`, `on_change` callbacks, and immutable update patterns per rerun.
**Warning signs:** Every-second-edit behavior, stale table rows after callback.

## Code Examples

Verified patterns from official sources:

### 1) Word-Level Timestamps
```python
# Source: https://github.com/SYSTRAN/faster-whisper and https://pypi.org/project/faster-whisper/
from faster_whisper import WhisperModel

model = WhisperModel("large-v3", device="cuda", compute_type="float16")
segments, _ = model.transcribe("audio.mp3", word_timestamps=True, vad_filter=True)
for segment in segments:
    for word in segment.words:
        print(word.start, word.end, word.word)
```

### 2) Audio Crossfade Between Segments
```bash
# Source: https://ffmpeg.org/ffmpeg-filters.html#acrossfade
ffmpeg -i first.wav -i second.wav \
  -filter_complex "acrossfade=d=0.15:c1=tri:c2=tri" \
  out.wav
```

### 3) Video Dissolve for Content Cuts
```bash
# Source: https://ffmpeg.org/ffmpeg-filters.html#xfade
ffmpeg -i first.mp4 -i second.mp4 \
  -filter_complex "xfade=transition=fade:duration=0.3:offset=5" \
  out.mp4
```

### 4) Session-State Callback Flow
```python
# Source: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
import streamlit as st

if "decisions" not in st.session_state:
    st.session_state.decisions = {}

def on_editor_change():
    edited = st.session_state["filler_editor"]
    st.session_state.decisions = edited

st.data_editor(data, key="filler_editor", on_change=on_editor_change)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hard cut join only (`trim/concat`) | Micro fades + selective `acrossfade`/`xfade` | Mature FFmpeg transition workflows (current docs) | Cleaner audible transitions without full NLE complexity |
| Segment-level timing only | Word-level cut boundary awareness | Whisper/faster-whisper word timestamp support | Fewer mid-word artifacts and less manual correction |
| Index-only filler approvals | Per-item decision objects + bulk rules | Streamlit callback/state patterns and richer review UX | Better editorial control while retaining deterministic persistence |
| Static older runtime assumptions | Version-aware stack checks (FFmpeg/faster-whisper/Streamlit) | Current releases as of 2026-02-21 | Fewer surprise compatibility failures |

**Deprecated/outdated:**
- Relying on hard-cut-only joins for spoken-word podcasts where splice audibility is a core quality issue.
- Assuming all filler categories should auto-remove; hedge words often need review defaults.

## Open Questions

1. **Speaker-aware filler context in multi-speaker transcripts**
   - What we know: Current transcript model has word timing but no robust speaker labels.
   - What's unclear: Whether speaker attribution is required for phase success.
   - Recommendation: Keep speaker field optional in this phase; do not block delivery.

2. **Exact default thresholds for category rules**
   - What we know: Existing defaults are broad and phase spec proposes disfluency vs hedge split.
   - What's unclear: Corpus-specific false positive rate for hedge words.
   - Recommendation: Start with conservative review defaults for hedge category and tune with fixture set.

3. **Context7 coverage gap in this run**
   - What we know: Context7 requests failed due quota exhaustion in this environment.
   - What's unclear: Whether additional Context7 snippets would materially change recommendations.
   - Recommendation: Re-run Context7 verification when quota is restored; current conclusions are based on official docs/source and local runtime checks.

## Sources

### Primary (HIGH confidence)
- FFmpeg filters manual (`afade`, `acrossfade`, `adeclick`, `atrim`, `trim`, `xfade`, `concat`): https://ffmpeg.org/ffmpeg-filters.html
- FFmpeg download page (current source release link): https://ffmpeg.org/download.html
- faster-whisper repository and README: https://github.com/SYSTRAN/faster-whisper
- faster-whisper transcribe implementation (API defaults/options): https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py
- faster-whisper latest release: https://github.com/SYSTRAN/faster-whisper/releases/tag/v1.2.1
- faster-whisper package metadata: https://pypi.org/project/faster-whisper/
- Streamlit releases (1.54.0): https://github.com/streamlit/streamlit/releases/tag/1.54.0
- Streamlit package metadata: https://pypi.org/project/streamlit/
- Streamlit Session State reference: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
- Streamlit `st.audio` API implementation/docstring (1.54.0 tag): https://raw.githubusercontent.com/streamlit/streamlit/1.54.0/lib/streamlit/elements/media.py
- Streamlit `st.data_editor` API implementation/docstring (1.54.0 tag): https://raw.githubusercontent.com/streamlit/streamlit/1.54.0/lib/streamlit/elements/widgets/data_editor.py

### Secondary (MEDIUM confidence)
- Streamlit issue patterns for `st.data_editor` + session state workflows: https://github.com/streamlit/streamlit/issues/7749

### Tertiary (LOW confidence)
- Perplexity ecosystem discovery output (used for source discovery only; critical claims re-verified against primary docs): internal run logs in this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - version/release claims validated from official release/package sources.
- Architecture: HIGH - FFmpeg constraints and current repo architecture align cleanly.
- Pitfalls: MEDIUM - several are validated via local runtime experiments and known integration behavior, but threshold tuning remains project-specific.

**Research date:** 2026-02-21
**Valid until:** 2026-03-23 (re-verify monthly for fast-moving app/library releases)
