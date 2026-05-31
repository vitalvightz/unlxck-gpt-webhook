from __future__ import annotations

import asyncio
import copy
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from postgrest.exceptions import APIError as PostgrestAPIError
from pydantic import ValidationError

from fightcamp.logging_utils import bind_log_context, clear_log_context, configure_logging
from fightcamp.plan_pipeline import prime_plan_banks
from fightcamp.stage2_pipeline import build_stage2_retry, review_stage2_output

from .auth import AuthService, AuthenticatedUser, SupabaseAuthService, is_auth_api_error
from .environment import (
    apply_production_environment_defaults,
    should_default_to_production,
)
from .models import (
    ApproveAndResumeGenerationRequest,
    AdminGenerationJobDiagnostic,
    AdminAthleteRecord,
    AdminLatestIntakeUpdateRequest,
    AdminPlanSummary,
    GenerationJobResponse,
    ManualStage2SubmissionRequest,
    NutritionWorkspaceUpdateRequest,
    PlanDetail,
    PlanRequest,
    ProfileRecord,
    ProfileUpdateRequest,
)
from .performance_focus import validate_performance_focus_selections
from .generation_runtime import (
    default_planner as runtime_default_planner,
    is_in_process_generation_enabled,
    schedule_generation_job_if_needed,
)
from .stage2_automation import (
    Stage2Automator,
    build_default_stage2_automator,
)
from .store import AppStore, SupabaseAppStore, is_startup_stale_generation_job
from .sentry_config import init_sentry
from .services.generation_retry_service import retry_generation_job as retry_generation_job_service
from .cors_config import (
    get_cors_origins as get_cors_origins,
    get_cors_origin_regex as get_cors_origin_regex,
    validate_production_cors_config as validate_production_cors_config,
)
from .plan_mappers import (
    _decode_structured_text,
    _map_profile_row,
    _is_archived_plan,
    _ALLOWED_PLAN_SOURCES,
    _lookup_plan_source,
    _map_plan_detail,
    _map_admin_plan_summary,
    _map_admin_athlete,
)
from .generation_job_helpers import (
    _utc_now_iso,
    _PROTECTED_TRIAGE_STATUSES,
    _normalized_client_request_id,
    _job_response,
    _build_protected_triage_response,
    _is_stale_job,
    _generation_job_stale_after_seconds,
    _find_blocking_generation_job_for_athlete,
    _stable_payload_signature,
    _triage_job_has_resume_approval,
    _job_final_result_triage_status,
    _find_existing_terminal_job_for_same_payload,
    _admin_generation_job_diagnostic,
    _resume_job_final_result_successful,
    _resume_job_resolved_successfully,
    _can_approve_and_resume_triage,
    _has_existing_triage_resume_approval,
    _triage_plan_has_resume_approval as _triage_plan_has_resume_approval,
)
from .routes import (
    build_generation_jobs_router,
    build_nutrition_router,
    build_plans_router,
    build_profile_router,
)

Planner = Callable[[dict[str, Any]], dict[str, Any]]
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

init_sentry()


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


def _noop_planner(
    payload: dict[str, Any],
    *,
    progress_callback=None,
) -> dict[str, Any]:
    return {}


