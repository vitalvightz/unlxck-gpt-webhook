from __future__ import annotations

from typing import Any, Literal

from .normalization import clean_list, normalize_fatigue_level, ordered_weekdays
from .stage2_payload_late_fight import _countdown_offset, _countdown_weekday_map, _resolve_plan_creation_weekday


ZERO_COST_INSERTS = {
    "tactical_watch",
    "self_review",
    "neural_visualization",
}

LOW_COST_RECOVERY_INSERTS = {
    "recovery_reset",
}

PHYSICAL_INSERTS = {
    "mobility_rehab",
    "movement_quality",
    "technical_shadow_rhythm",
}

GAP_FILL_MIN_DAYS = 4
MAX_INSERTS_TOTAL_D21_TO_D0 = 2
MAX_PHYSICAL_INSERTS_PER_7_DAY_SEGMENT = 1

_ALL_INSERTS = ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS | PHYSICAL_INSERTS

_INSERT_META = {
    "tactical_watch": {
        "label": "Fight Tactical Watch",
        "duration_min": [15, 30],
        "rpe_max": 0,
    },
    "self_review": {
        "label": "Self-Review Cues",
        "duration_min": [15, 30],
        "rpe_max": 0,
        "display_text": "Review the last clean technical work. Write three cues only: one entry, one defensive reset, one composure cue.",
    },
    "neural_visualization": {
        "label": "Neural Visualization",
        "duration_min": [15, 30],
        "rpe_max": 0,
        "display_text": "Quiet visualization only. Rehearse first exchange, best entry, exit/reset, and final-round composure.",
    },
    "recovery_reset": {
        "label": "Recovery Reset",
        "duration_min": [10, 20],
        "rpe_max": 2,
        "display_text": "Breathing reset, easy tissue work, and downshift mobility. Keep it restorative.",
    },
    "mobility_rehab": {
        "label": "Mobility/Rehab Reset",
        "duration_min": [8, 15],
        "rpe_max": 3,
        "display_text": "Target the flagged restriction with easy range, activation, and pain-free control. Stop well before fatigue.",
    },
    "movement_quality": {
        "label": "Movement Quality Check",
        "duration_min": [8, 15],
        "rpe_max": 3,
        "display_text": "Low-amplitude stance, posture, breathing, and foot placement quality. No sweat target.",
    },
    "technical_shadow_rhythm": {
        "label": "Technical Shadow Rhythm",
        "duration_min": [8, 15],
        "rpe_max": 4,
        "display_text": "Light shadow rhythm only. Smooth entries, exits, and reset cues. No bag, bands, bursts, or conditioning intent.",
    },
}


def _normalised_set(values: Any) -> set[str]:
    return {str(value).strip().lower().replace(" ", "_") for value in clean_list(values) if str(value).strip()}


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)


def _readiness_flags(athlete_model: dict[str, Any]) -> set[str]:
    return _normalised_set(athlete_model.get("readiness_flags", []))


def _has_active_weight_cut(athlete_model: dict[str, Any]) -> bool:
    flags = _readiness_flags(athlete_model)
    if flags & {"active_weight_cut", "weight_cut_active", "aggressive_weight_cut", "extreme_weight_cut"}:
        return True
    if bool(athlete_model.get("weight_cut_risk")):
        return True
    try:
        return float(athlete_model.get("weight_cut_pct") or 0.0) > 0
    except (TypeError, ValueError):
        return False


def _has_high_fatigue(athlete_model: dict[str, Any]) -> bool:
    return normalize_fatigue_level(athlete_model) == "high" or "high_fatigue" in _readiness_flags(athlete_model)


def _has_mobility_need(athlete_model: dict[str, Any]) -> bool:
    values = (
        _normalised_set(athlete_model.get("weaknesses", []))
        | _normalised_set(athlete_model.get("key_goals", []))
        | _normalised_set(athlete_model.get("readiness_flags", []))
    )
    return any("mobil" in value or "rehab" in value or "range" in value for value in values)


def _has_power_speed_goal(athlete_model: dict[str, Any]) -> bool:
    values = _normalised_set(athlete_model.get("key_goals", [])) | _normalised_set(athlete_model.get("weaknesses", []))
    return any("power" in value or "speed" in value or "explosive" in value for value in values)


