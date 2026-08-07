from __future__ import annotations

from typing import Any, Literal

from .normalization import clean_list, normalize_fatigue_level, ordered_weekdays
from .stage2_render_guards import _all_active_injuries_surface_only
from .stage2_payload_late_fight import (
    _countdown_offset,
    _countdown_weekday_map,
    _resolve_plan_creation_weekday,
    is_low_cost_coexistable_filler,
)
from .tactical_watch_library import (
    build_watch_display_text,
    extract_tactical_style,
    select_tactical_watch,
    watch_metadata,
)


ZERO_COST_INSERTS = {
    "tactical_watch",
    "tactical_cue_card",
    "self_review",
    "neural_visualization",
}

LOW_COST_RECOVERY_INSERTS = {
    "recovery_reset",
    "breathing_reset",
    "sleep_downshift",
}

PHYSICAL_INSERTS = {
    "mobility_rehab",
    "movement_quality",
    "technical_shadow_rhythm",
    "footwork_walkthrough",
    "joint_prep",
    "walk_flush",
}

LOW_COST_AEROBIC_INSERTS = {
    "aerobic_shadow_flow",
    "aerobic_walk_flush",
    "aerobic_footwork_rhythm",
    "aerobic_skip_flush",
    "aerobic_jog_flush",
}
_ZERO_IMPACT_AEROBIC_INSERTS = {"aerobic_shadow_flow", "aerobic_walk_flush"}
_IMPACT_AEROBIC_INSERTS = {"aerobic_skip_flush", "aerobic_jog_flush"}

GAP_FILL_MIN_DAYS = 3
TWO_INSERT_GAP_MIN_DAYS = 5
LEADING_SPAN_MAX_DAYS_UNTIL_FIGHT = 7
MAX_INSERTS_TOTAL_D21_TO_D0 = 6
MAX_PHYSICAL_INSERTS_PER_7_DAY_SEGMENT = 1
MIN_AEROBIC_MAINTENANCE_OFFSET = 2

_ALL_INSERTS = (
    ZERO_COST_INSERTS
    | LOW_COST_RECOVERY_INSERTS
    | PHYSICAL_INSERTS
    | LOW_COST_AEROBIC_INSERTS
)
TACTICAL_INSERTS = {"tactical_watch", "tactical_cue_card", "self_review"}
CONDITIONING_MAINTENANCE_INSERTS = LOW_COST_AEROBIC_INSERTS

_CONDITIONING_GOAL_MARKERS = (
    "conditioning",
    "gas",
    "aerobic",
    "endurance",
    "cardio",
    "work_capacity",
    "engine",
    "stamina",
)
_LOWER_LEG_LOAD_MARKERS = (
    "achilles",
    "calf",
    "calves",
    "shin",
    "ankle",
    "foot",
    "feet",
    "heel",
    "plantar",
    "knee",
    "lower leg",
    "hamstring",
    "tibia",
    "peroneal",
)

