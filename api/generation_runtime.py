from __future__ import annotations

import asyncio
import json
import logging
import traceback
import os
import threading
import time
from contextlib import suppress
from typing import Any, Callable

from fastapi import BackgroundTasks, HTTPException, status

from .models import PlanRequest, ProfileUpdateRequest
from .stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError, Stage2Automator
from .state_machine import job_status_for_plan_status
from .store import AppStore
from .generation.time_utils import utc_now_iso
from .generation.types import Planner, ProgressCallback
from .generation.errors import AdminLatestIntakeLinkageError, TriageResumeMissingPlanError
from .generation.timeouts import (
    _stage1_planner_timeout_seconds,
    _stage2_finalize_timeout_seconds as _stage2_finalize_timeout_seconds,
)
from .generation.stage2_runner import (
    _OPENAI_QUOTA_ADMIN_ERROR,
    _OPENAI_QUOTA_ATHLETE_ERROR as _OPENAI_QUOTA_ATHLETE_ERROR,
    finalize_stage2_with_timeout,
    is_openai_quota_error,
)
from .generation.triage import (
    _compact_generation_job_final_result as _compact_generation_job_final_result,
    _is_triage_skipped_final_result,
    should_skip_stage2,
)
from .generation.persistence import (
    persist_plan_and_finalize,
    persist_triage_review_required,
)
from .generation.milestones import (
    _MAX_PERSISTED_MILESTONES as _MAX_PERSISTED_MILESTONES,
    build_progress_recorder,
)
from .generation.heartbeat import (
    heartbeat_generation_job,
    is_stale_job as is_stale_job,
    recover_stale_running_job,
)
from .generation.stage1_runner import (
    _invoke_planner as _invoke_planner,
    _stage1_mp_start_method as _stage1_mp_start_method,
    default_planner as default_planner,
    run_stage1_planner,
)

logger = logging.getLogger(__name__)
_TRIAGE_RESUME_OVERRIDE_KEY = "_triage_resume_override"


_DETACHED_GENERATION_TASKS: set[asyncio.Task[None]] = set()
_TERMINAL_GENERATION_JOB_STATUSES = {"completed", "review_required", "failed"}


def generation_status_from_plan_status(plan_status: str) -> str:
    return job_status_for_plan_status(plan_status)


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    try:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        normalized = json.dumps(str(payload), ensure_ascii=False)
    return normalized


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


async def validate_admin_triage_resume_linkage(
    *,
    job_source: str,
    athlete_id: str,
    plan_id: str | None,
    intake_id: str | None,
    store: AppStore,
    to_thread_with_heartbeat: Callable[..., Any],
    emit_milestone: Callable[..., None],
) -> dict[str, Any] | None:
    """Validate an admin_triage_resume job's linkage before parsing the payload.

    Returns the linked legacy plan row when the resume was started against one,
    or ``None`` for resume-from-job (and for any non-resume source). Raises
    ``TriageResumeMissingPlanError`` on any ownership/linkage failure.
    """
    if job_source != "admin_triage_resume":
        return None
    if not intake_id:
        raise TriageResumeMissingPlanError(
            "admin triage resume job is missing intake_id; refusing to create a duplicate plan"
        )

    if plan_id:
        # Legacy plan-row resume: validate the linked plan exists and
        # is owned by the same athlete/intake before continuing.
        admin_resume_plan_row = await to_thread_with_heartbeat(store.get_plan, plan_id)
        if not admin_resume_plan_row:
            raise TriageResumeMissingPlanError(
                "admin triage resume job linked plan was not found; refusing to create a duplicate plan"
            )

        linked_athlete_id = str(admin_resume_plan_row.get("athlete_id") or "").strip()
        linked_intake_id = str(admin_resume_plan_row.get("intake_id") or "").strip()

        if linked_athlete_id != athlete_id:
            raise TriageResumeMissingPlanError(
                "admin triage resume job linked plan belongs to a different athlete"
            )

        if linked_intake_id != intake_id:
            raise TriageResumeMissingPlanError(
                "admin triage resume job intake_id does not match linked plan intake_id"
            )

        emit_milestone(
            "admin_resume_linkage_validated",
            "Admin resume linkage validated",
            "Linked plan and intake were verified before parsing the request payload.",
            plan_id=plan_id,
            intake_id=intake_id,
        )
        return admin_resume_plan_row

    # Resume-from-job (no legacy plan row): validate intake exists.
    linked_intake = await to_thread_with_heartbeat(store.get_intake, intake_id)
    if not linked_intake:
        raise TriageResumeMissingPlanError(
            "admin triage resume job intake_id was not found"
        )
    linked_athlete_id = str(linked_intake.get("athlete_id") or "").strip()
    if linked_athlete_id != athlete_id:
        raise TriageResumeMissingPlanError(
            "admin triage resume job intake belongs to a different athlete"
        )
    emit_milestone(
        "admin_resume_linkage_validated",
        "Admin resume linkage validated",
        "Intake was verified before parsing the request payload.",
        intake_id=intake_id,
    )
    return None


