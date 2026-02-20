"""Tests for the CLI module."""

import re

import pytest
from typer.testing import CliRunner

from podcast_pipeline.cli import _parse_approve_platforms, app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_version():
    """Test that --version prints version info."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "podcast-pipeline version" in result.stdout


def test_help():
    """Test that --help shows usage info."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "podcast-pipeline" in result.stdout
    assert "AI-powered podcast production" in result.stdout


def test_new_command_requires_video():
    """Test that 'new' command requires video path argument."""
    result = runner.invoke(app, ["new"])
    assert result.exit_code != 0


def test_new_command_file_not_found():
    """Test 'new' command with non-existent video shows error."""
    result = runner.invoke(app, ["new", "nonexistent_video.mp4"])
    assert result.exit_code == 1
    assert "File not found" in result.output or "Error" in result.output


def test_status_no_jobs():
    """Test 'status' command with no jobs."""
    result = runner.invoke(app, ["status"])
    # Should show empty list or no jobs message
    assert result.exit_code == 0


def test_status_nonexistent_job():
    """Test 'status' command with non-existent job."""
    result = runner.invoke(app, ["status", "nonexistent-job-id"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_run_nonexistent_job():
    """Test 'run' command with non-existent job."""
    result = runner.invoke(app, ["run", "nonexistent-job-id"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_review_nonexistent_job():
    """Test 'review' command with non-existent job."""
    result = runner.invoke(app, ["review", "nonexistent-job-id"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_approve_nonexistent_job():
    """Test 'approve' command with non-existent job."""
    result = runner.invoke(app, ["approve", "nonexistent-job-id"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_list_command():
    """Test 'list' command (alias for status)."""
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0


def test_service_help() -> None:
    """Test 'service' command shows help with host/port options."""
    result = runner.invoke(app, ["service", "--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "--host" in output
    assert "--port" in output
    assert "sidecar" in output.lower() or "service" in output.lower()


def test_parse_approve_platforms_defaults_when_omitted() -> None:
    """Approve parser should keep backward-compatible default platforms."""
    assert _parse_approve_platforms(None) == ["youtube", "spotify"]


def test_parse_approve_platforms_accepts_video_targets() -> None:
    """Approve parser should normalize and keep valid video target keys."""
    parsed = _parse_approve_platforms(" spotify_video,apple_video, apple_hls ,spotify_video ")
    assert parsed == ["spotify_video", "apple_video", "apple_hls"]


def test_parse_approve_platforms_rejects_invalid_keys() -> None:
    """Approve parser should fail when explicit unsupported keys are provided."""
    with pytest.raises(ValueError, match="Unsupported platform key"):
        _parse_approve_platforms("youtube,invalid")


def test_parse_approve_platforms_rejects_empty_explicit_value() -> None:
    """Explicit --platforms with no usable keys should not silently fallback."""
    with pytest.raises(ValueError, match="No valid platform keys provided"):
        _parse_approve_platforms("  ,   , ")


def test_approve_command_rejects_invalid_platform_keys() -> None:
    """CLI approve command should fail fast with actionable invalid-key diagnostics."""
    result = runner.invoke(app, ["approve", "nonexistent-job-id", "--platforms", "youtube,invalid"])

    output = _strip_ansi(result.output)
    assert result.exit_code == 1
    assert "Unsupported platform key" in output
    assert "Supported keys:" in output
