from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import BackgroundTasks, HTTPException, status

from fightcamp.main import generate_plan_sync

from .models import PlanRequest, ProfileUpdateRequest
from .stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError, Stage2Automator
from .store import AppStore

Planner = Callable[[dict[str, Any]], dict[str, Any]]
logger = logging.getLogger(__name__)
_TRIAGE_RESUME_OVERRIDE_KEY = "_triage_resume_override"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_planner(payload: dict[str, Any]) -> dict[str, Any]:
    return generate_plan_sync(payload)


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def is_stale_job(job: dict[str, Any], *, stale_after_seconds: int = 90) -> bool:
    if str(job.get("status") or "") != "running":
        return False
    last_progress_at = parse_datetime(job.get("heartbeat_at")) or parse_datetime(job.get("started_at"))
    if last_progress_at is None:
        return False
    return (datetime.now(timezone.utc) - last_progress_at).total_seconds() >= stale_after_seconds


def parse_plan_request(value: Any) -> PlanRequest:
    if isinstance(value, PlanRequest):
        return value
    if isinstance(value, dict):
        return PlanRequest.model_validate(value)
    if isinstance(value, str):
        return PlanRequest.model_validate(json.loads(value))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="generation job payload is invalid",
    )


async def run_stage1_planner(planner_fn: Planner, payload: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(planner_fn, payload)


def _is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "y", "on"}
    return False


def should_skip_stage2(stage1_result: dict[str, Any]) -> bool:
    why_log = stage1_result.get("why_log")
    if isinstance(why_log, dict):
        resume_override = why_log.get("injury_triage_resume_override")
        if isinstance(resume_override, dict) and _is_truthy_flag(resume_override.get("bypassed_blocking")):
            return False

    status_value = str(stage1_result.get("status") or "").strip().lower()
    if status_value == "triage_blocked":
        return True

    injury_triage = stage1_result.get("injury_triage")
    if isinstance(injury_triage, dict):
        if _is_truthy_flag(injury_triage.get("should_block_stage2")):
            return True
        triage_mode = str(injury_triage.get("mode") or "").strip().lower()
        if triage_mode in {"medical_hold", "restricted_rehab_only", "needs_review"}:
            return True

    if isinstance(why_log, dict):
        why_log_triage = why_log.get("injury_triage")
        if isinstance(why_log_triage, dict):
            if _is_truthy_flag(why_log_triage.get("should_block_stage2")):
                return True
            triage_mode = str(why_log_triage.get("mode") or "").strip().lower()
            if triage_mode in {"medical_hold", "restricted_rehab_only", "needs_review"}:
                return True

    return False


async def heartbeat_generation_job(job_id: str, store: AppStore, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15)
            return
        except asyncio.TimeoutError:
            try:
                await asyncio.to_thread(
                    store.update_generation_job,
                    job_id,
                    heartbeat_at=utc_now_iso(),
                )
            except Exception:
                logger.exception("[jobs] generation:heartbeat_failed job_id=%s", job_id)


