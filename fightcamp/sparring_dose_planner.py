from __future__ import annotations

from typing import Any

from .injury_formatting import parse_injury_entry
from .normalization import clean_list, ordered_weekdays as _ordered_weekdays

_ORDERED_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_WEEKDAY_ORDER = {day: idx for idx, day in enumerate(_ORDERED_WEEKDAYS)}
_PRIMARY_COLLISION_ROLE_KEYS = {
    "fight_pace_repeatability_day",
    "light_fight_pace_touch_day",
    "controlled_repeatability_day",
}
_HIGH_RISK_INJURY_TOKENS = {
    "tear",
    "rupture",
    "fracture",
    "dislocation",
    "subluxation",
}

_DOSE_CLASS_HARD_PRIMARY = "hard_primary"
_DOSE_CLASS_HARD_SECONDARY = "hard_secondary"
_DOSE_CLASS_HARD_DELOAD = "hard_deload"
_DOSE_CLASS_TECHNICAL_RHYTHM = "technical_rhythm"


def _dose_operational_profile(dose_class: str) -> dict[str, Any]:
    if dose_class == _DOSE_CLASS_HARD_PRIMARY:
        return {
            "max_round_fraction": 1.0,
            "max_live_intensity_pct": 100,
            "max_collision_intensity_pct": 100,
            "technical_finish_min_rounds": 0,
            "padwork_share_min_pct": 0,
        }
    if dose_class == _DOSE_CLASS_HARD_SECONDARY:
        return {
            "max_round_fraction": 0.85,
            "max_live_intensity_pct": 90,
            "max_collision_intensity_pct": 80,
            "technical_finish_min_rounds": 1,
            "padwork_share_min_pct": 20,
        }
    if dose_class == _DOSE_CLASS_HARD_DELOAD:
        return {
            "max_round_fraction": 0.65,
            "max_live_intensity_pct": 75,
            "max_collision_intensity_pct": 55,
            "technical_finish_min_rounds": 2,
            "padwork_share_min_pct": 40,
        }
    return {
        "max_round_fraction": 0.5,
        "max_live_intensity_pct": 60,
        "max_collision_intensity_pct": 20,
        "technical_finish_min_rounds": 3,
        "padwork_share_min_pct": 60,
    }


def _status_from_dose_class(dose_class: str) -> str:
    if dose_class == _DOSE_CLASS_TECHNICAL_RHYTHM:
        return "convert_to_technical_suggested"
    if dose_class == _DOSE_CLASS_HARD_DELOAD:
        return "deload_suggested"
    return "hard_as_planned"


def _dose_policy_from_dose_class(dose_class: str) -> str:
    if dose_class == _DOSE_CLASS_TECHNICAL_RHYTHM:
        return "convert"
    if dose_class == _DOSE_CLASS_HARD_DELOAD:
        return "deload"
    return "as_planned"


def _effective_load_from_dose_class(dose_class: str) -> str:
    if dose_class == _DOSE_CLASS_TECHNICAL_RHYTHM:
        return "technical"
    if dose_class == _DOSE_CLASS_HARD_DELOAD:
        return "reduced"
    return "hard"


def _base_secondary_limit(
    *,
    fatigue: str,
    cut: str,
    week_press: str,
    injury: dict[str, Any],
) -> int:
    secondary_limit = 2
    if week_press == "high":
        secondary_limit = 0
    if fatigue == "high" or cut == "high":
        secondary_limit = 0
    if injury.get("severity") in {"moderate", "high"}:
        secondary_limit = min(secondary_limit, 1)
    if injury.get("high_risk") or injury.get("worsening"):
        secondary_limit = 0
    if fatigue == "high" and cut in {"moderate", "high"}:
        secondary_limit = 0
    return max(0, secondary_limit)


