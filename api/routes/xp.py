"""Authenticated XP API with server-derived account progress."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from api.models import ProfileRecord, XpAwardResponse
from api.services.xp_progress import build_xp_progress
from api.store import AppStore
from api.xp import claim_daily_login_reward


def _require_athlete(profile: ProfileRecord) -> None:
    if profile.role != "athlete":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="athlete account required",
        )


def build_xp_router(*, require_profile, get_store) -> APIRouter:
    router = APIRouter(prefix="/api/xp", tags=["xp"])

    @router.get("/progress")
    def get_progress(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> dict[str, Any]:
        """Return progress and idempotently record today's app activity."""

        _require_athlete(profile)
        return build_xp_progress(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
            profile=profile,
        )

    @router.post("/daily-login", response_model=XpAwardResponse)
    def claim_daily_login(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> XpAwardResponse:
        # Retained for backwards compatibility only. Active clients use the
        # /progress endpoint, which records activity without awarding XP.
        _require_athlete(profile)
        result = claim_daily_login_reward(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
        )
        return XpAwardResponse.model_validate(result)

    return router