_INSERT_META = {
    "tactical_watch": {
        "label": "Fight Tactical Watch",
        "duration_min": [8, 12],
        "rpe_max": 1,
        "insert_category": "tactical",
        "repeat_allowed": False,
    },
    "tactical_cue_card": {
        "label": "Tactical Cue Card",
        "duration_min": [5, 8],
        "rpe_max": 1,
        "insert_category": "tactical",
        "repeat_allowed": False,
        "display_text": (
            "Write one fight cue only: entry, exit, counter, foot position, or "
            "guard reaction. Keep it short enough to recall under pressure."
        ),
    },
    "self_review": {
        "label": "Self-Review Cues",
        "duration_min": [8, 12],
        "rpe_max": 1,
        "insert_category": "tactical",
        "repeat_allowed": False,
        "display_text": (
            "Review the last clean technical work. Write three cues only: one "
            "entry, one defensive reset, one composure cue."
        ),
    },
    "neural_visualization": {
        "label": "Neural Visualization",
        "duration_min": [5, 8],
        "rpe_max": 1,
        "insert_category": "mental",
        "repeat_allowed": False,
        "display_text": (
            "Quiet visualization only. Rehearse first exchange, best entry, "
            "exit/reset, and final-round composure."
        ),
    },
    "recovery_reset": {
        "label": "Recovery Reset",
        "duration_min": [10, 20],
        "rpe_max": 2,
        "insert_category": "recovery",
        "repeat_allowed": False,
        "display_text": (
            "Breathing reset, easy tissue work, and downshift mobility. Keep it restorative."
        ),
    },
    "breathing_reset": {
        "label": "Breathing Reset",
        "duration_min": [3, 6],
        "rpe_max": 1,
        "insert_category": "recovery",
        "repeat_allowed": False,
        "display_text": (
            "Nasal breathing if comfortable. Use a 4-6 second inhale and 6-8 "
            "second exhale. Finish calmer than you started."
        ),
    },
    "sleep_downshift": {
        "label": "Sleep Downshift",
        "duration_min": [5, 10],
        "rpe_max": 1,
        "insert_category": "recovery",
        "repeat_allowed": False,
        "display_text": (
            "Lights down, phone away, easy breathing, then stretch two tight "
            "areas without chasing range."
        ),
    },
    "mobility_rehab": {
        "label": "Mobility/Rehab Reset",
        "duration_min": [8, 15],
        "rpe_max": 2,
        "insert_category": "mobility",
        "repeat_allowed": False,
        "display_text": (
            "Target the flagged restriction with easy range, activation, and "
            "pain-free control. Stop well before fatigue."
        ),
    },
    "movement_quality": {
        "label": "Movement Quality Check",
        "duration_min": [8, 15],
        "rpe_max": 2,
        "insert_category": "movement_quality",
        "repeat_allowed": False,
        "display_text": (
            "Low-amplitude stance, posture, breathing, and foot placement quality. "
            "No sweat target."
        ),
    },
    "technical_shadow_rhythm": {
        "label": "Technical Shadow Rhythm",
        "duration_min": [8, 15],
        "rpe_max": 3,
        "insert_category": "technical",
        "repeat_allowed": False,
        "display_text": (
            "Light shadow rhythm only. Smooth entries, exits, and reset cues. "
            "No bag, bands, bursts, or conditioning intent."
        ),
    },
    "footwork_walkthrough": {
        "label": "Footwork Walkthrough",
        "duration_min": [8, 12],
        "rpe_max": 2,
        "insert_category": "footwork",
        "repeat_allowed": False,
        "display_text": (
            "Stance walk, step-slide, pivot out, and exit after jab/cross. Slow "
            "rounds only; no fatigue target."
        ),
    },
    "joint_prep": {
        "label": "Joint Prep",
        "duration_min": [6, 8],
        "rpe_max": 1,
        "insert_category": "mobility",
        "repeat_allowed": False,
        "display_text": (
            "Neck CARs, shoulder CARs, wrist circles, hip circles, and ankle rocks. "
            "Stay smooth and pain-free."
        ),
    },
    "walk_flush": {
        "label": "Easy Walk Flush",
        "duration_min": [10, 20],
        "rpe_max": 2,
        "insert_category": "recovery_walk",
        "repeat_allowed": False,
        "display_text": (
            "Nose-breathing pace only. No sweat target. Finish feeling better than "
            "when you started."
        ),
    },
    "aerobic_shadow_flow": {
        "label": "Shadowboxing Aerobic Flow",
        "duration_min": [8, 12],
        "rpe_max": 4,
        "insert_category": "conditioning_maintenance",
        "repeat_allowed": False,
        "display_text": (
            "3-5 x 2 min easy shadowboxing rounds, 60 sec rest. Smooth boxing rhythm "
            "at RPE 3-4. No contact, no power, no impact - keep the gas tank ticking "
            "over without costing freshness."
        ),
    },
    "aerobic_walk_flush": {
        "label": "Brisk Walk Flush",
        "duration_min": [15, 25],
        "rpe_max": 4,
        "insert_category": "conditioning_maintenance",
        "repeat_allowed": False,
        "display_text": (
            "Brisk or incline walk at a nose-breathing pace, RPE 3-4. Low-impact "
            "aerobic maintenance and recovery support - finish fresher than you started."
        ),
    },
    "aerobic_footwork_rhythm": {
        "label": "Footwork Rhythm Flush",
        "duration_min": [6, 10],
        "rpe_max": 4,
        "insert_category": "conditioning_maintenance",
        "repeat_allowed": False,
        "display_text": (
            "Light in-out steps, pivots, and stance resets, RPE 3-4. Movement-economy "
            "work so you waste less energy in exchanges. No sprinting or sharp cuts."
        ),
    },
    "aerobic_skip_flush": {
        "label": "Light Skipping Flush",
        "duration_min": [6, 10],
        "rpe_max": 4,
        "insert_category": "conditioning_maintenance",
        "repeat_allowed": False,
        "display_text": (
            "30-45 sec easy skip / 30-45 sec rest, RPE 3-4. Keeps rhythm, calf "
            "stiffness, and breathing control without hard conditioning stress. "
            "Skip only while calves and Achilles are healthy."
        ),
    },
    "aerobic_jog_flush": {
        "label": "Easy Jog Flush",
        "duration_min": [12, 18],
        "rpe_max": 4,
        "insert_category": "conditioning_maintenance",
        "repeat_allowed": False,
        "display_text": (
            "Easy continuous jog or walk-jog, RPE 3-4. Maintains aerobic rhythm "
            "without fatigue. Keep it conversational."
        ),
    },
}

_INSERT_MECH_LOAD_REGIONS: dict[str, tuple[str, ...]] = {
    "technical_shadow_rhythm": (
        "shoulder",
        "elbow",
        "wrist",
        "chest",
        "ankle",
        "knee",
    ),
    "aerobic_shadow_flow": (
        "shoulder",
        "elbow",
        "wrist",
        "chest",
        "ankle",
        "knee",
    ),
    "footwork_walkthrough": ("ankle", "foot", "knee"),
    "aerobic_footwork_rhythm": ("ankle", "foot", "calf", "knee"),
    "movement_quality": ("ankle", "foot"),
    "aerobic_skip_flush": (
        "calf",
        "achilles",
        "ankle",
        "foot",
        "shin",
        "knee",
    ),
    "aerobic_jog_flush": (
        "calf",
        "achilles",
        "ankle",
        "foot",
        "shin",
        "knee",
        "hamstring",
    ),
    "walk_flush": ("ankle", "foot", "achilles", "calf", "knee"),
    "aerobic_walk_flush": ("ankle", "foot", "achilles", "calf", "knee"),
}


def insert_mechanical_load_regions(role_key: str) -> tuple[str, ...]:
    """Body regions a gap-fill insert mechanically loads."""
    return _INSERT_MECH_LOAD_REGIONS.get(role_key, ())


def _normalised_set(values: Any) -> set[str]:
    return {
        str(value).strip().lower().replace(" ", "_")
        for value in clean_list(values)
        if str(value).strip()
    }


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
    if flags & {
        "active_weight_cut",
        "weight_cut_active",
        "aggressive_weight_cut",
        "extreme_weight_cut",
    }:
        return True
    if bool(athlete_model.get("weight_cut_risk")):
        return True
    try:
        return float(athlete_model.get("weight_cut_pct") or 0.0) > 0
    except (TypeError, ValueError):
        return False


def _has_high_fatigue(athlete_model: dict[str, Any]) -> bool:
    return (
        normalize_fatigue_level(athlete_model) == "high"
        or "high_fatigue" in _readiness_flags(athlete_model)
    )


def _has_mobility_need(athlete_model: dict[str, Any]) -> bool:
    values = (
        _normalised_set(athlete_model.get("weaknesses", []))
        | _normalised_set(athlete_model.get("key_goals", []))
        | _normalised_set(athlete_model.get("readiness_flags", []))
    )
    return any(
        "mobil" in value or "rehab" in value or "range" in value
        for value in values
    )


def _has_power_speed_goal(athlete_model: dict[str, Any]) -> bool:
    values = _normalised_set(athlete_model.get("key_goals", [])) | _normalised_set(
        athlete_model.get("weaknesses", [])
    )
    return any(
        "power" in value or "speed" in value or "explosive" in value
        for value in values
    )


