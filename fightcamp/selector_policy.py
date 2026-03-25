from __future__ import annotations

from typing import Iterable, Mapping

from .tagging import normalize_tags

FALLBACK_CLASS_NORMAL = "normal"
FALLBACK_CLASS_DOWNRANKED = "downranked"
FALLBACK_CLASS_LAST_RESORT = "last_resort"
FALLBACK_CLASS_BLOCKED = "blocked_for_profile"
FALLBACK_CLASS_PENALTY = {
    FALLBACK_CLASS_NORMAL: 0.0,
    FALLBACK_CLASS_DOWNRANKED: -1.25,
    FALLBACK_CLASS_LAST_RESORT: -4.0,
    FALLBACK_CLASS_BLOCKED: -999.0,
}

_BOXING_BLOCKED_TAGS = {
    "bjj",
    "grappler",
    "grappling",
    "wrestling",
    "wrestler",
    "submission_hunter",
    "scrambler",
    "kickboxing",
    "muay_thai",
    "kicker",
}
_BOXING_BLOCKED_PHRASES = {
    "sprawl",
    "takedown",
    "double_leg",
    "single_leg",
    "cage",
    "octagon",
    "clinch_knee",
    "knee_strike",
    "kick",
    "elbow",
}
_GRAPPLING_ONLY_TAGS = {"bjj", "grappler", "grappling", "wrestling", "submission_hunter", "scrambler"}


def _combined_text(item: Mapping[str, object]) -> str:
    fields = [
        item.get("name", ""),
        item.get("category", ""),
        item.get("movement", ""),
        item.get("modality", ""),
        item.get("description", ""),
        item.get("notes", ""),
        item.get("equipment_note", ""),
    ]
    return " ".join(str(field).strip().lower().replace(" ", "_") for field in fields if field)


def sport_context_eligibility(
    item: Mapping[str, object],
    *,
    sport: str,
    technical_style_keys: Iterable[str],
    tactical_style_keys: Iterable[str],
) -> bool:
    sport_key = str(sport or "").strip().lower()
    tags = set(normalize_tags(item.get("tags", [])))
    text = _combined_text(item)
    technical = {str(value).strip().lower() for value in technical_style_keys if str(value).strip()}
    tactical = {str(value).strip().lower() for value in tactical_style_keys if str(value).strip()}

    if sport_key == "boxing":
        if tags & _BOXING_BLOCKED_TAGS:
            return False
        if any(phrase in text for phrase in _BOXING_BLOCKED_PHRASES):
            return False
        return True

    if sport_key in {"kickboxing", "muay_thai"}:
        if tags & _GRAPPLING_ONLY_TAGS and not (technical & {"mma", "wrestling", "bjj"} or tactical & {"grappler"}):
            return False
        return True

    if sport_key in {"wrestling", "bjj"}:
        if sport_key == "wrestling" and {"boxing", "kickboxing", "muay_thai"} & tags:
            return False
        if sport_key == "bjj" and "kickboxing" in tags:
            return False
        return True

    return True


def conditioning_fallback_class(
    item: Mapping[str, object],
    *,
    sport: str,
    goal_keys: Iterable[str],
    weakness_keys: Iterable[str],
    weakness_secondary: Iterable[str],
) -> str:
    sport_key = str(sport or "").strip().lower()
    goals = {str(value).strip() for value in goal_keys if str(value).strip()}
    weaknesses = {str(value).strip() for value in weakness_keys if str(value).strip()}
    weakness_expansions = {str(value).strip() for value in weakness_secondary if str(value).strip()}
    tags = set(normalize_tags(item.get("tags", [])))
    name = str(item.get("name", "")).strip().lower()
    modality = str(item.get("modality", "")).strip().lower()

    if sport_key == "boxing":
        needs_repeatability = "repeatability_endurance" in goals or "gas_tank" in weaknesses
        coordination_bottleneck = bool(
            {"footwork", "balance", "coordination_proprioception"} & weaknesses
            or {"coordination_proprioception", "lateral_movement"} & weakness_expansions
        )
        if needs_repeatability:
            if any(token in name for token in ("stair", "hill")):
                return FALLBACK_CLASS_LAST_RESORT
            if "steady" in name and "boxing" not in tags and modality not in {"shadowbox", "bag_work", "striking"}:
                return FALLBACK_CLASS_LAST_RESORT
        if coordination_bottleneck and "single_leg" in tags and "boxing" not in tags:
            return FALLBACK_CLASS_DOWNRANKED
    return FALLBACK_CLASS_NORMAL


def coordination_fallback_class(
    item: Mapping[str, object],
    *,
    sport: str,
    weakness_keys: Iterable[str],
    weakness_secondary: Iterable[str],
) -> str:
    sport_key = str(sport or "").strip().lower()
    weaknesses = {str(value).strip() for value in weakness_keys if str(value).strip()}
    weakness_expansions = {str(value).strip() for value in weakness_secondary if str(value).strip()}
    tags = set(normalize_tags(item.get("tags", [])))
    category = str(item.get("category", "")).strip().lower()
    name = str(item.get("name", "")).strip().lower()

    if sport_key == "boxing" and (
        {"footwork", "balance", "coordination_proprioception", "trunk_strength"} & weaknesses
        or {"lateral_movement", "coordination_proprioception", "rotation"} & weakness_expansions
    ):
        generic_single_leg = "single_leg" in tags or "single-leg" in name or "single leg" in name
        boxing_specific = "boxing" in tags or {"pressure_fighter", "counter_striker", "distance_striker"} & tags
        if generic_single_leg and not boxing_specific:
            return FALLBACK_CLASS_DOWNRANKED
        if category in {"footwork", "stance_control", "counter", "pressure"} and boxing_specific:
            return FALLBACK_CLASS_NORMAL
    return FALLBACK_CLASS_NORMAL
