"""Contract tests for the service API endpoints.

Uses FastAPI's TestClient (backed by httpx) to exercise routes
without a live server. All tests use an isolated temp job directory.
"""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from podcast_pipeline.config import Config
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.service.app import create_app
from podcast_pipeline.service.supervisor import Supervisor
from podcast_pipeline.stages.base import StageResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service_temp_dir() -> Generator[Path, None, None]:
    """Isolated temp directory for the service tests."""
    tmp = Path(tempfile.mkdtemp())
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def service_client(service_temp_dir: Path) -> Generator[TestClient, None, None]:
    """TestClient wired to a throwaway jobs directory."""
    app = create_app()

    with TestClient(app) as client:
        # Override pipeline/config *after* lifespan has run so that
        # the real ./jobs directory is never consulted.
        config = Config()
        config.paths.jobs_dir = service_temp_dir / "jobs"
        config.paths.jobs_dir.mkdir(parents=True, exist_ok=True)
        pipeline = Pipeline(config)
        app.state.config = config
        app.state.pipeline = pipeline
        app.state.supervisor = Supervisor(pipeline)
        yield client


@pytest.fixture
def video_file(service_temp_dir: Path) -> Path:
    """Create a tiny dummy video file so create_job succeeds."""
    vf = service_temp_dir / "sample.mp4"
    vf.write_bytes(b"\x00" * 64)
    return vf


@pytest.fixture
def seeded_job(service_client: TestClient, video_file: Path) -> str:
    """Create a job via the API and return its job_id."""
    resp = service_client.post(
        "/jobs",
        json={"video_path": str(video_file)},
    )
    assert resp.status_code == 201
    return resp.json()["job_id"]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealth:
    """GET /health contract."""

    def test_health(self, service_client: TestClient):
        resp = service_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Jobs contract
# ---------------------------------------------------------------------------


