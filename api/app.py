from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from contextlib import suppress
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from fightcamp.logging_utils import bind_log_context, clear_log_context, configure_logging
from fightcamp.main import generate_plan_sync
from fightcamp.plan_pipeline import prime_plan_banks
from fightcamp.sparring_advisories import build_plan_advisories
from fightcamp.stage2_pipeline import build_stage2_retry, review_stage2_output

from .auth import AuthService, AuthenticatedUser, SupabaseAuthService
from .demo import DemoAuthService, get_demo_store
from .models import (
    AdminAthleteRecord,
    AdminPlanOutputs,
    AdminPlanSummary,
    GenerationJobResponse,
    ManualStage2SubmissionRequest,
    MeResponse,
    NutritionWorkspaceState,
    NutritionWorkspaceUpdateRequest,
    PlanDetail,
    PlanRenameRequest,
    PlanOutputs,
    PlanRequest,
    PlanSummary,
    ProfileRecord,
    ProfileUpdateRequest,
)
from .nutrition_workspace import (
    build_nutrition_workspace,
    merge_workspace_into_payload,
    normalize_nutrition_update_request,
)
from .performance_focus import validate_performance_focus_selections
from .stage2_automation import (
    Stage2AutomationError,
    Stage2AutomationUnavailableError,
    Stage2Automator,
    build_default_stage2_automator,
)
from .store import AppStore, SupabaseAppStore

Planner = Callable[[dict[str, Any]], dict[str, Any]]
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
LOCAL_HOST_NAMES = ("localhost", "127.0.0.1", "::1")


class SlidingWindowRateLimiter:
    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: float,
        time_fn: Callable[[], float] | None = None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._time_fn = time_fn or time.monotonic
        self._lock = Lock()
        self._requests_by_key: dict[str, deque[float]] = {}

    def check(self, key: str) -> int | None:
        now = self._time_fn()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._requests_by_key.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                return retry_after
            bucket.append(now)
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
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


def _job_response(job: dict[str, Any], *, latest_plan_id: str | None = None) -> GenerationJobResponse:
    plan_id = str(job.get("plan_id")) if job.get("plan_id") else None
    updated_at = job.get("updated_at") or job.get("created_at") or _utc_now_iso()
    return GenerationJobResponse(
        job_id=str(job["id"]),
        athlete_id=str(job["athlete_id"]),
        client_request_id=str(job.get("client_request_id") or ""),
        status=str(job["status"]),
        created_at=str(job["created_at"]),
        updated_at=str(updated_at),
        started_at=str(job["started_at"]) if job.get("started_at") else None,
        completed_at=str(job["completed_at"]) if job.get("completed_at") else None,
        error=str(job["error"]) if job.get("error") else None,
        plan_id=plan_id,
        latest_plan_id=latest_plan_id or plan_id,
    )


def _is_stale_job(job: dict[str, Any], *, stale_after_seconds: int = 90) -> bool:
    if str(job.get("status") or "") != "running":
        return False
    last_progress_at = _parse_datetime(job.get("heartbeat_at")) or _parse_datetime(job.get("started_at"))
    if last_progress_at is None:
        return False
    return (datetime.now(timezone.utc) - last_progress_at).total_seconds() >= stale_after_seconds


def _deserialize_plan_request(value: Any) -> PlanRequest:
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


def _build_me_response(profile: ProfileRecord, store: AppStore) -> MeResponse:
    latest_intake = store.get_latest_intake(profile.athlete_id)
    plans = store.list_user_plans(profile.athlete_id)
    latest_plan = _map_plan_summary(plans[0]) if plans else None
    return MeResponse(
        profile=profile,
        latest_intake=latest_intake.get("intake") if latest_intake else None,
        latest_plan=latest_plan,
        plan_count=len(plans),
    )


