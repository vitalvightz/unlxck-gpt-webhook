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
        "countdown_label": "",
        "countdown_display_label": "",
        "sparring_day_class": "none",
        "effective_load": "none",
        "status": "",
        "reason": "",
        "coach_note": "",
        "reason_codes": [],
        "role_key": "",
        "role_label": "",
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
            "role_key": str(entry.get("role_key") or "hard_sparring_day").strip(),
            "role_label": str(entry.get("role_label") or "").strip(),
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


def _countdown_labels_by_weekday(week: dict[str, Any]) -> dict[str, str]:
    countdown_map = week.get("countdown_weekday_map")
    if not isinstance(countdown_map, dict):
        return {}
    labels_by_weekday: dict[str, str] = {}
    for label, weekday_value in countdown_map.items():
        weekday = _normalize_weekday(weekday_value)
        normalized_label = str(label or "").strip().upper()
        if weekday and normalized_label:
            labels_by_weekday[weekday] = normalized_label
    return labels_by_weekday


def _apply_countdown_labels(days: list[dict[str, Any]], week: dict[str, Any]) -> None:
    labels_by_weekday = _countdown_labels_by_weekday(week)
    for day in days:
        label = labels_by_weekday.get(day["weekday"], "")
        if not label:
            continue
        day["countdown_label"] = label
        day["countdown_display_label"] = f"{label} ({day['weekday']})"


def _late_fight_role_label(role_key: str) -> str:
    return {
        "hard_sparring_day": "Coach-led sparring",
        "technical_touch_day": "Technical rhythm",
        "neural_primer_day": "Neural primer",
        "strength_touch_day": "Neural primer",
        "alactic_sharpness_day": "Fight-speed primer",
        "light_fight_pace_touch_day": "Technical rhythm touch",
        "fight_week_freshness_day": "Freshness reset",
        "fight_day_protocol": "Fight day protocol",
    }.get(role_key, "")


def _fill_late_role_day(day: dict[str, Any], role: dict[str, Any]) -> None:
    role_key = str(role.get("role_key") or "").strip()
    if not role_key:
        return
    day["role_key"] = role_key
    day["role_label"] = str(role.get("athlete_facing_label") or _late_fight_role_label(role_key)).strip()
    if role_key == "hard_sparring_day":
        day.update(
            {
                "sparring_day_class": "primary_hard",
                "effective_load": "hard",
                "status": "hard_as_planned",
                "reason": "Declared hard sparring remains coach-owned for this countdown day.",
                "reason_codes": ["declared_hard_sparring"],
            }
        )


def _mark_late_declared_sparring_downgrade(day: dict[str, Any], week: dict[str, Any]) -> None:
    payload_mode = str(week.get("payload_mode") or "").strip()
    day.update(
        {
            "sparring_day_class": "technical",
            "effective_load": "technical",
            "status": "convert_to_technical_suggested",
            "reason": "Late-fight taper rules remove live sparring here; keep this as technical rhythm only.",
            "coach_note": "No live sparring load. Keep it technical, short, and coach-led.",
            "reason_codes": [code for code in (payload_mode, "late_fight_sparring_downgrade") if code],
            "role_key": "technical_touch_day",
            "role_label": "Technical rhythm",
        }
    )


def _mark_late_fight_day_protocol(day: dict[str, Any]) -> None:
    day.update(
        {
            "sparring_day_class": "none",
            "effective_load": "none",
            "status": "fight_day_protocol",
            "reason": "Fight day protocol only; no additional app S&C or live sparring.",
            "coach_note": "Follow coach warm-up and fight protocol.",
            "reason_codes": ["fight_day_protocol"],
            "role_key": "fight_day_protocol",
            "role_label": "Fight day protocol",
        }
    )


def _fill_late_fight_roles(days_by_weekday: dict[str, dict[str, Any]], week: dict[str, Any]) -> None:
    for role in week.get("session_roles") or []:
        if not isinstance(role, dict):
            continue
        weekday = _normalize_weekday(role.get("scheduled_day_hint") or role.get("real_weekday"))
        if weekday and weekday in days_by_weekday:
            _fill_late_role_day(days_by_weekday[weekday], role)

    for day_name in _clean_list(week.get("declared_hard_sparring_days")):
        weekday = _normalize_weekday(day_name)
        if not weekday or weekday not in days_by_weekday:
            continue
        day = days_by_weekday[weekday]
        if day["effective_load"] == "hard":
            continue
        _mark_late_declared_sparring_downgrade(day, week)

    for day in days_by_weekday.values():
        if day.get("countdown_label") == "D-0":
            _mark_late_fight_day_protocol(day)


def _countdown_span_label(week: dict[str, Any]) -> str:
    span = week.get("countdown_span")
    if not isinstance(span, dict):
        return ""
    start_day = span.get("start_day")
    end_day = span.get("end_day")
    if not isinstance(start_day, int) or not isinstance(end_day, int):
        return ""
    if start_day == end_day:
        return f"D-{start_day}"
    return f"D-{start_day} to D-{end_day}"


def _countdown_day_count(week: dict[str, Any]) -> int | None:
    span = week.get("countdown_span")
    if not isinstance(span, dict):
        return None
    start_day = span.get("start_day")
    end_day = span.get("end_day")
    if not isinstance(start_day, int) or not isinstance(end_day, int):
        return None
    return abs(start_day - end_day) + 1


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
    _apply_countdown_labels(days, week)

    hard_sparring_plan = week.get("hard_sparring_plan")
    hard_plan_is_list = isinstance(hard_sparring_plan, list)
    hard_entries = [entry for entry in hard_sparring_plan if isinstance(entry, dict)] if hard_plan_is_list else []
    if hard_entries:
        for entry in hard_entries:
            weekday = _normalize_weekday(entry.get("day") or entry.get("scheduled_day_hint"))
            if weekday and weekday in days_by_weekday:
                _fill_hard_day(days_by_weekday[weekday], entry)
    elif _is_protected_late_week(week) and hard_plan_is_list:
        _fill_late_fight_roles(days_by_weekday, week)
    elif _is_protected_late_week(week):
        if not hard_plan_is_list:
            for day_name in _clean_list(week.get("declared_hard_sparring_days")):
                weekday = _normalize_weekday(day_name)
                if weekday and weekday in days_by_weekday:
                    _mark_missing_effective_sparring_plan(days_by_weekday[weekday])
    else:
        for day_name in _clean_list(week.get("declared_hard_sparring_days")):
            weekday = _normalize_weekday(day_name)
            if weekday and weekday in days_by_weekday:
                _fill_legacy_hard_day(days_by_weekday[weekday])

    return {
        "week_index": week_index,
        "week_count": len(weeks),
        "phase": str(week.get("phase") or "").strip(),
        "stage_label": str(week.get("stage_label") or "").strip(),
        "payload_mode": str(week.get("payload_mode") or "").strip(),
        "countdown_span": _countdown_span_label(week),
        "countdown_day_count": _countdown_day_count(week),
        "days": days,
    }
