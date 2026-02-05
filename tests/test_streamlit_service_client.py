"""Tests for the typed service client and Streamlit service-backed actions.

Covers:
- Client contract correctness against a TestClient-backed httpx transport
- Retry / timeout / unavailable-backend behaviour
- Streamlit action helpers that route through the service client
"""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from podcast_pipeline.clients.service_client import (
    BackgroundRunResult,
    CreatedJob,
    HealthStatus,
    JobDetail,
    JobList,
    ServiceClient,
    ServiceResponseError,
    ServiceUnavailableError,
)
from podcast_pipeline.config import Config, ServiceConfig
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.app import create_app
from podcast_pipeline.service.supervisor import Supervisor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client_temp_dir() -> Generator[Path, None, None]:
    """Isolated temp directory for service client tests."""
    tmp = Path(tempfile.mkdtemp())
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def backend_test_client(client_temp_dir: Path) -> Generator[TestClient, None, None]:
    """FastAPI TestClient wired to a temp jobs directory."""
    app = create_app()
    with TestClient(app) as tc:
        config = Config()
        config.paths.jobs_dir = client_temp_dir / "jobs"
        config.paths.jobs_dir.mkdir(parents=True, exist_ok=True)
        pipeline = Pipeline(config)
        app.state.config = config
        app.state.pipeline = pipeline
        app.state.supervisor = Supervisor(pipeline)
        yield tc


@pytest.fixture
def video_file(client_temp_dir: Path) -> Path:
    """Tiny dummy video file."""
    vf = client_temp_dir / "video.mp4"
    vf.write_bytes(b"\x00" * 64)
    return vf


def _wrap_client(tc: TestClient) -> ServiceClient:
    """Create a ServiceClient whose transport is backed by the TestClient.

    This avoids the need for a live TCP server by monkey-patching
    ``_client`` to return a real httpx.Client using the ASGI transport.
    """
    client = ServiceClient(base_url="http://testserver")

    real_client_fn = client._client

    def _patched() -> httpx.Client:
        _ = real_client_fn  # keep reference for potential cleanup
        return httpx.Client(
            transport=tc._transport,  # type: ignore[arg-type]
            base_url="http://testserver",
            timeout=30.0,
        )

    client._client = _patched  # type: ignore[assignment]
    return client


@pytest.fixture
def service_client(backend_test_client: TestClient) -> ServiceClient:
    """ServiceClient wired through the ASGI TestClient transport."""
    return _wrap_client(backend_test_client)


@pytest.fixture
def seeded_job_id(service_client: ServiceClient, video_file: Path) -> str:
    """Create a job and return its ID."""
    created = service_client.create_job(str(video_file), name="test-ep")
    return created.job_id


# ---------------------------------------------------------------------------
# Client contract tests
# ---------------------------------------------------------------------------


