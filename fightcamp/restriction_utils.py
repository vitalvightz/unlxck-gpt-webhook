from __future__ import annotations

from .normalization import normalize_text, phrase_in_text, slugify, dedupe_preserve_order
from .restriction_parsing import CANONICAL_RESTRICTIONS

# ── Restriction and mechanical tag constants ──────────────────────────────

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
        "all-out sprint",
        "flying sprint",
        "overspeed sprint",
        "maximal speed",
    ],
    "high_impact": [
        "jump",
        "bound",
        "hop",
        "landing",
        "depth drop",
        "reactive pogo",
        "sprint landing",
        "impact run",
    ],
}

def restriction_item_text(item: dict) -> str:
    parts = []
    parts.append(str(item.get("movement", "") or ""))
    parts.append(str(item.get("primary_joint", "") or ""))
    parts.append(str(item.get("restriction", "") or ""))
    parts.append(str(item.get("reason", "") or ""))
    for tag in item.get("tags", []):
        parts.append(str(tag or ""))
    return normalize_text(" ".join(parts))

def derive_mechanical_risk_tags(item: dict) -> set[str]:
    tags = {
        str(tag).strip().lower().replace(" ", "_")
        for tag in item.get("tags", [])
        if str(tag).strip()
    }
    movement = str(item.get("movement", "")).strip().lower().replace(" ", "_")
    if movement:
        tags.add(movement)
    text = restriction_item_text(item)
    risk_tags = {
        tag
        for tag in tags
        if tag in _MECHANICAL_TAGS or any(tag.startswith(prefix) for prefix in _MECHANICAL_TAG_PREFIXES)
    }
    derived: set[str] = set()
    if any(tag in tags for tag in {"rotation", "rotational", "anti_rotation", "loaded_rotation", "loaded_twist", "mech_rotational_power"}):
        derived.add("loaded_rotation")
    if any(phrase_in_text(phrase, text) for phrase in _TEXT_DERIVED_RESTRICTIONS["loaded_rotation"]):
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
    if tags & overhead_tag_hits or any(phrase_in_text(phrase, text) for phrase in _TEXT_DERIVED_RESTRICTIONS["heavy_overhead_pressing"]):
        derived.add("heavy_overhead_pressing")
    deep_knee_hits = {
        "squat",
        "lunge",
        "split_squat",
        "quad_dominant",
        "knee_dominant",
        "deep_knee_flexion",
        "mech_knee_dominant_heavy",
        "mech_quad_heavy",
    }
    if tags & deep_knee_hits or any(phrase_in_text(phrase, text) for phrase in _TEXT_DERIVED_RESTRICTIONS["deep_knee_flexion"]):
        derived.add("deep_knee_flexion")
    deep_hip_hits = {
        "hinge",
        "deadlift",
        "swing",
        "hip_flexion",
        "deep_hip_flexion",
        "mech_hinge_heavy",
        "mech_hip_heavy",
    }
    if tags & deep_hip_hits or any(phrase_in_text(phrase, text) for phrase in _TEXT_DERIVED_RESTRICTIONS["deep_hip_flexion"]):
        derived.add("deep_hip_flexion")
    impact_hits = {
        "high_impact",
        "plyo",
        "plyometric",
        "jump",
        "bounding",
        "landing",
        "sprint",
        "max_velocity",
        "mech_high_impact",
        "mech_plyo_high",
    }
    if tags & impact_hits or any(phrase_in_text(phrase, text) for phrase in _TEXT_DERIVED_RESTRICTIONS["high_impact"]):
        derived.add("high_impact")
    if any(tag in tags for tag in {"situp", "crunch", "flexion", "spinal_flexion"}):
        derived.add("loaded_flexion")
    if any(phrase_in_text(phrase, text) for phrase in _TEXT_DERIVED_RESTRICTIONS["loaded_flexion"]):
        derived.add("loaded_flexion")
    if any(tag in tags for tag in {"sprint", "max_velocity", "mech_max_velocity"}):
        derived.add("max_velocity")
    if any(phrase_in_text(phrase, text) for phrase in _TEXT_DERIVED_RESTRICTIONS["max_velocity"]):
        derived.add("max_velocity")
    if tags & {"neck", "cervical_load", "cervical_extension_loaded", "cervical_flexion_loaded", "neck_bridge"}:
        derived.add("cervical_loading")
    if tags & {"loaded_carry", "axial_loading", "mech_axial_heavy"}:
        derived.add("axial_loading")
    if tags & {"cod_high", "mech_change_of_direction"}:
        derived.add("change_of_direction")

    return risk_tags | derived

def extract_restriction_tags(item: dict) -> list[str]:
    tags = {
        str(tag).strip().lower().replace(" ", "_")
        for tag in item.get("tags", [])
        if str(tag).strip()
    }
    movement = str(item.get("movement", "")).strip().lower().replace(" ", "_")
    if movement:
        tags.add(movement)
    return sorted(tags | derive_mechanical_risk_tags(item))

def extract_mechanical_risk_tags(item: dict) -> list[str]:
    return sorted(derive_mechanical_risk_tags(item))

def restriction_patterns_for_key(restriction_key: str) -> list[str]:
    base_key = _RESTRICTION_CANONICAL_KEYS.get(restriction_key)
    patterns = list(RESTRICTION_PATTERN_HINTS.get(restriction_key, []))
    if base_key:
        canonical = CANONICAL_RESTRICTIONS.get(base_key, {})
        patterns.extend(canonical.get("keywords", []))
    return dedupe_preserve_order([pattern for pattern in patterns if pattern])

def serialize_restrictions(restrictions: list[dict]) -> list[dict]:
    serialized: list[dict] = []
    for entry in restrictions or []:
        restriction_key = entry.get("restriction", "")
        blocked_patterns = restriction_patterns_for_key(restriction_key)
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