def _validate_session_type_consistency(workspace: NutritionWorkspaceUpdateRequest) -> None:
    training_days = {day.strip().lower() for day in workspace.shared_camp_context.training_availability if str(day).strip()}
    hard_days = {day.strip().lower() for day in workspace.shared_camp_context.hard_sparring_days if str(day).strip()}
    technical_days = {day.strip().lower() for day in workspace.shared_camp_context.technical_skill_days if str(day).strip()}

    for day, session_type in workspace.shared_camp_context.session_types_by_day.items():
        normalized_day = str(day or "").strip().lower()
        if session_type == "hard_spar" and normalized_day not in hard_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"session_types_by_day.{day} must also be included in hard_sparring_days",
            )
        if session_type == "technical" and normalized_day not in technical_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"session_types_by_day.{day} must also be included in technical_skill_days",
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

    invalid_technical_days = [day for day in shared.technical_skill_days if str(day).strip().lower() not in normalized_training_days]
    if invalid_technical_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"technical_skill_days must be included in training_availability: {', '.join(invalid_technical_days)}",
        )

    overlap = sorted(
        {
            hard_day
            for hard_day in shared.hard_sparring_days
            if str(hard_day).strip().lower() in {day.strip().lower() for day in shared.technical_skill_days if str(day).strip()}
        }
    )
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A day cannot be both hard_sparring and technical_skill: {', '.join(overlap)}",
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


def _default_planner(payload: dict[str, Any]) -> dict[str, Any]:
    return generate_plan_sync(payload)


def _health_payload(*, mode_label: str) -> dict[str, str | bool]:
    return {
        "ok": True,
        "app": "unlxck-fight-camp-api",
        "mode": mode_label,
    }


