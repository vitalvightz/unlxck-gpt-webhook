from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress

from fightcamp.logging_utils import configure_logging

from .generation_runtime import default_planner, run_generation_job, utc_now_iso
from .stage2_automation import build_default_stage2_automator
from .store import AppStore, SupabaseAppStore

logger = logging.getLogger(__name__)

_STAGE1_PLANNER_TIMEOUT_DEFAULT_SECONDS = 600
_WORKER_STALE_BUFFER_SECONDS = 60


def _worker_stale_after_seconds_default() -> int:
    raw_timeout = os.getenv("STAGE1_PLANNER_TIMEOUT_SECONDS")
    if raw_timeout is None:
        raw_timeout = os.getenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", str(_STAGE1_PLANNER_TIMEOUT_DEFAULT_SECONDS))
    try:
        stage1_timeout_seconds = float(str(raw_timeout).strip())
    except ValueError:
        stage1_timeout_seconds = float(_STAGE1_PLANNER_TIMEOUT_DEFAULT_SECONDS)
    if stage1_timeout_seconds <= 0:
        stage1_timeout_seconds = float(_STAGE1_PLANNER_TIMEOUT_DEFAULT_SECONDS)
    return max(
        _STAGE1_PLANNER_TIMEOUT_DEFAULT_SECONDS + _WORKER_STALE_BUFFER_SECONDS,
        int(stage1_timeout_seconds) + _WORKER_STALE_BUFFER_SECONDS,
    )


async def _mark_job_failed_before_runtime(
    *,
    store: AppStore,
    job_id: str,
    error: str,
) -> None:
    with suppress(Exception):
        await asyncio.to_thread(
            store.update_generation_job,
            job_id,
            status="failed",
            error=error,
            completed_at=utc_now_iso(),
            heartbeat_at=utc_now_iso(),
        )


async def _run_claimed_job(
    *,
    job_id: str,
    store: AppStore,
    active_tasks: set[str],
) -> None:
    try:
        stage2 = build_default_stage2_automator()
        await run_generation_job(
            job_id=job_id,
            store=store,
            planner_fn=default_planner,
            stage2=stage2,
            active_tasks=active_tasks,
            claim_on_start=False,
        )
    except Exception as exc:
        logger.exception("[worker] job failed before generation runtime job_id=%s", job_id)
        await _mark_job_failed_before_runtime(
            store=store,
            job_id=job_id,
            error=f"Worker failed before generation runtime: {exc}",
        )
        active_tasks.discard(job_id)


def _cleanup_worker_task(
    task: asyncio.Task[None],
    *,
    detached_tasks: set[asyncio.Task[None]],
) -> None:
    detached_tasks.discard(task)

    if task.cancelled():
        return

    with suppress(Exception):
        task.result()


async def _tick(
    *,
    store: AppStore,
    active_tasks: set[str],
    detached_tasks: set[asyncio.Task[None]],
    stale_after_seconds: int,
    max_concurrent_jobs: int,
) -> None:
    while len(active_tasks) < max_concurrent_jobs:
        worker_id = f"pid-{os.getpid()}"
        logger.info("[worker] generation:claim_attempt worker_id=%s", worker_id)
        try:
            claimed = await asyncio.to_thread(
                store.claim_next_generation_job,
                worker_id=worker_id,
                stale_after_seconds=stale_after_seconds,
            )
        except Exception:
            logger.exception("[worker] failed to claim generation job atomically")
            return

        if not claimed:
            logger.info("[worker] generation:no_claimable_jobs")
            return

        job_id = str(claimed.get("id") or "")
        if not job_id or job_id in active_tasks:
            continue

        logger.info(
            "[worker] generation:claim_success job_id=%s attempt=%s",
            job_id,
            int(claimed.get("attempt_count") or 0),
        )

        active_tasks.add(job_id)

        try:
            task = asyncio.create_task(
                _run_claimed_job(
                    job_id=job_id,
                    store=store,
                    active_tasks=active_tasks,
                )
            )
        except Exception:
            logger.exception("[worker] failed to create task job_id=%s", job_id)
            active_tasks.discard(job_id)
            await _mark_job_failed_before_runtime(
                store=store,
                job_id=job_id,
                error="Generation worker failed to schedule.",
            )
            continue

        detached_tasks.add(task)
        task.add_done_callback(
            lambda completed_task: _cleanup_worker_task(
                completed_task,
                detached_tasks=detached_tasks,
            )
        )


async def run_worker() -> None:
    configure_logging()

    store = SupabaseAppStore.from_env()
    store.validate_runtime_schema()
    mode = "supabase"

    interval_seconds = max(
        1.0,
        float(os.getenv("UNLXCK_GENERATION_WORKER_INTERVAL_SECONDS", "3")),
    )
    stale_after_seconds = max(
        30,
        int(os.getenv("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", str(_worker_stale_after_seconds_default()))),
    )
    max_concurrent_jobs = max(
        1,
        int(os.getenv("UNLXCK_GENERATION_WORKER_MAX_CONCURRENT_JOBS", "3")),
    )

    active_tasks: set[str] = set()
    detached_tasks: set[asyncio.Task[None]] = set()

    logger.info(
        "[worker] started mode=%s interval_seconds=%s stale_after_seconds=%s max_concurrent_jobs=%s",
        mode,
        interval_seconds,
        stale_after_seconds,
        max_concurrent_jobs,
    )
    if os.getenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", "1").strip() == "0":
        logger.info("[worker] generation:worker_only_mode enabled")

    while True:
        await _tick(
            store=store,
            active_tasks=active_tasks,
            detached_tasks=detached_tasks,
            stale_after_seconds=stale_after_seconds,
            max_concurrent_jobs=max_concurrent_jobs,
        )
        await asyncio.sleep(interval_seconds)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
