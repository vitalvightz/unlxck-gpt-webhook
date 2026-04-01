"""Deterministic sparring-dose planner.

Single source of truth for per-week sparring-dose decisions.  Computes
``hard_sparring_plan`` for each active week, deciding whether each declared
hard sparring day should remain ``hard_as_planned``, be marked
``deload_suggested``, or be marked ``convert_to_technical_suggested``.

Downstream consumers (weekly role map, advisory layer, day-hint placement)
read from the plan rather than recomputing independently.
"""
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

_HIGH_COLLISION_REGIONS = {
    "ankle",
    "knee",
    "shin",
    "hip",
    "lower_back",
    "foot",
    "achilles",
    "groin",
    "shoulder",
    "neck",
}


def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return [str(v).strip() for v in values if str(v).strip()]
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    return [str(values).strip()]


def _ordered_weekdays(values: Any) -> list[str]:
    cleaned = _clean_list(values)
    unique = list(dict.fromkeys(cleaned))
    return sorted(unique, key=lambda d: _WEEKDAY_ORDER.get(d, 99))


# ── Scoring helpers ──────────────────────────────────────────────────────


def _fatigue_level(athlete_snapshot: dict) -> str:
    return str(athlete_snapshot.get("fatigue", "")).strip().lower()


def _is_high_fatigue(athlete_snapshot: dict) -> bool:
    return _fatigue_level(athlete_snapshot) == "high"


def _cut_pressure(athlete_snapshot: dict) -> str:
    """Return ``'high'``, ``'moderate'``, or ``'none'``."""
    readiness_flags = {
        f.lower() for f in _clean_list(athlete_snapshot.get("readiness_flags", []))
    }

    cut_pct = 0.0
    try:
        cut_pct = float(athlete_snapshot.get("weight_cut_pct", 0) or 0)
    except (TypeError, ValueError):
        pass

    if "aggressive_weight_cut" in readiness_flags or cut_pct >= 5.0:
        return "high"
    if (
        athlete_snapshot.get("weight_cut_risk")
        or "active_weight_cut" in readiness_flags
        or cut_pct >= 3.0
    ):
        return "moderate"
    return "none"


def _week_pressure(week: dict, athlete_snapshot: dict) -> str:
    """Return ``'high'``, ``'moderate'``, or ``'none'``."""
    readiness_flags = {
        f.lower() for f in _clean_list(athlete_snapshot.get("readiness_flags", []))
    }
    phase = str(week.get("phase", "")).strip().upper()
    stage_key = str(week.get("stage_key", "")).strip().lower()

    days_until_fight = athlete_snapshot.get("days_until_fight")
    try:
        days_value = int(days_until_fight)
    except (TypeError, ValueError):
        days_value = None

    if "fight_week" in readiness_flags or "fight_week" in stage_key:
        return "high"
    if phase == "TAPER":
        return "high"
    if days_value is not None and days_value <= 7:
        return "high"
    if days_value is not None and days_value <= 14:
        return "moderate"
    if athlete_snapshot.get("short_notice"):
        return "moderate"
    return "none"


def _injury_assessment(athlete_snapshot: dict) -> dict:
    """Assess injury state for sparring-dose decisions."""
    injuries = _clean_list(athlete_snapshot.get("injuries", []))
    if not injuries:
        return {
            "has_injury": False,
            "high_risk": False,
            "worsening": False,
            "instability": False,
            "daily_symptoms": False,
            "severity": "none",
        }

    high_risk = False
    any_worsening = False
    any_instability = False
    any_daily_symptoms = False
    max_score = 0

    for raw in injuries:
        lowered = str(raw).strip().lower()
        if not lowered:
            continue

        parsed = parse_injury_entry(str(raw).strip()) or {}
        region = str(
            parsed.get("canonical_location") or "unspecified"
        ).strip().lower()

        worsening = any(
            t in lowered
            for t in (
                "worsen",
                "worsening",
                "worse",
                "flared",
                "aggravated",
                "regressing",
            )
        )
        improving = any(
            t in lowered
            for t in ("improving", "better", "settling", "resolved", "resolving")
        )
        stable = any(
            t in lowered
            for t in ("stable", "managed", "manageable", "maintenance")
        )
        instability = any(
            t in lowered
            for t in ("instability", "giving way", "buckled", "locking", "locked")
        )
        daily_symptoms = any(
            t in lowered
            for t in ("rest pain", "daily", "walking", "stairs", "sleep", "constant")
        )
        severe = instability or daily_symptoms or any(
            t in lowered
            for t in ("sharp", "severe", "tear", "rupture", "cannot", "can't")
        )
        moderate = severe or any(
            t in lowered
            for t in (
                "strain",
                "sprain",
                "pain",
                "tendon",
                "tendonitis",
                "tendinopathy",
                "impingement",
                "soreness",
                "stiffness",
                "irritation",
            )
        )

        score = 0
        if moderate:
            score = 2
        if severe:
            score = max(score, 4)
        if worsening:
            score += 2
        if stable:
            score = max(0, score - 1)
        if improving:
            score = max(0, score - 1)
        if daily_symptoms:
            score += 2
        if instability:
            score += 2
        if region in _HIGH_COLLISION_REGIONS:
            score += 1

        max_score = max(max_score, score)
        if worsening:
            any_worsening = True
        if instability:
            any_instability = True
        if daily_symptoms:
            any_daily_symptoms = True

        if (
            instability
            or daily_symptoms
            or (worsening and region in _HIGH_COLLISION_REGIONS)
            or score >= 6
        ):
            high_risk = True

    severity = "none"
    if max_score >= 6 or high_risk:
        severity = "high"
    elif max_score >= 3:
        severity = "moderate"
    elif max_score >= 1:
        severity = "mild"

    return {
        "has_injury": True,
        "high_risk": high_risk,
        "worsening": any_worsening,
        "instability": any_instability,
        "daily_symptoms": any_daily_symptoms,
        "severity": severity,
    }


