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
_SPARRING_DAY_CLASSES = {"primary_hard", "secondary_hard", "managed_hard", "technical", "none"}
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
    status = str(entry.get("status") or "").strip()
    effective_load = _coerce_effective_load(entry)
    if effective_load == "hard":
        hard_day_class = str(entry.get("hard_day_class") or entry.get("hard_sparring_class") or "").strip()
        return "secondary_hard" if hard_day_class == "secondary_hard" else "primary_hard"
    if effective_load == "reduced" or status == "deload_suggested":
        return "managed_hard"
    if effective_load == "technical" or status == "convert_to_technical_suggested":
        return "technical"
    return "none"


def _coerce_effective_load(entry: dict[str, Any]) -> str:
    effective_load = str(entry.get("effective_load") or "").strip()
    if effective_load in _EFFECTIVE_LOADS:
        return effective_load
    status = str(entry.get("status") or "").strip()
    if status == "convert_to_technical_suggested":
        return "technical"
    if status == "deload_suggested":
        return "reduced"
    return "hard"


def _fill_hard_day(day: dict[str, Any], entry: dict[str, Any]) -> None:
    reason_codes = _clean_list(entry.get("reason_codes"))
    day.update(
        {
            "sparring_day_class": _coerce_hard_day_class(entry),
            "effective_load": _coerce_effective_load(entry),
            "status": str(entry.get("status") or "").strip(),
            "reason": str(entry.get("reason") or "").strip(),
            "coach_note": str(entry.get("coach_note") or "").strip(),
            "reason_codes": reason_codes,
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


def _is_protected_late_week(week: dict[str, Any]) -> bool:
    final_week_sparring_cap = week.get("final_week_sparring_cap")
    if isinstance(final_week_sparring_cap, dict) and final_week_sparring_cap.get("active"):
        return True

    candidates = [
        str(week.get("phase") or "").strip().lower(),
        str(week.get("stage_key") or "").strip().lower(),
        str(week.get("payload_mode") or "").strip().lower(),
    ]
    intentional_compression = week.get("intentional_compression")
    if isinstance(intentional_compression, dict):
        candidates.extend(str(code).strip().lower() for code in _clean_list(intentional_compression.get("reason_codes")))
        candidates.append(str(intentional_compression.get("reason") or "").strip().lower())
        candidates.append(str(intentional_compression.get("summary") or "").strip().lower())

    return any(token in candidate for candidate in candidates for token in ("bridge", "taper", "fight"))


def _mark_missing_effective_sparring_plan(day: dict[str, Any]) -> None:
    day.update(
        {
            "sparring_day_class": "none",
            "effective_load": "none",
            "status": "missing_effective_sparring_plan",
            "reason": "Protected late week requires hard_sparring_plan; declared_hard_sparring_days is context only.",
            "reason_codes": ["missing_effective_sparring_plan"],
        }
    )


def _mark_late_hard_sparring_ban(day: dict[str, Any]) -> None:
    day.update(
        {
            "sparring_day_class": "technical",
            "effective_load": "technical",
            "status": "convert_to_technical_suggested",
            "reason": (
                "D-17 onward hard sparring ban: declared hard sparring is converted "
                "to technical/rhythm only. No effective hard sparring allowed."
            ),
            "coach_note": "Technical/rhythm only. No hard contact.",
            "reason_codes": ["d17_hard_sparring_ban"],
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
    hard_plan_is_list = isinstance(hard_sparring_plan, list)
    hard_entries = [entry for entry in hard_sparring_plan if isinstance(entry, dict)] if hard_plan_is_list else []
    if hard_entries:
        for entry in hard_entries:
            weekday = _normalize_weekday(entry.get("day") or entry.get("scheduled_day_hint"))
            if weekday and weekday in days_by_weekday:
                _fill_hard_day(days_by_weekday[weekday], entry)
    elif _is_protected_late_week(week):
        if not hard_plan_is_list:
            for day_name in _clean_list(week.get("declared_hard_sparring_days")):
                weekday = _normalize_weekday(day_name)
                if weekday and weekday in days_by_weekday:
                    _mark_missing_effective_sparring_plan(days_by_weekday[weekday])
        else:
            for day_name in _clean_list(week.get("effective_hard_sparring_days")):
                weekday = _normalize_weekday(day_name)
                if weekday and weekday in days_by_weekday:
                    _fill_legacy_hard_day(days_by_weekday[weekday])
            for day_name in _clean_list(week.get("declared_hard_sparring_days")):
                weekday = _normalize_weekday(day_name)
                if (
                    weekday
                    and weekday in days_by_weekday
                    and days_by_weekday[weekday]["effective_load"] != "hard"
                ):
                    _mark_late_hard_sparring_ban(days_by_weekday[weekday])
    else:
        for day_name in _clean_list(week.get("declared_hard_sparring_days")):
            weekday = _normalize_weekday(day_name)
            if weekday and weekday in days_by_weekday:
                _fill_legacy_hard_day(days_by_weekday[weekday])

    return {
        "week_index": week_index,
        "week_count": len(weeks),
        "phase": str(week.get("phase") or "").strip(),
        "projected_days_until_fight_start": week.get("projected_days_until_fight_start"),
        "projected_days_until_fight_end": week.get("projected_days_until_fight_end"),
        "day_label": str(week.get("day_label") or "").strip(),
        "days": days,
    }
