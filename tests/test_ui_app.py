"""Regression tests for Streamlit UI workflow helpers."""

import contextlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_ui_app_metadata_prefers_intermediate_path(tmp_path: Path) -> None:
    """Canonical ingest metadata should be loaded from intermediate/metadata.json."""
    from podcast_pipeline.ui.app import _load_ingest_metadata

    canonical = tmp_path / "intermediate" / "metadata.json"
    legacy = tmp_path / "input" / "metadata.json"
    _write_json(canonical, {"duration": 91.2, "source": "canonical"})
    _write_json(legacy, {"duration": 10.0, "source": "legacy"})

    loaded = _load_ingest_metadata(tmp_path)

    assert loaded is not None
    assert loaded["duration"] == 91.2
    assert loaded["source"] == "canonical"


def test_ui_app_metadata_legacy_fallback_is_logged(tmp_path: Path) -> None:
    """Legacy metadata path should still work but emit a fallback warning."""
    from podcast_pipeline.ui.app import _load_ingest_metadata

    legacy = tmp_path / "input" / "metadata.json"
    _write_json(legacy, {"duration": 33.0, "source": "legacy"})

    with patch("podcast_pipeline.ui.app.logger.warning") as warning:
        loaded = _load_ingest_metadata(tmp_path)

    assert loaded is not None
    assert loaded["source"] == "legacy"
    warning.assert_called_with(
        "ingest_metadata_legacy_fallback",
        path=str(legacy),
        canonical_exists=False,
    )


def test_ui_app_preview_metadata_duration_drives_slider(tmp_path: Path) -> None:
    """Preview scrubber range should use canonical ingest metadata duration."""
    from podcast_pipeline.ui.app import render_video_preview

    _write_json(tmp_path / "intermediate" / "metadata.json", {"duration": 47.5})
    proxy = tmp_path / "intermediate" / "proxy.mp4"
    proxy.parent.mkdir(parents=True, exist_ok=True)
    proxy.write_bytes(b"video")

    mock_st = MagicMock()
    mock_st.slider.return_value = 0.0

    with patch("podcast_pipeline.ui.app.st", mock_st):
        render_video_preview("job-123", tmp_path)

    assert mock_st.video.called
    assert mock_st.slider.call_args.kwargs["max_value"] == 47.5


def test_ui_app_timeline_reads_metadata_for_duration_caption(tmp_path: Path) -> None:
    """Timeline should surface source duration from ingest metadata."""
    from podcast_pipeline.ui.app import render_timeline_editor

    _write_json(tmp_path / "intermediate" / "metadata.json", {"duration": 120.0})
    _write_json(tmp_path / "analysis" / "analysis.json", {"content_cuts": []})

    mock_st = MagicMock()
    mock_st.session_state = {}
    mock_st.button.return_value = False
    mock_st.checkbox.return_value = False
    mock_st.number_input.return_value = 0.0
    mock_st.text_input.return_value = ""
    mock_st.columns.side_effect = lambda spec: [
        MagicMock() for _ in range(len(spec) if isinstance(spec, list) else int(spec))
    ]

    with patch("podcast_pipeline.ui.app.st", mock_st):
        render_timeline_editor("job-abc", tmp_path)

    mock_st.caption.assert_any_call("Source duration: 120.0s")


