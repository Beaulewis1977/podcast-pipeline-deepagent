"""Review stage: Human review interface."""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from podcast_pipeline.config import Config
from podcast_pipeline.export_targets import DEFAULT_EXPORT_PLATFORMS, normalize_export_platforms
from podcast_pipeline.models.edit_plan import (
    ClipRange,
    ContentCutRange,
    EditPlan,
    FillerCutRange,
)
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)


class FillerDecision(BaseModel):
    """Explicit keep/remove decision for one detected filler item."""

    index: int = Field(ge=0)
    action: Literal["remove", "keep"] = "remove"
    reason: str = ""
    category: str = ""


class ReviewDecisions(BaseModel):
    """Human review decisions."""

    # Filler cuts - list of indices to approve (empty = approve all)
    approved_filler_cuts: list[int] = Field(default_factory=list)
    filler_decisions: list[FillerDecision] = Field(default_factory=list)
    reject_all_fillers: bool = False

    # Content cuts - list of indices to approve
    approved_content_cuts: list[int] = Field(default_factory=list)

    # Viral clips - list of indices to export
    selected_clips: list[int] = Field(default_factory=list)

    # Thumbnails - ranked list of selected indices (primary + up to 2 alternates)
    selected_thumbnails: list[int] = Field(default_factory=list, max_length=3)

    # Legacy mirror of selected_thumbnails primary selection
    selected_thumbnail: int | None = Field(default=None, ge=0)

    # Marketing copy - edited versions (platform: content)
    marketing_edits: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Export settings
    export_platforms: list[str] = Field(default_factory=lambda: list(DEFAULT_EXPORT_PLATFORMS))
    export_quality: str = "final"  # draft or final

    # Review completion
    review_complete: bool = False
    review_notes: str = ""

    @field_validator("export_platforms", mode="before")
    @classmethod
    def validate_export_platforms(cls, value: Any) -> list[str]:
        """Normalize review export platform keys to canonical values.

        All platform keys (valid and invalid) are canonicalized (trimmed, lowercased,
        deduplicated). Unknown/invalid keys are still preserved in the returned list so
        the render stage can report them as unsupported rather than silently dropping them.
        """
        if value is None:
            return list(DEFAULT_EXPORT_PLATFORMS)
        if isinstance(value, str):
            raw_platforms: list[Any] = [part.strip() for part in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            raw_platforms = list(value)
        else:
            raw_platforms = []
        valid, invalid = normalize_export_platforms(
            raw_platforms, include_invalid=True, fallback_to_default=False
        )
        all_platforms = valid + invalid
        return all_platforms if all_platforms else list(DEFAULT_EXPORT_PLATFORMS)

    @field_validator("selected_thumbnails")
    @classmethod
    def validate_selected_thumbnails(cls, value: list[int]) -> list[int]:
        """Enforce ranked thumbnail index invariants."""
        if len(set(value)) != len(value):
            raise ValueError("selected_thumbnails must contain unique indices")
        if any(index < 0 for index in value):
            raise ValueError("selected_thumbnails indices must be >= 0")
        return value

    @field_validator("filler_decisions")
    @classmethod
    def validate_filler_decisions(cls, value: list[FillerDecision]) -> list[FillerDecision]:
        """Require deterministic uniqueness by filler index."""
        seen_indices: set[int] = set()
        for decision in value:
            if decision.index in seen_indices:
                raise ValueError("filler_decisions must not contain duplicate indices")
            seen_indices.add(decision.index)
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_thumbnail_selection(cls, value: Any) -> Any:
        """Normalize legacy and modern thumbnail selection payloads."""
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        raw_primary = payload.get("selected_thumbnail")
        raw_ranked = payload.get("selected_thumbnails")

        ranked_list: list[Any] | None
        if isinstance(raw_ranked, (list, tuple)):
            ranked_list = list(raw_ranked)
        else:
            ranked_list = None

        # If scalar selection is present, treat it as canonical primary and merge
        # any ranked alternates behind it for backward-compatible write paths.
        if raw_primary is not None:
            if ranked_list is None:
                payload["selected_thumbnails"] = [raw_primary]
            else:
                payload["selected_thumbnails"] = [
                    raw_primary,
                    *[index for index in ranked_list if index != raw_primary],
                ]
            payload["selected_thumbnail"] = raw_primary
            return payload

        if ranked_list:
            payload["selected_thumbnails"] = ranked_list
            payload["selected_thumbnail"] = ranked_list[0]
            return payload

        payload["selected_thumbnails"] = []
        payload["selected_thumbnail"] = None
        return payload


class ReviewStage(Stage):
    """Human review stage."""

    name = "review"

    def __init__(self, config: Config):
        super().__init__(config)

    def run(self, job: Job, job_dir: Path) -> StageResult:
        """Check review status - this stage waits for human input."""
        review_path = job_dir / "review" / "review_state.json"

        # If review state doesn't exist, create initial state
        if not review_path.exists():
            self._create_initial_review_state(job_dir)
            job.update_stage(self.name, StageStatus.WAITING)
            job.save(self.config.paths.jobs_dir)

            return StageResult(
                success=True,
                outputs=[str(review_path.relative_to(job_dir))],
                data={"status": "waiting_for_review"},
            )

        # Check if review is complete
        review_data = json.loads(review_path.read_text())
        decisions = ReviewDecisions.model_validate(review_data)

        if decisions.review_complete:
            analysis_path = job_dir / "analysis" / "analysis.json"
            filler_path = job_dir / "analysis" / "filler_cuts.json"

            analysis = json.loads(analysis_path.read_text()) if analysis_path.exists() else {}
            fillers = json.loads(filler_path.read_text()) if filler_path.exists() else []

            edit_plan_path = write_edit_plan(job_dir, decisions, analysis, fillers)

            return StageResult(
                success=True,
                outputs=[
                    str(review_path.relative_to(job_dir)),
                    str(edit_plan_path.relative_to(job_dir)),
                ],
                data={"status": "review_complete", "decisions": decisions.model_dump()},
            )

        # Still waiting
        job.update_stage(self.name, StageStatus.WAITING)
        job.save(self.config.paths.jobs_dir)

        return StageResult(
            success=True,
            outputs=[str(review_path.relative_to(job_dir))],
            data={"status": "waiting_for_review"},
        )

    def _create_initial_review_state(self, job_dir: Path) -> None:
        """Create initial review state file."""
        review_dir = job_dir / "review"
        review_dir.mkdir(parents=True, exist_ok=True)

        # Load analysis to get default selections
        analysis_path = job_dir / "analysis" / "analysis.json"
        filler_path = job_dir / "analysis" / "filler_cuts.json"

        decisions = ReviewDecisions()

        # Default: approve all filler cuts
        if filler_path.exists():
            fillers = json.loads(filler_path.read_text())
            decisions.approved_filler_cuts = list(range(len(fillers)))
            decisions.filler_decisions = [
                FillerDecision(index=i, action="remove") for i in range(len(fillers))
            ]

        # Default: no content cuts approved (require explicit approval)
        # Default: no clips selected (require explicit selection)

        # Default: first thumbnail selected
        if analysis_path.exists():
            analysis = json.loads(analysis_path.read_text())
            if analysis.get("thumbnail_frames"):
                decisions.selected_thumbnails = [0]
                decisions.selected_thumbnail = 0

        review_path = review_dir / "review_state.json"
        review_path.write_text(decisions.model_dump_json(indent=2))

        self.logger.info("review_state_created", path=str(review_path))


def approve_review(job_dir: Path, platforms: list[str] | None = None) -> ReviewDecisions:
    """Quick approval of all suggestions.

    Args:
        job_dir: Job directory path
        platforms: Platforms to export (default: youtube, spotify)

    Returns:
        Updated ReviewDecisions
    """
    review_path = job_dir / "review" / "review_state.json"
    analysis_path = job_dir / "analysis" / "analysis.json"
    filler_path = job_dir / "analysis" / "filler_cuts.json"

    # Load existing or create new
    if review_path.exists():
        decisions = ReviewDecisions.model_validate_json(review_path.read_text())
    else:
        decisions = ReviewDecisions()

    # Approve all fillers
    if filler_path.exists():
        fillers = json.loads(filler_path.read_text())
        decisions.approved_filler_cuts = list(range(len(fillers)))
        decisions.filler_decisions = [
            FillerDecision(index=i, action="remove") for i in range(len(fillers))
        ]

    # Approve all content cuts
    if analysis_path.exists():
        analysis = json.loads(analysis_path.read_text())
        cuts = analysis.get("content_cuts", [])
        decisions.approved_content_cuts = list(range(len(cuts)))

        # Select all clips
        clips = analysis.get("viral_clips", [])
        decisions.selected_clips = list(range(len(clips)))

        # Select first thumbnail
        if analysis.get("thumbnail_frames"):
            decisions.selected_thumbnails = [0]
            decisions.selected_thumbnail = 0

    # Set platforms
    decisions.export_platforms = normalize_export_platforms(platforms)
    decisions.review_complete = True

    # Save
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(decisions.model_dump_json(indent=2))

    analysis = json.loads(analysis_path.read_text()) if analysis_path.exists() else {}
    fillers = json.loads(filler_path.read_text()) if filler_path.exists() else []
    write_edit_plan(job_dir, decisions, analysis, fillers)

    return decisions


def write_edit_plan(
    job_dir: Path,
    decisions: ReviewDecisions,
    analysis: dict[str, Any] | None,
    filler_cuts: list[dict[str, Any]] | None,
) -> Path:
    """Write edit_plan.json based on review decisions."""
    analysis = analysis or {}
    filler_cuts = filler_cuts or []

    review_dir = job_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    # Determine approved filler cuts
    # Support both start_seconds/end_seconds and start/end key variants
    approved_filler: list[FillerCutRange] = []
    if not decisions.reject_all_fillers:
        filler_indices = _resolve_filler_cut_indices(decisions, len(filler_cuts))
        for idx in filler_indices:
            if idx < len(filler_cuts):
                filler = filler_cuts[idx]
                approved_filler.append(
                    FillerCutRange(
                        start_seconds=float(filler.get("start_seconds", filler.get("start", 0.0))),
                        end_seconds=float(filler.get("end_seconds", filler.get("end", 0.0))),
                        word=str(filler.get("word", "")),
                        confidence=filler.get("confidence"),
                    )
                )

    # Determine approved content cuts
    # Support both start_seconds/end_seconds and start/end key variants
    approved_content: list[ContentCutRange] = []
    content_cuts = analysis.get("content_cuts", [])
    for idx in decisions.approved_content_cuts:
        if idx < len(content_cuts):
            cut = content_cuts[idx]
            approved_content.append(
                ContentCutRange(
                    start_seconds=float(cut.get("start_seconds", cut.get("start", 0.0))),
                    end_seconds=float(cut.get("end_seconds", cut.get("end", 0.0))),
                    reason=str(cut.get("reason", "")),
                )
            )

    # Determine approved clip ranges
    # Support both start_seconds/end_seconds and start/end key variants
    approved_clips: list[ClipRange] = []
    viral_clips = analysis.get("viral_clips", [])
    for idx in decisions.selected_clips:
        if idx < len(viral_clips):
            clip = viral_clips[idx]
            approved_clips.append(
                ClipRange(
                    start_seconds=float(clip.get("start_seconds", clip.get("start", 0.0))),
                    end_seconds=float(clip.get("end_seconds", clip.get("end", 0.0))),
                    description=str(clip.get("description", "")),
                    score=clip.get("virality_score"),
                )
            )

    edit_plan = EditPlan(
        filler_cuts=approved_filler,
        content_cuts=approved_content,
        clip_ranges=approved_clips,
    )

    edit_path = review_dir / "edit_plan.json"
    edit_path.write_text(edit_plan.model_dump_json(indent=2))

    logger.info(
        "edit_plan_written",
        path=str(edit_path),
        filler_cuts=len(approved_filler),
        content_cuts=len(approved_content),
        clips=len(approved_clips),
    )

    return edit_path


def _resolve_filler_cut_indices(decisions: ReviewDecisions, filler_count: int) -> list[int]:
    """Resolve filler cuts using explicit decisions first, then legacy fallbacks."""
    if filler_count <= 0:
        return []

    if decisions.filler_decisions:
        explicit_remove = [
            item.index for item in decisions.filler_decisions if item.action == "remove"
        ]
        deduped: list[int] = []
        seen: set[int] = set()
        for idx in explicit_remove:
            if idx < 0 or idx >= filler_count:
                continue
            if idx in seen:
                continue
            seen.add(idx)
            deduped.append(idx)
        return sorted(deduped)

    fallback = decisions.approved_filler_cuts or list(range(filler_count))
    deduped_fallback: list[int] = []
    seen_fallback: set[int] = set()
    for idx in fallback:
        if idx < 0 or idx >= filler_count:
            continue
        if idx in seen_fallback:
            continue
        seen_fallback.add(idx)
        deduped_fallback.append(idx)
    return sorted(deduped_fallback)


def get_review_summary(job_dir: Path) -> dict[str, Any]:
    """Get a summary of content for review.

    Returns dict with transcript, filler cuts, content cuts, clips, marketing copy.
    """
    summary: dict[str, Any] = {}

    # Transcript
    transcript_path = job_dir / "analysis" / "transcript.json"
    if transcript_path.exists():
        data = json.loads(transcript_path.read_text())
        summary["transcript"] = {
            "text": data.get("text", "")[:2000] + "..."
            if len(data.get("text", "")) > 2000
            else data.get("text", ""),
            "duration": data.get("duration", 0),
            "language": data.get("language", "unknown"),
        }

    # Filler cuts
    filler_path = job_dir / "analysis" / "filler_cuts.json"
    if filler_path.exists():
        fillers = json.loads(filler_path.read_text())
        summary["filler_cuts"] = [
            {
                "index": i,
                "word": f["word"],
                "start": f"{f['start']:.1f}s",
                "end": f"{f['end']:.1f}s",
            }
            for i, f in enumerate(fillers)
        ]

    # Analysis
    analysis_path = job_dir / "analysis" / "analysis.json"
    if analysis_path.exists():
        analysis = json.loads(analysis_path.read_text())

        summary["content_cuts"] = [
            {
                "index": i,
                "start": c.get("start", ""),
                "end": c.get("end", ""),
                "reason": c.get("reason", ""),
            }
            for i, c in enumerate(analysis.get("content_cuts", []))
        ]

        summary["viral_clips"] = [
            {
                "index": i,
                "start": c.get("start", ""),
                "end": c.get("end", ""),
                "description": c.get("description", ""),
                "score": c.get("virality_score", 0),
                "hook": c.get("suggested_hook", ""),
            }
            for i, c in enumerate(analysis.get("viral_clips", []))
        ]

        summary["thumbnails"] = [
            {
                "index": i,
                "timestamp": t.get("timestamp", ""),
                "description": t.get("visual_description", ""),
                "text": t.get("suggested_text_overlay", ""),
            }
            for i, t in enumerate(analysis.get("thumbnail_frames", []))
        ]

        summary["marketing"] = analysis.get("marketing", {})
        summary["metadata"] = analysis.get("metadata", {})

    # Current review decisions
    review_path = job_dir / "review" / "review_state.json"
    if review_path.exists():
        summary["decisions"] = ReviewDecisions.model_validate_json(
            review_path.read_text()
        ).model_dump()

    return summary
