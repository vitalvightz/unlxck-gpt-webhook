"""Canonical Stage 2 restriction and mechanical-risk tag helpers.

Single source of truth for restriction/mechanical-tag parsing and
serialization. Both ``stage2_payload`` and ``stage2_planning_brief``
re-export these names so existing call sites continue to work, but neither
file owns a separate real implementation any more.

Authority decision: the implementation here mirrors the prior
``stage2_planning_brief`` version, which is consistent with the canonical
mechanical-tag vocabulary used elsewhere in the codebase
(``injury_filtering``, ``injury_guard``, ``injury_exclusion_rules``). The
old ``stage2_payload`` local copies emitted ``"cervical_loading"`` and
``"change_of_direction"`` which no other module reads — those were drift,
not an intentional fix, and are corrected by adopting the canonical names.
"""
from __future__ import annotations

from .normalization import (
    clean_list,
    dedupe_preserve_order,
    normalize_text,
    phrase_in_text,
)
from .restriction_parsing import CANONICAL_RESTRICTIONS


RESTRICTION_PATTERN_HINTS = {
    "deep_knee_flexion": [
        "deep bilateral squat",
        "full ROM lunge",
        "split squat",
        "rear-foot-elevated split squat",
        "deep knee-dominant step-up",
    ],
    "deep_hip_flexion": [
        "deep hip flexion",
        "knee drive above pelvis",
        "loaded tuck",
        "loaded pike",
        "deep seated compression",
    ],
    "high_impact": ["jump", "bound", "hop", "sprint landing", "reactive pogo"],
    "high_impact_lower": [
        "jump",
        "bound",
        "hop",
        "landing",
        "depth drop",
        "reactive pogo",
        "hard change of direction",
    ],
    "high_impact_upper": [
        "clap push-up",
        "plyo push-up",
        "explosive push-up",
        "ballistic upper-body catch",
    ],
    "high_impact_global": [
        "jump",
        "bound",
        "hop",
        "landing",
        "reactive rebound",
        "impact running",
    ],
    "heavy_overhead_pressing": [
        "overhead press",
        "jerk",
        "push press",
        "thruster",
        "overhead carry",
        "overhead slam",
        "z press",
    ],
    "spinal_flexion": ["loaded spinal flexion", "sit-up", "rounded hinge"],
    "loaded_flexion": ["weighted sit-up", "loaded crunch", "V-up", "toe-touch"],
    "loaded_rotation": ["med-ball rotational throw", "loaded twist", "dynamic trunk rotation"],
    "max_velocity": ["max sprint", "all-out sprint", "flying sprint", "overspeed sprint"],
}


_RESTRICTION_CANONICAL_KEYS = {
    "deep_knee_flexion": "deep knee flexion",
    "deep_hip_flexion": "deep hip flexion",
    "heavy_overhead_pressing": "heavy overhead pressing",
    "high_impact": "high impact",
    "high_impact_lower": "high impact",
    "high_impact_upper": "high impact",
    "high_impact_global": "high impact",
    "loaded_flexion": "loaded flexion",
    "max_velocity": "max velocity",
}


_MECHANICAL_TAG_PREFIXES = ("mech_",)
_MECHANICAL_TAGS = {
    "overhead",
    "press",
    "push_press",
    "jerk",
    "thruster",
    "dynamic_overhead",
    "press_heavy",
    "high_impact",
    "high_impact_plyo",
    "plyometric",
    "jumping",
    "landing_stress_high",
    "reactive_rebound_high",
    "impact_rebound_high",
    "foot_impact_high",
    "forefoot_load_high",
    "sprint",
    "max_velocity",
    "decel_high",
    "cod_high",
    "rotation",
    "rotational",
    "anti_rotation",
    "loaded_rotation",
    "loaded_twist",
    "squat",
    "lunge",
    "split_squat",
    "quad_dominant",
    "quad_dominant_heavy",
    "deep_knee_flexion_loaded",
    "knee_dominant_heavy",
    "situp",
    "crunch",
    "flexion",
    "spinal_flexion",
    "hip_flexion_loaded",
    "neck",
    "cervical_load",
    "cervical_extension_loaded",
    "cervical_flexion_loaded",
    "neck_bridge",
    "loaded_carry",
    "axial_loading",
    "mech_axial_heavy",
}