def classify_injury_state(athlete_model: dict[str, Any]) -> Literal["none", "mild_stable", "moderate_plus"]:
    parsed = athlete_model.get("parsed_injuries") or []
    guided = athlete_model.get("guided_injury")
    restrictions = athlete_model.get("injury_restrictions") or []
    raw_injuries = athlete_model.get("injuries") or athlete_model.get("injury") or athlete_model.get("injury_notes")
    active_injury = athlete_model.get("active_injury")
    has_active = bool(athlete_model.get("has_active_injury"))

    injury_text = _flatten_text([parsed, guided, restrictions, raw_injuries, active_injury]).lower().replace("_", " ")
    flags_text = " ".join(_readiness_flags(athlete_model)).replace("_", " ")

    empty_markers = {"", "none", "no", "false", "0", "n/a", "na"}
    active_injury_text = str(active_injury or "").strip().lower()
    has_raw_injury = bool(injury_text.strip()) and injury_text.strip() not in empty_markers
    if not parsed and not guided and not restrictions and not has_active and not has_raw_injury:
        return "none"
    if active_injury_text in {"none", "no", "false", "0"} and not parsed and not guided and not restrictions and not raw_injuries:
        return "none"

    combined = f"{injury_text} {flags_text}"
    moderate_markers = {
        "moderate",
        "severe",
        "high",
        "worsening",
        "unstable",
        "instability",
        "daily",
        "red flag",
        "red flags",
        "medical hold",
        "needs review",
        "acute",
        "neurological",
        "concussion",
        "fracture",
        "surgery",
    }
    if any(marker in combined for marker in moderate_markers):
        return "moderate_plus"

    mild_marker = any(marker in combined for marker in {"mild", "low", "minor"})
    stable_marker = any(marker in combined for marker in {"stable", "improving", "settled"})
    if mild_marker and stable_marker:
        return "mild_stable"

    return "moderate_plus"


def _allowed_inserts(
    athlete_model: dict[str, Any],
    insert_offset: int,
    *,
    on_hard_sparring_day: bool = False,
) -> set[str]:
    if insert_offset == 0:
        return set()

    allowed = set(_ALL_INSERTS)

    if insert_offset == 1:
        allowed &= ZERO_COST_INSERTS | {"recovery_reset"}
    elif insert_offset <= 3:
        allowed -= PHYSICAL_INSERTS

    if _has_high_fatigue(athlete_model):
        allowed &= ZERO_COST_INSERTS | {"recovery_reset"}

    if _has_active_weight_cut(athlete_model):
        allowed &= ZERO_COST_INSERTS | {"recovery_reset", "mobility_rehab"}

    injury_state = classify_injury_state(athlete_model)
    if injury_state == "moderate_plus":
        allowed &= ZERO_COST_INSERTS | {"recovery_reset", "mobility_rehab"}
    elif injury_state == "mild_stable":
        allowed |= {"mobility_rehab"}

    if insert_offset <= 4:
        allowed -= PHYSICAL_INSERTS
    elif "mobility_rehab" in allowed and not (_has_mobility_need(athlete_model) or injury_state == "mild_stable"):
        allowed.remove("mobility_rehab")

    if on_hard_sparring_day:
        allowed -= PHYSICAL_INSERTS
        allowed |= ZERO_COST_INSERTS | {"recovery_reset"}

    return allowed


def build_tactical_watch_template(athlete_model: dict[str, Any] | None = None) -> str:
    athlete_model = athlete_model or {}
    style_values = (
        _normalised_set(athlete_model.get("tactical_styles", []))
        | _normalised_set(athlete_model.get("style_tactical", []))
        | _normalised_set(athlete_model.get("technical_styles", []))
        | _normalised_set(athlete_model.get("style_technical", []))
        | _normalised_set(athlete_model.get("style", []))
        | _normalised_set(athlete_model.get("sport", []))
    )
    style_text = " ".join(style_values)
    focus = ""
    if "counter" in style_text:
        focus = "\nFocus: bait reactions, exits, first counter after feint."
    elif "pressure" in style_text:
        focus = "\nFocus: entries, clinch risk, angle exits."
    elif "boxer" in style_text or "boxing" in style_text:
        focus = "\nFocus: jab rhythm, lead-hand battle, exit side."
    elif "kicker" in style_text or "kickboxing" in style_text or "muay" in style_text:
        focus = "\nFocus: range line, stance matchups, check/counter timing."
    elif "grappler" in style_text or "mma" in style_text or "wrestling" in style_text:
        focus = "\nFocus: level-change triggers, cage exits, underhook habits."

    return (
        "Fight Tactical Watch - 15-30 min\n\n"
        "Watch 1-2 rounds or 10-20 clips.\n"
        f"{focus}\n\n"
        "Identify:\n"
        "1. Opponent/style rhythm\n"
        "2. First-exchange tendency\n"
        "3. Best entry\n"
        "4. Danger to avoid\n"
        "5. Reset cue\n\n"
        "Output:\n"
        "Write 3 fight cues only."
    )


