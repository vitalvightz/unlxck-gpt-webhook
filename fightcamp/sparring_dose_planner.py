from __future__ import annotations

from typing import Any

from .injury_formatting import parse_injury_entry

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


def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    return [str(values).strip()]


def _ordered_weekdays(values: Any) -> list[str]:
    cleaned = _clean_list(values)
    unique = list(dict.fromkeys(cleaned))
    return sorted(unique, key=lambda day: (_WEEKDAY_ORDER.get(day, 99), day.lower()))


def _fatigue_level(athlete_snapshot: dict[str, Any]) -> str:
    fatigue = str(athlete_snapshot.get("fatigue") or "").strip().lower()
    return fatigue if fatigue in {"low", "moderate", "high"} else "low"


def _cut_pressure(athlete_snapshot: dict[str, Any]) -> str:
    readiness_flags = {flag.lower() for flag in _clean_list(athlete_snapshot.get("readiness_flags", []))}
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
    readiness_flags = {flag.lower() for flag in _clean_list(athlete_snapshot.get("readiness_flags", []))}
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

    for raw_entry in _clean_list(athlete_snapshot.get("injuries", [])):
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


def _decide_action(
    *,
    hard_day_count: int,
    fatigue: str,
    cut: str,
    week_press: str,
    injury: dict[str, Any],
) -> str | None:
    if hard_day_count <= 0:
        return None

    if injury.get("instability"):
        return "convert"
    if injury.get("daily_symptoms"):
        return "convert"
    if injury.get("worsening") and injury.get("high_risk"):
        return "convert"
    if injury.get("worsening") and week_press == "high":
        return "convert"

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

    action = _decide_action(
        hard_day_count=len(hard_days),
        fatigue=fatigue,
        cut=cut,
        week_press=week_press,
        injury=injury,
    )
    if action is None:
        return [
            {
                "day": day,
                "status": "hard_as_planned",
                "effective_load": "hard",
                "reason_codes": [],
                "reason": "",
            }
            for day in hard_days
        ]

    target_day = _pick_downgrade_target(hard_days, week=week)
    reason_codes = _reason_codes(
        fatigue=fatigue,
        cut=cut,
        week_press=week_press,
        injury=injury,
        hard_day_count=len(hard_days),
    )
    target_status = "convert_to_technical_suggested" if action == "convert" else "deload_suggested"
    target_load = "technical" if action == "convert" else "reduced"
    target_reason = ", ".join(reason_codes)

    plan: list[dict[str, Any]] = []
    for day in hard_days:
        if day == target_day:
            plan.append(
                {
                    "day": day,
                    "status": target_status,
                    "effective_load": target_load,
                    "reason_codes": list(reason_codes),
                    "reason": target_reason,
                }
            )
            continue
        plan.append(
            {
                "day": day,
                "status": "hard_as_planned",
                "effective_load": "hard",
                "reason_codes": [],
                "reason": "",
            }
        )
    return plan


def effective_hard_days(plan: list[dict[str, Any]]) -> list[str]:
    return [entry["day"] for entry in plan if entry.get("status") == "hard_as_planned"]


def effective_hard_day_count(plan: list[dict[str, Any]]) -> int:
    return len(effective_hard_days(plan))