async def _run_stage1_planner(planner_fn: Planner, payload: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(planner_fn, payload)


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
    return ProfileRecord(
        athlete_id=str(row["id"]),
        email=str(row.get("email") or ""),
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


def _map_plan_summary(row: dict[str, Any]) -> PlanSummary:
    return PlanSummary(
        plan_id=str(row["id"]),
        plan_name=(str(row["plan_name"]).strip() if row.get("plan_name") is not None else None) or None,
        athlete_id=str(row["athlete_id"]),
        full_name=str(row.get("full_name") or ""),
        fight_date=str(row.get("fight_date") or ""),
        technical_style=list(row.get("technical_style") or []),
        created_at=str(row.get("created_at") or ""),
        status=str(row.get("status") or "generated"),
        pdf_url=row.get("pdf_url"),
    )


def _admin_draft_text(row: dict[str, Any]) -> str:
    return str(row.get("draft_plan_text") or row.get("plan_text") or "")


def _admin_final_text(row: dict[str, Any]) -> str:
    return str(row.get("final_plan_text") or row.get("plan_text") or "")


def _map_plan_detail(row: dict[str, Any], *, include_admin: bool) -> PlanDetail:
    summary = _map_plan_summary(row)
    planning_brief = _decode_structured_text(row.get("planning_brief"))
    return PlanDetail(
        **summary.model_dump(mode="json"),
        outputs=PlanOutputs(
            plan_text=str(row.get("plan_text") or ""),
            pdf_url=row.get("pdf_url"),
        ),
        advisories=build_plan_advisories(planning_brief=planning_brief),
        admin_outputs=(
            AdminPlanOutputs(
                coach_notes=str(row.get("coach_notes") or ""),
                why_log=row.get("why_log") or {},
                planning_brief=planning_brief,
                stage2_payload=row.get("stage2_payload"),
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
    return {
        "status": "ready",
        "plan_text": approved_text,
        "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
        "final_plan_text": approved_text,
        "pdf_url": None,
        "stage2_retry_text": str(plan_row.get("stage2_retry_text") or ""),
        "stage2_validator_report": plan_row.get("stage2_validator_report") or {},
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


def create_app(
    *,
    store: AppStore,
    auth_service: AuthService,
    planner: Planner = _default_planner,
    stage2_automator: Stage2Automator | None = None,
    mode_label: str = "supabase-authenticated",
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
    app.state.active_generation_tasks = set()
    rate_limit_requests = _plan_generate_rate_limit_requests()
    app.state.plan_generate_rate_limiter = (
        SlidingWindowRateLimiter(
            max_requests=rate_limit_requests,
            window_seconds=_plan_generate_rate_limit_window_seconds(),
        )
        if rate_limit_requests > 0
        else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_origin_regex=_cors_origin_regex(),
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
            "[http] request:start request_id=%s method=%s path=%s query=%s client=%s",
            request_id,
            request.method,
            request.url.path,
            str(request.url.query),
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

    def get_plan_generate_rate_limiter(request: Request) -> SlidingWindowRateLimiter | None:
        return request.app.state.plan_generate_rate_limiter

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
        except Exception:
            logger.exception("[auth] token_resolution_failed")
            raise

    def require_profile(
        user: AuthenticatedUser = Depends(require_user),
        store: AppStore = Depends(get_store),
    ) -> ProfileRecord:
        try:
            profile = _map_profile_row(store.ensure_profile(user))
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

    def require_admin(profile: ProfileRecord = Depends(require_profile)) -> ProfileRecord:
        if profile.role != "admin":
            logger.warning("[auth] admin_access_denied athlete_id=%s role=%s", profile.athlete_id, profile.role)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return profile

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

    async def _heartbeat_generation_job(job_id: str, store: AppStore, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=15)
                return
            except asyncio.TimeoutError:
                try:
                    await asyncio.to_thread(
                        store.update_generation_job,
                        job_id,
                        heartbeat_at=_utc_now_iso(),
                    )
                except Exception:
                    logger.exception("[jobs] generation:heartbeat_failed job_id=%s", job_id)

    async def _run_generation_job(
        *,
        job_id: str,
        store: AppStore,
        planner_fn: Planner,
        stage2: Stage2Automator,
        active_tasks: set[str],
    ) -> None:
        t_start = time.perf_counter()
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(_heartbeat_generation_job(job_id, store, stop_event))
        athlete_id = "unknown"
        try:
            job = await asyncio.to_thread(store.get_generation_job, job_id)
            if not job:
                logger.warning("[jobs] generation:job_missing job_id=%s", job_id)
                return

            athlete_id = str(job["athlete_id"])
            request_body = _deserialize_plan_request(job.get("request_payload") or {})
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
                    heartbeat_at=_utc_now_iso(),
                )

            stage1_result = job.get("stage1_result")
            if not isinstance(stage1_result, dict):
                stage1_result = await _run_stage1_planner(planner_fn, request_body.to_payload())
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
                    heartbeat_at=_utc_now_iso(),
                )

            final_result = job.get("final_result")
            if not isinstance(final_result, dict):
                finalized_result = await stage2.finalize(stage1_result=stage1_result)
                final_result = {**finalized_result, "full_name": request_body.athlete.full_name}
                job = await asyncio.to_thread(
                    store.update_generation_job,
                    job_id,
                    final_result=final_result,
                    heartbeat_at=_utc_now_iso(),
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

            final_status = "completed" if str(plan_row.get("status") or "ready") == "ready" else str(plan_row.get("status") or "failed")
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status=final_status,
                error=None,
                plan_id=plan_id,
                completed_at=_utc_now_iso(),
                heartbeat_at=_utc_now_iso(),
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
                    completed_at=_utc_now_iso(),
                    heartbeat_at=_utc_now_iso(),
                )
        except Stage2AutomationError as exc:
            logger.exception("[jobs] generation:stage2_failed athlete_id=%s job_id=%s", athlete_id, job_id)
            with suppress(Exception):
                await asyncio.to_thread(
                    store.update_generation_job,
                    job_id,
                    status="failed",
                    error=str(exc),
                    completed_at=_utc_now_iso(),
                    heartbeat_at=_utc_now_iso(),
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
                    completed_at=_utc_now_iso(),
                    heartbeat_at=_utc_now_iso(),
                )
        except Exception:
            logger.exception("[jobs] generation:unhandled_exception athlete_id=%s job_id=%s", athlete_id, job_id)
            with suppress(Exception):
                await asyncio.to_thread(
                    store.update_generation_job,
                    job_id,
                    status="failed",
                    error="Plan generation failed unexpectedly. Check server logs with the request ID.",
                    completed_at=_utc_now_iso(),
                    heartbeat_at=_utc_now_iso(),
                )
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            active_tasks.discard(job_id)

    async def _schedule_generation_job_if_needed(
        *,
        job: dict[str, Any],
        background_tasks: BackgroundTasks,
        store: AppStore,
        planner_fn: Planner,
        stage2: Stage2Automator,
        active_tasks: set[str],
    ) -> dict[str, Any]:
        job_id = str(job["id"])
        if job_id in active_tasks:
            return job

        current_status = str(job.get("status") or "queued")
        if current_status not in {"queued", "running"}:
            return job
        if current_status == "running" and not _is_stale_job(job):
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
            _run_generation_job,
            job_id=job_id,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
        )
        return claimed

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
        rate_limiter: SlidingWindowRateLimiter | None = Depends(get_plan_generate_rate_limiter),
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
        if rate_limiter is not None:
            retry_after = rate_limiter.check(profile.athlete_id)
            if retry_after is not None:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": "Too many plan generation requests. Try again shortly.",
                        "retry_after_seconds": retry_after,
                    },
                )
        client_request_id = (request.headers.get("X-Client-Request-Id") or "").strip() or f"cli_{uuid.uuid4().hex}"
        job = await asyncio.to_thread(
            store.create_or_get_generation_job,
            athlete_id=profile.athlete_id,
            client_request_id=client_request_id,
            source="self_serve",
            request_payload=request_body.model_dump(mode="json"),
        )
        job = await _schedule_generation_job_if_needed(
            job=job,
            background_tasks=background_tasks,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
        )
        return _job_response(job)

    @app.get("/api/generation-jobs/{job_id}", response_model=GenerationJobResponse)
    async def get_generation_job(
        job_id: str,
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
        active_tasks: set[str] = Depends(get_active_generation_tasks),
    ) -> GenerationJobResponse:
        job = await asyncio.to_thread(store.get_generation_job, job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
        if profile.role != "admin" and str(job["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        job = await _schedule_generation_job_if_needed(
            job=job,
            background_tasks=background_tasks,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
        )
        return _job_response(job)

    @app.get("/api/plans/latest", response_model=PlanDetail)
    def get_latest_plan(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        plan_row = store.get_latest_plan(profile.athlete_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        return _map_plan_detail(plan_row, include_admin=profile.role == "admin")

    @app.get("/api/plans", response_model=list[PlanSummary])
    def list_plans(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> list[PlanSummary]:
        return [_map_plan_summary(row) for row in store.list_user_plans(profile.athlete_id)]

    @app.get("/api/plans/{plan_id}", response_model=PlanDetail)
    def get_plan(
        plan_id: str,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        if profile.role != "admin" and str(plan_row["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        return _map_plan_detail(plan_row, include_admin=profile.role == "admin")

    @app.patch("/api/plans/{plan_id}", response_model=PlanDetail)
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
        updated = store.rename_plan(plan_id, update.plan_name)
        return _map_plan_detail(updated, include_admin=profile.role == "admin")

    @app.delete("/api/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_plan(
        plan_id: str,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> Response:
        plan_row = store.get_plan(plan_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        if profile.role != "admin" and str(plan_row["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        store.delete_plan(plan_id)
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
        return _map_plan_detail(updated, include_admin=True)

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
        return _map_plan_detail(updated, include_admin=True)

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
        return _map_plan_detail(updated, include_admin=True)

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
        client_request_id = (request.headers.get("X-Client-Request-Id") or "").strip() or f"cli_{uuid.uuid4().hex}"
        job = await asyncio.to_thread(
            store.create_or_get_generation_job,
            athlete_id=athlete_id,
            client_request_id=client_request_id,
            source="admin_latest_intake",
            request_payload=request_body.model_dump(mode="json"),
        )
        job = await _schedule_generation_job_if_needed(
            job=job,
            background_tasks=background_tasks,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
        )
        return _job_response(job)

    return app


def _build_runtime_app() -> FastAPI:
    logger.info(
        "[app] build_runtime_app:start demo_mode=%s has_supabase_url=%s has_service_role_key=%s",
        os.getenv("UNLXCK_DEMO_MODE"),
        bool(os.getenv("SUPABASE_URL")),
        bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
    )
    if os.getenv("UNLXCK_DEMO_MODE") == "1":
        logger.info("[app] build_runtime_app:using_demo_mode")
        store = get_demo_store()
        store.validate_runtime_schema()
        return create_app(
            store=store,
            auth_service=DemoAuthService(),
            mode_label="demo",
        )
    logger.info("[app] build_runtime_app:using_supabase_mode")
    store = SupabaseAppStore.from_env()
    store.validate_runtime_schema()
    return create_app(
        store=store,
        auth_service=SupabaseAuthService.from_env(),
        mode_label="supabase-authenticated",
    )


def _build_startup_failure_app(detail: str) -> FastAPI:
    app = FastAPI(title="UNLXCK Fight Camp API", version="0.2.0")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str | bool]:
        return {
            "ok": False,
            "app": "unlxck-fight-camp-api",
            "detail": detail,
        }

    @app.head("/", include_in_schema=False)
    def root_head() -> None:
        return None

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "ok": False,
            "app": "unlxck-fight-camp-api",
            "detail": detail,
        }

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
except ValueError:
    logger.exception("[app] runtime_app_build_failed")
    app = _build_startup_failure_app("application startup failed")
