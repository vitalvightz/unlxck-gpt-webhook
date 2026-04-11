from __future__ import annotations

from typing import Any


_PAYLOAD_MODE_MAP = {
    0: "fight_day_protocol_payload",
    1: "pre_fight_day_payload",
    2: "late_fight_session_payload",
    3: "late_fight_session_payload",
    4: "late_fight_session_payload",
    5: "late_fight_transition_payload",
    6: "late_fight_transition_payload",
    7: "late_fight_week_payload",
    8: "pre_fight_compressed_payload",
    9: "pre_fight_compressed_payload",
    10: "pre_fight_compressed_payload",
    11: "pre_fight_compressed_payload",
    12: "pre_fight_compressed_payload",
    13: "pre_fight_compressed_payload",
}

_MAX_BLOCKS_PER_SESSION = {
    "fight_day_protocol_payload": 3,
    "pre_fight_day_payload": 4,
    "late_fight_session_payload": 4,
    "late_fight_transition_payload": 4,
    "late_fight_week_payload": 5,
    "pre_fight_compressed_payload": 5,
    "camp_payload": None,
}

_WEEKDAY_ORDER = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

_WEEKDAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _clean_list(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    return [str(values).strip()]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _ordered_weekdays(values: list[str]) -> list[str]:
    cleaned = _dedupe_preserve_order([str(value).strip() for value in values if str(value).strip()])
    return sorted(cleaned, key=lambda day: (_WEEKDAY_ORDER.get(day.strip().lower(), 99), day.strip().lower()))


def _declared_hard_spar_cap(days_until_fight: Any) -> int | None:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return None
    if 8 <= days <= 13:
        return 2
    if days == 7:
        return 1
    if 0 <= days <= 6:
        return 0
    return None


def _future_declared_weekdays_with_countdown(
    plan_creation_weekday: str | None,
    days_until_fight: Any,
    declared_weekdays: list[str],
) -> list[dict[str, Any]]:
    """Resolve declared weekdays into real upcoming countdown instances."""
    ordered_declared = _ordered_weekdays(declared_weekdays)
    if not plan_creation_weekday:
        try:
            days = int(days_until_fight)
        except (TypeError, ValueError):
            return []
        return [
            {"weekday": weekday, "countdown_label": None, "offset": days}
            for weekday in ordered_declared
        ]
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return []
    if days <= 0:
        return []
    creation_index = _WEEKDAY_ORDER.get(plan_creation_weekday.strip().lower())
    if creation_index is None:
        return []
    declared_set = set(ordered_declared)
    if not declared_set:
        return []
    future: list[dict[str, Any]] = []
    for day_offset in range(0, days + 1):
        weekday = _WEEKDAY_NAMES[(creation_index + day_offset) % 7]
        if weekday not in declared_set:
            continue
        countdown_offset = days - day_offset
        future.append(
            {
                "weekday": weekday,
                "countdown_label": f"D-{countdown_offset}",
                "offset": countdown_offset,
            }
        )
    return future


def _hard_spar_status_for_countdown_offset(offset: int) -> str:
    if 8 <= offset <= 13:
        return "hard_allowed"
    if offset == 7:
        return "hard_allowed_but_final_window"
    if 0 <= offset <= 6:
        return "downgrade"
    return "downgrade"


def _classify_declared_hard_days_for_late_window(
    plan_creation_weekday: str | None,
    days_until_fight: Any,
    declared_weekdays: list[str],
) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for entry in _future_declared_weekdays_with_countdown(
        plan_creation_weekday=plan_creation_weekday,
        days_until_fight=days_until_fight,
        declared_weekdays=declared_weekdays,
    ):
        classified.append(
            {
                **entry,
                "status": _hard_spar_status_for_countdown_offset(int(entry.get("offset", -1))),
            }
        )
    return classified


def _protected_collision_owner_day(athlete_model: dict[str, Any]) -> str | None:
    for key in ("primary_collision_owner_day", "main_fight_pace_day", "collision_owner_day", "planned_collision_owner_day"):
        day = str(athlete_model.get(key) or "").strip().lower()
        if day in _WEEKDAY_ORDER:
            return day
    return None


def _select_capped_declared_hard_day_instances(
    hard_allowed_days: list[dict[str, Any]],
    cap: int | None,
    protected_day: str | None = None,
) -> list[dict[str, Any]]:
    ordered = sorted(hard_allowed_days, key=lambda entry: int(entry.get("offset", -1)), reverse=True)
    if cap is None or len(ordered) <= cap:
        return ordered
    if cap <= 0:
        return []
    if cap == 1:
        if protected_day:
            protected = next((entry for entry in ordered if entry.get("weekday") == protected_day), None)
            if protected is not None:
                return [protected]
        return ordered[:1]
    if cap == 2:
        return [ordered[0], ordered[-1]]
    return ordered[:cap]


def _select_spaced_hard_days(declared_hard_days: list[str], cap: int | None) -> list[str]:
    ordered_days = _ordered_weekdays(declared_hard_days)
    if cap is None or len(ordered_days) <= cap:
        return ordered_days
    if cap == 1:
        return ordered_days[:1]
    if cap == 2:
        return [ordered_days[0], ordered_days[-1]]
    return ordered_days[:cap]


def _filter_past_weekdays(
    weekdays: list[str],
    plan_creation_weekday: str | None,
    days_until_fight: Any,
) -> list[str]:
    """Remove days that have already elapsed this week when close to fight.

    Only activates for late-fight windows (<=7 days out).  If the athlete
    creates their plan on Wednesday for a Sunday fight, Monday and Tuesday
    sparring declarations are already in the past and should not generate
    roles.
    """
    if not plan_creation_weekday or not weekdays:
        return weekdays
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return weekdays
    if days > 7:
        return weekdays
    creation_index = _WEEKDAY_ORDER.get(plan_creation_weekday.strip().lower())
    if creation_index is None:
        return weekdays
    return [
        day for day in weekdays
        if _WEEKDAY_ORDER.get(day.strip().lower(), 99) >= creation_index
    ]


def _fight_weekday_from_context(
    plan_creation_weekday: str | None,
    days_until_fight: Any,
) -> str | None:
    """Return the real weekday name of the fight day.

    Uses the plan creation weekday plus the number of days until the fight to
    compute which day of the week the fight falls on.  Returns ``None`` when
    either input is unavailable or invalid.
    """
    if not plan_creation_weekday:
        return None
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return None
    if days < 0:
        return None
    creation_index = _WEEKDAY_ORDER.get(plan_creation_weekday.strip().lower())
    if creation_index is None:
        return None
    fight_index = (creation_index + days) % 7
    return _WEEKDAY_NAMES[fight_index]


def _countdown_weekday_map(
    plan_creation_weekday: str | None,
    days_until_fight: Any,
) -> dict[str, str]:
    """Map each countdown label (D-0, D-1, …) to its real weekday name.

    The fight date is used as the anchor (D-0). Each prior countdown day is
    projected backwards by the corresponding number of days.  Only countdown
    days within the current late-fight window (0 ≤ n ≤ days_until_fight,
    capped at 7) are included.

    Returns an empty dict when the fight weekday cannot be determined.
    """
    fight_weekday = _fight_weekday_from_context(plan_creation_weekday, days_until_fight)
    if fight_weekday is None:
        return {}
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return {}
    fight_index = _WEEKDAY_ORDER[fight_weekday]
    countdown_map: dict[str, str] = {}
    for offset in range(min(days, 7) + 1):
        label = f"D-{offset}"
        weekday_index = (fight_index - offset) % 7
        countdown_map[label] = _WEEKDAY_NAMES[weekday_index]
    return countdown_map


def _nearest_available_day(
    target_weekday: str,
    available_days: list[str],
) -> str | None:
    """Return the available day closest to ``target_weekday``.

    Searches forward then backward from the target position in the week.
    Returns ``None`` when ``available_days`` is empty.
    """
    if not available_days:
        return None
    normalised = [d.strip().lower() for d in available_days if d.strip()]
    target_index = _WEEKDAY_ORDER.get(target_weekday.strip().lower())
    if target_index is None:
        return normalised[0] if normalised else None
    available_indices = {
        _WEEKDAY_ORDER.get(d, 99): d
        for d in normalised
        if _WEEKDAY_ORDER.get(d) is not None
    }
    if not available_indices:
        return normalised[0]
    if target_index in available_indices:
        return available_indices[target_index]
    for delta in range(1, 7):
        forward = (target_index + delta) % 7
        if forward in available_indices:
            return available_indices[forward]
        backward = (target_index - delta) % 7
        if backward in available_indices:
            return available_indices[backward]
    return list(available_indices.values())[0]


def _countdown_offset(label: str) -> int | None:
    normalized = str(label or "").strip().upper()
    if not normalized.startswith("D-"):
        return None
    try:
        return int(normalized[2:])
    except ValueError:
        return None


def _candidate_countdown_labels(days: int, mode: str) -> list[str]:
    if days < 0:
        return []
    if mode == "pre_fight_compressed_payload":
        lower_bound = 8
    elif mode == "late_fight_week_payload":
        lower_bound = 7
    elif mode == "late_fight_transition_payload":
        lower_bound = 5
    elif mode == "late_fight_session_payload":
        lower_bound = 2
    elif mode == "pre_fight_day_payload":
        lower_bound = 1
    elif mode == "fight_day_protocol_payload":
        lower_bound = 0
    else:
        lower_bound = 0
    start = max(days, lower_bound)
    return [f"D-{offset}" for offset in range(start, lower_bound - 1, -1)]


def _spaced_countdown_priority(labels: list[str]) -> list[str]:
    """Prefer non-consecutive countdown labels when the window allows."""
    if not labels:
        return []
    ordered = sorted(
        [label for label in labels if _countdown_offset(label) is not None],
        key=lambda value: int(_countdown_offset(value) or 0),
        reverse=True,
    )
    if len(ordered) <= 2:
        return ordered
    even_indices = ordered[::2]
    odd_indices = ordered[1::2]
    return even_indices + odd_indices


def _resolve_countdown_weekday_with_availability(
    countdown_map: dict[str, str],
    available_days: list[str],
) -> dict[str, str]:
    """Adjust countdown-day weekdays so each falls on an available training day.

    When a countdown day maps to a weekday that is not in ``available_days``,
    it is moved to the nearest available weekday with minimal disruption.
    Days are only adjusted; the countdown label (D-N) itself is preserved.
    Returns the original map unchanged when ``available_days`` is empty.
    """
    if not available_days or not countdown_map:
        return countdown_map
    normalised_available = [d.strip().lower() for d in available_days if d.strip()]
    countdown_offsets = {
        label: _countdown_offset(label)
        for label in countdown_map
    }
    resolved: dict[str, str] = {}
    for label, weekday in countdown_map.items():
        normalized_weekday = weekday.strip().lower()
        if normalized_weekday in normalised_available:
            resolved[label] = weekday
        else:
            current_offset = countdown_offsets.get(label)
            if current_offset is None:
                allowed_available = list(normalised_available)
            else:
                allowed_weekdays = {
                    str(mapped_weekday or "").strip().lower()
                    for mapped_label, mapped_weekday in countdown_map.items()
                    if (countdown_offsets.get(mapped_label) or 0) >= current_offset
                }
                allowed_available = [
                    day for day in normalised_available
                    if day in allowed_weekdays
                ]
            # Keep remaps inside the active late-fight window and avoid moving
            # a countdown day to a later weekday outside its slice.
            nearest = _nearest_available_day(weekday, allowed_available)
            resolved[label] = nearest if nearest is not None else weekday
    return resolved


def _normalized_fatigue(athlete_model: dict[str, Any]) -> str:
    fatigue = str(
        athlete_model.get("fatigue")
        or athlete_model.get("fatigue_level")
        or ""
    ).strip().lower()
    return fatigue if fatigue in {"low", "moderate", "high"} else "low"


def _readiness_flags(athlete_model: dict[str, Any]) -> set[str]:
    return {flag.strip().lower() for flag in _clean_list(athlete_model.get("readiness_flags", [])) if flag.strip()}


def _suppress_standalone_glycolytic(active_hard_spar_days: list[str], athlete_model: dict[str, Any]) -> bool:
    fatigue = _normalized_fatigue(athlete_model)
    flags = _readiness_flags(athlete_model)
    if len(active_hard_spar_days) >= 2:
        return True
    if fatigue == "high":
        return True
    if "aggressive_weight_cut" in flags:
        return True
    if "injury_management" in flags and fatigue in {"moderate", "high"}:
        return True
    return False


def _d3_alactic_suppression_reasons(athlete_model: dict[str, Any], days_until_fight: Any) -> list[str]:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return []
    if days != 3:
        return []

    reasons: list[str] = []
    fatigue = _normalized_fatigue(athlete_model)
    flags = _readiness_flags(athlete_model)
    spillover_flags = {
        "recent_hard_spar_collision_spillover",
        "heavy_spar_spillover",
        "collision_spillover",
    }
    conflicting_day_flags = {
        "hard_dose_yesterday",
        "conflicting_hard_dose_previous_day",
        "back_to_back_collision_risk",
    }

    if fatigue == "high":
        reasons.append("high_fatigue")
    if flags & spillover_flags:
        reasons.append("recent_hard_spar_spillover")
    if flags & conflicting_day_flags:
        reasons.append("conflicting_hard_dose_day")
    if "short_notice" in flags:
        reasons.append("short_notice_compression")

    max_blocks = _MAX_BLOCKS_PER_SESSION.get(_days_out_payload_mode(days_until_fight))
    if max_blocks is not None and max_blocks < 2:
        reasons.append("insufficient_block_budget")

    return reasons


def _allow_late_fight_alactic_sharpness(athlete_model: dict[str, Any], days_until_fight: Any) -> bool:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return False
    if days >= 4:
        return True
    if days != 3:
        return False
    return not _d3_alactic_suppression_reasons(athlete_model, days_until_fight)


def _late_fight_max_meaningful_stress_exposures(days_until_fight: Any) -> int | None:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return None
    if 8 <= days <= 13:
        return 3
    if days == 7:
        return 2
    if 1 <= days <= 6:
        return 1
    if days == 0:
        return 0
    return None


def _late_fight_max_active_roles(days_until_fight: Any) -> int | None:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return None
    if 8 <= days <= 13:
        return 4
    if days == 7:
        return 3
    if 3 <= days <= 6:
        return 2
    if 1 <= days <= 2:
        return 1
    if days == 0:
        return 0
    return None


def _late_fight_forbidden_blocks(days_until_fight: Any) -> list[str]:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return []
    if 8 <= days <= 13:
        return ["multiple_hard_sparring_exposures", "standalone_glycolytic", "primary_strength_anchor"]
    if days == 7:
        return ["standalone_glycolytic", "multiple_hard_sparring_exposures"]
    if days in {6, 5}:
        return ["hard_sparring", "standalone_glycolytic", "primary_strength_anchor"]
    if days == 4:
        return ["hard_sparring", "standalone_glycolytic", "primary_strength_anchor"]
    if days == 3:
        return ["hard_sparring", "standalone_glycolytic", "primary_strength_anchor"]
    if days == 2:
        return ["conditioning", "hard_sparring", "primary_strength_anchor"]
    if days == 1:
        return ["glycolytic", "hinge_transfer", "jumps", "contrast_work", "fight_pace_conditioning"]
    if days == 0:
        return ["strength", "conditioning", "layered_rehab_stack"]
    return []


def _role_anchor(role_key: str) -> str:
    if role_key in {
        "primary_strength_day",
        "structural_strength_day",
        "neural_plus_strength_day",
        "neural_primer_day",
        "alactic_speed_day",
        "alactic_sharpness_day",
        "alactic_coordination_day",
        "alactic_support_day",
    }:
        return "highest_neural_day"
    if role_key in {"fight_pace_repeatability_day", "light_fight_pace_touch_day", "hard_sparring_day"}:
        return "highest_glycolytic_day"
    if role_key in {"recovery_reset_day", "tissue_recovery_day", "fight_week_freshness_day"}:
        return "lowest_load_day"
    return "support_day"


def _fight_week_override_band(days_until_fight: Any) -> str:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return "none"
    if days < 0:
        return "none"
    if days <= 1:
        return "final_day_protocol"
    if days <= 3:
        return "micro_taper_protocol"
    if days <= 6:
        return "mini_taper_protocol"
    return "none"


def _fight_week_override_payload(days_until_fight: Any) -> dict[str, Any] | None:
    band = _fight_week_override_band(days_until_fight)
    if band == "none":
        return None

    base = {
        "active": True,
        "days_until_fight": days_until_fight,
        "band": band,
        "red_flags": ["do not chase fitness now"],
    }

    if band == "final_day_protocol":
        return {
            **base,
            "plan_mode": "readiness_protocol_only",
            "coach_note": "Fight is immediate. Use fight-day protocol language only and keep everything execution-first.",
            "allowed_session_roles": [],
            "protocol": [
                "No training-plan structure, no extra workload, and no volume accumulation.",
                "Use activation, breathing, a short shakeout, and warm-up guidance only.",
                "Keep every cue short, sharp, and tied to rhythm, timing, or execution.",
                "Include hydration, fuel, sleep, and weight-cut execution reminders.",
                "Today should read like fight-day protocol: activation, cues, fuel, walk-through, and post-fight recovery/refuel notes only.",
            ],
        }

    if band == "micro_taper_protocol":
        return {
            **base,
            "plan_mode": "micro_taper_only",
            "coach_note": "Use primer-only language. Do not render a normal weekly build.",
            "allowed_session_roles": ["alactic_sharpness_day", "fight_week_freshness_day"],
            "max_sessions": 2,
            "protocol": [
                "At most one short primer plus one light mobility / reset session.",
                "No hard conditioning, no soreness-heavy loading, and no new drills.",
                "Keep the language on sharpness, rhythm, activation, and freshness.",
            ],
        }

    return {
        **base,
        "plan_mode": "mini_taper_only",
        "coach_note": "Use a mini taper only. Keep the wording on sharpness, rhythm, and freshness rather than camp development.",
        "allowed_session_roles": ["neural_primer_day", "alactic_sharpness_day", "fight_week_freshness_day"],
        "max_sessions": 3,
        "protocol": [
            "Reduce volume and keep only high-value sharpness touches.",
            "Preserve speed, timing, and rhythm with one to two key sessions.",
            "If a conditioning element remains, frame it as rhythm or repeatability touch — not as a stress block.",
        ],
    }


def _days_out_payload_mode(days_until_fight: Any) -> str:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return "camp_payload"
    if days < 0:
        return "camp_payload"
    return _PAYLOAD_MODE_MAP.get(days, "camp_payload")


def _uses_late_fight_stage2_payload(days_until_fight: Any) -> bool:
    return _days_out_payload_mode(days_until_fight) != "camp_payload"


def _days_out_bucket(days_until_fight: Any) -> str:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return "CAMP"
    if days < 0 or days > 13:
        return "CAMP"
    return f"D-{days}"


def _late_fight_window(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "pre_fight_compressed_payload":
        return "d13_to_d8"
    if mode == "late_fight_week_payload":
        return "d7"
    if mode == "late_fight_transition_payload":
        return "d6_to_d5"
    if mode == "late_fight_session_payload":
        return "d4_to_d2"
    if mode == "pre_fight_day_payload":
        return "d1"
    if mode == "fight_day_protocol_payload":
        return "d0"
    return "camp"


def _late_fight_session_type_rules(days_until_fight: Any) -> tuple[list[str], list[str]]:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "pre_fight_compressed_payload":
        return (
            ["sparring", "technical", "strength", "sharpness", "recovery"],
            ["multiple_primary_strength_anchors", "multiple_standalone_glycolytic_stressors", "broad_development_week"],
        )
    if mode == "late_fight_week_payload":
        return ["strength", "sharpness", "recovery", "technical", "sparring"], ["broad_development_week"]
    if mode == "late_fight_transition_payload":
        return ["recovery", "technical", "sharpness"], ["full_strength_block", "glycolytic_build", "broad_weekly_architecture", "hard_sparring", "anchor_structure", "standalone_conditioning"]
    if mode == "late_fight_session_payload":
        try:
            days = int(days_until_fight)
        except (TypeError, ValueError):
            days = 3
        if days == 2:
            return ["primer", "technical"], ["conditioning", "hard_sparring", "full_strength_block", "glycolytic_build", "broad_weekly_architecture"]
        allowed = ["recovery", "technical"]
        if days >= 3:
            allowed.insert(0, "sharpness")
        return allowed, ["full_strength_block", "glycolytic_build", "broad_weekly_architecture", "hard_sparring", "strength_anchor"]
    if mode == "pre_fight_day_payload":
        return ["primer", "technical", "recovery"], ["full_strength_block", "conditioning_block", "hard_sparring", "hinge_transfer", "jumps", "contrast_work"]
    if mode == "fight_day_protocol_payload":
        return ["activation", "warm_up", "tactical_cues", "fueling", "recovery_notes"], ["strength", "conditioning", "sparring", "weekly_architecture", "layered_rehab_stack"]
    return ["strength", "conditioning", "recovery", "technical", "sparring"], []


def _late_fight_permissions(days_until_fight: Any, athlete_model: dict) -> dict:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "camp_payload":
        return {
            "mode": mode,
            "allow_full_weekly_structure": True,
            "allow_normal_session_roles": True,
            "allow_anchor_wording": True,
            "allow_development_language": True,
            "allow_glycolytic_build": True,
            "allow_broad_weakness_building": True,
            "max_meaningful_strength_anchors": None,
            "max_meaningful_conditioning_stressors": None,
            "allow_hard_sparring_influence": True,
            "allow_weekly_frequency_reasoning": True,
            "allow_multi_session_stress": True,
            "sparring_role": "full_collision_owner",
        }
    if mode == "pre_fight_compressed_payload":
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": True,
            "allow_normal_session_roles": True,
            "allow_anchor_wording": False,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": 1,
            "max_meaningful_conditioning_stressors": 1,
            "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
            "max_active_roles": _late_fight_max_active_roles(days_until_fight),
            "allow_hard_sparring_influence": True,
            "allow_weekly_frequency_reasoning": True,
            "allow_multi_session_stress": False,
            "sparring_role": "collision_owner_narrow",
            "forbid": [
                "more than 2 hard sparring exposures",
                "multiple standalone glycolytic stressors",
                "multiple primary strength anchors",
                "glycolytic stressor between hard sparring collisions",
                "broad development week framing",
            ],
        }
    if mode == "late_fight_week_payload":
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": True,
            "allow_normal_session_roles": True,
            "allow_anchor_wording": True,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": 1,
            "max_meaningful_conditioning_stressors": 1,
            "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
            "max_active_roles": _late_fight_max_active_roles(days_until_fight),
            "allow_hard_sparring_influence": True,
            "allow_weekly_frequency_reasoning": True,
            "allow_multi_session_stress": False,
            "sparring_role": "collision_owner_narrow",
            "forbid": [
                "broad development language",
                "multiple meaningful non-sparring stressors",
            ],
        }
    if mode == "late_fight_transition_payload":
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": False,
            "allow_session_list_only": True,
            "allow_normal_session_roles": False,
            "allow_anchor_wording": False,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": 0,
            "max_meaningful_conditioning_stressors": 0,
            "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
            "max_active_roles": _late_fight_max_active_roles(days_until_fight),
            "allow_hard_sparring_influence": False,
            "allow_weekly_frequency_reasoning": False,
            "allow_multi_session_stress": False,
            "sparring_role": "advisory_only",
            "allow_alactic_sharpness": True,
            "allow_activation_mobility": True,
            "max_sessions": 2,
            "forbid": [
                "normal camp-week framing",
                "broad weekly architecture",
                "developmental strength block",
                "glycolytic build logic",
                "hard sparring",
                "multiple session stressors",
            ],
        }
    if mode == "late_fight_session_payload":
        try:
            days = int(days_until_fight)
        except (TypeError, ValueError):
            days = 3
        allow_alactic_sharpness = _allow_late_fight_alactic_sharpness(athlete_model, days_until_fight)
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": False,
            "allow_session_list_only": True,
            "allow_normal_session_roles": False,
            "allow_anchor_wording": False,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": 0,
            "max_meaningful_conditioning_stressors": 0,
            "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
            "max_active_roles": _late_fight_max_active_roles(days_until_fight),
            "allow_hard_sparring_influence": False,
            "allow_weekly_frequency_reasoning": False,
            "allow_multi_session_stress": False,
            "sparring_role": "suppressed",
            "allow_alactic_sharpness": allow_alactic_sharpness,
            "allow_activation_mobility": True,
            "max_sessions": 1 if days == 2 else 2,
            "forbid": [
                "normal camp-week framing",
                "broad weekly architecture",
                "developmental strength block",
                "glycolytic build logic",
                "broad weakness-building language",
                "program block framing",
                "phase-explanation dump",
                "long rationale sections",
                "hard sparring",
            ],
        }
    if mode == "pre_fight_day_payload":
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": False,
            "allow_session_list_only": False,
            "allow_primer_only": True,
            "allow_normal_session_roles": False,
            "allow_anchor_wording": False,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": 0,
            "max_meaningful_conditioning_stressors": 0,
            "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
            "max_active_roles": _late_fight_max_active_roles(days_until_fight),
            "allow_hard_sparring_influence": False,
            "allow_weekly_frequency_reasoning": False,
            "allow_multi_session_stress": False,
            "sparring_role": "suppressed",
            "allow": [
                "neural primer",
                "light technical touch",
                "mobility / reset",
                "pre-fight instructions",
            ],
            "forbid": [
                "anchor wording",
                "primary strength",
                "full strength block",
                "glycolytic insert",
                "weekly architecture framing",
                "hard sparring influence",
                "conditioning-system allocation",
                "fight-pace density",
                "conditioning block",
                "hinge-transfer work",
                "jumps",
                "contrast work",
            ],
        }
    return {
        "mode": mode,
        "allow_full_weekly_structure": False,
        "allow_compressed_weekly_structure": False,
        "allow_session_list_only": False,
        "allow_primer_only": False,
        "allow_fight_day_protocol_only": True,
        "allow_normal_session_roles": False,
        "allow_anchor_wording": False,
        "allow_development_language": False,
        "allow_glycolytic_build": False,
        "allow_broad_weakness_building": False,
        "max_meaningful_strength_anchors": 0,
        "max_meaningful_conditioning_stressors": 0,
        "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
        "max_active_roles": _late_fight_max_active_roles(days_until_fight),
        "allow_hard_sparring_influence": False,
        "allow_weekly_frequency_reasoning": False,
        "allow_multi_session_stress": False,
        "sparring_role": "suppressed",
        "allow": [
            "activation",
            "warm-up",
            "tactical cueing",
            "fueling / hydration / logistics",
            "post-fight recovery notes",
        ],
        "forbid": [
            "all normal week logic",
            "strength generation",
            "conditioning generation",
            "session-role generation",
            "hard sparring relevance",
            "weekly role map rendering as a real week",
            "layered rehab stack",
        ],
    }


