from __future__ import annotations

from typing import Any

from .injury_formatting import parse_injury_entry
from .sparring_dose_planner import compute_hard_sparring_plan, effective_hard_day_count
from .weight_cut import compute_weight_cut_pct

_ORDERED_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
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
_LOWER_LIMB_REGIONS = {"ankle", "knee", "shin", "hip", "foot", "achilles", "groin"}
_UPPER_BODY_COLLISION_REGIONS = {"shoulder", "neck"}
_TORSO_REGIONS = {"lower_back", "ribs"}
_DISCLAIMER = "Treat this as a flag, not an automatic change to your saved plan."
_SPARRING_INJURY_STATE_SCORE_CAP = 10


def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    return [str(values).strip()]


def _humanize_token(value: str) -> str:
    return str(value or "").strip().replace("_", " ")


def _ordered_weekdays(values: Any) -> list[str]:
    cleaned = _clean_list(values)
    order = {day: idx for idx, day in enumerate(_ORDERED_WEEKDAYS)}
    unique = list(dict.fromkeys(cleaned))
    return sorted(unique, key=lambda day: order.get(day, len(order)))


def _is_past_weekday(day: str, plan_creation_weekday: str | None) -> bool:
    """Return True if this weekday has already elapsed relative to the plan creation day."""
    if not plan_creation_weekday:
        return False
    _order = {d.lower(): i for i, d in enumerate(_ORDERED_WEEKDAYS)}
    creation_idx = _order.get(plan_creation_weekday.strip().lower())
    day_idx = _order.get(day.strip().lower())
    if creation_idx is None or day_idx is None:
        return False
    return day_idx < creation_idx


def _days_list_phrase(days: list[str]) -> str:
    """Return a natural-language phrase joining a list of weekday names."""
    if not days:
        return "all remaining sparring"
    if len(days) == 1:
        return days[0]
    if len(days) == 2:
        return f"{days[0]} and {days[1]}"
    return ", ".join(days[:-1]) + f", and {days[-1]}"


def _athlete_snapshot(planning_brief: dict[str, Any]) -> dict[str, Any]:
    snapshot = planning_brief.get("athlete_snapshot")
    if isinstance(snapshot, dict):
        return snapshot
    athlete_model = planning_brief.get("athlete_model")
    if isinstance(athlete_model, dict):
        return athlete_model
    return {}


def _active_cut_pct(athlete_snapshot: dict[str, Any]) -> float:
    pct = athlete_snapshot.get("weight_cut_pct")
    if pct is not None:
        try:
            return max(0.0, float(pct))
        except (TypeError, ValueError):
            return 0.0

    return compute_weight_cut_pct(
        athlete_snapshot.get("weight"),
        athlete_snapshot.get("target_weight"),
    )


def _fatigue_score(athlete_snapshot: dict[str, Any]) -> tuple[int, str | None]:
    fatigue = str(athlete_snapshot.get("fatigue", "")).strip().lower()
    if fatigue == "high":
        return 2, "fatigue is already high"
    if fatigue == "moderate":
        return 1, "fatigue is already elevated"
    return 0, None


def _cut_score(athlete_snapshot: dict[str, Any], *, cut_pct: float) -> tuple[int, str | None]:
    readiness_flags = {flag.lower() for flag in _clean_list(athlete_snapshot.get("readiness_flags", []))}
    has_active_cut_flag = "active_weight_cut" in readiness_flags

    if cut_pct >= 5.0:
        return 2, f"cut pressure is meaningful at about {cut_pct:.1f}%"
    if cut_pct >= 3.0:
        return 1, f"an active cut is still in play at about {cut_pct:.1f}%"
    if has_active_cut_flag:
        return 1, "an active cut is already in play"
    return 0, None


