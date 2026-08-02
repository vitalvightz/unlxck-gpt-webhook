"""State-aware coaching notification candidates for Today.

The Today command view remains the source of truth. This module does not rebuild
readiness or injury rules; it translates already-derived state into at most one
useful coach interruption. Silence is the default when no action changes today's
decision or completes an unfinished training record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from api.contracts.command_view import CommandView
from api.services.notification_foundation import (
    NotificationCandidate,
    NotificationStoreError,
    get_notification_preferences,
    select_notification_candidate,
)
from api.services.push_notifications import dispatch_push_candidate
from api.services.today_readiness_boundary import build_today_command_view
from api.store import AppStore

logger = logging.getLogger(__name__)

MORNING_START_HOUR = 7
MORNING_END_HOUR = 11
SESSION_LOG_START_HOUR = 12
SESSION_LOG_END_HOUR = 22
SESSION_LOG_MIN_AGE = timedelta(minutes=90)
HIGH_PAIN_FOLLOWUP_MAX_AGE = timedelta(hours=36)
TERMINAL_COMPLETION_STATUSES = frozenset({"done", "modified", "skipped"})
MORNING_NOTIFICATION_TYPES = frozenset(
    {"injury_recheck", "high_pain_followup", "readiness_checkin"}
)


@dataclass(frozen=True)
class CoachingDispatchResult:
    notification_type: str
    delivered_count: int


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware_utc(parsed)


def _local_now(now_utc: datetime, timezone_name: str) -> datetime:
    reference = _aware_utc(now_utc)
    try:
        return reference.astimezone(ZoneInfo(timezone_name or "UTC"))
    except Exception:  # noqa: BLE001 - device timezone is untrusted metadata
        return reference.astimezone(timezone.utc)


def _local_day_of(value: Any, timezone_name: str) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return _local_now(parsed, timezone_name).date().isoformat()


def _active_plan(view: CommandView) -> bool:
    return bool(str(view.active_plan.get("id") or "").strip())


def _today_is_finished(view: CommandView) -> bool:
    return str(view.today.completion_status or "") in TERMINAL_COMPLETION_STATUSES


def _morning_window(local_now: datetime) -> bool:
    return MORNING_START_HOUR <= local_now.hour < MORNING_END_HOUR


def _session_log_window(local_now: datetime) -> bool:
    return SESSION_LOG_START_HOUR <= local_now.hour < SESSION_LOG_END_HOUR


def _active_injuries(view: CommandView) -> list[dict[str, Any]]:
    return [
        dict(injury)
        for injury in view.open_injuries
        if str(injury.get("status") or "").strip().lower() in {"open", "monitoring"}
    ]


def _injury_rank(injury: Mapping[str, Any]) -> tuple[int, int, str]:
    surface_rank = {
        "surface_medical_review": 5,
        "surface_no_contact": 4,
        "surface_local_restriction": 3,
        "stable_surface": 0,
        "": 0,
    }.get(str(injury.get("surface_class") or ""), 0)
    severity_rank = {"severe": 3, "moderate": 2, "mild": 1}.get(
        str(injury.get("severity") or "").strip().lower(),
        0,
    )
    worse_rank = 2 if str(injury.get("latest_reported_status") or "").lower() == "worse" else 0
    return surface_rank + worse_rank, severity_rank, str(injury.get("id") or "")


def _injury_needs_recheck(
    injury: Mapping[str, Any],
    *,
    local_day: str,
    timezone_name: str,
) -> bool:
    surface_class = str(injury.get("surface_class") or "")
    latest_status = str(injury.get("latest_reported_status") or "").strip().lower()
    severity = str(injury.get("severity") or "").strip().lower()
    actionable = (
        latest_status == "worse"
        or severity == "severe"
        or surface_class
        in {"surface_local_restriction", "surface_no_contact", "surface_medical_review"}
    )
    if not actionable:
        return False
    # A response already recorded today must not immediately trigger another
    # "how is it?" notification. Silence means unchanged until tomorrow.
    updated_day = _local_day_of(
        injury.get("updated_at") or injury.get("created_at"),
        timezone_name,
    )
    return updated_day != local_day


def _injury_copy(injury: Mapping[str, Any]) -> tuple[str, str]:
    surface_class = str(injury.get("surface_class") or "")
    if surface_class == "surface_medical_review":
        return (
            "Get the injury checked",
            "Get it checked before training. Update me when you know the next step.",
        )
    if surface_class == "surface_no_contact":
        return (
            "No contact until it closes",
            "Update the wound before we clear contact.",
        )
    if surface_class == "surface_local_restriction":
        return (
            "Protect it before training",
            "Update the wound if it has changed.",
        )
    return (
        "Update the injury first",
        "Tell me if it is easing or worse before we set today's load.",
    )


def _injury_candidate(
    view: CommandView,
    *,
    profile_id: str,
    timezone_name: str,
    local_now: datetime,
    now_utc: datetime,
) -> NotificationCandidate | None:
    if not _morning_window(local_now):
        return None
    if not _active_plan(view) or view.today.session_scope != "today":
        return None
    if view.today.recommendation_state != "not_checked_in" or _today_is_finished(view):
        return None

    injuries = [
        injury
        for injury in _active_injuries(view)
        if _injury_needs_recheck(
            injury,
            local_day=local_now.date().isoformat(),
            timezone_name=timezone_name,
        )
    ]
    if not injuries:
        return None
    injury = max(injuries, key=_injury_rank)
    title, body = _injury_copy(injury)
    injury_id = str(injury.get("id") or "tracked").strip() or "tracked"
    return NotificationCandidate(
        profile_id=profile_id,
        notification_type="injury_recheck",
        category="injury_followups",
        priority=10,
        title=title,
        body=body,
        url="/today#today-injury",
        tag=f"injury-recheck-{injury_id}"[:80],
        dedupe_key=f"injury-recheck:{injury_id}:{local_now.date().isoformat()}",
        expires_at=now_utc + timedelta(hours=4),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
    )


def _recent_high_pain_completion(
    store: AppStore,
    profile_id: str,
    *,
    training_day: str,
    now_utc: datetime,
) -> dict[str, Any] | None:
    try:
        rows = store.list_session_completions(profile_id, limit=6)
    except Exception:  # noqa: BLE001 - missing context means silence, never a guess
        logger.exception("[notification] high-pain completion read failed profile_id=%s", profile_id)
        return None
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("training_day") or "") == training_day:
            continue
        if str(row.get("status") or "") not in {"done", "modified"}:
            continue
        try:
            pain_after = int(row.get("pain_after"))
        except (TypeError, ValueError):
            continue
        if pain_after < 7:
            continue
        completed_at = _parse_datetime(row.get("completed_at"))
        if completed_at is not None:
            age = _aware_utc(now_utc) - completed_at
            if age < timedelta(0) or age > HIGH_PAIN_FOLLOWUP_MAX_AGE:
                continue
        return dict(row)
    return None


def _high_pain_candidate(
    store: AppStore,
    view: CommandView,
    *,
    profile_id: str,
    timezone_name: str,
    local_now: datetime,
    now_utc: datetime,
) -> NotificationCandidate | None:
    if not _morning_window(local_now):
        return None
    if not _active_plan(view) or view.today.recommendation_state != "not_checked_in":
        return None
    if _today_is_finished(view):
        return None
    completion = _recent_high_pain_completion(
        store,
        profile_id,
        training_day=view.today.training_day,
        now_utc=now_utc,
    )
    if completion is None:
        return None
    source = str(
        completion.get("id")
        or f"{completion.get('session_id') or 'session'}:{completion.get('training_day') or 'recent'}"
    )
    return NotificationCandidate(
        profile_id=profile_id,
        notification_type="high_pain_followup",
        category="injury_followups",
        priority=15,
        title="How did your body settle?",
        body="Check in before we decide today's load.",
        url="/today#today-checkin",
        tag="high-pain-followup",
        dedupe_key=f"high-pain-followup:{source}",
        expires_at=now_utc + timedelta(hours=4),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
    )


def _readiness_candidate(
    view: CommandView,
    *,
    profile_id: str,
    timezone_name: str,
    local_now: datetime,
    now_utc: datetime,
) -> NotificationCandidate | None:
    if not _morning_window(local_now):
        return None
    if not _active_plan(view) or view.today.session_scope != "today":
        return None
    if view.today.recommendation_state != "not_checked_in" or _today_is_finished(view):
        return None
    return NotificationCandidate(
        profile_id=profile_id,
        notification_type="readiness_checkin",
        category="checkin_reminders",
        priority=20,
        title="Check in before we train",
        body="Give me sleep, body and pain so I can set today's call.",
        url="/today#today-checkin",
        tag="readiness-checkin",
        dedupe_key=f"readiness-checkin:{view.today.training_day}",
        expires_at=now_utc + timedelta(hours=4),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
    )


def _session_id(view: CommandView) -> str:
    session = view.today.next_session or {}
    return str(session.get("session_id") or session.get("id") or "").strip()


def _started_completion(
    store: AppStore,
    view: CommandView,
    profile_id: str,
) -> dict[str, Any] | None:
    session_id = _session_id(view)
    if not session_id:
        return None
    try:
        row = store.get_session_completion(profile_id, session_id, view.today.training_day)
    except Exception:  # noqa: BLE001
        logger.exception("[notification] completion read failed profile_id=%s", profile_id)
        return None
    if not isinstance(row, Mapping) or str(row.get("status") or "") != "started":
        return None
    return dict(row)


def _session_log_candidate(
    store: AppStore,
    view: CommandView,
    *,
    profile_id: str,
    timezone_name: str,
    local_now: datetime,
    now_utc: datetime,
) -> NotificationCandidate | None:
    if not _session_log_window(local_now):
        return None
    if not _active_plan(view) or view.today.session_scope != "today":
        return None
    if view.today.completion_status != "started":
        return None
    completion = _started_completion(store, view, profile_id)
    if completion is None:
        return None
    started_at = _parse_datetime(completion.get("started_at"))
    if started_at is None:
        return None
    age = _aware_utc(now_utc) - started_at
    if age < SESSION_LOG_MIN_AGE:
        return None
    source = str(
        completion.get("id")
        or f"{completion.get('session_id') or _session_id(view)}:{view.today.training_day}"
    )
    return NotificationCandidate(
        profile_id=profile_id,
        notification_type="session_log_due",
        category="session_reminders",
        priority=30,
        title="Log the work while it's fresh",
        body="Add effort and pain so tomorrow's call has the full picture.",
        url="/today#today-session",
        tag="session-log-due",
        dedupe_key=f"session-log-due:{source}",
        expires_at=now_utc + timedelta(hours=4),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
    )


def build_coaching_candidates_from_view(
    store: AppStore,
    view: CommandView,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> list[NotificationCandidate]:
    """Translate a command view into actionable candidates, ordered by policy."""

    reference = _aware_utc(now_utc)
    local_now = _local_now(reference, timezone_name)
    builders = (
        lambda: _injury_candidate(
            view,
            profile_id=profile_id,
            timezone_name=timezone_name,
            local_now=local_now,
            now_utc=reference,
        ),
        lambda: _high_pain_candidate(
            store,
            view,
            profile_id=profile_id,
            timezone_name=timezone_name,
            local_now=local_now,
            now_utc=reference,
        ),
        lambda: _readiness_candidate(
            view,
            profile_id=profile_id,
            timezone_name=timezone_name,
            local_now=local_now,
            now_utc=reference,
        ),
        lambda: _session_log_candidate(
            store,
            view,
            profile_id=profile_id,
            timezone_name=timezone_name,
            local_now=local_now,
            now_utc=reference,
        ),
    )
    return [candidate for build in builders if (candidate := build()) is not None]


def build_coaching_candidates(
    store: AppStore,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> list[NotificationCandidate]:
    try:
        view = build_today_command_view(
            store,
            athlete_id=profile_id,
            athlete_timezone=timezone_name,
            now=now_utc,
        )
    except Exception:  # noqa: BLE001 - an incomplete command view must never create a guess
        logger.exception("[notification] Today command read failed profile_id=%s", profile_id)
        return []
    return build_coaching_candidates_from_view(
        store,
        view,
        profile_id=profile_id,
        timezone_name=timezone_name,
        now_utc=now_utc,
    )


def dispatch_coaching_notification(
    store: AppStore,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> CoachingDispatchResult | None:
    candidates = build_coaching_candidates(
        store,
        profile_id=profile_id,
        timezone_name=timezone_name,
        now_utc=now_utc,
    )
    if not candidates:
        return None
    try:
        preferences = get_notification_preferences(store, profile_id)
        selected = select_notification_candidate(candidates, preferences, now_utc=now_utc)
    except NotificationStoreError:
        return None
    if selected is None:
        return None
    delivered = dispatch_push_candidate(store, selected, now_utc=now_utc)
    return CoachingDispatchResult(
        notification_type=selected.notification_type,
        delivered_count=delivered,
    )


__all__ = [
    "CoachingDispatchResult",
    "MORNING_NOTIFICATION_TYPES",
    "build_coaching_candidates",
    "build_coaching_candidates_from_view",
    "dispatch_coaching_notification",
]
