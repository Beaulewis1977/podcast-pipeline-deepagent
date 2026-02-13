"""Typed HTTP client for the podcast-pipeline backend service.

Provides a single-class API that mirrors the backend route contract
so that Streamlit, Tauri, and tests can interact with the service
through strongly-typed methods rather than raw HTTP calls.

Usage::

    from podcast_pipeline.clients.service_client import ServiceClient

    client = ServiceClient(base_url="http://127.0.0.1:8787")
    health = client.health()
    job = client.create_job("/path/to/video.mp4", name="my-ep")
    detail = client.get_job(job.job_id)
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Client-side response models (mirrors service schemas)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRIES = 2
DEFAULT_RUN_TIMEOUT_SECONDS = 900.0
DEFAULT_RESUME_TIMEOUT_SECONDS = 900.0


class HealthStatus(BaseModel):
    """Response from GET /health."""

    status: str


class CreatedJob(BaseModel):
    """Response from POST /jobs."""

    job_id: str
    status: str
    input_file: str
    created_at: datetime


class RunResult(BaseModel):
    """Response from POST /jobs/{id}/run."""

    job_id: str
    status: str
    message: str
    started: bool = True
    completed: bool = False
    rejected: bool = False


class BackgroundRunResult(BaseModel):
    """Response from POST /jobs/{id}/run/background."""

    job_id: str
    accepted: bool
    message: str


class StageDetail(BaseModel):
    """Single stage status inside a job detail response."""

    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None
    progress_percent: int | None = None
    progress_message: str | None = None


class JobDetail(BaseModel):
    """Response from GET /jobs/{id}."""

    job_id: str
    status: str
    input_file: str
    created_at: datetime
    updated_at: datetime
    stages: dict[str, StageDetail]
    error: str | None = None


class JobSummaryItem(BaseModel):
    """Single entry in the jobs list."""

    job_id: str
    status: str
    created: str
    stages: dict[str, str]


class JobList(BaseModel):
    """Response from GET /jobs."""

    jobs: list[JobSummaryItem]


class ResumeResult(BaseModel):
    """Response from POST /jobs/{id}/resume."""

    job_id: str
    status: str
    message: str
    started: bool = True
    completed: bool = False
    rejected: bool = False


class ResumableJobItem(BaseModel):
    """Single entry in the resumable jobs list."""

    job_id: str
    status: str
    resume_stage: str
    completed_stages: list[str] = Field(default_factory=list)
    failed_stages: list[str] = Field(default_factory=list)
    interrupted: bool = False


class ResumableJobsList(BaseModel):
    """Response from GET /jobs/resumable."""

    jobs: list[ResumableJobItem]


class DeleteJobResult(BaseModel):
    """Response from DELETE /jobs/{id}."""

    job_id: str
    deleted: bool
    message: str


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class ServiceError(Exception):
    """Base exception for service client errors."""


class ServiceUnavailableError(ServiceError):
    """Raised when the backend cannot be reached."""

    def __init__(self, base_url: str, cause: Exception | None = None) -> None:
        self.base_url = base_url
        self.cause = cause
        super().__init__(f"Backend service unavailable at {base_url}")


class ServiceResponseError(ServiceError):
    """Raised when the backend returns an unexpected HTTP status."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Service error {status_code}: {detail}")


class ServiceBadRequestError(ServiceResponseError):
    """Raised for HTTP 400 responses."""


class ServiceUnauthorizedError(ServiceResponseError):
    """Raised for HTTP 401 responses."""


class ServiceForbiddenError(ServiceResponseError):
    """Raised for HTTP 403 responses."""


class ServiceNotFoundError(ServiceResponseError):
    """Raised for HTTP 404 responses."""


class ServiceConflictError(ServiceResponseError):
    """Raised for HTTP 409 responses."""


class ServiceValidationError(ServiceResponseError):
    """Raised for HTTP 422 responses."""


class ServiceTimeoutError(ServiceError):
    """Raised when a request exceeds the configured timeout."""

    def __init__(
        self,
        base_url: str,
        *,
        method: str,
        path: str,
        timeout_seconds: float,
        cause: Exception | None = None,
    ) -> None:
        self.base_url = base_url
        self.method = method
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.cause = cause
        super().__init__(
            f"Service request timed out after {timeout_seconds:.1f}s: "
            f"{method.upper()} {base_url}{path}"
        )


