from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping


CANONICAL_GOAL_KEYS = {
    "power",
    "strength_general",
    "repeatability_endurance",
    "speed",
    "skill_refinement",
    "mobility",
}
CANONICAL_SUPPORT_FLAGS = {"recovery_support", "weight_cut_support"}
CANONICAL_WEAKNESS_KEYS = {
    "gas_tank",
    "strength_general",
    "power_general",
    "speed_reaction",
    "footwork",
    "balance",
    "mobility",
    "coordination_proprioception",
    "trunk_strength",
}
CANONICAL_TECHNICAL_STYLES = {
    "boxing",
    "kickboxing",
    "muay_thai",
    "mma",
    "wrestling",
    "bjj",
}
CANONICAL_TACTICAL_STYLES = {
    "pressure_fighter",
    "counter_striker",
    "distance_striker",
    "clinch_fighter",
    "grappler",
    "hybrid",
}

_GOAL_ALIASES = {
    "power": "power",
    "power_and_explosiveness": "power",
    "explosive": "power",
    "strength": "strength_general",
    "maximal_strength": "strength_general",
    "strength_general": "strength_general",
    "conditioning": "repeatability_endurance",
    "conditioning_endurance": "repeatability_endurance",
    "repeatability_endurance": "repeatability_endurance",
    "endurance": "repeatability_endurance",
    "speed": "speed",
    "reactive": "speed",
    "skill_refinement": "skill_refinement",
    "skill_refinement_technical": "skill_refinement",
    "mobility": "mobility",
    "recovery": "recovery_support",
    "recovery_support": "recovery_support",
    "weight_cut": "weight_cut_support",
    "weight_cut_support": "weight_cut_support",
}

_GOAL_SECONDARY_ALIASES = {
    "striking": "striking",
    "grappling": "grappling",
    "grappler": "grappler",
    "injury_prevention": "injury_prevention",
    "mental_resilience": "mental_resilience",
    "coordination": "coordination",
}

_WEAKNESS_ALIASES = {
    "gas_tank": "gas_tank",
    "conditioning": "gas_tank",
    "strength": "strength_general",
    "strength_general": "strength_general",
    "power": "power_general",
    "power_general": "power_general",
    "speed": "speed_reaction",
    "speed_reaction": "speed_reaction",
    "speed_reaction_reactivity": "speed_reaction",
    "footwork": "footwork",
    "balance": "balance",
    "mobility": "mobility",
    "coordination": "coordination_proprioception",
    "coordination_proprioception": "coordination_proprioception",
    "coordination_proprioception_proprioception": "coordination_proprioception",
    "trunk_strength": "trunk_strength",
    "core_stability": "trunk_strength",
    "rotation": "trunk_strength",
}

_WEAKNESS_SECONDARY = {
    "gas_tank": ["aerobic_repeatability", "fight_repeatability"],
    "footwork": ["lateral_movement", "coordination_proprioception"],
    "trunk_strength": ["core_stability", "rotation"],
}

_TECHNICAL_STYLE_ALIASES = {
    "boxer": "boxing",
    "boxing": "boxing",
    "kickboxing": "kickboxing",
    "kickboxer": "kickboxing",
    "muay_thai": "muay_thai",
    "muay_thai_k1": "muay_thai",
    "muaythai": "muay_thai",
    "muay_thai_kickboxing": "muay_thai",
    "mma": "mma",
    "mixed_martial_arts": "mma",
    "wrestler": "wrestling",
    "wrestling": "wrestling",
    "bjj": "bjj",
    "jiu_jitsu": "bjj",
    "brazilian_jiu_jitsu": "bjj",
}

_TACTICAL_STYLE_ALIASES = {
    "pressure": "pressure_fighter",
    "pressure_fighter": "pressure_fighter",
    "counter": "counter_striker",
    "counter_striker": "counter_striker",
    "distance": "distance_striker",
    "distance_striker": "distance_striker",
    "clinch": "clinch_fighter",
    "clinch_fighter": "clinch_fighter",
    "grappler": "grappler",
    "grappling": "grappler",
    "hybrid": "hybrid",
}

_TACTICAL_STYLE_SECONDARY = {
    "grappler": ["submission_hunter", "scrambler"],
}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower())
    return cleaned.strip("_")