async def run_generation_job(
    *,
    job_id: str,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator,
    active_tasks: set[str],
) -> None:
    t_start = time.perf_counter()
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_generation_job(job_id, store, stop_event))
    athlete_id = "unknown"
    try:
        job = await asyncio.to_thread(store.get_generation_job, job_id)
        if not job:
            logger.warning("[jobs] generation:job_missing job_id=%s", job_id)
            return

        athlete_id = str(job["athlete_id"])
        raw_request_payload = job.get("request_payload") or {}
        request_body = parse_plan_request(raw_request_payload)
        logger.info("[jobs] generation:start athlete_id=%s job_id=%s", athlete_id, job_id)

        try:
            await asyncio.to_thread(
                store.update_profile,
                athlete_id,
                ProfileUpdateRequest(
                    full_name=request_body.athlete.full_name,
                    technical_style=request_body.athlete.technical_style,
                    tactical_style=request_body.athlete.tactical_style,
                    stance=request_body.athlete.stance,
                    professional_status=request_body.athlete.professional_status,
                    record=request_body.athlete.record,
                    athlete_timezone=request_body.athlete.athlete_timezone,
                    athlete_locale=request_body.athlete.athlete_locale,
                    onboarding_draft=request_body.model_dump(mode="json"),
                ),
            )
        except Exception:
            logger.exception("[jobs] generation:update_profile_failed athlete_id=%s job_id=%s", athlete_id, job_id)

        intake_id = str(job.get("intake_id") or "")
        if not intake_id:
            intake = await asyncio.to_thread(store.create_intake, athlete_id, request_body)
            intake_id = str(intake["id"])
            job = await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                intake_id=intake_id,
                heartbeat_at=utc_now_iso(),
            )

        stage1_result = job.get("stage1_result")
        if not isinstance(stage1_result, dict):
            planner_payload = request_body.to_payload()
            if isinstance(raw_request_payload, dict):
                triage_override = raw_request_payload.get(_TRIAGE_RESUME_OVERRIDE_KEY)
                if isinstance(triage_override, dict):
                    planner_payload[_TRIAGE_RESUME_OVERRIDE_KEY] = triage_override
            stage1_result = await run_stage1_planner(planner_fn, planner_payload)
            if stage1_result.get("status") == "invalid_input":
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": stage1_result.get("error", "invalid planning input"),
                        "missing_fields": stage1_result.get("missing_fields", []),
                    },
                )
            job = await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                stage1_result=stage1_result,
                heartbeat_at=utc_now_iso(),
            )

        final_result = job.get("final_result")
        if not isinstance(final_result, dict):
            if should_skip_stage2(stage1_result):
                final_result = {**stage1_result, "full_name": request_body.athlete.full_name}
            else:
                finalized_result = await stage2.finalize(stage1_result=stage1_result)
                final_result = {**finalized_result, "full_name": request_body.athlete.full_name}
            job = await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                final_result=final_result,
                heartbeat_at=utc_now_iso(),
            )

        plan_id = str(job.get("plan_id") or "") or None
        plan_row: dict[str, Any] | None = None
        if plan_id:
            plan_row = await asyncio.to_thread(store.get_plan, plan_id)
        if not plan_row and intake_id:
            latest_plan = await asyncio.to_thread(store.get_latest_plan, athlete_id)
            if latest_plan and str(latest_plan.get("intake_id") or "") == intake_id:
                plan_row = latest_plan
                plan_id = str(latest_plan.get("id") or "")
        if not plan_row:
            plan_row = await asyncio.to_thread(
                store.create_plan,
                athlete_id=athlete_id,
                intake_id=intake_id,
                request=request_body,
                result=final_result,
            )
            plan_id = str(plan_row.get("id") or "") or None

        try:
            await asyncio.to_thread(store.clear_onboarding_draft, athlete_id)
        except Exception:
            logger.exception("[jobs] generation:clear_onboarding_draft_failed athlete_id=%s job_id=%s", athlete_id, job_id)

        plan_status = str(plan_row.get("status") or "failed")
        final_status = "completed" if plan_status in {"ready", "triage_blocked"} else plan_status
        await asyncio.to_thread(
            store.update_generation_job,
            job_id,
            status=final_status,
            error=None,
            plan_id=plan_id,
            completed_at=utc_now_iso(),
            heartbeat_at=utc_now_iso(),
        )
        logger.info(
            "[jobs] generation:complete athlete_id=%s job_id=%s plan_id=%s status=%s duration_ms=%s",
            athlete_id,
            job_id,
            plan_id,
            final_status,
            round((time.perf_counter() - t_start) * 1000, 2),
        )
    except Stage2AutomationUnavailableError as exc:
        logger.warning("[jobs] generation:stage2_unavailable athlete_id=%s job_id=%s detail=%s", athlete_id, job_id, exc)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=str(exc),
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except Stage2AutomationError as exc:
        logger.exception("[jobs] generation:stage2_failed athlete_id=%s job_id=%s", athlete_id, job_id)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=str(exc),
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
        logger.warning("[jobs] generation:http_error athlete_id=%s job_id=%s detail=%s", athlete_id, job_id, detail)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=detail,
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except Exception:
        logger.exception("[jobs] generation:unhandled_exception athlete_id=%s job_id=%s", athlete_id, job_id)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error="Plan generation failed unexpectedly. Check server logs with the request ID.",
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        active_tasks.discard(job_id)


async def schedule_generation_job_if_needed(
    *,
    job: dict[str, Any],
    background_tasks: BackgroundTasks,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator,
    active_tasks: set[str],
    enable_in_process_generation: bool,
    is_stale_job: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    if not enable_in_process_generation:
        return job

    job_id = str(job["id"])
    if job_id in active_tasks:
        return job

    current_status = str(job.get("status") or "queued")
    if current_status not in {"queued", "running"}:
        return job
    if current_status == "running" and not is_stale_job(job):
        return job

    try:
        claimed = await asyncio.to_thread(store.claim_generation_job, job_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            logger.warning(
                "[jobs] generation:schedule_claim_deferred job_id=%s detail=%s",
                job_id,
                exc.detail,
            )
            return job
        raise
    if not claimed:
        try:
            refreshed = await asyncio.to_thread(store.get_generation_job, job_id)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                logger.warning(
                    "[jobs] generation:schedule_refresh_deferred job_id=%s detail=%s",
                    job_id,
                    exc.detail,
                )
                return job
            raise
        return refreshed or job

    active_tasks.add(job_id)
    background_tasks.add_task(
        run_generation_job,
        job_id=job_id,
        store=store,
        planner_fn=planner_fn,
        stage2=stage2,
        active_tasks=active_tasks,
    )
    return claimed
