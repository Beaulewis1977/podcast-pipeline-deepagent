"""Streamlit UI for Podcast Pipeline - Complete Web Interface.

Job lifecycle operations (create, run, list, status) are routed through
the backend service via ``ServiceClient``.  Display-only operations that
read local analysis/review files continue to access the filesystem
directly, since both the service and Streamlit share the same ``jobs/``
directory on the local machine.
"""

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

from podcast_pipeline.clients.service_client import (
    ServiceClient,
    ServiceConflictError,
    ServiceError,
    ServiceUnavailableError,
)
from podcast_pipeline.config import Config, load_config
from podcast_pipeline.export_targets import (
    DEFAULT_EXPORT_PLATFORMS,
    EXPORT_TARGETS,
    normalize_export_platforms,
)
from podcast_pipeline.stages.review import (
    ReviewDecisions,
    approve_review,
    write_edit_plan,
)
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)
_MARKETING_METADATA_KEY = "__metadata__"
_NAV_LABELS_BY_PAGE = {
    "dashboard": "📊 Dashboard",
    "editor": "🎬 Editor",
    "settings": "⚙️ Settings",
}
_NAV_PAGES_BY_LABEL = {label: page for page, label in _NAV_LABELS_BY_PAGE.items()}


@dataclass(frozen=True, slots=True)
class MarketingEditorPlatformSpec:
    """Field-shape and character-bound guidance for one marketing platform."""

    label: str
    key: str
    icon: str
    title_mode: str
    max_description_chars: int
    description_height: int
    description_guidance: str


_MARKETING_EDITOR_PLATFORM_SPECS: tuple[MarketingEditorPlatformSpec, ...] = (
    MarketingEditorPlatformSpec(
        label="YouTube",
        key="youtube",
        icon="🎥",
        title_mode="multi",
        max_description_chars=5000,
        description_height=150,
        description_guidance="Long-form SEO description with chapters and key takeaways.",
    ),
    MarketingEditorPlatformSpec(
        label="Spotify",
        key="spotify",
        icon="🎧",
        title_mode="single",
        max_description_chars=4000,
        description_height=120,
        description_guidance="Listener-first audio show notes with a concise value promise.",
    ),
    MarketingEditorPlatformSpec(
        label="Spotify Video",
        key="spotify_video",
        icon="🎬",
        title_mode="single",
        max_description_chars=4000,
        description_height=120,
        description_guidance="Video-podcast positioning focused on watch intent and chapter moments.",
    ),
    MarketingEditorPlatformSpec(
        label="Apple Podcasts",
        key="apple",
        icon="🍎",
        title_mode="single",
        max_description_chars=4000,
        description_height=120,
        description_guidance="Editorial-style audio description tuned for Apple podcast browsing.",
    ),
    MarketingEditorPlatformSpec(
        label="Apple Video",
        key="apple_video",
        icon="📺",
        title_mode="single",
        max_description_chars=4000,
        description_height=120,
        description_guidance="Video-forward Apple copy emphasizing visual moments and episode flow.",
    ),
    MarketingEditorPlatformSpec(
        label="TikTok",
        key="tiktok",
        icon="📱",
        title_mode="none",
        max_description_chars=150,
        description_height=80,
        description_guidance="Ultra-short hook caption optimized for first-swipe attention.",
    ),
    MarketingEditorPlatformSpec(
        label="Instagram",
        key="instagram",
        icon="📷",
        title_mode="none",
        max_description_chars=2200,
        description_height=80,
        description_guidance="Reel-style caption with a quick hook and clear audience context.",
    ),
    MarketingEditorPlatformSpec(
        label="LinkedIn",
        key="linkedin",
        icon="💼",
        title_mode="none",
        max_description_chars=3000,
        description_height=150,
        description_guidance="Professional narrative focused on insight, outcomes, and practical value.",
    ),
    MarketingEditorPlatformSpec(
        label="Twitter/X",
        key="twitter",
        icon="🐦",
        title_mode="none",
        max_description_chars=280,
        description_height=80,
        description_guidance="Single high-signal post that fits in one short-form tweet.",
    ),
    MarketingEditorPlatformSpec(
        label="Facebook",
        key="facebook",
        icon="📘",
        title_mode="none",
        max_description_chars=63206,
        description_height=120,
        description_guidance="Conversational post copy with enough context for feed-driven discovery.",
    ),
)


def _marketing_editor_platform_specs() -> tuple[MarketingEditorPlatformSpec, ...]:
    """Return canonical marketing editor platform specs in deterministic order."""
    return _MARKETING_EDITOR_PLATFORM_SPECS