def _has_conditioning_goal(athlete_model: dict[str, Any]) -> bool:
    values = (
        _normalised_set(athlete_model.get("key_goals", []))
        | _normalised_set(athlete_model.get("weaknesses", []))
        | _normalised_set(athlete_model.get("readiness_flags", []))
    )
    return any(
        marker in value for value in values for marker in _CONDITIONING_GOAL_MARKERS
    )


def _has_lower_leg_load_risk(athlete_model: dict[str, Any]) -> bool:
    if _all_active_injuries_surface_only(athlete_model):
        return False
    text = _flatten_text(
        [
            athlete_model.get("parsed_injuries"),
            athlete_model.get("guided_injury"),
            athlete_model.get("injury_restrictions"),
            athlete_model.get("injuries")
            or athlete_model.get("injury")
            or athlete_model.get("injury_notes"),
            athlete_model.get("active_injury"),
            sorted(_readiness_flags(athlete_model)),
        ]
    ).lower().replace("_", " ")
    return any(marker in text for marker in _LOWER_LEG_LOAD_MARKERS)


def _safe_conditioning_maintenance_inserts(
    athlete_model: dict[str, Any],
    insert_offset: int,
    injury_state: str,
    *,
    on_hard_sparring_day: bool,
) -> set[str]:
    if insert_offset < MIN_AEROBIC_MAINTENANCE_OFFSET or on_hard_sparring_day:
        return set()
    if not _has_conditioning_goal(athlete_model):
        return set()
    if injury_state == "moderate_plus":
        return set()

    safe = set(_ZERO_IMPACT_AEROBIC_INSERTS)
    safe.add("aerobic_footwork_rhythm")

    lower_leg_risk = _has_lower_leg_load_risk(athlete_model)
    high_fatigue = _has_high_fatigue(athlete_model)
    active_cut = _has_active_weight_cut(athlete_model)
    fatigue_low = normalize_fatigue_level(athlete_model) == "low"

    if not lower_leg_risk and not high_fatigue:
        safe.add("aerobic_skip_flush")
        if fatigue_low and not active_cut:
            safe.add("aerobic_jog_flush")
    return safe


def _has_footwork_weakness(athlete_model: dict[str, Any]) -> bool:
    values = (
        _normalised_set(athlete_model.get("weaknesses", []))
        | _normalised_set(athlete_model.get("key_goals", []))
        | _normalised_set(athlete_model.get("readiness_flags", []))
    )
    return any(
        marker in value
        for value in values
        for marker in {
            "footwork",
            "feet",
            "stance",
            "ringcraft",
            "ring_craft",
            "angle",
            "angles",
        }
    )


def _is_fight_sport(athlete_model: dict[str, Any]) -> bool:
    text = _flatten_text(
        [
            athlete_model.get("sport"),
            athlete_model.get("mapped_format"),
            athlete_model.get("fight_format"),
            athlete_model.get("style"),
            athlete_model.get("style_technical"),
            athlete_model.get("style_tactical"),
        ]
    ).lower()
    return any(
        marker in text
        for marker in {
            "boxing",
            "boxer",
            "combat",
            "fight",
            "fighter",
            "mma",
            "muay",
            "kickbox",
            "grappling",
            "wrestling",
            "jiu",
        }
    )


def _cost_category(role_key: str) -> str:
    if role_key in ZERO_COST_INSERTS:
        return "zero_cost"
    if role_key in LOW_COST_RECOVERY_INSERTS:
        return "low_cost_recovery"
    if role_key in LOW_COST_AEROBIC_INSERTS:
        return "low_cost_aerobic"
    return "physical"


def _insert_category(role_key: str) -> str:
    meta = _INSERT_META.get(role_key) or {}
    return str(meta.get("insert_category") or _cost_category(role_key))


def classify_injury_state(
    athlete_model: dict[str, Any],
) -> Literal["none", "mild_stable", "moderate_plus"]:
    if _all_active_injuries_surface_only(athlete_model):
        return "none"

    parsed = athlete_model.get("parsed_injuries") or []
    guided = athlete_model.get("guided_injury")
    restrictions = athlete_model.get("injury_restrictions") or []
    raw_injuries = (
        athlete_model.get("injuries")
        or athlete_model.get("injury")
        or athlete_model.get("injury_notes")
    )
    active_injury = athlete_model.get("active_injury")
    has_active = bool(athlete_model.get("has_active_injury"))

    injury_text = _flatten_text(
        [parsed, guided, restrictions, raw_injuries, active_injury]
    ).lower().replace("_", " ")
    flags_text = " ".join(_readiness_flags(athlete_model)).replace("_", " ")

    empty_markers = {"", "none", "no", "false", "0", "n/a", "na"}
    active_injury_text = str(active_injury or "").strip().lower()
    has_raw_injury = bool(injury_text.strip()) and injury_text.strip() not in empty_markers
    if not parsed and not guided and not restrictions and not has_active and not has_raw_injury:
        return "none"
    if (
        active_injury_text in {"none", "no", "false", "0"}
        and not parsed
        and not guided
        and not restrictions
        and not raw_injuries
    ):
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
    stable_marker = any(
        marker in combined for marker in {"stable", "improving", "settled"}
    )
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
    injury_state = classify_injury_state(athlete_model)

    if _has_active_weight_cut(athlete_model):
        allowed -= {"walk_flush"}
        if injury_state in {"none", "mild_stable"}:
            allowed -= {
                "technical_shadow_rhythm",
                "footwork_walkthrough",
                "movement_quality",
            }

    if injury_state == "moderate_plus":
        allowed &= (
            ZERO_COST_INSERTS
            | LOW_COST_RECOVERY_INSERTS
            | {"mobility_rehab", "joint_prep"}
        )
    elif injury_state == "mild_stable":
        allowed |= {"mobility_rehab", "joint_prep"}

    has_injury = bool(
        athlete_model.get("has_active_injury")
        or athlete_model.get("injuries")
        or athlete_model.get("parsed_injuries")
        or athlete_model.get("guided_injury")
        or athlete_model.get("injury_restrictions")
    )
    if has_injury and _all_active_injuries_surface_only(athlete_model):
        allowed -= {"mobility_rehab", "joint_prep"}

    if "mobility_rehab" in allowed and not (
        _has_mobility_need(athlete_model)
        or injury_state in {"mild_stable", "moderate_plus"}
    ):
        allowed.remove("mobility_rehab")

    if insert_offset == 1 or _has_high_fatigue(athlete_model):
        allowed &= ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS

    if on_hard_sparring_day:
        allowed -= PHYSICAL_INSERTS
        allowed |= ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS

    allowed -= LOW_COST_AEROBIC_INSERTS
    allowed |= _safe_conditioning_maintenance_inserts(
        athlete_model,
        insert_offset,
        injury_state,
        on_hard_sparring_day=on_hard_sparring_day,
    )
    return allowed


