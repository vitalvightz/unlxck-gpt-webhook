from __future__ import annotations

from typing import Iterable, Mapping

from .injury_guard import ConstraintSensitivity
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
_SUPPORT_CATEGORY_SPORTS = {"boxing", "mma", "kickboxing", "muay_thai", "wrestling", "bjj"}

# Tokens that positively identify a drill as low-noise / safe boxing-specific.
# Intentionally broad: captures technical, pacing, tool-based, and method-based safety indicators.
_SAFE_BOXING_POSITIVE_TOKENS = frozenset(
    {
        "tempo",
        "rhythm",
        "technical",
        "slow",
        "shadow",
        "band",
        "flow",
        "steady",
        "light",
        "easy",
        "drill",
        "reset",
        "metronome",
        "pause",
        "controlled",
        "low_intensity",
        "low-intensity",
        "footwork",
        "slip",
        "bob",
        "weave",
        "defensive",
    }
)
# Modalities that are inherently sport-preserving without requiring name tokens.
_SAFE_BOXING_MODALITIES = frozenset({"shadowbox", "bag_work", "pad_work", "mitts", "heavy_bag"})
# Hard-exclusion tokens: presence of any of these overrides positive signals.
_SAFE_BOXING_HARD_EXCLUDES = frozenset({"reenter", "re-enter", "cut", "chase", "decel"})


def is_safe_boxing_specific(
    item: Mapping[str, object],
    *,
    text: str | None = None,
    tags: set[str] | None = None,
    sport: str = "boxing",
) -> bool:
    """Return True if *item* is a low-noise, sport-preserving boxing drill.

    The check is intentionally inclusive so that safe, boxing-specific options
    are not over-suppressed even when their names do not contain the narrow
    legacy token set (tempo/rhythm/shadow/band).  Recognition is based on:

    - Boxing tag or sport-specific modality
    - An expanded positive token list covering technical, pacing, and tool cues
    - Modality-based recognition (shadowbox, bag_work, pad_work are safe by default)
    - Hard-exclusion of high-risk direction-change tokens
    """
    if str(sport or "").strip().lower() != "boxing":
        return False

    if tags is None:
        tags = set(normalize_tags(item.get("tags", [])))
    if text is None:
        text = " ".join(
            str(value).lower()
            for value in (
                item.get("name", ""),
                item.get("notes", ""),
                item.get("purpose", ""),
                item.get("modality", ""),
                item.get("equipment_note", ""),
            )
            if value
        )
    else:
        text = text.lower()

    # Hard excludes override everything.
    if any(token in text for token in _SAFE_BOXING_HARD_EXCLUDES):
        return False

    modality = str(item.get("modality", "")).strip().lower()

    # Modality-based recognition: shadowbox/bag/pad work is inherently safe.
    if modality in _SAFE_BOXING_MODALITIES:
        return True

    # Require boxing identification (tag or shadowboxing/striking content).
    is_boxing_identified = (
        "boxing" in tags
        or "shadowboxing" in text
        or "jab" in text
        or "cross" in text
        or "bag_work" in tags
        or "pad_work" in tags
    )
    if not is_boxing_identified:
        return False

    # Positive token presence confirms low-noise character.
    return any(token in text for token in _SAFE_BOXING_POSITIVE_TOKENS)


