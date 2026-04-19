from __future__ import annotations
from .normalization import clean_list, dedupe_preserve_order, ordered_weekdays as _ordered_weekdays

from itertools import combinations, permutations
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

_LATE_FIGHT_WINDOW_BOUNDS = {
    "pre_fight_compressed_payload": (8, 13),
    "late_fight_week_payload": (7, 7),
    "late_fight_transition_payload": (5, 6),
    "late_fight_session_payload": (2, 4),
    "pre_fight_day_payload": (1, 1),
    "fight_day_protocol_payload": (0, 0),
}

_LATE_FIGHT_ROLE_COST_CLASS = {
    "hard_sparring_day": "high",
    "strength_touch_day": "medium",
    "neural_primer_day": "medium",
    "alactic_sharpness_day": "medium",
    "light_fight_pace_touch_day": "medium",
    "technical_touch_day": "low",
    "fight_week_freshness_day": "low",
}

_LATE_FIGHT_ROLE_STRESS_CLASS = {
    "hard_sparring_day": "meaningful_stress",
    "strength_touch_day": "meaningful_stress",
    "neural_primer_day": "meaningful_stress",
    "alactic_sharpness_day": "meaningful_stress",
    "light_fight_pace_touch_day": "meaningful_stress",
    "technical_touch_day": "support",
    "fight_week_freshness_day": "support",
}


def _coerce_days(days_until_fight: Any, default: int | None = None) -> int | None:
    """Coerce days_until_fight to int, returning *default* on failure.

    Centralises the 19 scattered try/except (TypeError, ValueError) blocks
    that previously appeared across this module. Every function that needs a
    numeric days value calls this once at the top instead of repeating the
    same three-line pattern inline.
    """
    try:
        return int(days_until_fight)
    except (TypeError, ValueError):
        return default




def _declared_hard_spar_cap(days_until_fight: Any) -> int | None:
    days = _coerce_days(days_until_fight)
    if days is None:
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
        days = _coerce_days(days_until_fight)
        if days is None:
            return []
        return [
            {"weekday": weekday, "countdown_label": None, "offset": days}
            for weekday in ordered_declared
        ]
    days = _coerce_days(days_until_fight)
    if days is None:
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
    days = _coerce_days(days_until_fight)
    if days is None:
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
    days = _coerce_days(days_until_fight)
    if days is None:
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
    """
    Map each countdown label (D-0, D-1, … D-N) to its real weekday name.

    D-0 is the fight day. Every earlier countdown label is projected backwards
    from that anchor. Do not cap this at 7 days — compressed late-fight windows
    can run out to D-13 and still need true weekday mapping.
    """
    fight_weekday = _fight_weekday_from_context(plan_creation_weekday, days_until_fight)
    if fight_weekday is None:
        return {}

    days = _coerce_days(days_until_fight)
    if days is None:
        return {}

    if days < 0:
        return {}

    fight_index = _WEEKDAY_ORDER[fight_weekday]
    countdown_map: dict[str, str] = {}
    for offset in range(days + 1):
        label = f"D-{offset}"
        weekday_index = (fight_index - offset) % 7
        countdown_map[label] = _WEEKDAY_NAMES[weekday_index]

    return countdown_map


def _countdown_display_label(label: str, weekday: str | None) -> str:
    """
    Render countdown labels in athlete-facing form:
    D-8 (Sunday), D-1 (Sunday), etc.
    """
    if not weekday:
        return label
    return f"{label} ({str(weekday).strip().title()})"


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


def _late_fight_legal_offsets(days_until_fight: Any) -> list[int]:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return []
    if days < 0:
        return []
    if days == 0:
        return [0]
    return list(range(min(days, 13), 0, -1))


def _late_fight_legal_countdown_labels(days_until_fight: Any) -> list[str]:
    return [f"D-{offset}" for offset in _late_fight_legal_offsets(days_until_fight)]


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
    return {flag.strip().lower() for flag in clean_list(athlete_model.get("readiness_flags", [])) if flag.strip()}


def _planned_sessions_per_week(athlete_model: dict[str, Any]) -> int:
    for key in ("weekly_training_frequency", "training_frequency", "weekly_sessions", "planned_sessions_per_week"):
        value = athlete_model.get(key)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    available_days = len(clean_list(athlete_model.get("training_days", [])))
    if available_days <= 0:
        return 0
    if available_days <= 5:
        return available_days
    # Availability can be broader than true intent ("I *can* train daily" is
    # not always "I *plan* to train daily").  When explicit frequency is
    # missing, use a conservative camp default rather than overestimating.
    return 5


