"""Admin job linkage validation for the generation runtime.

Covers the two admin-initiated job sources whose linkage/ownership must be
verified before the request payload is parsed:
- ``admin_triage_resume`` (legacy plan-row resume or resume-from-job), and
- ``admin_latest_intake`` (linked intake must match the request payload).
"""
from __future__ import annotations

from typing import Any, Callable

from ..store import AppStore
from .errors import AdminLatestIntakeLinkageError, TriageResumeMissingPlanError
from .payloads import _stable_payload_hash, parse_plan_request


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
