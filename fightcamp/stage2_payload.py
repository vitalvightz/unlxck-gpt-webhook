from __future__ import annotations

import json
import re

from .restriction_parsing import CANONICAL_RESTRICTIONS
from .rehab_protocols import _rehab_drills_for_phase
from .training_context import TrainingContext, allocate_sessions

RESTRICTION_PATTERN_HINTS = {
    "deep_knee_flexion": [
        "deep bilateral squat",
        "full ROM lunge",
        "split squat",
        "rear-foot-elevated split squat",
        "deep knee-dominant step-up",
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


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower())
    return cleaned.strip("_") or "slot"


def _clean_list(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    return [str(values).strip()]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _phrase_in_text(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    parts = [re.escape(part) for part in re.split(r"[\s-]+", phrase.strip().lower()) if part]
    if not parts:
        return False
    pattern = r"\b" + r"[\s-]+".join(parts) + r"\b"
    return re.search(pattern, text) is not None


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
    fields.extend(_clean_list(item.get("equipment", [])))
    return _normalize_text(" ".join(str(field) for field in fields if field))


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
    if any(_phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["loaded_rotation"]):
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
    if tags & overhead_tag_hits or any(_phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["heavy_overhead_pressing"]):
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
    if tags & deep_knee_hits or any(_phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["deep_knee_flexion"]):
        derived.add("deep_knee_flexion")

    if tags & {"situp", "crunch", "flexion", "spinal_flexion", "hip_flexion_loaded", "loaded_flexion"}:
        derived.add("loaded_flexion")
    if any(_phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["loaded_flexion"]):
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
    if tags & lower_impact_hits or any(_phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["high_impact_lower"]):
        derived.update({"high_impact", "high_impact_lower"})

    upper_impact_hits = {"explosive_upper_push", "mech_upper_ballistic", "mech_horizontal_push"}
    if tags & upper_impact_hits or any(_phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["high_impact_upper"]):
        derived.update({"high_impact", "high_impact_upper"})

    if "high_impact" in derived and not ({"high_impact_lower", "high_impact_upper"} & derived):
        derived.add("high_impact_global")

    if tags & {"max_velocity", "mech_max_velocity"} or any(_phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["max_velocity"]):
        derived.add("max_velocity")
        derived.update({"high_impact", "high_impact_lower"})

    if tags & {"cervical_load", "cervical_extension_loaded", "cervical_flexion_loaded", "neck_bridge", "neck"}:
        derived.add("cervical_loading")
    if tags & {"loaded_carry", "axial_loading", "mech_axial_heavy"}:
        derived.add("axial_loading")
    if tags & {"cod_high", "mech_change_of_direction"}:
        derived.add("change_of_direction")

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
    return _dedupe_preserve_order([pattern for pattern in patterns if pattern])


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

def _derive_readiness_flags(
    *,
    fatigue: str,
    weight_cut_risk: bool,
    weight_cut_pct: float,
    injuries: list[str],
    short_notice: bool,
    days_until_fight: int | None,
) -> list[str]:
    flags: list[str] = []
    fatigue_value = (fatigue or "").strip().lower()
    if fatigue_value in {"moderate", "high"}:
        flags.append(f"{fatigue_value}_fatigue")
    if weight_cut_risk:
        flags.append("active_weight_cut")
    if weight_cut_pct >= 5.0:
        flags.append("aggressive_weight_cut")
    if injuries:
        flags.append("injury_management")
    if short_notice:
        flags.append("short_notice")
    if isinstance(days_until_fight, int) and days_until_fight <= 7:
        flags.append("fight_week")
    return flags or ["baseline"]


PHASE_OBJECTIVES = {
    "GPP": "build aerobic base and general force capacity",
    "SPP": "increase fight-specific repeatability and power transfer",
    "TAPER": "maintain sharpness and freshness",
}

PHASE_EMPHASIS = {
    "GPP": ["aerobic repeatability", "general force", "trunk/neck robustness"],
    "SPP": ["glycolytic repeatability", "rotational intent", "sport speed"],
    "TAPER": ["alactic sharpness", "confidence", "low soreness"],
}

PHASE_DEPRIORITIZE = {
    "GPP": ["fight-week intensity", "excessive reactive fatigue"],
    "SPP": ["excessive eccentric damage", "non-specific conditioning volume"],
    "TAPER": ["new drills", "high lactate exposure", "soreness-heavy loading"],
}

CONDITIONING_ROLE_PURPOSES = {
    "aerobic": "low-damage aerobic development",
    "glycolytic": "fight-pace repeatability",
    "alactic": "speed and neural sharpness",
}

PHASE_CONDITIONING_PRIORITY = {
    "GPP": {"aerobic": "critical", "glycolytic": "medium", "alactic": "medium"},
    "SPP": {"glycolytic": "critical", "alactic": "high", "aerobic": "medium"},
    "TAPER": {"alactic": "critical", "aerobic": "medium", "glycolytic": "low"},
}

PHASE_SELECTION_GUARDRAILS = {
    "GPP": {
        "conditioning_minimums": {"aerobic": 1, "glycolytic": 0, "alactic": 0},
        "must_keep_if_present": ["rehab", "aerobic", "primary_strength"],
        "conditioning_drop_order_if_thin": ["alactic", "glycolytic"],
        "notes": [
            "Preserve at least one low-damage aerobic slot before trimming other conditioning work.",
            "If strength must be trimmed, keep the first strength slot before accessories.",
        ],
    },
    "SPP": {
        "conditioning_minimums": {"aerobic": 0, "glycolytic": 1, "alactic": 1},
        "must_keep_if_present": ["rehab", "glycolytic", "alactic", "primary_strength"],
        "conditioning_drop_order_if_thin": ["aerobic", "extra_strength_accessory"],
        "notes": [
            "Preserve fight-pace repeatability first, then speed/sharpness support.",
            "Do not let compliance filtering remove both glycolytic and alactic work if compliant options remain.",
        ],
    },
    "TAPER": {
        "conditioning_minimums": {"aerobic": 0, "glycolytic": 0, "alactic": 1},
        "must_keep_if_present": ["rehab", "alactic", "primary_strength"],
        "conditioning_drop_order_if_thin": ["glycolytic", "aerobic", "extra_strength_accessory"],
        "notes": [
            "Preserve neural sharpness before optional conditioning density.",
            "If a slot becomes thin, drop soreness-heavy or lactate-heavy work before sharpness work.",
        ],
    },
}


PLANNING_DECISION_HIERARCHY = [
    {
        "rank": 1,
        "driver": "phase_survival_rules",
        "scope": ["phase guardrails", "must-keep slots", "conditioning minimums", "drop order if thin"],
        "reason": "Phase survival rules decide what must stay alive when the plan gets thin.",
    },
    {
        "rank": 2,
        "driver": "safety_and_readiness",
        "scope": ["restrictions", "injuries", "fatigue", "weight cut", "short notice"],
        "reason": "Safety and readiness can only tighten or reduce work, never get overruled by style preference.",
    },
    {
        "rank": 3,
        "driver": "sport_load_collision_rules",
        "scope": ["highest collision sport load", "live work substitution", "collision pairings"],
        "reason": "Primary sport load outranks extra S&C when the two collide.",
    },
    {
        "rank": 4,
        "driver": "main_limiter",
        "scope": ["limiter profile", "weekly stress emphasis", "protect first", "cut first"],
        "reason": "The main limiter organizes emphasis once phase survival and safety are protected.",
    },
    {
        "rank": 5,
        "driver": "goal_emphasis",
        "scope": ["key goals", "phase objectives", "candidate pool bias"],
        "reason": "Goals shape what gets pushed only after survival, safety, sport load, and limiter needs are respected.",
    },
    {
        "rank": 6,
        "driver": "preferences_and_style_bias",
        "scope": ["training preference", "equipment preference", "flavor choices"],
        "reason": "Preferences should only break ties after higher-priority planning rules agree.",
    },
]

def _build_athlete_model(
    *,
    training_context: TrainingContext,
    sport: str,
    record: str,
    rounds_format: str,
    camp_length_weeks: int,
    short_notice: bool,
) -> dict:
    return {
        "sport": sport,
        "status": training_context.status,
        "record": record,
        "rounds_format": rounds_format,
        "camp_length_weeks": camp_length_weeks,
        "days_until_fight": training_context.days_until_fight,
        "fatigue": training_context.fatigue,
        "age": training_context.age,
        "weight_cut_risk": training_context.weight_cut_risk,
        "weight_cut_pct": training_context.weight_cut_pct,
        "technical_styles": training_context.style_technical,
        "tactical_styles": training_context.style_tactical,
        "weaknesses": training_context.weaknesses,
        "key_goals": training_context.key_goals,
        "mental_blocks": _clean_list(training_context.mental_block),
        "equipment": training_context.equipment,
        "training_days": training_context.training_days,
        "training_preference": training_context.training_preference,
        "injuries": training_context.injuries,
        "short_notice": short_notice,
        "readiness_flags": _derive_readiness_flags(
            fatigue=training_context.fatigue,
            weight_cut_risk=training_context.weight_cut_risk,
            weight_cut_pct=training_context.weight_cut_pct,
            injuries=training_context.injuries,
            short_notice=short_notice,
            days_until_fight=training_context.days_until_fight,
        ),
    }


def _build_phase_selection_guardrails(phase: str, training_context: TrainingContext) -> dict:
    guardrails = dict(PHASE_SELECTION_GUARDRAILS.get(phase, {}))
    guardrails["conditioning_minimums"] = dict(guardrails.get("conditioning_minimums", {}))
    guardrails["must_keep_if_present"] = list(guardrails.get("must_keep_if_present", []))
    guardrails["conditioning_drop_order_if_thin"] = list(guardrails.get("conditioning_drop_order_if_thin", []))
    guardrails["notes"] = list(guardrails.get("notes", []))
    guardrails["must_keep_rehab_if_present"] = bool(training_context.injuries)
    if training_context.weight_cut_risk and phase == "TAPER":
        guardrails["conditioning_drop_order_if_thin"] = _dedupe_preserve_order(
            ["glycolytic"] + guardrails.get("conditioning_drop_order_if_thin", [])
        )
        guardrails["notes"].append("During active weight cut, treat glycolytic work as optional unless it is the only compliant fight-specific slot left.")
    return guardrails


def _priority_value(priority: str) -> int:
    return {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(priority, 1)


def _downgrade_priority(priority: str) -> str:
    order = ["critical", "high", "medium", "low"]
    if priority not in order:
        return "medium"
    idx = order.index(priority)
    return order[min(idx + 1, len(order) - 1)]


def _strength_slot_priority(phase: str, role: str, idx: int) -> str:
    if idx == 1:
        return "critical"
    if role in {"neck", "core"}:
        return "high"
    if phase == "TAPER" and idx >= 3:
        return "low"
    return "high" if idx == 2 else "medium"


def _conditioning_slot_priority(phase: str, system: str, idx: int) -> str:
    base = PHASE_CONDITIONING_PRIORITY.get(phase, {}).get(system, "medium")
    return base if idx == 1 else _downgrade_priority(base)


def _build_phase_briefs(training_context: TrainingContext, phase_weeks: dict) -> dict[str, dict]:
    briefs: dict[str, dict] = {}
    for phase in ("GPP", "SPP", "TAPER"):
        if phase_weeks.get(phase, 0) <= 0 and phase_weeks.get("days", {}).get(phase, 0) < 1:
            continue
        session_counts = allocate_sessions(training_context.training_frequency, phase)
        risk_flags: list[str] = []
        if training_context.injuries:
            risk_flags.append("respect injury guardrails")
        if training_context.weight_cut_risk:
            risk_flags.append("manage cut stress")
        if training_context.fatigue in {"moderate", "high"}:
            risk_flags.append("manage accumulated fatigue")
        briefs[phase] = {
            "objective": PHASE_OBJECTIVES.get(phase, ""),
            "emphasize": PHASE_EMPHASIS.get(phase, []),
            "deprioritize": PHASE_DEPRIORITIZE.get(phase, []),
            "risk_flags": _dedupe_preserve_order(risk_flags),
            "session_counts": session_counts,
            "selection_guardrails": _build_phase_selection_guardrails(phase, training_context),
            "weeks": phase_weeks.get(phase, 0),
            "days": phase_weeks.get("days", {}).get(phase, 0),
        }
    return briefs



def _derive_athlete_archetype(athlete_model: dict) -> dict:
    technical_styles = _clean_list(athlete_model.get("technical_styles", []))
    tactical_styles = _clean_list(athlete_model.get("tactical_styles", []))
    style_identity = _dedupe_preserve_order(technical_styles + tactical_styles) or ["generalist"]

    readiness = "stable"
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    if readiness_flags & {"fight_week", "aggressive_weight_cut", "high_fatigue"}:
        readiness = "fragile"
    elif readiness_flags & {"moderate_fatigue", "active_weight_cut", "injury_management", "short_notice"}:
        readiness = "managed"

    return {
        "style_identity": style_identity,
        "training_preference": athlete_model.get("training_preference") or "balanced",
        "experience_band": athlete_model.get("status") or "unspecified",
        "readiness_state": readiness,
        "equipment_profile": _clean_list(athlete_model.get("equipment", [])),
    }


def _derive_main_limiter(athlete_model: dict) -> str:
    weaknesses = _clean_list(athlete_model.get("weaknesses", []))
    goals = _clean_list(athlete_model.get("key_goals", []))
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))

    if weaknesses:
        return f"Primary limiter is {weaknesses[0].replace('_', ' ')}."
    if "conditioning" in goals:
        return "Primary limiter is fight conditioning repeatability."
    if "power" in goals:
        return "Primary limiter is power expression under fight fatigue."
    if readiness_flags & {"moderate_fatigue", "high_fatigue"} or fatigue in {"moderate", "high"}:
        return "Primary limiter is accumulated fatigue management."
    return "Primary limiter is general fight-readiness capacity."


def _derive_main_risks(athlete_model: dict, restrictions: list[dict]) -> list[str]:
    risks: list[str] = []
    injuries = _clean_list(athlete_model.get("injuries", []))
    if injuries:
        risks.append("Injury management must constrain exercise choice and loading.")
    if athlete_model.get("weight_cut_risk"):
        pct = athlete_model.get("weight_cut_pct") or 0.0
        risks.append(f"Weight cut stress is active ({pct:.1f}% body mass target), so soreness and dehydration costs matter.")
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    if fatigue in {"moderate", "high"}:
        risks.append(f"Current fatigue is {fatigue}, so stacking hard sessions is a risk.")
    if athlete_model.get("short_notice"):
        risks.append("Short-notice timeline limits how much new capacity can be built.")
    if restrictions:
        risks.append("Restrictions require aggressive pattern filtering, including mechanical equivalents.")
    return risks or ["No exceptional risk flags beyond normal camp management."]


_LIMITER_PROFILES = {
    "coordination": {
        "label": "coordination",
        "organising_principle": "timing, rhythm, body control, and transfer under fatigue",
        "drill_emphasis": [
            "timing and rhythm before fatigue",
            "body control and transfer quality",
            "simple drills repeated under controlled fatigue",
        ],
        "protect_first": "timing quality, rhythm, and body control before extra fatigue work",
        "cut_first": "fatigue-heavy glycolytic work and attractive explosive extras",
        "boxing_load_rule": "If boxing timing degrades, cut conditioning density before skill-quality work.",
        "sparring_collision_rule": "Do not pair hard sparring with hard glycolytic conditioning; if sparring is the main collision, reduce same-day or next-day S&C volume by 30% and cut accessories first.",
        "conditioning_sequence": {
            "GPP": ["aerobic", "alactic", "glycolytic"],
            "SPP": ["alactic", "aerobic", "glycolytic"],
            "TAPER": ["alactic", "aerobic", "glycolytic"],
        },
    },
    "aerobic_repeatability": {
        "label": "aerobic repeatability",
        "organising_principle": "repeatability, density control, recovery spacing, and fatigue tolerance",
        "drill_emphasis": [
            "repeatability under controlled density",
            "recovery spacing between hard exposures",
            "low-damage conditioning progression before extra lifting",
        ],
        "protect_first": "repeatability work and recovery spacing before extra strength volume",
        "cut_first": "accessory strength volume and non-essential power work",
        "boxing_load_rule": "If there is no sparring this week, add fight-pace rounds before extra lifting.",
        "sparring_collision_rule": "Never pair hard glycolytic conditioning with hard sparring; let sparring own the fight-pace slot when it is already hard.",
        "conditioning_sequence": {
            "GPP": ["aerobic", "glycolytic", "alactic"],
            "SPP": ["aerobic", "glycolytic", "alactic"],
            "TAPER": ["aerobic", "alactic", "glycolytic"],
        },
    },
    "tissue_state": {
        "label": "tissue state",
        "organising_principle": "protection, conservative loading, reduced ballistic bias, and rebuild sequencing",
        "drill_emphasis": [
            "isometrics and carries before ballistics",
            "controlled trunk work and tissue calm",
            "low-impact repeatability before hard output",
        ],
        "protect_first": "next-day function, symptom stability, and conservative loading",
        "cut_first": "ballistic work, reactive contacts, and cool explosive drills",
        "boxing_load_rule": "If symptoms spike after boxing, the next day becomes recovery plus rehab only.",
        "sparring_collision_rule": "When sparring creates a collision with tissue state, protect the athlete first and remove accessory or ballistic S&C before boxing quality work.",
        "conditioning_sequence": {
            "GPP": ["aerobic", "alactic", "glycolytic"],
            "SPP": ["aerobic", "alactic", "glycolytic"],
            "TAPER": ["aerobic", "alactic", "glycolytic"],
        },
    },
    "sharpness_under_fatigue": {
        "label": "sharpness under fatigue",
        "organising_principle": "freshness protection, quality preservation, and clear cut-first hierarchy",
        "drill_emphasis": [
            "high-quality speed and sharpness work",
            "low-soreness neural priming",
            "fatigue work only when it does not flatten quality",
        ],
        "protect_first": "freshness, speed, and technical quality before extra volume",
        "cut_first": "glycolytic density and accessory strength volume",
        "boxing_load_rule": "If boxing quality is flat, preserve sharpness and drop fatigue work.",
        "sparring_collision_rule": "Hard sparring or boxing flatness overrides extra fatigue work; keep sharpness and cut accessory or glycolytic work first.",
        "conditioning_sequence": {
            "GPP": ["alactic", "aerobic", "glycolytic"],
            "SPP": ["alactic", "glycolytic", "aerobic"],
            "TAPER": ["alactic", "aerobic", "glycolytic"],
        },
    },
    "boxing_quality_under_load": {
        "label": "boxing quality under load",
        "organising_principle": "boxing quality under load with S&C staying secondary to sport output",
        "drill_emphasis": [
            "boxing transfer and quality under fatigue",
            "sport-load interaction before accessory work",
            "fight-pace support only when boxing stays crisp",
        ],
        "protect_first": "boxing quality and sparring freshness before extra lifting",
        "cut_first": "accessory strength and generic conditioning before boxing-support work",
        "boxing_load_rule": "If there is no sparring this week, add fight-pace rounds before extra lifting.",
        "sparring_collision_rule": "Hard sparring owns the main combat stress slot; never pair it with hard glycolytic conditioning and cut S&C accessories first.",
        "conditioning_sequence": {
            "GPP": ["aerobic", "alactic", "glycolytic"],
            "SPP": ["alactic", "glycolytic", "aerobic"],
            "TAPER": ["alactic", "aerobic", "glycolytic"],
        },
    },
    "general_fight_readiness": {
        "label": "general fight readiness",
        "organising_principle": "balanced development with clear fatigue control and phase protection",
        "drill_emphasis": [
            "phase-priority work first",
            "low-damage support work before extras",
            "preserve fight-specific quality under fatigue",
        ],
        "protect_first": "phase-critical work before accessories",
        "cut_first": "non-essential accessories and redundant fatigue work",
        "boxing_load_rule": "Let boxing quality and sparring output override extra S&C when collisions appear.",
        "sparring_collision_rule": "If hard sparring is present, reduce same-day or next-day S&C by 30% and cut accessories first.",
        "conditioning_sequence": {
            "GPP": ["aerobic", "glycolytic", "alactic"],
            "SPP": ["glycolytic", "alactic", "aerobic"],
            "TAPER": ["alactic", "aerobic", "glycolytic"],
        },
    },
}


def _normalize_limiter_tokens(values: list[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        token = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
        if token:
            tokens.add(token)
    return tokens



def _primary_limiter_key(athlete_model: dict, restrictions: list[dict]) -> str:
    weakness_tokens = _normalize_limiter_tokens(_clean_list(athlete_model.get("weaknesses", [])))
    goal_tokens = _normalize_limiter_tokens(_clean_list(athlete_model.get("key_goals", [])))
    style_tokens = _normalize_limiter_tokens(
        _clean_list(athlete_model.get("technical_styles", [])) + _clean_list(athlete_model.get("tactical_styles", []))
    )
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    days_until_fight = athlete_model.get("days_until_fight")

    if weakness_tokens & {"coordination", "coordination_proprioception", "proprioception", "balance", "timing", "rhythm"}:
        return "coordination"
    if weakness_tokens & {"conditioning", "aerobic", "endurance", "gas_tank", "recovery"}:
        return "aerobic_repeatability"
    if weakness_tokens & {"sharpness", "speed_reaction", "cns_fatigue", "speed", "reaction"}:
        return "sharpness_under_fatigue"
    if weakness_tokens & {"boxing", "striking", "skill_refinement"}:
        return "boxing_quality_under_load"
    if weakness_tokens & {"shoulder", "shoulders", "knee", "knees", "neck", "mobility", "stiffness"}:
        return "tissue_state"

    if athlete_model.get("injuries") or restrictions:
        return "tissue_state"
    if goal_tokens & {"conditioning", "conditioning_endurance", "endurance"}:
        return "aerobic_repeatability"
    if style_tokens & {"boxing", "boxer"} and goal_tokens & {"skill_refinement", "striking"}:
        return "boxing_quality_under_load"
    if readiness_flags & {"moderate_fatigue", "high_fatigue", "fight_week"}:
        return "sharpness_under_fatigue"
    if isinstance(days_until_fight, int) and days_until_fight <= 14:
        return "sharpness_under_fatigue"
    return "general_fight_readiness"



def _build_limiter_profile(athlete_model: dict, restrictions: list[dict]) -> dict:
    key = _primary_limiter_key(athlete_model, restrictions)
    template = _LIMITER_PROFILES.get(key, _LIMITER_PROFILES["general_fight_readiness"])
    return {
        "key": key,
        "label": template["label"],
        "organising_principle": template["organising_principle"],
        "drill_emphasis": list(template["drill_emphasis"]),
        "protect_first": template["protect_first"],
        "cut_first": template["cut_first"],
        "boxing_load_rule": template["boxing_load_rule"],
        "sparring_collision_rule": template["sparring_collision_rule"],
        "conditioning_sequence": {
            phase: list(sequence)
            for phase, sequence in template["conditioning_sequence"].items()
        },
    }



_SPORT_LOAD_PROFILES = {
    "boxing": {
        "label": "boxing",
        "highest_collision_load": "hard sparring and high-output pad or bag rounds",
        "primary_live_loads": ["hard sparring", "technical sparring", "pad rounds", "bag rounds"],
        "collision_rules": [
            "Never pair hard sparring with hard glycolytic conditioning.",
            "If boxing quality is flat, cut accessory strength or conditioning volume before technical work.",
        ],
        "cut_first_when_sport_load_spikes": "accessory strength volume and optional conditioning density",
        "replace_missing_live_load": "If no sparring is available that week, add fight-pace pad or bag rounds before extra lifting.",
        "quality_override": "If boxing quality is flat, preserve sharpness and drop fatigue work.",
    },
    "kickboxing_muay_thai": {
        "label": "kickboxing / muay thai",
        "highest_collision_load": "hard sparring, pad rounds, and clinch volume",
        "primary_live_loads": ["hard sparring", "pad rounds", "clinch rounds", "bag rounds"],
        "collision_rules": [
            "Never pair hard sparring or high-output clinch work with hard glycolytic conditioning.",
            "If pad sharpness or clinch quality falls, cut S&C accessories before adding more fatigue.",
        ],
        "cut_first_when_sport_load_spikes": "optional strength accessories and non-essential conditioning density",
        "replace_missing_live_load": "If no sparring happens that week, add fight-pace pad or clinch rounds before extra lifting.",
        "quality_override": "If striking sharpness or clinch quality drops, keep technical quality and remove extra fatigue first.",
    },
    "mma": {
        "label": "mma",
        "highest_collision_load": "hard MMA sparring plus live wrestling or wall-work rounds",
        "primary_live_loads": ["hard MMA sparring", "live wrestling", "wall work", "grappling rounds"],
        "collision_rules": [
            "Never pair hard live wrestling or hard MMA sparring with hard glycolytic conditioning.",
            "If live MMA output is flat, cut accessory strength or optional conditioning before fight-specific work.",
        ],
        "cut_first_when_sport_load_spikes": "accessory strength volume and redundant conditioning density",
        "replace_missing_live_load": "If live rounds are missing that week, add fight-pace positional or cage-wall rounds before extra lifting.",
        "quality_override": "Let live MMA quality override extra S&C when collisions appear.",
    },
    "wrestling": {
        "label": "wrestling",
        "highest_collision_load": "live goes, takedown exchanges, and high-output mat returns",
        "primary_live_loads": ["live goes", "takedown entries", "mat returns", "hand fighting"],
        "collision_rules": [
            "Do not pair hard live goes with hard glycolytic conditioning.",
            "If hand fighting or takedown speed falls, cut accessory work before adding more fatigue.",
        ],
        "cut_first_when_sport_load_spikes": "optional strength accessories and non-essential conditioning density",
        "replace_missing_live_load": "If live goes are missing that week, add short positional goes or takedown chains before extra lifting.",
        "quality_override": "Preserve takedown speed and mat quality before extra fatigue work.",
    },
    "bjj": {
        "label": "bjj",
        "highest_collision_load": "hard rolling, positional rounds, and grip-heavy live work",
        "primary_live_loads": ["hard rolling", "positional rounds", "grip fighting", "scramble rounds"],
        "collision_rules": [
            "Do not pair hard rolling with hard glycolytic conditioning.",
            "If positional quality or decision-making drops, cut accessory S&C before adding more fatigue.",
        ],
        "cut_first_when_sport_load_spikes": "optional strength volume and non-essential conditioning density",
        "replace_missing_live_load": "If hard rolling is absent that week, add positional rounds or grip-focused circuits before extra lifting.",
        "quality_override": "Preserve rolling quality and decision-making before extra fatigue work.",
    },
    "general_combat": {
        "label": "general combat sport",
        "highest_collision_load": "hard live rounds and sparring",
        "primary_live_loads": ["hard sparring", "live rounds", "fight-pace rounds"],
        "collision_rules": [
            "Do not pair the hardest live rounds with hard glycolytic conditioning.",
            "If sport quality drops, cut accessory work before technical work.",
        ],
        "cut_first_when_sport_load_spikes": "optional accessories and redundant conditioning density",
        "replace_missing_live_load": "If live rounds are absent that week, add fight-pace technical rounds before extra lifting.",
        "quality_override": "Let sport quality override extra S&C when collisions appear.",
    },
}


def _join_rule_parts(*parts: str) -> str:
    cleaned = _dedupe_preserve_order([str(part).strip() for part in parts if str(part).strip()])
    return " ".join(cleaned)



def _primary_sport_load_key(athlete_model: dict) -> str:
    sport_tokens = _normalize_limiter_tokens(_clean_list(athlete_model.get("sport")))
    style_tokens = _normalize_limiter_tokens(
        _clean_list(athlete_model.get("technical_styles", [])) + _clean_list(athlete_model.get("tactical_styles", []))
    )
    combined = sport_tokens | style_tokens

    if combined & {"bjj", "jiu_jitsu", "jits", "grappling"}:
        return "bjj"
    if combined & {"wrestler", "wrestling", "freestyle", "folkstyle", "greco"}:
        return "wrestling"
    if combined & {"muay_thai", "kickboxer", "kickboxing", "karate"}:
        return "kickboxing_muay_thai"
    if combined & {"boxing", "boxer"}:
        return "boxing"
    if combined & {"mma", "mixed_martial_arts", "cage_wrestling", "sambo", "judo"}:
        return "mma"
    return "general_combat"



def _build_sport_load_profile(athlete_model: dict) -> dict:
    key = _primary_sport_load_key(athlete_model)
    template = _SPORT_LOAD_PROFILES.get(key, _SPORT_LOAD_PROFILES["general_combat"])
    return {
        "key": key,
        "label": template["label"],
        "highest_collision_load": template["highest_collision_load"],
        "primary_live_loads": list(template["primary_live_loads"]),
        "collision_rules": list(template["collision_rules"]),
        "cut_first_when_sport_load_spikes": template["cut_first_when_sport_load_spikes"],
        "replace_missing_live_load": template["replace_missing_live_load"],
        "quality_override": template["quality_override"],
    }



def _build_weekly_stress_map(
    athlete_model: dict,
    phase_briefs: dict[str, dict],
    limiter_profile: dict,
    sport_load_profile: dict,
) -> dict[str, dict]:
    stress_map: dict[str, dict] = {}
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    short_notice = bool(athlete_model.get("short_notice"))
    weight_cut_risk = bool(athlete_model.get("weight_cut_risk"))

    for phase in phase_briefs:
        if phase == "GPP":
            highest_neural_day = "Place one highest neural day after the easiest day so the limiter quality stays crisp before volume accumulates."
            highest_glycolytic_day = "Keep one density-focused day only, and never let it sit beside hard sparring."
            lowest_load_day = "Use one lowest-load day for recovery, rehab, and easy aerobic support only."
        elif phase == "SPP":
            highest_neural_day = "Anchor one highest neural day around sport speed or power transfer and keep it away from hard sparring collisions."
            highest_glycolytic_day = "Use one highest glycolytic day as the main fight-pace stressor unless hard sparring already occupies that slot."
            lowest_load_day = "Keep one lowest-load day for recovery, tissue care, and limiter-preserving support work."
        else:
            highest_neural_day = "Use one highest neural day as a sharpness primer, not as a fatigue builder."
            highest_glycolytic_day = "Only keep a light fight-pace touch; drop glycolytic density first if freshness or boxing quality falls."
            lowest_load_day = "Make one day clearly lowest-load with recovery, rehab, and freshness protection only."

        protect_first = limiter_profile["protect_first"]
        cut_first = limiter_profile["cut_first"]
        if fatigue in {"moderate", "high"}:
            protect_first = f"Because fatigue is {fatigue}, protect the limiter quality and freshness before adding extra work."
        if short_notice and phase in {"SPP", "TAPER"}:
            cut_first = f"Because this is short notice, cut {limiter_profile['cut_first']} before touching phase-critical sharpness or boxing quality."
        if weight_cut_risk and phase == "TAPER":
            cut_first = f"{cut_first}; during the cut, remove glycolytic density before alactic sharpness or rehab support."
        cut_first = _join_rule_parts(
            cut_first,
            f"When sport load spikes, cut {sport_load_profile['cut_first_when_sport_load_spikes']} first.",
        )

        stress_map[phase] = {
            "organising_limiter": limiter_profile["label"],
            "highest_neural_day": highest_neural_day,
            "highest_glycolytic_day": highest_glycolytic_day,
            "lowest_load_day": lowest_load_day,
            "conditioning_sequence": list(limiter_profile["conditioning_sequence"].get(phase, [])),
            "drill_emphasis": list(limiter_profile["drill_emphasis"]),
            "protect_first": protect_first,
            "cut_first_when_collisions_rise": cut_first,
            "sparring_collision_rule": limiter_profile["sparring_collision_rule"],
            "sport_load_interaction": _join_rule_parts(
                limiter_profile["boxing_load_rule"],
                sport_load_profile["quality_override"],
            ),
            "highest_collision_sport_load": sport_load_profile["highest_collision_load"],
            "sport_load_collision_rules": list(sport_load_profile["collision_rules"]),
            "replace_missing_live_load": sport_load_profile["replace_missing_live_load"],
        }
    return stress_map

def _derive_global_priorities(
    athlete_model: dict,
    phase_briefs: dict[str, dict],
    candidate_pools: dict[str, dict],
) -> dict[str, list[str]]:
    preserve: list[str] = []
    push: list[str] = []
    avoid: list[str] = []

    injuries = _clean_list(athlete_model.get("injuries", []))
    goals = _clean_list(athlete_model.get("key_goals", []))

    if injuries:
        preserve.append("Keep rehab continuity and remove only clearly conflicting work.")
        avoid.append("Do not keep drills that mechanically overlap the injured pattern just because they sound different.")
    if athlete_model.get("weight_cut_risk"):
        preserve.append("Keep low-damage conditioning options during cut stress.")
        avoid.append("Avoid unnecessary soreness-heavy conditioning or accessory volume.")
    if "conditioning" in goals:
        push.append("Prioritize conditioning slots that match the phase objective before extra accessories.")
    if "power" in goals:
        push.append("Preserve explosive and alactic work if compliant options remain.")

    for phase, brief in phase_briefs.items():
        guardrails = brief.get("selection_guardrails", {})
        for item in guardrails.get("must_keep_if_present", []):
            label = str(item).replace("_", " ")
            preserve.append(f"In {phase}, keep {label} work if a compliant version exists.")
        for note in guardrails.get("notes", []):
            avoid.append(str(note))

    conditioning_roles = {
        slot.get("role")
        for pool in candidate_pools.values()
        for slot in pool.get("conditioning_slots", [])
        if slot.get("role")
    }
    if "aerobic" in conditioning_roles and "conditioning" in goals:
        push.append("Use aerobic work to support recovery and repeatability, not just to add volume.")
    if "alactic" in conditioning_roles:
        push.append("Keep at least one neural-speed option when the phase or taper calls for sharpness.")

    return {
        "preserve": _dedupe_preserve_order(preserve) or ["Preserve the main phase objectives and any active rehab work."],
        "push": _dedupe_preserve_order(push) or ["Push the highest-priority phase qualities first."],
        "avoid": _dedupe_preserve_order(avoid) or ["Avoid changes that break the phase intent or restriction logic."],
    }


def _build_phase_strategy(phase_briefs: dict[str, dict], candidate_pools: dict[str, dict]) -> dict[str, dict]:
    strategy: dict[str, dict] = {}
    for phase, brief in phase_briefs.items():
        pool = candidate_pools.get(phase, {})
        strategy[phase] = {
            "objective": brief.get("objective", ""),
            "build": _clean_list(brief.get("emphasize", [])),
            "protect": _clean_list(brief.get("risk_flags", [])),
            "deprioritize": _clean_list(brief.get("deprioritize", [])),
            "must_keep": _clean_list((brief.get("selection_guardrails") or {}).get("must_keep_if_present", [])),
            "drop_order_if_thin": _clean_list((brief.get("selection_guardrails") or {}).get("conditioning_drop_order_if_thin", [])),
            "slot_counts": {
                "strength": len(pool.get("strength_slots", [])),
                "conditioning": len(pool.get("conditioning_slots", [])),
                "rehab": len(pool.get("rehab_slots", [])),
            },
        }
    return strategy


def build_planning_brief(
    *,
    athlete_model: dict,
    restrictions: list[dict],
    phase_briefs: dict[str, dict],
    candidate_pools: dict[str, dict],
    omission_ledger: dict[str, dict],
    rewrite_guidance: dict,
) -> dict:
    limiter_profile = _build_limiter_profile(athlete_model, restrictions)
    sport_load_profile = _build_sport_load_profile(athlete_model)
    weekly_stress_map = _build_weekly_stress_map(
        athlete_model,
        phase_briefs,
        limiter_profile,
        sport_load_profile,
    )
    return {
        "schema_version": "planning_brief.v1",
        "generator_mode": "deterministic_planner_plus_ai_finalizer",
        "athlete_snapshot": athlete_model,
        "fight_demands": {
            "sport": athlete_model.get("sport"),
            "status": athlete_model.get("status"),
            "rounds_format": athlete_model.get("rounds_format"),
            "camp_length_weeks": athlete_model.get("camp_length_weeks"),
            "days_until_fight": athlete_model.get("days_until_fight"),
            "short_notice": athlete_model.get("short_notice"),
        },
        "archetype_summary": _derive_athlete_archetype(athlete_model),
        "main_limiter": _derive_main_limiter(athlete_model),
        "limiter_profile": limiter_profile,
        "sport_load_profile": sport_load_profile,
        "decision_hierarchy": PLANNING_DECISION_HIERARCHY,
        "main_risks": _derive_main_risks(athlete_model, restrictions),
        "global_priorities": _derive_global_priorities(athlete_model, phase_briefs, candidate_pools),
        "phase_strategy": _build_phase_strategy(phase_briefs, candidate_pools),
        "weekly_stress_map": weekly_stress_map,
        "restrictions": restrictions,
        "candidate_pools": candidate_pools,
        "omission_ledger": omission_ledger,
        "decision_rules": rewrite_guidance,
    }

def _serialize_strength_option(exercise: dict, why: str) -> dict:
    movement = str(exercise.get("movement", "")).strip().lower().replace(" ", "_")
    movement_patterns = [movement] if movement else []
    movement_patterns.extend(_clean_list(exercise.get("tags", [])))
    return {
        "name": exercise.get("name", "Unnamed"),
        "source": "exercise_bank",
        "movement_patterns": _dedupe_preserve_order(movement_patterns),
        "restriction_tags": _extract_restriction_tags(exercise),
        "mechanical_risk_tags": _extract_mechanical_risk_tags(exercise),
        "prescription": exercise.get("prescription") or exercise.get("method") or "",
        "why": why or "balanced selection",
    }


def _serialize_conditioning_option(drill: dict, system: str, why: str) -> dict:
    tags = _clean_list(drill.get("tags", []))
    return {
        "name": drill.get("name", "Unnamed"),
        "source": "conditioning_bank",
        "movement_patterns": _dedupe_preserve_order([system] + tags),
        "restriction_tags": _extract_restriction_tags(drill),
        "mechanical_risk_tags": _extract_mechanical_risk_tags(drill),
        "prescription": " | ".join(
            part for part in [drill.get("timing"), drill.get("rest"), drill.get("load")] if part
        ),
        "why": why or "balanced selection",
    }


def _serialize_rehab_option(prescription: str, *, role: str, source: str, why: str) -> dict:
    name = re.split(r"\s+(?:[\u2013-]|\u00e2\u20ac\u201c)\s+", prescription, maxsplit=1)[0].strip()
    return {
        "name": name or "Rehab Drill",
        "source": source,
        "movement_patterns": [role],
        "restriction_tags": ["rehab", role],
        "mechanical_risk_tags": ["rehab", role],
        "prescription": prescription,
        "why": why,
    }


def _build_strength_alternates(
    strength_block: dict,
    *,
    role: str,
    selected_names: set[str],
    current_name: str,
) -> list[dict]:
    alternates: list[dict] = []
    seen: set[str] = set()
    for candidate in (strength_block.get("candidate_reservoir") or {}).get(role, []):
        exercise = candidate.get("exercise", {})
        name = exercise.get("name")
        if not name or name == current_name or name in selected_names or name in seen:
            continue
        alternates.append(
            _serialize_strength_option(
                exercise,
                candidate.get("explanation", "balanced selection"),
            )
        )
        seen.add(name)
        if len(alternates) >= 2:
            break
    return alternates


def _build_conditioning_alternates(
    phase_block: dict,
    *,
    system: str,
    selected_names: set[str],
    current_name: str,
) -> list[dict]:
    alternates: list[dict] = []
    seen: set[str] = set()
    for candidate in (phase_block.get("candidate_reservoir") or {}).get(system, []):
        drill = candidate.get("drill", {})
        name = drill.get("name")
        if not name or name == current_name or name in selected_names or name in seen:
            continue
        alternates.append(
            _serialize_conditioning_option(
                drill,
                system,
                candidate.get("explanation", "balanced selection"),
            )
        )
        seen.add(name)
        if len(alternates) >= 2:
            break
    return alternates


def _parse_rehab_groups(rehab_block: str) -> list[dict]:
    groups: list[dict] = []
    current: dict | None = None

    for raw_line in rehab_block.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        header_match = re.match(r"^-\s+([^()]+?)\s*\(([^)]+)\):\s*$", stripped)
        if header_match:
            current = {
                "location": header_match.group(1).strip(),
                "injury_type": header_match.group(2).strip(),
                "drills": [],
            }
            groups.append(current)
            continue
        bullet_match = re.match(r"^(?:[-*]|[\u2022]|\u00e2\u20ac\u00a2)\s+(.+)$", stripped)
        is_indented = raw_line[:1].isspace()
        if current is not None and bullet_match and (is_indented or stripped.startswith(("\u00e2\u20ac\u00a2", "\u2022", "*"))):
            current["drills"].append(bullet_match.group(1).strip())

    return groups


def _build_strength_slots(strength_block: dict | None, phase: str) -> list[dict]:
    if not strength_block:
        return []
    reason_lookup = {
        entry.get("name"): entry
        for entry in strength_block.get("why_log", [])
        if entry.get("name")
    }
    selected_names = {
        exercise.get("name")
        for exercise in strength_block.get("exercises", [])
        if exercise.get("name")
    }
    slots: list[dict] = []
    for idx, exercise in enumerate(strength_block.get("exercises", []), start=1):
        name = exercise.get("name")
        if not name:
            continue
        reasons = reason_lookup.get(name, {})
        movement = str(exercise.get("movement", "")).strip().lower().replace(" ", "_")
        role = movement or "strength_support"
        slots.append(
            {
                "slot_id": f"{phase.lower()}_strength_{idx}_{_slugify(name)}",
                "role": role,
                "purpose": reasons.get("explanation", "balanced selection"),
                "selected": _serialize_strength_option(
                    exercise,
                    reasons.get("explanation", "balanced selection"),
                ),
                "alternates": _build_strength_alternates(
                    strength_block,
                    role=role,
                    selected_names=selected_names,
                    current_name=name,
                ),
                "replace_with_same_role": True,
                "priority": _strength_slot_priority(phase, role, idx),
            }
        )
    return slots


def _build_conditioning_slots(phase_block: dict | None, phase: str) -> list[dict]:
    if not phase_block:
        return []
    reason_lookup = {
        entry.get("name"): entry
        for entry in phase_block.get("why_log", [])
        if entry.get("name")
    }
    selected_names = {
        drill.get("name")
        for drills in (phase_block.get("grouped_drills") or {}).values()
        for drill in drills
        if drill.get("name")
    }
    slots: list[dict] = []
    for system, drills in (phase_block.get("grouped_drills") or {}).items():
        for idx, drill in enumerate(drills, start=1):
            name = drill.get("name")
            if not name:
                continue
            reasons = reason_lookup.get(name, {})
            slots.append(
                {
                    "slot_id": f"{phase.lower()}_{system}_{idx}_{_slugify(name)}",
                    "role": system,
                    "purpose": CONDITIONING_ROLE_PURPOSES.get(system, reasons.get("explanation", "balanced selection")),
                    "selected": _serialize_conditioning_option(
                        drill,
                        system,
                        reasons.get("explanation", "balanced selection"),
                    ),
                    "alternates": _build_conditioning_alternates(
                        phase_block,
                        system=system,
                        selected_names=selected_names,
                        current_name=name,
                    ),
                    "replace_with_same_role": True,
                    "priority": _conditioning_slot_priority(phase, system, idx),
                }
            )
    return slots


def _build_rehab_slots(rehab_block: str, phase: str) -> list[dict]:
    if not rehab_block or rehab_block.strip().startswith("**Red Flag Detected**"):
        return []
    slots: list[dict] = []
    for group in _parse_rehab_groups(rehab_block):
        location = group.get("location", "Unspecified")
        injury_type = group.get("injury_type", "unspecified")
        role = f"rehab_{_slugify(location)}_{_slugify(injury_type)}"
        selected_lines = [line for line in group.get("drills", []) if line]
        selected_set = set(selected_lines)
        rehab_options = _rehab_drills_for_phase(
            injury_type.lower(),
            location.lower().replace(" ", "_"),
            phase,
            limit=6,
        )
        why = f"phase-specific rehab support for {location.lower()} {injury_type.lower()}"
        for idx, line in enumerate(selected_lines, start=1):
            alternates: list[dict] = []
            for option in rehab_options:
                if option == line or option in selected_set:
                    continue
                alternates.append(
                    _serialize_rehab_option(
                        option,
                        role=role,
                        source="rehab_bank",
                        why=why,
                    )
                )
                if len(alternates) >= 2:
                    break
            slots.append(
                {
                    "slot_id": f"{phase.lower()}_{role}_{idx}_{_slugify(line)}",
                    "role": role,
                    "purpose": why,
                    "selected": _serialize_rehab_option(
                        line,
                        role=role,
                        source="rehab_block",
                        why=why,
                    ),
                    "alternates": alternates,
                    "replace_with_same_role": True,
                    "priority": "critical" if idx == 1 else "high",
                }
            )
    return slots

def _build_omission_ledger(
    *,
    strength_blocks: dict[str, dict | None],
    conditioning_blocks: dict[str, dict],
    phase_weeks: dict,
) -> dict[str, dict]:
    ledger: dict[str, dict] = {}
    for phase in ("GPP", "SPP", "TAPER"):
        if phase_weeks.get(phase, 0) <= 0 and phase_weeks.get("days", {}).get(phase, 0) < 1:
            continue
        entries: dict[str, list[dict]] = {}
        strength_block = strength_blocks.get(phase)
        if not strength_block or not strength_block.get("exercises"):
            entries["strength"] = [
                {
                    "reason": "no_strength_candidates",
                    "details": "No strength exercises remained in the final Stage 1 block.",
                }
            ]
        cond_block = conditioning_blocks.get(phase)
        missing_systems = (cond_block or {}).get("missing_systems", [])
        if missing_systems:
            entries["conditioning"] = [
                {
                    "reason": "missing_system",
                    "details": system_name,
                }
                for system_name in missing_systems
            ]
        if entries:
            ledger[phase] = entries
    return ledger


def build_stage2_payload(
    *,
    training_context: TrainingContext,
    mapped_format: str,
    record: str,
    rounds_format: str,
    camp_len: int,
    short_notice: bool,
    restrictions: list[dict],
    phase_weeks: dict,
    strength_blocks: dict[str, dict | None],
    conditioning_blocks: dict[str, dict],
    rehab_blocks: dict[str, str],
) -> dict:
    candidate_pools: dict[str, dict] = {}
    for phase in ("GPP", "SPP", "TAPER"):
        if phase_weeks.get(phase, 0) <= 0 and phase_weeks.get("days", {}).get(phase, 0) < 1:
            continue
        candidate_pools[phase] = {
            "strength_slots": _build_strength_slots(strength_blocks.get(phase), phase),
            "conditioning_slots": _build_conditioning_slots(conditioning_blocks.get(phase), phase),
            "rehab_slots": _build_rehab_slots(rehab_blocks.get(phase, ""), phase),
        }

    athlete_model = _build_athlete_model(
        training_context=training_context,
        sport=mapped_format,
        record=record,
        rounds_format=rounds_format,
        camp_length_weeks=camp_len,
        short_notice=short_notice,
    )
    serialized_restrictions = _serialize_restrictions(restrictions)
    phase_briefs = _build_phase_briefs(training_context, phase_weeks)
    omission_ledger = _build_omission_ledger(
        strength_blocks=strength_blocks,
        conditioning_blocks=conditioning_blocks,
        phase_weeks=phase_weeks,
    )
    rewrite_guidance = {
        "selection_rules": [
            "Prefer selected items first, then alternates in listed order.",
            "If a selected item is removed, replace only within the same slot when possible.",
            "Treat option mechanical_risk_tags plus restriction blocked_patterns/mechanical_equivalents as hard clues for mechanically equivalent matches.",
            "Do not invent new items when a slot becomes thin after filtering.",
        ],
        "writing_rules": [
            "Keep the final plan athlete-facing and clean.",
            "Do not mention excluded items.",
            "Preserve phase objectives when rewriting text.",
        ],
    }

    return {
        "schema_version": "stage2_payload.v1",
        "generator_mode": "restriction_aware_candidate_generator",
        "athlete_model": athlete_model,
        "restrictions": serialized_restrictions,
        "phase_briefs": phase_briefs,
        "candidate_pools": candidate_pools,
        "omission_ledger": omission_ledger,
        "rewrite_guidance": rewrite_guidance,
    }

STAGE2_FINALIZER_PROMPT = """You are Stage 2 (planner/finalizer). Input = PLANNING BRIEF + Stage 1 draft plan + athlete profile + restrictions + candidate pools.

SOURCE OF TRUTH:
1. Use the PLANNING BRIEF first for athlete intent, phase strategy, priorities, and risks.
2. Treat restrictions as hard constraints.
3. Treat candidate pools as the preferred exercise reservoir.
4. Treat the Stage 1 draft plan as raw material, not the final authority.

RULE 1 (hard filter): Remove or exclude any exercise, drill, or prescription that violates ANY restriction, including synonyms and mechanically equivalent patterns. Apply this to strength, conditioning, rehab, and any new item you consider. Do not soften a violating item into compliance; replace it or drop it.

RULE 2 (planning): Build the best final plan for this athlete using the planning brief. You may reorganize sessions, simplify sections, tighten phase focus, and improve sequencing, as long as the final plan remains consistent with the phase strategy and restrictions.

RULE 3 (selection): Prefer selected Stage 1 items first, then same-role alternates, then other compliant options from the candidate pools. Keep the highest-priority slots and preserve rehab and phase-critical systems when possible.

RULE 4 (invention): Prefer not to invent new exercises. Only introduce a new item if the existing material cannot produce a coherent, restriction-compliant plan, and only if the replacement is conservative, mechanically appropriate, and clearly aligned with the planning brief.

OUTPUT: Return a clean athlete-facing final plan that feels elite, personalized, and internally coherent. Preserve what is best from Stage 1, but rewrite weak structure, duplication, or sequencing when needed."""


def _json_block(value: dict | list) -> str:
    return "```json\n" + json.dumps(value, indent=2) + "\n```"


def build_stage2_handoff_text(
    *,
    stage2_payload: dict,
    plan_text: str,
    coach_notes: str = "",
    planning_brief: dict | None = None,
) -> str:
    sections = [
        STAGE2_FINALIZER_PROMPT.strip(),
        "PLANNING BRIEF\n" + _json_block(planning_brief or {}),
        "ATHLETE PROFILE\n" + _json_block(stage2_payload.get("athlete_model", {})),
        "RESTRICTIONS\n" + _json_block(stage2_payload.get("restrictions", [])),
        "PHASE BRIEFS\n" + _json_block(stage2_payload.get("phase_briefs", {})),
        "CANDIDATE POOLS\n" + _json_block(stage2_payload.get("candidate_pools", {})),
        "OMISSION LEDGER\n" + _json_block(stage2_payload.get("omission_ledger", {})),
        "REWRITE GUIDANCE\n" + _json_block(stage2_payload.get("rewrite_guidance", {})),
    ]
    cleaned_notes = (coach_notes or "").strip()
    if cleaned_notes:
        sections.append("COACH NOTES\n" + cleaned_notes)
    sections.append("STAGE 1 DRAFT PLAN\n" + (plan_text or "").strip())
    return "\n\n---\n\n".join(section for section in sections if section.strip())


