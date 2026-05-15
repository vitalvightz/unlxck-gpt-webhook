from __future__ import annotations

from .normalization import normalize_text_for_matching
from .tagging import normalize_tag


def _normalize_detail(value: str) -> str:
    return normalize_text_for_matching(value)


def _normalize_entry_tag(value: str) -> str:
    return normalize_tag(value) or ""


CLARIFICATION_DETAIL_TAG_MAP: dict[str, list[str]] = {
    "overall gas tank": ["aerobic", "conditioning", "work_capacity"],
    "late round fatigue": ["glycolytic", "conditioning", "work_capacity", "mental_toughness"],
    "recovery between bursts": ["anaerobic_alactic", "aerobic", "recovery", "cns_freshness"],
    "baseline cardio": ["aerobic", "recovery", "conditioning"],
    "repeated hard efforts": ["glycolytic", "work_capacity", "conditioning", "mental_toughness"],
    "overall power": ["explosive", "rate_of_force", "plyometric", "anaerobic_alactic"],
    "power drops when tired": ["explosive", "rate_of_force", "work_capacity", "conditioning", "anaerobic_alactic"],
    "first step explosiveness": ["explosive", "rate_of_force", "acceleration", "reactive", "anaerobic_alactic"],
    "punching striking power": ["striking", "rate_of_force", "rotational", "core", "shoulders"],
    "kicking power": ["rate_of_force", "hip_dominant", "rotational", "unilateral", "mobility"],
    "lower body power": ["explosive", "triple_extension", "horizontal_power", "plyometric", "quad_dominant"],
    "rotational power force transfer": ["rotational", "core", "anti_rotation", "rate_of_force"],
    "overall strength": ["strength", "compound", "posterior_chain", "quad_dominant", "upper_body", "core"],
    "lower body strength": ["posterior_chain", "quad_dominant", "hip_dominant", "deadlift", "compound"],
    "upper body strength": ["upper_body", "pull", "shoulders", "grip", "isometric"],
    "posterior chain strength": ["posterior_chain", "hip_dominant", "hamstring", "deadlift"],
    "clinch grip strength": ["grip", "pull", "isometric", "core", "manual_resistance"],
    "core bracing strength": ["core", "anti_rotation", "isometric", "stability"],
    "strength drops when tired": ["strength", "work_capacity", "conditioning", "isometric", "cns_freshness"],
    "general mobility": ["mobility", "movement_quality", "range"],
    "hip mobility": ["mobility", "hip_dominant", "range", "movement_quality"],
    "shoulder mobility": ["mobility", "shoulders", "range", "movement_quality"],
    "ankle mobility": ["mobility", "range", "balance", "movement_quality"],
    "movement stiffness under fatigue": ["mobility", "movement_quality", "range", "cns_freshness"],
    "first step speed": ["speed", "acceleration", "reactive", "anaerobic_alactic"],
    "reaction speed": ["reactive", "visual_processing", "coordination", "decision_speed"],
    "footwork speed": ["footwork", "speed", "reactive", "coordination"],
    "speed drops when tired": ["speed", "reactive", "conditioning", "work_capacity"],
    "it drops off under fatigue": ["work_capacity", "conditioning", "cns_freshness"],
    "it affects my technique": ["coordination", "movement_quality", "skill_refinement"],
    "it affects my power output": ["explosive", "rate_of_force", "core"],
    "it affects my conditioning": ["aerobic", "glycolytic", "conditioning", "work_capacity"],
    "not sure": [],
}


_GENERIC_OVERALL_BY_ENTRY_TAG: dict[str, list[str]] = {
    "conditioning": ["aerobic", "conditioning", "work_capacity"],
    "gas_tank": ["aerobic", "conditioning", "work_capacity"],
    "power": ["explosive", "rate_of_force", "plyometric"],
    "explosive": ["explosive", "rate_of_force", "plyometric"],
    "strength": ["strength", "compound", "posterior_chain", "core"],
    "mobility": ["mobility", "movement_quality", "range"],
    "speed": ["speed", "reactive", "coordination"],
    "reactive": ["speed", "reactive", "coordination"],
}


def _tags_for_detail(entry_tag: str, detail: str) -> list[str]:
    if detail == "i want to improve it overall":
        return _GENERIC_OVERALL_BY_ENTRY_TAG.get(entry_tag, [])
    return CLARIFICATION_DETAIL_TAG_MAP.get(detail, [])


def derive_clarification_tags(collision_details: list[dict[str, str]] | None) -> list[str]:
    if not collision_details or not isinstance(collision_details, list):
        return []

    ordered_tags: list[str] = []
    seen: set[str] = set()

    for entry in collision_details:
        if not isinstance(entry, dict):
            continue
        normalized_detail = _normalize_detail(entry.get("detail", ""))
        if not normalized_detail:
            continue
        normalized_entry_tag = _normalize_entry_tag(entry.get("tag", ""))
        mapped_tags = _tags_for_detail(normalized_entry_tag, normalized_detail)
        for tag in mapped_tags:
            if tag in seen:
                continue
            ordered_tags.append(tag)
            seen.add(tag)

    return ordered_tags
