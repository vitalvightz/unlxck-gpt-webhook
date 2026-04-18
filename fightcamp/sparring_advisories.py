from __future__ import annotations

import re
from typing import Any

from .injury_formatting import parse_injury_entry
from .sparring_dose_planner import compute_hard_sparring_plan, effective_hard_day_count
from .weight_cut import compute_cut_severity_score, compute_weight_cut_pct, cut_severity_bucket
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
_DISCLAIMER = "Treat this as a flag, not an automatic change to your saved plan."
_SPARRING_INJURY_STATE_SCORE_CAP = 10

# Risk band thresholds (risk_band_score → band)
# green: 0–2, amber: 3–5, red: 6–8, black: 9–10
_RISK_BAND_THRESHOLDS = [
    (9, "black"),
    (6, "red"),
    (3, "amber"),
    (0, "green"),
]
_RISK_BAND_RANK = {"black": 3, "red": 2, "amber": 1, "green": 0}

# Severity tier token sets — soreness/stiffness are LOW, not moderate
_HIGH_SEVERITY_TOKENS = {"tear", "rupture", "severe", "sharp"}
_MODERATE_SEVERITY_TOKENS = {
    "strain", "sprain", "pain", "tendon", "tendonitis", "tendinopathy", "impingement",
}
_SEVERITY_BASE_SCORE = {"high": 8, "moderate": 4, "low": 1}

# Trajectory token sets
_WORSENING_TOKENS = {"worsen", "worsening", "worse", "flared", "aggravated", "regressing"}
_IMPROVING_TOKENS = {"improving", "better", "settling", "resolved", "resolving"}
_STABLE_TOKENS = {"stable", "managed", "manageable", "maintenance"}
_CANNOT_PATTERN = re.compile(r"\b(?:cannot|can['\u2019]t)\b")


def _contains_cannot_phrase(lowered: str) -> bool:
    return bool(_CANNOT_PATTERN.search(lowered))


def _severity_tier(lowered: str, instability: bool, daily_symptoms: bool) -> str:
    """Classify structural severity: high / moderate / low."""
    if any(token in lowered for token in _HIGH_SEVERITY_TOKENS) or _contains_cannot_phrase(lowered):
        return "high"
    if any(token in lowered for token in _MODERATE_SEVERITY_TOKENS):
        return "moderate"
    return "low"


def _trajectory(lowered: str, worsening: bool, improving: bool, stable: bool) -> str:
    """Return exclusive trajectory; worsening wins when mixed."""
    if worsening:
        return "worsening"
    if improving:
        return "improving"
    if stable:
        return "stable"
    return "unknown"


def _collision_context(region: str) -> str:
    if region in _LOWER_LIMB_REGIONS:
        return "lower_limb"
    if region in _UPPER_BODY_COLLISION_REGIONS:
        return "upper_body_collision"
    return "low_collision"


def _override_flags(lowered: str, instability: bool, daily_symptoms: bool) -> list[str]:
    flags: list[str] = []
    if instability:
        flags.append("instability")
    if daily_symptoms:
        flags.append("daily_symptoms")
    if any(token in lowered for token in ("rest pain",)):
        flags.append("rest_pain")
    if _contains_cannot_phrase(lowered):
        flags.append("cannot_load")
    if any(token in lowered for token in ("giving way", "buckled", "locking", "locked")):
        flags.append("giving_way")
    return flags



def _band_from_score(score: int) -> str:
    for threshold, band in _RISK_BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "green"


def _humanize_token(value: str) -> str:
    return str(value or "").strip().replace("_", " ")




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
    bucket = str(athlete_snapshot.get("cut_severity_bucket") or "").strip().lower()
    if not bucket:
        bucket = cut_severity_bucket(
            compute_cut_severity_score(
                cut_pct,
                athlete_snapshot.get("days_until_fight"),
            )
        )

    if bucket in {"high", "critical"}:
        return 2, f"cut pressure is meaningful at about {cut_pct:.1f}%"
    if bucket == "moderate":
        return 1, f"an active cut is still in play at about {cut_pct:.1f}%"
    return 0, None


