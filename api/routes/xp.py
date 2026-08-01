"""Authenticated XP API with a server-derived account and award."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.models import ProfileRecord, XpAwardResponse
from api.store import AppStore
from api.xp import claim_daily_login_reward


def build_xp_router(*, require_profile, get_store) -> APIRouter:
    router = APIRouter(prefix="/api/xp", tags=["xp"])

    @router.post("/daily-login", response_model=XpAwardResponse)
    def claim_daily_login(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> XpAwardResponse:
        if profile.role != "athlete":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="athlete account required",
            )
        result = claim_daily_login_reward(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
        )
        return XpAwardResponse.model_validate(result)

    return router
