"""Streamlit UI for Podcast Pipeline - Complete Web Interface.

Job lifecycle operations (create, run, list, status) are routed through
the backend service via ``ServiceClient``.  Display-only operations that
read local analysis/review files continue to access the filesystem
directly, since both the service and Streamlit share the same ``jobs/``
directory on the local machine.
"""

import contextlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from podcast_pipeline.clients.service_client import (
    ServiceClient,
    ServiceError,
    ServiceUnavailableError,
)
from podcast_pipeline.config import Config, load_config
from podcast_pipeline.stages.review import (
    ReviewDecisions,
    approve_review,
    write_edit_plan,
)

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


def format_timestamp(ts: datetime | None) -> str:
    """Format timestamp for display."""
    if ts is None:
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M")


def status_badge(status: str) -> str:
    """Generate colored status badge."""
    colors = {
        "complete": "🟢",
        "running": "🔵",
        "waiting": "🟡",
        "failed": "🔴",
        "pending": "⚪",
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
def render_resumable_jobs() -> None:
    """Show resumable jobs banner if any interrupted jobs exist."""
    client = get_service_client()
    try:
        resumable = client.list_resumable_jobs()
    except ServiceError:
        return

    if not resumable.jobs:
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
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            with col1:
                st.markdown(f"**{job_info['job_id']}**")
            with col2:
                st.markdown(status_badge(job_info["status"]))
            with col3:
                st.markdown(f"📅 {job_info['created'][:10]}")
            with col4:
                if st.button("Open", key=f"open_{job_info['job_id']}"):
                    st.session_state.current_job_id = job_info["job_id"]
                    st.session_state.page = "editor"
                    st.rerun()
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

        # Generate job ID
        from datetime import UTC, datetime

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        name_part = job_name or uploaded_file.name.rsplit(".", 1)[0]
        job_id = f"{name_part}_{timestamp}"

        # Create job directory and save video
        job_dir = jobs_dir / job_id
        input_dir = job_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        # Save uploaded file
        ext = Path(uploaded_file.name).suffix
        video_path = input_dir / f"raw{ext}"
        with open(video_path, "wb") as f:
            f.write(uploaded_file.read())

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


# ============================================================================
# Editor Page
# ============================================================================
def render_editor() -> None:
    """Render the main editor interface."""
    job_id = st.session_state.get("current_job_id")

    if not job_id:
        st.warning("No job selected. Return to dashboard to select a job.")
        if st.button("← Back to Dashboard"):
            st.session_state.page = "dashboard"
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
        st.error(f"Job not found: {job_id}")
        return

    # Header
    col1, col2 = st.columns([4, 1])
    with col1:
        st.header(f"🎬 {job_id}")
    with col2:
        if st.button("← Dashboard"):
            st.session_state.page = "dashboard"
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
        metadata_path = job_dir / "input" / "metadata.json"
        duration = 0.0
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text())
                duration = float(metadata.get("duration", 0))
            except Exception:
                pass

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


