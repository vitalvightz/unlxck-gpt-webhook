"""Server-authoritative app, training-consistency and plan-adherence streaks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from api.services.active_plan import resolve_active_plan
from api.services.today_service import _structured_session_entry_for_day, resolve_training_day
from api.services.week_progress import COMPLETED_STATUSES, _latest_statuses, _plan_for_training_day
from api.store import AppStore


def _rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _read_state(store: AppStore, athlete_id: str) -> dict[str, Any]:
    custom = getattr(store, "get_athlete_streaks", None)
    if callable(custom):
        return dict(custom(athlete_id) or {})
    states = getattr(store, "athlete_streaks", None)
    if isinstance(states, Mapping):
        return dict(states.get(athlete_id) or {})
    response = (
        store.client.table("athlete_streaks").select("*")
        .eq("athlete_id", athlete_id).limit(1).execute()
    )
    rows = _rows(getattr(response, "data", None))
    return rows[0] if rows else {}


def _write_state(store: AppStore, athlete_id: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    custom = getattr(store, "upsert_athlete_streaks", None)
    if callable(custom):
        return dict(custom(athlete_id, dict(fields)))
    states = getattr(store, "athlete_streaks", None)
    if isinstance(states, dict):
        states[athlete_id] = {"athlete_id": athlete_id, **states.get(athlete_id, {}), **fields}
        return dict(states[athlete_id])
    response = (
        store.client.table("athlete_streaks")
        .upsert({"athlete_id": athlete_id, **fields}, on_conflict="athlete_id")
        .execute()
    )
    rows = _rows(getattr(response, "data", None))
    if not rows:
        raise RuntimeError("streak state write returned no row")
    return rows[0]


def _activity_dates(store: AppStore, athlete_id: str) -> set[date]:
    custom = getattr(store, "list_daily_activity", None)
    if callable(custom):
        rows = _rows(custom(athlete_id))
    else:
        activity = getattr(store, "athlete_daily_activity", None)
        if isinstance(activity, (set, list, tuple)):
            rows = [
                {"athlete_id": item[0], "activity_date": item[1]}
                for item in activity if isinstance(item, tuple) and len(item) == 2
            ]
        else:
            response = (
                store.client.table("athlete_daily_activity").select("activity_date")
                .eq("athlete_id", athlete_id).execute()
            )
            rows = _rows(getattr(response, "data", None))
    result: set[date] = set()
    for row in rows:
        if str(row.get("athlete_id") or athlete_id) != athlete_id:
            continue
        try:
            result.add(date.fromisoformat(str(row.get("activity_date"))))
        except ValueError:
            continue
    return result


def _insert_activity(
    store: AppStore, athlete_id: str, activity_day: date
) -> Mapping[str, Any] | None:
    custom = getattr(store, "record_daily_activity", None)
    if callable(custom):
        result = custom(athlete_id, activity_day.isoformat())
        return result if isinstance(result, Mapping) else None
    activity = getattr(store, "athlete_daily_activity", None)
    if isinstance(activity, set):
        activity.add((athlete_id, activity_day.isoformat()))
        return None
    (
        store.client.table("athlete_daily_activity")
        .upsert(
            {"athlete_id": athlete_id, "activity_date": activity_day.isoformat()},
            on_conflict="athlete_id,activity_date",
            ignore_duplicates=True,
        ).execute()
    )
    return None


def _public_state(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "login": {
            "current": max(0, int(row.get("login_current") or 0)),
            "best": max(0, int(row.get("login_best") or 0)),
            "last_active_date": row.get("login_last_active_date"),
        },
        "adherence": {
            # API key retained for the existing XP-card contract. The values are
            # the athlete-facing Training Streak, not plan adherence.
            "current": max(0, int(row.get("training_current") or 0)),
            "best": max(0, int(row.get("training_best") or 0)),
            "last_qualifying_day": row.get("training_last_qualifying_day"),
        },
        "plan_adherence": {
            "current": max(0, int(row.get("adherence_current") or 0)),
            "best": max(0, int(row.get("adherence_best") or 0)),
            "last_qualifying_day": row.get("adherence_last_qualifying_day"),
        },
    }


def reconcile_login_streak(store: AppStore, *, athlete_id: str, activity_day: date) -> dict[str, Any]:
    dates = _activity_dates(store, athlete_id)
    current = 0
    cursor = activity_day
    while cursor in dates:
        current += 1
        cursor -= timedelta(days=1)
    prior = _read_state(store, athlete_id)
    best = max(int(prior.get("login_best") or 0), current)
    return _write_state(store, athlete_id, {
        "login_current": current,
        "login_best": best,
        "login_last_active_date": max(dates).isoformat() if dates else None,
    })


def record_daily_activity(
    store: AppStore, *, athlete_id: str, athlete_timezone: str | None, now: datetime | None = None
) -> dict[str, Any]:
    """Record at most one activity row for the server-resolved effective day."""
    activity_day = date.fromisoformat(resolve_training_day(athlete_timezone, now=now))
    atomic_state = _insert_activity(store, athlete_id, activity_day)
    if atomic_state is not None:
        return _public_state(atomic_state)
    return _public_state(reconcile_login_streak(store, athlete_id=athlete_id, activity_day=activity_day))


def _scheduled_days(plan: Mapping[str, Any], training_day: str) -> list[tuple[date, set[str]]]:
    projected = _plan_for_training_day(plan, training_day)
    structured = projected.get("structured_plan")
    weeks = structured.get("weeks") if isinstance(structured, Mapping) else None
    result: list[tuple[date, set[str]]] = []
    for week in _rows(weeks):
        for day_row in _rows(week.get("days")):
            if str(day_row.get("day_type") or "").lower() == "rest":
                continue
            try:
                scheduled = date.fromisoformat(str(day_row.get("date")))
            except ValueError:
                continue
            ids = {str(row.get("session_id") or "").strip() for row in _rows(day_row.get("sessions"))}
            ids.discard("")
            if ids:
                result.append((scheduled, ids))
    return sorted(result)


def _training_schedule(plan: Mapping[str, Any], training_day: str) -> dict[date, set[str]]:
    """Expected training days and their canonical app-session identities."""
    projected = _plan_for_training_day(plan, training_day)
    structured = projected.get("structured_plan")
    weeks = structured.get("weeks") if isinstance(structured, Mapping) else None
    result: dict[date, set[str]] = {}
    for week in _rows(weeks):
        for day_row in _rows(week.get("days")):
            try:
                scheduled = date.fromisoformat(str(day_row.get("date")))
            except ValueError:
                continue
            ids = {
                str(session.get("session_id") or "").strip()
                for session in _rows(day_row.get("sessions"))
            }
            ids.discard("")
            # Sessionless coach/technical work is still expected training. The
            # Today projection owns the distinction between that and true rest.
            if ids or _structured_session_entry_for_day(day_row, week=week) is not None:
                result[scheduled] = ids
    return result


def _all_completions(store: AppStore, athlete_id: str) -> list[dict[str, Any]]:
    custom = getattr(store, "list_session_completions", None)
    if callable(custom):
        return _rows(custom(athlete_id, limit=500))
    return _rows(getattr(store, "completions", None))


def _session_logs(store: AppStore, athlete_id: str) -> list[dict[str, Any]]:
    custom = getattr(store, "list_session_logs", None)
    return _rows(custom(athlete_id, limit=500)) if callable(custom) else []


def qualifying_training_days(
    store: AppStore,
    *,
    athlete_id: str,
    today: date,
) -> tuple[set[date], set[date]]:
    """Return (completed training days, explicitly skipped expected days).

    Current session completions qualify only when tied to a canonical scheduled
    session, or to a sessionless coach/technical day in that completion's plan.
    Completed legacy/manual ``session_logs`` are authoritative actual training.
    """
    schedules: dict[str, dict[date, set[str]]] = {}
    qualifying: set[date] = set()
    skipped: set[date] = set()
    for row in _all_completions(store, athlete_id):
        if str(row.get("status") or "") not in {"done", "modified", "skipped"}:
            continue
        try:
            activity_day = date.fromisoformat(str(row.get("training_day")))
        except ValueError:
            continue
        plan_id = str(row.get("plan_id") or "")
        if plan_id not in schedules:
            plan = store.get_plan_for_athlete(plan_id, athlete_id) if plan_id else None
            schedules[plan_id] = _training_schedule(plan, today.isoformat()) if plan else {}
        expected_ids = schedules[plan_id].get(activity_day)
        session_id = str(row.get("session_id") or "").strip()
        # Before canonical identity was enforced, the supported Today flow used
        # the local day as its key for sessionless coach/technical cards. Accept
        # that narrow historical provenance for streak rebuild only; it remains
        # ineligible for XP and arbitrary ids still fail closed.
        legacy_sessionless = (
            expected_ids == set() and session_id == activity_day.isoformat()
        )
        legitimate = expected_ids is not None and (
            session_id in expected_ids or legacy_sessionless
        )
        if not legitimate:
            continue
        if row.get("status") == "skipped":
            skipped.add(activity_day)
        else:
            qualifying.add(activity_day)
    for row in _session_logs(store, athlete_id):
        if row.get("completed") is not True:
            continue
        try:
            qualifying.add(date.fromisoformat(str(row.get("session_date"))))
        except ValueError:
            continue
    return qualifying, skipped


def reconcile_training_streak(
    store: AppStore, *, athlete_id: str, athlete_timezone: str | None, now: datetime | None = None
) -> dict[str, Any]:
    """Rebuild actual-training consistency without awarding XP.

    Completed training advances once per athlete-local day. Expected training
    missed before today breaks the run. Genuine rest days are absent and neutral;
    an unresolved expected current day is also neutral.
    """
    today = date.fromisoformat(resolve_training_day(athlete_timezone, now=now))
    resolution = resolve_active_plan(store, athlete_id, current_training_day=today)
    plan = resolution.plan
    expected = set(_training_schedule(plan, today.isoformat())) if plan else set()
    qualifying, skipped = qualifying_training_days(
        store, athlete_id=athlete_id, today=today
    )
    current = best = 0
    last: date | None = None
    for activity_day in sorted(expected | qualifying | skipped):
        if activity_day > today:
            continue
        if activity_day in qualifying:
            current += 1
            best = max(best, current)
            last = activity_day
        elif activity_day < today or activity_day in skipped:
            current = 0
            last = None
    row = _write_state(store, athlete_id, {
        "training_current": current,
        "training_best": best,
        "training_last_qualifying_day": last.isoformat() if last else None,
    })
    return _public_state(row)


def reconcile_adherence_streak(
    store: AppStore, *, athlete_id: str, athlete_timezone: str | None, now: datetime | None = None
) -> dict[str, Any]:
    today = date.fromisoformat(resolve_training_day(athlete_timezone, now=now))
    resolution = resolve_active_plan(store, athlete_id, current_training_day=today)
    prior = _read_state(store, athlete_id)
    if resolution.plan is None:
        if resolution.source == "read_failure":
            return _public_state(prior)
        row = _write_state(store, athlete_id, {
            "adherence_current": 0,
            "adherence_best": max(0, int(prior.get("adherence_best") or 0)),
            "adherence_last_qualifying_day": None,
        })
        return _public_state(row)
    plan_id = str(resolution.plan.get("id") or "")
    completions = _rows(store.list_plan_session_completions(athlete_id, plan_id, limit=500))
    current = 0
    last_qualifying: date | None = None
    for scheduled, planned in _scheduled_days(resolution.plan, today.isoformat()):
        if scheduled > today:
            continue
        day_completions = [
            row for row in completions
            if str(row.get("training_day") or "") == scheduled.isoformat()
        ]
        statuses, ambiguous = _latest_statuses(planned=planned, completions=day_completions)
        qualifies = not ambiguous and all(statuses.get(item) in COMPLETED_STATUSES for item in planned)
        skipped = any(statuses.get(item) == "skipped" for item in planned)
        if qualifies:
            current += 1
            last_qualifying = scheduled
        elif scheduled < today or skipped:
            current = 0
            last_qualifying = None
        # An unresolved current day is still in progress and is neutral.
    best = max(int(prior.get("adherence_best") or 0), current)
    row = _write_state(store, athlete_id, {
        "adherence_current": current,
        "adherence_best": best,
        "adherence_last_qualifying_day": last_qualifying.isoformat() if last_qualifying else None,
    })
    return _public_state(row)


def get_streak_state(
    store: AppStore, *, athlete_id: str, athlete_timezone: str | None, now: datetime | None = None
) -> dict[str, Any]:
    """Read persisted streak state without recording activity or writing counters."""
    return _public_state(_read_state(store, athlete_id))


__all__ = ["get_streak_state", "qualifying_training_days", "record_daily_activity", "reconcile_adherence_streak", "reconcile_login_streak", "reconcile_training_streak"]
