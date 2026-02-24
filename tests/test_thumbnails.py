"""Tests for AI thumbnail generation service (09-09)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """Temporary thumbnail output directory."""
    out = tmp_path / "thumbnails"
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture
def fake_branding():
    """Minimal mock BrandingProfile-like object."""
    bp = MagicMock()
    bp.logo_path = None  # no logo by default
    bp.logo_placement = "top_right"
    bp.logo_opacity = 0.8
    bp.thumbnail_border = MagicMock(color="#000000", width=10)
    return bp


# ---------------------------------------------------------------------------
# Cache key tests
# ---------------------------------------------------------------------------


class TestCacheKey:
    """Prompt-hash caching prevents duplicate thumbnail generation."""

    def test_same_params_same_key(self):
        from podcast_pipeline.utils.thumbnails import compute_cache_key

        k1 = compute_cache_key("hello", "model-x", 1280, 720, seed=42, index=0)
        k2 = compute_cache_key("hello", "model-x", 1280, 720, seed=42, index=0)
        assert k1 == k2

    def test_different_prompt_different_key(self):
        from podcast_pipeline.utils.thumbnails import compute_cache_key

        k1 = compute_cache_key("hello", "model-x", 1280, 720, seed=42, index=0)
        k2 = compute_cache_key("world", "model-x", 1280, 720, seed=42, index=0)
        assert k1 != k2

    def test_different_model_different_key(self):
        from podcast_pipeline.utils.thumbnails import compute_cache_key

        k1 = compute_cache_key("hello", "model-a", 1280, 720, seed=None, index=0)
        k2 = compute_cache_key("hello", "model-b", 1280, 720, seed=None, index=0)
        assert k1 != k2

    def test_different_seed_different_key(self):
        from podcast_pipeline.utils.thumbnails import compute_cache_key

        k1 = compute_cache_key("hello", "model-x", 1280, 720, seed=1, index=0)
        k2 = compute_cache_key("hello", "model-x", 1280, 720, seed=2, index=0)
        assert k1 != k2

    def test_none_seed_distinct_from_zero(self):
        from podcast_pipeline.utils.thumbnails import compute_cache_key

        k1 = compute_cache_key("hello", "model-x", 1280, 720, seed=None, index=0)
        k2 = compute_cache_key("hello", "model-x", 1280, 720, seed=0, index=0)
        assert k1 != k2

    def test_key_is_16_hex_chars(self):
        from podcast_pipeline.utils.thumbnails import compute_cache_key

        key = compute_cache_key("test", "m", 1280, 720, seed=None, index=0)
        assert len(key) == 16
        assert all(c in "0123456789abcdef" for c in key)

    def test_different_index_different_key(self):
        from podcast_pipeline.utils.thumbnails import compute_cache_key

        k1 = compute_cache_key("hello", "model-x", 1280, 720, seed=42, index=0)
        k2 = compute_cache_key("hello", "model-x", 1280, 720, seed=42, index=1)
        assert k1 != k2


# ---------------------------------------------------------------------------
# Cache hit / skip tests
# ---------------------------------------------------------------------------


class TestCacheHit:
    """Cache hits avoid re-generation and billing."""

    def test_cache_hit_returns_cached_artifact(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailRequest,
            ThumbnailService,
            ThumbnailStatus,
            compute_cache_key,
        )

        prompt = "podcast host on stage"
        model = "imagen-4.0-generate-001"
        key = compute_cache_key(prompt, model, 1280, 720, seed=None, index=0)
        cached_file = tmp_output / f"{key}.jpg"
        cached_file.write_bytes(b"FAKEJPEG")

        service = ThumbnailService()
        request = ThumbnailRequest(
            prompts=[prompt],
            output_dir=tmp_output,
            images_per_prompt=1,
            model=model,
        )

        # Backend selection will fail (no credentials) but cache hit should
        # short-circuit before any backend call.
        # Patch _select_backend to return IMAGEN4 to exercise cache path.
        from podcast_pipeline.utils.thumbnails import ThumbnailBackend

        with patch.object(
            service,
            "_select_backend",
            return_value=(ThumbnailBackend.IMAGEN4, ""),
        ):
            result = service.generate(request)

        assert result.total_cached == 1
        assert result.total_generated == 0
        assert result.artifacts[0].status == ThumbnailStatus.CACHED
        assert result.artifacts[0].cache_hit is True

    def test_empty_cache_file_triggers_regeneration(self, tmp_output: Path):
        """A zero-byte cache file must not be treated as a valid cache hit."""
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
            compute_cache_key,
        )

        prompt = "empty cache test"
        model = "imagen-4.0-generate-001"
        key = compute_cache_key(prompt, model, 1280, 720, seed=None, index=0)
        empty_file = tmp_output / f"{key}.jpg"
        empty_file.write_bytes(b"")  # zero-byte — should NOT be treated as cache hit

        service = ThumbnailService()
        request = ThumbnailRequest(prompts=[prompt], output_dir=tmp_output)

        # Patch _run_backend to return a dummy file so generation 'succeeds'
        def fake_run_backend(*_args: object, **_kwargs: object) -> list[tuple[Path, bool]]:
            dummy = tmp_output / "dummy.jpg"
            dummy.write_bytes(b"FAKEJPEG")
            return [(dummy, False)]

        with (
            patch.object(
                service,
                "_select_backend",
                return_value=(ThumbnailBackend.IMAGEN4, ""),
            ),
            patch.object(service, "_run_backend", side_effect=fake_run_backend),
        ):
            result = service.generate(request)

        # Zero-byte cache files must trigger generation, not cache hit
        assert result.total_generated == 1
        assert result.total_cached == 0


# ---------------------------------------------------------------------------
# Backend selection tests
# ---------------------------------------------------------------------------


class TestBackendSelection:
    """Backend routing respects availability and fallback order."""

    def test_imagen4_selected_when_credentials_available(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import ThumbnailBackend, ThumbnailService

        with (
            patch(
                "podcast_pipeline.utils.thumbnails._imagen4_available",
                return_value=(True, ""),
            ),
        ):
            service = ThumbnailService()
            from podcast_pipeline.utils.thumbnails import ThumbnailRequest

            request = ThumbnailRequest(
                prompts=["test"],
                output_dir=tmp_output,
                project_id="my-project",
            )
            backend, reason = service._select_backend(request)

        assert backend == ThumbnailBackend.IMAGEN4
        assert reason == ""

    def test_flux_fallback_when_imagen4_unavailable(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import ThumbnailBackend, ThumbnailService

        with (
            patch(
                "podcast_pipeline.utils.thumbnails._imagen4_available",
                return_value=(False, "no project"),
            ),
            patch(
                "podcast_pipeline.utils.thumbnails._flux_available",
                return_value=(True, ""),
            ),
            patch(
                "podcast_pipeline.utils.thumbnails.check_vram_preflight",
                return_value=(True, ""),
            ),
        ):
            service = ThumbnailService()
            from podcast_pipeline.utils.thumbnails import ThumbnailRequest

            request = ThumbnailRequest(prompts=["test"], output_dir=tmp_output)
            backend, _reason = service._select_backend(request)

        assert backend == ThumbnailBackend.FLUX

    def test_none_backend_when_both_unavailable(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import ThumbnailBackend, ThumbnailService

        with (
            patch(
                "podcast_pipeline.utils.thumbnails._imagen4_available",
                return_value=(False, "no creds"),
            ),
            patch(
                "podcast_pipeline.utils.thumbnails._flux_available",
                return_value=(False, "diffusers missing"),
            ),
        ):
            service = ThumbnailService()
            from podcast_pipeline.utils.thumbnails import ThumbnailRequest

            request = ThumbnailRequest(prompts=["test"], output_dir=tmp_output)
            backend, reason = service._select_backend(request)

        assert backend == ThumbnailBackend.NONE
        assert "No thumbnail backend" in reason

    def test_none_backend_when_flux_vram_insufficient(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import ThumbnailBackend, ThumbnailService

        with (
            patch(
                "podcast_pipeline.utils.thumbnails._imagen4_available",
                return_value=(False, "no project"),
            ),
            patch(
                "podcast_pipeline.utils.thumbnails._flux_available",
                return_value=(True, ""),
            ),
            patch(
                "podcast_pipeline.utils.thumbnails.check_vram_preflight",
                return_value=(False, "only 8 GiB free"),
            ),
        ):
            service = ThumbnailService()
            from podcast_pipeline.utils.thumbnails import ThumbnailRequest

            request = ThumbnailRequest(prompts=["test"], output_dir=tmp_output)
            backend, reason = service._select_backend(request)

        assert backend == ThumbnailBackend.NONE
        assert "VRAM" in reason


# ---------------------------------------------------------------------------
# Graceful degradation when no backend available
# ---------------------------------------------------------------------------


class TestDegradedMode:
    """Service skips gracefully when no backend is available."""

    def test_no_backend_returns_degraded_result(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
        )

        with (
            patch(
                "podcast_pipeline.utils.thumbnails._imagen4_available",
                return_value=(False, "missing creds"),
            ),
            patch(
                "podcast_pipeline.utils.thumbnails._flux_available",
                return_value=(False, "no diffusers"),
            ),
        ):
            service = ThumbnailService()
            result = service.generate(
                ThumbnailRequest(prompts=["test prompt"], output_dir=tmp_output)
            )

        assert result.degraded is True
        assert result.backend_used == ThumbnailBackend.NONE
        assert len(result.artifacts) == 0
        assert result.total_generated == 0


# ---------------------------------------------------------------------------
# VRAM preflight tests
# ---------------------------------------------------------------------------


class TestVramPreflight:
    """VRAM preflight raises explicit diagnostics before loading FLUX."""

    def test_vram_ok_when_sufficient(self):
        from podcast_pipeline.utils.thumbnails import check_vram_preflight

        with patch("podcast_pipeline.utils.thumbnails._free_vram_gib", return_value=16.0):
            ok, msg = check_vram_preflight(min_free_gib=14.0)

        assert ok is True
        assert msg == ""

    def test_vram_fail_when_insufficient(self):
        from podcast_pipeline.utils.thumbnails import check_vram_preflight

        with patch("podcast_pipeline.utils.thumbnails._free_vram_gib", return_value=6.0):
            ok, msg = check_vram_preflight(min_free_gib=14.0)

        assert ok is False
        assert "6.0 GiB free" in msg

    def test_vram_fail_when_cuda_unavailable(self):
        from podcast_pipeline.utils.thumbnails import check_vram_preflight

        with patch("podcast_pipeline.utils.thumbnails._free_vram_gib", return_value=None):
            ok, msg = check_vram_preflight()

        assert ok is False
        assert "CUDA" in msg or "torch" in msg

    def test_vram_fail_when_torch_missing(self):
        from podcast_pipeline.utils.thumbnails import check_vram_preflight

        with patch("podcast_pipeline.utils.thumbnails._free_vram_gib", return_value=None):
            ok, _msg = check_vram_preflight()

        assert ok is False


# ---------------------------------------------------------------------------
# Imagen 4 availability checks
# ---------------------------------------------------------------------------


class TestImagen4Availability:
    """Imagen 4 backend routing diagnostics."""

    def test_unavailable_when_package_missing(self):
        from podcast_pipeline.utils.thumbnails import _imagen4_available

        with patch.dict(sys.modules, {"google.cloud.aiplatform": None}):
            ok, _reason = _imagen4_available("my-project", "us-central1")

        assert ok is False

    def test_unavailable_when_no_project(self):
        """Missing project ID makes Imagen 4 unavailable."""
        from podcast_pipeline.utils.thumbnails import _imagen4_available

        # Remove env var to simulate missing project
        env_backup = os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        try:
            mock_aiplatform = MagicMock()
            with patch.dict(sys.modules, {"google.cloud.aiplatform": mock_aiplatform}):
                ok, reason = _imagen4_available(None, "us-central1")
        finally:
            if env_backup is not None:
                os.environ["GOOGLE_CLOUD_PROJECT"] = env_backup

        assert ok is False
        assert "GOOGLE_CLOUD_PROJECT" in reason or "project_id" in reason


# ---------------------------------------------------------------------------
# FLUX availability checks
# ---------------------------------------------------------------------------


class TestFluxAvailability:
    """FLUX.1 Schnell backend routing diagnostics."""

    def test_unavailable_when_diffusers_missing(self):
        from podcast_pipeline.utils.thumbnails import _flux_available

        with patch(
            "podcast_pipeline.utils.thumbnails.importlib.util.find_spec",
            side_effect=lambda name: None,  # nothing found
        ):
            ok, reason = _flux_available()

        assert ok is False
        assert "diffusers" in reason

    def test_available_when_diffusers_and_quanto_present(self):
        from podcast_pipeline.utils.thumbnails import _flux_available

        def _fake_find_spec(name: str) -> MagicMock | None:
            if name in ("diffusers", "optimum.quanto"):
                return MagicMock()
            return None

        with patch(
            "podcast_pipeline.utils.thumbnails.importlib.util.find_spec",
            side_effect=_fake_find_spec,
        ):
            ok, _reason = _flux_available()

        assert ok is True


# ---------------------------------------------------------------------------
# Branding overlay integration
# ---------------------------------------------------------------------------


class TestBrandingOverlay:
    """Overlay integration uses toolkit overlay_image operation."""

    def test_overlay_skipped_when_no_logo(self, tmp_output: Path, fake_branding: MagicMock):
        from podcast_pipeline.utils.thumbnails import _apply_branding_overlay

        fake_branding.logo_path = None
        src = tmp_output / "thumb.jpg"
        src.write_bytes(b"FAKE")

        result = _apply_branding_overlay(src, fake_branding)

        # No logo — original path returned unchanged
        assert result == src

    def test_overlay_skipped_when_logo_missing_on_disk(
        self, tmp_output: Path, fake_branding: MagicMock
    ):
        from podcast_pipeline.utils.thumbnails import _apply_branding_overlay

        fake_branding.logo_path = tmp_output / "nonexistent_logo.png"
        src = tmp_output / "thumb.jpg"
        src.write_bytes(b"FAKE")

        result = _apply_branding_overlay(src, fake_branding)

        assert result == src

    def test_overlay_calls_toolkit_when_logo_exists(
        self, tmp_output: Path, fake_branding: MagicMock
    ):
        from podcast_pipeline.utils.thumbnails import _apply_branding_overlay

        # Create a fake logo file
        logo = tmp_output / "logo.png"
        logo.write_bytes(b"PNGDATA")
        fake_branding.logo_path = logo
        fake_branding.logo_placement = "top_right"
        fake_branding.logo_opacity = 0.8

        src = tmp_output / "thumb.jpg"
        src.write_bytes(b"FAKE")

        # The overlay_image function is imported inside _apply_branding_overlay;
        # patch the toolkit module directly.
        with patch("podcast_pipeline.utils.ffmpeg_toolkit.overlay_image") as mock_overlay:
            branded_out = tmp_output / "thumb_branded.jpg"
            branded_out.write_bytes(b"BRANDED")
            mock_overlay.return_value = MagicMock(output_path=branded_out)
            _apply_branding_overlay(src, fake_branding)

        mock_overlay.assert_called_once()
        # The call used a properly constructed request
        call_kwargs = mock_overlay.call_args[0][0]
        assert call_kwargs.image_path == logo

    def test_service_applies_branding_on_cache_hit(
        self, tmp_output: Path, fake_branding: MagicMock
    ):
        """Branding overlay is applied even to cache-hit images."""
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
            compute_cache_key,
        )

        prompt = "cache hit with branding"
        model = "imagen-4.0-generate-001"
        key = compute_cache_key(prompt, model, 1280, 720, seed=None, index=0)
        cached = tmp_output / f"{key}.jpg"
        cached.write_bytes(b"FAKEJPEG")

        fake_branding.logo_path = None  # no logo → overlay skipped

        service = ThumbnailService()
        request = ThumbnailRequest(
            prompts=[prompt],
            output_dir=tmp_output,
            branding_profile=fake_branding,
        )

        with patch.object(service, "_select_backend", return_value=(ThumbnailBackend.IMAGEN4, "")):
            result = service.generate(request)

        assert result.total_cached == 1
        # Branding was not applied (no logo) but artifact is returned
        assert result.artifacts[0].branded is False


# ---------------------------------------------------------------------------
# Prompt truncation
# ---------------------------------------------------------------------------


class TestPromptTruncation:
    """More than 5 prompts are silently truncated."""

    def test_more_than_5_prompts_truncated(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
        )

        prompts = [f"prompt {i}" for i in range(10)]
        service = ThumbnailService()

        with (
            patch.object(
                service,
                "_select_backend",
                return_value=(ThumbnailBackend.IMAGEN4, ""),
            ),
            patch.object(service, "_process_prompt") as mock_process,
        ):
            service.generate(ThumbnailRequest(prompts=prompts, output_dir=tmp_output))

        # Only 5 calls should have been made
        assert mock_process.call_count == 5


# ---------------------------------------------------------------------------
# Artifact metadata
# ---------------------------------------------------------------------------


class TestArtifactMetadata:
    """Generated artifact metadata is correctly populated."""

    def test_generated_artifact_has_correct_backend(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
            ThumbnailStatus,
        )

        service = ThumbnailService()
        request = ThumbnailRequest(prompts=["test"], output_dir=tmp_output)

        dummy_path = tmp_output / "dummy.jpg"
        dummy_path.write_bytes(b"FAKEJPEG")

        with (
            patch.object(
                service,
                "_select_backend",
                return_value=(ThumbnailBackend.FLUX, ""),
            ),
            patch.object(service, "_run_backend", return_value=[(dummy_path, False)]),
        ):
            result = service.generate(request)

        assert result.total_generated == 1
        assert result.artifacts[0].backend == ThumbnailBackend.FLUX
        assert result.artifacts[0].status == ThumbnailStatus.GENERATED
        assert result.artifacts[0].cache_hit is False

    def test_failed_artifact_records_error_message(self, tmp_output: Path):
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
            ThumbnailStatus,
        )

        service = ThumbnailService()
        request = ThumbnailRequest(prompts=["test"], output_dir=tmp_output)

        with (
            patch.object(
                service,
                "_select_backend",
                return_value=(ThumbnailBackend.IMAGEN4, ""),
            ),
            patch.object(
                service,
                "_run_backend",
                side_effect=RuntimeError("API quota exceeded"),
            ),
        ):
            result = service.generate(request)

        assert result.total_failed == 1
        assert "API quota exceeded" in result.artifacts[0].error
        assert result.artifacts[0].status == ThumbnailStatus.FAILED
