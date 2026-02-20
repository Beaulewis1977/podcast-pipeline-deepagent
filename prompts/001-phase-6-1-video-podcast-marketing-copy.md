<objective>
Fix a confirmed end-to-end gap: the marketing copy system does not include `spotify_video` or
`apple_video` as named platforms anywhere in the data pipeline. Only the audio-only `spotify` and
`apple` variants are present. This means operators publishing video episodes to Spotify Video or
Apple Podcasts Video get no video-specific marketing guidance from the pipeline.

The gap exists at FOUR levels — all four must be fixed together or the data will not flow end-to-end:
1. `models/analysis.py` — Pydantic schema missing fields (root cause: unknown keys are silently stripped)
2. `providers/base.py` — AI prompt template missing those platforms (AI never generates the content)
3. `render.py` — marketing doc generator missing those platforms (doc skips them)
4. `ui/app.py` — Streamlit editor missing those platforms (UI never shows them)
</objective>

<context>
Project: podcast-pipeline — AI-powered podcast production pipeline (Python 3.12+, Pydantic, Streamlit UI).
Branch: feat/phase6-audio-video-enhancement (continue work on this branch).

Read CLAUDE.md for project conventions before making any changes.

Data flow for marketing copy (trace this before touching anything):
  1. `providers/base.py:_build_prompt()` → instructs the AI model what JSON structure to return
  2. AI returns JSON with a `marketing` dict keyed by platform name
  3. `models/analysis.py:AnalysisResult.model_validate()` → deserializes the AI response; Pydantic
     silently drops any key not declared as a field in `MarketingCopy` — this is the root cause
  4. `stages/analyze.py` → writes `analysis.json` (the validated model dump)
  5. `render.py:_generate_marketing_doc()` → reads `analysis.json`, iterates a hardcoded platform list
  6. `ui/app.py:render_marketing_editor()` → renders a section per platform for operator review/edit

Key background:
- `spotify_video` and `apple_video` are fully wired platform specs in `config.yaml` and render paths
  (added in Phase 5). The omission is only in the marketing layer.
- Platform key names used everywhere in the codebase are lowercase snake_case.
- The `MarketingCopy` Pydantic model uses `extra = "ignore"` behaviour by default, silently stripping
  unknown keys — so adding fields to `base.py` prompt alone is not enough without also adding them to
  the Pydantic model.

Files to modify:
- @src/podcast_pipeline/models/analysis.py
- @src/podcast_pipeline/providers/base.py
- @src/podcast_pipeline/stages/render.py
- @src/podcast_pipeline/ui/app.py
- @tests/test_render.py

Files to read for context:
- @config.yaml (confirm exact platform key names)
- @src/podcast_pipeline/providers/kimi.py (check if it overrides _build_prompt; if so update it too)
</context>

<requirements>
### 1. `models/analysis.py` — Add fields to `MarketingCopy`

Locate the `MarketingCopy` Pydantic model. Add two new fields with defaults:

```python
spotify_video: PlatformMarketing = Field(default_factory=PlatformMarketing)
apple_video: PlatformMarketing = Field(default_factory=PlatformMarketing)
```

Insert them immediately after the existing `spotify` and `apple` fields respectively, to keep the
model ordered by platform family. This is the root fix — without it, any AI-generated content for
these platforms is silently discarded.

### 2. `providers/base.py` — Update `_build_prompt()` AI template

Locate the `_build_prompt()` method in `BaseProvider`. The method contains a hardcoded JSON schema
string that tells the AI what structure to return. Add `spotify_video` and `apple_video` entries to
the `marketing` section of that schema string, placed after their audio counterparts:

```json
"spotify_video": {
  "titles": ["Episode title for Spotify Video"],
  "description": "Spotify Video podcast description — mention video format and chapters",
  "hashtags": []
},
"apple_video": {
  "titles": ["Episode title for Apple Podcasts Video"],
  "description": "Apple Podcasts Video description — mention video chapters and thumbnail",
  "hashtags": []
}
```

