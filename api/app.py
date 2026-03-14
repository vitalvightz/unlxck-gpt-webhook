from __future__ import annotations

import json
import logging
import os
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from fightcamp.main import generate_plan

from .auth import AuthService, AuthenticatedUser, SupabaseAuthService
from .demo import DemoAuthService, get_demo_store
from .models import (
    AdminAthleteRecord,
    AdminPlanOutputs,
    AdminPlanSummary,
    MeResponse,
    PlanDetail,
    PlanOutputs,
    PlanRequest,
    PlanSummary,
    ProfileRecord,
    ProfileUpdateRequest,
)
from .stage2_automation import (
    Stage2AutomationError,
    Stage2AutomationUnavailableError,
    Stage2Automator,
    build_default_stage2_automator,
)
from .store import AppStore, SupabaseAppStore

Planner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    value = os.getenv(
        "APP_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    )
    return [origin.strip() for origin in value.split(",") if origin.strip()]


async def _default_planner(payload: dict[str, Any]) -> dict[str, Any]:
    return await generate_plan(payload)


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
        onboarding_draft=row.get("onboarding_draft"),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _map_plan_summary(row: dict[str, Any]) -> PlanSummary:
    return PlanSummary(
        plan_id=str(row["id"]),
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
    return PlanDetail(
        **summary.model_dump(mode="json"),
        outputs=PlanOutputs(
            plan_text=str(row.get("plan_text") or ""),
            pdf_url=row.get("pdf_url"),
        ),
        admin_outputs=(
            AdminPlanOutputs(
                coach_notes=str(row.get("coach_notes") or ""),
                why_log=row.get("why_log") or {},
                planning_brief=_decode_structured_text(row.get("planning_brief")),
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


def _map_admin_athlete(row: dict[str, Any]) -> AdminAthleteRecord:
    return AdminAthleteRecord(
        athlete_id=str(row["id"]),
        email=str(row.get("email") or ""),
        role=str(row.get("role") or "athlete"),
        full_name=str(row.get("full_name") or ""),
        technical_style=list(row.get("technical_style") or []),
        athlete_timezone=str(row.get("athlete_timezone") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        plan_count=int(row.get("plan_count") or 0),
        latest_plan_created_at=row.get("latest_plan_created_at"),
    )


def create_app(
    *,
    store: AppStore,
    auth_service: AuthService,
    planner: Planner = _default_planner,
    stage2_automator: Stage2Automator | None = None,
    mode_label: str = "supabase-authenticated",
) -> FastAPI:
    app = FastAPI(
        title="UNLXCK Fight Camp API",
        version="0.2.0",
        description="Authenticated athlete-first application API around the fight camp planner.",
    )
    app.state.store = store
    app.state.auth_service = auth_service
    app.state.planner = planner
    app.state.stage2_automator = stage2_automator or build_default_stage2_automator()
    app.state.mode_label = mode_label
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_store(request: Request) -> AppStore:
        return request.app.state.store

    def get_auth_service(request: Request) -> AuthService:
        return request.app.state.auth_service

    def get_planner(request: Request) -> Planner:
        return request.app.state.planner

    def get_stage2_automator(request: Request) -> Stage2Automator:
        return request.app.state.stage2_automator

    def require_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
        auth: AuthService = Depends(get_auth_service),
    ) -> AuthenticatedUser:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            )
        return auth.get_user_from_token(credentials.credentials)

    def require_profile(
        user: AuthenticatedUser = Depends(require_user),
        store: AppStore = Depends(get_store),
    ) -> ProfileRecord:
        return _map_profile_row(store.ensure_profile(user))

    def require_admin(profile: ProfileRecord = Depends(require_profile)) -> ProfileRecord:
        if profile.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return profile

    @app.get("/health")
    def health(request: Request) -> dict[str, str | bool]:
        return {
            "ok": True,
            "app": "unlxck-fight-camp-api",
            "mode": str(request.app.state.mode_label),
        }

    @app.get("/api/me", response_model=MeResponse)
    def get_me(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        latest_intake = store.get_latest_intake(profile.athlete_id)
        return MeResponse(
            profile=profile,
            latest_intake=latest_intake.get("intake") if latest_intake else None,
            plans=[_map_plan_summary(row) for row in store.list_user_plans(profile.athlete_id)],
        )

    @app.put("/api/me", response_model=MeResponse)
    def update_me(
        update: ProfileUpdateRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        updated = _map_profile_row(store.update_profile(profile.athlete_id, update))
        latest_intake = store.get_latest_intake(profile.athlete_id)
        return MeResponse(
            profile=updated,
            latest_intake=latest_intake.get("intake") if latest_intake else None,
            plans=[_map_plan_summary(row) for row in store.list_user_plans(profile.athlete_id)],
        )

    @app.post("/api/plans/generate", response_model=PlanDetail, status_code=201)
    async def generate_current_user_plan(
        request_body: PlanRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
        planner_fn: Planner = Depends(get_planner),
        stage2: Stage2Automator = Depends(get_stage2_automator),
    ) -> PlanDetail:
        logger.info(
            "[plans] generate requested athlete_id=%s fight_date=%s technical_style=%s",
            profile.athlete_id,
            request_body.fight_date,
            request_body.athlete.technical_style,
        )
        store.update_profile(
            profile.athlete_id,
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
        intake = store.create_intake(profile.athlete_id, request_body)
        stage1_result = await planner_fn(request_body.to_payload())
        if stage1_result.get("status") == "invalid_input":
            raise HTTPException(
                status_code=422,
                detail={
                    "message": stage1_result.get("error", "invalid planning input"),
                    "missing_fields": stage1_result.get("missing_fields", []),
                },
            )

        try:
            finalized_result = await stage2.finalize(stage1_result=stage1_result)
        except Stage2AutomationUnavailableError as exc:
            logger.warning("[plans] stage2 unavailable athlete_id=%s detail=%s", profile.athlete_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Stage2AutomationError as exc:
            logger.exception("[plans] stage2 failed athlete_id=%s", profile.athlete_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

        logger.info(
            "[plans] stage2 completed athlete_id=%s app_status=%s stage2_status=%s attempts=%s",
            profile.athlete_id,
            finalized_result.get("status"),
            finalized_result.get("stage2_status"),
            finalized_result.get("stage2_attempt_count"),
        )

        plan_row = store.create_plan(
            athlete_id=profile.athlete_id,
            intake_id=str(intake["id"]),
            request=request_body,
            result={
                **finalized_result,
                "full_name": request_body.athlete.full_name,
            },
        )
        store.clear_onboarding_draft(profile.athlete_id)
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

    @app.get("/api/admin/plans", response_model=list[AdminPlanSummary])
    def list_admin_plans(
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> list[AdminPlanSummary]:
        return [_map_admin_plan_summary(row) for row in store.list_admin_plans()]

    @app.get("/api/admin/athletes", response_model=list[AdminAthleteRecord])
    def list_admin_athletes(
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> list[AdminAthleteRecord]:
        return [_map_admin_athlete(row) for row in store.list_admin_athletes()]

    return app


def _build_runtime_app() -> FastAPI:
    if os.getenv("UNLXCK_DEMO_MODE") == "1":
        return create_app(
            store=get_demo_store(),
            auth_service=DemoAuthService(),
            mode_label="demo",
        )
    return create_app(
        store=SupabaseAppStore.from_env(),
        auth_service=SupabaseAuthService.from_env(),
        mode_label="supabase-authenticated",
    )


try:
    app = _build_runtime_app()
except RuntimeError:
    app = FastAPI(title="UNLXCK Fight Camp API", version="0.2.0")

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "ok": False,
            "app": "unlxck-fight-camp-api",
            "detail": "missing supabase configuration",
        }
