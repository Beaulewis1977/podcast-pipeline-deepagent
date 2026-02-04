"""Pytest configuration and fixtures."""

import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from podcast_pipeline.config import Config, load_config
from podcast_pipeline.models.job import Job


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
def config(temp_dir: Path) -> Config:
    """Create a test configuration."""
    config = Config()
    config.paths.jobs_dir = temp_dir / "jobs"
    config.paths.jobs_dir.mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def sample_job(config: Config) -> Job:
    """Create a sample job for testing."""
    job = Job(
        job_id="test-job-001",
        input_file="/path/to/test/video.mp4",
    )
    return job


@pytest.fixture
def sample_transcript() -> dict:
    """Create sample transcript data."""
    return {
        "text": "Hello and welcome to our podcast. Um, today we're going to talk about AI.",
        "segments": [
            {
                "start": 0.0,
                "end": 2.5,
                "text": "Hello and welcome to our podcast.",
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.99},
                    {"word": "and", "start": 0.5, "end": 0.7, "confidence": 0.98},
                    {"word": "welcome", "start": 0.7, "end": 1.2, "confidence": 0.99},
                    {"word": "to", "start": 1.2, "end": 1.4, "confidence": 0.97},
                    {"word": "our", "start": 1.4, "end": 1.6, "confidence": 0.98},
                    {"word": "podcast", "start": 1.6, "end": 2.5, "confidence": 0.99},
                ],
            },
            {
                "start": 2.5,
                "end": 6.0,
                "text": "Um, today we're going to talk about AI.",
                "words": [
                    {"word": "Um", "start": 2.5, "end": 2.8, "confidence": 0.85},
                    {"word": "today", "start": 3.0, "end": 3.5, "confidence": 0.99},
                    {"word": "we're", "start": 3.5, "end": 3.8, "confidence": 0.98},
                    {"word": "going", "start": 3.8, "end": 4.1, "confidence": 0.99},
                    {"word": "to", "start": 4.1, "end": 4.3, "confidence": 0.97},
                    {"word": "talk", "start": 4.3, "end": 4.6, "confidence": 0.99},
                    {"word": "about", "start": 4.6, "end": 4.9, "confidence": 0.98},
                    {"word": "AI", "start": 4.9, "end": 6.0, "confidence": 0.99},
                ],
            },
        ],
        "filler_cuts": [],
        "language": "en",
        "duration": 6.0,
    }