def _first_allowed(preferences: list[str], allowed: set[str]) -> str | None:
    return next((role_key for role_key in preferences if role_key in allowed), None)


def _build_insert_role(
    role_key: str,
    athlete_model: dict[str, Any],
    insert_offset: int,
    weekday: str | None = None,
) -> dict[str, Any]:
    meta = _INSERT_META[role_key]
    label = str(meta["label"])
    display_text = (
        build_tactical_watch_template(athlete_model)
        if role_key == "tactical_watch"
        else str(meta["display_text"])
    )
    role: dict[str, Any] = {
        "session_index": None,
        "category": "support_insert",
        "role_key": role_key,
        "scheduled_day_hint": weekday,
        "athlete_facing_label": label,
        "display_text": display_text,
        "duration_min": list(meta["duration_min"]),
        "rpe_max": int(meta["rpe_max"]),
        "countdown_offset": insert_offset,
        "countdown_label": f"D-{insert_offset}",
        "scheduled_countdown_label": f"D-{insert_offset}",
        "stress_class": "support",
        "cost_class": "low",
        "governance": {
            "authority": "gap_fill_support_insert",
            "meaningful_stress": False,
        },
    }
    if weekday:
        role["real_weekday"] = weekday
        role["countdown_display_label"] = f"D-{insert_offset} ({weekday.title()})"
    return role


def select_gap_fill_insert(
    athlete_model: dict[str, Any],
    insert_offset: int,
    *,
    on_hard_sparring_day: bool = False,
) -> dict[str, Any] | None:
    if insert_offset == 0:
        return None

    allowed = _allowed_inserts(
        athlete_model,
        insert_offset,
        on_hard_sparring_day=on_hard_sparring_day,
    )
    if not allowed:
        return None

    high_fatigue = _has_high_fatigue(athlete_model)
    active_cut = _has_active_weight_cut(athlete_model)
    injury_state = classify_injury_state(athlete_model)
    mobility_need = _has_mobility_need(athlete_model) or injury_state == "mild_stable"
    has_injury = injury_state != "none"

    role_key: str | None = None
    if insert_offset == 1:
        role_key = _first_allowed(["tactical_watch", "neural_visualization", "recovery_reset", "self_review"], allowed)
    elif high_fatigue:
        role_key = _first_allowed(["recovery_reset", "neural_visualization", "tactical_watch"], allowed)
    elif active_cut and injury_state == "mild_stable" and insert_offset > 4:
        role_key = _first_allowed(["mobility_rehab", "tactical_watch"], allowed)
    elif active_cut and insert_offset <= 10:
        role_key = _first_allowed(["tactical_watch", "neural_visualization", "recovery_reset"], allowed)
    elif active_cut and mobility_need and insert_offset > 3:
        role_key = _first_allowed(["mobility_rehab", "tactical_watch"], allowed)
    elif active_cut:
        role_key = _first_allowed(["tactical_watch"], allowed)
    elif insert_offset <= 10:
        role_key = _first_allowed(["tactical_watch", "neural_visualization", "recovery_reset"], allowed)
    elif mobility_need and insert_offset > 3:
        role_key = _first_allowed(["mobility_rehab"], allowed)
    elif _has_power_speed_goal(athlete_model) and not active_cut and not has_injury and insert_offset > 3:
        role_key = _first_allowed(["neural_visualization", "technical_shadow_rhythm"], allowed)
    elif not active_cut and not has_injury:
        role_key = _first_allowed(["tactical_watch", "self_review"], allowed)

    role_key = role_key or _first_allowed(["recovery_reset"], allowed) or sorted(allowed)[0]
    return _build_insert_role(role_key, athlete_model, insert_offset)


