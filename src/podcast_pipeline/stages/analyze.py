"""Analyze stage: AI analysis of video content."""

import json
from pathlib import Path

from podcast_pipeline.config import Config
from podcast_pipeline.models.job import Job
from podcast_pipeline.providers.base import ProviderError
from podcast_pipeline.providers.gemini import GeminiProvider
from podcast_pipeline.providers.kimi import KimiProvider
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.utils.logging import get_logger

logger = get_logger(__name__)


class AnalyzeStage(Stage):
    """Analyze video content using AI providers."""

    name = "analyze"

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

                return StageResult(
                    success=True,
                    outputs=[str(analysis_path.relative_to(job_dir))],
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
