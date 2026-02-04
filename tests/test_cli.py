"""Tests for the CLI module."""

from typer.testing import CliRunner

from podcast_pipeline.cli import app

runner = CliRunner()


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
