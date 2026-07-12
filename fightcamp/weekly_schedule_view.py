from __future__ import annotations

from datetime import date, timedelta
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
        "d_day": None,
        "day_label": "",
        "weekday_with_label": weekday,
        "calendar_date": None,
        "is_fight_day": False,
        "is_after_fight_day": False,
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

    if status == "hard_as_planned":
        return "hard"
    if status == "convert_to_technical_suggested":
        return "technical"
    if status == "deload_suggested":
        return "reduced"
    if status in {"blocked", "suppressed", "none", "no_hard_sparring_day"}:
        return "none"

    reason_codes = {str(code).strip() for code in _clean_list(entry.get("reason_codes"))}
    if "d17_hard_sparring_ban" in reason_codes or "final_week_sparring_cap" in reason_codes:
        return "technical"

    return "none"


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
        candidates.extend(
            str(code).strip().lower()
            for code in _clean_list(intentional_compression.get("reason_codes"))
        )
        candidates.append(str(intentional_compression.get("reason") or "").strip().lower())
        candidates.append(str(intentional_compression.get("summary") or "").strip().lower())

    return any(
        token in candidate
        for candidate in candidates
        for token in ("bridge", "taper", "fight_week", "late_fight", "countdown")
    )


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


def _is_d17_or_closer(day: dict[str, Any]) -> bool:
    d_day = day.get("d_day")
    if d_day is None:
        return True
    return isinstance(d_day, int) and 0 <= d_day <= 17


def _resolve_week_anchor_d_day(week: dict[str, Any]) -> int | None:
    """Resolve the closest-to-fight D-day for a week from any countdown contract.

    The normal-camp pipeline ships a list ``countdown_range`` (``[start, end]``)
    while the late-fight pipeline ships a ``countdown_span`` dict
    (``{"start_day": ..., "end_day": ...}``). Both describe the same thing — the
    end (closest-to-fight) D-day is the calendar anchor. Recognising both keeps
    the calendar the single source of truth regardless of which planner built
    the plan, so ≤21-day (late-fight) camps render the same countdown spine as
    longer camps instead of falling back to a blank day grid.
    """
    countdown_range = week.get("countdown_range")
    if isinstance(countdown_range, list) and len(countdown_range) == 2:
        try:
            return int(countdown_range[1])
        except (TypeError, ValueError):
            pass
    countdown_span = week.get("countdown_span")
    if isinstance(countdown_span, dict):
        try:
            return int(countdown_span.get("end_day"))
        except (TypeError, ValueError):
            pass
    return None


def _build_calendar_week_from_fight_date(
    *,
    fight_date: Any,
    anchor_d_day: Any,
) -> list[dict[str, Any]]:
    try:
        parsed_fight_date = date.fromisoformat(str(fight_date))
        anchor_d = int(anchor_d_day)
    except (TypeError, ValueError):
        return []
    anchor_date = parsed_fight_date - timedelta(days=anchor_d)
    week_monday = anchor_date - timedelta(days=anchor_date.weekday())

    days: list[dict[str, Any]] = []
    for day_offset in range(7):
        current_date = week_monday + timedelta(days=day_offset)
        d_day = (parsed_fight_date - current_date).days
        weekday = WEEKDAY_SHORT[current_date.weekday()]
        day_label = f"D-{d_day}" if d_day > 0 else ("D-0" if d_day == 0 else "")
        days.append(
            {
                "weekday": weekday,
                "calendar_date": current_date.isoformat(),
                "d_day": d_day,
                "day_label": day_label,
                "weekday_with_label": f"{weekday} ({day_label})" if day_label else weekday,
                "is_fight_day": d_day == 0,
                "is_after_fight_day": d_day < 0,
            }
        )
    return days


