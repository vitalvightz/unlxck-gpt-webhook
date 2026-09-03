from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from .config import DATA_DIR
from .injury_guard import injury_decision
from .training_context import normalize_athlete_equipment_list, normalize_equipment_list

PHASES = ("GPP", "SPP", "TAPER")
TACTICAL_STYLES = (
    "pressure_fighter",
    "counter_striker",
    "distance_striker",
    "clinch_fighter",
    "grappler",
    "hybrid",
)
SUPPORTED_SPORTS = ("boxing", "kickboxing", "muay_thai", "mma", "wrestling", "bjj")
BANK_FILES = (
    "coordination/universal.json",
    "coordination/striking.json",
    "coordination/kicks.json",
    "coordination/mma_transitions.json",
    "coordination/grappling.json",
)

_STYLE_ALIASES = {
    "pressure": "pressure_fighter",
    "pressure_fighter": "pressure_fighter",
    "brawler": "pressure_fighter",
    "swarmer": "pressure_fighter",
    "inside_fighter": "pressure_fighter",
    "counter": "counter_striker",
    "counter_striker": "counter_striker",
    "counter_puncher": "counter_striker",
    "distance": "distance_striker",
    "distance_striker": "distance_striker",
    "out_boxer": "distance_striker",
    "range_fighter": "distance_striker",
    "clinch": "clinch_fighter",
    "clinch_fighter": "clinch_fighter",
    "grappler": "grappler",
    "wrestler": "grappler",
    "submission_hunter": "grappler",
    "hybrid": "hybrid",
    "scrambler": "hybrid",
}

_SPORT_ALIASES = {
    "boxer": "boxing",
    "boxing": "boxing",
    "kickboxer": "kickboxing",
    "kickboxing": "kickboxing",
    "muay_thai": "muay_thai",
    "muaythai": "muay_thai",
    "mma": "mma",
    "mixed_martial_arts": "mma",
    "wrestler": "wrestling",
    "wrestling": "wrestling",
    "bjj": "bjj",
    "jiu_jitsu": "bjj",
    "brazilian_jiu_jitsu": "bjj",
}

_COORDINATION_TARGET_TOKENS = {
    "coordination",
    "coordination_proprioception",
    "coordination/proprioception",
    "coordination / proprioception",
}


@dataclass(frozen=True)
class CoordinationDrill:
    key: str
    name: str
    sports: tuple[str, ...]
    styles: tuple[str, ...]
    qualities: tuple[str, ...]
    phases: tuple[str, ...]
    equipment: tuple[str, ...]
    duration_min: int
    rpe: int
    impact_cost: str
    movement_cost: str
    why: str
    cue: str
    raw: dict[str, Any]


def _token(value: Any) -> str:
    text = str(value or "").strip().lower()
    for separator in (" ", "-", "/", ".", "+"):
        text = text.replace(separator, "_")
    return "_".join(part for part in text.split("_") if part)


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _tokens(value: Any) -> list[str]:
    return [token for raw in _values(value) if (token := _token(raw))]


def has_coordination_target(athlete_model: dict[str, Any] | None) -> bool:
    if not isinstance(athlete_model, dict):
        return False
    target_tokens: set[str] = set()
    for field in (
        "weaknesses",
        "weak_areas",
        "key_goals",
        "goals",
        "targets",
        "training_targets",
    ):
        target_tokens.update(_tokens(athlete_model.get(field)))
    normalized_targets = {_token(value) for value in _COORDINATION_TARGET_TOKENS}
    return bool(target_tokens & normalized_targets)


def normalize_sport(value: Any) -> str:
    """Canonicalize a sport / fight-format string via the shared sport ontology.

    Reuses the same ``_SPORT_ALIASES`` identity map the coordination-support
    selector uses, so every consumer resolves ``"muay thai"``, ``"muaythai"``,
    ``"wrestler"``, ``"jiu jitsu"`` etc. to one canonical sport in
    :data:`SUPPORTED_SPORTS`. Unknown tokens are returned in cleaned form (so an
    unsupported sport still filters strictly rather than silently matching a
    different sport), and empty input returns ``""``.
    """
    token = _token(value)
    return _SPORT_ALIASES.get(token, token)


