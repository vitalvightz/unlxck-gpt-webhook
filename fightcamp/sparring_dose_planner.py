from __future__ import annotations

import re
from typing import Any

from .fight_date_utils import d_day_for_weekday
from .injury_formatting import parse_injury_entry
from .normalization import clean_list, ordered_weekdays as _ordered_weekdays
from .weight_cut import compute_cut_severity_score, cut_severity_bucket

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




def _fatigue_level(athlete_snapshot: dict[str, Any]) -> str:
    fatigue = str(athlete_snapshot.get("fatigue") or "").strip().lower()
    # Critical / extreme are more severe than high; collapse them to "high" so
    # every downstream `fatigue == "high"` deload gate (including the D-21..D-18
    # bridge override) treats them at least as conservatively as a high load.
    if fatigue in {"critical", "extreme"}:
        return "high"
    return fatigue if fatigue in {"low", "moderate", "high"} else "low"


def _cut_pressure(athlete_snapshot: dict[str, Any]) -> str:
    cut_bucket = str(athlete_snapshot.get("cut_severity_bucket") or "").strip().lower()
    if not cut_bucket:
        cut_bucket = cut_severity_bucket(
            compute_cut_severity_score(
                athlete_snapshot.get("weight_cut_pct"),
                athlete_snapshot.get("days_until_fight"),
            )
        )
    if cut_bucket in {"high", "critical", "extreme"}:
        return "high"
    if cut_bucket == "moderate":
        return "moderate"
    return "none"


def _days_until_fight_int(athlete_snapshot: dict[str, Any]) -> int | None:
    try:
        return int(athlete_snapshot.get("days_until_fight"))
    except (TypeError, ValueError):
        return None


def _week_pressure(week: dict[str, Any], athlete_snapshot: dict[str, Any]) -> str:
    day_value = _days_until_fight_int(athlete_snapshot)

    if _is_final_week_sparring_cap_active(week, athlete_snapshot):
        return "high"
    if athlete_snapshot.get("short_notice") or (day_value is not None and day_value <= 14):
        return "moderate"
    return "none"


def _is_final_week_sparring_cap_active(week: dict[str, Any], athlete_snapshot: dict[str, Any]) -> bool:
    readiness_flags = {flag.lower() for flag in clean_list(athlete_snapshot.get("readiness_flags", []))}
    phase = str(week.get("phase") or "").strip().upper()
    stage_key = str(week.get("stage_key") or "").strip().lower()
    day_value = _days_until_fight_int(athlete_snapshot)
    return (
        phase == "TAPER"
        or "fight_week" in readiness_flags
        or "fight_week" in stage_key
        or (day_value is not None and 0 <= day_value <= 7)
    )


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
    """Final fight-week override.

    D-17 to D-0 converts every declared hard sparring day to technical/rhythm.
    Bridge-window caps are handled separately by _bridge_window_sparring_override().
    """
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return None

    return "convert_all" if 0 <= days <= 17 else None


