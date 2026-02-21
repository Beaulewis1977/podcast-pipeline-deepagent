"""Tests for pipeline orchestration."""

import json
import threading
from pathlib import Path

import pytest

from podcast_pipeline.config import Config
from podcast_pipeline.models.analysis import AnalysisResult
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


class TestStageValidation:
    """Tests for strict stage validation at pipeline entry points."""

    def test_invalid_stage_rejected_with_validation_error(self, config: Config) -> None:
        """Invalid explicit stage names should fail fast."""
        pipeline = Pipeline(config)
        job = Job(job_id="invalid-stage-job", input_file="/tmp/test.mp4")  # noqa: S108

        with pytest.raises(ValueError, match="Unknown stage: invalid-stage"):
            pipeline.run(job, stage="invalid-stage")

        assert job.status == StageStatus.PENDING
        assert all(stage.status == StageStatus.PENDING for stage in job.stages.values())

    def test_invalid_stage_validation_for_until_stage(self, config: Config) -> None:
        """Invalid until_stage values should fail fast."""
        pipeline = Pipeline(config)
        job = Job(job_id="invalid-until-job", input_file="/tmp/test.mp4")  # noqa: S108

        with pytest.raises(ValueError, match="Unknown stage: not-a-stage"):
            pipeline.run(job, until_stage="not-a-stage")

        assert job.status == StageStatus.PENDING


class TestPipelineLocking:
    """Tests for lock acquisition and state reload boundaries."""

    def test_state_reload_uses_latest_job_state(self, config: Config) -> None:
        """state_reload should skip stages already complete on disk."""
        pipeline = Pipeline(config)
        job = Job(job_id="state-reload-job", input_file="/tmp/test.mp4")  # noqa: S108
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
        job = Job(job_id="lock-contention-job", input_file="/tmp/test.mp4")  # noqa: S108
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

        monkeypatch.setattr("podcast_pipeline.stages.analyze.run_ffmpeg", _fake_ffmpeg)

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
