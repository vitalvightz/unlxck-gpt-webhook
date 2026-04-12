"""Boxing-specific conditioning utilities.

Contains sport-language sanitisation, aerobic drill classification,
aerobic priority/preference ranking, and alactic maintenance fallback
logic that only apply to the boxing fight format.

All public names are re-exported from conditioning.py for backward compat.
"""
from __future__ import annotations

import re



# ── Hint constants (only used by boxing aerobic logic) ───────────────────────
_LOWER_LIMB_UNLOAD_HINTS = {
    "ankle",
    "foot",
    "feet",
    "shin",
    "calf",
    "achilles",
    "knee",
    "quad",
    "hamstring",
    "groin",
    "hip",
}
_UPPER_BODY_SWIM_SENSITIVITY_HINTS = {
    "shoulder",
    "pec",
    "chest",
    "rib",
    "elbow",
    "wrist",
    "hand",
}
_TISSUE_IRRITATION_HINTS = {
    "sore",
    "soreness",
    "irritation",
    "irritated",
    "flare",
    "pain",
    "strain",
    "sprain",
    "tendon",
    "tendin",
    "swell",
    "bruise",
}
_IMPACT_SENSITIVE_RESTRICTIONS = {
    "high_impact",
    "high_impact_lower",
    "high_impact_global",
    "max_velocity",
}
_BIKE_EQUIPMENT_KEYS = {
    "assault_bike",
    "stationary_bike",
    "echo_bike",
    "bike_erg",
    "recumbent_bike",
    "air_dyne_bike",
}

# ── Boxing sport-language constants ──────────────────────────────────────────
SPORT_LANGUAGE_BLACKLIST = {
    "boxing": {
        "dirty td",
        "td setup",
        "takedown",
        "double-leg",
        "double leg",
        "single-leg",
        "single leg",
        "sprawl",
        "thai clinch",
        "clinch knee",
        "cage clinch",
        "elbow",
        "cage",
        "octagon",
        "ground and pound",
        "grappling",
    },
}
PLAIN_CONDITIONING_NAME_MAP = {
    "Barbell Bully": "Barbell Press-Squat Conditioning",
    "Trap Bar Death March": "Trap Bar Carry Intervals",
    "Barbell Smash & Dash": "Barbell Clean Sprint Intervals",
    "Jump Rope Endurance (Footwork Conditioning)": "Jump Rope Conditioning",
    "Assault Bike Steady State - Counter Striker": "Assault Bike Steady State",
    "Assault Bike Zone 2 Steady": "Easy Assault Bike",
    "Bike Zone 2 (Nasal Only)": "Easy Bike",
    "Tempo Shadowboxing (Aerobic)": "Tempo Shadowboxing",
    "Sled Harness Backward Drag": "Backward Sled Drag",
    "Dynamic Plank-to-Punch": "Plank Punch Reach",
    "Ankle Snap Bounce": "Ankling",
    "Clinch-Fighter Neck Endurance": "Neck Endurance Circuit",
}
BOXING_NAME_MAP = {
    "Clinch Frame Throws": "Medicine Ball Chest Pass",
    "Thai Clinch EMOM": "Hand-Fight Intervals",
    "Rope-A-Dope Clinch": "Hand-Fight Conditioning",
}


# ── Shared helpers (inline copies — conditioning.py also has these) ───────────

def _restriction_key_set(restrictions: Any) -> set[str]:
    if not restrictions:
        return set()
    keys: set[str] = set()
    for r in (restrictions if isinstance(restrictions, list) else [restrictions]):
        if isinstance(r, dict):
            key = r.get("key") or r.get("restriction_key") or r.get("type") or ""
            if key:
                keys.add(str(key).lower())
        elif isinstance(r, str):
            keys.add(r.lower())
    return keys


def _conditioning_context_text(*groups: Any) -> str:
    parts: list[str] = []
    for group in groups:
        if isinstance(group, list):
            parts.extend(str(item).lower() for item in group if item)
        elif group:
            parts.append(str(group).lower())
    return " ".join(parts)


