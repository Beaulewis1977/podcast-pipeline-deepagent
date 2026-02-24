"""Regression tests for runtime asset resolution and system readiness endpoints.

Tests cover:
- Binary path resolution (env, sidecar, PATH, unknown, missing)
- Model cache discovery (env, app_data, project, HuggingFace hub)
- System status endpoint (combined readiness)
- Single binary check endpoint
- Model warmup endpoint (already cached vs missing)
- Edge cases: bad env overrides, empty dirs, wrong names
"""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from podcast_pipeline.service.assets import (
    _BINARY_REGISTRY,
    AssetStatus,
    BinaryInfo,
    ModelInfo,
    get_model_cache_dir,
    resolve_all_binaries,
    resolve_binary,
    resolve_model,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executable(path: Path) -> None:
    """Create a dummy executable file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _make_model_dir(path: Path, *, with_files: bool = True) -> None:
    """Create a directory that looks like a faster-whisper model cache."""
    path.mkdir(parents=True, exist_ok=True)
    if with_files:
        (path / "model.bin").write_bytes(b"fake model data")
        (path / "config.json").write_text('{"model": "test"}')


# ---------------------------------------------------------------------------
# Binary resolution tests
# ---------------------------------------------------------------------------


class TestResolveBinary:
    """Tests for resolve_binary and resolve_all_binaries."""

    def test_unknown_binary_returns_error_status(self):
        """Requesting an unregistered binary name returns ERROR status."""
        info = resolve_binary("nonexistent-tool")
        assert info.status == AssetStatus.ERROR
        assert info.source == "unknown_binary"
        assert info.path is None

    def test_missing_binary_returns_missing_status(self, monkeypatch):
        """Binary not found anywhere returns MISSING status."""
        # Clear env vars so no override
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        # Patch sidecar and PATH to return nothing
        with (
            patch("podcast_pipeline.service.assets._resolve_from_sidecar", return_value=None),
            patch("podcast_pipeline.service.assets._resolve_from_path", return_value=None),
        ):
            info = resolve_binary("ffmpeg")
            assert info.status == AssetStatus.MISSING
            assert info.source == "missing"
            assert info.path is None

    def test_env_override_resolves_binary(self, tmp_path, monkeypatch):
        """Binary found via explicit env var override returns READY."""
        fake_binary = tmp_path / "ffmpeg"
        _make_executable(fake_binary)

        monkeypatch.setenv("FFMPEG_PATH", str(fake_binary))
        info = resolve_binary("ffmpeg")
        assert info.status == AssetStatus.READY
        assert info.source == "env"
        assert info.path == str(fake_binary)

    def test_bad_env_override_falls_through(self, tmp_path, monkeypatch):
        """Env var pointing to non-existent file falls through to next resolver."""
        monkeypatch.setenv("FFMPEG_PATH", "/does/not/exist/ffmpeg")
        with (
            patch("podcast_pipeline.service.assets._resolve_from_sidecar", return_value=None),
            patch("podcast_pipeline.service.assets._resolve_from_path", return_value=None),
        ):
            info = resolve_binary("ffmpeg")
            assert info.status == AssetStatus.MISSING

    def test_sidecar_resolves_binary(self, tmp_path, monkeypatch):
        """Binary found in sidecar directory returns READY with source=sidecar."""
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        fake_path = tmp_path / "ffmpeg"
        _make_executable(fake_path)

        with (
            patch(
                "podcast_pipeline.service.assets._resolve_from_sidecar",
                return_value=fake_path,
            ),
        ):
            info = resolve_binary("ffmpeg")
            assert info.status == AssetStatus.READY
            assert info.source == "sidecar"

    def test_path_resolves_binary(self, tmp_path, monkeypatch):
        """Binary found via system PATH returns READY with source=path."""
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        fake_path = tmp_path / "ffmpeg"
        _make_executable(fake_path)

        with (
            patch("podcast_pipeline.service.assets._resolve_from_sidecar", return_value=None),
            patch(
                "podcast_pipeline.service.assets._resolve_from_path",
                return_value=fake_path,
            ),
        ):
            info = resolve_binary("ffmpeg")
            assert info.status == AssetStatus.READY
            assert info.source == "path"

    def test_resolve_all_binaries_returns_all_registered(self, monkeypatch):
        """resolve_all_binaries returns an entry for every registered binary."""
        # Patch all resolvers to return missing
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        monkeypatch.delenv("FFPROBE_PATH", raising=False)
        monkeypatch.delenv("BACKEND_BIN", raising=False)
        with (
            patch("podcast_pipeline.service.assets._resolve_from_sidecar", return_value=None),
            patch("podcast_pipeline.service.assets._resolve_from_path", return_value=None),
        ):
            result = resolve_all_binaries()
            assert set(result.keys()) == set(_BINARY_REGISTRY.keys())
            for name, info in result.items():
                assert isinstance(info, BinaryInfo)
                assert info.name == name

    def test_env_override_priority_over_sidecar(self, tmp_path, monkeypatch):
        """Env var override takes priority over sidecar directory."""
        env_binary = tmp_path / "env_ffmpeg"
        _make_executable(env_binary)

        sidecar_binary = tmp_path / "sidecar_ffmpeg"
        _make_executable(sidecar_binary)

        monkeypatch.setenv("FFMPEG_PATH", str(env_binary))
        with patch(
            "podcast_pipeline.service.assets._resolve_from_sidecar",
            return_value=sidecar_binary,
        ):
            info = resolve_binary("ffmpeg")
            assert info.source == "env"
            assert info.path == str(env_binary)


# ---------------------------------------------------------------------------
# Model resolution tests
# ---------------------------------------------------------------------------


class TestResolveModel:
    """Tests for resolve_model and model cache discovery."""

    def test_model_not_found_returns_missing(self, monkeypatch):
        """Model not cached anywhere returns MISSING status."""
        monkeypatch.delenv("WHISPER_MODEL_DIR", raising=False)
        monkeypatch.delenv("PODCAST_PIPELINE_DATA_DIR", raising=False)
        monkeypatch.delenv("HF_HOME", raising=False)
        # Point HF_HOME to a temp empty dir
        monkeypatch.setenv("HF_HOME", str(Path("/tmp/nonexistent_hf_cache_dir")))

        with patch(
            "podcast_pipeline.service.assets._model_cache_search_paths",
            return_value=[],
        ):
            info = resolve_model("large-v3")
            assert info.status == AssetStatus.MISSING
            assert info.source == "missing"

    def test_model_found_via_env_dir(self, tmp_path, monkeypatch):
        """Model found via WHISPER_MODEL_DIR env returns READY."""
        model_dir = tmp_path / "models" / "large-v3"
        _make_model_dir(model_dir)

        monkeypatch.setenv("WHISPER_MODEL_DIR", str(tmp_path / "models"))
        monkeypatch.delenv("PODCAST_PIPELINE_DATA_DIR", raising=False)
        monkeypatch.delenv("HF_HOME", raising=False)

        with patch(
            "podcast_pipeline.service.assets._model_cache_search_paths",
            return_value=[("env", tmp_path / "models")],
        ):
            info = resolve_model("large-v3")
            assert info.status == AssetStatus.READY
            assert info.source == "env"
            assert info.path is not None

    def test_model_found_via_huggingface_hub_layout(self, tmp_path, monkeypatch):
        """Model found in HuggingFace hub cache layout returns READY."""
        hf_dir = tmp_path / "hub"
        snapshot_dir = hf_dir / "models--Systran--faster-whisper-large-v3" / "snapshots" / "abc123"
        _make_model_dir(snapshot_dir)

        with patch(
            "podcast_pipeline.service.assets._model_cache_search_paths",
            return_value=[("cache", hf_dir)],
        ):
            info = resolve_model("large-v3")
            assert info.status == AssetStatus.READY
            assert info.source == "cache"

    def test_model_empty_dir_not_ready(self, tmp_path, monkeypatch):
        """Directory without model.bin or config.json is not considered ready."""
        model_dir = tmp_path / "models" / "large-v3"
        _make_model_dir(model_dir, with_files=False)

        with patch(
            "podcast_pipeline.service.assets._model_cache_search_paths",
            return_value=[("env", tmp_path / "models")],
        ):
            info = resolve_model("large-v3")
            assert info.status == AssetStatus.MISSING

    def test_model_found_via_app_data(self, tmp_path, monkeypatch):
        """Model found in PODCAST_PIPELINE_DATA_DIR/models returns READY."""
        model_dir = tmp_path / "app_data" / "models" / "large-v3"
        _make_model_dir(model_dir)

        with patch(
            "podcast_pipeline.service.assets._model_cache_search_paths",
            return_value=[("app_data", tmp_path / "app_data" / "models")],
        ):
            info = resolve_model("large-v3")
            assert info.status == AssetStatus.READY
            assert info.source == "app_data"

    def test_default_model_name(self):
        """resolve_model with None defaults to large-v3."""
        with patch(
            "podcast_pipeline.service.assets._model_cache_search_paths",
            return_value=[],
        ):
            info = resolve_model(None)
            assert info.name == "large-v3"

    def test_model_size_bytes_reported(self, tmp_path):
        """Ready model includes size_bytes estimate."""
        model_dir = tmp_path / "models" / "large-v3"
        _make_model_dir(model_dir)

        with patch(
            "podcast_pipeline.service.assets._model_cache_search_paths",
            return_value=[("env", tmp_path / "models")],
        ):
            info = resolve_model("large-v3")
            assert info.status == AssetStatus.READY
            assert info.size_bytes is not None
            assert info.size_bytes > 0


# ---------------------------------------------------------------------------
# Model cache directory tests
# ---------------------------------------------------------------------------


class TestGetModelCacheDir:
    """Tests for get_model_cache_dir preferred writable directory."""

    def test_env_override(self, tmp_path, monkeypatch):
        """WHISPER_MODEL_DIR is preferred when set."""
        target = tmp_path / "custom_models"
        monkeypatch.setenv("WHISPER_MODEL_DIR", str(target))
        result = get_model_cache_dir()
        assert result == target
        assert target.exists()

    def test_app_data_fallback(self, tmp_path, monkeypatch):
        """PODCAST_PIPELINE_DATA_DIR/models used when WHISPER_MODEL_DIR not set."""
        monkeypatch.delenv("WHISPER_MODEL_DIR", raising=False)
        monkeypatch.setenv("PODCAST_PIPELINE_DATA_DIR", str(tmp_path / "appdata"))
        result = get_model_cache_dir()
        assert result == tmp_path / "appdata" / "models"
        assert result.exists()

    def test_cwd_fallback(self, tmp_path, monkeypatch):
        """Falls back to ./models relative to CWD."""
        monkeypatch.delenv("WHISPER_MODEL_DIR", raising=False)
        monkeypatch.delenv("PODCAST_PIPELINE_DATA_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        result = get_model_cache_dir()
        assert result == tmp_path / "models"
        assert result.exists()


# ---------------------------------------------------------------------------
# System endpoint tests (via TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client():
    """FastAPI TestClient with mocked lifespan (no real pipeline needed)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from podcast_pipeline.service.routes.system import router as system_router

    app = FastAPI()
    app.include_router(system_router, prefix="/system")
    return TestClient(app)


class TestSystemStatusEndpoint:
    """Tests for GET /system/status."""

    def test_status_all_ready(self, app_client):
        """All binaries + model ready returns ready=True."""
        fake_binaries = {
            "ffmpeg": BinaryInfo(
                name="ffmpeg", path="/usr/bin/ffmpeg", status=AssetStatus.READY, source="path"
            ),
            "ffprobe": BinaryInfo(
                name="ffprobe", path="/usr/bin/ffprobe", status=AssetStatus.READY, source="path"
            ),
            "podcast-backend": BinaryInfo(
                name="podcast-backend",
                path="/usr/bin/podcast-backend",
                status=AssetStatus.READY,
                source="path",
            ),
        }
        fake_model = ModelInfo(
            name="large-v3", path="/cache/model", status=AssetStatus.READY, source="cache"
        )

        with (
            patch(
                "podcast_pipeline.service.routes.system.resolve_all_binaries",
                return_value=fake_binaries,
            ),
            patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_model),
        ):
            resp = app_client.get("/system/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is True
            assert len(data["issues"]) == 0

    def test_status_missing_binary(self, app_client):
        """Missing required binary results in ready=False and issue listed."""
        fake_binaries = {
            "ffmpeg": BinaryInfo(name="ffmpeg", status=AssetStatus.MISSING, source="missing"),
            "ffprobe": BinaryInfo(
                name="ffprobe", path="/usr/bin/ffprobe", status=AssetStatus.READY, source="path"
            ),
            "podcast-backend": BinaryInfo(
                name="podcast-backend",
                path="/usr/bin/podcast-backend",
                status=AssetStatus.READY,
                source="path",
            ),
        }
        fake_model = ModelInfo(
            name="large-v3", path="/cache/model", status=AssetStatus.READY, source="cache"
        )

        with (
            patch(
                "podcast_pipeline.service.routes.system.resolve_all_binaries",
                return_value=fake_binaries,
            ),
            patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_model),
        ):
            resp = app_client.get("/system/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is False
            assert any("ffmpeg" in issue for issue in data["issues"])

    def test_status_missing_model(self, app_client):
        """Missing whisper model results in ready=False and issue listed."""
        fake_binaries = {
            "ffmpeg": BinaryInfo(
                name="ffmpeg", path="/usr/bin/ffmpeg", status=AssetStatus.READY, source="path"
            ),
            "ffprobe": BinaryInfo(
                name="ffprobe", path="/usr/bin/ffprobe", status=AssetStatus.READY, source="path"
            ),
            "podcast-backend": BinaryInfo(
                name="podcast-backend",
                path="/usr/bin/podcast-backend",
                status=AssetStatus.READY,
                source="path",
            ),
        }
        fake_model = ModelInfo(name="large-v3", status=AssetStatus.MISSING, source="missing")

        with (
            patch(
                "podcast_pipeline.service.routes.system.resolve_all_binaries",
                return_value=fake_binaries,
            ),
            patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_model),
        ):
            resp = app_client.get("/system/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is False
            assert any("model" in issue.lower() for issue in data["issues"])


class TestBinaryCheckEndpoint:
    """Tests for GET /system/binaries/{name}."""

    def test_check_existing_binary(self, app_client):
        """Known binary that exists returns ready=True."""
        fake_info = BinaryInfo(
            name="ffmpeg", path="/usr/bin/ffmpeg", status=AssetStatus.READY, source="path"
        )
        with patch("podcast_pipeline.service.routes.system.resolve_binary", return_value=fake_info):
            resp = app_client.get("/system/binaries/ffmpeg")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is True
            assert data["name"] == "ffmpeg"

    def test_check_missing_binary(self, app_client):
        """Known binary that is missing returns ready=False."""
        fake_info = BinaryInfo(name="ffmpeg", status=AssetStatus.MISSING, source="missing")
        with patch("podcast_pipeline.service.routes.system.resolve_binary", return_value=fake_info):
            resp = app_client.get("/system/binaries/ffmpeg")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is False

    def test_check_unknown_binary(self, app_client):
        """Unknown binary name returns ready=False with descriptive message."""
        fake_info = BinaryInfo(name="unknown", status=AssetStatus.ERROR, source="unknown_binary")
        with patch("podcast_pipeline.service.routes.system.resolve_binary", return_value=fake_info):
            resp = app_client.get("/system/binaries/unknown")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is False
            assert "unknown" in data["message"].lower()


class TestModelWarmupEndpoint:
    """Tests for POST /system/models/warmup."""

    def test_model_warmup_already_cached(self, app_client):
        """Model already cached returns status=ready immediately."""
        fake_info = ModelInfo(
            name="large-v3", path="/cache/model", status=AssetStatus.READY, source="cache"
        )
        with patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_info):
            resp = app_client.post("/system/models/warmup", json={"model_name": "large-v3"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ready"
            assert data["model_name"] == "large-v3"

    def test_model_warmup_triggers_download(self, app_client):
        """Missing model triggers download and returns status=downloading."""
        fake_info = ModelInfo(name="large-v3", status=AssetStatus.MISSING, source="missing")

        # Reset download tracking state
        from podcast_pipeline.service.routes import system as sys_mod

        sys_mod._download_tasks.clear()

        with (
            patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_info),
            patch("podcast_pipeline.service.routes.system._download_model", return_value=None),
        ):
            resp = app_client.post("/system/models/warmup", json={"model_name": "large-v3"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "downloading"
            assert data["model_name"] == "large-v3"

    def test_model_warmup_default_name(self, app_client):
        """Warmup without explicit model_name uses default (large-v3)."""
        fake_info = ModelInfo(
            name="large-v3", path="/cache/model", status=AssetStatus.READY, source="cache"
        )
        with patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_info):
            resp = app_client.post("/system/models/warmup", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["model_name"] == "large-v3"


class TestModelCheckEndpoint:
    """Tests for GET /system/models/{model_name}."""

    def test_check_cached_model(self, app_client):
        """Cached model returns READY status."""
        fake_info = ModelInfo(
            name="large-v3",
            path="/cache/model",
            status=AssetStatus.READY,
            source="cache",
            size_bytes=1024,
        )
        with patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_info):
            resp = app_client.get("/system/models/large-v3")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ready"
            assert data["name"] == "large-v3"

    def test_check_missing_model(self, app_client):
        """Missing model returns MISSING status."""
        fake_info = ModelInfo(name="tiny", status=AssetStatus.MISSING, source="missing")
        with patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_info):
            resp = app_client.get("/system/models/tiny")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "missing"


class TestWarmupStatusEndpoint:
    """Tests for GET /system/models/warmup/status."""

    def test_warmup_status_empty(self, app_client):
        """No active downloads returns empty dict."""
        from podcast_pipeline.service.routes import system as sys_mod

        sys_mod._download_tasks.clear()

        resp = app_client.get("/system/models/warmup/status")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_warmup_status_with_active_download(self, app_client):
        """Active download task appears in status response."""
        from podcast_pipeline.service.routes import system as sys_mod

        sys_mod._download_tasks.clear()
        sys_mod._download_tasks["large-v3"] = "downloading"

        fake_info = ModelInfo(name="large-v3", status=AssetStatus.MISSING, source="missing")
        with patch("podcast_pipeline.service.routes.system.resolve_model", return_value=fake_info):
            resp = app_client.get("/system/models/warmup/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "large-v3" in data
            assert data["large-v3"]["download_status"] == "downloading"

        # Clean up
        sys_mod._download_tasks.clear()
