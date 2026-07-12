"""Authenticated HTTP routes for isolated beta feedback."""

from __future__ import annotations

import logging
from typing import Annotated, Callable, TypeVar

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from api.feedback_images import MAX_SCREENSHOT_BYTES, ScreenshotValidationError
from api.models import (
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


def build_feedback_router(*, require_profile, get_store) -> APIRouter:
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
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> FeedbackRecord:
        return _invoke_feedback_route(
            request,
            surface="plan",
            category="plan_usefulness",
            priority="normal",
            screenshot_present=False,
            operation=lambda: put_plan_feedback(store, profile, plan_id, body, request),
        )

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
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> FeedbackRecord:
        is_safety = body.response == "unsafe"
        return _invoke_feedback_route(
            request,
            surface="daily_recommendation",
            category="recommendation_safety" if is_safety else "recommendation_fit",
            priority="safety" if is_safety else "normal",
            screenshot_present=False,
            operation=lambda: put_today_feedback(store, profile, body, request),
        )

    @router.post(
        "/api/feedback/global",
        response_model=FeedbackRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_global_feedback(
        request: Request,
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
            return await run_in_threadpool(
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
        except ScreenshotValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    return router