def _pressure_score(week: dict[str, Any], athlete_snapshot: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    phase = str(week.get("phase", "")).strip().upper()
    stage_key = str(week.get("stage_key", "")).strip().lower()
    readiness_flags = {flag.lower() for flag in _clean_list(athlete_snapshot.get("readiness_flags", []))}

    if phase == "TAPER":
        score += 2
        reasons.append("this is taper")

    if "fight_week" in readiness_flags or "fight_week" in stage_key:
        score += 3
        reasons.append("fight-week pressure is active")

    days_until_fight = athlete_snapshot.get("days_until_fight")
    try:
        days_value = int(days_until_fight)
    except (TypeError, ValueError):
        days_value = None
    if days_value is not None:
        if days_value <= 7:
            score += 2
        elif days_value <= 14:
            score += 1

    if athlete_snapshot.get("short_notice") or "short_notice" in readiness_flags:
        score += 1

    return score, reasons


def _week_major_minor_pressure(week: dict[str, Any], athlete_snapshot: dict[str, Any]) -> tuple[int, int]:
    readiness_flags = {flag.lower() for flag in _clean_list(athlete_snapshot.get("readiness_flags", []))}
    stage_key = str(week.get("stage_key", "")).strip().lower()
    phase = str(week.get("phase", "")).strip().upper()

    major = 0
    minor = 0
    if phase == "TAPER" or "fight_week" in readiness_flags or "fight_week" in stage_key:
        major = 1

    days_until_fight = athlete_snapshot.get("days_until_fight")
    try:
        days_value = int(days_until_fight)
    except (TypeError, ValueError):
        days_value = None
    if days_value is not None:
        if days_value <= 7:
            major = 1
        elif days_value <= 14:
            minor = 1

    if athlete_snapshot.get("short_notice") or "short_notice" in readiness_flags:
        minor = 1

    return major, minor


# ---------------------------------------------------------------------------
# v2 tiered scoring helpers
# ---------------------------------------------------------------------------

_BAND_ORDER = ("green", "amber", "red", "black")
_BAND_INDEX = {band: idx for idx, band in enumerate(_BAND_ORDER)}
_SEVERITY_TIER_INDEX = {"low": 0, "moderate": 1, "high": 2}
_TRAJECTORY_INDEX = {"improving": 0, "unknown": 1, "stable": 1, "worsening": 2}
_COLLISION_CONTEXT_INDEX = {
    "low_collision": 0,
    "torso": 1,
    "upper_body_collision": 2,
    "lower_limb": 2,
    "unspecified": 2,
}


def _max_band(*bands: str) -> str:
    return max(bands, key=lambda b: _BAND_INDEX.get(b, 0))


def _classify_severity_tier(lowered: str) -> str:
    if any(token in lowered for token in ("severe", "tear", "rupture", "fracture")):
        return "high"
    if any(token in lowered for token in ("cannot", "can't", "can\u2019t")):
        return "high"
    if "sharp" in lowered and any(token in lowered for token in ("cannot", "can't", "can\u2019t", "loss", "lose")):
        return "high"
    if any(token in lowered for token in ("strain", "sprain", "tendon", "tendonitis", "tendinopathy", "impingement")):
        return "moderate"
    if any(token in lowered for token in ("pain", "soreness", "stiffness", "irritation", "ache")):
        return "low"
    return "low"


def _classify_trajectory(worsening: bool, stable: bool, improving: bool) -> str:
    if worsening:
        return "worsening"
    if stable:
        return "stable"
    if improving:
        return "improving"
    return "unknown"


def _detect_override_flags(lowered: str, instability: bool, daily_symptoms: bool) -> list[str]:
    flags: list[str] = []
    if instability:
        flags.append("instability")
    if "locking" in lowered or "locked" in lowered:
        if "instability" not in flags:
            flags.append("locking")
    if "giving way" in lowered:
        flags.append("giving_way")
    if "rest pain" in lowered:
        flags.append("rest_pain")
    if daily_symptoms:
        flags.append("daily_symptoms")
    if any(token in lowered for token in ("cannot", "can't", "can\u2019t")):
        flags.append("cannot_load")
    if "sharp" in lowered and any(token in lowered for token in ("cannot", "can't", "can\u2019t", "loss", "lose")):
        flags.append("sharp_with_function_loss")
    return flags


def _classify_collision_context(region: str) -> str:
    if region in _LOWER_LIMB_REGIONS:
        return "lower_limb"
    if region in _UPPER_BODY_COLLISION_REGIONS:
        return "upper_body_collision"
    if region in _TORSO_REGIONS:
        return "torso"
    if region == "unspecified":
        return "unspecified"
    return "low_collision"


def _resolve_risk_band(
    severity_tier: str,
    trajectory: str,
    override_flags: list[str],
    collision_context: str,
) -> str:
    band = {"high": "red", "moderate": "amber", "low": "green"}.get(severity_tier, "green")

    if override_flags:
        band = _max_band(band, "red")

    if severity_tier == "high" and trajectory == "worsening":
        band = "black"
    elif severity_tier == "moderate" and trajectory == "worsening":
        band = _max_band(band, "red")
    elif severity_tier == "low" and trajectory == "worsening":
        band = _max_band(band, "amber")

    if severity_tier == "low" and trajectory in ("stable", "unknown") and not override_flags:
        if collision_context in ("lower_limb", "upper_body_collision", "unspecified"):
            band = _max_band(band, "amber")

    return band


def _derive_band_score(
    risk_band: str,
    severity_tier: str,
    override_flags: list[str],
    trajectory: str,
) -> int:
    base = {"green": 0, "amber": 3, "red": 6, "black": 9}.get(risk_band, 0)
    band_cap = {"green": 2, "amber": 5, "red": 8, "black": 10}.get(risk_band, 10)

    if severity_tier == "high":
        base += 1
    elif severity_tier == "moderate" and risk_band in {"amber", "red"}:
        base += 1

    if trajectory == "worsening":
        base += 1
    if len(override_flags) >= 2:
        base += 1

    return min(band_cap, max(0, base))


def _injury_priority(entry: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    return (
        _BAND_INDEX.get(str(entry.get("risk_band", "green")), 0),
        int(entry.get("risk_band_score", 0)),
        _SEVERITY_TIER_INDEX.get(str(entry.get("severity_tier", "low")), 0),
        len(entry.get("override_flags") or []),
        _TRAJECTORY_INDEX.get(str(entry.get("trajectory", "unknown")), 0),
        _COLLISION_CONTEXT_INDEX.get(str(entry.get("collision_context", "low_collision")), 0),
    )


def _sparring_injury_entries(athlete_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in _clean_list(athlete_snapshot.get("injuries", [])):
        raw_text = str(raw).strip()
        lowered = raw_text.lower()
        if not raw_text:
            continue

        parsed = parse_injury_entry(raw_text) or {}
        region = str(parsed.get("canonical_location") or "unspecified").strip().lower()
        injury_type = str(parsed.get("injury_type") or "unspecified").strip().lower()
        laterality = str(parsed.get("laterality") or parsed.get("side") or "").strip().lower()
        worsening = any(token in lowered for token in ("worsen", "worsening", "worse", "flared", "aggravated", "regressing"))
        improving = any(token in lowered for token in ("improving", "better", "settling", "resolved", "resolving"))
        stable = any(token in lowered for token in ("stable", "managed", "manageable", "maintenance"))
        instability = any(token in lowered for token in ("instability", "giving way", "buckled", "locking", "locked"))
        daily_symptoms = any(token in lowered for token in ("rest pain", "daily", "walking", "stairs", "sleep", "constant"))
        severe = instability or daily_symptoms or any(
            token in lowered for token in ("sharp", "severe", "tear", "rupture", "cannot", "can't", "can’t")
        )
        moderate = severe or any(
            token in lowered
            for token in (
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

        state_score = 0
        if moderate:
            state_score = 2
        if severe:
            state_score = max(state_score, 4)
        if worsening:
            state_score += 2
        if stable:
            state_score = max(0, state_score - 1)
        if improving:
            state_score = max(0, state_score - 1)
        if daily_symptoms:
            state_score += 2
        if instability:
            state_score += 2
        if region in _HIGH_COLLISION_REGIONS:
            state_score += 1
        state_score = min(_SPARRING_INJURY_STATE_SCORE_CAP, max(0, state_score))

        # v2 tiered model (computed alongside old state_score)
        severity_tier = _classify_severity_tier(lowered)
        trajectory = _classify_trajectory(worsening, stable, improving)
        override_flags = _detect_override_flags(lowered, instability, daily_symptoms)
        collision_context = _classify_collision_context(region)
        risk_band = _resolve_risk_band(severity_tier, trajectory, override_flags, collision_context)
        risk_band_score = _derive_band_score(risk_band, severity_tier, override_flags, trajectory)

        entries.append(
            {
                "raw": raw_text,
                "region": region,
                "injury_type": injury_type,
                "laterality": laterality,
                "state_score": state_score,
                "worsening": worsening,
                "improving": improving,
                "stable": stable,
                "instability": instability,
                "daily_symptoms": daily_symptoms,
                "high_collision_region": region in _HIGH_COLLISION_REGIONS,
                "lower_limb": region in _LOWER_LIMB_REGIONS,
                "severity_tier": severity_tier,
                "trajectory": trajectory,
                "override_flags": override_flags,
                "collision_context": collision_context,
                "risk_band": risk_band,
                "risk_band_score": risk_band_score,
            }
        )
    return entries


def _injury_risk(entries: list[dict[str, Any]]) -> int:
    if not entries:
        return 0
    best = max(entries, key=_injury_priority)
    score = best.get("risk_band_score", 0)
    if len(entries) > 1:
        score = min(10, score + 1)
    return score


def _highest_risk_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    return max(entries, key=_injury_priority)


def _replacement_focus(*, athlete_snapshot: dict[str, Any], injuries: list[dict[str, Any]], phase: str) -> str:
    sport_key = str(athlete_snapshot.get("sport", "")).strip().lower().replace(" ", "_")
    if any(entry.get("lower_limb") for entry in injuries):
        if sport_key in {"boxing", "kickboxing", "muay_thai"}:
            return "Technical rounds with stance-stable pad or bag work."
        return "Controlled technical drilling with lower collision cost."
    if any(str(entry.get("region", "")) == "shoulder" for entry in injuries):
        return "Footwork, defensive reads, and low-force tactical drilling."
    if phase == "TAPER":
        return "Sharpness-only technical rehearsal."
    return "Controlled technical work with lower collision cost."


def _join_reason_parts(parts: list[str]) -> str:
    filtered = [part.strip() for part in parts if part and part.strip()]
    if not filtered:
        return ""
    if len(filtered) == 1:
        return filtered[0]
    if len(filtered) == 2:
        return f"{filtered[0]} and {filtered[1]}"
    return ", ".join(filtered[:-1]) + f", and {filtered[-1]}"


def _injury_label(entry: dict[str, Any] | None) -> str | None:
    if not entry:
        return None
    region = _humanize_token(str(entry.get("region") or "")).strip()
    injury_type = _humanize_token(str(entry.get("injury_type") or "")).strip()
    laterality = _humanize_token(str(entry.get("laterality") or "")).strip()
    qualifier = ""
    if entry.get("worsening"):
        qualifier = "worsening"
    elif entry.get("improving"):
        qualifier = "improving"
    elif entry.get("stable"):
        qualifier = "stable"
    if injury_type == "unspecified":
        injury_type = ""
    if region == "unspecified":
        region = ""

    pieces = [piece for piece in (qualifier, laterality, region, injury_type) if piece]
    if pieces:
        return " ".join(pieces)

    raw = str(entry.get("raw") or "").strip()
    return raw.lower() if raw else None


def _future_state_label(
    *,
    athlete_snapshot: dict[str, Any],
    highest_injury: dict[str, Any] | None,
    cut_pct: float,
) -> tuple[str, str]:
    parts: list[str] = []
    fatigue = str(athlete_snapshot.get("fatigue", "")).strip().lower()
    if fatigue == "high":
        parts.append("high fatigue")
    elif fatigue == "moderate":
        parts.append("elevated fatigue")

    readiness_flags = {flag.lower() for flag in _clean_list(athlete_snapshot.get("readiness_flags", []))}
    if cut_pct >= 5.0:
        parts.append("an aggressive cut")
    elif cut_pct >= 3.0 or "active_weight_cut" in readiness_flags:
        parts.append("an active cut")

    injury_label = _injury_label(highest_injury)
    if injury_label:
        parts.append(injury_label)

    if not parts:
        return "the same readiness picture", "is"
    if len(parts) == 1:
        return parts[0], "is"
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}", "are"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}", "are"


def _week_label(week: dict[str, Any]) -> str:
    week_index = week.get("week_index") or week.get("phase_week_index") or 1
    return f"Week {week_index}"


def _is_future_week(week: dict[str, Any]) -> bool:
    try:
        return int(week.get("week_index") or 1) > 1
    except (TypeError, ValueError):
        return False


def _build_week_advisory(
    week: dict[str, Any],
    *,
    athlete_snapshot: dict[str, Any],
    injuries: list[dict[str, Any]],
    injury_risk: int,
    cut_pct: float,
    hard_sparring_plan: list[dict[str, Any]] | None = None,
) -> tuple[tuple[int, int, int, int], dict[str, Any]] | None:
    if not isinstance(week, dict):
        return None

    hard_days = _ordered_weekdays(week.get("declared_hard_sparring_days") or athlete_snapshot.get("hard_sparring_days"))
    if not hard_days:
        return None
    plan = hard_sparring_plan or week.get("hard_sparring_plan")
    if not isinstance(plan, list):
        plan = compute_hard_sparring_plan(week=week, athlete_snapshot=athlete_snapshot)
    downgraded = [entry for entry in plan if entry.get("status") != "hard_as_planned"]
    if not downgraded:
        return None
    target_entry = next(
        (entry for entry in downgraded if entry.get("status") == "convert_to_technical_suggested"),
        downgraded[0],
    )
    hard_day_count = len(hard_days)

    pressure_score, pressure_reasons = _pressure_score(week, athlete_snapshot)
    fatigue_score, fatigue_reason = _fatigue_score(athlete_snapshot)
    cut_score, cut_reason = _cut_score(athlete_snapshot, cut_pct=cut_pct)
    highest_injury = _highest_risk_entry(injuries)
    action = "convert" if target_entry.get("status") == "convert_to_technical_suggested" else "deload"

    phase = str(week.get("phase", "")).strip().upper() or "UNKNOWN"
    week_label = _week_label(week)
    future_week = _is_future_week(week)
    days_label = str(target_entry.get("day") or "").strip()
    all_downgraded_days = [str(entry.get("day") or "").strip() for entry in downgraded if str(entry.get("day") or "").strip()]
    reported_days = all_downgraded_days or ([days_label] if days_label else [])
    plan_creation_weekday = athlete_snapshot.get("plan_creation_weekday")
    all_downgraded = len(downgraded) == len(hard_days)
    days_phrase = _days_list_phrase(reported_days) if (all_downgraded and len(reported_days) > 1) else days_label
    target_is_past = _is_past_weekday(days_label, plan_creation_weekday)

    reason_parts = list(pressure_reasons)
    if hard_day_count >= 2:
        past_count = sum(1 for d in hard_days if _is_past_weekday(d, plan_creation_weekday))
        remaining_count = hard_day_count - past_count
        if plan_creation_weekday is not None and past_count >= 1 and remaining_count >= 1:
            reason_parts.append("a hard sparring session earlier this week adds to the overall collision load")
        elif remaining_count >= 2:
            reason_parts.append(f"this week carries {remaining_count} hard sparring sessions")
    if highest_injury:
        injury_label = _injury_label(highest_injury) or str(highest_injury["raw"]).lower()
        reason_parts.append(f"the brief shows {injury_label}")
    if fatigue_reason:
        reason_parts.append(fatigue_reason)
    if cut_reason:
        reason_parts.append(cut_reason)
    if not all_downgraded and effective_hard_day_count(plan) < hard_day_count:
        reason_parts.append(f"{days_label} is the lower-priority hard sparring day this week")
    because = _join_reason_parts(reason_parts)
    future_state_label, future_state_verb = _future_state_label(
        athlete_snapshot=athlete_snapshot,
        highest_injury=highest_injury,
        cut_pct=cut_pct,
    )

    if future_week:
        if len(reported_days) > 1:
            sparring_ref = f"multiple hard sparring sessions ({days_phrase})"
            session_verb = "are still scheduled"
        else:
            sparring_ref = f"hard sparring on {days_phrase}"
            session_verb = "is still set"
        reason = (
            f"If the current readiness picture carries into {week_label}, {because} and "
            f"{sparring_ref} {session_verb} — that collision exposure is probably too high to leave untouched."
        )
    elif all_downgraded and len(reported_days) > 1:
        reason = (
            f"{because.capitalize()}, so all remaining hard sparring ({days_phrase}) "
            "is getting pulled back — the collision load is running too high for this window."
        )
    else:
        sparring_verb = "was scheduled for" if target_is_past else "is set for"
        reason = (
            f"{because.capitalize()} and hard sparring {sparring_verb} {days_phrase}, "
            "so the collision cost is running ahead of what you are likely to absorb well this week."
        )

    if action == "convert":
        if future_week:
            suggestion = (
                f"If {future_state_label} {future_state_verb} still there by {week_label}, "
                f"convert hard sparring on {days_phrase} to technical rounds or controlled drilling."
            )
        elif all_downgraded and len(reported_days) > 1:
            suggestion = (
                f"Shift all remaining sparring ({days_phrase}) to technical rounds or controlled drilling "
                "— no hard contact."
            )
        else:
            suggestion = f"Convert hard sparring on {days_phrase} to technical rounds or controlled drilling."
    else:
        if future_week:
            suggestion = (
                f"If {future_state_label} {future_state_verb} still there by {week_label}, "
                f"deload hard sparring on {days_phrase} by trimming rounds, lowering intensity, or reducing total collision exposure."
            )
        elif all_downgraded and len(reported_days) > 1:
            suggestion = (
                f"Deload remaining sparring ({days_phrase}) — trim rounds, lower intensity, "
                "and reduce total collision exposure across sessions."
            )
        else:
            suggestion = (
                f"Deload hard sparring on {days_phrase} by trimming rounds, lowering intensity, "
                "or reducing total collision exposure."
            )

    advisory: dict[str, Any] = {
        "kind": "sparring_adjustment",
        "action": action,
        "phase": phase,
        "week_label": week_label,
        "days": reported_days,
        "title": "Coach note",
        "reason": reason,
        "suggestion": suggestion,
        "disclaimer": _DISCLAIMER,
    }
    if highest_injury and highest_injury.get("risk_band"):
        advisory["risk_band"] = str(highest_injury.get("risk_band"))
    if action == "convert":
        advisory["replacement"] = _replacement_focus(
            athlete_snapshot=athlete_snapshot,
            injuries=injuries,
            phase=phase,
        )

    rank = (
        2 if action == "convert" else 1,
        pressure_score,
        hard_day_count,
        injury_risk,
        fatigue_score + cut_score,
    )
    return rank, advisory


def build_plan_advisories(*, planning_brief: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(planning_brief, dict):
        return []

    weekly_role_map = planning_brief.get("weekly_role_map")
    if not isinstance(weekly_role_map, dict):
        return []
    weeks = weekly_role_map.get("weeks")
    if not isinstance(weeks, list) or not weeks:
        return []

    athlete_snapshot = _athlete_snapshot(planning_brief)
    if not athlete_snapshot:
        return []

    injuries = _sparring_injury_entries(athlete_snapshot)
    cut_pct = _active_cut_pct(athlete_snapshot)

    candidates = [
        candidate
        for candidate in (
            _build_week_advisory(
                week,
                athlete_snapshot=athlete_snapshot,
                injuries=injuries,
                injury_risk=_injury_risk(injuries),
                cut_pct=cut_pct,
            )
            for week in weeks
        )
        if candidate is not None
    ]
    if not candidates:
        return []

    _, best_advisory = max(candidates, key=lambda item: item[0])
    return [best_advisory]
