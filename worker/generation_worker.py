from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from contextlib import suppress
from typing import Any

from fightcamp.logging_utils import configure_logging

from api.generation_runtime import default_planner, run_generation_job
from api.stage2_automation import build_default_stage2_automator
from api.store import AppStore, SupabaseAppStore

logger = logging.getLogger(__name__)


def _worker_poll_seconds() -> float:
    return max(0.1, float(os.getenv("APP_GENERATION_WORKER_POLL_SECONDS", "5").strip()))


def _worker_idle_seconds() -> float:
    return max(0.1, float(os.getenv("APP_GENERATION_WORKER_IDLE_SECONDS", "5").strip()))


def _worker_max_jobs_per_loop() -> int:
    return max(1, int(os.getenv("APP_GENERATION_WORKER_MAX_JOBS_PER_LOOP", "1").strip()))


def _stale_after_seconds() -> int:
    return max(60, int(os.getenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "1400").strip()))


async def _process_job(*, store: AppStore, job: dict[str, Any]) -> None:
    job_id = str(job.get("id") or "")
    if not job_id:
        return
    logger.info("[worker] generation:job_start job_id=%s", job_id)
    await run_generation_job(
        job_id=job_id,
        store=store,
        planner_fn=default_planner,
        stage2=build_default_stage2_automator(),
        active_tasks=set(),
    )
    logger.info("[worker] generation:job_finish job_id=%s", job_id)


async def run_worker_loop(*, store: AppStore, once: bool = False) -> None:
    poll_seconds = _worker_poll_seconds()
    idle_seconds = _worker_idle_seconds()
    max_jobs = _worker_max_jobs_per_loop()
    stale_after = _stale_after_seconds()

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    logger.info(
        "[worker] generation:started once=%s poll_seconds=%s idle_seconds=%s max_jobs_per_loop=%s",
        once,
        poll_seconds,
        idle_seconds,
        max_jobs,
    )

    while not stop_event.is_set():
        claimed_any = False

        for _ in range(max_jobs):
            job = await asyncio.to_thread(
                store.claim_next_queued_generation_job,
                stale_after_seconds=stale_after,
            )
            if not job:
                break

            claimed_any = True
            job_id = str(job.get("id") or "")
            logger.info("[worker] generation:job_claimed job_id=%s", job_id)
            try:
                await _process_job(store=store, job=job)
            except Exception:
                logger.exception("[worker] generation:job_failed job_id=%s", job_id)

            if once:
                return

        if once:
            return

        await asyncio.sleep(poll_seconds if claimed_any else idle_seconds)

    logger.info("[worker] generation:stopped")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the durable generation worker.")
    parser.add_argument("--once", action="store_true", help="Claim at most one job then exit.")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = _parse_args()

    store = SupabaseAppStore.from_env()
    store.validate_runtime_schema()

    asyncio.run(run_worker_loop(store=store, once=args.once))


if __name__ == "__main__":
    main()
