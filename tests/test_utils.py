"""Tests for utility functions."""

import pytest

from podcast_pipeline.utils.time import (
    format_duration,
    seconds_to_srt_timestamp,
    seconds_to_timestamp,
    seconds_to_vtt_timestamp,
    timestamp_to_seconds,
)


class TestTimeUtils:
    """Tests for time utilities."""

    def test_seconds_to_timestamp(self):
        """Test converting seconds to MM:SS format."""
        assert seconds_to_timestamp(65) == "01:05"
        assert seconds_to_timestamp(3661) == "01:01:01"
        assert seconds_to_timestamp(0) == "00:00"

    def test_seconds_to_srt_timestamp(self):
        """Test SRT timestamp format."""
        assert seconds_to_srt_timestamp(0) == "00:00:00,000"
        assert seconds_to_srt_timestamp(65.5) == "00:01:05,500"
        assert seconds_to_srt_timestamp(3661.123) == "01:01:01,123"

    def test_seconds_to_vtt_timestamp(self):
        """Test VTT timestamp format."""
        assert seconds_to_vtt_timestamp(0) == "00:00:00.000"
        assert seconds_to_vtt_timestamp(65.5) == "00:01:05.500"

    def test_timestamp_to_seconds(self):
        """Test parsing timestamps to seconds."""
        assert timestamp_to_seconds("01:05") == 65
        assert timestamp_to_seconds("01:01:01") == 3661
        assert timestamp_to_seconds("00:01:05,500") == 65.5
        assert timestamp_to_seconds("00:01:05.500") == 65.5

    def test_format_duration(self):
        """Test human-readable duration formatting."""
        assert format_duration(65) == "1m 5s"
        assert format_duration(3661) == "1h 1m 1s"
        assert format_duration(0) == "0s"
        assert format_duration(60) == "1m"