def _weight_cut_is_extreme(athlete_model: dict[str, Any], flags: set[str]) -> bool:
    if "aggressive_weight_cut" in flags or "extreme_weight_cut" in flags:
        return True
    risk = bool(athlete_model.get("weight_cut_risk"))
    try:
        pct = float(athlete_model.get("weight_cut_pct") or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    return risk and pct >= 5.0


def _suppress_standalone_glycolytic(active_hard_spar_days: list[str], athlete_model: dict[str, Any]) -> bool:
    if len(active_hard_spar_days) >= 2:
        return True
    fatigue = _normalized_fatigue(athlete_model)
    if fatigue == "high":
        return True
    flags = _readiness_flags(athlete_model)
    extreme_cut = _weight_cut_is_extreme(athlete_model, flags)
    if extreme_cut:
        return True
    if "injury_management" in flags and fatigue == "moderate":
        sessions_per_week = _planned_sessions_per_week(athlete_model)
        if sessions_per_week <= 3:
            return True
    return False



def _d3_alactic_suppression_reasons(athlete_model: dict[str, Any], days_until_fight: Any) -> list[str]:
    days = _coerce_days(days_until_fight)
    if days is None:
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
    days = _coerce_days(days_until_fight)
    if days is None:
        return False
    if days >= 4:
        return True
    if days != 3:
        return False
    return not _d3_alactic_suppression_reasons(athlete_model, days_until_fight)


def _late_fight_max_meaningful_stress_exposures(days_until_fight: Any) -> int | None:
    days = _coerce_days(days_until_fight)
    if days is None:
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
    days = _coerce_days(days_until_fight)
    if days is None:
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


def _late_fight_max_support_roles(days_until_fight: Any) -> int | None:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return None
    if 8 <= days <= 13:
        return 2
    if 3 <= days <= 7:
        return 1
    if 1 <= days <= 2:
        return 0
    if days == 0:
        return 0
    return None


def _late_fight_cost_class(role_key: str) -> str:
    return _LATE_FIGHT_ROLE_COST_CLASS.get(role_key, "low")


def _late_fight_stress_class(role_key: str) -> str:
    return _LATE_FIGHT_ROLE_STRESS_CLASS.get(role_key, "support")


def _late_fight_countdown_context(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any]:
    plan_creation_weekday = athlete_model.get("plan_creation_weekday")
    available_days = clean_list(athlete_model.get("training_days", []))
    countdown_map = _countdown_weekday_map(plan_creation_weekday, days_until_fight)
    resolved_map = _resolve_countdown_weekday_with_availability(countdown_map, available_days)
    legal_countdown_labels = _late_fight_legal_countdown_labels(days_until_fight)
    legal_weekdays = [
        str(resolved_map.get(label) or countdown_map.get(label) or "").strip().lower()
        for label in legal_countdown_labels
        if str(resolved_map.get(label) or countdown_map.get(label) or "").strip()
    ]
    availability_adjustments = [
        {
            "countdown_label": label,
            "raw_weekday": countdown_map.get(label),
            "resolved_weekday": resolved_map.get(label),
        }
        for label in legal_countdown_labels
        if countdown_map.get(label) and resolved_map.get(label) and countdown_map.get(label) != resolved_map.get(label)
    ]
    return {
        "countdown_weekday_map": resolved_map,
        "raw_countdown_weekday_map": countdown_map,
        "legal_countdown_labels": legal_countdown_labels,
        "legal_weekdays": legal_weekdays,
        "availability_adjustments": availability_adjustments,
        "available_days": available_days,
    }


def _late_fight_permission_policy(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any]:
    mode = _days_out_payload_mode(days_until_fight)
    countdown_context = _late_fight_countdown_context(days_until_fight, athlete_model)
    plan_weekday = athlete_model.get("plan_creation_weekday")
    declared_hard_days = _filter_past_weekdays(
        _ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))),
        plan_weekday,
        days_until_fight,
    )
    classified_hard_days = _classify_declared_hard_days_for_late_window(
        plan_creation_weekday=plan_weekday,
        days_until_fight=days_until_fight,
        declared_weekdays=declared_hard_days,
    )
    hard_allowed_instances = [
        entry
        for entry in classified_hard_days
        if entry.get("status") in {"hard_allowed", "hard_allowed_but_final_window"}
    ]
    preserved_hard_instances = _select_capped_declared_hard_day_instances(
        hard_allowed_instances,
        _declared_hard_spar_cap(days_until_fight),
        protected_day=_protected_collision_owner_day(athlete_model),
    )
    days = _coerce_days(days_until_fight)
    if mode == "pre_fight_compressed_payload" and days == 8 and len(preserved_hard_instances) < 2:
        fallback_instance = next(
            (
                entry
                for entry in classified_hard_days
                if entry.get("status") == "downgrade"
                and str(entry.get("weekday") or "").strip()
                and entry not in preserved_hard_instances
            ),
            None,
        )
        if fallback_instance is not None:
            preserved_hard_instances = preserved_hard_instances + [fallback_instance]
    preserved_hard_days = dedupe_preserve_order(
        [
            str(entry.get("weekday") or "").strip().lower()
            for entry in preserved_hard_instances
            if str(entry.get("weekday") or "").strip()
        ]
    )
    downgraded_hard_days = dedupe_preserve_order(
        [
            str(day).strip().lower()
            for day in declared_hard_days
            if str(day).strip().lower() not in preserved_hard_days
        ]
    )

    allowed_role_keys: list[str] = []
    if mode == "pre_fight_compressed_payload":
        allowed_role_keys = ["hard_sparring_day", "strength_touch_day", "light_fight_pace_touch_day", "technical_touch_day", "fight_week_freshness_day"]
    elif mode == "late_fight_week_payload":
        allowed_role_keys = ["hard_sparring_day", "neural_primer_day", "alactic_sharpness_day", "technical_touch_day", "fight_week_freshness_day"]
    elif mode == "late_fight_transition_payload":
        allowed_role_keys = ["alactic_sharpness_day", "technical_touch_day", "fight_week_freshness_day"]
    elif mode == "late_fight_session_payload":
        allowed_role_keys = ["neural_primer_day", "alactic_sharpness_day", "technical_touch_day", "fight_week_freshness_day"]
    elif mode == "pre_fight_day_payload":
        allowed_role_keys = ["neural_primer_day", "technical_touch_day"]

    declared_hard_day_actions = [
        {
            "day": str(entry.get("weekday") or "").strip().lower(),
            "outcome": "hard_sparring_day",
            "locked": True,
            "countdown_label": entry.get("countdown_label"),
            "countdown_offset": entry.get("offset"),
        }
        for entry in preserved_hard_instances
        if str(entry.get("weekday") or "").strip()
    ] + [
        {
            "day": day,
            "outcome": "technical_touch_day",
            "locked": False,
            "downgraded_from_role_key": "hard_sparring_day",
        }
        for day in downgraded_hard_days
    ]

    return {
        "mode": mode,
        "legal_countdown_labels": list(countdown_context.get("legal_countdown_labels", [])),
        "countdown_weekday_map": dict(countdown_context.get("countdown_weekday_map", {})),
        "raw_countdown_weekday_map": dict(countdown_context.get("raw_countdown_weekday_map", {})),
        "legal_weekdays": list(countdown_context.get("legal_weekdays", [])),
        "availability_adjustments": list(countdown_context.get("availability_adjustments", [])),
        "declared_hard_day_actions": declared_hard_day_actions,
        "preserved_hard_days": preserved_hard_days,
        "downgraded_hard_days": downgraded_hard_days,
        "allowed_role_keys": dedupe_preserve_order(allowed_role_keys),
    }


def _late_fight_role_budget(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": _days_out_payload_mode(days_until_fight),
        "max_active_roles": _late_fight_max_active_roles(days_until_fight),
        "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
        "max_support_roles": _late_fight_max_support_roles(days_until_fight),
        "legal_countdown_labels": _late_fight_legal_countdown_labels(days_until_fight),
    }


def _late_fight_forbidden_blocks(days_until_fight: Any) -> list[str]:
    days = _coerce_days(days_until_fight)
    if days is None:
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
    days = _coerce_days(days_until_fight)
    if days is None:
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
    days = _coerce_days(days_until_fight)
    if days is None:
        return "camp_payload"
    if days < 0:
        return "camp_payload"
    return _PAYLOAD_MODE_MAP.get(days, "camp_payload")


def _uses_late_fight_stage2_payload(days_until_fight: Any) -> bool:
    return _days_out_payload_mode(days_until_fight) != "camp_payload"


