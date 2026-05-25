from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress

from fightcamp.logging_utils import configure_logging

from .generation_runtime import default_planner, is_stale_job, run_generation_job, utc_now_iso
from .generation_config import generation_job_stale_after_seconds
from .stage2_automation import build_default_stage2_automator
from .store import AppStore, SupabaseAppStore

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        return max(minimum, int(raw_value))
    except ValueError:
        logger.warning("[worker] invalid integer env %s=%r; using %s", name, raw_value, default)
        return default


def _worker_stale_after_seconds() -> int:
    return generation_job_stale_after_seconds(minimum=30)


def _worker_max_concurrent_jobs() -> int:
    return _int_env("UNLXCK_GENERATION_WORKER_MAX_CONCURRENT_JOBS", 1, minimum=1)

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
    remaining_capacity = max_concurrent_jobs - len(active_tasks)
    if remaining_capacity <= 0:
        return

    try:
        candidates = await asyncio.to_thread(
            store.list_claimable_generation_jobs,
            limit=remaining_capacity,
            stale_after_seconds=stale_after_seconds,
        )
    except Exception:
        logger.exception("[worker] failed to list claimable generation jobs")
        return

    for job in candidates:
        if len(active_tasks) >= max_concurrent_jobs:
            break

        job_id = str(job.get("id") or "")
        if not job_id or job_id in active_tasks:
            continue

        status = str(job.get("status") or "")
        if status == "running" and not is_stale_job(
            job,
            stale_after_seconds=stale_after_seconds,
        ):
            continue

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
    stale_after_seconds = _worker_stale_after_seconds()
    max_concurrent_jobs = _worker_max_concurrent_jobs()

    active_tasks: set[str] = set()
    detached_tasks: set[asyncio.Task[None]] = set()

    logger.info(
        "[worker] started mode=%s interval_seconds=%s stale_after_seconds=%s max_concurrent_jobs=%s",
        mode,
        interval_seconds,
        stale_after_seconds,
        max_concurrent_jobs,
    )
    if os.getenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", "0").strip() == "0":
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
