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
from api.store import AppStore

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _invoke_feedback_route(
    request: Request,
    *,
    surface: str,
    category: str,
    priority: str,
    screenshot_present: bool,
    operation: Callable[[], T],
) -> T:
    try:
        return operation()
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else None
        error_code = (
            str(detail.get("code"))
            if isinstance(detail, dict) and detail.get("code")
            else "screenshot_invalid"
            if isinstance(exc, ScreenshotValidationError)
            else "feedback_route_failed"
        )
        logger.error(
            "[feedback] route_failed request_id=%s surface=%s category=%s priority=%s screenshot_present=%s error_code=%s error_class=%s",
            getattr(request.state, "request_id", ""),
            surface,
            category,
            priority,
            screenshot_present,
            error_code,
            type(exc).__name__,
        )
        raise


def _admin_feedback_record(row: dict) -> AdminFeedbackRecord:
    profile = row.get("profiles") if isinstance(row.get("profiles"), dict) else {}
    return AdminFeedbackRecord(
        id=str(row.get("id") or ""),
        submitted_by_profile_id=str(row.get("submitted_by_profile_id") or ""),
        submitter_email=str(profile.get("email") or ""),
        submitter_name=str(profile.get("full_name") or ""),
        surface=str(row.get("surface") or "global"),
        category=str(row.get("category") or "general_feedback"),
        response=row.get("response"),
        reason=row.get("reason"),
        comment=str(row.get("comment") or ""),
        contact_allowed=bool(row.get("contact_allowed")),
        priority=str(row.get("priority") or "normal"),
        plan_id=row.get("plan_id"),
        today_checkin_id=row.get("today_checkin_id"),
        camp_phase=row.get("camp_phase"),
        app_version=str(row.get("app_version") or ""),
        has_screenshot=bool(row.get("screenshot_path")),
        screenshot_expires_at=row.get("screenshot_expires_at"),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def build_feedback_router(*, require_profile, require_admin, get_store) -> APIRouter:
    router = APIRouter(tags=["feedback"])

    @router.get("/api/plans/{plan_id}/feedback", response_model=FeedbackRecord | None)
    def read_plan_feedback(
        plan_id: str,
        request: Request,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> FeedbackRecord | None:
        return _invoke_feedback_route(
            request,
            surface="plan",
            category="plan_usefulness",
            priority="normal",
            screenshot_present=False,
            operation=lambda: get_plan_feedback(store, profile, plan_id),
        )

    @router.put("/api/plans/{plan_id}/feedback", response_model=FeedbackRecord)
    def update_plan_feedback(
        plan_id: str,
        body: ContextualFeedbackRequest,
        request: Request,
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> FeedbackRecord:
        record = _invoke_feedback_route(
            request,
            surface="plan",
            category="plan_usefulness",
            priority="normal",
            screenshot_present=False,
            operation=lambda: put_plan_feedback(store, profile, plan_id, body, request),
        )
        background_tasks.add_task(send_feedback_notification, record, profile)
        return record

    @router.get("/api/today/feedback", response_model=FeedbackRecord | None)
    def read_today_feedback(
        request: Request,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> FeedbackRecord | None:
        return _invoke_feedback_route(
            request,
            surface="daily_recommendation",
            category="recommendation_fit",
            priority="normal",
            screenshot_present=False,
            operation=lambda: get_today_feedback(store, profile),
        )

    @router.put("/api/today/feedback", response_model=FeedbackRecord)
    def update_today_feedback(
        body: ContextualFeedbackRequest,
        request: Request,
        background_tasks: BackgroundTasks,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> FeedbackRecord:
        is_safety = body.response == "unsafe"
        record = _invoke_feedback_route(
            request,
            surface="daily_recommendation",
            category="recommendation_safety" if is_safety else "recommendation_fit",
            priority="safety" if is_safety else "normal",
            screenshot_present=False,
            operation=lambda: put_today_feedback(store, profile, body, request),
        )
        background_tasks.add_task(send_feedback_notification, record, profile)
        return record

    @router.post(
        "/api/feedback/global",
        response_model=FeedbackRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_global_feedback(
        request: Request,
        background_tasks: BackgroundTasks,
        category: Annotated[str, Form(max_length=40)],
        description: Annotated[str, Form(max_length=500)] = "",
        contact_allowed: Annotated[bool, Form()] = False,
        screenshot: Annotated[UploadFile | None, File()] = None,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> FeedbackRecord:
        try:
            payload = GlobalFeedbackRequest(
                category=category,
                description=description,
                contact_allowed=contact_allowed,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid feedback form") from exc

        raw_screenshot: bytes | None = None
        if screenshot is not None:
            raw_screenshot = await screenshot.read(MAX_SCREENSHOT_BYTES + 1)
            await screenshot.close()
        try:
            record = await run_in_threadpool(
                _invoke_feedback_route,
                request,
                surface="global",
                category=payload.category,
                priority="safety" if payload.category == "safety_issue" else "normal",
                screenshot_present=raw_screenshot is not None,
                operation=lambda: submit_global_feedback(
                    store,
                    profile,
                    payload,
                    request,
                    raw_screenshot,
                ),
            )
            background_tasks.add_task(send_feedback_notification, record, profile)
            return record
        except ScreenshotValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.get("/api/admin/feedback", response_model=list[AdminFeedbackRecord])
    def read_admin_feedback(
        _: ProfileRecord = Depends(require_admin),
        limit: int = Query(50, ge=1, le=100),
        store: AppStore = Depends(get_store),
    ) -> list[AdminFeedbackRecord]:
        return [_admin_feedback_record(row) for row in store.list_admin_feedback(limit=limit)]

    return router
