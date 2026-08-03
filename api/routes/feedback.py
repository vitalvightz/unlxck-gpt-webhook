"""Authenticated HTTP routes for isolated beta feedback."""

from __future__ import annotations

import logging
from typing import Annotated, Callable, TypeVar

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from api.feedback_images import MAX_SCREENSHOT_BYTES, ScreenshotValidationError
from api.models import (
    AdminFeedbackRecord,
    AdminFeedbackScreenshotAccess,
    ContextualFeedbackRequest,
    FeedbackRecord,
    GlobalFeedbackRequest,
    ProfileRecord,
)
from api.services.feedback_service import (
    get_plan_feedback,
    get_today_feedback,
    put_plan_feedback,
    put_today_feedback,
    submit_global_feedback,
)
from api.services.feedback_notifications import send_feedback_notification
from api.services.xp_awards import award_feedback_xp
from api.store import AppStore

logger = logging.getLogger(__name__)
T = TypeVar("T")

_ADMIN_READINESS_FIELDS = (
    "sleep", "body", "pain", "active_injury", "previous_session", "sharp_pain",
    "instability", "swelling", "neurological_symptoms", "illness_symptoms",
    "cannot_warm_into_movement", "worse_next_day_pain", "recommendation_state",
)
_ADMIN_TECHNICAL_FIELDS = (
    "referer_path", "device_platform", "device_mobile", "browser_brands",
    "user_agent", "language",
)
_ADMIN_INTAKE_FIELDS = (
    "fatigue_level", "training_restriction_level", "training_availability",
)
_ADMIN_INJURY_FLAG_FIELDS = ("id", "body_area", "severity", "status")


def _invoke_feedback_route(request: Request, *, surface: str, category: str, priority: str,
                           screenshot_present: bool, operation: Callable[[], T]) -> T:
    try:
        return operation()
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else None
        error_code = (
            str(detail.get("code")) if isinstance(detail, dict) and detail.get("code")
            else "screenshot_invalid" if isinstance(exc, ScreenshotValidationError)
            else "feedback_route_failed"
        )
        logger.error(
            "[feedback] route_failed request_id=%s surface=%s category=%s priority=%s screenshot_present=%s error_code=%s error_class=%s",
            getattr(request.state, "request_id", ""), surface, category, priority,
            screenshot_present, error_code, type(exc).__name__,
        )
        raise


def _safe_dict(source: dict, fields: tuple[str, ...]) -> dict:
    return {key: source[key] for key in fields if key in source}


def _safe_admin_injury_snapshot(injuries: dict) -> tuple[dict, list[str]]:
    raw_flags = injuries.get("open_flags") if isinstance(injuries.get("open_flags"), list) else []
    valid_flags = [flag for flag in raw_flags if isinstance(flag, dict)]
    safe_flags = [_safe_dict(flag, _ADMIN_INJURY_FLAG_FIELDS) for flag in valid_flags[:3]]
    intake = injuries.get("intake") if isinstance(injuries.get("intake"), dict) else {}
    safe_snapshot: dict = {"open_flags": safe_flags}
    safe_intake = _safe_dict(intake, _ADMIN_INTAKE_FIELDS)
    if safe_intake:
        safe_snapshot["intake"] = safe_intake
    injury_summaries: list[str] = []
    for flag in valid_flags:
        parts = [str(flag.get(key) or "").strip()[:80] for key in ("body_area", "severity", "status")]
        summary = " · ".join(part for part in parts if part)
        if summary:
            injury_summaries.append(summary)
    injury_context = injury_summaries[:3]
    if len(injury_summaries) > 3:
        injury_context.append(f"{len(injury_summaries)} open injury flags total")
    return safe_snapshot, injury_context


