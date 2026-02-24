"""Tests for pipeline orchestration."""

import json
import threading
from pathlib import Path

import pytest

from podcast_pipeline.config import BrandingConfig, Config
from podcast_pipeline.models.analysis import AnalysisResult
from podcast_pipeline.models.branding import BrandingProfile, PlatformBrandingOverride
from podcast_pipeline.models.job import Job, StageStatus
from podcast_pipeline.models.transcript import Segment, Word
from podcast_pipeline.pipeline import Pipeline
from podcast_pipeline.stages.analyze import AnalyzeStage
from podcast_pipeline.stages.base import StageResult
from podcast_pipeline.stages.transcribe import TranscribeStage
from podcast_pipeline.utils.locks import JobLockAcquisitionError


class TestPipeline:
    """Tests for Pipeline class."""

    def test_create_pipeline(self, config: Config):
        """Test creating a pipeline."""
        pipeline = Pipeline(config)
        assert "ingest" in pipeline.stages
        assert "transcribe" in pipeline.stages
        assert "analyze" in pipeline.stages
        assert "review" in pipeline.stages
        assert "render" in pipeline.stages

    def test_list_empty_jobs(self, config: Config):
        """Test listing jobs when none exist."""
        pipeline = Pipeline(config)
        jobs = pipeline.list_jobs()
        assert jobs == []

    def test_stage_order(self, config: Config):
        """Test pipeline stage order."""
        pipeline = Pipeline(config)
        expected = ["ingest", "transcribe", "analyze", "review", "render"]
        assert expected == pipeline.STAGE_ORDER


class TestReviewStage:
    """Tests for review stage functionality."""

    def test_approve_review(self, config: Config, temp_dir: Path):
        """Test approving a review."""
        from podcast_pipeline.stages.review import approve_review

        # Create job directory structure
        job_dir = temp_dir / "test-job"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True)

        # Create mock analysis file
        analysis = {
            "content_cuts": [
                {
                    "start": "00:10",
                    "end": "00:20",
                    "start_seconds": 10,
                    "end_seconds": 20,
                    "reason": "test",
                }
            ],
            "viral_clips": [
                {
                    "start": "00:30",
                    "end": "01:00",
                    "start_seconds": 30,
                    "end_seconds": 60,
                    "description": "test",
                    "virality_score": 8,
                    "suggested_hook": "watch",
                }
            ],
            "thumbnail_frames": [
                {
                    "timestamp": "00:15",
                    "timestamp_seconds": 15,
                    "visual_description": "test",
                    "suggested_text_overlay": "text",
                    "emotion": "joy",
                }
            ],
            "marketing": {},
            "metadata": {},
        }
        (analysis_dir / "analysis.json").write_text(json.dumps(analysis))

        # Create mock filler cuts
        fillers = [{"start": 2.5, "end": 2.8, "word": "um", "confidence": 0.85}]
        (analysis_dir / "filler_cuts.json").write_text(json.dumps(fillers))

        # Approve review
        decisions = approve_review(job_dir, ["youtube", "spotify"])

        assert decisions.review_complete
        assert len(decisions.approved_filler_cuts) == 1
        assert len(decisions.approved_content_cuts) == 1
        assert len(decisions.selected_clips) == 1
        assert decisions.selected_thumbnail == 0
        assert "youtube" in decisions.export_platforms

    def test_review_edit_plan_render_contract_respects_explicit_filler_decisions(
        self,
        temp_dir: Path,
    ) -> None:
        """review/edit_plan contract should serialize only fillers marked remove."""
        from podcast_pipeline.stages.review import FillerDecision, ReviewDecisions, write_edit_plan

        job_dir = temp_dir / "review-render-explicit"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "analysis.json").write_text(
            json.dumps({"content_cuts": [], "viral_clips": [], "thumbnail_frames": []})
        )
        filler_cuts = [
            {"start_seconds": 1.0, "end_seconds": 1.2, "word": "um"},
            {"start_seconds": 2.0, "end_seconds": 2.3, "word": "like"},
            {"start_seconds": 3.0, "end_seconds": 3.2, "word": "uh"},
        ]

        decisions = ReviewDecisions(
            filler_decisions=[
                FillerDecision(index=0, action="keep"),
                FillerDecision(index=1, action="remove"),
                FillerDecision(index=2, action="remove"),
            ],
            approved_filler_cuts=[0],
        )
        edit_path = write_edit_plan(
            job_dir, decisions, {"content_cuts": [], "viral_clips": []}, filler_cuts
        )

        payload = json.loads(edit_path.read_text())
        assert [item["word"] for item in payload["filler_cuts"]] == ["like", "uh"]

    def test_review_edit_plan_legacy_approved_filler_cuts_remains_compatible(
        self,
        temp_dir: Path,
    ) -> None:
        """Legacy approved_filler_cuts payloads should still produce deterministic edit plans."""
        from podcast_pipeline.stages.review import ReviewDecisions, write_edit_plan

        job_dir = temp_dir / "review-render-legacy"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "analysis.json").write_text(
            json.dumps({"content_cuts": [], "viral_clips": [], "thumbnail_frames": []})
        )
        filler_cuts = [
            {"start_seconds": 0.5, "end_seconds": 0.8, "word": "um"},
            {"start_seconds": 1.0, "end_seconds": 1.3, "word": "like"},
            {"start_seconds": 1.6, "end_seconds": 1.9, "word": "uh"},
        ]

        decisions = ReviewDecisions(approved_filler_cuts=[2, 0], filler_decisions=[])
        edit_path = write_edit_plan(
            job_dir, decisions, {"content_cuts": [], "viral_clips": []}, filler_cuts
        )

        payload = json.loads(edit_path.read_text())
        assert [item["word"] for item in payload["filler_cuts"]] == ["um", "uh"]

    def test_review_edit_plan_mixed_new_and_legacy_payload_remains_deterministic(
        self,
        temp_dir: Path,
    ) -> None:
        """Explicit filler decisions should take precedence over legacy approved indices."""
        from podcast_pipeline.stages.review import FillerDecision, ReviewDecisions, write_edit_plan

        job_dir = temp_dir / "review-render-mixed"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "analysis.json").write_text(
            json.dumps({"content_cuts": [], "viral_clips": [], "thumbnail_frames": []})
        )
        filler_cuts = [
            {"start_seconds": 0.5, "end_seconds": 0.8, "word": "um"},
            {"start_seconds": 1.0, "end_seconds": 1.3, "word": "like"},
            {"start_seconds": 1.6, "end_seconds": 1.9, "word": "uh"},
        ]

        decisions = ReviewDecisions(
            approved_filler_cuts=[0, 2],
            filler_decisions=[FillerDecision(index=1, action="remove")],
        )
        edit_path = write_edit_plan(
            job_dir,
            decisions,
            {"content_cuts": [], "viral_clips": []},
            filler_cuts,
        )

        payload = json.loads(edit_path.read_text())
        assert [item["word"] for item in payload["filler_cuts"]] == ["like"]


