from __future__ import annotations

from fastapi import APIRouter, Depends

from api.models import (
    MeResponse,
    OnboardingDraftSaveRequest,
    ProfileRecord,
    ProfileUpdateRequest,
    UsernameChangeRequest,
)
from api.plan_mappers import _build_me_response, _map_profile_row
from api.services.xp_awards import reconcile_activation_xp
from api.store import AppStore


def build_profile_router(*, require_profile, get_store) -> APIRouter:
    router = APIRouter()

    def _build_me_with_activation_xp(
        profile: ProfileRecord,
        store: AppStore,
    ) -> MeResponse:
        response = _build_me_response(profile, store)
        reconcile_activation_xp(
            store,
            athlete_id=profile.athlete_id,
            profile=response.profile,
            latest_intake=response.latest_intake,
            latest_plan=response.latest_plan,
        )
        return response

    @router.get("/api/me", response_model=MeResponse)
    def get_me(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        return _build_me_with_activation_xp(profile, store)

    @router.put("/api/me", response_model=MeResponse)
    def update_me(
        update: ProfileUpdateRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        updated = _map_profile_row(store.update_profile(profile.athlete_id, update))
        return _build_me_with_activation_xp(updated, store)

    @router.post("/api/me/username", response_model=MeResponse)
    def change_username_endpoint(
        update: UsernameChangeRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        updated = _map_profile_row(store.change_username(profile.athlete_id, update.username))
        return _build_me_with_activation_xp(updated, store)

    @router.patch("/api/onboarding/draft")
    def save_onboarding_draft(
        update: OnboardingDraftSaveRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> dict[str, str | bool]:
        update_data = update.model_dump(exclude_unset=True)
        updated = store.update_profile(
            profile.athlete_id,
            ProfileUpdateRequest(**update_data),
        )
        updated_at = (updated or {}).get("updated_at")
        return {"ok": True, "updated_at": str(updated_at or "")}

    return router
