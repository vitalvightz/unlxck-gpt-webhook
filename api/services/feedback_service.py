"""Server-authoritative beta feedback orchestration.

This module is deliberately separate from plan generation and Today mutation
services. It reads contextual state, but never writes programme data.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping, TypeVar
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from api.feedback_images import SanitisedScreenshot, sanitise_screenshot
from api.models import (
    ContextualFeedbackRequest,
    FeedbackRecord,
    GlobalFeedbackRequest,
    ProfileRecord,
    SessionFeedbackRequest,
)
from api.services.active_plan import resolve_active_plan
from api.services.plan_schedule import resolve_current_week
from api.services.today_service import resolve_training_day
from api.state_machine import ATHLETE_DISPLAYABLE_PLAN_STATUSES
from api.store import AppStore

logger = logging.getLogger(__name__)
T = TypeVar("T")

PLAN_REASONS = frozenset(
    {
        "too_hard",
        "too_easy",
        "schedule_mismatch",
        "injury_restrictions_wrong",
        "exercises_unsuitable",
        "instructions_unclear",
        "other",
    }
)
DAILY_REASONS = frozenset(
    {
        "too_demanding",
        "too_cautious",
        "pain_or_injury_ignored",
        "training_mismatch",
        "repetitive",
        "unclear",
    }
)
_READINESS_FIELDS = (
    "sleep",
    "body",
    "pain",
    "phase",
    "active_injury",
    "previous_session",
    "sharp_pain",
    "instability",
    "swelling",
    "neurological_symptoms",
    "illness_symptoms",
    "cannot_warm_into_movement",
    "worse_next_day_pain",
    "recommendation_state",
    "recommendation_reason",
    "recommendation_triggers",
)
_INJURY_FIELDS = (
    "id",
    "plan_id",
    "source",
    "body_area",
    "description",
    "severity",
    "status",
    "latest_reported_status",
)
_INTAKE_SNAPSHOT_FIELDS = (
    "fatigue_level",
    "injuries",
    "guided_injury",
    "guided_injuries",
    "training_restriction_level",
    "training_availability",
    "phase_override",
    "phase",
    "training_preference",
    "days_available",
)
_GENERATED_RECOMMENDATION_STATES = frozenset({"train_as_planned", "modify", "pull_back"})
# Only a session the athlete actually trained can be reviewed. A skipped session
# was not experienced, and "started" is not finished, so neither is prompted for
# feedback and neither is accepted here.
_REVIEWABLE_COMPLETION_STATUSES = frozenset({"done", "modified"})


def _configured_non_negative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
        if value < 0:
            raise ValueError
        return value
    except ValueError:
        # Payload-free by design: do not echo environment contents.
        logger.warning("[feedback] invalid_configuration name=%s fallback=%s", name, default)
        return default


def report_limit_per_hour() -> int:
    return _configured_non_negative_int("FEEDBACK_REPORT_LIMIT_PER_HOUR", 5)


def screenshot_limit_per_hour() -> int:
    return _configured_non_negative_int("FEEDBACK_SCREENSHOT_LIMIT_PER_HOUR", 2)


def screenshot_retention_days() -> int:
    """Days a beta screenshot is kept, capped at the period the notice promises.

    The Privacy Notice tells athletes screenshots are kept "no more than 90
    days", so 90 is a ceiling here and not merely a default — a misconfigured
    environment must not be able to quietly outlive a published commitment. A
    shorter period is a valid operational choice and passes through unchanged.
    """
    value = _configured_non_negative_int("FEEDBACK_SCREENSHOT_RETENTION_DAYS", 90)
    return min(value or 90, 90)


def app_version() -> str:
    return (
        os.getenv("VERCEL_GIT_COMMIT_SHA", "").strip()
        or os.getenv("APP_VERSION", "").strip()
        or "local"
    )[:120]


def _bounded_header(request: Request, name: str, limit: int) -> str:
    return str(request.headers.get(name) or "").strip()[:limit]


def technical_context(request: Request) -> dict[str, str]:
    context = {
        "user_agent": _bounded_header(request, "user-agent", 512),
        "browser_brands": _bounded_header(request, "sec-ch-ua", 256),
        "device_platform": _bounded_header(request, "sec-ch-ua-platform", 80),
        "device_mobile": _bounded_header(request, "sec-ch-ua-mobile", 16),
        "language": _bounded_header(request, "accept-language", 80),
    }
    referer = _bounded_header(request, "referer", 1024)
    origin = _bounded_header(request, "origin", 512)
    if referer:
        parsed = urlsplit(referer)
        expected = urlsplit(origin) if origin else request.url
        if (
            parsed.scheme in {"http", "https"}
            and not parsed.username
            and not parsed.password
            and parsed.scheme == expected.scheme
            and parsed.netloc == expected.netloc
        ):
            context["referer_path"] = parsed.path[:512]
    return {key: value for key, value in context.items() if value}


def _feedback_record(row: Mapping[str, Any]) -> FeedbackRecord:
    structured = row.get("structured_response")
    return FeedbackRecord(
        id=str(row.get("id") or ""),
        surface=str(row.get("surface") or "global"),
        category=str(row.get("category") or "general_feedback"),
        response=row.get("response"),
        reason=row.get("reason"),
        comment=str(row.get("comment") or ""),
        structured_response=structured if isinstance(structured, dict) else {},
        priority=str(row.get("priority") or "normal"),
        has_screenshot=bool(row.get("screenshot_path")),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _require_contextual_submitter(profile: ProfileRecord) -> None:
    if profile.role not in {"athlete", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="feedback access required")


def _require_plan_feedback_eligible(plan: Mapping[str, Any]) -> None:
    plan_status = str(plan.get("status") or "").strip().lower()
    plan_text = str(plan.get("plan_text") or plan.get("final_plan_text") or "").strip()
    if plan_status not in ATHLETE_DISPLAYABLE_PLAN_STATUSES or not plan_text:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="plan is not eligible for feedback",
        )


def _require_recommendation_feedback_eligible(checkin: Mapping[str, Any]) -> None:
    recommendation_state = str(checkin.get("recommendation_state") or "").strip()
    if not str(checkin.get("id") or "").strip() or recommendation_state not in _GENERATED_RECOMMENDATION_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="daily recommendation is not eligible for feedback",
        )


def _optional_context(label: str, default: T, operation: Callable[[], T]) -> T:
    """Read non-authoritative feedback context without blocking persistence."""

    try:
        return operation()
    except Exception as exc:
        logger.warning(
            "[feedback] context_enrichment_failed field=%s "
            "error_code=feedback_context_unavailable error_class=%s",
            label,
            type(exc).__name__,
        )
        return default


def _camp_phase(plan: Mapping[str, Any], training_day: str, fallback: Any = "") -> str:
    _index, week = resolve_current_week(plan, today=date.fromisoformat(training_day))
    return str(week.phase if week else fallback or "")


def _plan_context(store: AppStore, profile: ProfileRecord, plan_id: str) -> tuple[dict[str, Any], str, str]:
    _require_contextual_submitter(profile)
    plan = store.get_feedback_plan_for_owner(plan_id, profile.profile_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    _require_plan_feedback_eligible(plan)
    training_day = resolve_training_day(profile.athlete_timezone)
    phase = _optional_context(
        "camp_phase",
        "",
        lambda: _camp_phase(plan, training_day),
    )
    return plan, training_day, phase


def _injury_snapshot(store: AppStore, profile_id: str) -> dict[str, Any]:
    flags = store.list_feedback_injury_flags(profile_id, limit=20)
    return {
        "open_flags": [
            {key: flag.get(key) for key in _INJURY_FIELDS if key in flag}
            for flag in flags
        ]
    }


def _intake_snapshot(store: AppStore, plan: Mapping[str, Any]) -> dict[str, Any]:
    intake_id = str(plan.get("intake_id") or "")
    intake = store.get_feedback_intake(intake_id) if intake_id else None
    if not intake:
        return {}
    raw_intake = intake.get("intake")
    source = raw_intake if isinstance(raw_intake, dict) else {}
    return {
        key: source.get(key)
        for key in _INTAKE_SNAPSHOT_FIELDS
        if key in source
    }


def _validate_contextual(surface: str, payload: ContextualFeedbackRequest) -> tuple[str, str]:
    if surface == "plan":
        if payload.response not in {"yes", "no"}:
            raise HTTPException(status_code=422, detail="invalid plan feedback response")
        allowed_reasons = PLAN_REASONS
        category = "plan_usefulness"
    else:
        allowed_reasons = DAILY_REASONS
        category = "recommendation_safety" if payload.response == "unsafe" else "recommendation_fit"
    if payload.response != "no" and payload.reason is not None:
        raise HTTPException(status_code=422, detail="reason is only valid for a negative response")
    if payload.reason is not None and payload.reason not in allowed_reasons:
        raise HTTPException(status_code=422, detail="invalid feedback reason")
    return category, "safety" if category == "recommendation_safety" else "normal"


def get_plan_feedback(store: AppStore, profile: ProfileRecord, plan_id: str) -> FeedbackRecord | None:
    plan, _training_day, _phase = _plan_context(store, profile, plan_id)
    row = store.get_context_feedback(profile.profile_id, f"plan:{plan['id']}")
    return _feedback_record(row) if row else None


def put_plan_feedback(
    store: AppStore,
    profile: ProfileRecord,
    plan_id: str,
    payload: ContextualFeedbackRequest,
    request: Request,
) -> FeedbackRecord:
    plan, _training_day, phase = _plan_context(store, profile, plan_id)
    category, priority = _validate_contextual("plan", payload)
    row = store.upsert_context_feedback(
        {
            "submitted_by_profile_id": profile.profile_id,
            "context_key": f"plan:{plan['id']}",
            "surface": "plan",
            "category": category,
            "response": payload.response,
            "reason": payload.reason,
            "comment": "" if payload.response == "yes" else payload.comment,
            "contact_allowed": False,
            "priority": priority,
            "plan_id": plan["id"],
            "today_checkin_id": None,
            "camp_phase": phase or None,
            "readiness_snapshot": {},
            "injury_snapshot": {
                **_optional_context(
                    "injury_flags",
                    {"open_flags": []},
                    lambda: _injury_snapshot(store, profile.profile_id),
                ),
                "intake": _optional_context(
                    "intake",
                    {},
                    lambda: _intake_snapshot(store, plan),
                ),
            },
            "app_version": app_version(),
            "technical_context": technical_context(request),
        }
    )
    return _feedback_record(row)


def _today_recommendation_context(
    store: AppStore, profile: ProfileRecord, training_day: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Locate the check-in behind the recommendation the athlete is looking at.

    Mirrors the Today page: the displayed recommendation belongs to the
    ``resolve_active_plan`` result (explicit ``active_plan_id`` only while that
    plan stays eligible, otherwise the latest eligible plan) — not to the raw
    ``profiles.active_plan_id`` pointer. If the resolved plan has no check-in
    for today, fall back to today's stored check-ins so a stale pointer or a
    same-day plan switch cannot orphan a recommendation already on screen.
    """
    plan = resolve_active_plan(
        store,
        profile.profile_id,
        current_training_day=training_day,
    ).plan
    if plan:
        checkin = store.get_feedback_today_checkin(
            profile.profile_id, str(plan.get("id") or ""), training_day
        )
        if checkin:
            return plan, checkin
    for row in store.list_today_checkins_for_day(profile.profile_id, training_day):
        row_plan_id = str(row.get("plan_id") or "").strip()
        row_plan = (
            store.get_feedback_plan_for_owner(row_plan_id, profile.profile_id)
            if row_plan_id
            else None
        )
        if row_plan:
            return row_plan, row
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="active plan not found")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="today check-in not found")


