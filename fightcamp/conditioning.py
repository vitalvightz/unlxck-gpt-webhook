from __future__ import annotations

import json
import logging
import os
from time import perf_counter
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Callable, Iterable
from collections import defaultdict
from .training_context import (
    allocate_sessions,
    normalize_athlete_equipment_list,
    normalize_equipment_list,
    calculate_exercise_numbers,
)
from .bank_schema import (
    KNOWN_SYSTEMS,
    NON_EQUIPMENT_TOKENS,
    SYSTEM_ALIASES,
    is_late_fight_metadata_safe,
    validate_training_item,
)
from .injury_filtering import injury_match_details, _log_exclusion, _log_replacement
from .injury_guard import Decision, choose_injury_replacement, injury_decision, make_guarded_decision_factory
from .coordination_support_library import extract_coordination_style, normalize_sport
from .restriction_filtering import evaluate_restriction_impact
from .diagnostics import format_missing_system_block
from .tagging import normalize_item_tags, normalize_tags
from .tag_maps import GOAL_TAG_MAP, STYLE_TAG_MAP, WEAKNESS_TAG_MAP
from .config import (
    PHASE_SYSTEM_RATIOS,
    STYLE_CONDITIONING_RATIO,
    DATA_DIR,
    INJURY_GUARD_SHORTLIST,
    trim_to_injury_guard_shortlist,
)
from .late_selector_windows import (
    D1,
    D4_TO_D2,
    D6_TO_D5,
    D7,
    D13_TO_D8,
    D21_TO_D14,
    classify_late_selector_window,
    is_active_late_selector_window,
)
from .stage2_payload_late_fight import compute_bridge_rules
from .selection_metadata import build_score_evidence, normalize_selection_metadata
from .weight_cut import compute_cut_severity_score, cut_severity_bucket
from .priority_profile import (
    PRIMARY_GOAL_WEIGHT,
    PRIMARY_WEAKNESS_WEIGHT,
    build_priority_profile,
    goal_priority_weight,
    is_priority_collision_tag,
    weakness_priority_weight,
)
from .priority_clarification_tags import derive_clarification_tags
from .stage1_fail_safe import bounded_max_iterations, log_fail_safe_degrade

TAPER_AVOID_TAGS = {
    "contrast_pairing",
    "triple_extension",
    "overhead",
    "compound",
    "mental_toughness",
    "work_capacity",
    "eccentric",
}

CONDITIONING_MAX_GOAL_PRIORITY_BONUS = 4.0
CONDITIONING_MAX_WEAKNESS_PRIORITY_BONUS = 5.0
CONDITIONING_PRIMARY_GOAL_BONUS = 2.0
CONDITIONING_SECONDARY_GOAL_BONUS = 1.0
CONDITIONING_PRIMARY_WEAKNESS_BONUS = 2.5
CONDITIONING_SECONDARY_WEAKNESS_BONUS = 1.25
CONDITIONING_MAX_COLLISION_SAFE_PRIORITY_BONUS = 5.0
CONDITIONING_PRIMARY_COLLISION_BONUS = 3.0
CONDITIONING_SECONDARY_COLLISION_BONUS = 1.5
CONDITIONING_CLARIFICATION_TAG_BONUS = 0.75
CONDITIONING_MAX_CLARIFICATION_TAG_BONUS = 2.0

_RAW_SPEED_GOAL_TOKENS = {
    "speed",
    "reactive",
    "reaction",
    "acceleration",
}

_RAW_FOOTWORK_GOAL_TOKENS = {
    "footwork",
    "lateral_movement",
    "lateral movement",
    "ringcraft",
    "angles",
    "pivot",
    "stance",
    "stance_reset",
    "angle_exit",
}

def _conditioning_goal_priority_bonus(tags: list[str], priority_profile) -> float:
    unique_tags = list(dict.fromkeys(tags))
    total = 0.0
    for tag in unique_tags:
        weight = goal_priority_weight(tag, priority_profile)
        if weight == PRIMARY_GOAL_WEIGHT:
            total += CONDITIONING_PRIMARY_GOAL_BONUS
        elif weight > 0:
            total += CONDITIONING_SECONDARY_GOAL_BONUS
    return min(total, CONDITIONING_MAX_GOAL_PRIORITY_BONUS)


def _conditioning_weakness_priority_bonus(tags: list[str], priority_profile) -> float:
    unique_tags = list(dict.fromkeys(tags))
    total = 0.0
    for tag in unique_tags:
        weight = weakness_priority_weight(tag, priority_profile)
        if weight == PRIMARY_WEAKNESS_WEIGHT:
            total += CONDITIONING_PRIMARY_WEAKNESS_BONUS
        elif weight > 0:
            total += CONDITIONING_SECONDARY_WEAKNESS_BONUS
    return min(total, CONDITIONING_MAX_WEAKNESS_PRIORITY_BONUS)


def _conditioning_priority_value_for_tag(tag: str, priority_profile) -> float:
    goal_weight = goal_priority_weight(tag, priority_profile)
    weakness_weight = weakness_priority_weight(tag, priority_profile)

    if is_priority_collision_tag(tag, priority_profile):
        if goal_weight == PRIMARY_GOAL_WEIGHT and weakness_weight == PRIMARY_WEAKNESS_WEIGHT:
            return CONDITIONING_PRIMARY_COLLISION_BONUS
        return CONDITIONING_SECONDARY_COLLISION_BONUS

    total = 0.0
    if goal_weight == PRIMARY_GOAL_WEIGHT:
        total += CONDITIONING_PRIMARY_GOAL_BONUS
    elif goal_weight > 0:
        total += CONDITIONING_SECONDARY_GOAL_BONUS

    if weakness_weight == PRIMARY_WEAKNESS_WEIGHT:
        total += CONDITIONING_PRIMARY_WEAKNESS_BONUS
    elif weakness_weight > 0:
        total += CONDITIONING_SECONDARY_WEAKNESS_BONUS

    return total


def _conditioning_collision_safe_priority_bonus(
    goal_tags: list[str],
    weakness_tags: list[str],
    priority_profile,
) -> float:
    unique_tags = list(dict.fromkeys([*goal_tags, *weakness_tags]))
    if not any(is_priority_collision_tag(tag, priority_profile) for tag in unique_tags):
        return _conditioning_goal_priority_bonus(goal_tags, priority_profile) + _conditioning_weakness_priority_bonus(
            weakness_tags,
            priority_profile,
        )

    total = sum(_conditioning_priority_value_for_tag(tag, priority_profile) for tag in unique_tags)
    return min(total, CONDITIONING_MAX_COLLISION_SAFE_PRIORITY_BONUS)


def _add_conditioning_priority_reason_codes(
    reasons: dict,
    matched_goal_tags: list[str],
    matched_weak_tags: list[str],
    priority_profile,
) -> None:
    for tag in matched_goal_tags:
        goal_weight = goal_priority_weight(tag, priority_profile)
        if goal_weight == PRIMARY_GOAL_WEIGHT:
            reasons["reason_codes"].append(f"priority_primary_goal_match:{tag}")
        elif goal_weight > 0:
            reasons["reason_codes"].append(f"priority_secondary_goal_match:{tag}")
    for tag in matched_weak_tags:
        weakness_weight = weakness_priority_weight(tag, priority_profile)
        if weakness_weight == PRIMARY_WEAKNESS_WEIGHT:
            reasons["reason_codes"].append(f"priority_primary_weakness_match:{tag}")
        elif weakness_weight > 0:
            reasons["reason_codes"].append(f"priority_secondary_weakness_match:{tag}")
    for tag in list(dict.fromkeys(matched_goal_tags + matched_weak_tags)):
        if is_priority_collision_tag(tag, priority_profile):
            reasons["reason_codes"].append(f"priority_collision_goal_weakness:{tag}")


def _conditioning_resolve_derived_clarification_tags(flags: dict) -> list[str]:
    priority_focus = flags.get("priority_focus") or {}
    focus_tags = normalize_tags(priority_focus.get("derived_clarification_tags") or [])
    if focus_tags:
        return list(dict.fromkeys(focus_tags))

    collision_details = flags.get("goal_weakness_collision_details") or []
    derived_tags = normalize_tags(derive_clarification_tags(collision_details))
    return list(dict.fromkeys(derived_tags))


def _conditioning_clarification_bonus(tags: list[str], derived_clarification_tags: list[str]) -> tuple[float, list[str]]:
    if not derived_clarification_tags:
        return 0.0, []
    hits = sorted(set(tags).intersection(derived_clarification_tags))
    if not hits:
        return 0.0, []
    bonus = min(len(hits) * CONDITIONING_CLARIFICATION_TAG_BONUS, CONDITIONING_MAX_CLARIFICATION_TAG_BONUS)
    return bonus, hits


def _style_specificity_sport_tag(primary_tech: str, selection_format: str) -> str:
    """Preserve the athlete's real sport identity before format collapsing.

    BJJ and wrestling intentionally use MMA programming weights, but they must
    not therefore make an MMA-tagged style drill look more sport-specific than
    a BJJ- or wrestling-tagged drill.
    """
    tech = str(primary_tech or "").strip().lower().replace("-", " " )
    aliases = {
        "boxer": "boxing",
        "boxing": "boxing",
        "kickboxer": "kickboxing",
        "kickboxing": "kickboxing",
        "karate": "kickboxing",
        "muay thai": "muay_thai",
        "muaythai": "muay_thai",
        "muay_thai": "muay_thai",
        "mma": "mma",
        "bjj": "bjj",
        "wrestler": "wrestling",
        "wrestling": "wrestling",
        "grappler": "grappling",
        "grappling": "grappling",
    }
    return aliases.get(tech, str(selection_format or "").strip().lower())


def _style_exact_sport_bonus(raw_tags: list[str], athlete_sport_tag: str) -> float:
    """Return the small preference for a raw exact-sport style-bank match.

    Raw bank tags are inspected before compatibility rewrites. The athlete sport
    tag is deliberately distinct from the broader programming format.
    """
    sport = str(athlete_sport_tag or "").strip().lower()
    if not sport:
        return 0.0
    return STYLE_EXACT_SPORT_BONUS if sport in set(normalize_tags(raw_tags or [])) else 0.0

_MIXED_SYSTEM_LOGGED: set[tuple[str, str]] = set()
_UNKNOWN_SYSTEM_LOGGED: set[tuple[str, str]] = set()
_UNKNOWN_SYSTEM_DRILL_LOGGED: set[tuple[str, str, str]] = set()

logger = logging.getLogger(__name__)

ALACTIC_MAX_WORK_SEC = 12
ALACTIC_MIN_REST_SEC = 60
CONDITIONING_MULTI_ROUND_MIN_ROUNDS = 3
GLYCOLYTIC_DENSE_MIN_WORK_SEC = 45
GLYCOLYTIC_DENSE_MAX_REST_SEC = 90
GLYCOLYTIC_SUSTAINED_MIN_TOTAL_MINUTES = 12
GLYCOLYTIC_SUSTAINED_MIN_RPE = 7
GLYCOLYTIC_LABEL_BASE_MAX_REST_SEC = 60
PREFERRED_EXERCISE_NAME_BOOST = 3.0
STYLE_EXACT_SPORT_BONUS = 0.5
SPEED_REPEATABILITY_MAX_WORK_SEC = 30
SPEED_REPEATABILITY_MIN_REST_SEC = 60
FRESHNESS_LACTATE_LEVELS = {"none", "low"}
FRESHNESS_MAX_RPE = 6
LATE_CONDITIONING_SAFE_TAGS = {
    "low_impact",
    "zero_impact",
    "cns_freshness",
    "sharpness",
    "recovery",
    "skill_refinement",
    "coordination",
    "reactive",
}
LATE_CONDITIONING_TIGHT_WINDOWS = {D7, D6_TO_D5, D4_TO_D2, D1}
TAPER_ONLY_CONDITIONING_WINDOWS = {D13_TO_D8, D7, D6_TO_D5, D4_TO_D2, D1}
_AEROBIC_MAINTENANCE_WINDOWS = {D21_TO_D14, D13_TO_D8}
_AEROBIC_MAINTENANCE_SIGNAL_TERMS = {"conditioning", "gas_tank", "gas tank", "endurance", "aerobic"}
_GAS_TANK_SIGNAL_TERMS = {"conditioning", "gas_tank", "gas tank", "endurance", "work_capacity"}
_GAS_TANK_MACHINE_TOKENS = ("assault bike", "air bike", "echo bike", "rower", "concept2", "bike erg", "stationary bike")
_GAS_TANK_SAFE_TAGS = {"aerobic", "low_impact", "recovery", "cns_freshness"}
_GAS_TANK_MACHINE_EQUIPMENT = {
    "assault_bike",
    "air_dyne_bike",
    "echo_bike",
    "stationary_bike",
    "bike_erg",
    "rower",
    "rowing_machine",
    "concept2",
}

from .conditioning_boxing import (  # noqa: E402
    BOXING_NAME_MAP,
    _alactic_maintenance_fallback,
    _boxing_aerobic_context_flags,
    _boxing_aerobic_preference_rank,
    _boxing_aerobic_priority_adjustment,
    _is_pool_treading_drill,
    _normalize_conditioning_name,
    _sanitize_sport_language,
    _suppress_alactic_maintenance,
    _violates_sport_language_blacklist,
)
from .normalization import clean_list, normalize_fight_format as _normalize_fight_format  # noqa: E402

_TIME_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|-)?\s*(\d+(?:\.\d+)?)?\s*"
    r"(s|sec|secs|second|seconds|min|mins|minute|minutes)\b",
    re.IGNORECASE,
)

def _time_token_to_seconds(value: float, unit: str) -> float:
    if unit.lower().startswith("m"):
        return value * 60.0
    return value

def _extract_time_values(text: str) -> list[float]:
    values: list[float] = []
    for match in _TIME_TOKEN.finditer(text or ""):
        start_val = float(match.group(1))
        end_val = float(match.group(2)) if match.group(2) else None
        unit = match.group(3)
        value = max(start_val, end_val) if end_val is not None else start_val
        values.append(_time_token_to_seconds(value, unit))
    return values

def _metadata_number(drill: dict, field_name: str) -> float | None:
    value = drill.get(field_name)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None

def _metadata_level(drill: dict, field_name: str) -> str:
    return str(drill.get(field_name) or "").strip().lower()

def _coerce_optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None

def _low_level(level: str) -> bool:
    return level in {"none", "low"}

def _high_level(level: str) -> bool:
    return level in {"high", "very_high", "max"}

def _has_dense_glycolytic_interval(
    *,
    work_sec: float | None,
    rest_sec: float | None,
    rounds: float | None,
) -> bool:
    return bool(
        work_sec is not None
        and rest_sec is not None
        and rounds is not None
        and work_sec >= GLYCOLYTIC_DENSE_MIN_WORK_SEC
        and rest_sec <= GLYCOLYTIC_DENSE_MAX_REST_SEC
        and rounds >= CONDITIONING_MULTI_ROUND_MIN_ROUNDS
    )

def _has_sustained_high_rpe_dose(
    *,
    total_minutes: float | None,
    rpe: float | None,
) -> bool:
    return bool(
        total_minutes is not None
        and total_minutes >= GLYCOLYTIC_SUSTAINED_MIN_TOTAL_MINUTES
        and rpe is not None
        and rpe >= GLYCOLYTIC_SUSTAINED_MIN_RPE
    )

def _has_structured_glycolytic_density(
    *,
    lactate_load: str,
    work_sec: float | None,
    rest_sec: float | None,
    rounds: float | None,
    total_minutes: float | None,
    rpe: float | None,
) -> bool:
    return bool(
        lactate_load == "high"
        or _has_dense_glycolytic_interval(
            work_sec=work_sec,
            rest_sec=rest_sec,
            rounds=rounds,
        )
        or _has_sustained_high_rpe_dose(total_minutes=total_minutes, rpe=rpe)
    )

def _has_freshness_profile(
    *,
    lactate_load: str,
    impact_cost: str,
    movement_cost: str,
    rpe: float | None,
) -> bool:
    return bool(
        lactate_load in FRESHNESS_LACTATE_LEVELS
        and (not impact_cost or _low_level(impact_cost))
        and (not movement_cost or _low_level(movement_cost))
        and (rpe is None or rpe <= FRESHNESS_MAX_RPE)
    )

def _conditioning_structured_profile(drill: dict, *, system: str | None = None) -> dict:
    work_sec = _metadata_number(drill, "work_sec")
    rest_sec = _metadata_number(drill, "rest_sec")
    rounds = _metadata_number(drill, "rounds")
    total_minutes = _metadata_number(drill, "total_minutes")
    rpe = _metadata_number(drill, "rpe")
    impact_cost = _metadata_level(drill, "impact_cost")
    lactate_load = _metadata_level(drill, "lactate_load")
    movement_cost = _metadata_level(drill, "movement_cost")
    system = str(system or drill.get("system") or "").strip().lower()

    has_dose_metadata = any(value is not None for value in (work_sec, rest_sec, rounds, total_minutes, rpe))
    has_cost_metadata = any(level for level in (impact_cost, lactate_load, movement_cost))
    multi_round = bool(rounds is not None and rounds >= CONDITIONING_MULTI_ROUND_MIN_ROUNDS)
    glycolytic_density = _has_structured_glycolytic_density(
        lactate_load=lactate_load,
        work_sec=work_sec,
        rest_sec=rest_sec,
        rounds=rounds,
        total_minutes=total_minutes,
        rpe=rpe,
    )
    alactic_structure = bool(
        work_sec is not None
        and rest_sec is not None
        and work_sec <= ALACTIC_MAX_WORK_SEC
        and rest_sec >= ALACTIC_MIN_REST_SEC
    )
    freshness = _has_freshness_profile(
        lactate_load=lactate_load,
        impact_cost=impact_cost,
        movement_cost=movement_cost,
        rpe=rpe,
    )

    return {
        "work_sec": work_sec,
        "rest_sec": rest_sec,
        "rounds": rounds,
        "total_minutes": total_minutes,
        "rpe": rpe,
        "impact_cost": impact_cost,
        "lactate_load": lactate_load,
        "movement_cost": movement_cost,
        "has_dose_metadata": has_dose_metadata,
        "has_cost_metadata": has_cost_metadata,
        "multi_round": multi_round,
        "glycolytic_density": glycolytic_density,
        "alactic_structure": alactic_structure,
        "freshness": freshness,
        "high_impact": _high_level(impact_cost),
        "high_lactate": lactate_load == "high" or (system == "glycolytic" and glycolytic_density),
        "high_movement_cost": _high_level(movement_cost),
    }

def _alactic_structure_ok(drill: dict) -> bool:
    structured = _conditioning_structured_profile(drill)
    if structured["has_dose_metadata"]:
        return bool(structured["alactic_structure"])

    timing = drill.get("timing") or ""
    duration = drill.get("duration") or ""
    rest = drill.get("rest") or ""
    duration_text = " ".join(filter(None, [timing, duration]))
    work_candidates: list[float] = []
    rest_candidates: list[float] = []

    for clause in re.split(r"[;,/]", duration_text):
        clause_lower = clause.lower()
        is_rest_clause = any(
            key in clause_lower
            for key in ("rest", "off", "recovery", "recover", "between")
        )
        targets = rest_candidates if is_rest_clause else work_candidates
        targets.extend(_extract_time_values(clause))

    if rest:
        rest_candidates.extend(_extract_time_values(rest))

    if not work_candidates:
        return False
    if not rest_candidates:
        return False

    work_seconds = max(work_candidates)
    rest_seconds = max(rest_candidates)
    return work_seconds <= ALACTIC_MAX_WORK_SEC and rest_seconds >= ALACTIC_MIN_REST_SEC

def _conditioning_window_severity(window: str | None) -> float:
    return {
        "d21_to_d14": 0.55,
        "d13_to_d8": 0.9,
        D7: 1.05,
        D6_TO_D5: 1.15,
        D4_TO_D2: 1.25,
        D1: 1.35,
    }.get(window, 0.0)

def _conditioning_text_blob(drill: dict) -> str:
    fields = (
        drill.get("name", ""),
        drill.get("duration", ""),
        drill.get("timing", ""),
        drill.get("rest", ""),
        drill.get("notes", ""),
        drill.get("modality", ""),
        drill.get("equipment_note", ""),
    )
    return " ".join(str(field or "") for field in fields).strip().lower()


def _is_machine_biased_gas_tank_drill(drill: dict) -> bool:
    text = _conditioning_text_blob(drill)
    system = str(drill.get("system") or "").strip().lower()
    equipment = set(normalize_equipment_list(drill.get("equipment", [])))
    tags = set(normalize_tags(drill.get("tags", [])))
    machine_match = bool(_GAS_TANK_MACHINE_EQUIPMENT & equipment) or any(token in text for token in _GAS_TANK_MACHINE_TOKENS)
    if not machine_match:
        return False
    structured = _conditioning_structured_profile(drill, system=system)
    safe_by_structure = (
        structured["lactate_load"] in {"", "none", "low"}
        and (structured["rpe"] is None or structured["rpe"] <= 6)
        and not structured["glycolytic_density"]
    )
    safe_by_tags = bool(tags & _GAS_TANK_SAFE_TAGS)
    return safe_by_structure and (system == "aerobic" or safe_by_tags)


