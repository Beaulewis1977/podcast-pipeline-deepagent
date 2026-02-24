# Phase 9: Model Update Requirements

**IMPORTANT:** These updates were requested during the Phase 8 review but could not be applied automatically because the active Git branch (`feat/phase8-intelligent-cut-quality`) does not contain the latest Phase 9 `_v4.md` specification file.

When switching to the Phase 9 branch, **the first step** is to apply the following model modifications to `docs/plans/2026-02-21-branding-automation-and-sync-spec_v4.md`.

## The Objective
We are completely dropping references to the older "Gemini 1.5 Pro" and "Imagen 3" models. For all visual and generative image tasks, we must use the newest Gemini Vision generation and analysis models.

## Required Model Replacements

### 1. The Heavy Lifter (`gemini-3-pro-image-preview`)
* **Role:** Compositional auditing, rigorous frame review, and thumbnail prompt engineering.
* **Requirements:**
  * Must be used for the complex reasoning required to look at an extracted video frame (`extract_frame`) and understand the scene/context.
  * Must be used for the "Thumbnail Visionary" Prompt Generation stage to construct the 3 high-impact thumbnail prompts based on the transcript and Brand Voice.

### 2. The Speedy Pipeline (`gemini-2.5-flash-image`)
* **Role:** Layout validation, rapid scanning, and thumbnail image generation.
* **Requirements:**
  * Use this model to generate the actual thumbnail art (replacing the previous Imagen 3 endpoint spec).
  * Use this ultra-fast vision model to review the final "composited" image (the auto-branded thumbnail with the `thumbnail_border` and logo).
  * Must verify that the logo or text is not obstructing the subject's face (bad hand / text artifact verification).

## Specific Spec Updates to Apply
When on the Phase 9 branch, edit the V4 spec to reflect these changes:

1. **Section 1.1 (BrandVoice Injection):** Update the Thumbnail Prompts section to explicitly state `gemini-3-pro-image-preview` drafts the visual prompts.
2. **Section 5 (AI Thumbnail Studio):** Replace the entire "Imagen 3 API" section to state the app calls `gemini-2.5-flash-image` to produce the 4 unique candidate images, then uses Flash to auto-brand and verify the border/logo.
3. **Section 6.2 (The Production Sidebar):** In the "Thumbnail Visionary" UX description, specify the Magic Wand uses `gemini-3-pro-image-preview` and `gemini-2.5-flash-image`.
4. **Section 9.0 (Cost & Technology Research Table):**
   * Remove: `| Imagen 3 API | AI Art | ...`
   * Add: `| Gemini Vision Models | Visual Verification & Art | Pay-as-you-go (gemini-2.5-flash-image, gemini-3-pro-image-preview) | Studio Quality |`
5. **Section 10.0 (Next Steps):** Update Phase 9.8 to say "Build the AI Thumbnail Studio natively integrating `gemini-3-pro-image-preview` for prompt generation/audit and `gemini-2.5-flash-image` for layout validation."
