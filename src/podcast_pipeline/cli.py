"""Command-line interface for podcast-pipeline."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from podcast_pipeline import __version__
from podcast_pipeline.config import load_config
from podcast_pipeline.export_targets import (
    DEFAULT_EXPORT_PLATFORMS,
    SUPPORTED_EXPORT_PLATFORMS,
    normalize_export_platforms,
)
from podcast_pipeline.models.job import StageStatus
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.stages.review import approve_review, get_review_summary
from podcast_pipeline.utils.logging import setup_logging

app = typer.Typer(
    name="podcast-pipeline",
    help="AI-powered podcast production pipeline for multi-platform content.",
    add_completion=True,
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"podcast-pipeline version {__version__}")
        raise typer.Exit()


def _parse_approve_platforms(platforms: str | None) -> list[str]:
    """Parse and validate approve-platform input against canonical supported keys."""
    if platforms is None:
        return list(DEFAULT_EXPORT_PLATFORMS)

    raw_platforms = [part.strip() for part in platforms.split(",")]
    normalized, invalid = normalize_export_platforms(
        raw_platforms,
        fallback_to_default=False,
        include_invalid=True,
    )
    supported = ", ".join(SUPPORTED_EXPORT_PLATFORMS)
    if invalid:
        invalid_text = ", ".join(invalid)
        raise ValueError(
            f"Unsupported platform key(s): {invalid_text}. Supported keys: {supported}"
        )
    if not normalized:
        raise ValueError(
            f"No valid platform keys provided in --platforms. Supported keys: {supported}"
        )
    return normalized


@app.callback()
def main(
    _version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Enable verbose logging.",
    ),
) -> None:
    """Podcast Pipeline - Transform raw recordings into multi-platform content."""
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level=log_level)


@app.command()
def new(
    video_path: str = typer.Argument(..., help="Path to the input video file"),
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Custom name for the job (defaults to video filename)",
    ),
) -> None:
    """Create a new job from a video file."""
    video = Path(video_path)
    if not video.exists():
        console.print(f"[red]Error:[/red] File not found: {video_path}")
        raise typer.Exit(1)

    config = load_config()
    pipeline = Pipeline(config)

    try:
        job = pipeline.create_job(video, name)
        console.print(
            Panel(
                f"[green]Job created successfully![/green]\n\n"
                f"Job ID: [cyan]{job.job_id}[/cyan]\n"
                f"Input: {job.input_file}\n\n"
                f"Next steps:\n"
                f"  1. Run: [cyan]podcast-pipeline run {job.job_id}[/cyan]\n"
                f"  2. Review: [cyan]podcast-pipeline review {job.job_id}[/cyan]\n"
                f"  3. Check status: [cyan]podcast-pipeline status {job.job_id}[/cyan]",
                title="New Job",
            )
        )
    except Exception as e:
        console.print(f"[red]Error creating job:[/red] {e}")
        raise typer.Exit(1) from None


@app.command()
def status(
    job_id: str | None = typer.Argument(None, help="Job ID to check (or list all if omitted)"),
) -> None:
    """Check the status of a job or list all jobs."""
    config = load_config()
    pipeline = Pipeline(config)

    if job_id is None:
        # List all jobs
        jobs = pipeline.list_jobs()
        if not jobs:
            console.print("[yellow]No jobs found.[/yellow]")
            return

        table = Table(title="Jobs")
        table.add_column("Job ID", style="cyan")
        table.add_column("Status")
        table.add_column("Created")
        table.add_column("Stages")

        for job_info in jobs:
            status_color = {
                "complete": "green",
                "running": "blue",
                "waiting": "yellow",
                "failed": "red",
            }.get(job_info["status"], "white")

            # Build stages string with colors
            stage_parts = []
            status_colors = {
                "complete": "green",
                "running": "blue",
                "waiting": "yellow",
                "failed": "red",
            }
            for n, s in job_info["stages"].items():
                color = status_colors.get(s, "white")
                stage_parts.append(f"[{color}]{n}[/]")
            stages_str = " → ".join(stage_parts)

            table.add_row(
                job_info["job_id"],
                f"[{status_color}]{job_info['status']}[/]",
                job_info["created"][:10],
                stages_str[:60],
            )

        console.print(table)
    else:
        # Show specific job
        try:
            job = pipeline.load_job(job_id)
        except FileNotFoundError:
            console.print(f"[red]Job not found:[/red] {job_id}")
            raise typer.Exit(1) from None

        table = Table(title=f"Job: {job.job_id}")
        table.add_column("Stage")
        table.add_column("Status")
        table.add_column("Started")
        table.add_column("Completed")
        table.add_column("Outputs")

        for stage_name in ["ingest", "transcribe", "analyze", "review", "render"]:
            stage = job.stages.get(stage_name)
            if not stage:
                continue

            status_color = {
                StageStatus.COMPLETE: "green",
                StageStatus.RUNNING: "blue",
                StageStatus.WAITING: "yellow",
                StageStatus.FAILED: "red",
                StageStatus.PENDING: "dim",
            }.get(stage.status, "white")

            table.add_row(
                stage_name,
                f"[{status_color}]{stage.status.value}[/]",
                stage.started_at.strftime("%H:%M:%S") if stage.started_at else "-",
                stage.completed_at.strftime("%H:%M:%S") if stage.completed_at else "-",
                ", ".join(stage.outputs[:2]) + ("..." if len(stage.outputs) > 2 else ""),
            )

        console.print(table)

        if job.error:
            console.print(f"\n[red]Error:[/red] {job.error}")


@app.command()
def run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    stage: str | None = typer.Option(
        None,
        "--stage",
        "-s",
        help="Specific stage to run (ingest, transcribe, analyze, review, render)",
    ),
    until: str | None = typer.Option(
        None,
        "--until",
        "-u",
        help="Run all stages up to and including this one",
    ),
) -> None:
    """Run pipeline stages for a job."""
    config = load_config()
    pipeline = Pipeline(config)

    try:
        job = pipeline.load_job(job_id)
    except FileNotFoundError:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1) from None

    console.print(f"[blue]Running pipeline for job:[/blue] {job_id}")
    if stage:
        console.print(f"[blue]Stage:[/blue] {stage}")
    elif until:
        console.print(f"[blue]Running until:[/blue] {until}")

    try:
        results = pipeline.run(job, stage=stage, until_stage=until)

        # Show results
        for stage_name, result in results.items():
            if result.success:
                console.print(f"  [green]✓[/green] {stage_name}: complete")
                for output in result.outputs:
                    console.print(f"    → {output}")
            else:
                console.print(f"  [red]✗[/red] {stage_name}: {result.error}")

        # Check if waiting for review
        review_result = results.get("review")
        if review_result and review_result.data.get("status") == "waiting_for_review":
            console.print(
                "\n[yellow]Pipeline paused for review.[/yellow]\n"
                f"Run: [cyan]podcast-pipeline review {job_id}[/cyan] to view and approve\n"
                f"Or: [cyan]podcast-pipeline approve {job_id}[/cyan] to auto-approve all"
            )

    except Exception as e:
        console.print(f"[red]Pipeline error:[/red] {e}")
        raise typer.Exit(1) from None


@app.command()
def review(
    job_id: str = typer.Argument(..., help="Job ID to review"),
) -> None:
    """View content for review and show summary."""
    config = load_config()
    pipeline = Pipeline(config)

    try:
        job = pipeline.load_job(job_id)
    except FileNotFoundError:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1) from None

    job_dir = job.get_job_dir(config.paths.jobs_dir)
    summary = get_review_summary(job_dir)

    # Show transcript summary
    if "transcript" in summary:
        t = summary["transcript"]
        console.print(
            Panel(
                f"Duration: {t['duration']:.1f}s | Language: {t['language']}\n\n"
                f"{t['text'][:500]}...",
                title="Transcript Preview",
            )
        )

    # Show filler cuts
    if summary.get("filler_cuts"):
        console.print(f"\n[bold]Filler Words Detected:[/bold] {len(summary['filler_cuts'])}")
        for f in summary["filler_cuts"][:5]:
            console.print(f'  [{f["index"]}] "{f["word"]}" at {f["start"]} - {f["end"]}')
        if len(summary["filler_cuts"]) > 5:
            console.print(f"  ... and {len(summary['filler_cuts']) - 5} more")

    # Show content cuts
    if summary.get("content_cuts"):
        console.print("\n[bold]Suggested Content Cuts:[/bold]")
        for c in summary["content_cuts"]:
            console.print(f"  [{c['index']}] {c['start']} - {c['end']}: {c['reason']}")

    # Show viral clips
    if summary.get("viral_clips"):
        console.print("\n[bold]Viral Clip Candidates:[/bold]")
        for c in summary["viral_clips"]:
            console.print(
                f"  [{c['index']}] {c['start']} - {c['end']} (score: {c['score']}/10)\n"
                f"       {c['description']}\n"
                f'       Hook: "{c["hook"]}"'
            )

    # Show thumbnails
    if summary.get("thumbnails"):
        console.print("\n[bold]Thumbnail Candidates:[/bold]")
        for t in summary["thumbnails"]:
            console.print(
                f'  [{t["index"]}] {t["timestamp"]}: {t["description"]}\n       Text: "{t["text"]}"'
            )

    # Show marketing
    if summary.get("marketing"):
        yt = summary["marketing"].get("youtube", {})
        if yt.get("titles"):
            console.print("\n[bold]YouTube Title Suggestions:[/bold]")
            for i, title in enumerate(yt["titles"], 1):
                console.print(f"  {i}. {title}")

    # Show current decisions
    if summary.get("decisions"):
        d = summary["decisions"]
        console.print(
            f"\n[bold]Current Review State:[/bold]\n"
            f"  Complete: {'Yes' if d.get('review_complete') else 'No'}\n"
            f"  Platforms: {', '.join(d.get('export_platforms', []))}"
        )

    console.print(
        f"\n[dim]To approve all suggestions: podcast-pipeline approve {job_id}[/dim]\n"
        f"[dim]To continue with render: podcast-pipeline run {job_id} --stage render[/dim]"
    )


@app.command()
def approve(
    job_id: str = typer.Argument(..., help="Job ID to approve"),
    platforms: str | None = typer.Option(
        None,
        "--platforms",
        "-p",
        help="Comma-separated list of platforms to export",
    ),
) -> None:
    """Auto-approve all AI suggestions and mark review as complete."""
    try:
        platform_list = _parse_approve_platforms(platforms)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    config = load_config()
    pipeline = Pipeline(config)

    try:
        job = pipeline.load_job(job_id)
    except FileNotFoundError:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1) from None

    job_dir = job.get_job_dir(config.paths.jobs_dir)
    decisions = approve_review(job_dir, platform_list)

    console.print(
        Panel(
            f"[green]Review approved![/green]\n\n"
            f"Approved filler cuts: {len(decisions.approved_filler_cuts)}\n"
            f"Approved content cuts: {len(decisions.approved_content_cuts)}\n"
            f"Selected clips: {len(decisions.selected_clips)}\n"
            f"Selected thumbnail: {decisions.selected_thumbnail}\n"
            f"Export platforms: {', '.join(decisions.export_platforms)}\n\n"
            f"Run: [cyan]podcast-pipeline run {job_id}[/cyan] to continue",
            title="Review Approved",
        )
    )


@app.command(name="list")
def list_jobs() -> None:
    """List all jobs."""
    # Alias for `status` without arguments
    status(None)


@app.command()
def ui(
    port: int = typer.Option(8501, "--port", "-p", help="Port to run the Streamlit server on"),
    host: str = typer.Option("localhost", "--host", "-h", help="Host to bind the server to"),
) -> None:
    """Launch the Streamlit web UI."""
    import subprocess
    import sys
    from pathlib import Path

    # Find the app.py file
    ui_app_path = Path(__file__).parent / "ui" / "app.py"

    if not ui_app_path.exists():
        console.print(f"[red]Error:[/red] UI app not found at {ui_app_path}")
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[green]Starting Podcast Pipeline UI[/green]\n\n"
            f"URL: [cyan]http://{host}:{port}[/cyan]\n\n"
            f"Press Ctrl+C to stop the server.",
            title="🎙️ Podcast Pipeline UI",
        )
    )

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ui_app_path),
                "--server.port",
                str(port),
                "--server.address",
                host,
                "--server.headless",
                "true",
            ],
            check=True,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]UI server stopped.[/yellow]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error starting UI:[/red] {e}")
        raise typer.Exit(1) from None


@app.command()
def service(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind the server to"),
    port: int = typer.Option(8787, "--port", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
) -> None:
    """Start the FastAPI backend service (sidecar-compatible).

    Launches the local API server that both the Streamlit UI and the
    desktop Tauri shell can connect to. Suitable for headless /
    non-interactive startup (e.g. as a sidecar process).
    """
    import uvicorn

    console.print(
        Panel(
            f"[green]Starting Podcast Pipeline Service[/green]\n\n"
            f"URL: [cyan]http://{host}:{port}[/cyan]\n"
            f"Docs: [cyan]http://{host}:{port}/docs[/cyan]\n\n"
            f"Press Ctrl+C to stop the server.",
            title="Podcast Pipeline Service",
        )
    )

    uvicorn.run(
        "podcast_pipeline.service.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


if __name__ == "__main__":
    app()