def _normalize_focus_tokens(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        token = str(value or "").strip().lower().replace("_", " ")
        if not token:
            continue
        normalized.add(token)
        normalized.add(token.replace(" ", "_"))
    return normalized


_SPEED_GOAL_TOKENS = _normalize_focus_tokens(_RAW_SPEED_GOAL_TOKENS)
_FOOTWORK_GOAL_TOKENS = _normalize_focus_tokens(_RAW_FOOTWORK_GOAL_TOKENS)
_GAS_TANK_NORMALIZED_SIGNAL_TERMS = _normalize_focus_tokens(_GAS_TANK_SIGNAL_TERMS)

def _conditioning_dense_pattern(text: str) -> bool:
    return any(keyword in text for keyword in ("emom", "tabata", "amrap", "for time"))

def _conditioning_multi_round_pattern(text: str) -> bool:
    time_values = _extract_time_values(text)
    if "round" in text and any(value >= 120 for value in time_values):
        return True
    if re.search(r"\b\d+\s*x\s*\d+", text) and ("rest" in text or len(time_values) >= 2):
        return True
    if "interval" in text and ("rest" in text or len(time_values) >= 2):
        return True
    return False

def _conditioning_fight_pace_pattern(text: str, tags: set[str]) -> bool:
    if "fight-pace" in text or "fight pace" in text:
        return True
    return (
        "round" in text
        and any(value >= 120 for value in _extract_time_values(text))
        and bool(tags & {"conditioning", "glycolytic", "work_capacity"})
    )

def _conditioning_generic_glycolytic(system: str, tags: set[str]) -> bool:
    if system != "glycolytic":
        return False
    return not bool(tags & {"skill_refinement", "cns_freshness", "sharpness", "low_impact", "reactive"})

_ATHLETE_LABEL_BLOCKED_GLYCOLYTIC_WINDOWS = {D7, D6_TO_D5, D4_TO_D2, D1}

def athlete_facing_system_label(drill: dict, *, late_window: str | None = None) -> str:
    """Coach-voiced conditioning label based on prescribed dose.

    Internal system fields (``glycolytic``, ``alactic``, ``aerobic``) leak coach
    jargon into athlete-facing output. This helper translates them using the
    drill's actual work/rest prescription so the label matches what the session
    feels like in practice.

    ``late_window`` is the resolved late-fight window
    (``classify_late_selector_window``); when D-7 or tighter, ``glycolytic``
    is never returned even if the dose qualifies — fight-week output must not
    frame sessions around lactate stress.
    """

    # Technical footwork carries system:"aerobic" only to satisfy the legacy
    # conditioning schema; it is not aerobic conditioning. Label it honestly by
    # its modality so it never renders as "Aerobic support" et al.
    if str(drill.get("modality") or "").strip().lower() == "technical_footwork":
        return "technical footwork"

    system = str(drill.get("system") or "").strip().lower()
    tags = set(normalize_tags(drill.get("tags", [])))
    text = _conditioning_text_blob(drill)
    structured = _conditioning_structured_profile(drill, system=system)

    work_values: list[float] = []
    rest_values: list[float] = []
    raw_text = " ; ".join(filter(None, [drill.get("timing", ""), drill.get("duration", "")]))
    for clause in re.split(r"[;,/]", raw_text):
        is_rest = any(k in clause.lower() for k in ("rest", "off", "recovery", "recover", "between"))
        targets = rest_values if is_rest else work_values
        targets.extend(_extract_time_values(clause))
    if drill.get("rest"):
        rest_values.extend(_extract_time_values(drill.get("rest") or ""))

    work_max = structured["work_sec"] or (max(work_values) if work_values else None)
    rest_max = structured["rest_sec"] or (max(rest_values) if rest_values else None)
    multi_round = structured["multi_round"] or _conditioning_multi_round_pattern(text)
    fight_pace = structured["high_lactate"] or _conditioning_fight_pace_pattern(text, tags)

    # Dose is the primary decider. A "fight-pace" tag on a short-work + full-rest
    # drill does not earn the "glycolytic" label — the prescription has to
    # actually create lactate stress.
    base_glycolytic_dose = (
        work_max is not None
        and rest_max is not None
        and work_max >= GLYCOLYTIC_DENSE_MIN_WORK_SEC
        and rest_max <= GLYCOLYTIC_LABEL_BASE_MAX_REST_SEC
        and multi_round
    )
    fight_pace_glycolytic_dose = (
        fight_pace
        and work_max is not None
        and rest_max is not None
        and work_max >= GLYCOLYTIC_DENSE_MIN_WORK_SEC
        and rest_max <= GLYCOLYTIC_DENSE_MAX_REST_SEC
        and multi_round
    )
    glycolytic_dose = structured["glycolytic_density"] or base_glycolytic_dose or fight_pace_glycolytic_dose

    short_work_full_rest = (
        work_max is not None
        and rest_max is not None
        and work_max <= SPEED_REPEATABILITY_MAX_WORK_SEC
        and rest_max >= SPEED_REPEATABILITY_MIN_REST_SEC
    )

    if glycolytic_dose and late_window not in _ATHLETE_LABEL_BLOCKED_GLYCOLYTIC_WINDOWS:
        return "glycolytic"

    if "coordination" in tags:
        return "coordination conditioning"
    if "reactive" in tags:
        return "reactive footwork"
    if short_work_full_rest and tags & {"sharpness", "skill_refinement"}:
        return "technical rhythm"
    if short_work_full_rest:
        return "footwork speed repeatability"

    if late_window in _ATHLETE_LABEL_BLOCKED_GLYCOLYTIC_WINDOWS and system == "glycolytic":
        if tags & {"sharpness", "skill_refinement", "cns_freshness"}:
            return "technical rhythm"
        return "coordination conditioning"

    return system or "conditioning"

def _conditioning_resolve_bridge_rules(
    *,
    flags: dict,
    days_until_fight: int | None,
    sport: str,
    style_names: list[str],
    tech_style_tags: list[str],
    fatigue: str,
) -> dict:
    triage_summary = flags.get("triage_summary") or {}
    injury_mode = str(triage_summary.get("mode") or "full_plan").strip().lower() or "full_plan"
    cut_bucket = str(flags.get("cut_severity_bucket") or "").strip().lower()
    if not cut_bucket:
        cut_bucket = cut_severity_bucket(
            compute_cut_severity_score(flags.get("weight_cut_pct"), days_until_fight)
        )
    return compute_bridge_rules(
        days_until_fight=days_until_fight,
        sport=sport,
        style=style_names or tech_style_tags,
        fatigue=fatigue,
        weight_cut_bucket=cut_bucket,
        injury_mode=injury_mode,
        hard_sparring_days_declared=len(flags.get("hard_sparring_days") or []),
        athlete_pct_above_class=flags.get("weight_cut_pct"),
        hours_to_recovery_after_weigh_in=flags.get("hours_to_recovery_after_weigh_in"),
    )


def _has_aerobic_maintenance_signal(goals: list[str], weaknesses: list[str]) -> bool:
    values = {str(v).strip().lower() for v in (goals or []) + (weaknesses or []) if v and str(v).strip()}
    return bool(values & _AEROBIC_MAINTENANCE_SIGNAL_TERMS)


def _is_low_noise_aerobic_maintenance_drill(drill: dict, *, system: str) -> bool:
    if system != "aerobic":
        return False
    tags = set(normalize_tags(drill.get("tags", [])))
    text = _conditioning_text_blob(drill)
    structured = _conditioning_structured_profile(drill, system=system)
    if not structured["freshness"]:
        return False
    rpe = structured["rpe"]
    if rpe is not None and not (4 <= rpe <= 6):
        return False
    if "high_cns" in tags or "plyometric" in tags:
        return False
    banned_terms = ("tabata", "burpee", "sprint start", "sprint-start", "fight-pace")
    if any(term in text for term in banned_terms):
        return False
    return bool(tags & {"aerobic", "recovery", "low_impact", "cns_freshness", "skill_refinement"})

def _evaluate_conditioning_late_window(
    drill: dict,
    *,
    system: str,
    window: str | None,
    bridge_rules: dict | None,
    source: str = "conditioning_bank.json",
) -> dict:
    if not is_active_late_selector_window(window):
        return {
            "blocked": False,
            "severity": "safe",
            "block_codes": [],
            "reason_codes": [],
            "penalty_codes": [],
            "adjustment": 0.0,
            "ambiguous_gap": None,
        }
    metadata_safety = None
    metadata_penalty_codes: list[str] = []
    metadata_adjustment = 0.0
    if source == "runtime_fallback" or drill.get("_schema_source") or drill.get("_schema_issues") or drill.get("_schema_safety"):
        metadata_source = str(drill.get("_schema_source") or source)
        metadata_source_kind = "conditioning" if metadata_source == "runtime_fallback" else None
        metadata_safety = is_late_fight_metadata_safe(
            drill,
            metadata_source,
            window,
            source_kind=metadata_source_kind,
        )
        if metadata_safety.get("severity") == "blocked":
            return {
                "blocked": True,
                "severity": "blocked",
                "block_codes": metadata_safety["block_codes"],
                "reason_codes": metadata_safety["reason_codes"],
                "penalty_codes": metadata_safety.get("penalty_codes", []),
                "adjustment": -1.0,
                "ambiguous_gap": None,
                "unsafe_metadata": metadata_safety["unsafe_metadata"],
            }
        metadata_penalty_codes = list(metadata_safety.get("penalty_codes", []))
        if metadata_penalty_codes:
            metadata_adjustment = max(-0.75, -0.35 * len(metadata_penalty_codes))

    tags = set(normalize_tags(drill.get("tags", [])))
    equipment = set(normalize_equipment_list(drill.get("equipment", [])))
    if window in TAPER_ONLY_CONDITIONING_WINDOWS:
        phases = {str(value).strip().upper() for value in (drill.get("phases") or []) if str(value).strip()}
        support_alactic = (
            system == "alactic"
            and bool(drill.get("support_only"))
            and str(drill.get("lactate_load", "")).strip().lower() == "low"
        )
        if phases and "TAPER" not in phases and not support_alactic:
            return {
                "blocked": True,
                "severity": "blocked",
                "block_codes": ["late_conditioning_block_not_taper_phased"],
                "reason_codes": ["late_conditioning_penalty_not_taper_phased"],
                "penalty_codes": [],
                "adjustment": -1.0,
                "ambiguous_gap": None,
            }
    text = _conditioning_text_blob(drill)
    severity = _conditioning_window_severity(window)
    late_windows = {str(w).strip().lower() for w in (drill.get("late_windows") or []) if str(w).strip()}
    structured = _conditioning_structured_profile(drill, system=system)
    dense = structured["glycolytic_density"] or _conditioning_dense_pattern(text)
    multi_round = structured["multi_round"] or _conditioning_multi_round_pattern(text)
    fight_pace = structured["high_lactate"] or _conditioning_fight_pace_pattern(text, tags)
    generic_glycolytic = _conditioning_generic_glycolytic(system, tags) or (
        system == "glycolytic" and structured["high_lactate"]
    )
    low_noise_sharpness = (
        system == "alactic"
        and not dense
        and (tags & LATE_CONDITIONING_SAFE_TAGS or structured["alactic_structure"] or _alactic_structure_ok(drill))
    )
    aerobic_rhythm = (
        system == "aerobic"
        and not dense
        and (
            structured["freshness"]
            or bool(tags & {"low_impact", "cns_freshness", "recovery", "skill_refinement", "coordination"})
        )
    )
    developmental_taper = (
        not structured["freshness"]
        and (dense or multi_round or fight_pace or structured["high_lactate"])
        and bool(tags & {"conditioning", "glycolytic", "work_capacity", "mech_systemic_fatigue"})
    )

    reason_codes: list[str] = []
    penalty_codes: list[str] = list(metadata_penalty_codes)
    adjustment = metadata_adjustment
    reason_codes.extend(metadata_penalty_codes)
    late_band_lockout_window = window in {D7, D6_TO_D5, D4_TO_D2, D1}
    rehab_mobility_band_ok = bool(
        tags
        & {
            "mobility",
            "recovery",
            "rehab",
            "rehab_friendly",
            "prehab",
            "injury_prevention",
        }
    )
    block_codes: list[str] = []
    if late_band_lockout_window and "bands" in equipment and (window == "d1" or not rehab_mobility_band_ok):
        block_codes.append("late_conditioning_block_band_work_lockout")
        reason_codes.append("late_conditioning_penalty_band_work_lockout")
    # d1 allows no equipment of any kind.
    if window == D1 and equipment - NON_EQUIPMENT_TOKENS:
        block_codes.append("late_conditioning_block_d1_equipment")
        reason_codes.append("late_conditioning_block_d1_equipment")

    if low_noise_sharpness:
        adjustment += 0.75
        reason_codes.append("late_conditioning_boost_alactic_sharpness")
    elif aerobic_rhythm:
        adjustment += 0.5
        reason_codes.append("late_conditioning_boost_aerobic_rhythm")
    elif tags & {"cns_freshness", "sharpness", "skill_refinement"}:
        adjustment += 0.35
        reason_codes.append("late_conditioning_boost_freshness")

    if dense and multi_round:
        adjustment -= 0.7 * severity
        reason_codes.append("late_conditioning_penalty_dense_multi_round")
    if fight_pace:
        adjustment -= 0.9 * severity
        reason_codes.append("late_conditioning_penalty_fight_pace_leak")
    if structured["high_lactate"]:
        adjustment -= 0.9 * severity
        reason_codes.append("late_conditioning_penalty_high_lactate_metadata")
    if structured["high_impact"] or "high_impact_lower" in tags or ("mech_landing_impact" in tags and system == "alactic"):
        adjustment -= 0.4 * severity
        reason_codes.append("late_conditioning_penalty_impact_noise")
    if structured["high_movement_cost"]:
        adjustment -= 0.35 * severity
        reason_codes.append("late_conditioning_penalty_high_movement_cost_metadata")
    if structured["freshness"]:
        adjustment += 0.25
        reason_codes.append("late_conditioning_boost_structured_freshness")
    if developmental_taper:
        adjustment -= 0.8 * severity
        reason_codes.append("late_conditioning_penalty_developmental_taper")
    bridge_allows_glycolytic = bool((bridge_rules or {}).get("glycolytic_touch_max", 0) > 0)
    if generic_glycolytic:
        adjustment -= (0.8 if bridge_allows_glycolytic and window == "d21_to_d14" else 1.5) * severity
        reason_codes.append("late_conditioning_penalty_generic_glycolytic")

    if generic_glycolytic and not bridge_allows_glycolytic:
        block_codes.append("late_conditioning_block_bridge_glycolytic_cap")

    if late_windows:
        if window in late_windows:
            adjustment += 0.8 + (0.15 * severity)
            reason_codes.append("late_conditioning_boost_window_fit")
        else:
            adjustment -= 0.85
            reason_codes.append("late_conditioning_penalty_outside_window")
            block_codes.append("late_conditioning_block_window_mismatch")

    if window in LATE_CONDITIONING_TIGHT_WINDOWS:
        if structured["high_lactate"] or structured["glycolytic_density"]:
            block_codes.append("late_conditioning_block_structured_glycolytic_density")
        if generic_glycolytic:
            block_codes.append("late_conditioning_block_generic_glycolytic")
        if dense and multi_round:
            block_codes.append("late_conditioning_block_dense_multi_round")
        if fight_pace or developmental_taper:
            block_codes.append("late_conditioning_block_density_leakage")

    ambiguous_gap = None
    if (
        not block_codes
        and not (tags & LATE_CONDITIONING_SAFE_TAGS)
        and bool(tags & {"plyometric", "mech_ballistic", "mech_reactive", "mech_shoulder_overhead"})
        and not dense
        and system == "alactic"
    ):
        ambiguous_gap = {
            "name": drill.get("name", "<unnamed>"),
            "issue": "late_safe_intent_not_explicit",
            "signals": sorted(
                signal
                for signal in {"plyometric", "mech_ballistic", "mech_reactive", "mech_shoulder_overhead"} & tags
            ),
        }

    return {
        "blocked": bool(block_codes),
        "severity": "blocked" if block_codes else "penalty" if penalty_codes else "safe",
        "block_codes": sorted(set(block_codes)),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "penalty_codes": list(dict.fromkeys(penalty_codes)),
        "adjustment": round(adjustment, 4),
        "ambiguous_gap": ambiguous_gap,
    }

def normalize_system(raw_system: str | None, *, source: str) -> str:
    """Return a normalized system name and log unknown values once."""
    system = (raw_system or "").strip().lower()
    if not system:
        normalized = "misc"
    else:
        normalized = SYSTEM_ALIASES.get(system, system)

    if any(sep in system for sep in ("+", "\u2192", "/", "&")) or "->" in system:
        parts = [
            part.strip()
            for part in re.split(r"\s*(?:\+|/|\u2192|->|&)\s*", system)
            if part.strip()
        ]
        mapped_parts = [SYSTEM_ALIASES.get(part, part) for part in parts]
        known_parts = [part for part in mapped_parts if part in KNOWN_SYSTEMS]
        if known_parts:
            if "glycolytic" in known_parts:
                normalized = "glycolytic"
            else:
                normalized = known_parts[0]
            log_key = (source, system)
            if log_key not in _MIXED_SYSTEM_LOGGED and len(known_parts) > 1:
                _MIXED_SYSTEM_LOGGED.add(log_key)
                logger.warning(
                    "[conditioning] Mixed energy system '%s' normalized='%s' source=%s",
                    system,
                    normalized,
                    source,
                )
        else:
            normalized = SYSTEM_ALIASES.get(system, system or "misc")
    if normalized not in KNOWN_SYSTEMS:
        log_key = (source, normalized)
        if log_key not in _UNKNOWN_SYSTEM_LOGGED:
            _UNKNOWN_SYSTEM_LOGGED.add(log_key)
            logger.warning(
                "[conditioning] Unknown energy system '%s' normalized='%s' source=%s",
                system or "unknown",
                normalized,
                source,
            )
    return normalized

def _sanitize_conditioning_bank(bank, *, source: str):
    def normalize_items(items: list[dict]) -> list[dict]:
        cleaned: list[dict] = []
        for item in items:
            placement = item.get("placement", "conditioning").lower()
            validate_training_item(
                item,
                source=source,
                require_phases=True,
                require_system=placement == "conditioning",
                mode="runtime",
            )
            normalize_item_tags(item)
            if placement != "conditioning":
                cleaned.append(item)
                continue
            normalized = normalize_system(item.get("system"), source=source)
            if normalized not in KNOWN_SYSTEMS:
                name = item.get("name", "Unnamed Drill")
                logger.warning(
                    "[conditioning] Removing drill with invalid system bank=%s name='%s' system='%s'",
                    source,
                    name,
                    item.get("system"),
                )
                continue
            if item.get("system") != normalized:
                item["system"] = normalized
            cleaned.append(item)
        return cleaned

    if isinstance(bank, list):
        return normalize_items(bank)
    cleaned_bank = {}
    for key, items in bank.items():
        if isinstance(items, list):
            cleaned_bank[key] = normalize_items(items)
        else:
            cleaned_bank[key] = items
    return cleaned_bank

def _load_bank(path: Path, *, source: str, enforce_conditioning_systems: bool = False):
    bank = json.loads(path.read_text(encoding="utf-8"))
    if enforce_conditioning_systems:
        return _sanitize_conditioning_bank(bank, source=source)
    if isinstance(bank, list):
        for item in bank:
            validate_training_item(item, source=source, require_phases=True, mode="runtime")
            normalize_item_tags(item)
        return bank
    for items in bank.values():
        if isinstance(items, list):
            for item in items:
                validate_training_item(item, source=source, require_phases=True, mode="runtime")
                normalize_item_tags(item)
    return bank

_conditioning_bank_cache = None
_style_conditioning_bank_cache = None

TAPER_CONDITIONING_SAFE_NAMES = {
    "Shadowboxing Technical Rhythm",
    "Breath Control Drills",
    "Explosive Boxing Burst Intervals",
    "Reactive Shuffle Repeats",
    "Easy Assault Bike",
    "Easy Bike",
    "Mobility Flow",
    "Light Footwork Rhythm",
    "Low-intensity capacity circuits (non-steady)",
}
_format_weights_cache = None
_coordination_bank_cache = None
coordination_bank = None
_technical_footwork_bank_cache = None

def get_conditioning_bank():
    global _conditioning_bank_cache
    if _conditioning_bank_cache is None:
        _conditioning_bank_cache = _load_bank(
            DATA_DIR / "conditioning_bank.json",
            source="conditioning_bank.json",
            enforce_conditioning_systems=True,
        )
    return _conditioning_bank_cache

def get_style_conditioning_bank():
    global _style_conditioning_bank_cache
    if _style_conditioning_bank_cache is None:
        _style_conditioning_bank_cache = _load_bank(
            DATA_DIR / "style_conditioning_bank.json",
            source="style_conditioning_bank.json",
            enforce_conditioning_systems=True,
        )
    return _style_conditioning_bank_cache

def get_format_weights():
    global _format_weights_cache
    if _format_weights_cache is None:
        _format_weights_cache = json.loads(
            (DATA_DIR / "format_energy_weights.json").read_text(encoding="utf-8")
        )
    return _format_weights_cache

def get_coordination_bank():
    global _coordination_bank_cache, coordination_bank
    if coordination_bank is not None:
        return coordination_bank
    if _coordination_bank_cache is not None:
        coordination_bank = _coordination_bank_cache
        return _coordination_bank_cache
    try:
        coord_data = _load_bank(DATA_DIR / "coordination_bank.json", source="coordination_bank.json")
    except FileNotFoundError:
        logger.warning("[bank-load] optional coordination bank missing")
        coord_data = []
    except (json.JSONDecodeError, ValueError):
        logger.exception("[bank-load-failed] bank=coordination_bank.json")
        coord_data = []
    loaded_coordination_bank: list[dict] = []
    if isinstance(coord_data, list):
        loaded_coordination_bank.extend(coord_data)
    elif isinstance(coord_data, dict):
        for val in coord_data.values():
            if isinstance(val, list):
                loaded_coordination_bank.extend(val)
    _coordination_bank_cache = loaded_coordination_bank
    coordination_bank = loaded_coordination_bank
    return _coordination_bank_cache

def get_technical_footwork_bank():
    """Load the standalone technical footwork bank.

    This bank holds sport-specific movement-quality / taper footwork rehearsal
    (stance resets, pivots, ring cutting, kick recovery, scramble rebase). It is
    deliberately kept OUT of the main conditioning scoring pool
    (``get_conditioning_bank``): these are technical drills, not a physiological
    conditioning dose. They reach a plan only through the dedicated
    ``_insert_technical_footwork_drill`` guarantee, gated on footwork relevance
    (mirroring the coordination bank). The bank is optional; a missing file
    degrades to an empty list rather than raising.
    """
    global _technical_footwork_bank_cache
    if _technical_footwork_bank_cache is not None:
        return _technical_footwork_bank_cache
    try:
        bank = _load_bank(
            DATA_DIR / "technical_footwork_bank.json",
            source="technical_footwork_bank.json",
            enforce_conditioning_systems=True,
        )
    except FileNotFoundError:
        logger.warning("[bank-load] optional technical footwork bank missing")
        bank = []
    loaded: list[dict] = []
    if isinstance(bank, list):
        loaded.extend(item for item in bank if isinstance(item, dict))
    elif isinstance(bank, dict):
        for items in bank.values():
            if isinstance(items, list):
                loaded.extend(item for item in items if isinstance(item, dict))
    for item in loaded:
        _validate_technical_footwork_entry(item)
    _technical_footwork_bank_cache = loaded
    return _technical_footwork_bank_cache

def prime_conditioning_banks() -> None:
    get_conditioning_bank()
    get_style_conditioning_bank()
    get_format_weights()
    get_coordination_bank()
    get_technical_footwork_bank()

def get_system_or_warn(drill: dict, *, source: str) -> str | None:
    system = normalize_system(drill.get("system"), source=source)
    if system in KNOWN_SYSTEMS:
        return system
    name = drill.get("name", "Unnamed Drill")
    log_key = (source, system, name)
    if log_key not in _UNKNOWN_SYSTEM_DRILL_LOGGED:
        _UNKNOWN_SYSTEM_DRILL_LOGGED.add(log_key)
        logger.warning(
            "[conditioning] Dropping drill with unknown system bank=%s name='%s' system='%s'",
            source,
            name,
            system,
        )
    return None

def _drill_text_injury_reasons(drill: dict, injuries: list[str]) -> list[dict]:
    return injury_match_details(drill, injuries, fields=("name", "notes"))

def _is_drill_text_safe(
    drill: dict,
    injuries: list[str],
    *,
    label: str,
    phase: str = "GPP",
    fatigue: str = "moderate",
) -> bool:
    decision = injury_decision(drill, injuries, phase, fatigue)
    if decision.action != "exclude":
        return True
    return False

# Relative emphasis of each energy system by training phase
def expand_tags(input_list, tag_map):
    expanded = []
    for item in input_list:
        tags = tag_map.get(item.lower(), [])
        expanded.extend(tags)
    return normalize_tags(expanded)

def is_banned_drill(
    name: str,
    tags: list[str],
    fight_format: str,
    details: str = "",
    tactical_styles: list[str] | None = None,
    technical_styles: list[str] | None = None,
) -> bool:
    """Return True if the drill should be removed for the given sport."""
    name = name.lower()
    tags = normalize_tags(tags)
    details = details.lower()

    tactical_styles = [s.lower().replace(" ", "_") for s in tactical_styles or []]
    technical_styles = [s.lower().replace(" ", "_") for s in technical_styles or []]

    grappling_terms = {
        "wrestling",
        "wrestle",
        "wrestler",
        "bjj",
        "grappling",
        "grapple",
        "grappler",
        "sprawl",
        "thai clinch",
        "clinch knee",
        "cage clinch",
        "sprawling",
        "takedown",
        "takedowns",
    }

    joined_tags = " ".join(tags)

    if fight_format in {"boxing", "kickboxing"}:
        for term in grappling_terms:
            if term in name or term in joined_tags or term in details:
                return True

    if fight_format == "boxing":
        boxing_terms = {
            "grappling",
            "wrestling",
            "muay_thai",
            "thai clinch",
            "clinch knee",
            "kick",
            "teep",
            "elbow",
        }
        for term in boxing_terms:
            if term in name or term in joined_tags or term in details:
                return True

    kick_terms = ["kick", "knee", "clinch knee strike", "teep"]

    if fight_format not in {"kickboxing", "muay_thai"}:
        if (
            "kicker" not in tactical_styles
            and not any(s in {"kickboxing", "muay_thai"} for s in technical_styles)
        ):
            for term in kick_terms:
                if term in name or term in tags or term in details:
                    return True

    return False

# Boxing-specific functions moved to conditioning_boxing.py

def _conditioning_required_equipment(drill: dict) -> list[str]:
    return normalize_equipment_list(
        drill.get("required_equipment")
        or drill.get("equipment")
        or []
    )

def _conditioning_is_universally_available(drill: dict) -> bool:
    required_equipment = set(_conditioning_required_equipment(drill))
    return not required_equipment or required_equipment.issubset({"bodyweight"})

def _decorate_conditioning_drill(
    drill: dict,
    *,
    system: str,
    phase: str,
    session_index: int,
    is_fallback: bool = False,
) -> dict:
    decorated = dict(drill)
    required_equipment = _conditioning_required_equipment(decorated)
    decorated["system"] = str(decorated.get("system") or system).upper()
    decorated["required_equipment"] = required_equipment
    decorated["universally_available"] = _conditioning_is_universally_available(decorated)
    decorated["generic_fallback"] = bool(decorated.get("generic_fallback"))
    decorated["session_index"] = session_index
    decorated["phase"] = str(phase or "").upper()
    decorated["render_as_fallback"] = bool(is_fallback)
    return decorated

def _conditioning_fallback_allowed(primary: dict, fallback: dict, *, phase: str) -> bool:
    if str(phase or "").upper() == "TAPER":
        return False
    contingency_reason = (
        primary.get("availability_contingency_reason")
        or fallback.get("availability_contingency_reason")
        or primary.get("availability_contingency")
        or fallback.get("availability_contingency")
        or ""
    )
    return bool(str(contingency_reason).strip())

def _resolve_conditioning_sessions(
    grouped_drills: dict[str, list[dict]],
    *,
    phase: str,
    num_sessions: int,
    alactic_primary_cap: int = 1,
) -> list[dict]:
    """Distribute already-selected conditioning drills into sessions.

    Per system: the first non-fallback drill becomes the primary, and at most one
    additional drill can render as a fallback — only when ``_conditioning_fallback_allowed``
    permits it (i.e. availability contingency reason is present and the phase is
    not TAPER). Extra drills beyond that are dropped silently unless the caller
    explicitly allows a second alactic primary. Across all systems inside a
    single session, at most one fallback is surfaced.
    """

    ordered_keys = ["aerobic", "glycolytic", "alactic"]
    ordered_keys += [k for k in grouped_drills.keys() if k not in ordered_keys]

    system_entries: list[dict] = []

    for system in ordered_keys:
        drills = [d for d in grouped_drills.get(system, []) if d]
        if not drills:
            continue

        primary_cap = max(1, int(alactic_primary_cap or 1)) if system == "alactic" else 1
        explicit_primaries = [d for d in drills if not d.get("render_as_fallback")]
        primary_raws = explicit_primaries[:primary_cap]
        if len(primary_raws) < primary_cap:
            primary_raw_ids = {id(primary) for primary in primary_raws}
            for drill in drills:
                if id(drill) in primary_raw_ids or drill.get("render_as_fallback"):
                    continue
                primary_raws.append(drill)
                primary_raw_ids.add(id(drill))
                if len(primary_raws) >= primary_cap:
                    break
        if not primary_raws:
            primary_raws = drills[:1]

        primary_entries = [
            {
                "system": system,
                "primary": _decorate_conditioning_drill(
                    primary_raw,
                    system=system,
                    phase=phase,
                    session_index=0,
                    is_fallback=False,
                ),
                "fallback": None,
            }
            for primary_raw in primary_raws
        ]

        # Fallback candidates must exclude the primary itself, otherwise an
        # all-fallback-marked drill list (or any list where the only candidate
        # is also the primary) would render the same drill twice — once as
        # primary, once as fallback. The fallback pool is therefore drawn from
        # the remaining drills only, with explicitly fallback-marked entries
        # preferred over implicit ones.
        primary_raw_ids = {id(primary_raw) for primary_raw in primary_raws}
        remaining_drills = [d for d in drills if id(d) not in primary_raw_ids]
        candidate_fallback_raw = None
        candidate_is_explicit = False
        if remaining_drills:
            explicit_remaining_fallbacks = [
                d for d in remaining_drills if d.get("render_as_fallback")
            ]
            if explicit_remaining_fallbacks:
                candidate_fallback_raw = explicit_remaining_fallbacks[0]
                candidate_is_explicit = True
            else:
                candidate_fallback_raw = remaining_drills[0]

        fallback_decorated = None
        if candidate_fallback_raw is not None:
            allowed = candidate_is_explicit or _conditioning_fallback_allowed(
                primary_raws[0], candidate_fallback_raw, phase=phase
            )
            if allowed and str(phase or "").upper() != "TAPER":
                fallback_decorated = _decorate_conditioning_drill(
                    candidate_fallback_raw,
                    system=system,
                    phase=phase,
                    session_index=0,
                    is_fallback=True,
                )

        if primary_entries:
            primary_entries[0]["fallback"] = fallback_decorated
            system_entries.extend(primary_entries)

    if not system_entries:
        return []

    session_count = max(1, num_sessions or 1)
    session_count = min(session_count, len(system_entries))

    sessions = [
        {
            "session_index": idx + 1,
            "systems": set(),
            "entries": [],
        }
        for idx in range(session_count)
    ]

    for idx, entry in enumerate(system_entries):
        target_session = sessions[idx % session_count]
        session_index = target_session["session_index"]

        if entry.get("primary"):
            entry["primary"]["session_index"] = session_index
        if entry.get("fallback"):
            entry["fallback"]["session_index"] = session_index

        target_session["entries"].append(entry)
        target_session["systems"].add(entry["system"])

    # Cap: at most one fallback per session, regardless of how many systems share it.
    for session in sessions:
        seen_fallback = False
        for entry in session["entries"]:
            if entry.get("fallback"):
                if seen_fallback:
                    entry["fallback"] = None
                else:
                    seen_fallback = True

    return sessions

def _resolved_grouped_drills(resolved_sessions: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for session in resolved_sessions:
        for entry in session.get("entries", []):
            system = entry.get("system")
            primary = entry.get("primary")
            if not system or not primary:
                continue
            grouped.setdefault(system, []).append(primary)
    return grouped

def _resolved_conditioning_names(resolved_sessions: list[dict]) -> list[str]:
    names: list[str] = []
    for session in resolved_sessions:
        for entry in session.get("entries", []):
            for key in ("primary", "fallback"):
                drill = entry.get(key) or {}
                name = drill.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    return names

def select_coordination_drill(flags, existing_names: set[str], injuries: list[str]):
    """Return a coordination drill matching the current phase if needed."""
    goals = [g.lower() for g in flags.get("key_goals", [])]
    weaknesses = [w.lower() for w in flags.get("weaknesses", [])]
    coord_terms = {"coordination", "coordination/proprioception", "coordination / proprioception"}
    if not any(g in coord_terms for g in goals) and not any(w in coord_terms for w in weaknesses):
        return None

    phase = flags.get("phase", "GPP").upper()
    equipment_access = set(normalize_athlete_equipment_list(flags.get("equipment", [])))
    candidates = []
    for drill in get_coordination_bank():
        if phase not in [p.upper() for p in drill.get("phases", [])]:
            continue
        if drill.get("placement", "conditioning").lower() != "conditioning":
            continue
        if drill.get("name") in existing_names:
            continue
        equipment = normalize_equipment_list(drill.get("equipment", []))
        if equipment and not set(equipment).issubset(equipment_access):
            continue
        candidates.append(drill)

    candidates = sorted(candidates, key=lambda d: d.get("name") or "")
    for drill in candidates[:INJURY_GUARD_SHORTLIST]:
        decision = injury_decision(drill, injuries, phase, flags.get("fatigue", "low"))
        if decision.action != "exclude":
            return drill
    return None

# Dedicated placement/render channel key for technical footwork. It is
# deliberately NOT one of the three energy systems ("aerobic"/"glycolytic"/
# "alactic"): routing footwork under this key keeps it out of energy-system
# dose accounting (``selected_counts``/``system_quota``/``missing_systems`` all
# key off the three real systems), so a footwork rehearsal drill can never be
# grouped, counted, titled, or resolved as an aerobic conditioning primary. The
# drill still occupies a visible plan slot and renders under its own labelled
# block (see ``render_conditioning_block`` / ``athlete_facing_system_label``).
TECHNICAL_FOOTWORK_GROUP = "technical_footwork"

# Goal/weakness tokens that make sport-specific technical footwork relevant.
# Mirrors the coordination-goal gate: technical footwork is a deliberate,
# relevance-gated insert, not generic aerobic filler.
TECHNICAL_FOOTWORK_FOCUS_TOKENS = {
    "footwork",
    "foot_work",
    "footwork_speed",
    "footwork_quality",
    "ring_movement",
    "ringcraft",
    "ring_craft",
    "ring_generalship",
    "ring_iq",
    "ring_cutting",
    "angles",
    "angle",
    "angle_creation",
    "angle_exit",
    "pivot",
    "pivots",
    "lateral_movement",
    "lateral",
    "stance",
    "stance_reset",
    "movement_quality",
    "cut_off",
    "cutting_off",
    "distance_management",
    "distance_control",
    "range_management",
    "in_and_out",
}

# reactive_level values permitted per phase. Technical footwork stays familiar
# and low-novelty in taper (no new coordination challenge near the fight); SPP
# is where fight-reactive movement is phase-appropriate.
_TECHNICAL_FOOTWORK_REACTIVE_BY_PHASE = {
    "GPP": {"closed", "semi_reactive"},
    "SPP": {"closed", "semi_reactive", "reactive"},
    "TAPER": {"closed", "semi_reactive"},
}

# Canonical sport (see coordination_support_library.SUPPORTED_SPORTS, resolved
# through the shared normalize_sport ontology) -> the drill sport-identity tags
# that are genuinely appropriate for that sport. muay_thai and kickboxing share
# a striking-footwork vocabulary. Wrestling and BJJ are grappling sports with a
# limited standing-footwork game, so they are gated to the specific
# grappling-transition drills explicitly tagged for them (a per-drill movement
# audit), never blanket-mapped onto the whole MMA set. When a sport has no
# eligible drill in a phase/window, deliberate omission is safer than surfacing
# another sport's footwork.
_TECHNICAL_FOOTWORK_SPORT_TAGS = {
    "boxing": {"boxing"},
    "kickboxing": {"kickboxing", "muay_thai"},
    "muay_thai": {"kickboxing", "muay_thai"},
    "mma": {"mma"},
    "wrestling": {"wrestling"},
    "bjj": {"bjj"},
}

# This relationship intentionally reuses the canonical style tokens already
# present in intake/tag normalization and the bank. It is a tactical preference
# model, not a second style ontology. Earlier ranking compared style tokens
# directly with function tokens (for example counter_striker == counter_setup),
# which could never match. Values stay small and relative: eligibility gates
# above this layer always win.
_TECHNICAL_FOOTWORK_FUNCTION_PREFERENCES = {
    "counter_striker": {
        "counter_setup": 1.0,
        "defensive_exit": 0.85,
        "angle_creation": 0.7,
        "range_management": 0.5,
    },
    "pressure_fighter": {
        "pressure": 1.0,
        "ring_cutting": 0.85,
        "exit_lane_control": 0.7,
        "angle_creation": 0.4,
    },
    "brawler": {
        "pressure": 1.0,
        "ring_cutting": 0.85,
        "exit_lane_control": 0.7,
        "angle_creation": 0.4,
    },
    "distance_striker": {
        "range_management": 1.0,
        "defensive_exit": 0.8,
        "angle_creation": 0.65,
        "base_recovery": 0.35,
    },
    "clinch_fighter": {
        "clinch_management": 1.0,
        "base_recovery": 0.75,
        "defensive_exit": 0.5,
    },
    "kicker": {
        "kick_recovery": 1.0,
        "range_management": 0.8,
        "defensive_exit": 0.55,
        "base_recovery": 0.4,
    },
    "wrestler": {
        "takedown_setup": 1.0,
        "takedown_defense": 0.95,
        "scramble_recovery": 0.8,
        "base_recovery": 0.6,
        "cage_control": 0.5,
    },
    "grappler": {
        "standup_transition": 1.0,
        "base_recovery": 0.8,
        "scramble_recovery": 0.6,
    },
    "submission_hunter": {
        "standup_transition": 1.0,
        "base_recovery": 0.8,
        "scramble_recovery": 0.6,
    },
}

_TECHNICAL_FOOTWORK_REACTIVE_LEVELS = {"closed", "semi_reactive", "reactive"}
_TECHNICAL_FOOTWORK_CUE_SOURCES = {"self", "coach", "partner", "visual"}
_TECHNICAL_FOOTWORK_SIDE_RULES = {
    "both_directions",
    "athlete_primary_stance",
    "alternate_stances",
}

# Cue-source availability is a real runtime fact, not drill metadata taken at
# face value. Two sources are genuinely executable and we commit to providing
# them:
#   - "self": an athlete-initiated start/reset, always executable solo.
#   - "visual": a self-administered random visual cue (a reaction-cue app or a
#     randomized left/right/shot call sequence the athlete runs without a
#     helper). This is a genuinely reactive, solo-executable mechanism (option A
#     of the availability fix); when it is the cue the athlete relies on, the
#     prescription states the concrete executable method so a bare "visual"
#     metadata value is never silently assumed to be available.
# "partner" is available only when the athlete's declared equipment includes a
# partner. "coach" has no runtime signal in intake and is never auto-available;
# a drill that can only be driven by a coach is filtered for that athlete.
_TECHNICAL_FOOTWORK_SOLO_EXECUTABLE_CUE_SOURCES = {"self", "visual"}
_TECHNICAL_FOOTWORK_EQUIPMENT_CUE_SOURCES = {"partner"}


def _technical_footwork_available_cue_sources(equipment_access: set[str]) -> set[str]:
    """Cue sources this athlete can actually execute right now."""
    return _TECHNICAL_FOOTWORK_SOLO_EXECUTABLE_CUE_SOURCES | (
        _TECHNICAL_FOOTWORK_EQUIPMENT_CUE_SOURCES & set(equipment_access)
    )


def _technical_footwork_cue_execution(drill: dict, available_cue_sources: set[str]) -> str:
    """State the concrete, executable way the athlete produces this drill's cue.

    Makes cue availability explicit rather than assumed: a partner feed when a
    partner is available, otherwise the self-administered random visual/random
    cue method that keeps a semi-reactive/reactive drill genuinely executable
    solo. Closed drills (self-paced) need no external cue.
    """
    reactive_level = str(drill.get("reactive_level") or "closed").strip().lower()
    cue_sources = {
        str(value).strip().lower()
        for value in drill.get("cue_source", [])
        if str(value).strip()
    }
    usable = cue_sources & available_cue_sources
    if reactive_level == "closed" or usable <= {"self"}:
        return ""
    if "partner" in usable:
        return "Have your partner feed the cue at random timing; reset fully between reps."
    if "visual" in usable:
        return (
            "Self-administer a random visual cue (reaction-cue app or a randomized "
            "left/right/shot call sequence) so the read stays genuinely reactive without a helper."
        )
    return ""


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_technical_footwork_entry(drill: dict) -> None:
    """Validate the dedicated execution contract without widening conditioning."""
    name = str(drill.get("name") or "<unnamed>")
    if drill.get("modality") != TECHNICAL_FOOTWORK_GROUP:
        raise ValueError(f"Technical footwork drill {name!r} has invalid modality")

    functions = drill.get("tactical_function")
    if not isinstance(functions, list) or not all(str(value).strip() for value in functions):
        raise ValueError(f"Technical footwork drill {name!r} needs tactical_function values")

    reactive_level = str(drill.get("reactive_level") or "").strip().lower()
    if reactive_level not in _TECHNICAL_FOOTWORK_REACTIVE_LEVELS:
        raise ValueError(f"Technical footwork drill {name!r} has invalid reactive_level")

    cue_sources = drill.get("cue_source")
    if not isinstance(cue_sources, list) or not cue_sources:
        raise ValueError(f"Technical footwork drill {name!r} needs cue_source values")
    normalized_sources = {str(value).strip().lower() for value in cue_sources}
    if normalized_sources - _TECHNICAL_FOOTWORK_CUE_SOURCES:
        raise ValueError(f"Technical footwork drill {name!r} has invalid cue_source")
    if reactive_level == "reactive" and not (
        normalized_sources & {"coach", "partner", "visual"}
    ):
        raise ValueError(
            f"Reactive technical footwork drill {name!r} needs an external/random cue source"
        )
    if not str(drill.get("cue") or "").strip():
        raise ValueError(f"Technical footwork drill {name!r} needs an executable cue")

    if drill.get("side_rule") not in _TECHNICAL_FOOTWORK_SIDE_RULES:
        raise ValueError(f"Technical footwork drill {name!r} has invalid side_rule")

    rep_fields = [field for field in ("reps", "reps_per_side") if field in drill]
    if rep_fields:
        if len(rep_fields) != 1 or not _positive_int(drill.get(rep_fields[0])):
            raise ValueError(f"Technical footwork drill {name!r} has invalid rep dose")
        if not _positive_int(drill.get("sets")) or not _positive_int(drill.get("rest_sec")):
            raise ValueError(f"Technical footwork drill {name!r} needs sets and rest_sec")
        if any(field in drill for field in ("work_sec", "rounds", "total_minutes")):
            raise ValueError(
                f"Rep-based technical footwork drill {name!r} cannot carry timed-work metadata"
            )
        if not str(drill.get("quality_stop_rule") or "").strip():
            raise ValueError(f"Rep-based technical footwork drill {name!r} needs quality_stop_rule")
    elif not (_positive_int(drill.get("work_sec")) and _positive_int(drill.get("rounds"))):
        raise ValueError(f"Timed technical footwork drill {name!r} needs work_sec and rounds")


def _technical_footwork_style_preferences(
    flags: dict, *, canonical_sport: str
) -> tuple[list[str], dict[str, float]]:
    raw_tactical_styles = list(flags.get("style_tactical", []))
    style_tokens = set(
        normalize_tags(
            [*raw_tactical_styles, *flags.get("style_technical", [])]
        )
    )
    # Reuse the shared coordination style aliases for established inputs such
    # as out-boxer/range-fighter. Preserve more specific bank identities such as
    # wrestler and kicker instead of collapsing them into a broader family.
    specialist_tokens = style_tokens & {"wrestler", "submission_hunter", "kicker"}
    if not specialist_tokens:
        style_tokens.add(
            extract_coordination_style({"style_tactical": raw_tactical_styles})
        )
    # A wrestling-format athlete is wrestling-oriented even when the intake's
    # broader tactical label is grappler. MMA remains dependent on the declared
    # tactical style so submission-oriented grapplers are not treated as wrestlers.
    if canonical_sport == "wrestling":
        style_tokens.add("wrestler")

    styles = sorted(style_tokens & _TECHNICAL_FOOTWORK_FUNCTION_PREFERENCES.keys())
    preferences: dict[str, float] = {}
    for style in styles:
        for function, weight in _TECHNICAL_FOOTWORK_FUNCTION_PREFERENCES[style].items():
            preferences[function] = max(preferences.get(function, 0.0), weight)
    return styles, preferences


def _technical_footwork_match_evidence(
    drill: dict,
    *,
    canonical_sport: str,
    style_tokens: set[str],
    function_preferences: dict[str, float],
) -> tuple[float, list[str]]:
    tags = set(normalize_tags(drill.get("tags", [])))
    functions = {
        str(value).strip().lower()
        for value in drill.get("tactical_function", [])
        if str(value).strip()
    }
    matched_functions = sorted(
        functions & function_preferences.keys(),
        key=lambda function: (-function_preferences[function], function),
    )
    score = sum(function_preferences[function] for function in matched_functions)
    # Small tie-breakers preserve exact declared identity and exact sport tags
    # without overpowering the tactical-function relationship.
    score += 0.25 * len(style_tokens & tags)
    if canonical_sport and canonical_sport in tags:
        score += 0.1
    return score, matched_functions


def _technical_footwork_selection_reasons(flags: dict, drill: dict) -> dict:
    canonical_sport = normalize_sport(flags.get("fight_format") or flags.get("sport") or "")
    # ``styles`` are the athlete's own styles that feed the tactical-function
    # preference model. They are NOT evidence that the selected drill matches
    # that style. A real style match exists only when the drill's own tags carry
    # the athlete's style, so ``style_hits`` and the ``style_match`` reason codes
    # are derived from the drill tags, kept strictly separate from the
    # preference-deriving styles below.
    preference_styles, function_preferences = _technical_footwork_style_preferences(
        flags, canonical_sport=canonical_sport
    )
    score, matched_functions = _technical_footwork_match_evidence(
        drill,
        canonical_sport=canonical_sport,
        style_tokens=set(preference_styles),
        function_preferences=function_preferences,
    )
    drill_tags = set(normalize_tags(drill.get("tags", [])))
    matched_styles = sorted(set(preference_styles) & drill_tags)
    reason_codes = ["technical_footwork_guarantee"]
    # Only emit a style-match reason when the drill's own tags satisfy it.
    reason_codes.extend(f"technical_footwork_style_match:{style}" for style in matched_styles)
    reason_codes.extend(
        f"technical_footwork_function_match:{function}"
        for function in matched_functions
    )
    return {
        "goal_hits": 1,
        "weakness_hits": 0,
        # Truthful: count only direct drill style-tag matches.
        "style_hits": len(matched_styles),
        "phase_hits": 1,
        "load_adjustments": 0,
        "equipment_boost": 0,
        "penalties": 0,
        # Athlete styles used to derive tactical-function preferences (not a
        # claim that the drill carries them).
        "technical_footwork_preference_styles": preference_styles,
        # Actual direct drill style-tag matches (the only real style evidence).
        "technical_footwork_styles": matched_styles,
        "technical_footwork_style_matches": matched_styles,
        "technical_footwork_function_matches": matched_functions,
        "technical_footwork_function_hits": len(matched_functions),
        "reason_codes": reason_codes,
        "final_score": round(score, 4),
    }


def _footwork_focus_tokens(values) -> set[str]:
    tokens: set[str] = set()
    for value in values or []:
        text = str(value).strip().lower()
        if not text:
            continue
        tokens.add(text.replace(" ", "_").replace("-", "_"))
    tokens.update(normalize_tags(list(values or [])))
    return tokens


def _technical_footwork_relevance(flags) -> bool:
    """Whether the athlete's goals/weaknesses call for technical footwork work."""
    tokens = _footwork_focus_tokens(
        [*flags.get("key_goals", []), *flags.get("weaknesses", [])]
    )
    return bool(tokens & TECHNICAL_FOOTWORK_FOCUS_TOKENS)


def select_technical_footwork_candidates(
    flags, existing_names: set[str], injuries: list[str]
) -> list[dict]:
    """Return injury-safe technical footwork drills, best match first.

    Gated on footwork relevance (goals/weaknesses), phase eligibility,
    per-drill ``reactive_level`` vs phase, equipment, and strict sport
    compatibility. Tactical function then drives the within-sport rank so a
    counter striker gets defensive/angle movement. Injury gating is applied to
    the whole ranked list.

    Every eligible, injury-safe candidate is returned (not only the top one) so
    the caller can fall through to the next-best drill when the highest-ranked
    one is later blocked by per-drill ``late_windows`` (taper/D-day) gating.
    Taper/D-day gating itself is deliberately handled downstream by
    ``_try_append_conditioning_drill`` so it stays consistent with the rest of
    the conditioning selector; returning a single pick here and blocking it
    downstream would strand a valid window-eligible drill (e.g. at D-4 a
    ``d6_to_d5``-capped angle drill outranks the ``d4_to_d2``-eligible stance
    reset, so only a list lets the reset still be used).
    """
    if not _technical_footwork_relevance(flags):
        return []

    phase = str(flags.get("phase", "GPP")).upper()
    reactive_allowed = _TECHNICAL_FOOTWORK_REACTIVE_BY_PHASE.get(
        phase, {"closed", "semi_reactive"}
    )
    equipment_access = set(normalize_athlete_equipment_list(flags.get("equipment", [])))
    # Resolve the athlete's sport through the shared canonical ontology so
    # aliases (muay thai / muaythai / wrestler / jiu jitsu ...) and every
    # supported combat sport — including wrestling and bjj — map consistently,
    # rather than a footwork-local sport table that silently omitted them.
    canonical_sport = normalize_sport(flags.get("fight_format") or flags.get("sport") or "")
    compatible_sport_tags = _TECHNICAL_FOOTWORK_SPORT_TAGS.get(
        canonical_sport, {canonical_sport} if canonical_sport else set()
    )
    style_tokens, function_preferences = _technical_footwork_style_preferences(
        flags, canonical_sport=canonical_sport
    )
    style_token_set = set(style_tokens)
    available_cue_sources = _technical_footwork_available_cue_sources(equipment_access)

    candidates = []
    for drill in get_technical_footwork_bank():
        drill_tags = set(normalize_tags(drill.get("tags", [])))
        # Sport is an eligibility rule here, not merely a ranking preference.
        # When a sport-specific late-window candidate is unavailable, omission
        # is safer and more correct than filling the slot with another sport.
        if compatible_sport_tags and not (drill_tags & compatible_sport_tags):
            continue
        if phase not in [str(p).upper() for p in drill.get("phases", [])]:
            continue
        if drill.get("name") in existing_names:
            continue
        reactive_level = str(drill.get("reactive_level", "closed")).strip().lower() or "closed"
        if reactive_level not in reactive_allowed:
            continue
        # Keep novel, high-complexity coordination out of the taper: the athlete
        # rehearses only well-grooved movement close to the fight.
        complexity = str(drill.get("technical_complexity", "moderate")).strip().lower()
        if phase == "TAPER" and complexity == "high":
            continue
        equipment = normalize_equipment_list(drill.get("equipment", []))
        if equipment and not set(equipment).issubset(equipment_access):
            continue
        if drill.get("partner_required") is True and "partner" not in equipment_access:
            continue
        # Reactive drills declare their executability through cue_source, not
        # partner_required: they need an external/random cue the athlete can
        # actually produce. Availability is a real runtime fact (see
        # _technical_footwork_available_cue_sources): "self" and a
        # self-administered random "visual" cue are executable solo, "partner"
        # only with a declared partner, "coach" never. A drill whose declared
        # cue sources are all unavailable is dropped; a reactive drill also
        # needs at least one available non-self (external/random) cue, so a
        # coach-only reactive drill is filtered for a solo athlete.
        cue_sources = {
            str(value).strip().lower()
            for value in drill.get("cue_source", [])
            if str(value).strip()
        }
        if cue_sources and not (cue_sources & available_cue_sources):
            continue
        if reactive_level == "reactive" and not (
            (cue_sources - {"self"}) & available_cue_sources
        ):
            continue
        candidates.append(drill)

    if not candidates:
        return []

    def _match_score(drill: dict) -> float:
        score, _matched = _technical_footwork_match_evidence(
            drill,
            canonical_sport=canonical_sport,
            style_tokens=style_token_set,
            function_preferences=function_preferences,
        )
        return score

    candidates.sort(key=lambda d: (-_match_score(d), d.get("name") or ""))
    safe: list[dict] = []
    for drill in candidates:
        decision = injury_decision(drill, injuries, phase, flags.get("fatigue", "low"))
        if decision.action != "exclude":
            # Stamp the concrete executable cue method resolved from this
            # athlete's real availability so a bare "visual"/"partner" cue
            # source is never assumed downstream. Copy so the cached bank stays
            # athlete-agnostic.
            cue_execution = _technical_footwork_cue_execution(drill, available_cue_sources)
            if cue_execution:
                drill = {**drill, "cue_execution": cue_execution}
            safe.append(drill)
    return safe


def select_technical_footwork_drill(flags, existing_names: set[str], injuries: list[str]):
    """Return the best injury-safe technical footwork drill, or ``None``.

    Thin wrapper over :func:`select_technical_footwork_candidates` returning the
    top-ranked candidate. It does NOT apply per-drill ``late_windows``
    (taper/D-day) gating — that stays with ``_try_append_conditioning_drill`` at
    insertion time, which is why the insert path consumes the full candidate
    list rather than this single pick.
    """
    candidates = select_technical_footwork_candidates(flags, existing_names, injuries)
    return candidates[0] if candidates else None


def _technical_footwork_side_instruction(drill: dict, stance: str | None) -> str:
    rule = str(drill.get("side_rule") or "").strip().lower()
    stance_token = str(stance or "").strip().lower()
    stance_label = {
        "orthodox": "orthodox",
        "southpaw": "southpaw",
    }.get(stance_token)

    if rule == "alternate_stances":
        return "Alternate orthodox and southpaw stances each rep."
    if rule == "athlete_primary_stance":
        if stance_label:
            return f"Use your {stance_label} stance throughout."
        return "Use your normal starting stance throughout."
    if stance_token in {"switch", "hybrid"}:
        return "Work both directions evenly from each stance."
    if stance_label:
        return f"Start in your {stance_label} stance and work both directions evenly."
    return "Work both directions evenly from your normal stance."


def technical_footwork_prescription_fields(drill: dict, *, stance: str | None = None) -> dict:
    """Canonical technical-footwork prescription fields for a selected bank drill.

    Single source for dose (timing + rest), cue, resolved side/stance
    instruction, and quality-stop rule so normal conditioning rendering and
    late-fight gap-fill rendering never diverge on what a selected bank drill
    actually prescribes.
    """
    timing = str(drill.get("timing") or drill.get("duration") or "").strip()
    rest = drill.get("rest")
    if not rest and drill.get("rest_sec"):
        rest = f"{drill['rest_sec']} sec between sets"
    rest = str(rest or "").strip()
    return {
        "name": str(drill.get("name") or "Technical Footwork"),
        "timing": timing,
        "rest": rest,
        "cue": str(drill.get("cue") or "").strip(),
        "cue_execution": str(drill.get("cue_execution") or "").strip(),
        "side_instruction": _technical_footwork_side_instruction(drill, stance),
        "quality_stop_rule": str(drill.get("quality_stop_rule") or "").strip(),
    }


def format_drill_block(drill: dict, *, phase_color: str = "#000", fallback: bool = False) -> str:
    """Return a formatted Markdown block for a single drill."""
    title = f"Fallback: {drill['name']}" if fallback else drill["name"]
    load_line = f"Load: {drill['load']}"
    if drill.get("equipment_note"):
        load_line += f" ({drill['equipment_note']})"
    parts = [
        f"- **{title}**",
        f"  - {load_line}",
        f"  - Rest: {drill['rest']}",
        f"  - Timing: {drill['timing']}",
        f"  - Purpose: {drill['purpose']}",
    ]
    if drill.get("cue"):
        parts.append(f"  - Cue: {drill['cue']}")
    if drill.get("cue_execution"):
        parts.append(f"  - Cue Method: {drill['cue_execution']}")
    if drill.get("side_instruction"):
        parts.append(f"  - Side / Stance: {drill['side_instruction']}")
    if drill.get("quality_stop_rule"):
        parts.append(f"  - Quality Stop: {drill['quality_stop_rule']}")
    parts.append(f"  - Red Flags: {drill['red_flags']}")
    return "\n".join(parts) + "\n"

def _conditioning_session_title(*, phase: str, systems: set[str]) -> str:
    phase = phase.upper()
    systems = set(systems or set())
    # Technical footwork is not an energy system: it renders under its own
    # labelled block and must never title (or, when it is the only content,
    # masquerade as) an energy-system conditioning session such as "Aerobic
    # support". Strip it before the energy-system title logic; when it is the
    # only thing present, title the session as technical footwork.
    energy_systems = systems - {TECHNICAL_FOOTWORK_GROUP}
    if TECHNICAL_FOOTWORK_GROUP in systems and not energy_systems:
        return "Technical footwork"
    systems = energy_systems
    if phase == "TAPER":
        if "alactic" in systems:
            return "Alactic sharpness"
        if "aerobic" in systems:
            return "Aerobic support"
        return "Recovery"
    if systems == {"aerobic"}:
        return "Aerobic support"
    if systems == {"glycolytic"}:
        return "Fight-pace conditioning" if phase == "SPP" else "Conditioning"
    if systems == {"alactic"}:
        return "Alactic sharpness"
    if "glycolytic" in systems and phase == "SPP":
        return "Fight-pace conditioning"
    return "Conditioning"

def _glycolytic_fallback(phase: str) -> dict:
    phase = phase.upper()
    intensity = "RPE 7–8" if phase == "SPP" else "RPE 6–7"
    return {
        "system": "GLYCOLYTIC",
        "name": "Fight-Pace Rounds: 6-10 x (2-3 min on / 1 min off)",
        "load": f"{intensity} fight-pace",
        "rest": "1 min between rounds",
        "timing": "2-3 min work / 1 min rest",
        "purpose": "Maintain glycolytic conditioning with clear work:rest structure.",
        "red_flags": "None",
        "equipment": [],
        "required_equipment": [],
        "generic_fallback": True,
    }

def _bridge_glycolytic_touch_fallback() -> dict:
    """Low-dose bridge touch for D-21 to D-18 when bridge rules allow glycolytic.

    This is not a full fight-pace conditioning fallback. It is only a small
    rhythm / tempo exposure for clean late-bridge athletes.
    """

    return {
        "system": "GLYCOLYTIC",
        "name": "Bridge Tempo Touch: 2-3 x 90 sec Technical Tempo",
        "load": "RPE 5-6 technical tempo",
        "rest": "2 min between rounds",
        "timing": "2-3 x 90 sec work / 2 min rest",
        "purpose": "Maintain fight rhythm and light glycolytic touch without creating heavy fatigue.",
        "red_flags": "Stop if speed drops, breathing spikes, legs feel heavy, or sharpness fades.",
        "equipment": [],
        "required_equipment": [],
        "generic_fallback": True,
        "phases": ["TAPER"],
        "tags": [
            "glycolytic",
            "technical_rhythm",
            "skill_refinement",
            "cns_freshness",
            "low_impact",
        ],
        "late_windows": ["d21_to_d14"],
        "work_sec": 90,
        "rest_sec": 120,
        "rounds": 2,
        "rpe": 6,
        "rpe_max": 6,
        "lactate_load": "low",
        "impact_cost": "low",
        "movement_cost": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
    }

def _late_support_fallback(window: str | None) -> dict:
    """App-owned support insert for late windows where physical conditioning is unsafe."""
    late_windows = [window] if window else ["d1"]
    name = "Final Readiness Cue Reset" if window == D1 else "Late-Camp Readiness Cue Reset"
    return {
        "system": "recovery",
        "name": name,
        "load": "RPE 2-3 easy breathing, visualization, and tactical cue review",
        "rest": "As needed",
        "timing": "6-8 min",
        "purpose": "Keep the athlete settled, clear, and ready without adding physical fatigue.",
        "red_flags": "Stop if the athlete becomes more anxious, dizzy, or distracted.",
        "equipment": [],
        "required_equipment": [],
        "generic_fallback": True,
        "phases": ["TAPER"],
        "tags": ["breathing", "visualization", "tactical", "readiness_check", "recovery"],
        "late_windows": late_windows,
        "rpe": 2,
        "rpe_max": 3,
        "lactate_load": "low",
        "impact_cost": "low",
        "movement_cost": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
    }

def _late_fight_dosage_caps(days_until_fight: int) -> str:
    """Return countdown-aware dosage caps for late-fight TAPER days."""
    override_note = "These caps override any drill default structure."
    _d10_to_d7_caps = (
        "late-fight caps: no conditioning development; neural speed bursts "
        "3-4 max (5-6 sec @ RPE 6-7, rest 90-120 sec); med-ball work optional only, never required; "
        "technical touch 1-2 short rounds max (<=2 min @ RPE 5-6); "
        "no generic conditioning rounds; cap 6-8 min active. "
        f"{override_note}"
    )
    final_week_caps = {
        10: f"D-10 {_d10_to_d7_caps}",
        9: f"D-9 {_d10_to_d7_caps}",
        8: f"D-8 {_d10_to_d7_caps}",
        7: f"D-7 {_d10_to_d7_caps}",
        6: (
            "D-6 late-fight caps: no conditioning development; optional alactic sharpness only "
            "2-3 bursts max (5-6 sec @ RPE 6-7, rest 120 sec); no kettlebell swings, no loaded power cleans; "
            "technical touch 1-2 short rounds max (<=2 min @ RPE 5-6); "
            "no generic conditioning rounds; cap 5-7 min active. "
            f"{override_note}"
        ),
        5: (
            "D-5 late-fight caps: alactic bursts 2-3 max (5-6 sec @ RPE 6-7, rest 120 sec); "
            "technical touch 1-2 short rounds max (<=2 min @ RPE 5-6); "
            "no generic 6-10 round structures; cap 5-7 min active. "
            f"{override_note}"
        ),
        4: (
            "D-4 late-fight caps: alactic bursts 2-3 max (4-6 sec @ RPE 5-6, rest 120 sec); "
            "technical touch 1-2 short rounds max (<=2 min @ RPE 5-6); "
            "cap 4-6 min active. "
            f"{override_note}"
        ),
        3: (
            "D-3 late-fight caps: alactic bursts 0-3 conditional only "
            "(4-6 sec @ RPE 5-6, rest 120 sec), rendered as light shadow bursts; "
            "med-ball work optional only, never required; "
            "technical touch 1-2 short rounds max (<=2 min @ RPE 5); "
            "cap 4-6 min active. "
            f"{override_note}"
        ),
        2: (
            "D-2 late-fight caps: alactic bursts 0-2 optional only "
            "(4-6 sec @ RPE 5-6, rest 120 sec); "
            "technical walk-through 1-2 short rounds max (<=90 sec @ RPE 4-5); "
            "cap 3-5 min active. "
            f"{override_note}"
        ),
        1: (
            "D-1 late-fight caps: no conditioning work; optional rhythm touch only "
            "1-2 very short rhythm touches max (3-4 sec @ RPE 3-5, full rest); "
            "light shadowboxing 2 x 60-90 sec max plus breathing/visualization; "
            "technical walk-through only; cap 2-4 min active. "
            f"{override_note}"
        ),
    }
    if days_until_fight in final_week_caps:
        return final_week_caps[days_until_fight]
    if days_until_fight == 0:
        return (
            "Fight day: no conditioning prescription. Follow coach warm-up and fight protocol only. "
            "No additional S&C. Optional breathing and shoulder mobility only."
        )
    return "Late-fight caps: no conditioning development; keep only low-volume rhythm, sharpness, or recovery work."

def render_conditioning_block(
    grouped_drills: dict[str, list[dict]],
    *,
    phase: str,
    phase_color: str,
    missing_systems: Iterable[str] | None = None,
    num_sessions: int = 1,
    diagnostic_context: dict | None = None,
    sport: str | None = None,
    stance: str | None = None,
    resolved_sessions: list[dict] | None = None,
) -> str:
    phase = phase.upper()
    _diag = diagnostic_context or {}
    _days_until_fight = _diag.get("days_until_fight")
    try:
        _days_int = int(_days_until_fight)
    except (TypeError, ValueError):
        _days_int = None

    phase_intent = {
        "GPP": "Build aerobic base, improve repeatability, low damage.",
        "SPP": "Match fight demands with intervals and skill-relevant density.",
        "TAPER": "Speed + alactic sharpness, neural freshness, low damage.",
    }
    _taper_dosage = (
        _late_fight_dosage_caps(_days_int)
        if phase == "TAPER" and _days_int is not None and _days_int <= 10
        else "6–10 rounds of 6–12 sec @ RPE 8–9, rest 60–120 sec (cap 8–12 min). Template applies unless a drill lists its own structure."
    )
    dosage_template = {
        "GPP": "3–5 rounds of 3–5 min @ RPE 6–7, work:rest 1:1–1:0.5 (cap 20–30 min). Template applies unless a drill lists its own structure.",
        "SPP": "4–6 rounds of 2–5 min @ RPE 7–8, work:rest 1:1–1:0.5 (cap 18–25 min). Template applies unless a drill lists its own structure.",
        "TAPER": _taper_dosage,
    }
    weekly_progression = {
        "GPP": "Add 1 round or ~5–10% volume weekly; deload final week by ~20%.",
        "SPP": "Increase density or intensity weekly; keep volume flat; deload final week by ~20%.",
        "TAPER": "Reduce volume 40–60%; keep speed sharp; last 3–5 days very light.",
    }
    time_short = {
        "GPP": "Keep 2 aerobic rounds + 1 alactic pop.",
        "SPP": "Keep 2 fight-pace rounds (system priority).",
        "TAPER": "Keep 4–6 alactic bursts + shadowboxing rhythm.",
    }
    fatigue_note = {
        "GPP": "If fatigue high: drop 1–2 rounds, keep intensity easy.",
        "SPP": "If fatigue high: drop volume, keep rest longer.",
        "TAPER": "If fatigue high: keep only 4–6 low-impact bursts.",
    }

    output_lines = []
    missing_systems = set(missing_systems or [])
    diagnostic_context = diagnostic_context or {}
    if missing_systems:
        diagnostic_blocks = [
            format_missing_system_block(
                system_name,
                phase=phase,
                sport=sport or "",
                context=diagnostic_context,
            )
            for system_name in ["aerobic", "glycolytic", "alactic"]
            if system_name in missing_systems
        ]
        if diagnostic_blocks:
            output_lines.append("\n\n".join(diagnostic_blocks))

    ordered_keys = ["aerobic", "glycolytic", "alactic"]
    ordered_keys += [k for k in grouped_drills.keys() if k not in ordered_keys]
    sessions = resolved_sessions or _resolve_conditioning_sessions(
        grouped_drills,
        phase=phase,
        num_sessions=num_sessions,
    )

    for idx, session in enumerate(sessions, start=1):
        if not session.get("entries"):
            continue
        systems = session.get("systems", set())
        title = _conditioning_session_title(phase=phase, systems=systems)
        output_lines.append(f"\n#### {title}")
        output_lines.append(f"**Intent:** {phase_intent.get(phase, 'Match phase intent.')}")
        output_lines.append(f"**Dosage Template:** {dosage_template.get(phase, 'Match system goals.')}")
        if diagnostic_context.get("speed_dose_allowed"):
            output_lines.append(
                "**Speed Dose:** 1-2 exposures/week; 4-6 reps x 4-8 sec; full rest 60-120 sec; RPE 7-8; stop before fatigue."
            )
        # Combat pressure conditioning floor. GPP base work sits at RPE 6-7, but a
        # safe build week still needs one controlled hard exposure so the fighter
        # touches discomfort before fight week. When a glycolytic / fight-pace
        # exposure is actually present this session (never in TAPER), surface the
        # hard-pressure dose so the plan is not only easy aerobic support.
        if phase in {"GPP", "SPP"} and "glycolytic" in systems:
            if phase == "SPP":
                output_lines.append(
                    "**Combat Pressure Floor:** 4-6 x 2-3 min fight-pace on / 60 sec off @ RPE 8-9. "
                    "Repeat high output under fatigue and hold technique while breathing hard — "
                    "hard enough to breathe, not sloppy. Stop the round when output or technique drops."
                )
            else:
                output_lines.append(
                    "**Combat Pressure Floor:** one gas-tank / repeatability touch — "
                    "6-8 x 60 sec hard / 60-90 sec easy @ RPE 8. Controlled discomfort, not punishment. "
                    "Stop when output or technique drops."
                )
        if phase != "TAPER":
            output_lines.append(f"**Weekly Progression:** {weekly_progression.get(phase, 'Progress weekly.')}")
            output_lines.append(f"**If Time Short:** {time_short.get(phase, 'Keep top 2 drills.')}")
            output_lines.append(f"**If Fatigue High:** {fatigue_note.get(phase, 'Reduce volume.')}")

        show_system_labels = len(session.get("entries", [])) > 1

        for system in ordered_keys:
            system_entries = [
                item for item in session.get("entries", [])
                if item.get("system") == system
            ]

            if not system_entries:
                continue

            if show_system_labels:
                label_source = next(
                    (
                        item.get("primary") or item.get("fallback")
                        for item in system_entries
                        if item.get("primary") or item.get("fallback")
                    ),
                    {},
                )
                label = athlete_facing_system_label(
                    label_source,
                    late_window=diagnostic_context.get("late_window"),
                )
                output_lines.append(f"\n**{label.title()}**")

            for entry in system_entries:
                session_drills = [entry.get("primary")]

                if entry.get("fallback"):
                    session_drills.append(entry.get("fallback"))

                for d in [drill for drill in session_drills if drill]:
                    name = d.get("name", "Unnamed Drill")
                    timing = d.get("timing") or d.get("duration") or "—"
                    load = d.get("load") or d.get("intensity") or "—"
                    equip_note = d.get("equipment_note") or d.get("equipment_notes")
                    purpose = (
                        d.get("purpose")
                        or d.get("notes")
                        or d.get("description")
                        or "—"
                    )
                    rest = d.get("rest")
                    if not rest and d.get("rest_sec"):
                        rest = f"{d['rest_sec']} sec between sets"
                    rest = rest or "—"

                    name = _normalize_conditioning_name(
                        name,
                        fight_format=(sport or "").lower(),
                        phase=phase,
                    )
                    timing = _sanitize_sport_language(
                        timing,
                        fight_format=(sport or "").lower(),
                    )
                    load = _sanitize_sport_language(
                        load,
                        fight_format=(sport or "").lower(),
                    )
                    rest = _sanitize_sport_language(
                        rest,
                        fight_format=(sport or "").lower(),
                    )
                    purpose = _sanitize_sport_language(
                        purpose,
                        fight_format=(sport or "").lower(),
                    )

                    drill_block = {
                        "system": system.upper(),
                        "name": name,
                        "load": load,
                        "equipment_note": equip_note,
                        "rest": rest,
                        "timing": timing,
                        "purpose": purpose,
                        "red_flags": d.get("red_flags", "None"),
                    }
                    if d.get("modality") == TECHNICAL_FOOTWORK_GROUP:
                        prescription_fields = technical_footwork_prescription_fields(
                            d, stance=stance
                        )
                        drill_block.update(
                            {
                                "cue": prescription_fields["cue"],
                                "cue_execution": prescription_fields["cue_execution"],
                                "side_instruction": prescription_fields["side_instruction"],
                                "quality_stop_rule": prescription_fields["quality_stop_rule"],
                            }
                        )

                    output_lines.append(
                        format_drill_block(
                            drill_block,
                            phase_color=phase_color,
                            fallback=bool(d.get("render_as_fallback")),
                        )
                    )

    return "\n".join(output_lines)

def _conditioning_explanation(reasons: dict) -> str:
    parts = []
    if reasons.get("goal_hits"):
        parts.append(f"{reasons['goal_hits']} goal match")
    if reasons.get("weakness_hits"):
        parts.append(f"{reasons['weakness_hits']} weakness tag")
    if reasons.get("style_hits"):
        parts.append(f"{reasons['style_hits']} style tag")
    if reasons.get("phase_hits"):
        parts.append(f"{reasons['phase_hits']} phase tag")
    if reasons.get("equipment_boost"):
        parts.append("equipment boost")
    if reasons.get("sport_specificity_bonus"):
        parts.append("exact sport match")
    if reasons.get("load_adjustments"):
        parts.append("system emphasis")
    if reasons.get("preferred_exercise_name_match"):
        parts.append("preferred exercise match")
    return ", ".join(parts) if parts else "balanced selection"

def _build_conditioning_candidate_reservoir(
    system_drills: dict[str, list[tuple[dict, float, dict]]],
    style_system_drills: dict[str, list[tuple[dict, float, dict]]],
    grouped_drills: dict[str, list[dict]],
    reason_lookup: dict[str, dict],
    *,
    limit_per_system: int = 5,
) -> dict[str, list[dict]]:
    reservoirs: dict[str, list[dict]] = defaultdict(list)
    seen_by_system: dict[str, set[str]] = defaultdict(set)

    def _append(system: str, drill: dict, score: float, reasons: dict) -> None:
        name = drill.get("name")
        if not name:
            return
        if name in seen_by_system[system]:
            return
        if len(reservoirs[system]) >= limit_per_system:
            return
        reservoirs[system].append(
            {
                "drill": drill.copy(),
                "score": score,
                "reasons": (reasons or {}).copy(),
                "explanation": _conditioning_explanation(reasons or {}),
                "score_evidence": build_score_evidence(score=score, reasons=reasons or {}),
                "metadata": normalize_selection_metadata(drill),
            }
        )
        seen_by_system[system].add(name)

    for system, drills in grouped_drills.items():
        for drill in drills:
            reasons = reason_lookup.get(drill.get("name"), {}).copy()
            reasons.setdefault("final_score", 0)
            _append(system, drill, float(reasons.get("final_score", 0) or 0), reasons)

    for source in (system_drills, style_system_drills):
        for system, candidates in source.items():
            for drill, score, reasons in candidates:
                _append(system, drill, score, reasons)

    return dict(reservoirs)

def generate_conditioning_block(flags):
    phase = str(flags.get("phase", "GPP") or "GPP").strip().upper()
    conditioning_substep_callback = flags.get("conditioning_substep_callback")

    def _emit_conditioning_substep(code: str, label: str) -> None:
        if conditioning_substep_callback is None:
            return
        try:
            conditioning_substep_callback(code, label)
        except Exception:
            logger.exception("[progress] conditioning_callback_failed code=%s", code)

    def _run_conditioning_poststep(step_name: str, fn):
        _emit_conditioning_substep(f"stage1_conditioning_{step_name}_started", f"Stage 1 conditioning {step_name} started")
        step_started = perf_counter()
        result = fn()
        elapsed = perf_counter() - step_started
        logger.info("[stage1] conditioning_substep_elapsed step=%s elapsed=%.2f", step_name, elapsed)
        if elapsed > 5.0:
            logger.warning("[stage1] slow_conditioning_substep step=%s elapsed=%.2f", step_name, elapsed)
        _emit_conditioning_substep(f"stage1_conditioning_{step_name}_finished", f"Stage 1 conditioning {step_name} finished")
        return result

    phase_color = {"GPP": "#4CAF50", "SPP": "#FF9800", "TAPER": "#F44336"}.get(phase, "#000")

    fatigue = str(flags.get("fatigue", "low") or "low").strip().lower()
    style = flags.get("style_tactical") or []
    technical = flags.get("style_technical") or []
    goals = flags.get("key_goals") or []
    weaknesses = flags.get("weaknesses") or []
    priority_profile = build_priority_profile(
        SimpleNamespace(
            key_goals=goals,
            primary_goal=flags.get("primary_goal", ""),
            weak_areas=weaknesses,
            primary_weak_area=flags.get("primary_weak_area", ""),
        )
    )
    injuries = flags.get("injuries") or []
    restrictions = flags.get("restrictions")
    ignore_restrictions = bool(flags.get("ignore_restrictions", False))
    injury_trace = os.environ.get("INJURY_TRACE", "0") == "1"
    training_frequency = flags.get("training_frequency", flags.get("days_available", 3))
    equipment_access = normalize_athlete_equipment_list(flags.get("equipment", []))
    equipment_access_set = set(equipment_access)
    base_conditioning_bank = get_conditioning_bank()
    style_conditioning_bank = get_style_conditioning_bank()

    _normalize_tags_cache: dict[object, list[str]] = {}
    _normalize_equipment_cache: dict[object, list[str]] = {}
    _system_cache: dict[object, str | None] = {}
    _injury_match_cache: dict[object, dict] = {}
    _injury_decision_cache: dict[object, Decision] = {}
    _text_blob_cache: dict[object, str] = {}
    _structured_profile_cache: dict[tuple[object, str], dict] = {}
    _late_eval_cache: dict[tuple[object, str], dict] = {}

    def _drill_cache_key(drill: dict) -> object:
        return drill.get("id") or drill.get("name") or id(drill)

    def _cached_tags(drill: dict) -> list[str]:
        key = _drill_cache_key(drill)
        if key not in _normalize_tags_cache:
            _normalize_tags_cache[key] = normalize_tags(drill.get("tags", []))
        return _normalize_tags_cache[key]

    def _cached_equipment(drill: dict) -> list[str]:
        key = _drill_cache_key(drill)
        if key not in _normalize_equipment_cache:
            _normalize_equipment_cache[key] = normalize_equipment_list(drill.get("equipment", []))
        return _normalize_equipment_cache[key]

    def _cached_system(drill: dict, source: str) -> str | None:
        key = _drill_cache_key(drill)
        if key not in _system_cache:
            _system_cache[key] = get_system_or_warn(drill, source=source)
        return _system_cache[key]

    def _cached_injury_decision(drill: dict) -> Decision:
        key = _drill_cache_key(drill)
        if key not in _injury_decision_cache:
            _injury_decision_cache[key] = _guarded_injury_decision(drill)
        return _injury_decision_cache[key]

    def _cached_text_blob(drill: dict) -> str:
        key = _drill_cache_key(drill)
        if key not in _text_blob_cache:
            _text_blob_cache[key] = _conditioning_text_blob(drill)
        return _text_blob_cache[key]

    def _cached_structured_profile(drill: dict, system: str) -> dict:
        key = (_drill_cache_key(drill), str(system or ""))
        if key not in _structured_profile_cache:
            _structured_profile_cache[key] = _conditioning_structured_profile(drill, system=system)
        return _structured_profile_cache[key]

    def _cached_late_eval(drill: dict, system: str, source: str = "conditioning_bank.json") -> dict:
        key = (_drill_cache_key(drill), str(system or ""), source)
        if key not in _late_eval_cache:
            _late_eval_cache[key] = _evaluate_conditioning_late_window(
                drill,
                system=system,
                window=late_window,
                bridge_rules=bridge_rules,
                source=source,
            )
        return _late_eval_cache[key]

    def _cached_injury_match(drill: dict, fields, risk_levels):
        key = (_drill_cache_key(drill), tuple(fields), tuple(risk_levels))
        if key not in _injury_match_cache:
            _injury_match_cache[key] = injury_match_details(
                drill,
                injuries,
                fields=fields,
                risk_levels=risk_levels,
            )
        return _injury_match_cache[key]


    days_until_fight = _coerce_optional_int(flags.get("days_until_fight"))
    late_window = classify_late_selector_window(days_until_fight, include_control=True)
    active_late_window = is_active_late_selector_window(late_window)
    # Normalize technical style(s)
    if isinstance(technical, str):
        tech_styles = [t.strip().lower() for t in technical.split(',') if t.strip()]
    elif isinstance(technical, list):
        tech_styles = [t.strip().lower() for t in technical if t]
    else:
        tech_styles = []
    # First style in list determines fight format
    primary_tech = tech_styles[0] if tech_styles else ""

    # preserve tactical style names for style drill filtering
    if isinstance(style, list):
        style_names = [s.lower().replace(" ", "_") for s in style]
    elif isinstance(style, str) and style:
        style_names = [style.lower().replace(" ", "_")]
    else:
        style_names = []
    tech_style_tags = [t.replace(" ", "_") for t in tech_styles]
    if not style_names:
        style_names = tech_style_tags

    style_tags = [s.lower() for s in style] if isinstance(style, list) else [style.lower()]
    style_tags = normalize_tags([t for s in style_tags for t in STYLE_TAG_MAP.get(s, [])])

    goal_tags = expand_tags(goals, GOAL_TAG_MAP)
    goal_list = [g.lower() for g in goals]
    weak_list = [w.lower() for w in weaknesses]
    weak_tags = expand_tags(weaknesses, WEAKNESS_TAG_MAP)
    raw_goal_tokens = _normalize_focus_tokens(goal_list)
    raw_weak_tokens = _normalize_focus_tokens(weak_list)
    goal_tag_tokens = _normalize_focus_tokens(goal_tags)
    
    speed_goal_requested = bool(
        (raw_goal_tokens | raw_weak_tokens | goal_tag_tokens) & _SPEED_GOAL_TOKENS
    )

    speed_dose_allowed = (
        speed_goal_requested
        and fatigue != "high"
        and not active_late_window
        and phase.upper() != "TAPER"
    )
    alactic_primary_cap = 2 if speed_dose_allowed else 1
    derived_clarification_tags = _conditioning_resolve_derived_clarification_tags(flags)
    preferred_exercise_names = {
        str(name).strip().lower()
        for name in clean_list(flags.get("preferred_exercise_names", []))
        if str(name).strip()
    }
    shoulder_focus = any('shoulder' in g.lower() for g in goals) or any(
        'shoulder' in w.lower() for w in weaknesses
    )

    style_map = {
        "mma": "mma",
        "boxer": "boxing",
        "boxing": "boxing",
        "kickboxer": "kickboxing",
        "kickboxing": "kickboxing",
        "muay thai": "muay_thai",
        "muaythai": "muay_thai",
        "bjj": "mma",
        "wrestler": "mma",
        "wrestling": "wrestler",
        "grappler": "mma",
        "grappling": "grappler",
        "karate": "kickboxing",
    }
    fight_format = style_map.get(primary_tech, "mma")
    selection_format = _normalize_fight_format(fight_format)
    specificity_sport_tag = _style_specificity_sport_tag(primary_tech, selection_format)
    energy_weights = get_format_weights().get(selection_format, {})
    bridge_rules = (
        _conditioning_resolve_bridge_rules(
            flags=flags,
            days_until_fight=days_until_fight,
            sport=flags.get("sport") or selection_format,
            style_names=style_names,
            tech_style_tags=tech_style_tags,
            fatigue=fatigue,
        )
        if active_late_window
        else {}
    )

    rename_map = BOXING_NAME_MAP if selection_format == "boxing" else {}

    format_tag_map = {
        "mma": ["mma", "bjj", "wrestler"],
        "boxing": ["boxing"],
        "kickboxing": ["kickboxing", "muay_thai"],
        "muay_thai": ["muay_thai"]
    }
    fight_format_tags = flags.get("fight_format_tags") or format_tag_map.get(selection_format, [])

    phase_priority = {
        "GPP": ["aerobic", "glycolytic", "alactic"],
        "SPP": ["glycolytic", "alactic", "aerobic"],
        "TAPER": ["alactic", "aerobic", "glycolytic"]
    }
    preferred_order = phase_priority.get(phase.upper(), ["aerobic", "glycolytic", "alactic"])
    system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}
    style_system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}
    scored_system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}
    scored_style_system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}
    # Track drills per individual style for even distribution
    style_drills_by_style = {
        s: {"aerobic": [], "glycolytic": [], "alactic": []} for s in style_names
    }
    selected_drill_names = []
    reason_lookup: dict[str, dict] = {}
    excluded_by_injury: list[dict] = []
    restriction_candidates = 0
    restriction_blocked = 0
    restriction_reason_counts: dict[str, int] = defaultdict(int)
    restriction_warning_counts: dict[str, int] = defaultdict(int)
    restriction_blocked_items: list[dict] = []
    late_window_blocked: list[dict] = []
    late_window_penalized: list[dict] = []
    late_window_ambiguous: dict[str, dict] = {}
    style_conditioning_diagnostics: dict[str, object] = {
        "total_style_bank_entries_loaded": len(style_conditioning_bank),
        "entries_passing_phase": 0,
        "entries_passing_target_style_match": 0,
        "entries_blocked_by_sport_language_ban": 0,
        "entries_blocked_by_equipment": 0,
        "entries_blocked_by_alactic_structure": 0,
        "entries_blocked_by_injury_restrictions": 0,
        "entries_blocked_by_late_window": 0,
        "entries_scored": 0,
        "entries_exact_sport_bonus_applied": 0,
        "entries_selected": 0,
        "final_selected_exact_sport_names": [],
        "style_target": 0,
        "style_remaining_before_selection": 0,
        "final_selected_style_conditioning_names": [],
    }
    style_conditioning_scored_names: set[str] = set()

    def _record_late_block(drill: dict, score: float, reason_codes: list[str]) -> None:
        if not active_late_window:
            return
        late_window_blocked.append(
            {
                "name": drill.get("name", "<unnamed>"),
                "score": round(float(score), 4),
                "reason_codes": list(reason_codes),
            }
        )

    def _record_late_penalty(drill: dict, score: float, penalty_codes: list[str]) -> None:
        if not active_late_window or not penalty_codes:
            return
        late_window_penalized.append(
            {
                "name": drill.get("name", "<unnamed>"),
                "score": round(float(score), 4),
                "penalty_codes": list(penalty_codes),
            }
        )

    def _record_ambiguous_gap(ambiguous_gap: dict | None) -> None:
        if not active_late_window or not ambiguous_gap:
            return
        name = str(ambiguous_gap.get("name") or "").strip()
        if not name:
            return
        late_window_ambiguous[name] = ambiguous_gap

    def _load_and_score_base_conditioning_bank() -> None:
            nonlocal restriction_candidates, restriction_blocked
            for drill in base_conditioning_bank:
                d = drill.copy()
                if d.get("placement", "conditioning").lower() != "conditioning":
                    continue
                if selection_format == "boxing":
                    d["name"] = rename_map.get(d.get("name"), d.get("name"))
                    d["tags"] = [
                        "boxing" if t.lower() == "muay_thai" else t
                        for t in d.get("tags", [])
                    ]
                d["name"] = _normalize_conditioning_name(d.get("name", ""), fight_format=selection_format)
                if phase.upper() not in d.get("phases", []):
                    continue

                system = _cached_system(d, "conditioning_bank.json")
                if system is None:
                    continue
                if system == "alactic" and not _alactic_structure_ok(d):
                    continue

                tags = _cached_tags(d)
                details = " ".join(
                    [
                        d.get("duration", ""),
                        d.get("notes", ""),
                        d.get("modality", ""),
                        d.get("equipment_note", ""),
                    ]
                )
                restriction_text = " ".join(
                    [
                        d.get("name", ""),
                        d.get("modality", ""),
                        d.get("notes", ""),
                        d.get("equipment_note", ""),
                    ]
                )
                if is_banned_drill(
                    d.get("name", ""),
                    tags,
                    selection_format,
                    details,
                    style_names,
                    tech_style_tags,
                ):
                    continue
                if _violates_sport_language_blacklist(d, fight_format=selection_format):
                    continue

                if (
                    selection_format == "boxing"
                    and phase.upper() == "TAPER"
                    and {"overhead", "rotational", "heavy_load"}.issubset(tags)
                    and not (shoulder_focus and fatigue == "low")
                ):
                    continue

                drill_equipment = _cached_equipment(d)
                if drill_equipment and not set(drill_equipment).issubset(equipment_access_set):
                    continue

                # Suppress high CNS drills in TAPER unless criteria met
                if (
                    phase.upper() == "TAPER"
                    and "high_cns" in tags
                    and not (
                        fatigue == "low"
                        and system == "alactic"
                        and any(t in weak_tags or t in goal_tags for t in tags)
                    )
                ):
                    continue

                # Additional tag suppression in TAPER for moderate/high fatigue
                if (
                    phase.upper() == "TAPER"
                    and fatigue != "low"
                    and any(t in TAPER_AVOID_TAGS for t in tags)
                    and not any(t in goal_tags or t in weak_tags for t in tags)
                ):
                    continue

                restriction_candidates += 1
                restriction_result = evaluate_restriction_impact(
                    restrictions,
                    text=restriction_text,
                    tags=tags,
                    limit_penalty=-0.75,
                )
                restriction_penalty = restriction_result.get("penalty", 0.0)
                matched_restrictions = restriction_result.get("matched", [])
                if not ignore_restrictions and not restriction_result.get("allowed", True):
                    restriction_blocked += 1
                    for match in matched_restrictions:
                        restriction_reason_counts[match.get("restriction", "generic_constraint")] += 1
                    if matched_restrictions:
                        top_match = max(matched_restrictions, key=lambda m: m.get("confidence", 0))
                        restriction_blocked_items.append(
                            {
                                "name": d.get("name", "<unnamed>"),
                                "match": top_match,
                                "risk": restriction_result.get("risk", 0.0),
                            }
                        )
                    if injury_trace:
                        print(
                            "[guard-block] conditioning:%s name=%s matched=%s risk=%.2f"
                            % (
                                phase.upper(),
                                d.get("name", "<unnamed>"),
                                matched_restrictions,
                                restriction_result.get("risk", 0.0),
                            )
                        )
                    continue
                if restriction_result.get("no_match_hints"):
                    for hint in restriction_result.get("no_match_hints", []):
                        restriction_warning_counts[hint] += 1

                matched_weak_tags = sorted({t for t in tags if t in weak_tags})
                matched_goal_tags = sorted({t for t in tags if t in goal_tags})
                num_weak = len(matched_weak_tags)
                num_goals = len(matched_goal_tags)
                num_style = sum(1 for t in tags if t in style_tags)
                num_format = sum(1 for t in tags if t in fight_format_tags)

                base_score = _conditioning_collision_safe_priority_bonus(
                    matched_goal_tags,
                    matched_weak_tags,
                    priority_profile,
                )
                clarification_bonus, clarification_hits = _conditioning_clarification_bonus(tags, derived_clarification_tags)
                base_score += clarification_bonus
                base_score += 0.75 * min(num_style, 2)
                base_score += 1.0 * min(num_format, 1)

                energy_multiplier = energy_weights.get(system, 1.0)
                system_score = round(energy_multiplier * 1.0, 2)
                total_score = base_score + system_score

                preferred_name_match = str(d.get("name", "")).strip().lower() in preferred_exercise_names
                if preferred_name_match:
                    total_score += PREFERRED_EXERCISE_NAME_BOOST

                penalty = 0.0
                if fatigue == "high" and "high_cns" in tags:
                    total_score -= 2.0
                    penalty = -2.0
                elif fatigue == "moderate" and "high_cns" in tags:
                    total_score -= 1.0
                    penalty = -1.0
                boxer_aerobic_adjustment = 0.0
                if selection_format == "boxing" and system == "aerobic":
                    boxer_aerobic_adjustment = _boxing_aerobic_priority_adjustment(
                        d,
                        injuries=injuries,
                        weaknesses=weaknesses,
                        goals=goals,
                        restrictions=restrictions,
                        equipment_access_set=equipment_access_set,
                    )
                    total_score += boxer_aerobic_adjustment
                if not ignore_restrictions and restriction_penalty:
                    total_score += restriction_penalty
                    penalty += restriction_penalty
                late_eval = _cached_late_eval(d, system, "conditioning_bank.json")
                _record_ambiguous_gap(late_eval.get("ambiguous_gap"))
                if late_eval["blocked"]:
                    _record_late_block(d, total_score, late_eval["block_codes"])
                    continue
                if late_eval.get("penalty_codes"):
                    _record_late_penalty(d, total_score, late_eval["penalty_codes"])
                if late_eval["adjustment"]:
                    total_score += late_eval["adjustment"]
                if (
                    phase.upper() == "TAPER"
                    and isinstance(days_until_fight, int)
                    and days_until_fight <= 7
                    and d.get("name") not in TAPER_CONDITIONING_SAFE_NAMES
                ):
                    _record_late_block(d, total_score, ["late_taper_safe_whitelist"])
                    continue

                reasons = {
                    "weakness_hits": num_weak,
                    "goal_hits": num_goals,
                    "style_hits": num_style,
                    "phase_hits": 1,
                    "load_adjustments": system_score,
                    "equipment_boost": 0.0,
                    "preferred_exercise_name_match": PREFERRED_EXERCISE_NAME_BOOST if preferred_name_match else 0.0,
                    "penalties": penalty,
                    "restriction_hits": len(matched_restrictions),
                    "boxing_aerobic_preference": round(boxer_aerobic_adjustment, 4),
                    "clarification_tag_hits": clarification_hits,
                    "clarification_bonus": round(clarification_bonus, 4),
                    "reason_codes": list(late_eval["reason_codes"]),
                    "penalty_codes": list(late_eval.get("penalty_codes", [])),
                    "late_window_adjustment": late_eval["adjustment"],
                    "final_score": round(total_score, 4),
                }
                _add_conditioning_priority_reason_codes(reasons, matched_goal_tags, matched_weak_tags, priority_profile)
                for tag in clarification_hits:
                    reasons["reason_codes"].append(f"priority_clarification_tag_match:{tag}")
                if preferred_name_match:
                    reasons["reason_codes"].append(f"preferred_exercise_name_match:+{PREFERRED_EXERCISE_NAME_BOOST:.1f}")

                entry = (d, total_score, reasons)
                system_drills[system].append(entry)
                scored_system_drills[system].append(entry)

    _run_conditioning_poststep("base_bank_score", _load_and_score_base_conditioning_bank)

    # ---- Style specific conditioning ----
    target_style_tags = set(
        normalize_tags(
            [
                *style_names,
                *tech_style_tags,
                *fight_format_tags,
                selection_format,
                *style_tags,
            ]
        )
    )
    style_conditioning_diagnostics["target_style_tags"] = sorted(target_style_tags)

    def _style_bucket_tags(style_name: str) -> set[str]:
        raw_name = str(style_name or "").strip()
        if not raw_name:
            return set()
        spaced_name = raw_name.replace("_", " ")
        return set(
            normalize_tags(
                [
                    raw_name,
                    spaced_name,
                    *STYLE_TAG_MAP.get(raw_name, []),
                    *STYLE_TAG_MAP.get(spaced_name, []),
                ]
            )
        )

    # Precompute each declared style's bucket tags once so per-style distribution
    # can test a scored drill's tags against the style it belongs to.
    style_bucket_tags_map = {st: _style_bucket_tags(st) for st in style_names}

    def _load_and_score_style_conditioning_bank() -> None:
            nonlocal restriction_candidates, restriction_blocked
            for drill in style_conditioning_bank:
                # Compute specificity before any runtime sport-tag compatibility rewrite.
                sport_specificity_bonus = _style_exact_sport_bonus(
                    drill.get("tags", []), specificity_sport_tag
                )
                d = drill.copy()
                if d.get("placement", "conditioning").lower() != "conditioning":
                    continue
                if selection_format == "boxing":
                    d["name"] = rename_map.get(d.get("name"), d.get("name"))
                    d["tags"] = [
                        "boxing" if t.lower() == "muay_thai" else t
                        for t in d.get("tags", [])
                    ]
                d["name"] = _normalize_conditioning_name(d.get("name", ""), fight_format=selection_format)
                tags = _cached_tags(d)
                details = " ".join(
                    [
                        d.get("duration", ""),
                        d.get("notes", ""),
                        d.get("modality", ""),
                        d.get("equipment_note", ""),
                    ]
                )
                restriction_text = " ".join(
                    [
                        d.get("name", ""),
                        d.get("modality", ""),
                        d.get("notes", ""),
                        d.get("equipment_note", ""),
                    ]
                )
                if phase.upper() in d.get("phases", []):
                    style_conditioning_diagnostics["entries_passing_phase"] += 1
                if is_banned_drill(
                    d.get("name", ""),
                    tags,
                    selection_format,
                    details,
                    style_names,
                    tech_style_tags,
                ):
                    style_conditioning_diagnostics["entries_blocked_by_sport_language_ban"] += 1
                    continue
                if _violates_sport_language_blacklist(d, fight_format=selection_format):
                    style_conditioning_diagnostics["entries_blocked_by_sport_language_ban"] += 1
                    continue
                matched_style_tokens = target_style_tags.intersection(tags)
                if not matched_style_tokens:
                    continue
                style_conditioning_diagnostics["entries_passing_target_style_match"] += 1
                if phase.upper() not in d.get("phases", []):
                    continue

                if (
                    selection_format == "boxing"
                    and phase.upper() == "TAPER"
                    and {"overhead", "rotational", "heavy_load"}.issubset(tags)
                    and not (shoulder_focus and fatigue == "low")
                ):
                    style_conditioning_diagnostics["entries_blocked_by_late_window"] += 1
                    continue

                system = _cached_system(d, "style_conditioning_bank.json")
                if system is None:
                    continue
                if system == "alactic" and not _alactic_structure_ok(d):
                    style_conditioning_diagnostics["entries_blocked_by_alactic_structure"] += 1
                    continue

                # Apply same fatigue/CNS suppression rules
                if (
                    phase.upper() == "TAPER"
                    and "high_cns" in tags
                    and not (
                        fatigue == "low"
                        and system == "alactic"
                        and any(t in weak_tags or t in goal_tags for t in tags)
                    )
                ):
                    style_conditioning_diagnostics["entries_blocked_by_late_window"] += 1
                    continue
                if (
                    phase.upper() == "TAPER"
                    and fatigue != "low"
                    and any(t in TAPER_AVOID_TAGS for t in tags)
                    and not any(t in goal_tags or t in weak_tags for t in tags)
                ):
                    style_conditioning_diagnostics["entries_blocked_by_late_window"] += 1
                    continue
                drill_equipment = _cached_equipment(d)
                if drill_equipment and not set(drill_equipment).issubset(equipment_access_set):
                    style_conditioning_diagnostics["entries_blocked_by_equipment"] += 1
                    continue
                equip_bonus = 0.5 if drill_equipment else 0.0

                restriction_candidates += 1
                restriction_result = evaluate_restriction_impact(
                    restrictions,
                    text=restriction_text,
                    tags=tags,
                    limit_penalty=-0.75,
                )
                restriction_penalty = restriction_result.get("penalty", 0.0)
                matched_restrictions = restriction_result.get("matched", [])
                if not ignore_restrictions and not restriction_result.get("allowed", True):
                    style_conditioning_diagnostics["entries_blocked_by_injury_restrictions"] += 1
                    restriction_blocked += 1
                    for match in matched_restrictions:
                        restriction_reason_counts[match.get("restriction", "generic_constraint")] += 1
                    if matched_restrictions:
                        top_match = max(matched_restrictions, key=lambda m: m.get("confidence", 0))
                        restriction_blocked_items.append(
                            {
                                "name": d.get("name", "<unnamed>"),
                                "match": top_match,
                                "risk": restriction_result.get("risk", 0.0),
                            }
                        )
                    if injury_trace:
                        print(
                            "[guard-block] conditioning:%s name=%s matched=%s risk=%.2f"
                            % (
                                phase.upper(),
                                d.get("name", "<unnamed>"),
                                matched_restrictions,
                                restriction_result.get("risk", 0.0),
                            )
                        )
                    continue
                if restriction_result.get("no_match_hints"):
                    for hint in restriction_result.get("no_match_hints", []):
                        restriction_warning_counts[hint] += 1

                matched_weak_tags = sorted({t for t in tags if t in weak_tags})
                matched_goal_tags = sorted({t for t in tags if t in goal_tags})
                weak_matches = len(matched_weak_tags)
                goal_matches = len(matched_goal_tags)
                top_system = preferred_order[0]
                if system != top_system and not weak_matches and not goal_matches:
                    continue

                score = 0.0
                score += 0.75  # style match already guaranteed by filter
                score += 1.0  # phase match
                if system == top_system:
                    score += 0.75
                score += equip_bonus
                score += sport_specificity_bonus
                if sport_specificity_bonus:
                    style_conditioning_diagnostics["entries_exact_sport_bonus_applied"] += 1
                score += _conditioning_collision_safe_priority_bonus(
                    matched_goal_tags,
                    matched_weak_tags,
                    priority_profile,
                )
                clarification_bonus, clarification_hits = _conditioning_clarification_bonus(tags, derived_clarification_tags)
                score += clarification_bonus
                preferred_name_match = str(d.get("name", "")).strip().lower() in preferred_exercise_names
                if preferred_name_match:
                    score += PREFERRED_EXERCISE_NAME_BOOST
                penalty = 0.0
                if "high_cns" in tags:
                    if fatigue == "high":
                        score -= 1.0
                        penalty = -1.0
                    elif fatigue == "moderate":
                        score -= 0.5
                        penalty = -0.5
                boxer_aerobic_adjustment = 0.0
                if selection_format == "boxing" and system == "aerobic":
                    boxer_aerobic_adjustment = _boxing_aerobic_priority_adjustment(
                        d,
                        injuries=injuries,
                        weaknesses=weaknesses,
                        goals=goals,
                        restrictions=restrictions,
                        equipment_access_set=equipment_access_set,
                    )
                    score += boxer_aerobic_adjustment
                if not ignore_restrictions and restriction_penalty:
                    score += restriction_penalty
                    penalty += restriction_penalty
                late_eval = _cached_late_eval(d, system, "style_conditioning_bank.json")
                _record_ambiguous_gap(late_eval.get("ambiguous_gap"))
                if late_eval["blocked"]:
                    style_conditioning_diagnostics["entries_blocked_by_late_window"] += 1
                    _record_late_block(d, score, late_eval["block_codes"])
                    continue
                if late_eval.get("penalty_codes"):
                    _record_late_penalty(d, score, late_eval["penalty_codes"])
                if late_eval["adjustment"]:
                    score += late_eval["adjustment"]
                if (
                    phase.upper() == "TAPER"
                    and isinstance(days_until_fight, int)
                    and days_until_fight <= 7
                    and d.get("name") not in TAPER_CONDITIONING_SAFE_NAMES
                ):
                    style_conditioning_diagnostics["entries_blocked_by_late_window"] += 1
                    _record_late_block(d, score, ["late_taper_safe_whitelist"])
                    continue
                reasons = {
                    "weakness_hits": weak_matches,
                    "goal_hits": goal_matches,
                    "style_hits": 1,
                    "phase_hits": 1,
                    "load_adjustments": 0.75 if system == top_system else 0.0,
                    "equipment_boost": equip_bonus,
                    "sport_specificity_bonus": sport_specificity_bonus,
                    "exact_sport_match": bool(sport_specificity_bonus),
                    "preferred_exercise_name_match": PREFERRED_EXERCISE_NAME_BOOST if preferred_name_match else 0.0,
                    "penalties": penalty,
                    "restriction_hits": len(matched_restrictions),
                    "boxing_aerobic_preference": round(boxer_aerobic_adjustment, 4),
                    "clarification_tag_hits": clarification_hits,
                    "clarification_bonus": round(clarification_bonus, 4),
                    "reason_codes": list(late_eval["reason_codes"]),
                    "penalty_codes": list(late_eval.get("penalty_codes", [])),
                    "late_window_adjustment": late_eval["adjustment"],
                    "final_score": round(score, 4),
                }
                _add_conditioning_priority_reason_codes(reasons, matched_goal_tags, matched_weak_tags, priority_profile)
                for tag in clarification_hits:
                    reasons["reason_codes"].append(f"priority_clarification_tag_match:{tag}")
                if preferred_name_match:
                    reasons["reason_codes"].append(f"preferred_exercise_name_match:+{PREFERRED_EXERCISE_NAME_BOOST:.1f}")
                if sport_specificity_bonus:
                    reasons["reason_codes"].append(
                        f"exact_sport_match:+{STYLE_EXACT_SPORT_BONUS:.1f}"
                    )

                entry = (d, score, reasons)
                style_system_drills[system].append(entry)
                scored_style_system_drills[system].append(entry)
                style_conditioning_diagnostics["entries_scored"] += 1
                if d.get("name"):
                    style_conditioning_scored_names.add(d["name"])
                for st in style_names:
                    if style_bucket_tags_map[st].intersection(tags):
                        style_drills_by_style[st][system].append((d, score, reasons))

    _run_conditioning_poststep("style_bank_score", _load_and_score_style_conditioning_bank)

    for drills in system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)
    for drills in style_system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)
    for style_lists in style_drills_by_style.values():
        for drills in style_lists.values():
            drills.sort(key=lambda x: x[1], reverse=True)

    if selection_format == "boxing":
        def _boxing_sort_key(item: tuple[dict, float, dict]) -> tuple[int, float]:
            drill, score, _ = item
            return (
                _boxing_aerobic_preference_rank(
                    drill,
                    injuries=injuries,
                    weaknesses=weaknesses,
                    goals=goals,
                    restrictions=restrictions,
                    equipment_access_set=equipment_access_set,
                ),
                -score,
            )

        system_drills["aerobic"].sort(key=_boxing_sort_key)
        style_system_drills["aerobic"].sort(key=_boxing_sort_key)
        for style_lists in style_drills_by_style.values():
            style_lists["aerobic"].sort(key=_boxing_sort_key)

    if injury_trace and restrictions:
        active_restrictions = sorted({r.get("restriction", "generic_constraint") for r in restrictions})
        top_blocks = sorted(
            restriction_blocked_items,
            key=lambda item: item.get("risk", 0.0),
            reverse=True,
        )[:5]
        formatted_blocks = [
            {
                "name": item.get("name"),
                "rule": item.get("match", {}).get("restriction"),
                "method": item.get("match", {}).get("method"),
                "confidence": item.get("match", {}).get("confidence"),
                "risk": item.get("risk"),
            }
            for item in top_blocks
        ]
        logger.info(
            "[guard-report] conditioning:%s restrictions=%s candidates=%d blocked=%d reasons=%s",
            phase.upper(),
            active_restrictions,
            restriction_candidates,
            restriction_blocked,
            dict(restriction_reason_counts),
        )
        logger.info(
            "[guard-report] conditioning:%s top_blocks=%s",
            phase.upper(),
            formatted_blocks,
        )
        logger.info(
            "[guard-report] conditioning:%s warnings=%s",
            phase.upper(),
            dict(restriction_warning_counts),
        )

    # Refactored: Use utility function instead of local duplicate implementation
    system_drills = {system: trim_to_injury_guard_shortlist(drills) for system, drills in system_drills.items()}
    style_system_drills = {system: trim_to_injury_guard_shortlist(drills) for system, drills in style_system_drills.items()}
    style_drills_by_style = {
        style: {system: trim_to_injury_guard_shortlist(drills) for system, drills in systems.items()}
        for style, systems in style_drills_by_style.items()
    }

    injury_guard_names: set[str] = {
        d.get("name")
        for drills in system_drills.values()
        for d, _, _ in drills
        if d.get("name")
    }
    injury_guard_names |= {
        d.get("name")
        for drills in style_system_drills.values()
        for d, _, _ in drills
        if d.get("name")
    }

    # Refactored: Use factory function instead of local duplicate implementation
    _guarded_injury_decision = make_guarded_decision_factory(
        injuries,
        phase,
        fatigue,
        injury_guard_names,
        restrictions=restrictions,
        ignore_restrictions=ignore_restrictions,
    )

    all_candidates_by_system = {
        system: [drill for drill, _, _ in system_drills.get(system, [])]
        + [drill for drill, _, _ in style_system_drills.get(system, [])]
        for system in system_drills
    }
    score_lookup: dict[str, float] = {}
    for drills in (system_drills, style_system_drills):
        for drill_list in drills.values():
            for drill, score, _ in drill_list:
                name = drill.get("name")
                if not name:
                    continue
                score_lookup[name] = max(score_lookup.get(name, float("-inf")), score)

    num_conditioning_sessions = allocate_sessions(training_frequency, phase).get(
        "conditioning", 0
    )
    exercise_counts = calculate_exercise_numbers(training_frequency, phase)

    # Use recommended drill count based on phase multipliers
    total_drills = exercise_counts.get("conditioning", 0)

    system_quota = {
        k: max(1 if v > 0 else 0, round(total_drills * v))
        for k, v in PHASE_SYSTEM_RATIOS.get(phase.upper(), {}).items()
    }
    visible_drill_cap = total_drills
    if speed_dose_allowed:
        system_quota["alactic"] = min(system_quota.get("alactic", 0) + 1, 2)
        visible_drill_cap = total_drills + 1

    # Whether the athlete has an explicit footwork/ring-movement focus. Gates
    # the dedicated technical footwork insert (below). Technical footwork is a
    # relevance-gated supplementary insert, never a primary energy-system
    # conditioning dose, mirroring the coordination-goal guarantee.
    technical_footwork_focus = _technical_footwork_relevance(flags)

    final_drills = []
    taper_selected = 0
    selected_counts = {"aerobic": 0, "glycolytic": 0, "alactic": 0}

    style_counts = {s: 0 for s in style_names}

    def _delay_pool_treading(
        drill: dict,
        remaining_candidates: list[tuple[dict, float, dict]],
        system: str,
    ) -> bool:
        if selection_format != "boxing" or system != "aerobic" or not _is_pool_treading_drill(drill):
            return False
        if _boxing_aerobic_priority_adjustment(
            drill,
            injuries=injuries,
            weaknesses=weaknesses,
            goals=goals,
            restrictions=restrictions,
            equipment_access_set=equipment_access_set,
        ) >= 0:
            return False
        return any(not _is_pool_treading_drill(candidate) for candidate, _, _ in remaining_candidates)

    def pop_drill(source: dict, system: str):
        drills = source.get(system, [])
        for idx, (drill, _, reasons) in enumerate(drills):
            if _delay_pool_treading(drill, drills[idx + 1 :], system):
                continue
            name = drill.get("name")
            tags = _cached_tags(drill)
            allow_repeat = (
                phase.upper() == "TAPER"
                and system == "alactic"
                and any(t in weak_tags for t in tags)
            )
            if name in selected_drill_names and not allow_repeat:
                continue
            selected_drill_names.append(name)
            del drills[idx]
            source[system] = drills
            return drill, reasons
        return None, None

    def pop_style_drill(system: str):
        for style in sorted(style_counts, key=style_counts.get):
            drills = style_drills_by_style.get(style, {}).get(system, [])
            for idx, (drill, _, reasons) in enumerate(drills):
                if _delay_pool_treading(drill, drills[idx + 1 :], system):
                    continue
                name = drill.get("name")
                tags = _cached_tags(drill)
                allow_repeat = (
                    phase.upper() == "TAPER"
                    and system == "alactic"
                    and any(t in weak_tags for t in tags)
                )
                if name in selected_drill_names and not allow_repeat:
                    continue
                selected_drill_names.append(name)
                del drills[idx]
                style_drills_by_style[style][system] = drills
                style_counts[style] += 1
                return drill, reasons
        return None, None

    style_candidate_count = sum(len(v) for v in style_system_drills.values())
    style_target = round(total_drills * STYLE_CONDITIONING_RATIO.get(phase.upper(), 0))
    normalized_focus_tokens = _normalize_focus_tokens([*goal_list, *weak_list, *goal_tags, *weak_tags])
    conditioning_focus_requested = bool(
        normalized_focus_tokens
        & {
            "conditioning",
            "endurance",
            "gas tank",
            "gas_tank",
            "work capacity",
            "work_capacity",
            "aerobic",
            "glycolytic",
        }
    )
    style_specific_relevant = bool(style_names or tech_style_tags or style_tags)
    if (
        phase.upper() == "GPP"
        and num_conditioning_sessions > 0
        and style_candidate_count > 0
        and total_drills > 0
        and (conditioning_focus_requested or style_specific_relevant)
    ):
        style_target = max(style_target, 1)
    elif (
        phase.upper() == "SPP"
        and num_conditioning_sessions > 0
        and style_candidate_count > 0
        and total_drills > 0
    ):
        style_target = max(style_target, min(2, total_drills))
    elif phase.upper() == "TAPER":
        style_target = 0

    style_remaining = min(style_target, style_candidate_count)
    style_remaining_before_selection = style_remaining
    style_conditioning_diagnostics["style_target"] = style_target
    style_conditioning_diagnostics["style_remaining_before_selection"] = style_remaining_before_selection
    general_remaining = visible_drill_cap - style_remaining

    allow_glycolytic = False
    aerobic_maintenance_signal = _has_aerobic_maintenance_signal(goals, weaknesses)
    allow_aerobic_maintenance = (
        active_late_window
        and late_window in _AEROBIC_MAINTENANCE_WINDOWS
        and aerobic_maintenance_signal
    )
    if phase.upper() == "TAPER":
        lactic_goal_tags = {"glycolytic", "anaerobic_lactic", "lactic"}
        has_conditioning_goal = any(g in {"conditioning", "endurance"} for g in goal_list)
        has_lactic_goal = bool(set(goal_tags) & lactic_goal_tags)
        if active_late_window:
            allow_glycolytic = (
                fatigue == "low"
                and (has_conditioning_goal or has_lactic_goal)
                and (bridge_rules.get("glycolytic_touch_max", 0) > 0)
            )
        else:
            allow_glycolytic = (
                fatigue == "low"
                and (has_conditioning_goal or has_lactic_goal)
                and isinstance(days_until_fight, int)
                and days_until_fight > 7
            )

    def _allow_system_insert(system: str) -> bool:
        if phase.upper() == "TAPER" and system == "glycolytic":
            return allow_glycolytic and selected_counts["glycolytic"] < 1
        return True

    def _append_drill(system: str, drill: dict, reasons: dict | None) -> bool:
        name = drill.get("name")

        if not isinstance(name, str) or not name.strip():
            return False

        name = name.strip()

        if not _allow_system_insert(system):
            return False

        if name in selected_drill_names:
            return False

        final_drills.append((system, [drill]))
        selected_drill_names.append(name)

        if system in selected_counts:
            selected_counts[system] += 1

        if reasons is not None:
            reason_lookup[name] = reasons

        return True

    def _try_append_conditioning_drill(
        system: str,
        drill: dict,
        reasons: dict | None,
        *,
        source: str,
        enforce_restrictions: bool = True,
        enforce_injury: bool = True,
        enforce_late_window: bool = True,
        group_key: str | None = None,
    ) -> bool:
        """Safely append late/guarantee conditioning drills.

        ``system`` is the real physiological system used for late-window and
        injury gating. ``group_key`` (defaulting to ``system``) is the bucket the
        drill is actually placed into for grouping/rendering/dose accounting;
        technical footwork passes ``TECHNICAL_FOOTWORK_GROUP`` here so it is
        gated exactly like an aerobic drill but never counted or resolved as an
        aerobic energy-system dose.
        """

        name = drill.get("name")
        if not isinstance(name, str) or not name.strip():
            return False

        name = name.strip()

        if name in selected_drill_names:
            return False

        if not _allow_system_insert(system):
            return False

        drill_equipment = _cached_equipment(drill)
        if drill_equipment and not set(drill_equipment).issubset(equipment_access_set):
            return False

        tags = _cached_tags(drill)
        restriction_text = " ".join(
            str(value or "")
            for value in [
                drill.get("name", ""),
                drill.get("modality", ""),
                drill.get("notes", ""),
                drill.get("equipment_note", ""),
            ]
        )

        if enforce_restrictions and not ignore_restrictions:
            restriction_result = evaluate_restriction_impact(
                restrictions,
                text=restriction_text,
                tags=tags,
                limit_penalty=-0.75,
            )

            if not restriction_result.get("allowed", True):
                return False

        if enforce_injury:
            decision = _cached_injury_decision(drill)
            if decision.action == "exclude":
                _log_exclusion(f"conditioning:{phase.upper()}:{source}", drill, decision)
                return False

        if enforce_late_window:
            source_file = {
                "coordination": "coordination_bank.json",
                "skill_refinement": "style_conditioning_bank.json",
                "style_taper": "style_taper_conditioning.json",
                "technical_footwork": "technical_footwork_bank.json",
                "runtime_fallback": "runtime_fallback",
            }.get(source, "conditioning_bank.json")
            late_eval = _cached_late_eval(drill, system, source_file)
            _record_ambiguous_gap(late_eval.get("ambiguous_gap"))

            if late_eval["blocked"]:
                _record_late_block(drill, 0.0, late_eval["block_codes"])
                return False
            if late_eval.get("penalty_codes"):
                _record_late_penalty(drill, 0.0, late_eval["penalty_codes"])

            if reasons is not None:
                reasons = {
                    **reasons,
                    "reason_codes": list(reasons.get("reason_codes", []))
                    + list(late_eval["reason_codes"]),
                    "penalty_codes": list(reasons.get("penalty_codes", []))
                    + list(late_eval.get("penalty_codes", [])),
                    "late_window_adjustment": late_eval["adjustment"],
                    "final_score": round(
                        float(reasons.get("final_score", 0) or 0)
                        + float(late_eval["adjustment"] or 0),
                        4,
                    ),
                }

        return _append_drill(group_key or system, drill, reasons)

    _pool_treading_strong_case: bool | None = None

    def _base_head_is_priority_pool_treading(system: str) -> bool:
        """Whether the leading base aerobic drill is a strong-case pool tread.

        For an impact-restricted boxer with pool access, pool treading is the
        clinically-preferred zero-impact aerobic option — ``_boxing_sort_key``
        already ranks it to the head of the base list. Left to the default blend,
        a style shadow-drill takes the slot ahead of it and the injury guard then
        swaps that style pick out for a generic mobility drill, burying the pool
        option a rank down. Letting the strong-case pool drill lead keeps the
        athlete on the option their restriction actually calls for.
        """
        nonlocal _pool_treading_strong_case
        if system != "aerobic" or selection_format != "boxing" or general_remaining <= 0:
            return False
        head = next(
            (
                drill
                for drill, _score, _reasons in system_drills.get(system, [])
                if drill.get("name") not in selected_drill_names
            ),
            None,
        )
        if head is None or not _is_pool_treading_drill(head):
            return False
        if _pool_treading_strong_case is None:
            _pool_treading_strong_case = _boxing_aerobic_context_flags(
                injuries=injuries,
                weaknesses=weaknesses,
                goals=goals,
                restrictions=restrictions,
                equipment_access_set=equipment_access_set,
            )["pool_treading_strong_case"]
        return _pool_treading_strong_case

    def blended_pick(system: str):
        nonlocal style_remaining, general_remaining
        drill = None
        reasons = None
        if _base_head_is_priority_pool_treading(system):
            drill, reasons = pop_drill(system_drills, system)
            if drill:
                general_remaining -= 1
                return drill, reasons
        if style_remaining > 0:
            drill, reasons = pop_style_drill(system)
            if drill:
                style_remaining -= 1
                return drill, reasons
        if general_remaining > 0:
            drill, reasons = pop_drill(system_drills, system)
            if drill:
                general_remaining -= 1
                return drill, reasons
        return None, None

    if phase.upper() == "TAPER":
        combined_focus = [w.lower() for w in weaknesses] + goal_list
        allow_aerobic = any(k in combined_focus for k in ["conditioning", "endurance"])

        d, r = blended_pick("alactic")
        if d:
            final_drills.append(("alactic", [d]))
            reason_lookup[d.get("name")] = r
            selected_counts["alactic"] += 1
            taper_selected += 1

        if allow_aerobic and taper_selected < 2:
            d, r = blended_pick("aerobic")
            if d:
                final_drills.append(("aerobic", [d]))
                reason_lookup[d.get("name")] = r
                selected_counts["aerobic"] += 1
                taper_selected += 1

        if allow_glycolytic and taper_selected < 2 and _allow_system_insert("glycolytic"):
            d, r = blended_pick("glycolytic")
            if d:
                final_drills.append(("glycolytic", [d]))
                reason_lookup[d.get("name")] = r
                selected_counts["glycolytic"] += 1
                taper_selected += 1

        if allow_aerobic_maintenance and selected_counts["aerobic"] < 1:
            aerobic_candidates: list[tuple[dict, float, dict, int]] = []
            preferred_names = (
                "Rower Gas-Tank Flush",
                "Assault Bike Rhythm Primer",
            )
            for drill, score, reasons in system_drills.get("aerobic", []):
                if _is_low_noise_aerobic_maintenance_drill(drill, system="aerobic"):
                    name = str(drill.get("name") or "")
                    priority = 99
                    if name == preferred_names[0]:
                        priority = 0
                    elif name == preferred_names[1]:
                        priority = 1
                    elif "bike" in name.lower():
                        priority = 2
                    elif "shadowbox" in name.lower() or "shadow boxing" in name.lower():
                        priority = 3
                    aerobic_candidates.append((drill, score, reasons, priority))
            aerobic_candidates.sort(key=lambda item: (item[3], -item[1]))
            for drill, _score, reasons, _prio in aerobic_candidates:
                if _try_append_conditioning_drill("aerobic", drill, reasons, source="aerobic_maintenance_insert"):
                    break
    else:
        def _fill_system_quotas() -> None:
            for system in preferred_order:
                quota = system_quota.get(system, 0)
                if quota <= 0:
                    continue
                guard = 0
                max_iter = bounded_max_iterations(quota)
                while quota > 0:
                    guard += 1
                    if guard > max_iter:
                        log_fail_safe_degrade(module="conditioning", phase=phase, reason=f"system_quota_guard:{system}", target=system_quota.get(system, 0), actual=selected_counts.get(system, 0))
                        break
                    d, r = blended_pick(system)
                    if not d:
                        log_fail_safe_degrade(module="conditioning", phase=phase, reason=f"system_quota_no_candidate:{system}", target=system_quota.get(system, 0), actual=selected_counts.get(system, 0))
                        break
                    final_drills.append((system, [d]))
                    reason_lookup[d.get("name")] = r
                    selected_counts[system] += 1
                    quota -= 1

        def _fill_deficits() -> None:
            remaining_slots = total_drills - len(selected_drill_names)
            deficits = {
                s: max(0, system_quota.get(s, 0) - selected_counts.get(s, 0))
                for s in system_quota
            }
            guard = 0
            max_iter = bounded_max_iterations(remaining_slots)
            while remaining_slots > 0 and any(deficits.values()):
                guard += 1
                if guard > max_iter:
                    log_fail_safe_degrade(module="conditioning", phase=phase, reason="deficit_fill_guard", target=total_drills, actual=len(selected_drill_names))
                    break
                system = max(deficits, key=deficits.get)
                if deficits[system] <= 0:
                    break
                d, r = blended_pick(system)
                if not d:
                    log_fail_safe_degrade(module="conditioning", phase=phase, reason=f"deficit_fill_no_candidate:{system}", target=deficits[system], actual=0)
                    deficits[system] = 0
                    continue
                final_drills.append((system, [d]))
                reason_lookup[d.get("name")] = r
                selected_counts[system] += 1
                deficits[system] = max(0, deficits[system] - 1)
                remaining_slots -= 1

        _run_conditioning_poststep("system_quota_fill", _fill_system_quotas)
        _run_conditioning_poststep("deficit_fill", _fill_deficits)

    def _insert_gas_tank_machine_bias() -> None:
            normalized_focus = _normalize_focus_tokens([*goal_list, *weak_list])
            needs_gas_tank_focus = bool(normalized_focus & _GAS_TANK_NORMALIZED_SIGNAL_TERMS)
            has_machine_equipment = bool(_GAS_TANK_MACHINE_EQUIPMENT & equipment_access_set)
            if (
                phase.upper() in {"GPP", "SPP"}
                and needs_gas_tank_focus
                and has_machine_equipment
            ):
                has_machine_gas_tank = any(
                    _is_machine_biased_gas_tank_drill(drill)
                    for _system, drills in final_drills
                    for drill in drills
                )
                if not has_machine_gas_tank:
                    machine_candidates: list[tuple[int, float, dict, dict]] = []
                    for system in ("aerobic", "alactic"):
                        for drill, score, reasons in system_drills.get(system, []):
                            if not _is_machine_biased_gas_tank_drill(drill):
                                continue
                            priority = 0 if system == "aerobic" else 1
                            if "rower" in _cached_text_blob(drill):
                                priority -= 1
                            machine_candidates.append((priority, score, drill, reasons))
                    if not machine_candidates:
                        for drill in base_conditioning_bank:
                            if drill.get("placement", "conditioning").lower() != "conditioning":
                                continue
                            if phase.upper() not in [str(p).upper() for p in drill.get("phases", [])]:
                                continue
                            if not _is_machine_biased_gas_tank_drill(drill):
                                continue
                            drill_system = str(_cached_system(drill, "gas_tank_machine_bias_fallback") or "").strip().lower()
                            drill_text = _cached_text_blob(drill)
                            drill_structured = _cached_structured_profile(drill, system=drill_system)
                            if drill_system == "glycolytic":
                                continue
                            if drill_structured["high_lactate"] or drill_structured["glycolytic_density"]:
                                continue
                            if _conditioning_dense_pattern(drill_text) or _conditioning_multi_round_pattern(drill_text):
                                continue
                            if (drill_structured["rpe"] or 0) > 6:
                                continue
                            drill_eq = _cached_equipment(drill)
                            if drill_eq and not set(drill_eq).issubset(equipment_access_set):
                                continue
                            machine_candidates.append((0, 0.0, drill, {"reason_codes": ["gas_tank_machine_bias"], "final_score": 0}))
                    machine_candidates.sort(key=lambda item: (item[0], -item[1]))
                    for _priority, _score, drill, reasons in machine_candidates:
                        if _try_append_conditioning_drill("aerobic", drill, reasons, source="gas_tank_machine_bias"):
                            break


    _run_conditioning_poststep("gas_tank_machine_bias", _insert_gas_tank_machine_bias)

        # --------- STYLE TAPER DRILL INSERTION ---------
    def _insert_style_taper_drill() -> None:
        if phase != "TAPER":
            return
        try:
            style_taper_bank = _load_bank(
                DATA_DIR / "style_taper_conditioning.json",
                source="style_taper_conditioning.json",
                enforce_conditioning_systems=True,
            )
        except Exception:
            style_taper_bank = []

        existing_cond_names = {d.get("name") for _, drills in final_drills for d in drills}
        style_set = set(style_names)
        taper_candidates = []

        for d in style_taper_bank:
            if d.get("placement", "conditioning").lower() != "conditioning":
                continue
            if not style_set.intersection(set(_cached_tags(d))):
                continue
            eq = _cached_equipment(d)
            if eq and not set(eq).issubset(equipment_access_set):
                continue
            taper_candidates.append(d)

        if not taper_candidates:
            taper_candidates = [
                d
                for d in style_taper_bank
                if d.get("placement", "conditioning").lower() == "conditioning"
                and (
                    not _cached_equipment(d)
                    or set(_cached_equipment(d)).issubset(
                        equipment_access_set
                    )
                )
            ]

        inserted = False
        if taper_candidates and len(selected_drill_names) < total_drills:
            scan_pool = sorted(
                taper_candidates,
                key=lambda d: d.get("name") or "",
            )[:INJURY_GUARD_SHORTLIST]
            max_scan = bounded_max_iterations(len(scan_pool), multiplier=2, floor=4)
            for scan_idx, drill in enumerate(scan_pool, start=1):
                if scan_idx > max_scan:
                    log_fail_safe_degrade(module="conditioning", phase=phase, reason="guarantee_scan_guard:style_taper", target=len(scan_pool), actual=scan_idx)
                    break
                if drill.get("name") in existing_cond_names:
                    continue

                system = _cached_system(
                    drill,
                    "style_taper_conditioning.json",
                )
                if system is None:
                    continue

                if _try_append_conditioning_drill(
                    system,
                    drill,
                    {
                        "goal_hits": 0,
                        "weakness_hits": 0,
                        "style_hits": 1,
                        "phase_hits": 1,
                        "load_adjustments": 0,
                        "equipment_boost": 0,
                        "penalties": 0,
                        "reason_codes": ["style_taper_guarantee"],
                        "final_score": 0,
                    },
                    source="style_taper",
                ):
                    inserted = True
                    break
        if not inserted:
            log_fail_safe_degrade(module="conditioning", phase=phase, reason="style_taper_no_candidate", target=1, actual=0)
                    
    _run_conditioning_poststep("style_taper_insertion", _insert_style_taper_drill)

    def _insert_taper_plyometric_guarantee() -> None:
        if phase != "TAPER":
            return
        taper_plyos = [
            d
            for d in base_conditioning_bank
            if "TAPER" in [p.upper() for p in d.get("phases", [])]
            and d.get("placement", "conditioning").lower() == "conditioning"
            and "plyometric" in set(_cached_tags(d))
            and (
                not _cached_equipment(d)
                or set(_cached_equipment(d)).issubset(
                    equipment_access_set
                )
            )
        ]

        inserted = False
        if taper_plyos and len(selected_drill_names) < total_drills:
            existing_cond_names = {d.get("name") for _, drills in final_drills for d in drills}
            scan_pool = sorted(
                taper_plyos,
                key=lambda d: d.get("name") or "",
            )[:INJURY_GUARD_SHORTLIST]
            max_scan = bounded_max_iterations(len(scan_pool), multiplier=2, floor=4)
            for scan_idx, drill in enumerate(scan_pool, start=1):
                if scan_idx > max_scan:
                    log_fail_safe_degrade(module="conditioning", phase=phase, reason="guarantee_scan_guard:taper_plyometric", target=len(scan_pool), actual=scan_idx)
                    break
                if drill.get("name") in existing_cond_names:
                    continue

                system = _cached_system(drill, "conditioning_taper_plyo")
                if system is None:
                    continue

                if _try_append_conditioning_drill(
                    system,
                    drill,
                    {
                        "goal_hits": 0,
                        "weakness_hits": 0,
                        "style_hits": 0,
                        "phase_hits": 1,
                        "load_adjustments": 0,
                        "equipment_boost": 0,
                        "penalties": 0,
                        "reason_codes": ["taper_plyometric_guarantee"],
                        "final_score": 0,
                    },
                    source="taper_plyometric",
                ):
                    inserted = True
                    break
        if not inserted:
            log_fail_safe_degrade(module="conditioning", phase=phase, reason="taper_plyometric_no_candidate", target=1, actual=0)
    _run_conditioning_poststep("taper_plyometric_guarantee", _insert_taper_plyometric_guarantee)
                    
    def _insert_skill_refinement_guarantee() -> None:
        goal_set = {g.lower() for g in goals}
        if "skill_refinement" not in goal_set or len(selected_drill_names) >= total_drills:
            return
        existing_names = {d.get("name") for _, drills in final_drills for d in drills}
        skill_drills = [
            d for d in style_conditioning_bank
            if "skill_refinement" in set(_cached_tags(d))
            and d.get("placement", "conditioning").lower() == "conditioning"
            and phase.upper() in d.get("phases", [])
            and (
                not _cached_equipment(d)
                or set(_cached_equipment(d)).issubset(equipment_access_set)
            )
        ]
        inserted = False
        scan_pool = sorted(skill_drills, key=lambda d: d.get("name") or "")[:INJURY_GUARD_SHORTLIST]
        max_scan = bounded_max_iterations(len(scan_pool), multiplier=2, floor=4)
        for scan_idx, drill in enumerate(scan_pool, start=1):
            if scan_idx > max_scan:
                log_fail_safe_degrade(module="conditioning", phase=phase, reason="guarantee_scan_guard:skill_refinement", target=len(scan_pool), actual=scan_idx)
                break
            if drill.get("name") in existing_names:
                continue
            decision = _cached_injury_decision(drill)
            if decision.action == "exclude":
                _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)
                continue
            system = _cached_system(drill, "skill_refinement")
            if system is None:
                continue
            if _try_append_conditioning_drill(system, drill, {"goal_hits": 1, "weakness_hits": 0, "style_hits": 0, "phase_hits": 1, "load_adjustments": 0, "equipment_boost": 0, "penalties": 0, "reason_codes": ["skill_refinement_guarantee"], "final_score": 0}, source="skill_refinement"):
                inserted = True
                break
        if not inserted:
            log_fail_safe_degrade(module="conditioning", phase=phase, reason="skill_refinement_no_candidate", target=1, actual=0)
    _run_conditioning_poststep("skill_refinement_guarantee", _insert_skill_refinement_guarantee)

    # --------- OPTIONAL COORDINATION DRILL INSERTION ---------
    def _insert_coordination_drill() -> None:
        existing_names = {d.get("name") for _, drills in final_drills for d in drills}
        normalized_focus = _normalize_focus_tokens([*goal_list, *weak_list, *goal_tags, *weak_tags])
        coordination_expected = bool(
            normalized_focus
            & {"coordination", "proprioception", "coordination_proprioception"}
        )
        coord_drill = select_coordination_drill({**flags, "equipment": equipment_access}, existing_names, injuries)
        if not coord_drill or len(selected_drill_names) >= total_drills:
            if coordination_expected:
                log_fail_safe_degrade(module="conditioning", phase=phase, reason="coordination_no_candidate", target=1, actual=0)
            return
        system = _cached_system(coord_drill, "coordination")
        if system is None or not _try_append_conditioning_drill(system, coord_drill, {"goal_hits": 0, "weakness_hits": 1, "style_hits": 0, "phase_hits": 1, "load_adjustments": 0, "equipment_boost": 0, "penalties": 0, "reason_codes": ["coordination_guarantee"], "final_score": 0}, source="coordination"):
            if coordination_expected:
                log_fail_safe_degrade(module="conditioning", phase=phase, reason="coordination_no_candidate", target=1, actual=0)
    _run_conditioning_poststep("coordination_insertion", _insert_coordination_drill)

    # --------- PRO NECK DRILL GUARANTEE ---------
    def _insert_pro_neck_drill() -> None:
        status = flags.get("status", "").strip().lower()
        if status not in {"professional", "pro"}:
            return
        has_neck = any(
            "neck" in set(_cached_tags(d))
            for _, drills in final_drills
            for d in drills
        )
        if not has_neck:
            neck_candidates = [
                d
                for d in base_conditioning_bank
                if "neck" in set(_cached_tags(d))
                and phase.upper() in d.get("phases", [])
                and (
                    not _cached_equipment(d)
                    or set(_cached_equipment(d)).issubset(equipment_access_set)
                )
            ]
            inserted = False
            if neck_candidates and len(selected_drill_names) < total_drills:
                scan_pool = sorted(neck_candidates, key=lambda d: d.get("name") or "")[:INJURY_GUARD_SHORTLIST]
                max_scan = bounded_max_iterations(len(scan_pool), multiplier=2, floor=4)
                for scan_idx, drill in enumerate(scan_pool, start=1):
                    if scan_idx > max_scan:
                        log_fail_safe_degrade(module="conditioning", phase=phase, reason="guarantee_scan_guard:pro_neck", target=len(scan_pool), actual=scan_idx)
                        break
                    decision = _cached_injury_decision(drill)
                    if decision.action == "exclude":
                        _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)
                        continue
                    system = _cached_system(drill, "pro_neck")
                    if system is None:
                        continue

                    if _try_append_conditioning_drill(
                        system,
                        drill,
                        {
                            "goal_hits": 0,
                            "weakness_hits": 0,
                            "style_hits": 0,
                            "phase_hits": 1,
                            "load_adjustments": 0,
                            "equipment_boost": 0,
                            "penalties": 0,
                            "reason_codes": ["pro_neck_guarantee"],
                            "final_score": 0,
                        },
                        source="pro_neck",
                    ):
                        inserted = True
                        break
            if not inserted:
                log_fail_safe_degrade(module="conditioning", phase=phase, reason="pro_neck_no_candidate", target=1, actual=0)
    _run_conditioning_poststep("pro_neck_guarantee", _insert_pro_neck_drill)

    # --------- OPTIONAL TECHNICAL FOOTWORK INSERTION ---------
    # Relevance-gated technical movement rehearsal for footwork-focused
    # athletes, mirroring the coordination/skill-refinement guarantees. Runs
    # last (after the energy-system fill, the other guarantees and the pro neck
    # safety insert) so it only ever fills a leftover drill slot and never
    # starves a primary conditioning dose. It is never scored against the
    # energy-system pool, so it cannot be selected as a primary conditioning
    # dose; when it appears it carries the ``technical_footwork_guarantee``
    # reason code. In taper the conditioning pool is heavily restricted, so this
    # is where familiar low-fatigue footwork most often fills the gap.
    def _insert_technical_footwork_drill() -> None:
        if not technical_footwork_focus or len(selected_drill_names) >= visible_drill_cap:
            return
        existing_names = {d.get("name") for _, drills in final_drills for d in drills}
        # Consume the full ranked candidate list, not a single pick: the
        # highest-ranked drill can be blocked by its own late_windows
        # (taper/D-day) inside _try_append_conditioning_drill while a lower-ranked
        # but window-eligible drill is still valid. Fall through until one clears
        # late-window + injury + restriction gating, so a window-blocked top pick
        # never strands the whole insert. Footwork is placed under
        # TECHNICAL_FOOTWORK_GROUP so it is gated like aerobic work but never
        # counted or resolved as an aerobic energy-system dose.
        candidates = select_technical_footwork_candidates(
            {**flags, "equipment": equipment_access}, existing_names, injuries
        )
        for drill in candidates:
            system = _cached_system(drill, "technical_footwork")
            if system is None:
                continue
            if _try_append_conditioning_drill(
                system,
                drill,
                _technical_footwork_selection_reasons(flags, drill),
                source="technical_footwork",
                group_key=TECHNICAL_FOOTWORK_GROUP,
            ):
                return
        log_fail_safe_degrade(
            module="conditioning",
            phase=phase,
            reason="technical_footwork_no_candidate",
            target=1,
            actual=0,
        )
    _run_conditioning_poststep("technical_footwork_insertion", _insert_technical_footwork_drill)

    # Trim any extras beyond the recommended count
    def _trim_extra_drills() -> None:
        nonlocal final_drills, selected_drill_names
        if len(selected_drill_names) > visible_drill_cap:
            extra = len(selected_drill_names) - visible_drill_cap
            final_drills = final_drills[:-extra]
            selected_drill_names = selected_drill_names[:-extra]
    _run_conditioning_poststep("trim_extras", _trim_extra_drills)

    # Group drills by energy system so each system only prints once
    def _build_grouped_drills() -> dict[str, list[dict]]:
        grouped_drills_local: dict[str, list[dict]] = {}
        for system, drills in final_drills:
            grouped_drills_local.setdefault(system, []).extend(drills)
        return grouped_drills_local

    grouped_drills = _run_conditioning_poststep("grouped_drills_build", _build_grouped_drills)

    def _record_injury_exclusion(drill: dict, decision: Decision) -> None:
        if drill.get("name") in style_conditioning_scored_names:
            style_conditioning_diagnostics["entries_blocked_by_injury_restrictions"] += 1
        reason = decision.reason if isinstance(decision.reason, dict) else {}
        excluded_by_injury.append({
            "name": drill.get("name", "<unnamed>"),
            "score": float(score_lookup.get(drill.get("name"), 0.0)),
            "region": reason.get("region"),
            "severity": reason.get("severity"),
            "bucket": reason.get("bucket"),
            "matched_tags": list(decision.matched_tags or []),
        })

    def _finalize_injury_safe_drills(
        grouped: dict[str, list[dict]],
        injuries: list[dict],
        all_candidates_by_system: dict[str, list[dict]],
        selected_drill_names: list[str],
        reason_lookup: dict,
        score_fn: Callable[[dict], float] | None = None,
    ) -> None:
        def _name(x: dict) -> str | None:
            n = x.get("name")
            return n.strip() if isinstance(n, str) and n.strip() else None

        used_names = {n for drills in grouped.values() for d in drills if (n := _name(d))}
        def _decision(d: dict) -> Decision:
            return _cached_injury_decision(d)

        for system, drills in list(grouped.items()):
            idx = 0
            candidates = all_candidates_by_system.get(system, [])

            while idx < len(drills):
                max_iter = bounded_max_iterations(len(drills))
                if idx > max_iter:
                    log_fail_safe_degrade(module="conditioning", phase=phase, reason=f"replacement_scan_guard:{system}", target=len(drills), actual=idx)
                    break
                drill = drills[idx]
                decision = _decision(drill)

                if decision.action != "exclude":
                    idx += 1
                    continue
                _record_injury_exclusion(drill, decision)
                # Log exclusion using new helper
                _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)

                safe_pool: list[dict] = []
                capped_candidates = candidates[: max(1, bounded_max_iterations(len(candidates), multiplier=1, floor=32))]
                for cand in capped_candidates:
                    cand_name = _name(cand)
                    if not cand_name or cand_name in used_names:
                        continue
                    cand_decision = _decision(cand)
                    if cand_decision.action == "exclude":
                        continue
                    safe_pool.append(cand)

                replacement = None
                if safe_pool:
                    replacement = choose_injury_replacement(
                        excluded_item=drill,
                        candidates=safe_pool,
                        injuries=injuries,
                        phase=phase,
                        fatigue=fatigue,
                        score_fn=score_fn,
                    )

                if replacement:
                    rep_name = _name(replacement) or "(unnamed)"

                    old_name = _name(drill)
                    if old_name:
                        used_names.discard(old_name)
                    used_names.add(rep_name)

                    drills[idx] = replacement
                    
                    # Log replacement when INJURY_DEBUG is enabled
                    _log_replacement(f"conditioning:{phase.upper()}", old_name or "<unnamed>", rep_name)

                    reason_lookup.setdefault(rep_name, {
                        "goal_hits": 0,
                        "weakness_hits": 0,
                        "style_hits": 0,
                        "phase_hits": 1,
                        "load_adjustments": 0,
                        "equipment_boost": 0,
                        "penalties": 0,
                        "final_score": 0,
                    })

                    if old_name and old_name in selected_drill_names:
                        selected_drill_names[selected_drill_names.index(old_name)] = rep_name

                    idx += 1
                else:
                    old_name = _name(drill)
                    if old_name:
                        used_names.discard(old_name)
                        if old_name in selected_drill_names:
                            selected_drill_names.remove(old_name)

                    drills.pop(idx)
                    log_fail_safe_degrade(module="conditioning", phase=phase, reason=f"injury_finalize_no_replacement:{system}", target=1, actual=0)

            grouped[system] = drills

    def _finalize_injury_safe_drills_step() -> None:
        _finalize_injury_safe_drills(
            grouped_drills,
            injuries,
            all_candidates_by_system,
            selected_drill_names,
            reason_lookup,
        )

    _run_conditioning_poststep("injury_safe_finalize", _finalize_injury_safe_drills_step)

    def _record_speed_dose_trace() -> None:
        if not speed_goal_requested:
            return
        alactic_drills = grouped_drills.get("alactic") or []
        if not alactic_drills:
            return
        trace_drill = alactic_drills[1] if speed_dose_allowed and len(alactic_drills) > 1 else alactic_drills[0]
        trace_name = trace_drill.get("name")
        if not isinstance(trace_name, str) or not trace_name.strip():
            return
        reasons = reason_lookup.setdefault(
            trace_name,
            {
                "goal_hits": 0,
                "weakness_hits": 0,
                "style_hits": 0,
                "phase_hits": 1,
                "load_adjustments": 0,
                "equipment_boost": 0,
                "penalties": 0,
                "final_score": 0,
            },
        )
        reason_codes = reasons.setdefault("reason_codes", [])
        if speed_dose_allowed and len(alactic_drills) > 1:
            reason_code = "speed_goal_alactic_microdose"
        else:
            reason_code = "speed_goal_alactic_microdose_suppressed"
        if reason_code not in reason_codes:
            reason_codes.append(reason_code)
        reasons["speed_goal_requested"] = speed_goal_requested
        reasons["speed_dose_allowed"] = speed_dose_allowed
        reasons["alactic_primary_cap"] = alactic_primary_cap
        reasons["speed_dose_reason"] = (
            "speed goal adds one small full-rest alactic exposure"
            if speed_dose_allowed
            else "speed goal did not add a second alactic exposure because safety caps applied"
        )

    _is_late_fight_taper = active_late_window
    bridge_allows_glycolytic_touch = bool(
        active_late_window
        and (bridge_rules or {}).get("glycolytic_touch_max", 0) > 0
    )

    def _insert_energy_system_fallbacks() -> None:
        if (
            phase.upper() == "SPP"
            and not grouped_drills.get("glycolytic")
            and not _is_late_fight_taper
        ):
            fallback = _glycolytic_fallback(phase)
            decision = _cached_injury_decision(fallback)

            if decision.action != "exclude":
                grouped_drills["glycolytic"] = [fallback]
                selected_drill_names.append(fallback["name"])
                reason_lookup[fallback["name"]] = {
                    "goal_hits": 0,
                    "weakness_hits": 0,
                    "style_hits": 0,
                    "phase_hits": 1,
                    "load_adjustments": 0,
                    "equipment_boost": 0,
                    "penalties": 0,
                    "reason_codes": ["spp_glycolytic_fallback"],
                    "final_score": 0,
                }
            else:
                _log_exclusion(f"conditioning:{phase.upper()}:spp_glycolytic_fallback", fallback, decision)

        elif (
            phase.upper() == "TAPER"
            and not grouped_drills.get("glycolytic")
            and bridge_allows_glycolytic_touch
        ):
            fallback = _bridge_glycolytic_touch_fallback()
            late_eval = _cached_late_eval(fallback, "glycolytic", "runtime_fallback")
            decision = _cached_injury_decision(fallback)

            if not late_eval["blocked"] and decision.action != "exclude":
                if late_eval.get("penalty_codes"):
                    _record_late_penalty(fallback, 0.0, late_eval["penalty_codes"])
                grouped_drills["glycolytic"] = [fallback]
                selected_drill_names.append(fallback["name"])
                reason_lookup[fallback["name"]] = {
                    "goal_hits": 0,
                    "weakness_hits": 0,
                    "style_hits": 0,
                    "phase_hits": 1,
                    "load_adjustments": 0,
                    "equipment_boost": 0,
                    "penalties": 0,
                    "reason_codes": ["bridge_glycolytic_touch_fallback"]
                    + list(late_eval["reason_codes"]),
                    "penalty_codes": list(late_eval.get("penalty_codes", [])),
                    "late_window_adjustment": late_eval["adjustment"],
                    "final_score": round(float(late_eval["adjustment"] or 0), 4),
                }
            elif late_eval["blocked"]:
                _record_late_block(fallback, 0.0, late_eval["block_codes"])
            else:
                _log_exclusion(f"conditioning:{phase.upper()}:bridge_glycolytic_touch_fallback", fallback, decision)

        if (
            selection_format in {"boxing", "kickboxing"}
            and phase.upper() in {"SPP", "TAPER"}
            and not grouped_drills.get("alactic")
            and not _suppress_alactic_maintenance(fatigue=fatigue, injuries=injuries)
        ):
            fallback = _alactic_maintenance_fallback(phase)
            late_eval = _cached_late_eval(fallback, "alactic", "runtime_fallback")
            decision = _cached_injury_decision(fallback)

            if not late_eval["blocked"] and decision.action != "exclude":
                if late_eval.get("penalty_codes"):
                    _record_late_penalty(fallback, 0.0, late_eval["penalty_codes"])
                grouped_drills["alactic"] = [fallback]
                selected_drill_names.append(fallback["name"])
                reason_lookup[fallback["name"]] = {
                    "goal_hits": 0,
                    "weakness_hits": 0,
                    "style_hits": 0,
                    "phase_hits": 1,
                    "load_adjustments": 0,
                    "equipment_boost": 0,
                    "penalties": 0,
                    "reason_codes": ["alactic_maintenance_fallback"]
                    + list(late_eval["reason_codes"]),
                    "penalty_codes": list(late_eval.get("penalty_codes", [])),
                    "late_window_adjustment": late_eval["adjustment"],
                    "final_score": round(float(late_eval["adjustment"] or 0), 4),
                }
            elif late_eval["blocked"]:
                _record_late_block(fallback, 0.0, late_eval["block_codes"])
            else:
                _log_exclusion(f"conditioning:{phase.upper()}:alactic_maintenance_fallback", fallback, decision)

        if (
            phase.upper() == "TAPER"
            and active_late_window
            and not any(grouped_drills.get(system_name) for system_name in ("aerobic", "glycolytic", "alactic"))
        ):
            fallback = _late_support_fallback(late_window)
            late_eval = _cached_late_eval(fallback, "aerobic", "runtime_fallback")
            decision = _cached_injury_decision(fallback)

            if not late_eval["blocked"] and decision.action != "exclude":
                if late_eval.get("penalty_codes"):
                    _record_late_penalty(fallback, 0.0, late_eval["penalty_codes"])
                grouped_drills["aerobic"] = [fallback]
                selected_drill_names.append(fallback["name"])
                reason_lookup[fallback["name"]] = {
                    "goal_hits": 0,
                    "weakness_hits": 0,
                    "style_hits": 0,
                    "phase_hits": 1,
                    "load_adjustments": 0,
                    "equipment_boost": 0,
                    "penalties": 0,
                    "reason_codes": ["late_support_fallback"] + list(late_eval["reason_codes"]),
                    "penalty_codes": list(late_eval.get("penalty_codes", [])),
                    "late_window_adjustment": late_eval["adjustment"],
                    "final_score": round(float(late_eval["adjustment"] or 0), 4),
                }
            elif late_eval["blocked"]:
                _record_late_block(fallback, 0.0, late_eval["block_codes"])
            else:
                _log_exclusion(f"conditioning:{phase.upper()}:late_support_fallback", fallback, decision)
    _run_conditioning_poststep("energy_system_fallbacks", _insert_energy_system_fallbacks)
    _run_conditioning_poststep("speed_dose_trace", _record_speed_dose_trace)
    resolved_sessions = _resolve_conditioning_sessions(
        grouped_drills,
        phase=phase,
        num_sessions=num_conditioning_sessions,
        alactic_primary_cap=alactic_primary_cap,
    )
    grouped_drills = _resolved_grouped_drills(resolved_sessions)
    selected_drill_names = _resolved_conditioning_names(resolved_sessions)
    final_style_conditioning_names = [
        d.get("name")
        for drills in grouped_drills.values()
        for d in drills
        if d.get("name") in style_conditioning_scored_names
    ]
    style_conditioning_diagnostics["entries_selected"] = len(final_style_conditioning_names)
    style_conditioning_diagnostics["final_selected_style_conditioning_names"] = final_style_conditioning_names
    style_conditioning_diagnostics["final_selected_exact_sport_names"] = [
        name
        for name in final_style_conditioning_names
        if reason_lookup.get(name, {}).get("sport_specificity_bonus", 0) > 0
    ]

    def _build_missing_systems() -> list[str]:
        missing = [
            system_name
            for system_name in ["aerobic", "glycolytic", "alactic"]
            if not grouped_drills.get(system_name)
        ]
        for system_name in missing:
            log_fail_safe_degrade(
                module="conditioning",
                phase=phase,
                reason=f"missing_system_safe_omission:{system_name}",
                target=1,
                actual=0,
            )
        return missing

    missing_systems = _run_conditioning_poststep("missing_systems_build", _build_missing_systems)
    diagnostic_context = {
        "phase": phase,
        "sport": flags.get("sport"),
        "time_to_fight_days": flags.get("time_to_fight_days"),
        "days_until_fight": days_until_fight,
        "late_window": late_window,
        "weeks_out": flags.get("weeks_out"),
        "fatigue_level": fatigue,
        "injuries": injuries,
        "fight_format": fight_format,
        "speed_goal_requested": speed_goal_requested,
        "speed_dose_allowed": speed_dose_allowed,
        "alactic_primary_cap": alactic_primary_cap,
    }
    def _format_conditioning_output():
        return render_conditioning_block(
            grouped_drills,
            phase=phase,
            phase_color=phase_color,
            missing_systems=missing_systems,
            num_sessions=num_conditioning_sessions,
            diagnostic_context=diagnostic_context,
            sport=flags.get("sport"),
            stance=flags.get("stance"),
            resolved_sessions=resolved_sessions,
        )

    output_lines = _run_conditioning_poststep("block_formatting", _format_conditioning_output)

    why_log = []
    for system, drills in grouped_drills.items():
        for d in drills:
            nm = d.get("name")
            reasons = reason_lookup.get(nm, {}).copy()
            reasons.setdefault("final_score", 0)
            explanation = _conditioning_explanation(reasons)
            why_log.append({"name": nm, "system": system, "reasons": reasons, "explanation": explanation})

    def _build_candidate_reservoir_step():
        reservoir = _build_conditioning_candidate_reservoir(
            scored_system_drills,
            scored_style_system_drills,
            grouped_drills,
            reason_lookup,
        )
        total_candidates = sum(len(v) for v in reservoir.values())
        max_candidates = 400
        if total_candidates > max_candidates:
            log_fail_safe_degrade(
                module="conditioning",
                phase=phase,
                reason="candidate_reservoir_capped",
                target=total_candidates,
                actual=max_candidates,
            )
            trimmed: dict[str, list[dict]] = {}
            remaining = max_candidates
            for system_name in ("aerobic", "glycolytic", "alactic"):
                entries = reservoir.get(system_name, [])
                take = min(len(entries), remaining)
                trimmed[system_name] = entries[:take]
                remaining -= take
            for key, value in reservoir.items():
                if key in trimmed:
                    continue
                if remaining <= 0:
                    trimmed[key] = []
                    continue
                take = min(len(value), remaining)
                trimmed[key] = value[:take]
                remaining -= take
            return trimmed
        return reservoir

    candidate_reservoir = _run_conditioning_poststep("candidate_reservoir_build", _build_candidate_reservoir_step)
    deduped_late_blocks = {
        (
            entry.get("name", ""),
            tuple(entry.get("reason_codes", [])),
        ): entry
        for entry in late_window_blocked
    }
    deduped_late_penalties = {
        (
            entry.get("name", ""),
            tuple(entry.get("penalty_codes", [])),
        ): entry
        for entry in late_window_penalized
    }
    candidate_reservoir["__late_window__"] = {
        "window": late_window,
        "blocked": sorted(
            deduped_late_blocks.values(),
            key=lambda entry: (entry.get("name", ""), entry.get("score", 0.0)),
        ),
        "penalized": sorted(
            deduped_late_penalties.values(),
            key=lambda entry: (entry.get("name", ""), entry.get("score", 0.0)),
        ),
        "ambiguous_tag_gaps": [
            late_window_ambiguous[name]
            for name in sorted(late_window_ambiguous)
        ],
        "bridge_rules": {
            "glycolytic_touch_max": bridge_rules.get("glycolytic_touch_max"),
            "strength_touch_max": bridge_rules.get("strength_touch_max"),
            "reason_codes": list(bridge_rules.get("reason_codes", [])),
        } if bridge_rules else {},
    }
    candidate_reservoir["__style_conditioning__"] = style_conditioning_diagnostics.copy()

    return output_lines, selected_drill_names, why_log, grouped_drills, missing_systems, candidate_reservoir
# Map for tactical styles