def _support_category_allowed(*, category: str, sport: str, technical: set[str]) -> bool:
    if not category.endswith("_support"):
        return True
    support_sport = category[: -len("_support")]
    if support_sport not in _SUPPORT_CATEGORY_SPORTS:
        return True

    allowed_support_sports = {sport} | technical
    if sport == "kickboxing":
        allowed_support_sports.add("muay_thai")
    if sport == "muay_thai":
        allowed_support_sports.add("kickboxing")
    if "kickboxing" in technical:
        allowed_support_sports.add("muay_thai")
    if "muay_thai" in technical:
        allowed_support_sports.add("kickboxing")
    return support_sport in allowed_support_sports


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
    category = str(item.get("category", "")).strip().lower()
    tags = set(normalize_tags(item.get("tags", [])))
    text = _combined_text(item)
    technical = {str(value).strip().lower() for value in technical_style_keys if str(value).strip()}
    tactical = {str(value).strip().lower() for value in tactical_style_keys if str(value).strip()}

    if not _support_category_allowed(category=category, sport=sport_key, technical=technical):
        return False

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
    constraint_context: ConstraintSensitivity | None = None,
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
        safe_specific = is_safe_boxing_specific(item, tags=tags, sport=sport_key)
        if needs_repeatability:
            if any(token in name for token in ("stair", "hill")):
                return FALLBACK_CLASS_LAST_RESORT
            if "steady" in name and "boxing" not in tags and modality not in {"shadowbox", "bag_work", "striking"}:
                return FALLBACK_CLASS_LAST_RESORT
        if coordination_bottleneck and "single_leg" in tags and "boxing" not in tags:
            return FALLBACK_CLASS_DOWNRANKED
        if constraint_context is not None:
            direction_change_sensitive = constraint_context.has_aggravator(
                "fast direction changes",
                "lateral cutting",
            )
            rotation_sensitive = constraint_context.has_aggravator("hard rotation")
            prolonged_stance_sensitive = constraint_context.has_aggravator("prolonged stance/load")
            if (
                direction_change_sensitive
                and constraint_context.state == "critical"
                and any(token in name for token in ("exit", "angle", "pivot", "cut", "chase", "decel"))
            ):
                # Critical state: block all direction-change drills regardless of
                # safe-specific status.  Safe-specific protection only applies below
                # critical to avoid over-suppression in guarded/constrained states.
                return FALLBACK_CLASS_BLOCKED
            if rotation_sensitive and not safe_specific and any(
                token in name for token in ("rotation", "rotational", "med ball", "slam")
            ):
                return (
                    FALLBACK_CLASS_BLOCKED
                    if constraint_context.state == "critical"
                    else FALLBACK_CLASS_LAST_RESORT
                )
            if direction_change_sensitive and not safe_specific and any(
                token in name for token in ("exit", "reenter", "re-enter")
            ):
                return (
                    FALLBACK_CLASS_BLOCKED
                    if constraint_context.state in {"constrained", "critical"}
                    else FALLBACK_CLASS_LAST_RESORT
                )
            if direction_change_sensitive and not safe_specific and any(
                token in name for token in ("pivot", "cut", "chase", "angle")
            ):
                return (
                    FALLBACK_CLASS_LAST_RESORT
                    if constraint_context.state in {"constrained", "critical"}
                    else FALLBACK_CLASS_DOWNRANKED
                )
            if prolonged_stance_sensitive and "single_leg" in tags and not safe_specific:
                return (
                    FALLBACK_CLASS_LAST_RESORT
                    if constraint_context.state == "critical"
                    else FALLBACK_CLASS_DOWNRANKED
                )
    return FALLBACK_CLASS_NORMAL


def coordination_fallback_class(
    item: Mapping[str, object],
    *,
    sport: str,
    weakness_keys: Iterable[str],
    weakness_secondary: Iterable[str],
    constraint_context: ConstraintSensitivity | None = None,
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
        if constraint_context is not None:
            safe_specific = is_safe_boxing_specific(item, tags=tags, sport=sport_key)
            if constraint_context.has_aggravator("prolonged stance/load") and generic_single_leg and not safe_specific:
                return (
                    FALLBACK_CLASS_LAST_RESORT
                    if constraint_context.state == "critical"
                    else FALLBACK_CLASS_DOWNRANKED
                )
            if constraint_context.has_aggravator("fast direction changes", "lateral cutting") and not safe_specific and any(
                token in name for token in ("exit", "reenter", "re-enter", "pivot", "angle", "decel", "change")
            ):
                return (
                    FALLBACK_CLASS_BLOCKED
                    if constraint_context.state == "critical"
                    else FALLBACK_CLASS_LAST_RESORT
                )
            if constraint_context.has_aggravator("hard rotation") and not safe_specific and (
                "rotation" in name or "rotational" in tags
            ):
                return (
                    FALLBACK_CLASS_LAST_RESORT
                    if constraint_context.state == "critical"
                    else FALLBACK_CLASS_DOWNRANKED
                )
    return FALLBACK_CLASS_NORMAL