def _assign_dose_classes(
    *,
    hard_days: list[str],
    week: dict[str, Any],
    fatigue: str,
    cut: str,
    week_press: str,
    injury: dict[str, Any],
    days_until_fight: Any,
) -> dict[str, str]:
    classes_by_day: dict[str, str] = {}
    if not hard_days:
        return classes_by_day

    protected_day = _pick_protected_hard_day(hard_days, week=week) or hard_days[0]
    countdown_override = _countdown_sparring_override(days_until_fight)
    if countdown_override == "convert_all":
        return {day: _DOSE_CLASS_TECHNICAL_RHYTHM for day in hard_days}
    if countdown_override == "deload_all":
        return {day: _DOSE_CLASS_HARD_DELOAD for day in hard_days}

    classes_by_day[protected_day] = _DOSE_CLASS_HARD_PRIMARY
    remaining = [day for day in hard_days if day != protected_day]
    if not remaining:
        return classes_by_day

    if countdown_override == "cap_one":
        for day in remaining:
            classes_by_day[day] = _DOSE_CLASS_HARD_DELOAD
        return classes_by_day

    if injury.get("instability") or injury.get("daily_symptoms"):
        return {day: _DOSE_CLASS_TECHNICAL_RHYTHM for day in hard_days}
    if injury.get("worsening") and (injury.get("high_risk") or week_press == "high"):
        return {day: _DOSE_CLASS_TECHNICAL_RHYTHM for day in hard_days}

    secondary_limit = min(_base_secondary_limit(fatigue=fatigue, cut=cut, week_press=week_press, injury=injury), len(remaining))
    for idx, day in enumerate(remaining):
        if idx < secondary_limit:
            classes_by_day[day] = _DOSE_CLASS_HARD_SECONDARY
            continue
        if week_press == "high" or fatigue == "high" or cut == "high" or injury.get("severity") in {"moderate", "high"}:
            classes_by_day[day] = _DOSE_CLASS_HARD_DELOAD
        else:
            classes_by_day[day] = _DOSE_CLASS_TECHNICAL_RHYTHM
    return classes_by_day




def _fatigue_level(athlete_snapshot: dict[str, Any]) -> str:
    fatigue = str(athlete_snapshot.get("fatigue") or "").strip().lower()
    return fatigue if fatigue in {"low", "moderate", "high"} else "low"


def _cut_pressure(athlete_snapshot: dict[str, Any]) -> str:
    readiness_flags = {flag.lower() for flag in clean_list(athlete_snapshot.get("readiness_flags", []))}
    cut_pct = athlete_snapshot.get("weight_cut_pct")
    try:
        cut_value = float(cut_pct or 0.0)
    except (TypeError, ValueError):
        cut_value = 0.0

    if "aggressive_weight_cut" in readiness_flags or cut_value >= 5.0:
        return "high"
    if athlete_snapshot.get("weight_cut_risk") or "active_weight_cut" in readiness_flags or cut_value >= 3.0:
        return "moderate"
    return "none"


def _week_pressure(week: dict[str, Any], athlete_snapshot: dict[str, Any]) -> str:
    readiness_flags = {flag.lower() for flag in clean_list(athlete_snapshot.get("readiness_flags", []))}
    phase = str(week.get("phase") or "").strip().upper()
    stage_key = str(week.get("stage_key") or "").strip().lower()
    days_until_fight = athlete_snapshot.get("days_until_fight")
    try:
        day_value = int(days_until_fight)
    except (TypeError, ValueError):
        day_value = None

    if phase == "TAPER" or "fight_week" in readiness_flags or "fight_week" in stage_key:
        return "high"
    if day_value is not None and day_value <= 7:
        return "high"
    if athlete_snapshot.get("short_notice") or (day_value is not None and day_value <= 14):
        return "moderate"
    return "none"


def _injury_severity(lowered: str) -> str:
    if any(token in lowered for token in ("severe", "major", "significant", "grade 3", "grade iii")):
        return "high"
    if any(token in lowered for token in ("moderate", "grade 2", "grade ii")):
        return "moderate"
    if any(token in lowered for token in ("mild", "minor", "low grade", "low-grade", "grade 1", "grade i")):
        return "mild"
    if any(token in lowered for token in _HIGH_RISK_INJURY_TOKENS):
        return "high"
    if any(token in lowered for token in ("strain", "sprain", "impingement", "tendinopathy", "tendonitis")):
        return "mild"
    if any(token in lowered for token in ("pain", "soreness", "stiffness", "irritation", "ache")):
        return "mild"
    return "none"


def _severity_rank(severity: str) -> int:
    return {"none": 0, "mild": 1, "moderate": 2, "high": 3}.get(severity, 0)


def _injury_assessment(athlete_snapshot: dict[str, Any]) -> dict[str, Any]:
    severity = "none"
    worsening = False
    instability = False
    daily_symptoms = False
    high_risk = False

    for raw_entry in clean_list(athlete_snapshot.get("injuries", [])):
        lowered = raw_entry.lower()
        parsed = parse_injury_entry(raw_entry) or {}
        region = str(parsed.get("canonical_location") or "").strip().lower()

        entry_severity = _injury_severity(lowered)
        if _severity_rank(entry_severity) > _severity_rank(severity):
            severity = entry_severity

        worsening = worsening or any(
            token in lowered
            for token in ("worsen", "worsening", "worse", "flared", "aggravated", "regressing")
        )
        instability = instability or any(
            token in lowered
            for token in ("instability", "giving way", "buckled", "locking", "locked")
        )
        daily_symptoms = daily_symptoms or any(
            token in lowered
            for token in (
                "daily",
                "rest pain",
                "night pain",
                "sleep",
                "walking",
                "stairs",
                "constant",
            )
        )
        high_risk = high_risk or instability or daily_symptoms or any(token in lowered for token in _HIGH_RISK_INJURY_TOKENS)
        if worsening and region in {"knee", "ankle", "hip", "shoulder", "neck", "lower_back"}:
            high_risk = True

    if instability or daily_symptoms:
        severity = "high"
    elif high_risk and _severity_rank(severity) < _severity_rank("moderate"):
        severity = "moderate"

    return {
        "has_injury": severity != "none",
        "severity": severity,
        "high_risk": high_risk,
        "worsening": worsening,
        "instability": instability,
        "daily_symptoms": daily_symptoms,
    }