def _today_context(
    store: AppStore, profile: ProfileRecord
) -> tuple[dict[str, Any], dict[str, Any], str]:
    _require_contextual_submitter(profile)
    training_day = resolve_training_day(profile.athlete_timezone)
    plan, checkin = _today_recommendation_context(store, profile, training_day)
    _require_recommendation_feedback_eligible(checkin)
    phase = _optional_context(
        "camp_phase",
        str(checkin.get("phase") or ""),
        lambda: _camp_phase(plan, training_day, checkin.get("phase")),
    )
    return plan, checkin, phase


def get_today_feedback(store: AppStore, profile: ProfileRecord) -> FeedbackRecord | None:
    _plan, checkin, _phase = _today_context(store, profile)
    row = store.get_context_feedback(profile.profile_id, f"today:{checkin['id']}")
    return _feedback_record(row) if row else None


def put_today_feedback(
    store: AppStore,
    profile: ProfileRecord,
    payload: ContextualFeedbackRequest,
    request: Request,
) -> FeedbackRecord:
    plan, checkin, phase = _today_context(store, profile)
    category, priority = _validate_contextual("daily_recommendation", payload)
    row = store.upsert_context_feedback(
        {
            "submitted_by_profile_id": profile.profile_id,
            "context_key": f"today:{checkin['id']}",
            "surface": "daily_recommendation",
            "category": category,
            "response": payload.response,
            "reason": payload.reason,
            "comment": "" if payload.response == "yes" else payload.comment,
            "contact_allowed": False,
            "priority": priority,
            "plan_id": plan["id"],
            "today_checkin_id": checkin["id"],
            "camp_phase": phase or None,
            "readiness_snapshot": {
                key: checkin.get(key) for key in _READINESS_FIELDS if key in checkin
            },
            "injury_snapshot": _optional_context(
                "injury_flags",
                {"open_flags": []},
                lambda: _injury_snapshot(store, profile.profile_id),
            ),
            "app_version": app_version(),
            "technical_context": technical_context(request),
        }
    )
    return _feedback_record(row)


