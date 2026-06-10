from __future__ import annotations

import os
import socket
import uuid

DEFAULT_GENERATION_JOB_STALE_AFTER_SECONDS = 300

_DEFAULT_GENERATION_WORKER_ID: str | None = None


def generation_worker_id() -> str:
    """Stable identity for this process when claiming generation jobs.

    Stored in ``generation_jobs.claimed_by`` on claim and compared against it
    by the terminal RPCs, so a stale worker cannot complete or fail a job that
    another worker has since reclaimed. ``UNLXCK_GENERATION_WORKER_ID`` can
    pin the identity per deployment instance; it must be unique per concurrent
    worker process. The default is unique per process.
    """
    configured = os.getenv("UNLXCK_GENERATION_WORKER_ID", "").strip()
    if configured:
        return configured
    global _DEFAULT_GENERATION_WORKER_ID
    if _DEFAULT_GENERATION_WORKER_ID is None:
        _DEFAULT_GENERATION_WORKER_ID = (
            f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        )
    return _DEFAULT_GENERATION_WORKER_ID


def generation_job_stale_after_seconds(*, minimum: int = 60) -> int:
    raw_value = os.getenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS")
    if not raw_value:
        raw_value = os.getenv(
            "UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS",
            str(DEFAULT_GENERATION_JOB_STALE_AFTER_SECONDS),
        )
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        return max(1, minimum, DEFAULT_GENERATION_JOB_STALE_AFTER_SECONDS)
    return max(1, minimum, parsed)
