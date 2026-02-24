"""Tests for AI thumbnail generation service (09-09, updated 09-11 Gemini Vision)."""

from __future__ import annotations

import os
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

    def test_cache_hit_returns_cached_artifact(self, tmp_output: Path) -> None:
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailRequest,
            ThumbnailService,
            ThumbnailStatus,
            compute_cache_key,
        )

        prompt = "podcast host on stage"
        model = "gemini-2.5-flash-image"
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
        from podcast_pipeline.utils.thumbnails import ThumbnailBackend

        with patch.object(
            service,
            "_select_backend",
            return_value=(ThumbnailBackend.GEMINI, ""),
        ):
            result = service.generate(request)

        assert result.total_cached == 1
        assert result.total_generated == 0
        assert result.artifacts[0].status == ThumbnailStatus.CACHED
        assert result.artifacts[0].cache_hit is True

    def test_empty_cache_file_triggers_regeneration(self, tmp_output: Path) -> None:
        """A zero-byte cache file must not be treated as a valid cache hit."""
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
            compute_cache_key,
        )

        prompt = "empty cache test"
        model = "gemini-2.5-flash-image"
        key = compute_cache_key(prompt, model, 1280, 720, seed=None, index=0)
        empty_file = tmp_output / f"{key}.jpg"
        empty_file.write_bytes(b"")  # zero-byte -- should NOT be treated as cache hit

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
                return_value=(ThumbnailBackend.GEMINI, ""),
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
    """Backend routing respects Gemini availability."""

    def test_gemini_selected_when_api_key_available(self, tmp_output: Path) -> None:
        from podcast_pipeline.utils.thumbnails import ThumbnailBackend, ThumbnailService

        with patch(
            "podcast_pipeline.utils.thumbnails._gemini_available",
            return_value=(True, ""),
        ):
            service = ThumbnailService()
            from podcast_pipeline.utils.thumbnails import ThumbnailRequest

            request = ThumbnailRequest(
                prompts=["test"],
                output_dir=tmp_output,
            )
            backend, reason = service._select_backend(request)

        assert backend == ThumbnailBackend.GEMINI
        assert reason == ""

    def test_none_backend_when_gemini_unavailable(self, tmp_output: Path) -> None:
        from podcast_pipeline.utils.thumbnails import ThumbnailBackend, ThumbnailService

        with patch(
            "podcast_pipeline.utils.thumbnails._gemini_available",
            return_value=(False, "GEMINI_API_KEY not set"),
        ):
            service = ThumbnailService()
            from podcast_pipeline.utils.thumbnails import ThumbnailRequest

            request = ThumbnailRequest(prompts=["test"], output_dir=tmp_output)
            backend, reason = service._select_backend(request)

        assert backend == ThumbnailBackend.NONE
        assert "No thumbnail backend" in reason


# ---------------------------------------------------------------------------
# Graceful degradation when no backend available
# ---------------------------------------------------------------------------


