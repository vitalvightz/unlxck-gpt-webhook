from __future__ import annotations

import asyncio
import json
import logging
import traceback
import os
import time
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import BackgroundTasks, HTTPException, status

from fightcamp.main import generate_plan_sync

from .models import PlanRequest, ProfileUpdateRequest
from .stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError, Stage2Automator
from .store import AppStore

Planner = Callable[..., dict[str, Any]]
ProgressCallback = Callable[[str, str, str, dict[str, Any]], None]
logger = logging.getLogger(__name__)
_TRIAGE_RESUME_OVERRIDE_KEY = "_triage_resume_override"
_DETACHED_GENERATION_TASKS: set[asyncio.Task[None]] = set()
_MAX_PERSISTED_MILESTONES = 40


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_planner(
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    return generate_plan_sync(payload, progress_callback=progress_callback)


def _invoke_planner(
    planner_fn: Planner,
    payload: dict[str, Any],
    progress_callback: ProgressCallback | None,
) -> dict[str, Any]:
    """Call a planner that may or may not accept a ``progress_callback`` kwarg."""
    if progress_callback is None:
        return planner_fn(payload)
    try:
        return planner_fn(payload, progress_callback=progress_callback)
    except TypeError:
        # Planners written before milestones existed (or test stubs) won't
        # accept the kwarg. Fall back transparently.
        return planner_fn(payload)


def build_progress_recorder(
    *,
    job_id: str,
    store: AppStore,
) -> tuple[list[dict[str, Any]], ProgressCallback]:
    """Return a milestone list + callback that persists each emit to the job row.

    Emits are low-volume (~10 over several minutes), so writing on every event
    is fine. Persistence failures are logged and ignored — they must never
    surface into the planner pipeline.
    """
    milestones: list[dict[str, Any]] = []

    def _callback(code: str, label: str, detail: str, meta: dict[str, Any]) -> None:
        entry = {
            "code": code,
            "label": label,
            "detail": detail or "",
            "meta": dict(meta or {}),
            "at": utc_now_iso(),
        }
        milestones.append(entry)
        # Cap list size so a runaway emitter cannot bloat the row.
        if len(milestones) > _MAX_PERSISTED_MILESTONES:
            del milestones[:-_MAX_PERSISTED_MILESTONES]
        snapshot = list(milestones)
        try:
            store.update_generation_job(
                job_id,
                progress_milestones=snapshot,
                heartbeat_at=utc_now_iso(),
            )
        except Exception:
            logger.exception(
                "[jobs] generation:milestone_persist_failed job_id=%s code=%s",
                job_id,
                code,
            )

    return milestones, _callback


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


def _stage2_finalize_timeout_seconds() -> float | None:
    raw_value = os.getenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "1000").strip()
    if raw_value in {"", "0", "none", "None", "NONE"}:
        return None
    try:
        return max(1.0, float(raw_value))
    except ValueError:
        logger.warning(
            "[jobs] generation:invalid_stage2_timeout value=%r; falling back to 300s",
            raw_value,
        )
        return 300.0


def _use_fastapi_background_tasks() -> bool:
    scheduler = os.getenv("APP_GENERATION_SCHEDULER", "detached").strip().lower()
    return scheduler in {"fastapi", "background_tasks", "backgroundtasks"}


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


async def run_stage1_planner(
    planner_fn: Planner,
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(_invoke_planner, planner_fn, payload, progress_callback)


async def finalize_stage2_with_timeout(
    *,
    stage2: Stage2Automator,
    stage1_result: dict[str, Any],
) -> dict[str, Any]:
    finalize = stage2.finalize(stage1_result=stage1_result)
    timeout_seconds = _stage2_finalize_timeout_seconds()
    if timeout_seconds is None:
        return await finalize
    return await asyncio.wait_for(finalize, timeout=timeout_seconds)


def _is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "y", "on"}
    return False