async def validate_admin_latest_intake_linkage(
    *,
    job_source: str,
    athlete_id: str,
    intake_id: str | None,
    raw_request_payload: Any,
    store: AppStore,
    to_thread_with_heartbeat: Callable[..., Any],
) -> None:
    """Validate an admin_latest_intake job's linked intake before parsing.

    Raises ``AdminLatestIntakeLinkageError`` if the intake is missing, owned by
    a different athlete, or does not semantically match the job request payload.
    """
    if job_source != "admin_latest_intake":
        return
    if not intake_id:
        raise AdminLatestIntakeLinkageError("admin latest intake job is missing intake_id")
    linked_intake = await to_thread_with_heartbeat(store.get_intake, intake_id)
    if not linked_intake:
        raise AdminLatestIntakeLinkageError("admin latest intake job intake_id was not found")
    linked_athlete_id = str(linked_intake.get("athlete_id") or "").strip()
    if linked_athlete_id != athlete_id:
        raise AdminLatestIntakeLinkageError("admin latest intake job intake belongs to a different athlete")
    linked_payload = linked_intake.get("intake")
    if not isinstance(linked_payload, dict):
        raise AdminLatestIntakeLinkageError("admin latest intake job linked intake payload is invalid")
    from pydantic import ValidationError
    try:
        normalized_linked_payload = parse_plan_request(linked_payload).model_dump(mode="json")
    except ValidationError as exc:
        raise AdminLatestIntakeLinkageError("admin latest intake job linked intake payload is invalid") from exc

    normalized_request_payload = parse_plan_request(raw_request_payload).model_dump(mode="json")

    if _stable_payload_hash(normalized_linked_payload) != _stable_payload_hash(normalized_request_payload):
        raise AdminLatestIntakeLinkageError(
            "admin latest intake job request_payload does not match linked intake payload"
        )


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
    heartbeat_task: asyncio.Task[None] | None = None
    athlete_id = "unknown"
    progress_callback: ProgressCallback | None = None
    stage1_timed_out = threading.Event()
    seen_milestone_codes: set[str] = set()

    def _emit_milestone(code: str, label: str, detail: str = "", **meta: Any) -> None:
        if progress_callback is None:
            return
        if code == "stage1_planner_timeout" and code in seen_milestone_codes:
            return
        try:
            progress_callback(code, label, detail, meta)
            seen_milestone_codes.add(code)
        except Exception:
            logger.exception("[jobs] generation:milestone_emit_failed job_id=%s code=%s", job_id, code)

    async def _touch_heartbeat() -> None:
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                heartbeat_at=utc_now_iso(),
            )

    async def _to_thread_with_heartbeat(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        await _touch_heartbeat()
        result = await asyncio.to_thread(fn, *args, **kwargs)
        await _touch_heartbeat()
        return result

    async def _ensure_admin_resume_plan_exists(linked_plan_id: str | None) -> None:
        if job_source != "admin_triage_resume":
            return
        # resume-from-job (no legacy plan_id) is valid: a real plan row
        # will be created after Stage 2 succeeds. Only validate when the
        # resume was started against a legacy plan row.
        if not linked_plan_id:
            if resume_from_job_only:
                return
            raise TriageResumeMissingPlanError(
                "admin triage resume job lost its linked plan_id; refusing to continue"
            )
        linked = await _to_thread_with_heartbeat(store.get_plan, linked_plan_id)
        if not linked:
            raise TriageResumeMissingPlanError(
                "admin triage resume job linked plan was deleted while generation was running"
            )

    try:
        # Claim the job for processing. This implements the worker-claim model
        # introduced in #1417 while preserving Main's heartbeat-on-read safety.
        job = await asyncio.to_thread(store.claim_generation_job_start, job_id)
        if not job:
            logger.warning("[jobs] generation:claim_unavailable job_id=%s", job_id)
            return

        # Use persisted milestones as the initial state for the progress recorder.
        persisted_milestones = job.get("progress_milestones")
        initial_milestones = persisted_milestones if isinstance(persisted_milestones, list) else []
        for milestone in initial_milestones:
            if isinstance(milestone, dict):
                milestone_code = str(milestone.get("code") or "").strip()
                if milestone_code:
                    seen_milestone_codes.add(milestone_code)
        _, progress_callback = build_progress_recorder(
            job_id=job_id,
            store=store,
            initial_milestones=initial_milestones,
            should_persist=lambda: not stage1_timed_out.is_set(),
        )
        heartbeat_task = asyncio.create_task(heartbeat_generation_job(job_id, store, stop_event))

        athlete_id = str(job["athlete_id"])
        raw_request_payload = job.get("request_payload") or {}

        # Triaging override information: track approval flag and any allowed modes.
        triage_resume_override_approved = False
        triage_override_allowed_modes: list[Any] = []
        if isinstance(raw_request_payload, dict):
            triage_override = raw_request_payload.get(_TRIAGE_RESUME_OVERRIDE_KEY)
            if isinstance(triage_override, dict):
                triage_resume_override_approved = triage_override.get("approved") is True
                modes = triage_override.get("allowed_modes")
                if isinstance(modes, list):
                    triage_override_allowed_modes = list(modes)

        # Normalize source and linked ids early for admin resume validation.
        job_source = str(job.get("source") or "").strip().lower()
        plan_id = str(job.get("plan_id") or "").strip() or None
        intake_id = str(job.get("intake_id") or "").strip() or None
        # Track whether this resume was started without a legacy plan_id —
        # in that case the resume runs against the generation job/intake
        # directly, and a real plan is created only when Stage 2 succeeds.
        resume_from_job_only = job_source == "admin_triage_resume" and not plan_id

        admin_resume_plan_row = await validate_admin_triage_resume_linkage(
            job_source=job_source,
            athlete_id=athlete_id,
            plan_id=plan_id,
            intake_id=intake_id,
            store=store,
            to_thread_with_heartbeat=_to_thread_with_heartbeat,
            emit_milestone=_emit_milestone,
        )

        await validate_admin_latest_intake_linkage(
            job_source=job_source,
            athlete_id=athlete_id,
            intake_id=intake_id,
            raw_request_payload=raw_request_payload,
            store=store,
            to_thread_with_heartbeat=_to_thread_with_heartbeat,
        )

        await _touch_heartbeat()
        request_body = parse_plan_request(raw_request_payload)
        await _touch_heartbeat()
        _emit_milestone(
            "request_payload_parsed",
            "Request payload parsed",
            "Stored intake payload passed request validation.",
        )
        logger.info(
            "[jobs] generation:start athlete_id=%s job_id=%s source=%s job_plan_id=%s job_intake_id=%s "
            "override_present=%s override_approved=%s override_allowed_modes=%s",
            athlete_id,
            job_id,
            job.get("source"),
            job.get("plan_id"),
            job.get("intake_id"),
            isinstance(raw_request_payload, dict)
            and _TRIAGE_RESUME_OVERRIDE_KEY in raw_request_payload,
            triage_resume_override_approved,
            triage_override_allowed_modes,
        )

        try:
            _emit_milestone(
                "profile_update_started",
                "Profile update started",
                "Refreshing athlete profile fields from the request payload.",
            )
            await _to_thread_with_heartbeat(
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
            _emit_milestone(
                "profile_update_finished",
                "Profile update finished",
                "Athlete profile fields were refreshed.",
            )
        except Exception:
            logger.exception("[jobs] generation:update_profile_failed athlete_id=%s job_id=%s", athlete_id, job_id)
            _emit_milestone(
                "profile_update_finished",
                "Profile update finished",
                "Profile refresh failed; generation is continuing with the stored payload.",
                failed=True,
            )
        if not intake_id:
            intake = await _to_thread_with_heartbeat(store.create_intake, athlete_id, request_body)
            intake_id = str(intake["id"])
            job = await _to_thread_with_heartbeat(
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
            _emit_milestone(
                "stage1_planner_starting",
                "Stage 1 planner starting",
                "Starting the deterministic planner pass.",
            )
            await _touch_heartbeat()
            _emit_milestone(
                "stage1_planner_invoked",
                "Stage 1 planner invoked",
                "Planner process was invoked and is waiting for its first result.",
            )
            stage1_timeout_seconds = _stage1_planner_timeout_seconds()
            try:
                stage1_result = await run_stage1_planner(
                    planner_fn,
                    planner_payload,
                    progress_callback=progress_callback,
                    timeout_seconds=stage1_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.exception("[jobs] generation:stage1_timeout athlete_id=%s job_id=%s", athlete_id, job_id)
                now_iso = utc_now_iso()
                _emit_milestone(
                    "stage1_planner_timeout",
                    "Stage 1 planner timed out",
                    "Planner did not return after invocation and the job was failed for recovery.",
                    timestamp=now_iso,
                    failed=True,
                )
                stage1_timed_out.set()
                with suppress(Exception):
                    await asyncio.to_thread(
                        store.update_generation_job,
                        job_id,
                        status="failed",
                        error="Stage 1 planner timed out before producing a result.",
                        completed_at=now_iso,
                        heartbeat_at=now_iso,
                    )
                return
            _emit_milestone(
                "stage1_planner_finished",
                "Stage 1 planner finished",
                "Planner returned a Stage 1 result.",
            )
            await _touch_heartbeat()
            if stage1_result.get("status") == "invalid_input":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": stage1_result.get("error", "invalid planning input"),
                        "missing_fields": stage1_result.get("missing_fields", []),
                    },
                )
            _stage1_why_log = stage1_result.get("why_log") if isinstance(stage1_result.get("why_log"), dict) else {}
            _injury_triage = _stage1_why_log.get("injury_triage") if isinstance(_stage1_why_log.get("injury_triage"), dict) else {}
            _override_marker = (
                _stage1_why_log.get("injury_triage_resume_override")
                if isinstance(_stage1_why_log.get("injury_triage_resume_override"), dict)
                else None
            )
            logger.info(
                "[jobs] generation:stage1_done athlete_id=%s job_id=%s stage1_status=%s "
                "triage_mode=%s should_block_stage2=%s override_applied=%s",
                athlete_id,
                job_id,
                stage1_result.get("status"),
                _injury_triage.get("mode"),
                _injury_triage.get("should_block_stage2"),
                bool(_override_marker and _override_marker.get("bypassed_blocking") is True),
            )
            _emit_milestone(
                "stage1_result_persist_started",
                "Stage 1 result persist started",
                "Saving Stage 1 planner result to the generation job.",
            )
            job = await _to_thread_with_heartbeat(
                store.update_generation_job,
                job_id,
                stage1_result=stage1_result,
                heartbeat_at=utc_now_iso(),
            )
            _emit_milestone(
                "stage1_result_persisted",
                "Stage 1 result persisted",
                "Stage 1 planner result was saved to the generation job.",
            )
            await _ensure_admin_resume_plan_exists(plan_id)

        final_result = job.get("final_result")
        if not isinstance(final_result, dict):
            await _ensure_admin_resume_plan_exists(plan_id)
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
                await _touch_heartbeat()
                stage1_result = {
                    **stage1_result,
                    "_generation_source": str(job.get("source") or ""),
                }
                finalized_result = await finalize_stage2_with_timeout(
                    stage2=stage2,
                    stage1_result=stage1_result,
                )
                await _touch_heartbeat()
                final_result = {**finalized_result, "full_name": request_body.athlete.full_name}
                _emit_milestone(
                    "stage2_result_ready",
                    "Stage 2 result ready",
                    "Finalizer result returned; saving review state.",
                )
                if str(final_result.get("status") or "").strip().lower() == "ready":
                    _emit_milestone(
                        "stage2_validated",
                        "Stage 2 finalizer complete",
                        "Validator passed. Final coach-voice plan ready for handoff.",
                    )
                else:
                    _emit_milestone(
                        "stage2_review_required",
                        "Stage 2 needs review",
                        "First-pass finalizer output did not pass validation. No automatic retry was sent.",
                    )
        # Triage-blocked Stage 1 outcomes are protected review states, not
        # plans. They live exclusively on the generation job — no plan row
        # is created or updated. The admin "Approve & Resume" flow drives
        # the next generation from the job; if Stage 2 then succeeds, the
        # resume runtime branch persists a real plan row at that point.
        triage_skipped = _is_triage_skipped_final_result(final_result)
        plan_id = plan_id or (str(job.get("plan_id") or "") or None)

        if triage_skipped:
            await persist_triage_review_required(
                job_id=job_id,
                athlete_id=athlete_id,
                plan_id=plan_id,
                job_source=job_source,
                final_result=final_result,
                admin_resume_plan_row=admin_resume_plan_row,
                store=store,
                emit_milestone=_emit_milestone,
                to_thread_with_heartbeat=_to_thread_with_heartbeat,
                t_start=t_start,
            )
            return

        await persist_plan_and_finalize(
            job=job,
            job_id=job_id,
            athlete_id=athlete_id,
            plan_id=plan_id,
            intake_id=intake_id,
            job_source=job_source,
            resume_from_job_only=resume_from_job_only,
            admin_resume_plan_row=admin_resume_plan_row,
            final_result=final_result,
            request_body=request_body,
            store=store,
            emit_milestone=_emit_milestone,
            to_thread_with_heartbeat=_to_thread_with_heartbeat,
            t_start=t_start,
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
        resolved_error = _OPENAI_QUOTA_ADMIN_ERROR if is_openai_quota_error(exc) else str(exc)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=resolved_error,
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
    except TriageResumeMissingPlanError as exc:
        logger.error(
            "[jobs] generation:resume_missing_plan_failure athlete_id=%s job_id=%s",
            athlete_id,
            job_id,
        )
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=str(exc),
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except AdminLatestIntakeLinkageError as exc:
        logger.error(
            "[jobs] generation:admin_latest_intake_linkage_failure athlete_id=%s job_id=%s",
            athlete_id,
            job_id,
        )
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=str(exc),
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
        if heartbeat_task is not None:
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