def _late_fight_rendering_rules(days_until_fight: Any) -> dict:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "camp_payload":
        return {"mode": mode, "rules": []}
    if mode == "pre_fight_compressed_payload":
        return {
            "mode": mode,
            "framing": "countdown_insert_or_unified_countdown",
            "rules": [
                "Frame this as either a countdown insert or one unified countdown schedule, never as a fake Monday-Sunday week.",
                "Present sessions countdown-first (D-N first, weekday second).",
                "If this does not fully prescribe every active day, label exactly: Coach-prescribed S&C / rehab schedule only. Boxing schedule remains as set by gym/coach.",
                "Never mix two schedule realities in one output (no 'sessions only' statement plus separate boxing-day listing).",
                "Keep the language on technical rhythm, sharpness, one meaningful strength touch, and freshness.",
                "No broad development week framing or conditioning-build language.",
                "Do not stack standalone glycolytic density beside multiple hard sparring days.",
                "Cap total meaningful stress exposures at 3 and keep each session at five blocks or less.",
                "Never label D-0 as training. D-0 is fight-day protocol only.",
            ],
            "preferred_terms": [
                "countdown insert",
                "countdown schedule",
                "technical rhythm",
                "sharpness",
                "strength touch",
                "freshness",
                "mobility / reset",
            ],
            "forbidden_terms": [
                "development block",
                "conditioning build",
                "secondary anchor",
                "extra density push",
                "monday-sunday schedule",
                "d-0 freshness session",
                "d-0 strength touch",
                "d-0 conditioning",
            ],
        }
    if mode == "late_fight_week_payload":
        return {
            "mode": mode,
            "framing": "compressed_week",
            "rules": [
                "Use concise sharpness-week framing.",
                "Anchor all sessions by countdown position first (D-N), not by a synthetic Monday-Sunday skeleton.",
                "Keep the language on power touch, neural touch, technical rhythm, freshness, and mobility / reset.",
                "No broad development language or camp-block wording.",
                "Cap meaningful non-sparring stressors at one.",
                "Keep sparring collision logic active but capped to one hard session.",
                "Keep each session at five blocks or less.",
            ],
            "preferred_terms": [
                "sharpness week",
                "power touch",
                "neural touch",
                "technical rhythm",
                "freshness session",
                "mobility / reset",
            ],
            "forbidden_terms": [
                "primary strength",
                "secondary strength",
                "anchor day",
                "conditioning block",
                "development block",
                "support strength",
            ],
        }
    if mode == "late_fight_transition_payload":
        return {
            "mode": mode,
            "framing": "session_by_session",
            "rules": [
                "Render session-by-session, not as a weekly build.",
                "Lead each item with its countdown label (D-N) and then weekday.",
                "No hard sparring — technical rhythm and sharpness touch only.",
                "When this is an insert, cap coach-prescribed insert work to 2 sessions: one power touch or technical rhythm session + one freshness session.",
                "If this does not fully prescribe every active day, label exactly: Coach-prescribed S&C / rehab schedule only. Boxing schedule remains as set by gym/coach.",
                "Never mix insert-only wording with separate full-week boxing listings in the same output.",
                "No strength-anchor, conditioning-stressor, or support-strength wording.",
                "No development language or program-block framing.",
                "Keep each session at four blocks or less.",
                "Never label D-0 as training. D-0 is fight-day protocol only.",
            ],
            "preferred_terms": [
                "sharpness",
                "power touch",
                "technical rhythm",
                "recovery",
                "freshness",
                "mobility / reset",
            ],
            "forbidden_terms": [
                "primary strength",
                "anchor day",
                "conditioning block",
                "developmental work",
                "volume build",
            ],
        }
    if mode == "late_fight_session_payload":
        return {
            "mode": mode,
            "framing": "session_by_session",
            "rules": [
                "Render session-by-session, not as a program block.",
                "Lead each session with countdown-first framing (D-N, then weekday).",
                "If this does not fully prescribe every active day, label exactly: Coach-prescribed S&C / rehab schedule only. Boxing schedule remains as set by gym/coach.",
                "Never mix insert-only wording with separate full-week boxing listings in the same output.",
                "Use sharpness session, technical touch, low-noise power, freshness session, primer, and reset language.",
                "No 'program block' framing.",
                "No phase-explanation dump.",
                "No long rationale sections.",
                "Keep each session description tight and action-oriented.",
                "Respect the per-session four-block ceiling.",
                "Never label D-0 as training. D-0 is fight-day protocol only.",
            ],
            "preferred_terms": [
                "sharpness session",
                "technical touch",
                "low-noise power",
                "freshness session",
                "rhythm day",
                "primer",
            ],
            "forbidden_terms": [
                "strength block",
                "conditioning stressor",
                "glycolytic session",
                "support strength",
                "secondary strength",
                "weekly architecture",
            ],
        }
    if mode == "pre_fight_day_payload":
        return {
            "mode": mode,
            "framing": "primer_only",
            "rules": [
                "Output primer-only content.",
                "No anchor, strength, conditioning, block, or fight-pace density language.",
                "Prefer terms: neural primer, technical touch, sharpness, activation, reset, rhythm.",
                "Keep the entire output under 300 words.",
                "Keep the session at four blocks or less.",
            ],
            "forbidden_terms": [
                "anchor",
                "primary strength",
                "strength",
                "conditioning block",
                "conditioning",
                "fight-pace density",
                "block",
                "hinge-transfer",
                "jumps",
                "contrast",
            ],
            "preferred_terms": [
                "neural primer",
                "technical touch",
                "sharpness",
                "activation",
                "reset",
                "rhythm",
            ],
        }
    return {
        "mode": mode,
        "framing": "fight_day_protocol",
        "rules": [
            "No training language.",
            "Output activation, warm-up, cue, fuel, walk-through, and recovery content only.",
            "Do not render a weekly role map or session architecture.",
            "Keep the output minimal and fight-day focused.",
            "If you present an activation sequence, keep it to three blocks or less.",
        ],
        "forbidden_terms": [
            "anchor",
            "primary strength",
            "conditioning block",
            "fight-pace density",
            "weekly role map",
            "session architecture",
            "strength",
            "conditioning",
            "rehab stack",
        ],
        "preferred_terms": [
            "activation",
            "warm-up",
            "cue",
            "fuel",
            "walk-through",
            "recover",
        ],
    }