def _pressure_score(week: dict[str, Any], athlete_snapshot: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    phase = str(week.get("phase", "")).strip().upper()
    stage_key = str(week.get("stage_key", "")).strip().lower()
    readiness_flags = {flag.lower() for flag in clean_list(athlete_snapshot.get("readiness_flags", []))}

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



def _sparring_injury_entries(athlete_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in clean_list(athlete_snapshot.get("injuries", [])):
        parsed_payload: dict[str, Any] | None = raw if isinstance(raw, dict) else None
        raw_text = str(
            (
                (parsed_payload or {}).get("raw")
                or (parsed_payload or {}).get("text")
                or (parsed_payload or {}).get("label")
                or raw
            )
        ).strip()
        lowered = raw_text.lower()
        structured_text = ""
        if parsed_payload:
            structured_text = " ".join(
                str(parsed_payload.get(key) or "").strip()
                for key in ("severity", "status", "trajectory", "notes")
                if str(parsed_payload.get(key) or "").strip()
            ).lower()
        lowered_for_signals = f"{lowered} {structured_text}".strip()
        if not raw_text:
            continue

        parsed = parse_injury_entry(raw_text) or {}
        region = str(
            parsed.get("canonical_location")
            or (parsed_payload or {}).get("canonical_location")
            or (parsed_payload or {}).get("region")
            or "unspecified"
        ).strip().lower()
        injury_type = str(
            parsed.get("injury_type")
            or (parsed_payload or {}).get("injury_type")
            or "unspecified"
        ).strip().lower()
        laterality = str(
            parsed.get("laterality")
            or parsed.get("side")
            or (parsed_payload or {}).get("laterality")
            or (parsed_payload or {}).get("side")
            or ""
        ).strip().lower()

        # -- Trajectory (exclusive: worsening wins) --
        worsening = any(token in lowered_for_signals for token in _WORSENING_TOKENS)
        improving = any(token in lowered_for_signals for token in _IMPROVING_TOKENS)
        stable = any(token in lowered_for_signals for token in _STABLE_TOKENS)
        traj = _trajectory(lowered, worsening, improving, stable)

        # -- Override flags --
        instability = any(
            token in lowered_for_signals for token in ("instability", "giving way", "buckled", "locking", "locked")
        )
        daily_symptoms = any(
            token in lowered_for_signals for token in ("rest pain", "daily", "walking", "stairs", "sleep", "constant")
        )
        oflags = _override_flags(lowered_for_signals, instability, daily_symptoms)

        # -- Legacy state_score (old algorithm, kept for backward compat) --
        severe = instability or daily_symptoms or any(
            token in lowered_for_signals for token in ("sharp", "severe", "tear", "rupture")
        ) or _contains_cannot_phrase(lowered_for_signals)
        moderate = severe or any(
            token in lowered_for_signals
            for token in (
                "strain", "sprain", "pain", "tendon", "tendonitis",
                "tendinopathy", "impingement", "soreness", "stiffness", "irritation",
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

        # -- Severity tier and collision context (new system) --
        tier = _severity_tier(lowered_for_signals, instability, daily_symptoms)
        ctx = _collision_context(region)

        # -- risk_band_score (new system, used for band classification) --
        base = _SEVERITY_BASE_SCORE[tier]
        if tier == "low" and region in _HIGH_COLLISION_REGIONS:
            base += 2  # lifts mild high-collision injuries to amber territory
        if traj == "worsening":
            base += 2
        elif traj == "improving":
            base -= 1
        # Override floor: instability/daily_symptoms force minimum red (6).
        # When worsening is ALSO present, the floor is 7 (active deterioration
        # on top of an already-flagged injury).
        if instability or daily_symptoms:
            if worsening:
                base = max(base, 7)
            else:
                base = max(base, 6)

        rbs = min(_SPARRING_INJURY_STATE_SCORE_CAP, max(0, base))
        band = _band_from_score(rbs)

        entries.append(
            {
                "raw": raw_text,
                "region": region,
                "injury_type": injury_type,
                "laterality": laterality,
                "state_score": state_score,
                "severity_tier": tier,
                "trajectory": traj,
                "worsening": worsening,
                "improving": improving,
                "stable": stable,
                "instability": instability,
                "daily_symptoms": daily_symptoms,
                "high_collision_region": region in _HIGH_COLLISION_REGIONS,
                "lower_limb": region in _LOWER_LIMB_REGIONS,
                "collision_context": ctx,
                "override_flags": oflags,
                "risk_band_score": rbs,
                "risk_band": band,
            }
        )
    return entries

def _injury_risk(entries: list[dict[str, Any]]) -> int:
    if not entries:
        return 0
    best = _highest_risk_entry(entries)
    if best is None:
        return 0
    base = int(best.get("risk_band_score", best.get("state_score", 0)))
    bonus = 1 if len(entries) > 1 else 0
    return min(10, base + bonus)


def _highest_risk_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    return max(
        entries,
        key=lambda e: (
            _RISK_BAND_RANK.get(str(e.get("risk_band", "green")), 0),
            int(e.get("risk_band_score", e.get("state_score", 0))),
        ),
    )


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

    cut_bucket = str(athlete_snapshot.get("cut_severity_bucket") or "").strip().lower()
    if not cut_bucket:
        cut_bucket = cut_severity_bucket(
            compute_cut_severity_score(cut_pct, athlete_snapshot.get("days_until_fight"))
        )
    if cut_bucket in {"high", "critical"}:
        parts.append("an aggressive cut")
    elif cut_bucket == "moderate":
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
    reason_parts = list(pressure_reasons)
    if hard_day_count >= 2:
        reason_parts.append(f"this week already carries {hard_day_count} declared hard sparring days")
    if highest_injury:
        injury_label = _injury_label(highest_injury) or str(highest_injury["raw"]).lower()
        reason_parts.append(f"the brief shows {injury_label}")
    if fatigue_reason:
        reason_parts.append(fatigue_reason)
    if cut_reason:
        reason_parts.append(cut_reason)
    if effective_hard_day_count(plan) < hard_day_count:
        reason_parts.append(f"{days_label} is the lower-priority hard sparring day this week")
    because = _join_reason_parts(reason_parts)
    future_state_label, future_state_verb = _future_state_label(
        athlete_snapshot=athlete_snapshot,
        highest_injury=highest_injury,
        cut_pct=cut_pct,
    )
    if future_week:
        reason = (
            f"If the current readiness picture carries into {week_label}, {because} and hard sparring is still set for "
            f"{days_label}, that collision cost is probably too high to leave untouched."
        )
    else:
        reason = (
            f"{because.capitalize()} and hard sparring is set for {days_label}, "
            "so the collision cost is running ahead of what you are likely to absorb well this week."
        )

    if action == "convert":
        suggestion = (
            f"If {future_state_label} {future_state_verb} still there by {week_label}, convert hard sparring on {days_label} to technical rounds or controlled drilling."
            if future_week
            else f"Convert hard sparring on {days_label} in {week_label} to technical rounds or controlled drilling."
        )
    else:
        suggestion = (
            f"If {future_state_label} {future_state_verb} still there by {week_label}, deload hard sparring on {days_label} by trimming rounds, lowering intensity, or reducing total collision exposure."
            if future_week
            else f"Deload hard sparring on {days_label} in {week_label} by trimming rounds, lowering intensity, or reducing total collision exposure."
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
    if highest_injury:
        advisory["risk_band"] = str(highest_injury.get("risk_band", "green"))
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


def summarize_sparring_injury_risk(*, injury_texts: list[str]) -> dict[str, Any]:
    entries = _sparring_injury_entries({"injuries": injury_texts})
    highest = _highest_risk_entry(entries)
    if highest is None:
        return {
            "risk_band": "green",
            "risk_band_score": 0,
            "entry": None,
            "entry_count": 0,
        }
    return {
        "risk_band": str(highest.get("risk_band") or "green"),
        "risk_band_score": int(highest.get("risk_band_score", highest.get("state_score", 0))),
        "entry": highest,
        "entry_count": len(entries),
    }


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