STATUS_ERROR_MAP: dict[int, type[ServiceResponseError]] = {
    400: ServiceBadRequestError,
    401: ServiceUnauthorizedError,
    403: ServiceForbiddenError,
    404: ServiceNotFoundError,
    409: ServiceConflictError,
    422: ServiceValidationError,
}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ServiceClient:
    """Typed HTTP client for the podcast-pipeline backend service.

    Parameters
    ----------
    base_url:
        Root URL of the backend (default ``http://127.0.0.1:8787``).
    timeout:
        Request timeout in seconds (default 30).
    retries:
        Number of retries on connection errors (default 2).
    run_timeout:
        Timeout for synchronous ``run_job`` requests (defaults to 900s minimum).
    resume_timeout:
        Timeout for synchronous ``resume_job`` requests (defaults to 900s minimum).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        run_timeout: float | None = None,
        resume_timeout: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.run_timeout = run_timeout or max(timeout, DEFAULT_RUN_TIMEOUT_SECONDS)
        self.resume_timeout = resume_timeout or max(timeout, DEFAULT_RESUME_TIMEOUT_SECONDS)
        self._http_client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        """Create a configured HTTPX client for this backend."""
        transport = httpx.HTTPTransport(retries=self.retries)
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
        )

    def _get_client(self) -> httpx.Client:
        """Create and cache a persistent HTTPX client."""
        if self._http_client is None:
            self._http_client = self._client()
        return self._http_client

    def close(self) -> None:
        """Close the persistent HTTPX client if it exists."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def __enter__(self) -> ServiceClient:
        self._get_client()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        """Raise ``ServiceResponseError`` for non-2xx responses."""
        if resp.is_success:
            return
        try:
            payload = resp.json()
            detail = payload.get("detail", payload)
        except Exception:
            detail = resp.text
        error_cls = STATUS_ERROR_MAP.get(resp.status_code, ServiceResponseError)
        raise error_cls(resp.status_code, detail)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Execute a request with connection-error wrapping.

        Converts connectivity and timeout errors into typed client errors.
        """
        timeout_seconds = timeout if timeout is not None else self.timeout
        try:
            resp = self._get_client().request(
                method,
                path,
                json=json,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ServiceTimeoutError(
                self.base_url,
                method=method,
                path=path,
                timeout_seconds=float(timeout_seconds),
                cause=exc,
            ) from exc
        except httpx.ConnectError as exc:
            raise ServiceUnavailableError(self.base_url, cause=exc) from exc
        return resp

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health(self) -> HealthStatus:
        """Check backend health (GET /health)."""
        resp = self._request("GET", "/health")
        self._raise_for_status(resp)
        return HealthStatus.model_validate(resp.json())

    def is_available(self) -> bool:
        """Return True if the backend health endpoint responds."""
        try:
            self.health()
        except ServiceError:
            return False
        return True

    def create_job(self, video_path: str, name: str | None = None) -> CreatedJob:
        """Create a new pipeline job (POST /jobs)."""
        payload: dict[str, object] = {"video_path": video_path}
        if name is not None:
            payload["name"] = name
        resp = self._request("POST", "/jobs", json=payload)
        self._raise_for_status(resp)
        return CreatedJob.model_validate(resp.json())

    def get_job(self, job_id: str) -> JobDetail:
        """Fetch full job detail (GET /jobs/{id})."""
        resp = self._request("GET", f"/jobs/{job_id}")
        self._raise_for_status(resp)
        return JobDetail.model_validate(resp.json())

    def list_jobs(self) -> JobList:
        """List all jobs (GET /jobs)."""
        resp = self._request("GET", "/jobs")
        self._raise_for_status(resp)
        return JobList.model_validate(resp.json())

    def run_job(
        self,
        job_id: str,
        *,
        stage: str | None = None,
        until_stage: str | None = None,
        quality_controls: dict[str, object] | None = None,
    ) -> RunResult:
        """Trigger a synchronous pipeline run (POST /jobs/{id}/run)."""
        payload: dict[str, object] = {}
        if stage is not None:
            payload["stage"] = stage
        if until_stage is not None:
            payload["until_stage"] = until_stage
        if quality_controls is not None:
            payload["quality_controls"] = quality_controls
        resp = self._request(
            "POST",
            f"/jobs/{job_id}/run",
            json=payload,
            timeout=self.run_timeout,
        )
        self._raise_for_status(resp)
        return RunResult.model_validate(resp.json())

    def run_job_background(
        self,
        job_id: str,
        *,
        stage: str | None = None,
        until_stage: str | None = None,
    ) -> BackgroundRunResult:
        """Start a background pipeline run (POST /jobs/{id}/run/background)."""
        payload: dict[str, object] = {}
        if stage is not None:
            payload["stage"] = stage
        if until_stage is not None:
            payload["until_stage"] = until_stage
        resp = self._request(
            "POST",
            f"/jobs/{job_id}/run/background",
            json=payload,
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return BackgroundRunResult.model_validate(resp.json())

    def resume_job(
        self,
        job_id: str,
        *,
        from_stage: str | None = None,
        until_stage: str | None = None,
        background: bool = False,
    ) -> ResumeResult:
        """Resume a paused/failed job (POST /jobs/{id}/resume)."""
        payload: dict[str, object] = {"background": background}
        if from_stage is not None:
            payload["from_stage"] = from_stage
        if until_stage is not None:
            payload["until_stage"] = until_stage
        timeout = self.timeout if background else self.resume_timeout
        resp = self._request(
            "POST",
            f"/jobs/{job_id}/resume",
            json=payload,
            timeout=timeout,
        )
        self._raise_for_status(resp)
        return ResumeResult.model_validate(resp.json())

    def list_resumable_jobs(self) -> ResumableJobsList:
        """Fetch jobs that can be resumed (GET /jobs/resumable).

        The backend reconciles stale runtime metadata before returning
        the list, so results reflect actual resumability.
        """
        resp = self._request("GET", "/jobs/resumable")
        self._raise_for_status(resp)
        return ResumableJobsList.model_validate(resp.json())

    def reconcile_jobs(self) -> int:
        """Force reconciliation of all job runtime metadata (POST /jobs/reconcile).

        Returns the number of jobs that had corrections applied.
        """
        resp = self._request("POST", "/jobs/reconcile")
        self._raise_for_status(resp)
        data: dict[str, int] = resp.json()
        return data.get("corrected", 0)

    def delete_job(self, job_id: str) -> DeleteJobResult:
        """Delete a job and its managed artifacts (DELETE /jobs/{id})."""
        resp = self._request("DELETE", f"/jobs/{job_id}")
        self._raise_for_status(resp)
        return DeleteJobResult.model_validate(resp.json())