_TEXT_DERIVED_RESTRICTIONS = {
    "deep_knee_flexion": [
        "deep squat",
        "full rom lunge",
        "split squat",
        "rear foot elevated split squat",
        "bulgarian split squat",
        "pistol squat",
        "cyclist squat",
        "deep knee flexion",
        "step-up heavy",
    ],
    "deep_hip_flexion": [
        "deep hip flexion",
        "knee drive above pelvis",
        "high knee drive",
        "loaded pike",
        "loaded tuck",
        "compression hold",
        "seated compression",
        "hip flexion under load",
    ],
    "heavy_overhead_pressing": [
        "overhead press",
        "push press",
        "jerk",
        "thruster",
        "snatch",
        "overhead carry",
        "overhead hold",
        "overhead slam",
        "strict press",
        "military press",
        "z press",
        "handstand",
    ],
    "loaded_flexion": [
        "weighted sit-up",
        "weighted sit up",
        "loaded sit-up",
        "loaded sit up",
        "loaded crunch",
        "weighted crunch",
        "v-up",
        "v up",
        "toe-touch",
        "toe touch",
    ],
    "loaded_rotation": [
        "rotational throw",
        "rotational slam",
        "loaded twist",
        "russian twist",
        "med ball scoop",
        "shotput throw",
        "rotation throw",
    ],
    "max_velocity": [
        "max sprint",
        "maximal sprint",
        "all-out sprint",
        "all out sprint",
        "full sprint",
        "flying sprint",
        "overspeed sprint",
        "top-speed sprint",
        "top speed sprint",
    ],
    "high_impact_upper": [
        "clap push-up",
        "clap pushup",
        "plyo push-up",
        "plyo pushup",
        "plyometric push-up",
        "plyometric pushup",
        "explosive push-up",
        "explosive pushup",
    ],
    "high_impact_lower": [
        "jump",
        "hop",
        "bound",
        "landing",
        "depth jump",
        "drop jump",
        "depth drop",
        "pogo",
        "reactive hop",
        "reactive rebound",
        "hard decel",
        "hard deceleration",
        "change of direction",
        "agility cut",
        "sharp cut",
        "lateral bound",
        "jump rope",
        "burpee",
        "sprawl",
    ],
}


def _restriction_item_text(item: dict) -> str:
    fields = [
        item.get("name", ""),
        item.get("movement", ""),
        item.get("method", ""),
        item.get("prescription", ""),
        item.get("timing", ""),
        item.get("rest", ""),
        item.get("load", ""),
        item.get("notes", ""),
        item.get("purpose", ""),
        item.get("description", ""),
        item.get("modality", ""),
        item.get("equipment_note", ""),
    ]
    fields.extend(clean_list(item.get("equipment", [])))
    return normalize_text(" ".join(str(field) for field in fields if field))