def _bridge_window_sparring_override(
    week: dict[str, Any], athlete_snapshot: dict[str, Any]
) -> str | None:
    """Week-aware bridge-window (D-21 to D-14) sparring override.

    Only fires when the week being evaluated is the imminent bridge week —
    i.e. ``phase == "TAPER"`` or the week's stage_key / readiness_flags mark
    it as the current bridge compression window. Future-planning weeks at
    the same days_until_fight value stay untouched so advisories can still
    use their "if the current picture carries forward" conditional wording.

    Return values reflect the evidence review:
      D-21 to D-18 (clean / low-risk)   → cap_one
      D-21 to D-18 (fatigue high or
        cut high)                       → deload_all
      D-17 to D-14                      → convert_all

    A moderate active cut is note-only and no longer forces deload_all here —
    only high+ fatigue / cut pressure removes hard sparring.
    """
    days = _days_until_fight_int(athlete_snapshot)
    if days is None or not (14 <= days <= 21):
        return None

    phase = str(week.get("phase") or "").strip().upper()
    stage_key = str(week.get("stage_key") or "").strip().lower()
    readiness_flags = {flag.lower() for flag in clean_list(athlete_snapshot.get("readiness_flags", []))}
    phase_week_index = week.get("phase_week_index")

    is_imminent = (
        phase == "TAPER"
        or "bridge" in stage_key
        or "taper" in stage_key
        or "fight_week" in readiness_flags
        or (isinstance(phase_week_index, int) and phase_week_index <= 1)
    )
    if not is_imminent:
        return None

    if 14 <= days <= 17:
        return "convert_all"

    # 18 <= days <= 21: cap_one is the clean-athlete default, but high-fatigue
    # or a high+ cut forces zero hard sparring via deload_all. A moderate cut is
    # note-only and keeps the clean-athlete cap_one behaviour.
    fatigue = _fatigue_level(athlete_snapshot)
    cut = _cut_pressure(athlete_snapshot)
    if fatigue == "high":
        return "deload_all"
    if cut == "high":
        return "deload_all"
    return "cap_one"


def _is_d_window_stage(stage_key: Any) -> bool:
    stage = str(stage_key or "").strip().lower()
    if not stage:
        return False
    if re.fullmatch(r"d\d+", stage):
        return True
    return re.fullmatch(r"d\d+_to_d\d+", stage) is not None


def _standard_camp_final_two_weeks_override(week: dict[str, Any]) -> str | None:
    """For regular (non D-window) camps, suppress hard sparring in final taper week(s).

    Behaviour by TAPER layout:

    * Single-week TAPER (``phase_week_total == 1``): use ``cap_one`` so a
      compressed taper can still keep one effective hard sparring day. The
      ``final_week_sparring_cap`` mechanism in ``_lock_declared_hard_sparring_roles``
      then enforces the 1-day ceiling and surfaces the surviving day as
      ``effective_hard_sparring_days``.
    * Multi-week TAPER (``phase_week_total >= 2``): keep the existing
      ``deload_all`` policy for the last 2 weeks so longer tapers fully
      remove hard sparring in their final week.
    """
    phase = str(week.get("phase") or "").strip().upper()
    if phase != "TAPER":
        return None

    if _is_d_window_stage(week.get("stage_key")):
        return None

    phase_week_index = week.get("phase_week_index")
    phase_week_total = week.get("phase_week_total")
    if isinstance(phase_week_index, int) and isinstance(phase_week_total, int) and phase_week_total >= 1:
        if phase_week_total == 1:
            return "cap_one"
        if phase_week_index >= max(1, phase_week_total - 1):
            return "deload_all"
        return None

    # Fallback when week-position metadata is unavailable.
    projected_days = week.get("projected_days_until_fight_start")
    if not isinstance(projected_days, int):
        return None
    if projected_days < 0:
        return None
    if projected_days > 14:
        return None
    return "deload_all"


def _decide_action(
    *,
    hard_day_count: int,
    fatigue: str,
    cut: str,
    week_press: str,
    injury: dict[str, Any],
    days_until_fight: Any = None,
    bridge_override: str | None = None,
) -> str | None:
    if hard_day_count <= 0:
        return None

    # --- Countdown-graduated override (deterministic, fires first) ---
    countdown_override = _countdown_sparring_override(days_until_fight) or bridge_override
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

    # High-pressure environment with any active injury overrides readiness ordering.
    if week_press == "high" and injury.get("severity") == "moderate" and hard_day_count >= 1:
        return "deload"
    # Four or more hard days in a single week exceeds safe density regardless of readiness signals.
    if hard_day_count >= 4:
        return "deload"
    # Three hard days with two or more amber readiness signals: the "well-spaced, ready" allowance
    # does not hold — deload one.
    if hard_day_count >= 3:
        amber_signals = sum(
            1 for signal in (fatigue, cut, week_press) if signal in {"moderate", "high"}
        )
        if amber_signals >= 2:
            return "deload"

    # --- Readiness-based deload ---
    if fatigue == "high" and hard_day_count >= 2:
        return "deload"
    if cut == "high" and hard_day_count >= 2:
        return "deload"
    if fatigue == "high" and cut in {"moderate", "high"} and hard_day_count >= 1:
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
    if hard_day_count >= 4:
        codes.append("four_hard_days")
    return codes