# ── Core decision logic ─────────────────────────────────────────────────


def _decide_action(
    *,
    hard_day_count: int,
    fatigue: str,
    cut: str,
    week_press: str,
    injury: dict,
) -> str | None:
    """Decide the sparring-dose action.

    Returns ``None`` when no change is warranted (borderline → no action),
    ``'deload'``, or ``'convert'``.
    """
    if hard_day_count == 0:
        return None

    # No change when all signals are mild / absent
    if (
        fatigue in ("low", "moderate")
        and cut == "none"
        and injury["severity"] in ("none", "mild")
        and week_press == "none"
    ):
        return None

    # ── convert_to_technical_suggested (strong red flags) ────────
    if injury.get("instability") or injury.get("daily_symptoms"):
        if (
            week_press in ("high", "moderate")
            or fatigue == "high"
            or hard_day_count >= 2
        ):
            return "convert"
    if injury.get("worsening") and injury.get("high_risk"):
        return "convert"
    if injury.get("worsening") and week_press == "high":
        return "convert"

    # ── deload_suggested (meaningful mismatch) ───────────────────
    if fatigue == "high" and hard_day_count >= 2:
        return "deload"
    if cut == "high" and hard_day_count >= 2:
        return "deload"
    if week_press == "high" and injury["severity"] in ("mild", "moderate"):
        return "deload"
    if fatigue in ("moderate", "high") and cut in ("moderate", "high"):
        return "deload"
    if fatigue == "high" and week_press in ("moderate", "high"):
        return "deload"
    if week_press == "high" and hard_day_count >= 2:
        return "deload"

    # Borderline: do nothing.  False negatives are acceptable.
    return None


def _pick_downgrade_target(hard_days: list[str], week: dict) -> str:
    """Choose which day to downgrade.

    Priority:
    * Preserve the day that best aligns with the week's main collision /
      fight-pace slot (typically the first declared hard day).
    * Downgrade the latest declared hard sparring day first.
    """
    if len(hard_days) <= 1:
        return hard_days[0] if hard_days else ""
    return hard_days[-1]


def _build_reason_codes(
    *,
    fatigue: str,
    cut: str,
    week_press: str,
    injury: dict,
    hard_day_count: int,
) -> list[str]:
    codes: list[str] = []
    if fatigue == "high":
        codes.append("high_fatigue")
    elif fatigue == "moderate":
        codes.append("moderate_fatigue")
    if cut == "high":
        codes.append("aggressive_cut")
    elif cut == "moderate":
        codes.append("active_cut")
    if week_press == "high":
        codes.append("high_week_pressure")
    elif week_press == "moderate":
        codes.append("moderate_week_pressure")
    if injury.get("instability"):
        codes.append("instability")
    if injury.get("worsening"):
        codes.append("worsening_injury")
    if injury.get("daily_symptoms"):
        codes.append("daily_symptoms")
    elif injury["severity"] not in ("none",):
        codes.append("injury_present")
    if hard_day_count >= 2:
        codes.append("multiple_hard_days")
    return codes


def _status_summary(action: str, day: str, reason_codes: list[str]) -> str:
    codes_label = " + ".join(reason_codes) if reason_codes else "threshold crossed"
    if action == "convert":
        return (
            f"Convert hard sparring on {day} to technical rounds; {codes_label}."
        )
    return f"Deload hard sparring on {day}; {codes_label}."


# ── Public API ───────────────────────────────────────────────────────────


def compute_hard_sparring_plan(
    *,
    week: dict[str, Any],
    athlete_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute per-day sparring status for each declared hard sparring day.

    Each entry contains:
      day            – weekday name
      status         – ``hard_as_planned`` | ``deload_suggested`` |
                       ``convert_to_technical_suggested``
      effective_load – ``hard`` | ``reduced`` | ``technical``
      reason_codes   – contributing factors (empty when hard_as_planned)
      reason         – human-readable explanation (empty when hard_as_planned)
      summary        – short summary (empty when hard_as_planned)
    """
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
                "summary": "",
            }
            for day in hard_days
        ]

    reason_codes = _build_reason_codes(
        fatigue=fatigue,
        cut=cut,
        week_press=week_press,
        injury=injury,
        hard_day_count=len(hard_days),
    )

    status = (
        "convert_to_technical_suggested"
        if action == "convert"
        else "deload_suggested"
    )
    effective_load = "technical" if action == "convert" else "reduced"

    target_day = _pick_downgrade_target(hard_days, week)

    reason_text = " + ".join(reason_codes) if reason_codes else ""
    summary_text = _status_summary(action, target_day, reason_codes)

    entries: list[dict[str, Any]] = []
    for day in hard_days:
        if day == target_day:
            entries.append(
                {
                    "day": day,
                    "status": status,
                    "effective_load": effective_load,
                    "reason_codes": list(reason_codes),
                    "reason": reason_text,
                    "summary": summary_text,
                }
            )
        else:
            entries.append(
                {
                    "day": day,
                    "status": "hard_as_planned",
                    "effective_load": "hard",
                    "reason_codes": [],
                    "reason": "",
                    "summary": "",
                }
            )
    return entries


def effective_hard_days(plan: list[dict[str, Any]]) -> list[str]:
    """Return the days that still count as effective hard sparring."""
    return [entry["day"] for entry in plan if entry["status"] == "hard_as_planned"]


def effective_hard_day_count(plan: list[dict[str, Any]]) -> int:
    """Return how many days still count as effective hard sparring."""
    return len(effective_hard_days(plan))
