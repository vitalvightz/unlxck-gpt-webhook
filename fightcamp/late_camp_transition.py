"""Normal-camp late transition overlay.

This layer keeps a full normal camp feeling continuous as it approaches the
fight. It does not switch the plan into the short-notice late-fight payload.
Instead, it tapers the existing role map: anchors become touches, harder
conditioning becomes rhythm, recovery becomes freshness, and unused late-camp
training days can receive low-cost tactical/reset inserts.
"""

from __future__ import annotations

from typing import Any

from .gap_fill_inserts import (
    PHYSICAL_INSERTS,
    apply_gap_fill_inserts,
)
from .normalization import clean_list, dedupe_preserve_order
from .stage2_payload_late_fight import _days_out_payload_mode, _late_fight_window


_WEEKDAY_CANON = {
    "monday": "monday",
    "mon": "monday",
    "tuesday": "tuesday",
    "tue": "tuesday",
    "wednesday": "wednesday",
    "wed": "wednesday",
    "thursday": "thursday",
    "thu": "thursday",
    "friday": "friday",
    "fri": "friday",
    "saturday": "saturday",
    "sat": "saturday",
    "sunday": "sunday",
    "sun": "sunday",
}

_WEEKDAY_ABBR = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
    "saturday": "Sat",
    "sunday": "Sun",
}

_STRENGTH_ROLES = {
    "primary_strength_day",
    "secondary_strength_day",
    "structural_strength_day",
    "transfer_strength_day",
    "neural_plus_strength_day",
    "strength_touch_day",
    "small_strength_touch_day",
    "neural_primer_day",
}
_GLYCOLYTIC_ROLES = {
    "fight_pace_repeatability_day",
    "main_fight_pace_day",
    "highest_glycolytic_day",
    "controlled_repeatability_day",
    "light_fight_pace_touch_day",
}
_RECOVERY_ROLES = {
    "recovery_reset_day",
    "recovery_only_day",
    "tissue_recovery_day",
    "fight_week_freshness_day",
}

_MAX_TRANSITION_INSERTS_TOTAL = 4
_MAX_TRANSITION_INSERTS_PER_WEEK = 1


def _weekday_key(value: Any) -> str:
    return _WEEKDAY_CANON.get(str(value or "").strip().lower(), "")


def _weekday_label(key: str) -> str:
    return _WEEKDAY_ABBR.get(key, key.title())