def build_tactical_watch_template(
    athlete_model: dict[str, Any] | None = None,
    *,
    phase: str | None = None,
    used_keys: set[str] | None = None,
    camp_focus: str = "",
) -> str:
    """Render the display text for a style/phase-aware Tactical Watch.

    Selection is deterministic (see ``tactical_watch_library``): the style is
    read from the athlete's declared style (never the sport), the phase defaults
    to GPP when unknown, and ``used_keys`` prevents repeats within a camp. The
    old shared four-line ``entry/danger/reset/round 1`` output is gone — each
    watch carries its own required output.
    """
    athlete_model = athlete_model or {}
    style = extract_tactical_style(athlete_model)
    watch = select_tactical_watch(style, phase, used_keys)
    return build_watch_display_text(watch, camp_focus)


def stamp_tactical_watch_role(
    role: dict[str, Any],
    athlete_model: dict[str, Any] | None,
    *,
    phase: str | None,
    used_keys: set[str] | None = None,
    camp_focus: str = "",
) -> dict[str, Any]:
    """Select a Tactical Watch and write its content into the filler fields.

    Puts the selected watch's full content into ``display_text`` (which the
    normal structured-plan conversion turns into the card, exactly like every
    other filler) and records the selection metadata (``tactical_watch_key`` /
    ``_name`` / ``_style`` / ``_phase``). Adds the selected key to ``used_keys``
    so the camp never repeats a watch. Returns the selected watch. Propagates
    :class:`TacticalWatchBankExhausted` if the bank is under-sized — the generic
    banks are sized so this can never happen for a real camp.
    """
    athlete_model = athlete_model or {}
    style = extract_tactical_style(athlete_model)
    watch = select_tactical_watch(style, phase, used_keys)
    if used_keys is not None:
        used_keys.add(watch.key)
    role["display_text"] = build_watch_display_text(watch, camp_focus)
    role.update(watch_metadata(watch))
    return watch


def _first_allowed(preferences: list[str], allowed: set[str]) -> str | None:
    return next((role_key for role_key in preferences if role_key in allowed), None)


def _time_band_preferences(insert_offset: int) -> list[str]:
    if insert_offset == 1:
        return [
            "tactical_cue_card",
            "neural_visualization",
            "breathing_reset",
            "sleep_downshift",
            "recovery_reset",
            "tactical_watch",
            "self_review",
        ]
    if 2 <= insert_offset <= 4:
        return [
            "tactical_cue_card",
            "neural_visualization",
            "breathing_reset",
            "mobility_rehab",
            "recovery_reset",
            "sleep_downshift",
        ]
    if 5 <= insert_offset <= 7:
        return [
            "tactical_cue_card",
            "neural_visualization",
            "breathing_reset",
            "mobility_rehab",
            "technical_shadow_rhythm",
            "tactical_watch",
            "recovery_reset",
        ]
    if 8 <= insert_offset <= 13:
        return [
            "tactical_watch",
            "tactical_cue_card",
            "technical_shadow_rhythm",
            "footwork_walkthrough",
            "mobility_rehab",
            "breathing_reset",
            "neural_visualization",
            "recovery_reset",
        ]
    return [
        "tactical_watch",
        "footwork_walkthrough",
        "mobility_rehab",
        "joint_prep",
        "walk_flush",
        "self_review",
        "movement_quality",
        "breathing_reset",
        "recovery_reset",
    ]


def _new_usage_ledger() -> dict[str, Any]:
    return {
        "used_role_keys": set(),
        "used_categories": set(),
        "role_key_offsets": {},
        "category_counts": {},
        # Tactical Watch keys already selected in this camp. Shared across every
        # week so no style/phase watch repeats and each phase occurrence advances
        # to the next authored watch (see tactical_watch_library).
        "used_tactical_watch_keys": set(),
    }


def _record_insert_usage(
    ledger: dict[str, Any], role_key: str, offset: int | None
) -> None:
    if role_key not in _ALL_INSERTS:
        return
    category = _insert_category(role_key)
    ledger.setdefault("used_role_keys", set()).add(role_key)
    ledger.setdefault("used_categories", set()).add(category)
    category_counts = ledger.setdefault("category_counts", {})
    category_counts[category] = int(category_counts.get(category, 0)) + 1
    if offset is not None:
        ledger.setdefault("role_key_offsets", {}).setdefault(role_key, []).append(offset)


def _usage_ledger_from_sequence(
    session_sequence: list[dict[str, Any]],
) -> dict[str, Any]:
    ledger = _new_usage_ledger()
    for role in session_sequence:
        role_key = str(role.get("role_key") or "")
        _record_insert_usage(ledger, role_key, _role_offset(role))
    return ledger


def _role_repeat_blocked(
    role_key: str,
    insert_offset: int,
    usage_ledger: dict[str, Any] | None,
) -> bool:
    if not usage_ledger:
        return False
    if bool((_INSERT_META.get(role_key) or {}).get("repeat_allowed")):
        return False
    previous_offsets = usage_ledger.get("role_key_offsets", {}).get(role_key, [])
    return any(abs(int(previous) - insert_offset) <= 7 for previous in previous_offsets)


def _base_preference_score(role_key: str, insert_offset: int) -> float:
    preferences = _time_band_preferences(insert_offset)
    if role_key not in preferences:
        return 1.0
    return float((len(preferences) - preferences.index(role_key)) * 4)