def _health_payload(*, mode_label: str) -> dict[str, str | bool]:
    return {
        "ok": True,
        "app": "unlxck-fight-camp-api",
        "mode": mode_label,
    }


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
    cors_origins = get_cors_origins()
    cors_regex = get_cors_origin_regex()
    validate_production_cors_config(cors_origins, cors_regex)
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
            "[http] request:start request_id=%s method=%s path=%s has_query=%s",
            request_id,
            request.method,
            request.url.path,
            bool(request.url.query),
            extra={
                "request_id": request_id,
                "status": "started",
            },
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
                extra={
                    "request_id": request_id,
                    "status": response.status_code,
                },
            )
            return response
        except HTTPException as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.warning(
                "[http] request:http_exception request_id=%s method=%s path=%s status=%s duration_ms=%s error_code=%s",
                request_id,
                request.method,
                request.url.path,
                exc.status_code,
                duration_ms,
                "http_exception",
                extra={
                    "request_id": request_id,
                    "status": exc.status_code,
                    "error_code": "http_exception",
                },
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
                "[http] request:exception request_id=%s method=%s path=%s duration_ms=%s error_code=%s",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
                "unhandled_exception",
                extra={
                    "request_id": request_id,
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "error_code": "unhandled_exception",
                },
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
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
        auth: AuthService = Depends(get_auth_service),
    ) -> AuthenticatedUser:
        request_id = getattr(request.state, "request_id", "")
        if credentials is None or credentials.scheme.lower() != "bearer":
            logger.warning(
                "[auth] missing_or_invalid_bearer_token request_id=%s auth_event=%s status=%s error_code=%s",
                request_id,
                "missing_or_invalid_bearer_token",
                "failure",
                "authentication_required",
                extra={
                    "request_id": request_id,
                    "auth_event": "missing_or_invalid_bearer_token",
                    "status": "failure",
                    "error_code": "authentication_required",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            )
        try:
            user = auth.get_user_from_token(credentials.credentials)
            logger.info(
                "[auth] token_resolved request_id=%s athlete_id=%s auth_event=%s status=%s",
                request_id,
                user.user_id,
                "token_resolved",
                "success",
                extra={
                    "request_id": request_id,
                    "athlete_id": user.user_id,
                    "auth_event": "token_resolved",
                    "status": "success",
                },
            )
            return user
        except HTTPException as exc:
            logger.warning(
                "[auth] token_resolution_http_error request_id=%s status=%s auth_event=%s error_code=%s",
                request_id,
                exc.status_code,
                "token_resolution_http_error",
                "auth_http_error",
                extra={
                    "request_id": request_id,
                    "auth_event": "token_resolution_http_error",
                    "status": exc.status_code,
                    "error_code": "auth_http_error",
                },
            )
            raise
        except Exception as exc:
            if is_auth_api_error(exc):
                logger.warning(
                    "[auth] token_resolution_invalid_token request_id=%s auth_event=%s status=%s error_code=%s error_class=%s",
                    request_id,
                    "token_resolution_invalid_token",
                    status.HTTP_401_UNAUTHORIZED,
                    "invalid_authentication_token",
                    exc.__class__.__module__ + "." + exc.__class__.__name__,
                    extra={
                        "request_id": request_id,
                        "auth_event": "token_resolution_invalid_token",
                        "status": status.HTTP_401_UNAUTHORIZED,
                        "error_code": "invalid_authentication_token",
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid authentication token",
                ) from exc
            logger.exception(
                "[auth] token_resolution_failed request_id=%s auth_event=%s status=%s error_code=%s",
                request_id,
                "token_resolution_failed",
                "failure",
                "auth_resolution_failed",
                extra={
                    "request_id": request_id,
                    "auth_event": "token_resolution_failed",
                    "status": "failure",
                    "error_code": "auth_resolution_failed",
                },
            )
            raise

    def require_profile(
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
        store: AppStore = Depends(get_store),
    ) -> ProfileRecord:
        request_id = getattr(request.state, "request_id", "")
        try:
            profile = _map_profile_row(store.ensure_profile(user))
            logger.info(
                "[auth] profile_resolved request_id=%s athlete_id=%s auth_event=%s status=%s",
                request_id,
                profile.athlete_id,
                "profile_resolved",
                "success",
                extra={
                    "request_id": request_id,
                    "athlete_id": profile.athlete_id,
                    "auth_event": "profile_resolved",
                    "status": "success",
                },
            )
            return profile
        except HTTPException as exc:
            logger.warning(
                "[auth] profile_resolution_http_error request_id=%s athlete_id=%s status=%s auth_event=%s error_code=%s",
                request_id,
                user.user_id,
                exc.status_code,
                "profile_resolution_http_error",
                "profile_http_error",
                extra={
                    "request_id": request_id,
                    "athlete_id": user.user_id,
                    "auth_event": "profile_resolution_http_error",
                    "status": exc.status_code,
                    "error_code": "profile_http_error",
                },
            )
            raise
        except Exception:
            logger.exception(
                "[auth] profile_resolution_failed request_id=%s athlete_id=%s auth_event=%s status=%s error_code=%s",
                request_id,
                user.user_id,
                "profile_resolution_failed",
                "failure",
                "profile_resolution_failed",
                extra={
                    "request_id": request_id,
                    "athlete_id": user.user_id,
                    "auth_event": "profile_resolution_failed",
                    "status": "failure",
                    "error_code": "profile_resolution_failed",
                },
            )
            raise

    def require_admin(
        profile: ProfileRecord = Depends(require_profile),
    ) -> ProfileRecord:
        if profile.role != "admin":
            logger.warning(
                "[auth] admin_access_denied athlete_id=%s role=%s",
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
        try:
            uuid.UUID(plan_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
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

    if os.getenv("ENABLE_SENTRY_DEBUG_ROUTE", "false").strip().lower() == "true":
        @app.get("/sentry-debug", include_in_schema=False)
        def sentry_debug() -> None:
            raise Exception("Sentry backend test error")

    app.include_router(
        build_profile_router(
            require_profile=require_profile,
            get_store=get_store,
        )
    )
    app.include_router(
        build_nutrition_router(
            require_profile=require_profile,
            require_admin=require_admin,
            get_store=get_store,
            validate_schedule_consistency=_validate_schedule_consistency,
            validate_session_type_consistency=_validate_session_type_consistency,
            update_profile_with_nutrition_fallback=_update_profile_with_nutrition_fallback,
        )
    )

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
            latest_stage2_status = str(latest_plan.get("stage2_status") or "").strip().lower()
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

    app.include_router(
        build_generation_jobs_router(
            require_profile=require_profile,
            get_store=get_store,
            get_planner=get_planner,
            get_stage2_automator=get_stage2_automator,
            get_active_generation_tasks=get_active_generation_tasks,
            get_enable_in_process_generation=get_enable_in_process_generation,
            schedule_generation_job_if_needed=schedule_generation_job_if_needed,
        )
    )

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
        return await retry_generation_job_service(
            request=request,
            job_id=job_id,
            background_tasks=background_tasks,
            profile=profile,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
            enable_in_process_generation=enable_in_process_generation,
            schedule_generation_job_if_needed=schedule_generation_job_if_needed,
            plan_generate_daily_limit_per_user=_plan_generate_daily_limit_per_user,
            is_exempt_from_daily_generation_cap=_is_exempt_from_daily_generation_cap,
        )

    app.include_router(
        build_plans_router(
            require_profile=require_profile,
            require_plan_row=require_plan_row,
            get_store=get_store,
        )
    )

    @app.get("/api/admin/plans", response_model=list[AdminPlanSummary])
    def list_admin_plans(
        _: ProfileRecord = Depends(require_admin),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        q: str | None = Query(None, max_length=200),
        store: AppStore = Depends(get_store),
    ) -> list[AdminPlanSummary]:
        return [
            _map_admin_plan_summary(row)
            for row in store.list_admin_plans(limit=limit, offset=offset, q=q)
        ]

    @app.get("/api/admin/generation-jobs/triage", response_model=list[AdminGenerationJobDiagnostic])
    def list_admin_triage_generation_jobs(
        _: ProfileRecord = Depends(require_admin),
        limit: int = Query(50, ge=1, le=200),
        store: AppStore = Depends(get_store),
    ) -> list[AdminGenerationJobDiagnostic]:
        stale_after_seconds = _generation_job_stale_after_seconds()
        diagnostics = [
            _admin_generation_job_diagnostic(job, stale_after_seconds=stale_after_seconds)
            for job in store.list_admin_triage_generation_jobs(limit=limit * 4)
        ]
        return [job for job in diagnostics if job.requires_admin_resume][:limit]

    @app.get("/api/admin/generation-jobs/active", response_model=list[AdminGenerationJobDiagnostic])
    def list_admin_active_generation_jobs(
        _: ProfileRecord = Depends(require_admin),
        limit: int = Query(50, ge=1, le=200),
        store: AppStore = Depends(get_store),
    ) -> list[AdminGenerationJobDiagnostic]:
        stale_after_seconds = _generation_job_stale_after_seconds()
        return [
            _admin_generation_job_diagnostic(job, stale_after_seconds=stale_after_seconds)
            for job in store.list_admin_active_generation_jobs(limit=limit)
        ]

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

        # Persist the plan's triage-approval markers BEFORE scheduling the
        # runtime. The runtime's `update_plan_stage2` preserve-keys block
        # (generation_runtime.py) reads `triage_regeneration_cleared` and
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

    @app.post(
        "/api/admin/generation-jobs/{job_id}/approve-and-resume-generation",
        response_model=GenerationJobResponse,
        status_code=202,
    )
    async def approve_and_resume_generation_from_job(
        request: Request,
        job_id: str,
        approval: ApproveAndResumeGenerationRequest,
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
        active_tasks: set[str] = Depends(get_active_generation_tasks),
        enable_in_process_generation: bool = Depends(get_enable_in_process_generation),
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")

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

        source_final_result = source_job.get("final_result") if isinstance(source_job.get("final_result"), dict) else {}
        source_why_log = source_final_result.get("why_log") if isinstance(source_final_result.get("why_log"), dict) else {}
        triage = source_why_log.get("injury_triage") if isinstance(source_why_log.get("injury_triage"), dict) else {}
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
            # plan-based flow's running-not-stale early return at line
            # ~2212. Stale running jobs fall through to the reset/recovery
            # path below.
            if existing_status == "running" and not existing_is_stale:
                return _job_response(existing_resume_job, store=store, viewer_role=profile.role)

        intake_row = await asyncio.to_thread(store.get_intake, intake_id)
        if not intake_row or not isinstance(intake_row.get("intake"), dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="stored intake is missing for this job",
            )

        request_payload = copy.deepcopy(intake_row.get("intake"))
        request_payload["_triage_resume_override"] = {
            "approved": True,
            "approved_by": {
                "user_id": profile.athlete_id,
                "email": profile.email,
            },
            "reason": approval.reason,
            "allowed_modes": ["needs_review", "restricted_rehab_only"],
        }

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
        q: str | None = Query(None, max_length=200),
        store: AppStore = Depends(get_store),
    ) -> list[AdminAthleteRecord]:
        return [
            _map_admin_athlete(row)
            for row in store.list_admin_athletes(limit=limit, offset=offset, q=q)
        ]

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
                "[admin] generate_from_latest_intake:invalid_intake athlete_id=%s error_code=%s validation_error_count=%s",
                athlete_id,
                "invalid_intake",
                len(exc.errors()),
                extra={
                    "athlete_id": athlete_id,
                    "status": status.HTTP_409_CONFLICT,
                    "error_code": "invalid_intake",
                },
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
                and _stable_payload_signature(existing_payload) == _stable_payload_signature(request_payload)
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
                    or _stable_payload_signature(existing_payload_after_reset) != _stable_payload_signature(request_payload)
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
    if should_default_to_production():
        apply_production_environment_defaults()

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