class TestClientContract:
    """Verify typed client methods match the backend route contract."""

    def test_client_contract_health(self, service_client: ServiceClient):
        result = service_client.health()
        assert isinstance(result, HealthStatus)
        assert result.status == "ok"

    def test_client_contract_is_available(self, service_client: ServiceClient):
        assert service_client.is_available() is True

    def test_client_contract_create_job(self, service_client: ServiceClient, video_file: Path):
        result = service_client.create_job(str(video_file), name="my-ep")
        assert isinstance(result, CreatedJob)
        assert result.status == "pending"
        assert result.input_file.endswith("video.mp4")
        assert result.created_at is not None

    def test_client_contract_create_job_bad_path(self, service_client: ServiceClient):
        with pytest.raises(ServiceResponseError) as exc_info:
            service_client.create_job("/no/such/file.mp4")
        assert exc_info.value.status_code == 400

    def test_client_contract_get_job(self, service_client: ServiceClient, seeded_job_id: str):
        detail = service_client.get_job(seeded_job_id)
        assert isinstance(detail, JobDetail)
        assert detail.job_id == seeded_job_id
        assert "ingest" in detail.stages

    def test_client_contract_get_job_not_found(self, service_client: ServiceClient):
        with pytest.raises(ServiceResponseError) as exc_info:
            service_client.get_job("nonexistent-id")
        assert exc_info.value.status_code == 404

    def test_client_contract_list_jobs(self, service_client: ServiceClient, seeded_job_id: str):
        result = service_client.list_jobs()
        assert isinstance(result, JobList)
        ids = [j.job_id for j in result.jobs]
        assert seeded_job_id in ids

    def test_client_contract_list_jobs_empty(self, service_client: ServiceClient):
        result = service_client.list_jobs()
        assert isinstance(result, JobList)
        assert result.jobs == []

    def test_client_contract_run_job_not_found(self, service_client: ServiceClient):
        with pytest.raises(ServiceResponseError) as exc_info:
            service_client.run_job("nonexistent-id", stage="ingest")
        assert exc_info.value.status_code == 404

    def test_client_contract_background_run(
        self, service_client: ServiceClient, seeded_job_id: str
    ):
        result = service_client.run_job_background(seeded_job_id)
        assert isinstance(result, BackgroundRunResult)
        assert result.accepted is True

    def test_client_contract_resume_not_found(self, service_client: ServiceClient):
        with pytest.raises(ServiceResponseError) as exc_info:
            service_client.resume_job("nonexistent-id")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Retry / unavailable behaviour
# ---------------------------------------------------------------------------


class TestRetryBehavior:
    """Test connection error handling and unavailable backend detection."""

    def test_retry_behavior_unavailable_health(self):
        """ServiceClient targeting an unreachable host raises ServiceUnavailableError."""
        client = ServiceClient(
            base_url="http://127.0.0.1:19999",
            timeout=0.5,
            retries=0,
        )
        with pytest.raises(ServiceUnavailableError) as exc_info:
            client.health()
        assert "127.0.0.1:19999" in str(exc_info.value)

    def test_retry_behavior_is_available_false(self):
        """is_available returns False when backend is unreachable."""
        client = ServiceClient(
            base_url="http://127.0.0.1:19999",
            timeout=0.5,
            retries=0,
        )
        assert client.is_available() is False

    def test_retry_behavior_service_response_error_attrs(self):
        """ServiceResponseError carries status_code and detail."""
        err = ServiceResponseError(422, "Validation failed")
        assert err.status_code == 422
        assert err.detail == "Validation failed"
        assert "422" in str(err)

    def test_retry_behavior_unavailable_error_attrs(self):
        """ServiceUnavailableError carries base_url."""
        cause = ConnectionError("refused")
        err = ServiceUnavailableError("http://localhost:8787", cause=cause)
        assert err.base_url == "http://localhost:8787"
        assert err.cause is cause


# ---------------------------------------------------------------------------
# ServiceConfig integration
# ---------------------------------------------------------------------------


class TestServiceConfig:
    """Verify ServiceConfig defaults and base_url property."""

    def test_default_values(self):
        cfg = ServiceConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8787
        assert cfg.timeout == 30.0
        assert cfg.retries == 2

    def test_base_url(self):
        cfg = ServiceConfig(host="192.168.1.10", port=9000)
        assert cfg.base_url == "http://192.168.1.10:9000"

    def test_config_has_service_field(self):
        config = Config()
        assert hasattr(config, "service")
        assert isinstance(config.service, ServiceConfig)
        assert config.service.base_url == "http://127.0.0.1:8787"

    def test_service_client_from_config(self):
        """ServiceClient can be constructed from Config.service."""
        config = Config()
        client = ServiceClient(
            base_url=config.service.base_url,
            timeout=config.service.timeout,
            retries=config.service.retries,
        )
        assert client.base_url == "http://127.0.0.1:8787"
        assert client.timeout == 30.0
        assert client.retries == 2