class TestStageValidation:
    """Tests for strict stage validation at pipeline entry points."""

    def test_invalid_stage_rejected_with_validation_error(self, config: Config) -> None:
        """Invalid explicit stage names should fail fast."""
        pipeline = Pipeline(config)
        job = Job(job_id="invalid-stage-job", input_file="/tmp/test.mp4")

        with pytest.raises(ValueError, match="Unknown stage: invalid-stage"):
            pipeline.run(job, stage="invalid-stage")

        assert job.status == StageStatus.PENDING
        assert all(stage.status == StageStatus.PENDING for stage in job.stages.values())

    def test_invalid_stage_validation_for_until_stage(self, config: Config) -> None:
        """Invalid until_stage values should fail fast."""
        pipeline = Pipeline(config)
        job = Job(job_id="invalid-until-job", input_file="/tmp/test.mp4")

        with pytest.raises(ValueError, match="Unknown stage: not-a-stage"):
            pipeline.run(job, until_stage="not-a-stage")

        assert job.status == StageStatus.PENDING


class TestPipelineLocking:
    """Tests for lock acquisition and state reload boundaries."""

    def test_state_reload_uses_latest_job_state(self, config: Config) -> None:
        """state_reload should skip stages already complete on disk."""
        pipeline = Pipeline(config)
        job = Job(job_id="state-reload-job", input_file="/tmp/test.mp4")
        job.save(config.paths.jobs_dir)

        stale_job = pipeline.load_job(job.job_id)
        fresh_job = pipeline.load_job(job.job_id)
        fresh_job.update_stage("ingest", StageStatus.COMPLETE, outputs=["input/audio.wav"])
        fresh_job.save(config.paths.jobs_dir)

        run_counter = {"calls": 0}

        class CountingStage:
            def execute(self, stage_job: Job, job_dir: Path) -> StageResult:
                run_counter["calls"] += 1
                return StageResult(success=True)

        pipeline.stages["ingest"] = CountingStage()
        results = pipeline.run(stale_job, stage="ingest")

        assert results == {}
        assert run_counter["calls"] == 0

    def test_job_lock_rejects_second_run_attempt(self, config: Config) -> None:
        """lock contention should reject a concurrent run for the same job."""
        pipeline_one = Pipeline(config)
        pipeline_two = Pipeline(config)
        job = Job(job_id="lock-contention-job", input_file="/tmp/test.mp4")
        job.save(config.paths.jobs_dir)

        stage_started = threading.Event()
        stage_release = threading.Event()
        runner_errors: list[Exception] = []

        class BlockingStage:
            def execute(self, stage_job: Job, job_dir: Path) -> StageResult:
                stage_started.set()
                stage_release.wait(timeout=5)
                return StageResult(success=True)

        pipeline_one.stages["ingest"] = BlockingStage()

        def _run_with_lock() -> None:
            try:
                locked_job = pipeline_one.load_job(job.job_id)
                pipeline_one.run(locked_job, stage="ingest")
            except Exception as exc:  # pragma: no cover - assertion below captures failures
                runner_errors.append(exc)
            finally:
                stage_release.set()

        worker = threading.Thread(target=_run_with_lock)
        worker.start()
        assert stage_started.wait(timeout=5)

        second_job = pipeline_two.load_job(job.job_id)
        with pytest.raises(JobLockAcquisitionError, match="already running"):
            pipeline_two.run(second_job, stage="ingest")

        stage_release.set()
        worker.join(timeout=5)

        assert runner_errors == []
        assert not worker.is_alive()


