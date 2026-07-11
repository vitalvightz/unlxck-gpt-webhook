"""Shared weekly-schedule resolution for the persisted plan.

Single derivation of "which schedule week contains today" and "today's / the
next scheduled day" from a persisted plan row. Both the daily dashboard routes
(``api/routes/daily.py``) and the Today service (``api/services/today_service.py``)
import this module normally — it lives below the route layer precisely so
neither side needs a lazy route import to share the logic.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

from fastapi import HTTPException

from api.models import WeeklyDayEntry, WeeklySchedule
from api.plan_mappers import _map_weekly_schedule, _visible_plans_for_athlete
from api.store import AppStore

_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Structured cards always carry a headline, including motivational and advisory
# copy. A synthetic ``scheduled_session`` (the Today service's representation of
# a headline-only day) therefore needs affirmative work language before it can
# count as scheduled training. Explicit session objects use their real
# ``session_type`` and bypass this headline gate.
_STRUCTURED_REST_HEADLINE_RE = re.compile(
    r"^(?:full\s+|complete\s+|total\s+)?(?:rest|off|no\s+training|day\s+off|travel)\b",
    re.I,
)
_STRUCTURED_WORK_HEADLINE_RE = re.compile(
    r"\b(coach|spar|technical|boxing|pad\s?work|pads|mitts?|skill|primer|"
    r"strength|conditioning|mobility|reset|fight\s+day|protocol|rhythm|flush|"
    r"breath(?:ing)?|downshift|(?:easy|recovery)\s+walk|visuali[sz](?:e|ation)|"
    r"cue\s+card|mindset\s+(?:reset|work)|movement\s+quality|shadowbox|footwork|"
    r"tactical\s+(?:watch|review)|film\s+(?:review|study))\b",
    re.I,
)


def parse_iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except (ValueError, AttributeError):
        return None


def latest_visible_plan_row(store: AppStore, athlete_id: str) -> dict[str, Any] | None:
    return next(iter(_visible_plans_for_athlete(store.list_user_plans(athlete_id))), None)


def weekly_schedule_or_none(plan_row: Mapping[str, Any], *, week_index: int) -> WeeklySchedule | None:
    try:
        return _map_weekly_schedule(plan_row, week_index=week_index)
    except HTTPException:
        return None


def resolve_current_week(plan_row: Mapping[str, Any], *, today: date) -> tuple[int | None, WeeklySchedule | None]:
    """Find the schedule week containing today.

    Prefers calendar dates (set when a fight date exists); falls back to weeks
    elapsed since the plan was created for open-ended camps.
    """
    first_week = weekly_schedule_or_none(plan_row, week_index=0)
    if first_week is None:
        return None, None
    week_count = max(1, first_week.week_count)

    candidate = first_week
    for index in range(week_count):
        week = candidate if index == 0 else weekly_schedule_or_none(plan_row, week_index=index)
        if week is None:
            break
        dated = [d for d in week.days if d.calendar_date]
        if dated:
            dates = [parse_iso_date(d.calendar_date) for d in dated]
            dates = [d for d in dates if d is not None]
            if dates and min(dates) <= today <= max(dates):
                return index, week
        else:
            # No calendar dates anywhere — fall back to elapsed weeks.
            created = parse_iso_date(plan_row.get("created_at"))
            elapsed_weeks = ((today - created).days // 7) if created else 0
            fallback_index = min(max(0, elapsed_weeks), week_count - 1)
            fallback_week = (
                week if fallback_index == index else weekly_schedule_or_none(plan_row, week_index=fallback_index)
            )
            return (fallback_index, fallback_week) if fallback_week else (index, week)
    # Dated plan but today is outside every week (camp over or not started):
    # clamp to the nearest end.
    last_week = weekly_schedule_or_none(plan_row, week_index=week_count - 1)
    if last_week is not None:
        last_dates = [parse_iso_date(d.calendar_date) for d in last_week.days if d.calendar_date]
        last_dates = [d for d in last_dates if d is not None]
        if last_dates and today > max(last_dates):
            return week_count - 1, last_week
    return 0, first_week


def _headline_only_entry_is_scheduled(*, status: Any, title: Any) -> bool:
    """Validate the Today service's synthetic headline-only session entry.

    ``scheduled_session`` means no structured session object existed and the
    entry was inferred from ``today_card.headline``. Unknown prose is not enough
    evidence of prescribed work: an explicit support/training phrase is required,
    and a rest/off prefix always wins even if later text mentions mobility.
    """
    if str(status or "").strip().lower() != "scheduled_session":
        return True
    headline = str(title or "").strip()
    if not headline or _STRUCTURED_REST_HEADLINE_RE.search(headline):
        return False
    return _STRUCTURED_WORK_HEADLINE_RE.search(headline) is not None


def has_scheduled_day_content(entry: Any) -> bool:
    """True when a day entry carries real training (not a rest/off day).

    Accepts both ``WeeklyDayEntry`` models and the plain mappings the Today
    service derives from structured plans.
    """
    if entry is None:
        return False
    if isinstance(entry, Mapping):
        status = entry.get("status")
        title = entry.get("title")
        coach_note = entry.get("coach_note")
        effective_load = entry.get("effective_load")
    else:
        status = getattr(entry, "status", None)
        title = getattr(entry, "title", None)
        coach_note = getattr(entry, "coach_note", None)
        effective_load = getattr(entry, "effective_load", None)
    if not _headline_only_entry_is_scheduled(status=status, title=title):
        return False
    if isinstance(effective_load, str):
        effective_load = effective_load.strip().lower()
    if effective_load in {"none", "off", "rest"}:
        return False
    return bool(effective_load not in (None, "") or status or coach_note)


def resolve_today_and_next(
    week: WeeklySchedule | None, *, today: date
) -> tuple[WeeklyDayEntry | None, WeeklyDayEntry | None]:
    if week is None or not week.days:
        return None, None
    today_entry: WeeklyDayEntry | None = None
    today_index: int | None = None
    for index, entry in enumerate(week.days):
        entry_date = parse_iso_date(entry.calendar_date) if entry.calendar_date else None
        if entry_date == today or (entry_date is None and entry.weekday == _WEEKDAY_NAMES[today.weekday()]):
            today_entry = entry
            today_index = index
            break
    next_entry: WeeklyDayEntry | None = None
    future_dated_entries: list[tuple[date, WeeklyDayEntry]] = []
    for entry in week.days:
        if not has_scheduled_day_content(entry):
            continue
        entry_date = parse_iso_date(entry.calendar_date) if entry.calendar_date else None
        if entry_date is not None and entry_date > today:
            future_dated_entries.append((entry_date, entry))
    if future_dated_entries:
        future_dated_entries.sort(key=lambda item: item[0])
        return today_entry, future_dated_entries[0][1]

    if today_index is not None:
        for entry in week.days[today_index + 1:]:
            if has_scheduled_day_content(entry):
                next_entry = entry
                break
    return today_entry, next_entry