def test_ui_app_marketing_review_flow_save_writes_review_state_only(tmp_path: Path) -> None:
    """Saving marketing should persist through review artifacts, not analysis mutation."""
    from podcast_pipeline.stages.review import ReviewDecisions
    from podcast_pipeline.ui.app import _save_marketing_edits_to_review_flow

    analysis_path = tmp_path / "analysis" / "analysis.json"
    initial_analysis = {
        "marketing": {"youtube": {"description": "Original description", "hashtags": ["#old"]}},
        "metadata": {"summary": "Original summary", "topics": ["alpha"], "mood": "calm"},
        "content_cuts": [],
    }
    _write_json(analysis_path, initial_analysis)
    _write_json(tmp_path / "analysis" / "filler_cuts.json", [])

    _save_marketing_edits_to_review_flow(
        tmp_path,
        ReviewDecisions(),
        edited_marketing={"youtube": {"description": "Updated desc", "hashtags": ["#new"]}},
        summary="Updated summary",
        topics="topic-1, topic-2",
        mood="energetic",
    )

    loaded_analysis = json.loads(analysis_path.read_text())
    assert loaded_analysis["marketing"]["youtube"]["description"] == "Original description"

    review_state_path = tmp_path / "review" / "review_state.json"
    assert review_state_path.exists()
    review_state = ReviewDecisions.model_validate_json(review_state_path.read_text())
    assert review_state.marketing_edits["youtube"]["description"] == "Updated desc"
    assert review_state.marketing_edits["__metadata__"]["summary"] == "Updated summary"
    assert review_state.marketing_edits["__metadata__"]["topics"] == ["topic-1", "topic-2"]

    assert (tmp_path / "review" / "edit_plan.json").exists()


def test_ui_app_marketing_review_flow_regeneration_resets_review_state(tmp_path: Path) -> None:
    """Regeneration should clear marketing edits and require re-review."""
    from podcast_pipeline.stages.review import ReviewDecisions
    from podcast_pipeline.ui.app import _prepare_marketing_regeneration_review_state

    _write_json(
        tmp_path / "analysis" / "analysis.json",
        {"marketing": {}, "metadata": {}, "content_cuts": []},
    )
    _write_json(tmp_path / "analysis" / "filler_cuts.json", [])

    seeded = ReviewDecisions(
        review_complete=True,
        marketing_edits={
            "youtube": {"description": "edited"},
            "__metadata__": {"summary": "edited summary"},
        },
    )
    review_dir = tmp_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "review_state.json").write_text(seeded.model_dump_json(indent=2))

    _prepare_marketing_regeneration_review_state(tmp_path)

    updated = ReviewDecisions.model_validate_json((review_dir / "review_state.json").read_text())
    assert updated.review_complete is False
    assert updated.marketing_edits == {}


def test_ui_app_delete_job_clears_related_session_state() -> None:
    """Deleting a job clears current/timeline session state and reruns."""
    from podcast_pipeline.ui.app import delete_job_via_service

    fake_client = MagicMock()
    fake_client.delete_job.return_value = MagicMock(message="Deleted job job-abc")

    mock_st = MagicMock()
    mock_st.session_state = {
        "current_job_id": "job-abc",
        "timeline_rows_job-abc": [{"id": "row-1"}],
    }
    mock_st.spinner.return_value = contextlib.nullcontext()

    with (
        patch("podcast_pipeline.ui.app.get_service_client", return_value=fake_client),
        patch("podcast_pipeline.ui.app.st", mock_st),
    ):
        delete_job_via_service("job-abc")

    fake_client.delete_job.assert_called_once_with("job-abc")
    assert "current_job_id" not in mock_st.session_state
    assert "timeline_rows_job-abc" not in mock_st.session_state
    mock_st.success.assert_called_once_with("Deleted job job-abc")
    mock_st.rerun.assert_called_once()


def test_ui_app_delete_job_legacy_client_falls_back_to_http_delete() -> None:
    """Legacy cached client instances without delete_job should use HTTP fallback."""
    from podcast_pipeline.ui.app import delete_job_via_service

    class _LegacyClient:
        pass

    mock_st = MagicMock()
    mock_st.session_state = {
        "current_job_id": "job-legacy",
        "timeline_rows_job-legacy": [{"id": "row-1"}],
    }
    mock_st.spinner.return_value = contextlib.nullcontext()

    config = SimpleNamespace(service=SimpleNamespace(base_url="http://testserver", timeout=7.0))
    response = httpx.Response(
        200,
        json={
            "job_id": "job-legacy",
            "deleted": True,
            "message": "Deleted job job-legacy",
        },
        request=httpx.Request("DELETE", "http://testserver/jobs/job-legacy"),
    )

    with (
        patch("podcast_pipeline.ui.app.get_service_client", return_value=_LegacyClient()),
        patch("podcast_pipeline.ui.app.get_config", return_value=config),
        patch("podcast_pipeline.ui.app.httpx.delete", return_value=response) as delete_call,
        patch("podcast_pipeline.ui.app.st", mock_st),
    ):
        delete_job_via_service("job-legacy")

    delete_call.assert_called_once_with("http://testserver/jobs/job-legacy", timeout=7.0)
    assert "current_job_id" not in mock_st.session_state
    assert "timeline_rows_job-legacy" not in mock_st.session_state
    mock_st.success.assert_called_once_with("Deleted job job-legacy")
    mock_st.rerun.assert_called_once()


