from __future__ import annotations

import asyncio
import copy
from typing import TYPE_CHECKING, Any, Callable

from fastapi import BackgroundTasks, HTTPException, status

from ..generation_job_helpers import (
    _can_approve_and_resume_triage,
    _generation_job_stale_after_seconds,
    _has_existing_triage_resume_approval,
    _is_stale_job,
    _job_final_result_triage_status,
    _job_response,
    _resume_job_final_result_successful,
    _resume_job_resolved_successfully,
    _triage_job_has_resume_approval,
    _utc_now_iso,
)
from ..models import (
    ApproveAndResumeGenerationRequest,
    GenerationJobResponse,
    ProfileRecord,
)
from ..generation.lazy_scheduler import schedule_generation_job_if_needed
from ..store import AppStore

if TYPE_CHECKING:
    from ..stage2_automation import Stage2Automator

Planner = Callable[[dict[str, Any]], dict[str, Any]]


def _is_correctly_linked_admin_resume_job(
    job: dict[str, Any],
    *,
    athlete_id: str,
    plan_id: str,
    intake_id: str,
    client_request_id: str,
) -> bool:
    return (
        str(job.get("source") or "").strip().lower() == "admin_triage_resume"
        and str(job.get("athlete_id") or "").strip() == athlete_id
        and str(job.get("plan_id") or "").strip() == plan_id
        and str(job.get("intake_id") or "").strip() == intake_id
        and str(job.get("client_request_id") or "").strip() == client_request_id
    )


def _build_triage_resume_override(
    *,
    profile: ProfileRecord,
    approval: ApproveAndResumeGenerationRequest,
) -> dict[str, Any]:
    return {
        "approved": True,
        "approved_by": {
            "user_id": profile.athlete_id,
            "email": profile.email,
        },
        "reason": approval.reason,
        "allowed_modes": ["needs_review", "restricted_rehab_only"],
    }


