from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from postgrest.exceptions import APIError as PostgrestAPIError
from pydantic import ValidationError

from fightcamp.logging_utils import bind_log_context, clear_log_context, configure_logging
from fightcamp.plan_pipeline import prime_plan_banks
from fightcamp.sparring_advisories import build_plan_advisories
from fightcamp.stage2_pipeline import build_stage2_retry, review_stage2_output
from fightcamp.weekly_schedule_view import extract_weekly_schedule

from .auth import AuthService, AuthenticatedUser, SupabaseAuthService, is_auth_api_error
from .environment import is_production_environment
from .generation_config import generation_job_stale_after_seconds
from .models import (
    ApproveAndResumeGenerationRequest,
    AdminGenerationJobDiagnostic,
    AdminAthleteRecord,
    AdminLatestIntakeUpdateRequest,
    AdminPlanOutputs,
    AdminPlanSummary,
    GenerationJobResponse,
    GenerationRequestPayloadSummary,
    ManualStage2SubmissionRequest,
    MeResponse,
    NutritionWorkspaceState,
    NutritionWorkspaceUpdateRequest,
    OnboardingDraftSaveRequest,
    OnboardingDraftSaveResponse,
    PlanDetail,
    PlanRenameRequest,
    PlanOutputs,
    PlanSafetyState,
    PlanRequest,
    PlanSummary,
    ProfileRecord,
    ProfileUpdateRequest,
    USERNAME_CHANGE_WINDOW_DAYS,
    USERNAME_MAX_CHANGES_PER_WINDOW,
    UsernameChangeRequest,
    UsernameRateLimitInfo,
    WeeklySchedule,
)
from .nutrition_workspace import (
    build_nutrition_workspace,
    merge_workspace_into_payload,
    normalize_nutrition_update_request,
)
from .performance_focus import validate_performance_focus_selections
from .generation_runtime import (
    _OPENAI_QUOTA_ADMIN_ERROR,
    _OPENAI_QUOTA_ATHLETE_ERROR,
    default_planner as runtime_default_planner,
    is_in_process_generation_enabled,
    is_stale_job as runtime_is_stale_job,
    schedule_generation_job_if_needed,
)
from .stage2_automation import (
    Stage2Automator,
    build_default_stage2_automator,
)
from .store import AppStore, SupabaseAppStore, is_startup_stale_generation_job

Planner = Callable[[dict[str, Any]], dict[str, Any]]
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
LOCAL_HOST_NAMES = ("localhost", "127.0.0.1", "::1")
_CLIENT_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROTECTED_TRIAGE_STATUSES = frozenset({"triage_blocked", "needs_review", "restricted_rehab_only", "medical_hold"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    if normalized_status in {"completed", "review_required"} and not plan_id:
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
            if athlete_id:
                latest_plan = store.get_latest_plan(athlete_id)
                latest_id = str(latest_plan.get("id") or "").strip() if latest_plan else ""
                latest_intake = str(latest_plan.get("intake_id") or "").strip() if latest_plan else ""
                latest_status = str(latest_plan.get("status") or "").strip().lower() if latest_plan else ""
                if latest_id and latest_status != "archived" and (not intake_id or latest_intake == intake_id):
                    plan_id = latest_id
        resolved_latest_plan_id = resolved_latest_plan_id or plan_id
    updated_at = job.get("updated_at") or job.get("created_at") or _utc_now_iso()
    error = str(job["error"]) if job.get("error") else None
    if viewer_role != "admin" and error == _OPENAI_QUOTA_ADMIN_ERROR:
        error = _OPENAI_QUOTA_ATHLETE_ERROR
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
        message=status_messages.get(normalized_status, "Generation queued and will be processed shortly."),
        progress_milestones=_normalize_progress_milestones(job.get("progress_milestones")),
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


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _find_existing_terminal_job_for_same_payload(
    *,
    store: AppStore,
    athlete_id: str,
    request_payload: dict[str, Any],
) -> dict[str, Any] | None:
    target_hash = _stable_payload_hash(request_payload)
    jobs = store.list_generation_jobs_for_athlete(athlete_id, limit=25)
    for job in jobs:
        job_payload = job.get("request_payload")
        if not isinstance(job_payload, dict):
            continue
        if _stable_payload_hash(job_payload) != target_hash:
            continue
        status_value = str(job.get("status") or "").strip().lower()
        has_plan = bool(str(job.get("plan_id") or "").strip())
        if status_value in {"completed", "review_required"}:
            return job
        if has_plan:
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

    return AdminGenerationJobDiagnostic(
        job_id=str(job.get("id") or ""),
        athlete_id=str(job.get("athlete_id") or ""),
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
        is_stale=is_stale,
        request_payload_summary=_request_payload_summary(job.get("request_payload")),
    )


def _build_me_response(profile: ProfileRecord, store: AppStore) -> MeResponse:
    latest_intake = store.get_latest_intake(profile.athlete_id)
    plans = _visible_plans_for_athlete(store.list_user_plans(profile.athlete_id))
    latest_plan = _map_plan_summary(plans[0]) if plans else None
    return MeResponse(
        profile=profile,
        latest_intake=latest_intake.get("intake") if latest_intake else None,
        latest_plan=latest_plan,
        plan_count=len(plans),
        username_rate_limit=_username_rate_limit_info(profile.username_change_history),
    )


def _validate_session_type_consistency(workspace: NutritionWorkspaceUpdateRequest) -> None:
    training_days = {day.strip().lower() for day in workspace.shared_camp_context.training_availability if str(day).strip()}
    hard_days = {day.strip().lower() for day in workspace.shared_camp_context.hard_sparring_days if str(day).strip()}
    support_days = {day.strip().lower() for day in workspace.shared_camp_context.support_work_days if str(day).strip()}

    for day, session_type in workspace.shared_camp_context.session_types_by_day.items():
        normalized_day = str(day or "").strip().lower()
        if session_type == "hard_spar" and normalized_day not in hard_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"session_types_by_day.{day} must also be included in hard_sparring_days",
            )
        if session_type == "technical" and normalized_day not in support_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"session_types_by_day.{day} must also be included in support_work_days",
            )
        if session_type != "off" and normalized_day not in training_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"session_types_by_day.{day} must also be included in training_availability",
            )


def _validate_schedule_consistency(workspace: NutritionWorkspaceUpdateRequest) -> None:
    shared = workspace.shared_camp_context
    training_days = [day for day in shared.training_availability if str(day).strip()]
    normalized_training_days = {day.strip().lower() for day in training_days}
    if shared.weekly_training_frequency and len(training_days) and shared.weekly_training_frequency > len(training_days):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="weekly_training_frequency cannot exceed selected training_availability days",
        )

    invalid_hard_days = [day for day in shared.hard_sparring_days if str(day).strip().lower() not in normalized_training_days]
    if invalid_hard_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"hard_sparring_days must be included in training_availability: {', '.join(invalid_hard_days)}",
        )

    invalid_support_days = [day for day in shared.support_work_days if str(day).strip().lower() not in normalized_training_days]
    if invalid_support_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"support_work_days must be included in training_availability: {', '.join(invalid_support_days)}",
        )

    overlap = sorted(
        {
            hard_day
            for hard_day in shared.hard_sparring_days
            if str(hard_day).strip().lower() in {day.strip().lower() for day in shared.support_work_days if str(day).strip()}
        }
    )
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A day cannot be both hard_sparring and support_work: {', '.join(overlap)}",
        )


