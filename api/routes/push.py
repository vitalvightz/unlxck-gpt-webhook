from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

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
    list_notification_evaluations,
    update_notification_preferences,
)
from api.services.progress_notifications import send_coach_message_notification
from api.services.push_notifications import push_notifications_configured, vapid_public_key
from api.store import AppStore


class CoachMessagePushRequest(BaseModel):
    athlete_id: str = Field(min_length=1, max_length=80)
    message_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=40)
    body: str = Field(min_length=1, max_length=90)
    url: str = Field(default="/today", min_length=1, max_length=500)
    urgent: bool = False

    @field_validator("athlete_id", "message_id", "title", "body")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value is required")
        return cleaned

    @field_validator("url")
    @classmethod
    def validate_app_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.startswith("/") or cleaned.startswith("//"):
            raise ValueError("url must be an app-relative path")
        return cleaned


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


def build_push_router(*, require_profile, require_admin, get_store) -> APIRouter:
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

    @router.post("/api/admin/notifications/coach-message")
    def send_coach_message(
        request: CoachMessagePushRequest,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> dict[str, int | bool]:
        athlete = store.get_admin_athlete(request.athlete_id)
        if not athlete:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        athlete_timezone = str(athlete.get("athlete_timezone") or "").strip() or "UTC"
        delivered = send_coach_message_notification(
            store,
            athlete_id=request.athlete_id,
            message_id=request.message_id,
            title=request.title,
            body=request.body,
            url=request.url,
            timezone_name=athlete_timezone,
            urgent=request.urgent,
        )
        return {"ok": True, "delivered_count": delivered}

    @router.get("/api/admin/notifications/diagnostics")
    def notification_diagnostics(
        athlete_id: str = Query(min_length=1, max_length=80),
        training_day: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
        intent: str | None = Query(default=None, min_length=1, max_length=64),
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> dict[str, object]:
        athlete = store.get_admin_athlete(athlete_id)
        if not athlete:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        try:
            evaluations = list_notification_evaluations(
                store,
                profile_id=athlete_id,
                training_day=training_day,
                intent=intent,
            )
        except NotificationStoreError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="notification diagnostics temporarily unavailable",
            ) from exc
        return {
            "athlete_id": athlete_id,
            "training_day": training_day,
            "intent": intent,
            "evaluations": evaluations,
        }

    return router
