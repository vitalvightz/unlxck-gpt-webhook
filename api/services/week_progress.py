"""Authoritative full-training-week detection and XP award orchestration."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

from api.services.progress_notifications import dispatch_progress_award_notification
from api.store import AppStore

logger = logging.getLogger(__name__)

COMPLETED_STATUSES = frozenset({"done", "modified"})
RESOLVED_STATUSES = frozenset({"done", "modified", "skipped"})
_TIMESTAMP_FIELDS = ("updated_at", "completed_at", "created_at")


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _row_timestamp(row: Mapping[str, Any]) -> datetime | None:
    for field in _TIMESTAMP_FIELDS:
        parsed = _parse_timestamp(row.get(field))
        if parsed is not None:
            return parsed
    return None


def _mapping_rows(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _weeks(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    structured = plan.get("structured_plan")
    if not isinstance(structured, Mapping):
        return []
    return _mapping_rows(structured.get("weeks"))


def _planned_session_ids(week: Mapping[str, Any]) -> set[str]:
    planned: set[str] = set()
    for day in _mapping_rows(week.get("days")):
        if str(day.get("day_type") or "").strip().lower() == "rest":
            continue
        for session in _mapping_rows(day.get("sessions")):
            session_id = str(session.get("session_id") or "").strip()
            if session_id:
                planned.add(session_id)
    return planned


def _latest_statuses(
    *,
    planned: set[str],
    completions: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], set[str]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in completions:
        session_id = str(row.get("session_id") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        if session_id in planned and status:
            grouped.setdefault(session_id, []).append(row)

    latest_by_session: dict[str, str] = {}
    ambiguous: set[str] = set()

    for session_id, rows in grouped.items():
        status_rows = [
            (str(row.get("status") or "").strip().lower(), _row_timestamp(row))
            for row in rows
            if str(row.get("status") or "").strip()
        ]
        statuses = {status for status, _ in status_rows}
        if len(statuses) == 1:
            latest_by_session[session_id] = next(iter(statuses))
            continue

        if any(timestamp is None for _, timestamp in status_rows):
            ambiguous.add(session_id)
            continue

        latest_timestamp = max(
            timestamp for _, timestamp in status_rows if timestamp is not None
        )
        latest_statuses = {
            status
            for status, timestamp in status_rows
            if timestamp == latest_timestamp
        }
        if len(latest_statuses) == 1:
            latest_by_session[session_id] = next(iter(latest_statuses))
        else:
            ambiguous.add(session_id)

    return latest_by_session, ambiguous


def find_week_for_training_day(
    plan: Mapping[str, Any],
    training_day: str,
) -> Mapping[str, Any] | None:
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
        return {
            "complete": False,
            "reason": "no_planned_sessions",
            "planned": 0,
            "resolved": 0,
            "ambiguous_session_ids": [],
        }

    latest_by_session, ambiguous = _latest_statuses(
        planned=planned,
        completions=completions,
    )
    unresolved = sorted(
        session_id
        for session_id in planned
        if latest_by_session.get(session_id) not in RESOLVED_STATUSES
    )
    unauthorised_skips = sorted(
        session_id
        for session_id in planned
        if latest_by_session.get(session_id) == "skipped"
    )
    complete = all(
        latest_by_session.get(session_id) in COMPLETED_STATUSES
        for session_id in planned
    )
    return {
        "complete": complete,
        "reason": "complete" if complete else "unresolved_or_skipped",
        "planned": len(planned),
        "resolved": len(planned) - len(unresolved),
        "unresolved_session_ids": unresolved,
        "skipped_session_ids": unauthorised_skips,
        "ambiguous_session_ids": sorted(ambiguous),
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

    completions = store.list_plan_session_completions(
        athlete_id,
        plan_id,
        limit=500,
    )
    relevant = [
        row
        for row in completions
        if start_date <= str(row.get("training_day") or "") <= end_date
    ]
    result = evaluate_week_completion(week=week, completions=relevant)
    if not result["complete"]:
        return None

    source_key = f"{plan_id}:{week_id}"
    award = store.award_xp(
        athlete_id,
        action="full_training_week_completed",
        idempotency_key=f"full-week:{source_key}",
    )
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
    except Exception:  # noqa: BLE001 - push must not block lifecycle persistence
        logger.exception(
            "[notification] week completion delivery failed athlete_id=%s plan_id=%s week_id=%s",
            athlete_id,
            plan_id,
            week_id,
        )

    try:
        # Local import avoids a module cycle: plan milestones reuse this module's
        # authoritative latest-completion evaluator for every week.
        from api.services.plan_milestones import (
            record_plan_milestones_after_completed_week,
        )

        record_plan_milestones_after_completed_week(
            store,
            athlete_id=athlete_id,
            athlete_timezone=athlete_timezone,
            plan=plan,
            completed_week=week,
            completions=completions,
        )
    except Exception:  # noqa: BLE001 - milestones must never break week/session XP
        logger.exception(
            "[xp] plan milestone evaluation failed athlete_id=%s plan_id=%s week_id=%s",
            athlete_id,
            plan_id,
            week_id,
        )
    return normalized


def try_award_completed_week_for_completion(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    completion: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Best-effort wrapper covering plan lookup, evaluation, XP and push."""

    plan_id = str(completion.get("plan_id") or "").strip()
    training_day = str(completion.get("training_day") or "").strip()
    if not plan_id or not training_day:
        return None

    try:
        plan = store.get_plan_for_athlete(plan_id, athlete_id)
        if not isinstance(plan, Mapping):
            return None
        return award_completed_week(
            store,
            athlete_id=athlete_id,
            athlete_timezone=athlete_timezone,
            plan=plan,
            training_day=training_day,
        )
    except Exception:  # noqa: BLE001 - week XP must never break session logging
        logger.exception(
            "[xp] week evaluation failed athlete_id=%s plan_id=%s training_day=%s",
            athlete_id,
            plan_id,
            training_day,
        )
        return None


__all__ = [
    "award_completed_week",
    "evaluate_week_completion",
    "find_week_for_training_day",
    "try_award_completed_week_for_completion",
]