def _update_profile_with_nutrition_fallback(
    *,
    store: AppStore,
    athlete_id: str,
    update: ProfileUpdateRequest,
) -> ProfileRecord:
    try:
        return _map_profile_row(store.update_profile(athlete_id, update))
    except HTTPException as exc:
        should_retry_without_profile = (
            update.nutrition_profile is not None
            and exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        if not should_retry_without_profile:
            raise
        logger.warning(
            "[nutrition] retrying profile update without nutrition_profile athlete_id=%s status=%s detail=%s",
            athlete_id,
            exc.status_code,
            exc.detail,
        )
        fallback_update = update.model_copy(update={"nutrition_profile": None})
        return _map_profile_row(store.update_profile(athlete_id, fallback_update))


def _cors_origins() -> list[str]:
    value = os.getenv(
        "APP_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    )
    return [_normalize_origin(origin) for origin in value.split(",") if origin.strip()]


def _normalize_origin(origin: str) -> str:
    normalized = origin.strip()
    if not normalized:
        return ""
    if "://" not in normalized:
        host = normalized.split("/", 1)[0].lower()
        if host.startswith("[") and "]" in host:
            host_name = host[1:].split("]", 1)[0]
        else:
            host_name = host.split(":", 1)[0]
        scheme = "http" if host_name in LOCAL_HOST_NAMES else "https"
        normalized = f"{scheme}://{normalized}"
    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"APP_CORS_ORIGINS entries must be full origins. Received: {origin!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def _cors_origin_regex() -> str | None:
    value = os.getenv("APP_CORS_ORIGIN_REGEX", "").strip()
    return value or None


_UNSAFE_CORS_REGEX_PATTERNS = frozenset({".*", "^.*$", ".+", "^.+$", "^.*", ".*$", "^.+", ".+$"})
_UNSAFE_CORS_REGEX_SCHEME_PATTERNS = frozenset({
    "https://.*",
    "^https://.*$",
    "https://.+",
    "^https://.+$",
    "http://.*",
    "^http://.*$",
    "http://.+",
    "^http://.+$",
})


def _is_broad_cors_regex(regex: str) -> bool:
    normalized = regex.strip()
    if not normalized:
        return False
    if normalized in _UNSAFE_CORS_REGEX_PATTERNS:
        return True
    if normalized in _UNSAFE_CORS_REGEX_SCHEME_PATTERNS:
        return True
    return False


def _validate_production_cors_config(origins: list[str], regex: str | None) -> None:
    if not is_production_environment():
        return

    violations: list[str] = []

    if not origins and not regex:
        violations.append(
            "APP_CORS_ORIGINS must list at least one origin "
            "(or APP_CORS_ORIGIN_REGEX must be set) in production"
        )

    for origin in origins:
        if origin == "*":
            violations.append("APP_CORS_ORIGINS cannot contain '*' in production")
            continue
        parsed = urlsplit(origin)
        host = (parsed.hostname or "").lower()
        netloc = (parsed.netloc or "").lower()
        if not host or "*" in netloc:
            violations.append(
                f"APP_CORS_ORIGINS cannot contain '*' wildcards in production: {origin!r}"
            )
            continue
        if host in LOCAL_HOST_NAMES:
            violations.append(
                f"APP_CORS_ORIGINS cannot contain localhost origins in production: {origin!r}"
            )

    if regex is not None and _is_broad_cors_regex(regex):
        violations.append(
            f"APP_CORS_ORIGIN_REGEX is too broad for production: {regex!r}"
        )

    if not violations:
        return

    allow_unsafe = os.getenv("APP_ALLOW_UNSAFE_PRODUCTION_CORS_BOOT", "").strip() == "1"
    if allow_unsafe:
        for violation in violations:
            logger.critical("[cors] UNSAFE_PRODUCTION_CORS_OVERRIDE_ACTIVE: %s", violation)
        return

    raise RuntimeError(
        "Unsafe production CORS configuration. "
        "Refusing to boot unless APP_ALLOW_UNSAFE_PRODUCTION_CORS_BOOT=1 is set. "
        + "; ".join(violations)
    )


def _plan_generate_rate_limit_requests() -> int:
    raw_value = os.getenv("APP_PLAN_GENERATE_RATE_LIMIT", "5").strip()
    try:
        return max(0, int(raw_value))
    except ValueError:
        logger.warning("[rate-limit] invalid APP_PLAN_GENERATE_RATE_LIMIT=%r; falling back to 5", raw_value)
        return 5


def _plan_generate_rate_limit_window_seconds() -> float:
    raw_value = os.getenv("APP_PLAN_GENERATE_RATE_LIMIT_WINDOW_SECONDS", "60").strip()
    try:
        return max(1.0, float(raw_value))
    except ValueError:
        logger.warning(
            "[rate-limit] invalid APP_PLAN_GENERATE_RATE_LIMIT_WINDOW_SECONDS=%r; falling back to 60",
            raw_value,
        )
        return 60.0


def _plan_generate_daily_limit_per_user() -> int:
    raw_value = os.getenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "5").strip()
    try:
        return max(0, int(raw_value))
    except ValueError:
        logger.warning(
            "[rate-limit] invalid APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER=%r; falling back to 5",
            raw_value,
        )
        return 5


def _daily_generation_cap_exempt_emails() -> frozenset[str]:
    return frozenset(
        email.strip().lower()
        for email in os.getenv("APP_DAILY_GENERATION_CAP_EXEMPT_EMAILS", "").split(",")
        if email.strip()
    )


def _is_exempt_from_daily_generation_cap(email: str) -> bool:
    return email.strip().lower() in _daily_generation_cap_exempt_emails()


def _default_planner(
    payload: dict[str, Any],
    *,
    progress_callback=None,
) -> dict[str, Any]:
    return runtime_default_planner(payload, progress_callback=progress_callback)


def _health_payload(*, mode_label: str) -> dict[str, str | bool]:
    return {
        "ok": True,
        "app": "unlxck-fight-camp-api",
        "mode": mode_label,
    }


def _decode_structured_text(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            return {"raw": stripped}
        return decoded if isinstance(decoded, dict) else {"raw": decoded}
    return {"raw": value}


def _map_profile_row(row: dict[str, Any]) -> ProfileRecord:
    raw_username = row.get("username")
    history_raw = row.get("username_change_history") or []
    username_history: list[str] = [str(entry) for entry in history_raw if entry]
    return ProfileRecord(
        athlete_id=str(row["id"]),
        email=str(row.get("email") or ""),
        username=str(raw_username) if raw_username else None,
        username_change_history=username_history,
        role=str(row.get("role") or "athlete"),
        full_name=str(row.get("full_name") or ""),
        technical_style=list(row.get("technical_style") or []),
        tactical_style=list(row.get("tactical_style") or []),
        stance=str(row.get("stance") or ""),
        professional_status=str(row.get("professional_status") or ""),
        record=str(row.get("record_summary") or ""),
        athlete_timezone=str(row.get("athlete_timezone") or ""),
        athlete_locale=str(row.get("athlete_locale") or ""),
        appearance_mode=str(row.get("appearance_mode") or "dark"),
        onboarding_draft=row.get("onboarding_draft"),
        avatar_url=row.get("avatar_url") or None,
        nutrition_profile=row.get("nutrition_profile") or {},
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _username_rate_limit_info(history: list[str]) -> UsernameRateLimitInfo:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=USERNAME_CHANGE_WINDOW_DAYS)
    recent: list[datetime] = []
    for entry in history:
        try:
            parsed = datetime.fromisoformat(str(entry).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed >= cutoff:
            recent.append(parsed)
    remaining = max(0, USERNAME_MAX_CHANGES_PER_WINDOW - len(recent))
    next_available_at: str | None = None
    if remaining == 0 and recent:
        next_available_at = (min(recent) + timedelta(days=USERNAME_CHANGE_WINDOW_DAYS)).isoformat()
    return UsernameRateLimitInfo(
        remaining=remaining,
        next_available_at=next_available_at,
    )


def _map_plan_summary(row: dict[str, Any]) -> PlanSummary:
    raw_status = str(row.get("status") or "generated")
    normalized_status = raw_status
    if raw_status == "review_required":
        report = row.get("stage2_validator_report") if isinstance(row.get("stage2_validator_report"), dict) else {}
        report_exists = bool(report)
        if not report_exists:
            normalized_status = "held_for_review"
        else:
            has_errors = bool(report.get("errors"))
            has_blocking = bool(report.get("blocking_warnings"))
            if not has_blocking:
                warnings = list(report.get("warnings") or [])
                has_blocking = any(bool(w.get("blocking")) for w in warnings if isinstance(w, dict))
            normalized_status = "held_for_review" if has_errors or has_blocking else "publishable_with_flags"
    return PlanSummary(
        plan_id=str(row["id"]),
        plan_name=(str(row["plan_name"]).strip() if row.get("plan_name") is not None else None) or None,
        athlete_id=str(row["athlete_id"]),
        full_name=str(row.get("full_name") or ""),
        fight_date=str(row.get("fight_date") or ""),
        technical_style=list(row.get("technical_style") or []),
        created_at=str(row.get("created_at") or ""),
        status=normalized_status,
        pdf_url=row.get("pdf_url"),
    )


def _is_archived_plan(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    return str(row.get("status") or "").strip().lower() == "archived"


def _is_triage_blocked_plan(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    return str(row.get("status") or "").strip().lower() == "triage_blocked"


def _visible_plans_for_athlete(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Triage-blocked outcomes are screening decisions, not plans — they must
    # not surface in the athlete's archive or "latest plan" snapshot. Admin
    # endpoints bypass this filter so the ops team can still review and
    # approve-and-resume blocked attempts.
    return [
        row
        for row in rows
        if not _is_archived_plan(row) and not _is_triage_blocked_plan(row)
    ]


def _admin_draft_text(row: dict[str, Any]) -> str:
    return str(row.get("draft_plan_text") or row.get("plan_text") or "")


def _admin_final_text(row: dict[str, Any]) -> str:
    return str(row.get("final_plan_text") or row.get("plan_text") or "")


def _map_plan_safety_state(row: dict[str, Any]) -> PlanSafetyState:
    triage = {}
    why_log = row.get("why_log")
    if isinstance(why_log, dict):
        triage = why_log.get("injury_triage") or {}
    if not isinstance(triage, dict):
        triage = {}

    mode = str(triage.get("mode") or "")
    triage_blocked = str(row.get("status") or "").strip().lower() == "triage_blocked"
    stage2_was_skipped = bool(triage.get("should_block_stage2")) or triage_blocked
    if mode == "medical_hold":
        return PlanSafetyState(
            state="medical_hold",
            status_chip="MEDICAL HOLD",
            header="Medical hold: no training plan generated",
            subtext=(
                "Urgent neurological or medical red-flag signals were detected. "
                "Planning was intentionally blocked before normal generation."
            ),
            stage2_skipped=stage2_was_skipped,
            clinician_clearance_required=bool(triage.get("clinician_clearance_required", True)),
            matched_high_risk_categories=list(triage.get("matched_high_risk_categories") or []),
            red_flags=list(triage.get("red_flags") or []),
            sparring_risk_band=triage.get("sparring_risk_band"),
            next_steps=[
                "Seek appropriate medical review before training guidance.",
                "Update the intake after clearance.",
                "Regenerate only when medically cleared.",
            ],
        )
    if mode == "restricted_rehab_only":
        return PlanSafetyState(
            state="restricted_rehab_only",
            status_chip="RESTRICTED REHAB ONLY",
            header="Planning paused: clinician clearance required",
            subtext=(
                "Serious structural injury signals were detected. "
                "Normal fight-camp generation is paused to avoid unsafe loading recommendations."
            ),
            stage2_skipped=stage2_was_skipped,
            clinician_clearance_required=bool(triage.get("clinician_clearance_required", True)),
            matched_high_risk_categories=list(triage.get("matched_high_risk_categories") or []),
            red_flags=list(triage.get("red_flags") or []),
            sparring_risk_band=triage.get("sparring_risk_band"),
            next_steps=[
                "Review injury details and current restrictions.",
                "Update the intake after clinician clearance.",
                "Regenerate normal planning only when safe.",
            ],
        )
    if mode == "needs_review":
        return PlanSafetyState(
            state="needs_review",
            status_chip="NEEDS REVIEW",
            header="Safety review required before planning",
            subtext=(
                "Guided injury severity/trend combinations triggered a conservative safety gate. "
                "Automatic planning is paused pending coach/admin review."
            ),
            stage2_skipped=stage2_was_skipped,
            clinician_clearance_required=bool(triage.get("clinician_clearance_required", False)),
            matched_high_risk_categories=list(triage.get("matched_high_risk_categories") or []),
            red_flags=list(triage.get("red_flags") or []),
            sparring_risk_band=triage.get("sparring_risk_band"),
            next_steps=[
                "Review guided injury severity/trend details.",
                "Clarify diagnosis progression and restrictions.",
                "Approve before rerunning full planning.",
            ],
        )

    return PlanSafetyState(
        state="plan_ready",
        status_chip="PLAN READY",
        header="Plan ready",
        subtext="Normal planning completed.",
        stage2_skipped=False,
        clinician_clearance_required=False,
        matched_high_risk_categories=[],
        red_flags=[],
        sparring_risk_band=None,
        next_steps=[],
    )


_ALLOWED_PLAN_SOURCES: frozenset[str] = frozenset({"quick_build", "self_serve"})


def _lookup_plan_source(store: AppStore, plan_id: str) -> str | None:
    job = store.get_generation_job_by_plan_id(plan_id)
    if not isinstance(job, dict):
        return None
    raw = job.get("source")
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if value in _ALLOWED_PLAN_SOURCES else None


def _map_plan_detail(
    row: dict[str, Any],
    *,
    include_admin: bool,
    plan_source: str | None = None,
) -> PlanDetail:
    summary = _map_plan_summary(row)
    planning_brief = _decode_structured_text(row.get("planning_brief"))
    raw_stage2_payload = row.get("stage2_payload")
    fallback_parsing_metadata = (
        raw_stage2_payload.get("input_parsing_metadata")
        if isinstance(raw_stage2_payload, dict)
        else {}
    )
    parsing_metadata = row.get("parsing_metadata") or fallback_parsing_metadata or {}
    display_plan_text = str(row.get("plan_text") or "")
    is_legacy_review_required = str(row.get("status") or "").strip().lower() == "review_required"
    if (
        not display_plan_text
        and is_legacy_review_required
        and summary.status == "publishable_with_flags"
    ):
        display_plan_text = str(row.get("final_plan_text") or "")
    return PlanDetail(
        **summary.model_dump(mode="json"),
        outputs=PlanOutputs(
            plan_text=display_plan_text,
            pdf_url=row.get("pdf_url"),
        ),
        safety_state=_map_plan_safety_state(row),
        advisories=build_plan_advisories(planning_brief=planning_brief),
        plan_source=plan_source,
        admin_outputs=(
            AdminPlanOutputs(
                coach_notes=str(row.get("coach_notes") or ""),
                why_log=row.get("why_log") or {},
                planning_brief=planning_brief,
                stage2_payload=raw_stage2_payload,
                parsing_metadata=parsing_metadata if isinstance(parsing_metadata, dict) else {},
                stage2_handoff_text=str(row.get("stage2_handoff_text") or ""),
                draft_plan_text=_admin_draft_text(row),
                final_plan_text=_admin_final_text(row),
                stage2_retry_text=str(row.get("stage2_retry_text") or ""),
                stage2_validator_report=row.get("stage2_validator_report") or {},
                stage2_status=str(row.get("stage2_status") or "legacy"),
                stage2_attempt_count=int(row.get("stage2_attempt_count") or 0),
            )
            if include_admin
            else None
        ),
    )


def _map_weekly_schedule(row: dict[str, Any], *, week_index: int) -> WeeklySchedule:
    planning_brief = _decode_structured_text(row.get("planning_brief"))
    schedule = extract_weekly_schedule(
        planning_brief,
        week_index=week_index,
        fight_date=row.get("fight_date"),
    )
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="weekly schedule not found")
    return WeeklySchedule(plan_id=str(row["id"]), **schedule)


def _map_admin_plan_summary(row: dict[str, Any]) -> AdminPlanSummary:
    profile = row.get("profiles") or {}
    summary = _map_plan_summary(row)
    return AdminPlanSummary(
        **summary.model_dump(mode="json"),
        athlete_email=str(profile.get("email") or ""),
    )


def _map_admin_athlete(row: dict[str, Any], latest_intake: dict[str, Any] | None = None) -> AdminAthleteRecord:
    onboarding_draft = row.get("onboarding_draft")
    return AdminAthleteRecord(
        athlete_id=str(row["id"]),
        email=str(row.get("email") or ""),
        role=str(row.get("role") or "athlete"),
        full_name=str(row.get("full_name") or ""),
        technical_style=list(row.get("technical_style") or []),
        tactical_style=list(row.get("tactical_style") or []),
        stance=str(row.get("stance") or ""),
        professional_status=str(row.get("professional_status") or ""),
        record=str(row.get("record") or row.get("record_summary") or ""),
        athlete_timezone=str(row.get("athlete_timezone") or ""),
        athlete_locale=str(row.get("athlete_locale") or ""),
        appearance_mode=str(row.get("appearance_mode") or "dark"),
        onboarding_draft=onboarding_draft if isinstance(onboarding_draft, dict) else None,
        latest_intake=latest_intake.get("intake") if isinstance(latest_intake, dict) else None,
        nutrition_profile=row.get("nutrition_profile") or {},
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        plan_count=int(row.get("plan_count") or 0),
        latest_plan_created_at=row.get("latest_plan_created_at"),
    )


def _manual_stage2_result(plan_row: dict[str, Any], final_plan_text: str) -> dict[str, Any]:
    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    review = review_stage2_output(planning_brief=planning_brief, final_plan_text=final_plan_text)
    next_attempt_count = int(plan_row.get("stage2_attempt_count") or 0) + 1
    had_retry_prompt = bool(str(plan_row.get("stage2_retry_text") or "").strip())

    if review["status"] == "PASS":
        return {
            "status": "ready",
            "plan_text": final_plan_text,
            "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
            "final_plan_text": final_plan_text,
            "pdf_url": None,
            "stage2_retry_text": "",
            "stage2_validator_report": review["validator_report"],
            "stage2_status": "manual_stage2_retry_pass" if had_retry_prompt else "manual_stage2_pass",
            "stage2_attempt_count": next_attempt_count,
        }

    retry = build_stage2_retry(
        stage1_result={"planning_brief": planning_brief},
        final_plan_text=final_plan_text,
        validator_report=review["validator_report"],
    )
    return {
        "status": "review_required",
        "plan_text": "",
        "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
        "final_plan_text": final_plan_text,
        "pdf_url": None,
        "stage2_retry_text": str(retry.get("repair_prompt") or ""),
        "stage2_validator_report": review["validator_report"],
        "stage2_status": "manual_stage2_retry_required",
        "stage2_attempt_count": next_attempt_count,
    }


def _admin_approved_result(plan_row: dict[str, Any]) -> dict[str, Any]:
    approved_text = str(plan_row.get("final_plan_text") or plan_row.get("draft_plan_text") or plan_row.get("plan_text") or "").strip()
    if not approved_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No saved Stage 2 or draft text is available to approve.",
        )
    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    validator_report = plan_row.get("stage2_validator_report") or {}
    if planning_brief:
        review = review_stage2_output(planning_brief=planning_brief, final_plan_text=approved_text)
        validator_report = review["validator_report"]
    return {
        "status": "ready",
        "plan_text": approved_text,
        "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
        "final_plan_text": approved_text,
        "pdf_url": None,
        "stage2_retry_text": str(plan_row.get("stage2_retry_text") or ""),
        "stage2_validator_report": validator_report,
        "stage2_status": "admin_review_approved",
        "stage2_attempt_count": int(plan_row.get("stage2_attempt_count") or 0),
    }


def _admin_rejected_result(plan_row: dict[str, Any]) -> dict[str, Any]:
    held_text = str(plan_row.get("final_plan_text") or plan_row.get("draft_plan_text") or plan_row.get("plan_text") or "").strip()
    if not held_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No saved Stage 2 or draft text is available to keep in review.",
        )
    return {
        "status": "review_required",
        "plan_text": "",
        "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
        "final_plan_text": held_text,
        "pdf_url": None,
        "stage2_retry_text": str(plan_row.get("stage2_retry_text") or ""),
        "stage2_validator_report": plan_row.get("stage2_validator_report") or {},
        "stage2_status": "admin_review_rejected",
        "stage2_attempt_count": int(plan_row.get("stage2_attempt_count") or 0),
    }


def _admin_archived_result(plan_row: dict[str, Any]) -> dict[str, Any]:
    archived_text = str(plan_row.get("final_plan_text") or plan_row.get("draft_plan_text") or plan_row.get("plan_text") or "").strip()
    return {
        "status": "archived",
        "plan_text": "",
        "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
        "final_plan_text": archived_text,
        "pdf_url": None,
        "stage2_retry_text": str(plan_row.get("stage2_retry_text") or ""),
        "stage2_validator_report": plan_row.get("stage2_validator_report") or {},
        "stage2_status": "admin_archived",
        "stage2_attempt_count": int(plan_row.get("stage2_attempt_count") or 0),
    }


def _can_approve_and_resume_triage(triage_mode: str) -> bool:
    return triage_mode in {"needs_review", "restricted_rehab_only"}


def _has_existing_triage_resume_approval(plan_row: dict[str, Any]) -> bool:
    if str(plan_row.get("stage2_status") or "").strip().lower() == "triage_resume_approved":
        return True
    why_log = plan_row.get("why_log")
    if not isinstance(why_log, dict):
        return False
    return bool(why_log.get("triage_regeneration_cleared"))



def create_app(
    *,
    store: AppStore,
    auth_service: AuthService,
    planner: Planner = _default_planner,
    stage2_automator: Stage2Automator | None = None,
    mode_label: str = "supabase-authenticated",
    enable_in_process_generation: bool = True,
) -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def _app_lifespan(_: FastAPI):
        await asyncio.to_thread(prime_plan_banks, logger=logger)
        yield

    app = FastAPI(
        title="UNLXCK Fight Camp API",
        version="0.2.0",
        description="Authenticated athlete-first application API around the fight camp planner.",
        lifespan=_app_lifespan,
    )
    app.state.store = store
    app.state.auth_service = auth_service
    app.state.planner = planner
    app.state.stage2_automator = stage2_automator or build_default_stage2_automator()
    app.state.mode_label = mode_label
    app.state.enable_in_process_generation = enable_in_process_generation
    app.state.active_generation_tasks = set()
    cors_origins = _cors_origins()
    cors_regex = _cors_origin_regex()
    _validate_production_cors_config(cors_origins, cors_regex)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=cors_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        started = time.perf_counter()
        bind_log_context(request_id=request_id, method=request.method, path=request.url.path)

        logger.info(
            "[http] request:start request_id=%s method=%s path=%s has_query=%s client=%s",
            request_id,
            request.method,
            request.url.path,
            bool(request.url.query),
            request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "[http] request:complete request_id=%s method=%s path=%s status=%s duration_ms=%s",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        except HTTPException as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.warning(
                "[http] request:http_exception request_id=%s method=%s path=%s status=%s duration_ms=%s detail=%r",
                request_id,
                request.method,
                request.url.path,
                exc.status_code,
                duration_ms,
                exc.detail,
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "detail": exc.detail,
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "[http] request:exception request_id=%s method=%s path=%s duration_ms=%s",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )
        finally:
            clear_log_context()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        content: dict[str, Any] = {"detail": exc.detail}
        if request_id:
            content["request_id"] = request_id
        headers = {"X-Request-ID": request_id} if request_id else None
        return JSONResponse(status_code=exc.status_code, content=content, headers=headers)

    def get_store(request: Request) -> AppStore:
        return request.app.state.store

    def get_auth_service(request: Request) -> AuthService:
        return request.app.state.auth_service

    def get_planner(request: Request) -> Planner:
        return request.app.state.planner

    def get_stage2_automator(request: Request) -> Stage2Automator:
        return request.app.state.stage2_automator

    def get_active_generation_tasks(request: Request) -> set[str]:
        return request.app.state.active_generation_tasks

    def get_enable_in_process_generation(request: Request) -> bool:
        return bool(request.app.state.enable_in_process_generation)

    def require_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
        auth: AuthService = Depends(get_auth_service),
    ) -> AuthenticatedUser:
        if credentials is None or credentials.scheme.lower() != "bearer":
            logger.warning("[auth] missing_or_invalid_bearer_token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            )
        try:
            user = auth.get_user_from_token(credentials.credentials)
            logger.info("[auth] token_resolved user_id=%s email=%s", user.user_id, user.email)
            return user
        except HTTPException as exc:
            logger.warning("[auth] token_resolution_http_error status=%s", exc.status_code)
            raise
        except Exception as exc:
            if is_auth_api_error(exc):
                logger.warning(
                    "[auth] token_resolution_invalid_token error_class=%s error=%s",
                    exc.__class__.__module__ + "." + exc.__class__.__name__,
                    exc,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid authentication token",
                ) from exc
            logger.exception("[auth] token_resolution_failed")
            raise

    def require_profile(
        user: AuthenticatedUser = Depends(require_user),
        store: AppStore = Depends(get_store),
    ) -> ProfileRecord:
        try:
            profile = _map_profile_row(store.ensure_profile(user))
            # UNLXCK_ADMIN_EMAILS is the authoritative source for admin access.
            # Sync the request-scoped role to the current allowlist so downstream
            # checks (`profile.role == "admin"`) cannot drift if the DB role is
            # stale after an env allowlist change.
            env_is_admin = store.is_admin_email(profile.email)
            if env_is_admin and profile.role != "admin":
                profile = profile.model_copy(update={"role": "admin"})
            elif not env_is_admin and profile.role == "admin":
                profile = profile.model_copy(update={"role": "athlete"})
            logger.info("[auth] profile_resolved athlete_id=%s role=%s", profile.athlete_id, profile.role)
            return profile
        except HTTPException as exc:
            logger.warning(
                "[auth] profile_resolution_http_error user_id=%s email=%s status_code=%s detail=%s",
                user.user_id,
                user.email,
                exc.status_code,
                exc.detail,
            )
            raise
        except Exception:
            logger.exception("[auth] profile_resolution_failed user_id=%s email=%s", user.user_id, user.email)
            raise

    def require_admin(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> ProfileRecord:
        # Defense in depth: re-check the env allowlist directly so admin routes
        # never depend on the stored DB role even if the require_profile sync
        # is bypassed.
        if not store.is_admin_email(profile.email):
            logger.warning(
                "[auth] admin_access_denied athlete_id=%s role=%s email_in_allowlist=False",
                profile.athlete_id,
                profile.role,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return profile

    def require_plan_row(
        plan_id: str,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> dict[str, Any]:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        if profile.role != "admin" and str(plan_row["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        if profile.role != "admin" and _is_archived_plan(plan_row):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        return plan_row

    @app.get("/", include_in_schema=False)
    def root(request: Request) -> dict[str, str | bool]:
        return _health_payload(mode_label=str(request.app.state.mode_label))

    @app.head("/", include_in_schema=False)
    def root_head() -> None:
        return None

    @app.get("/health")
    def health(request: Request) -> dict[str, str | bool]:
        return _health_payload(mode_label=str(request.app.state.mode_label))

    @app.get("/api/me", response_model=MeResponse)
    def get_me(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        return _build_me_response(profile, store)

    @app.put("/api/me", response_model=MeResponse)
    def update_me(
        update: ProfileUpdateRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        updated = _map_profile_row(store.update_profile(profile.athlete_id, update))
        return _build_me_response(updated, store)

    @app.post("/api/me/username", response_model=MeResponse)
    def change_username_endpoint(
        update: UsernameChangeRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        updated = _map_profile_row(store.change_username(profile.athlete_id, update.username))
        return _build_me_response(updated, store)

    @app.patch("/api/onboarding/draft", response_model=OnboardingDraftSaveResponse)
    def save_onboarding_draft(
        update: OnboardingDraftSaveRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> OnboardingDraftSaveResponse:
        update_data = update.model_dump(exclude_unset=True)
        updated = _map_profile_row(
            store.update_profile(
                profile.athlete_id,
                ProfileUpdateRequest(**update_data),
            )
        )
        return OnboardingDraftSaveResponse(updated_at=updated.updated_at)

    @app.get("/api/nutrition/current", response_model=NutritionWorkspaceState)
    def get_nutrition_current(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> NutritionWorkspaceState:
        latest_intake = store.get_latest_intake(profile.athlete_id)
        return build_nutrition_workspace(profile=profile, latest_intake_row=latest_intake)

    @app.put("/api/nutrition/current", response_model=NutritionWorkspaceState)
    def update_nutrition_current(
        update: NutritionWorkspaceUpdateRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> NutritionWorkspaceState:
        latest_intake = store.get_latest_intake(profile.athlete_id)
        current_workspace = build_nutrition_workspace(profile=profile, latest_intake_row=latest_intake)
        update = update.model_copy(update={"nutrition_coach_controls": current_workspace.nutrition_coach_controls})
        normalized_update = normalize_nutrition_update_request(
            update=update,
            existing_shared_camp_context=current_workspace.shared_camp_context,
        )
        _validate_schedule_consistency(normalized_update)
        _validate_session_type_consistency(normalized_update)

        merged_payload = merge_workspace_into_payload(
            base_payload=(
                profile.onboarding_draft
                if current_workspace.source == "draft" and isinstance(profile.onboarding_draft, dict)
                else latest_intake.get("intake")
                if current_workspace.source == "intake" and isinstance(latest_intake, dict)
                else {}
            ),
            workspace=normalized_update,
            profile=profile,
        )

        if current_workspace.source == "intake" and current_workspace.intake_id:
            updated_profile = _update_profile_with_nutrition_fallback(
                store=store,
                athlete_id=profile.athlete_id,
                update=ProfileUpdateRequest(nutrition_profile=normalized_update.nutrition_profile),
            )
            store.update_intake(
                current_workspace.intake_id,
                intake=merged_payload,
                fight_date=normalized_update.shared_camp_context.fight_date or None,
                technical_style=list(merged_payload.get("athlete", {}).get("technical_style") or updated_profile.technical_style),
            )
            refreshed_intake = store.get_latest_intake(profile.athlete_id)
            return build_nutrition_workspace(profile=updated_profile, latest_intake_row=refreshed_intake)

        updated_profile = _update_profile_with_nutrition_fallback(
            store=store,
            athlete_id=profile.athlete_id,
            update=ProfileUpdateRequest(
                nutrition_profile=normalized_update.nutrition_profile,
                onboarding_draft=merged_payload,
            ),
        )
        refreshed_intake = store.get_latest_intake(profile.athlete_id)
        return build_nutrition_workspace(profile=updated_profile, latest_intake_row=refreshed_intake)

    @app.post("/api/plans/generate", response_model=GenerationJobResponse, status_code=202)
    async def generate_current_user_plan(
        request: Request,
        request_body: PlanRequest,
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
        active_tasks: set[str] = Depends(get_active_generation_tasks),
        enable_in_process_generation: bool = Depends(get_enable_in_process_generation),
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
        short_window_limit = _plan_generate_rate_limit_requests()
        if short_window_limit > 0:
            allowed, retry_after = await asyncio.to_thread(
                store.check_plan_generation_short_window_limit,
                athlete_id=profile.athlete_id,
                max_requests=short_window_limit,
                window_seconds=_plan_generate_rate_limit_window_seconds(),
            )
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": "Too many plan generation requests. Try again shortly.",
                        "retry_after_seconds": retry_after,
                    },
                )
        client_request_id = _normalized_client_request_id(
            request.headers.get("X-Client-Request-Id"),
            "cli",
        )
        existing_job = await asyncio.to_thread(
            store.get_generation_job_by_client_request_id,
            athlete_id=profile.athlete_id,
            client_request_id=client_request_id,
        )
        stale_after_seconds = _generation_job_stale_after_seconds()
        if existing_job:
            if is_startup_stale_generation_job(existing_job, stale_after_seconds=stale_after_seconds):
                existing_job = await asyncio.to_thread(
                    store.create_or_get_generation_job,
                    athlete_id=profile.athlete_id,
                    client_request_id=client_request_id,
                    source=str(existing_job.get("source") or "self_serve"),
                    request_payload=request_body.model_dump(mode="json"),
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
            return _job_response(job, store=store, viewer_role=profile.role)
        recovered_existing = await asyncio.to_thread(
            _find_existing_terminal_job_for_same_payload,
            store=store,
            athlete_id=profile.athlete_id,
            request_payload=request_body.model_dump(mode="json"),
        )
        if recovered_existing:
            return _job_response(recovered_existing, store=store, viewer_role=profile.role)
        latest_plan = await asyncio.to_thread(store.get_latest_plan, profile.athlete_id)
        if isinstance(latest_plan, dict):
            latest_status = str(latest_plan.get("status") or "").strip().lower()
            latest_stage2_status = str((latest_plan.get("admin_outputs") or {}).get("stage2_status") or "").strip().lower()
            latest_intake_id = str(latest_plan.get("intake_id") or "").strip()
            request_intake_id = str(request_body.intake_id or "").strip()
            if (
                profile.role == "admin"
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
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A generation job is already queued or running for this account.",
            )
        daily_limit = _plan_generate_daily_limit_per_user()
        if daily_limit > 0 and profile.role != "admin" and not _is_exempt_from_daily_generation_cap(profile.email):
            utc_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            jobs_today = await asyncio.to_thread(
                store.count_generation_jobs_for_athlete_since,
                profile.athlete_id,
                utc_midnight,
                sources=_ALLOWED_PLAN_SOURCES,
            )
            if jobs_today >= daily_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Daily generation limit reached. Try again tomorrow.",
                )
        plan_source_header = (request.headers.get("X-Plan-Source") or "").strip()
        resolved_source = plan_source_header if plan_source_header in _ALLOWED_PLAN_SOURCES else "self_serve"
        job = await asyncio.to_thread(
            store.create_or_get_generation_job,
            athlete_id=profile.athlete_id,
            client_request_id=client_request_id,
            source=resolved_source,
            request_payload=request_body.model_dump(mode="json"),
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
        return _job_response(job, store=store, viewer_role=profile.role)

    @app.get("/api/generation-jobs/active", response_model=GenerationJobResponse | None)
    async def get_active_generation_job(
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
        active_tasks: set[str] = Depends(get_active_generation_tasks),
        enable_in_process_generation: bool = Depends(get_enable_in_process_generation),
    ) -> GenerationJobResponse | None:
        stale_after_seconds = _generation_job_stale_after_seconds()
        job = await asyncio.to_thread(
            store.get_active_generation_job_for_athlete,
            profile.athlete_id,
            stale_after_seconds=stale_after_seconds,
        )
        if not job:
            return None
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

    @app.get("/api/generation-jobs/latest", response_model=GenerationJobResponse | None)
    async def get_latest_generation_job(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> GenerationJobResponse | None:
        job = await asyncio.to_thread(store.get_latest_generation_job_for_athlete, profile.athlete_id)
        if not job:
            return None
        if profile.role != "admin" and str(job["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        return _job_response(job, store=store, viewer_role=profile.role)

    @app.get("/api/generation-jobs/{job_id}", response_model=GenerationJobResponse)
    async def get_generation_job(
        job_id: str,
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
        active_tasks: set[str] = Depends(get_active_generation_tasks),
        enable_in_process_generation: bool = Depends(get_enable_in_process_generation),
    ) -> GenerationJobResponse:
        job = await asyncio.to_thread(store.get_generation_job, job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
        if profile.role != "admin" and str(job["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        job = await asyncio.to_thread(store.recover_generation_job_if_stale, job)
        job = await schedule_generation_job_if_needed(
            job=job,
            background_tasks=background_tasks,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
            enable_in_process_generation=enable_in_process_generation,
            stale_job_checker=_is_stale_job,
            stale_after_seconds=_generation_job_stale_after_seconds(),
        )
        return _job_response(job, store=store, viewer_role=profile.role)

    @app.post("/api/generation-jobs/{job_id}/retry", response_model=GenerationJobResponse, status_code=202)
    async def retry_generation_job(
        request: Request,
        job_id: str,
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
        active_tasks: set[str] = Depends(get_active_generation_tasks),
        enable_in_process_generation: bool = Depends(get_enable_in_process_generation),
    ) -> GenerationJobResponse:
        original = await asyncio.to_thread(store.get_generation_job, job_id)
        if not original:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
        is_admin = profile.role == "admin"
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

        # Daily cap enforcement: admins and exempt emails are not rate-limited.
        if not is_admin and not _is_exempt_from_daily_generation_cap(profile.email):
            daily_limit = _plan_generate_daily_limit_per_user()
            if daily_limit > 0:
                utc_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                jobs_today = await asyncio.to_thread(
                    store.count_generation_jobs_for_athlete_since,
                    target_athlete_id,
                    utc_midnight,
                    sources=_ALLOWED_PLAN_SOURCES,
                )
                if jobs_today >= daily_limit:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Daily generation limit reached. Try again tomorrow.",
                    )

        # If the original job is a pre-start stale running job, reuse its client_request_id
        # so we reset the existing job instead of creating a duplicate. Otherwise prefer
        # the header-provided id or generate a retry id.
        retry_client_request_id = (
            str(original.get("client_request_id") or "") if is_startup_stale
            else _normalized_client_request_id(
                request.headers.get("X-Client-Request-Id"),
                f"retry_{job_id}",
            )
        )
        retry_intake_id = str(original.get("intake_id") or "").strip() or None
        retry_plan_id = existing_plan_id or None
        if source == "admin_triage_resume" and (not retry_intake_id or not retry_plan_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="admin triage resume retry is missing plan/intake linkage",
            )
        existing_retry_job = await asyncio.to_thread(
            store.get_generation_job_by_client_request_id,
            athlete_id=target_athlete_id,
            client_request_id=retry_client_request_id,
        )
        if existing_retry_job:
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
            return _job_response(job, store=store, viewer_role=profile.role)
        blocking_job = await asyncio.to_thread(
            _find_blocking_generation_job_for_athlete,
            store=store,
            athlete_id=target_athlete_id,
            stale_after_seconds=stale_after_seconds,
        )
        if blocking_job and str(blocking_job.get("id")) != str(original.get("id")):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A generation job is already queued or running for this account.",
            )

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
        return _job_response(job, store=store, viewer_role=profile.role)

    @app.get("/api/plans/latest", response_model=PlanDetail)
    def get_latest_plan(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        plan_row = next(
            iter(_visible_plans_for_athlete(store.list_user_plans(profile.athlete_id))),
            None,
        )
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        return _map_plan_detail(
            plan_row,
            include_admin=profile.role == "admin",
            plan_source=_lookup_plan_source(store, str(plan_row.get("id") or "")),
        )

    @app.get("/api/plans/latest/weekly-schedule", response_model=WeeklySchedule)
    def get_latest_weekly_schedule(
        week_index: int = Query(0, ge=0),
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> WeeklySchedule:
        plan_row = next(
            iter(_visible_plans_for_athlete(store.list_user_plans(profile.athlete_id))),
            None,
        )
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        return _map_weekly_schedule(plan_row, week_index=week_index)

    @app.get("/api/plans", response_model=list[PlanSummary])
    def list_plans(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> list[PlanSummary]:
        rows = store.list_user_plans(profile.athlete_id)
        if profile.role != "admin":
            rows = _visible_plans_for_athlete(rows)
        return [_map_plan_summary(row) for row in rows]

    @app.get("/api/plans/{plan_id}", response_model=PlanDetail)
    def get_plan(
        plan_row: dict[str, Any] = Depends(require_plan_row),
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        return _map_plan_detail(
            plan_row,
            include_admin=profile.role == "admin",
            plan_source=_lookup_plan_source(store, str(plan_row.get("id") or "")),
        )

    @app.get("/api/plans/{plan_id}/weekly-schedule", response_model=WeeklySchedule)
    def get_plan_weekly_schedule(
        week_index: int = Query(0, ge=0),
        plan_row: dict[str, Any] = Depends(require_plan_row),
    ) -> WeeklySchedule:
        return _map_weekly_schedule(plan_row, week_index=week_index)

    @app.patch("/api/plans/{plan_id}", response_model=PlanDetail)
    @app.patch("/api/plans/{plan_id}/name", response_model=PlanDetail)
    def rename_plan(
        plan_id: str,
        update: PlanRenameRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        if profile.role != "admin" and str(plan_row["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        if profile.role != "admin" and _is_archived_plan(plan_row):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        updated = store.rename_plan(plan_id, update.plan_name)
        return _map_plan_detail(
            updated,
            include_admin=profile.role == "admin",
            plan_source=_lookup_plan_source(store, plan_id),
        )

    @app.delete("/api/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
    def archive_user_plan(
        plan_id: str,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> Response:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        if profile.role != "admin" and str(plan_row["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        if store.has_active_generation_job_for_plan(plan_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Plan has an active generation job. Cancel or wait before deleting.",
            )
        if profile.role == "admin" or _is_archived_plan(plan_row):
            store.delete_plan(plan_id)
        else:
            store.archive_plan(plan_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/admin/plans", response_model=list[AdminPlanSummary])
    def list_admin_plans(
        _: ProfileRecord = Depends(require_admin),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        store: AppStore = Depends(get_store),
    ) -> list[AdminPlanSummary]:
        return [_map_admin_plan_summary(row) for row in store.list_admin_plans(limit=limit, offset=offset)]

    @app.post("/api/admin/plans/{plan_id}/manual-stage2", response_model=PlanDetail)
    def submit_manual_stage2(
        plan_id: str,
        submission: ManualStage2SubmissionRequest,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

        updated = store.update_plan_stage2(
            plan_id,
            _manual_stage2_result(plan_row, submission.final_plan_text),
        )
        return _map_plan_detail(
            updated,
            include_admin=True,
            plan_source=_lookup_plan_source(store, plan_id),
        )

    @app.post("/api/admin/plans/{plan_id}/approve", response_model=PlanDetail)
    def approve_review_required_plan(
        plan_id: str,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

        updated = store.update_plan_stage2(
            plan_id,
            _admin_approved_result(plan_row),
        )
        return _map_plan_detail(
            updated,
            include_admin=True,
            plan_source=_lookup_plan_source(store, plan_id),
        )

    @app.post("/api/admin/plans/{plan_id}/approve-and-resume-generation", response_model=GenerationJobResponse, status_code=202)
    async def approve_and_resume_generation(
        request: Request,
        plan_id: str,
        approval: ApproveAndResumeGenerationRequest,
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
        active_tasks: set[str] = Depends(get_active_generation_tasks),
        enable_in_process_generation: bool = Depends(get_enable_in_process_generation),
    ) -> GenerationJobResponse:
        plan_row = await asyncio.to_thread(store.get_plan, plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

        intake_id = str(plan_row.get("intake_id") or "").strip()
        if not intake_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan is missing intake_id")
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
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="stored intake is missing for this plan")
            payload = copy.deepcopy(intake_row.get("intake"))
            payload["_triage_resume_override"] = {
                "approved": True,
                "approved_by": {
                    "user_id": profile.athlete_id,
                    "email": profile.email,
                },
                "reason": approval.reason,
                "allowed_modes": ["needs_review", "restricted_rehab_only"],
            }
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
                        return _job_response(existing_resume_job, store=store, viewer_role=profile.role)
                    existing_resume_job = await _requeue_existing_resume_job(existing_resume_job)
                    job_status = str(existing_resume_job.get("status") or "").strip().lower()
                if job_status in {"failed", "completed"} and not _resume_job_final_result_successful(existing_resume_job):
                    existing_resume_job = await _requeue_existing_resume_job(existing_resume_job)
                    job_status = str(existing_resume_job.get("status") or "").strip().lower()
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
                    return _job_response(existing_resume_job, store=store, viewer_role=profile.role)

        why_log = plan_row.get("why_log") if isinstance(plan_row.get("why_log"), dict) else {}
        triage = why_log.get("injury_triage") if isinstance(why_log.get("injury_triage"), dict) else {}
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
            "approved_at": datetime.now(timezone.utc).isoformat(),
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

    @app.post("/api/admin/plans/{plan_id}/reject", response_model=PlanDetail)
    def reject_approved_plan(
        plan_id: str,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

        updated = store.update_plan_stage2(
            plan_id,
            _admin_rejected_result(plan_row),
        )
        return _map_plan_detail(
            updated,
            include_admin=True,
            plan_source=_lookup_plan_source(store, plan_id),
        )

    @app.post("/api/admin/plans/{plan_id}/archive", response_model=PlanDetail)
    def archive_plan(
        plan_id: str,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

        updated = store.update_plan_stage2(
            plan_id,
            _admin_archived_result(plan_row),
        )
        return _map_plan_detail(
            updated,
            include_admin=True,
            plan_source=_lookup_plan_source(store, plan_id),
        )

    @app.get("/api/admin/athletes", response_model=list[AdminAthleteRecord])
    def list_admin_athletes(
        _: ProfileRecord = Depends(require_admin),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        store: AppStore = Depends(get_store),
    ) -> list[AdminAthleteRecord]:
        return [_map_admin_athlete(row) for row in store.list_admin_athletes(limit=limit, offset=offset)]

    @app.get("/api/admin/athletes/{athlete_id}", response_model=AdminAthleteRecord)
    def get_admin_athlete(
        athlete_id: str,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> AdminAthleteRecord:
        row = store.get_admin_athlete(athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        latest_intake = store.get_latest_intake(athlete_id)
        return _map_admin_athlete(row, latest_intake=latest_intake)

    @app.get("/api/admin/athletes/{athlete_id}/generation-jobs", response_model=list[AdminGenerationJobDiagnostic])
    def list_admin_athlete_generation_jobs(
        athlete_id: str,
        _: ProfileRecord = Depends(require_admin),
        limit: int = Query(10, ge=1, le=50),
        store: AppStore = Depends(get_store),
    ) -> list[AdminGenerationJobDiagnostic]:
        row = store.get_admin_athlete(athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        jobs = store.list_generation_jobs_for_athlete(athlete_id, limit=limit)
        stale_after_seconds = _generation_job_stale_after_seconds()
        return [_admin_generation_job_diagnostic(job, stale_after_seconds=stale_after_seconds) for job in jobs]

    @app.get("/api/admin/diagnostics/state-integrity")
    def get_admin_state_integrity_diagnostics(
        _: ProfileRecord = Depends(require_admin),
        limit: int = Query(500, ge=1, le=5000),
        store: AppStore = Depends(get_store),
    ) -> dict[str, Any]:
        orphaned_terminal_jobs = store.list_orphaned_terminal_generation_jobs(limit=limit)
        failed_resume_with_approved_marker = store.list_failed_triage_resume_jobs_with_approved_marker(limit=limit)

        return {
            "limit": limit,
            "orphaned_terminal_jobs": orphaned_terminal_jobs,
            "failed_resume_with_approved_marker": failed_resume_with_approved_marker,
            "orphaned_terminal_job_count": len(orphaned_terminal_jobs),
            "failed_resume_with_approved_marker_count": len(failed_resume_with_approved_marker),
        }

    @app.get("/api/admin/athletes/{athlete_id}/nutrition/current", response_model=NutritionWorkspaceState)
    def get_admin_athlete_nutrition_current(
        athlete_id: str,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> NutritionWorkspaceState:
        row = store.get_admin_athlete(athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        latest_intake = store.get_latest_intake(athlete_id)
        athlete = _map_admin_athlete(row, latest_intake=latest_intake)
        return build_nutrition_workspace(profile=athlete, latest_intake_row=latest_intake)

    @app.put("/api/admin/athletes/{athlete_id}/nutrition/current", response_model=NutritionWorkspaceState)
    def update_admin_athlete_nutrition_current(
        athlete_id: str,
        update: NutritionWorkspaceUpdateRequest,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> NutritionWorkspaceState:
        row = store.get_admin_athlete(athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")

        latest_intake = store.get_latest_intake(athlete_id)
        athlete = _map_admin_athlete(row, latest_intake=latest_intake)
        current_workspace = build_nutrition_workspace(profile=athlete, latest_intake_row=latest_intake)
        if "nutrition_coach_controls" not in update.model_fields_set:
            update = update.model_copy(update={"nutrition_coach_controls": current_workspace.nutrition_coach_controls})
        normalized_update = normalize_nutrition_update_request(
            update=update,
            existing_shared_camp_context=current_workspace.shared_camp_context,
        )
        _validate_schedule_consistency(normalized_update)
        _validate_session_type_consistency(normalized_update)

        merged_payload = merge_workspace_into_payload(
            base_payload=(
                athlete.onboarding_draft
                if current_workspace.source == "draft" and isinstance(athlete.onboarding_draft, dict)
                else latest_intake.get("intake")
                if current_workspace.source == "intake" and isinstance(latest_intake, dict)
                else {}
            ),
            workspace=normalized_update,
            profile=athlete,
        )

        if current_workspace.source == "intake" and current_workspace.intake_id:
            updated_profile = _update_profile_with_nutrition_fallback(
                store=store,
                athlete_id=athlete_id,
                update=ProfileUpdateRequest(nutrition_profile=normalized_update.nutrition_profile),
            )
            store.update_intake(
                current_workspace.intake_id,
                intake=merged_payload,
                fight_date=normalized_update.shared_camp_context.fight_date or None,
                technical_style=list(merged_payload.get("athlete", {}).get("technical_style") or updated_profile.technical_style),
            )
            refreshed_intake = store.get_latest_intake(athlete_id)
            return build_nutrition_workspace(profile=updated_profile, latest_intake_row=refreshed_intake)

        updated_profile = _update_profile_with_nutrition_fallback(
            store=store,
            athlete_id=athlete_id,
            update=ProfileUpdateRequest(
                nutrition_profile=normalized_update.nutrition_profile,
                onboarding_draft=merged_payload,
            ),
        )
        refreshed_intake = store.get_latest_intake(athlete_id)
        return build_nutrition_workspace(profile=updated_profile, latest_intake_row=refreshed_intake)

    @app.post("/api/admin/athletes/{athlete_id}/plans/generate-from-latest-intake", response_model=GenerationJobResponse, status_code=202)
    async def generate_admin_athlete_plan_from_latest_intake(
        request: Request,
        athlete_id: str,
        background_tasks: BackgroundTasks,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
        active_tasks: set[str] = Depends(get_active_generation_tasks),
        enable_in_process_generation: bool = Depends(get_enable_in_process_generation),
    ) -> GenerationJobResponse:
        row = store.get_admin_athlete(athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        latest_intake = store.get_latest_intake(athlete_id)
        if not latest_intake or not isinstance(latest_intake.get("intake"), dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="latest intake not found for athlete",
            )
        latest_intake_athlete_id = str(latest_intake.get("athlete_id") or "").strip()
        latest_intake_id = str(latest_intake.get("id") or "").strip() or None
        if latest_intake_athlete_id != athlete_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="latest intake belongs to a different athlete",
            )
        if not latest_intake_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="latest intake is missing id",
            )
        try:
            request_body = PlanRequest.model_validate(latest_intake["intake"])
        except ValidationError as exc:
            logger.warning(
                "[admin] generate_from_latest_intake:invalid_intake athlete_id=%s errors=%s",
                athlete_id,
                exc.errors(),
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="latest intake is invalid and cannot be used for generation",
            ) from exc
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
        stale_after_seconds = _generation_job_stale_after_seconds()
        request_payload = request_body.model_dump(mode="json")
        existing_job = await asyncio.to_thread(
            store.get_generation_job_by_client_request_id,
            athlete_id=athlete_id,
            client_request_id=client_request_id,
        )
        if existing_job:
            existing_source = str(existing_job.get("source") or "").strip()
            existing_intake_id = str(existing_job.get("intake_id") or "").strip() or None
            existing_payload = existing_job.get("request_payload")
            has_safe_linkage = (
                existing_source == "admin_latest_intake"
                and existing_intake_id == latest_intake_id
                and isinstance(existing_payload, dict)
                and _stable_payload_hash(existing_payload) == _stable_payload_hash(request_payload)
            )
            is_startup_stale = is_startup_stale_generation_job(existing_job, stale_after_seconds=stale_after_seconds)
            if not has_safe_linkage and not is_startup_stale:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="unsafe existing admin generation job linkage",
                )
            if is_startup_stale:
                existing_job = await asyncio.to_thread(
                    store.create_or_get_generation_job,
                    athlete_id=athlete_id,
                    client_request_id=client_request_id,
                    source="admin_latest_intake",
                    request_payload=request_payload,
                    intake_id=latest_intake_id,
                    stale_after_seconds=stale_after_seconds,
                )
                existing_payload_after_reset = existing_job.get("request_payload")
                if (
                    str(existing_job.get("source") or "").strip() != "admin_latest_intake"
                    or str(existing_job.get("intake_id") or "").strip() != (latest_intake_id or "")
                    or not isinstance(existing_payload_after_reset, dict)
                    or _stable_payload_hash(existing_payload_after_reset) != _stable_payload_hash(request_payload)
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="unsafe existing admin generation job linkage",
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
            return _job_response(job, store=store, viewer_role="admin")
        blocking_job = await asyncio.to_thread(
            _find_blocking_generation_job_for_athlete,
            store=store,
            athlete_id=athlete_id,
            stale_after_seconds=stale_after_seconds,
        )
        if blocking_job:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A generation job is already queued or running for this account.",
            )
        job = await asyncio.to_thread(
            store.create_or_get_generation_job,
            athlete_id=athlete_id,
            client_request_id=client_request_id,
            source="admin_latest_intake",
            request_payload=request_payload,
            intake_id=latest_intake_id,
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
        return _job_response(job, store=store, viewer_role="admin")

    @app.patch("/api/admin/athletes/{athlete_id}/latest-intake", response_model=AdminAthleteRecord)
    def update_admin_athlete_latest_intake(
        athlete_id: str,
        update: AdminLatestIntakeUpdateRequest,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> AdminAthleteRecord:
        row = store.get_admin_athlete(athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        latest_intake = store.get_latest_intake(athlete_id)
        if not latest_intake or not isinstance(latest_intake.get("intake"), dict):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="latest intake not found for athlete")
        if str(latest_intake.get("athlete_id") or "").strip() != athlete_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="latest intake belongs to a different athlete")
        latest_intake_id = str(latest_intake.get("id") or "").strip()
        if not latest_intake_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="latest intake is missing id")
        merged = dict(latest_intake["intake"])
        for field in ("fight_date", "no_scheduled_fight", "rounds_format", "weekly_training_frequency", "training_availability", "equipment_access", "key_goals", "weak_areas", "injuries"):
            if field in update.model_fields_set:
                merged[field] = getattr(update, field)
        try:
            request_body = PlanRequest.model_validate(merged)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc
        focus_validation = validate_performance_focus_selections(
            request_body.fight_date,
            key_goals=request_body.key_goals,
            weak_areas=request_body.weak_areas,
            time_zone=request_body.athlete.athlete_timezone,
        )
        if focus_validation.is_over_cap:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=focus_validation.error_message or "Too many focus selections for this camp.")
        if request_body.weekly_training_frequency and request_body.weekly_training_frequency > len(request_body.training_availability):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="weekly_training_frequency cannot exceed selected training_availability days")
        refreshed = store.update_intake(
            latest_intake_id,
            intake=request_body.model_dump(mode="json"),
            fight_date=None if request_body.no_scheduled_fight else (request_body.fight_date.strip() or None),
            technical_style=list(request_body.athlete.technical_style),
        )
        return _map_admin_athlete(row, latest_intake=refreshed)

    return app


def _build_runtime_app() -> FastAPI:
    enable_in_process_generation = is_in_process_generation_enabled()
    logger.info(
        "[app] build_runtime_app:start has_supabase_url=%s has_service_role_key=%s in_process_generation=%s",
        bool(os.getenv("SUPABASE_URL")),
        bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        enable_in_process_generation,
    )
    logger.info("[app] build_runtime_app:using_supabase_mode")
    store = SupabaseAppStore.from_env()
    store.validate_runtime_schema()
    return create_app(
        store=store,
        auth_service=SupabaseAuthService.from_env(),
        mode_label="supabase-authenticated",
        enable_in_process_generation=enable_in_process_generation,
    )



def _build_startup_failure_app(detail: str) -> FastAPI:
    app = FastAPI(title="UNLXCK Fight Camp API", version="0.2.0")

    def _failure_response() -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "ok": False,
                "app": "unlxck-fight-camp-api",
                "detail": detail,
            },
        )

    @app.get("/", include_in_schema=False)
    def root() -> JSONResponse:
        return _failure_response()

    @app.head("/", include_in_schema=False)
    def root_head() -> Response:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    @app.get("/health")
    def health() -> JSONResponse:
        return _failure_response()

    return app


try:
    app = _build_runtime_app()
except RuntimeError as exc:
    logger.exception("[app] runtime_app_build_failed")
    detail = str(exc)
    if "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required" in detail:
        detail = "missing supabase configuration"
    elif not detail:
        detail = "application startup failed"
    app = _build_startup_failure_app(detail)
except PostgrestAPIError as exc:
    logger.exception("[app] runtime_app_build_failed")
    detail = str(exc) or "store service unavailable"
    app = _build_startup_failure_app(detail)
except ValueError:
    logger.exception("[app] runtime_app_build_failed")
    app = _build_startup_failure_app("application startup failed")
