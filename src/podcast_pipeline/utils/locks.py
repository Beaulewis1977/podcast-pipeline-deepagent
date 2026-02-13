"""Job-scoped file locking helpers."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class JobLockAcquisitionError(RuntimeError):
    """Raised when a job lock cannot be acquired."""


class JobFileLock:
    """Exclusive file lock for a single job directory."""

    def __init__(
        self,
        lock_path: Path,
        *,
        timeout_seconds: float = 0.0,
        retry_interval_seconds: float = 0.05,
    ) -> None:
        self.lock_path = lock_path
        self.timeout_seconds = timeout_seconds
        self.retry_interval_seconds = retry_interval_seconds
        self._fd: int | None = None

    def acquire(self) -> None:
        """Acquire lock by creating an exclusive lock file."""
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise JobLockAcquisitionError(
                        f"Job is already running: {self.lock_path.parent.name}"
                    ) from exc
                time.sleep(self.retry_interval_seconds)
                continue

            os.write(fd, str(os.getpid()).encode("utf-8"))
            self._fd = fd
            return

    def release(self) -> None:
        """Release lock by closing and removing the lock file."""
        if self._fd is None:
            return

        os.close(self._fd)
        self._fd = None

        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            return


@contextmanager
def acquire_job_lock(
    jobs_dir: Path,
    job_id: str,
    *,
    timeout_seconds: float = 0.0,
    retry_interval_seconds: float = 0.05,
) -> Iterator[None]:
    """Acquire and release a job-scoped lock as a context manager."""
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    lock = JobFileLock(
        job_dir / ".run.lock",
        timeout_seconds=timeout_seconds,
        retry_interval_seconds=retry_interval_seconds,
    )
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
