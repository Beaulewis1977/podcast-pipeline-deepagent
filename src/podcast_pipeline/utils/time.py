"""Time parsing and formatting utilities."""

import re


def seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS or HH:MM:SS format.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted timestamp string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    int((seconds % 1) * 1000)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def seconds_to_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds

    Returns:
        SRT-formatted timestamp
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def seconds_to_vtt_timestamp(seconds: float) -> str:
    """Convert seconds to VTT timestamp format (HH:MM:SS.mmm).

    Args:
        seconds: Time in seconds

    Returns:
        VTT-formatted timestamp
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def timestamp_to_seconds(timestamp: str) -> float:
    """Convert various timestamp formats to seconds.

    Supports:
        - MM:SS
        - HH:MM:SS
        - HH:MM:SS,mmm (SRT)
        - HH:MM:SS.mmm (VTT)

    Args:
        timestamp: Timestamp string

    Returns:
        Time in seconds
    """
    # Handle SRT format (comma for milliseconds)
    timestamp = timestamp.replace(",", ".")

    # Match various formats
    patterns = [
        r"^(\d+):(\d{2}):(\d{2})\.(\d{3})$",  # HH:MM:SS.mmm
        r"^(\d+):(\d{2}):(\d{2})$",  # HH:MM:SS
        r"^(\d+):(\d{2})\.(\d{3})$",  # MM:SS.mmm
        r"^(\d+):(\d{2})$",  # MM:SS
    ]

    for pattern in patterns:
        match = re.match(pattern, timestamp)
        if match:
            groups = match.groups()
            if len(groups) == 4:  # HH:MM:SS.mmm
                h, m, s, ms = map(int, groups)
                return h * 3600 + m * 60 + s + ms / 1000
            elif len(groups) == 3:
                if ":" in timestamp and "." in timestamp:  # MM:SS.mmm
                    m, s, ms = map(int, groups)
                    return m * 60 + s + ms / 1000
                else:  # HH:MM:SS
                    h, m, s = map(int, groups)
                    return h * 3600 + m * 60 + s
            elif len(groups) == 2:  # MM:SS
                m, s = map(int, groups)
                return m * 60 + s

    # Try to parse as plain float
    try:
        return float(timestamp)
    except ValueError as e:
        raise ValueError(f"Unable to parse timestamp: {timestamp}") from e


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable duration (e.g., "1h 23m 45s")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)
