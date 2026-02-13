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

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
import hmac
import os
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from podcast_pipeline import __version__
from podcast_pipeline.config import Config, load_config
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.recovery import periodic_reconcile, startup_reconcile
from podcast_pipeline.service.schemas import HealthResponse
from podcast_pipeline.service.supervisor import Supervisor
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# Default service configuration
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
SERVICE_ENVIRONMENT_ENV_VAR = "PODCAST_PIPELINE_SERVICE_ENV"
SERVICE_API_KEY_ENV_VAR = "PODCAST_PIPELINE_SERVICE_API_KEY"
SERVICE_DEV_AUTH_BYPASS_ENV_VAR = "PODCAST_PIPELINE_SERVICE_ALLOW_UNAUTHENTICATED_DEV"
SERVICE_RECONCILE_INTERVAL_ENV_VAR = "PODCAST_PIPELINE_SERVICE_RECONCILE_INTERVAL_SECONDS"
SERVICE_API_KEY_HEADER_NAME = "X-API-Key"
DEFAULT_RECONCILE_INTERVAL_SECONDS = 30.0


def _parse_bool_env(raw: str | None, *, default: bool) -> bool:
    """Parse permissive boolean environment values with a fallback default."""
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_positive_float_env(raw: str | None, *, default: float) -> float:
    """Parse positive float environment values with fallback default."""
    if raw is None:
        return default
    value = float(raw.strip())
    if value <= 0:
        raise ValueError("Expected a positive float value")
    return value


@dataclass(frozen=True)
class ServiceAuthPolicy:
    """Runtime auth policy loaded at app startup.

    Behavior:
    - ``production`` always enforces an API key.
    - ``development`` can bypass auth when
      ``PODCAST_PIPELINE_SERVICE_ALLOW_UNAUTHENTICATED_DEV=true``.
    """

    environment: str
    api_key: str | None
    allow_unauthenticated_dev: bool

    @property
    def auth_required(self) -> bool:
        """Return True when requests must provide an API key."""
        if self.environment == "production":
            return True
        return self.api_key is not None and not self.allow_unauthenticated_dev


def _load_service_auth_policy() -> ServiceAuthPolicy:
    """Load auth policy from environment variables."""
    environment = os.getenv(SERVICE_ENVIRONMENT_ENV_VAR, "development").strip().lower()
    if environment not in {"development", "production"}:
        raise RuntimeError(
            f"Unsupported {SERVICE_ENVIRONMENT_ENV_VAR} value: {environment}. "
            "Expected 'development' or 'production'."
        )

    raw_api_key = os.getenv(SERVICE_API_KEY_ENV_VAR)
    api_key = raw_api_key.strip() if raw_api_key and raw_api_key.strip() else None
    allow_unauthenticated_dev = _parse_bool_env(
        os.getenv(SERVICE_DEV_AUTH_BYPASS_ENV_VAR),
        default=True,
    )

    if environment == "production" and api_key is None:
        raise RuntimeError(
            "Production mode requires PODCAST_PIPELINE_SERVICE_API_KEY to be set."
        )

    return ServiceAuthPolicy(
        environment=environment,
        api_key=api_key,
        allow_unauthenticated_dev=allow_unauthenticated_dev,
    )


async def require_service_auth(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias=SERVICE_API_KEY_HEADER_NAME)] = None,
) -> None:
    """Enforce service auth policy for job-control endpoints."""
    policy: ServiceAuthPolicy = request.app.state.service_auth_policy
    if not policy.auth_required:
        return

    if policy.api_key is None:
        logger.error("service_auth_misconfigured", environment=policy.environment)
        raise HTTPException(status_code=503, detail="Service authentication is misconfigured")
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not hmac.compare_digest(x_api_key, policy.api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")


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
    app.state.service_auth_policy = _load_service_auth_policy()
    reconcile_interval_seconds = _parse_positive_float_env(
        os.getenv(SERVICE_RECONCILE_INTERVAL_ENV_VAR),
        default=DEFAULT_RECONCILE_INTERVAL_SECONDS,
    )
    app.state.reconcile_interval_seconds = reconcile_interval_seconds
    startup_reconcile(config.paths.jobs_dir)
    app.state.reconcile_task = asyncio.create_task(
        periodic_reconcile(
            config.paths.jobs_dir,
            interval_seconds=reconcile_interval_seconds,
        )
    )
    logger.info(
        "service_started",
        version=__version__,
        environment=app.state.service_auth_policy.environment,
        auth_required=app.state.service_auth_policy.auth_required,
        reconcile_interval_seconds=reconcile_interval_seconds,
    )
    yield
    reconcile_task = app.state.reconcile_task
    reconcile_task.cancel()
    with suppress(asyncio.CancelledError):
        await reconcile_task
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

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """Return structured HTTP errors and sanitize 5xx details."""
        if exc.status_code < 500:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "Internal server error",
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Sanitize unhandled server exceptions for API clients."""
        logger.exception(
            "service_unhandled_exception",
            method=request.method,
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "Internal server error",
                }
            },
        )

    # --- top-level routes ---
    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Return service health status."""
        return HealthResponse(status="ok")

    # --- job lifecycle routes ---
    app.include_router(
        jobs_router,
        prefix="/jobs",
        tags=["jobs"],
        dependencies=[Depends(require_service_auth)],
    )

    # --- system / asset readiness routes ---
    app.include_router(system_router, prefix="/system", tags=["system"])

    return app