# ── Boxing aerobic functions ──────────────────────────────────────────────────
def _sanitize_sport_language(text: str, *, fight_format: str) -> str:
    """Swap blacklisted sport language with sport-safe alternatives."""
    if not text:
        return text
    sanitized = text
    if fight_format == "boxing":
        replacements = {
            r"\bdirty\s*td\s*setups?\b": "entry setups",
            r"\btd\s*setups?\b": "entry setups",
            r"\btakedowns?\b": "entries",
            r"\bdouble\s*-?\s*legs?\b": "level changes",
            r"\bsingle\s*-?\s*legs?\b": "angle entries",
            r"\bsprawls?\b": "quick resets",
            r"\belbows?\b": "short hooks",
            r"\bthai\s+clinch\b": "inside hand-fight",
            r"\bclinch\s+knees?\b": "inside body-shot entries",
            r"\bcage\s+clinch\b": "inside hand-fight",
            r"\bcage\b": "ring edge",
            r"\boctagon\b": "ring",
            r"\bground\s+and\s+pound\b": "close-range punch flurries",
            r"\bgrappling\b": "hand-fighting",
        }
        for pattern, replacement in replacements.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def _normalize_conditioning_name(name: str, *, fight_format: str) -> str:
    cleaned = PLAIN_CONDITIONING_NAME_MAP.get(name, name)
    if fight_format == "boxing":
        cleaned = BOXING_NAME_MAP.get(cleaned, cleaned)
    return _sanitize_sport_language(cleaned, fight_format=fight_format)


def _is_pool_treading_drill(drill: dict) -> bool:
    name = str(drill.get("name", "")).lower()
    return "pool treading" in name or ("treading" in name and "pool" in name)


def _is_continuous_swim_drill(drill: dict) -> bool:
    name = str(drill.get("name", "")).lower()
    modality = str(drill.get("modality", "")).lower()
    if _is_pool_treading_drill(drill):
        return False
    if "pool running" in name or "pool walking" in name:
        return False
    return modality == "swim" and any(token in name for token in ("swim", "swimming", "freestyle"))


def _is_shadowbox_aerobic_drill(drill: dict) -> bool:
    name = str(drill.get("name", "")).lower()
    modality = str(drill.get("modality", "")).lower()
    return modality == "shadowbox" or "shadowboxing" in name


def _is_sled_drag_aerobic_drill(drill: dict) -> bool:
    name = str(drill.get("name", "")).lower()
    modality = str(drill.get("modality", "")).lower()
    return modality == "sled" or ("sled" in name and "drag" in name)


def _boxing_aerobic_priority_adjustment(
    drill: dict,
    *,
    injuries: list[str],
    weaknesses: list[str],
    goals: list[str],
    restrictions,
    equipment_access_set: set[str],
) -> float:
    modality = str(drill.get("modality", "")).lower()
    context = _boxing_aerobic_context_flags(
        injuries=injuries,
        weaknesses=weaknesses,
        goals=goals,
        restrictions=restrictions,
        equipment_access_set=equipment_access_set,
    )

    if _is_pool_treading_drill(drill):
        if context["pool_treading_strong_case"]:
            return 1.15
        if context["pool_treading_justified"]:
            return -0.25
        return -2.0

    if modality == "bike" or "bike" in str(drill.get("name", "")).lower():
        return 1.5

    if _is_continuous_swim_drill(drill):
        bonus = 1.1
        if context["upper_body_swim_sensitive"]:
            bonus -= 0.6
        return bonus

    if _is_shadowbox_aerobic_drill(drill):
        bonus = 0.9
        if context["lower_limb_unload_desirable"] or context["impact_tolerance_reduced"]:
            bonus -= 0.5
        return bonus

    if _is_sled_drag_aerobic_drill(drill):
        bonus = 0.75
        if context["lower_limb_unload_desirable"]:
            bonus -= 0.35
        return bonus

    if modality == "swim":
        return 0.55 if context["pool_treading_justified"] else 0.8

    return 0.0