def _with_final_week_cap_reason(codes: list[str]) -> list[str]:
    updated = list(codes)
    if "fight_week_taper" not in updated:
        updated.insert(0, "fight_week_taper")
    if "final_week_sparring_cap" not in updated:
        updated.append("final_week_sparring_cap")
    return updated


def _final_week_cap_reason(codes: list[str]) -> str:
    reason = ", ".join(codes)
    cap_note = (
        "Final taper week cap: keep at most one effective hard sparring day, even when the "
        "declared coach schedule includes more. Extra declared hard days should become managed "
        "technical or reduced-contact work to protect freshness."
    )
    return f"{reason}; {cap_note}" if reason else cap_note


def _hard_day_class(
    entry: dict[str, Any],
    *,
    protected_day: str,
    hard_days: list[str],
) -> str:
    if entry.get("effective_load") != "hard":
        return "managed_hard"
    day = entry["day"]
    if protected_day:
        return "primary_hard" if day == protected_day else "secondary_hard"
    if hard_days and day == hard_days[0]:
        return "primary_hard"
    return "secondary_hard"


def _annotate_hard_day_classes(
    plan: list[dict[str, Any]],
    *,
    protected_day: str,
    hard_days: list[str],
) -> list[dict[str, Any]]:
    return [
        {**e, "hard_day_class": _hard_day_class(e, protected_day=protected_day, hard_days=hard_days)}
        for e in plan
    ]


def _consecutive_hard_day_pairs(hard_days: list[str]) -> list[tuple[str, str]]:
    """Return (earlier, later) pairs of hard days that are calendar-adjacent."""
    order = {k.lower(): v for k, v in _WEEKDAY_ORDER.items()}
    pairs = []
    for i in range(len(hard_days) - 1):
        idx_a = order.get(hard_days[i].lower(), -1)
        idx_b = order.get(hard_days[i + 1].lower(), -1)
        if idx_b - idx_a == 1:
            pairs.append((hard_days[i], hard_days[i + 1]))
    return pairs


def sandwiched_training_days(
    training_days: list[str],
    effective_hard_days_set: set[str],
) -> set[str]:
    """Non-spar training days that fall between two effective hard spar days in the week."""
    if len(effective_hard_days_set) < 2:
        return set()
    order = {k.lower(): v for k, v in _WEEKDAY_ORDER.items()}
    hard_indices = sorted([order[d.lower()] for d in effective_hard_days_set if d.lower() in order])
    if len(hard_indices) < 2:
        return set()

    min_idx, max_idx = hard_indices[0], hard_indices[-1]
    result: set[str] = set()
    for day in training_days:
        if day in effective_hard_days_set:
            continue
        idx = order.get(day.lower(), -1)
        if min_idx < idx < max_idx:
            result.add(day)
    return result


def _apply_consecutive_deloads(
    plan: list[dict[str, Any]],
    *,
    hard_days: list[str],
    protected_day: str,
) -> list[dict[str, Any]]:
    """Deload the later day of any still-hard consecutive pair (earlier if later is protected)."""
    plan_by_day = {e["day"]: dict(e) for e in plan}
    for earlier, later in _consecutive_hard_day_pairs(hard_days):
        if (
            plan_by_day.get(earlier, {}).get("effective_load") != "hard"
            or plan_by_day.get(later, {}).get("effective_load") != "hard"
        ):
            continue
        target = later if later != protected_day else earlier
        entry = plan_by_day[target]
        codes = list(entry.get("reason_codes") or [])
        if "consecutive_hard_days" not in codes:
            codes.append("consecutive_hard_days")
        plan_by_day[target] = {
            **entry,
            "status": "deload_suggested",
            "effective_load": "reduced",
            "reason_codes": codes,
            "reason": entry.get("reason") or "consecutive_hard_days",
        }
    return [plan_by_day[d] for d in hard_days]