def _days_out_payload_block(days_until_fight: Any, athlete_model: dict) -> dict:
    mode = _days_out_payload_mode(days_until_fight)
    permissions = _late_fight_permissions(days_until_fight, athlete_model)
    rendering_rules = _late_fight_rendering_rules(days_until_fight)
    fight_week_override = _fight_week_override_payload(days_until_fight)
    allowed_session_types, forbidden_session_types = _late_fight_session_type_rules(days_until_fight)
    max_blocks = _MAX_BLOCKS_PER_SESSION.get(mode)
    return {
        "days_until_fight": days_until_fight,
        "payload_mode": mode,
        "payload_variant": "late_fight_stage2_payload" if _uses_late_fight_stage2_payload(days_until_fight) else "normal_stage2_payload",
        "days_out_bucket": _days_out_bucket(days_until_fight),
        "late_fight_window": _late_fight_window(days_until_fight),
        "fight_week_override": fight_week_override or {"active": False},
        "late_fight_permissions": permissions,
        "allowed_session_types": allowed_session_types,
        "forbidden_session_types": forbidden_session_types,
        "rendering_rules": rendering_rules,
        "forbidden_blocks": _late_fight_forbidden_blocks(days_until_fight),
        "max_blocks_per_session": max_blocks,
    }


def _late_fight_role_entry(
    *,
    session_index: int,
    category: str,
    role_key: str,
    selection_rule: str,
    preferred_pool: str,
    placement_rule: str,
    preferred_system: str | None = None,
) -> dict[str, Any]:
    entry = {
        "session_index": session_index,
        "category": category,
        "role_key": role_key,
        "preferred_pool": preferred_pool,
        "selection_rule": selection_rule,
        "anchor": _role_anchor(role_key),
        "placement_rule": placement_rule,
        "governance": {"late_fight_payload": True},
    }
    if preferred_system:
        entry["preferred_system"] = preferred_system
    return entry