def test_ui_app_set_current_page_marks_nav_sync_flag() -> None:
    """Page helper should mark sidebar sync for the next rerun."""
    from podcast_pipeline.ui.app import _set_current_page

    mock_st = MagicMock()
    mock_st.session_state = {}

    with patch("podcast_pipeline.ui.app.st", mock_st):
        _set_current_page("editor")

    assert mock_st.session_state["page"] == "editor"
    assert mock_st.session_state["_sync_nav_to_page"] is True
    assert "nav_radio" not in mock_st.session_state


def test_ui_app_sync_nav_with_page_realigns_stale_sidebar_selection() -> None:
    """Sidebar selection should be corrected when page state changed via button."""
    from podcast_pipeline.ui.app import _sync_nav_with_page

    mock_st = MagicMock()
    mock_st.session_state = {
        "page": "dashboard",
        "nav_radio": "🎬 Editor",
        "_sync_nav_to_page": True,
    }

    with patch("podcast_pipeline.ui.app.st", mock_st):
        _sync_nav_with_page()

    assert mock_st.session_state["nav_radio"] == "📊 Dashboard"
    assert mock_st.session_state["page"] == "dashboard"
    assert "_sync_nav_to_page" not in mock_st.session_state


def test_ui_app_timeline_edit_prefers_saved_edit_plan(tmp_path: Path) -> None:
    """Timeline rows should load from review/edit_plan.json when available."""
    from podcast_pipeline.stages.review import ReviewDecisions
    from podcast_pipeline.ui.app import _timeline_rows_from_artifacts

    _write_json(
        tmp_path / "analysis" / "analysis.json",
        {
            "content_cuts": [
                {
                    "start_seconds": 1.0,
                    "end_seconds": 2.0,
                    "reason": "analysis-cut",
                }
            ]
        },
    )
    _write_json(
        tmp_path / "review" / "edit_plan.json",
        {
            "content_cuts": [
                {
                    "start_seconds": 10.5,
                    "end_seconds": 12.25,
                    "reason": "saved-cut",
                }
            ]
        },
    )

    rows = _timeline_rows_from_artifacts(
        tmp_path,
        analysis={"content_cuts": []},
        decisions=ReviewDecisions(),
    )

    assert len(rows) == 1
    assert rows[0]["start_seconds"] == 10.5
    assert rows[0]["end_seconds"] == 12.25
    assert rows[0]["reason"] == "saved-cut"
    assert rows[0]["enabled"] is True


def test_ui_app_timeline_edit_validation_reports_overlap_and_bounds() -> None:
    """Timeline validation should reject overlaps and out-of-bounds ranges."""
    from podcast_pipeline.ui.app import _validate_timeline_rows

    errors = _validate_timeline_rows(
        [
            {"enabled": True, "start_seconds": 5.0, "end_seconds": 7.0, "reason": "A"},
            {"enabled": True, "start_seconds": 6.5, "end_seconds": 8.0, "reason": "B"},
            {"enabled": True, "start_seconds": 20.0, "end_seconds": 40.0, "reason": "C"},
        ],
        duration_seconds=30.0,
    )

    assert any("overlap" in error.lower() for error in errors)
    assert any("exceeds source duration" in error for error in errors)


