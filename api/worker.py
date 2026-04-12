from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fightcamp.logging_utils import configure_logging

from .app import _default_planner, _is_stale_job
from .demo import DemoAuthService, get_demo_store
from .generation_runtime import run_generation_job
from .stage2_automation import build_default_stage2_automator
from .store import AppStore, SupabaseAppStore

logger = logging.getLogger(__name__)


async def _tick(*, store: AppStore, active_tasks: set[str]) -> None:
    try:
        candidates = await asyncio.to_thread(store.list_claimable_generation_jobs, limit=20)
    except Exception:
        logger.exception("[worker] failed to list claimable generation jobs")
        return

    for job in candidates:
        job_id = str(job.get("id") or "")
        if not job_id or job_id in active_tasks:
            continue
        status = str(job.get("status") or "")
        if status == "running" and not _is_stale_job(job):
            continue
        try:
            claimed = await asyncio.to_thread(store.claim_generation_job, job_id)
        except Exception:
            logger.exception("[worker] failed to claim job_id=%s", job_id)
            continue
        if not claimed:
            continue
        active_tasks.add(job_id)
        asyncio.create_task(
            run_generation_job(
                job_id=job_id,
                store=store,
                planner_fn=_default_planner,
                stage2=build_default_stage2_automator(),
                active_tasks=active_tasks,
            )
        )


async def run_worker() -> None:
    configure_logging()
    if os.getenv("UNLXCK_DEMO_MODE") == "1":
        store = get_demo_store()
        store.validate_runtime_schema()
        _ = DemoAuthService()
        mode = "demo"
    else:
        store = SupabaseAppStore.from_env()
        store.validate_runtime_schema()
        mode = "supabase"

    interval_seconds = max(1.0, float(os.getenv("UNLXCK_GENERATION_WORKER_INTERVAL_SECONDS", "3")))
    active_tasks: set[str] = set()
    logger.info("[worker] started mode=%s interval_seconds=%s", mode, interval_seconds)

    while True:
        await _tick(store=store, active_tasks=active_tasks)
        await asyncio.sleep(interval_seconds)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
