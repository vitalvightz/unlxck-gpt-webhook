"""Calendar projection for renewable open training plans.

Open plans do not have an event countdown.  Their persisted structured card is
therefore a four-week template, and this module projects that template onto the
current renewable block from one stable compatibility anchor: the first Monday
on or after the plan was created.

The projection is deliberately strict.  Legacy cards are only assigned
weekdays when their day count and coach-owned pattern agree with the saved
``open_plan_spec.weekly_template``; ambiguous cards remain undated rather than
silently attaching a session to the wrong day.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date, timedelta
from typing import Any, Mapping


WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_WEEKDAY_ALIASES = {
    "mon": "Mon",
    "monday": "Mon",
    "tue": "Tue",
    "tues": "Tue",
    "tuesday": "Tue",
    "wed": "Wed",
    "wednesday": "Wed",
    "thu": "Thu",
    "thur": "Thu",
    "thurs": "Thu",
    "thursday": "Thu",
    "fri": "Fri",
    "friday": "Fri",
    "sat": "Sat",
    "saturday": "Sat",
    "sun": "Sun",
    "sunday": "Sun",
}
_COACH_LED_RE = re.compile(r"\b(coach|spar|boxing|pads?|mitts?|technical\s+only)\b", re.I)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except (ValueError, AttributeError):
        return None


def normalize_weekday(value: Any) -> str | None:
    return _WEEKDAY_ALIASES.get(str(value or "").strip().lower())


def _ordered_weekdays(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized = {day for value in values if (day := normalize_weekday(value))}
    return [day for day in WEEKDAYS if day in normalized]


def open_plan_spec(plan_row: Mapping[str, Any]) -> dict[str, Any] | None:
    if _parse_date(plan_row.get("fight_date")) is not None:
        return None
    planning_brief = _mapping(plan_row.get("planning_brief"))
    spec = planning_brief.get("open_plan_spec")
    if not isinstance(spec, Mapping) or spec.get("plan_type") != "open_ongoing_system":
        return None
    return dict(spec)


def schedule_mode(plan_row: Mapping[str, Any]) -> str:
    if _parse_date(plan_row.get("fight_date")) is not None:
        return "event_countdown"
    if open_plan_spec(plan_row) is not None:
        return "open_recurring"
    return "static_undated"


def open_plan_anchor_date(plan_row: Mapping[str, Any]) -> date | None:
    created = _parse_date(plan_row.get("created_at"))
    if created is None:
        return None
    return created + timedelta(days=(-created.weekday()) % 7)


def _coach_owned_days(template: Mapping[str, Any]) -> list[str]:
    coach_owned = template.get("coach_owned_days")
    coach_owned = coach_owned if isinstance(coach_owned, Mapping) else {}
    values: list[Any] = []
    for key in ("technical_skill_days", "hard_sparring_days"):
        raw = coach_owned.get(key)
        if isinstance(raw, (list, tuple, set)):
            values.extend(raw)
    # Older open-plan briefs only exposed hard_sparring_days at template level.
    raw_hard = template.get("hard_sparring_days")
    if isinstance(raw_hard, (list, tuple, set)):
        values.extend(raw_hard)
    return _ordered_weekdays(values)


def _is_coach_led_day(day: Mapping[str, Any]) -> bool:
    today_card = day.get("today_card")
    today_card = today_card if isinstance(today_card, Mapping) else {}
    if str(today_card.get("coach_led_contact") or "").strip():
        return True

    sessions = [item for item in (day.get("sessions") or []) if isinstance(item, Mapping)]
    has_executable_blocks = any(
        isinstance(session.get("blocks"), list) and bool(session.get("blocks"))
        for session in sessions
    )
    text = " ".join(
        str(value or "")
        for value in (
            today_card.get("headline"),
            *(session.get("title") for session in sessions),
            *(session.get("session_type") for session in sessions),
        )
    )
    return not has_executable_blocks and _COACH_LED_RE.search(text) is not None


def _base_context(
    plan_row: Mapping[str, Any], *, current_training_day: date | None
) -> dict[str, Any]:
    mode = schedule_mode(plan_row)
    return {
        "schedule_mode": mode,
        "projection_status": "not_required" if mode == "event_countdown" else "unavailable",
        "anchor_date": None,
        "current_training_day": current_training_day.isoformat() if current_training_day else None,
        "block_number": None,
        "current_week_number": None,
    }


def project_open_structured_plan(
    plan_row: Mapping[str, Any],
    structured_plan: Mapping[str, Any] | None,
    *,
    current_training_day: date | str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(projected_plan, response_context)`` for an open plan.

    Dated camps and non-open legacy plans pass through unchanged.  A failed
    legacy reconciliation also passes through unchanged with
    ``projection_status=unavailable``.
    """

    source = dict(structured_plan or {})
    training_day = (
        current_training_day
        if isinstance(current_training_day, date)
        else _parse_date(current_training_day)
    )
    context = _base_context(plan_row, current_training_day=training_day)
    spec = open_plan_spec(plan_row)
    if spec is None:
        return source, context

    anchor = open_plan_anchor_date(plan_row)
    template = spec.get("weekly_template")
    template = template if isinstance(template, Mapping) else {}
    training_days = _ordered_weekdays(template.get("training_days"))
    coach_owned_days = set(_coach_owned_days(template))
    hard_sparring_days = set(_ordered_weekdays(template.get("hard_sparring_days")))
    weeks = source.get("weeks")
    if anchor is None or not training_days or not isinstance(weeks, list) or not weeks:
        return source, context

    if training_day is None or training_day < anchor:
        block_number = 1
        current_week_number = 1
    else:
        elapsed = (training_day - anchor).days
        block_number = elapsed // 28 + 1
        current_week_number = (elapsed % 28) // 7 + 1

    # Validate every week before applying any dates so projection is atomic.
    for week in weeks:
        if not isinstance(week, Mapping):
            return source, context
        days = week.get("days")
        if not isinstance(days, list) or len(days) != len(training_days):
            return source, context
        for day, expected_weekday in zip(days, training_days, strict=True):
            if not isinstance(day, Mapping):
                return source, context
            explicit_weekday = normalize_weekday(day.get("weekday"))
            if explicit_weekday and explicit_weekday != expected_weekday:
                return source, context
            is_coach_led = _is_coach_led_day(day)
            # A coach-led card may only land on a declared coach-owned day, and
            # a declared hard-sparring day must remain coach-led. Technical days
            # are allowed to carry executable app work as well, so they do not
            # have to be sessionless to reconcile safely.
            if is_coach_led and expected_weekday not in coach_owned_days:
                return source, context
            if expected_weekday in hard_sparring_days and not is_coach_led:
                return source, context

    projected = copy.deepcopy(source)
    block_anchor = anchor + timedelta(days=(block_number - 1) * 28)
    for week_position, week in enumerate(projected["weeks"]):
        week_start = block_anchor + timedelta(days=week_position * 7)
        week["start_date"] = week_start.isoformat()
        week["end_date"] = (week_start + timedelta(days=6)).isoformat()
        week["countdown_start"] = None
        week["countdown_end"] = None
        for day, weekday in zip(week["days"], training_days, strict=True):
            projected_date = week_start + timedelta(days=WEEKDAYS.index(weekday))
            day["weekday"] = weekday
            day["date"] = projected_date.isoformat()
            day["countdown_label"] = ""

    context.update(
        {
            "projection_status": "projected",
            "anchor_date": anchor.isoformat(),
            "block_number": block_number,
            "current_week_number": current_week_number,
        }
    )
    return projected, context
