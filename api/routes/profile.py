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
from api.store import AppStore


def build_profile_router(*, require_profile, get_store) -> APIRouter:
    router = APIRouter()

    @router.get("/api/me", response_model=MeResponse)
    def get_me(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        return _build_me_response(profile, store)

    @router.put("/api/me", response_model=MeResponse)
    def update_me(
        update: ProfileUpdateRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        updated = _map_profile_row(store.update_profile(profile.athlete_id, update))
        return _build_me_response(updated, store)

    @router.post("/api/me/username", response_model=MeResponse)
    def change_username_endpoint(
        update: UsernameChangeRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        updated = _map_profile_row(store.change_username(profile.athlete_id, update.username))
        return _build_me_response(updated, store)

    @router.patch("/api/onboarding/draft", response_model=MeResponse)
    def save_onboarding_draft(
        update: OnboardingDraftSaveRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> MeResponse:
        update_data = update.model_dump(exclude_unset=True)
        updated = _map_profile_row(
            store.update_profile(
                profile.athlete_id,
                ProfileUpdateRequest(**update_data),
            )
        )
        return _build_me_response(updated, store)
    
    return router
