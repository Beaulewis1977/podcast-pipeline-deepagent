"""Security and exception hardening tests for the FastAPI service."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from podcast_pipeline.config import Config
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.app import (
    SERVICE_API_KEY_ENV_VAR,
    SERVICE_DEV_AUTH_BYPASS_ENV_VAR,
    SERVICE_ENVIRONMENT_ENV_VAR,
    create_app,
)
from podcast_pipeline.service.supervisor import Supervisor


@pytest.fixture
def security_temp_dir() -> Generator[Path, None, None]:
    """Isolated temp directory used for service security tests."""
    tmp = Path(tempfile.mkdtemp())
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def _configure_service_state(app, temp_dir: Path) -> None:
    """Wire app state to an isolated jobs directory for deterministic tests."""
    config = Config()
    config.paths.jobs_dir = temp_dir / "jobs"
    config.paths.jobs_dir.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(config)
    app.state.config = config
    app.state.pipeline = pipeline
    app.state.supervisor = Supervisor(pipeline)


@pytest.fixture
def make_security_client(monkeypatch: pytest.MonkeyPatch, security_temp_dir: Path):
    """Factory yielding configured TestClient contexts with auth policy env."""

    @contextmanager
    def _factory(
        *,
        environment: str = "development",
        api_key: str | None = None,
        allow_unauthenticated_dev: bool = True,
        raise_server_exceptions: bool = True,
        configure_app: Callable[[Any], None] | None = None,
    ):
        monkeypatch.setenv(SERVICE_ENVIRONMENT_ENV_VAR, environment)
        monkeypatch.setenv(
            SERVICE_DEV_AUTH_BYPASS_ENV_VAR,
            "true" if allow_unauthenticated_dev else "false",
        )
        if api_key is None:
            monkeypatch.delenv(SERVICE_API_KEY_ENV_VAR, raising=False)
        else:
            monkeypatch.setenv(SERVICE_API_KEY_ENV_VAR, api_key)

        app = create_app()
        if configure_app is not None:
            configure_app(app)
        with TestClient(app, raise_server_exceptions=raise_server_exceptions) as client:
            _configure_service_state(app, security_temp_dir)
            yield client

    return _factory


def test_auth_rejects_missing_api_key_in_production_auth(make_security_client) -> None:
    """Production mode rejects unauthenticated job-control requests."""
    with make_security_client(environment="production", api_key="prod-secret-123") as client:
        response = client.get("/jobs")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_auth_rejects_invalid_api_key_in_production_auth(make_security_client) -> None:
    """Production mode rejects invalid API keys."""
    with make_security_client(environment="production", api_key="prod-secret-123") as client:
        response = client.get("/jobs", headers={"X-API-Key": "wrong-key"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key"


def test_auth_allows_valid_api_key_in_production_auth(make_security_client) -> None:
    """Production mode accepts the configured key for job-control endpoints."""
    with make_security_client(environment="production", api_key="prod-secret-123") as client:
        response = client.get("/jobs", headers={"X-API-Key": "prod-secret-123"})

    assert response.status_code == 200
    assert response.json() == {"jobs": []}


def test_auth_dev_override_allows_unauthenticated_requests(make_security_client) -> None:
    """Development mode can explicitly bypass auth for local iteration."""
    with make_security_client(
        environment="development",
        api_key="dev-key-123",
        allow_unauthenticated_dev=True,
    ) as client:
        response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {"jobs": []}


def test_auth_requires_key_when_dev_override_disabled(make_security_client) -> None:
    """Development mode can opt into auth by disabling the bypass flag."""
    with make_security_client(
        environment="development",
        api_key="dev-key-123",
        allow_unauthenticated_dev=False,
    ) as client:
        response = client.get("/jobs")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_exception_handler_sanitizes_unhandled_errors(make_security_client) -> None:
    """Unhandled exceptions return structured non-leaky 500 responses."""
    def _configure_route(app: Any) -> None:
        @app.get("/debug/unhandled")
        async def debug_unhandled() -> dict[str, str]:
            raise RuntimeError("secret traceback detail")

    with make_security_client(
        environment="development",
        raise_server_exceptions=False,
        configure_app=_configure_route,
    ) as client:
        response = client.get("/debug/unhandled")

    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"]["code"] == "internal_error"
    assert payload["detail"]["message"] == "Internal server error"
    assert "secret traceback detail" not in response.text


def test_exception_handler_sanitizes_http_500_details(make_security_client) -> None:
    """Raised HTTP 500 exceptions do not expose raw internal detail strings."""
    def _configure_route(app: Any) -> None:
        @app.get("/debug/http-error")
        async def debug_http_error() -> None:
            raise HTTPException(status_code=500, detail="do-not-leak-this")

    with make_security_client(
        environment="development",
        configure_app=_configure_route,
    ) as client:
        response = client.get("/debug/http-error")

    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"]["code"] == "internal_error"
    assert payload["detail"]["message"] == "Internal server error"
    assert "do-not-leak-this" not in response.text