class TestDegradedMode:
    """Service skips gracefully when no backend is available."""

    def test_no_backend_returns_degraded_result(self, tmp_output: Path) -> None:
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
        )

        with patch(
            "podcast_pipeline.utils.thumbnails._gemini_available",
            return_value=(False, "GEMINI_API_KEY not set"),
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
# Gemini availability checks
# ---------------------------------------------------------------------------


class TestGeminiAvailability:
    """Gemini Vision backend availability diagnostics."""

    def test_unavailable_when_api_key_missing(self) -> None:
        from podcast_pipeline.utils.thumbnails import _gemini_available

        env = os.environ.copy()
        env.pop("GEMINI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            ok, reason = _gemini_available()

        assert ok is False
        assert "GEMINI_API_KEY" in reason

    def test_unavailable_when_sdk_missing(self) -> None:
        from podcast_pipeline.utils.thumbnails import _gemini_available

        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch.dict("sys.modules", {"google": None, "google.genai": None}),
        ):
            ok, reason = _gemini_available()

        assert ok is False
        assert "google-genai" in reason

    def test_available_when_key_and_sdk_present(self) -> None:
        from podcast_pipeline.utils.thumbnails import _gemini_available

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-123"}):
            ok, reason = _gemini_available()

        assert ok is True
        assert reason == ""


# ---------------------------------------------------------------------------
# Branding overlay integration
# ---------------------------------------------------------------------------


class TestBrandingOverlay:
    """Overlay integration uses toolkit overlay_image operation."""

    def test_overlay_skipped_when_no_logo(self, tmp_output: Path, fake_branding: MagicMock) -> None:
        from podcast_pipeline.utils.thumbnails import _apply_branding_overlay

        fake_branding.logo_path = None
        src = tmp_output / "thumb.jpg"
        src.write_bytes(b"FAKE")

        result = _apply_branding_overlay(src, fake_branding)

        # No logo -- original path returned unchanged
        assert result == src

    def test_overlay_skipped_when_logo_missing_on_disk(
        self, tmp_output: Path, fake_branding: MagicMock
    ) -> None:
        from podcast_pipeline.utils.thumbnails import _apply_branding_overlay

        fake_branding.logo_path = tmp_output / "nonexistent_logo.png"
        src = tmp_output / "thumb.jpg"
        src.write_bytes(b"FAKE")

        result = _apply_branding_overlay(src, fake_branding)

        assert result == src

    def test_overlay_calls_toolkit_when_logo_exists(
        self, tmp_output: Path, fake_branding: MagicMock
    ) -> None:
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
    ) -> None:
        """Branding overlay is applied even to cache-hit images."""
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
            compute_cache_key,
        )

        prompt = "cache hit with branding"
        model = "gemini-2.5-flash-image"
        key = compute_cache_key(prompt, model, 1280, 720, seed=None, index=0)
        cached = tmp_output / f"{key}.jpg"
        cached.write_bytes(b"FAKEJPEG")

        fake_branding.logo_path = None  # no logo -> overlay skipped

        service = ThumbnailService()
        request = ThumbnailRequest(
            prompts=[prompt],
            output_dir=tmp_output,
            branding_profile=fake_branding,
        )

        with patch.object(service, "_select_backend", return_value=(ThumbnailBackend.GEMINI, "")):
            result = service.generate(request)

        assert result.total_cached == 1
        # Branding was not applied (no logo) but artifact is returned
        assert result.artifacts[0].branded is False


# ---------------------------------------------------------------------------
# Prompt truncation
# ---------------------------------------------------------------------------


class TestPromptTruncation:
    """More than 5 prompts are silently truncated."""

    def test_more_than_5_prompts_truncated(self, tmp_output: Path) -> None:
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
                return_value=(ThumbnailBackend.GEMINI, ""),
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

    def test_generated_artifact_has_correct_backend(self, tmp_output: Path) -> None:
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
                return_value=(ThumbnailBackend.GEMINI, ""),
            ),
            patch.object(service, "_run_backend", return_value=[(dummy_path, False)]),
        ):
            result = service.generate(request)

        assert result.total_generated == 1
        assert result.artifacts[0].backend == ThumbnailBackend.GEMINI
        assert result.artifacts[0].status == ThumbnailStatus.GENERATED
        assert result.artifacts[0].cache_hit is False

    def test_failed_artifact_records_error_message(self, tmp_output: Path) -> None:
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
                return_value=(ThumbnailBackend.GEMINI, ""),
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


# ---------------------------------------------------------------------------
# Integration regressions -- cache, overlay, and degradation continuity
# ---------------------------------------------------------------------------


