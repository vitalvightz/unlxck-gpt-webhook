from __future__ import annotations
import logging
from .normalization import clean_list, dedupe_preserve_order, normalize_fatigue_level, ordered_weekdays as _ordered_weekdays
from .fight_date_utils import resolve_fight_weekday
from .sparring_dose_planner import compute_hard_sparring_plan, effective_hard_days
from .performance_bias import bridge_low_risk_profile

from itertools import combinations
from typing import Any

logger = logging.getLogger(__name__)


CANONICAL_HARD_SPARRING_LABEL = "Coach-led boxing — hard sparring / controlled hard contact"
CANONICAL_HARD_SPARRING_BAN_LABEL = "Coach-led boxing — technical-only combat"
CANONICAL_HARD_SPARRING_NOTE = "Coach-owned combat session. Keep freshness priority."


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
    14: "bridge_compression_payload",
    15: "bridge_compression_payload",
    16: "bridge_compression_payload",
    17: "bridge_compression_payload",
    18: "bridge_compression_payload",
    19: "bridge_compression_payload",
    20: "bridge_compression_payload",
    21: "bridge_compression_payload",
}

_MAX_BLOCKS_PER_SESSION = {
    "fight_day_protocol_payload": 3,
    "pre_fight_day_payload": 4,
    "late_fight_session_payload": 4,
    "late_fight_transition_payload": 4,
    "late_fight_week_payload": 5,
    "pre_fight_compressed_payload": 5,
    "bridge_compression_payload": 5,
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
    "bridge_compression_payload": (14, 21),
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

_LATE_FIGHT_ROLE_SELECTION_PRIORITY = {
    "hard_sparring_day": 120,
    "neural_primer_day": 110,
    "strength_touch_day": 108,
    "alactic_sharpness_day": 106,
    "fight_week_freshness_day": 104,
    "light_fight_pace_touch_day": 100,
    "technical_touch_day": -10,
}

_COEXISTABLE_FILLER_ROLE_KEYS = {
    "tactical_watch",
    "tactical_cue_card",
    "self_review",
    "neural_visualization",
    "breathing_reset",
    "recovery_reset",
    "sleep_downshift",
    "mobility_rehab",
    "joint_prep",
    "movement_quality",
    "technical_shadow_rhythm",
    "footwork_walkthrough",
    "fight_week_freshness_day",
}
_DAY_EXCLUSIVE_STRESSOR_ROLE_KEYS = {
    "strength_touch_day",
    "neural_primer_day",
    "alactic_sharpness_day",
    "light_fight_pace_touch_day",
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
    if 18 <= days <= 21:
        # Declared hard sparring at D-18 or further out is a coach-owned
        # combat lock: the app never caps or deloads it.
        return None
    if 0 <= days <= 17:
        return 0
    return None


def _future_declared_weekdays_with_countdown(
    plan_creation_weekday: str | None,
    days_until_fight: Any,
    declared_weekdays: list[str],
) -> list[dict[str, Any]]:
    """Resolve declared weekdays into real upcoming countdown instances."""
    # Normalise casing: declared days often arrive title-cased ("Friday")
    # while countdown weekday names are lowercase — without this the whole
    # classification silently returns empty.
    ordered_declared = [
        str(day).strip().lower() for day in _ordered_weekdays(declared_weekdays)
    ]
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
    if 18 <= offset <= 21:
        return "hard_allowed"
    if 0 <= offset <= 17:
        # D-17 onward caps hard sparring at zero, so declared hard days
        # downgrade to technical / rhythm instead of staying hard-allowed.
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


def _late_fight_hard_sparring_plan(
    *,
    days_until_fight: Any,
    athlete_model: dict[str, Any],
    declared_hard_days: list[str] | None = None,
    phase: str = "TAPER",
    stage_key: str = "late_fight_window",
    week_index: int = 1,
) -> list[dict[str, Any]]:
    """Return planner-owned sparring truth for a late-fight window.

    Late-fight allocation may decide which app-owned sessions are visible, but
    sparring dose/class/status must come from sparring_dose_planner.
    """
    hard_days = _ordered_weekdays(
        declared_hard_days
        if declared_hard_days is not None
        else clean_list(athlete_model.get("hard_sparring_days", []))
    )
    if not hard_days:
        return []

    athlete_snapshot = dict(athlete_model)
    athlete_snapshot["days_until_fight"] = days_until_fight
    week: dict[str, Any] = {
        "phase": phase,
        "stage_key": stage_key,
        "week_index": week_index,
        "phase_week_index": 1,
        "phase_week_total": 1,
        "declared_hard_sparring_days": hard_days,
        "primary_collision_owner_day": athlete_model.get("primary_collision_owner_day"),
        "main_fight_pace_day": athlete_model.get("main_fight_pace_day"),
    }
    # Thread the fight calendar through so the planner's per-day countdown
    # authority (D-17 ban, D-18+ coach-owned hard lock) can resolve each
    # declared weekday to its own D-day. Without this the whole window is
    # judged by its start day, and a D-20 hard day could be downgraded while
    # a D-16 day survived as hard.
    days = _coerce_days(days_until_fight)
    if days is not None and days >= 0:
        fight_weekday = resolve_fight_weekday(
            fight_date=athlete_model.get("fight_date") or athlete_model.get("next_fight_date"),
            plan_creation_weekday=athlete_model.get("plan_creation_weekday"),
            days_until_fight=days,
        )
        if fight_weekday:
            end_d = max(0, days - 6)
            week["fight_weekday"] = fight_weekday
            week["projected_days_until_fight_end"] = end_d
            week["span_days"] = days - end_d + 1
    return compute_hard_sparring_plan(week=week, athlete_snapshot=athlete_snapshot)


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
        backward = (target_index - delta) % 7
        if backward in available_indices:
            return available_indices[backward]
        forward = (target_index + delta) % 7
        if forward in available_indices:
            return available_indices[forward]
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
    days = _coerce_days(days_until_fight)
    if days is None:
        return []
    if days < 0:
        return []
    if days == 0:
        return [0]
    mode = _days_out_payload_mode(days)
    if mode == "bridge_compression_payload":
        # Bridge starts at D-21..D-14 but must carry countdown continuity
        # through fight week so role placement can use legal downstream slots.
        return list(range(days, 0, -1))
    return list(range(min(days, 21), 0, -1))


def _late_fight_legal_countdown_labels(days_until_fight: Any) -> list[str]:
    return [f"D-{offset}" for offset in _late_fight_legal_offsets(days_until_fight)]


def can_render_late_taper_day(*, countdown_offset: int, weekday: str, training_days: list[str]) -> bool:
    if 0 <= countdown_offset <= 6:
        return True
    weekday_norm = str(weekday or "").strip().lower()
    training_set = {str(day).strip().lower() for day in training_days if str(day).strip()}
    return weekday_norm in training_set


def _normalized_fatigue(athlete_model: dict[str, Any]) -> str:
    return normalize_fatigue_level(athlete_model)


def _readiness_flags(athlete_model: dict[str, Any]) -> set[str]:
    return {flag.strip().lower() for flag in clean_list(athlete_model.get("readiness_flags", [])) if flag.strip()}


def _planned_sessions_per_week(athlete_model: dict[str, Any]) -> int:
    for key in ("weekly_training_frequency", "training_frequency", "weekly_sessions"):
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


def _active_weight_cut_present(athlete_model: dict[str, Any], flags: set[str]) -> bool:
    if flags & {"active_weight_cut", "aggressive_weight_cut", "extreme_weight_cut"}:
        return True
    if bool(athlete_model.get("weight_cut_risk")):
        return True
    try:
        return float(athlete_model.get("weight_cut_pct") or 0.0) > 0.0
    except (TypeError, ValueError):
        return True


def _blocks_bridge_extra_glycolytic_touch(athlete_model: dict[str, Any]) -> bool:
    flags = _readiness_flags(athlete_model)
    fatigue = _normalized_fatigue(athlete_model)
    if fatigue in {"moderate", "high", "critical", "extreme"}:
        return True
    # A moderate/routine cut keeps the D-20..D-18 controlled pressure touch;
    # only a high/extreme cut removes it.
    if _weight_cut_is_extreme(athlete_model, flags):
        return True
    if clean_list(athlete_model.get("injuries", [])):
        return True
    if flags & {"injury_management", "medical_hold", "restricted_rehab", "restricted_rehab_only", "needs_review"}:
        return True
    return False


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
    # A stable surface/skin-only injury is a hygiene note, not injured tissue —
    # it must not suppress hard conditioning even if a legacy/persisted model
    # still carries the injury_management flag.
    if (
        "injury_management" in flags
        and fatigue == "moderate"
        and not athlete_model.get("surface_injury_only")
    ):
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
    if 14 <= days <= 21:
        return 3
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
    if 14 <= days <= 21:
        return 2
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
    days = _coerce_days(days_until_fight)
    if days is None:
        return None
    if 14 <= days <= 21:
        return 2
    if 8 <= days <= 13:
        return 2
    if 3 <= days <= 7:
        return 1
    if 0 <= days <= 2:
        return 0
    return None


# --- Bridge window (D-21 to D-14) -------------------------------------------
#
# Evidence-based on-ramp into the final taper. Co-located with the late-fight
# cap helpers above so the cap logic for the entire pre-fight stretch lives in
# one file. compute_bridge_rules() is the public entry point and returns the
# full cap set: hard sparring cap, strength/glycolytic touches, freshness
# requirement, consecutive-hard-day cap, double-stress-day allowance, plus the
# usual max_active_roles and max_meaningful_stress_exposures.

TIMING_STATE_NORMAL = "normal"
TIMING_STATE_BRIDGE = "bridge"
TIMING_STATE_LATE_TAPER = "late_taper"

BRIDGE_SUB_BANDS = {
    "d21_to_d19": (19, 21),
    "d18_to_d16": (16, 18),
    "d15_to_d14": (14, 15),
}

_BRIDGE_FATIGUE_LEVELS = ("none", "low", "moderate", "high", "critical", "extreme")
_BRIDGE_WEIGHT_CUT_BUCKETS = ("none", "low", "moderate", "high", "critical", "extreme")
_BRIDGE_INJURY_MODES = (
    "full_plan",
    "needs_review",
    "restricted_rehab_only",
    "medical_hold",
)

_BRIDGE_STRIKING_SPORTS = {"boxing", "kickboxing", "muay_thai", "muay thai"}
_BRIDGE_MMA_SPORTS = {"mma"}
_BRIDGE_PRESSURE_STYLES = {"pressure", "pressure fighter", "pace", "pace-heavy"}
_BRIDGE_COUNTER_STYLES = {"counter", "counter striker", "reactive", "counter/reactive"}
_BRIDGE_GRAPPLER_STYLES = {"grappler", "grappler-heavy", "wrestler", "bjj"}


def timing_state(days_until_fight: Any) -> str:
    """Return ``normal``, ``bridge`` or ``late_taper`` for ``days_until_fight``."""
    days = _coerce_days(days_until_fight)
    if days is None or days < 0:
        return TIMING_STATE_NORMAL
    if days >= 22:
        return TIMING_STATE_NORMAL
    if 14 <= days <= 21:
        return TIMING_STATE_BRIDGE
    return TIMING_STATE_LATE_TAPER


def bridge_sub_band(days_until_fight: Any) -> str | None:
    """Return the bridge sub-band key, or ``None`` outside D-14 to D-21."""
    days = _coerce_days(days_until_fight)
    if days is None:
        return None
    for name, (low, high) in BRIDGE_SUB_BANDS.items():
        if low <= days <= high:
            return name
    return None


def _bridge_normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _bridge_normalize_styles(style: Any) -> list[str]:
    if style is None:
        return []
    items = style.split(",") if isinstance(style, str) else style
    return [_bridge_normalize(item) for item in items if _bridge_normalize(item)]


def _bridge_baseline(state: str, days_until_fight: Any) -> dict[str, Any]:
    days = _coerce_days(days_until_fight)
    if state == TIMING_STATE_NORMAL:
        return {
            "max_active_roles": 3,
            "max_meaningful_stress_exposures": 4,
            "hard_sparring_cap_default": 2,
            "strength_touch_max": 2,
            "glycolytic_touch_max": 2,
            "max_consecutive_hard_days": 2,
            "double_stress_day_allowed": True,
            "freshness_mandatory": False,
        }
    if state == TIMING_STATE_BRIDGE:
        sub = bridge_sub_band(days_until_fight)
        # D-21 to D-18 allow one hard sparring exposure for clean/low-risk
        # athletes; D-17 and closer always convert declared hard days to
        # technical/rhythm only.
        hard_spar_default = 1 if (days is not None and 18 <= days <= 21) else 0
        return {
            "max_active_roles": 3,
            "max_meaningful_stress_exposures": 3,
            "hard_sparring_cap_default": hard_spar_default,
            "strength_touch_max": 1,
            "glycolytic_touch_max": 1 if (days is not None and 18 <= days <= 21) else 0,
            "max_consecutive_hard_days": 1,
            "double_stress_day_allowed": False,
            "freshness_mandatory": True,
            "bridge_sub_band": sub,
            "no_hard_sparring_after_d16": days is not None and days <= 17,
        }
    # Late taper baseline reflects the spec's evidence-based caps (D-13 to D-8
    # tighter than the legacy late-fight role budget). Callers that need the
    # legacy late-fight role budget for downstream allocation continue to use
    # _late_fight_max_active_roles / _late_fight_max_meaningful_stress_exposures
    # directly; this baseline is the conservative bridge-side view.
    if days is not None and days >= 8:
        return {
            "max_active_roles": 2,
            "max_meaningful_stress_exposures": 2,
            "hard_sparring_cap_default": 0,
            "strength_touch_max": 1,
            "glycolytic_touch_max": 0,
            "max_consecutive_hard_days": 0,
            "double_stress_day_allowed": False,
            "freshness_mandatory": True,
        }
    return {
        "max_active_roles": 1,
        "max_meaningful_stress_exposures": 1,
        "hard_sparring_cap_default": 0,
        "strength_touch_max": 1,
        "glycolytic_touch_max": 0,
        "max_consecutive_hard_days": 0,
        "double_stress_day_allowed": False,
        "freshness_mandatory": True,
    }


def _bridge_target_active_roles(
    bridge_rules: dict[str, Any]
) -> int:
    days = bridge_rules.get("days_until_fight") or 0
    fatigue = str(bridge_rules.get("fatigue") or "").strip().lower()
    cut = str(bridge_rules.get("weight_cut_bucket") or "").strip().lower()

    if cut in {"high", "critical", "extreme"} or fatigue in {"high", "critical", "extreme"}:
        return 1

    # Unified bridge active-role guidance (kept in step with the binding
    # _bridge_active_role_cap): a low-fatigue athlete on a none/low/moderate cut
    # keeps one extra low-risk active role across the whole bridge window
    # (D-21..D-14), so this render-side guidance matches what the allocator
    # actually places. Hard sparring + glycolytic caps are unchanged, so the
    # extra role is filled by low-risk work only. Any high-pressure signal stays
    # at the conservative 2. (The binding cap additionally gates on
    # injury/readiness via bridge_low_risk_profile, which this coarse scalar
    # guidance cannot see; it therefore remains a conservative upper-bound view.)
    if isinstance(days, int) and 14 <= days <= 21:
        if fatigue in {"none", "low"} and cut in {"none", "low", "moderate"}:
            return 3
        return 2
    return 2


def _bridge_unsafe_weight(
    bucket: str,
    pct_above_class: float | None,
    hours_to_recovery: float | None,
    force_unsafe: bool,
) -> bool:
    if force_unsafe:
        return True
    if bucket in {"critical", "extreme"}:
        return True
    if pct_above_class is None:
        return False
    try:
        pct = float(pct_above_class)
    except (TypeError, ValueError):
        return False
    if pct > 5.0:
        return True
    if pct > 3.0:
        try:
            hours = float(hours_to_recovery) if hours_to_recovery is not None else None
        except (TypeError, ValueError):
            hours = None
        if hours is not None and hours < 4.0:
            return True
    return False


def _bridge_apply_injury(rules: dict[str, Any], injury_mode: str) -> dict[str, Any]:
    if injury_mode == "medical_hold":
        rules.update(plan_mode="medical_hold", block_full_plan=True)
        rules["reason_codes"].append("injury_medical_hold")
        return rules
    if injury_mode == "restricted_rehab_only":
        rules.update(plan_mode="restricted_rehab_only", block_full_plan=True)
        rules["reason_codes"].append("injury_restricted_rehab_only")
        return rules
    if injury_mode == "needs_review":
        if rules.get("plan_mode") in (None, "", "full_plan"):
            rules["plan_mode"] = "needs_review"
        rules["block_full_plan"] = True
        rules["reason_codes"].append("injury_needs_review")
    return rules


def _bridge_apply_fatigue(rules: dict[str, Any], fatigue: str) -> dict[str, Any]:
    if fatigue in {"critical", "extreme"}:
        rules.update(plan_mode="needs_review", block_full_plan=True)
        rules["reason_codes"].append("fatigue_critical_escalate")
        return rules
    if fatigue == "high":
        rules["phase_downgraded_by_fatigue"] = True
        rules["hard_sparring_cap"] = 0
        rules["glycolytic_touch_max"] = 0
        rules["strength_touch_max"] = min(rules.get("strength_touch_max", 1), 1)
        rules["max_active_roles"] = min(rules.get("max_active_roles", 2), 2)
        rules["freshness_mandatory"] = True
        rules["double_stress_day_allowed"] = False
        if rules["timing_state"] == TIMING_STATE_NORMAL:
            bridge = _bridge_baseline(TIMING_STATE_BRIDGE, rules.get("days_until_fight"))
            rules["max_meaningful_stress_exposures"] = min(
                rules.get("max_meaningful_stress_exposures", 3),
                bridge["max_meaningful_stress_exposures"],
            )
        else:
            rules["max_meaningful_stress_exposures"] = max(
                0, rules.get("max_meaningful_stress_exposures", 3) - 1
            )
        rules["reason_codes"].append("fatigue_high_downgrade_phase")
        return rules
    if fatigue == "moderate":
        rules["max_meaningful_stress_exposures"] = max(
            0, rules.get("max_meaningful_stress_exposures", 3) - 1
        )
        rules["strength_touch_max"] = min(rules.get("strength_touch_max", 1), 1)
        rules["freshness_mandatory"] = True
        rules["double_stress_day_allowed"] = False
        if (
            rules.get("timing_state") == TIMING_STATE_BRIDGE
            and isinstance(rules.get("days_until_fight"), int)
            and 18 <= rules["days_until_fight"] <= 21
        ):
            rules["glycolytic_touch_max"] = 0
            rules["reason_codes"].append("fatigue_moderate_blocks_extra_glycolytic_touch")
        rules["reason_codes"].append("fatigue_moderate_trim_stress")
    return rules


def _resolve_bridge_cut_bucket(athlete_model: dict[str, Any]) -> str:
    """Return the cut severity bucket for bridge permissions.

    Prefers an explicit ``cut_severity_bucket`` on the athlete model; when
    that is absent, derives it from ``weight_cut_pct`` and
    ``days_until_fight`` via the shared severity scorer so the bridge
    payload agrees with ``sparring_dose_planner._cut_pressure``.
    """
    from .weight_cut import compute_cut_severity_score, cut_severity_bucket

    explicit = str(athlete_model.get("cut_severity_bucket") or "").strip().lower()
    if explicit:
        return explicit
    score = compute_cut_severity_score(
        athlete_model.get("weight_cut_pct"),
        athlete_model.get("days_until_fight"),
    )
    return cut_severity_bucket(score)


def _bridge_apply_weight_cut(
    rules: dict[str, Any],
    bucket: str,
    unsafe: bool,
) -> dict[str, Any]:
    if unsafe:
        if rules.get("plan_mode") in (None, "", "full_plan"):
            rules["plan_mode"] = "needs_review"
        rules["block_full_plan"] = True
        rules["hard_sparring_cap"] = 0
        rules["glycolytic_touch_max"] = 0
        rules["strength_touch_max"] = min(rules.get("strength_touch_max", 1), 1)
        rules["freshness_mandatory"] = True
        rules["double_stress_day_allowed"] = False
        rules["reason_codes"].append("weight_cut_unsafe_block")
        return rules
    if bucket == "high":
        rules["hard_sparring_cap"] = 0
        rules["glycolytic_touch_max"] = 0
        rules["strength_touch_max"] = min(rules.get("strength_touch_max", 1), 1)
        rules["freshness_mandatory"] = True
        rules["double_stress_day_allowed"] = False
        rules["reason_codes"].append("weight_cut_high_suppress_hard_work")
        return rules
    if bucket == "moderate":
        # A moderate/routine active cut is note-only: it keeps the single
        # controlled pressure touch in D-20..D-18. Only a high+ cut removes
        # bridge-window pressure exposure.
        rules["reason_codes"].append("weight_cut_moderate_note_only")
    return rules


def _bridge_apply_sport_style(
    rules: dict[str, Any], sport: str, styles: list[str]
) -> dict[str, Any]:
    rules["sport"] = sport or ""
    rules["styles"] = list(styles)
    if rules.get("timing_state") != TIMING_STATE_BRIDGE:
        return rules
    if sport in _BRIDGE_STRIKING_SPORTS:
        rules["latest_hard_spar_day"] = "d16"
        rules["headgear_recommended_for_contact"] = True
    if sport in _BRIDGE_MMA_SPORTS:
        rules["mma_grappling_shares_hard_spar_slot"] = True
    if any(style in _BRIDGE_GRAPPLER_STYLES for style in styles):
        rules["grappler_hard_live_shares_spar_slot"] = True
        rules["striking_hard_contact_blocked_in_bridge"] = True
    if any(style in _BRIDGE_PRESSURE_STYLES for style in styles):
        if rules.get("bridge_sub_band") == "d21_to_d19":
            rules["allow_pace_specific_interval_swap"] = True
        rules["pressure_style_stress_cap_unchanged"] = True
    if any(style in _BRIDGE_COUNTER_STYLES for style in styles):
        rules["counter_style_bias_precision_over_density"] = True
    return rules


def _bridge_resolve_hard_spar_slots(
    rules: dict[str, Any], hard_sparring_days_declared: int
) -> dict[str, Any]:
    cap = max(0, int(rules.get("hard_sparring_cap", rules.get("hard_sparring_cap_default", 0))))
    declared = max(0, int(hard_sparring_days_declared or 0))
    days = rules.get("days_until_fight")
    if (
        rules.get("timing_state") == TIMING_STATE_BRIDGE
        and isinstance(days, int)
        and 18 <= days <= 21
        and declared > cap
    ):
        # Declared hard sparring days at D-18 or further out are coach-owned
        # combat locks — the surfaced cap never asks the renderer to deload
        # or drop them.
        cap = declared
        rules["reason_codes"].append("declared_hard_spar_coach_owned_lock")
    rules["hard_sparring_cap"] = cap
    rules["hard_sparring_days_declared"] = declared
    rules["remaining_hard_spar_slots"] = 0 if declared >= cap else cap - declared
    if rules.get("timing_state") == TIMING_STATE_BRIDGE and declared > 0:
        rules["glycolytic_touch_max"] = 0
        rules["reason_codes"].append("hard_sparring_load_blocks_extra_glycolytic_touch")
    return rules


def _bridge_apply_permissive(
    rules: dict[str, Any],
    fatigue: str,
    bucket: str,
    injury_mode: str,
    declared: int,
    permissive: bool,
) -> dict[str, Any]:
    if not permissive:
        rules["permissive_mode_eligible"] = False
        return rules
    # A moderate cut is note-only, so it qualifies for permissive mode exactly
    # like a none/low cut — clean and moderate athletes keep matching caps.
    eligible = (
        rules.get("timing_state") == TIMING_STATE_BRIDGE
        and injury_mode == "full_plan"
        and fatigue in {"none", "low"}
        and bucket in {"none", "low", "moderate"}
        and declared == 0
    )
    rules["permissive_mode_eligible"] = bool(eligible)
    if not eligible:
        rules["reason_codes"].append("permissive_mode_gated_off")
        return rules
    if rules.get("sport") in _BRIDGE_STRIKING_SPORTS | _BRIDGE_MMA_SPORTS:
        rules["reason_codes"].append("permissive_mode_blocked_for_contact_sport")
        return rules
    if rules.get("bridge_sub_band") == "d21_to_d19":
        rules["strength_touch_max"] = max(rules.get("strength_touch_max", 1), 2)
        rules["reason_codes"].append("permissive_mode_extra_strength_touch")
    return rules


def compute_bridge_rules(
    *,
    days_until_fight: Any,
    sport: Any = "",
    style: Any = None,
    fatigue: Any = "low",
    weight_cut_bucket: Any = "none",
    injury_mode: Any = "full_plan",
    hard_sparring_days_declared: Any = 0,
    athlete_pct_above_class: float | None = None,
    hours_to_recovery_after_weigh_in: float | None = None,
    force_unsafe_weight_cut: bool = False,
    permissive_mode: bool = False,
) -> dict[str, Any]:
    """Evidence-based bridge / late-taper / normal-camp cap set.

    Centralises the D-21 to D-14 "taper-on-ramp" rules alongside the existing
    late-fight cap helpers so the entire pre-fight stretch lives in one file.
    Sport/style modifiers only reallocate inside the phase ceiling — they
    never raise total caps.
    """
    state = timing_state(days_until_fight)
    days = _coerce_days(days_until_fight)

    fatigue_norm = _bridge_normalize(fatigue) if _bridge_normalize(fatigue) in _BRIDGE_FATIGUE_LEVELS else "low"
    bucket_norm = _bridge_normalize(weight_cut_bucket) if _bridge_normalize(weight_cut_bucket) in _BRIDGE_WEIGHT_CUT_BUCKETS else "none"
    injury_norm = _bridge_normalize(injury_mode) if _bridge_normalize(injury_mode) in _BRIDGE_INJURY_MODES else "full_plan"
    sport_norm = _bridge_normalize(sport).replace(" ", "_") if sport else ""
    styles = _bridge_normalize_styles(style)

    unsafe = _bridge_unsafe_weight(
        bucket_norm,
        athlete_pct_above_class,
        hours_to_recovery_after_weigh_in,
        force_unsafe_weight_cut,
    )

    baseline = _bridge_baseline(state, days_until_fight)
    rules: dict[str, Any] = {
        "timing_state": state,
        "bridge_sub_band": baseline.get("bridge_sub_band"),
        "days_until_fight": days,
        "max_active_roles": baseline["max_active_roles"],
        "max_meaningful_stress_exposures": baseline["max_meaningful_stress_exposures"],
        "hard_sparring_cap_default": baseline["hard_sparring_cap_default"],
        "hard_sparring_cap": baseline["hard_sparring_cap_default"],
        "strength_touch_max": baseline["strength_touch_max"],
        "glycolytic_touch_max": baseline["glycolytic_touch_max"],
        "max_consecutive_hard_days": baseline["max_consecutive_hard_days"],
        "double_stress_day_allowed": baseline["double_stress_day_allowed"],
        "freshness_mandatory": baseline["freshness_mandatory"],
        "plan_mode": "full_plan",
        "block_full_plan": False,
        "reason_codes": [],
        "fatigue": fatigue_norm,
        "weight_cut_bucket": bucket_norm,
        "injury_mode": injury_norm,
        "unsafe_weight_flag": unsafe,
    }
    if baseline.get("no_hard_sparring_after_d16"):
        rules["no_hard_sparring_after_d16"] = True

    rules = _bridge_apply_injury(rules, injury_norm)
    rules = _bridge_apply_fatigue(rules, fatigue_norm)
    rules = _bridge_apply_weight_cut(rules, bucket_norm, unsafe)
    rules = _bridge_apply_sport_style(rules, sport_norm, styles)

    # Sport/style must never raise caps above the phase baseline.
    rules["max_active_roles"] = min(rules["max_active_roles"], baseline["max_active_roles"])
    rules["max_meaningful_stress_exposures"] = min(
        rules["max_meaningful_stress_exposures"], baseline["max_meaningful_stress_exposures"]
    )
    rules["strength_touch_max"] = min(rules["strength_touch_max"], baseline["strength_touch_max"])
    rules["glycolytic_touch_max"] = min(rules["glycolytic_touch_max"], baseline["glycolytic_touch_max"])
    rules["max_consecutive_hard_days"] = min(
        rules["max_consecutive_hard_days"], baseline["max_consecutive_hard_days"]
    )

    rules = _bridge_resolve_hard_spar_slots(rules, _coerce_days(hard_sparring_days_declared, 0) or 0)
    rules = _bridge_apply_permissive(
        rules,
        fatigue_norm,
        bucket_norm,
        injury_norm,
        _coerce_days(hard_sparring_days_declared, 0) or 0,
        permissive=permissive_mode,
    )
    if rules.get("timing_state") == TIMING_STATE_BRIDGE:
        rules["max_active_roles"] = min(
            rules["max_active_roles"],
            _bridge_target_active_roles(rules),
        )

    if rules["block_full_plan"]:
        rules["max_active_roles"] = 0
        rules["max_meaningful_stress_exposures"] = 0
        rules["hard_sparring_cap"] = 0
        rules["remaining_hard_spar_slots"] = 0
        rules["glycolytic_touch_max"] = 0
        if rules["plan_mode"] not in {"restricted_rehab_only", "medical_hold"}:
            rules["strength_touch_max"] = 0

    return rules


def _late_fight_cost_class(role_key: str) -> str:
    return _LATE_FIGHT_ROLE_COST_CLASS.get(role_key, "low")


def _late_fight_stress_class(role_key: str) -> str:
    return _LATE_FIGHT_ROLE_STRESS_CLASS.get(role_key, "support")


def _resolve_plan_creation_weekday(days_until_fight: Any, athlete_model: dict[str, Any]) -> str | None:
    """Return the plan-creation weekday, deriving it from fight_date when missing.

    Without this fallback ``_countdown_weekday_map`` returns an empty mapping
    when an athlete model omits ``plan_creation_weekday`` but has a real
    ``fight_date``. Empty maps suppress every late-fight candidate (no
    eligible weekday) and collapse composite-bridge segments to downstream
    roles only.
    """
    plan_creation_weekday = athlete_model.get("plan_creation_weekday")
    if plan_creation_weekday:
        return str(plan_creation_weekday).strip().lower() or None
    fight_weekday = resolve_fight_weekday(
        fight_date=athlete_model.get("fight_date") or athlete_model.get("next_fight_date"),
        plan_creation_weekday=None,
        days_until_fight=days_until_fight,
    )
    days_val = _coerce_days(days_until_fight)
    if not fight_weekday or not isinstance(days_val, int) or days_val < 0:
        return None
    fight_idx = _WEEKDAY_ORDER.get(fight_weekday)
    if fight_idx is None:
        return None
    creation_idx = (fight_idx - days_val) % 7
    return _WEEKDAY_NAMES[creation_idx]


def _late_fight_countdown_context(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any]:
    plan_creation_weekday = _resolve_plan_creation_weekday(days_until_fight, athlete_model)
    available_days = clean_list(athlete_model.get("training_days", []))
    countdown_map = _countdown_weekday_map(plan_creation_weekday, days_until_fight)
    resolved_map: dict[str, str] = {}
    legal_countdown_labels = _late_fight_legal_countdown_labels(days_until_fight)
    for label, weekday in countdown_map.items():
        weekday_name = str(weekday or "").strip().lower()
        if not weekday_name:
            continue
        resolved_day = _nearest_available_day(weekday_name, available_days)
        if resolved_day:
            resolved_map[label] = resolved_day
    legal_weekdays = [
        str(resolved_map.get(label) or "").strip().lower()
        for label in legal_countdown_labels
        if str(resolved_map.get(label) or "").strip()
    ]
    availability_adjustments: list[dict[str, Any]] = []
    for label in legal_countdown_labels:
        raw_weekday = str(countdown_map.get(label) or "").strip().lower()
        resolved_weekday = str(resolved_map.get(label) or "").strip().lower()
        if raw_weekday and resolved_weekday and raw_weekday != resolved_weekday:
            availability_adjustments.append(
                {
                    "countdown_label": label,
                    "raw_weekday": raw_weekday,
                    "resolved_weekday": resolved_weekday,
                    "reason": "nearest_available_day",
                }
            )
    eligible_countdown_labels = [
        label
        for label in legal_countdown_labels
        if (offset := _countdown_offset(label)) is not None
        and can_render_late_taper_day(
            countdown_offset=offset,
            weekday=str(countdown_map.get(label) or ""),
            training_days=available_days,
        )
    ]
    return {
        "countdown_weekday_map": resolved_map,
        "raw_countdown_weekday_map": countdown_map,
        "legal_countdown_labels": legal_countdown_labels,
        "eligible_countdown_labels": eligible_countdown_labels,
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
    countdown_by_day = {
        str(entry.get("weekday") or "").strip().lower(): entry
        for entry in classified_hard_days
        if str(entry.get("weekday") or "").strip()
    }
    hard_sparring_plan = _late_fight_hard_sparring_plan(
        days_until_fight=days_until_fight,
        athlete_model=athlete_model,
        declared_hard_days=declared_hard_days,
        stage_key=_late_fight_window(days_until_fight),
    )
    plan_by_day = {
        str(entry.get("day") or "").strip().lower(): entry
        for entry in hard_sparring_plan
        if str(entry.get("day") or "").strip()
    }
    preserved_hard_days = dedupe_preserve_order(
        [
            day
            for day in (str(entry.get("day") or "").strip().lower() for entry in hard_sparring_plan)
            if day and str(plan_by_day.get(day, {}).get("effective_load") or "") == "hard"
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
    if mode in {"bridge_compression_payload", "pre_fight_compressed_payload"}:
        allowed_role_keys = ["hard_sparring_day", "strength_touch_day", "light_fight_pace_touch_day", "alactic_sharpness_day", "technical_touch_day", "fight_week_freshness_day"]
    elif mode == "late_fight_week_payload":
        allowed_role_keys = ["hard_sparring_day", "neural_primer_day", "alactic_sharpness_day", "technical_touch_day", "fight_week_freshness_day"]
    elif mode == "late_fight_transition_payload":
        allowed_role_keys = ["alactic_sharpness_day", "technical_touch_day", "fight_week_freshness_day"]
    elif mode == "late_fight_session_payload":
        allowed_role_keys = ["neural_primer_day", "alactic_sharpness_day", "technical_touch_day", "fight_week_freshness_day"]
    elif mode == "pre_fight_day_payload":
        allowed_role_keys = ["neural_primer_day", "technical_touch_day"]

    # A weekday can recur inside the countdown window (e.g. Friday at D-20,
    # D-13, and D-6). The hard lock belongs to the hard-allowed occurrence
    # (D-18 or further out), never to the closest occurrence — later
    # occurrences of the same weekday are technical-only coach days.
    hard_instance_by_day: dict[str, dict[str, Any]] = {}
    for entry in classified_hard_days:
        weekday = str(entry.get("weekday") or "").strip().lower()
        if weekday and str(entry.get("status") or "") == "hard_allowed":
            hard_instance_by_day.setdefault(weekday, entry)

    declared_hard_day_actions: list[dict[str, Any]] = []
    for day in declared_hard_days:
        normalized_day = str(day).strip().lower()
        if not normalized_day:
            continue
        plan_entry = plan_by_day.get(normalized_day, {})
        countdown_entry = countdown_by_day.get(normalized_day, {})
        is_effective_hard = str(plan_entry.get("effective_load") or "") == "hard"
        action: dict[str, Any] = {
            "day": normalized_day,
            "outcome": "hard_sparring_day" if is_effective_hard else "technical_touch_day",
            "locked": bool(is_effective_hard),
        }
        if is_effective_hard:
            hard_instance = hard_instance_by_day.get(normalized_day) or countdown_entry
            action["countdown_label"] = hard_instance.get("countdown_label")
            action["countdown_offset"] = hard_instance.get("offset")
        else:
            action["downgraded_from_role_key"] = "hard_sparring_day"
        declared_hard_day_actions.append(action)

    return {
        "mode": mode,
        "legal_countdown_labels": list(countdown_context.get("legal_countdown_labels", [])),
        "eligible_countdown_labels": list(countdown_context.get("eligible_countdown_labels", [])),
        "countdown_weekday_map": dict(countdown_context.get("countdown_weekday_map", {})),
        "raw_countdown_weekday_map": dict(countdown_context.get("raw_countdown_weekday_map", {})),
        "legal_weekdays": list(countdown_context.get("legal_weekdays", [])),
        "availability_adjustments": list(countdown_context.get("availability_adjustments", [])),
        "declared_hard_day_actions": declared_hard_day_actions,
        "preserved_hard_days": preserved_hard_days,
        "downgraded_hard_days": downgraded_hard_days,
        "allowed_role_keys": dedupe_preserve_order(allowed_role_keys),
    }


def _bridge_active_role_cap(days_until_fight: Any, athlete_model: dict[str, Any]) -> int | None:
    """Single source of truth for the binding D-21..D-14 active-role cap.

    The flat late-fight budget caps D-14..D-21 at 2 app-owned active roles. That
    silently overrode the bridge baseline of 3 and shrank plans for clean /
    mildly-managed athletes. This unifies the two: a low-risk athlete (low
    fatigue, at most mild injury, none/low/moderate cut) keeps one extra
    low-risk active role across the whole bridge window (D-21..D-14); any safety
    signal — high fatigue, moderate+ injury, aggressive cut, restricted injury
    mode — drops them back to the conservative baseline. Hard sparring and
    glycolytic caps are untouched, so the extra role is filled by low-risk work
    only (a non-fatiguing alactic sharpness touch).

    Why the bump now extends through D-17..D-14: the freshness/reset day is
    mandatory in the bridge and counts against the active-role budget, so a flat
    cap of 2 there is fully consumed by the strength touch + freshness day,
    leaving no room for a single real conditioning exposure. Keeping the extra
    low-risk role makes room for that one alactic touch. (Previously this was
    only granted in D-21..D-18, or in D-17..D-14 when the athlete had *declared*
    hard sparring that converted to technical and freed a coach-owned slot.)
    """
    base = _late_fight_max_active_roles(days_until_fight)
    if base is None:
        return None
    days = _coerce_days(days_until_fight)
    if not (isinstance(days, int) and bridge_low_risk_profile(athlete_model)):
        return base
    if 14 <= days <= 21:
        return max(base, 3)
    return base


def _late_fight_role_budget(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": _days_out_payload_mode(days_until_fight),
        "max_active_roles": _bridge_active_role_cap(days_until_fight, athlete_model),
        "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
        "max_support_roles": _late_fight_max_support_roles(days_until_fight),
        "legal_countdown_labels": _late_fight_legal_countdown_labels(days_until_fight),
    }


def _late_fight_forbidden_blocks(days_until_fight: Any) -> list[str]:
    days = _coerce_days(days_until_fight)
    if days is None:
        return []
    if 14 <= days <= 21:
        forbidden = [
            "multiple_hard_sparring_exposures",
            "stacked_hard_day_pair",
            "double_stress_day",
        ]
        if days < 19:
            forbidden.append("standalone_glycolytic")
        return forbidden
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


def _late_fight_countdown_exercise_rules(days_until_fight: Any) -> list[dict[str, Any]]:
    days = _coerce_days(days_until_fight)
    if days is None or days < 0:
        return []

    covered_days: list[int] = []
    sequence = _countdown_mode_sequence(days)
    if sequence:
        for segment in sequence:
            start_day = segment.get("start_day")
            end_day = segment.get("end_day")
            if not isinstance(start_day, int) or not isinstance(end_day, int):
                continue
            covered_days.extend(range(start_day, end_day - 1, -1))
    else:
        covered_days = [days]

    rules: list[dict[str, Any]] = []
    for day in dedupe_preserve_order(covered_days):
        if day == 13:
            rules.append(
                {
                    "countdown_label": "D-13",
                    "blocked_drills": [
                        "Band-Resisted Sprint Start",
                        "Band-Resisted Sprint Starts (ATP-PCr)",
                        "resisted acceleration",
                        "sprint start",
                    ],
                    "preferred_drills": [
                        "Explosive Boxing Burst Intervals",
                        "Reactive Shuffle Repeats",
                        "Mobility Reset Flow",
                        "Breathing Reset",
                    ],
                    "reason": "D-13 may keep low-damage sharpness but must not render SPP-only sprint-start or resisted acceleration work.",
                }
            )
        elif day == 6:
            rules.append(
                {
                    "countdown_label": "D-6",
                    "blocked_drills": [
                        "Band-Assisted Jump Reset",
                        "Band-Resisted Sprint Start",
                        "Band-Resisted Sprint Starts (ATP-PCr)",
                    ],
                    "preferred_drills": [
                        "Explosive Boxing Burst Intervals",
                        "Reactive Shuffle Repeats",
                    ],
                    "reason": "D-6 boxing taper should keep sharpness low-impact and should not use jumps or sprint-start fallbacks.",
                }
            )
        elif day == 1:
            rules.append(
                {
                    "countdown_label": "D-1",
                    "blocked_drills": [
                        "Staggered-Stance Medicine-Ball Punch Throw",
                        "medicine ball",
                        "med-ball",
                        "band",
                        "banded",
                        "Band-Resisted Sprint Start",
                        "Band-Resisted Sprint Starts (ATP-PCr)",
                        "Jump Reset",
                        "Heavy Bag",
                        "Pull-Up Hold",
                        "barbell",
                        "trap bar",
                        "slow eccentric",
                        "loaded strength",
                    ],
                    "preferred_drills": [
                        "Technical Shadowboxing Tempo",
                        "Mobility Reset Flow",
                        "Breathing Reset",
                    ],
                    "reason": "D-1 is a boring readiness day: no med-ball, bands, jumps, sprint starts, pull-up holds, heavy bag, or loaded strength.",
                }
            )
    return rules


_TAPER_MICRO_SUPPORT_TAG = "taper_micro_support"
_TAPER_MICRO_SUPPORT_CORE_OPTIONS = (
    "Dead Bug Breathing: 1-2 x 4 reps/side",
    "Bird Dog Hold: 1-2 x 10 sec/side",
    "Side Plank Breathing Hold: 1 x 10-15 sec/side",
    "Pallof Iso Hold: 1-2 x 10 sec/side",
)


def _late_fight_taper_micro_support_policy(
    days_until_fight: Any,
    athlete_model: dict[str, Any],
) -> dict[str, Any]:
    days = _coerce_days(days_until_fight)
    fatigue = _normalized_fatigue(athlete_model)
    flags = _readiness_flags(athlete_model)
    cut_bucket = _resolve_bridge_cut_bucket(athlete_model)
    sport = str(athlete_model.get("sport") or "").strip().lower()
    high_fatigue = fatigue == "high" or "high_fatigue" in flags
    weight_cut_suppressed = cut_bucket in {"moderate", "high", "critical", "extreme"}
    grappling_sport = sport in {"mma", "grappling", "wrestling", "bjj", "jiu_jitsu"}

    if days in {10, 9, 8}:
        day_band, max_minutes = "d10_to_d8", 6
    elif days in {7, 6, 5}:
        day_band, max_minutes = "d7_to_d5", 5
    elif days in {4, 3, 2}:
        day_band, max_minutes = "d4_to_d2", 4
    elif days == 1:
        day_band, max_minutes = "d1", 4
    else:
        day_band, max_minutes = "inactive", 0

    policy: dict[str, Any] = {
        "tag": _TAPER_MICRO_SUPPORT_TAG,
        "active": day_band != "inactive",
        "optional_add_on_only": True,
        "never_primary_anchor": True,
        "standalone_session_allowed": False,
        "max_items": 1 if day_band != "inactive" else 0,
        "max_total_minutes": max_minutes,
        "day_band": day_band,
        "allowed_categories": ["breathing", "mobility"],
        "suppressed_categories": [],
        "suppression_reasons": [],
        "core_allowed_options": list(_TAPER_MICRO_SUPPORT_CORE_OPTIONS),
        "core_blocked_options": [
            "Hanging Leg Raises",
            "Russian Twists",
            "Weighted Sit-Ups",
            "Long Planks",
            "High-Rep Abs",
        ],
        "d1_allowed_list": [
            "breathing",
            "mobility",
            "light technical shadowboxing",
        ],
        "d1_blocked_list": [
            "core",
            "neck",
            "heavy_bag",
            "grip",
            "conditioning",
            "bands",
            "hard_bands",
            "equipment_work",
            "power_work",
        ],
    }

    suppressed: set[str] = set()
    if not policy["active"]:
        policy["suppression_reasons"].append("outside_taper_micro_support_window")
    elif high_fatigue:
        suppressed.update({"core", "neck", "heavy_bag", "grip", "shadowboxing", "band_face_pull"})
        policy["suppression_reasons"].append("high_fatigue_breathing_mobility_only")
    else:
        if day_band in {"d10_to_d8", "d7_to_d5"}:
            policy["allowed_categories"].extend(["core", "neck", "heavy_bag"])
        elif day_band == "d4_to_d2":
            policy["allowed_categories"].append("breathing_based_core_cue")
            suppressed.update({"neck", "heavy_bag", "grip"})
        elif day_band == "d1":
            # D-1 is equipment-free: shadowboxing is the only add-on beyond
            # breathing/mobility, and band work is suppressed with the rest.
            policy["allowed_categories"].append("shadowboxing")
            suppressed.update({"core", "neck", "heavy_bag", "grip", "band_face_pull"})
            policy["suppression_reasons"].append("d1_blocks_core_neck_heavy_bag_grip")
            policy["suppression_reasons"].append("d1_blocks_all_equipment_work")

        allow_grip = grappling_sport and days in {10, 9, 8, 7} and sport != "boxing"

        if allow_grip:
            policy["allowed_categories"].append("grip")
        else:
            suppressed.add("grip")
            if sport == "boxing":
                policy["suppression_reasons"].append("boxing_taper_blocks_grip")

    if weight_cut_suppressed:
        suppressed.update({"core", "neck", "heavy_bag", "grip"})
        policy["suppression_reasons"].append("moderate_or_high_weight_cut_blocks_nonessential_micro_support")

    policy["allowed_categories"] = [
        category for category in dedupe_preserve_order(policy["allowed_categories"])
        if category not in suppressed
    ]
    policy["suppressed_categories"] = sorted(suppressed)
    return policy


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
    if days < 0 or days > 21:
        return "CAMP"
    return f"D-{days}"


def _late_fight_window(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "bridge_compression_payload":
        return "d21_to_d14"
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
    if mode == "bridge_compression_payload":
        return (
            ["sparring", "technical", "strength", "sharpness", "recovery"],
            [
                "multiple_hard_sparring_exposures",
                "stacked_hard_day_pair",
                "double_stress_day",
                "broad_development_week",
            ],
        )
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
    if mode == "bridge_compression_payload":
        bridge_rules = compute_bridge_rules(
            days_until_fight=days_until_fight,
            sport=athlete_model.get("sport"),
            style=athlete_model.get("tactical_style") or athlete_model.get("style"),
            fatigue=athlete_model.get("fatigue") or athlete_model.get("fatigue_level"),
            weight_cut_bucket=_resolve_bridge_cut_bucket(athlete_model),
            injury_mode=athlete_model.get("injury_mode"),
            hard_sparring_days_declared=len(
                clean_list(athlete_model.get("hard_sparring_days", []))
            ),
        )
        # One source of truth: the binding allocation cap (_bridge_active_role_cap)
        # is athlete-aware (injury severity, declared-sparring freed slot) where the
        # scalar bridge guidance is not. Align the surfaced guidance to it so the
        # bridge policy never under-reports the plan it will actually allocate.
        bridge_rules["max_active_roles"] = _bridge_active_role_cap(days_until_fight, athlete_model)
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": True,
            "allow_normal_session_roles": True,
            "allow_anchor_wording": False,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": bridge_rules["strength_touch_max"],
            "max_meaningful_conditioning_stressors": bridge_rules["glycolytic_touch_max"],
            "max_meaningful_stress_exposures": bridge_rules["max_meaningful_stress_exposures"],
            "max_active_roles": bridge_rules["max_active_roles"],
            "hard_sparring_cap": bridge_rules["hard_sparring_cap"],
            "remaining_hard_spar_slots": bridge_rules["remaining_hard_spar_slots"],
            "freshness_mandatory": bridge_rules["freshness_mandatory"],
            "max_consecutive_hard_days": bridge_rules["max_consecutive_hard_days"],
            "double_stress_day_allowed": bridge_rules["double_stress_day_allowed"],
            "no_hard_sparring_after_d16": bridge_rules.get("no_hard_sparring_after_d16", False),
            "bridge_sub_band": bridge_rules.get("bridge_sub_band"),
            "allow_hard_sparring_influence": True,
            "allow_weekly_frequency_reasoning": True,
            "allow_multi_session_stress": False,
            "sparring_role": "bridge_collision_owner_capped",
            "forbid": [
                "deloading, capping, or dropping a declared hard sparring day at D-18 or further out",
                "hard sparring from D-17 onward",
                "stacked hard days",
                "double-stress day",
                "broad development language",
            ],
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
    if mode == "bridge_compression_payload":
        return {
            "mode": mode,
            "framing": "bridge_compression_week",
            "rules": [
                "Bridge compression week: taper-on-ramp framing, not full camp.",
                "5 blocks per session max. 3 meaningful stress exposures max per rolling 7-day block.",
                "At most 1 hard sparring exposure in D-21 to D-18. From D-17 onward, all declared hard sparring converts to technical/rhythm only.",
                "One freshness / mobility session is mandatory. No double-stress days.",
            ],
            "preferred_terms": [
                "bridge week",
                "taper on-ramp",
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
                "back-to-back hard days",
            ],
        }
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
                "D-7 primers must stay submaximal: use selected drill RPE when present; otherwise cap at RPE 6-7, 3-4 x 6 sec, full rest.",
                "5 blocks per session max. No effective hard sparring — all declared hard sparring converts to technical/rhythm only.",
            ],
            "preferred_terms": ["sharpness week", "power touch", "neural touch", "technical rhythm", "freshness session", "mobility / reset"],
            "forbidden_terms": ["primary strength", "secondary strength", "anchor day", "conditioning block", "development block", "all-out bursts", "RPE 8"],
        }
    if mode == "late_fight_transition_payload":
        return {
            "mode": mode,
            "framing": "session_by_session",
            "rules": [
                "Session-by-session only. No hard sparring — spar days become technical rhythm.",
                "Insert: 2 sessions max. 4 blocks per session max.",
                "D-6/D-5 primers must stay submaximal: use selected drill RPE when present; cap alactic bursts at 3-4 x 6 sec, RPE 6-7, full rest.",
            ],
            "preferred_terms": ["sharpness", "power touch", "technical rhythm", "recovery", "freshness", "mobility / reset"],
            "forbidden_terms": ["primary strength", "anchor day", "conditioning block", "developmental work", "volume build", "all-out bursts", "RPE 8"],
        }
    if mode == "late_fight_session_payload":
        return {
            "mode": mode,
            "framing": "session_by_session",
            "rules": [
                "Session-by-session only. No program block, no phase-explanation dump.",
                "4 blocks per session max. Tight and action-oriented.",
                "D-4 to D-2 primers are rhythm-only unless explicitly selected otherwise; cap at RPE 5-6 and avoid all-out language.",
            ],
            "preferred_terms": ["sharpness session", "technical touch", "low-noise power", "freshness session", "rhythm day", "primer"],
            "forbidden_terms": ["strength block", "conditioning stressor", "glycolytic session", "support strength", "weekly architecture", "all-out bursts", "RPE 8"],
        }
    if mode == "pre_fight_day_payload":
        return {
            "mode": mode,
            "framing": "primer_only",
            "rules": [
                "Primer-only output. 4 blocks max. Under 300 words.",
                "D-1 neural primer is micro-dose only: 1-2 sets or 2-3 minutes total, RPE 3-5; no RPE 6-7, no pump, no fatigue.",
            ],
            "preferred_terms": ["neural primer", "technical touch", "sharpness", "activation", "reset", "rhythm"],
            "forbidden_terms": ["anchor", "strength", "conditioning", "fight-pace density", "block", "glycolytic", "contrast", "RPE 6-7", "RPE 8"],
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
        "countdown_mode_sequence": _countdown_mode_sequence(days_until_fight),
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
        # Public mirror of _selection_priority: underscore keys are stripped by
        # _late_fight_public_role, and composite spacing must still rank roles
        # by their real candidate priority (e.g. the required bridge pressure
        # touch) rather than the static role-key fallback map.
        "selection_priority": selection_priority,
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


def _is_app_owned_visible_role(role_key: Any) -> bool:
    """
    Return whether a role should be rendered as an app-owned visible session.

    Declared boxing load (for example hard sparring) must stay in the
    placement map as context, but should not be rendered as coach-prescribed
    S&C session ownership in insert-style countdown outputs.
    """
    return str(role_key or "").strip().lower() not in {"hard_sparring_day"}


def is_low_cost_coexistable_filler(role: dict[str, Any]) -> bool:
    """True for support fillers that can share a coach-owned combat day."""
    if not isinstance(role, dict):
        return False
    role_key = str(role.get("role_key") or "").strip().lower()
    if role_key in _DAY_EXCLUSIVE_STRESSOR_ROLE_KEYS:
        return False
    if role_key in _COEXISTABLE_FILLER_ROLE_KEYS:
        return True

    category = str(role.get("category") or "").strip().lower()
    stress_class = str(role.get("stress_class") or "").strip().lower()
    cost_class = str(role.get("cost_class") or "").strip().lower()
    governance = role.get("governance") if isinstance(role.get("governance"), dict) else {}
    non_stressor = (
        stress_class == "support"
        or governance.get("meaningful_stress") is False
        or bool(role.get("execution_only"))
        or bool(role.get("nonphysical"))
        or bool(role.get("recovery_compatible"))
    )
    low_cost = cost_class in {"", "low", "zero"} or bool(role.get("low_cost"))
    support_category = category in {
        "support",
        "support_insert",
        "tactical",
        "mental",
        "mindset",
        "recovery",
        "mobility",
        "movement_quality",
        "technical",
    }
    return bool(non_stressor and low_cost and support_category)


def _visible_insert_session_sequence(session_sequence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter post-placement sessions to the app-owned roles only."""
    return [
        session
        for session in session_sequence
        if _is_app_owned_visible_role(session.get("role_key"))
    ]


def _coach_owned_context_session_sequence(session_sequence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return coach-owned boxing context sessions that must stay visible in the calendar."""
    coach_owned: list[dict[str, Any]] = []
    for session in session_sequence:
        role_key = str(session.get("role_key") or "").strip()
        downgraded_from = str(session.get("downgraded_from_role_key") or "").strip()
        is_declared_boxing_context = (
            role_key == "hard_sparring_day"
            or downgraded_from == "hard_sparring_day"
        )
        if not is_declared_boxing_context:
            continue
        if str(session.get("scheduled_day_hint") or "").strip():
            session_copy = dict(session)
            if role_key == "hard_sparring_day" and not session.get("downgraded"):
                session_copy["athlete_facing_label"] = CANONICAL_HARD_SPARRING_LABEL
                session_copy["display_text"] = CANONICAL_HARD_SPARRING_NOTE
            elif role_key == "hard_sparring_day" or downgraded_from == "hard_sparring_day":
                # Downgraded context entries (D-17 ban) and downgraded roles
                # both render as coach-led technical-only combat.
                session_copy["athlete_facing_label"] = CANONICAL_HARD_SPARRING_BAN_LABEL
                session_copy["display_text"] = CANONICAL_HARD_SPARRING_NOTE
            coach_owned.append(session_copy)
    return coach_owned


def _visible_calendar_session_sequence(session_sequence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return calendar-visible sessions (coach-owned boxing context + app-owned inserts)."""
    combined = _coach_owned_context_session_sequence(session_sequence) + _visible_insert_session_sequence(session_sequence)
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | None]] = set()
    for session in combined:
        role_key = str(session.get("role_key") or "")
        label = str(session.get("scheduled_countdown_label") or session.get("countdown_label") or session.get("scheduled_day_hint") or "")
        offset_val = session.get("countdown_offset")
        offset = int(offset_val) if isinstance(offset_val, int) else None
        key = (role_key, label, offset)
        if key in seen:
            continue
        seen.add(key)
        unique.append(session)
    return sorted(unique, key=lambda entry: int(entry.get("countdown_offset") or 0), reverse=True)


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

    hard_sparring_plan = _late_fight_hard_sparring_plan(
        days_until_fight=days,
        athlete_model=athlete_model,
        declared_hard_days=declared_hard_days,
        stage_key=_late_fight_window(days),
    )
    surviving_days = dedupe_preserve_order(
        [
            str(entry.get("day") or "").strip().lower()
            for entry in hard_sparring_plan
            if str(entry.get("effective_load") or "") == "hard"
            and str(entry.get("day") or "").strip()
        ]
    )
    surviving_set = set(surviving_days)
    downgraded_days = [day.lower() for day in declared_hard_days if day.lower() not in surviving_set]
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
            # Pin the lock to the hard-allowed occurrence (D-18+) when known,
            # so a weekday that recurs later in the countdown can never have
            # its hard lock resolved onto a banned D-17-or-closer occurrence.
            hard_lock_label = str(item.get("countdown_label") or "").strip()
            candidates.append(
                _late_fight_role_entry(
                    category="sparring",
                    role_key="hard_sparring_day",
                    preferred_pool="declared_hard_sparring_days",
                    selection_rule="Keep declared hard sparring only when it still lives inside the active legal countdown slice.",
                    placement_rule=(
                        "Keep this declared hard sparring slot fixed on the athlete's stated day inside the active "
                        "countdown window. The coach owns the whole day: render it as hard sparring / controlled hard "
                        "contact and do not stack any programmed S&C on it."
                    ),
                    selection_priority=120,
                    required=True,
                    locked_day=day,
                    preferred_day=day,
                    placement_source="declared_hard_day_lock",
                    legal_countdown_labels=[hard_lock_label] if hard_lock_label else legal_countdown_labels,
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

    if mode == "bridge_compression_payload":
        candidates.append(
            _late_fight_role_entry(
                category="strength",
                role_key="strength_touch_day",
                preferred_pool="strength_slots",
                selection_rule="Use one meaningful strength or power touch only (bridge-window taper-on-ramp).",
                placement_rule="Keep clear of hard sparring and never stack on another hard day.",
                selection_priority=108,
                required=True,
                legal_countdown_labels=legal_countdown_labels,
            )
        )
        glycolytic_touch_added = False
        days = _coerce_days(days_until_fight)
        if (
            days is not None
            and 18 <= days <= 21
            and not preserved_hard_days
            and not _blocks_bridge_extra_glycolytic_touch(athlete_model)
            and not _suppress_standalone_glycolytic(preserved_hard_days, athlete_model)
        ):
            # One controlled pressure exposure around D-20..D-18 is expected in
            # the bridge unless a declared coach hard-sparring day already owns
            # that band (preserved_hard_days) or a readiness blocker fires.
            pressure_labels = [
                label
                for label in legal_countdown_labels
                if (offset := _countdown_offset(str(label))) is not None and 18 <= offset <= 20
            ] or [
                label
                for label in legal_countdown_labels
                if (offset := _countdown_offset(str(label))) is not None and 18 <= offset <= 21
            ]
            candidates.append(
                _late_fight_role_entry(
                    category="conditioning",
                    role_key="light_fight_pace_touch_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="glycolytic",
                    selection_rule=(
                        "D-20 to D-18: one controlled fight-pace pressure touch. This is the bridge window's "
                        "single pressure exposure when no coach hard-sparring day owns D-21 to D-18."
                    ),
                    placement_rule=(
                        "Place it on D-20, D-19, or D-18. Keep it controlled — a short pressure touch, "
                        "not a conditioning build — and never on a coach-owned combat day."
                    ),
                    selection_priority=106,
                    required=True,
                    legal_countdown_labels=pressure_labels or legal_countdown_labels,
                )
            )
            glycolytic_touch_added = True
        if (
            not glycolytic_touch_added
            and not preserved_hard_days
            and bridge_low_risk_profile(athlete_model)
        ):
            # Guarantee one real conditioning exercise across the rest of the
            # bridge (D-17..D-14) for a low-risk athlete. Below D-18 standalone
            # glycolytic work is correctly forbidden, so this is an alactic
            # sharpness touch (low metabolic fatigue, non-glycolytic,
            # freshness-preserving) — the conditioning exposure the lifted
            # active-role cap (_bridge_active_role_cap) makes room for alongside
            # the strength touch + mandatory freshness day. This also covers the
            # freed coach-owned slot when declared hard sparring converts to
            # technical from D-17. Hard sparring / glycolytic / freshness safety
            # caps are untouched.
            candidates.append(
                _late_fight_role_entry(
                    category="conditioning",
                    role_key="alactic_sharpness_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="alactic",
                    selection_rule="One short alactic sharpness touch only. Keep it crisp and non-fatiguing.",
                    placement_rule="Keep this brief and very low volume; never describe it as a conditioning build and never place it on the freshness day.",
                    selection_priority=96,
                    legal_countdown_labels=legal_countdown_labels,
                )
            )
        candidates.append(
            _late_fight_role_entry(
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Freshness/mobility/reset is mandatory in the bridge window.",
                placement_rule="Lowest-load day. Preserve readiness over extra development.",
                selection_priority=104,
                required=True,
                legal_countdown_labels=legal_countdown_labels,
            )
        )
        return candidates

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
                    selection_rule=(
                        "Allow at most one rhythm/freshness touch only when sparring does not already own the window. "
                        "This cannot satisfy a hard conditioning, glycolytic, or combat-pressure quota."
                    ),
                    placement_rule=(
                        "Keep this light (RPE <= 5), never describe it as a conditioning build or progression, "
                        "and never place it between two hard sparring collisions."
                    ),
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
                preferred_pool="declared_support_work_days_or_conditioning_slots",
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


def _late_fight_active_role_count(roles: list[dict[str, Any]]) -> int:
    """Count app-owned active sessions for the ``max_active_roles`` budget.

    Coach-owned placeholders (declared hard sparring) live in the placement map
    as context but are never rendered as app-prescribed sessions
    (``_is_app_owned_visible_role``). They must not consume the app's
    active-role budget — otherwise a required declared hard-spar day in the
    D-21..D-18 bridge window pushes the app's own strength + freshness past the
    cap of 2 and the allocator drops *every* role, leaving that window empty and
    making the visible plan start at D-13 instead of D-21.
    """
    return sum(1 for role in roles if _is_app_owned_visible_role(role.get("role_key")))


def _late_fight_support_role_count(roles: list[dict[str, Any]]) -> int:
    return sum(1 for role in roles if role.get("stress_class") == "support")


def _late_fight_locked_label(role: dict[str, Any], label_to_weekday: dict[str, str]) -> str | None:
    locked_day = str(role.get("locked_day") or "").strip().lower()
    if not locked_day:
        return None
    legal_labels = [
        str(label)
        for label in role.get("legal_countdown_labels", [])
        if str(label).strip() and _countdown_offset(str(label)) is not None
    ]
    legal_labels.sort(key=lambda label: int(_countdown_offset(label) or 0))
    for label in legal_labels:
        weekday = label_to_weekday.get(label)
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
    label_to_display_weekday: dict[str, str] | None = None,
    label_to_resolved_training_weekday: dict[str, str] | None = None,
    hard_weekdays: set[str] | None = None,
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

    best_score: int | None = None
    best_roles: list[dict[str, Any]] | None = None

    assignments: list[dict[int, str]] = []

    def _search_labels(index: int, assigned_labels: dict[int, str], used_unlocked: set[str]) -> None:
        if index >= len(unlocked_roles):
            assignments.append(dict(assigned_labels))
            return
        role = unlocked_roles[index]
        candidate_id = int(role.get("_candidate_id") or 0)
        label_options = _prefer_non_hard_weekday_labels(
            list(open_labels),
            role,
            label_to_weekday,
            hard_weekdays,
        )
        if is_low_cost_coexistable_filler(role):
            label_options.extend(
                label
                for label in sorted(occupied_labels)
                if label not in label_options
            )
        for label in label_options:
            if label in used_unlocked:
                continue
            if label in occupied_labels and not is_low_cost_coexistable_filler(role):
                continue
            assigned_labels[candidate_id] = label
            _search_labels(index + 1, assigned_labels, used_unlocked | {label})
            assigned_labels.pop(candidate_id, None)

    _search_labels(0, dict(locked_labels), set())

    for assigned_labels in assignments:

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
            display_weekday = str(
                (label_to_display_weekday or {}).get(assigned_label) or real_weekday
            ).strip()
            if real_weekday:
                role_copy["scheduled_day_hint"] = real_weekday
                role_copy["real_weekday"] = real_weekday
            resolved_training_weekday = str(
                (label_to_resolved_training_weekday or {}).get(assigned_label) or ""
            ).strip()
            if resolved_training_weekday and resolved_training_weekday != real_weekday:
                role_copy["resolved_training_weekday"] = resolved_training_weekday
                role_copy["availability_adjustment"] = {
                    "raw_weekday": real_weekday,
                    "resolved_training_weekday": resolved_training_weekday,
                    "reason": "nearest_available_day",
                }
            if display_weekday:
                role_copy["countdown_weekday"] = display_weekday
                role_copy["countdown_display_label"] = _countdown_display_label(assigned_label, display_weekday)
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
        if hard_weekdays:
            # Coach-owned combat lock: keep programmed S&C off declared spar
            # weekdays whenever any other legal day can host it. Low-cost
            # fillers are allowed to attach under the coach-owned combat day.
            for scored_role in scored_roles:
                if not _is_app_owned_visible_role(scored_role.get("role_key")):
                    continue
                if is_low_cost_coexistable_filler(scored_role):
                    continue
                assigned_weekday = str(scored_role.get("real_weekday") or "").strip().lower()
                if assigned_weekday in hard_weekdays:
                    score -= 100000
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
                "legal_countdown_labels": (labels := _late_fight_legal_countdown_labels(days_until_fight)),
                "eligible_countdown_labels": labels,
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
    eligible_countdown_labels = list(permission_policy.get("eligible_countdown_labels", legal_countdown_labels))
    label_to_weekday = {
        label: str(permission_policy.get("countdown_weekday_map", {}).get(label) or "").strip().lower()
        for label in legal_countdown_labels
        if str(permission_policy.get("countdown_weekday_map", {}).get(label) or "").strip()
    }
    label_to_display_weekday = dict(label_to_weekday)
    label_to_resolved_training_weekday = {
        str(item.get("countdown_label") or ""): str(item.get("resolved_weekday") or "").strip().lower()
        for item in permission_policy.get("availability_adjustments", [])
        if str(item.get("countdown_label") or "").strip() and str(item.get("resolved_weekday") or "").strip()
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

    # Required roles are mandatory by definition: the budget caps may only limit
    # how many *optional* roles ride on top of them. If a required set already
    # meets or exceeds a cap, raising the effective cap to the required floor
    # keeps the required-only baseline selectable instead of skipping every
    # subset and silently emitting an empty window (which made plans start a
    # week late). On healthy windows required < cap, so the effective cap equals
    # the original cap and behaviour is unchanged.
    required_active = _late_fight_active_role_count(required_roles)
    required_stress = _late_fight_meaningful_stress_count(required_roles)
    required_support = _late_fight_support_role_count(required_roles)
    effective_max_active = max(max_active_roles, required_active) if isinstance(max_active_roles, int) else None
    effective_max_stress = max(max_meaningful_stress_exposures, required_stress) if isinstance(max_meaningful_stress_exposures, int) else None
    effective_max_support = max(max_support_roles, required_support) if isinstance(max_support_roles, int) else None

    best_roles: list[dict[str, Any]] = []
    best_score: int | None = None
    for optional_count in range(len(optional_roles) + 1):
        for optional_subset in combinations(optional_roles, optional_count):
            selected_roles = required_roles + list(optional_subset)
            if effective_max_active is not None and _late_fight_active_role_count(selected_roles) > effective_max_active:
                continue
            if effective_max_stress is not None and _late_fight_meaningful_stress_count(selected_roles) > effective_max_stress:
                continue
            if effective_max_support is not None and _late_fight_support_role_count(selected_roles) > effective_max_support:
                continue
            assignment = _late_fight_best_assignment(
                selected_roles,
                eligible_countdown_labels,
                label_to_weekday,
                label_to_display_weekday,
                label_to_resolved_training_weekday,
                hard_weekdays=_declared_hard_weekdays(athlete_model),
            )
            if assignment is None:
                continue
            score, assigned_roles = assignment
            if best_score is None or score > best_score:
                best_score = score
                best_roles = assigned_roles

    if required_roles and not best_roles:
        # Invariant breach: an active window has required roles but none could be
        # placed (every subset failed _late_fight_best_assignment — e.g. a locked
        # declared-hard-spar weekday with no legal countdown label). We never
        # fabricate illegal placements here; surface it loudly so the CI sweep
        # fails and prod is observable, rather than silently shipping an empty
        # window that makes the plan start late.
        logger.warning(
            "late_fight_allocation_empty_active_window days_until_fight=%s mode=%s required_roles=%s",
            days_until_fight,
            mode,
            [role.get("role_key") for role in required_roles],
        )

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
            "eligible_countdown_labels": eligible_countdown_labels,
            "locked_days": [role.get("locked_day") for role in public_roles if role.get("locked_day")],
            "blocked_days": [],
            "countdown_weekday_map": {
                label: permission_policy.get("raw_countdown_weekday_map", {}).get(label)
                for label in legal_countdown_labels
                if permission_policy.get("raw_countdown_weekday_map", {}).get(label)
            },
            "availability_adjustments": list(permission_policy.get("availability_adjustments", [])),
        },
    }


def _late_fight_session_roles(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    return list(_late_fight_allocation_plan(days_until_fight, athlete_model).get("session_roles", []))


def _build_late_fight_session_sequence(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    """Return the visible/app-owned late-fight session sequence.

    Coach-owned ``hard_sparring_day`` placeholders (including downgraded
    context entries appended for D-17 downgrade tracking) are filtered out
    so the brief surfaces only the sessions the athlete actually does. The
    full list — including the coach-owned context — remains available on
    ``late_fight_plan_spec.session_sequence``.
    """
    session_roles = list(_late_fight_practical_allocation_plan(days_until_fight, athlete_model).get("session_roles", []))
    return [
        role
        for role in session_roles
        if _is_app_owned_visible_role(role.get("role_key"))
    ]


def _is_bridge_countdown(days_until_fight: Any) -> bool:
    days = _coerce_days(days_until_fight)
    return isinstance(days, int) and 14 <= days <= 21


def _is_countdown_continuation_start(days_until_fight: Any) -> bool:
    days = _coerce_days(days_until_fight)
    return isinstance(days, int) and 3 <= days <= 21


def _shifted_segment_athlete_model(
    days_until_fight: Any,
    segment_start_day: int,
    athlete_model: dict[str, Any],
) -> dict[str, Any]:
    segment_athlete = dict(athlete_model)
    segment_athlete["days_until_fight"] = segment_start_day
    days = _coerce_days(days_until_fight)
    plan_weekday = str(athlete_model.get("plan_creation_weekday") or "").strip().lower()
    plan_index = _WEEKDAY_ORDER.get(plan_weekday)
    if isinstance(days, int) and plan_index is not None and segment_start_day <= days:
        segment_athlete["plan_creation_weekday"] = _WEEKDAY_NAMES[(plan_index + (days - segment_start_day)) % 7]
    return segment_athlete


def _segment_legal_countdown_labels(role: dict[str, Any], start_day: int, end_day: int) -> list[str]:
    labels = [
        str(label)
        for label in role.get("legal_countdown_labels", [])
        if (offset := _countdown_offset(str(label))) is not None
        and offset > 0
        and end_day <= offset <= start_day
    ]
    if labels:
        return labels
    return [f"D-{offset}" for offset in range(start_day, end_day - 1, -1) if offset > 0]


def _copy_composite_segment_role(
    role: dict[str, Any],
    *,
    segment: dict[str, Any],
    segment_index: int,
) -> dict[str, Any]:
    start_day = int(segment["start_day"])
    end_day = int(segment["end_day"])
    role_copy = dict(role)
    role_copy["legal_countdown_labels"] = _segment_legal_countdown_labels(role, start_day, end_day)
    role_copy["composite_source"] = "bridge_countdown_practical_allocation"
    role_copy["composite_segment_index"] = segment_index
    role_copy["composite_segment_stage_key"] = segment.get("stage_key")
    role_copy["composite_segment_payload_mode"] = segment.get("payload_mode")
    role_copy["countdown_span"] = {"start_day": start_day, "end_day": end_day}
    role_copy["_original_countdown_label"] = role.get("scheduled_countdown_label") or role.get("countdown_label")
    return role_copy


def _full_countdown_weekday_map(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, str]:
    return _countdown_weekday_map(
        _resolve_plan_creation_weekday(days_until_fight, athlete_model),
        days_until_fight,
    )


def _declared_hard_weekdays(athlete_model: dict[str, Any]) -> set[str]:
    return {
        str(day).strip().lower()
        for day in _ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", [])))
        if str(day).strip()
    }


def _meaningful_app_owned_role(role: dict[str, Any]) -> bool:
    return (
        _is_app_owned_visible_role(role.get("role_key"))
        and str(role.get("stress_class") or "").strip() == "meaningful_stress"
    )


def _role_has_non_hard_weekday_option(
    role: dict[str, Any],
    label_to_weekday: dict[str, str],
    hard_weekdays: set[str],
) -> bool:
    return any(
        str(label_to_weekday.get(str(label)) or "").strip().lower() not in hard_weekdays
        for label in role.get("legal_countdown_labels", [])
    )


def _prefer_non_hard_weekday_labels(
    labels: list[str],
    role: dict[str, Any],
    label_to_weekday: dict[str, str],
    hard_weekdays: set[str] | None,
) -> list[str]:
    if not hard_weekdays or not _is_app_owned_visible_role(role.get("role_key")):
        return labels
    if is_low_cost_coexistable_filler(role):
        return labels
    non_hard_labels = [
        label
        for label in labels
        if str(label_to_weekday.get(label) or "").strip().lower() not in hard_weekdays
    ]
    return non_hard_labels or labels


def _assign_role_to_countdown_label(
    role: dict[str, Any],
    label: str,
    label_to_weekday: dict[str, str],
    label_to_display_weekday: dict[str, str] | None = None,
    label_to_resolved_training_weekday: dict[str, str] | None = None,
) -> dict[str, Any]:
    role_copy = dict(role)
    role_copy["scheduled_countdown_label"] = label
    role_copy["countdown_label"] = label
    offset = _countdown_offset(label)
    if offset is not None:
        role_copy["countdown_offset"] = offset
    weekday = str(label_to_weekday.get(label) or "").strip()
    display_weekday = str((label_to_display_weekday or {}).get(label) or weekday).strip()
    if weekday:
        role_copy["scheduled_day_hint"] = weekday
        role_copy["real_weekday"] = weekday
    resolved_training_weekday = str((label_to_resolved_training_weekday or {}).get(label) or "").strip()
    if resolved_training_weekday and resolved_training_weekday != weekday:
        role_copy["resolved_training_weekday"] = resolved_training_weekday
        role_copy["availability_adjustment"] = {
            "raw_weekday": weekday,
            "resolved_training_weekday": resolved_training_weekday,
            "reason": "nearest_available_day",
        }
    if display_weekday:
        role_copy["countdown_weekday"] = display_weekday
        role_copy["countdown_display_label"] = _countdown_display_label(label, display_weekday)
    else:
        role_copy.pop("scheduled_day_hint", None)
        role_copy.pop("real_weekday", None)
        role_copy["countdown_display_label"] = label
    role_copy["day_assignment_reason"] = _late_fight_assignment_reason(role_copy)
    return role_copy


def _composite_role_selection_priority(role: dict[str, Any]) -> int:
    for key in ("_selection_priority", "selection_priority"):
        value = role.get(key)
        if isinstance(value, int) and value != 0:
            return value
    return int(_LATE_FIGHT_ROLE_SELECTION_PRIORITY.get(str(role.get("role_key") or ""), 0))


def _composite_role_selection_score(selected_roles: list[dict[str, Any]], days_until_fight: Any) -> int:
    score = 0
    role_key_counts: dict[str, int] = {}
    stage_keys: set[str] = set()
    for role in selected_roles:
        role_key = str(role.get("role_key") or "")
        role_key_counts[role_key] = role_key_counts.get(role_key, 0) + 1
        priority = _composite_role_selection_priority(role)
        segment_index = int(role.get("composite_segment_index") or 0)
        offset = int(role.get("countdown_offset") or 0)
        score += priority * 1000
        score += segment_index * 600
        if _is_app_owned_visible_role(role_key):
            score += 3500
        if offset:
            score += offset * 10
        stage_key = str(role.get("composite_segment_stage_key") or "").strip()
        if stage_key:
            stage_keys.add(stage_key)
        if _is_bridge_countdown(days_until_fight) and stage_key == "d21_to_d14":
            score += 6000

    for count in role_key_counts.values():
        if count > 1:
            score -= (count - 1) * 1200

    if "d1" in stage_keys:
        score += 1500
    if _is_bridge_countdown(days_until_fight) and "d21_to_d14" in stage_keys:
        # Require visible bridge representation when the composite plan runs
        # from a bridge-window day; without this bonus the per-role visible
        # bonus on downstream stages drowns out the bridge segment and the
        # plan collapses to D-7→D-1 only.
        score += 12000
    elif _is_bridge_countdown(days_until_fight):
        # Strong penalty so any other selection that keeps the bridge segment
        # outranks an otherwise-better downstream-only selection.
        score -= 18000
    score += len(stage_keys) * 250
    return score


def _composite_role_key_cap(role_key: str, days_until_fight: Any) -> int | None:
    if role_key == "hard_sparring_day":
        return _declared_hard_spar_cap(days_until_fight)
    if _is_bridge_countdown(days_until_fight):
        return None
    if role_key in {
        "strength_touch_day",
        "neural_primer_day",
        "alactic_sharpness_day",
        "light_fight_pace_touch_day",
        "fight_week_freshness_day",
    }:
        return 1
    return None


def _score_composite_practical_assignment(
    assigned_roles: list[dict[str, Any]],
    label_to_weekday: dict[str, str],
    hard_weekdays: set[str],
) -> int:
    score = 0
    visible_roles = [
        role
        for role in assigned_roles
        if _is_app_owned_visible_role(role.get("role_key"))
        and isinstance(role.get("countdown_offset"), int)
    ]
    for role in assigned_roles:
        offset = int(role.get("countdown_offset") or 0)
        original_offset = _countdown_offset(str(role.get("_original_countdown_label") or ""))
        cost_class = str(role.get("cost_class") or "")
        if cost_class in {"high", "medium"}:
            score += offset * 40
        if role.get("role_key") == "fight_week_freshness_day":
            legal_offsets = [
                _countdown_offset(str(label))
                for label in role.get("legal_countdown_labels", [])
                if _countdown_offset(str(label)) is not None
            ]
            if legal_offsets:
                score -= abs(offset - min(legal_offsets)) * 45
        if original_offset is not None:
            score -= abs(offset - original_offset) * 8
        if _is_app_owned_visible_role(role.get("role_key")):
            # Declared spar weekdays are coach-owned combat days. Keep app-owned
            # stressors off them, but allow low-cost fillers to attach under the
            # coach-owned combat role.
            weekday = str(label_to_weekday.get(str(role.get("scheduled_countdown_label") or "")) or "").strip().lower()
            if (
                not is_low_cost_coexistable_filler(role)
                and weekday in hard_weekdays
                and _role_has_non_hard_weekday_option(role, label_to_weekday, hard_weekdays)
            ):
                score -= 8000

    ordered_visible = sorted(visible_roles, key=lambda role: int(role.get("countdown_offset") or 0), reverse=True)
    for first_role, second_role in zip(ordered_visible, ordered_visible[1:]):
        first_offset = int(first_role.get("countdown_offset") or 0)
        second_offset = int(second_role.get("countdown_offset") or 0)
        gap = first_offset - second_offset
        score += gap * 20
        if gap == 1:
            score -= 10000
            if (
                first_role.get("stress_class") == "meaningful_stress"
                or second_role.get("stress_class") == "meaningful_stress"
            ):
                score -= 3000
    return score


def _assignment_labels_for_role(
    role: dict[str, Any],
    *,
    label_to_weekday: dict[str, str],
    training_days: list[str],
) -> list[str]:
    role_key = str(role.get("role_key") or "").strip().lower()
    labels = [
        str(label)
        for label in role.get("legal_countdown_labels", [])
        if str(label).strip() and _countdown_offset(str(label)) is not None
    ]
    if role_key == "hard_sparring_day":
        return labels
    if _is_app_owned_visible_role(role_key):
        return [
            label
            for label in labels
            if can_render_late_taper_day(
                countdown_offset=int(_countdown_offset(label) or 0),
                weekday=str(label_to_weekday.get(label) or ""),
                training_days=training_days,
            )
        ]
    return labels


def _space_bridge_countdown_roles(
    roles: list[dict[str, Any]],
    *,
    days_until_fight: Any,
    athlete_model: dict[str, Any],
) -> list[dict[str, Any]]:
    if not roles:
        return []
    role_budget = _late_fight_role_budget(days_until_fight, athlete_model)
    max_meaningful_stress_exposures = role_budget.get("max_meaningful_stress_exposures")
    max_support_roles = role_budget.get("max_support_roles")
    max_visible_roles = None
    if isinstance(max_meaningful_stress_exposures, int) and isinstance(max_support_roles, int):
        max_visible_roles = max_meaningful_stress_exposures + max_support_roles
    hard_spar_cap = _declared_hard_spar_cap(days_until_fight)
    label_to_weekday = _full_countdown_weekday_map(days_until_fight, athlete_model)
    label_to_display_weekday = dict(label_to_weekday)
    hard_weekdays = _declared_hard_weekdays(athlete_model)
    training_days = clean_list(athlete_model.get("training_days", []))
    label_to_resolved_training_weekday = {
        label: str(_nearest_available_day(weekday, training_days) or "").strip().lower()
        for label, weekday in label_to_weekday.items()
        if str(weekday or "").strip()
    }
    ordered_roles = sorted(
        roles,
        key=lambda role: (
            int(role.get("composite_segment_index") or 0),
            -int(role.get("countdown_offset") or 0),
            -_composite_role_selection_priority(role),
            str(role.get("role_key") or ""),
        ),
    )

    best_score: int | None = None
    best_roles: list[dict[str, Any]] | None = None

    # A composite that starts in the D-21..D-18 band may carry the required
    # controlled pressure touch on top of the usual bridge exposures. Give the
    # whole-window caps exactly one extra slot for it so the pressure exposure
    # never has to evict a later sharpness-window role.
    has_bridge_pressure_touch = any(
        str(role.get("role_key") or "") == "light_fight_pace_touch_day"
        and str(role.get("composite_segment_stage_key") or "") == "d21_to_d14"
        for role in roles
    )
    if has_bridge_pressure_touch:
        if isinstance(max_meaningful_stress_exposures, int):
            max_meaningful_stress_exposures += 1
        if isinstance(max_visible_roles, int):
            max_visible_roles += 1

    def _search(
        index: int,
        occupied_labels: set[str],
        assigned: list[dict[str, Any]],
        visible_active_count: int,
        visible_meaningful_count: int,
        visible_support_count: int,
        hard_spar_count: int,
        role_key_counts: dict[str, int],
    ) -> None:
        nonlocal best_score, best_roles
        if isinstance(max_visible_roles, int) and visible_active_count > max_visible_roles:
            return
        if isinstance(max_meaningful_stress_exposures, int) and visible_meaningful_count > max_meaningful_stress_exposures:
            return
        if isinstance(max_support_roles, int) and visible_support_count > max_support_roles:
            return
        if isinstance(hard_spar_cap, int) and hard_spar_count > hard_spar_cap:
            return
        if index >= len(ordered_roles):
            score = _score_composite_practical_assignment(assigned, label_to_weekday, hard_weekdays)
            score += _composite_role_selection_score(assigned, days_until_fight)
            if best_score is None or score > best_score:
                best_score = score
                best_roles = list(assigned)
            return

        role = ordered_roles[index]
        role_is_meaningful = str(role.get("stress_class") or "").strip() == "meaningful_stress"
        role_is_support = str(role.get("stress_class") or "").strip() == "support"
        role_key = str(role.get("role_key") or "")
        role_is_visible = _is_app_owned_visible_role(role_key)
        role_is_hard_spar = role_key == "hard_sparring_day"

        _search(
            index + 1,
            occupied_labels,
            assigned,
            visible_active_count,
            visible_meaningful_count,
            visible_support_count,
            hard_spar_count,
            role_key_counts,
        )

        labels = _assignment_labels_for_role(
            role,
            label_to_weekday=label_to_weekday,
            training_days=training_days,
        )
        labels = _prefer_non_hard_weekday_labels(
            labels,
            role,
            label_to_weekday,
            hard_weekdays,
        )
        if not labels:
            if role_is_visible:
                return
            existing = str(role.get("scheduled_countdown_label") or role.get("countdown_label") or "").strip()
            labels = [existing] if existing else []
        locked_label = _late_fight_locked_label(role, label_to_weekday)
        if locked_label:
            labels = [locked_label]

        next_role_key_counts = dict(role_key_counts)
        next_role_key_counts[role_key] = next_role_key_counts.get(role_key, 0) + 1
        role_key_cap = _composite_role_key_cap(role_key, days_until_fight)
        if isinstance(role_key_cap, int) and next_role_key_counts[role_key] > role_key_cap:
            return

        for label in labels:
            if label in occupied_labels and not (
                is_low_cost_coexistable_filler(role)
                and any(
                    str(assigned_role.get("role_key") or "") == "hard_sparring_day"
                    and str(
                        assigned_role.get("scheduled_countdown_label")
                        or assigned_role.get("countdown_label")
                        or ""
                    ) == label
                    for assigned_role in assigned
                )
                and not any(
                    _is_app_owned_visible_role(assigned_role.get("role_key"))
                    and str(
                        assigned_role.get("scheduled_countdown_label")
                        or assigned_role.get("countdown_label")
                        or ""
                    ) == label
                    for assigned_role in assigned
                )
            ):
                continue
            assigned_role = _assign_role_to_countdown_label(
                role,
                label,
                label_to_weekday,
                label_to_display_weekday,
                label_to_resolved_training_weekday,
            )
            _search(
                index + 1,
                occupied_labels | {label},
                assigned + [assigned_role],
                visible_active_count + (1 if role_is_visible else 0),
                visible_meaningful_count + (1 if role_is_visible and role_is_meaningful else 0),
                visible_support_count + (1 if role_is_visible and role_is_support else 0),
                hard_spar_count + (1 if role_is_hard_spar else 0),
                next_role_key_counts,
            )

    _search(0, set(), [], 0, 0, 0, 0, {})
    final_roles = best_roles or roles
    final_roles = sorted(
        final_roles,
        key=lambda role: int(role.get("countdown_offset") or 0),
        reverse=True,
    )
    public_roles: list[dict[str, Any]] = []
    for session_index, role in enumerate(final_roles, start=1):
        role_copy = dict(role)
        role_copy["session_index"] = session_index
        public_roles.append(_late_fight_public_role(role_copy))
    return public_roles


def _bridge_countdown_practical_allocation_plan(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any]:
    mode = _days_out_payload_mode(days_until_fight)
    roles: list[dict[str, Any]] = []
    suppressed_roles: list[dict[str, Any]] = []
    segment_allocations: list[dict[str, Any]] = []

    for segment_index, segment in enumerate(_countdown_mode_sequence(days_until_fight), start=1):
        start_day = segment.get("start_day")
        end_day = segment.get("end_day")
        if not isinstance(start_day, int) or not isinstance(end_day, int) or start_day <= 0:
            continue
        segment_athlete = _shifted_segment_athlete_model(days_until_fight, start_day, athlete_model)
        allocation = _late_fight_allocation_plan(start_day, segment_athlete)
        segment_roles = [
            _copy_composite_segment_role(role, segment=segment, segment_index=segment_index)
            for role in allocation.get("session_roles", [])
            if isinstance(role.get("countdown_offset"), int)
            and role["countdown_offset"] > 0
        ]
        roles.extend(segment_roles)
        for role in allocation.get("suppressed_roles", []):
            suppressed = dict(role)
            suppressed["composite_segment_index"] = segment_index
            suppressed["composite_segment_stage_key"] = segment.get("stage_key")
            suppressed["composite_segment_payload_mode"] = segment.get("payload_mode")
            suppressed_roles.append(suppressed)
        segment_allocations.append(
            {
                "segment_index": segment_index,
                "stage_key": segment.get("stage_key"),
                "payload_mode": segment.get("payload_mode"),
                "countdown_span": {"start_day": start_day, "end_day": end_day},
                "selected_roles": len(segment_roles),
                "role_budget": allocation.get("role_budget", {}),
            }
        )

    public_roles = _space_bridge_countdown_roles(
        roles,
        days_until_fight=days_until_fight,
        athlete_model=athlete_model,
    )
    visible_roles = _visible_insert_session_sequence(public_roles)
    label_to_weekday = _full_countdown_weekday_map(days_until_fight, athlete_model)
    top_level_budget = _late_fight_role_budget(days_until_fight, athlete_model)
    legal_labels = dedupe_preserve_order(
        str(label)
        for role in public_roles
        for label in role.get("legal_countdown_labels", [])
        if str(label).strip()
    )
    role_budget = {
        "mode": mode,
        "composite_practical_allocation": True,
        "max_active_roles": len(visible_roles),
        "max_meaningful_stress_exposures": top_level_budget.get("max_meaningful_stress_exposures"),
        "max_support_roles": top_level_budget.get("max_support_roles"),
        "selected_active_roles": len(public_roles),
        "selected_visible_roles": len(visible_roles),
        "selected_meaningful_stress_exposures": _late_fight_meaningful_stress_count(public_roles),
        "selected_support_roles": _late_fight_support_role_count(public_roles),
        "legal_countdown_labels": legal_labels,
    }
    return {
        "mode": mode,
        "permission_policy": _late_fight_permission_policy(days_until_fight, athlete_model),
        "role_budget": role_budget,
        "session_roles": public_roles,
        "suppressed_roles": suppressed_roles,
        "allocator": {
            "composite_practical_allocation": True,
            "legal_countdown_labels": legal_labels,
            "locked_days": [role.get("locked_day") for role in public_roles if role.get("locked_day")],
            "blocked_days": [],
            "countdown_weekday_map": {
                label: label_to_weekday.get(label)
                for label in legal_labels
                if label_to_weekday.get(label)
            },
            "availability_adjustments": [],
            "countdown_mode_sequence": _countdown_mode_sequence(days_until_fight),
            "segment_allocations": segment_allocations,
        },
    }


def _composite_segment_lookup_for_offset(days_until_fight: Any) -> dict[int, dict[str, Any]]:
    """Map each countdown offset to its composite-window segment metadata."""
    lookup: dict[int, dict[str, Any]] = {}
    for segment_index, segment in enumerate(_countdown_mode_sequence(days_until_fight), start=1):
        start_day = segment.get("start_day")
        end_day = segment.get("end_day")
        if not isinstance(start_day, int) or not isinstance(end_day, int):
            continue
        for offset in range(end_day, start_day + 1):
            if offset not in lookup:
                lookup[offset] = {
                    "segment_index": segment_index,
                    "stage_key": segment.get("stage_key"),
                    "payload_mode": segment.get("payload_mode"),
                    "start_day": start_day,
                    "end_day": end_day,
                }
    return lookup


def _append_declared_hard_spar_context(
    allocation: dict[str, Any],
    days_until_fight: Any,
    athlete_model: dict[str, Any],
) -> dict[str, Any]:
    """Append coach-owned ``hard_sparring_day`` context entries to the plan.

    Declared boxing days that the D-17 ban downgraded to technical/rhythm
    still belong to the gym/coach. ``_late_fight_allocation_plan`` builds
    them as ``technical_touch_day`` candidates that compete (and usually
    lose) for app-side insert slots. The session_roles list, however, must
    still surface the day as ``hard_sparring_day`` so callers can see
    which days the coach owns; the visibility filter in
    ``_is_app_owned_visible_role`` already keeps ``hard_sparring_day`` out
    of athlete-facing insert sessions.

    The context entries are appended once per declared spar instance, at
    the actual countdown offset for that weekday, with the matching
    composite segment metadata so downstream weekly-role-map builders
    place them in the right window.
    """
    permission_policy = allocation.get("permission_policy", {}) or {}
    actions = list(permission_policy.get("declared_hard_day_actions", []))
    if not actions:
        return allocation

    countdown_map = _full_countdown_weekday_map(days_until_fight, athlete_model)
    if not countdown_map:
        return allocation

    composite_lookup = _composite_segment_lookup_for_offset(days_until_fight)
    composite_allocation = bool(
        (allocation.get("allocator", {}) or {}).get("composite_practical_allocation")
    )

    session_roles = list(allocation.get("session_roles", []))
    existing_locked: set[tuple[str, int | None]] = set()
    for role in session_roles:
        if str(role.get("role_key") or "") != "hard_sparring_day":
            continue
        day = str(role.get("locked_day") or role.get("scheduled_day_hint") or "").strip().lower()
        offset = role.get("countdown_offset")
        existing_locked.add((day, int(offset) if isinstance(offset, int) else None))

    new_entries: list[dict[str, Any]] = []
    for action in actions:
        declared_day = str(action.get("day") or "").strip().lower()
        if not declared_day:
            continue
        is_hard_locked = str(action.get("outcome") or "") == "hard_sparring_day"
        hard_lock_offset = action.get("countdown_offset")
        for label, weekday in countdown_map.items():
            if str(weekday or "").strip().lower() != declared_day:
                continue
            offset = _countdown_offset(label)
            if offset is None or offset <= 0:
                continue
            if is_hard_locked and (offset == hard_lock_offset or offset >= 18):
                # The hard-allowed occurrence is already carried by the locked
                # hard_sparring_day role; only later (D-17 or closer)
                # recurrences of this weekday become technical-only context.
                continue
            key = (declared_day, offset)
            if key in existing_locked:
                continue
            existing_locked.add(key)
            segment_meta = composite_lookup.get(offset, {})
            context_role: dict[str, Any] = {
                "session_index": len(session_roles) + len(new_entries) + 1,
                "category": "sparring",
                "role_key": "hard_sparring_day",
                "preferred_pool": "declared_hard_sparring_days",
                "selection_rule": (
                    "Coach-owned boxing day converted to technical-only combat "
                    "under the D-17 hard-sparring ban; render it as a coach-owned "
                    "label, never as a programmed S&C session. The coach owns the "
                    "whole day — do not stack any programmed S&C on it."
                ),
                "anchor": _role_anchor("hard_sparring_day"),
                "placement_rule": (
                    "Keep this declared boxing day fixed on the athlete's stated weekday. "
                    "Always surface the coach-owned label on that day and keep the day "
                    "clean: no programmed S&C session is scheduled on a coach-owned "
                    "combat day."
                ),
                "cost_class": _late_fight_cost_class("hard_sparring_day"),
                "stress_class": _late_fight_stress_class("hard_sparring_day"),
                "placement_source": "declared_hard_day_downgrade_context",
                "legal_countdown_labels": [label],
                "governance": {"late_fight_payload": True, "coach_owned": True},
                "locked_day": declared_day,
                "scheduled_day_hint": declared_day,
                "real_weekday": declared_day,
                "scheduled_countdown_label": label,
                "countdown_label": label,
                "countdown_display_label": _countdown_display_label(label, declared_day),
                "countdown_weekday": declared_day,
                "countdown_offset": offset,
                "declared_day_locked": True,
                "coach_owned": True,
                "downgraded": True,
                "downgraded_to_role_key": "technical_touch_day",
                "downgrade_reason_code": "d17_hard_sparring_ban",
                "day_assignment_reason": (
                    "Coach-owned boxing day fixed by declaration; downgraded to "
                    "technical/rhythm under the D-17 hard-sparring ban."
                ),
                "placement_basis": "locked",
            }
            if composite_allocation and segment_meta:
                context_role["composite_source"] = "bridge_countdown_practical_allocation"
                context_role["composite_segment_index"] = segment_meta.get("segment_index")
                context_role["composite_segment_stage_key"] = segment_meta.get("stage_key")
                context_role["composite_segment_payload_mode"] = segment_meta.get("payload_mode")
                context_role["countdown_span"] = {
                    "start_day": segment_meta.get("start_day"),
                    "end_day": segment_meta.get("end_day"),
                }
            new_entries.append(context_role)

    if not new_entries:
        return allocation

    augmented = dict(allocation)
    augmented["session_roles"] = session_roles + new_entries
    return augmented


def _late_fight_practical_allocation_plan(days_until_fight: Any, athlete_model: dict[str, Any]) -> dict[str, Any]:
    if _is_countdown_continuation_start(days_until_fight):
        allocation = _bridge_countdown_practical_allocation_plan(days_until_fight, athlete_model)
    else:
        allocation = _late_fight_allocation_plan(days_until_fight, athlete_model)
    return _append_declared_hard_spar_context(allocation, days_until_fight, athlete_model)


def _late_fight_stage_label(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "bridge_compression_payload":
        return "Bridge Compression Week"
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
    if mode == "bridge_compression_payload":
        return (
            "Use a bridge compression week: taper-on-ramp rather than full camp. "
            "Declared hard sparring days in D-21 to D-18 are coach-owned and stay hard. Keep one meaningful strength touch, "
            "one freshness/mobility reset, and one controlled pressure touch on D-20 to D-18 when no coach hard-sparring day owns that band. "
            "From D-17 onward, all declared hard sparring is coach-led technical-only combat. Never stack programmed S&C on a coach-owned combat day. No double-stress days."
        )
    if mode == "pre_fight_compressed_payload":
        return (
            "Use a compressed pre-fight week. No effective hard sparring is allowed: all declared hard sparring "
            "from D-17 onward converts to technical/rhythm only. Keep one meaningful strength touch, an optional "
            "light fight-rhythm touch, and one freshness / mobility reset day."
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
    if _is_countdown_continuation_start(days_until_fight):
        return {"weeks": _build_bridge_then_late_countdown_weeks(days_until_fight, athlete_model, phase_briefs)}
    if _days_out_payload_mode(days_until_fight) in {
        "fight_day_protocol_payload",
        "pre_fight_day_payload",
        "late_fight_session_payload",
        "late_fight_transition_payload",
    }:
        return {"weeks": []}
    phase = _resolve_late_fight_phase(phase_briefs)
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


def _build_bridge_then_late_countdown_weeks(days_until_fight: Any, athlete_model: dict, phase_briefs: dict[str, dict]) -> list[dict[str, Any]]:
    days = _coerce_days(days_until_fight)
    if not _is_countdown_continuation_start(days):
        return []
    phase = _resolve_late_fight_phase(phase_briefs)

    segment_days = [
        (int(segment["start_day"]), int(segment["end_day"]))
        for segment in _countdown_mode_sequence(days_until_fight)
        if isinstance(segment.get("start_day"), int) and isinstance(segment.get("end_day"), int)
    ]
    weeks: list[dict[str, Any]] = []
    for week_index, (start_day, end_day) in enumerate(segment_days, start=1):
        segment_mode = _days_out_payload_mode(start_day)
        segment_athlete = _shifted_segment_athlete_model(days_until_fight, start_day, athlete_model)
        segment_allocation = _late_fight_allocation_plan(start_day, segment_athlete)
        segment_roles = [
            _copy_composite_segment_role(role, segment={"start_day": start_day, "end_day": end_day}, segment_index=week_index)
            for role in segment_allocation.get("session_roles", [])
            if isinstance(role.get("countdown_offset"), int)
            and role["countdown_offset"] > 0
        ]
        session_counts = {
            "strength": sum(1 for role in segment_roles if role.get("category") == "strength"),
            "conditioning": sum(1 for role in segment_roles if role.get("category") == "conditioning"),
            "recovery": sum(1 for role in segment_roles if role.get("category") == "recovery"),
        }
        technical_count = sum(1 for role in segment_roles if role.get("category") == "technical")
        if technical_count:
            session_counts["technical"] = technical_count
        conditioning_sequence = [
            role.get("preferred_system")
            for role in segment_roles
            if role.get("category") == "conditioning" and role.get("preferred_system")
        ]
        weeks.append(
            {
                "week_index": week_index,
                "phase": phase,
                "stage_key": _late_fight_window(start_day),
                "stage_label": _late_fight_stage_label(start_day),
                "stage_objective": _late_fight_summary(start_day),
                "phase_week_index": 1,
                "phase_week_total": 1,
                "countdown_span": {"start_day": start_day, "end_day": end_day},
                "payload_mode": segment_mode,
                "session_counts": session_counts,
                "conditioning_sequence": conditioning_sequence or ["alactic"],
                "role_budget": segment_allocation.get("role_budget", {}),
                "intentional_compression": {
                    "active": True,
                    "reason_codes": [segment_mode],
                    "reason": segment_mode,
                    "summary": _late_fight_summary(start_day),
                },
            }
        )
    return weeks


def _resolve_late_fight_phase(phase_briefs: dict[str, dict]) -> str:
    return next((phase_name for phase_name in ("TAPER", "SPP", "GPP") if phase_name in phase_briefs), next(iter(phase_briefs), "TAPER"))


def _build_late_fight_weekly_role_map(
    days_until_fight: Any,
    athlete_model: dict,
    fight_week_override: dict[str, Any] | None = None,
    phase: str = "TAPER",
) -> dict[str, Any]:
    allocation = _late_fight_practical_allocation_plan(days_until_fight, athlete_model)
    mode = allocation.get("mode", _days_out_payload_mode(days_until_fight))
    roles = allocation.get("session_roles", [])
    suppressed_roles = list(allocation.get("suppressed_roles", []))
    resolved_countdown_map = dict((allocation.get("allocator", {}) or {}).get("countdown_weekday_map", {}))
    plan_weekday = athlete_model.get("plan_creation_weekday")
    composite_allocation = bool((allocation.get("allocator", {}) or {}).get("composite_practical_allocation"))
    if composite_allocation:
        weeks = []
        for week_index, segment in enumerate(_countdown_mode_sequence(days_until_fight), start=1):
            start_day = segment.get("start_day")
            end_day = segment.get("end_day")
            if not isinstance(start_day, int) or not isinstance(end_day, int):
                continue
            stage_key = str(segment.get("stage_key") or "")
            segment_mode = str(segment.get("payload_mode") or _days_out_payload_mode(start_day))
            segment_athlete = _shifted_segment_athlete_model(days_until_fight, start_day, athlete_model)
            segment_plan_weekday = segment_athlete.get("plan_creation_weekday")
            filtered_training = _filter_past_weekdays(
                _ordered_weekdays(clean_list(segment_athlete.get("training_days", []))),
                segment_plan_weekday,
                start_day,
            )
            filtered_sparring = _filter_past_weekdays(
                _ordered_weekdays(clean_list(segment_athlete.get("hard_sparring_days", []))),
                segment_plan_weekday,
                start_day,
            )
            filtered_technical = _filter_past_weekdays(
                _ordered_weekdays(
                    clean_list(
                        segment_athlete.get(
                            "support_work_days",
                            segment_athlete.get("technical_skill_days", []),
                        )
                    )
                ),
                segment_plan_weekday,
                start_day,
            )
            segment_roles = [
                role
                for role in roles
                if str(role.get("composite_segment_stage_key") or "") == stage_key
            ]
            segment_suppressed_roles = [
                role
                for role in suppressed_roles
                if str(role.get("composite_segment_stage_key") or "") == stage_key
            ]
            hard_sparring_plan = _late_fight_hard_sparring_plan(
                days_until_fight=start_day,
                athlete_model=segment_athlete,
                declared_hard_days=filtered_sparring,
                phase=phase,
                stage_key=stage_key,
                week_index=week_index,
            )
            effective_days = effective_hard_days(hard_sparring_plan)
            weeks.append(
                {
                    "week_index": week_index,
                    "phase": phase,
                    "stage_key": stage_key,
                    "stage_label": _late_fight_stage_label(start_day),
                    "payload_mode": segment_mode,
                    "phase_week_index": 1,
                    "phase_week_total": 1,
                    "countdown_span": {"start_day": start_day, "end_day": end_day},
                    "declared_training_days": filtered_training,
                    "declared_hard_sparring_days": filtered_sparring,
                    "declared_support_work_days": filtered_technical,
                    "hard_sparring_plan": hard_sparring_plan,
                    "effective_hard_sparring_days": list(effective_days),
                    "coach_note_flags": [_late_fight_stage_label(start_day)],
                    "intentional_compression": {
                        "active": True,
                        "reason_codes": [segment_mode],
                        "reason": segment_mode,
                        "summary": _late_fight_summary(start_day),
                    },
                    "intentionally_unused_days": [],
                    "session_roles": segment_roles,
                    "suppressed_roles": segment_suppressed_roles,
                    "countdown_weekday_map": resolved_countdown_map,
                    "allocator": allocation.get("allocator", {}),
                    "role_budget": allocation.get("role_budget", {}),
                }
            )
    elif mode in {"fight_day_protocol_payload", "pre_fight_day_payload", "late_fight_session_payload", "late_fight_transition_payload"}:
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
            _ordered_weekdays(
                clean_list(
                    athlete_model.get(
                        "support_work_days",
                        athlete_model.get("technical_skill_days", []),
                    )
                )
            ),
            plan_weekday,
            days_until_fight,
        )
        hard_sparring_plan = _late_fight_hard_sparring_plan(
            days_until_fight=days_until_fight,
            athlete_model=athlete_model,
            declared_hard_days=filtered_sparring,
            phase=phase,
            stage_key=_late_fight_window(days_until_fight),
        )
        effective_days = effective_hard_days(hard_sparring_plan)
        weeks = [
            {
                "week_index": 1,
                "phase": phase,
                "stage_key": _late_fight_window(days_until_fight),
                "phase_week_index": 1,
                "phase_week_total": 1,
                "declared_training_days": filtered_training,
                "declared_hard_sparring_days": filtered_sparring,
                "declared_support_work_days": filtered_technical,
                "hard_sparring_plan": hard_sparring_plan,
                "effective_hard_sparring_days": list(effective_days),
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
    allocation = _late_fight_practical_allocation_plan(days_until_fight, athlete_model)
    roles = list(allocation.get("session_roles", []))
    session_sequence = list(roles)
    visible_session_sequence = _visible_insert_session_sequence(session_sequence)
    mode = payload_block["payload_mode"]
    max_blocks = _MAX_BLOCKS_PER_SESSION.get(mode)
    resolved_countdown_map = dict((allocation.get("allocator", {}) or {}).get("countdown_weekday_map", {}))
    role_budget = dict(allocation.get("role_budget", {}) or {})
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
        "countdown_exercise_rules": _late_fight_countdown_exercise_rules(days_until_fight),
        "taper_micro_support_policy": _late_fight_taper_micro_support_policy(days_until_fight, athlete_model),
        "rendering_rules": payload_block["rendering_rules"],
        "max_meaningful_stress_exposures": _late_fight_max_meaningful_stress_exposures(days_until_fight),
        "max_active_roles": _bridge_active_role_cap(days_until_fight, athlete_model),
        "max_support_roles": _late_fight_max_support_roles(days_until_fight),
        "countdown_weekday_map": resolved_countdown_map,
        "role_budget": role_budget,
        "allocator": allocation.get("allocator", {}),
        "suppressed_roles": allocation.get("suppressed_roles", []),
        "permission_policy": allocation.get("permission_policy", {}),
        "countdown_mode_sequence": _countdown_mode_sequence(days_until_fight),
    }
    if isinstance(role_budget.get("max_meaningful_stress_exposures"), int):
        spec["max_meaningful_stress_exposures"] = role_budget["max_meaningful_stress_exposures"]
    if isinstance(role_budget.get("max_active_roles"), int):
        spec["max_active_roles"] = role_budget["max_active_roles"]
    if isinstance(role_budget.get("max_support_roles"), int):
        spec["max_support_roles"] = role_budget["max_support_roles"]
    if max_blocks is not None:
        spec["max_blocks_per_session"] = max_blocks
    hard_sparring_context = _hard_sparring_window_context(days_until_fight, athlete_model)
    if hard_sparring_context:
        spec.update(hard_sparring_context)
    days = _coerce_days(days_until_fight)
    if days is not None and 0 <= days <= 17:
        spec["hard_sparring_ban_summary"] = (
            "All declared hard sparring from D-17 onward is converted to technical/rhythm only. "
            "No effective hard sparring allowed."
        )
    return spec


def _countdown_mode_sequence(days_until_fight: Any) -> list[dict[str, Any]]:
    days = _coerce_days(days_until_fight)
    if not isinstance(days, int) or days < 0:
        return []
    if _is_countdown_continuation_start(days_until_fight):
        windows = [
            {"stage_key": "d21_to_d14", "payload_mode": "bridge_compression_payload", "window_start": 21, "window_end": 14},
            {"stage_key": "d13_to_d8", "payload_mode": "pre_fight_compressed_payload", "window_start": 13, "window_end": 8},
            {"stage_key": "d7", "payload_mode": "late_fight_week_payload", "window_start": 7, "window_end": 7},
            {"stage_key": "d6_to_d5", "payload_mode": "late_fight_transition_payload", "window_start": 6, "window_end": 5},
            {"stage_key": "d4_to_d2", "payload_mode": "late_fight_session_payload", "window_start": 4, "window_end": 2},
            {"stage_key": "d1", "payload_mode": "pre_fight_day_payload", "window_start": 1, "window_end": 1},
            {"stage_key": "d0", "payload_mode": "fight_day_protocol_payload", "window_start": 0, "window_end": 0},
        ]
        started = False
        sequence: list[dict[str, Any]] = []
        for window in windows:
            window_start = int(window["window_start"])
            window_end = int(window["window_end"])
            if not started:
                if not (window_end <= days <= window_start):
                    continue
                started = True
                sequence.append(
                    {
                        "stage_key": window["stage_key"],
                        "payload_mode": window["payload_mode"],
                        "start_day": days,
                        "end_day": window_end,
                    }
                )
                continue
            sequence.append(
                {
                    "stage_key": window["stage_key"],
                    "payload_mode": window["payload_mode"],
                    "start_day": window_start,
                    "end_day": window_end,
                }
            )
        return sequence
    mode = _days_out_payload_mode(days)
    if mode == "camp_payload":
        return []
    return [
        {
            "stage_key": _late_fight_window(days),
            "payload_mode": mode,
            "start_day": days,
            "end_day": days,
        }
    ]


def _handoff_mode_instructions(payload_mode: str) -> str:
    _CONTRACT = (
        "COUNTDOWN CONTRACT\n"
        "One coherent countdown truth. Lead every active day D-N first, weekday second — use resolved countdown_display_label when present.\n"
        "Placement governs day assignment only — it never expands the visible session list.\n"
        "State the ownership split to the athlete plainly: the gym/coach owns the boxing load; the S&C and rehab inserts are programmed for you. Never call these 'app-owned' or 'app-provided' in athlete-facing text — name the work directly.\n"
        "Render only the programmed S&C/rehab roles as athlete-facing sessions; boxing schedule is context.\n"
        "Partial prescription: label exactly — Coach-prescribed S&C / rehab schedule only. Boxing schedule remains as set by gym/coach.\n"
        "Full prescription: label — Countdown schedule.\n"
        "D-0 = fight-day protocol only. Never a training session.\n"
        "From D-10 to the fight, the progression/regression line offers regressions and stop rules only — never a progression/advance option (no add load/sets, heavier ball, stronger band, or \"to progress\").\n"
        "From D-13, strength & conditioning sessions (strength, power, alactic, aerobic, fight-pace, neural speed work) also lock to regressions and stop rules only; fillers, rehab, mobility, and light recovery work may still progress on D-13 to D-11.\n"
        "Declared hard-spar days are fixed coach-owned combat locks. Never move, drop, or deload them; from D-17 onward they render as coach-led technical-only combat.\n"
        "If late_fight_plan_spec.surviving_hard_spar_days / late_fight_plan_spec.downgraded_declared_spar_days are present, use those fields as source of truth and add one short deterministic sentence (hard days first, downgraded days second).\n"
        "Add one short rationale only when placement/compression would otherwise make day choice look arbitrary.\n"
        "One hard-spar doctrine per output. No split schedule realities.\n"
"Hard sparring days are gym/coach-owned combat locks. The app must not prescribe the sparring and never deloads it. At D-18 or further out render the label \"" + CANONICAL_HARD_SPARRING_LABEL + "\" (or sport-equivalent like \"Coach-led MMA — hard sparring / controlled hard contact\"). From D-17 onward hard sparring is banned: render \"" + CANONICAL_HARD_SPARRING_BAN_LABEL + "\" (or sport-equivalent). No round counts, no time-x-rounds, no intensity targets, no dose, no RPE, no work:rest, no sparring template wording. After the label, emit exactly one note: \"" + CANONICAL_HARD_SPARRING_NOTE + "\" Nothing else — never schedule or list programmed S&C on a coach-owned combat day."
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
            "Primer intensity cap: micro-dose only, RPE 3-5, 1-2 sets or 2-3 minutes total; no RPE 6-7, no pump, no fatigue.\n"
            "Optional taper_micro_support only: breathing, mobility, or light technical shadowboxing. No equipment of any kind on D-1: no bands, no med ball, no heavy bag, no weights, no core, no neck, no grip tools.\n"
            "No weekly architecture. No hard sparring. No suppressed role restoration.\n\n"
            + _CONTRACT
        )
    if payload_mode == "bridge_compression_payload":
        return (
            "BRIDGE COMPRESSION WEEK (D-21 to D-14)\n"
            "Taper-on-ramp, not full camp. 5 blocks per session max.\n"
            "Meaningful stress cap: 3 per rolling 7 days. Declared hard sparring in D-21 to D-18 is coach-owned and stays hard; from D-17 onward all declared hard sparring converts to technical-only combat.\n"
            "Strength/power: 1 touch max. Pressure exposure: one controlled fight-pace pressure touch on D-20, D-19, or D-18 when no coach hard-sparring day owns D-21 to D-18; otherwise 0.\n"
            "One freshness/mobility reset is mandatory. Never stack programmed S&C on a coach-owned combat day. No double-stress day.\n\n"
            + _CONTRACT
        )
    if payload_mode == "pre_fight_compressed_payload":
        return (
            "COMPRESSED PRE-FIGHT WEEK (D-13 to D-8)\n"
            "5 blocks per session max. No effective hard sparring; all declared hard sparring converts to technical/rhythm only. Strength/power: 1 touch max.\n"
            "Fight-rhythm touch: 1 max, rhythm/freshness only, RPE <= 5 - it cannot satisfy a hard conditioning, glycolytic, or combat-pressure quota. Suppress entirely if sparring already owns the week.\n"
            "One freshness, mobility, or reset session is mandatory.\n"
            "From D-10 to D-8, taper_micro_support may appear only as one optional add-on line (4-6 min max) - never as a standalone session or anchor.\n"
            "No SPP development framing, no conditioning-build language, no glycolytic stressor between spar days.\n\n"
            + _CONTRACT
        )
    if payload_mode == "late_fight_week_payload":
        return (
            "SHARPNESS WEEK (D-7)\n"
            "5 blocks per session max. Stress cap: 2 meaningful exposures total.\n"
            "Neural/power: 1 max. Fight-rhythm: 1 max. No effective hard sparring; all declared hard sparring converts to technical/rhythm only.\n"
            "Primer intensity cap: use selected drill RPE when present; otherwise cap at RPE 6-7, 3-4 x 6 sec, full rest. No all-out language.\n"
            "Optional taper_micro_support: one optional add-on line only, 3-5 min max.\n"
            "No development language, no multi-stressor stacking.\n\n"
            + _CONTRACT
        )
    if payload_mode == "late_fight_transition_payload":
        return (
            "SHARPNESS & FRESHNESS WINDOW (D-6 to D-5)\n"
            "4 blocks per session max. Stress cap: 1 meaningful exposure.\n"
            "No hard sparring — all declared spar days convert to technical rhythm.\n"
            "Insert cap: 2 sessions (one power touch or technical rhythm + one freshness).\n"
            "Primer intensity cap: use selected drill RPE when present; otherwise cap at RPE 6-7, 3-4 x 6 sec, full rest. No all-out language.\n"
            "Optional taper_micro_support: one optional add-on line only, 3-5 min max.\n"
            "Session-by-session only. S&C inserts titled explicitly as countdown inserts.\n\n"
            + _CONTRACT
        )
    if payload_mode == "late_fight_session_payload":
        return (
            "SHARPNESS-FIRST SESSIONS (D-4 to D-2)\n"
            "4 blocks per session max. Session-by-session only — no week headers, no program blocks.\n"
            "D-4: sharpness + freshness. D-3: freshness default; power/sharpness touch only if fatigue is not high and no spar-spillover flag. D-2: neural primer or technical touch only.\n"
            "Primer intensity cap: rhythm-only unless a selected drill is lower; max RPE 5-6. No all-out language.\n"
            "Optional taper_micro_support: breathing/mobility only, or one tiny rehab-style cue, 2-4 min max.\n"
            "No strength, no conditioning, no glycolytic work, no hard sparring.\n\n"
            + _CONTRACT
        )
    return ""