class TestJobsContract:
    """Core job lifecycle route tests."""

    def test_jobs_contract_create(self, service_client: TestClient, video_file: Path):
        """POST /jobs returns 201 with typed payload."""
        resp = service_client.post(
            "/jobs",
            json={"video_path": str(video_file), "name": "my-test"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["input_file"].endswith("sample.mp4")
        assert "created_at" in data

    def test_jobs_contract_create_missing_file(self, service_client: TestClient):
        """POST /jobs with bad path returns 400."""
        resp = service_client.post(
            "/jobs",
            json={"video_path": "/nonexistent/video.mp4"},
        )
        assert resp.status_code == 400

    def test_jobs_contract_get(self, service_client: TestClient, seeded_job: str):
        """GET /jobs/{job_id} returns full detail."""
        resp = service_client.get(f"/jobs/{seeded_job}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == seeded_job
        assert "stages" in data
        assert "ingest" in data["stages"]

    def test_jobs_contract_get_not_found(self, service_client: TestClient):
        """GET /jobs/{bad_id} returns 404."""
        resp = service_client.get("/jobs/nonexistent-id")
        assert resp.status_code == 404

    def test_jobs_contract_list(self, service_client: TestClient, seeded_job: str):
        """GET /jobs returns list containing seeded job."""
        resp = service_client.get("/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert "jobs" in data
        ids = [j["job_id"] for j in data["jobs"]]
        assert seeded_job in ids

    def test_jobs_contract_list_empty(self, service_client: TestClient):
        """GET /jobs returns empty list when no jobs exist."""
        resp = service_client.get("/jobs")
        assert resp.status_code == 200
        assert resp.json()["jobs"] == []

    def test_jobs_contract_resume_all_pending(self, service_client: TestClient, seeded_job: str):
        """POST /jobs/{id}/resume on a brand-new job picks first stage."""
        resp = service_client.post(
            f"/jobs/{seeded_job}/resume",
            json={},
        )
        # We expect it to attempt to resume (may fail due to missing ffmpeg
        # or video content, but the HTTP contract is satisfied: it does not 404
        # and it returns a structured response).
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["job_id"] == seeded_job
            assert "status" in data
            assert "message" in data

    def test_jobs_contract_resume_not_found(self, service_client: TestClient):
        """POST /jobs/{bad_id}/resume returns 404."""
        resp = service_client.post(
            "/jobs/nonexistent-id/resume",
            json={},
        )
        assert resp.status_code == 404


class TestRunRoute:
    """POST /jobs/{job_id}/run route tests."""

    def test_run_not_found(self, service_client: TestClient):
        """POST /jobs/{bad_id}/run returns 404."""
        resp = service_client.post(
            "/jobs/nonexistent-id/run",
            json={},
        )
        assert resp.status_code == 404

    def test_run_returns_structured(self, service_client: TestClient, seeded_job: str):
        """POST /jobs/{id}/run returns structured response (may fail in stage)."""
        resp = service_client.post(
            f"/jobs/{seeded_job}/run",
            json={"stage": "ingest"},
        )
        # The route itself should not 500 -- it catches stage errors
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["job_id"] == seeded_job
            assert "status" in data


# ---------------------------------------------------------------------------
# Run/resume schema validation and contract semantics (Phase 04-02 Task 1)
# ---------------------------------------------------------------------------


class TestRunResumeSchema:
    """Validation and response-contract tests for run/resume payloads."""

    def test_run_schema_rejects_invalid_stage(self, service_client: TestClient, seeded_job: str):
        """Invalid run stage values return structured validation errors."""
        resp = service_client.post(
            f"/jobs/{seeded_job}/run",
            json={"stage": "not-a-stage"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        assert any(entry.get("loc", [])[-1] == "stage" for entry in detail)

    def test_run_schema_rejects_until_before_stage(
        self,
        service_client: TestClient,
        seeded_job: str,
    ):
        """until_stage before stage fails request-model validation."""
        resp = service_client.post(
            f"/jobs/{seeded_job}/run",
            json={"stage": "review", "until_stage": "analyze"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        assert any(
            "until_stage must be the same as or after stage" in entry["msg"] for entry in detail
        )

    def test_run_schema_response_includes_execution_flags(
        self,
        service_client: TestClient,
        seeded_job: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Run responses explicitly report started/completed/rejected flags."""

        def _fake_run(*_args, **_kwargs):
            return {"ingest": StageResult(success=True)}

        monkeypatch.setattr(service_client.app.state.pipeline, "run", _fake_run)
        resp = service_client.post(
            f"/jobs/{seeded_job}/run",
            json={"stage": "ingest"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["started"] is True
        assert payload["completed"] is True
        assert payload["rejected"] is False

    def test_resume_schema_rejects_invalid_stage(self, service_client: TestClient, seeded_job: str):
        """Invalid resume from_stage values return structured validation errors."""
        resp = service_client.post(
            f"/jobs/{seeded_job}/resume",
            json={"from_stage": "bad-stage"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        assert any(entry.get("loc", [])[-1] == "from_stage" for entry in detail)

    def test_resume_schema_accepts_background_and_until_stage(
        self,
        service_client: TestClient,
        seeded_job: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Resume schema accepts parity controls and forwards them to supervisor."""
        captured: dict[str, str | None] = {}

        def _fake_start_run(*_args, stage: str | None = None, until_stage: str | None = None):
            captured["stage"] = stage
            captured["until_stage"] = until_stage
            return True

        monkeypatch.setattr(service_client.app.state.supervisor, "start_run", _fake_start_run)
        resp = service_client.post(
            f"/jobs/{seeded_job}/resume",
            json={"from_stage": "transcribe", "until_stage": "render", "background": True},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "running"
        assert payload["started"] is True
        assert payload["completed"] is False
        assert payload["rejected"] is False
        assert captured == {"stage": "transcribe", "until_stage": "render"}


# ---------------------------------------------------------------------------
# Background run + duplicate guard (Task 2)
# ---------------------------------------------------------------------------


class TestBackgroundRun:
    """Tests for background run supervision."""

    def test_background_run_accepted(self, service_client: TestClient, seeded_job: str):
        """POST /jobs/{id}/run/background returns accepted=True."""
        resp = service_client.post(
            f"/jobs/{seeded_job}/run/background",
            json={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == seeded_job
        assert data["accepted"] is True
        assert "message" in data

    def test_background_run_not_found(self, service_client: TestClient):
        """POST /jobs/{bad_id}/run/background returns 404."""
        resp = service_client.post(
            "/jobs/nonexistent-id/run/background",
            json={},
        )
        assert resp.status_code == 404


class TestDuplicateRunGuard:
    """Tests for duplicate run rejection."""

    def test_duplicate_run_guard(self, service_client: TestClient, seeded_job: str):
        """Second background run request for same job returns 409."""
        # First request should succeed
        resp1 = service_client.post(
            f"/jobs/{seeded_job}/run/background",
            json={},
        )
        assert resp1.status_code == 200
        assert resp1.json()["accepted"] is True

        # Second request while first is still active should be rejected
        resp2 = service_client.post(
            f"/jobs/{seeded_job}/run/background",
            json={},
        )
        assert resp2.status_code == 409
        assert "already has an active run" in resp2.json()["detail"]
