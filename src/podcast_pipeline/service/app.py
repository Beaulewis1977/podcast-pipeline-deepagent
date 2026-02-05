"""FastAPI application and lifespan wiring.

This module creates the single FastAPI application instance that both
the CLI ``service`` command and test harness use. Pipeline and config
are initialised once in the lifespan and shared across request handlers.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from podcast_pipeline.config import Config, load_config
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.schemas import HealthResponse
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise shared resources on startup, clean up on shutdown."""
    config: Config = load_config()
    pipeline = Pipeline(config)
    app.state.config = config
    app.state.pipeline = pipeline
    # Track active background runs: job_id -> asyncio.Task
    active_runs: dict[str, Any] = {}
    app.state.active_runs = active_runs
    logger.info("service_started")
    yield
    logger.info("service_stopped")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    from podcast_pipeline.service.routes.jobs import router as jobs_router

    app = FastAPI(
        title="Podcast Pipeline Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- top-level routes ---
    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    # --- job lifecycle routes ---
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])

    return app