def extract_coordination_sport(athlete_model: dict[str, Any] | None) -> str:
    if not isinstance(athlete_model, dict):
        return "mma"
    for field in ("technical_styles", "technical_style", "sport"):
        for raw in _values(athlete_model.get(field)):
            token = _token(raw)
            if token in _SPORT_ALIASES:
                return _SPORT_ALIASES[token]
    return "mma"


def extract_coordination_style(athlete_model: dict[str, Any] | None) -> str:
    if not isinstance(athlete_model, dict):
        return "hybrid"
    for field in (
        "tactical_styles",
        "tactical_style",
        "style_tactical",
        "fighting_styles",
        "fighting_style",
        "style",
    ):
        for raw in _values(athlete_model.get(field)):
            token = _token(raw)
            if token in _STYLE_ALIASES:
                return _STYLE_ALIASES[token]
    return "hybrid"


def _raw_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for relative_path in BANK_FILES:
        raw = json.loads((DATA_DIR / relative_path).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"{relative_path} must contain a list")
        entries.extend(entry for entry in raw if isinstance(entry, dict))
    return entries


@lru_cache(maxsize=1)
def all_coordination_drills() -> tuple[CoordinationDrill, ...]:
    drills: list[CoordinationDrill] = []
    seen_keys: set[str] = set()
    seen_names: set[str] = set()

    for entry in _raw_entries():
        key = str(entry.get("key") or "").strip()
        name = str(entry.get("name") or "").strip()
        placement = _token(entry.get("placement"))
        sports = tuple(_tokens(entry.get("sports")))
        styles = tuple(_tokens(entry.get("styles")))
        qualities = tuple(_tokens(entry.get("qualities")))
        phases = tuple(str(value or "").strip().upper() for value in _values(entry.get("phases")))
        equipment = tuple(normalize_equipment_list(entry.get("equipment") or ["bodyweight"]))
        why = str(entry.get("why") or "").strip()
        cue = str(entry.get("cue") or "").strip()

        if not key or key in seen_keys:
            raise ValueError(f"duplicate or blank coordination key: {key!r}")
        if not name or name in seen_names:
            raise ValueError(f"duplicate or blank coordination name: {name!r}")
        if placement != "support":
            raise ValueError(f"coordination drill {key!r} must use placement='support'")
        if not sports or any(sport != "universal" and sport not in SUPPORTED_SPORTS for sport in sports):
            raise ValueError(f"coordination drill {key!r} has invalid sports")
        if not styles or any(style not in TACTICAL_STYLES for style in styles):
            raise ValueError(f"coordination drill {key!r} has invalid tactical styles")
        if not qualities:
            raise ValueError(f"coordination drill {key!r} needs coordination qualities")
        if not phases or any(phase not in PHASES for phase in phases):
            raise ValueError(f"coordination drill {key!r} has invalid phases")
        if not why or not cue:
            raise ValueError(f"coordination drill {key!r} has incomplete coaching content")

        drill = CoordinationDrill(
            key=key,
            name=name,
            sports=sports,
            styles=styles,
            qualities=qualities,
            phases=phases,
            equipment=equipment,
            duration_min=max(4, int(entry.get("duration_min") or 8)),
            rpe=max(1, min(6, int(entry.get("rpe") or 4))),
            impact_cost=_token(entry.get("impact_cost") or "low"),
            movement_cost=_token(entry.get("movement_cost") or "low"),
            why=why,
            cue=cue,
            raw=dict(entry),
        )
        drills.append(drill)
        seen_keys.add(key)
        seen_names.add(name)

    return tuple(drills)


def _athlete_equipment(athlete_model: dict[str, Any]) -> set[str]:
    raw: list[Any] = []
    for field in ("equipment", "equipment_access", "available_equipment"):
        raw.extend(_values(athlete_model.get(field)))
    return set(normalize_athlete_equipment_list(raw))


