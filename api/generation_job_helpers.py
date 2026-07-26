"""Generation-job response/diagnostic helpers extracted from api.app (PR2: pure helpers)."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

try:  # zoneinfo is stdlib on Python 3.9+; degrade gracefully if unavailable.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - defensive fallback only
    ZoneInfo = None  # type: ignore[assignment]

from fastapi import HTTPException, status

from .generation_config import generation_job_stale_after_seconds
# Import from the concrete (light) generation modules rather than the
# generation_runtime shim: the shim eagerly re-exports the planner/orchestrator
# surface (fightcamp.main), which the web service must not load just to reach a
# couple of error strings and the stale-job check.
from .generation.stage2_runner import (
    _OPENAI_QUOTA_ADMIN_ERROR,
    _OPENAI_QUOTA_ATHLETE_ERROR,
)
from .generation.heartbeat import is_stale_job as runtime_is_stale_job
from .generation.time_utils import utc_now_iso as _utc_now_iso
from .models import (
    PROFILE_REFRESH_FAILED_WARNING,
    PROFILE_REFRESH_FAILED_WHY_LOG_KEY,
    AdminGenerationJobDiagnostic,
    GenerationJobResponse,
    GenerationRequestPayloadSummary,
)
from .plan_mappers import _is_archived_plan, _is_triage_blocked_plan
from .store import AppStore


_CLIENT_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


_PROTECTED_TRIAGE_STATUSES = frozenset({"triage_blocked", "needs_review", "restricted_rehab_only", "medical_hold"})

# Non-athlete, non-admin viewers (coach / gym_owner, reserved for public beta)
# get a retry-oriented message instead of the stored technical error. Admins
# keep the raw error for debugging; athletes keep the existing sanitized text.
_GENERATION_FRIENDLY_RETRY_ERROR = (
    "Plan generation didn't complete this time. Please try again in a few moments."
)


def resolve_viewer_role(profile: Any, *, is_admin: bool) -> str:
    """Viewer role for ``_job_response`` error redaction.

    Only an effective admin (role AND allowlisted email, per
    ``is_effective_admin_profile``) may see raw stored errors. A profile whose
    role still says "admin" without passing that check must be redacted like an
    athlete, not trusted on its stored role. Missing/blank roles also collapse
    to "athlete".
    """
    if is_admin:
        return "admin"
    role = str(getattr(profile, "role", "") or "").strip()
    if not role or role == "admin":
        return "athlete"
    return role


_DAILY_LIMIT_DETAIL_TZ_AWARE = (
    "Daily generation limit reached. Try again after midnight in your athlete timezone."
)
_DAILY_LIMIT_DETAIL_UTC = (
    "Daily generation limit reached. Try again after midnight UTC."
)


def daily_generation_cap_window(
    athlete_timezone: str | None,
    *,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Compute the start of the current local day for the daily generation cap.

    Returns a ``(cutoff_iso_utc, limit_reached_detail)`` tuple:

    * ``cutoff_iso_utc`` is the UTC ISO timestamp for the start of the current
      day in the athlete's timezone, suitable for
      ``store.count_generation_jobs_for_athlete_since``.
    * ``limit_reached_detail`` is the user-facing message describing when the
      cap resets.

    When the timezone is missing or invalid (or ``zoneinfo`` is unavailable),
    this safely falls back to UTC midnight and a UTC-based reset message.
    """
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    tz_name = (athlete_timezone or "").strip()
    if tz_name and ZoneInfo is not None:
        try:
            local_now = reference.astimezone(ZoneInfo(tz_name))
            local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_iso = local_midnight.astimezone(timezone.utc).isoformat()
            return cutoff_iso, _DAILY_LIMIT_DETAIL_TZ_AWARE
        except Exception:
            # Invalid/unknown timezone — fall back to UTC below.
            pass

    utc_midnight = (
        reference.astimezone(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )
    return utc_midnight, _DAILY_LIMIT_DETAIL_UTC


def _normalized_client_request_id(raw_value: str | None, fallback_prefix: str) -> str:
    normalized = (raw_value or "").strip()
    if not normalized:
        return f"{fallback_prefix}_{uuid.uuid4().hex}"
    if _CLIENT_REQUEST_ID_PATTERN.fullmatch(normalized):
        return normalized
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-Client-Request-Id")


def _normalize_progress_milestones(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "").strip()
        if not code:
            continue
        meta_raw = entry.get("meta")
        meta = meta_raw if isinstance(meta_raw, dict) else {}
        normalized.append(
            {
                "code": code,
                "label": str(entry.get("label") or "").strip(),
                "detail": str(entry.get("detail") or ""),
                "at": str(entry.get("at") or ""),
                "meta": meta,
            }
        )
    return normalized


def _job_warnings_from_milestones(raw: Any) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for milestone in _normalize_progress_milestones(raw):
        meta = milestone.get("meta")
        if not isinstance(meta, dict) or meta.get("warning") is not True:
            continue
        detail = str(milestone.get("detail") or "").strip()
        if not detail or detail in seen:
            continue
        warnings.append(detail)
        seen.add(detail)
    return warnings


def _has_durable_profile_refresh_failed(job: dict[str, Any]) -> bool:
    """Whether the durable profile-refresh-failed marker is set on the job.

    The marker rides ``final_result["why_log"]`` (written by the generation
    orchestrator), so it survives the FIFO eviction of the progress-milestone list.
    """
    final_result = job.get("final_result")
    if not isinstance(final_result, dict):
        return False
    why_log = final_result.get("why_log")
    if not isinstance(why_log, dict):
        return False
    return bool(why_log.get(PROFILE_REFRESH_FAILED_WHY_LOG_KEY))


def _job_warnings(job: dict[str, Any]) -> list[str]:
    """Job warnings, merging progress-milestone warnings with the durable marker.

    The progress-milestone list is capped (FIFO), so a long run can evict the
    profile-refresh warning milestone. Merging the durable ``why_log`` marker keeps
    the warning on the response regardless of eviction, deduped against milestones.
    """
    warnings = _job_warnings_from_milestones(job.get("progress_milestones"))
    if _has_durable_profile_refresh_failed(job) and PROFILE_REFRESH_FAILED_WARNING not in warnings:
        warnings.append(PROFILE_REFRESH_FAILED_WARNING)
    return warnings


def _job_response(
    job: dict[str, Any],
    *,
    store: AppStore | None = None,
    latest_plan_id: str | None = None,
    viewer_role: str = "athlete",
) -> GenerationJobResponse:
    def _resolve_existing_plan_id(candidate: str | None) -> str | None:
        if not candidate:
            return None
        normalized_candidate = str(candidate).strip()
        if not normalized_candidate:
            return None
        if store is None:
            return normalized_candidate
        existing_plan = store.get_plan(normalized_candidate)
        return normalized_candidate if existing_plan is not None else None

    status_value = str(job.get("status") or "")
    normalized_status = normalize_generation_job_status(status_value)
    plan_id = _resolve_existing_plan_id(str(job.get("plan_id")) if job.get("plan_id") else None)
    resolved_latest_plan_id = latest_plan_id
    # Triage-blocked outcomes live only on the job — they explicitly must
    # not back-fill a plan_id from milestones or latest_plan, otherwise the
    # UI would re-open the wrong (old) plan and the duplicate-generation
    # loop returns. Skip the fallback chain for these outcomes.
    job_triage_status = _job_final_result_triage_status(job)
    if (
        normalized_status in {"completed", "review_required"}
        and not plan_id
        and not job_triage_status
    ):
        milestones = _normalize_progress_milestones(job.get("progress_milestones"))
        for milestone in reversed(milestones):
            meta = milestone.get("meta")
            if not isinstance(meta, dict):
                continue
            milestone_plan_id = str(meta.get("plan_id") or "").strip()
            if milestone_plan_id:
                resolved_milestone_plan_id = _resolve_existing_plan_id(milestone_plan_id)
                if resolved_milestone_plan_id:
                    plan_id = resolved_milestone_plan_id
                    break
        if not plan_id and store is not None:
            athlete_id = str(job.get("athlete_id") or "").strip()
            intake_id = str(job.get("intake_id") or "").strip()
            # Require an explicit intake_id link AND an exact match. Without
            # an intake_id we cannot prove the latest plan was produced by
            # this job, so we must not surface it: a stale "latest_plan_id"
            # would let the UI open an unrelated plan that just happens to
            # be the newest row for the athlete.
            if athlete_id and intake_id:
                latest_plan = store.get_latest_plan(athlete_id)
                latest_id = str(latest_plan.get("id") or "").strip() if latest_plan else ""
                latest_intake = str(latest_plan.get("intake_id") or "").strip() if latest_plan else ""
                latest_status = str(latest_plan.get("status") or "").strip().lower() if latest_plan else ""
                if latest_id and latest_status != "archived" and latest_intake == intake_id:
                    plan_id = latest_id
        resolved_latest_plan_id = resolved_latest_plan_id or plan_id
    updated_at = job.get("updated_at") or job.get("created_at") or _utc_now_iso()
    error = str(job["error"]) if job.get("error") else None
    if error and viewer_role != "admin":
        if error == _OPENAI_QUOTA_ADMIN_ERROR:
            # Quota exhaustion keeps its dedicated message for EVERY non-admin
            # viewer (athlete or coach/gym_owner): "try again in a few moments"
            # would be wrong guidance when the actual fix is an admin restoring
            # the OpenAI billing/quota.
            error = _OPENAI_QUOTA_ATHLETE_ERROR
        elif viewer_role != "athlete":
            error = _GENERATION_FRIENDLY_RETRY_ERROR
    can_retry = (
        normalized_status == "failed"
        and isinstance(job.get("request_payload"), dict)
        and not plan_id
    )
    status_messages = {
        "queued": "Generation queued and will be processed shortly.",
        "running": "Generation started and is processing.",
        "failed": "Generation failed.",
        "review_required": "Your plan is ready for review.",
        "completed": "Your plan is ready.",
    }
    stage2_status = ""
    requires_admin_resume = False
    if plan_id and store is not None:
        linked_plan = store.get_plan(plan_id)
        linked_status = str(linked_plan.get("status") or "").strip().lower() if isinstance(linked_plan, dict) else ""
        linked_stage2 = (
            str(linked_plan.get("stage2_status") or "").strip().lower()
            if isinstance(linked_plan, dict)
            else ""
        )
        stage2_status = linked_stage2
        if linked_status in _PROTECTED_TRIAGE_STATUSES or linked_stage2 in _PROTECTED_TRIAGE_STATUSES:
            requires_admin_resume = True
    # Triage outcomes without a plan_id derive their state from the job's
    # final_result. They are protected review states, not saved plans.
    if not plan_id and job_triage_status:
        requires_admin_resume = True
        stage2_status = stage2_status or job_triage_status
    # A terminal job whose linked plan is still triage-blocked must not be
    # framed as a normal "plan ready" outcome — the UI needs to route to
    # admin review instead of celebrating a saved plan.
    message = status_messages.get(normalized_status, "Generation queued and will be processed shortly.")
    if requires_admin_resume and normalized_status in {"completed", "review_required"}:
        message = (
            "Planning paused. Admin review is required before generation can continue."
        )
    return GenerationJobResponse(
        job_id=str(job["id"]),
        athlete_id=str(job["athlete_id"]),
        client_request_id=str(job.get("client_request_id") or ""),
        status=normalized_status,
        created_at=str(job["created_at"]),
        updated_at=str(updated_at),
        started_at=str(job["started_at"]) if job.get("started_at") else None,
        heartbeat_at=str(job["heartbeat_at"]) if job.get("heartbeat_at") else None,
        completed_at=str(job["completed_at"]) if job.get("completed_at") else None,
        error=error,
        plan_id=plan_id,
        latest_plan_id=resolved_latest_plan_id or plan_id,
        status_url=f"/api/generation-jobs/{job['id']}",
        message=message,
        progress_milestones=_normalize_progress_milestones(job.get("progress_milestones")),
        warnings=_job_warnings(job),
        can_retry=can_retry,
        stage2_status=stage2_status or None,
        requires_admin_resume=requires_admin_resume,
    )


def _build_protected_triage_response(plan: dict[str, Any], athlete_id: str) -> GenerationJobResponse:
    plan_id = str(plan.get("id") or "").strip()
    plan_status = str(plan.get("status") or "").strip().lower()
    stage2_status = str(plan.get("stage2_status") or "").strip().lower()
    return GenerationJobResponse(
        job_id=f"protected_{plan_id or athlete_id}",
        athlete_id=athlete_id,
        client_request_id="protected_triage_restore",
        status="completed",
        created_at=_utc_now_iso(),
        updated_at=_utc_now_iso(),
        plan_id=plan_id or None,
        latest_plan_id=plan_id or None,
        message="This intake is protected. Normal Generate Plan cannot bypass triage. Use Admin Review → Resume Generation.",
        stage2_status=stage2_status or plan_status or None,
        requires_admin_resume=True,
    )


def normalize_generation_job_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "held_for_review":
        return "review_required"
    if normalized in {"publishable_with_flags", "ready"}:
        return "completed"
    if normalized in {"queued", "running", "completed", "review_required", "failed"}:
        return normalized
    return "failed"


def _is_stale_job(job: dict[str, Any], *, stale_after_seconds: int = 90) -> bool:
    return runtime_is_stale_job(job, stale_after_seconds=stale_after_seconds)


def _resume_job_final_result_successful(job: dict[str, Any]) -> bool:
    final_result = job.get("final_result")
    if not isinstance(final_result, dict):
        return False
    result_status = str(final_result.get("status") or "").strip().lower()
    if result_status in {"ready", "generated", "completed"}:
        return True
    stage2_status = str(final_result.get("stage2_status") or "").strip().lower()
    return stage2_status in {"stage2_pass", "stage2_retry_pass", "manual_stage2_pass", "manual_stage2_retry_pass"}


def _resume_job_resolved_successfully(job: dict[str, Any]) -> bool:
    job_status = str(job.get("status") or "").strip().lower()
    return job_status == "completed" and _resume_job_final_result_successful(job)


def _generation_job_stale_after_seconds() -> int:
    return generation_job_stale_after_seconds(minimum=60)


def _find_blocking_generation_job_for_athlete(
    *,
    store: AppStore,
    athlete_id: str,
    stale_after_seconds: int,
) -> dict[str, Any] | None:
    jobs = store.list_generation_jobs_for_athlete(athlete_id, limit=25)
    for job in jobs:
        status_value = str(job.get("status") or "")
        if status_value == "queued":
            return job
        if status_value == "running" and not _is_stale_job(
            job,
            stale_after_seconds=stale_after_seconds,
        ):
            return job
    return None


def _stable_payload_signature(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _has_triage_resume_approval_markers(
    *,
    stage2_status: str | None,
    why_log: Any,
) -> bool:
    """Detect resume-approval markers regardless of source (plan row vs job final_result)."""
    if str(stage2_status or "").strip().lower() == "triage_resume_approved":
        return True
    if not isinstance(why_log, dict):
        return False
    if why_log.get("triage_regeneration_cleared") is True:
        return True
    if isinstance(why_log.get("triage_resume_approval"), dict):
        return True
    resume_override = why_log.get("injury_triage_resume_override")
    if isinstance(resume_override, dict) and resume_override.get("bypassed_blocking") is True:
        return True
    triage_original = why_log.get("injury_triage_original")
    if isinstance(triage_original, dict) and triage_original.get("triage_resume_approved") is True:
        return True
    return False


def _triage_plan_has_resume_approval(plan: dict[str, Any] | None) -> bool:
    # Once a triage-blocked plan has been approved for resume, the old
    # same-payload terminal job no longer represents the live decision —
    # the admin resume flow owns the next regeneration and the old
    # triage-blocked output must not be returned as a completed duplicate.
    if not isinstance(plan, dict):
        return False
    return _has_triage_resume_approval_markers(
        stage2_status=plan.get("stage2_status"),
        why_log=plan.get("why_log"),
    )


def _triage_job_has_resume_approval(job: dict[str, Any] | None) -> bool:
    """Resume-approval markers stored on a generation job's final_result."""
    if not isinstance(job, dict):
        return False
    final_result = job.get("final_result")
    if not isinstance(final_result, dict):
        return False
    return _has_triage_resume_approval_markers(
        stage2_status=final_result.get("stage2_status"),
        why_log=final_result.get("why_log"),
    )


def _job_final_result_triage_status(job: dict[str, Any] | None) -> str | None:
    """Return the triage status from job.final_result, or None."""
    if not isinstance(job, dict):
        return None
    final_result = job.get("final_result")
    if not isinstance(final_result, dict):
        return None
    status_value = str(final_result.get("status") or "").strip().lower()
    if status_value in _PROTECTED_TRIAGE_STATUSES:
        return status_value
    return None


def _plan_blocks_duplicate_generation(
    plan: dict[str, Any] | None,
) -> bool:
    # Duplicate prevention must only apply to plans the viewer can still open.
    # Athlete soft-delete archives the plan (hidden from athlete views) and a
    # hard-delete removes it entirely, so a stale same-payload job pointing at
    # such a plan must not block a fresh generation. Unapproved triage-blocked
    # plans still block here so the existing admin-review behaviour is kept,
    # but once a triage-blocked plan has resume approval markers, the original
    # same-payload terminal job no longer reflects the live decision — the
    # admin resume flow must drive the next regeneration instead.
    if not isinstance(plan, dict):
        return False
    if _is_archived_plan(plan):
        return False
    if _is_triage_blocked_plan(plan) and _triage_plan_has_resume_approval(plan):
        return False
    return True


def _find_existing_terminal_job_for_same_payload(
    *,
    store: AppStore,
    athlete_id: str,
    request_payload: dict[str, Any],
) -> dict[str, Any] | None:
    target_hash = _stable_payload_signature(request_payload)
    jobs = store.list_generation_jobs_for_athlete(athlete_id, limit=25)
    for job in jobs:
        job_payload = job.get("request_payload")
        if not isinstance(job_payload, dict):
            continue
        if _stable_payload_signature(job_payload) != target_hash:
            continue
        plan_id = str(job.get("plan_id") or "").strip()
        if plan_id:
            if not _plan_blocks_duplicate_generation(store.get_plan(plan_id)):
                continue
            return job
        # No plan_id: this is a new-style triage outcome that lives only on
        # the job. Block the duplicate only if the job still holds a triage
        # state and has not been approved for resume.
        if _job_final_result_triage_status(job) and not _triage_job_has_resume_approval(job):
            return job
    return None


def _request_payload_summary(payload: Any) -> GenerationRequestPayloadSummary:
    if not isinstance(payload, dict):
        return GenerationRequestPayloadSummary()
    athlete = payload.get("athlete") if isinstance(payload.get("athlete"), dict) else {}
    technical_style_value = athlete.get("technical_style")
    technical_style: list[str] = []
    if isinstance(technical_style_value, list):
        technical_style = [str(item).strip() for item in technical_style_value if str(item).strip()]
    injuries_value = payload.get("injuries")
    injuries: list[str] = []
    if isinstance(injuries_value, list):
        injuries = [str(item).strip() for item in injuries_value if str(item).strip()]
    elif isinstance(injuries_value, str) and injuries_value.strip():
        injuries = [injuries_value.strip()]
    guided_injury = payload.get("guided_injury")
    if isinstance(guided_injury, dict):
        area = str(guided_injury.get("area") or "").strip()
        severity = str(guided_injury.get("severity") or "").strip()
        guidance = ", ".join([part for part in [area, severity] if part])
        if guidance:
            injuries.append(f"guided_injury: {guidance}")
    training_availability = payload.get("training_availability")
    availability_summary = ""
    if isinstance(training_availability, list):
        availability_summary = ", ".join([str(day).strip() for day in training_availability if str(day).strip()])
    return GenerationRequestPayloadSummary(
        athlete_name=str(athlete.get("full_name") or ""),
        fight_date=str(payload.get("fight_date") or ""),
        phase=str(payload.get("phase") or payload.get("training_phase") or ""),
        fight_format=str(payload.get("rounds_format") or ""),
        fatigue_level=str(payload.get("fatigue_level") or ""),
        goals=[str(item) for item in (payload.get("key_goals") or []) if isinstance(item, str)],
        weaknesses=[str(item) for item in (payload.get("weak_areas") or []) if isinstance(item, str)],
        injuries=injuries,
        training_availability=availability_summary,
        technical_style=technical_style,
    )


def _admin_generation_job_diagnostic(job: dict[str, Any], *, stale_after_seconds: int) -> AdminGenerationJobDiagnostic:
    raw_status = str(job.get("status") or "queued").strip().lower()
    normalized_status = "completed" if raw_status == "ready" else raw_status
    if normalized_status not in {"queued", "running", "completed", "review_required", "failed"}:
        normalized_status = "queued"
    is_stale = normalized_status == "running" and _is_stale_job(job, stale_after_seconds=stale_after_seconds)
    stale_reason = "Heartbeat timed out while job is still running." if is_stale else None
    error_message = str(job.get("error") or "") or None
    client_request_id = str(job.get("client_request_id") or "")

    retry_of = None
    if client_request_id.startswith("retry_"):
        content = client_request_id[6:]
        if "_" in content:
            retry_of = content.rsplit("_", 1)[0]

    # Surface protected-triage signals on diagnostic rows so admin UI can
    # show an explicit "Approve & Resume" CTA for new-style triage outcomes
    # that have no plan_id.
    triage_status = _job_final_result_triage_status(job)
    stage2_status: str | None = None
    requires_admin_resume = False
    final_result = job.get("final_result") if isinstance(job.get("final_result"), dict) else {}
    if final_result:
        stage2_raw = str(final_result.get("stage2_status") or "").strip().lower()
        if stage2_raw:
            stage2_status = stage2_raw
    if triage_status and not _triage_job_has_resume_approval(job):
        requires_admin_resume = True
        stage2_status = stage2_status or triage_status
    profile = job.get("profiles") if isinstance(job.get("profiles"), dict) else {}

    return AdminGenerationJobDiagnostic(
        job_id=str(job.get("id") or ""),
        athlete_id=str(job.get("athlete_id") or ""),
        athlete_email=str(profile.get("email") or ""),
        athlete_full_name=str(profile.get("full_name") or ""),
        intake_id=str(job.get("intake_id") or "") or None,
        status=normalized_status,
        source=str(job.get("source") or ""),
        created_at=str(job.get("created_at") or ""),
        started_at=job.get("started_at"),
        heartbeat_at=job.get("heartbeat_at"),
        completed_at=job.get("completed_at"),
        client_request_id=client_request_id,
        retry_of=retry_of,
        error=error_message,
        stale_reason=stale_reason,
        plan_id=job.get("plan_id"),
        can_retry=str(job.get("status") or "") == "failed",
        stage2_status=stage2_status,
        requires_admin_resume=requires_admin_resume,
        is_stale=is_stale,
        profile_unavailable=bool(job.get("profile_enrichment_failed")),
        warnings=_job_warnings(job),
        request_payload_summary=_request_payload_summary(job.get("request_payload")),
    )


def _can_approve_and_resume_triage(triage_mode: str) -> bool:
    return triage_mode in {"needs_review", "restricted_rehab_only"}


def _has_existing_triage_resume_approval(plan_row: dict[str, Any]) -> bool:
    if str(plan_row.get("stage2_status") or "").strip().lower() == "triage_resume_approved":
        return True
    why_log = plan_row.get("why_log")
    if not isinstance(why_log, dict):
        return False
    return bool(why_log.get("triage_regeneration_cleared"))
