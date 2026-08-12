"""Session-timed coaching notifications driven by the Today command view."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from api.contracts.command_view import CommandView
from api.notification_models import NotificationPreferences
from api.services.notification_foundation import (
    NotificationCandidate,
    get_notification_preferences,
    select_notification_candidate,
)
from api.services.push_notifications import dispatch_push_candidate
from api.services.notification_timing import resolve_training_time
from api.services.today_readiness_boundary import build_today_command_view
from api.store import AppStore

logger = logging.getLogger(__name__)

SESSION_REMINDER_LEAD = timedelta(minutes=30)
SESSION_REMINDER_GRACE = timedelta(minutes=15)
STOP_WINDOW_START_HOUR = 7
STOP_WINDOW_END_HOUR = 22
TRAINING_DAY_ROLLOVER_HOUR = 3


@dataclass(frozen=True)
class SessionTimingDispatchResult:
    notification_type: str
    delivered_count: int


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or "UTC")
    except Exception:  # noqa: BLE001 - subscription timezone is untrusted metadata
        return ZoneInfo("UTC")


def _local_now(now_utc: datetime, timezone_name: str) -> datetime:
    return _aware_utc(now_utc).astimezone(_timezone(timezone_name))


def _preferred_training_at(
    view: CommandView,
    preferences: NotificationPreferences,
    *,
    timezone_name: str,
) -> datetime | None:
    value = preferences.preferred_training_time
    if not value:
        return None
    try:
        hour, minute = (int(part) for part in value.split(":"))
        training_day = datetime.fromisoformat(view.today.training_day)
    except (TypeError, ValueError):
        return None

    # UNLXCK's training day rolls at 03:00. Therefore, a saved time between
    # 00:00 and 02:59 belongs to the following calendar date while remaining
    # part of the previous training day.
    if hour < TRAINING_DAY_ROLLOVER_HOUR:
        training_day += timedelta(days=1)

    local_tz = _timezone(timezone_name)
    return training_day.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
        tzinfo=local_tz,
    )


def _next_quiet_start_utc(
    now_utc: datetime,
    timezone_name: str,
    preferences: NotificationPreferences,
) -> datetime | None:
    if not preferences.quiet_hours_enabled:
        return None
    local_now = _local_now(now_utc, timezone_name)
    hour, minute = (int(part) for part in preferences.quiet_hours_start.split(":"))
    quiet_start = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if quiet_start <= local_now:
        quiet_start += timedelta(days=1)
    return quiet_start.astimezone(timezone.utc)


def _bound_expiry(
    candidate: NotificationCandidate,
    preferences: NotificationPreferences,
    *,
    now_utc: datetime,
) -> NotificationCandidate:
    quiet_start = _next_quiet_start_utc(now_utc, candidate.timezone_name, preferences)
    if quiet_start is None or quiet_start >= candidate.expires_at:
        return candidate
    return replace(candidate, expires_at=quiet_start)


def _has_today_session(view: CommandView) -> bool:
    return bool(
        str(view.active_plan.get("id") or "").strip()
        and view.today.session_scope == "today"
        and view.today.completion_status not in {"done", "modified", "skipped", "started"}
    )


def _decision_tier(view: CommandView) -> str:
    return str(getattr(view.today, "decision_tier", "") or "").strip().lower()


def _recommendation_state(view: CommandView) -> str:
    return str(view.today.recommendation_state or "").strip().lower()


def _session_title(view: CommandView) -> str:
    session = view.today.next_session or {}
    return str(session.get("title") or session.get("name") or "today's session").strip()


def _session_id(view: CommandView) -> str:
    session = view.today.next_session or {}
    return str(session.get("session_id") or session.get("id") or "").strip()


def _stop_candidate(
    view: CommandView,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> NotificationCandidate | None:
    local_now = _local_now(now_utc, timezone_name)
    if not _has_today_session(view):
        return None
    if _recommendation_state(view) == "not_checked_in":
        return None
    if _decision_tier(view) != "stop":
        return None
    if not (STOP_WINDOW_START_HOUR <= local_now.hour < STOP_WINDOW_END_HOUR):
        return None
    local_end = local_now.replace(
        hour=STOP_WINDOW_END_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    return NotificationCandidate(
        profile_id=profile_id,
        notification_type="session_stop",
        category="session_reminders",
        priority=5,
        title="No training today",
        body="A safety flag changed the call. Open Today and follow the instruction.",
        url="/today#today-command",
        tag="session-stop",
        dedupe_key=f"session-stop:{view.today.training_day}",
        expires_at=min(_aware_utc(now_utc) + timedelta(hours=2), local_end.astimezone(timezone.utc)),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
        intent="session_stop",
        training_day=view.today.training_day,
        action_key=f"acknowledge-stop:{_session_id(view) or view.today.training_day}",
        notification_class="safety",
        daily_cap=2,
        min_spacing_minutes=30,
    )


def _timed_session_candidate(
    view: CommandView,
    preferences: NotificationPreferences,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
    store: AppStore | None = None,
) -> NotificationCandidate | None:
    if not _has_today_session(view):
        return None
    state = _recommendation_state(view)
    if state == "not_checked_in" or _decision_tier(view) == "stop":
        return None
    timing = resolve_training_time(
        store or object(),  # type: ignore[arg-type]
        view,
        preferences,
        profile_id=profile_id,
        timezone_name=timezone_name,
    )
    preferred_at = timing.resolved_training_time
    local_now = _local_now(now_utc, timezone_name)

    # At exactly 03:00 the new training day does not exist until rollover, so a
    # GREEN/MODIFY/PULL BACK decision cannot truthfully be current at 02:30. A
    # 03:00 session is therefore eligible from 03:00 onward, while every other
    # saved time keeps the normal 30-minute lead.
    is_rollover_session = (
        preferred_at.hour == TRAINING_DAY_ROLLOVER_HOUR and preferred_at.minute == 0
    )
    window_start = preferred_at if is_rollover_session else preferred_at - SESSION_REMINDER_LEAD
    window_end = preferred_at + SESSION_REMINDER_GRACE
    if not (window_start <= local_now < window_end):
        return None

    session_title = _session_title(view)
    if state in {"modify", "pull_back"} or _decision_tier(view) in {"modify", "pull_back"}:
        notification_type = "session_modified"
        title = "I've adjusted today's work"
        body = "The session is still useful. Open it and see what changed."
        tag = "session-modified"
    else:
        notification_type = "session_ready"
        title = "Today's work is set"
        body = (
            f"{session_title[:45]}. Open it when you're ready."
            if timing.allows_exact_copy
            else f"{session_title[:30]}. Training is later. Open the call before you start."
        )
        tag = "session-ready"

    return NotificationCandidate(
        profile_id=profile_id,
        notification_type=notification_type,
        category="session_reminders",
        priority=25,
        title=title,
        body=body,
        url="/today#today-session",
        tag=tag,
        dedupe_key=f"{notification_type}:{view.today.training_day}",
        expires_at=window_end.astimezone(timezone.utc),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
        intent=notification_type,
        training_day=view.today.training_day,
        scheduled_for=preferred_at.astimezone(timezone.utc),
        timing_source=timing.timing_source,
        timing_confidence=timing.timing_confidence,  # type: ignore[arg-type]
        action_key=f"complete-session:{_session_id(view) or view.today.training_day}",
        notification_class="event" if notification_type == "session_modified" else "routine",
    )


def build_session_timing_candidates_from_view(
    view: CommandView,
    preferences: NotificationPreferences,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
    store: AppStore | None = None,
) -> list[NotificationCandidate]:
    candidates = [
        _stop_candidate(
            view,
            profile_id=profile_id,
            timezone_name=timezone_name,
            now_utc=now_utc,
        ),
        _timed_session_candidate(
            view,
            preferences,
            profile_id=profile_id,
            timezone_name=timezone_name,
            now_utc=now_utc,
            store=store,
        ),
    ]
    return [candidate for candidate in candidates if candidate is not None]


def dispatch_session_timing_notification(
    store: AppStore,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> SessionTimingDispatchResult | None:
    try:
        preferences = get_notification_preferences(store, profile_id)
        if not preferences.push_enabled or not preferences.session_reminders:
            return None
        view = build_today_command_view(
            store,
            athlete_id=profile_id,
            athlete_timezone=timezone_name,
            now=now_utc,
        )
        candidates = build_session_timing_candidates_from_view(
            view,
            preferences,
            profile_id=profile_id,
            timezone_name=timezone_name,
            now_utc=now_utc,
            store=store,
        )
        selected = select_notification_candidate(candidates, preferences, now_utc=now_utc)
    except Exception:  # noqa: BLE001 - one profile must not break the worker sweep
        logger.exception("[notification] session timing resolution failed profile_id=%s", profile_id)
        return None
    if selected is None:
        return None
    selected = _bound_expiry(selected, preferences, now_utc=now_utc)
    if selected.expires_at <= _aware_utc(now_utc):
        return None
    delivered = dispatch_push_candidate(store, selected, now_utc=now_utc)
    return SessionTimingDispatchResult(
        notification_type=selected.notification_type,
        delivered_count=delivered,
    )


__all__ = [
    "SessionTimingDispatchResult",
    "build_session_timing_candidates_from_view",
    "dispatch_session_timing_notification",
]