def _boxing_aerobic_context_flags(
    *,
    injuries: list[str],
    weaknesses: list[str],
    goals: list[str],
    restrictions,
    equipment_access_set: set[str],
) -> dict[str, bool]:
    restriction_keys = _restriction_key_set(restrictions)
    context_text = _conditioning_context_text(injuries, weaknesses, goals)
    lower_limb_unload_desirable = any(token in context_text for token in _LOWER_LIMB_UNLOAD_HINTS)
    impact_tolerance_reduced = bool(restriction_keys & _IMPACT_SENSITIVE_RESTRICTIONS)
    if not impact_tolerance_reduced:
        impact_tolerance_reduced = any(
            token in context_text for token in ("impact", "shin splint", "landing", "reactive", "jarring")
        )
    active_tissue_irritation = any(token in context_text for token in _TISSUE_IRRITATION_HINTS)
    upper_body_swim_sensitive = any(token in context_text for token in _UPPER_BODY_SWIM_SENSITIVITY_HINTS)
    bike_available = bool(equipment_access_set & _BIKE_EQUIPMENT_KEYS)
    sled_available = "sled" in equipment_access_set

    pool_treading_justified = (
        lower_limb_unload_desirable
        or impact_tolerance_reduced
        or active_tissue_irritation
        or (not bike_available and not sled_available)
    )
    pool_treading_strong_case = (
        pool_treading_justified
        and (lower_limb_unload_desirable or impact_tolerance_reduced)
        and upper_body_swim_sensitive
        and not bike_available
    )

    return {
        "lower_limb_unload_desirable": lower_limb_unload_desirable,
        "impact_tolerance_reduced": impact_tolerance_reduced,
        "active_tissue_irritation": active_tissue_irritation,
        "upper_body_swim_sensitive": upper_body_swim_sensitive,
        "bike_available": bike_available,
        "sled_available": sled_available,
        "pool_treading_justified": pool_treading_justified,
        "pool_treading_strong_case": pool_treading_strong_case,
    }


def _boxing_aerobic_preference_rank(
    drill: dict,
    *,
    injuries: list[str],
    weaknesses: list[str],
    goals: list[str],
    restrictions,
    equipment_access_set: set[str],
) -> int:
    modality = str(drill.get("modality", "")).lower()
    context = _boxing_aerobic_context_flags(
        injuries=injuries,
        weaknesses=weaknesses,
        goals=goals,
        restrictions=restrictions,
        equipment_access_set=equipment_access_set,
    )

    if modality == "bike" or "bike" in str(drill.get("name", "")).lower():
        return 0
    if _is_pool_treading_drill(drill):
        if context["pool_treading_strong_case"]:
            return 1
        if context["pool_treading_justified"]:
            return 4
        return 5
    if _is_continuous_swim_drill(drill):
        return 3 if context["upper_body_swim_sensitive"] else 1
    if _is_shadowbox_aerobic_drill(drill):
        return 4 if context["lower_limb_unload_desirable"] or context["impact_tolerance_reduced"] else 2
    if _is_sled_drag_aerobic_drill(drill):
        return 4 if context["lower_limb_unload_desirable"] else 3
    if modality == "swim":
        return 4 if context["upper_body_swim_sensitive"] else 2
    return 3


def _violates_sport_language_blacklist(drill: dict, *, fight_format: str) -> bool:
    terms = SPORT_LANGUAGE_BLACKLIST.get(fight_format, set())
    if not terms:
        return False
    haystack = " ".join(
        str(drill.get(field, ""))
        for field in ("name", "modality", "notes", "purpose", "description", "duration", "timing")
    ).lower()
    return any(term in haystack for term in terms)


def _alactic_maintenance_fallback(phase: str) -> dict:
    phase = phase.upper()
    rounds = "6–8" if phase == "SPP" else "4–6"
    return {
        "system": "ALACTIC",
        "name": "Explosive Boxing Burst Intervals",
        "load": "RPE 8–9, keep quality high and stop before speed drop-off",
        "rest": "75-120 sec complete rest between reps",
        "timing": f"{rounds} x 6–10 sec fast punch bursts",
        "purpose": "Minimal-dose ATP-PCr maintenance for striking speed and neural sharpness.",
        "red_flags": "Terminate set if punch speed/position quality drops.",
        "equipment": [],
        "required_equipment": [],
        "generic_fallback": True,
    }


def _suppress_alactic_maintenance(*, fatigue: str, injuries: list[str]) -> bool:
    if (fatigue or "").lower() == "high":
        return True
    risk_terms = {
        "concussion",
        "dizzy",
        "vertigo",
        "hamstring tear",
        "achilles",
        "calf tear",
    }
    joined = " ".join(i.lower() for i in injuries)
    return any(term in joined for term in risk_terms)