def _admin_feedback_record(row: dict) -> AdminFeedbackRecord:
    profile = row.get("profiles") if isinstance(row.get("profiles"), dict) else {}
    technical = row.get("technical_context") if isinstance(row.get("technical_context"), dict) else {}
    readiness = row.get("readiness_snapshot") if isinstance(row.get("readiness_snapshot"), dict) else {}
    injuries = row.get("injury_snapshot") if isinstance(row.get("injury_snapshot"), dict) else {}
    safe_technical = _safe_dict(technical, _ADMIN_TECHNICAL_FIELDS)
    safe_readiness = _safe_dict(readiness, _ADMIN_READINESS_FIELDS)
    safe_injuries, injury_context = _safe_admin_injury_snapshot(injuries)
    platform = str(safe_technical.get("device_platform") or "").strip().strip('"')[:80]
    mobile_hint = str(safe_technical.get("device_mobile") or "").strip()
    device_kind = "Mobile" if mobile_hint == "?1" else "Desktop" if mobile_hint == "?0" else ""
    browser = str(safe_technical.get("browser_brands") or safe_technical.get("user_agent") or "").strip()[:160]
    device_context = " · ".join(part for part in (device_kind, platform, browser) if part)
    readiness_context = [
        f"{key.replace('_', ' ').title()}: {str(safe_readiness[key])[:100]}"
        for key in ("sleep", "body", "pain", "active_injury", "previous_session", "recommendation_state")
        if safe_readiness.get(key) not in (None, "", [])
    ]
    return AdminFeedbackRecord(
        id=str(row.get("id") or ""), submitted_by_profile_id=str(row.get("submitted_by_profile_id") or ""),
        submitter_email=str(profile.get("email") or ""), submitter_name=str(profile.get("full_name") or ""),
        surface=str(row.get("surface") or "global"), category=str(row.get("category") or "general_feedback"),
        response=row.get("response"), reason=row.get("reason"), comment=str(row.get("comment") or ""),
        contact_allowed=bool(row.get("contact_allowed")), priority=str(row.get("priority") or "normal"),
        plan_id=row.get("plan_id"), today_checkin_id=row.get("today_checkin_id"), camp_phase=row.get("camp_phase"),
        app_version=str(row.get("app_version") or ""), page_path=str(safe_technical.get("referer_path") or "").strip()[:512],
        device_context=device_context, language=str(safe_technical.get("language") or "").strip()[:80],
        readiness_context=readiness_context, injury_context=injury_context,
        readiness_snapshot=safe_readiness, injury_snapshot=safe_injuries, technical_context=safe_technical,
        has_screenshot=bool(row.get("screenshot_path")), screenshot_expires_at=row.get("screenshot_expires_at"),
        created_at=str(row.get("created_at") or ""), updated_at=str(row.get("updated_at") or ""),
    )


