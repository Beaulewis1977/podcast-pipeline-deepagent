# Research Summary: Podcast Production Pipeline

**Domain:** Local-first AI podcast production pipeline
**Researched:** 2026-02-04
**Overall confidence:** MEDIUM (internal sources only; no external verification)

## Executive Summary

The current repository already provides a working staged pipeline (ingest → transcribe → analyze → review → render) and a Streamlit UI. The key research finding is that the product’s fastest path to a usable v1 is not new tooling, but wiring the existing stages end-to-end and removing stubs. This aligns with the app research report’s recommendation to ship a Streamlit-first version and defer desktop distribution to a later phase.

The recommended stack remains Python + FFmpeg + faster-whisper + Streamlit, with Gemini as the primary analysis provider and Kimi as fallback. The main risks are in workflow wiring (multi-track not default, render not applying edits) rather than missing components. Once those are resolved, research integration and viral scoring can deliver differentiation.

## Key Findings

**Stack:** Python 3.11+, FFmpeg, faster-whisper, Streamlit, Typer, Pydantic, Gemini + Kimi (`pyproject.toml`, `src/podcast_pipeline/*`).
**Architecture:** File-backed staged pipeline with persistent job state (`src/podcast_pipeline/pipeline.py`, `src/podcast_pipeline/models/job.py`).
**Critical pitfall:** Render ignores review edits because cut logic is stubbed (`src/podcast_pipeline/stages/render.py`).

## Implications for Roadmap

Suggested phase structure:

1. **Wiring + Stability** — Apply edits in render, make multi-track default, fix UI job consistency.
   - Addresses: core table-stakes workflow and reliable outputs
   - Avoids: “outputs don’t match review” pitfall

2. **Research + Viral Integration** — Wire research outputs into analysis and re-rank clips.
   - Addresses: differentiation via research-informed suggestions
   - Avoids: stale or ungrounded marketing outputs

3. **Desktop Distribution** — Package the pipeline with Tauri v2 and a Python backend service.
   - Addresses: usability, distribution, and performance for non-technical users
   - Avoids: Streamlit deployment constraints

**Phase ordering rationale:** The repository already contains most components; the highest ROI is connecting them and ensuring outputs reflect human review before investing in research enhancements or desktop UX.

**Research flags for phases:**
- Phase 1: standard patterns (no extra research required)
- Phase 2: needs targeted research on YouTube trend metrics and viral scoring
- Phase 3: needs packaging and desktop UX research

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Directly reflected in repo and config files |
| Features | MEDIUM | Based on internal research report, not external validation |
| Architecture | HIGH | Directly reflected in codebase |
| Pitfalls | MEDIUM | Derived from code review + internal report |

## Gaps to Address

- No external verification of competitor landscape or current API limits
- Platform spec changes not validated against official docs
- Desktop packaging requirements not yet researched in depth