def _open_ongoing_weekly_schedule(
    planning_brief: dict[str, Any], *, week_index: int
) -> dict[str, Any] | None:
    """Map a renewable open-plan template onto the live weekly schedule.

    Open plans intentionally have no fight date, countdown calendar, or
    ``weekly_role_map``. Their deterministic source of truth is instead
    ``open_plan_spec.weekly_template`` plus the four-week development block.
    Keeping that contract here lets Today/check-ins use the same schedule
    adapter as dated camps without inventing calendar dates.
    """

    open_spec = planning_brief.get("open_plan_spec")
    if not isinstance(open_spec, dict) or open_spec.get("plan_type") != "open_ongoing_system":
        return None
    template = open_spec.get("weekly_template")
    if not isinstance(template, dict):
        return None

    development_block = open_spec.get("development_block")
    week_count = len(development_block) if isinstance(development_block, dict) else 4
    week_count = max(1, week_count)
    if week_index >= week_count:
        return None

    training_days = {
        weekday
        for value in _clean_list(template.get("training_days"))
        if (weekday := _normalize_weekday(value)) is not None
    }
    hard_sparring_days = {
        weekday
        for value in _clean_list(template.get("hard_sparring_days"))
        if (weekday := _normalize_weekday(value)) is not None
    }
    coach_owned = template.get("coach_owned_days")
    coach_owned = coach_owned if isinstance(coach_owned, dict) else {}
    technical_skill_days = {
        weekday
        for value in _clean_list(coach_owned.get("technical_skill_days"))
        if (weekday := _normalize_weekday(value)) is not None
    }
    coach_led_days = hard_sparring_days | technical_skill_days
    if not training_days:
        return None

    days = [_empty_day(weekday) for weekday in WEEKDAY_SHORT]
    for day in days:
        weekday = day["weekday"]
        if weekday not in training_days:
            continue
        if weekday in coach_led_days:
            is_hard = weekday in hard_sparring_days
            day.update(
                {
                    "sparring_day_class": "primary_hard" if is_hard else "none",
                    "effective_load": "hard" if is_hard else "reduced",
                    "status": "hard_as_planned" if is_hard else "coach_led_session",
                    "title": f"{weekday} coach-led {'sparring' if is_hard else 'boxing'}",
                    "reason": f"Coach-owned {'sparring' if is_hard else 'boxing'} day from the renewable weekly rhythm.",
                }
            )
        else:
            day.update(
                {
                    "effective_load": "reduced",
                    "status": "open_plan_session",
                    "title": f"{weekday} training",
                    "reason": "Scheduled training day from the renewable weekly rhythm.",
                }
            )

    selection_summary = planning_brief.get("stage1_selection_summary")
    phase = (
        str(selection_summary.get("current_phase") or "").strip()
        if isinstance(selection_summary, dict)
        else ""
    )
    return {
        "week_index": week_index,
        "week_count": week_count,
        "phase": phase,
        "projected_days_until_fight_start": None,
        "projected_days_until_fight_end": None,
        "day_label": f"Development week {week_index + 1}",
        "countdown_range": [],
        "original_countdown_range": [],
        "week_countdown_label": "",
        "week_label_with_countdown": f"Development week {week_index + 1}",
        "days": days,
    }


