from __future__ import annotations

import re
from typing import Any

from .tagging import normalize_tags
from .training_context import normalize_equipment_list

ANCHOR_CAPABLE_CLASSES = {"anchor_loaded", "anchor_power", "anchor_force_isometric"}
SUPPORT_ONLY_CLASSES = {"support_isometric", "support_accessory", "rehab_support"}

STRENGTH_QUALITY_WEIGHTS = {
    "anchor_loaded": {"GPP": 1.0, "SPP": 1.0, "TAPER": 0.45},
    "anchor_power": {"GPP": 0.7, "SPP": 0.9, "TAPER": 0.5},
    "anchor_force_isometric": {"GPP": 0.45, "SPP": 0.35, "TAPER": 0.15},
    "support_only_penalty": {"GPP": -0.7, "SPP": -0.8, "TAPER": -0.25},
    "rehab_support_penalty": {"GPP": -0.9, "SPP": -1.0, "TAPER": -0.35},
    "duplicate_support_penalty": {"GPP": -0.35, "SPP": -0.4, "TAPER": -0.2},
}

ISOMETRIC_SESSION_SCORE_BAND = {"GPP": 0.08, "SPP": 0.08, "TAPER": 0.05}

_LOADED_EQUIPMENT = {
    "barbell",
    "trap_bar",
    "dumbbell",
    "dumbbells",
    "kettlebell",
    "kettlebells",
    "cable",
    "landmine",
    "sandbag",
    "bulgarian_bag",
    "log",
    "atlas_stone",
    "water_jug",
    "weight_vest",
    "plate",
    "partner",
}

_PUSH_HINTS = {"push", "press", "bench", "dip"}
_PULL_HINTS = {"pull", "row", "chin", "pullup", "pull-up"}
_LOWER_BODY_HINTS = {"squat", "hinge", "deadlift", "rdl", "lunge", "split squat", "step-up", "step up"}
_UNILATERAL_HINTS = {"unilateral", "single_leg", "single leg", "split squat", "step-up", "step up"}
_POWER_HINTS = {
    "explosive",
    "rate_of_force",
    "speed_strength",
    "ballistic",
    "reactive",
    "medicine_ball",
    "med ball",
    "throw",
    "slam",
    "jump",
    "hop",
    "bound",
    "contrast",
    "neural_primer",
}
_SUPPORT_HINTS = {
    "carry",
    "loaded_carry",
    "core",
    "trunk",
    "stability",
    "anti_rotation",
    "anti rotation",
    "breathing",
    "mobility",
    "neck",
    "parasympathetic",
}
_REHAB_HINTS = {"rehab", "therapy", "prehab"}
_ISOMETRIC_HINTS = {"isometric", "iso hold", "iso", "hold"}
_FORCE_ISOMETRIC_HINTS = {
    "pins",
    "pin",
    "% 1rm",
    "%1rm",
    "110%",
    "115%",
    "120%",
    "mid-shin",
    "deadlift isometric",
    "squat hold",
    "split squat hold",
    "overcoming",
    "yielding",
}


def _collect_tags(item: dict[str, Any]) -> set[str]:
    tags = set(normalize_tags(item.get("tags") or []))
    tags.update(normalize_tags(item.get("movement_patterns") or []))
    movement = str(item.get("movement") or "").strip().lower()
    if movement:
        tags.add(movement.replace(" ", "_"))
    return {tag for tag in tags if tag}


def _collect_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("name", "movement", "method", "prescription", "purpose", "notes", "description"):
        value = item.get(key)
        if value:
            parts.append(str(value))
    patterns = item.get("movement_patterns") or []
    if patterns:
        parts.extend(str(pattern) for pattern in patterns if str(pattern).strip())
    return " ".join(parts).lower()


def _has_any_hint(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)


def _loaded_pattern(tags: set[str], text: str, equipment: set[str]) -> bool:
    if equipment & _LOADED_EQUIPMENT:
        return True
    if "compound" in tags:
        return True
    if _has_any_hint(text, _LOWER_BODY_HINTS | _PUSH_HINTS | _PULL_HINTS):
        return any(hint in text for hint in {"deadlift", "squat", "press", "row", "pull", "split squat", "step-up", "step up"})
    return False