def _apply_hard_day_cap(
    plan: list[dict[str, Any]],
    *,
    hard_days: list[str],
    protected_day: str,
    cap: int = 2,
) -> list[dict[str, Any]]:
    """Reduce effective hard days to at most cap, targeting least-protected days first."""
    plan_by_day = {e["day"]: dict(e) for e in plan}
    while True:
        effective = [d for d in hard_days if plan_by_day[d].get("effective_load") == "hard"]
        if len(effective) <= cap:
            break
        target = next((d for d in reversed(effective) if d != protected_day), effective[-1])
        entry = plan_by_day[target]
        codes = list(entry.get("reason_codes") or [])
        if "hard_day_cap" not in codes:
            codes.append("hard_day_cap")
        existing_reason = entry.get("reason") or ""
        cap_note = (
            "Four or more hard sparring sessions were declared this week. "
            "This session is preserved in the schedule as a managed/deloaded exposure "
            "to protect load quality across the full week — the slot is not removed."
        )
        new_reason = f"{existing_reason}; {cap_note}".lstrip("; ") if existing_reason else cap_note
        plan_by_day[target] = {
            **entry,
            "status": "deload_suggested",
            "effective_load": "reduced",
            "reason_codes": codes,
            "reason": new_reason,
        }
    return [plan_by_day[d] for d in hard_days]


def _per_day_d_days(
    week: dict[str, Any], hard_days: list[str]
) -> dict[str, int]:
    """Return per-weekday D-day for declared hard sparring days in this week.

    Skips days when the week's calendar metadata is missing (e.g. legacy
    callers that have not threaded fight_weekday / projected_days_until_fight_end
    through). Per-day countdown rules are no-ops when this returns empty.
    """
    fight_weekday = week.get("fight_weekday")
    end_d = week.get("projected_days_until_fight_end")
    span = week.get("span_days")
    if not fight_weekday or not isinstance(end_d, int) or not isinstance(span, int):
        return {}
    result: dict[str, int] = {}
    for day in hard_days:
        d_day = d_day_for_weekday(
            day,
            fight_weekday=fight_weekday,
            projected_days_until_fight_end=end_d,
            span_days=span,
        )
        if d_day is not None:
            result[day] = d_day
    return result