def build_feedback_router(*, require_profile, require_admin, get_store) -> APIRouter:
    router = APIRouter(tags=["feedback"])

    @router.get("/api/plans/{plan_id}/feedback", response_model=FeedbackRecord | None)
    def read_plan_feedback(plan_id: str, request: Request, profile: ProfileRecord = Depends(require_profile),
                           store: AppStore = Depends(get_store)) -> FeedbackRecord | None:
        return _invoke_feedback_route(request, surface="plan", category="plan_usefulness", priority="normal",
                                      screenshot_present=False, operation=lambda: get_plan_feedback(store, profile, plan_id))

    @router.put("/api/plans/{plan_id}/feedback", response_model=FeedbackRecord)
    def update_plan_feedback(plan_id: str, body: ContextualFeedbackRequest, request: Request,
                             background_tasks: BackgroundTasks, profile: ProfileRecord = Depends(require_profile),
                             store: AppStore = Depends(get_store)) -> FeedbackRecord:
        record = _invoke_feedback_route(request, surface="plan", category="plan_usefulness", priority="normal",
                                        screenshot_present=False,
                                        operation=lambda: put_plan_feedback(store, profile, plan_id, body, request))
        award_feedback_xp(store, athlete_id=profile.athlete_id, feedback=record.model_dump())
        background_tasks.add_task(send_feedback_notification, record, profile)
        return record

    @router.get("/api/today/feedback", response_model=FeedbackRecord | None)
    def read_today_feedback(request: Request, profile: ProfileRecord = Depends(require_profile),
                            store: AppStore = Depends(get_store)) -> FeedbackRecord | None:
        return _invoke_feedback_route(request, surface="daily_recommendation", category="recommendation_fit",
                                      priority="normal", screenshot_present=False,
                                      operation=lambda: get_today_feedback(store, profile))

    @router.put("/api/today/feedback", response_model=FeedbackRecord)
    def update_today_feedback(body: ContextualFeedbackRequest, request: Request, background_tasks: BackgroundTasks,
                              profile: ProfileRecord = Depends(require_profile),
                              store: AppStore = Depends(get_store)) -> FeedbackRecord:
        is_safety = body.response == "unsafe"
        record = _invoke_feedback_route(
            request, surface="daily_recommendation",
            category="recommendation_safety" if is_safety else "recommendation_fit",
            priority="safety" if is_safety else "normal", screenshot_present=False,
            operation=lambda: put_today_feedback(store, profile, body, request),
        )
        award_feedback_xp(store, athlete_id=profile.athlete_id, feedback=record.model_dump())
        background_tasks.add_task(send_feedback_notification, record, profile)
        return record

    @router.post("/api/feedback/global", response_model=FeedbackRecord, status_code=status.HTTP_201_CREATED)
    async def create_global_feedback(
        request: Request, background_tasks: BackgroundTasks,
        category: Annotated[str, Form(max_length=40)], description: Annotated[str, Form(max_length=500)] = "",
        contact_allowed: Annotated[bool, Form()] = False,
        screenshot: Annotated[UploadFile | None, File()] = None,
        profile: ProfileRecord = Depends(require_profile), store: AppStore = Depends(get_store),
    ) -> FeedbackRecord:
        try:
            payload = GlobalFeedbackRequest(category=category, description=description, contact_allowed=contact_allowed)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid feedback form") from exc
        raw_screenshot: bytes | None = None
        if screenshot is not None:
            raw_screenshot = await screenshot.read(MAX_SCREENSHOT_BYTES + 1)
            await screenshot.close()
        try:
            record = await run_in_threadpool(
                _invoke_feedback_route, request, surface="global", category=payload.category,
                priority="safety" if payload.category == "safety_issue" else "normal",
                screenshot_present=raw_screenshot is not None,
                operation=lambda: submit_global_feedback(store, profile, payload, request, raw_screenshot),
            )
            award_feedback_xp(store, athlete_id=profile.athlete_id, feedback=record.model_dump())
            background_tasks.add_task(send_feedback_notification, record, profile)
            return record
        except ScreenshotValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.get("/api/admin/feedback", response_model=list[AdminFeedbackRecord])
    def read_admin_feedback(_: ProfileRecord = Depends(require_admin), limit: int = Query(50, ge=1, le=100),
                            store: AppStore = Depends(get_store)) -> list[AdminFeedbackRecord]:
        return [_admin_feedback_record(row) for row in store.list_admin_feedback(limit=limit)]

    @router.get("/api/admin/feedback/{feedback_id}/screenshot", response_model=AdminFeedbackScreenshotAccess)
    def read_admin_feedback_screenshot(feedback_id: str, _: ProfileRecord = Depends(require_admin),
                                       store: AppStore = Depends(get_store)) -> AdminFeedbackScreenshotAccess:
        screenshot_path = store.get_feedback_screenshot_path(feedback_id)
        if not screenshot_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feedback screenshot not found")
        expires_in = 60
        return AdminFeedbackScreenshotAccess(
            url=store.create_feedback_screenshot_signed_url(screenshot_path, expires_in=expires_in),
            expires_in=expires_in,
        )

    return router
