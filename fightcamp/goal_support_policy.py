from __future__ import annotations

from typing import Any

from .normalization import clean_list

GOAL_SUPPORT_POLICY: dict[str, dict[str, Any]] = {
    "gas_tank": {
        "support_type": "low_aerobic",
        "role_class": "support_only",
        "weekly_caps_by_phase": {"GPP": 2, "SPP": 2, "TAPER": 1, "FIGHT_WEEK": 1},
        "allowed_near_hard_sparring": True,
        "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=4", "no glycolytic", "no ATP-PCr"],
        "blocked_systems": ["glycolytic", "ATP-PCr"],
        "blocked_intensities": ["high", "max"],
        "blocked_tags": ["sprint", "plyometric", "high_cns", "mech_cns_high", "high_impact_lower", "mech_landing_impact"],
        "taper_compatible": True,
        "weight_cut_behaviour": "keep_allowed_low_load",
        "priority_rank": 10,
    },
    "mobility": {"support_type": "mobility_reset", "role_class": "support_only", "weekly_caps_by_phase": {"GPP": 2, "SPP": 2, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=4", "no glycolytic", "no ATP-PCr"], "blocked_systems": ["glycolytic", "ATP-PCr"], "blocked_intensities": ["high", "max"], "blocked_tags": ["sprint", "plyometric", "high_cns", "mech_cns_high", "high_impact_lower", "mech_landing_impact"], "taper_compatible": True, "weight_cut_behaviour": "keep_allowed_low_load", "priority_rank": 20},
    "skill_refinement": {"support_type": "technical_touch", "role_class": "technical_support", "weekly_caps_by_phase": {"GPP": 1, "SPP": 2, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=4", "no glycolytic", "no ATP-PCr"], "blocked_systems": ["glycolytic", "ATP-PCr"], "blocked_intensities": ["high", "max"], "blocked_tags": ["sprint", "plyometric", "high_cns", "mech_cns_high"], "taper_compatible": True, "weight_cut_behaviour": "keep_allowed_low_load", "priority_rank": 30},
    "footwork": {"support_type": "coordination_touch", "role_class": "technical_support", "weekly_caps_by_phase": {"GPP": 1, "SPP": 2, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=4"], "blocked_systems": ["glycolytic"], "blocked_intensities": ["high", "max"], "blocked_tags": ["sprint", "plyometric", "high_cns"], "taper_compatible": True, "weight_cut_behaviour": "keep_allowed_low_load", "priority_rank": 40},
    "balance": {"support_type": "coordination_touch", "role_class": "support_only", "weekly_caps_by_phase": {"GPP": 1, "SPP": 1, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=4"], "blocked_systems": ["glycolytic", "ATP-PCr"], "blocked_intensities": ["high", "max"], "blocked_tags": ["sprint", "plyometric", "high_cns"], "taper_compatible": True, "weight_cut_behaviour": "keep_allowed_low_load", "priority_rank": 50},
    "coordination": {"support_type": "coordination_touch", "role_class": "support_only", "weekly_caps_by_phase": {"GPP": 1, "SPP": 1, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=4"], "blocked_systems": ["glycolytic", "ATP-PCr"], "blocked_intensities": ["high", "max"], "blocked_tags": ["sprint", "plyometric", "high_cns"], "taper_compatible": True, "weight_cut_behaviour": "keep_allowed_low_load", "priority_rank": 60},
    "core_trunk_strength": {"support_type": "core_support", "role_class": "support_only", "weekly_caps_by_phase": {"GPP": 1, "SPP": 1, "TAPER": 1, "FIGHT_WEEK": 0}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=4"], "blocked_systems": ["glycolytic"], "blocked_intensities": ["high", "max"], "blocked_tags": ["high_cns", "mech_cns_high"], "taper_compatible": True, "weight_cut_behaviour": "keep_allowed_low_load", "priority_rank": 70},
    "speed": {"support_type": "alactic_speed", "role_class": "anchor_required", "weekly_caps_by_phase": {"GPP": 1, "SPP": 2, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": False, "hard_sparring_adjacent_allowed_only_if": [], "blocked_systems": ["glycolytic"], "blocked_intensities": [], "blocked_tags": [], "taper_compatible": True, "weight_cut_behaviour": "suppress_high_damage", "priority_rank": 80},
    "power": {"support_type": "power_anchor", "role_class": "anchor_required", "weekly_caps_by_phase": {"GPP": 1, "SPP": 2, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": False, "hard_sparring_adjacent_allowed_only_if": [], "blocked_systems": ["glycolytic"], "blocked_intensities": [], "blocked_tags": [], "taper_compatible": True, "weight_cut_behaviour": "suppress_high_damage", "priority_rank": 90},
    "strength": {"support_type": "strength_anchor", "role_class": "anchor_required", "weekly_caps_by_phase": {"GPP": 2, "SPP": 2, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": False, "hard_sparring_adjacent_allowed_only_if": [], "blocked_systems": [], "blocked_intensities": [], "blocked_tags": [], "taper_compatible": True, "weight_cut_behaviour": "suppress_high_damage", "priority_rank": 100},
    "conditioning": {"support_type": "low_aerobic", "role_class": "support_only", "weekly_caps_by_phase": {"GPP": 2, "SPP": 2, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=4", "no glycolytic"], "blocked_systems": ["glycolytic", "ATP-PCr"], "blocked_intensities": ["high", "max"], "blocked_tags": ["sprint", "plyometric", "high_cns"], "taper_compatible": True, "weight_cut_behaviour": "keep_allowed_low_load", "priority_rank": 15},
    "recovery": {"support_type": "recovery_reset", "role_class": "recovery_compatible_support", "weekly_caps_by_phase": {"GPP": 2, "SPP": 2, "TAPER": 2, "FIGHT_WEEK": 2}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=3"], "blocked_systems": ["glycolytic", "ATP-PCr"], "blocked_intensities": ["high", "max"], "blocked_tags": ["sprint", "plyometric", "high_cns"], "taper_compatible": True, "weight_cut_behaviour": "keep_allowed_low_load", "priority_rank": 5},
    "weight_cut_support": {"support_type": "weight_cut_support", "role_class": "suppressive_context_only", "weekly_caps_by_phase": {"GPP": 1, "SPP": 1, "TAPER": 1, "FIGHT_WEEK": 1}, "allowed_near_hard_sparring": True, "hard_sparring_adjacent_allowed_only_if": ["recovery_compatible=true", "RPE<=3"], "blocked_systems": ["glycolytic", "ATP-PCr"], "blocked_intensities": ["high", "max"], "blocked_tags": ["sprint", "plyometric", "high_cns", "mech_cns_high", "high_impact_lower", "mech_landing_impact"], "taper_compatible": True, "weight_cut_behaviour": "suppress_hard_high_lactate_high_damage", "priority_rank": 1},
}


GOAL_TOKEN_MAP = {k: [k] for k in GOAL_SUPPORT_POLICY}
GOAL_TOKEN_MAP["core_trunk_strength"].extend(["core", "trunk", "core_strength"])


def resolve_goal_support_policy_tokens(athlete_model: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    raw_values: list[Any] = []
    for key in ("key_goals", "goals", "weaknesses", "weak_areas", "performance_goals", "main_limiter", "limiter_key"):
        raw_values.extend(clean_list(athlete_model.get(key, [])))
    tokens = {str(v).strip().lower().replace("-", "_").replace(" ", "_") for v in raw_values if str(v).strip()}
    matched: list[tuple[str, dict[str, Any]]] = []
    for goal, policy in GOAL_SUPPORT_POLICY.items():
        synonyms = GOAL_TOKEN_MAP.get(goal, [goal])
        if any(s in tokens for s in synonyms):
            matched.append((goal, policy))
    return sorted(matched, key=lambda it: int(it[1].get("priority_rank", 999)))