def _days_out_bucket(days_until_fight: Any) -> str:
    days = _coerce_days(days_until_fight)
    if days is None:
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
        days = _coerce_days(days_until_fight, default=3)
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
        days = _coerce_days(days_until_fight, default=3)
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
                "Countdown insert or unified countdown schedule only — never a Monday-Sunday week.",
                "Render only app-owned roles as sessions. Boxing schedule is context only.",
                "5 blocks per session max. 3 meaningful stress exposures max.",
            ],
            "preferred_terms": ["compressed week", "technical rhythm", "sharpness", "strength touch", "freshness", "mobility / reset"],
            "forbidden_terms": ["development block", "conditioning build", "secondary anchor", "extra density push", "d-0 training"],
        }
    if mode == "late_fight_week_payload":
        return {
            "mode": mode,
            "framing": "compressed_week",
            "rules": [
                "Sharpness-week framing. D-N first, weekday second.",
                "5 blocks per session max. 1 hard sparring day max — extras become technical rhythm.",
            ],
            "preferred_terms": ["sharpness week", "power touch", "neural touch", "technical rhythm", "freshness session", "mobility / reset"],
            "forbidden_terms": ["primary strength", "secondary strength", "anchor day", "conditioning block", "development block"],
        }
    if mode == "late_fight_transition_payload":
        return {
            "mode": mode,
            "framing": "session_by_session",
            "rules": [
                "Session-by-session only. No hard sparring — spar days become technical rhythm.",
                "Insert: 2 sessions max. 4 blocks per session max.",
            ],
            "preferred_terms": ["sharpness", "power touch", "technical rhythm", "recovery", "freshness", "mobility / reset"],
            "forbidden_terms": ["primary strength", "anchor day", "conditioning block", "developmental work", "volume build"],
        }
    if mode == "late_fight_session_payload":
        return {
            "mode": mode,
            "framing": "session_by_session",
            "rules": [
                "Session-by-session only. No program block, no phase-explanation dump.",
                "4 blocks per session max. Tight and action-oriented.",
            ],
            "preferred_terms": ["sharpness session", "technical touch", "low-noise power", "freshness session", "rhythm day", "primer"],
            "forbidden_terms": ["strength block", "conditioning stressor", "glycolytic session", "support strength", "weekly architecture"],
        }
    if mode == "pre_fight_day_payload":
        return {
            "mode": mode,
            "framing": "primer_only",
            "rules": [
                "Primer-only output. 4 blocks max. Under 300 words.",
            ],
            "preferred_terms": ["neural primer", "technical touch", "sharpness", "activation", "reset", "rhythm"],
            "forbidden_terms": ["anchor", "strength", "conditioning", "fight-pace density", "block", "glycolytic", "contrast"],
        }
    return {
        "mode": mode,
        "framing": "fight_day_protocol",
        "rules": [
            "Fight-day content only. Activation sequence 3 blocks max.",
        ],
        "preferred_terms": ["activation", "warm-up", "cue", "fuel", "walk-through", "recover"],
        "forbidden_terms": ["anchor", "strength", "conditioning", "fight-pace density", "weekly role map", "rehab stack"],
    }

def _days_out_payload_block(days_until_fight: Any, athlete_model: dict) -> dict:
    mode = _days_out_payload_mode(days_until_fight)
    permissions = _late_fight_permissions(days_until_fight, athlete_model)
    permission_policy = _late_fight_permission_policy(days_until_fight, athlete_model)
    role_budget = _late_fight_role_budget(days_until_fight, athlete_model)
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
        "permission_policy": permission_policy,
        "role_budget": role_budget,
        "allowed_session_types": allowed_session_types,
        "forbidden_session_types": forbidden_session_types,
        "rendering_rules": rendering_rules,
        "forbidden_blocks": _late_fight_forbidden_blocks(days_until_fight),
        "max_blocks_per_session": max_blocks,
    }


def _late_fight_role_entry(
    *,
    session_index: int | None = None,
    category: str,
    role_key: str,
    selection_rule: str,
    preferred_pool: str,
    placement_rule: str,
    preferred_system: str | None = None,
    selection_priority: int = 0,
    required: bool = False,
    locked_day: str | None = None,
    preferred_day: str | None = None,
    placement_source: str = "allocator",
    legal_countdown_labels: list[str] | None = None,
    downgraded_from_role_key: str | None = None,
    declared_day_order: int | None = None,
    day_assignment_reason: str | None = None,
    coach_notes: list[str] | None = None,
) -> dict[str, Any]:
    entry = {
        "category": category,
        "role_key": role_key,
        "preferred_pool": preferred_pool,
        "selection_rule": selection_rule,
        "anchor": _role_anchor(role_key),
        "placement_rule": placement_rule,
        "cost_class": _late_fight_cost_class(role_key),
        "stress_class": _late_fight_stress_class(role_key),
        "placement_source": placement_source,
        "legal_countdown_labels": list(legal_countdown_labels or []),
        "governance": {"late_fight_payload": True},
        "_selection_priority": selection_priority,
        "_required": required,
    }
    if session_index is not None:
        entry["session_index"] = session_index
    if preferred_system:
        entry["preferred_system"] = preferred_system
    if locked_day:
        entry["locked_day"] = locked_day
    if preferred_day:
        entry["_preferred_day"] = preferred_day
    if downgraded_from_role_key:
        entry["downgraded_from_role_key"] = downgraded_from_role_key
    if declared_day_order is not None:
        entry["_declared_day_order"] = declared_day_order
    if day_assignment_reason:
        entry["day_assignment_reason"] = day_assignment_reason
    if coach_notes:
        entry["coach_notes"] = list(coach_notes)
    return entry


def _late_fight_session_roles(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    mode = _days_out_payload_mode(days_until_fight)
    plan_weekday = athlete_model.get("plan_creation_weekday")
    declared_hard_days = _filter_past_weekdays(
        _ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))),
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
        days = _coerce_days(days_until_fight, default=3)
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
    """
    Build the ordered session sequence for the late-fight window.

    Delegates placement to the dedicated placement engine (Layer 3).  The
    budget layer (_late_fight_session_roles) already decided *what* roles exist
    and *how many*.  This function's only job is to coordinate the inputs and
    call the engine which decides *where* each role goes.
    """
    from fightcamp.late_fight_placement import place_roles_in_countdown

    plan_creation_weekday = athlete_model.get("plan_creation_weekday")
    available_days = clean_list(athlete_model.get("training_days", []))
    countdown_map = _countdown_weekday_map(plan_creation_weekday, days_until_fight)
    resolved_map = _resolve_countdown_weekday_with_availability(countdown_map, available_days)
    roles = _late_fight_session_roles(days_until_fight, athlete_model)

    days = _coerce_days(days_until_fight)
    if days is None:
        return []

    if days < 0:
        return []

    fatigue = athlete_model.get("fatigue_level") or athlete_model.get("fatigue")
    readiness_flags = clean_list(athlete_model.get("readiness_flags", []))
    declared_hard_offsets = [
        int(role.get("countdown_offset"))
        for role in roles
        if (
            str(role.get("role_key") or "").strip().lower() == "hard_sparring_day"
            and role.get("declared_day_locked") is True
            and isinstance(role.get("countdown_offset"), int)
            and int(role.get("countdown_offset")) > 0
        )
    ]
    declared_technical_offsets = [
        int(entry.get("offset"))
        for entry in _future_declared_weekdays_with_countdown(
            plan_creation_weekday=plan_creation_weekday,
            days_until_fight=days,
            declared_weekdays=_ordered_weekdays(clean_list(athlete_model.get("technical_skill_days", []))),
        )
        if isinstance(entry.get("offset"), int) and int(entry.get("offset")) > 0
    ]
    placement_context = {
        "declared_hard_spar_offsets": declared_hard_offsets,
        "declared_technical_offsets": declared_technical_offsets,
        "today_label": f"D-{days}",
        "today_offset": days,
        "plan_creation_offset": days,
        "fatigue": str(fatigue or "").strip().lower(),
        "readiness_flags": readiness_flags,
    }

    return place_roles_in_countdown(
        roles=roles,
        days_until_fight=days,
        countdown_weekday_map=resolved_map,
        placement_context=placement_context,
    )