def _role_offset(role: dict[str, Any]) -> int | None:
    value = role.get("countdown_offset")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    label = str(role.get("scheduled_countdown_label") or role.get("countdown_label") or "")
    return _countdown_offset(label)


def _segment_for_offset(offset: int) -> int:
    return max(0, (offset - 1) // 7)


def _select_non_physical_insert(
    athlete_model: dict[str, Any],
    insert_offset: int,
    *,
    on_hard_sparring_day: bool,
) -> dict[str, Any] | None:
    allowed = _allowed_inserts(
        athlete_model,
        insert_offset,
        on_hard_sparring_day=on_hard_sparring_day,
    ) - PHYSICAL_INSERTS
    role_key = _first_allowed(
        ["tactical_watch", "neural_visualization", "recovery_reset", "self_review"],
        allowed,
    )
    if not role_key:
        return None
    return _build_insert_role(role_key, athlete_model, insert_offset)


def apply_gap_fill_inserts(session_sequence: list[dict[str, Any]], athlete_model: dict[str, Any]) -> list[dict[str, Any]]:
    ordered = sorted(
        [dict(role) for role in session_sequence],
        key=lambda role: int(_role_offset(role) or 0),
        reverse=True,
    )
    if not ordered:
        return ordered

    offsets = [offset for role in ordered if (offset := _role_offset(role)) is not None and offset > 0]
    if not offsets:
        return ordered

    raw_days = athlete_model.get("days_until_fight")
    if raw_days is not None and str(raw_days).strip() != "":
        try:
            days_until_fight = int(raw_days)
        except (TypeError, ValueError):
            days_until_fight = max(offsets)
    else:
        days_until_fight = max(offsets)
    creation_weekday = _resolve_plan_creation_weekday(days_until_fight, athlete_model)
    countdown_map = _countdown_weekday_map(creation_weekday, days_until_fight)
    hard_sparring_days = set(ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))))

    existing_offsets = set(offsets)
    candidate_offsets: list[int] = []
    for far_offset, near_offset in zip(offsets, offsets[1:]):
        gap = far_offset - near_offset
        if gap >= GAP_FILL_MIN_DAYS:
            candidate_offsets.append(near_offset + gap // 2)

    trailing_gap = min(offsets)
    if trailing_gap >= GAP_FILL_MIN_DAYS:
        candidate_offsets.append(trailing_gap // 2)

    inserts: list[dict[str, Any]] = []
    physical_segment_counts: dict[int, int] = {}

    for target_offset in candidate_offsets:
        if len(inserts) >= MAX_INSERTS_TOTAL_D21_TO_D0:
            break
        if target_offset <= 0 or target_offset in existing_offsets:
            continue
        weekday = countdown_map.get(f"D-{target_offset}")
        on_hard_sparring_day = bool(weekday and weekday in hard_sparring_days)
        insert = select_gap_fill_insert(
            athlete_model,
            target_offset,
            on_hard_sparring_day=on_hard_sparring_day,
        )
        if insert is None:
            continue
        if insert["role_key"] in PHYSICAL_INSERTS:
            segment = _segment_for_offset(target_offset)
            if physical_segment_counts.get(segment, 0) >= MAX_PHYSICAL_INSERTS_PER_7_DAY_SEGMENT:
                insert = _select_non_physical_insert(
                    athlete_model,
                    target_offset,
                    on_hard_sparring_day=on_hard_sparring_day,
                )
                if insert is None:
                    continue
            else:
                physical_segment_counts[segment] = physical_segment_counts.get(segment, 0) + 1
        insert["scheduled_day_hint"] = weekday
        if weekday:
            insert["real_weekday"] = weekday
            insert["countdown_display_label"] = f"D-{target_offset} ({weekday.title()})"
        inserts.append(insert)
        existing_offsets.add(target_offset)

    final_sequence = sorted(ordered + inserts, key=lambda role: int(_role_offset(role) or 0), reverse=True)
    for index, role in enumerate(final_sequence, start=1):
        role["session_index"] = index
    return final_sequence