def _active_injuries(athlete_model: dict[str, Any]) -> list[Any]:
    injuries: list[Any] = []
    for field in ("parsed_injuries", "injuries"):
        injuries.extend(_values(athlete_model.get(field)))
    guided = athlete_model.get("guided_injury")
    if guided:
        injuries.append(guided)
    return [injury for injury in injuries if injury]


def _relevance_score(drill: CoordinationDrill, athlete_model: dict[str, Any], sport: str, style: str) -> float:
    score = 0.0
    if sport in drill.sports:
        score += 6.0
    elif "universal" in drill.sports:
        score += 2.0

    if style in drill.styles:
        score += 4.0
    if style == "hybrid" and len(drill.sports) > 1:
        score += 1.0

    weakness_tokens = set(_tokens(athlete_model.get("weaknesses")) + _tokens(athlete_model.get("weak_areas")))
    goal_tokens = set(_tokens(athlete_model.get("key_goals")) + _tokens(athlete_model.get("goals")))
    quality_tokens = set(drill.qualities)
    score += 2.0 * len(quality_tokens & weakness_tokens)
    score += 1.0 * len(quality_tokens & goal_tokens)

    if drill.impact_cost == "low":
        score += 0.5
    if drill.movement_cost == "low":
        score += 0.5
    return score


def select_coordination_support(
    athlete_model: dict[str, Any],
    phase: Any,
    used_keys: Iterable[str] | None = None,
) -> CoordinationDrill | None:
    if not has_coordination_target(athlete_model):
        return None

    phase_key = str(phase or "GPP").strip().upper()
    if phase_key not in PHASES:
        phase_key = "GPP"
    sport = extract_coordination_sport(athlete_model)
    style = extract_coordination_style(athlete_model)
    used = {str(key) for key in (used_keys or ())}
    athlete_equipment = _athlete_equipment(athlete_model)
    injuries = _active_injuries(athlete_model)
    fatigue = str(athlete_model.get("fatigue") or athlete_model.get("fatigue_level") or "low").strip().lower()

    candidates: list[tuple[float, str, CoordinationDrill]] = []
    for drill in all_coordination_drills():
        if drill.key in used or phase_key not in drill.phases:
            continue
        if sport not in drill.sports and "universal" not in drill.sports:
            continue
        if set(drill.equipment) - athlete_equipment:
            continue
        decision = injury_decision(drill.raw, injuries, phase_key, fatigue)
        if decision.action != "allow":
            continue
        candidates.append((_relevance_score(drill, athlete_model, sport, style), drill.key, drill))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def coordination_support_metadata(drill: CoordinationDrill) -> dict[str, Any]:
    global_tags = _tokens(drill.raw.get("tags")) or ["coordination"]
    return {
        "preferred_exercise_names": [drill.name],
        # Fine-grained coordination qualities stay local to this selector rather
        # than expanding the app-wide tag vocabulary.
        "preferred_tags": list(dict.fromkeys(global_tags)),
        "coordination_qualities": list(drill.qualities),
        "stress_class": "support",
        "cost_class": "low",
        "support_insert_category": "coordination",
        "support_insert_cost_category": "low_cost",
        "support_kind": "coordination",
        "governance": {
            "authority": "coordination_support_library",
            "selected_drill_locked": True,
            "selected_drill_name": drill.name,
            "render_selected_drill_exactly": True,
            "do_not_reselect_or_generalize": True,
            "meaningful_stress": False,
        },
    }


def build_coordination_display_text(drill: CoordinationDrill) -> str:
    return "\n".join(
        [
            f"Why: {drill.why}",
            f"- {drill.name}: {drill.duration_min} minutes, coordination support, RPE {drill.rpe}/10.",
            f"  Focus: {drill.cue}",
            "  Rule: Keep every rep clean. Stop the set when timing or stance quality drops.",
        ]
    )
