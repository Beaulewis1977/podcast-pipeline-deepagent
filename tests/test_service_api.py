"""Contract tests for the service API endpoints.

Uses FastAPI's TestClient (backed by httpx) to exercise routes
without a live server. All tests use an isolated temp job directory.
"""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from podcast_pipeline.clients.service_client import ServiceClient, ServiceConflictError
from podcast_pipeline.config import Config
from podcast_pipeline.models.job import StageStatus
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

    def test_jobs_contract_delete_removes_managed_upload_file(self, service_client: TestClient):
        """Deleting a job also removes its orphaned jobs/_uploads source file."""
        jobs_dir = service_client.app.state.pipeline.config.paths.jobs_dir
        upload_path = jobs_dir / "_uploads" / "sample_upload.mp4"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(b"\x00" * 32)

        create_resp = service_client.post(
            "/jobs",
            json={"video_path": str(upload_path), "name": "delete-upload"},
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["job_id"]

        delete_resp = service_client.delete(f"/jobs/{job_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True
        assert not (jobs_dir / job_id).exists()
        assert not upload_path.exists()

    def test_jobs_contract_delete_keeps_shared_upload_file(self, service_client: TestClient):
        """Deleting one job does not remove an upload still referenced by another job."""
        jobs_dir = service_client.app.state.pipeline.config.paths.jobs_dir
        upload_path = jobs_dir / "_uploads" / "shared_upload.mp4"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(b"\x00" * 32)

        create_a = service_client.post(
            "/jobs",
            json={"video_path": str(upload_path), "name": "shared-a"},
        )
        create_b = service_client.post(
            "/jobs",
            json={"video_path": str(upload_path), "name": "shared-b"},
        )
        assert create_a.status_code == 201
        assert create_b.status_code == 201
        job_a = create_a.json()["job_id"]
        job_b = create_b.json()["job_id"]

        delete_resp = service_client.delete(f"/jobs/{job_a}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True
        assert upload_path.exists()
        assert (jobs_dir / job_b).exists()

    def test_jobs_contract_list_includes_invalid_state_jobs(self, service_client: TestClient):
        """GET /jobs should include entries that fail strict model validation."""
        jobs_dir = service_client.app.state.pipeline.config.paths.jobs_dir
        broken_dir = jobs_dir / "broken-job"
        broken_dir.mkdir(parents=True, exist_ok=True)
        (broken_dir / "state.json").write_text(
            """
{
  "job_id": "broken-job",
  "created_at": "2026-02-01T00:00:00Z",
  "updated_at": "2026-02-01T00:00:05Z",
  "status": "complete",
  "input_file": "/tmp/broken.mp4",
  "stages": {
    "ingest": {
      "status": "complete",
      "started_at": "2026-02-01T00:00:10Z",
      "completed_at": "2026-02-01T00:00:01Z",
      "outputs": [],
      "error": null
    }
  },
  "error": null,
  "config": {}
}
            """.strip()
        )

        resp = service_client.get("/jobs")
        assert resp.status_code == 200
        jobs = resp.json()["jobs"]
        broken = next((item for item in jobs if item["job_id"] == "broken-job"), None)
        assert broken is not None
        assert broken["status"] == "invalid"

    def test_jobs_contract_delete_allows_invalid_state_jobs(self, service_client: TestClient):
        """DELETE /jobs/{id} should work even when state.json is invalid."""
        jobs_dir = service_client.app.state.pipeline.config.paths.jobs_dir
        broken_dir = jobs_dir / "invalid-delete-job"
        broken_dir.mkdir(parents=True, exist_ok=True)
        (broken_dir / "state.json").write_text(
            """
{
  "job_id": "invalid-delete-job",
  "created_at": "2026-02-01T00:00:00Z",
  "updated_at": "2026-02-01T00:00:05Z",
  "status": "complete",
  "input_file": "/tmp/broken.mp4",
  "stages": {
    "analyze": {
      "status": "complete",
      "error": "should not exist on complete"
    }
  },
  "error": null,
  "config": {}
}
            """.strip()
        )

        delete_resp = service_client.delete("/jobs/invalid-delete-job")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True
        assert not broken_dir.exists()

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
# Resume-through-completion semantics (Phase 04-02 Task 2)
# ---------------------------------------------------------------------------


class TestResumeToCompletion:
    """Resume endpoint behavior for continuation-through-completion flow."""

    def test_resume_to_completion_defaults_to_final_stage(
        self,
        service_client: TestClient,
        seeded_job: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """from_stage resumes through final stage when until_stage is omitted."""
        captured: dict[str, str | None] = {}

        def _fake_run(*_args, stage: str | None = None, until_stage: str | None = None):
            captured["stage"] = stage
            captured["until_stage"] = until_stage
            return {
                "analyze": StageResult(success=True),
                "review": StageResult(success=True),
                "render": StageResult(success=True),
            }

        monkeypatch.setattr(service_client.app.state.pipeline, "run", _fake_run)
        resp = service_client.post(
            f"/jobs/{seeded_job}/resume",
            json={"from_stage": "analyze"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "complete"
        assert payload["started"] is True
        assert payload["completed"] is True
        assert payload["rejected"] is False
        assert captured == {"stage": "analyze", "until_stage": "render"}

    def test_resume_to_completion_honors_explicit_until_stage(
        self,
        service_client: TestClient,
        seeded_job: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """until_stage narrows continuation range for resume."""
        captured: dict[str, str | None] = {}

        def _fake_run(*_args, stage: str | None = None, until_stage: str | None = None):
            captured["stage"] = stage
            captured["until_stage"] = until_stage
            return {
                "analyze": StageResult(success=True),
                "review": StageResult(success=True),
            }

        monkeypatch.setattr(service_client.app.state.pipeline, "run", _fake_run)
        resp = service_client.post(
            f"/jobs/{seeded_job}/resume",
            json={"from_stage": "analyze", "until_stage": "review"},
        )
        assert resp.status_code == 200
        assert captured == {"stage": "analyze", "until_stage": "review"}

    def test_resume_to_completion_rejects_until_before_detected_resume_stage(
        self,
        service_client: TestClient,
        seeded_job: str,
    ):
        """until_stage earlier than auto-detected resume stage returns 422."""
        pipeline = service_client.app.state.pipeline
        job = pipeline.load_job(seeded_job)
        job.update_stage("ingest", StageStatus.COMPLETE)
        job.save(pipeline.config.paths.jobs_dir)

        resp = service_client.post(
            f"/jobs/{seeded_job}/resume",
            json={"until_stage": "ingest"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        assert any(entry.get("loc", [])[-1] == "until_stage" for entry in detail)

    def test_already_complete_resume_returns_noop_response(
        self,
        service_client: TestClient,
        seeded_job: str,
    ):
        """Already-complete jobs return deterministic no-op resume response."""
        pipeline = service_client.app.state.pipeline
        job = pipeline.load_job(seeded_job)
        for stage_name in Pipeline.STAGE_ORDER:
            job.update_stage(stage_name, StageStatus.COMPLETE)
        job.save(pipeline.config.paths.jobs_dir)

        resp = service_client.post(
            f"/jobs/{seeded_job}/resume",
            json={},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "complete"
        assert payload["started"] is False
        assert payload["completed"] is True
        assert payload["rejected"] is False
        assert "no incomplete stages" in payload["message"]


# ---------------------------------------------------------------------------
# Service client parity + timeout behavior (Phase 04-02 Task 3)
# ---------------------------------------------------------------------------


class TestServiceClientResumeTimeout:
    """Client-side run/resume parity, timeout, and status-mapping tests."""

    def test_service_client_resume_timeout_payload_parity(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """resume_job sends from_stage/until_stage/background parity fields."""
        client = ServiceClient(base_url="http://testserver", timeout=5.0, resume_timeout=45.0)
        captured: dict[str, object] = {}

        def _fake_request(
            method: str,
            path: str,
            *,
            json: dict[str, object] | None = None,
            timeout: float | None = None,
        ) -> httpx.Response:
            captured["method"] = method
            captured["path"] = path
            captured["json"] = json
            captured["timeout"] = timeout
            return httpx.Response(
                200,
                json={
                    "job_id": "job-1",
                    "status": "running",
                    "message": "ok",
                    "started": True,
                    "completed": False,
                    "rejected": False,
                },
                request=httpx.Request(method, f"http://testserver{path}"),
            )

        monkeypatch.setattr(client, "_request", _fake_request)
        result = client.resume_job(
            "job-1",
            from_stage="analyze",
            until_stage="review",
            background=True,
        )
        assert result.status == "running"
        assert captured == {
            "method": "POST",
            "path": "/jobs/job-1/resume",
            "json": {"background": True, "from_stage": "analyze", "until_stage": "review"},
            "timeout": 5.0,
        }

    def test_service_client_resume_timeout_uses_long_timeout_for_blocking_resume(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Blocking resume requests use the endpoint-specific timeout."""
        client = ServiceClient(base_url="http://testserver", timeout=3.0, resume_timeout=77.0)
        captured: dict[str, object] = {}

        def _fake_request(
            method: str,
            path: str,
            *,
            json: dict[str, object] | None = None,
            timeout: float | None = None,
        ) -> httpx.Response:
            captured["method"] = method
            captured["path"] = path
            captured["json"] = json
            captured["timeout"] = timeout
            return httpx.Response(
                200,
                json={
                    "job_id": "job-1",
                    "status": "complete",
                    "message": "done",
                    "started": True,
                    "completed": True,
                    "rejected": False,
                },
                request=httpx.Request(method, f"http://testserver{path}"),
            )

        monkeypatch.setattr(client, "_request", _fake_request)
        result = client.resume_job("job-1", from_stage="transcribe")
        assert result.status == "complete"
        assert captured["json"] == {"background": False, "from_stage": "transcribe"}
        assert captured["timeout"] == 77.0

    def test_service_client_resume_timeout_maps_conflict_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """HTTP 409 responses map to ServiceConflictError."""
        client = ServiceClient(base_url="http://testserver")

        def _fake_request(
            method: str,
            path: str,
            *,
            json: dict[str, object] | None = None,
            timeout: float | None = None,
        ) -> httpx.Response:
            _ = (json, timeout)
            return httpx.Response(
                409,
                json={"detail": f"{path} already has an active run"},
                request=httpx.Request(method, f"http://testserver{path}"),
            )

        monkeypatch.setattr(client, "_request", _fake_request)
        with pytest.raises(ServiceConflictError) as exc_info:
            client.resume_job("job-1", from_stage="analyze", background=True)
        assert exc_info.value.status_code == 409
        assert "active run" in str(exc_info.value)

    def test_service_client_resume_timeout_reuses_persistent_http_client(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """resume_job requests reuse a single cached HTTPX client."""
        client = ServiceClient(base_url="http://testserver", timeout=5.0)
        client_factory_calls = 0
        request_calls = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_calls
            request_calls += 1
            return httpx.Response(
                200,
                json={
                    "job_id": "job-1",
                    "status": "running",
                    "message": "ok",
                    "started": True,
                    "completed": False,
                    "rejected": False,
                },
                request=request,
            )

        transport = httpx.MockTransport(_handler)

        def _fake_client_factory() -> httpx.Client:
            nonlocal client_factory_calls
            client_factory_calls += 1
            return httpx.Client(
                transport=transport,
                base_url="http://testserver",
                timeout=client.timeout,
            )

        monkeypatch.setattr(client, "_client", _fake_client_factory)
        client.resume_job("job-1", from_stage="analyze", background=True)
        client.resume_job("job-1", from_stage="analyze", background=True)
        client.close()

        assert client_factory_calls == 1
        assert request_calls == 2

    def test_service_client_delete_job_calls_delete_endpoint(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """delete_job uses DELETE /jobs/{id} and returns typed payload."""
        client = ServiceClient(base_url="http://testserver")
        captured: dict[str, object] = {}

        def _fake_request(
            method: str,
            path: str,
            *,
            json: dict[str, object] | None = None,
            timeout: float | None = None,
        ) -> httpx.Response:
            captured["method"] = method
            captured["path"] = path
            captured["json"] = json
            captured["timeout"] = timeout
            return httpx.Response(
                200,
                json={
                    "job_id": "job-123",
                    "deleted": True,
                    "message": "Deleted job job-123",
                },
                request=httpx.Request(method, f"http://testserver{path}"),
            )

        monkeypatch.setattr(client, "_request", _fake_request)
        result = client.delete_job("job-123")
        assert result.deleted is True
        assert captured == {
            "method": "DELETE",
            "path": "/jobs/job-123",
            "json": None,
            "timeout": None,
        }


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
