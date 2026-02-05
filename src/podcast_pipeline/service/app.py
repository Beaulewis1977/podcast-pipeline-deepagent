"""FastAPI application and lifespan wiring.

This module creates the single FastAPI application instance that both
the CLI ``service`` command and test harness use. Pipeline and config
are initialised once in the lifespan and shared across request handlers.

Usage::

    # Production (via CLI)
    podcast-pipeline service --host 127.0.0.1 --port 8787

    # Test harness
    from podcast_pipeline.service.app import create_app
    app = create_app()
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from podcast_pipeline import __version__
from podcast_pipeline.config import Config, load_config
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.schemas import HealthResponse
from podcast_pipeline.service.supervisor import Supervisor
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# Default service configuration
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise shared resources on startup, clean up on shutdown.

    Resources created here are available on ``request.app.state``:

    - ``config``: The loaded :class:`Config` instance
    - ``pipeline``: Shared :class:`Pipeline` orchestrator
    - ``supervisor``: :class:`Supervisor` for background run management
    """
    config: Config = load_config()
    pipeline = Pipeline(config)
    app.state.config = config
    app.state.pipeline = pipeline
    app.state.supervisor = Supervisor(pipeline)
    logger.info("service_started", version=__version__)
    yield
    logger.info("service_stopped")


def create_app() -> FastAPI:
    """Build and return the FastAPI application.

    The app is constructed with a factory pattern so that ``uvicorn``
    can instantiate it via ``podcast_pipeline.service.app:create_app``
    with the ``factory=True`` flag.
    """
    from podcast_pipeline.service.routes.jobs import router as jobs_router
    from podcast_pipeline.service.routes.system import router as system_router

    app = FastAPI(
        title="Podcast Pipeline Service",
        description="Local backend API for podcast pipeline job lifecycle",
        version=__version__,
        lifespan=lifespan,
    )

    # --- top-level routes ---
    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Return service health status."""
        return HealthResponse(status="ok")

    # --- job lifecycle routes ---
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])

    # --- system / asset readiness routes ---
    app.include_router(system_router, prefix="/system", tags=["system"])

    return app
