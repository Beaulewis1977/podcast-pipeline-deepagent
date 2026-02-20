<research_objective>
Research and design a complete solution for upgrading the podcast pipeline's thumbnail selector UI
from text-only candidate cards to a visual frame-preview UI that shows actual extracted video frames,
supports multi-thumbnail selection (1–3), and surfaces at least one "viral-style" thumbnail candidate.

This is a RESEARCH task — do not write implementation code. Produce a structured findings document at
`./research/thumbnail-ui-visual-selection.md` that an implementation planner can use directly to
write a PLAN.md.
</research_objective>

<current-state>
Read these files to understand the existing implementation before researching:

- @src/podcast_pipeline/ui/app.py — focus on `render_thumbnail_selector()` (~line 1296)
- @src/podcast_pipeline/models/analysis.py — focus on `ThumbnailCandidate` and `AnalysisResult`
- @src/podcast_pipeline/models/job.py — look for `ReviewDecisions` and `selected_thumbnail`
- @src/podcast_pipeline/stages/render.py — look for how selected_thumbnail is consumed in outputs
- @src/podcast_pipeline/stages/ingest.py — understand what the ingest stage produces (proxy.mp4 location)
- @src/podcast_pipeline/providers/base.py — focus on `_build_prompt()` thumbnail section

Current state summary (verified from code):
- `ThumbnailCandidate` has: timestamp (str), timestamp_seconds (float), visual_description, suggested_text_overlay, emotion, confidence_score, source_label
- NO virality score on thumbnails — only confidence_score
- The UI reads `thumbnail_frames` from analysis.json and renders text cards
- `ReviewDecisions.selected_thumbnail` is a single `int` (index)
- Frames are NEVER extracted to disk — no image files exist anywhere in the job pipeline
- The proxy video is at `job_dir / "intermediate" / "proxy.mp4"`
</current-state>

<research-questions>
Investigate each of the following areas. Use web search (Perplexity) and library docs (Context7)
as needed. For each question, provide a recommended approach with rationale.

### 1. Frame Extraction — When and Where

The AI returns candidate timestamps. Actual frame images must be extracted from the proxy video
using FFmpeg. Research the tradeoffs of these timing options:

a) **During the Analyze stage** — extract frames immediately after AI returns timestamps; save to
   `job_dir/intermediate/thumbnails/{idx}.jpg`. Pro: frames ready before UI loads. Con: re-analyze
   discards old frames.

b) **On-demand in the UI** — Streamlit calls FFmpeg when the thumbnail tab is opened; cache to
   disk after first extraction. Pro: no pipeline changes. Con: UI freezes while extracting.

c) **As a new Thumbnail Extract sub-stage** — explicit `thumbnail-extract` stage between analyze
   and review. Pro: clean pipeline. Con: adds a stage operators must remember to run.

Recommend one approach. Consider the existing stage architecture and the job_dir layout.
Identify the exact FFmpeg command needed to extract a single frame at a precise timestamp
(to nearest frame, no seeking artifacts).

### 2. Streamlit Image Display

Research how to display extracted frame images in the Streamlit thumbnail selector:

- `st.image()` capabilities: what formats are supported, max size recommendations for a 3-column
  grid layout, whether file paths or PIL Images or bytes are preferred
- How to display images inside `st.columns()` alongside text metadata
- Whether `st.image()` inside `unsafe_allow_html` markdown blocks works or if a hybrid approach
  is needed (image above, HTML card below)
- Caching: does Streamlit cache `st.image()` renders or re-read from disk every rerun?
- Aspect ratio handling: proxy video may be 16:9 widescreen; what thumbnail dimensions work
  best in a 3-col grid without distortion?

Provide a concrete Streamlit layout recommendation with pseudo-code.

### 3. Multi-Select (1–3 thumbnails)

The current model supports only `selected_thumbnail: int` (single index). The user wants to
pick 1, 2, or 3 thumbnails:

- Research how other tools handle multi-thumbnail selection (e.g., YouTube allows A/B testing,
  Spotify shows cover art alternatives)
- Recommend a UX pattern for 1–3 selection:
  - Checkbox-style (operator ticks up to 3)?
  - Primary + alternates model (one "main" + up to 2 "alternatives")?
  - Ranked selection (first selected = primary, second = A/B test, third = backup)?
- Identify the exact schema changes needed in `ReviewDecisions` (and any related models)
- Identify how the render stage should consume multi-selection (separate output files? naming
  convention? e.g., `thumbnail_primary.jpg`, `thumbnail_alt_1.jpg`)

### 4. Viral Thumbnail Criteria and Scoring

The user wants at least one thumbnail candidate flagged as "viral-style." Research:

a) **What makes thumbnails go viral** — look up YouTube/podcast thumbnail best practices (2025/2026):
   - Face close-ups with strong emotion (surprise, excitement)
   - High contrast color palette
   - Clear space for text overlay
   - Action or peak-moment frames
   - Curiosity gap (incomplete scene)
   Research 3–5 concrete, computable signal criteria.

b) **How to score existing candidates** — the AI already returns `confidence_score`. Research
   whether to:
   - Add a `virality_score` field to `ThumbnailCandidate` and have the AI rate each candidate
     (extend `_build_prompt()` schema)
   - Post-process AI descriptions heuristically (keyword matching: "surprise", "laugh", "shock",
     "intense") to compute a virality signal
   - Request one explicitly viral candidate by extending the AI prompt instructions

c) **UI surfacing** — how should viral candidates be surfaced in the grid UI?
   - A "🔥 Viral Pick" badge on the card?
   - Sorted to first position?
   - Separate "Recommended" row above the full grid?

Recommend which approach best fits the existing pipeline without overcomplicating it.

### 5. Impact on Existing Data Models and Pipeline

Map out every file that needs to change to deliver the full feature:

- `models/analysis.py` — ThumbnailCandidate changes (virality field?)
- `models/job.py` — ReviewDecisions changes (multi-select)
- `providers/base.py` — _build_prompt() changes (virality instruction, JSON schema)
- `stages/analyze.py` — any changes for frame extraction timing
- `stages/render.py` — how render stage uses selected thumbnail(s) for output files
- `ui/app.py` — render_thumbnail_selector() UI changes
- `tests/` — which test files cover ThumbnailCandidate, ReviewDecisions, render thumbnail outputs

For each file, note whether the change is additive-only (low risk) or requires modifying
existing behaviour (higher risk, needs regression test).

### 6. Phase Boundary Recommendation

Given the scope, recommend how to phase this work:
- Should visual frame display + multi-select be one phase?
- Should viral scoring be a separate phase?
- What is the minimum viable increment that delivers visible value?
</research-questions>

<deliverable>
Save findings to: `./research/thumbnail-ui-visual-selection.md`

Structure the document as:

```markdown
# Thumbnail UI Visual Selection — Research Findings

## Executive Summary
[3-5 bullet points: what the feature requires, key decisions, recommended approach]

## 1. Frame Extraction — Recommendation + FFmpeg Command
## 2. Streamlit Image Display — Layout Recommendation + Pseudo-code
## 3. Multi-Select UX — Recommended Pattern + Schema Changes
## 4. Viral Thumbnail Scoring — Criteria + Approach Recommendation
## 5. Full File Impact Map
## 6. Phasing Recommendation

## Open Questions
[Anything that needs operator/user input before planning]
```

Be concrete and specific — include exact FFmpeg flags, exact field names, exact Streamlit API
calls where possible. The planner agent will use this document directly.
</deliverable>

<constraints>
- Do not write implementation code or modify any source files.
- Use web search and library docs to validate FFmpeg frame extraction commands and Streamlit APIs.
- Base all analysis on the actual current codebase state (read the files listed above first).
- Flag any assumption you make that the planner should verify.
</constraints>