def _calendar_d_by_weekday(week: dict[str, Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for day in week.get("calendar_days") or []:
        if not isinstance(day, dict):
            continue
        weekday = _weekday_key(day.get("weekday"))
        d_day = day.get("d_day")
        if weekday and isinstance(d_day, int):
            mapping[weekday] = d_day
    return mapping


def _role_d_day(role: dict[str, Any], d_by_weekday: dict[str, int]) -> int | None:
    for key in ("countdown_offset", "d_day"):
        value = role.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass

    label = str(role.get("scheduled_countdown_label") or role.get("countdown_label") or "").strip().upper()
    if label.startswith("D-"):
        try:
            return int(label[2:])
        except ValueError:
            pass

    weekday = _weekday_key(role.get("scheduled_day_hint"))
    if weekday:
        return d_by_weekday.get(weekday)
    return None


def _stamp_role_countdown(role: dict[str, Any], weekday: str, d_day: int) -> None:
    role["scheduled_day_hint"] = _weekday_label(weekday)
    role["countdown_offset"] = d_day
    role["countdown_label"] = f"D-{d_day}"
    role["scheduled_countdown_label"] = f"D-{d_day}"
    role["real_weekday"] = weekday
    role["countdown_display_label"] = f"D-{d_day} ({weekday.title()})"


def _flatten_text_values(values: list[Any]) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ") for value in values if str(value).strip())


def _transition_focus(athlete_model: dict[str, Any]) -> list[str]:
    raw = []
    for key in ("key_goals", "goals", "performance_goals", "weaknesses", "weak_areas"):
        raw.extend(clean_list(athlete_model.get(key)))
    text = _flatten_text_values(raw)
    focus: list[str] = []
    if any(token in text for token in ("power", "speed", "explosive", "reaction", "sharp")):
        focus.append("power / speed")
    if any(token in text for token in ("gas", "conditioning", "cardio", "engine", "stamina", "endurance")):
        focus.append("gas tank")
    if any(token in text for token in ("footwork", "angle", "pivot", "ring", "stance")):
        focus.append("footwork")
    if any(token in text for token in ("mobility", "pain", "injury", "rehab", "restriction")):
        focus.append("mobility / tissue tolerance")
    if any(token in text for token in ("tactical", "counter", "pressure", "distance", "clinch", "defence", "defense")):
        focus.append("tactical clarity")
    return focus[:3] or ["fight sharpness"]


def _continuity_phrase(focus: list[str]) -> str:
    if not focus:
        return "Carry the camp's main quality forward while load comes down."
    if len(focus) == 1:
        return f"Carry {focus[0]} forward while load comes down."
    return f"Carry {', '.join(focus[:-1])}, and {focus[-1]} forward while load comes down."


def _role_transition_text(role_key: str, d_day: int, focus: list[str]) -> tuple[str, str]:
    continuity = _continuity_phrase(focus)
    if role_key in _STRENGTH_ROLES:
        if d_day <= 7:
            return (
                "Final Neural Cue",
                f"{continuity} Dose: 2-3 x 3-5 sec crisp explosive or technical reps, full rest, RPE 4-6. Stop before fatigue, pump, or soreness.",
            )
        if d_day <= 13:
            return (
                "Power Transfer Touch",
                f"{continuity} Dose: 2-3 x 3 explosive reps or throws, full rest, RPE 6-7. Same intent as SPP, sharply reduced volume.",
            )
        return (
            "Strength Maintain",
            f"{continuity} Dose: 2-3 x 3-5 clean reps, full rest, RPE 6-7. Keep force quality; no grind, no accessory fatigue.",
        )
    if role_key in _GLYCOLYTIC_ROLES:
        if d_day <= 13:
            return (
                "Technical Rhythm Touch",
                f"{continuity} Dose: 3-5 x 60-90 sec smooth fight rhythm, 60-90 sec rest, RPE 4-5. No lactic burn and no conditioning-build framing.",
            )
        return (
            "Controlled Rhythm Touch",
            f"{continuity} Dose: 2-4 x 2 min technical flow, equal rest, RPE 5-6. Keep rhythm without chasing fatigue.",
        )
    if role_key in _RECOVERY_ROLES:
        return (
            "Freshness Reset",
            f"{continuity} Dose: 6-10 min breathing, easy mobility, and tissue reset. Finish fresher than you started.",
        )
    return (
        "Late-Camp Support",
        f"{continuity} Keep this low-cost, familiar, and clean. No novelty and no fatigue target.",
    )


def _transition_role_key(role: dict[str, Any], d_day: int) -> str | None:
    role_key = str(role.get("role_key") or "").strip()
    category = str(role.get("category") or "").strip().lower()
    system = str(role.get("preferred_system") or "").strip().lower()

    if role_key == "hard_sparring_day":
        return None
    if category == "strength" or role_key in _STRENGTH_ROLES:
        return "neural_primer_day" if d_day <= 7 else "strength_touch_day"
    if role_key in _GLYCOLYTIC_ROLES or system == "glycolytic":
        return "light_fight_pace_touch_day" if d_day <= 13 else None
    if category == "conditioning" and system == "aerobic" and d_day <= 13:
        return role_key or "aerobic_flush_day"
    if category == "conditioning" and system == "alactic" and d_day <= 7:
        return "alactic_sharpness_day"
    if category == "recovery" or role_key in _RECOVERY_ROLES:
        return "fight_week_freshness_day" if d_day <= 7 else None
    return None


def _mark_transition_role(role: dict[str, Any], d_day: int, focus: list[str]) -> str | None:
    role_key = str(role.get("role_key") or "").strip()
    if not role_key or role_key == "fight_day_protocol":
        return None

    new_key = _transition_role_key(role, d_day)
    changed = bool(new_key and new_key != role_key)
    if changed:
        role["transition_from_role_key"] = role_key
        role["role_key"] = new_key
        role_key = new_key

    if role_key == "hard_sparring_day" and d_day <= 17:
        role["late_camp_transition"] = True
        role["transition_window"] = _late_fight_window(d_day)
        role["transition_continuity"] = "Hard contact is removed by countdown rule; the coach-led day stays technical only."
        role["display_text"] = "Coach-led technical-only boxing. No extra S&C today. Keep freshness priority."
        return "sparring_hard_contact_removed"

    if role_key not in _STRENGTH_ROLES | _GLYCOLYTIC_ROLES | _RECOVERY_ROLES and not changed:
        category = str(role.get("category") or "").strip().lower()
        if category not in {"conditioning", "strength", "recovery"}:
            return None

    label, display_text = _role_transition_text(role_key, d_day, focus)
    role["late_camp_transition"] = True
    role["transition_window"] = _late_fight_window(d_day)
    role["transition_continuity"] = _continuity_phrase(focus)
    role["athlete_facing_label"] = label
    role["display_text"] = display_text
    role["counts_toward_transition_stress"] = role_key not in _RECOVERY_ROLES
    role["selection_rule"] = (
        "Late-camp transition: preserve the camp's existing quality with lower volume, "
        "lower soreness risk, and no new development work."
    )
    governance = dict(role.get("governance") or {})
    governance["late_camp_transition"] = True
    governance["support_cap"] = "tapered_touch"
    governance["forbidden_secondary_stressors"] = dedupe_preserve_order(
        clean_list(governance.get("forbidden_secondary_stressors"))
        + ["standalone_glycolytic", "contrast_work", "jumps", "grinding_strength", "new_exercise_variation"]
    )
    role["governance"] = governance
    return "role_morphed" if changed else "role_capped"


def _existing_transition_offsets(weeks: list[dict[str, Any]]) -> set[int]:
    offsets: set[int] = set()
    for week in weeks:
        d_by_weekday = _calendar_d_by_weekday(week)
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            d_day = _role_d_day(role, d_by_weekday)
            if isinstance(d_day, int):
                offsets.add(d_day)
    return offsets


def _insert_usage_blocks(insert_role_key: str, insert_offset: int, inserted: list[dict[str, Any]]) -> bool:
    return any(
        str(item.get("role_key") or "") == insert_role_key
        and abs(int(item.get("countdown_offset") or 0) - insert_offset) <= 7
        for item in inserted
    )


def _remove_intentionally_unused_day(week: dict[str, Any], weekday: str) -> None:
    if not weekday:
        return
    updated = []
    for item in week.get("intentionally_unused_days") or []:
        if not isinstance(item, dict):
            updated.append(item)
            continue
        if _weekday_key(item.get("day")) == weekday:
            continue
        updated.append(item)
    week["intentionally_unused_days"] = updated


def _week_for_offset(weeks: list[dict[str, Any]], offset: int) -> dict[str, Any] | None:
    for week in weeks:
        for day in week.get("calendar_days") or []:
            if isinstance(day, dict) and day.get("d_day") == offset:
                return week
    return None


def _late_sequence_roles(weeks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for week in weeks:
        d_by_weekday = _calendar_d_by_weekday(week)
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            if str(role.get("category") or "").strip().lower() == "support_insert":
                continue
            if str(role.get("role_key") or "") == "fight_day_protocol":
                continue
            d_day = _role_d_day(role, d_by_weekday)
            if not isinstance(d_day, int) or not (0 < d_day <= 21):
                continue
            role_copy = dict(role)
            role_copy["countdown_offset"] = d_day
            role_copy["countdown_label"] = f"D-{d_day}"
            role_copy["scheduled_countdown_label"] = f"D-{d_day}"
            sequence.append(role_copy)
    return sequence


def _append_gap_transition_inserts(
    weeks: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    *,
    focus: list[str],
    inserted_so_far: list[dict[str, Any]],
    existing_offsets: set[int],
) -> dict[Any, list[str]]:
    sequence = _late_sequence_roles(weeks)
    if len(sequence) < 2:
        return {}

    expanded = apply_gap_fill_inserts(sequence, athlete_model)
    insert_candidates = [
        role
        for role in expanded
        if isinstance(role, dict) and str(role.get("category") or "").strip().lower() == "support_insert"
    ]
    if not insert_candidates:
        return {}

    actions_by_week: dict[Any, list[str]] = {}
    per_week_count: dict[Any, int] = {}
    for insert in insert_candidates:
        if len(inserted_so_far) >= _MAX_TRANSITION_INSERTS_TOTAL:
            break
        try:
            d_day = int(insert.get("countdown_offset"))
        except (TypeError, ValueError):
            continue
        if d_day in existing_offsets:
            continue
        week = _week_for_offset(weeks, d_day)
        if week is None:
            continue
        week_index = week.get("week_index")
        if per_week_count.get(week_index, 0) >= _MAX_TRANSITION_INSERTS_PER_WEEK:
            continue
        role_key = str(insert.get("role_key") or "")
        if _insert_usage_blocks(role_key, d_day, inserted_so_far):
            continue

        d_by_weekday = _calendar_d_by_weekday(week)
        weekday = next((day for day, offset in d_by_weekday.items() if offset == d_day), "")
        declared_days = {_weekday_key(day) for day in clean_list(week.get("declared_training_days"))}
        if declared_days and weekday not in declared_days:
            continue
        if weekday:
            _stamp_role_countdown(insert, weekday, d_day)
        insert["late_camp_transition"] = True
        insert["transition_window"] = _late_fight_window(d_day)
        insert["transition_continuity"] = _continuity_phrase(focus)
        insert["day_assignment_reason"] = (
            "Late-camp countdown gap converted into low-cost continuity support."
        )
        display = str(insert.get("display_text") or "").strip()
        continuity_line = f"Purpose: {_continuity_phrase(focus)}"
        insert["display_text"] = f"{display}\n{continuity_line}" if display else continuity_line

        week.setdefault("session_roles", []).append(insert)
        if weekday:
            _remove_intentionally_unused_day(week, weekday)
        inserted_so_far.append(insert)
        existing_offsets.add(d_day)
        per_week_count[week_index] = per_week_count.get(week_index, 0) + 1
        actions_by_week.setdefault(week_index, []).append(f"inserted_{role_key}_d{d_day}")

    return actions_by_week


def apply_late_camp_transition_overlay(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any],
) -> dict[str, Any]:
    """Mutate ``weekly_role_map`` with a normal-camp late transition overlay.

    Returns a compact context dict for the planning brief/finalizer packet.
    """

    if not isinstance(weekly_role_map, dict):
        return {"active": False, "reason": "missing_weekly_role_map"}
    weeks = [week for week in weekly_role_map.get("weeks") or [] if isinstance(week, dict)]
    if not weeks:
        return {"active": False, "reason": "no_weeks"}

    focus = _transition_focus(athlete_model)
    inserted: list[dict[str, Any]] = []
    existing_offsets = _existing_transition_offsets(weeks)
    transition_weeks: list[dict[str, Any]] = []

    for week in weeks:
        d_by_weekday = _calendar_d_by_weekday(week)
        if not d_by_weekday:
            continue
        week_actions: list[str] = []
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            d_day = _role_d_day(role, d_by_weekday)
            weekday = _weekday_key(role.get("scheduled_day_hint"))
            if isinstance(d_day, int) and weekday:
                _stamp_role_countdown(role, weekday, d_day)
            if not isinstance(d_day, int) or not (0 < d_day <= 21):
                continue
            action = _mark_transition_role(role, d_day, focus)
            if action:
                week_actions.append(f"{action}_d{d_day}")

        if not week_actions:
            continue
        d_values = list(d_by_weekday.values())
        week_context = {
            "week_index": week.get("week_index"),
            "phase": week.get("phase"),
            "countdown_range": [max(d_values), min(d_values)] if d_values else [],
            "window": _late_fight_window(min(d_values)) if d_values else "camp",
            "actions": week_actions[:6],
        }
        week["late_camp_transition"] = {
            "active": True,
            "window": week_context["window"],
            "continuity": _continuity_phrase(focus),
            "actions": week_actions[:6],
        }
        transition_weeks.append(week_context)

    gap_actions_by_week = _append_gap_transition_inserts(
        weeks,
        athlete_model,
        focus=focus,
        inserted_so_far=inserted,
        existing_offsets=existing_offsets,
    )
    for week in weeks:
        week_index = week.get("week_index")
        gap_actions = gap_actions_by_week.get(week_index) or []
        if not gap_actions:
            continue
        d_by_weekday = _calendar_d_by_weekday(week)
        d_values = list(d_by_weekday.values())
        late_context = week.setdefault(
            "late_camp_transition",
            {
                "active": True,
                "window": _late_fight_window(min(d_values)) if d_values else "camp",
                "continuity": _continuity_phrase(focus),
                "actions": [],
            },
        )
        late_context["actions"] = dedupe_preserve_order(
            clean_list(late_context.get("actions")) + gap_actions
        )[:8]
        existing_context = next(
            (entry for entry in transition_weeks if entry.get("week_index") == week_index),
            None,
        )
        if existing_context is None:
            existing_context = {
                "week_index": week_index,
                "phase": week.get("phase"),
                "countdown_range": [max(d_values), min(d_values)] if d_values else [],
                "window": late_context.get("window"),
                "actions": [],
            }
            transition_weeks.append(existing_context)
        existing_context["actions"] = dedupe_preserve_order(
            clean_list(existing_context.get("actions")) + gap_actions
        )[:8]

    active = bool(transition_weeks)
    context = {
        "active": active,
        "model": "normal_camp_taper_morph.v1",
        "summary": (
            "Normal camp keeps its phase structure; D-21 to fight morphs existing work "
            "into lower-cost sharpness, rhythm, freshness, and tactical support."
        )
        if active
        else "",
        "carried_focus": focus if active else [],
        "rules": [
            "Preserve earlier camp qualities; reduce volume and soreness risk.",
            "Use low-cost inserts only on unused late-camp training days.",
            "Do not restore development work, hard conditioning build, or extra strength volume.",
        ]
        if active
        else [],
        "weeks": transition_weeks,
    }
    if active:
        weekly_role_map["late_camp_transition"] = context
        weekly_role_map["transition_payload_mode"] = "normal_camp_taper_morph"
    return context