def _main_collision_owner_day(week: dict[str, Any], hard_days: list[str]) -> str:
    explicit_day = str(week.get("primary_collision_owner_day") or week.get("main_fight_pace_day") or "").strip()
    if explicit_day in hard_days:
        return explicit_day

    for role in week.get("session_roles") or []:
        if role.get("role_key") not in _PRIMARY_COLLISION_ROLE_KEYS:
            continue
        for key in ("collision_owner_day", "planned_collision_owner_day"):
            candidate_day = str(role.get(key) or "").strip()
            if candidate_day in hard_days:
                return candidate_day
    return ""


def _countdown_sparring_override(days_until_fight: Any) -> str | None:
    """Return a deterministic sparring override based on countdown alone.

    Returns:
        ``None``  – no countdown override (normal rules apply)
        ``"convert_all"`` – convert every declared hard day to technical/rhythm
        ``"deload_all"`` – deload every declared hard day
        ``"cap_one"`` – keep at most one hard day, deload the rest
    """
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return None
    if days < 0 or days > 7:
        return None
    if days <= 5:
        return "convert_all"
    if days == 6:
        return "deload_all"
    # days == 7
    return "cap_one"


def _decide_action(
    *,
    hard_day_count: int,
    fatigue: str,
    cut: str,
    week_press: str,
    injury: dict[str, Any],
    days_until_fight: Any = None,
) -> str | None:
    if hard_day_count <= 0:
        return None

    # --- Countdown-graduated override (deterministic, fires first) ---
    countdown_override = _countdown_sparring_override(days_until_fight)
    if countdown_override == "convert_all":
        return "convert"
    if countdown_override == "deload_all":
        return "deload"
    if countdown_override == "cap_one" and hard_day_count >= 2:
        return "deload"

    # --- Injury-based hard overrides ---
    if injury.get("instability"):
        return "convert"
    if injury.get("daily_symptoms"):
        return "convert"
    if injury.get("worsening") and injury.get("high_risk"):
        return "convert"
    if injury.get("worsening") and week_press == "high":
        return "convert"

    # --- Readiness-based deload ---
    if fatigue == "high" and hard_day_count >= 2:
        return "deload"
    if cut == "high" and hard_day_count >= 2:
        return "deload"
    if fatigue == "high" and cut in {"moderate", "high"} and hard_day_count >= 1:
        return "deload"
    if week_press == "high" and injury.get("severity") == "moderate" and hard_day_count >= 1:
        return "deload"
    if week_press == "high" and hard_day_count >= 2:
        return "deload"

    return None


def _pick_downgrade_target(
    hard_days: list[str],
    *,
    week: dict[str, Any],
) -> str:
    if not hard_days:
        return ""
    if len(hard_days) == 1:
        return hard_days[0]

    protected_day = _main_collision_owner_day(week, hard_days)
    if protected_day:
        for day in reversed(hard_days):
            if day != protected_day:
                return day
        return protected_day

    return hard_days[-1]


def _pick_protected_hard_day(
    hard_days: list[str],
    *,
    week: dict[str, Any],
) -> str:
    if not hard_days:
        return ""
    protected_day = _main_collision_owner_day(week, hard_days)
    if protected_day:
        return protected_day
    return hard_days[0]


def _reason_codes(
    *,
    fatigue: str,
    cut: str,
    week_press: str,
    injury: dict[str, Any],
    hard_day_count: int,
) -> list[str]:
    codes: list[str] = []
    if fatigue == "high":
        codes.append("high_fatigue")
    elif fatigue == "moderate":
        codes.append("moderate_fatigue")
    if cut == "high":
        codes.append("high_cut")
    elif cut == "moderate":
        codes.append("moderate_cut")
    if week_press == "high":
        codes.append("high_week_pressure")
    elif week_press == "moderate":
        codes.append("moderate_week_pressure")
    if injury.get("severity") == "moderate":
        codes.append("moderate_injury")
    elif injury.get("severity") == "high":
        codes.append("high_injury")
    if injury.get("worsening"):
        codes.append("worsening")
    if injury.get("instability"):
        codes.append("instability")
    if injury.get("daily_symptoms"):
        codes.append("daily_symptoms")
    if hard_day_count >= 2:
        codes.append("two_hard_days")
    return codes