def _is_app_owned_visible_role(role_key: Any) -> bool:
    """
    Return whether a role should be rendered as an app-owned visible session.

    Declared boxing load (for example hard sparring) must stay in the
    placement map as context, but should not be rendered as coach-prescribed
    S&C session ownership in insert-style countdown outputs.
    """
    return str(role_key or "").strip().lower() not in {"hard_sparring_day"}


def _visible_insert_session_sequence(session_sequence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter post-placement sessions to the app-owned roles only."""
    return [
        session
        for session in session_sequence
        if _is_app_owned_visible_role(session.get("role_key"))
    ]


def _title_case_days(days: list[str]) -> list[str]:
    return [str(day).strip().title() for day in days if str(day).strip()]


def _join_day_list(days: list[str]) -> str:
    cleaned = [day for day in days if day]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _hard_sparring_window_context(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any] | None:
    """Return structured surviving/downgraded hard-sparring context plus one concise line."""
    plan_weekday = athlete_model.get("plan_creation_weekday")
    declared_hard_days = _filter_past_weekdays(
        _ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))),
        plan_weekday,
        days_until_fight,
    )
    if not declared_hard_days:
        return None

    days = _coerce_days(days_until_fight)
    if days is None:
        return None

    surviving_instances: list[dict[str, Any]] = []
    downgraded_days: list[str] = []

    if days <= 6:
        downgraded_days = [day.lower() for day in declared_hard_days]
    else:
        classified = _classify_declared_hard_days_for_late_window(
            plan_creation_weekday=plan_weekday,
            days_until_fight=days,
            declared_weekdays=declared_hard_days,
        )
        hard_allowed = [
            entry for entry in classified
            if entry.get("status") in {"hard_allowed", "hard_allowed_but_final_window"}
        ]
        surviving_instances = _select_capped_declared_hard_day_instances(
            hard_allowed,
            _declared_hard_spar_cap(days),
            protected_day=_protected_collision_owner_day(athlete_model),
        )
        surviving_set = {str(entry.get("weekday") or "").strip().lower() for entry in surviving_instances}
        downgraded_days = [day.lower() for day in declared_hard_days if day.lower() not in surviving_set]

    surviving_days = dedupe_preserve_order(
        [
            str(entry.get("weekday") or "").strip().lower()
            for entry in surviving_instances
            if str(entry.get("weekday") or "").strip()
        ]
    )
    surviving_display = _join_day_list(_title_case_days(surviving_days))
    downgraded_display = _join_day_list(_title_case_days(downgraded_days))

    downgraded_verb = "are" if len(downgraded_days) != 1 else "is"

    if surviving_display and downgraded_display:
        line = f"Hard sparring this window: {surviving_display}. {downgraded_display} {downgraded_verb} technical rhythm only."
    elif surviving_display:
        line = f"Hard sparring this window: {surviving_display}."
    else:
        line = f"Hard sparring this window: none. {downgraded_display} {downgraded_verb} technical rhythm only."

    return {
        "surviving_hard_spar_days": surviving_days,
        "downgraded_declared_spar_days": downgraded_days,
        "hard_sparring_context_line": line,
    }


def _weekday_distance(day_a: str | None, day_b: str | None) -> int:
    index_a = _WEEKDAY_ORDER.get(str(day_a or "").strip().lower())
    index_b = _WEEKDAY_ORDER.get(str(day_b or "").strip().lower())
    if index_a is None or index_b is None:
        return 7
    return abs(index_a - index_b)


def _late_fight_candidate_roles(
    days_until_fight: Any,
    athlete_model: dict[str, Any],
    permission_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    mode = permission_policy.get("mode")
    legal_countdown_labels = permission_policy.get("legal_countdown_labels", [])
    declared_day_order = {
        str(item.get("day") or "").strip(): index
        for index, item in enumerate(permission_policy.get("declared_hard_day_actions", []), start=1)
        if str(item.get("day") or "").strip()
    }
    candidates: list[dict[str, Any]] = []

    for item in permission_policy.get("declared_hard_day_actions", []):
        day = str(item.get("day") or "").strip()
        outcome = str(item.get("outcome") or "").strip()
        day_order = declared_day_order.get(day)
        if outcome == "hard_sparring_day":
            candidates.append(
                _late_fight_role_entry(
                    category="sparring",
                    role_key="hard_sparring_day",
                    preferred_pool="declared_hard_sparring_days",
                    selection_rule="Keep declared hard sparring only when it still lives inside the active legal countdown slice.",
                    placement_rule="Keep this declared hard sparring slot fixed on the athlete's stated day inside the active countdown window.",
                    selection_priority=120,
                    required=True,
                    locked_day=day,
                    preferred_day=day,
                    placement_source="declared_hard_day_lock",
                    legal_countdown_labels=legal_countdown_labels,
                    declared_day_order=day_order,
                    day_assignment_reason="Declared hard sparring day stays fixed inside the active late-fight window.",
                )
            )
        elif outcome == "technical_touch_day":
            candidates.append(
                _late_fight_role_entry(
                    category="technical",
                    role_key="technical_touch_day",
                    preferred_pool="declared_technical_touch_days",
                    selection_rule="Downgraded declared hard boxing days become technical timing touches only.",
                    placement_rule="Keep this on the declared boxing day or nearest legal countdown day without turning it into conditioning or sparring.",
                    selection_priority=-10,
                    preferred_day=day,
                    placement_source="downgraded_declared_hard_day",
                    legal_countdown_labels=legal_countdown_labels,
                    downgraded_from_role_key="hard_sparring_day",
                    declared_day_order=day_order,
                )
            )

    preserved_hard_days = permission_policy.get("preserved_hard_days", [])
    has_downgraded_hard_days = bool(permission_policy.get("downgraded_hard_days", []))

    if mode == "pre_fight_compressed_payload":
        strength_selection_rule = "Use one meaningful strength or power touch only."
        strength_placement_rule = "Keep this away from the main collision load and do not let it become a second anchor."
        if len(preserved_hard_days) >= 2:
            strength_selection_rule = "Use one smaller strength or power touch only when two hard sparring exposures already own the window."
            strength_placement_rule = "Keep this clearly smaller than a full neural anchor and away from the heavier collision day."
        candidates.append(
            _late_fight_role_entry(
                category="strength",
                role_key="strength_touch_day",
                preferred_pool="strength_slots",
                selection_rule=strength_selection_rule,
                placement_rule=strength_placement_rule,
                selection_priority=108,
                required=True,
                legal_countdown_labels=legal_countdown_labels,
            )
        )
        if not _suppress_standalone_glycolytic(preserved_hard_days, athlete_model):
            candidates.append(
                _late_fight_role_entry(
                    category="conditioning",
                    role_key="light_fight_pace_touch_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="glycolytic",
                    selection_rule="Allow at most one light fight-rhythm touch only when sparring does not already own the window.",
                    placement_rule="Keep this light, never describe it as a conditioning build, and never place it between two hard sparring collisions.",
                    selection_priority=96 if has_downgraded_hard_days else 100,
                    legal_countdown_labels=legal_countdown_labels,
                )
            )
        candidates.append(
            _late_fight_role_entry(
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Require one freshness, mobility, and reset session in this compressed pre-fight week.",
                placement_rule="Keep this as the lowest-load day and preserve readiness over extra development.",
                selection_priority=104,
                required=True,
                legal_countdown_labels=legal_countdown_labels,
            )
        )
        return candidates

    if mode == "late_fight_week_payload":
        candidates.append(
            _late_fight_role_entry(
                category="strength",
                role_key="neural_primer_day",
                preferred_pool="strength_slots",
                selection_rule="Use one sharp, low-volume neural strength or power exposure only.",
                placement_rule="Keep this away from the main collision load and keep the dose small.",
                selection_priority=110,
                required=True,
                legal_countdown_labels=legal_countdown_labels,
            )
        )
        if not preserved_hard_days:
            candidates.append(
                _late_fight_role_entry(
                    category="conditioning",
                    role_key="alactic_sharpness_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="alactic",
                    selection_rule="Use one alactic sharpness exposure instead of a normal conditioning build.",
                    placement_rule="Keep this brief and crisp; do not turn it into density work.",
                    selection_priority=106,
                    required=True,
                    legal_countdown_labels=legal_countdown_labels,
                )
            )
        candidates.append(
            _late_fight_role_entry(
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Use freshness, mobility, and reset work to preserve readiness.",
                placement_rule="Keep this as the lowest-load day of the week.",
                selection_priority=104,
                required=True,
                legal_countdown_labels=legal_countdown_labels,
            )
        )
        return candidates

    if mode == "late_fight_transition_payload":
        coach_notes: list[str] = []
        if permission_policy.get("downgraded_hard_days"):
            coach_notes.append(
                f"Hard sparring overridden to technical/rhythm only - {_days_out_bucket(days_until_fight)} is too close to fight day."
            )
        candidates.extend(
            [
                _late_fight_role_entry(
                    category="conditioning",
                    role_key="alactic_sharpness_day",
                    preferred_pool="declared_technical_skill_days_or_conditioning_slots",
                    preferred_system="alactic",
                    selection_rule="One short alactic sharpness touch only. Keep it tiny, crisp, and non-fatiguing.",
                    placement_rule="Keep this brief and very low volume. Do not turn it into density work.",
                    selection_priority=106,
                    required=True,
                    legal_countdown_labels=legal_countdown_labels,
                    coach_notes=coach_notes,
                ),
                _late_fight_role_entry(
                    category="recovery",
                    role_key="fight_week_freshness_day",
                    preferred_pool="rehab_slots_or_recovery_only",
                    selection_rule="Mobility, breathing, and tissue recovery only.",
                    placement_rule="Lowest-load session. Prioritise readiness over any training stimulus.",
                    selection_priority=104,
                    required=True,
                    legal_countdown_labels=legal_countdown_labels,
                    coach_notes=coach_notes,
                ),
            ]
        )
        return candidates

    if mode == "late_fight_session_payload":
        try:
            days = int(days_until_fight)
        except (TypeError, ValueError):
            days = 3
        if days == 2:
            candidates.append(
                _late_fight_role_entry(
                    category="strength",
                    role_key="neural_primer_day",
                    preferred_pool="strength_slots",
                    selection_rule="One short neural sharpness touch only.",
                    placement_rule="Keep it crisp, low-volume, and fully non-fatiguing.",
                    selection_priority=110,
                    required=True,
                    legal_countdown_labels=legal_countdown_labels,
                )
            )
            return candidates
        if days >= 4 or _allow_late_fight_alactic_sharpness(athlete_model, days_until_fight):
            candidates.append(
                _late_fight_role_entry(
                    category="conditioning",
                    role_key="alactic_sharpness_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="alactic",
                    selection_rule="Use one short alactic sharpness touch only if it keeps the athlete fresher, not flatter.",
                    placement_rule="Keep this brief and low-noise.",
                    selection_priority=106,
                    required=True,
                    legal_countdown_labels=legal_countdown_labels,
                )
            )
        candidates.append(
            _late_fight_role_entry(
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Use recovery, breathing, and mobility to preserve rhythm and readiness.",
                placement_rule="Keep this as the lowest-load session in the window.",
                selection_priority=104,
                required=True,
                legal_countdown_labels=legal_countdown_labels,
            )
        )
        return candidates

    if mode == "pre_fight_day_payload":
        candidates.append(
            _late_fight_role_entry(
                category="strength",
                role_key="neural_primer_day",
                preferred_pool="strength_slots",
                selection_rule="Render at most one tiny neural primer; do not build a normal training week.",
                placement_rule="Keep it short, clean, and immediately supportive of tomorrow's performance.",
                selection_priority=110,
                required=True,
                legal_countdown_labels=legal_countdown_labels,
            )
        )
    return candidates


def _late_fight_meaningful_stress_count(roles: list[dict[str, Any]]) -> int:
    return sum(1 for role in roles if role.get("stress_class") == "meaningful_stress")


def _late_fight_support_role_count(roles: list[dict[str, Any]]) -> int:
    return sum(1 for role in roles if role.get("stress_class") == "support")


def _late_fight_locked_label(role: dict[str, Any], label_to_weekday: dict[str, str]) -> str | None:
    locked_day = str(role.get("locked_day") or "").strip().lower()
    if not locked_day:
        return None
    for label, weekday in label_to_weekday.items():
        if str(weekday or "").strip().lower() == locked_day:
            return label
    return None


def _late_fight_assignment_reason(role: dict[str, Any]) -> str:
    role_key = str(role.get("role_key") or "")
    if role_key == "hard_sparring_day":
        return "Declared hard sparring day stays fixed inside the active late-fight window."
    if role_key == "technical_touch_day":
        return "Downgraded declared hard day is kept as a low-cost technical touch on the best legal countdown day."
    if role_key == "fight_week_freshness_day":
        return "Allocator kept freshness latest inside the active legal countdown window."
    return "Allocator placed higher-cost work earlier while protecting spacing and taper shape."


def _late_fight_public_role(role: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in role.items()
        if not key.startswith("_")
    }


def _late_fight_assignment_score(
    assigned_roles: list[dict[str, Any]],
    legal_countdown_labels: list[str],
    label_to_weekday: dict[str, str],
) -> int:
    if not assigned_roles:
        return 0
    offsets = [
        _countdown_offset(label)
        for label in legal_countdown_labels
        if _countdown_offset(label) is not None
    ]
    if not offsets:
        return 0
    min_offset = min(offsets)
    score = 0
    ordered_roles = sorted(
        assigned_roles,
        key=lambda role: _countdown_offset(role.get("scheduled_countdown_label", "")) or -1,
        reverse=True,
    )

    for role in ordered_roles:
        label = str(role.get("scheduled_countdown_label") or "")
        offset = _countdown_offset(label) or 0
        score += int(role.get("_selection_priority") or 0) * 1000
        cost_class = str(role.get("cost_class") or "")
        if cost_class == "high":
            score += offset * 40
        elif cost_class == "medium":
            score += offset * 20
        elif role.get("role_key") == "technical_touch_day":
            score += offset * 8

        if role.get("role_key") == "fight_week_freshness_day":
            if offset == min_offset:
                score += 300
            else:
                score -= (offset - min_offset) * 120

        if role.get("role_key") == "technical_touch_day":
            preferred_day = str(role.get("_preferred_day") or "").strip().lower()
            actual_day = str(label_to_weekday.get(label) or "").strip().lower()
            distance = _weekday_distance(actual_day, preferred_day)
            score += max(0, 120 - (distance * 35))
            if actual_day and actual_day == preferred_day:
                score += 80

    for first_role, second_role in zip(ordered_roles, ordered_roles[1:]):
        first_offset = _countdown_offset(first_role.get("scheduled_countdown_label", "")) or 0
        second_offset = _countdown_offset(second_role.get("scheduled_countdown_label", "")) or 0
        gap = first_offset - second_offset
        score += gap * 35
        if gap == 1:
            score -= 90
            if (
                first_role.get("stress_class") == "meaningful_stress"
                and second_role.get("stress_class") == "meaningful_stress"
            ):
                score -= 180
            elif (
                first_role.get("cost_class") in {"high", "medium"}
                and second_role.get("cost_class") in {"high", "medium"}
            ):
                score -= 120

    score -= sum(
        int(role.get("_declared_day_order") or 0)
        for role in ordered_roles
        if role.get("role_key") == "technical_touch_day"
    )
    return score


def _late_fight_best_assignment(
    selected_roles: list[dict[str, Any]],
    legal_countdown_labels: list[str],
    label_to_weekday: dict[str, str],
) -> tuple[int, list[dict[str, Any]]] | None:
    locked_labels: dict[int, str] = {}
    occupied_labels: set[str] = set()
    unlocked_roles: list[dict[str, Any]] = []

    for role in selected_roles:
        locked_label = _late_fight_locked_label(role, label_to_weekday)
        candidate_id = int(role.get("_candidate_id") or 0)
        if role.get("locked_day") and label_to_weekday:
            if not locked_label or locked_label in occupied_labels:
                return None
            locked_labels[candidate_id] = locked_label
            occupied_labels.add(locked_label)
        else:
            unlocked_roles.append(role)

    open_labels = [label for label in legal_countdown_labels if label not in occupied_labels]
    if len(unlocked_roles) > len(open_labels):
        return None

    best_score: int | None = None
    best_roles: list[dict[str, Any]] | None = None

    for label_perm in permutations(open_labels, len(unlocked_roles)):
        assigned_labels = dict(locked_labels)
        for index, role in enumerate(unlocked_roles):
            assigned_labels[int(role.get("_candidate_id") or 0)] = label_perm[index]

        scored_roles: list[dict[str, Any]] = []
        for role in selected_roles:
            role_copy = dict(role)
            candidate_id = int(role.get("_candidate_id") or 0)
            assigned_label = assigned_labels.get(candidate_id)
            role_copy["scheduled_countdown_label"] = assigned_label
            role_copy["countdown_label"] = assigned_label
            offset = _countdown_offset(assigned_label)
            if offset is not None:
                role_copy["countdown_offset"] = offset
            real_weekday = str(label_to_weekday.get(assigned_label) or "").strip()
            if real_weekday:
                role_copy["scheduled_day_hint"] = real_weekday
                role_copy["real_weekday"] = real_weekday
                role_copy["countdown_display_label"] = _countdown_display_label(assigned_label, real_weekday)
            elif assigned_label:
                role_copy["countdown_display_label"] = assigned_label
            if role_copy.get("locked_day"):
                role_copy["declared_day_locked"] = True
                role_copy["placement_basis"] = "locked"
            else:
                role_copy["placement_basis"] = str(role_copy.get("cost_class") or "medium")
            role_copy["day_assignment_reason"] = _late_fight_assignment_reason(role_copy)
            scored_roles.append(role_copy)

        score = _late_fight_assignment_score(scored_roles, legal_countdown_labels, label_to_weekday)
        if best_score is None or score > best_score:
            best_score = score
            best_roles = scored_roles

    if best_score is None or best_roles is None:
        return None
    return best_score, best_roles


def _late_fight_suppression_entry(role: dict[str, Any], reason: str) -> dict[str, Any]:
    entry = {
        "category": role.get("category"),
        "role_key": role.get("role_key"),
        "preferred_pool": role.get("preferred_pool"),
        "placement_source": role.get("placement_source"),
        "cost_class": role.get("cost_class"),
        "stress_class": role.get("stress_class"),
        "legal_countdown_labels": list(role.get("legal_countdown_labels") or []),
        "reasons": [reason],
    }
    if role.get("preferred_system"):
        entry["preferred_system"] = role.get("preferred_system")
    if role.get("locked_day"):
        entry["locked_day"] = role.get("locked_day")
    if role.get("downgraded_from_role_key"):
        entry["downgraded_from_role_key"] = role.get("downgraded_from_role_key")
    return entry


def _late_fight_allocation_plan(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any]:
    mode = _days_out_payload_mode(days_until_fight)
    if mode in {"camp_payload", "fight_day_protocol_payload"}:
        return {
            "mode": mode,
            "permission_policy": _late_fight_permission_policy(days_until_fight, athlete_model),
            "role_budget": _late_fight_role_budget(days_until_fight, athlete_model),
            "session_roles": [],
            "suppressed_roles": [],
            "allocator": {
                "legal_countdown_labels": _late_fight_legal_countdown_labels(days_until_fight),
                "locked_days": [],
                "blocked_days": [],
                "countdown_weekday_map": {},
                "availability_adjustments": [],
            },
        }

    permission_policy = _late_fight_permission_policy(days_until_fight, athlete_model)
    role_budget = _late_fight_role_budget(days_until_fight, athlete_model)
    candidates = _late_fight_candidate_roles(days_until_fight, athlete_model, permission_policy)
    for index, role in enumerate(candidates, start=1):
        role["_candidate_id"] = index

    legal_countdown_labels = list(permission_policy.get("legal_countdown_labels", []))
    label_to_weekday = {
        label: str(permission_policy.get("countdown_weekday_map", {}).get(label) or "").strip().lower()
        for label in legal_countdown_labels
        if str(permission_policy.get("countdown_weekday_map", {}).get(label) or "").strip()
    }

    invalid_locked_roles: list[dict[str, Any]] = []
    eligible_candidates: list[dict[str, Any]] = []
    for role in candidates:
        if role.get("locked_day") and label_to_weekday and _late_fight_locked_label(role, label_to_weekday) is None:
            invalid_locked_roles.append(
                _late_fight_suppression_entry(
                    role,
                    "No legal countdown day preserves this locked declared hard sparring day inside the active late-fight window.",
                )
            )
            continue
        eligible_candidates.append(role)

    max_active_roles = role_budget.get("max_active_roles")
    max_meaningful_stress_exposures = role_budget.get("max_meaningful_stress_exposures")
    max_support_roles = role_budget.get("max_support_roles")

    required_roles = [role for role in eligible_candidates if role.get("_required")]
    optional_roles = [role for role in eligible_candidates if not role.get("_required")]

    best_roles: list[dict[str, Any]] = []
    best_score: int | None = None
    for optional_count in range(len(optional_roles) + 1):
        for optional_subset in combinations(optional_roles, optional_count):
            selected_roles = required_roles + list(optional_subset)
            if isinstance(max_active_roles, int) and len(selected_roles) > max_active_roles:
                continue
            if isinstance(max_meaningful_stress_exposures, int) and _late_fight_meaningful_stress_count(selected_roles) > max_meaningful_stress_exposures:
                continue
            if isinstance(max_support_roles, int) and _late_fight_support_role_count(selected_roles) > max_support_roles:
                continue
            assignment = _late_fight_best_assignment(selected_roles, legal_countdown_labels, label_to_weekday)
            if assignment is None:
                continue
            score, assigned_roles = assignment
            if best_score is None or score > best_score:
                best_score = score
                best_roles = assigned_roles

    ordered_roles = sorted(
        best_roles,
        key=lambda role: _countdown_offset(role.get("scheduled_countdown_label", "")) or -1,
        reverse=True,
    )
    public_roles: list[dict[str, Any]] = []
    for session_index, role in enumerate(ordered_roles, start=1):
        role["session_index"] = session_index
        public_roles.append(_late_fight_public_role(role))

    selected_ids = {int(role.get("_candidate_id") or 0) for role in best_roles}
    suppressed_roles = list(invalid_locked_roles)
    for role in eligible_candidates:
        candidate_id = int(role.get("_candidate_id") or 0)
        if candidate_id in selected_ids:
            continue
        if role.get("stress_class") == "meaningful_stress" and isinstance(max_meaningful_stress_exposures, int):
            reason = f"Meaningful stress is capped at {max_meaningful_stress_exposures} in this window, so higher-priority stress roles kept the slot."
        elif role.get("role_key") == "technical_touch_day":
            reason = "Allocator kept higher-priority late-fight roles and taper spacing inside the active-role cap; this downgraded hard day remains advisory only in this window."
        else:
            reason = "Allocator kept a higher-priority late-fight mix inside the active-role cap and legal countdown days."
        suppressed_roles.append(_late_fight_suppression_entry(role, reason))

    return {
        "mode": mode,
        "permission_policy": permission_policy,
        "role_budget": {
            **role_budget,
            "selected_active_roles": len(public_roles),
            "selected_meaningful_stress_exposures": _late_fight_meaningful_stress_count(public_roles),
            "selected_support_roles": _late_fight_support_role_count(public_roles),
        },
        "session_roles": public_roles,
        "suppressed_roles": suppressed_roles,
        "allocator": {
            "legal_countdown_labels": legal_countdown_labels,
            "locked_days": [role.get("locked_day") for role in public_roles if role.get("locked_day")],
            "blocked_days": [],
            "countdown_weekday_map": {
                label: permission_policy.get("countdown_weekday_map", {}).get(label)
                for label in legal_countdown_labels
                if permission_policy.get("countdown_weekday_map", {}).get(label)
            },
            "availability_adjustments": list(permission_policy.get("availability_adjustments", [])),
        },
    }


def _late_fight_session_roles(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    return list(_late_fight_allocation_plan(days_until_fight, athlete_model).get("session_roles", []))


def _build_late_fight_session_sequence(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    return list(_late_fight_allocation_plan(days_until_fight, athlete_model).get("session_roles", []))


def _late_fight_stage_label(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "pre_fight_compressed_payload":
        return "Compressed Pre-Fight Week"
    if mode == "late_fight_week_payload":
        return "Sharpness Week"
    if mode == "late_fight_transition_payload":
        return "Sharpness & Freshness Window"
    if mode == "late_fight_session_payload":
        return "Sharpness Sessions"
    if mode == "pre_fight_day_payload":
        return "Primer Day"
    if mode == "fight_day_protocol_payload":
        return "Fight-Day Protocol"
    return "Camp"


def _late_fight_summary(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "pre_fight_compressed_payload":
        return (
            "Use a compressed pre-fight week. Keep no more than two hard sparring exposures, one meaningful "
            "strength touch, an optional light fight-rhythm touch only when sparring does not already own the "
            "week, and one freshness / mobility reset day."
        )
    if mode == "late_fight_week_payload":
        return "Use a compressed sharpness week. Keep one main neural or power touch, one fight-rhythm touch at most, and the rest on freshness, mobility, and reset."
    if mode == "late_fight_transition_payload":
        return "Use a transition window built around technical rhythm, a small power touch, and freshness only. No hard sparring and no camp-style headings."
    if mode == "late_fight_session_payload":
        return "Use a short sharpness-first session list. Think technical touch, low-noise power, freshness, and reset — not normal camp architecture."
    if mode == "pre_fight_day_payload":
        return "Use primer-only guidance. Keep it to neural primer, technical touch, activation, reset, and rhythm."
    if mode == "fight_day_protocol_payload":
        return "Use fight-day protocol guidance only. Activation, warm-up, cue, fuel, walk-through, and recover — no training-plan language."
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
    allocation = _late_fight_allocation_plan(days_until_fight, athlete_model)
    roles = allocation.get("session_roles", [])
    session_counts = {
        "strength": sum(1 for role in roles if role.get("category") == "strength"),
        "conditioning": sum(1 for role in roles if role.get("category") == "conditioning"),
        "recovery": sum(1 for role in roles if role.get("category") == "recovery"),
    }
    technical_count = sum(1 for role in roles if role.get("category") == "technical")
    if technical_count:
        session_counts["technical"] = technical_count
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
                "role_budget": allocation.get("role_budget", {}),
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
    allocation = _late_fight_allocation_plan(days_until_fight, athlete_model)
    mode = allocation.get("mode", _days_out_payload_mode(days_until_fight))
    roles = allocation.get("session_roles", [])
    suppressed_roles = list(allocation.get("suppressed_roles", []))
    resolved_countdown_map = dict((allocation.get("allocator", {}) or {}).get("countdown_weekday_map", {}))
    plan_weekday = athlete_model.get("plan_creation_weekday")
    if mode in {"fight_day_protocol_payload", "pre_fight_day_payload", "late_fight_session_payload", "late_fight_transition_payload"}:
        weeks: list[dict[str, Any]] = []
    else:
        filtered_training = _filter_past_weekdays(
            _ordered_weekdays(clean_list(athlete_model.get("training_days", []))),
            plan_weekday, days_until_fight,
        )
        filtered_sparring = _filter_past_weekdays(
            _ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))),
            plan_weekday, days_until_fight,
        )
        filtered_technical = _filter_past_weekdays(
            _ordered_weekdays(clean_list(athlete_model.get("technical_skill_days", []))),
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
                "effective_hard_sparring_days": [
                    role.get("scheduled_day_hint")
                    for role in roles
                    if role.get("role_key") == "hard_sparring_day" and role.get("scheduled_day_hint")
                ],
                "coach_note_flags": [_late_fight_stage_label(days_until_fight)],
                "intentional_compression": {
                    "active": True,
                    "reason_codes": [mode],
                    "reason": mode,
                    "summary": _late_fight_summary(days_until_fight),
                },
                "intentionally_unused_days": [],
                "session_roles": roles,
                "suppressed_roles": suppressed_roles + [
                    {
                        "category": "plan",
                        "role_key": "normal_stage2_payload",
                        "reasons": ["late_fight_stage2_payload: bypassed normal camp-style stage2 payload assumptions"],
                    }
                ],
                "countdown_weekday_map": resolved_countdown_map,
                "allocator": allocation.get("allocator", {}),
                "role_budget": allocation.get("role_budget", {}),
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
        "allocator": allocation.get("allocator", {}),
        "role_budget": allocation.get("role_budget", {}),
        "weeks": weeks,
    }


def _build_late_fight_plan_spec(days_until_fight: Any, athlete_model: dict) -> dict[str, Any]:
    payload_block = _days_out_payload_block(days_until_fight, athlete_model)
    allocation = _late_fight_allocation_plan(days_until_fight, athlete_model)
    roles = list(allocation.get("session_roles", []))
    session_sequence = list(roles)
    visible_session_sequence = _visible_insert_session_sequence(session_sequence)
    mode = payload_block["payload_mode"]
    max_blocks = _MAX_BLOCKS_PER_SESSION.get(mode)
    resolved_countdown_map = dict((allocation.get("allocator", {}) or {}).get("countdown_weekday_map", {}))
    spec: dict[str, Any] = {
        "payload_variant": "late_fight_stage2_payload",
        "payload_mode": mode,
        "days_out_bucket": payload_block["days_out_bucket"],
        "late_fight_window": payload_block["late_fight_window"],
        "summary": _late_fight_summary(days_until_fight),
        "session_cap": len(roles),
        "session_roles": [role.get("role_key") for role in roles],
        "session_sequence": session_sequence,
        "visible_session_cap": len(visible_session_sequence),
        "visible_session_roles": [entry.get("role_key") for entry in visible_session_sequence],
        "visible_session_sequence": visible_session_sequence,
        "allowed_session_types": payload_block["allowed_session_types"],
        "forbidden_session_types": payload_block["forbidden_session_types"],
        "forbidden_blocks": payload_block["forbidden_blocks"],
        "rendering_rules": payload_block["rendering_rules"],
        "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
        "max_active_roles": _late_fight_max_active_roles(days_until_fight),
        "max_support_roles": _late_fight_max_support_roles(days_until_fight),
        "countdown_weekday_map": resolved_countdown_map,
        "role_budget": allocation.get("role_budget", {}),
        "allocator": allocation.get("allocator", {}),
        "suppressed_roles": allocation.get("suppressed_roles", []),
        "permission_policy": allocation.get("permission_policy", {}),
    }
    if max_blocks is not None:
        spec["max_blocks_per_session"] = max_blocks
    hard_sparring_context = _hard_sparring_window_context(days_until_fight, athlete_model)
    if hard_sparring_context:
        spec.update(hard_sparring_context)
    return spec


def _handoff_mode_instructions(payload_mode: str) -> str:
    _CONTRACT = (
        "COUNTDOWN CONTRACT\n"
        "One coherent countdown truth. Lead every active day D-N first, weekday second — use resolved countdown_display_label when present.\n"
        "Placement governs day assignment only — it never expands the visible session list.\n"
        "State the ownership split: gym/coach owns boxing load; app owns S&C and rehab inserts.\n"
        "Render only app-owned roles as athlete-facing sessions; boxing schedule is context.\n"
        "Partial prescription: label exactly — Coach-prescribed S&C / rehab schedule only. Boxing schedule remains as set by gym/coach.\n"
        "Full prescription: label — Countdown schedule.\n"
        "D-0 = fight-day protocol only. Never a training session.\n"
        "Declared hard-spar days are fixed. Downgrade the dose; never move or drop the day.\n"
        "If late_fight_plan_spec.surviving_hard_spar_days / late_fight_plan_spec.downgraded_declared_spar_days are present, use those fields as source of truth and add one short deterministic sentence (hard days first, downgraded days second).\n"
        "Add one short rationale only when placement/compression would otherwise make day choice look arbitrary.\n"
        "One hard-spar doctrine per output. No split schedule realities."
    )
    if payload_mode == "fight_day_protocol_payload":
        return (
            "HARD OVERRIDE — FIGHT DAY PROTOCOL (D-0)\n"
            "The athlete fights today. No training plan, no session architecture.\n"
            "3-block activation sequence max.\n"
            "Output: activation · tactical cueing · fueling/hydration · walk-through · post-fight recovery.\n"
            "Nothing else. Do not restore suppressed roles.\n\n"
            + _CONTRACT
        )
    if payload_mode == "pre_fight_day_payload":
        return (
            "HARD OVERRIDE — PRIMER DAY (D-1)\n"
            "4 blocks max. Output: neural primer · technical touch · activation · mobility/reset · pre-fight notes.\n"
            "Banned: strength, conditioning, anchor, block, glycolytic, development, fight-pace density.\n"
            "No weekly architecture. No hard sparring. No suppressed role restoration.\n\n"
            + _CONTRACT
        )
    if payload_mode == "pre_fight_compressed_payload":
        return (
            "COMPRESSED PRE-FIGHT WEEK (D-13 to D-8)\n"
            "5 blocks per session max. Hard sparring: 2 max. Strength/power: 1 touch max.\n"
            "Fight-rhythm touch: 1 max — suppress entirely if sparring already owns the week.\n"
            "One freshness, mobility, or reset session is mandatory.\n"
            "No SPP development framing, no conditioning-build language, no glycolytic stressor between spar days.\n\n"
            + _CONTRACT
        )
    if payload_mode == "late_fight_week_payload":
        return (
            "SHARPNESS WEEK (D-7)\n"
            "5 blocks per session max. Stress cap: 2 meaningful exposures total.\n"
            "Neural/power: 1 max. Fight-rhythm: 1 max. Hard sparring: 1 declared day — extras become technical rhythm.\n"
            "No development language, no multi-stressor stacking.\n\n"
            + _CONTRACT
        )
    if payload_mode == "late_fight_transition_payload":
        return (
            "SHARPNESS & FRESHNESS WINDOW (D-6 to D-5)\n"
            "4 blocks per session max. Stress cap: 1 meaningful exposure.\n"
            "No hard sparring — all declared spar days convert to technical rhythm.\n"
            "Insert cap: 2 sessions (one power touch or technical rhythm + one freshness).\n"
            "Session-by-session only. S&C inserts titled explicitly as countdown inserts.\n\n"
            + _CONTRACT
        )
    if payload_mode == "late_fight_session_payload":
        return (
            "SHARPNESS-FIRST SESSIONS (D-4 to D-2)\n"
            "4 blocks per session max. Session-by-session only — no week headers, no program blocks.\n"
            "D-4: sharpness + freshness. D-3: freshness default; power/sharpness touch only if fatigue is not high and no spar-spillover flag. D-2: neural primer or technical touch only.\n"
            "No strength, no conditioning, no glycolytic work, no hard sparring.\n\n"
            + _CONTRACT
        )
    return ""