If `kimi.py` overrides `_build_prompt()`, update it in the same way.

### 3. `render.py` — Update `_generate_marketing_doc()`

Locate the `platform_sections` list in `_generate_marketing_doc()`. Add entries for the two new
platforms, inserted after their audio counterparts:

```python
("Spotify Video", "spotify_video"),
...
("Apple Podcasts Video", "apple_video"),
```

Do not change the surrounding logic — only extend the list.

### 4. `ui/app.py` — Update `render_marketing_editor()`

Locate the `platforms` list in `render_marketing_editor()`. Add the two new platforms after their
audio counterparts:

```python
("Spotify Video", "spotify_video", "🎬"),
("Apple Video", "apple_video", "🍎"),
```

Do not change any existing platform entries or surrounding UI logic.

### 5. `tests/test_render.py` — Add regression tests

Using the existing mocking/fixture patterns already present in the file, add:

- A test asserting that `_generate_marketing_doc()` includes a section for `spotify_video` in its
  output when the analysis JSON contains content for that key.
- A test asserting the same for `apple_video`.
- A test asserting that `MarketingCopy` model validation accepts (does not strip) `spotify_video`
  and `apple_video` keys — i.e., they survive a round-trip through `model_validate()` → `model_dump()`.

Do not modify any existing test.
</requirements>

<constraints>
- Do not add any new Python dependencies.
- Do not change any method signatures — all public functions must retain their existing type annotations.
- Do not alter any existing platform entries, rendering logic, or prompt text beyond the additions.
- Keep the `_build_prompt()` JSON schema additions consistent in style with adjacent platform entries.
- Use structlog for any logging (never print()).
- Maintain ordering by platform family: YouTube → Spotify → Spotify Video → TikTok → Instagram →
  LinkedIn → Twitter → Facebook → Apple → Apple Video (or whatever order makes sense given the
  existing list — just keep audio/video variants adjacent).
</constraints>

<implementation_steps>
1. Read `src/podcast_pipeline/models/analysis.py` — understand `MarketingCopy` and `PlatformMarketing`.
2. Read `src/podcast_pipeline/providers/base.py` — find `_build_prompt()` and the JSON schema string.
3. Read `src/podcast_pipeline/providers/kimi.py` — check if it overrides `_build_prompt()`.
4. Read `src/podcast_pipeline/stages/render.py` — find `_generate_marketing_doc()`.
5. Read `src/podcast_pipeline/ui/app.py` — find `render_marketing_editor()` and the `platforms` list.
6. Read `tests/test_render.py` — understand existing test patterns and fixture setup.
7. Make all four code changes in this order: models → base provider → render → ui.
8. Add regression tests to `tests/test_render.py`.
9. Run full verification before declaring done.
</implementation_steps>

<verification>
Run ALL of the following and confirm each passes before declaring complete.
Do NOT claim success without running each command and reading the full output.

```bash
uv run pytest tests/test_render.py -v 2>&1 | tail -30
uv run pytest tests/ 2>&1 | tail -10
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```

Include pass/fail counts in your completion summary.
</verification>

<success_criteria>
- `MarketingCopy` Pydantic model has `spotify_video` and `apple_video` fields with defaults.
- Round-tripping AI JSON with those keys through `AnalysisResult.model_validate()` preserves them.
- `_build_prompt()` instructs the AI to generate `spotify_video` and `apple_video` marketing sections.
- `_generate_marketing_doc()` produces sections for `spotify_video` AND `apple_video`.
- `render_marketing_editor()` renders tabs/sections for "Spotify Video" AND "Apple Video".
- Three new regression tests exist in `tests/test_render.py` and pass.
- All previously passing tests continue to pass (no regressions).
- `ruff check`, `ruff format --check`, and `mypy src/` all exit clean.
- Changes are committed atomically:
  `fix(models,providers,render,ui): add spotify_video and apple_video marketing copy end-to-end`
</success_criteria>
