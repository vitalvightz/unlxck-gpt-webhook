from __future__ import annotations

from fastapi import APIRouter, Depends

from api.models import (
    ProfileRecord,
    PushSettingsResponse,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
)
from api.services.push_notifications import push_notifications_configured, vapid_public_key
from api.store import AppStore


def build_push_router(*, require_profile, get_store) -> APIRouter:
    router = APIRouter()

    @router.get("/api/push/settings", response_model=PushSettingsResponse)
    def get_push_settings(
        profile: ProfileRecord = Depends(require_profile),
    ) -> PushSettingsResponse:
        # The VAPID public key is not secret, but there is no reason to serve it
        # unauthenticated — only signed-in users can register subscriptions.
        enabled = push_notifications_configured()
        return PushSettingsResponse(
            enabled=enabled,
            public_key=vapid_public_key() if enabled else "",
        )

    @router.post("/api/push/subscriptions")
    def save_push_subscription(
        request: PushSubscribeRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> dict[str, bool]:
        store.upsert_push_subscription(
            profile.profile_id,
            {
                "endpoint": request.endpoint,
                "p256dh": request.keys.p256dh,
                "auth": request.keys.auth,
                "timezone": request.timezone,
            },
        )
        return {"ok": True}

    @router.delete("/api/push/subscriptions")
    def remove_push_subscription(
        request: PushUnsubscribeRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> dict[str, bool]:
        store.delete_push_subscription(profile.profile_id, request.endpoint)
        return {"ok": True}

    return router