def _late_fight_session_roles(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    mode = _days_out_payload_mode(days_until_fight)
    plan_weekday = athlete_model.get("plan_creation_weekday")
    declared_hard_days = _filter_past_weekdays(
        _ordered_weekdays(_clean_list(athlete_model.get("hard_sparring_days", []))),
        plan_weekday,
        days_until_fight,
    )
    declared_countdown_hard_days = _classify_declared_hard_days_for_late_window(
        plan_creation_weekday=plan_weekday,
        days_until_fight=days_until_fight,
        declared_weekdays=declared_hard_days,
    )
    protected_day = _protected_collision_owner_day(athlete_model)
    hard_allowed_instances = [
        day for day in declared_countdown_hard_days
        if day.get("status") in {"hard_allowed", "hard_allowed_but_final_window"}
    ]
    active_hard_instances = _select_capped_declared_hard_day_instances(
        hard_allowed_instances,
        _declared_hard_spar_cap(days_until_fight),
        protected_day=protected_day,
    )
    active_hard_days = [str(entry.get("weekday")) for entry in active_hard_instances]

    if mode == "pre_fight_compressed_payload":
        roles: list[dict[str, Any]] = []
        session_index = 1

        for hard_day in active_hard_instances:
            role = _late_fight_role_entry(
                session_index=session_index,
                category="conditioning",
                role_key="hard_sparring_day",
                preferred_pool="declared_hard_sparring_days",
                selection_rule="Resolve future declared hard sparring days by countdown first, then cap surviving hard-allowed exposures.",
                placement_rule="Never remap hard sparring to a non-declared day; keep surviving declared days fixed.",
            )
            role.update(
                {
                    "scheduled_day_hint": hard_day.get("weekday"),
                    "locked_day": hard_day.get("weekday"),
                    "countdown_label": hard_day.get("countdown_label"),
                    "countdown_offset": hard_day.get("offset"),
                    "day_assignment_reason": "Declared hard sparring day survives countdown and cap rules.",
                    "declared_day_locked": True,
                }
            )
            roles.append(role)
            session_index += 1

        strength_selection_rule = "Use one meaningful strength or power touch only."
        strength_placement_rule = "Keep this away from the main collision load and do not let it become a second anchor."
        if len(active_hard_days) >= 2:
            strength_selection_rule = "Use one smaller strength or power touch only when two hard sparring exposures already own the week."
            strength_placement_rule = "Keep this clearly smaller than a full neural anchor and away from the heavier collision day."
        roles.append(
            _late_fight_role_entry(
                session_index=session_index,
                category="strength",
                role_key="strength_touch_day",
                preferred_pool="strength_slots",
                selection_rule=strength_selection_rule,
                placement_rule=strength_placement_rule,
            )
        )
        session_index += 1

        if not _suppress_standalone_glycolytic(active_hard_days, athlete_model):
            roles.append(
                _late_fight_role_entry(
                    session_index=session_index,
                    category="conditioning",
                    role_key="light_fight_pace_touch_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="glycolytic",
                    selection_rule="Allow at most one light fight-rhythm touch only when sparring does not already own the week.",
                    placement_rule="Keep this light, never describe it as a conditioning build, and never place it between two hard sparring collisions.",
                )
            )
            session_index += 1

        roles.append(
            _late_fight_role_entry(
                session_index=session_index,
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Require one freshness, mobility, and reset session in this compressed pre-fight week.",
                placement_rule="Keep this as the lowest-load day and preserve readiness over extra development.",
            )
        )
        return roles
    if mode == "late_fight_week_payload":
        roles: list[dict[str, Any]] = []
        session_index = 1
        # Cap to at most 1 hard sparring slot even with multiple declared days
        if active_hard_instances:
            surviving = active_hard_instances[0]
            role = _late_fight_role_entry(
                session_index=session_index,
                category="conditioning",
                role_key="hard_sparring_day",
                preferred_pool="declared_hard_sparring_days",
                selection_rule="Keep exactly one declared hard sparring day when countdown allows hard sparring.",
                placement_rule="Treat the declared hard sparring day as fixed and compress everything around it.",
            )
            role.update(
                {
                    "scheduled_day_hint": surviving.get("weekday"),
                    "locked_day": surviving.get("weekday"),
                    "countdown_label": surviving.get("countdown_label"),
                    "countdown_offset": surviving.get("offset"),
                    "day_assignment_reason": "Declared hard sparring day survives countdown and cap rules.",
                    "declared_day_locked": True,
                }
            )
            roles.append(role)
            session_index += 1
        roles.append(
            _late_fight_role_entry(
                session_index=session_index,
                category="strength",
                role_key="neural_primer_day",
                preferred_pool="strength_slots",
                selection_rule="Use one sharp, low-volume neural strength or power exposure only.",
                placement_rule="Keep this away from the main collision load and keep the dose small.",
            )
        )
        session_index += 1
        if not active_hard_days:
            roles.append(
                _late_fight_role_entry(
                    session_index=session_index,
                    category="conditioning",
                    role_key="alactic_sharpness_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="alactic",
                    selection_rule="Use one alactic sharpness exposure instead of a normal conditioning build.",
                    placement_rule="Keep this brief and crisp; do not turn it into density work.",
                )
            )
            session_index += 1
        roles.append(
            _late_fight_role_entry(
                session_index=session_index,
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Use freshness, mobility, and reset work to preserve readiness.",
                placement_rule="Keep this as the lowest-load day of the week.",
            )
        )
        return roles
    if mode == "late_fight_transition_payload":
        # D-6/D-5: alactic sharpness touch + recovery only, no hard sparring
        roles: list[dict[str, Any]] = [
            _late_fight_role_entry(
                session_index=1,
                category="conditioning",
                role_key="alactic_sharpness_day",
                preferred_pool="declared_technical_skill_days_or_conditioning_slots",
                preferred_system="alactic",
                selection_rule="One short alactic sharpness touch only. Keep it tiny, crisp, and non-fatiguing.",
                placement_rule="Keep this brief and very low volume. Do not turn it into density work.",
            ),
            _late_fight_role_entry(
                session_index=2,
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Mobility, breathing, and tissue recovery only.",
                placement_rule="Lowest-load session. Prioritise readiness over any training stimulus.",
            ),
        ]
        if declared_hard_days:
            for role in roles:
                role.setdefault("coach_notes", [])
                role["coach_notes"].append(
                    f"Hard sparring overridden to technical/rhythm only — {_days_out_bucket(days_until_fight)} is too close to fight day."
                )
        return roles
    if mode == "late_fight_session_payload":
        roles: list[dict[str, Any]] = []
        try:
            days = int(days_until_fight)
        except (TypeError, ValueError):
            days = 3
        if days == 2:
            return [
                _late_fight_role_entry(
                    session_index=1,
                    category="strength",
                    role_key="neural_primer_day",
                    preferred_pool="strength_slots",
                    selection_rule="One short neural sharpness touch only.",
                    placement_rule="Keep it crisp, low-volume, and fully non-fatiguing.",
                )
            ]
        if days >= 4 or _allow_late_fight_alactic_sharpness(athlete_model, days_until_fight):
            roles.append(
                _late_fight_role_entry(
                    session_index=1,
                    category="conditioning",
                    role_key="alactic_sharpness_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="alactic",
                    selection_rule="Use one short alactic sharpness touch only if it keeps the athlete fresher, not flatter.",
                    placement_rule="Keep this brief and low-noise.",
                )
            )
        roles.append(
            _late_fight_role_entry(
                session_index=len(roles) + 1,
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Use recovery, breathing, and mobility to preserve rhythm and readiness.",
                placement_rule="Keep this as the lowest-load session in the window.",
            )
        )
        return roles
    if mode == "pre_fight_day_payload":
        return [
            _late_fight_role_entry(
                session_index=1,
                category="strength",
                role_key="neural_primer_day",
                preferred_pool="strength_slots",
                selection_rule="Render at most one tiny neural primer; do not build a normal training week.",
                placement_rule="Keep it short, clean, and immediately supportive of tomorrow's performance.",
            )
        ]
    return []


def _build_late_fight_session_sequence(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    plan_creation_weekday = athlete_model.get("plan_creation_weekday")
    available_days = _clean_list(athlete_model.get("training_days", []))
    countdown_map = _countdown_weekday_map(plan_creation_weekday, days_until_fight)
    resolved_map = _resolve_countdown_weekday_with_availability(countdown_map, available_days)
    roles = _late_fight_session_roles(days_until_fight, athlete_model)
    mode = _days_out_payload_mode(days_until_fight)
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        days = None
    available_countdown_labels: list[str] = []
    reserved_countdown_labels: set[str] = set()
    if days is not None and days >= 0:
        all_labels = _candidate_countdown_labels(days, mode)
        reserved_countdown_labels = {
            str(role.get("countdown_label"))
            for role in roles
            if str(role.get("countdown_label") or "").startswith("D-")
        }
        available_countdown_labels = _spaced_countdown_priority(
            [label for label in all_labels if label not in reserved_countdown_labels]
        )
    sequence: list[dict[str, Any]] = []
    for role in roles:
        if days is not None:
            role_countdown_label = role.get("countdown_label")
            if role_countdown_label and str(role_countdown_label).startswith("D-"):
                candidate_label = str(role_countdown_label)
                if candidate_label in reserved_countdown_labels:
                    countdown_label = candidate_label
                    reserved_countdown_labels.discard(candidate_label)
                elif available_countdown_labels:
                    countdown_label = available_countdown_labels.pop(0)
                else:
                    countdown_label = candidate_label
            else:
                countdown_label = available_countdown_labels.pop(0) if available_countdown_labels else None
        else:
            countdown_label = None
        locked_day = str(role.get("locked_day") or "").strip().lower()
        if role.get("role_key") == "hard_sparring_day" and locked_day:
            real_weekday = locked_day
        else:
            real_weekday = resolved_map.get(countdown_label) if countdown_label else None
        entry: dict[str, Any] = {
            "session_index": role.get("session_index"),
            "category": role.get("category"),
            "role_key": role.get("role_key"),
            "preferred_pool": role.get("preferred_pool"),
            "preferred_system": role.get("preferred_system"),
            "selection_rule": role.get("selection_rule"),
            "placement_rule": role.get("placement_rule"),
            "anchor": role.get("anchor"),
        }
        if countdown_label:
            entry["countdown_label"] = countdown_label
        if real_weekday:
            entry["real_weekday"] = real_weekday
        if role.get("declared_day_locked"):
            entry["declared_day_locked"] = True
        if role.get("scheduled_day_hint"):
            entry["scheduled_day_hint"] = role.get("scheduled_day_hint")
        if role.get("locked_day"):
            entry["locked_day"] = role.get("locked_day")
        if role.get("day_assignment_reason"):
            entry["day_assignment_reason"] = role.get("day_assignment_reason")
        sequence.append(entry)
    return sequence


def _late_fight_stage_label(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "pre_fight_compressed_payload":
        return "Countdown Insert Window (D-13 to D-8)"
    if mode == "late_fight_week_payload":
        return "Countdown Sharpness Window (D-7)"
    if mode == "late_fight_transition_payload":
        return "Countdown Insert Window (D-6 to D-5)"
    if mode == "late_fight_session_payload":
        return "Countdown Insert Sessions (D-4 to D-2)"
    if mode == "pre_fight_day_payload":
        return "Countdown Primer (D-1)"
    if mode == "fight_day_protocol_payload":
        return "Fight-Day Protocol (D-0)"
    return "Camp"


def _late_fight_summary(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "pre_fight_compressed_payload":
        return (
            "Use countdown-first late-fight guidance. If you are not prescribing every active day, present this as "
            "a coach-prescribed S&C / rehab insert around the gym boxing schedule; otherwise present one unified "
            "countdown schedule."
        )
    if mode == "late_fight_week_payload":
        return "Use countdown-first D-7 sharpness guidance without Monday-Sunday framing. Keep scope explicit (insert-only vs one unified countdown schedule) and avoid mixed schedule realities."
    if mode == "late_fight_transition_payload":
        return "Use a D-6 to D-5 countdown insert focused on technical rhythm, small power touch, and freshness. No hard sparring, no camp-style headings, and no conflicting full-week claims."
    if mode == "late_fight_session_payload":
        return "Use a short D-4 to D-2 countdown insert list (technical touch, low-noise power, freshness, reset), not a fake full-week planner."
    if mode == "pre_fight_day_payload":
        return "Use D-1 primer-only guidance: neural primer, technical touch, activation, reset, and rhythm."
    if mode == "fight_day_protocol_payload":
        return "Use D-0 fight-day protocol only: activation, warm-up, cue, fuel, walk-through, and recover. No training-session language."
    return "Use the normal camp-stage payload."


def _build_late_fight_week_by_week_progression(days_until_fight: Any, athlete_model: dict, phase_briefs: dict[str, dict]) -> dict[str, Any]:
    if _days_out_payload_mode(days_until_fight) in {
        "fight_day_protocol_payload",
        "pre_fight_day_payload",
        "late_fight_session_payload",
        "late_fight_transition_payload",
    }:
        return {"weeks": []}
    phase = next((phase_name for phase_name in ("TAPER", "SPP", "GPP") if phase_name in phase_briefs), next(iter(phase_briefs), "TAPER"))
    roles = _late_fight_session_roles(days_until_fight, athlete_model)
    session_counts = {
        "strength": sum(1 for role in roles if role.get("category") == "strength"),
        "conditioning": sum(1 for role in roles if role.get("category") == "conditioning"),
        "recovery": sum(1 for role in roles if role.get("category") == "recovery"),
    }
    conditioning_sequence = [role.get("preferred_system") for role in roles if role.get("category") == "conditioning" and role.get("preferred_system")]
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase": phase,
                "stage_key": _late_fight_window(days_until_fight),
                "stage_label": _late_fight_stage_label(days_until_fight),
                "stage_objective": _late_fight_summary(days_until_fight),
                "phase_week_index": 1,
                "phase_week_total": 1,
                "session_counts": session_counts,
                "conditioning_sequence": conditioning_sequence or ["alactic"],
                "intentional_compression": {
                    "active": True,
                    "reason_codes": [_days_out_payload_mode(days_until_fight)],
                    "reason": _days_out_payload_mode(days_until_fight),
                    "summary": _late_fight_summary(days_until_fight),
                },
            }
        ]
    }


def _build_late_fight_weekly_role_map(days_until_fight: Any, athlete_model: dict, fight_week_override: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = _days_out_payload_mode(days_until_fight)
    plan_weekday = athlete_model.get("plan_creation_weekday")
    roles = _late_fight_session_roles(days_until_fight, athlete_model)
    available_days = _clean_list(athlete_model.get("training_days", []))
    raw_countdown_map = _countdown_weekday_map(plan_weekday, days_until_fight)
    resolved_countdown_map = _resolve_countdown_weekday_with_availability(raw_countdown_map, available_days)
    if mode in {"fight_day_protocol_payload", "pre_fight_day_payload", "late_fight_session_payload", "late_fight_transition_payload"}:
        weeks: list[dict[str, Any]] = []
    else:
        filtered_training = _filter_past_weekdays(
            _ordered_weekdays(_clean_list(athlete_model.get("training_days", []))),
            plan_weekday, days_until_fight,
        )
        filtered_sparring = _filter_past_weekdays(
            _ordered_weekdays(_clean_list(athlete_model.get("hard_sparring_days", []))),
            plan_weekday, days_until_fight,
        )
        filtered_technical = _filter_past_weekdays(
            _ordered_weekdays(_clean_list(athlete_model.get("technical_skill_days", []))),
            plan_weekday, days_until_fight,
        )
        weeks = [
            {
                "week_index": 1,
                "phase": "TAPER",
                "stage_key": _late_fight_window(days_until_fight),
                "phase_week_index": 1,
                "phase_week_total": 1,
                "declared_training_days": filtered_training,
                "declared_hard_sparring_days": filtered_sparring,
                "declared_technical_skill_days": filtered_technical,
                "hard_sparring_plan": [],
                "effective_hard_sparring_days": [],
                "coach_note_flags": [_late_fight_stage_label(days_until_fight)],
                "intentional_compression": {
                    "active": True,
                    "reason_codes": [mode],
                    "reason": mode,
                    "summary": _late_fight_summary(days_until_fight),
                },
                "intentionally_unused_days": [],
                "session_roles": roles,
                "suppressed_roles": [
                    {
                        "category": "plan",
                        "role_key": "normal_stage2_payload",
                        "reasons": ["late_fight_stage2_payload: bypassed normal camp-style stage2 payload assumptions"],
                    }
                ],
                "countdown_weekday_map": resolved_countdown_map,
            }
        ]
    return {
        "model": "late_fight_role_overlay.v1",
        "source_of_truth": [
            "Late-fight Stage 2 payload bypasses the normal camp-week payload path for 13 days and less.",
            "Use the late-fight role map as a compressed execution guide, not as a normal weekly build.",
            "Keep the output aligned to the time window first, then the athlete profile.",
        ],
        "payload_variant": "late_fight_stage2_payload",
        "payload_mode": mode,
        "fight_week_override": fight_week_override or {"active": False},
        "countdown_weekday_map": resolved_countdown_map,
        "weeks": weeks,
    }


def _build_late_fight_plan_spec(days_until_fight: Any, athlete_model: dict) -> dict[str, Any]:
    payload_block = _days_out_payload_block(days_until_fight, athlete_model)
    roles = _late_fight_session_roles(days_until_fight, athlete_model)
    session_sequence = _build_late_fight_session_sequence(days_until_fight, athlete_model)
    mode = payload_block["payload_mode"]
    max_blocks = _MAX_BLOCKS_PER_SESSION.get(mode)
    plan_creation_weekday = athlete_model.get("plan_creation_weekday")
    available_days = _clean_list(athlete_model.get("training_days", []))
    raw_countdown_map = _countdown_weekday_map(plan_creation_weekday, days_until_fight)
    resolved_countdown_map = _resolve_countdown_weekday_with_availability(raw_countdown_map, available_days)
    spec: dict[str, Any] = {
        "payload_variant": "late_fight_stage2_payload",
        "payload_mode": mode,
        "days_out_bucket": payload_block["days_out_bucket"],
        "late_fight_window": payload_block["late_fight_window"],
        "summary": _late_fight_summary(days_until_fight),
        "session_cap": len(roles),
        "session_roles": [role.get("role_key") for role in roles],
        "session_sequence": session_sequence,
        "allowed_session_types": payload_block["allowed_session_types"],
        "forbidden_session_types": payload_block["forbidden_session_types"],
        "forbidden_blocks": payload_block["forbidden_blocks"],
        "rendering_rules": payload_block["rendering_rules"],
        "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
        "max_active_roles": _late_fight_max_active_roles(days_until_fight),
        "countdown_weekday_map": resolved_countdown_map,
    }
    if max_blocks is not None:
        spec["max_blocks_per_session"] = max_blocks
    return spec


def _handoff_mode_instructions(payload_mode: str) -> str:
    countdown_contract = (
        "D-13 TO D-0 OUTPUT CONTRACT\n"
        "For any athlete with 13 days or fewer until fight, use one coherent countdown truth.\n"
        "Lead each active day with countdown-first labeling (D-N first, weekday second), and avoid fake Monday-Sunday framing.\n"
        "If output does NOT fully prescribe every active day, label it exactly as: Coach-prescribed S&C / rehab schedule only. Boxing schedule remains as set by gym/coach.\n"
        "When output fully prescribes all active days, use one unified section title: Countdown schedule.\n"
        "Do not frame late windows as a normal Monday-Sunday week without countdown labels.\n"
        "Never label D-0 as a training session. D-0 is fight-day protocol only (or omitted when no fight-day protocol is provided).\n"
        "Never claim 'two sessions only' while also listing separate boxing-day sessions in the same output.\n"
        "If output includes boxing plus S&C, treat all listed active days as one real integrated schedule and do not split into conflicting schedule realities.\n"
        "For declared hard-spar days: keep the declared day fixed. If countdown rules downgrade it, keep it on that same day as technical touch / controlled rounds / rhythm timing.\n"
        "Do not drop declared hard-spar days and do not move them.\n"
        "Use one hard-spar doctrine only inside a single output. No contradictions."
    )
    if payload_mode == "fight_day_protocol_payload":
        return (
            "HARD OVERRIDE — FIGHT DAY PROTOCOL\n"
            "This is D-0. The athlete fights today.\n"
            "Do NOT generate a training week, session-role structure, or weekly architecture.\n"
            "Do NOT use training-plan language such as strength, conditioning, anchor, block, or programming terms.\n"
            "If you present an activation sequence, cap it at 3 blocks.\n"
            "Output ONLY:\n"
            "- Activation / warm-up protocol\n"
            "- Tactical cueing (style, stance, rhythm)\n"
            "- Fueling / hydration / logistics\n"
            "- Walk-through reminders\n"
            "- Post-fight recovery notes\n"
            "Keep it short, decisive, and fight-ready.\n"
            "Do NOT restore any suppressed roles from the planning brief.\n"
            "Do NOT add any training session, conditioning dose, or layered rehab stack.\n\n"
            + countdown_contract
        )
    if payload_mode == "pre_fight_day_payload":
        return (
            "HARD OVERRIDE — PRIMER DAY (D-1)\n"
            "This is the day before the fight. Do NOT build a normal training week.\n"
            "Cap the session at 4 blocks.\n"
            "Output ONLY:\n"
            "- Neural primer (max 1 short session)\n"
            "- Technical touch if applicable\n"
            "- Activation\n"
            "- Mobility / reset protocol\n"
            "- Pre-fight instructions and preparation notes\n"
            "FORBIDDEN TERMS: strength, conditioning, anchor, development, stressor, fight-pace density, block, glycolytic, hinge-transfer, jumps, contrast.\n"
            "PREFERRED TERMS: neural primer, technical touch, sharpness, activation, reset, rhythm.\n"
            "Do NOT use weekly architecture framing.\n"
            "Do NOT restore suppressed session roles.\n"
            "Do NOT generate hard sparring or conditioning-system allocation.\n\n"
            + countdown_contract
        )
    if payload_mode == "pre_fight_compressed_payload":
        return (
            "LATE FIGHT MODE — COUNTDOWN PRE-FIGHT WINDOW (D-13 to D-8)\n"
            "This is a countdown window, not a normal SPP build.\n"
            "Use countdown framing and cap each session at 5 blocks.\n"
            "Keep no more than 2 hard sparring exposures.\n"
            "Keep one meaningful strength or power touch at most.\n"
            "Allow at most one light fight-rhythm touch, and suppress it entirely when sparring already owns the week.\n"
            "Always keep one freshness, mobility, or reset session.\n"
            "Do NOT frame this as a broad development week, conditioning build, or density push.\n"
            "Do NOT rebuild a normal SPP week in Stage 2.\n"
            "Do NOT place a standalone glycolytic stressor between two hard sparring collisions.\n"
            "Preferred headings: Countdown Insert, Countdown Schedule, Technical Rhythm, Sharpness, Strength Touch, Freshness, Mobility / Reset.\n"
            "Avoid headings such as Development Block, Conditioning Build, Secondary Anchor, Extra Density Push.\n"
            "Preserve freshness over extra development.\n\n"
            + countdown_contract
        )
    if payload_mode == "late_fight_session_payload":
        return (
            "LATE FIGHT MODE — SHARPNESS-FIRST SESSIONS (D-4 to D-2)\n"
            "Do NOT frame this as a normal camp week.\n"
            "Present the plan session-by-session, not as a program block.\n"
            "Do NOT render week headers, Monday-to-Sunday structure, or a full weekly schedule.\n"
            "Do NOT use broad development language, weekly architecture language, phase-explanation dumps, or long rationale sections.\n"
            "Do NOT generate strength blocks, conditioning stressors, support-strength language, or glycolytic build logic.\n"
            "D-4 may keep one short sharpness session plus one freshness session.\n"
            "D-3 defaults to freshness; only allow one low-noise power or sharpness touch if fatigue is not high, there is no heavy-spar spillover flag, and no conflicting hard-dose flag is active.\n"
            "D-2 is one short neural primer or technical touch only.\n"
            "Preferred headings: Sharpness Session, Technical Touch, Low-Noise Power, Freshness Session, Rhythm Day, Primer.\n"
            "Avoid headings such as Strength Block, Conditioning Stressor, Glycolytic Session, Support Strength, Secondary Strength.\n"
            "Cap every session at 4 blocks.\n"
            "Keep output concise. No weekly frequency reasoning.\n"
            "No 'program block' framing. No phase-explanation dump. No hard sparring.\n\n"
            + countdown_contract
        )
    if payload_mode == "late_fight_week_payload":
        return (
            "LATE FIGHT MODE — SHARPNESS WEEK (D-7)\n"
            "This is the final compressed week. Use sharpness-first weekly framing.\n"
            "Cap meaningful stress exposures at 2 total and cap each session at 5 blocks.\n"
            "At most 1 main neural or power touch. At most 1 fight-rhythm touch.\n"
            "Cap hard sparring to 1 declared day; convert any extras to technical rhythm.\n"
            "Preferred headings: Main Sharpness Day, Power Touch, Neural Touch, Technical Rhythm, Freshness Session, Mobility / Reset.\n"
            "Avoid headings such as Primary Strength, Secondary Strength, Anchor Day, Conditioning Block, Development Block, Support Strength.\n"
            "Forbid broad development language and multiple non-sparring stressors.\n"
            "Keep output concise, fresh, and low-noise.\n\n"
            + countdown_contract
        )
    if payload_mode == "late_fight_transition_payload":
        return (
            "LATE FIGHT MODE — SHARPNESS & FRESHNESS WINDOW (D-6 to D-5)\n"
            "This is the transition taper window. Do NOT use normal camp-week framing.\n"
            "Do NOT generate hard sparring under any circumstances.\n"
            "All declared hard sparring days convert to technical rhythm only.\n"
            "If this is an insert, max 2 coach-prescribed insert sessions: one technical rhythm or power touch + one freshness session.\n"
            "Cap meaningful stress exposures at 1 and cap each session at 4 blocks.\n"
            "No primary strength, no anchor day, no conditioning block, and no glycolytic work.\n"
            "No development language, volume-build language, or program-block framing.\n"
            "Preferred headings: Sharpness, Power Touch, Neural Touch, Technical Rhythm, Recovery / Freshness, Mobility / Reset.\n"
            "Present session-by-session, not as a weekly build.\n"
            "Keep output minimal and focused on freshness and fight readiness.\n"
            "If this is an S&C insert rather than the full boxing week, title it explicitly as an insert for the countdown window.\n\n"
            + countdown_contract
        )
    return ""
