from __future__ import annotations

import os

DEFAULT_GENERATION_JOB_STALE_AFTER_SECONDS = 300


def generation_job_stale_after_seconds(*, minimum: int = 60) -> int:
    raw_value = os.getenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS")
    if not raw_value:
        raw_value = os.getenv(
            "UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS",
            str(DEFAULT_GENERATION_JOB_STALE_AFTER_SECONDS),
        )
    try:
        parsed = int(str(raw_value).strip())
    except ValueError:
        return max(1, minimum, DEFAULT_GENERATION_JOB_STALE_AFTER_SECONDS)
    return max(1, minimum, parsed)
