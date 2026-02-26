"""PyInstaller-compatible entry point for the FastAPI backend sidecar.

This module is the ``__main__`` target packaged by PyInstaller into the
``binaries/podcast-backend`` sidecar that Tauri spawns at runtime.

Usage::

    # Direct (development / CI smoke-test)
    python -m podcast_pipeline.service.cli --host 127.0.0.1 --port 8787

    # Via installed entry-point (after `uv sync`)
    podcast-pipeline-service --port 8787

Tauri watches stdout for the ``BACKEND_READY port=<port>`` line to know
when the HTTP server is accepting connections.  This line is printed
*before* uvicorn's own startup banner so the Tauri frontend does not have
to scrape uvicorn logs.

Design notes
------------
* UTF-8 stdout reconfiguration happens at the top of ``main()`` so that the
  ``BACKEND_READY`` marker (and all subsequent structlog JSON output) is
  always safely encoded, even on Windows consoles that default to cp1252.
* The ``create_app`` import is deferred until *after* env-var setup so that
  any module-level code that reads ``PYTHONIOENCODING`` sees the correct
  value.
* ``uvicorn.run`` blocks until the server exits, which means the process
  lifetime matches the server lifetime — exactly what Tauri expects from a
  sidecar.
"""

import argparse
import os
import sys


def _ensure_utf8_stdout() -> None:
    """Reconfigure stdout to UTF-8 with replacement for non-encodable chars.

    On Windows the default console encoding is often cp1252 or similar.
    Setting the environment variables *before* any output ensures child
    processes inherit UTF-8 as well.
    """
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
        # reconfigure() is available in Python 3.7+ and is the recommended way
        # to change the encoding of an already-open text stream.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="podcast-pipeline-service",
        description="Start the Podcast Pipeline FastAPI backend service.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="TCP port to listen on (default: 8787)",
    )
    return parser


def main() -> None:
    """Entry point for the backend sidecar process.

    Execution order is important:
    1. Reconfigure stdout to UTF-8 so the BACKEND_READY marker is safe.
    2. Parse CLI arguments.
    3. Print ``BACKEND_READY port=<port>`` — Tauri watches for this line.
    4. Import and start uvicorn (deferred import keeps env setup first).
    """
    _ensure_utf8_stdout()

    parser = _build_arg_parser()
    args = parser.parse_args()

    # Signal to Tauri (and any other process watching stdout) that we are
    # about to start accepting HTTP connections.  This must be printed BEFORE
    # uvicorn.run() is called so the Tauri frontend does not time-out waiting.
    print(f"BACKEND_READY port={args.port}", flush=True)

    # Deferred import: env vars must be set before any podcast_pipeline module
    # is imported in case those modules read env vars at import time.
    import uvicorn

    from podcast_pipeline.service.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