# Page config must be first Streamlit command
st.set_page_config(
    page_title="Podcast Pipeline",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# Service / Config helpers
# ============================================================================


def get_config() -> Config:
    """Get cached config."""
    if "config" not in st.session_state:
        st.session_state.config = load_config()
    config: Config = st.session_state.config
    return config


def get_service_client() -> ServiceClient:
    """Get a cached ``ServiceClient`` configured from project settings."""
    cached_client = st.session_state.get("service_client")
    if cached_client is not None and not hasattr(cached_client, "delete_job"):
        with contextlib.suppress(Exception):
            cached_client.close()
        st.session_state.pop("service_client", None)

    if "service_client" not in st.session_state:
        config = get_config()
        st.session_state.service_client = ServiceClient(
            base_url=config.service.base_url,
            timeout=config.service.timeout,
            retries=config.service.retries,
        )
    client: ServiceClient = st.session_state.service_client
    return client


def check_service_status() -> bool:
    """Return True if the backend service is reachable, False otherwise."""
    return get_service_client().is_available()


def _job_dir_for(job_id: str) -> Path:
    """Resolve the local filesystem job directory for a given job_id."""
    config = get_config()
    return config.paths.jobs_dir / job_id


def _persist_uploaded_video(uploaded_file: Any, jobs_dir: Path) -> Path:
    """Persist a Streamlit upload for service-side job creation."""
    uploads_dir = jobs_dir / "_uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    source_name = Path(str(getattr(uploaded_file, "name", "upload.mp4")))
    stem = source_name.stem or "upload"
    ext = source_name.suffix or ".mp4"
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    upload_path = uploads_dir / f"{stem}_{timestamp}{ext}"
    suffix = 1
    while upload_path.exists():
        upload_path = uploads_dir / f"{stem}_{timestamp}_{suffix}{ext}"
        suffix += 1

    payload = (
        uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    )
    upload_path.write_bytes(payload)
    return upload_path


def _read_metadata_json(path: Path) -> dict[str, Any] | None:
    """Read metadata JSON and return a dict payload."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("ingest_metadata_load_failed", path=str(path), error=str(exc))
        return None
    if not isinstance(raw, dict):
        logger.warning("ingest_metadata_invalid_payload", path=str(path), type=type(raw).__name__)
        return None
    return raw


def _load_ingest_metadata(job_dir: Path) -> dict[str, Any] | None:
    """Load ingest metadata from canonical path with logged legacy fallback."""
    canonical_path = job_dir / "intermediate" / "metadata.json"
    legacy_path = job_dir / "input" / "metadata.json"

    canonical_metadata = _read_metadata_json(canonical_path) if canonical_path.exists() else None
    if canonical_metadata is not None:
        return canonical_metadata

    if legacy_path.exists():
        logger.warning(
            "ingest_metadata_legacy_fallback",
            path=str(legacy_path),
            canonical_exists=canonical_path.exists(),
        )
        return _read_metadata_json(legacy_path)
    return None


def _load_review_decisions(job_dir: Path) -> ReviewDecisions:
    """Load review decisions with safe fallback to defaults."""
    review_path = job_dir / "review" / "review_state.json"
    if not review_path.exists():
        return ReviewDecisions()
    try:
        return ReviewDecisions.model_validate_json(review_path.read_text())
    except Exception as exc:
        logger.warning("review_state_load_failed", path=str(review_path), error=str(exc))
        return ReviewDecisions()


def _apply_marketing_review_edits(
    analysis: dict[str, Any], decisions: ReviewDecisions
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Overlay review-state marketing edits on top of analysis defaults."""
    base_marketing_raw = analysis.get("marketing", {})
    base_metadata_raw = analysis.get("metadata", {})

    base_marketing = (
        {key: value for key, value in base_marketing_raw.items() if isinstance(value, dict)}
        if isinstance(base_marketing_raw, dict)
        else {}
    )
    base_metadata = base_metadata_raw.copy() if isinstance(base_metadata_raw, dict) else {}

    merged_marketing: dict[str, dict[str, Any]] = {
        key: value.copy() for key, value in base_marketing.items()
    }
    merged_metadata = base_metadata.copy()

    for key, value in decisions.marketing_edits.items():
        if not isinstance(value, dict):
            continue
        if key == _MARKETING_METADATA_KEY:
            merged_metadata.update(value)
            continue
        existing = merged_marketing.get(key, {})
        merged_marketing[key] = {**existing, **value}

    return merged_marketing, merged_metadata


def _topics_to_text(topics: Any) -> str:
    """Convert metadata topics payload to text input form."""
    if isinstance(topics, list):
        return ", ".join(str(topic) for topic in topics if topic)
    if isinstance(topics, str):
        return topics
    return ""


def _save_marketing_edits_to_review_flow(
    job_dir: Path,
    decisions: ReviewDecisions,
    edited_marketing: dict[str, Any],
    summary: str,
    topics: str,
    mood: str,
) -> None:
    """Persist marketing edits in review state and regenerate edit plan."""
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in edited_marketing.items():
        if isinstance(value, dict):
            normalized[key] = value

    normalized[_MARKETING_METADATA_KEY] = {
        "summary": summary.strip(),
        "topics": [topic.strip() for topic in topics.split(",") if topic.strip()],
        "mood": mood.strip(),
    }
    decisions.marketing_edits = normalized
    save_review_decisions(job_dir, decisions)


def _export_platform_options() -> list[tuple[str, str, str]]:
    """Build export option tuples from canonical platform registry."""
    category_icon = {"audio": "🎧", "video": "🎥", "package": "📦"}
    options: list[tuple[str, str, str]] = []
    for target in EXPORT_TARGETS:
        help_text = f"{category_icon.get(target.category, '📁')} {target.description}"
        if target.artifact_only:
            help_text = f"{help_text}; artifact packaging only"
        options.append((target.label, target.key, help_text))
    return options


def _export_boundary_guidance() -> str:
    """Return operator-facing guidance for provider-mediated publishing limits."""
    return (
        "`apple_hls` packages HLS artifacts only; Apple/Spotify publishing remains "
        "provider/dashboard-mediated (no direct upload automation)."
    )


def _load_normalized_export_platforms(review_path: Path) -> tuple[list[str], list[str]]:
    """Load normalized export platforms and any dropped invalid keys from review state."""
    if not review_path.exists():
        return list(DEFAULT_EXPORT_PLATFORMS), []

    try:
        payload = json.loads(review_path.read_text())
    except (OSError, json.JSONDecodeError):
        return list(DEFAULT_EXPORT_PLATFORMS), []

    raw_platforms: Any
    if isinstance(payload, dict):
        raw_platforms = payload.get("export_platforms")
    else:
        raw_platforms = None

    normalized, invalid = normalize_export_platforms(raw_platforms, include_invalid=True)
    return normalized, invalid


def _prepare_marketing_regeneration_review_state(job_dir: Path) -> None:
    """Reset review-gated marketing edits before re-running analyze."""
    decisions = _load_review_decisions(job_dir)
    decisions.review_complete = False
    decisions.marketing_edits = {}
    save_review_decisions(job_dir, decisions)


def format_timestamp(ts: datetime | None) -> str:
    """Format timestamp for display."""
    if ts is None:
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M")


def _normalize_page(page: str | None) -> str:
    """Return a valid page name for UI navigation."""
    return page if page in _NAV_LABELS_BY_PAGE else "dashboard"


def _set_current_page(page: str) -> None:
    """Set page state and mark navigation for sidebar sync on next rerun."""
    normalized_page = _normalize_page(page)
    st.session_state["page"] = normalized_page
    st.session_state["_sync_nav_to_page"] = True


def _sync_nav_with_page() -> str:
    """Normalize page and optionally mirror it into the sidebar radio key."""
    current_page = _normalize_page(st.session_state.get("page"))
    st.session_state["page"] = current_page

    should_sync = bool(st.session_state.pop("_sync_nav_to_page", False))
    if st.session_state.get("nav_radio") not in _NAV_PAGES_BY_LABEL:
        should_sync = True

    if should_sync:
        st.session_state["nav_radio"] = _NAV_LABELS_BY_PAGE[current_page]
    return current_page


def status_badge(status: str) -> str:
    """Generate colored status badge."""
    colors = {
        "complete": "🟢",
        "running": "🔵",
        "waiting": "🟡",
        "failed": "🔴",
        "pending": "⚪",
        "invalid": "🟠",
    }
    return f"{colors.get(status, '⚫')} {status.capitalize()}"


def load_jobs_list() -> list[dict[str, Any]]:
    """Load list of all jobs via the backend service."""
    client = get_service_client()
    try:
        result = client.list_jobs()
        return [j.model_dump() for j in result.jobs]
    except ServiceUnavailableError:
        st.error("Backend service is not running. Start it with: `podcast-pipeline service`")
        return []
    except ServiceError as exc:
        st.error(f"Failed to fetch jobs: {exc}")
        return []


def _is_invalid_job_conflict(exc: ServiceError) -> bool:
    """Return True when backend rejects a job due to invalid persisted state."""
    return isinstance(exc, ServiceConflictError) and "job state is invalid" in str(exc).lower()


def _safe_current_job_status(job_id: str) -> str | None:
    """Return current job status; None when the job cannot be queried."""
    client = get_service_client()
    try:
        detail = client.get_job(job_id)
        return detail.status
    except ServiceConflictError as exc:
        if _is_invalid_job_conflict(exc):
            return "invalid"
    except ServiceError:
        return None
    return None


def _raise_service_error(status_code: int, detail: Any) -> None:
    """Raise a normalized service-layer error for UI actions."""
    raise ServiceError(f"Service error {status_code}: {detail}")


def _build_research_panel_data(research_payload: dict[str, Any]) -> dict[str, Any]:
    """Transform research artifact data into UI-friendly display values."""
    insights = research_payload.get("insights", {}) or {}
    engagement = insights.get("engagement_benchmarks", {}) or {}

    raw_posting_windows = insights.get("best_posting_windows", [])
    posting_windows: list[str] = []
    for item in raw_posting_windows:
        if not isinstance(item, dict):
            continue
        window = item.get("window")
        videos_published = item.get("videos_published")
        if window and videos_published is not None:
            posting_windows.append(f"{window} ({videos_published} videos)")
        elif window:
            posting_windows.append(str(window))

    competition_score = insights.get("competition_score")
    if isinstance(competition_score, (int, float)):
        competition_score = float(competition_score)
    else:
        competition_score = None

    return {
        "query": research_payload.get("query", "N/A"),
        "competition_score": competition_score,
        "competition_tier": insights.get("competition_tier"),
        "avg_engagement_rate": engagement.get("avg_engagement_rate"),
        "avg_velocity_per_hour": engagement.get("avg_velocity_per_hour"),
        "keywords": [
            str(keyword) for keyword in research_payload.get("suggested_keywords", [])[:10]
        ],
        "posting_windows": posting_windows,
    }


def _build_clip_score_rows(viral_payload: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    """Build sorted clip score rows with legacy-field fallbacks."""

    def _to_score(value: Any, default: float = 0.0) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return default
        return min(max(score, 0.0), 10.0)

    rows: list[dict[str, Any]] = []
    for item in viral_payload.get("clip_scores", []) or []:
        if not isinstance(item, dict):
            continue
        clip = item.get("clip", {}) or {}
        legacy_score = item.get("score", {}) or {}

        ai_score = _to_score(item.get("ai_score", clip.get("virality_score", 0)))
        detector_score = _to_score(item.get("detector_score", legacy_score.get("overall_score", 0)))
        combined_score = item.get("combined_score")
        if combined_score is None:
            combined_score = min(max((ai_score * 0.45) + (detector_score * 0.55), 0.0), 10.0)
        combined_score = _to_score(combined_score)

        reasons = item.get("reasons")
        if not isinstance(reasons, list) or not reasons:
            reasons = legacy_score.get("reasons", []) if isinstance(legacy_score, dict) else []
        reason_text = "; ".join(str(reason) for reason in reasons[:2]) if reasons else ""

        rows.append(
            {
                "Start (s)": clip.get("start_seconds", 0),
                "End (s)": clip.get("end_seconds", 0),
                "AI Score": round(ai_score, 2),
                "Detector Score": round(detector_score, 2),
                "Combined Score": round(combined_score, 2),
                "Reasons": reason_text,
                "Description": clip.get("description", ""),
            }
        )

    rows.sort(key=lambda row: row["Combined Score"], reverse=True)
    return rows[:limit]


# ============================================================================
# Dashboard Page
# ============================================================================
def _fetch_runtime_diagnostics(base_url: str, timeout_seconds: float) -> dict[str, Any] | None:
    """Fetch runtime diagnostics payload from /system/runtime."""
    url = f"{base_url.rstrip('/')}/system/runtime"
    try:
        response = httpx.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("runtime_diagnostics_fetch_failed", url=url, error=str(exc))
        return None

    return payload if isinstance(payload, dict) else None


def _runtime_recovery_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize runtime diagnostics for display in recovery controls."""
    if not isinstance(payload, dict):
        return {
            "available": False,
            "active_runs": 0,
            "stale_jobs": [],
            "orphaned_jobs": [],
            "job_rows": [],
        }

    active_jobs = [str(job_id) for job_id in payload.get("active_jobs", []) if job_id]
    stale_jobs = [str(job_id) for job_id in payload.get("stale_jobs", []) if job_id]
    orphaned_jobs = [str(job_id) for job_id in payload.get("orphaned_jobs", []) if job_id]

    job_rows: list[dict[str, Any]] = []
    raw_jobs = payload.get("jobs", [])
    if isinstance(raw_jobs, list):
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue
            job_rows.append(
                {
                    "Job": item.get("job_id", ""),
                    "Status": item.get("status", ""),
                    "Last Stage": item.get("last_known_stage", ""),
                    "Heartbeat Age (s)": item.get("heartbeat_age_seconds"),
                    "Stale": bool(item.get("stale", False)),
                    "Orphaned": bool(item.get("orphaned", False)),
                }
            )

    return {
        "available": True,
        "active_runs": len(active_jobs),
        "stale_jobs": stale_jobs,
        "orphaned_jobs": orphaned_jobs,
        "job_rows": job_rows,
    }


def render_resumable_jobs() -> None:
    """Show resumable jobs banner if any interrupted jobs exist."""
    client = get_service_client()
    try:
        resumable = client.list_resumable_jobs()
    except ServiceError:
        return

    timeout_seconds = max(5.0, float(get_config().service.timeout))
    runtime_payload = _fetch_runtime_diagnostics(get_config().service.base_url, timeout_seconds)
    runtime_summary = _runtime_recovery_summary(runtime_payload)

    action_col1, action_col2 = st.columns([1, 1])
    with action_col1:
        if st.button("♻️ Reconcile Now", key="reconcile_jobs"):
            try:
                corrected = client.reconcile_jobs()
                if corrected > 0:
                    st.success(
                        f"Reconciled {corrected} stale runtime entr{'y' if corrected == 1 else 'ies'}."
                    )
                else:
                    st.info("Reconcile complete: no stale runtime entries found.")
                st.rerun()
            except ServiceError as exc:
                st.error(f"Reconcile failed: {exc}")
    with action_col2:
        if st.button("🧭 Refresh Runtime", key="refresh_runtime"):
            st.rerun()

    if runtime_summary["available"]:
        runtime_col1, runtime_col2, runtime_col3 = st.columns(3)
        runtime_col1.metric("Active Runs", runtime_summary["active_runs"])
        runtime_col2.metric("Stale Runs", len(runtime_summary["stale_jobs"]))
        runtime_col3.metric("Orphaned Runs", len(runtime_summary["orphaned_jobs"]))

        if runtime_summary["stale_jobs"]:
            st.warning(f"Stale runtime jobs: {', '.join(runtime_summary['stale_jobs'])}")
        if runtime_summary["orphaned_jobs"]:
            st.warning(f"Orphaned runtime jobs: {', '.join(runtime_summary['orphaned_jobs'])}")

        if runtime_summary["job_rows"]:
            with st.expander("Runtime Journal Details", expanded=False):
                st.table(runtime_summary["job_rows"])
    else:
        st.caption("Runtime diagnostics unavailable; showing resumable jobs only.")

    if not resumable.jobs:
        st.divider()
        return

    st.warning(
        f"**Recovery:** {len(resumable.jobs)} interrupted "
        f"{'job' if len(resumable.jobs) == 1 else 'jobs'} found"
    )

    for job in resumable.jobs:
        with st.container():
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**{job.job_id}**")
                st.caption(
                    f"Resume from: **{job.resume_stage}** | "
                    f"Done: {', '.join(job.completed_stages) or 'none'}"
                )
            with col2:
                if job.failed_stages:
                    st.caption(f"Failed: {', '.join(job.failed_stages)}")
                if job.interrupted:
                    st.caption("(interrupted)")
            with col3:
                if st.button("Resume", key=f"resume_{job.job_id}"):
                    resume_job_via_service(job.job_id, job.resume_stage)

    st.divider()


def resume_job_via_service(job_id: str, from_stage: str) -> None:
    """Resume an interrupted job through the backend service."""
    client = get_service_client()
    with st.spinner(f"Resuming {job_id} from {from_stage}..."):
        try:
            result = client.resume_job(job_id, from_stage=from_stage)
            st.success(f"Resumed: {result.message}")
            st.rerun()
        except ServiceUnavailableError:
            st.error("Backend service is not running. Start it with: `podcast-pipeline service`")
        except ServiceError as exc:
            st.error(f"Resume failed: {exc}")


def delete_job_via_service(job_id: str) -> None:
    """Delete a job and clear related local UI state."""
    client = get_service_client()
    with st.spinner(f"Deleting {job_id}..."):
        try:
            delete_job = getattr(client, "delete_job", None)
            if callable(delete_job):
                result = delete_job(job_id)
                message = result.message
            else:
                config = get_config()
                response = httpx.delete(
                    f"{config.service.base_url.rstrip('/')}/jobs/{job_id}",
                    timeout=max(5.0, float(config.service.timeout)),
                )
                detail: Any = response.text
                payload: dict[str, Any] = {}
                with contextlib.suppress(ValueError):
                    raw_payload = response.json()
                    if isinstance(raw_payload, dict):
                        payload = raw_payload
                        detail = payload.get("detail", raw_payload)
                if response.is_error:
                    _raise_service_error(response.status_code, detail)
                message = str(payload.get("message", f"Deleted job {job_id}"))
            if st.session_state.get("current_job_id") == job_id:
                st.session_state.pop("current_job_id", None)
            st.session_state.pop(f"timeline_rows_{job_id}", None)
            st.success(message)
            st.rerun()
        except ServiceUnavailableError:
            st.error("Backend service is not running. Start it with: `podcast-pipeline service`")
        except ServiceError as exc:
            st.error(f"Delete failed: {exc}")


def render_dashboard() -> None:
    """Render main dashboard with job list and status."""
    st.header("📊 Dashboard")

    # Show resumable jobs banner if any exist
    render_resumable_jobs()

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Jobs Overview")
    with col2:
        if st.button("🔄 Refresh", key="refresh_jobs"):
            st.rerun()

    jobs = load_jobs_list()

    if not jobs:
        st.info("No jobs found. Create a new job to get started.")
        with st.expander("📁 Create New Job"):
            render_new_job_form()
        return

    # Job stats
    total = len(jobs)
    complete = sum(1 for j in jobs if j["status"] == "complete")
    running = sum(1 for j in jobs if j["status"] in ["running", "waiting"])
    failed = sum(1 for j in jobs if j["status"] == "failed")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Jobs", total)
    col2.metric("Complete", complete)
    col3.metric("In Progress", running)
    col4.metric("Failed", failed)

    st.divider()

    # Jobs table
    for job_info in jobs:
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
            with col1:
                st.markdown(f"**{job_info['job_id']}**")
            with col2:
                st.markdown(status_badge(job_info["status"]))
            with col3:
                st.markdown(f"📅 {job_info['created'][:10]}")
            with col4:
                if st.button("Open", key=f"open_{job_info['job_id']}"):
                    st.session_state.current_job_id = job_info["job_id"]
                    _set_current_page("editor")
                    st.rerun()
            with col5:
                if st.button("🗑️ Delete", key=f"delete_{job_info['job_id']}"):
                    delete_job_via_service(job_info["job_id"])
            st.divider()

    # New job section
    with st.expander("📁 Create New Job"):
        render_new_job_form()


def render_new_job_form() -> None:
    """Render form to create a new job via the backend service."""
    uploaded_file = st.file_uploader(
        "Upload Video File",
        type=["mp4", "mov", "mkv", "avi", "webm"],
        key="new_job_upload",
    )

    job_name = st.text_input("Job Name (optional)", key="new_job_name")

    if uploaded_file and st.button("Create Job", key="create_job_btn"):
        config = get_config()
        jobs_dir = config.paths.jobs_dir

        name_part = job_name.strip() or Path(uploaded_file.name).stem
        video_path = _persist_uploaded_video(uploaded_file, jobs_dir)

        # Create job via service
        client = get_service_client()
        try:
            created = client.create_job(str(video_path), name=name_part)
            st.success(f"Job created: {created.job_id}")
            st.session_state.current_job_id = created.job_id
            st.rerun()
        except ServiceUnavailableError:
            st.error("Backend service is not running. Start it with: `podcast-pipeline service`")
        except ServiceError as exc:
            st.error(f"Failed to create job: {exc}")
        except OSError as exc:
            st.error(f"Failed to save upload for processing: {exc}")


# ============================================================================
# Editor Page
# ============================================================================
def render_editor() -> None:
    """Render the main editor interface."""
    job_id = st.session_state.get("current_job_id")

    if not job_id:
        st.warning("No job selected. Return to dashboard to select a job.")
        if st.button("← Back to Dashboard"):
            _set_current_page("dashboard")
            st.rerun()
        return

    job_dir = _job_dir_for(job_id)

    # Fetch job status from service
    client = get_service_client()
    try:
        job_detail = client.get_job(job_id)
    except ServiceUnavailableError:
        st.error("Backend service is not running. Start it with: `podcast-pipeline service`")
        return
    except ServiceError:
        st.error(
            f"Unable to load job {job_id}. The job state may be invalid. "
            "Delete it from Dashboard and re-run if needed."
        )
        if st.button("← Back to Dashboard", key=f"back_invalid_{job_id}"):
            _set_current_page("dashboard")
            st.rerun()
        return

    # Header
    col1, col2 = st.columns([4, 1])
    with col1:
        st.header(f"🎬 {job_id}")
    with col2:
        if st.button("← Dashboard"):
            _set_current_page("dashboard")
            st.rerun()

    # Stage status from service response
    render_stage_status_from_detail(job_detail.stages)

    # Tab navigation
    tabs = st.tabs(
        [
            "📹 Preview",
            "✂️ Timeline Editor",
            "🖼️ Thumbnails",
            "📝 Marketing",
            "⚙️ Export",
        ]
    )

    with tabs[0]:
        render_video_preview(job_id, job_dir)

    with tabs[1]:
        render_timeline_editor(job_id, job_dir)

    with tabs[2]:
        render_thumbnail_selector(job_dir)

    with tabs[3]:
        render_marketing_editor(job_dir)

    with tabs[4]:
        render_export_panel(job_id, job_dir)


def render_stage_status_from_detail(stages: dict[str, Any]) -> None:
    """Render pipeline stage status from a service detail response."""
    stage_names = ["ingest", "transcribe", "analyze", "review", "render"]
    cols = st.columns(len(stage_names))

    for i, stage_name in enumerate(stage_names):
        stage = stages.get(stage_name)
        status = stage.status if stage else "pending"

        with cols[i]:
            icon = {
                "complete": "✅",
                "running": "⏳",
                "waiting": "⏸️",
                "failed": "❌",
                "pending": "○",
            }.get(status, "○")
            st.markdown(f"**{icon} {stage_name.title()}**")
            if stage:
                if stage.progress_percent is not None:
                    progress_value = max(0, min(stage.progress_percent, 100))
                    st.progress(progress_value)
                if stage.progress_message:
                    st.caption(stage.progress_message)


def render_video_preview(job_id: str, job_dir: Path) -> None:
    """Render video preview with playback controls."""
    st.subheader("Video Preview")

    # Find video file
    proxy_path = job_dir / "intermediate" / "proxy.mp4"
    input_dir = job_dir / "input"

    video_path = None
    if proxy_path.exists():
        video_path = proxy_path
    else:
        for ext in [".mp4", ".mov", ".mkv", ".avi", ".webm"]:
            p = input_dir / f"raw{ext}"
            if p.exists():
                video_path = p
                break

    if video_path and video_path.exists():
        st.video(str(video_path))

        # Get video duration from metadata
        duration = 0.0
        metadata = _load_ingest_metadata(job_dir)
        if metadata is not None:
            with contextlib.suppress(TypeError, ValueError):
                duration = float(metadata.get("duration", 0))

        # Timeline scrubber
        if duration > 0:
            st.markdown("**Timeline Scrubber**")
            time_pos = st.slider(
                "Position (seconds)",
                min_value=0.0,
                max_value=duration,
                value=0.0,
                step=0.1,
                key="video_timeline_scrub",
            )

            mins = int(time_pos // 60)
            secs = time_pos % 60
            st.caption(f"Current position: {mins:02d}:{secs:05.2f}")
    else:
        st.info("No video file available. Run the ingest stage first.")
        if st.button("Run Ingest Stage", key="run_ingest"):
            run_stage_via_service(job_id, "ingest")


def _parse_time_seconds(raw: Any) -> float | None:
    """Parse timestamp values from float/int/HH:MM:SS-like strings."""
    parsed: float | None = None

    if isinstance(raw, (int, float)):
        parsed = float(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if text:
            with contextlib.suppress(ValueError):
                parsed = float(text)
            if parsed is None:
                parts = text.split(":")
                if 1 <= len(parts) <= 3:
                    seconds = 0.0
                    valid = True
                    for part in parts:
                        try:
                            seconds = (seconds * 60.0) + float(part)
                        except ValueError:
                            valid = False
                            break
                    if valid:
                        parsed = seconds

    if parsed is None or parsed < 0:
        return None
    return parsed


def _format_time_seconds(value: float) -> str:
    """Format seconds as HH:MM:SS.ss or MM:SS.ss."""
    safe_seconds = max(0.0, float(value))
    hours = int(safe_seconds // 3600)
    minutes = int((safe_seconds % 3600) // 60)
    seconds = safe_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"


def _clone_timeline_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a shallow-cloned list of timeline row dicts."""
    return [{**row} for row in rows]


def _timeline_rows_from_artifacts(
    job_dir: Path,
    analysis: dict[str, Any],
    decisions: ReviewDecisions,
) -> list[dict[str, Any]]:
    """Load timeline rows from edit_plan first, then analysis+review defaults."""
    edit_plan_path = job_dir / "review" / "edit_plan.json"
    if edit_plan_path.exists():
        try:
            payload = json.loads(edit_plan_path.read_text())
            raw_cuts = payload.get("content_cuts", []) if isinstance(payload, dict) else []
            rows: list[dict[str, Any]] = []
            for idx, cut in enumerate(raw_cuts):
                if not isinstance(cut, dict):
                    continue
                start_seconds = _parse_time_seconds(cut.get("start_seconds"))
                end_seconds = _parse_time_seconds(cut.get("end_seconds"))
                if start_seconds is None or end_seconds is None:
                    continue
                rows.append(
                    {
                        "id": f"plan-{idx}",
                        "enabled": True,
                        "start_seconds": start_seconds,
                        "end_seconds": end_seconds,
                        "reason": str(cut.get("reason", "")),
                    }
                )
            if rows:
                return rows
        except Exception as exc:
            logger.warning(
                "timeline_edit_plan_load_failed", path=str(edit_plan_path), error=str(exc)
            )

    approved_indices = set(decisions.approved_content_cuts)
    analysis_cuts = analysis.get("content_cuts", [])
    analysis_rows: list[dict[str, Any]] = []
    if not isinstance(analysis_cuts, list):
        return analysis_rows

    for idx, cut in enumerate(analysis_cuts):
        if not isinstance(cut, dict):
            continue
        start_seconds = _parse_time_seconds(cut.get("start_seconds", cut.get("start")))
        end_seconds = _parse_time_seconds(cut.get("end_seconds", cut.get("end")))
        if start_seconds is None or end_seconds is None:
            continue
        analysis_rows.append(
            {
                "id": f"analysis-{idx}",
                "enabled": idx in approved_indices,
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "reason": str(cut.get("reason", "")),
            }
        )

    return analysis_rows


def _validate_timeline_rows(
    rows: list[dict[str, Any]], duration_seconds: float | None
) -> list[str]:
    """Validate timeline rows and return user-facing error messages."""
    errors: list[str] = []
    enabled_rows: list[tuple[int, float, float]] = []

    for row_index, row in enumerate(rows, start=1):
        if not row.get("enabled", True):
            continue
        start_seconds = _parse_time_seconds(row.get("start_seconds"))
        end_seconds = _parse_time_seconds(row.get("end_seconds"))
        if start_seconds is None or end_seconds is None:
            errors.append(f"Cut {row_index}: start/end must be valid numeric timestamps.")
            continue
        if end_seconds <= start_seconds:
            errors.append(f"Cut {row_index}: end must be greater than start.")
            continue
        if duration_seconds and end_seconds > duration_seconds:
            errors.append(
                f"Cut {row_index}: end {end_seconds:.2f}s exceeds source duration {duration_seconds:.2f}s."
            )
        enabled_rows.append((row_index, start_seconds, end_seconds))

    ordered = sorted(enabled_rows, key=lambda item: item[1])
    for previous, current in pairwise(ordered):
        if current[1] < previous[2]:
            errors.append(
                f"Cuts {previous[0]} and {current[0]} overlap ({previous[1]:.2f}-{previous[2]:.2f}s "
                f"vs {current[1]:.2f}-{current[2]:.2f}s)."
            )

    return errors


def _serialize_enabled_timeline_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert enabled timeline rows into analysis-compatible content cuts."""
    serialized: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("enabled", True):
            continue
        start_seconds = _parse_time_seconds(row.get("start_seconds"))
        end_seconds = _parse_time_seconds(row.get("end_seconds"))
        if start_seconds is None or end_seconds is None:
            continue
        serialized.append(
            {
                "start_seconds": round(start_seconds, 3),
                "end_seconds": round(end_seconds, 3),
                "start": _format_time_seconds(start_seconds),
                "end": _format_time_seconds(end_seconds),
                "reason": str(row.get("reason", "")),
            }
        )
    return serialized


def _persist_timeline_edit_plan(
    job_dir: Path,
    decisions: ReviewDecisions,
    analysis: dict[str, Any],
    fillers: list[dict[str, Any]],
    timeline_rows: list[dict[str, Any]],
) -> None:
    """Persist review state and regenerate edit plan using edited timeline rows."""
    enabled_content_cuts = _serialize_enabled_timeline_rows(timeline_rows)

    review_dir = job_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    decisions_for_plan = decisions.model_copy(deep=True)
    decisions_for_plan.approved_content_cuts = list(range(len(enabled_content_cuts)))
    decisions.approved_content_cuts = list(decisions_for_plan.approved_content_cuts)

    review_path = review_dir / "review_state.json"
    review_path.write_text(decisions.model_dump_json(indent=2))

    analysis_for_plan = analysis.copy()
    analysis_for_plan["content_cuts"] = enabled_content_cuts
    write_edit_plan(job_dir, decisions_for_plan, analysis_for_plan, fillers)


def render_timeline_editor(job_id: str, job_dir: Path) -> None:
    """Render timeline-capable cut editor with persisted range edits."""
    st.subheader("Timeline Editor")

    source_duration: float | None = None
    ingest_metadata = _load_ingest_metadata(job_dir)
    if ingest_metadata is not None:
        with contextlib.suppress(TypeError, ValueError):
            duration_seconds = float(ingest_metadata.get("duration", 0))
            if duration_seconds > 0:
                source_duration = duration_seconds
                st.caption(f"Source duration: {duration_seconds:.1f}s")

    # Load analysis data
    analysis_path = job_dir / "analysis" / "analysis.json"
    if not analysis_path.exists():
        st.info("No analysis available. Run the analyze stage first.")
        if st.button("Run Analyze Stage", key="run_analyze"):
            run_stage_via_service(job_id, "analyze")
        return

    try:
        analysis = json.loads(analysis_path.read_text())
    except Exception as e:
        st.error(f"Failed to load analysis: {e}")
        return

    # Load current review decisions
    review_path = job_dir / "review" / "review_state.json"
    decisions = None
    if review_path.exists():
        with contextlib.suppress(Exception):
            decisions = ReviewDecisions.model_validate_json(review_path.read_text())
    if decisions is None:
        decisions = ReviewDecisions()

    # Content Cuts Section
    st.markdown("#### Content Cuts")
    timeline_state_key = f"timeline_rows_{job_id}"
    timeline_defaults = _timeline_rows_from_artifacts(job_dir, analysis, decisions)
    if timeline_state_key not in st.session_state:
        st.session_state[timeline_state_key] = _clone_timeline_rows(timeline_defaults)

    timeline_rows = st.session_state.get(timeline_state_key, [])
    if not isinstance(timeline_rows, list):
        timeline_rows = _clone_timeline_rows(timeline_defaults)
        st.session_state[timeline_state_key] = timeline_rows

    if not timeline_rows:
        st.info("No content cuts suggested yet. Add ranges below if needed.")
    else:
        st.caption("Adjust start/end timestamps, disable ranges, or remove rows before saving.")

    updated_rows: list[dict[str, Any]] = []
    remove_target_id: str | None = None

    for row_index, row in enumerate(timeline_rows):
        row_id = str(row.get("id", f"row-{row_index}"))
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 3, 1])
            with col1:
                enabled = st.checkbox(
                    "Use",
                    value=bool(row.get("enabled", True)),
                    key=f"timeline_enabled_{job_id}_{row_id}",
                )
            with col2:
                start_seconds = st.number_input(
                    "Start (s)",
                    min_value=0.0,
                    value=float(row.get("start_seconds", 0.0)),
                    step=0.1,
                    format="%.2f",
                    key=f"timeline_start_{job_id}_{row_id}",
                )
            with col3:
                end_seconds = st.number_input(
                    "End (s)",
                    min_value=0.0,
                    value=float(row.get("end_seconds", 0.0)),
                    step=0.1,
                    format="%.2f",
                    key=f"timeline_end_{job_id}_{row_id}",
                )
            with col4:
                reason = st.text_input(
                    "Reason",
                    value=str(row.get("reason", "")),
                    key=f"timeline_reason_{job_id}_{row_id}",
                )
            with col5:
                if st.button("🗑", key=f"timeline_remove_{job_id}_{row_id}"):
                    remove_target_id = row_id

        if remove_target_id == row_id:
            continue

        updated_rows.append(
            {
                "id": row_id,
                "enabled": enabled,
                "start_seconds": float(start_seconds),
                "end_seconds": float(end_seconds),
                "reason": reason,
            }
        )

    if remove_target_id is not None:
        st.session_state[timeline_state_key] = updated_rows
        st.rerun()

    st.divider()

    st.markdown("**Add Cut Range**")
    add_col1, add_col2, add_col3, add_col4 = st.columns([2, 2, 3, 1])
    with add_col1:
        new_start = st.number_input(
            "New start (s)",
            min_value=0.0,
            value=0.0,
            step=0.1,
            format="%.2f",
            key=f"timeline_new_start_{job_id}",
        )
    with add_col2:
        new_end = st.number_input(
            "New end (s)",
            min_value=0.0,
            value=1.0,
            step=0.1,
            format="%.2f",
            key=f"timeline_new_end_{job_id}",
        )
    with add_col3:
        new_reason = st.text_input(
            "New reason",
            value="",
            key=f"timeline_new_reason_{job_id}",
            placeholder="Optional reason for this cut",
        )
    with add_col4:
        if st.button("Add", key=f"timeline_add_{job_id}"):
            if new_end <= new_start:
                st.error("New cut must have end greater than start.")
            else:
                new_id = f"custom-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
                updated_rows.append(
                    {
                        "id": new_id,
                        "enabled": True,
                        "start_seconds": float(new_start),
                        "end_seconds": float(new_end),
                        "reason": new_reason.strip(),
                    }
                )
                st.session_state[timeline_state_key] = updated_rows
                st.rerun()

    st.divider()

    # Filler Words Section
    st.markdown("#### Filler Words")
    filler_path = job_dir / "analysis" / "filler_cuts.json"
    transcript_path = job_dir / "analysis" / "transcript.json"

    fillers: list[dict[str, Any]] = []
    try:
        if filler_path.exists():
            raw_fillers = json.loads(filler_path.read_text())
            if isinstance(raw_fillers, list):
                fillers = [f for f in raw_fillers if isinstance(f, dict)]
        elif transcript_path.exists():
            transcript = json.loads(transcript_path.read_text())
            transcript_fillers = (
                transcript.get("filler_cuts") or transcript.get("filler_words") or []
            )
            if isinstance(transcript_fillers, list):
                fillers = [f for f in transcript_fillers if isinstance(f, dict)]
    except Exception as e:
        st.error(f"Failed to load filler cuts: {e}")

    if not fillers:
        st.success("No filler words detected!")
    else:
        st.info(f"Found {len(fillers)} filler words")

        with st.expander(f"View {len(fillers)} filler words"):
            approved_fillers = list(decisions.approved_filler_cuts or list(range(len(fillers))))

            select_all = st.checkbox(
                "Select All Fillers",
                value=len(approved_fillers) == len(fillers),
                key=f"select_all_fillers_{job_id}",
            )

            if select_all:
                approved_fillers = list(range(len(fillers)))

            for j, filler in enumerate(fillers[:50]):  # Show first 50
                col1, col2, col3 = st.columns([1, 2, 2])
                with col1:
                    selected = st.checkbox(
                        "✓",
                        value=j in approved_fillers,
                        key=f"filler_{job_id}_{j}",
                        label_visibility="collapsed",
                    )
                    if selected and j not in approved_fillers:
                        approved_fillers.append(j)
                    elif not selected and j in approved_fillers:
                        approved_fillers.remove(j)
                with col2:
                    st.caption(f'"{filler.get("word", "")}"')
                with col3:
                    start = filler.get("start_seconds", filler.get("start", ""))
                    st.caption(f"{start}")

            if len(fillers) > 50:
                st.caption(f"... and {len(fillers) - 50} more")

            decisions.approved_filler_cuts = sorted(set(approved_fillers))

    # Save changes button
    if st.button("💾 Save Timeline Changes", key="save_timeline"):
        validation_errors = _validate_timeline_rows(updated_rows, source_duration)
        if validation_errors:
            for issue in validation_errors:
                st.error(issue)
            return

        st.session_state[timeline_state_key] = _clone_timeline_rows(updated_rows)
        try:
            _persist_timeline_edit_plan(job_dir, decisions, analysis, fillers, updated_rows)
        except Exception as exc:
            st.error(f"Failed to persist timeline edits: {exc}")
            return
        st.success("Timeline changes saved to review state and edit plan.")


def render_thumbnail_selector(job_dir: Path) -> None:
    """Render thumbnail candidate selector with grid view."""
    st.subheader("Thumbnail Selector")

    # Load analysis
    analysis_path = job_dir / "analysis" / "analysis.json"
    if not analysis_path.exists():
        st.info("No analysis available. Run the analyze stage first.")
        return

    try:
        analysis = json.loads(analysis_path.read_text())
    except Exception as e:
        st.error(f"Failed to load analysis: {e}")
        return

    thumbnails = analysis.get("thumbnail_frames", [])

    if not thumbnails:
        st.info("No thumbnail candidates found.")
        return

    decisions = _load_review_decisions(job_dir)
    selected_thumbnails = _normalize_ranked_thumbnail_selection(
        decisions.selected_thumbnails,
        decisions.selected_thumbnail,
    )
    rank_by_index = {index: rank for rank, index in enumerate(selected_thumbnails, start=1)}

    st.markdown("**Select up to 3 thumbnail frames (ranked):**")
    st.caption("Selection order is preserved. Rank #1 is the primary thumbnail.")

    cols_per_row = 3
    for row_start in range(0, len(thumbnails), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, thumb_idx in enumerate(
            range(row_start, min(row_start + cols_per_row, len(thumbnails)))
        ):
            thumb = thumbnails[thumb_idx]
            with cols[col_idx]:
                rank = rank_by_index.get(thumb_idx)
                if rank is None:
                    st.caption("Not selected")
                elif rank == 1:
                    st.caption("Selected #1 (Primary)")
                else:
                    st.caption(f"Selected #{rank} (Alternate)")

                image_path = _thumbnail_image_path(job_dir, thumb)
                if image_path is not None and image_path.exists():
                    try:
                        st.image(str(image_path), width="stretch")
                    except TypeError:
                        # Streamlit versions before width="stretch" support this fallback path.
                        st.image(str(image_path), use_container_width=True)
                else:
                    st.caption("Preview image unavailable for this candidate.")

                timestamp_label = str(thumb.get("timestamp", "N/A"))
                visual_description = str(thumb.get("visual_description", "")).strip()
                overlay_text = str(thumb.get("suggested_text_overlay", "")).strip()
                emotion = str(thumb.get("emotion", "neutral")).strip() or "neutral"
                recommendation_signal = str(thumb.get("recommendation_signal", "")).strip()
                virality_score = thumb.get("virality_score")

                st.caption(f"⏱️ {timestamp_label}")
                if visual_description:
                    st.caption(visual_description[:120])
                if overlay_text:
                    st.caption(f'💬 "{overlay_text[:120]}"')
                if isinstance(virality_score, (int, float)):
                    st.caption(f"🔥 Virality: {float(virality_score):.1f}/10")
                if recommendation_signal:
                    st.caption(f"⭐ Signal: {recommendation_signal}")
                st.caption(f"😊 {emotion}")

                can_add_more = len(selected_thumbnails) < 3
                if rank is not None:
                    button_label = f"Remove #{rank}"
                    button_disabled = False
                else:
                    button_label = (
                        f"Add as #{len(selected_thumbnails) + 1}" if can_add_more else "Max 3"
                    )
                    button_disabled = not can_add_more

                if st.button(
                    button_label, key=f"thumb_select_{thumb_idx}", disabled=button_disabled
                ):
                    update_thumbnail_selection(job_dir, thumb_idx)
                    st.rerun()


def render_marketing_editor(job_dir: Path) -> None:
    """Render interactive marketing copy editor."""
    st.subheader("Marketing Copy Editor")

    # Load analysis
    analysis_path = job_dir / "analysis" / "analysis.json"
    if not analysis_path.exists():
        st.info("No marketing copy available. Run the analyze stage first.")
        return

    try:
        analysis = json.loads(analysis_path.read_text())
    except Exception as e:
        st.error(f"Failed to load analysis: {e}")
        return

    decisions = _load_review_decisions(job_dir)
    marketing, metadata = _apply_marketing_review_edits(analysis, decisions)

    # Episode info
    with st.expander("📋 Episode Information", expanded=True):
        summary = st.text_area(
            "Summary",
            value=metadata.get("summary", ""),
            height=100,
            key="edit_summary",
        )
        topics = st.text_input(
            "Topics (comma-separated)",
            value=_topics_to_text(metadata.get("topics")),
            key="edit_topics",
        )
        mood = st.text_input(
            "Mood",
            value=metadata.get("mood", ""),
            key="edit_mood",
        )

    # Research + Viral Insights
    with st.expander("📈 Research & Viral Insights", expanded=False):
        research_path = job_dir / "analysis" / "research.json"
        viral_path = job_dir / "analysis" / "viral_signals.json"

        if not research_path.exists() and not viral_path.exists():
            st.info(
                "Research and viral insights are not available yet. Run the analyze stage after configuring YOUTUBE_API_KEY."
            )
        else:
            if research_path.exists():
                try:
                    research = json.loads(research_path.read_text())
                    panel_data = _build_research_panel_data(research)
                    st.markdown("**Research Query:**")
                    st.caption(panel_data["query"])

                    if panel_data["competition_score"] is not None:
                        competition_tier = panel_data.get("competition_tier") or "unrated"
                        st.markdown("**Competition Score:**")
                        st.caption(
                            f"{panel_data['competition_score']:.1f}/100 ({competition_tier} competition)"
                        )

                    avg_engagement = panel_data.get("avg_engagement_rate")
                    avg_velocity = panel_data.get("avg_velocity_per_hour")
                    if avg_engagement is not None or avg_velocity is not None:
                        st.markdown("**Engagement Benchmarks:**")
                        metrics = []
                        if avg_engagement is not None:
                            metrics.append(f"avg engagement: {float(avg_engagement):.4f}")
                        if avg_velocity is not None:
                            metrics.append(f"avg velocity/hr: {float(avg_velocity):.2f}")
                        st.caption(" • ".join(metrics))

                    keywords = panel_data["keywords"]
                    if keywords:
                        st.markdown("**Top Weighted Keywords:**")
                        st.write(", ".join(keywords))

                    posting_windows = panel_data["posting_windows"]
                    if posting_windows:
                        st.markdown("**Best Posting Windows (UTC):**")
                        for window in posting_windows[:3]:
                            st.caption(window)

                    competitors = research.get("competitor_channels", [])
                    if competitors:
                        st.markdown("**Competitor Channels:**")
                        for channel in competitors[:5]:
                            title = channel.get("title", "Unknown")
                            subs = channel.get("subscriber_count", 0)
                            st.caption(f"{title} — {subs:,} subscribers")

                    trending_videos = research.get("trending_videos", [])
                    if trending_videos:
                        st.caption(f"{len(trending_videos)} trending videos analyzed")
                except Exception as e:
                    st.warning(f"Failed to load research insights: {e}")

            if viral_path.exists():
                try:
                    viral = json.loads(viral_path.read_text())
                    signals = viral.get("signals", [])
                    if signals:
                        st.markdown("**Top Engagement Signals:**")
                        top_signals = sorted(
                            signals,
                            key=lambda s: s.get("strength", 0),
                            reverse=True,
                        )[:5]
                        for signal in top_signals:
                            timestamp = signal.get("timestamp_seconds", 0)
                            signal_type = signal.get("signal_type", "signal")
                            description = signal.get("description", "")
                            st.caption(f"{signal_type} @ {timestamp:.1f}s — {description}")

                    clip_scores = viral.get("clip_scores", [])
                    if clip_scores:
                        st.markdown("**Per-Clip Score Breakdown:**")
                        st.table(_build_clip_score_rows(viral, limit=10))
                except Exception as e:
                    st.warning(f"Failed to load viral signals: {e}")

    # Platform-specific marketing
    edited_marketing: dict[str, Any] = {}

    for platform_spec in _marketing_editor_platform_specs():
        platform_name = platform_spec.label
        platform_key = platform_spec.key
        icon = platform_spec.icon
        platform_data = marketing.get(platform_key, {})

        with st.expander(f"{icon} {platform_name}", expanded=(platform_key == "youtube")):
            titles = [title for title in platform_data.get("titles", []) if isinstance(title, str)]

            # Titles
            if platform_spec.title_mode == "multi":
                st.markdown("**Title Options:**")
                edited_titles = []
                existing_titles = titles[:5] if titles else [""]
                for i, title in enumerate(existing_titles):
                    edited_title = st.text_input(
                        f"Title {i + 1}",
                        value=title,
                        key=f"{platform_key}_title_{i}",
                    )
                    if edited_title.strip():
                        edited_titles.append(edited_title.strip())
                edited_marketing[platform_key] = {"titles": edited_titles}
            elif platform_spec.title_mode == "single":
                st.markdown("**Episode Title:**")
                base_title = titles[0] if titles else ""
                edited_title = st.text_input(
                    "Title",
                    value=base_title,
                    key=f"{platform_key}_title_0",
                )
                edited_marketing[platform_key] = {
                    "titles": [edited_title.strip()] if edited_title.strip() else []
                }

            # Description
            description = platform_data.get("description", "")

            edited_desc = st.text_area(
                "Description",
                value=description,
                height=platform_spec.description_height,
                max_chars=platform_spec.max_description_chars,
                key=f"{platform_key}_desc",
            )
            st.caption(f"{len(edited_desc)}/{platform_spec.max_description_chars} characters")
            st.caption(platform_spec.description_guidance)

            if platform_key not in edited_marketing:
                edited_marketing[platform_key] = {}
            edited_marketing[platform_key]["description"] = edited_desc

            # Hashtags
            hashtags = platform_data.get("hashtags", [])
            edited_hashtags = st.text_input(
                "Hashtags",
                value=" ".join(hashtags),
                key=f"{platform_key}_hashtags",
                help="Space-separated hashtags",
            )
            edited_marketing[platform_key]["hashtags"] = edited_hashtags.split()

    # Save button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 Save Marketing Copy", key="save_marketing"):
            _save_marketing_edits_to_review_flow(
                job_dir,
                decisions,
                edited_marketing,
                summary,
                topics,
                mood,
            )
            st.success("Marketing copy saved to review workflow!")

    with col2:
        if st.button("🔄 Regenerate Marketing Copy", key="regen_marketing"):
            job_id = job_dir.name
            client = get_service_client()
            with st.spinner("Regenerating analysis and marketing copy..."):
                try:
                    _prepare_marketing_regeneration_review_state(job_dir)
                    result = client.resume_job(
                        job_id,
                        from_stage="analyze",
                        until_stage="review",
                    )
                    if result.status in {"complete", "running"}:
                        st.success(
                            "Regenerated through review workflow. Reloading latest analysis..."
                        )
                        st.rerun()
                    else:
                        st.error(f"Regeneration failed: {result.message}")
                except ServiceUnavailableError:
                    st.error(
                        "Backend service is not running. Start it with: `podcast-pipeline service`"
                    )
                except ServiceError as exc:
                    st.error(f"Regeneration error: {exc}")


def render_export_panel(job_id: str, job_dir: Path) -> None:
    """Render export configuration and execution panel."""
    st.subheader("Export Configuration")

    get_config()

    # Platform selection
    st.markdown("**Select Export Platforms:**")

    available_platforms = _export_platform_options()

    # Load existing selections
    review_path = job_dir / "review" / "review_state.json"
    selected_platforms, dropped_saved_keys = _load_normalized_export_platforms(review_path)
    if dropped_saved_keys:
        dropped_text = ", ".join(dropped_saved_keys)
        st.info(f"Ignored unsupported saved export targets: {dropped_text}")

    # Grid of platform toggles
    cols = st.columns(4)
    new_selected: list[str] = []

    for i, (name, key, desc) in enumerate(available_platforms):
        with cols[i % 4]:
            if st.checkbox(
                f"{name}",
                value=key in selected_platforms,
                key=f"export_platform_{key}",
                help=desc,
            ):
                new_selected.append(key)

    st.caption(_export_boundary_guidance())
    st.divider()

    # Quality settings
    st.markdown("**Quality Settings:**")
    col1, col2 = st.columns(2)

    with col1:
        video_quality = st.select_slider(
            "Video Quality",
            options=["draft", "standard", "high", "ultra"],
            value="standard",
            key="video_quality",
        )

    with col2:
        audio_normalize = st.checkbox(
            "Normalize Audio Loudness",
            value=True,
            key="audio_normalize",
        )

    quality_controls = {
        "video_quality": video_quality,
        "audio_normalize": bool(audio_normalize),
    }

    st.divider()

    # Review status check
    review_complete = False
    if review_path.exists():
        try:
            decisions = ReviewDecisions.model_validate_json(review_path.read_text())
            review_complete = decisions.review_complete
        except Exception:
            pass

    # Export buttons
    col1, col2, _col3 = st.columns([1, 1, 2])

    with col1:
        if not review_complete:
            if st.button("✅ Approve & Export", key="approve_export"):
                # Save platform selections
                normalized_platforms, dropped = update_export_platforms(job_dir, new_selected)
                if dropped:
                    st.warning(f"Unsupported platform keys were ignored: {', '.join(dropped)}")
                # Mark review complete
                approve_review(job_dir, normalized_platforms)
                # Run render via service
                run_stage_via_service(job_id, "render", quality_controls=quality_controls)
        elif st.button("🎬 Export Now", key="export_now"):
            _, dropped = update_export_platforms(job_dir, new_selected)
            if dropped:
                st.warning(f"Unsupported platform keys were ignored: {', '.join(dropped)}")
            run_stage_via_service(job_id, "render", quality_controls=quality_controls)

    with col2:
        if not review_complete:
            st.warning("Review not approved")
        else:
            st.success("Review approved ✓")

    # Output files
    output_dir = job_dir / "output"
    if output_dir.exists():
        st.divider()
        st.markdown("**Generated Outputs:**")

        for platform_dir in output_dir.iterdir():
            if platform_dir.is_dir():
                for f in platform_dir.iterdir():
                    if f.is_file():
                        file_size = f.stat().st_size / (1024 * 1024)  # MB
                        st.markdown(f"📁 `{platform_dir.name}/{f.name}` ({file_size:.1f} MB)")


# ============================================================================
# Helper Functions
# ============================================================================
def run_stage_via_service(
    job_id: str,
    stage_name: str,
    quality_controls: dict[str, Any] | None = None,
) -> None:
    """Run a pipeline stage through the backend service."""
    client = get_service_client()

    with st.spinner(f"Running {stage_name} stage..."):
        try:
            run_kwargs: dict[str, Any] = {"stage": stage_name}
            if quality_controls is not None:
                run_kwargs["quality_controls"] = quality_controls
            result = client.run_job(job_id, **run_kwargs)
            if result.status == "complete":
                st.success(f"{stage_name.title()} stage completed!")
                st.rerun()
            else:
                st.error(f"{stage_name.title()} failed: {result.message}")
        except ServiceUnavailableError:
            st.error("Backend service is not running. Start it with: `podcast-pipeline service`")
        except ServiceConflictError as exc:
            if _is_invalid_job_conflict(exc):
                if st.session_state.get("current_job_id") == job_id:
                    st.session_state.pop("current_job_id", None)
                st.session_state.pop(f"timeline_rows_{job_id}", None)
                st.error(
                    f"Job {job_id} has invalid state and cannot run. "
                    "Delete or repair it from Dashboard."
                )
                _set_current_page("dashboard")
                return
            st.error(f"Error running {stage_name}: {exc}")
        except ServiceError as exc:
            st.error(f"Error running {stage_name}: {exc}")


def run_full_pipeline_via_service(job_id: str) -> None:
    """Run the pipeline from the first stage through the normal workflow."""
    client = get_service_client()

    with st.spinner("Running full pipeline..."):
        try:
            result = client.run_job(job_id)
            if result.status == "complete":
                st.success(f"Full pipeline run complete: {result.message}")
                st.rerun()
            else:
                st.error(f"Full pipeline run failed: {result.message}")
        except ServiceUnavailableError:
            st.error("Backend service is not running. Start it with: `podcast-pipeline service`")
        except ServiceConflictError as exc:
            if _is_invalid_job_conflict(exc):
                if st.session_state.get("current_job_id") == job_id:
                    st.session_state.pop("current_job_id", None)
                st.session_state.pop(f"timeline_rows_{job_id}", None)
                st.error(
                    f"Job {job_id} has invalid state and cannot run. "
                    "Delete or repair it from Dashboard."
                )
                _set_current_page("dashboard")
                return
            st.error(f"Error running full pipeline: {exc}")
        except ServiceError as exc:
            st.error(f"Error running full pipeline: {exc}")


def save_review_decisions(job_dir: Path, decisions: ReviewDecisions | None) -> None:
    """Save review decisions to file."""
    review_dir = job_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    if decisions is None:
        decisions = ReviewDecisions()

    review_path = review_dir / "review_state.json"
    review_path.write_text(decisions.model_dump_json(indent=2))

    analysis_path = job_dir / "analysis" / "analysis.json"
    filler_path = job_dir / "analysis" / "filler_cuts.json"
    analysis = json.loads(analysis_path.read_text()) if analysis_path.exists() else {}
    fillers = json.loads(filler_path.read_text()) if filler_path.exists() else []
    write_edit_plan(job_dir, decisions, analysis, fillers)


def update_thumbnail_selection(job_dir: Path, thumbnail_idx: int) -> None:
    """Toggle thumbnail selection while preserving ranked order and compatibility mirror."""
    if thumbnail_idx < 0:
        return

    review_dir = job_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    review_path = review_dir / "review_state.json"

    if review_path.exists():
        decisions = ReviewDecisions.model_validate_json(review_path.read_text())
    else:
        decisions = ReviewDecisions()

    current_ranked = _normalize_ranked_thumbnail_selection(
        decisions.selected_thumbnails,
        decisions.selected_thumbnail,
    )
    updated_ranked = _toggle_ranked_thumbnail_selection(current_ranked, thumbnail_idx)
    decisions.selected_thumbnails = updated_ranked
    decisions.selected_thumbnail = updated_ranked[0] if updated_ranked else None
    review_path.write_text(decisions.model_dump_json(indent=2))


def _normalize_ranked_thumbnail_selection(
    selected_thumbnails: list[int] | None,
    primary_thumbnail: int | None,
) -> list[int]:
    """Normalize ranked thumbnail selections to unique 0-based indices capped at 3."""
    normalized: list[int] = []
    if isinstance(primary_thumbnail, int) and primary_thumbnail >= 0:
        normalized.append(primary_thumbnail)

    for index in selected_thumbnails or []:
        if not isinstance(index, int) or index < 0 or index in normalized:
            continue
        normalized.append(index)
        if len(normalized) >= 3:
            break

    return normalized


def _toggle_ranked_thumbnail_selection(current: list[int], thumbnail_idx: int) -> list[int]:
    """Toggle one thumbnail index in a ranked list with a max of three entries."""
    deduped = _normalize_ranked_thumbnail_selection(current, None)
    if thumbnail_idx in deduped:
        return [index for index in deduped if index != thumbnail_idx]
    if len(deduped) >= 3:
        return deduped
    return [*deduped, thumbnail_idx]


def _thumbnail_image_path(job_dir: Path, thumbnail: dict[str, Any]) -> Path | None:
    """Resolve thumbnail preview image path from analysis payload candidate metadata."""
    raw_path = thumbnail.get("image_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    return job_dir / raw_path


def update_export_platforms(job_dir: Path, platforms: list[str]) -> tuple[list[str], list[str]]:
    """Update selected export platforms with canonical normalization."""
    review_dir = job_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    review_path = review_dir / "review_state.json"

    if review_path.exists():
        decisions = ReviewDecisions.model_validate_json(review_path.read_text())
    else:
        decisions = ReviewDecisions()

    normalized, invalid = normalize_export_platforms(platforms, include_invalid=True)
    decisions.export_platforms = normalized
    review_path.write_text(decisions.model_dump_json(indent=2))
    return normalized, invalid


# ============================================================================
# Main App
# ============================================================================
def main() -> None:
    """Main Streamlit application entry point."""
    # Sidebar navigation
    with st.sidebar:
        st.image(
            "https://www.shutterstock.com/shutterstock/photos/2047266761/display_1500/stock-vector-banner-template-for-podcast-show-microphone-headphones-text-and-sound-wave-trend-vector-design-2047266761.jpg",
            use_container_width=True,
        )
        st.title("Podcast Pipeline")
        st.divider()

        # Service status indicator
        if check_service_status():
            st.success("Service: Connected", icon="🟢")
        else:
            st.error("Service: Offline", icon="🔴")
            st.caption("Run: `podcast-pipeline service`")

        st.divider()

        # Navigation
        _sync_nav_with_page()
        page = st.radio(
            "Navigation",
            list(_NAV_PAGES_BY_LABEL.keys()),
            key="nav_radio",
            label_visibility="collapsed",
        )

        # Update page state
        selected_page = _NAV_PAGES_BY_LABEL.get(page, "dashboard")
        if selected_page != _normalize_page(st.session_state.get("page")):
            st.session_state["page"] = selected_page

        st.divider()

        # Quick actions
        st.markdown("**Quick Actions**")

        current_job = st.session_state.get("current_job_id")
        if current_job:
            st.caption(f"Current: {current_job[:20]}...")
            current_status = _safe_current_job_status(current_job)
            if current_status == "invalid":
                st.warning("Current job state is invalid.")
                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    if st.button("🗑️ Delete Job", key=f"delete_invalid_quick_{current_job}"):
                        delete_job_via_service(current_job)
                with action_col2:
                    if st.button("🧹 Clear Selection", key=f"clear_invalid_quick_{current_job}"):
                        st.session_state.pop("current_job_id", None)
                        st.session_state.pop(f"timeline_rows_{current_job}", None)
                        _set_current_page("dashboard")
                        st.rerun()
            elif current_status is None:
                st.warning("Current job is unavailable.")
                if st.button("🧹 Clear Selection", key=f"clear_missing_quick_{current_job}"):
                    st.session_state.pop("current_job_id", None)
                    st.session_state.pop(f"timeline_rows_{current_job}", None)
                    _set_current_page("dashboard")
                    st.rerun()
            else:
                if st.button("▶️ Run Full Pipeline"):
                    run_full_pipeline_via_service(current_job)

                if st.button("📋 View Status"):
                    _set_current_page("editor")
                    st.rerun()

        st.divider()
        st.caption("v0.1.0 | Streamlit UI")

    # Main content
    current_page = st.session_state.get("page", "dashboard")

    if current_page == "dashboard":
        render_dashboard()
    elif current_page == "editor":
        render_editor()
    elif current_page == "settings":
        render_settings()
    else:
        render_dashboard()


def render_settings() -> None:
    """Render settings page."""
    st.header("⚙️ Settings")

    config = get_config()

    # Paths
    with st.expander("📁 Paths", expanded=True):
        st.text_input("Jobs Directory", value=str(config.paths.jobs_dir), disabled=True)
        st.text_input("Models Cache", value=str(config.paths.models_cache), disabled=True)

    # Service
    with st.expander("🌐 Backend Service"):
        st.text_input("Service URL", value=config.service.base_url, disabled=True)
        st.text_input("Timeout (s)", value=str(config.service.timeout), disabled=True)
        if check_service_status():
            st.success("Status: Connected")
        else:
            st.error("Status: Offline - start with `podcast-pipeline service`")

    # AI Models
    with st.expander("🤖 AI Models"):
        st.text_input("Provider", value=config.models.provider, disabled=True)
        st.text_input("Model", value=config.models.model, disabled=True)
        st.text_input(
            "Fallback Provider", value=config.models.fallback_provider or "None", disabled=True
        )

    # Transcription
    with st.expander("🎤 Transcription"):
        st.text_input("Whisper Model", value=config.transcription.model, disabled=True)
        st.text_input("Device", value=config.transcription.device, disabled=True)

    # API Keys status
    with st.expander("🔑 API Keys"):
        st.markdown("**Status:**")
        st.markdown(f"- Gemini: {'✅ Configured' if config.api_keys.gemini else '❌ Not set'}")
        st.markdown(f"- Kimi: {'✅ Configured' if config.api_keys.kimi else '❌ Not set'}")
        st.markdown(f"- YouTube: {'✅ Configured' if config.api_keys.youtube else '❌ Not set'}")

        st.info("API keys are configured via environment variables or .env file")

    st.divider()
    st.caption("Configuration is loaded from config.yaml and environment variables")


if __name__ == "__main__":
    main()