def _score_insert_role(
    role_key: str,
    athlete_model: dict[str, Any],
    insert_offset: int,
    *,
    usage_ledger: dict[str, Any] | None = None,
    gap_span: int | None = None,
) -> float:
    score = _base_preference_score(role_key, insert_offset)
    high_fatigue = _has_high_fatigue(athlete_model)
    active_cut = _has_active_weight_cut(athlete_model)
    injury_state = classify_injury_state(athlete_model)
    mobility_need = _has_mobility_need(athlete_model) or injury_state in {
        "mild_stable",
        "moderate_plus",
    }
    footwork_weakness = _has_footwork_weakness(athlete_model)
    power_speed_goal = _has_power_speed_goal(athlete_model)

    if active_cut:
        if role_key in {
            "tactical_cue_card",
            "breathing_reset",
            "sleep_downshift",
            "recovery_reset",
        }:
            score += 16
        if role_key == "tactical_watch":
            score += 14
        if role_key in PHYSICAL_INSERTS:
            score -= 20

    if high_fatigue:
        if role_key in {
            "breathing_reset",
            "sleep_downshift",
            "neural_visualization",
        }:
            score += 16
        elif role_key == "recovery_reset":
            score += 10
        if role_key in PHYSICAL_INSERTS:
            score -= 8

    if mobility_need:
        if injury_state != "none" and active_cut:
            mobility_boost = 55
        elif injury_state != "none" or not active_cut:
            mobility_boost = 28
        else:
            mobility_boost = 8
        if role_key in {"mobility_rehab", "joint_prep"}:
            score += mobility_boost

    if footwork_weakness:
        if role_key == "footwork_walkthrough":
            score += 24
        elif role_key == "technical_shadow_rhythm":
            score += 20
        elif role_key in {"tactical_watch", "tactical_cue_card"}:
            score += 6

    if power_speed_goal:
        if role_key in {"neural_visualization", "technical_shadow_rhythm"}:
            score += 16
        elif role_key == "footwork_walkthrough":
            score += 4

    if role_key in LOW_COST_AEROBIC_INSERTS:
        if _has_conditioning_goal(athlete_model):
            score += 22
            if high_fatigue or active_cut:
                if role_key in _ZERO_IMPACT_AEROBIC_INSERTS:
                    score += 6
                elif role_key in _IMPACT_AEROBIC_INSERTS:
                    score -= 10
            if role_key == "aerobic_shadow_flow" and _is_fight_sport(athlete_model):
                score += 3
        else:
            score -= 100

    if gap_span is not None and gap_span >= TWO_INSERT_GAP_MIN_DAYS:
        if role_key == "walk_flush":
            score += 8
        elif role_key == "mobility_rehab":
            score += 5
        elif role_key == "tactical_watch":
            score += 5
        elif role_key == "footwork_walkthrough":
            score += 4

    if usage_ledger:
        used_role_keys = usage_ledger.get("used_role_keys", set())
        used_categories = usage_ledger.get("used_categories", set())
        category = _insert_category(role_key)
        score += 2 if role_key not in used_role_keys else -2
        score += 1 if category not in used_categories else -0.75
        score -= (
            min(int(usage_ledger.get("category_counts", {}).get(category, 0)), 3)
            * 0.25
        )
    return score


def _select_role_key(
    athlete_model: dict[str, Any],
    insert_offset: int,
    allowed: set[str],
    *,
    usage_ledger: dict[str, Any] | None = None,
    gap_span: int | None = None,
    force_tactical: bool = False,
    force_conditioning: bool = False,
) -> str | None:
    candidates = set(allowed)
    if force_tactical:
        candidates &= TACTICAL_INSERTS
    elif force_conditioning:
        aerobic = candidates & LOW_COST_AEROBIC_INSERTS
        if aerobic:
            candidates = aerobic

    candidates = {
        role_key
        for role_key in candidates
        if not _role_repeat_blocked(role_key, insert_offset, usage_ledger)
    }
    if not candidates:
        return None

    preference_rank = {
        role_key: index
        for index, role_key in enumerate(_time_band_preferences(insert_offset))
    }
    all_inserts_index = {
        role_key: index for index, role_key in enumerate(sorted(_ALL_INSERTS))
    }
    return max(
        sorted(candidates),
        key=lambda role_key: (
            _score_insert_role(
                role_key,
                athlete_model,
                insert_offset,
                usage_ledger=usage_ledger,
                gap_span=gap_span,
            ),
            -preference_rank.get(role_key, 99),
            -all_inserts_index.get(role_key, 99),
        ),
    )


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
        "support_insert_category": _insert_category(role_key),
        "support_insert_cost_category": _cost_category(role_key),
        "mechanical_load_regions": list(insert_mechanical_load_regions(role_key)),
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
        role["countdown_display_label"] = (
            f"D-{insert_offset} ({weekday.title()})"
        )
    return role


def _phase_for_offset(offset: int | None) -> str:
    """Infer the camp phase for a countdown offset used by late-camp placement.

    The late-fight path has no explicit phase field; the countdown distance is
    the only signal. Fight week (<= 7 days) is TAPER; the compressed pre-fight
    window is opponent-specific (SPP).
    """
    try:
        value = int(offset)
    except (TypeError, ValueError):
        return "GPP"
    if value <= 0:
        return "TAPER"
    if value <= 7:
        return "TAPER"
    return "SPP"


