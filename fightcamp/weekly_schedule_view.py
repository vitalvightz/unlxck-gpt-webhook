from __future__ import annotations

from typing import Any

from .normalization import clean_list as _clean_list

WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_WEEKDAY_ALIASES = {
    "mon": "Mon",
    "monday": "Mon",
    "tue": "Tue",
    "tues": "Tue",
    "tuesday": "Tue",
    "wed": "Wed",
    "weds": "Wed",
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
_SPARRING_DAY_CLASSES = {"primary_hard", "secondary_hard", "managed_hard", "support_work", "none"}
_EFFECTIVE_LOADS = {"hard", "technical", "reduced", "none"}


def _normalize_weekday(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().rstrip(".")
    if not normalized:
        return None
    return _WEEKDAY_ALIASES.get(normalized)


def _empty_day(weekday: str) -> dict[str, Any]:
    return {
        "weekday": weekday,
        "sparring_day_class": "none",
        "effective_load": "none",
        "status": "",
        "reason": "",
        "coach_note": "",
        "reason_codes": [],
    }


def _coerce_hard_day_class(entry: dict[str, Any]) -> str:
    hard_day_class = str(entry.get("hard_day_class") or entry.get("hard_sparring_class") or "").strip()
    if hard_day_class in _SPARRING_DAY_CLASSES and hard_day_class != "support_work":
        return hard_day_class
    status = str(entry.get("status") or "").strip()
    return "managed_hard" if status and status != "hard_as_planned" else "primary_hard"


def _coerce_effective_load(entry: dict[str, Any]) -> str:
    effective_load = str(entry.get("effective_load") or "").strip()
    if effective_load in _EFFECTIVE_LOADS and effective_load != "none":
        return effective_load
    status = str(entry.get("status") or "").strip()
    if status == "convert_to_technical_suggested":
        return "technical"
    if status == "deload_suggested":
        return "reduced"
    return "hard"


def _fill_hard_day(day: dict[str, Any], entry: dict[str, Any]) -> None:
    day.update(
        {
            "sparring_day_class": _coerce_hard_day_class(entry),
            "effective_load": _coerce_effective_load(entry),
            "status": str(entry.get("status") or "").strip(),
            "reason": str(entry.get("reason") or "").strip(),
            "coach_note": str(entry.get("coach_note") or "").strip(),
            "reason_codes": _clean_list(entry.get("reason_codes")),
        }
    )


def _fill_legacy_hard_day(day: dict[str, Any]) -> None:
    day.update(
        {
            "sparring_day_class": "primary_hard",
            "effective_load": "hard",
            "status": "hard_as_planned",
        }
    )


def _fill_support_day(day: dict[str, Any]) -> None:
    day.update(
        {
            "sparring_day_class": "support_work",
            "effective_load": "technical",
            "status": "support_work_day",
        }
    )


def extract_weekly_schedule(planning_brief: Any, *, week_index: int = 0) -> dict[str, Any] | None:
    if not isinstance(planning_brief, dict) or week_index < 0:
        return None

    weekly_role_map = planning_brief.get("weekly_role_map")
    if not isinstance(weekly_role_map, dict):
        return None

    weeks = weekly_role_map.get("weeks")
    if not isinstance(weeks, list) or week_index >= len(weeks):
        return None

    week = weeks[week_index]
    if not isinstance(week, dict):
        return None

    days = [_empty_day(weekday) for weekday in WEEKDAY_SHORT]
    days_by_weekday = {day["weekday"]: day for day in days}

    hard_sparring_plan = week.get("hard_sparring_plan")
    hard_entries = [entry for entry in hard_sparring_plan if isinstance(entry, dict)] if isinstance(hard_sparring_plan, list) else []
    if hard_entries:
        for entry in hard_entries:
            weekday = _normalize_weekday(entry.get("day") or entry.get("scheduled_day_hint"))
            if weekday and weekday in days_by_weekday:
                _fill_hard_day(days_by_weekday[weekday], entry)
    else:
        for day_name in _clean_list(week.get("declared_hard_sparring_days")):
            weekday = _normalize_weekday(day_name)
            if weekday and weekday in days_by_weekday:
                _fill_legacy_hard_day(days_by_weekday[weekday])

    support_days = week.get("declared_support_work_days")
    if support_days is None:
        support_days = week.get("declared_technical_skill_days")
    for day_name in _clean_list(support_days):
        weekday = _normalize_weekday(day_name)
        if weekday and weekday in days_by_weekday and days_by_weekday[weekday]["sparring_day_class"] == "none":
            _fill_support_day(days_by_weekday[weekday])

    return {
        "week_index": week_index,
        "week_count": len(weeks),
        "phase": str(week.get("phase") or "").strip(),
        "days": days,
    }