def render_timeline_editor(job_id: str, job_dir: Path) -> None:
    """Render visual cut editor with timeline markers."""
    st.subheader("Timeline Editor")

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

    # Content Cuts Section
    st.markdown("#### Content Cuts")
    content_cuts = analysis.get("content_cuts", [])

    if not content_cuts:
        st.info("No content cuts suggested.")
    else:
        approved_cuts = decisions.approved_content_cuts if decisions else []

        for i, cut in enumerate(content_cuts):
            with st.container():
                col1, col2, col3, col4 = st.columns([1, 3, 2, 1])
                with col1:
                    is_approved = i in approved_cuts
                    if st.checkbox(
                        "✓",
                        value=is_approved,
                        key=f"cut_approve_{i}",
                        label_visibility="collapsed",
                    ):
                        if i not in approved_cuts:
                            approved_cuts.append(i)
                    elif i in approved_cuts:
                        approved_cuts.remove(i)
                with col2:
                    st.markdown(f"**{cut.get('start', '')} - {cut.get('end', '')}**")
                with col3:
                    st.caption(cut.get("reason", ""))
                with col4:
                    st.caption(f"Cut #{i + 1}")

    st.divider()

    # Filler Words Section
    st.markdown("#### Filler Words")
    transcript_path = job_dir / "analysis" / "transcript.json"

    if transcript_path.exists():
        try:
            transcript = json.loads(transcript_path.read_text())
            fillers = transcript.get("filler_words", [])

            if not fillers:
                st.success("No filler words detected!")
            else:
                st.info(f"Found {len(fillers)} filler words")

                # Show summary of fillers
                with st.expander(f"View {len(fillers)} filler words"):
                    approved_fillers = (
                        decisions.approved_filler_cuts if decisions else list(range(len(fillers)))
                    )

                    select_all = st.checkbox(
                        "Select All Fillers",
                        value=len(approved_fillers) == len(fillers),
                        key="select_all_fillers",
                    )

                    if select_all:
                        approved_fillers = list(range(len(fillers)))

                    for j, filler in enumerate(fillers[:50]):  # Show first 50
                        col1, col2, col3 = st.columns([1, 2, 2])
                        with col1:
                            st.checkbox(
                                "✓",
                                value=j in approved_fillers,
                                key=f"filler_{j}",
                                label_visibility="collapsed",
                            )
                        with col2:
                            st.caption(f'"{filler.get("word", "")}"')
                        with col3:
                            st.caption(f"{filler.get('start', '')}")

                    if len(fillers) > 50:
                        st.caption(f"... and {len(fillers) - 50} more")
        except Exception as e:
            st.error(f"Failed to load transcript: {e}")

    # Save changes button
    if st.button("💾 Save Timeline Changes", key="save_timeline"):
        save_review_decisions(job_dir, decisions)
        st.success("Timeline changes saved!")


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

    # Load current selection
    review_path = job_dir / "review" / "review_state.json"
    selected_idx = 0
    if review_path.exists():
        try:
            decisions = ReviewDecisions.model_validate_json(review_path.read_text())
            selected_idx = decisions.selected_thumbnail or 0
        except Exception:
            pass

    # Display thumbnail grid
    st.markdown("**Select a thumbnail frame:**")

    cols_per_row = 3
    for row_start in range(0, len(thumbnails), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, thumb_idx in enumerate(
            range(row_start, min(row_start + cols_per_row, len(thumbnails)))
        ):
            thumb = thumbnails[thumb_idx]
            with cols[col_idx]:
                # Thumbnail card
                is_selected = thumb_idx == selected_idx
                border_style = (
                    "border: 3px solid #00ff00;" if is_selected else "border: 1px solid #ccc;"
                )

                st.markdown(
                    f"""
                    <div style="padding: 10px; {border_style} border-radius: 8px; margin: 5px;">
                        <p><strong>⏱️ {thumb.get("timestamp", "N/A")}</strong></p>
                        <p style="font-size: 0.9em;">{thumb.get("visual_description", "")[:100]}...</p>
                        <p style="font-size: 0.8em; color: #666;">💬 "{thumb.get("suggested_text_overlay", "")}"</p>
                        <p style="font-size: 0.8em;">😊 {thumb.get("emotion", "neutral")}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button(
                    "✓ Select" if not is_selected else "✓ Selected",
                    key=f"thumb_select_{thumb_idx}",
                    disabled=is_selected,
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

    marketing = analysis.get("marketing", {})
    metadata = analysis.get("metadata", {})

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
            value=", ".join(metadata.get("topics", [])),
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
    platforms = [
        ("YouTube", "youtube", "🎥"),
        ("Spotify", "spotify", "🎧"),
        ("TikTok", "tiktok", "📱"),
        ("Instagram", "instagram", "📷"),
        ("LinkedIn", "linkedin", "💼"),
        ("Twitter/X", "twitter", "🐦"),
        ("Facebook", "facebook", "📘"),
    ]

    edited_marketing: dict[str, Any] = {}

    for platform_name, platform_key, icon in platforms:
        platform_data = marketing.get(platform_key, {})

        with st.expander(f"{icon} {platform_name}", expanded=(platform_key == "youtube")):
            # Titles (for platforms that support multiple)
            if platform_key in ["youtube"]:
                titles = platform_data.get("titles", [])
                st.markdown("**Title Options:**")
                edited_titles = []
                for i, title in enumerate(titles[:5]):
                    edited_title = st.text_input(
                        f"Title {i + 1}",
                        value=title,
                        key=f"{platform_key}_title_{i}",
                    )
                    edited_titles.append(edited_title)
                edited_marketing[platform_key] = {"titles": edited_titles}

            # Description
            description = platform_data.get("description", "")
            max_chars = {
                "youtube": 5000,
                "tiktok": 150,
                "instagram": 2200,
                "twitter": 280,
                "linkedin": 3000,
                "facebook": 63206,
                "spotify": 4000,
            }.get(platform_key, 2000)

            edited_desc = st.text_area(
                "Description",
                value=description,
                height=150 if platform_key in ["youtube", "linkedin"] else 80,
                max_chars=max_chars,
                key=f"{platform_key}_desc",
            )
            st.caption(f"{len(edited_desc)}/{max_chars} characters")

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
            # Update analysis file with edited marketing
            analysis["marketing"] = {**marketing, **edited_marketing}
            analysis["metadata"]["summary"] = summary
            analysis["metadata"]["topics"] = [t.strip() for t in topics.split(",")]
            analysis["metadata"]["mood"] = mood

            analysis_path.write_text(json.dumps(analysis, indent=2))
            st.success("Marketing copy saved!")

    with col2:
        if st.button("🔄 Regenerate Marketing Copy", key="regen_marketing"):
            st.info("Regenerating marketing copy... (This would call AI in production)")


def render_export_panel(job_id: str, job_dir: Path) -> None:
    """Render export configuration and execution panel."""
    st.subheader("Export Configuration")

    get_config()

    # Platform selection
    st.markdown("**Select Export Platforms:**")

    available_platforms = [
        ("YouTube", "youtube", "🎥 Video (1920x1080)"),
        ("Spotify", "spotify", "🎧 Audio (MP3 320kbps)"),
        ("Apple Podcasts", "apple", "🎧 Audio (AAC 128kbps)"),
        ("TikTok", "tiktok", "📱 Vertical (1080x1920, 60s max)"),
        ("Instagram Reels", "instagram", "📷 Vertical (1080x1920, 90s max)"),
        ("LinkedIn", "linkedin", "💼 Square/Landscape (1080x1080)"),
        ("Twitter/X", "twitter", "🐦 Landscape (1280x720, 2:20 max)"),
        ("Facebook", "facebook", "📘 Landscape (1920x1080)"),
    ]

    # Load existing selections
    review_path = job_dir / "review" / "review_state.json"
    selected_platforms = ["youtube", "spotify"]
    if review_path.exists():
        try:
            decisions = ReviewDecisions.model_validate_json(review_path.read_text())
            selected_platforms = decisions.export_platforms or ["youtube", "spotify"]
        except Exception:
            pass

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

    st.divider()

    # Quality settings
    st.markdown("**Quality Settings:**")
    col1, col2 = st.columns(2)

    with col1:
        st.select_slider(
            "Video Quality",
            options=["draft", "standard", "high", "ultra"],
            value="standard",
            key="video_quality",
        )

    with col2:
        st.checkbox(
            "Normalize Audio Loudness",
            value=True,
            key="audio_normalize",
        )

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
                update_export_platforms(job_dir, new_selected)
                # Mark review complete
                approve_review(job_dir, new_selected)
                # Run render via service
                run_stage_via_service(job_id, "render")
        elif st.button("🎬 Export Now", key="export_now"):
            update_export_platforms(job_dir, new_selected)
            run_stage_via_service(job_id, "render")

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
def run_stage_via_service(job_id: str, stage_name: str) -> None:
    """Run a pipeline stage through the backend service."""
    client = get_service_client()

    with st.spinner(f"Running {stage_name} stage..."):
        try:
            result = client.run_job(job_id, stage=stage_name)
            if result.status == "complete":
                st.success(f"{stage_name.title()} stage completed!")
                st.rerun()
            else:
                st.error(f"{stage_name.title()} failed: {result.message}")
        except ServiceUnavailableError:
            st.error("Backend service is not running. Start it with: `podcast-pipeline service`")
        except ServiceError as exc:
            st.error(f"Error running {stage_name}: {exc}")


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
    """Update selected thumbnail in review state."""
    review_dir = job_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    review_path = review_dir / "review_state.json"

    if review_path.exists():
        decisions = ReviewDecisions.model_validate_json(review_path.read_text())
    else:
        decisions = ReviewDecisions()

    decisions.selected_thumbnail = thumbnail_idx
    review_path.write_text(decisions.model_dump_json(indent=2))


def update_export_platforms(job_dir: Path, platforms: list[str]) -> None:
    """Update selected export platforms."""
    review_dir = job_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    review_path = review_dir / "review_state.json"

    if review_path.exists():
        decisions = ReviewDecisions.model_validate_json(review_path.read_text())
    else:
        decisions = ReviewDecisions()

    decisions.export_platforms = platforms
    review_path.write_text(decisions.model_dump_json(indent=2))


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
        page = st.radio(
            "Navigation",
            ["📊 Dashboard", "🎬 Editor", "⚙️ Settings"],
            key="nav_radio",
            label_visibility="collapsed",
        )

        # Update page state
        if "📊 Dashboard" in page:
            st.session_state.page = "dashboard"
        elif "🎬 Editor" in page:
            st.session_state.page = "editor"
        elif "⚙️ Settings" in page:
            st.session_state.page = "settings"

        st.divider()

        # Quick actions
        st.markdown("**Quick Actions**")

        current_job = st.session_state.get("current_job_id")
        if current_job:
            st.caption(f"Current: {current_job[:20]}...")

            if st.button("▶️ Run Full Pipeline"):
                run_stage_via_service(current_job, "ingest")

            if st.button("📋 View Status"):
                st.session_state.page = "editor"
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