def _apply_per_day_countdown_overrides(
    plan: list[dict[str, Any]],
    *,
    week: dict[str, Any],
    hard_days: list[str],
    protected_day: str,
) -> list[dict[str, Any]]:
    """Per-day calendar authority: ban D-17 onward, cap D-21..D-18 at one.

    D-18 is the last allowed hard-spar day if already declared. D-17 and closer
    convert to technical/rhythm/reduced-contact regardless of declaration.

    Acts on each declared hard sparring day individually using its own D-day
    inside the week — independent of phase/stage labels. This is the rule that
    makes normal-camp weeks countdown-aware.
    """
    per_day = _per_day_d_days(week, hard_days)
    if not per_day:
        return plan
    plan_by_day = {e["day"]: dict(e) for e in plan}

    # D-17 and closer: convert to technical/rhythm/reduced-contact.
    for day, d_day in per_day.items():
        if d_day > 17 or d_day < 0:
            continue
        entry = plan_by_day.get(day)
        if entry is None:
            continue
        codes = list(entry.get("reason_codes") or [])
        if "d17_hard_sparring_ban" not in codes:
            codes.append("d17_hard_sparring_ban")
        plan_by_day[day] = {
            **entry,
            "status": "convert_to_technical_suggested",
            "effective_load": "technical",
            "reason_codes": codes,
            "reason": entry.get("reason")
            or "D-17 onward: hard sparring banned; convert to technical/rhythm only. No effective hard sparring allowed.",
            "coach_note": entry.get("coach_note")
            or _sparring_override_coach_note(d_day, "convert"),
            "d_day": d_day,
        }

    # D-21 to D-18: cap at one effective hard exposure across that band.
    band_days = [d for d, dd in per_day.items() if 18 <= dd <= 21]
    band_days_sorted = [d for d in hard_days if d in band_days]
    if len(band_days_sorted) >= 2:
        keeper = (
            protected_day
            if protected_day in band_days_sorted
            else band_days_sorted[0]
        )
        for day in band_days_sorted:
            if day == keeper:
                continue
            entry = plan_by_day.get(day)
            if entry is None or entry.get("effective_load") != "hard":
                continue
            codes = list(entry.get("reason_codes") or [])
            if "d21_d18_cap_one" not in codes:
                codes.append("d21_d18_cap_one")
            plan_by_day[day] = {
                **entry,
                "status": "deload_suggested",
                "effective_load": "reduced",
                "reason_codes": codes,
                "reason": entry.get("reason")
                or "D-21 to D-18: cap to one effective hard sparring exposure.",
                "d_day": per_day[day],
            }

    # Stamp d_day on every other entry too so downstream consumers see the
    # calendar reasoning regardless of whether the override fired.
    for day, d_day in per_day.items():
        entry = plan_by_day.get(day)
        if entry is not None and "d_day" not in entry:
            plan_by_day[day] = {**entry, "d_day": d_day}

    return [plan_by_day[d] for d in hard_days]


