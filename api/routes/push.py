from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.models import (
    ProfileRecord,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
)
from api.notification_models import (
    NotificationPreferences,
    NotificationPreferencesUpdate,
    PushSettingsResponse,
)
from api.services.notification_foundation import (
    NotificationStoreError,
    get_notification_preferences,
    update_notification_preferences,
)
from api.services.push_notifications import push_notifications_configured, vapid_public_key
from api.store import AppStore


def _preferences_unavailable(exc: NotificationStoreError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="notification preferences temporarily unavailable",
    )


def _preference_patch(request: NotificationPreferencesUpdate) -> dict:
    """Preserve explicit null only for the optional preferred training time."""

    raw = request.model_dump(exclude_unset=True)
    return {
        key: value
        for key, value in raw.items()
        if value is not None or key == "preferred_training_time"
    }


def build_push_router(*, require_profile, get_store) -> APIRouter:
    router = APIRouter()

    @router.get("/api/push/settings", response_model=PushSettingsResponse)
    def get_push_settings(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> PushSettingsResponse:
        enabled = push_notifications_configured()
        try:
            preferences = get_notification_preferences(store, profile.athlete_id)
        except NotificationStoreError as exc:
            raise _preferences_unavailable(exc) from exc
        return PushSettingsResponse(
            enabled=enabled,
            public_key=vapid_public_key() if enabled else "",
            preferences=preferences,
        )

    @router.put("/api/push/preferences", response_model=NotificationPreferences)
    def save_notification_preferences(
        request: NotificationPreferencesUpdate,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> NotificationPreferences:
        try:
            return update_notification_preferences(
                store,
                profile.athlete_id,
                _preference_patch(request),
            )
        except NotificationStoreError as exc:
            raise _preferences_unavailable(exc) from exc

    @router.post("/api/push/subscriptions")
    def save_push_subscription(
        request: PushSubscribeRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> dict[str, bool]:
        store.upsert_push_subscription(
            profile.athlete_id,
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
        store.delete_push_subscription(profile.athlete_id, request.endpoint)
        return {"ok": True}

    return router