def _derive_mechanical_risk_tags(item: dict) -> set[str]:
    tags = {
        str(tag).strip().lower().replace(" ", "_")
        for tag in item.get("tags", [])
        if str(tag).strip()
    }
    movement = str(item.get("movement", "")).strip().lower().replace(" ", "_")
    if movement:
        tags.add(movement)
    text = _restriction_item_text(item)

    risk_tags = {
        tag
        for tag in tags
        if tag in _MECHANICAL_TAGS or any(tag.startswith(prefix) for prefix in _MECHANICAL_TAG_PREFIXES)
    }

    derived: set[str] = set()

    if any(tag in tags for tag in {"rotation", "rotational", "anti_rotation", "loaded_rotation", "loaded_twist", "mech_rotational_power"}):
        derived.add("loaded_rotation")
    if any(phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["loaded_rotation"]):
        derived.add("loaded_rotation")

    overhead_tag_hits = {
        "overhead",
        "press",
        "push_press",
        "jerk",
        "thruster",
        "dynamic_overhead",
        "press_heavy",
        "mech_overhead_dynamic",
        "mech_overhead_static",
        "mech_axial_heavy",
    }
    if tags & overhead_tag_hits or any(phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["heavy_overhead_pressing"]):
        derived.add("heavy_overhead_pressing")

    deep_knee_hits = {
        "squat",
        "lunge",
        "split_squat",
        "quad_dominant",
        "quad_dominant_heavy",
        "deep_knee_flexion_loaded",
        "knee_dominant_heavy",
        "mech_knee_dominant",
    }
    if tags & deep_knee_hits or any(phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["deep_knee_flexion"]):
        derived.add("deep_knee_flexion")

    deep_hip_hits = {"hip_flexion_loaded", "mech_hip_flexion", "mech_core_compression"}
    if tags & deep_hip_hits or any(phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["deep_hip_flexion"]):
        derived.add("deep_hip_flexion")

    if tags & {"situp", "crunch", "flexion", "spinal_flexion", "hip_flexion_loaded", "loaded_flexion"}:
        derived.add("loaded_flexion")
    if any(phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["loaded_flexion"]):
        derived.add("loaded_flexion")
    if "spinal_flexion" in derived or "loaded_flexion" in derived:
        derived.add("spinal_flexion")

    lower_impact_hits = {
        "high_impact",
        "high_impact_plyo",
        "plyometric",
        "jumping",
        "landing_stress_high",
        "reactive_rebound_high",
        "impact_rebound_high",
        "foot_impact_high",
        "forefoot_load_high",
        "decel_high",
        "cod_high",
        "mech_landing_impact",
        "mech_reactive_rebound",
        "mech_reactive",
        "mech_ballistic",
        "mech_change_of_direction",
        "mech_deceleration",
        "achilles_high_risk_impact",
    }
    if tags & lower_impact_hits or any(phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["high_impact_lower"]):
        derived.update({"high_impact", "high_impact_lower"})

    upper_impact_hits = {"explosive_upper_push", "mech_upper_ballistic", "mech_horizontal_push"}
    if tags & upper_impact_hits or any(phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["high_impact_upper"]):
        derived.update({"high_impact", "high_impact_upper"})

    if "high_impact" in derived and not ({"high_impact_lower", "high_impact_upper"} & derived):
        derived.add("high_impact_global")

    if tags & {"max_velocity", "mech_max_velocity"} or any(phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["max_velocity"]):
        derived.add("max_velocity")
        derived.update({"high_impact", "high_impact_lower"})

    if tags & {"cervical_load", "cervical_extension_loaded", "cervical_flexion_loaded", "neck_bridge", "neck"}:
        derived.add("cervical_load")
    if tags & {"loaded_carry", "axial_loading", "mech_axial_heavy"}:
        derived.add("axial_loading")
    if tags & {"cod_high", "mech_change_of_direction"}:
        derived.add("cod_high")

    return risk_tags | derived


def _extract_restriction_tags(item: dict) -> list[str]:
    tags = {
        str(tag).strip().lower().replace(" ", "_")
        for tag in item.get("tags", [])
        if str(tag).strip()
    }
    movement = str(item.get("movement", "")).strip().lower().replace(" ", "_")
    if movement:
        tags.add(movement)
    return sorted(tags | _derive_mechanical_risk_tags(item))


def _extract_mechanical_risk_tags(item: dict) -> list[str]:
    return sorted(_derive_mechanical_risk_tags(item))


def _restriction_patterns_for_key(restriction_key: str) -> list[str]:
    base_key = _RESTRICTION_CANONICAL_KEYS.get(restriction_key)
    patterns = list(RESTRICTION_PATTERN_HINTS.get(restriction_key, []))
    if base_key:
        canonical = CANONICAL_RESTRICTIONS.get(base_key, {})
        patterns.extend(canonical.get("keywords", []))
    return dedupe_preserve_order([pattern for pattern in patterns if pattern])


def _serialize_restrictions(restrictions: list[dict]) -> list[dict]:
    serialized: list[dict] = []
    for entry in restrictions or []:
        restriction_key = entry.get("restriction", "")
        blocked_patterns = _restriction_patterns_for_key(restriction_key)
        row = {
            "restriction": restriction_key,
            "region": entry.get("region"),
            "strength": entry.get("strength"),
            "side": entry.get("side"),
            "source_phrase": entry.get("original_phrase"),
            "blocked_patterns": blocked_patterns,
            "mechanical_equivalents": blocked_patterns[:6],
        }
        serialized.append({key: value for key, value in row.items() if value not in (None, "", [])})
    return serialized
