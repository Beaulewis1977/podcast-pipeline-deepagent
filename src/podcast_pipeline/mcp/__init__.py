"""Developer-only MCP package for the podcast pipeline.

This package exposes the Phase 9 FFmpeg toolkit as a FastMCP server
for local developer automation and debugging.

IMPORTANT: This package is dev-only. Production pipeline stages must NOT
import from this module. FastMCP is an optional dev dependency only.

Usage:
    uv run --group dev python -m podcast_pipeline.mcp.ffmpeg_server
"""

__all__: list[str] = []