def _clean_list(values: Iterable[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        parts = re.split(r"\s*,\s*", values)
    else:
        parts = []
        for value in values:
            if isinstance(value, str):
                parts.extend(re.split(r"\s*,\s*", value))
            else:
                parts.append(str(value))
    cleaned = []
    for part in parts:
        text = str(part).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


@dataclass(frozen=True)
class NormalizedIntakeProfile:
    raw_goal_values: list[str] = field(default_factory=list)
    raw_weakness_values: list[str] = field(default_factory=list)
    raw_technical_styles: list[str] = field(default_factory=list)
    raw_tactical_styles: list[str] = field(default_factory=list)
    goal_keys: list[str] = field(default_factory=list)
    goal_secondary: list[str] = field(default_factory=list)
    support_flags: list[str] = field(default_factory=list)
    weakness_keys: list[str] = field(default_factory=list)
    weakness_secondary: list[str] = field(default_factory=list)
    technical_style_keys: list[str] = field(default_factory=list)
    tactical_style_keys: list[str] = field(default_factory=list)
    technical_style_secondary: list[str] = field(default_factory=list)
    tactical_style_secondary: list[str] = field(default_factory=list)
    style_secondary: list[str] = field(default_factory=list)


def normalize_goal_values(values: Iterable[str] | str | None) -> tuple[list[str], list[str], list[str]]:
    goal_keys: list[str] = []
    goal_secondary: list[str] = []
    support_flags: list[str] = []

    for raw in _clean_list(values):
        token = _slug(raw)
        primary = _GOAL_ALIASES.get(token)
        if primary:
            if primary in CANONICAL_SUPPORT_FLAGS:
                support_flags.append(primary)
            else:
                goal_keys.append(primary)
            continue
        if token in CANONICAL_GOAL_KEYS:
            goal_keys.append(token)
            continue
        secondary = _GOAL_SECONDARY_ALIASES.get(token)
        if secondary:
            goal_secondary.append(secondary)
            continue
        if token:
            goal_secondary.append(token)

    return (
        _dedupe_preserve_order(goal_keys),
        _dedupe_preserve_order(goal_secondary),
        _dedupe_preserve_order(support_flags),
    )


def normalize_weakness_values(values: Iterable[str] | str | None) -> tuple[list[str], list[str]]:
    weakness_keys: list[str] = []
    weakness_secondary: list[str] = []

    for raw in _clean_list(values):
        token = _slug(raw)
        primary = _WEAKNESS_ALIASES.get(token)
        if primary:
            weakness_keys.append(primary)
            weakness_secondary.extend(_WEAKNESS_SECONDARY.get(primary, []))
            continue
        if token in CANONICAL_WEAKNESS_KEYS:
            weakness_keys.append(token)
            weakness_secondary.extend(_WEAKNESS_SECONDARY.get(token, []))
            continue
        if token:
            weakness_secondary.append(token)

    return (
        _dedupe_preserve_order(weakness_keys),
        _dedupe_preserve_order(weakness_secondary),
    )


def normalize_style_values(
    technical_values: Iterable[str] | str | None,
    tactical_values: Iterable[str] | str | None,
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    technical_style_keys: list[str] = []
    tactical_style_keys: list[str] = []
    technical_style_secondary: list[str] = []
    tactical_style_secondary: list[str] = []

    for raw in _clean_list(technical_values):
        token = _slug(raw)
        primary = _TECHNICAL_STYLE_ALIASES.get(token, token if token in CANONICAL_TECHNICAL_STYLES else "")
        if primary:
            technical_style_keys.append(primary)

    for raw in _clean_list(tactical_values):
        token = _slug(raw)
        primary = _TACTICAL_STYLE_ALIASES.get(token, token if token in CANONICAL_TACTICAL_STYLES else "")
        if primary:
            tactical_style_keys.append(primary)
            tactical_style_secondary.extend(_TACTICAL_STYLE_SECONDARY.get(primary, []))

    technical_style_keys = _dedupe_preserve_order(technical_style_keys)
    tactical_style_keys = _dedupe_preserve_order(tactical_style_keys)
    technical_style_secondary = _dedupe_preserve_order(technical_style_secondary)
    tactical_style_secondary = _dedupe_preserve_order(tactical_style_secondary)
    style_secondary = _dedupe_preserve_order(
        technical_style_secondary + tactical_style_secondary
    )
    return (
        technical_style_keys,
        tactical_style_keys,
        technical_style_secondary,
        tactical_style_secondary,
        style_secondary,
    )


def normalize_intake_profile(
    *,
    goals: Iterable[str] | str | None,
    weaknesses: Iterable[str] | str | None,
    technical_styles: Iterable[str] | str | None,
    tactical_styles: Iterable[str] | str | None,
) -> NormalizedIntakeProfile:
    raw_goal_values = _clean_list(goals)
    raw_weakness_values = _clean_list(weaknesses)
    raw_technical_styles = _clean_list(technical_styles)
    raw_tactical_styles = _clean_list(tactical_styles)
    goal_keys, goal_secondary, support_flags = normalize_goal_values(raw_goal_values)
    weakness_keys, weakness_secondary = normalize_weakness_values(raw_weakness_values)
    (
        technical_style_keys,
        tactical_style_keys,
        technical_style_secondary,
        tactical_style_secondary,
        style_secondary,
    ) = normalize_style_values(raw_technical_styles, raw_tactical_styles)
    return NormalizedIntakeProfile(
        raw_goal_values=raw_goal_values,
        raw_weakness_values=raw_weakness_values,
        raw_technical_styles=raw_technical_styles,
        raw_tactical_styles=raw_tactical_styles,
        goal_keys=goal_keys,
        goal_secondary=goal_secondary,
        support_flags=support_flags,
        weakness_keys=weakness_keys,
        weakness_secondary=weakness_secondary,
        technical_style_keys=technical_style_keys,
        tactical_style_keys=tactical_style_keys,
        technical_style_secondary=technical_style_secondary,
        tactical_style_secondary=tactical_style_secondary,
        style_secondary=style_secondary,
    )


def normalized_profile_from_state(
    *,
    raw_goals: Iterable[str] | str | None = None,
    raw_weaknesses: Iterable[str] | str | None = None,
    raw_technical_styles: Iterable[str] | str | None = None,
    raw_tactical_styles: Iterable[str] | str | None = None,
    normalized_fields: Mapping[str, object] | None = None,
) -> NormalizedIntakeProfile:
    normalized_fields = normalized_fields or {}
    profile = normalize_intake_profile(
        goals=raw_goals,
        weaknesses=raw_weaknesses,
        technical_styles=raw_technical_styles,
        tactical_styles=raw_tactical_styles,
    )
    return NormalizedIntakeProfile(
        raw_goal_values=_clean_list(raw_goals or profile.raw_goal_values),
        raw_weakness_values=_clean_list(raw_weaknesses or profile.raw_weakness_values),
        raw_technical_styles=_clean_list(raw_technical_styles or profile.raw_technical_styles),
        raw_tactical_styles=_clean_list(raw_tactical_styles or profile.raw_tactical_styles),
        goal_keys=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("goal_keys")) or profile.goal_keys
        ),
        goal_secondary=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("goal_secondary")) or profile.goal_secondary
        ),
        support_flags=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("support_flags")) or profile.support_flags
        ),
        weakness_keys=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("weakness_keys")) or profile.weakness_keys
        ),
        weakness_secondary=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("weakness_secondary")) or profile.weakness_secondary
        ),
        technical_style_keys=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("technical_style_keys"))
            or profile.technical_style_keys
        ),
        tactical_style_keys=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("tactical_style_keys"))
            or profile.tactical_style_keys
        ),
        technical_style_secondary=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("technical_style_secondary"))
            or profile.technical_style_secondary
        ),
        tactical_style_secondary=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("tactical_style_secondary"))
            or profile.tactical_style_secondary
        ),
        style_secondary=_dedupe_preserve_order(
            _clean_list(normalized_fields.get("style_secondary")) or profile.style_secondary
        ),
    )


def normalized_profile_from_flags(flags: Mapping[str, object]) -> NormalizedIntakeProfile:
    return normalized_profile_from_state(
        raw_goals=flags.get("raw_key_goals") or flags.get("key_goals"),
        raw_weaknesses=flags.get("raw_weaknesses") or flags.get("weaknesses"),
        raw_technical_styles=flags.get("raw_style_technical") or flags.get("style_technical"),
        raw_tactical_styles=flags.get("raw_style_tactical") or flags.get("style_tactical"),
        normalized_fields={
            "goal_keys": flags.get("goal_keys"),
            "goal_secondary": flags.get("goal_secondary"),
            "support_flags": flags.get("support_flags"),
            "weakness_keys": flags.get("weakness_keys"),
            "weakness_secondary": flags.get("weakness_secondary"),
            "technical_style_keys": flags.get("technical_style_keys"),
            "tactical_style_keys": flags.get("tactical_style_keys"),
            "technical_style_secondary": flags.get("technical_style_secondary"),
            "tactical_style_secondary": flags.get("tactical_style_secondary"),
            "style_secondary": flags.get("style_secondary"),
        },
    )