def _session_context(
    store: AppStore, profile: ProfileRecord, payload: SessionFeedbackRequest
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Resolve the completed session the review belongs to.

    The completion record — not the client — is the authority on which session
    was trained and on which training day. An athlete may only review a session
    they logged as done or modified, on a day they logged it.
    """

    _require_contextual_submitter(profile)
    plan = store.get_feedback_plan_for_owner(payload.plan_id, profile.profile_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    # An omitted training_day means "the session I just finished". A retro-log
    # reviewed from history sends the day it was logged against.
    training_day = payload.training_day or resolve_training_day(profile.athlete_timezone)
    completion = store.get_session_completion(
        profile.profile_id, payload.session_id, training_day
    )
    if not completion or str(completion.get("plan_id") or "") != str(plan["id"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session completion not found"
        )
    if str(completion.get("status") or "") not in _REVIEWABLE_COMPLETION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="session is not eligible for feedback",
        )
    phase = _optional_context(
        "camp_phase",
        "",
        lambda: _camp_phase(plan, training_day),
    )
    return plan, completion, phase


def _session_completion_snapshot(completion: Mapping[str, Any]) -> dict[str, Any]:
    """What the athlete logged when finishing the session, for review context."""

    return {
        key: completion.get(key)
        for key in ("status", "session_rpe", "pain_after", "modification_reason", "training_day")
        if completion.get(key) not in (None, "")
    }


def submit_session_feedback(
    store: AppStore,
    profile: ProfileRecord,
    payload: SessionFeedbackRequest,
    request: Request,
    raw_screenshot: bytes | None,
) -> FeedbackRecord:
    """Persist the quick review shown after a completed session.

    Upserts on the session's context key so re-answering corrects the record
    instead of stacking duplicates. A replacement screenshot is uploaded before
    the row is written and the superseded image is purged afterwards, so a
    failed write never leaves the row pointing at a deleted file.
    """

    plan, completion, phase = _session_context(store, profile, payload)
    structured = payload.structured_response()
    if not structured and not payload.comment and raw_screenshot is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="answer at least one question or add a comment",
        )

    context_key = f"session:{plan['id']}:{payload.session_id}:{completion['training_day']}"
    existing = store.get_context_feedback(profile.profile_id, context_key) or {}
    previous_screenshot_path = str(existing.get("screenshot_path") or "") or None

    # Only screenshot uploads are rate limited here. The row itself is bounded
    # by the athlete's own logged completions, so the report allowance is left
    # for the free-form reporting surface; storage writes still need a ceiling.
    screenshot: SanitisedScreenshot | None = None
    screenshot_path: str | None = None
    if raw_screenshot is not None:
        _rate_limit_or_raise(store, profile.profile_id, has_screenshot=True)
        screenshot = sanitise_screenshot(raw_screenshot)
        screenshot_path = f"{profile.profile_id}/session-{uuid.uuid4()}.{screenshot.extension}"
        store.upload_feedback_screenshot(screenshot_path, screenshot.data, screenshot.mime)

    row_payload: dict[str, Any] = {
        "submitted_by_profile_id": profile.profile_id,
        "context_key": context_key,
        "surface": "session",
        "category": "session_review",
        "response": None,
        "reason": None,
        "comment": payload.comment,
        "structured_response": structured,
        "contact_allowed": False,
        "priority": "normal",
        "plan_id": plan["id"],
        "today_checkin_id": None,
        "session_id": payload.session_id,
        "camp_phase": phase or None,
        "readiness_snapshot": _session_completion_snapshot(completion),
        "injury_snapshot": _optional_context(
            "injury_flags",
            {"open_flags": []},
            lambda: _injury_snapshot(store, profile.profile_id),
        ),
        "app_version": app_version(),
        "technical_context": technical_context(request),
    }
    if screenshot is not None:
        row_payload.update(
            {
                "screenshot_path": screenshot_path,
                "screenshot_mime": screenshot.mime,
                "screenshot_size_bytes": len(screenshot.data),
                "screenshot_width": screenshot.width,
                "screenshot_height": screenshot.height,
                "screenshot_expires_at": (
                    datetime.now(timezone.utc) + timedelta(days=screenshot_retention_days())
                ).isoformat(),
                "screenshot_deleted_at": None,
            }
        )

    try:
        row = store.upsert_context_feedback(row_payload)
    except Exception:
        if screenshot is not None and screenshot_path:
            _purge_screenshot(store, screenshot_path, reason="rollback")
        raise

    # The row now points at the new image, so the superseded one is unreferenced.
    if screenshot is not None and previous_screenshot_path:
        _purge_screenshot(store, previous_screenshot_path, reason="replaced")
    return _feedback_record(row)


def _purge_screenshot(store: AppStore, path: str, *, reason: str) -> None:
    try:
        store.delete_feedback_screenshots([path])
    except Exception as exc:
        logger.error(
            "[feedback] screenshot_cleanup_failed operation=%s error_class=%s",
            reason,
            type(exc).__name__,
        )


def _rate_limit_or_raise(store: AppStore, profile_id: str, *, has_screenshot: bool) -> None:
    allowed, blocked_scope, retry_after = store.claim_feedback_rate_limit(
        profile_id,
        report_limit=report_limit_per_hour(),
        screenshot_limit=screenshot_limit_per_hour(),
        has_screenshot=has_screenshot,
    )
    if allowed:
        return
    code = "screenshot_rate_limited" if blocked_scope == "screenshot" else "feedback_rate_limited"
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": code, "message": "Please wait before sending more feedback."},
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _global_programme_context(
    store: AppStore,
    profile: ProfileRecord,
) -> tuple[str | None, str | None, str | None, dict[str, Any], dict[str, Any]]:
    if profile.role not in {"athlete", "admin"}:
        return None, None, None, {}, {}
    injuries = _optional_context(
        "injury_flags",
        {"open_flags": []},
        lambda: _injury_snapshot(store, profile.profile_id),
    )
    plan_id = _optional_context(
        "active_plan",
        None,
        lambda: store.get_feedback_active_plan_id(profile.profile_id),
    )
    if not plan_id:
        return None, None, None, {}, injuries
    plan = _optional_context(
        "plan",
        None,
        lambda: store.get_feedback_plan_for_owner(plan_id, profile.profile_id),
    )
    if not plan:
        return None, None, None, {}, injuries
    training_day = resolve_training_day(profile.athlete_timezone)
    checkin = _optional_context(
        "today_checkin",
        None,
        lambda: store.get_feedback_today_checkin(profile.profile_id, plan_id, training_day),
    )
    phase = _optional_context(
        "camp_phase",
        str((checkin or {}).get("phase") or "") or None,
        lambda: _camp_phase(plan, training_day, (checkin or {}).get("phase")) or None,
    )
    readiness = (
        {key: checkin.get(key) for key in _READINESS_FIELDS if key in checkin}
        if checkin
        else {}
    )
    return (
        str(plan["id"]),
        str(checkin["id"]) if checkin else None,
        phase,
        readiness,
        injuries,
    )


def submit_global_feedback(
    store: AppStore,
    profile: ProfileRecord,
    payload: GlobalFeedbackRequest,
    request: Request,
    raw_screenshot: bytes | None,
) -> FeedbackRecord:
    has_screenshot = raw_screenshot is not None
    _rate_limit_or_raise(store, profile.profile_id, has_screenshot=has_screenshot)
    plan_id, checkin_id, phase, readiness, injuries = _global_programme_context(store, profile)

    feedback_id = str(uuid.uuid4())
    screenshot: SanitisedScreenshot | None = None
    screenshot_path: str | None = None
    if raw_screenshot is not None:
        screenshot = sanitise_screenshot(raw_screenshot)
        screenshot_path = f"{profile.profile_id}/{feedback_id}.{screenshot.extension}"

    priority = "safety" if payload.category == "safety_issue" else "normal"
    try:
        row_payload: dict[str, Any] = {
            "id": feedback_id,
            "submitted_by_profile_id": profile.profile_id,
            "context_key": f"global:{feedback_id}",
            "surface": "global",
            "category": payload.category,
            "response": None,
            "reason": None,
            "comment": payload.description,
            "contact_allowed": payload.contact_allowed,
            "priority": priority,
            "plan_id": plan_id,
            "today_checkin_id": checkin_id,
            "camp_phase": phase,
            "readiness_snapshot": readiness,
            "injury_snapshot": injuries,
            "app_version": app_version(),
            "technical_context": technical_context(request),
            "screenshot_path": screenshot_path,
            "screenshot_mime": screenshot.mime if screenshot else None,
            "screenshot_size_bytes": len(screenshot.data) if screenshot else None,
            "screenshot_width": screenshot.width if screenshot else None,
            "screenshot_height": screenshot.height if screenshot else None,
            "screenshot_expires_at": (
                datetime.now(timezone.utc) + timedelta(days=screenshot_retention_days())
            ).isoformat() if screenshot else None,
        }
        if screenshot_path and screenshot:
            store.upload_feedback_screenshot(screenshot_path, screenshot.data, screenshot.mime)
        row = store.insert_global_feedback(row_payload)
    except Exception as exc:
        if screenshot_path:
            try:
                store.delete_feedback_screenshots([screenshot_path])
            except Exception as cleanup_exc:
                logger.error(
                    "[feedback] screenshot_cleanup_failed feedback_id=%s operation=rollback error_class=%s",
                    feedback_id,
                    type(cleanup_exc).__name__,
                )
        logger.error(
            "[feedback] route_failed request_id=%s feedback_id=%s surface=global category=%s priority=%s screenshot_present=%s error_code=feedback_persist_failed error_class=%s",
            getattr(request.state, "request_id", ""),
            feedback_id,
            payload.category,
            priority,
            has_screenshot,
            type(exc).__name__,
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="feedback could not be saved",
        ) from None
    return _feedback_record(row)
