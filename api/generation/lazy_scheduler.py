"""Create-only scheduling entry point that keeps the planner out of the web process.

The web service creates generation jobs and lets the worker run them. Importing
``api.generation.scheduler`` eagerly would pull the planner/orchestrator surface
— and through it ``fightcamp.main`` — into a process that only ever enqueues
work, so every heavy import in this module is function-local and reached only
when in-process generation is explicitly enabled.

Keep this module dependency-light: anything imported at module scope here is
paid for by the web process on startup.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def schedule_generation_job_if_needed(**kwargs: Any) -> dict[str, Any]:
    """Create-only in the default (worker) path; schedule in-process on demand.

    A job left ``running`` past its staleness window is first recovered back to
    ``queued`` so it can be picked up again. Only then, and only when in-process
    generation is enabled, is the real scheduler imported — building a Stage 2
    automator lazily if the caller did not supply one.
    """
    job = kwargs["job"]
    current_status = str(job.get("status") or "queued")
    if current_status == "running":
        stale_job_checker = kwargs.get("stale_job_checker")
        stale_after_seconds = int(kwargs.get("stale_after_seconds") or 90)
        if callable(stale_job_checker) and stale_job_checker(job, stale_after_seconds=stale_after_seconds):
            from .heartbeat import recover_stale_running_job

            job = await asyncio.to_thread(
                recover_stale_running_job,
                job=job,
                store=kwargs["store"],
                stale_after_seconds=stale_after_seconds,
            )
            kwargs["job"] = job
            current_status = str(job.get("status") or "")
            if current_status != "queued":
                return job
        else:
            return job

    if not bool(kwargs.get("enable_in_process_generation")):
        logger.info(
            "[api] generation:job_created_worker_will_process job_id=%s",
            str(job.get("id") or ""),
        )
        return job

    if kwargs.get("stage2") is None:
        from ..stage2_automation import build_default_stage2_automator

        kwargs["stage2"] = build_default_stage2_automator()

    from .scheduler import schedule_generation_job_if_needed as _schedule_in_process

    return await _schedule_in_process(**kwargs)
