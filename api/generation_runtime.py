from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from typing import Any, Callable

from fastapi import BackgroundTasks, HTTPException, status

from .stage2_automation import Stage2Automator
from .state_machine import job_status_for_plan_status
from .store import AppStore
from .generation.time_utils import utc_now_iso
from .generation.types import Planner
from .generation.timeouts import (
    _stage1_planner_timeout_seconds as _stage1_planner_timeout_seconds,
    _stage2_finalize_timeout_seconds as _stage2_finalize_timeout_seconds,
)
from .generation.stage2_runner import (
    _OPENAI_QUOTA_ADMIN_ERROR as _OPENAI_QUOTA_ADMIN_ERROR,
    _OPENAI_QUOTA_ATHLETE_ERROR as _OPENAI_QUOTA_ATHLETE_ERROR,
    is_openai_quota_error as is_openai_quota_error,
)
from .generation.triage import (
    _compact_generation_job_final_result as _compact_generation_job_final_result,
    should_skip_stage2 as should_skip_stage2,
)
from .generation.milestones import (
    _MAX_PERSISTED_MILESTONES as _MAX_PERSISTED_MILESTONES,
    build_progress_recorder as build_progress_recorder,
)
from .generation.heartbeat import (
    is_stale_job as is_stale_job,
    recover_stale_running_job,
)
from .generation.stage1_runner import (
    _invoke_planner as _invoke_planner,
    _stage1_mp_start_method as _stage1_mp_start_method,
    default_planner as default_planner,
    run_stage1_planner as run_stage1_planner,
)
from .generation.orchestrator import run_generation_job

logger = logging.getLogger(__name__)


_DETACHED_GENERATION_TASKS: set[asyncio.Task[None]] = set()
_TERMINAL_GENERATION_JOB_STATUSES = {"completed", "review_required", "failed"}


def generation_status_from_plan_status(plan_status: str) -> str:
    return job_status_for_plan_status(plan_status)


def _use_fastapi_background_tasks() -> bool:
    scheduler = os.getenv("APP_GENERATION_SCHEDULER", "detached").strip().lower()
    return scheduler in {"fastapi", "background_tasks", "backgroundtasks"}


def is_in_process_generation_enabled() -> bool:
    return os.getenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", "0").strip() == "1"


def generation_max_concurrent_jobs() -> int:
    raw_value = os.getenv("APP_GENERATION_MAX_CONCURRENT_JOBS", "1").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "[jobs] generation:invalid_max_concurrent_jobs value=%r; falling back to 1",
            raw_value,
        )
        return 1
    return max(1, parsed)


def _cleanup_detached_generation_task(task: asyncio.Task[None]) -> None:
    _DETACHED_GENERATION_TASKS.discard(task)
    if task.cancelled():
        return
    with suppress(Exception):
        task.result()


def _schedule_detached_generation_task(
    *,
    job_id: str,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator,
    active_tasks: set[str],
) -> None:
    task = asyncio.create_task(
        run_generation_job(
            job_id=job_id,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
        )
    )
    _DETACHED_GENERATION_TASKS.add(task)
    task.add_done_callback(_cleanup_detached_generation_task)


async def schedule_generation_job_if_needed(
    *,
    job: dict[str, Any],
    background_tasks: BackgroundTasks,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator,
    active_tasks: set[str],
    enable_in_process_generation: bool,
    stale_job_checker: Callable[..., bool],
    stale_after_seconds: int,
) -> dict[str, Any]:
    current_status = str(job.get("status") or "queued")
    if current_status not in {"queued", "running"}:
        return job

    if current_status == "running":
        if stale_job_checker(job, stale_after_seconds=stale_after_seconds):
            job = await asyncio.to_thread(
                recover_stale_running_job,
                job=job,
                store=store,
                stale_after_seconds=stale_after_seconds,
            )
            current_status = str(job.get("status") or "")
            if current_status != "queued":
                return job
        else:
            return job

    if not enable_in_process_generation:
        logger.info(
            "[api] generation:job_created_worker_will_process job_id=%s",
            str(job.get("id") or ""),
        )
        return job

    job_id = str(job["id"])
    if job_id in active_tasks:
        return job

    max_concurrent_jobs = generation_max_concurrent_jobs()
    try:
        active_running_jobs = await asyncio.to_thread(
            store.count_active_generation_jobs,
            stale_after_seconds=stale_after_seconds,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            logger.warning(
                "[jobs] generation:schedule_capacity_count_deferred job_id=%s detail=%s",
                job_id,
                exc.detail,
            )
            return job
        raise

    if active_running_jobs >= max_concurrent_jobs:
        logger.info(
            "[jobs] generation:schedule_capacity_reached job_id=%s active_running_jobs=%s max_concurrent_jobs=%s",
            job_id,
            active_running_jobs,
            max_concurrent_jobs,
        )
        return job

    active_tasks.add(job_id)
    try:
        if _use_fastapi_background_tasks():
            background_tasks.add_task(
                run_generation_job,
                job_id=job_id,
                store=store,
                planner_fn=planner_fn,
                stage2=stage2,
                active_tasks=active_tasks,
            )
        else:
            _schedule_detached_generation_task(
                job_id=job_id,
                store=store,
                planner_fn=planner_fn,
                stage2=stage2,
                active_tasks=active_tasks,
            )
    except Exception:
        active_tasks.discard(job_id)
        logger.exception("[jobs] generation:schedule_failed job_id=%s", job_id)
        return await asyncio.to_thread(
            store.update_generation_job,
            job_id,
            status="failed",
            error="Generation worker failed to schedule.",
            completed_at=utc_now_iso(),
            heartbeat_at=utc_now_iso(),
        )

    return job