def extract_weekly_schedule(
    planning_brief: Any, *, week_index: int = 0, fight_date: Any = None
) -> dict[str, Any] | None:
    if not isinstance(planning_brief, dict) or week_index < 0:
        return None

    weekly_role_map = planning_brief.get("weekly_role_map")
    if not isinstance(weekly_role_map, dict):
        return _open_ongoing_weekly_schedule(planning_brief, week_index=week_index)

    weeks = weekly_role_map.get("weeks")
    if not isinstance(weeks, list) or week_index >= len(weeks):
        return None

    week = weeks[week_index]
    if not isinstance(week, dict):
        return None

    resolved_fight_date = (
        fight_date
        or planning_brief.get("fight_date")
        or (planning_brief.get("athlete_model") or {}).get("fight_date")
    )

    calendar_days = week.get("calendar_days")
    calendar_entries = [
        entry for entry in calendar_days if isinstance(entry, dict)
    ] if isinstance(calendar_days, list) else []
    if not calendar_entries:
        anchor_d_day = _resolve_week_anchor_d_day(week)
        if anchor_d_day is not None:
            calendar_entries = _build_calendar_week_from_fight_date(
                fight_date=resolved_fight_date,
                anchor_d_day=anchor_d_day,
            )

    if calendar_entries:
        days_by_weekday: dict[str, dict[str, Any]] = {weekday: _empty_day(weekday) for weekday in WEEKDAY_SHORT}
        anchor_weekday: str | None = None
        anchor_date: date | None = None
        anchor_d_day: int | None = None
        for entry in calendar_entries:
            weekday = _normalize_weekday(entry.get("weekday"))
            if not weekday:
                continue

            day = days_by_weekday[weekday]

            raw_d_day = entry.get("d_day")
            try:
                d_day = int(raw_d_day)
            except (TypeError, ValueError):
                d_day = None

            day.update(
                {
                    "d_day": d_day,
                    "day_label": (
                        f"D-{d_day}"
                        if d_day is not None and d_day > 0
                        else ("D-0" if d_day == 0 else "")
                    ),
                    "calendar_date": entry.get("calendar_date") or entry.get("date"),
                    "is_fight_day": bool(entry.get("is_fight_day")),
                    "is_after_fight_day": bool(entry.get("is_after_fight_day")),
                }
            )
            day["weekday_with_label"] = (
                f"{weekday} ({day['day_label']})" if day["day_label"] else weekday
            )
            if isinstance(d_day, int) and day["calendar_date"]:
                try:
                    parsed_date = date.fromisoformat(str(day["calendar_date"]))
                except (TypeError, ValueError):
                    parsed_date = None
                if parsed_date is not None and anchor_weekday is None:
                    anchor_weekday = weekday
                    anchor_date = parsed_date
                    anchor_d_day = d_day

        if anchor_weekday is not None and anchor_date is not None and isinstance(anchor_d_day, int):
            anchor_index = WEEKDAY_SHORT.index(anchor_weekday)
            for weekday, day in days_by_weekday.items():
                weekday_index = WEEKDAY_SHORT.index(weekday)
                day_offset = weekday_index - anchor_index
                if not day.get("calendar_date"):
                    day["calendar_date"] = (anchor_date + timedelta(days=day_offset)).isoformat()
                if day.get("d_day") is None:
                    inferred_d_day = anchor_d_day - day_offset
                    day["d_day"] = inferred_d_day
                    day["day_label"] = f"D-{inferred_d_day}" if inferred_d_day > 0 else ("D-0" if inferred_d_day == 0 else "")
                    day["weekday_with_label"] = f"{weekday} ({day['day_label']})" if day["day_label"] else weekday
                if not day.get("is_fight_day"):
                    day["is_fight_day"] = day.get("d_day") == 0
        days = [days_by_weekday[weekday] for weekday in WEEKDAY_SHORT]
    else:
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
            # Protected late/countdown weeks must not infer sparring dose from
            # declarations or legacy effective-day lists. The structured
            # hard_sparring_plan is the only authority for hard/technical/
            # managed sparring truth in these weeks.
            pass
    else:
        for day_name in _clean_list(week.get("declared_hard_sparring_days")):
            weekday = _normalize_weekday(day_name)
            if weekday and weekday in days_by_weekday:
                _fill_legacy_hard_day(days_by_weekday[weekday])

    original_countdown_range = week.get("countdown_range")
    d_days = [day.get("d_day") for day in days if isinstance(day.get("d_day"), int)]
    countdown_range = [max(d_days), min(d_days)] if d_days else []

    week_countdown_label = ""
    if isinstance(countdown_range, list) and len(countdown_range) == 2:
        start_d, end_d = countdown_range
        if isinstance(start_d, int) and isinstance(end_d, int):
            week_countdown_label = f"D-{start_d} → D-{end_d}"

    return {
        "week_index": week_index,
        "week_count": len(weeks),
        "phase": str(week.get("phase") or "").strip(),
        "projected_days_until_fight_start": week.get("projected_days_until_fight_start"),
        "projected_days_until_fight_end": week.get("projected_days_until_fight_end"),
        "day_label": str(week.get("day_label") or "").strip(),
        "countdown_range": countdown_range,
        "original_countdown_range": (
            original_countdown_range
            if isinstance(original_countdown_range, list) and len(original_countdown_range) == 2
            else []
        ),
        "week_countdown_label": week_countdown_label,
        "week_label_with_countdown": (
            f"Week {week_index + 1} — {str(week.get('phase') or '').strip()} ({week_countdown_label})"
            if week_countdown_label
            else f"Week {week_index + 1} — {str(week.get('phase') or '').strip()}"
        ),
        "days": days,
    }
