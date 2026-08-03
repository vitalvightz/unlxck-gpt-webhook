"""Authoritative full-training-week detection and XP award orchestration."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from api.services.progress_notifications import dispatch_progress_award_notification
from api.store import AppStore

logger = logging.getLogger(__name__)

COMPLETED_STATUSES = frozenset({"done", "modified"})
RESOLVED_STATUSES = frozenset({"done", "modified", "skipped"})


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _weeks(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    structured = plan.get("structured_plan")
    if not isinstance(structured, Mapping):
        return []
    rows = structured.get("weeks")
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, Sequence) else []


def _planned_session_ids(week: Mapping[str, Any]) -> set[str]:
    planned: set[str] = set()
    days = week.get("days")
    if not isinstance(days, Sequence):
        return planned
    for day in days:
        if not isinstance(day, Mapping) or str(day.get("day_type") or "") == "rest":
            continue
        sessions = day.get("sessions")
        if not isinstance(sessions, Sequence):
            continue
        for session in sessions:
            if not isinstance(session, Mapping):
                continue
            session_id = str(session.get("session_id") or "").strip()
            if session_id:
                planned.add(session_id)
    return planned


def find_week_for_training_day(plan: Mapping[str, Any], training_day: str) -> Mapping[str, Any] | None:
    target = _parse_date(training_day)
    if target is None:
        return None
    for week in _weeks(plan):
        start = _parse_date(week.get("start_date"))
        end = _parse_date(week.get("end_date"))
        if start is not None and end is not None and start <= target <= end:
            return week
    return None


def evaluate_week_completion(
    *,
    week: Mapping[str, Any],
    completions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    planned = _planned_session_ids(week)
    if not planned:
        return {"complete": False, "reason": "no_planned_sessions", "planned": 0, "resolved": 0}

    latest_by_session: dict[str, str] = {}
    for row in completions:
        session_id = str(row.get("session_id") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        if session_id in planned and status:
            latest_by_session[session_id] = status

    unresolved = sorted(session_id for session_id in planned if latest_by_session.get(session_id) not in RESOLVED_STATUSES)
    unauthorised_skips = sorted(session_id for session_id in planned if latest_by_session.get(session_id) == "skipped")
    complete = not unresolved and not unauthorised_skips
    return {
        "complete": complete,
        "reason": "complete" if complete else "unresolved_or_skipped",
        "planned": len(planned),
        "resolved": len(planned) - len(unresolved),
        "unresolved_session_ids": unresolved,
        "skipped_session_ids": unauthorised_skips,
    }


def award_completed_week(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    plan: Mapping[str, Any],
    training_day: str,
) -> dict[str, Any] | None:
    week = find_week_for_training_day(plan, training_day)
    if week is None:
        return None
    plan_id = str(plan.get("id") or "").strip()
    week_id = str(week.get("week_id") or "").strip()
    start_date = str(week.get("start_date") or "").strip()
    end_date = str(week.get("end_date") or "").strip()
    if not plan_id or not week_id or not start_date or not end_date:
        return None

    completions = store.list_plan_session_completions(athlete_id, plan_id, limit=500)
    relevant = [
        row for row in completions
        if start_date <= str(row.get("training_day") or "") <= end_date
    ]
    result = evaluate_week_completion(week=week, completions=relevant)
    if not result["complete"]:
        return None

    source_key = f"{plan_id}:{week_id}"
    try:
        award = store.award_xp(
            athlete_id,
            action="full_training_week_completed",
            idempotency_key=f"full-week:{source_key}",
        )
    except Exception:  # noqa: BLE001 - week XP must not break session logging
        logger.exception("[xp] full week award failed athlete_id=%s source_key=%s", athlete_id, source_key)
        return None
    if not isinstance(award, Mapping):
        return None
    normalized = dict(award)
    try:
        dispatch_progress_award_notification(
            store,
            athlete_id=athlete_id,
            action="full_training_week_completed",
            award_result=normalized,
            source_key=source_key,
            timezone_name=athlete_timezone or "UTC",
        )
    except Exception:  # noqa: BLE001 - push must not break XP
        logger.exception("[notification] full week delivery failed athlete_id=%s", athlete_id)
    return normalized


__all__ = [
    "award_completed_week",
    "evaluate_week_completion",
    "find_week_for_training_day",
]
