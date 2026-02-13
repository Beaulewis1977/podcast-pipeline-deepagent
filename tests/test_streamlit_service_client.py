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
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from podcast_pipeline.clients.service_client import (
    BackgroundRunResult,
    CreatedJob,
    HealthStatus,
    JobDetail,
    JobList,
    RunResult,
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


# ---------------------------------------------------------------------------
# Streamlit action helpers (service-backed)
# ---------------------------------------------------------------------------


class TestStreamlitActions:
    """Verify that Streamlit UI helper functions correctly route through the ServiceClient.

    These tests mock both ``streamlit`` (which is unavailable in test context)
    and the service client to isolate the routing logic in the UI module.
    """

    def test_streamlit_actions_load_jobs_success(self, service_client: ServiceClient):
        """load_jobs_list returns dicts from service client list_jobs."""
        from podcast_pipeline.ui.app import load_jobs_list

        mock_st = MagicMock()
        with (
            patch("podcast_pipeline.ui.app.get_service_client", return_value=service_client),
            patch("podcast_pipeline.ui.app.st", mock_st),
        ):
            result = load_jobs_list()
        # Empty list since no jobs created
        assert isinstance(result, list)
        assert result == []

    def test_streamlit_actions_load_jobs_unavailable(self):
        """load_jobs_list shows error and returns [] when backend unreachable."""
        from podcast_pipeline.ui.app import load_jobs_list

        bad_client = ServiceClient(
            base_url="http://127.0.0.1:19999",
            timeout=0.5,
            retries=0,
        )
        mock_st = MagicMock()
        with (
            patch("podcast_pipeline.ui.app.get_service_client", return_value=bad_client),
            patch("podcast_pipeline.ui.app.st", mock_st),
        ):
            result = load_jobs_list()
        assert result == []
        mock_st.error.assert_called_once()
        assert "not running" in mock_st.error.call_args[0][0]

    def test_streamlit_actions_load_jobs_with_data(self, service_client: ServiceClient, video_file):
        """load_jobs_list returns populated list after creating a job."""
        from podcast_pipeline.ui.app import load_jobs_list

        # Seed a job
        service_client.create_job(str(video_file), name="action-test")

        mock_st = MagicMock()
        with (
            patch("podcast_pipeline.ui.app.get_service_client", return_value=service_client),
            patch("podcast_pipeline.ui.app.st", mock_st),
        ):
            result = load_jobs_list()
        assert len(result) == 1
        assert "job_id" in result[0]
        assert result[0]["status"] == "pending"

    def test_streamlit_actions_run_stage_success(
        self, service_client: ServiceClient, seeded_job_id: str
    ):
        """run_stage_via_service calls service client run_job."""
        from podcast_pipeline.ui.app import run_stage_via_service

        # Mock run_job to return success without actually running pipeline
        mock_run = MagicMock(
            return_value=RunResult(job_id=seeded_job_id, status="complete", message="OK")
        )
        service_client.run_job = mock_run  # type: ignore[assignment]

        mock_st = MagicMock()
        # Prevent st.rerun() from raising
        mock_st.rerun = MagicMock()
        with (
            patch("podcast_pipeline.ui.app.get_service_client", return_value=service_client),
            patch("podcast_pipeline.ui.app.st", mock_st),
        ):
            run_stage_via_service(seeded_job_id, "ingest")
        mock_run.assert_called_once_with(seeded_job_id, stage="ingest")
        mock_st.success.assert_called_once()

    def test_streamlit_actions_run_stage_unavailable(self):
        """run_stage_via_service shows error when backend is down."""
        from podcast_pipeline.ui.app import run_stage_via_service

        bad_client = ServiceClient(
            base_url="http://127.0.0.1:19999",
            timeout=0.5,
            retries=0,
        )
        mock_st = MagicMock()
        with (
            patch("podcast_pipeline.ui.app.get_service_client", return_value=bad_client),
            patch("podcast_pipeline.ui.app.st", mock_st),
        ):
            run_stage_via_service("fake-id", "ingest")
        mock_st.error.assert_called()
        assert "not running" in mock_st.error.call_args[0][0]

    def test_streamlit_actions_run_stage_failure(
        self, service_client: ServiceClient, seeded_job_id: str
    ):
        """run_stage_via_service shows error message on failed stage."""
        from podcast_pipeline.ui.app import run_stage_via_service

        mock_run = MagicMock(
            return_value=RunResult(
                job_id=seeded_job_id, status="failed", message="FFmpeg not found"
            )
        )
        service_client.run_job = mock_run  # type: ignore[assignment]

        mock_st = MagicMock()
        with (
            patch("podcast_pipeline.ui.app.get_service_client", return_value=service_client),
            patch("podcast_pipeline.ui.app.st", mock_st),
        ):
            run_stage_via_service(seeded_job_id, "ingest")
        mock_st.error.assert_called_once()
        assert "FFmpeg not found" in mock_st.error.call_args[0][0]

    def test_streamlit_actions_run_stage_quality_controls_payload(
        self,
        service_client: ServiceClient,
        seeded_job_id: str,
    ) -> None:
        """Render action should forward quality controls in run payload."""
        from podcast_pipeline.ui.app import run_stage_via_service

        quality_controls = {"video_quality": "ultra", "audio_normalize": False}
        mock_run = MagicMock(
            return_value=RunResult(job_id=seeded_job_id, status="complete", message="OK")
        )
        service_client.run_job = mock_run  # type: ignore[assignment]

        mock_st = MagicMock()
        mock_st.rerun = MagicMock()
        with (
            patch("podcast_pipeline.ui.app.get_service_client", return_value=service_client),
            patch("podcast_pipeline.ui.app.st", mock_st),
        ):
            run_stage_via_service(
                seeded_job_id,
                "render",
                quality_controls=quality_controls,
            )

        mock_run.assert_called_once_with(
            seeded_job_id,
            stage="render",
            quality_controls=quality_controls,
        )
        mock_st.success.assert_called_once()

    def test_streamlit_actions_run_full_pipeline_calls_run_job_without_stage(
        self, service_client: ServiceClient, seeded_job_id: str
    ) -> None:
        """Run Full Pipeline should trigger full-run semantics (no stage override)."""
        from podcast_pipeline.ui.app import run_full_pipeline_via_service

        mock_run = MagicMock(
            return_value=RunResult(
                job_id=seeded_job_id, status="complete", message="Ran 4 stage(s)"
            )
        )
        service_client.run_job = mock_run  # type: ignore[assignment]

        mock_st = MagicMock()
        mock_st.rerun = MagicMock()
        with (
            patch("podcast_pipeline.ui.app.get_service_client", return_value=service_client),
            patch("podcast_pipeline.ui.app.st", mock_st),
        ):
            run_full_pipeline_via_service(seeded_job_id)

        mock_run.assert_called_once_with(seeded_job_id)
        mock_st.success.assert_called_once()

    def test_streamlit_actions_upload_path_uses_service_upload_dir(
        self, client_temp_dir: Path
    ) -> None:
        """Uploaded file is persisted outside pre-created per-job directories."""
        from podcast_pipeline.ui.app import _persist_uploaded_video

        class _FakeUpload:
            def __init__(self) -> None:
                self.name = "episode.mp4"
                self._payload = b"video-bytes"

            def getvalue(self) -> bytes:
                return self._payload

        saved_path = _persist_uploaded_video(_FakeUpload(), client_temp_dir)

        assert saved_path.parent == client_temp_dir / "_uploads"
        assert saved_path.suffix == ".mp4"
        assert saved_path.read_bytes() == b"video-bytes"

    def test_streamlit_actions_check_service_available(self, service_client: ServiceClient):
        """check_service_status returns True when backend is up."""
        from podcast_pipeline.ui.app import check_service_status

        with patch("podcast_pipeline.ui.app.get_service_client", return_value=service_client):
            assert check_service_status() is True

    def test_streamlit_actions_check_service_unavailable(self):
        """check_service_status returns False when backend is down."""
        from podcast_pipeline.ui.app import check_service_status

        bad_client = ServiceClient(
            base_url="http://127.0.0.1:19999",
            timeout=0.5,
            retries=0,
        )
        with patch("podcast_pipeline.ui.app.get_service_client", return_value=bad_client):
            assert check_service_status() is False

    def test_streamlit_actions_no_direct_pipeline_import(self):
        """Verify Streamlit UI module does NOT import Pipeline directly."""
        import inspect

        from podcast_pipeline.ui import app as ui_app

        source = inspect.getsource(ui_app)
        # The module should not import Pipeline
        assert "from podcast_pipeline.pipeline import Pipeline" not in source
        # It should use ServiceClient instead
        assert "ServiceClient" in source


class TestQualityControlsContract:
    """Validate schema and persistence behavior for render quality controls."""

    def test_run_quality_controls_schema_rejects_invalid_video_quality(
        self,
        backend_test_client: TestClient,
        video_file: Path,
    ) -> None:
        """Invalid quality profile should fail request validation."""
        create_resp = backend_test_client.post(
            "/jobs",
            json={"video_path": str(video_file), "name": "quality-controls"},
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["job_id"]

        resp = backend_test_client.post(
            f"/jobs/{job_id}/run",
            json={
                "stage": "render",
                "quality_controls": {
                    "video_quality": "cinema",
                    "audio_normalize": True,
                },
            },
        )
        assert resp.status_code == 422

    def test_run_quality_controls_persist_to_job_config(
        self,
        backend_test_client: TestClient,
        video_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run route should persist valid quality controls before execution."""
        create_resp = backend_test_client.post(
            "/jobs",
            json={"video_path": str(video_file), "name": "quality-controls"},
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["job_id"]

        captured: dict[str, object] = {}

        def _fake_run(job, stage=None, until_stage=None):
            captured["controls"] = job.config.get("render_quality_controls")
            return {}

        monkeypatch.setattr(backend_test_client.app.state.pipeline, "run", _fake_run)

        controls = {"video_quality": "high", "audio_normalize": False}
        resp = backend_test_client.post(
            f"/jobs/{job_id}/run",
            json={
                "stage": "render",
                "quality_controls": controls,
            },
        )
        assert resp.status_code == 200
        assert captured["controls"] == controls