def test_ui_app_review_state_timeline_save_writes_custom_edit_plan(tmp_path: Path) -> None:
    """Saving timeline edits should persist review state and custom edit plan ranges."""
    from podcast_pipeline.stages.review import ReviewDecisions
    from podcast_pipeline.ui.app import _persist_timeline_edit_plan

    _write_json(
        tmp_path / "analysis" / "analysis.json",
        {
            "content_cuts": [],
            "viral_clips": [],
            "thumbnail_frames": [],
        },
    )

    decisions = ReviewDecisions()
    timeline_rows = [
        {
            "id": "row-1",
            "enabled": True,
            "start_seconds": 12.0,
            "end_seconds": 18.5,
            "reason": "tighten intro",
        },
        {
            "id": "row-2",
            "enabled": False,
            "start_seconds": 30.0,
            "end_seconds": 35.0,
            "reason": "disabled cut",
        },
    ]

    _persist_timeline_edit_plan(
        tmp_path,
        decisions,
        analysis={"content_cuts": []},
        fillers=[],
        timeline_rows=timeline_rows,
    )

    review_state = ReviewDecisions.model_validate_json(
        (tmp_path / "review" / "review_state.json").read_text()
    )
    assert review_state.approved_content_cuts == [0]

    edit_plan = json.loads((tmp_path / "review" / "edit_plan.json").read_text())
    assert len(edit_plan["content_cuts"]) == 1
    assert edit_plan["content_cuts"][0]["start_seconds"] == 12.0
    assert edit_plan["content_cuts"][0]["end_seconds"] == 18.5


def test_ui_app_recovery_summary_normalizes_runtime_payload() -> None:
    """Recovery summary helper should normalize runtime diagnostics payloads."""
    from podcast_pipeline.ui.app import _runtime_recovery_summary

    summary = _runtime_recovery_summary(
        {
            "active_jobs": ["job-a", "job-b"],
            "stale_jobs": ["job-stale"],
            "orphaned_jobs": ["job-orphan"],
            "jobs": [
                {
                    "job_id": "job-stale",
                    "status": "interrupted",
                    "last_known_stage": "analyze",
                    "heartbeat_age_seconds": 88.5,
                    "stale": True,
                    "orphaned": False,
                }
            ],
        }
    )

    assert summary["available"] is True
    assert summary["active_runs"] == 2
    assert summary["stale_jobs"] == ["job-stale"]
    assert summary["orphaned_jobs"] == ["job-orphan"]
    assert summary["job_rows"][0]["Job"] == "job-stale"


def test_ui_app_reconcile_runtime_fetch_returns_none_on_http_error() -> None:
    """Runtime diagnostics fetch should fail closed and return None."""
    from podcast_pipeline.ui.app import _fetch_runtime_diagnostics

    with patch("podcast_pipeline.ui.app.httpx.get", side_effect=RuntimeError("boom")):
        payload = _fetch_runtime_diagnostics("http://127.0.0.1:8787", timeout_seconds=5.0)

    assert payload is None


def test_ui_app_export_platform_options_include_video_targets() -> None:
    """Export panel options should expose canonical audio/video/package targets."""
    from podcast_pipeline.ui.app import _export_platform_options

    options = _export_platform_options()
    keys = [key for _label, key, _help_text in options]

    assert "spotify_video" in keys
    assert "apple_video" in keys
    assert "apple_hls" in keys
    assert "youtube" in keys


def test_ui_app_export_boundary_guidance_mentions_apple_hls_artifact_only() -> None:
    """Export guidance should explicitly document apple_hls workflow boundaries."""
    from podcast_pipeline.ui.app import _export_boundary_guidance

    guidance = _export_boundary_guidance()
    assert "apple_hls" in guidance
    assert "artifacts" in guidance
    assert "no direct upload automation" in guidance


def test_ui_app_load_normalized_export_platforms_drops_invalid_saved_keys(
    tmp_path: Path,
) -> None:
    """Persisted invalid export keys should be dropped with diagnostics."""
    from podcast_pipeline.ui.app import _load_normalized_export_platforms

    review_path = tmp_path / "review" / "review_state.json"
    _write_json(
        review_path,
        {"export_platforms": [" youtube ", "spotify_video", "unknown", "spotify_video"]},
    )

    normalized, invalid = _load_normalized_export_platforms(review_path)

    assert normalized == ["youtube", "spotify_video"]
    assert invalid == ["unknown"]
