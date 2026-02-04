"""Analyze stage: AI analysis of video content."""

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from podcast_pipeline.config import Config
from podcast_pipeline.models.analysis import AnalysisResult
from podcast_pipeline.models.job import Job
from podcast_pipeline.providers.base import ProviderError
from podcast_pipeline.providers.gemini import GeminiProvider
from podcast_pipeline.providers.kimi import KimiProvider
from podcast_pipeline.research.viral_detector import ViralClipDetector
from podcast_pipeline.research.youtube import ResearchResult, YouTubeResearcher
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)


class AnalyzeStage(Stage):
    """Analyze video content using AI providers."""

    name = "analyze"
    ai_score_weight = 0.45
    detector_score_weight = 0.55

    def __init__(self, config: Config):
        super().__init__(config)
        self.providers: list[GeminiProvider | KimiProvider] = []

        # Initialize primary provider
        if config.api_keys.gemini:
            self.providers.append(
                GeminiProvider(
                    api_key=config.api_keys.gemini,
                    model=config.models.model,
                )
            )

        # Initialize fallback provider
        if config.api_keys.kimi:
            self.providers.append(
                KimiProvider(
                    api_key=config.api_keys.kimi,
                    model=config.models.fallback_model or "moonshot-v1-128k",
                )
            )

    def run(self, job: Job, job_dir: Path) -> StageResult:
        """Execute analysis stage.

        Creates:
            - analysis/analysis.json
            - analysis/research.json (optional)
            - analysis/viral_signals.json
        """
        # Check for required files
        transcript_path = job_dir / "analysis" / "transcript.json"
        proxy_path = job_dir / "intermediate" / "proxy.mp4"

        if not transcript_path.exists():
            return StageResult(
                success=False,
                error=f"Transcript not found: {transcript_path}. Run transcribe stage first.",
            )

        if not proxy_path.exists():
            return StageResult(
                success=False,
                error=f"Proxy video not found: {proxy_path}. Run ingest stage first.",
            )

        # Load transcript
        transcript_data = json.loads(transcript_path.read_text())

        # Try each provider
        last_error: str | None = None
        used_provider: str | None = None
        used_model: str | None = None

        for provider in self.providers:
            if not provider.is_available():
                self.logger.info(
                    "provider_unavailable",
                    provider=provider.name,
                )
                continue

            self.logger.info(
                "trying_provider",
                provider=provider.name,
            )

            try:
                result = provider.analyze(proxy_path, transcript_data)
                used_provider = provider.name
                used_model = getattr(provider, "model", "unknown")

                # Save analysis result
                analysis_path = job_dir / "analysis" / "analysis.json"
                analysis_path.parent.mkdir(parents=True, exist_ok=True)
                analysis_path.write_text(result.model_dump_json(indent=2))

                # Update job with provider info
                job.stages[self.name].provider = used_provider
                job.stages[self.name].model = used_model

                self.logger.info(
                    "analysis_complete",
                    provider=used_provider,
                    model=used_model,
                    clips=len(result.viral_clips),
                    cuts=len(result.content_cuts),
                )

                outputs = [str(analysis_path.relative_to(job_dir))]

                # Optional research integration
                research_output = self._run_research(job, result, job_dir)
                if research_output:
                    outputs.append(research_output)

                # Viral signal analysis
                viral_output = self._run_viral_signals(result, transcript_data, job_dir)
                if viral_output:
                    outputs.append(viral_output)

                self.logger.info("analysis_outputs_ready", outputs=outputs)

                return StageResult(
                    success=True,
                    outputs=outputs,
                    data={
                        "provider": used_provider,
                        "model": used_model,
                        "analysis": result.model_dump(),
                    },
                )

            except ProviderError as e:
                last_error = str(e)
                self.logger.warning(
                    "provider_failed",
                    provider=provider.name,
                    error=last_error,
                )
                continue

        # All providers failed
        if not self.providers:
            return StageResult(
                success=False,
                error="No AI providers configured. Set GEMINI_API_KEY or KIMI_API_KEY in .env",
            )

        return StageResult(
            success=False,
            error=f"All providers failed. Last error: {last_error}",
        )

    def _run_research(
        self,
        job: Job,
        analysis_result: AnalysisResult,
        job_dir: Path,
    ) -> str | None:
        """Run YouTube research if configured."""
        api_key = self.config.api_keys.youtube
        if not api_key:
            self.logger.info("research_skipped", reason="missing_api_key")
            return None

        researcher = None
        try:
            analysis_data = (
                analysis_result.model_dump() if hasattr(analysis_result, "model_dump") else {}
            )
            query, related_topics = self._derive_research_query(job, analysis_data)

            researcher = YouTubeResearcher(api_key=api_key)
            research_result: ResearchResult = researcher.research_topic(
                query, related_topics=related_topics
            )

            research_path = job_dir / "analysis" / "research.json"
            research_path.parent.mkdir(parents=True, exist_ok=True)
            research_path.write_text(research_result.model_dump_json(indent=2))

            self.logger.info(
                "research_complete",
                query=query,
                topics=len(research_result.topics),
                videos=len(research_result.trending_videos),
            )

            return str(research_path.relative_to(job_dir))
        except Exception as e:
            self.logger.warning("research_failed", error=str(e))
            return None
        finally:
            if researcher is not None:
                researcher.close()

    def _derive_research_query(
        self,
        job: Job,
        analysis_data: dict[str, Any],
    ) -> tuple[str, list[str]]:
        """Derive research query from analysis metadata or job name."""
        topics = analysis_data.get("metadata", {}).get("topics", []) or []
        topics = [topic for topic in topics if topic]
        if topics:
            return topics[0], topics[1:4]

        fallback = Path(job.input_file).stem or job.job_id
        return fallback, []

    def _normalize_score(self, value: Any, default: float = 5.0) -> float:
        """Normalize potentially-missing score inputs to bounded floats."""
        try:
            score = float(value)
        except (TypeError, ValueError):
            return default
        return min(max(score, 0.0), 10.0)

    def _combined_score(self, ai_score: float, detector_score: float) -> float:
        """Blend provider and detector scores into one bounded value."""
        combined = (
            ai_score * self.ai_score_weight
            + detector_score * self.detector_score_weight
        )
        return min(max(combined, 0.0), 10.0)

    def _run_viral_signals(
        self,
        analysis_result: AnalysisResult,
        transcript_data: dict[str, Any],
        job_dir: Path,
    ) -> str | None:
        """Compute viral signals and per-clip scores."""
        try:
            analysis_data = (
                analysis_result.model_dump() if hasattr(analysis_result, "model_dump") else {}
            )
            detector = ViralClipDetector()
            signals = detector.analyze_transcript(transcript_data)

            clip_scores = []
            for clip in analysis_data.get("viral_clips", []) or []:
                score = detector.score_clip(clip, transcript_data, signals)
                ai_score = self._normalize_score(clip.get("virality_score"))
                detector_score = self._normalize_score(score.overall_score, default=0.0)
                combined_score = self._combined_score(ai_score, detector_score)
                clip_scores.append(
                    {
                        "clip": clip,
                        "score": score.model_dump(),
                        "ai_score": round(ai_score, 2),
                        "detector_score": round(detector_score, 2),
                        "combined_score": round(combined_score, 2),
                    }
                )

            clip_scores.sort(
                key=lambda item: (item["combined_score"], item["detector_score"]),
                reverse=True,
            )
            for rank, item in enumerate(clip_scores, start=1):
                item["rank"] = rank

            def _serialize_signal(obj: Any) -> dict[str, Any]:
                """Safely serialize dataclass or Pydantic model to dict."""
                if hasattr(obj, "model_dump"):
                    return dict(obj.model_dump())
                if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                    return dataclasses.asdict(obj)
                if isinstance(obj, dict):
                    return obj
                return dict(vars(obj))

            viral_payload = {
                "generated_at": datetime.now(UTC).isoformat(),
                "signals": [_serialize_signal(signal) for signal in signals],
                "clip_scores": clip_scores,
            }

            viral_path = job_dir / "analysis" / "viral_signals.json"
            viral_path.parent.mkdir(parents=True, exist_ok=True)
            viral_path.write_text(json.dumps(viral_payload, indent=2))

            self.logger.info(
                "viral_signals_complete",
                signals=len(signals),
                clips=len(clip_scores),
            )

            return str(viral_path.relative_to(job_dir))
        except Exception as e:
            self.logger.warning("viral_signals_failed", error=str(e))
            return None