async def approve_and_resume_plan_triage(
    *,
    plan_id: str,
    approval: ApproveAndResumeGenerationRequest,
    background_tasks: BackgroundTasks,
    profile: ProfileRecord,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator | None,
    active_tasks: set[str],
    enable_in_process_generation: bool,
) -> GenerationJobResponse:
    plan_row = await asyncio.to_thread(store.get_plan, plan_id)
    if not plan_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="plan not found"
        )

    intake_id = str(plan_row.get("intake_id") or "").strip()
    if not intake_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="plan is missing intake_id"
        )
    client_request_id = f"triage_resume_{plan_id}"
    stale_after_seconds = _generation_job_stale_after_seconds()
    existing_resume_job = await asyncio.to_thread(
        store.get_generation_job_by_client_request_id,
        athlete_id=str(plan_row["athlete_id"]),
        client_request_id=client_request_id,
    )

    async def _build_resume_request_payload() -> dict[str, Any]:
        intake_row = await asyncio.to_thread(store.get_intake, intake_id)
        if not intake_row or not isinstance(intake_row.get("intake"), dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="stored intake is missing for this plan",
            )
        payload = copy.deepcopy(intake_row.get("intake"))
        payload["_triage_resume_override"] = _build_triage_resume_override(
            profile=profile,
            approval=approval,
        )
        return payload

    async def _requeue_existing_resume_job(job: dict[str, Any]) -> dict[str, Any]:
        request_payload = await _build_resume_request_payload()
        return await asyncio.to_thread(
            store.update_generation_job,
            str(job.get("id") or ""),
            source="admin_triage_resume",
            request_payload=request_payload,
            intake_id=intake_id,
            plan_id=plan_id,
            stage1_result=None,
            final_result=None,
            error=None,
            completed_at=None,
            status="queued",
            heartbeat_at=_utc_now_iso(),
        )

    # Check for an existing approval first: once the resume has already
    # been run and the plan was updated in place, the triage state in
    # why_log no longer exists, so the triage-mode guard below would
    # otherwise mask the duplicate with a less specific error.
    if existing_resume_job and not _is_correctly_linked_admin_resume_job(
        existing_resume_job,
        athlete_id=str(plan_row["athlete_id"]),
        plan_id=plan_id,
        intake_id=intake_id,
        client_request_id=client_request_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="existing triage resume job has unsafe linkage; create a new resume request",
        )

    if _has_existing_triage_resume_approval(plan_row):
        if existing_resume_job:
            if _resume_job_resolved_successfully(existing_resume_job):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="this blocked plan has already been approved and resumed",
                )
            job_status = str(existing_resume_job.get("status") or "").strip().lower()
            if job_status == "running":
                if not _is_stale_job(
                    existing_resume_job,
                    stale_after_seconds=stale_after_seconds,
                ):
                    return _job_response(
                        existing_resume_job, store=store, viewer_role=profile.role
                    )
                existing_resume_job = await _requeue_existing_resume_job(
                    existing_resume_job
                )
                job_status = (
                    str(existing_resume_job.get("status") or "").strip().lower()
                )
            if job_status in {
                "failed",
                "completed",
            } and not _resume_job_final_result_successful(existing_resume_job):
                existing_resume_job = await _requeue_existing_resume_job(
                    existing_resume_job
                )
                job_status = (
                    str(existing_resume_job.get("status") or "").strip().lower()
                )
            if job_status == "queued":
                job = await schedule_generation_job_if_needed(
                    job=existing_resume_job,
                    background_tasks=background_tasks,
                    store=store,
                    planner_fn=planner_fn,
                    stage2=stage2,
                    active_tasks=active_tasks,
                    enable_in_process_generation=enable_in_process_generation,
                    stale_job_checker=_is_stale_job,
                    stale_after_seconds=stale_after_seconds,
                )
                return _job_response(job, store=store, viewer_role=profile.role)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this blocked plan has already been approved for resume",
        )

    if existing_resume_job:
        existing_status = str(existing_resume_job.get("status") or "").strip().lower()
        existing_is_stale = _is_stale_job(
            existing_resume_job,
            stale_after_seconds=stale_after_seconds,
        )
        if _resume_job_resolved_successfully(existing_resume_job):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="this blocked plan has already been approved and resumed",
            )
        if existing_status == "running":
            if existing_status == "running" and not existing_is_stale:
                return _job_response(
                    existing_resume_job, store=store, viewer_role=profile.role
                )

    why_log = (
        plan_row.get("why_log") if isinstance(plan_row.get("why_log"), dict) else {}
    )
    triage = (
        why_log.get("injury_triage")
        if isinstance(why_log.get("injury_triage"), dict)
        else {}
    )
    triage_mode = str(triage.get("mode") or "").strip().lower()
    if not _can_approve_and_resume_triage(triage_mode):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="approve_and_resume_generation is only allowed for needs_review or restricted_rehab_only plans",
        )
    request_payload = await _build_resume_request_payload()
    approval_log = {
        "approved_by_user_id": profile.athlete_id,
        "approved_by_email": profile.email,
        "approved_at": _utc_now_iso(),
        "reason": approval.reason,
        "action": "approve_and_resume_generation",
    }

    updated_why_log = dict(why_log)
    updated_why_log["triage_resume_approval"] = approval_log
    updated_why_log["triage_regeneration_cleared"] = True
    job = await asyncio.to_thread(
        store.create_or_get_generation_job,
        athlete_id=str(plan_row["athlete_id"]),
        client_request_id=client_request_id,
        source="admin_triage_resume",
        request_payload=request_payload,
        plan_id=plan_id,
        intake_id=intake_id,
        stale_after_seconds=stale_after_seconds,
    )
    if not _is_correctly_linked_admin_resume_job(
        job,
        athlete_id=str(plan_row["athlete_id"]),
        plan_id=plan_id,
        intake_id=intake_id,
        client_request_id=client_request_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="existing triage resume job has unsafe linkage; create a new resume request",
        )

    # Refresh/requeue only after run-state checks above. Non-stale running
    # jobs are returned as-is; completed successful jobs are rejected.
    job = await asyncio.to_thread(
        store.update_generation_job,
        str(job.get("id") or ""),
        source="admin_triage_resume",
        request_payload=request_payload,
        intake_id=intake_id,
        plan_id=plan_id,
        stage1_result=None,
        final_result=None,
        error=None,
        completed_at=None,
        status="queued",
        heartbeat_at=_utc_now_iso(),
    )

    # Persist the plan's triage-approval markers BEFORE scheduling the
    # runtime. The runtime's `update_plan_stage2_from_result` (see
    # generation_runtime.py) reads `triage_regeneration_cleared` and
    # `triage_resume_approval` out of the existing plan's why_log and
    # carries them onto the new Stage 2 result. Persisting after the
    # runtime can race the worker reading a not-yet-marked plan and lose
    # the audit trail.
    await asyncio.to_thread(
        store.update_plan_triage_approval,
        plan_id,
        why_log=updated_why_log,
        stage2_status="triage_resume_approved",
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
    return _job_response(job, store=store, viewer_role=profile.role)


async def approve_and_resume_job_triage(
    *,
    job_id: str,
    approval: ApproveAndResumeGenerationRequest,
    background_tasks: BackgroundTasks,
    profile: ProfileRecord,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator | None,
    active_tasks: set[str],
    enable_in_process_generation: bool,
) -> GenerationJobResponse:
    """Approve and resume generation for a triage-blocked outcome that
    lives only on the generation job (no plan row).

    Mirrors `/api/admin/plans/{plan_id}/approve-and-resume-generation`
    but reads athlete_id/intake_id/triage_mode from the source job's
    `final_result`. The resume job is created without a `plan_id`;
    Stage 2 produces a real plan row only if it succeeds.
    """
    source_job = await asyncio.to_thread(store.get_generation_job, job_id)
    if not source_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found"
        )

    triage_status = _job_final_result_triage_status(source_job)
    if not triage_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="generation job is not in a protected triage state",
        )

    athlete_id = str(source_job.get("athlete_id") or "").strip()
    intake_id = str(source_job.get("intake_id") or "").strip()
    if not athlete_id or not intake_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="generation job is missing athlete_id or intake_id",
        )

    source_final_result = (
        source_job.get("final_result")
        if isinstance(source_job.get("final_result"), dict)
        else {}
    )
    source_why_log = (
        source_final_result.get("why_log")
        if isinstance(source_final_result.get("why_log"), dict)
        else {}
    )
    triage = (
        source_why_log.get("injury_triage")
        if isinstance(source_why_log.get("injury_triage"), dict)
        else {}
    )
    triage_mode = str(triage.get("mode") or "").strip().lower()
    if not _can_approve_and_resume_triage(triage_mode):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="approve_and_resume_generation is only allowed for needs_review or restricted_rehab_only outcomes",
        )

    if _triage_job_has_resume_approval(source_job):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this blocked job has already been approved for resume",
        )

    client_request_id = f"triage_resume_job_{job_id}"
    stale_after_seconds = _generation_job_stale_after_seconds()

    # If a prior resume attempt already produced a successful resume job
    # under the deterministic client_request_id, refuse re-approval. This
    # prevents the state_machine's completed→queued transition from
    # silently wiping a good resume_job's final_result/plan_id, and it
    # avoids reaching the marker write below without first surfacing a
    # clear conflict to the admin.
    existing_resume_job = await asyncio.to_thread(
        store.get_generation_job_by_client_request_id,
        athlete_id=athlete_id,
        client_request_id=client_request_id,
    )
    if existing_resume_job:
        if _resume_job_resolved_successfully(existing_resume_job):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="this blocked job has already been approved and resumed",
            )
        existing_status = str(existing_resume_job.get("status") or "").strip().lower()
        existing_is_stale = _is_stale_job(
            existing_resume_job,
            stale_after_seconds=stale_after_seconds,
        )
        # A healthy in-flight resume job already represents the approved
        # regeneration. Returning it as-is preserves stage1_result,
        # final_result, plan_id, and heartbeat state — the reset path
        # below would otherwise wipe in-progress work. Mirrors the
        # plan-based flow's running-not-stale early return in
        # approve_and_resume_plan_triage. Stale running jobs fall through
        # to the reset/recovery path below.
        if existing_status == "running" and not existing_is_stale:
            return _job_response(
                existing_resume_job, store=store, viewer_role=profile.role
            )

    intake_row = await asyncio.to_thread(store.get_intake, intake_id)
    if not intake_row or not isinstance(intake_row.get("intake"), dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="stored intake is missing for this job",
        )

    request_payload = copy.deepcopy(intake_row.get("intake"))
    request_payload["_triage_resume_override"] = _build_triage_resume_override(
        profile=profile,
        approval=approval,
    )

    approval_log = {
        "approved_by_user_id": profile.athlete_id,
        "approved_by_email": profile.email,
        "approved_at": _utc_now_iso(),
        "reason": approval.reason,
        "action": "approve_and_resume_generation_from_job",
        "source_job_id": job_id,
    }

    # Create + reset the resume job FIRST. The source-job approval marker
    # is the gate that future re-approval attempts hit (line 2348), so it
    # must only be written once the resume job is durably persisted —
    # otherwise a failure between marker-write and resume-job-create would
    # permanently lock the source job in "already approved" without any
    # functional resume job to drive the regeneration.
    resume_job = await asyncio.to_thread(
        store.create_or_get_generation_job,
        athlete_id=athlete_id,
        client_request_id=client_request_id,
        source="admin_triage_resume",
        request_payload=request_payload,
        intake_id=intake_id,
        stale_after_seconds=stale_after_seconds,
    )
    # Reset job state in case it was reused (idempotent retry).
    resume_job = await asyncio.to_thread(
        store.update_generation_job,
        str(resume_job.get("id") or ""),
        source="admin_triage_resume",
        request_payload=request_payload,
        intake_id=intake_id,
        stage1_result=None,
        final_result=None,
        error=None,
        completed_at=None,
        status="queued",
        heartbeat_at=_utc_now_iso(),
    )

    # Resume job is durable; now mark the source job's final_result with
    # the approval marker so a second approval attempt is rejected with a
    # clear conflict error.
    updated_source_final_result = dict(source_final_result)
    merged_source_why_log = dict(source_why_log)
    merged_source_why_log["triage_resume_approval"] = approval_log
    merged_source_why_log["triage_regeneration_cleared"] = True
    updated_source_final_result["why_log"] = merged_source_why_log
    updated_source_final_result["stage2_status"] = "triage_resume_approved"
    await asyncio.to_thread(
        store.update_generation_job,
        job_id,
        final_result=updated_source_final_result,
        heartbeat_at=_utc_now_iso(),
    )
    resume_job = await schedule_generation_job_if_needed(
        job=resume_job,
        background_tasks=background_tasks,
        store=store,
        planner_fn=planner_fn,
        stage2=stage2,
        active_tasks=active_tasks,
        enable_in_process_generation=enable_in_process_generation,
        stale_job_checker=_is_stale_job,
        stale_after_seconds=stale_after_seconds,
    )
    return _job_response(resume_job, store=store, viewer_role=profile.role)