def should_skip_stage2(stage1_result: dict[str, Any], *, allow_triage_resume_override: bool = False) -> bool:
    status_value = str(stage1_result.get("status") or "").strip().lower()
    if status_value == "triage_blocked":
        return not allow_triage_resume_override

    injury_triage = stage1_result.get("injury_triage")
    if isinstance(injury_triage, dict):
        if _is_truthy_flag(injury_triage.get("should_block_stage2")):
            return False if allow_triage_resume_override else True
        triage_mode = str(injury_triage.get("mode") or "").strip().lower()
        if triage_mode in {"medical_hold", "restricted_rehab_only", "needs_review"}:
            return False if allow_triage_resume_override else True

    why_log = stage1_result.get("why_log")
    if isinstance(why_log, dict):
        why_log_triage = why_log.get("injury_triage")
        if isinstance(why_log_triage, dict):
            if _is_truthy_flag(why_log_triage.get("should_block_stage2")):
                return False if allow_triage_resume_override else True
            triage_mode = str(why_log_triage.get("mode") or "").strip().lower()
            if triage_mode in {"medical_hold", "restricted_rehab_only", "needs_review"}:
                return False if allow_triage_resume_override else True

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
    _, progress_callback = build_progress_recorder(job_id=job_id, store=store)

    def _emit_milestone(code: str, label: str, detail: str = "", **meta: Any) -> None:
        try:
            progress_callback(code, label, detail, meta)
        except Exception:
            logger.exception("[jobs] generation:milestone_emit_failed job_id=%s code=%s", job_id, code)

    try:
        job = await asyncio.to_thread(store.get_generation_job, job_id)
        if not job:
            logger.warning("[jobs] generation:job_missing job_id=%s", job_id)
            return

        athlete_id = str(job["athlete_id"])
        raw_request_payload = job.get("request_payload") or {}
        triage_resume_override_approved = False
        if isinstance(raw_request_payload, dict):
            triage_override = raw_request_payload.get(_TRIAGE_RESUME_OVERRIDE_KEY)
            triage_resume_override_approved = isinstance(triage_override, dict) and triage_override.get("approved") is True
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
            stage1_result = await run_stage1_planner(
                planner_fn,
                planner_payload,
                progress_callback=progress_callback,
            )
            if stage1_result.get("status") == "invalid_input":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
            if should_skip_stage2(stage1_result, allow_triage_resume_override=triage_resume_override_approved):
                _emit_milestone(
                    "stage2_skipped",
                    "Stage 2 skipped",
                    "Triage routing held the plan at Stage 1 — no AI finalization needed.",
                )
                final_result = {**stage1_result, "full_name": request_body.athlete.full_name}
            else:
                _emit_milestone(
                    "stage2_drafting",
                    "Stage 2 finalizer drafting",
                    "Sending the planning brief to the AI finalizer.",
                )
                finalized_result = await finalize_stage2_with_timeout(
                    stage2=stage2,
                    stage1_result=stage1_result,
                )
                final_result = {**finalized_result, "full_name": request_body.athlete.full_name}
                _emit_milestone(
                    "stage2_validated",
                    "Stage 2 finalizer complete",
                    "Validator passed. Final coach-voice plan ready for handoff.",
                )
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
        if plan_row and plan_id:
            plan_row = await asyncio.to_thread(
                store.update_plan_stage2,
                plan_id,
                final_result,
            )
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
        if final_status == "completed":
            _emit_milestone(
                "plan_saved",
                "Plan saved to your workspace",
                "Opening the saved plan for review.",
            )
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
    except asyncio.TimeoutError:
        logger.exception("[jobs] generation:stage2_timeout athlete_id=%s job_id=%s", athlete_id, job_id)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error="Stage 2 finalization timed out. Retry the job or run manual review.",
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
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
    except Exception as exc:
        tb = traceback.extract_tb(exc.__traceback__)
        frame = tb[-1] if tb else None
        logger.exception(
            "[jobs] generation:unhandled_exception athlete_id=%s job_id=%s exception_type=%s exception_msg=%s file=%s line=%s function=%s",
            athlete_id,
            job_id,
            type(exc).__name__,
            str(exc),
            frame.filename if frame else "",
            frame.lineno if frame else "",
            frame.name if frame else "",
        )
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
        raise
    return claimed