class TestIntegrationRegressions:
    """Integration regressions protecting cache hits, overlay continuity, and degradation."""

    def test_cache_hit_skips_backend_invocation_entirely(self, tmp_output: Path) -> None:
        """A valid cache file must prevent _run_backend from being called at all."""
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
            compute_cache_key,
        )

        prompt = "cached integration test prompt"
        model = "gemini-2.5-flash-image"
        key = compute_cache_key(prompt, model, 1280, 720, seed=None, index=0)
        cached = tmp_output / f"{key}.jpg"
        cached.write_bytes(b"FAKEJPEG_CACHED")

        service = ThumbnailService()
        backend_calls: list[object] = []

        def _spy_run_backend(*args: object, **kwargs: object) -> list[object]:
            backend_calls.append((args, kwargs))
            return []

        with (
            patch.object(
                service,
                "_select_backend",
                return_value=(ThumbnailBackend.GEMINI, ""),
            ),
            patch.object(service, "_run_backend", side_effect=_spy_run_backend),
        ):
            result = service.generate(ThumbnailRequest(prompts=[prompt], output_dir=tmp_output))

        # _run_backend must NOT be called -- cache hit short-circuits generation
        assert backend_calls == []
        assert result.total_cached == 1
        assert result.total_generated == 0

    def test_overlay_applied_after_generation_not_just_cache_hits(
        self, tmp_output: Path, fake_branding: MagicMock
    ) -> None:
        """Branding overlay should fire for freshly generated images, not only cache hits."""
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
        )

        service = ThumbnailService()
        dummy_path = tmp_output / "generated.jpg"
        dummy_path.write_bytes(b"GENERATED_CONTENT")

        # Logo exists so overlay should be attempted
        logo = tmp_output / "logo.png"
        logo.write_bytes(b"PNGDATA")
        fake_branding.logo_path = logo

        branding_calls: list[object] = []

        def _spy_apply_branding(artifact: object, profile: object) -> object:
            branding_calls.append(artifact)
            return artifact  # return unchanged

        with (
            patch.object(
                service,
                "_select_backend",
                return_value=(ThumbnailBackend.GEMINI, ""),
            ),
            patch.object(service, "_run_backend", return_value=[(dummy_path, False)]),
            patch.object(service, "_apply_branding", side_effect=_spy_apply_branding),
        ):
            service.generate(
                ThumbnailRequest(
                    prompts=["overlay test"],
                    output_dir=tmp_output,
                    branding_profile=fake_branding,
                )
            )

        assert len(branding_calls) == 1

    def test_all_generation_failures_sets_degraded_result(self, tmp_output: Path) -> None:
        """When every generation attempt fails, the result should be marked degraded."""
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
        )

        service = ThumbnailService()

        with (
            patch.object(
                service,
                "_select_backend",
                return_value=(ThumbnailBackend.GEMINI, ""),
            ),
            patch.object(
                service,
                "_run_backend",
                side_effect=RuntimeError("API error"),
            ),
        ):
            result = service.generate(
                ThumbnailRequest(prompts=["fail1", "fail2"], output_dir=tmp_output)
            )

        assert result.degraded is True
        assert "failed" in result.degraded_reason.lower()
        assert result.total_failed == 2
        assert result.total_generated == 0

    def test_cache_and_generation_in_same_run_count_independently(self, tmp_output: Path) -> None:
        """When some prompts are cached and others generate, counts must be independent."""
        from podcast_pipeline.utils.thumbnails import (
            ThumbnailBackend,
            ThumbnailRequest,
            ThumbnailService,
            ThumbnailStatus,
            compute_cache_key,
        )

        model = "gemini-2.5-flash-image"
        cached_prompt = "cached prompt"
        new_prompt = "new prompt"

        # Pre-seed cache for first prompt only
        key = compute_cache_key(cached_prompt, model, 1280, 720, seed=None, index=0)
        cached_file = tmp_output / f"{key}.jpg"
        cached_file.write_bytes(b"CACHED_JPEG")

        service = ThumbnailService()
        new_path = tmp_output / "new.jpg"
        new_path.write_bytes(b"NEW_JPEG")

        with (
            patch.object(
                service,
                "_select_backend",
                return_value=(ThumbnailBackend.GEMINI, ""),
            ),
            patch.object(service, "_run_backend", return_value=[(new_path, False)]),
        ):
            result = service.generate(
                ThumbnailRequest(
                    prompts=[cached_prompt, new_prompt],
                    output_dir=tmp_output,
                    model=model,
                )
            )

        assert result.total_cached == 1
        assert result.total_generated == 1
        statuses = {a.status for a in result.artifacts}
        assert ThumbnailStatus.CACHED in statuses
        assert ThumbnailStatus.GENERATED in statuses