class TestAnalyzeStageThumbnailMaterialization:
    """Tests for analyze-stage thumbnail frame extraction artifacts."""

    def test_analyze_stage_materializes_thumbnail_images_for_ui(
        self,
        config: Config,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Analyze stage should persist extracted thumbnail image paths for UI preview cards."""

        class _Provider:
            name = "stub"
            model = "stub-model"
            supports_video = True

            def is_available(self) -> bool:
                return True

            def analyze(
                self,
                video_path: Path,
                transcript: dict[str, object],
            ) -> AnalysisResult:
                del video_path, transcript
                return AnalysisResult.model_validate(
                    {
                        "content_cuts": [],
                        "viral_clips": [],
                        "thumbnail_frames": [
                            {
                                "timestamp": "00:05",
                                "timestamp_seconds": 5.0,
                                "visual_description": "Host smiling",
                                "suggested_text_overlay": "Big claim",
                                "emotion": "surprise",
                            },
                            {
                                "timestamp": "00:12",
                                "timestamp_seconds": 12.0,
                                "visual_description": "Guest reaction",
                                "suggested_text_overlay": "Unexpected twist",
                                "emotion": "joy",
                            },
                        ],
                        "marketing": {},
                        "metadata": {"summary": "Summary", "topics": [], "mood": "energetic"},
                    }
                )

        stage = AnalyzeStage(config)
        stage.providers = [_Provider()]  # type: ignore[assignment]
        monkeypatch.setattr(stage, "_run_research", lambda *args, **kwargs: None)
        monkeypatch.setattr(stage, "_run_viral_signals", lambda *args, **kwargs: None)

        def _fake_ffmpeg(args: list[str], timeout: int = 0, check: bool = True) -> None:
            del timeout, check
            output_path = Path(args[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"thumbnail")

        import podcast_pipeline.stages.analyze as _analyze_mod

        monkeypatch.setattr(_analyze_mod, "run_ffmpeg", _fake_ffmpeg)

        job_dir = temp_dir / "jobs" / "thumbnail-job"
        (job_dir / "analysis").mkdir(parents=True, exist_ok=True)
        (job_dir / "analysis" / "transcript.json").write_text(json.dumps({"text": "test"}))
        (job_dir / "intermediate").mkdir(parents=True, exist_ok=True)
        (job_dir / "intermediate" / "proxy.mp4").write_bytes(b"proxy")

        job = Job(job_id="thumbnail-job", input_file=str(job_dir / "input.mp4"))
        result = stage.run(job, job_dir)

        assert result.success is True

        analysis_payload = json.loads((job_dir / "analysis" / "analysis.json").read_text())
        frames = analysis_payload["thumbnail_frames"]

        first_image_path = frames[0].get("image_path")
        second_image_path = frames[1].get("image_path")
        assert isinstance(first_image_path, str)
        assert isinstance(second_image_path, str)
        assert first_image_path.startswith("intermediate/thumbnails/thumbnail_01_")
        assert second_image_path.startswith("intermediate/thumbnails/thumbnail_02_")
        assert first_image_path != second_image_path
        assert (job_dir / first_image_path).exists()
        assert (job_dir / second_image_path).exists()


class TestAnalyzeStageAIThumbnailGeneration:
    """Tests for AI thumbnail generation wiring in the analyze stage."""

    def test_ai_thumbnail_generation_skipped_when_disabled(
        self,
        config: Config,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_generate_ai_thumbnails must not be called when thumbnail_generation.enabled=False."""

        # Config has thumbnail_generation.enabled=False by default
        assert config.branding.thumbnail_generation.enabled is False

        class _Provider:
            name = "stub"
            model = "stub-model"
            supports_video = True

            def is_available(self) -> bool:
                return True

            def analyze(self, video_path: Path, transcript: dict) -> AnalysisResult:  # type: ignore[type-arg]
                del video_path, transcript
                return AnalysisResult.model_validate(
                    {
                        "content_cuts": [],
                        "viral_clips": [],
                        "thumbnail_frames": [
                            {
                                "timestamp": "00:05",
                                "timestamp_seconds": 5.0,
                                "visual_description": "Host on stage",
                            }
                        ],
                        "marketing": {},
                        "metadata": {"summary": "", "topics": [], "mood": ""},
                    }
                )

        stage = AnalyzeStage(config)
        stage.providers = [_Provider()]  # type: ignore[assignment]
        monkeypatch.setattr(stage, "_run_research", lambda *args, **kwargs: None)
        monkeypatch.setattr(stage, "_run_viral_signals", lambda *args, **kwargs: None)
        import podcast_pipeline.stages.analyze as _analyze_mod

        monkeypatch.setattr(_analyze_mod, "run_ffmpeg", lambda *a, **k: None)

        ai_gen_calls: list[object] = []

        def _spy_ai_gen(*args: object, **kwargs: object) -> list[str]:
            ai_gen_calls.append((args, kwargs))
            return []

        monkeypatch.setattr(stage, "_generate_ai_thumbnails", _spy_ai_gen)

        job_dir = temp_dir / "jobs" / "ai-thumbnail-disabled-job"
        (job_dir / "analysis").mkdir(parents=True, exist_ok=True)
        (job_dir / "analysis" / "transcript.json").write_text(json.dumps({"text": "test"}))
        (job_dir / "intermediate").mkdir(parents=True, exist_ok=True)
        (job_dir / "intermediate" / "proxy.mp4").write_bytes(b"proxy")

        job = Job(job_id="ai-thumbnail-disabled-job", input_file=str(job_dir / "input.mp4"))
        result = stage.run(job, job_dir)

        assert result.success is True
        # _generate_ai_thumbnails must not have been called
        assert ai_gen_calls == []

    def test_ai_thumbnail_generation_invoked_when_enabled(
        self,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_generate_ai_thumbnails should be called when thumbnail_generation.enabled=True."""
        from podcast_pipeline.config.settings import BrandingConfig, ThumbnailGenerationConfig

        cfg = Config()
        cfg.branding = BrandingConfig(thumbnail_generation=ThumbnailGenerationConfig(enabled=True))

        class _Provider:
            name = "stub"
            model = "stub-model"
            supports_video = True

            def is_available(self) -> bool:
                return True

            def analyze(self, video_path: Path, transcript: dict) -> AnalysisResult:  # type: ignore[type-arg]
                del video_path, transcript
                return AnalysisResult.model_validate(
                    {
                        "content_cuts": [],
                        "viral_clips": [],
                        "thumbnail_frames": [
                            {
                                "timestamp": "00:03",
                                "timestamp_seconds": 3.0,
                                "visual_description": "Energetic host moment",
                            }
                        ],
                        "marketing": {},
                        "metadata": {"summary": "", "topics": [], "mood": ""},
                    }
                )

        stage = AnalyzeStage(cfg)
        stage.providers = [_Provider()]  # type: ignore[assignment]
        monkeypatch.setattr(stage, "_run_research", lambda *args, **kwargs: None)
        monkeypatch.setattr(stage, "_run_viral_signals", lambda *args, **kwargs: None)
        import podcast_pipeline.stages.analyze as _analyze_mod

        monkeypatch.setattr(_analyze_mod, "run_ffmpeg", lambda *a, **k: None)

        ai_gen_calls: list[tuple[object, object]] = []

        def _spy_ai_gen(*args: object, **kwargs: object) -> list[str]:
            ai_gen_calls.append((args, kwargs))
            return []

        monkeypatch.setattr(stage, "_generate_ai_thumbnails", _spy_ai_gen)

        job_dir = temp_dir / "jobs" / "ai-thumbnail-enabled-job"
        (job_dir / "analysis").mkdir(parents=True, exist_ok=True)
        (job_dir / "analysis" / "transcript.json").write_text(json.dumps({"text": "test"}))
        (job_dir / "intermediate").mkdir(parents=True, exist_ok=True)
        (job_dir / "intermediate" / "proxy.mp4").write_bytes(b"proxy")

        job = Job(job_id="ai-thumbnail-enabled-job", input_file=str(job_dir / "input.mp4"))
        result = stage.run(job, job_dir)

        assert result.success is True
        # _generate_ai_thumbnails must have been called exactly once
        assert len(ai_gen_calls) == 1

    def test_generate_ai_thumbnails_skips_frames_without_visual_description(
        self,
        config: Config,
        temp_dir: Path,
    ) -> None:
        """Frames with empty or missing visual_description should be silently skipped."""
        from unittest.mock import patch

        stage = AnalyzeStage(config)

        analysis_payload: dict = {  # type: ignore[type-arg]
            "thumbnail_frames": [
                {"timestamp_seconds": 1.0, "visual_description": ""},
                {"timestamp_seconds": 2.0},  # missing key entirely
                {"timestamp_seconds": 3.0, "visual_description": "   "},  # only whitespace
            ]
        }

        with patch("podcast_pipeline.utils.thumbnails.ThumbnailService") as mock_svc_cls:
            stage._generate_ai_thumbnails(  # type: ignore[attr-defined]
                analysis_payload=analysis_payload,
                job_dir=temp_dir,
            )
        # ThumbnailService.generate must not have been called for empty descriptions
        mock_svc_cls.return_value.generate.assert_not_called()

    def test_generate_ai_thumbnails_writes_ai_image_path_to_frames(
        self,
        config: Config,
        temp_dir: Path,
    ) -> None:
        """Successful AI generation should write ai_image_path into each matched frame."""
        from unittest.mock import patch

        from podcast_pipeline.utils.thumbnails import (
            ThumbnailArtifact,
            ThumbnailBackend,
            ThumbnailResult,
            ThumbnailStatus,
        )

        stage = AnalyzeStage(config)
        output_dir = temp_dir / "intermediate" / "ai_thumbnails"
        output_dir.mkdir(parents=True, exist_ok=True)
        ai_img = output_dir / "aabb1122.jpg"
        ai_img.write_bytes(b"AI_IMAGE")

        description = "Engaging podcast thumbnail"
        analysis_payload: dict = {  # type: ignore[type-arg]
            "thumbnail_frames": [{"timestamp_seconds": 5.0, "visual_description": description}]
        }

        mock_result = ThumbnailResult(
            artifacts=[
                ThumbnailArtifact(
                    path=ai_img,
                    prompt=description,
                    backend=ThumbnailBackend.IMAGEN4,
                    status=ThumbnailStatus.GENERATED,
                )
            ],
            backend_used=ThumbnailBackend.IMAGEN4,
            total_generated=1,
        )

        with patch("podcast_pipeline.utils.thumbnails.ThumbnailService") as mock_svc_cls:
            mock_svc_cls.return_value.generate.return_value = mock_result
            paths = stage._generate_ai_thumbnails(  # type: ignore[attr-defined]
                analysis_payload=analysis_payload,
                job_dir=temp_dir,
            )

        assert len(paths) == 1
        # ai_image_path must be written back into the frame entry
        frame = analysis_payload["thumbnail_frames"][0]
        assert "ai_image_path" in frame
        assert frame["ai_image_path"].endswith(".jpg")


class TestTranscribeFillerDetection:
    """Tests for filler-word extraction behavior."""

    def test_detect_fillers_handles_punctuation_tokens(self, config: Config) -> None:
        """Words like 'um,' and 'basically,' should still match configured fillers."""
        stage = TranscribeStage(config)
        segments = [
            Segment(
                start=0.0,
                end=1.2,
                text="Um, uh, like, basically,",
                words=[
                    Word(word="Um,", start=0.0, end=0.2, confidence=0.90),
                    Word(word="uh,", start=0.2, end=0.4, confidence=0.92),
                    Word(word="like,", start=0.4, end=0.7, confidence=0.95),
                    Word(word="basically,", start=0.7, end=1.2, confidence=0.97),
                ],
            )
        ]

        cuts = stage._detect_fillers(segments)
        detected_words = [cut.word.lower().strip(",") for cut in cuts]
        assert "uh" in detected_words
        assert "like" in detected_words
        assert "basically" in detected_words

    def test_detect_fillers_supports_two_word_phrase(self, config: Config) -> None:
        """Configured phrase fillers like 'you know' should be detected as one cut."""
        stage = TranscribeStage(config)
        segments = [
            Segment(
                start=0.0,
                end=1.0,
                text="you know this",
                words=[
                    Word(word="you", start=0.0, end=0.2, confidence=0.95),
                    Word(word="know", start=0.2, end=0.4, confidence=0.93),
                    Word(word="this", start=0.4, end=0.8, confidence=0.99),
                ],
            )
        ]

        cuts = stage._detect_fillers(segments)
        assert any(cut.word == "you know" for cut in cuts)


# ---------------------------------------------------------------------------
# Phase 8 Integration Tests
# ---------------------------------------------------------------------------


class TestPhase8LegacyCompatibility:
    """Legacy artifact compatibility tests for Phase 8 fields."""

    def test_legacy_filler_cuts_load_without_phase8_fields(self, temp_dir: Path) -> None:
        """filler_cuts.json without Phase 8 fields loads and defaults correctly.

        A legacy filler_cuts.json has only {start, end, word, confidence}.
        The review stage helpers must produce FillerDecision items and FillerCutRange
        objects with safe defaults for all Phase 8 fields (category, protected, etc.)
        without raising any errors.
        """
        from podcast_pipeline.stages.review import (
            FillerDecision,
            ReviewDecisions,
            _derive_editorial_action,
            _load_filler_triage_map,
            write_edit_plan,
        )

        job_dir = temp_dir / "legacy-fillers-job"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        # Legacy format: no category, no protected, no pause fields
        legacy_fillers = [
            {"start": 1.0, "end": 1.2, "word": "um", "confidence": 0.85},
            {"start": 3.0, "end": 3.3, "word": "uh", "confidence": 0.90},
            {"start": 5.0, "end": 5.4, "word": "like", "confidence": 0.80},
        ]
        (analysis_dir / "filler_cuts.json").write_text(json.dumps(legacy_fillers))
        (analysis_dir / "analysis.json").write_text(
            json.dumps({"content_cuts": [], "viral_clips": [], "thumbnail_frames": []})
        )
        # No filler_triage.json — legacy job

        triage_map = _load_filler_triage_map(job_dir)
        assert triage_map == {}

        # Each filler should get a safe editorial_action using the legacy path
        for idx, filler in enumerate(legacy_fillers):
            action = _derive_editorial_action(filler, triage_map.get(idx), None)
            # Legacy fillers without 'protected' or 'category' default to "keep"
            assert action in ("keep", "remove")

        # write_edit_plan should succeed with remove-all decisions
        decisions = ReviewDecisions(
            filler_decisions=[
                FillerDecision(index=0, action="remove"),
                FillerDecision(index=1, action="remove"),
                FillerDecision(index=2, action="remove"),
            ]
        )
        edit_path = write_edit_plan(job_dir, decisions, {}, legacy_fillers)
        payload = json.loads(edit_path.read_text())

        # All three fillers are in filler_cuts
        assert len(payload["filler_cuts"]) == 3
        for entry in payload["filler_cuts"]:
            # Phase 8 fields must have safe defaults when not in legacy data
            assert entry.get("category", "") == ""  # defaults to empty string
            assert entry.get("protected", False) is False
            assert entry.get("pause_before_ms", 0.0) == 0.0
            assert entry.get("pause_after_ms", 0.0) == 0.0
            assert entry.get("llm_safe_to_remove") is None
            assert entry.get("llm_reason", "") == ""

    def test_legacy_edit_plan_load_without_phase8_fields(self, temp_dir: Path) -> None:
        """edit_plan.json without Phase 8 FillerCutRange fields loads and validates.

        A legacy edit_plan.json may contain FillerCutRange entries that lack
        llm_safe_to_remove, llm_reason, protected, category etc.  The Pydantic
        model must validate and supply safe defaults without raising errors.
        """
        from podcast_pipeline.models.edit_plan import EditPlan, FillerCutRange

        # Minimal legacy entry — only the fields that existed before Phase 8
        legacy_edit_plan = {
            "filler_cuts": [
                {"start_seconds": 1.0, "end_seconds": 1.2, "word": "um"},
                {"start_seconds": 3.0, "end_seconds": 3.3, "word": "uh", "confidence": 0.90},
            ],
            "content_cuts": [],
            "clip_ranges": [],
        }

        plan = EditPlan.model_validate(legacy_edit_plan)

        assert len(plan.filler_cuts) == 2
        for cut in plan.filler_cuts:
            # Phase 8 fields default safely
            assert isinstance(cut, FillerCutRange)
            assert cut.category == ""
            assert cut.protected is False
            assert cut.pause_before_ms == 0.0
            assert cut.pause_after_ms == 0.0
            assert cut.llm_safe_to_remove is None
            assert cut.llm_reason == ""
            assert cut.editorial_action == "remove"  # default

    def test_legacy_edit_plan_roundtrip_via_json(self, temp_dir: Path) -> None:
        """Legacy edit_plan JSON can be persisted and re-loaded without errors."""
        from podcast_pipeline.models.edit_plan import EditPlan

        legacy_json = json.dumps(
            {
                "filler_cuts": [
                    {"start_seconds": 0.5, "end_seconds": 0.7, "word": "um"},
                ],
                "content_cuts": [
                    {"start_seconds": 10.0, "end_seconds": 20.0, "reason": "tangent"},
                ],
                "clip_ranges": [],
            }
        )

        plan = EditPlan.model_validate_json(legacy_json)
        # Roundtrip: dump back to JSON and reload
        roundtripped = EditPlan.model_validate_json(plan.model_dump_json())

        assert len(roundtripped.filler_cuts) == 1
        assert roundtripped.filler_cuts[0].word == "um"
        assert len(roundtripped.content_cuts) == 1


class TestPhase8TriageReviewChain:
    """End-to-end triage -> review -> editorial_action derivation tests."""

    def test_triage_to_review_chain_editorial_actions(self, temp_dir: Path) -> None:
        """Triage -> review chain produces correct editorial actions for all filler categories.

        Scenario:
          - index 0: disfluency ("um") → remove
          - index 1: protected hedge ("like" with pause_before_ms=400) → keep
          - index 2: LLM-safe hedge ("you know", triage safe_to_remove=True) → remove
          - index 3: LLM-review hedge ("basically", triage safe_to_remove=False) → keep
        """
        from podcast_pipeline.stages.review import (
            _derive_editorial_action,
            _load_filler_triage_map,
        )

        job_dir = temp_dir / "triage-chain-job"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        # Filler cuts with Phase 8 fields
        filler_cuts = [
            {
                "start_seconds": 1.0,
                "end_seconds": 1.2,
                "word": "um",
                "confidence": 0.90,
                "category": "disfluency",
                "protected": False,
                "pause_before_ms": 50.0,
                "pause_after_ms": 30.0,
            },
            {
                "start_seconds": 3.0,
                "end_seconds": 3.2,
                "word": "like",
                "confidence": 0.80,
                "category": "hedge",
                "protected": True,  # pause gate fired (400ms pause)
                "pause_before_ms": 400.0,
                "pause_after_ms": 20.0,
            },
            {
                "start_seconds": 5.0,
                "end_seconds": 5.4,
                "word": "you know",
                "confidence": 0.85,
                "category": "hedge",
                "protected": False,
                "pause_before_ms": 80.0,
                "pause_after_ms": 60.0,
            },
            {
                "start_seconds": 7.0,
                "end_seconds": 7.3,
                "word": "basically",
                "confidence": 0.82,
                "category": "hedge",
                "protected": False,
                "pause_before_ms": 90.0,
                "pause_after_ms": 40.0,
            },
        ]
        (analysis_dir / "filler_cuts.json").write_text(json.dumps(filler_cuts))

        # Triage results: "you know" is safe, "basically" is not safe
        triage_results = [
            {
                "filler_index": 2,
                "word": "you know",
                "safe_to_remove": True,
                "reason": "Conversational filler, no semantic content",
            },
            {
                "filler_index": 3,
                "word": "basically",
                "safe_to_remove": False,
                "reason": "Word introduces a key simplification the speaker relies on",
            },
        ]
        (analysis_dir / "filler_triage.json").write_text(json.dumps(triage_results))

        triage_map = _load_filler_triage_map(job_dir)

        # Verify triage map loaded correctly
        assert 2 in triage_map
        assert 3 in triage_map
        assert triage_map[2]["safe_to_remove"] is True
        assert triage_map[3]["safe_to_remove"] is False

        # Derive editorial actions for each filler
        expected = ["remove", "keep", "remove", "keep"]
        for idx, filler in enumerate(filler_cuts):
            action = _derive_editorial_action(filler, triage_map.get(idx), None)
            assert action == expected[idx], (
                f"Filler index {idx} ('{filler['word']}'): "
                f"expected '{expected[idx]}', got '{action}'"
            )

    def test_protected_filler_overrides_disfluency_category(self, temp_dir: Path) -> None:
        """protected=True must override even disfluency category -> keep."""
        from podcast_pipeline.stages.review import _derive_editorial_action

        # Unusual edge case: disfluency but protected (e.g. long pause before "um")
        filler = {
            "word": "um",
            "category": "disfluency",
            "protected": True,
        }
        action = _derive_editorial_action(filler, None, None)
        assert action == "keep"

    def test_explicit_action_overrides_all_rules(self, temp_dir: Path) -> None:
        """Explicit user action beats category, protection, and triage."""
        from podcast_pipeline.stages.review import _derive_editorial_action

        # Protected hedge with LLM safe=True, but explicit action="keep"
        filler = {
            "word": "like",
            "category": "hedge",
            "protected": True,
        }
        triage = {"safe_to_remove": True, "reason": "ok to remove"}

        # Explicit keep -> keep even when LLM says safe_to_remove
        action = _derive_editorial_action(filler, triage, "keep")
        assert action == "keep"

        # Explicit remove -> remove even when protected
        action = _derive_editorial_action(filler, triage, "remove")
        assert action == "remove"

    def test_write_edit_plan_uses_triage_enriched_fields(self, temp_dir: Path) -> None:
        """write_edit_plan populates llm_safe_to_remove and llm_reason from triage."""
        from podcast_pipeline.stages.review import (
            FillerDecision,
            ReviewDecisions,
            write_edit_plan,
        )

        job_dir = temp_dir / "triage-enriched-job"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        fillers = [
            {
                "start_seconds": 2.0,
                "end_seconds": 2.3,
                "word": "you know",
                "category": "hedge",
                "protected": False,
            }
        ]
        triage = [
            {
                "filler_index": 0,
                "word": "you know",
                "safe_to_remove": True,
                "reason": "Pure conversational filler",
            }
        ]
        (analysis_dir / "filler_cuts.json").write_text(json.dumps(fillers))
        (analysis_dir / "filler_triage.json").write_text(json.dumps(triage))
        (analysis_dir / "analysis.json").write_text(
            json.dumps({"content_cuts": [], "viral_clips": [], "thumbnail_frames": []})
        )

        decisions = ReviewDecisions(filler_decisions=[FillerDecision(index=0, action="remove")])
        edit_path = write_edit_plan(job_dir, decisions, {}, fillers)
        payload = json.loads(edit_path.read_text())

        assert len(payload["filler_cuts"]) == 1
        fc = payload["filler_cuts"][0]
        assert fc["llm_safe_to_remove"] is True
        assert fc["llm_reason"] == "Pure conversational filler"
        assert fc["category"] == "hedge"
        assert fc["protected"] is False


class TestPhase8RenderDisabledBaseline:
    """Regression tests: all Phase 8 features disabled = Phase 7 baseline."""

    def test_smoothing_config_all_phase8_disabled(self) -> None:
        """SmoothingConfig with all Phase 8 passes disabled has correct defaults."""
        from podcast_pipeline.config.settings import SmoothingConfig

        config = SmoothingConfig(
            de_breathing_enabled=False,
            noise_floor_match_enabled=False,
            pose_match_enabled=False,
            rife_enabled=False,
        )

        assert config.de_breathing_enabled is False
        assert config.noise_floor_match_enabled is False
        assert config.pose_match_enabled is False
        assert config.rife_enabled is False
        # Phase 7 fields still present and unchanged
        assert config.enabled is True
        assert config.micro_fade_ms == 30.0
        assert config.content_audio_crossfade_ms == 150.0
        assert config.content_video_dissolve_ms == 300.0

    def test_detect_breath_extension_returns_zero_when_vad_not_available(
        self, monkeypatch: pytest.MonkeyPatch, temp_dir: Path
    ) -> None:
        """detect_breath_extension must return 0.0 when silero-vad is not installed."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "silero_vad":
                raise ImportError("silero_vad not available in test environment")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from podcast_pipeline.utils import vad as vad_module

        monkeypatch.setattr(vad_module, "_vad_model", None)

        # Create a dummy audio file path (doesn't need to exist — we hit ImportError first)
        dummy_audio = temp_dir / "dummy.wav"
        dummy_audio.write_bytes(b"RIFF" + b"\x00" * 44)

        extension = vad_module.detect_breath_extension(dummy_audio, cut_out_seconds=5.0)
        assert extension == 0.0

    def test_measure_rms_db_returns_sentinel_when_librosa_not_available(
        self, monkeypatch: pytest.MonkeyPatch, temp_dir: Path
    ) -> None:
        """measure_rms_db must return -120.0 when librosa is not installed."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "librosa":
                raise ImportError("librosa not available in test environment")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        dummy_audio = temp_dir / "dummy.wav"
        dummy_audio.write_bytes(b"RIFF" + b"\x00" * 44)

        from podcast_pipeline.utils.noise_match import measure_rms_db

        rms = measure_rms_db(dummy_audio)
        assert rms == -120.0

    def test_pose_distance_returns_inf_when_cv2_not_available(
        self, monkeypatch: pytest.MonkeyPatch, temp_dir: Path
    ) -> None:
        """pose_distance must return float('inf') when opencv is not installed."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "cv2":
                raise ImportError("cv2 not available in test environment")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        dummy_frame = temp_dir / "frame.png"
        dummy_frame.write_bytes(b"PNG_HEADER")

        from podcast_pipeline.utils.pose_match import pose_distance

        dist = pose_distance(dummy_frame, dummy_frame)
        assert dist == float("inf")


# ──────────────────────────────────────────────────────────────────────────────
# Phase 9 — Branding profile resolution tests
# ──────────────────────────────────────────────────────────────────────────────


class TestBrandingAndResolve:
    """Tests for branding profile resolution in the runtime configuration flow."""

    def test_branding_not_configured_returns_none_from_analyze_stage(self, config: Config) -> None:
        """AnalyzeStage.resolve_branding_for_platform returns None when no profile configured."""
        assert config.branding.active_profile is None
        stage = AnalyzeStage(config)
        assert stage.resolve_branding_for_platform("youtube") is None
        assert stage.resolve_branding_for_platform("tiktok") is None

    def test_branding_config_default_values(self, config: Config) -> None:
        """BrandingConfig defaults should be backward-compatible (no active profile)."""
        assert config.branding.active_profile is None
        assert config.branding.branding_dir == Path("branding")

    def test_branding_config_accepts_profile_name(self) -> None:
        """BrandingConfig can be constructed with an active_profile name."""
        bc = BrandingConfig(active_profile="neon_viral", branding_dir=Path("/tmp/branding"))
        assert bc.active_profile == "neon_viral"
        assert bc.branding_dir == Path("/tmp/branding")

    def test_branding_resolve_with_active_profile_applies_overrides(
        self, config: Config, tmp_path: Path
    ) -> None:
        """resolve_branding_for_platform with a loaded profile applies platform overrides."""
        from podcast_pipeline.utils.branding import save_profile

        # Create a branding profile with a tiktok override.
        profile = BrandingProfile(
            profile_name="test_kit",
            brand_voice="Energetic Gen Z tone.",
            logo_placement="top_right",
            highlight_color="#FFFF00",
            platform_overrides={
                "tiktok": PlatformBrandingOverride(
                    logo_placement="bottom_left",
                    highlight_color="#FF0000",
                )
            },
        )
        branding_dir = tmp_path / "branding"
        save_profile(profile, branding_dir=branding_dir)

        # Wire config to use the saved profile.
        config_with_branding = Config.model_validate(
            config.model_dump()
            | {"branding": {"active_profile": "test_kit", "branding_dir": str(branding_dir)}}
        )
        stage = AnalyzeStage(config_with_branding)

        # youtube: no override → base profile values
        yt = stage.resolve_branding_for_platform("youtube")
        assert yt is not None
        assert yt.logo_placement == "top_right"
        assert yt.highlight_color == "#FFFF00"
        assert yt.platform_overrides == {}

        # tiktok: override applied
        tk = stage.resolve_branding_for_platform("tiktok")
        assert tk is not None
        assert tk.logo_placement == "bottom_left"
        assert tk.highlight_color == "#FF0000"
        assert tk.platform_overrides == {}

    def test_branding_resolve_missing_profile_file_returns_none(
        self, config: Config, tmp_path: Path
    ) -> None:
        """When active_profile points to a non-existent YAML, AnalyzeStage logs and returns None."""
        config_with_missing = Config.model_validate(
            config.model_dump()
            | {
                "branding": {
                    "active_profile": "does_not_exist",
                    "branding_dir": str(tmp_path / "branding"),
                }
            }
        )
        # AnalyzeStage construction must not raise; missing profile logs a warning.
        stage = AnalyzeStage(config_with_missing)
        assert stage._active_branding is None
        assert stage.resolve_branding_for_platform("youtube") is None

    def test_pipeline_runs_without_branding_configured(
        self, config: Config, temp_dir: Path
    ) -> None:
        """Pipeline runs without error when branding section is absent (default config)."""
        pipeline = Pipeline(config)
        # Default Config() has no active branding — stage construction must succeed.
        analyze_stage = pipeline.stages.get("analyze")
        assert analyze_stage is not None


# =============================================================================
# Phase 9.7 — Sync artifact wiring tests
# =============================================================================


class TestIngestSyncArtifact:
    """Tests for sync artifact generation in IngestStage._run_sync_estimation."""

    def test_sync_skipped_for_single_audio_track(self, config: Config, temp_dir: Path) -> None:
        """_run_sync_estimation should return None when audio_track_count < 2."""
        from podcast_pipeline.stages.ingest import IngestStage

        stage = IngestStage(config)
        metadata = {"audio_track_count": 1}
        artifact_path = temp_dir / "sync_artifact.json"

        result = stage._run_sync_estimation(
            input_path=temp_dir / "input.mp4",
            metadata=metadata,
            intermediate_dir=temp_dir,
            artifact_path=artifact_path,
        )

        assert result is None
        assert not artifact_path.exists()

    def test_sync_skipped_when_audio_track_count_missing(
        self, config: Config, temp_dir: Path
    ) -> None:
        """_run_sync_estimation should skip when audio_track_count key is absent."""
        from podcast_pipeline.stages.ingest import IngestStage

        stage = IngestStage(config)
        metadata: dict[str, object] = {}  # no audio_track_count
        artifact_path = temp_dir / "sync_artifact.json"

        result = stage._run_sync_estimation(
            input_path=temp_dir / "input.mp4",
            metadata=metadata,
            intermediate_dir=temp_dir,
            artifact_path=artifact_path,
        )

        assert result is None

    def test_sync_estimation_writes_artifact_on_success(
        self, config: Config, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When SyncEstimator succeeds on a multi-track file, artifact is persisted to disk."""
        from podcast_pipeline.stages.ingest import IngestStage
        from podcast_pipeline.utils.sync import SyncResult

        stage = IngestStage(config)
        metadata = {"audio_track_count": 2}
        artifact_path = temp_dir / "sync_artifact.json"
        input_path = temp_dir / "input.mp4"
        input_path.write_bytes(b"fake_video")

        # Stub out stream extraction and SyncEstimator
        fake_result = SyncResult(
            offset_ms=125.0,
            confidence=0.72,
            source="correlation",
            no_clap=False,
            low_confidence=False,
            warnings=[],
        )

        def _noop_extract(src: object, dst: Path, stream_index: int) -> None:  # type: ignore[name-defined]
            dst.write_bytes(b"")

        monkeypatch.setattr(
            "podcast_pipeline.stages.ingest.IngestStage._extract_stream_wav",
            staticmethod(_noop_extract),
        )

        class _FakeEstimator:
            def __init__(self, search_window_s: float = 60.0) -> None:
                pass

            def _estimate_from_wavs(self, _ref: object, _ext: object) -> SyncResult:
                return fake_result

        monkeypatch.setattr(
            "podcast_pipeline.utils.sync.SyncEstimator",
            _FakeEstimator,
        )

        result = stage._run_sync_estimation(
            input_path=input_path,
            metadata=metadata,
            intermediate_dir=temp_dir,
            artifact_path=artifact_path,
        )

        assert result is not None
        assert result["offset_ms"] == 125.0
        assert result["confidence"] == 0.72
        assert result["low_confidence"] is False
        assert artifact_path.exists()
        loaded = json.loads(artifact_path.read_text())
        assert loaded["offset_ms"] == 125.0

    def test_sync_estimation_returns_none_on_ffmpeg_failure(
        self, config: Config, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stream extraction FFmpegError should be handled gracefully (returns None)."""
        from podcast_pipeline.stages.ingest import IngestStage
        from podcast_pipeline.utils.ffmpeg import FFmpegError

        stage = IngestStage(config)
        metadata = {"audio_track_count": 2}
        artifact_path = temp_dir / "sync_artifact.json"

        def _raise_ffmpeg(src: object, dst: object, stream_index: int) -> None:
            raise FFmpegError("stream extraction failed")

        monkeypatch.setattr(
            "podcast_pipeline.stages.ingest.IngestStage._extract_stream_wav",
            staticmethod(_raise_ffmpeg),
        )

        result = stage._run_sync_estimation(
            input_path=temp_dir / "input.mp4",
            metadata=metadata,
            intermediate_dir=temp_dir,
            artifact_path=artifact_path,
        )

        assert result is None
        assert not artifact_path.exists()

    def test_extract_stream_wav_builds_correct_ffmpeg_args(
        self, config: Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_extract_stream_wav should request -map 0:a:<N> -ac 1 -ar 8000 -t 60 via run_ffmpeg."""
        from podcast_pipeline.stages.ingest import IngestStage

        stage = IngestStage(config)
        captured_args: list[list[str]] = []

        def _capture(args: list[str], **_kwargs: object) -> None:
            captured_args.append(args)

        monkeypatch.setattr("podcast_pipeline.stages.ingest.run_ffmpeg", _capture)

        from pathlib import Path

        stage._extract_stream_wav(
            src=Path("/tmp/input.mp4"),
            dst=Path("/tmp/out.wav"),
            stream_index=1,
        )

        assert len(captured_args) == 1
        args = captured_args[0]
        assert "-map" in args
        assert "0:a:1" in args
        assert "-ac" in args
        assert "1" in args
        assert "-ar" in args
        assert "8000" in args
        assert "-t" in args
        assert "60" in args


class TestRenderSyncOffset:
    """Tests for sync offset resolution and application in RenderStage."""

    def test_resolve_sync_offset_prefers_manual_over_auto(
        self, config: Config, temp_dir: Path
    ) -> None:
        """Manual sync override in decisions takes priority over auto artifact."""
        from podcast_pipeline.stages.render import RenderStage
        from podcast_pipeline.stages.review import ReviewDecisions

        # Write an auto sync artifact that would produce a different offset
        artifact_path = temp_dir / "intermediate" / "sync_artifact.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(
                {
                    "offset_ms": 300.0,
                    "confidence": 0.9,
                    "low_confidence": False,
                    "no_clap": False,
                }
            )
        )

        decisions = ReviewDecisions(manual_sync_offset_ms=750.0)
        stage = RenderStage(config)

        offset_ms, meta = stage._resolve_sync_offset(temp_dir, decisions)

        assert offset_ms == 750.0
        assert meta["source"] == "manual"

    def test_resolve_sync_offset_loads_auto_artifact_when_no_manual_override(
        self, config: Config, temp_dir: Path
    ) -> None:
        """Auto sync artifact should be loaded when manual_sync_offset_ms is None."""
        from podcast_pipeline.stages.render import RenderStage
        from podcast_pipeline.stages.review import ReviewDecisions

        artifact_path = temp_dir / "intermediate" / "sync_artifact.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(
                {
                    "offset_ms": 200.0,
                    "confidence": 0.65,
                    "low_confidence": False,
                    "no_clap": True,
                }
            )
        )

        decisions = ReviewDecisions(manual_sync_offset_ms=None)
        stage = RenderStage(config)

        offset_ms, meta = stage._resolve_sync_offset(temp_dir, decisions)

        assert offset_ms == 200.0
        assert meta["source"] == "auto"
        assert meta["confidence"] == 0.65

    def test_resolve_sync_offset_returns_none_when_no_artifact(
        self, config: Config, temp_dir: Path
    ) -> None:
        """Returns (None, source=None) when no sync artifact and no manual override."""
        from podcast_pipeline.stages.render import RenderStage
        from podcast_pipeline.stages.review import ReviewDecisions

        stage = RenderStage(config)
        decisions = ReviewDecisions(manual_sync_offset_ms=None)

        offset_ms, meta = stage._resolve_sync_offset(temp_dir, decisions)

        assert offset_ms is None
        assert meta["source"] is None

    def test_apply_sync_offset_positive_delays_external_track(
        self, config: Config, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive offset should produce -itsoffset on the second -i (external track lags)."""
        from podcast_pipeline.stages.render import RenderStage

        stage = RenderStage(config)
        captured: list[list[str]] = []

        def _fake_run_ffmpeg(args: list[str], **_kwargs: object) -> None:
            captured.append(args)
            # Create the expected output file so the check passes
            synced_path = temp_dir / "intermediate" / "synced_input.mp4"
            synced_path.parent.mkdir(parents=True, exist_ok=True)
            synced_path.write_bytes(b"synced_fake_video")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_run_ffmpeg)

        input_video = temp_dir / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"fake_video")

        result = stage._apply_sync_offset(input_video, temp_dir, offset_ms=500.0)

        assert result is not None
        assert result.name == "synced_input.mp4"
        args = captured[0]
        # Positive offset: first -i has no -itsoffset, second -i has -itsoffset
        assert args[0] == "-i"  # first input has no itsoffset prefix
        assert "-itsoffset" in args

    def test_apply_sync_offset_negative_delays_reference_track(
        self, config: Config, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative offset should use -itsoffset before the first -i (reference lags)."""
        from podcast_pipeline.stages.render import RenderStage

        stage = RenderStage(config)
        captured: list[list[str]] = []

        def _fake_run_ffmpeg(args: list[str], **_kwargs: object) -> None:
            captured.append(args)
            synced_path = temp_dir / "intermediate" / "synced_input.mp4"
            synced_path.parent.mkdir(parents=True, exist_ok=True)
            synced_path.write_bytes(b"synced_fake_video")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _fake_run_ffmpeg)

        input_video = temp_dir / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"fake_video")

        result = stage._apply_sync_offset(input_video, temp_dir, offset_ms=-300.0)

        assert result is not None
        args = captured[0]
        # Negative offset: -itsoffset before first -i
        assert args[0] == "-itsoffset"

    def test_apply_sync_offset_returns_none_on_ffmpeg_failure(
        self, config: Config, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FFmpegError in _apply_sync_offset should log and return None gracefully."""
        from podcast_pipeline.stages.render import RenderStage
        from podcast_pipeline.utils.ffmpeg import FFmpegError

        stage = RenderStage(config)

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise FFmpegError("mux failed")

        monkeypatch.setattr("podcast_pipeline.stages.render.run_ffmpeg", _raise)

        input_video = temp_dir / "input" / "raw.mp4"
        input_video.parent.mkdir(parents=True, exist_ok=True)
        input_video.write_bytes(b"fake_video")

        result = stage._apply_sync_offset(input_video, temp_dir, offset_ms=100.0)
        assert result is None