def classify_strength_item(item: dict[str, Any]) -> dict[str, Any]:
    tags = _collect_tags(item)
    text = _collect_text(item)
    equipment = set(normalize_equipment_list(item.get("equipment") or []))
    is_rehab = _has_any_hint(text, _REHAB_HINTS) or "rehab" in tags
    is_isometric = "isometric" in tags or _has_any_hint(text, _ISOMETRIC_HINTS)
    loaded_pattern = _loaded_pattern(tags, text, equipment)
    lower_body_loaded = loaded_pattern and _has_any_hint(text, _LOWER_BODY_HINTS | {"quad_dominant", "posterior_chain", "hip_dominant"})
    upper_body_push_pull = loaded_pattern and _has_any_hint(text, _PUSH_HINTS | _PULL_HINTS | {"upper_body"})
    unilateral = "unilateral" in tags or _has_any_hint(text, _UNILATERAL_HINTS)
    power_pattern = bool(tags & _POWER_HINTS) or _has_any_hint(text, _POWER_HINTS)
    support_only = bool(tags & _SUPPORT_HINTS) or _has_any_hint(text, _SUPPORT_HINTS)
    force_isometric = is_isometric and (
        loaded_pattern
        or bool(tags & {"posterior_chain", "quad_dominant", "hip_dominant", "push", "pull"})
        or _has_any_hint(text, _FORCE_ISOMETRIC_HINTS)
    )

    if is_rehab:
        quality_class = "rehab_support"
    elif force_isometric:
        quality_class = "anchor_force_isometric"
    elif power_pattern and not support_only:
        quality_class = "anchor_power"
    elif loaded_pattern and (lower_body_loaded or upper_body_push_pull or unilateral):
        quality_class = "anchor_loaded"
    elif is_isometric:
        quality_class = "support_isometric"
    else:
        quality_class = "support_accessory"

    base_categories: set[str] = set()
    if lower_body_loaded:
        base_categories.add("lower_body_loaded")
    if upper_body_push_pull:
        base_categories.add("upper_body_push_pull")
    if unilateral:
        base_categories.add("unilateral")

    return {
        "quality_class": quality_class,
        "anchor_capable": quality_class in ANCHOR_CAPABLE_CLASSES,
        "support_only": quality_class in SUPPORT_ONLY_CLASSES,
        "force_isometric": quality_class == "anchor_force_isometric",
        "loaded_pattern": loaded_pattern,
        "power_pattern": quality_class == "anchor_power",
        "rehab_support": quality_class == "rehab_support",
        "base_categories": sorted(base_categories),
    }


def infer_strength_sessions(exercises: list[dict[str, Any]], num_sessions: int) -> list[dict[str, Any]]:
    session_count = max(1, int(num_sessions or 1))
    if not exercises:
        return [{"session_index": idx + 1, "items": []} for idx in range(session_count)]

    sessions = [{"session_index": idx + 1, "items": [], "positions": []} for idx in range(session_count)]
    for idx, exercise in enumerate(exercises):
        session_idx = idx if idx < session_count else idx % session_count
        sessions[session_idx]["items"].append(exercise)
        sessions[session_idx]["positions"].append(idx)

    for session in sessions:
        anchor_index = None
        for idx, exercise in enumerate(session["items"]):
            if classify_strength_item(exercise)["anchor_capable"]:
                anchor_index = idx
                break
        session["anchor_index"] = anchor_index
    return sessions


def score_band_margin(values: list[float], *, phase: str) -> float:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return ISOMETRIC_SESSION_SCORE_BAND.get(phase.upper(), 0.08)
    high = max(cleaned)
    low = min(cleaned)
    spread = max(high - low, 0.0)
    return max(ISOMETRIC_SESSION_SCORE_BAND.get(phase.upper(), 0.08), spread * 0.08)


def session_support_count_before_anchor(session_items: list[dict[str, Any]]) -> int:
    count = 0
    for exercise in session_items:
        profile = classify_strength_item(exercise)
        if profile["anchor_capable"]:
            break
        if profile["support_only"]:
            count += 1
    return count


def session_starts_with_support_only(session_items: list[dict[str, Any]]) -> bool:
    first_two = session_items[:2]
    if not first_two:
        return False
    return all(classify_strength_item(exercise)["support_only"] for exercise in first_two)


def has_anchor_capable_option(exercises: list[dict[str, Any]]) -> bool:
    return any(classify_strength_item(exercise)["anchor_capable"] for exercise in exercises)


def count_support_only(exercises: list[dict[str, Any]]) -> int:
    return sum(1 for exercise in exercises if classify_strength_item(exercise)["support_only"])


def missing_base_categories(exercises: list[dict[str, Any]]) -> list[str]:
    present: set[str] = set()
    for exercise in exercises:
        present.update(classify_strength_item(exercise)["base_categories"])
    ordered = ["lower_body_loaded", "upper_body_push_pull", "unilateral"]
    return [category for category in ordered if category not in present]


def normalize_line_name(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def strength_quality_adjustment(item: dict[str, Any], *, phase: str) -> tuple[float, dict[str, Any]]:
    profile = classify_strength_item(item)
    quality_class = profile["quality_class"]
    weights = STRENGTH_QUALITY_WEIGHTS
    if quality_class in {"anchor_loaded", "anchor_power", "anchor_force_isometric"}:
        adjustment = weights[quality_class].get(phase.upper(), 0.0)
    elif quality_class == "rehab_support":
        adjustment = weights["rehab_support_penalty"].get(phase.upper(), 0.0)
    else:
        adjustment = weights["support_only_penalty"].get(phase.upper(), 0.0)
    return adjustment, profile
