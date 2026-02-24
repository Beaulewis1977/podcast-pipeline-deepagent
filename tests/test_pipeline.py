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
