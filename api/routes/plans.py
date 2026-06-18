from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from api.active_plan import plan_is_eligible_for_active, resolve_active_plan
from api.models import (
    ActivePlanResponse,
    PlanDetail,
    PlanRenameRequest,
    PlanSummary,
    ProfileRecord,
    WeeklySchedule,
)
from api.plan_mappers import (
    _is_archived_plan,
    _lookup_plan_source,
    _map_plan_detail,
    _map_plan_summary,
    _map_weekly_schedule,
    _visible_plans_for_athlete,
)
from api.store import AppStore, is_effective_admin_profile


def build_plans_router(*, require_profile, require_plan_row, get_store) -> APIRouter:
    router = APIRouter()

    @router.get("/api/plans/latest", response_model=PlanDetail)
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
        is_admin = is_effective_admin_profile(profile, store)
        return _map_plan_detail(
            plan_row,
            include_admin=is_admin,
            plan_source=_lookup_plan_source(store, str(plan_row.get("id") or "")),
        )

    @router.get("/api/plans/latest/weekly-schedule", response_model=WeeklySchedule)
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

    @router.get("/api/plans", response_model=list[PlanSummary])
    def list_plans(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> list[PlanSummary]:
        rows = store.list_user_plans(profile.athlete_id)
        if not is_effective_admin_profile(profile, store):
            rows = _visible_plans_for_athlete(rows)
        return [_map_plan_summary(row) for row in rows]

    @router.get("/api/plans/active", response_model=ActivePlanResponse)
    def get_active_plan(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> ActivePlanResponse:
        """The athlete's single active plan, via the central resolver.

        Same resolution Overview and Today use — see api/active_plan.py.
        """
        resolution = resolve_active_plan(store, profile.athlete_id)
        if not resolution.plan_row:
            return ActivePlanResponse(active_plan=None, source=None)
        return ActivePlanResponse(
            active_plan=_map_plan_summary(resolution.plan_row),
            source=resolution.source,
        )

    @router.post("/api/plans/{plan_id}/active", response_model=ActivePlanResponse)
    def set_active_plan(
        plan_id: str,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> ActivePlanResponse:
        """Make ``plan_id`` the athlete's explicit active plan.

        Rejects unknown/unowned plans (404) and archived/non-displayable plans
        (422). Only ``ready``/``publishable_with_flags`` plans may become active.
        """
        try:
            uuid.UUID(plan_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        # Ownership: the athlete-scoped read returns None for someone else's plan.
        plan_row = store.get_plan_for_athlete(plan_id, profile.athlete_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        if not plan_is_eligible_for_active(plan_row):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only a ready plan can be set active. Archived or in-review plans cannot.",
            )
        store.set_active_plan_id(profile.athlete_id, plan_id)
        return ActivePlanResponse(active_plan=_map_plan_summary(plan_row), source="explicit")

    @router.get("/api/plans/{plan_id}", response_model=PlanDetail)
    def get_plan(
        plan_row: dict[str, Any] = Depends(require_plan_row),
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        is_admin = is_effective_admin_profile(profile, store)
        return _map_plan_detail(
            plan_row,
            include_admin=is_admin,
            plan_source=_lookup_plan_source(store, str(plan_row.get("id") or "")),
        )

    @router.get("/api/plans/{plan_id}/weekly-schedule", response_model=WeeklySchedule)
    def get_plan_weekly_schedule(
        week_index: int = Query(0, ge=0),
        plan_row: dict[str, Any] = Depends(require_plan_row),
    ) -> WeeklySchedule:
        return _map_weekly_schedule(plan_row, week_index=week_index)

    @router.patch("/api/plans/{plan_id}", response_model=PlanDetail)
    @router.patch("/api/plans/{plan_id}/name", response_model=PlanDetail)
    def rename_plan(
        plan_id: str,
        update: PlanRenameRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> PlanDetail:
        try:
            uuid.UUID(plan_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        is_admin = is_effective_admin_profile(profile, store)
        if is_admin:
            plan_row = store.get_plan(plan_id)
            if not plan_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
            updated = store.rename_plan(plan_id, update.plan_name)
        else:
            # Ownership is enforced by the athlete-scoped store methods: a plan
            # owned by someone else reads back as missing (404).
            plan_row = store.get_plan_for_athlete(plan_id, profile.athlete_id)
            if not plan_row or _is_archived_plan(plan_row):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
            updated = store.rename_plan_for_athlete(plan_id, profile.athlete_id, update.plan_name)
        return _map_plan_detail(
            updated,
            include_admin=is_admin,
            plan_source=_lookup_plan_source(store, plan_id),
        )

    @router.delete("/api/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
    def archive_user_plan(
        plan_id: str,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> Response:
        try:
            uuid.UUID(plan_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        # Ownership is enforced by the athlete-scoped store methods for
        # non-admins; admins intentionally operate on the raw plan id.
        is_admin = is_effective_admin_profile(profile, store)
        if is_admin:
            plan_row = store.get_plan(plan_id)
        else:
            plan_row = store.get_plan_for_athlete(plan_id, profile.athlete_id)
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        if store.has_active_generation_job_for_plan(plan_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Plan has an active generation job. Cancel or wait before archiving.",
            )
        if _is_archived_plan(plan_row):
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        if is_admin:
            store.archive_plan(plan_id)
        else:
            store.archive_plan_for_athlete(plan_id, profile.athlete_id)
        # An archived plan can never be active: clear the owner's explicit
        # pointer so Overview/Today fall back to the next eligible plan rather
        # than dereferencing an archived one.
        owner_id = str(plan_row.get("athlete_id") or "") or profile.athlete_id
        if store.get_active_plan_id(owner_id) == plan_id:
            store.clear_active_plan_id(owner_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