def _finalize_plan(
    plan: list[dict[str, Any]],
    *,
    hard_days: list[str],
    protected_day: str,
    week: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run the post-processing pipeline: consecutive-pair deload, 4+ day cap, classification.

    Centralizes invariants so every return path in ``compute_hard_sparring_plan``
    is guaranteed to pass through the same rules regardless of which branch produced
    the plan. Consecutive and cap passes are no-ops when no eligible pairs remain.
    """
    if week is not None:
        plan = _apply_per_day_countdown_overrides(
            plan, week=week, hard_days=hard_days, protected_day=protected_day
        )
    plan = _apply_consecutive_deloads(plan, hard_days=hard_days, protected_day=protected_day)
    if len(hard_days) >= 4:
        plan = _apply_hard_day_cap(plan, hard_days=hard_days, protected_day=protected_day)
    return _annotate_hard_day_classes(plan, protected_day=protected_day, hard_days=hard_days)


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
    protected_day = _pick_protected_hard_day(hard_days, week=week)
    bridge_override = _bridge_window_sparring_override(week, athlete_snapshot)
    if bridge_override is None:
        bridge_override = _standard_camp_final_two_weeks_override(week)

    action = _decide_action(
        hard_day_count=len(hard_days),
        fatigue=fatigue,
        cut=cut,
        week_press=week_press,
        injury=injury,
        days_until_fight=days_until_fight,
        bridge_override=bridge_override,
    )
    if action is None:
        plan: list[dict[str, Any]] = [
            {
                "day": day,
                "status": "hard_as_planned",
                "effective_load": "hard",
                "reason_codes": [],
                "reason": "",
            }
            for day in hard_days
        ]
        return _finalize_plan(plan, hard_days=hard_days, protected_day=protected_day, week=week)

    reason_codes_list = _reason_codes(
        fatigue=fatigue,
        cut=cut,
        week_press=week_press,
        injury=injury,
        hard_day_count=len(hard_days),
    )
    target_status = "convert_to_technical_suggested" if action == "convert" else "deload_suggested"
    target_load = "technical" if action == "convert" else "reduced"
    target_reason = ", ".join(reason_codes_list)

    # --- Countdown-graduated: convert_all / deload_all apply to EVERY day ---
    countdown_override = _countdown_sparring_override(days_until_fight) or bridge_override
    if countdown_override in {"convert_all", "deload_all"}:
        countdown_codes = _with_final_week_cap_reason(reason_codes_list)
        countdown_reason = ", ".join(countdown_codes)
        plan = [
            {
                "day": day,
                "status": target_status,
                "effective_load": target_load,
                "reason_codes": list(countdown_codes),
                "reason": countdown_reason,
                "coach_note": _sparring_override_coach_note(days_until_fight, action),
            }
            for day in hard_days
        ]
        return _finalize_plan(plan, hard_days=hard_days, protected_day=protected_day, week=week)

    # --- Final-week cap: keep only one hard day and downgrade the rest ---
    if countdown_override == "cap_one" or (
        len(hard_days) >= 2 and _is_final_week_sparring_cap_active(week, athlete_snapshot)
    ):
        countdown_codes = _with_final_week_cap_reason(reason_codes_list)
        countdown_reason = _final_week_cap_reason(countdown_codes)

        plan: list[dict[str, Any]] = []
        for day in hard_days:
            if day == protected_day:
                plan.append(
                    {
                        "day": day,
                        "status": "hard_as_planned",
                        "effective_load": "hard",
                        "reason_codes": [],
                        "reason": "",
                    }
                )
                continue
            plan.append(
                {
                    "day": day,
                    "status": target_status,
                    "effective_load": target_load,
                    "reason_codes": list(countdown_codes),
                    "reason": countdown_reason,
                    "coach_note": _sparring_override_coach_note(days_until_fight, action)
                    or _final_week_sparring_cap_coach_note(),
                }
            )
        return _finalize_plan(plan, hard_days=hard_days, protected_day=protected_day, week=week)

    # --- Single-target downgrade (readiness-based only) ---
    target_day = _pick_downgrade_target(hard_days, week=week)

    plan: list[dict[str, Any]] = []
    for day in hard_days:
        if day == target_day:
            plan.append(
                {
                    "day": day,
                    "status": target_status,
                    "effective_load": target_load,
                    "reason_codes": list(reason_codes_list),
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
    return _finalize_plan(plan, hard_days=hard_days, protected_day=protected_day, week=week)


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
        "Six days out. No hard sparring — keep only technical/rhythm rounds "
        "and stay focused on timing over damage."
    ),
    14: (
        "Fourteen days out. Hard sparring is still banned in this countdown window. "
        "Keep rounds technical, brief, and low-contact."
    ),
    15: (
        "Fifteen days out. The D-17 hard-sparring ban is already active — "
        "convert any declared hard day to technical/rhythm work; no hard contact."
    ),
    16: (
        "Sixteen days out. The D-17 hard-sparring ban is active — "
        "technical rhythm only, with no effective hard sparring."
    ),
    17: (
        "Seventeen days out. Hard sparring is banned from here onward; "
        "convert declared hard days to technical/rhythm only."
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
    if 7 <= days <= 17 and action == "convert":
        return (
            f"D-{days}: inside the D-17 hard-sparring ban. Convert this declared hard "
            "day to technical/rhythm work — no effective hard sparring allowed."
        )
    return ""


def _final_week_sparring_cap_coach_note() -> str:
    return (
        "Final taper week: keep only one effective hard sparring day. If the declared coach "
        "schedule has more, keep the priority collision day and make the rest reduced-contact "
        "or technical so freshness wins over extra damage."
    )


def effective_hard_days(plan: list[dict[str, Any]]) -> list[str]:
    return [entry["day"] for entry in plan if entry.get("status") == "hard_as_planned"]


def effective_hard_day_count(plan: list[dict[str, Any]]) -> int:
    return len(effective_hard_days(plan))