def select_gap_fill_insert(
    athlete_model: dict[str, Any],
    insert_offset: int,
    *,
    on_hard_sparring_day: bool = False,
    usage_ledger: dict[str, Any] | None = None,
    gap_span: int | None = None,
    force_tactical: bool = False,
    force_conditioning: bool = False,
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

    role_key = _select_role_key(
        athlete_model,
        insert_offset,
        allowed,
        usage_ledger=usage_ledger,
        gap_span=gap_span,
        force_tactical=force_tactical,
        force_conditioning=force_conditioning,
    )
    if role_key is None:
        return None
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
    label = str(
        role.get("scheduled_countdown_label") or role.get("countdown_label") or ""
    )
    return _countdown_offset(label)


def _segment_for_offset(offset: int) -> int:
    return max(0, (offset - 1) // 7)


def _select_non_physical_insert(
    athlete_model: dict[str, Any],
    insert_offset: int,
    *,
    on_hard_sparring_day: bool,
    usage_ledger: dict[str, Any] | None = None,
    gap_span: int | None = None,
    force_tactical: bool = False,
) -> dict[str, Any] | None:
    allowed = _allowed_inserts(
        athlete_model,
        insert_offset,
        on_hard_sparring_day=on_hard_sparring_day,
    ) - PHYSICAL_INSERTS
    role_key = _select_role_key(
        athlete_model,
        insert_offset,
        allowed,
        usage_ledger=usage_ledger,
        gap_span=gap_span,
        force_tactical=force_tactical,
    )
    if not role_key:
        return None
    return _build_insert_role(role_key, athlete_model, insert_offset)


def _nearest_available_offset(
    target: int, available: list[int], chosen: set[int]
) -> int | None:
    candidates = [offset for offset in available if offset not in chosen]
    if not candidates:
        return None
    return min(candidates, key=lambda offset: (abs(offset - target), -offset))


def _gap_candidate_offsets(far_offset: int, near_offset: int) -> list[int]:
    gap = far_offset - near_offset
    if gap < GAP_FILL_MIN_DAYS:
        return []
    available = [
        offset for offset in range(far_offset - 1, near_offset, -1) if offset > 0
    ]
    if not available:
        return []

    target_count = 2 if gap >= TWO_INSERT_GAP_MIN_DAYS else 1
    if target_count == 1:
        targets = [near_offset + max(1, gap // 2)]
    else:
        targets = [
            near_offset + max(1, (gap * 2) // 3),
            near_offset + max(1, gap // 3),
        ]

    chosen: set[int] = set()
    for target in targets:
        selected = _nearest_available_offset(target, available, chosen)
        if selected is not None:
            chosen.add(selected)
    return sorted(chosen, reverse=True)


def _candidate_offsets_from_sequence(
    offsets: list[int], days_until_fight: int | None = None
) -> list[tuple[int, int]]:
    candidate_offsets: list[tuple[int, int]] = []

    if (
        days_until_fight is not None
        and 0 < days_until_fight <= LEADING_SPAN_MAX_DAYS_UNTIL_FIGHT
        and offsets
    ):
        first_offset = max(offsets)
        if days_until_fight > first_offset:
            leading_gap = days_until_fight - first_offset
            for target_offset in _gap_candidate_offsets(
                days_until_fight + 1, first_offset
            ):
                candidate_offsets.append((target_offset, leading_gap))

    for far_offset, near_offset in zip(offsets, offsets[1:]):
        gap = far_offset - near_offset
        for target_offset in _gap_candidate_offsets(far_offset, near_offset):
            candidate_offsets.append((target_offset, gap))

    trailing_gap = min(offsets)
    for target_offset in _gap_candidate_offsets(trailing_gap, 0):
        candidate_offsets.append((target_offset, trailing_gap))
    return candidate_offsets


def _declared_hard_sparring_offsets(
    countdown_map: dict[str, str],
    hard_sparring_days: set[str],
) -> list[int]:
    offsets: list[int] = []
    if not hard_sparring_days:
        return offsets
    for label, weekday in countdown_map.items():
        if str(weekday or "").strip().lower() not in hard_sparring_days:
            continue
        offset = _countdown_offset(label)
        if offset is not None and offset > 0:
            offsets.append(offset)
    return sorted(set(offsets), reverse=True)


def _has_tactical_support(session_sequence: list[dict[str, Any]]) -> bool:
    return any(
        str(role.get("role_key") or "") in TACTICAL_INSERTS
        for role in session_sequence
    )


def _has_future_fight(athlete_model: dict[str, Any], fallback: int) -> bool:
    try:
        return int(athlete_model.get("days_until_fight")) > 0
    except (TypeError, ValueError):
        return fallback > 0


def _watch_segment_bounds(segment: int, days_until_fight: int) -> tuple[int, int]:
    lower = segment * 7 + 1
    upper = min((segment + 1) * 7, days_until_fight)
    return lower, upper


def _watch_target_offset(segment: int, days_until_fight: int) -> int:
    lower, upper = _watch_segment_bounds(segment, days_until_fight)
    # D-5, D-13, D-21... keeps adjacent weekly watches eight days apart
    # whenever the available countdown window is long enough.
    preferred = 5 + (segment * 8)
    return min(upper, max(lower, preferred))


def _offset_role_counts(sequence: list[dict[str, Any]]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for role in sequence:
        offset = _role_offset(role)
        if offset is not None and offset > 0:
            counts[offset] = counts.get(offset, 0) + 1
    return counts


def _segment_watch_roles(
    sequence: list[dict[str, Any]], segment: int
) -> list[dict[str, Any]]:
    return [
        role
        for role in sequence
        if str(role.get("role_key") or "") == "tactical_watch"
        and (offset := _role_offset(role)) is not None
        and _segment_for_offset(offset) == segment
    ]


def _segment_watch_offset(
    sequence: list[dict[str, Any]],
    *,
    segment: int,
    days_until_fight: int,
) -> int | None:
    lower, upper = _watch_segment_bounds(segment, days_until_fight)
    if lower > upper:
        return None

    target = _watch_target_offset(segment, days_until_fight)
    roles_by_offset: dict[int, list[dict[str, Any]]] = {}
    for role in sequence:
        offset = _role_offset(role)
        if offset is not None and offset > 0:
            roles_by_offset.setdefault(offset, []).append(role)

    offsets = list(range(lower, upper + 1))
    fully_spaced = [
        offset
        for offset in offsets
        if offset not in roles_by_offset
        and all(abs(existing - offset) > 1 for existing in roles_by_offset)
    ]
    if fully_spaced:
        return min(fully_spaced, key=lambda offset: (abs(offset - target), -offset))

    occupied = [offset for offset in offsets if offset in roles_by_offset]
    if occupied:
        def shared_day_priority(offset: int) -> tuple[int, int, int, int]:
            roles = roles_by_offset[offset]
            categories = {
                str(role.get("category") or "").strip().lower()
                for role in roles
            }
            role_keys = {
                str(role.get("role_key") or "").strip().lower()
                for role in roles
            }
            if categories & {"support_insert", "recovery", "technical"}:
                load_priority = 0
            elif "hard_sparring_day" in role_keys or "sparring" in categories:
                load_priority = 1
            else:
                load_priority = 2
            return (load_priority, len(roles), abs(offset - target), -offset)

        return min(occupied, key=shared_day_priority)

    role_counts = {offset: len(roles) for offset, roles in roles_by_offset.items()}
    return min(
        offsets,
        key=lambda offset: (
            sum(count for existing, count in role_counts.items() if abs(existing - offset) == 1),
            sum(count for existing, count in role_counts.items() if abs(existing - offset) == 2),
            abs(offset - target),
            -offset,
        ),
        default=None,
    )

def _mandatory_watch_guidance(offset: int) -> str:
    if offset <= 7:
        return (
            "Fight-week focus: review familiar opponent footage and confirmed cues "
            "only. Do not add a new tactical theory this week."
        )
    return (
        "Camp focus: study the confirmed opponent. If footage is limited, use the "
        "closest style match and connect each cue to this week's technical work."
    )


def _build_mandatory_tactical_watch(
    athlete_model: dict[str, Any],
    offset: int,
    weekday: str | None,
    used_keys: set[str] | None = None,
) -> dict[str, Any]:
    watch = _build_insert_role("tactical_watch", athlete_model, offset, weekday)
    stamp_tactical_watch_role(
        watch,
        athlete_model,
        phase=_phase_for_offset(offset),
        used_keys=used_keys,
        camp_focus=_mandatory_watch_guidance(offset),
    )
    watch["mandatory_tactical_watch"] = True
    watch["weekly_requirement"] = "fight_tactical_watch"
    watch["tactical_watch_segment"] = _segment_for_offset(offset)
    watch["governance"] = {
        **dict(watch.get("governance") or {}),
        "authority": "gap_fill_support_insert",
        "mandatory": True,
        "meaningful_stress": False,
    }
    return watch


def _promote_mandatory_tactical_watch(
    role: dict[str, Any],
    athlete_model: dict[str, Any],
    countdown_map: dict[str, str],
    used_keys: set[str] | None = None,
) -> dict[str, Any]:
    offset = _role_offset(role)
    if offset is None or offset <= 0:
        raise RuntimeError("Existing Tactical Watch is not on a valid countdown day.")
    weekday = str(
        role.get("scheduled_day_hint")
        or role.get("real_weekday")
        or countdown_map.get(f"D-{offset}")
        or ""
    ).strip() or None
    template = _build_mandatory_tactical_watch(
        athlete_model, offset, weekday, used_keys
    )
    preserved = {
        key: value
        for key, value in role.items()
        if key not in {
            "display_text",
            "mandatory_tactical_watch",
            "weekly_requirement",
            "tactical_watch_segment",
            "governance",
            "tactical_watch_key",
            "tactical_watch_name",
            "tactical_watch_style",
            "tactical_watch_phase",
        }
    }
    role.clear()
    role.update(template)
    for key, value in preserved.items():
        role.setdefault(key, value)
    return role


def _replace_with_mandatory_tactical_watch(
    role: dict[str, Any],
    athlete_model: dict[str, Any],
    countdown_map: dict[str, str],
    used_keys: set[str] | None = None,
) -> dict[str, Any]:
    offset = _role_offset(role)
    if offset is None or offset <= 0:
        raise RuntimeError("Tactical support replacement has no valid countdown day.")
    weekday = str(
        role.get("scheduled_day_hint")
        or role.get("real_weekday")
        or countdown_map.get(f"D-{offset}")
        or ""
    ).strip() or None
    replaced_role_key = str(role.get("role_key") or "")
    replacement = _build_mandatory_tactical_watch(
        athlete_model, offset, weekday, used_keys
    )
    replacement["replaced_role_key"] = replaced_role_key
    role.clear()
    role.update(replacement)
    return role


def _ensure_weekly_tactical_watches(
    ordered: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    *,
    days_until_fight: int,
    countdown_map: dict[str, str],
) -> list[dict[str, Any]]:
    if not _has_future_fight(athlete_model, days_until_fight):
        return []

    required_segments = range(_segment_for_offset(days_until_fight) + 1)
    inserts: list[dict[str, Any]] = []
    combined = ordered + inserts
    # One shared ledger for this late-fight sequence: segments are walked from
    # the earliest date (largest segment) toward fight week, so each watch
    # advances to the next authored watch for its phase without repeating.
    used_watch_keys: set[str] = set()
    for segment in reversed(list(required_segments)):
        existing_watches = _segment_watch_roles(combined, segment)
        if existing_watches:
            keeper = existing_watches[0]
            _promote_mandatory_tactical_watch(
                keeper, athlete_model, countdown_map, used_watch_keys
            )
            for duplicate in existing_watches[1:]:
                duplicate["suppressed"] = True
                duplicate["reasons"] = list(
                    dict.fromkeys(
                        [
                            *clean_list(duplicate.get("reasons")),
                            (
                                "Only one Tactical Watch is allowed per seven-day "
                                "fight segment."
                            ),
                        ]
                    )
                )
                duplicate["reason_codes"] = list(
                    dict.fromkeys(
                        [
                            *clean_list(duplicate.get("reason_codes")),
                            "duplicate_weekly_tactical_watch",
                        ]
                    )
                )
                ordered[:] = [role for role in ordered if role is not duplicate]
                inserts[:] = [role for role in inserts if role is not duplicate]
            combined = ordered + inserts
            continue

        replaceable_tactical = next(
            (
                role
                for role in combined
                if str(role.get("role_key") or "") in (TACTICAL_INSERTS - {"tactical_watch"})
                and (offset := _role_offset(role)) is not None
                and _segment_for_offset(offset) == segment
            ),
            None,
        )
        if replaceable_tactical is not None:
            _replace_with_mandatory_tactical_watch(
                replaceable_tactical, athlete_model, countdown_map, used_watch_keys
            )
            continue

        offset = _segment_watch_offset(
            combined,
            segment=segment,
            days_until_fight=days_until_fight,
        )
        if offset is None or offset <= 0:
            raise RuntimeError(
                f"Unable to place mandatory Tactical Watch in countdown segment {segment}."
            )
        weekday = countdown_map.get(f"D-{offset}")
        watch = _build_mandatory_tactical_watch(
            athlete_model, offset, weekday, used_watch_keys
        )
        inserts.append(watch)
        combined = ordered + inserts
    return inserts


def apply_gap_fill_inserts(
    session_sequence: list[dict[str, Any]],
    athlete_model: dict[str, Any],
) -> list[dict[str, Any]]:
    ordered = sorted(
        [dict(role) for role in session_sequence],
        key=lambda role: int(_role_offset(role) or 0),
        reverse=True,
    )

    raw_days = athlete_model.get("days_until_fight")
    positive_offsets = [
        offset
        for role in ordered
        if (offset := _role_offset(role)) is not None and offset > 0
    ]
    if raw_days is not None and str(raw_days).strip() != "":
        try:
            days_until_fight = int(raw_days)
        except (TypeError, ValueError):
            days_until_fight = max(positive_offsets, default=0)
    else:
        days_until_fight = max(positive_offsets, default=0)

    if days_until_fight <= 0:
        return ordered

    creation_weekday = _resolve_plan_creation_weekday(days_until_fight, athlete_model)
    countdown_map = _countdown_weekday_map(creation_weekday, days_until_fight)
    hard_sparring_days = {
        day.strip().lower()
        for day in ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", [])))
    }

    existing_exclusive_offsets = {
        offset
        for role in ordered
        if str(role.get("role_key") or "") != "hard_sparring_day"
        and not is_low_cost_coexistable_filler(role)
        and (offset := _role_offset(role)) is not None
    }
    candidate_offsets = (
        _candidate_offsets_from_sequence(positive_offsets, days_until_fight)
        if positive_offsets
        else []
    )

    watch_horizon = min(days_until_fight, 21)
    inserts = _ensure_weekly_tactical_watches(
        ordered,
        athlete_model,
        days_until_fight=watch_horizon,
        countdown_map=countdown_map,
    )
    mandatory_watch_offsets = {
        int(offset)
        for role in ordered + inserts
        if str(role.get("role_key") or "") == "tactical_watch"
        and role.get("mandatory_tactical_watch")
        and (offset := _role_offset(role)) is not None
    }

    if days_until_fight <= 7:
        final_sequence = sorted(
            ordered + inserts,
            key=lambda role: int(_role_offset(role) or 0),
            reverse=True,
        )
        for index, role in enumerate(final_sequence, start=1):
            role["session_index"] = index
        return final_sequence

    physical_segment_counts: dict[int, int] = {}
    for role in ordered:
        role_key = str(role.get("role_key") or "")
        offset = _role_offset(role)
        if role_key in PHYSICAL_INSERTS and offset is not None:
            segment = _segment_for_offset(offset)
            physical_segment_counts[segment] = (
                physical_segment_counts.get(segment, 0) + 1
            )

    usage_ledger = _usage_ledger_from_sequence(ordered + inserts)
    conditioning_present = any(
        str(role.get("role_key") or "") in LOW_COST_AEROBIC_INSERTS
        for role in ordered + inserts
    )
    conditioning_required = _has_conditioning_goal(athlete_model)
    injury_state = classify_injury_state(athlete_model)
    coach_day_candidates = [
        (offset, 0)
        for offset in _declared_hard_sparring_offsets(
            countdown_map, hard_sparring_days
        )
        if offset not in existing_exclusive_offsets
        and offset not in mandatory_watch_offsets
    ]
    candidate_offsets = candidate_offsets + coach_day_candidates

    for target_offset, gap_span in candidate_offsets:
        if (
            target_offset <= 0
            or target_offset in existing_exclusive_offsets
            or target_offset in mandatory_watch_offsets
            or (
                days_until_fight > 13
                and any(
                    abs(target_offset - watch_offset) <= 1
                    for watch_offset in mandatory_watch_offsets
                )
            )
        ):
            continue
        weekday = countdown_map.get(f"D-{target_offset}")
        on_hard_sparring_day = bool(
            weekday and weekday.strip().lower() in hard_sparring_days
        )
        force_conditioning = (
            conditioning_required
            and not conditioning_present
            and bool(
                _safe_conditioning_maintenance_inserts(
                    athlete_model,
                    target_offset,
                    injury_state,
                    on_hard_sparring_day=on_hard_sparring_day,
                )
            )
        )
        if (
            len(inserts) >= MAX_INSERTS_TOTAL_D21_TO_D0
            and not force_conditioning
        ):
            break

        insert = select_gap_fill_insert(
            athlete_model,
            target_offset,
            on_hard_sparring_day=on_hard_sparring_day,
            usage_ledger=usage_ledger,
            gap_span=gap_span,
            force_tactical=False,
            force_conditioning=force_conditioning,
        )
        if insert is None:
            continue

        if insert["role_key"] in PHYSICAL_INSERTS:
            segment = _segment_for_offset(target_offset)
            if (
                physical_segment_counts.get(segment, 0)
                >= MAX_PHYSICAL_INSERTS_PER_7_DAY_SEGMENT
            ):
                insert = _select_non_physical_insert(
                    athlete_model,
                    target_offset,
                    on_hard_sparring_day=on_hard_sparring_day,
                    usage_ledger=usage_ledger,
                    gap_span=gap_span,
                    force_tactical=False,
                )
                if insert is None:
                    continue
            else:
                physical_segment_counts[segment] = (
                    physical_segment_counts.get(segment, 0) + 1
                )

        insert["scheduled_day_hint"] = weekday
        if weekday:
            insert["real_weekday"] = weekday
            insert["countdown_display_label"] = (
                f"D-{target_offset} ({weekday.title()})"
            )
        inserts.append(insert)
        _record_insert_usage(
            usage_ledger, str(insert.get("role_key") or ""), target_offset
        )
        if insert.get("role_key") in LOW_COST_AEROBIC_INSERTS:
            conditioning_present = True
        if not is_low_cost_coexistable_filler(insert):
            existing_exclusive_offsets.add(target_offset)

    final_sequence = sorted(
        ordered + inserts,
        key=lambda role: int(_role_offset(role) or 0),
        reverse=True,
    )
    for index, role in enumerate(final_sequence, start=1):
        role["session_index"] = index
    return final_sequence
