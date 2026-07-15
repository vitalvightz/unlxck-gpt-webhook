from __future__ import annotations

import asyncio
import copy
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks, HTTPException, Request, status

from api.generation_job_helpers import (
    _find_blocking_generation_job_for_athlete,
    _generation_job_stale_after_seconds,
    _is_stale_job,
    _job_response,
    _normalized_client_request_id,
    daily_generation_cap_window,
)
from api.errors import generation_already_in_flight_error
from api.models import GenerationJobResponse, ProfileRecord
from api.plan_mappers import _ALLOWED_PLAN_SOURCES
from api.store import AppStore, is_effective_admin_profile, is_startup_stale_generation_job

if TYPE_CHECKING:
    from api.stage2_automation import Stage2Automator

Planner = Callable[[dict[str, Any]], dict[str, Any]]
ScheduleGenerationJob = Callable[..., Awaitable[dict[str, Any]]]


async def cancel_generation_job(
    *,
    job_id: str,
    profile: ProfileRecord,
    store: AppStore,
) -> GenerationJobResponse:
    """Manually terminate a queued/running generation job.

    Lets an athlete (their own job) or an admin kill a job that is stuck —
    without waiting for heartbeat-based staleness detection to catch up, which
    can lag well behind a genuine hang. The job is left in the database as a
    terminal ``failed`` row (not hard-deleted) so it stops blocking new
    generation attempts and clears the athlete's active-job slot, while still
    leaving an audit trail for debugging.
    """
    job = await asyncio.to_thread(store.get_generation_job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")

    is_admin = is_effective_admin_profile(profile, store)
    if not is_admin and str(job.get("athlete_id")) != profile.athlete_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")

    current_status = str(job.get("status") or "")
    if current_status not in {"queued", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only queued or running generation jobs can be cancelled",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    cancelled_by = "admin" if is_admin else "athlete"
    updated = await asyncio.to_thread(
        store.update_generation_job,
        job_id,
        status="failed",
        error=f"Cancelled by {cancelled_by}.",
        completed_at=now_iso,
        heartbeat_at=now_iso,
    )
    viewer_role = "admin" if is_admin else "athlete"
    return _job_response(updated, store=store, viewer_role=viewer_role)


async def retry_generation_job(
    *,
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    profile: ProfileRecord,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator | None,
    active_tasks: set[str],
    enable_in_process_generation: bool,
    schedule_generation_job_if_needed: ScheduleGenerationJob,
    plan_generate_daily_limit_per_user: Callable[[], int],
    is_exempt_from_daily_generation_cap: Callable[[str], bool],
) -> GenerationJobResponse:
    original = await asyncio.to_thread(store.get_generation_job, job_id)
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
    is_admin = is_effective_admin_profile(profile, store)
    viewer_role = "admin" if is_admin else "athlete"
    if not is_admin and str(original["athlete_id"]) != profile.athlete_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
    stale_after_seconds = _generation_job_stale_after_seconds()
    is_startup_stale = is_startup_stale_generation_job(
        original,
        stale_after_seconds=stale_after_seconds,
    )
    if str(original.get("status") or "") != "failed" and not is_startup_stale:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only failed generation jobs can be retried",
        )
    request_payload = original.get("request_payload")
    if not isinstance(request_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="original job request payload is missing",
        )

    target_athlete_id = str(original["athlete_id"])
    source = str(original.get("source") or "").strip() or "self_serve"
    existing_plan_id = str(original.get("plan_id") or "").strip()
    if existing_plan_id and source != "admin_triage_resume":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="generation job already produced a saved plan",
        )

    daily_limit = plan_generate_daily_limit_per_user()
    enforce_daily_limit = (
        daily_limit > 0
        and not is_admin
        and not is_exempt_from_daily_generation_cap(profile.email)
    )
    limit_reached_detail = ""
    day_start_iso = ""
    if enforce_daily_limit:
        athlete_payload = request_payload.get("athlete")
        athlete_timezone = (
            athlete_payload.get("athlete_timezone")
            if isinstance(athlete_payload, dict)
            else None
        )
        day_start_iso, limit_reached_detail = daily_generation_cap_window(athlete_timezone)

    # If the original job is a pre-start stale running job, reuse its client_request_id
    # so we reset the existing job instead of creating a duplicate. Otherwise prefer
    # the header-provided id or generate a retry id.
    retry_client_request_id = (
        str(original.get("client_request_id") or "")
        if is_startup_stale
        else _normalized_client_request_id(
            request.headers.get("X-Client-Request-Id"),
            f"retry_{job_id}",
        )
    )
    retry_intake_id = str(original.get("intake_id") or "").strip() or None
    retry_plan_id = existing_plan_id or None
    if source == "admin_triage_resume":
        is_job_based_triage_resume = str(original.get("client_request_id") or "").startswith(
            "triage_resume_job_"
        )
        if not retry_intake_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="admin triage resume retry is missing intake linkage",
            )
        if not is_job_based_triage_resume and not retry_plan_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="admin triage resume retry is missing plan linkage",
            )
    existing_retry_job = await asyncio.to_thread(
        store.get_generation_job_by_client_request_id,
        athlete_id=target_athlete_id,
        client_request_id=retry_client_request_id,
    )
    if existing_retry_job and not is_startup_stale:
        job = await schedule_generation_job_if_needed(
            job=existing_retry_job,
            background_tasks=background_tasks,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
            enable_in_process_generation=enable_in_process_generation,
            stale_job_checker=_is_stale_job,
            stale_after_seconds=stale_after_seconds,
        )
        return _job_response(job, store=store, viewer_role=viewer_role)
    blocking_job = await asyncio.to_thread(
        _find_blocking_generation_job_for_athlete,
        store=store,
        athlete_id=target_athlete_id,
        stale_after_seconds=stale_after_seconds,
    )
    if blocking_job and str(blocking_job.get("id")) != str(original.get("id")):
        raise generation_already_in_flight_error()

    if is_startup_stale:
        job = await asyncio.to_thread(
            store.create_or_get_generation_job,
            athlete_id=target_athlete_id,
            client_request_id=retry_client_request_id,
            source=source,
            request_payload=copy.deepcopy(request_payload),
            plan_id=retry_plan_id,
            intake_id=retry_intake_id,
            stale_after_seconds=stale_after_seconds,
        )
    elif enforce_daily_limit:
        job = await asyncio.to_thread(
            store.create_or_get_generation_job_with_daily_limit,
            athlete_id=target_athlete_id,
            client_request_id=retry_client_request_id,
            source=source,
            request_payload=copy.deepcopy(request_payload),
            daily_limit=daily_limit,
            day_start_iso=day_start_iso,
            limit_reached_detail=limit_reached_detail,
            counted_sources=_ALLOWED_PLAN_SOURCES,
            plan_id=retry_plan_id,
            intake_id=retry_intake_id,
            stale_after_seconds=stale_after_seconds,
        )
    else:
        job = await asyncio.to_thread(
            store.create_or_get_generation_job,
            athlete_id=target_athlete_id,
            client_request_id=retry_client_request_id,
            source=source,
            request_payload=copy.deepcopy(request_payload),
            plan_id=retry_plan_id,
            intake_id=retry_intake_id,
            stale_after_seconds=stale_after_seconds,
        )
    job = await schedule_generation_job_if_needed(
        job=job,
        background_tasks=background_tasks,
        store=store,
        planner_fn=planner_fn,
        stage2=stage2,
        active_tasks=active_tasks,
        enable_in_process_generation=enable_in_process_generation,
        stale_job_checker=_is_stale_job,
        stale_after_seconds=stale_after_seconds,
    )
    return _job_response(job, store=store, viewer_role=viewer_role)