def _dose_rank(dose_class: str) -> int:
    return {
        _DOSE_CLASS_HARD_PRIMARY: 0,
        _DOSE_CLASS_HARD_SECONDARY: 1,
        _DOSE_CLASS_HARD_DELOAD: 2,
        _DOSE_CLASS_TECHNICAL_RHYTHM: 3,
    }.get(dose_class, 1)


def compute_hard_sparring_plan(*, week: dict[str, Any], athlete_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    hard_days = _ordered_weekdays(
        week.get("declared_hard_sparring_days")
        or athlete_snapshot.get("hard_sparring_days")
    )
    if not hard_days:
        return []

    fatigue = _fatigue_level(athlete_snapshot)
    cut = _cut_pressure(athlete_snapshot)
    week_press = _week_pressure(week, athlete_snapshot)
    injury = _injury_assessment(athlete_snapshot)
    days_until_fight = athlete_snapshot.get("days_until_fight")
    classes_by_day = _assign_dose_classes(
        hard_days=hard_days,
        week=week,
        fatigue=fatigue,
        cut=cut,
        week_press=week_press,
        injury=injury,
        days_until_fight=days_until_fight,
    )

    reason_codes_list = _reason_codes(
        fatigue=fatigue,
        cut=cut,
        week_press=week_press,
        injury=injury,
        hard_day_count=len(hard_days),
    )
    countdown_override = _countdown_sparring_override(days_until_fight)
    if countdown_override in {"convert_all", "deload_all", "cap_one"} and "fight_week_taper" not in reason_codes_list:
        reason_codes_list.insert(0, "fight_week_taper")
    reason_text = ", ".join(reason_codes_list)
    note_action_by_countdown = {
        "convert_all": "convert",
        "deload_all": "deload",
        "cap_one": "deload",
    }
    plan: list[dict[str, Any]] = []
    for day in hard_days:
        dose_class = classes_by_day.get(day, _DOSE_CLASS_HARD_SECONDARY)
        status = _status_from_dose_class(dose_class)
        entry: dict[str, Any] = {
            "day": day,
            "status": status,
            "effective_load": _effective_load_from_dose_class(dose_class),
            "reason_codes": list(reason_codes_list) if status != "hard_as_planned" else [],
            "reason": reason_text if status != "hard_as_planned" else "",
            "dose_class": dose_class,
            "dose_policy": _dose_policy_from_dose_class(dose_class),
            "dose_rank": _dose_rank(dose_class),
            "dose_profile": _dose_operational_profile(dose_class),
        }
        if countdown_override in note_action_by_countdown and status != "hard_as_planned":
            entry["coach_note"] = _sparring_override_coach_note(
                days_until_fight,
                note_action_by_countdown[countdown_override],
            )
        plan.append(entry)
    return plan


_COUNTDOWN_COACH_NOTES: dict[int, str] = {
    1: (
        "Fight is tomorrow. If sparring happens at all, keep it controlled technical flow "
        "only — no hard contact. Freshness matters more than any final prep hit."
    ),
    2: (
        "Two days out. Pull everything back to rhythm and reads — no hard contact from "
        "here. The work is done; protect what you've built."
    ),
    3: (
        "Three days out. No hard sparring. Keep any pad or bag work sharp and technical "
        "— stay crisp, not flat, and let the body stay ready to perform."
    ),
    4: (
        "Four days out. Move all sparring to controlled, purposeful technical rounds. "
        "Nothing you can gain from hard collision now is worth the cost."
    ),
    5: (
        "Five days to fight. Move sparring to rhythm-only rounds "
        "— bring the technical intent but leave the damage out."
    ),
    6: (
        "Six days out. Pull the intensity back on sparring "
        "— keep rounds lighter and stay focused on timing over damage."
    ),
}


def _sparring_override_coach_note(days_until_fight: Any, action: str) -> str:
    """Generate a taper-driven coach note explaining the sparring change."""
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return ""
    if days in _COUNTDOWN_COACH_NOTES:
        return _COUNTDOWN_COACH_NOTES[days]
    if days == 7 and action == "deload":
        return (
            "Seven days out. With multiple hard sparring sessions this week, one shifts to "
            "reduced intensity to protect the cumulative load going into fight week."
        )
    return ""


def effective_hard_days(plan: list[dict[str, Any]]) -> list[str]:
    return [entry["day"] for entry in plan if entry.get("status") == "hard_as_planned"]


def effective_hard_day_count(plan: list[dict[str, Any]]) -> int:
    return len(effective_hard_days(plan))
