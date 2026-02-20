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
from podcast_pipeline.utils.ffmpeg import FFmpegError, run_ffmpeg
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
        trend_context = self._load_prompt_trend_context(job_dir)

        # Try each provider
        last_error: str | None = None
        used_provider: str | None = None
        used_model: str | None = None

        for provider_index, provider in enumerate(self.providers):
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
                provider_transcript = dict(transcript_data)
                if trend_context is not None:
                    provider_transcript["trend_context"] = trend_context
                result = provider.analyze(proxy_path, provider_transcript)
                used_provider = provider.name
                used_model = getattr(provider, "model", "unknown")
                degraded_mode = self._build_degraded_mode_metadata(
                    provider=provider,
                    provider_index=provider_index,
                )
                analysis_payload = result.model_dump()
                metadata_payload = analysis_payload.setdefault("metadata", {})
                metadata_payload["degraded_mode"] = degraded_mode
                thumbnail_artifacts = self._materialize_thumbnail_frames(
                    proxy_path=proxy_path,
                    analysis_payload=analysis_payload,
                    job_dir=job_dir,
                )
                if thumbnail_artifacts:
                    self.logger.info(
                        "analysis_thumbnail_frames_materialized",
                        generated=len(thumbnail_artifacts),
                    )

                # Save analysis result
                analysis_path = job_dir / "analysis" / "analysis.json"
                analysis_path.parent.mkdir(parents=True, exist_ok=True)
                analysis_path.write_text(json.dumps(analysis_payload, indent=2))

                # Update job with provider info
                job.stages[self.name].provider = used_provider
                job.stages[self.name].model = used_model

                if degraded_mode["enabled"]:
                    self.logger.warning(
                        "analysis_degraded_mode",
                        provider=used_provider,
                        model=used_model,
                        reason=degraded_mode["reason"],
                    )

                self.logger.info(
                    "analysis_complete",
                    provider=used_provider,
                    model=used_model,
                    clips=len(result.viral_clips),
                    cuts=len(result.content_cuts),
                )

                outputs = [str(analysis_path.relative_to(job_dir))]

                # Optional research integration
                research_output = self._run_research(job, result, transcript_data, job_dir)
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
                        "degraded_mode": degraded_mode,
                        "analysis": analysis_payload,
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

    def _materialize_thumbnail_frames(
        self,
        proxy_path: Path,
        analysis_payload: dict[str, Any],
        job_dir: Path,
    ) -> list[str]:
        """Extract thumbnail frame image artifacts for UI preview rendering."""
        raw_frames = analysis_payload.get("thumbnail_frames")
        if not isinstance(raw_frames, list) or not raw_frames:
            return []

        thumbnail_dir = job_dir / "intermediate" / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        generated: list[str] = []
        for index, raw_frame in enumerate(raw_frames, start=1):
            if not isinstance(raw_frame, dict):
                continue

            timestamp_seconds = self._parse_thumbnail_timestamp_seconds(
                raw_seconds=raw_frame.get("timestamp_seconds"),
                raw_timestamp=raw_frame.get("timestamp"),
            )
            if timestamp_seconds is None:
                self.logger.warning(
                    "analysis_thumbnail_frame_missing_timestamp",
                    index=index,
                )
                continue

            timestamp_millis = int(round(timestamp_seconds * 1000))
            thumbnail_path = thumbnail_dir / f"thumbnail_{index:02d}_{timestamp_millis:08d}ms.jpg"
            ffmpeg_args = [
                "-ss",
                f"{timestamp_seconds:.3f}",
                "-i",
                str(proxy_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(thumbnail_path),
            ]

            try:
                run_ffmpeg(ffmpeg_args, timeout=120)
            except (FFmpegError, FileNotFoundError) as exc:
                self.logger.warning(
                    "analysis_thumbnail_frame_extract_failed",
                    index=index,
                    timestamp_seconds=timestamp_seconds,
                    error=str(exc),
                )
                continue

            try:
                if not thumbnail_path.exists() or thumbnail_path.stat().st_size == 0:
                    self.logger.warning(
                        "analysis_thumbnail_frame_extract_empty",
                        index=index,
                        path=str(thumbnail_path),
                    )
                    continue
            except OSError as exc:
                self.logger.warning(
                    "analysis_thumbnail_frame_stat_failed",
                    index=index,
                    path=str(thumbnail_path),
                    error=str(exc),
                )
                continue

            relative_path = str(thumbnail_path.relative_to(job_dir))
            raw_frame["image_path"] = relative_path
            generated.append(relative_path)

        return generated

    def _parse_thumbnail_timestamp_seconds(
        self,
        raw_seconds: Any,
        raw_timestamp: Any,
    ) -> float | None:
        """Parse thumbnail timestamp values to non-negative seconds."""
        if isinstance(raw_seconds, (int, float)):
            return max(float(raw_seconds), 0.0)

        if not isinstance(raw_timestamp, str):
            return None
        value = raw_timestamp.strip()
        if not value:
            return None

        parts = value.split(":")
        if len(parts) not in {2, 3}:
            return None
        try:
            numeric = [float(part) for part in parts]
        except ValueError:
            return None

        if any(part < 0 for part in numeric):
            return None

        if len(numeric) == 2:
            minutes, seconds = numeric
            if seconds >= 60:
                return None
            return (minutes * 60.0) + seconds

        hours, minutes, seconds = numeric
        if minutes >= 60 or seconds >= 60:
            return None
        return (hours * 3600.0) + (minutes * 60.0) + seconds

    def _load_prompt_trend_context(self, job_dir: Path) -> dict[str, Any] | None:
        """Load optional trend context from prior research artifacts for prompt injection."""
        research_payload = self._load_optional_analysis_payload(job_dir / "analysis" / "research.json")
        viral_payload = self._load_optional_analysis_payload(
            job_dir / "analysis" / "viral_signals.json"
        )

        if research_payload is None and viral_payload is None:
            return None

        keywords = self._extract_trend_keywords(research_payload)
        trending_hooks = self._extract_trending_hooks(research_payload, viral_payload)
        competitive_angle = self._extract_competitive_angle(research_payload)
        momentum_signals = self._extract_momentum_signals(research_payload, viral_payload)

        if not any([keywords, trending_hooks, competitive_angle, momentum_signals]):
            return None

        trend_context = {
            "keywords": keywords,
            "trending_hooks": trending_hooks,
            "competitive_angle": competitive_angle,
            "momentum_signals": momentum_signals,
        }

        self.logger.info(
            "analysis_prompt_trend_context_loaded",
            keywords=len(keywords),
            hooks=len(trending_hooks),
            momentum_signals=len(momentum_signals),
        )
        return trend_context

    def _load_optional_analysis_payload(self, path: Path) -> dict[str, Any] | None:
        """Read an optional artifact payload and normalize to dictionary values."""
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.warning("analysis_trend_context_load_failed", path=str(path), error=str(exc))
            return None
        if not isinstance(raw, dict):
            self.logger.warning(
                "analysis_trend_context_invalid_payload",
                path=str(path),
                payload_type=type(raw).__name__,
            )
            return None
        return raw

    def _extract_trend_keywords(self, research_payload: dict[str, Any] | None) -> list[str]:
        """Extract trend keywords and related topics from research artifacts."""
        if not research_payload:
            return []

        collected: list[str] = []
        suggested_keywords = research_payload.get("suggested_keywords")
        if isinstance(suggested_keywords, list):
            for value in suggested_keywords:
                if isinstance(value, str):
                    text = value.strip()
                    if text:
                        collected.append(text)

        insights = research_payload.get("insights")
        if isinstance(insights, dict):
            query_derivation = insights.get("query_derivation")
            if isinstance(query_derivation, dict):
                query = query_derivation.get("query")
                if isinstance(query, str) and query.strip():
                    collected.append(query.strip())
                related_topics = query_derivation.get("related_topics")
                if isinstance(related_topics, list):
                    for topic in related_topics:
                        if isinstance(topic, str):
                            text = topic.strip()
                            if text:
                                collected.append(text)

        return self._dedupe_strings(collected)

    def _extract_trending_hooks(
        self,
        research_payload: dict[str, Any] | None,
        viral_payload: dict[str, Any] | None,
    ) -> list[str]:
        """Extract trend hooks from prior viral signals and research recommendations."""
        collected: list[str] = []
        if viral_payload:
            clip_scores = viral_payload.get("clip_scores")
            if isinstance(clip_scores, list):
                for row in clip_scores[:5]:
                    if not isinstance(row, dict):
                        continue
                    clip = row.get("clip")
                    if isinstance(clip, dict):
                        suggested_hook = clip.get("suggested_hook")
                        if isinstance(suggested_hook, str) and suggested_hook.strip():
                            collected.append(suggested_hook.strip())
                    reasons = row.get("reasons")
                    if isinstance(reasons, list):
                        for reason in reasons[:2]:
                            if isinstance(reason, str):
                                text = reason.strip()
                                if text:
                                    collected.append(text)

        if research_payload:
            insights = research_payload.get("insights")
            if isinstance(insights, dict):
                recommendation = insights.get("recommendation")
                if isinstance(recommendation, str) and recommendation.strip():
                    collected.append(recommendation.strip())

        return self._dedupe_strings(collected)

    def _extract_competitive_angle(self, research_payload: dict[str, Any] | None) -> str:
        """Extract a concise competitive angle summary from research insights."""
        if not research_payload:
            return ""

        insights = research_payload.get("insights")
        if not isinstance(insights, dict):
            return ""

        recommendation = insights.get("recommendation")
        if isinstance(recommendation, str) and recommendation.strip():
            return recommendation.strip()

        competition_tier = insights.get("competition_tier")
        if isinstance(competition_tier, str) and competition_tier.strip():
            return f"Competition tier: {competition_tier.strip()}"

        competition_score = insights.get("competition_score")
        if isinstance(competition_score, (int, float)):
            return f"Competition score: {competition_score:.1f}/100"

        return ""

    def _extract_momentum_signals(
        self,
        research_payload: dict[str, Any] | None,
        viral_payload: dict[str, Any] | None,
    ) -> list[str]:
        """Extract compact momentum signals from research and viral-score artifacts."""
        collected: list[str] = []
        if research_payload:
            insights = research_payload.get("insights")
            if isinstance(insights, dict):
                engagement = insights.get("engagement_benchmarks")
                if isinstance(engagement, dict):
                    avg_velocity = engagement.get("avg_velocity_per_hour")
                    if isinstance(avg_velocity, (int, float)):
                        collected.append(f"avg_velocity_per_hour={avg_velocity:.2f}")

        if viral_payload:
            clip_scores = viral_payload.get("clip_scores")
            if isinstance(clip_scores, list):
                for row in clip_scores[:3]:
                    if not isinstance(row, dict):
                        continue
                    combined_score = row.get("combined_score")
                    if isinstance(combined_score, (int, float)):
                        rank = row.get("rank")
                        rank_label = rank if isinstance(rank, int) else "n/a"
                        collected.append(
                            f"clip_rank_{rank_label}_combined_score={combined_score:.2f}"
                        )

        return self._dedupe_strings(collected)

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        """Return unique string values while preserving input order."""
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _build_degraded_mode_metadata(
        self,
        provider: GeminiProvider | KimiProvider,
        provider_index: int,
    ) -> dict[str, Any]:
        """Build degraded-mode metadata for transcript-only provider outputs."""
        supports_video = getattr(provider, "supports_video", True)
        if supports_video:
            return {
                "enabled": False,
                "reason": None,
                "provider": provider.name,
                "model": getattr(provider, "model", "unknown"),
            }

        is_fallback = provider_index > 0
        reason = "fallback_provider_transcript_only" if is_fallback else "provider_transcript_only"
        return {
            "enabled": True,
            "reason": reason,
            "provider": provider.name,
            "model": getattr(provider, "model", "unknown"),
        }

    def _run_research(
        self,
        job: Job,
        analysis_result: AnalysisResult,
        transcript_data: dict[str, Any],
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
            query, related_topics, query_source = self._derive_research_query(
                job=job,
                analysis_data=analysis_data,
                transcript_data=transcript_data,
            )

            researcher = YouTubeResearcher(api_key=api_key)
            research_result: ResearchResult = researcher.research_topic(
                query, related_topics=related_topics
            )
            research_result.insights["query_derivation"] = {
                "query": query,
                "related_topics": related_topics,
                "source": query_source,
            }

            research_path = job_dir / "analysis" / "research.json"
            research_path.parent.mkdir(parents=True, exist_ok=True)
            research_path.write_text(research_result.model_dump_json(indent=2))

            self.logger.info(
                "research_complete",
                query=query,
                query_source=query_source,
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
        transcript_data: dict[str, Any],
    ) -> tuple[str, list[str], str]:
        """Derive research query from metadata + transcript evidence."""
        topics = analysis_data.get("metadata", {}).get("topics", []) or []
        fallback = Path(job.input_file).stem or job.job_id
        query, related_topics, source = YouTubeResearcher.derive_query_terms(
            transcript_data=transcript_data,
            metadata_topics=topics,
            fallback_query=fallback,
        )
        return query, related_topics, source

    def _normalize_score(self, value: Any, default: float = 5.0) -> float:
        """Normalize potentially-missing score inputs to bounded floats."""
        try:
            score = float(value)
        except (TypeError, ValueError):
            return default
        return min(max(score, 0.0), 10.0)

    def _combined_score(self, ai_score: float, detector_score: float) -> float:
        """Blend provider and detector scores into one bounded value."""
        combined = ai_score * self.ai_score_weight + detector_score * self.detector_score_weight
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
                score_payload = score.model_dump()
                ai_score = self._normalize_score(clip.get("virality_score"))
                detector_score = self._normalize_score(score.overall_score, default=0.0)
                combined_score = self._combined_score(ai_score, detector_score)
                reason_snippets = [str(reason) for reason in score_payload.get("reasons", [])[:3]]
                clip_scores.append(
                    {
                        "clip": clip,
                        "score": score_payload,
                        "ai_score": round(ai_score, 2),
                        "detector_score": round(detector_score, 2),
                        "combined_score": round(combined_score, 2),
                        "reasons": reason_snippets,
                        "score_components": {
                            "ai_weight": self.ai_score_weight,
                            "detector_weight": self.detector_score_weight,
                        },
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
                "score_weights": {
                    "ai_weight": self.ai_score_weight,
                    "detector_weight": self.detector_score_weight,
                },
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
