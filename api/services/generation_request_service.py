from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import BackgroundTasks, HTTPException, Request, status

from api.generation.payloads import _stable_payload_hash
from api.generation_job_helpers import (
    _PROTECTED_TRIAGE_STATUSES,
    _build_protected_triage_response,
    _find_blocking_generation_job_for_athlete,
    _find_existing_terminal_job_for_same_payload,
    _generation_job_stale_after_seconds,
    _is_stale_job,
    _job_response,
    _normalized_client_request_id,
    daily_generation_cap_window,
)
from api.errors import client_request_id_payload_mismatch_error, generation_already_in_flight_error
from api.models import GenerationJobResponse, PlanRequest, ProfileRecord
from api.performance_focus import validate_performance_focus_selections
from api.plan_mappers import _ALLOWED_PLAN_SOURCES
from api.stage2_automation import Stage2Automator
from api.store import AppStore, is_effective_admin_profile, is_startup_stale_generation_job

Planner = Callable[[dict[str, Any]], dict[str, Any]]
ScheduleGenerationJob = Callable[..., Awaitable[dict[str, Any]]]


async def generate_plan_for_current_user(
    *,
    request: Request,
    request_body: PlanRequest,
    background_tasks: BackgroundTasks,
    profile: ProfileRecord,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator,
    active_tasks: set[str],
    enable_in_process_generation: bool,
    schedule_generation_job_if_needed: ScheduleGenerationJob,
    plan_generate_rate_limit_requests: Callable[[], int],
    plan_generate_rate_limit_window_seconds: Callable[[], float],
    plan_generate_daily_limit_per_user: Callable[[], int],
    is_exempt_from_daily_generation_cap: Callable[[str], bool],
) -> GenerationJobResponse:
    focus_validation = validate_performance_focus_selections(
        request_body.fight_date,
        key_goals=request_body.key_goals,
        weak_areas=request_body.weak_areas,
        time_zone=request_body.athlete.athlete_timezone,
    )
    if focus_validation.is_over_cap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=focus_validation.error_message or "Too many focus selections for this camp.",
        )

    client_request_id = _normalized_client_request_id(
        request.headers.get("X-Client-Request-Id"),
        "cli",
    )
    request_payload = request_body.model_dump(mode="json")
    payload_hash = _stable_payload_hash(request_payload)
    is_admin = is_effective_admin_profile(profile, store)
    viewer_role = "admin" if is_admin else "athlete"
    existing_job = await asyncio.to_thread(
        store.get_generation_job_by_client_request_id,
        athlete_id=profile.athlete_id,
        client_request_id=client_request_id,
    )
    stale_after_seconds = _generation_job_stale_after_seconds()
    if existing_job:
        existing_payload_hash = existing_job.get("payload_hash")
        if existing_payload_hash and existing_payload_hash != payload_hash:
            raise client_request_id_payload_mismatch_error()
        if is_startup_stale_generation_job(existing_job, stale_after_seconds=stale_after_seconds):
            existing_job = await asyncio.to_thread(
                store.create_or_get_generation_job,
                athlete_id=profile.athlete_id,
                client_request_id=client_request_id,
                source=str(existing_job.get("source") or "self_serve"),
                request_payload=request_payload,
                stale_after_seconds=stale_after_seconds,
            )
        job = await schedule_generation_job_if_needed(
            job=existing_job,
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

    recovered_existing = await asyncio.to_thread(
        _find_existing_terminal_job_for_same_payload,
        store=store,
        athlete_id=profile.athlete_id,
        request_payload=request_payload,
    )
    if recovered_existing:
        return _job_response(recovered_existing, store=store, viewer_role=viewer_role)

    latest_plan = await asyncio.to_thread(store.get_latest_plan, profile.athlete_id)
    if isinstance(latest_plan, dict):
        latest_status = str(latest_plan.get("status") or "").strip().lower()
        latest_stage2_status = str(latest_plan.get("stage2_status") or "").strip().lower()
        latest_intake_id = str(latest_plan.get("intake_id") or "").strip()
        request_intake_id = str(request_body.intake_id or "").strip()
        if (
            is_admin
            and latest_intake_id
            and request_intake_id
            and latest_intake_id == request_intake_id
            and (latest_status in _PROTECTED_TRIAGE_STATUSES or latest_stage2_status in _PROTECTED_TRIAGE_STATUSES)
        ):
            return _build_protected_triage_response(latest_plan, profile.athlete_id)

    blocking_job = await asyncio.to_thread(
        _find_blocking_generation_job_for_athlete,
        store=store,
        athlete_id=profile.athlete_id,
        stale_after_seconds=stale_after_seconds,
    )
    if blocking_job:
        raise generation_already_in_flight_error()

    short_window_limit = plan_generate_rate_limit_requests()
    if short_window_limit > 0:
        allowed, retry_after = await asyncio.to_thread(
            store.check_plan_generation_short_window_limit,
            athlete_id=profile.athlete_id,
            max_requests=short_window_limit,
            window_seconds=plan_generate_rate_limit_window_seconds(),
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "Too many plan generation requests. Try again shortly.",
                    "retry_after_seconds": retry_after,
                },
            )

    daily_limit = plan_generate_daily_limit_per_user()
    enforce_daily_limit = (
        daily_limit > 0
        and not is_admin
        and not is_exempt_from_daily_generation_cap(profile.email)
    )

    plan_source_header = (request.headers.get("X-Plan-Source") or "").strip()
    resolved_source = plan_source_header if plan_source_header in _ALLOWED_PLAN_SOURCES else "self_serve"
    if enforce_daily_limit:
        day_start_iso, limit_reached_detail = daily_generation_cap_window(
            request_body.athlete.athlete_timezone
        )
        job = await asyncio.to_thread(
            store.create_or_get_generation_job_with_daily_limit,
            athlete_id=profile.athlete_id,
            client_request_id=client_request_id,
            source=resolved_source,
            request_payload=request_payload,
            daily_limit=daily_limit,
            day_start_iso=day_start_iso,
            limit_reached_detail=limit_reached_detail,
            counted_sources=_ALLOWED_PLAN_SOURCES,
            stale_after_seconds=stale_after_seconds,
        )
    else:
        job = await asyncio.to_thread(
            store.create_or_get_generation_job,
            athlete_id=profile.athlete_id,
            client_request_id=client_request_id,
            source=resolved_source,
            request_payload=request_payload,
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
