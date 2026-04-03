from __future__ import annotations

import json
import re
from typing import Any

from .normalization import normalize_lower_text
from .restriction_parsing import CANONICAL_RESTRICTIONS
from .rehab_protocols import _rehab_drills_for_phase, classify_drill_function, _FUNCTION_LABELS
from .sparring_dose_planner import compute_hard_sparring_plan, effective_hard_day_count, effective_hard_days
from .strength_session_quality import classify_strength_item, infer_strength_sessions
from .training_context import TrainingContext, allocate_sessions

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
    return normalize_lower_text(value)


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

    deep_hip_hits = {"hip_flexion_loaded", "mech_hip_flexion", "mech_core_compression"}
    if tags & deep_hip_hits or any(_phrase_in_text(text, phrase) for phrase in _TEXT_DERIVED_RESTRICTIONS["deep_hip_flexion"]):
        derived.add("deep_hip_flexion")

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
    if isinstance(days_until_fight, int) and 0 <= days_until_fight <= 7:
        flags.append("fight_week")
    return flags or ["baseline"]


def _is_high_pressure_weight_cut(*, athlete_model: dict) -> bool:
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    if "aggressive_weight_cut" in readiness_flags:
        return True
    if not (
        athlete_model.get("weight_cut_risk")
        or readiness_flags & {"active_weight_cut", "aggressive_weight_cut"}
    ):
        return False
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    days_until_fight = athlete_model.get("days_until_fight")
    return fatigue in {"moderate", "high"} or (
        isinstance(days_until_fight, int) and days_until_fight <= 28
    )


PHASE_OBJECTIVES = {
    "GPP": "build aerobic base and general force capacity",
    "SPP": "increase fight-specific repeatability and power transfer",
    "TAPER": "maintain sharpness and freshness",
}

PHASE_EMPHASIS = {
    "GPP": ["aerobic repeatability", "general force", "structural strength foundation"],
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


_RECORD_PATTERN = re.compile(r"^(\d+)-(\d+)(?:-(\d+))?$")
_UNKNOWN_COMPETITIVE_MATURITY = "unknown_competitive_maturity"


def _parse_record(record: str) -> dict:
    normalized = str(record or "").strip()
    match = _RECORD_PATTERN.fullmatch(normalized)
    if not match:
        return {
            "record": normalized,
            "wins": None,
            "losses": None,
            "draws": None,
            "total_bouts": None,
            "competitive_maturity": _UNKNOWN_COMPETITIVE_MATURITY,
        }

    wins = int(match.group(1))
    losses = int(match.group(2))
    draws = int(match.group(3)) if match.group(3) is not None else 0
    return {
        "record": normalized,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "total_bouts": wins + losses + draws,
        "competitive_maturity": _UNKNOWN_COMPETITIVE_MATURITY,
    }


def _derive_competitive_maturity(status: str, record: str) -> dict:
    parsed_record = _parse_record(record)
    normalized_status = str(status or "").strip().lower()
    total_bouts = parsed_record.get("total_bouts")

    competitive_maturity = _UNKNOWN_COMPETITIVE_MATURITY
    if normalized_status == "amateur" and isinstance(total_bouts, int):
        if total_bouts <= 4:
            competitive_maturity = "novice_amateur"
        elif total_bouts <= 11:
            competitive_maturity = "developing_amateur"
        else:
            competitive_maturity = "experienced_amateur"

    parsed_record["competitive_maturity"] = competitive_maturity
    return parsed_record


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
    record_profile = _derive_competitive_maturity(training_context.status, record)
    athlete_model = {
        "sport": sport,
        "status": training_context.status,
        "record": record_profile["record"],
        "wins": record_profile["wins"],
        "losses": record_profile["losses"],
        "draws": record_profile["draws"],
        "total_bouts": record_profile["total_bouts"],
        "competitive_maturity": record_profile["competitive_maturity"],
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
        "training_frequency": training_context.training_frequency,
        "training_days": training_context.training_days,
        "hard_sparring_days": training_context.hard_sparring_days,
        "technical_skill_days": training_context.technical_skill_days,
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
    return athlete_model


def _priority_bucket(label: str, kind: str) -> dict:
    return {"label": label, "kind": kind}


def _priority_bucket_labels(entries: list[dict]) -> list[str]:
    return [str(entry.get("label", "")).strip() for entry in entries if str(entry.get("label", "")).strip()]


def _compress_short_camp_priorities(athlete_model: dict) -> dict:
    days_until_fight = athlete_model.get("days_until_fight")
    camp_length_weeks = athlete_model.get("camp_length_weeks")
    if isinstance(days_until_fight, int):
        timeline_days = days_until_fight
    elif isinstance(camp_length_weeks, int):
        timeline_days = camp_length_weeks * 7
    else:
        timeline_days = None

    weakness_tokens = _normalize_limiter_tokens(_clean_list(athlete_model.get("weaknesses", [])))
    goal_tokens = _normalize_limiter_tokens(_clean_list(athlete_model.get("key_goals", [])))
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    short_window = isinstance(timeline_days, int) and timeline_days <= 7
    ultra_short_window = isinstance(timeline_days, int) and timeline_days <= 5

    if not short_window:
        return {
            "timeline_days": timeline_days,
            "is_short_camp": False,
            "is_ultra_short_camp": False,
            "primary_targets": [],
            "maintenance_targets": [],
            "embedded_support": [],
            "deferred": [],
        }

    primary: list[dict] = []
    maintenance: list[dict] = []
    embedded: list[dict] = []
    deferred: list[dict] = []
    used_labels: set[str] = set()

    def add_unique(bucket: list[dict], label: str, kind: str, reason: str) -> None:
        if label in used_labels:
            return
        bucket.append(_priority_bucket(label, kind))
        used_labels.add(label)

    immediate_performance_limiter = (
        weakness_tokens & {"footwork", "coordination", "coordination_proprioception", "proprioception", "balance", "timing", "rhythm", "boxing"}
        or goal_tokens & {"skill_refinement", "striking"}
    )
    if immediate_performance_limiter:
        add_unique(
            primary,
            "footwork / technical sharpness",
            "technical_sharpness",
            "Collapse footwork, timing, boxing quality, and skill refinement into one practical fight-week target.",
        )

    if goal_tokens & {"power", "speed", "explosive_power"} or weakness_tokens & {"sharpness", "speed", "speed_reaction", "reaction", "cns_fatigue"}:
        add_unique(
            primary,
            "power expression",
            "power_expression",
            "Keep neural speed and power output as one sharpness-oriented target.",
        )

    if readiness_flags & {"fight_week", "high_fatigue", "active_weight_cut", "aggressive_weight_cut"} or athlete_model.get("injuries"):
        add_unique(
            primary,
            "fight-readiness and freshness protection",
            "freshness_protection",
            "Freshness, symptom stability, and readiness outrank optional development in the final week.",
        )

    if not primary:
        add_unique(
            primary,
            "fight-readiness and sharpness",
            "fight_readiness",
            "Short camps default to a readiness-first target when no clearer immediate limiter is present.",
        )

    while len(primary) > 2:
        moved = primary.pop()
        destination = embedded if moved["kind"] == "freshness_protection" else maintenance
        destination.append(
            _priority_bucket(moved["label"], moved["kind"])
        )

    conditioning_selected = bool(
        weakness_tokens & {"conditioning", "gas_tank", "aerobic", "endurance", "recovery"}
        or goal_tokens & {"conditioning", "conditioning_endurance", "endurance"}
    )
    if conditioning_selected:
        target_bucket = maintenance
        reason = "Conditioning stays as one small exposure unless the athlete is clearly underprepared this week."
        if not primary and not ultra_short_window:
            target_bucket = primary
            reason = "Conditioning remains primary only because no more urgent fight-week target displaced it."
        add_unique(target_bucket, "gas tank maintenance", "conditioning_maintenance", reason)

    if weakness_tokens & {"mobility", "stiffness"} or goal_tokens & {"mobility", "durability"}:
        mobility_reason = "Mobility is embedded through warm-up, tissue care, and exercise choice unless it is the direct limiter."
        if weakness_tokens & {"mobility", "stiffness"} and athlete_model.get("injuries") and not any(
            entry["kind"] == "freshness_protection" for entry in primary
        ):
            add_unique(primary, "tissue protection / mobility bottleneck", "tissue_state", "Mobility stays primary only because tissue state is the direct limiter.")
        else:
            add_unique(embedded, "mobility support", "mobility_support", mobility_reason)

    if goal_tokens & {"skill_refinement"}:
        add_unique(
            deferred,
            "skill refinement as standalone work",
            "skill_refinement",
            "Absorb skill refinement into technical sharpness instead of giving it its own session objective.",
        )

    raw_other_labels = [
        *(value.replace("_", " ") for value in _clean_list(athlete_model.get("key_goals", []))),
        *(value.replace("_", " ") for value in _clean_list(athlete_model.get("weaknesses", []))),
    ]
    claimed_terms = " ".join(_priority_bucket_labels(primary) + _priority_bucket_labels(maintenance) + _priority_bucket_labels(embedded) + _priority_bucket_labels(deferred)).lower()
    for label in raw_other_labels:
        normalized_label = str(label).strip()
        if not normalized_label or normalized_label.lower() in claimed_terms:
            continue
        add_unique(
            embedded if not ultra_short_window else deferred,
            normalized_label,
            "selection_only",
            "Selected item is acknowledged but not promoted to a standalone short-camp objective.",
        )

    if len(maintenance) > 1:
        overflow = maintenance[1:]
        maintenance = maintenance[:1]
        deferred.extend(_priority_bucket(item["label"], item["kind"]) for item in overflow)

    return {
        "timeline_days": timeline_days,
        "is_short_camp": True,
        "is_ultra_short_camp": ultra_short_window,
        "primary_targets": primary,
        "maintenance_targets": maintenance[:1],
        "embedded_support": embedded,
        "deferred": deferred,
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

    competitive_maturity = athlete_model.get("competitive_maturity") or _UNKNOWN_COMPETITIVE_MATURITY
    specificity_guidance = {
        "unknown_competitive_maturity": "Keep style framing conservative and avoid overstating identity-specific reads.",
        "novice_amateur": "Use clear style labels, but keep tactical wording broad and amateur-safe.",
        "developing_amateur": "Use moderately specific style framing when it matches declared styles and goals.",
        "experienced_amateur": "Use confident athlete-specific style framing when it matches the declared style profile.",
    }.get(competitive_maturity, "Keep style framing conservative and avoid overstating identity-specific reads.")

    return {
        "style_identity": style_identity,
        "training_preference": athlete_model.get("training_preference") or "balanced",
        "experience_band": athlete_model.get("status") or "unspecified",
        "competitive_maturity": competitive_maturity,
        "total_bouts": athlete_model.get("total_bouts"),
        "style_specificity": specificity_guidance,
        "readiness_state": readiness,
        "equipment_profile": _clean_list(athlete_model.get("equipment", [])),
    }


def _derive_main_limiter(athlete_model: dict) -> str:
    compressed = athlete_model.get("compressed_priorities") or {}
    primary_labels = _priority_bucket_labels(compressed.get("primary_targets", []))
    if primary_labels:
        return f"Primary limiter is {primary_labels[0]}."
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
    hard_sparring_days = _clean_list(athlete_model.get("hard_sparring_days", []))
    if injuries:
        risks.append("Injury management must constrain exercise choice and loading.")
    if hard_sparring_days:
        risks.append(
            "Declared hard sparring days create fixed weekly collision points, so peak glycolytic work and primary neural loading cannot stack blindly."
        )
    if athlete_model.get("weight_cut_risk"):
        pct = athlete_model.get("weight_cut_pct") or 0.0
        risks.append(
            f"Weight cut stress is active ({pct:.1f}% body mass target), so recovery margin, strength expression, and conditioning tolerance all tighten."
        )
        if _is_high_pressure_weight_cut(athlete_model=athlete_model):
            risks.append(
                "This is a high-pressure cut window, so protect freshness and remove optional fatigue before extra density or accessory volume."
            )
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
        "organising_principle": "conservative loading with meaningful force production, symptom stability, and rebuild sequencing",
        "drill_emphasis": [
            "conservative loading with meaningful force production",
            "symptom-stable strength before ballistic exposure",
            "low-impact repeatability before unnecessary reactive stress",
        ],
        "protect_first": "symptom stability and meaningful loading before ballistic progression or extra volume",
        "cut_first": "ballistic extras, reaction-heavy accessories, and non-essential reactive contacts before primary strength loading",
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
    compressed = athlete_model.get("compressed_priorities") or {}
    compressed_labels = " ".join(
        _priority_bucket_labels(compressed.get("primary_targets", []))
        + _priority_bucket_labels(compressed.get("maintenance_targets", []))
    ).lower()
    if "technical sharpness" in compressed_labels or "footwork" in compressed_labels:
        return "boxing_quality_under_load"
    if "power expression" in compressed_labels:
        return "sharpness_under_fatigue"
    if "freshness protection" in compressed_labels or "fight-readiness and sharpness" in compressed_labels:
        return "sharpness_under_fatigue"
    if "gas tank maintenance" in compressed_labels:
        return "aerobic_repeatability"

    weakness_tokens = _normalize_limiter_tokens(_clean_list(athlete_model.get("weaknesses", [])))
    goal_tokens = _normalize_limiter_tokens(_clean_list(athlete_model.get("key_goals", [])))
    style_tokens = _normalize_limiter_tokens(
        _clean_list(athlete_model.get("technical_styles", [])) + _clean_list(athlete_model.get("tactical_styles", []))
    )
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    days_until_fight = athlete_model.get("days_until_fight")
    restriction_keys = {
        str((restriction or {}).get("restriction", "")).strip().lower()
        for restriction in restrictions or []
        if str((restriction or {}).get("restriction", "")).strip()
    }
    restriction_regions = {
        str((restriction or {}).get("region", "")).strip().lower()
        for restriction in restrictions or []
        if str((restriction or {}).get("region", "")).strip()
    }
    tissue_restriction_keys = {
        "deep_knee_flexion",
        "deep_hip_flexion",
        "heavy_overhead_pressing",
        "high_impact",
        "high_impact_lower",
        "high_impact_upper",
        "high_impact_global",
        "loaded_flexion",
        "loaded_rotation",
        "spinal_flexion",
        "max_velocity",
    }
    tissue_region_tokens = {"shoulder", "knee", "neck", "back", "spine", "hip", "ankle", "elbow", "wrist"}
    performance_priority_signals = bool(
        goal_tokens & {
            "conditioning",
            "conditioning_endurance",
            "endurance",
            "power",
            "strength",
            "speed",
            "skill_refinement",
            "striking",
        }
        or readiness_flags & {"moderate_fatigue", "high_fatigue", "fight_week"}
        or (style_tokens & {"boxing", "boxer"} and goal_tokens & {"skill_refinement", "striking"})
    )
    tissue_pressure = bool(
        athlete_model.get("injuries")
        or readiness_flags & {"injury_management"}
        or restriction_keys & tissue_restriction_keys
        or restriction_regions & tissue_region_tokens
    )

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
    if athlete_model.get("injuries") and tissue_pressure and (
        athlete_model.get("short_notice")
        or readiness_flags & {"fight_week", "high_fatigue"}
        or (isinstance(days_until_fight, int) and 0 <= days_until_fight <= 14)
    ):
        return "tissue_state"

    if goal_tokens & {"conditioning", "conditioning_endurance", "endurance"}:
        return "aerobic_repeatability"
    if style_tokens & {"boxing", "boxer"} and goal_tokens & {"skill_refinement", "striking"}:
        return "boxing_quality_under_load"
    if readiness_flags & {"moderate_fatigue", "high_fatigue", "fight_week"}:
        return "sharpness_under_fatigue"
    if isinstance(days_until_fight, int) and 0 <= days_until_fight <= 14:
        return "sharpness_under_fatigue"
    if tissue_pressure and not performance_priority_signals:
        return "tissue_state"
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



def _resolve_phase_rule_state(
    phase: str,
    athlete_model: dict,
    phase_brief: dict,
    limiter_profile: dict,
    sport_load_profile: dict,
) -> dict:
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    short_notice = bool(athlete_model.get("short_notice"))
    weight_cut_risk = bool(athlete_model.get("weight_cut_risk"))
    guardrails = phase_brief.get("selection_guardrails") or {}

    tissue_protection_priority = bool(athlete_model.get("injuries")) or "injury_management" in readiness_flags or (
        limiter_profile.get("key") == "tissue_state"
    )
    freshness_priority = phase == "TAPER" or bool(
        readiness_flags & {"fight_week", "high_fatigue", "active_weight_cut", "aggressive_weight_cut"}
    )
    sport_load_owns_density = phase == "TAPER" and bool(sport_load_profile.get("highest_collision_load"))

    protect_first = limiter_profile["protect_first"]
    if fatigue in {"moderate", "high"}:
        protect_first = f"Because fatigue is {fatigue}, protect the limiter quality and freshness before adding extra work."

    cut_first = limiter_profile["cut_first"]
    if short_notice and phase in {"SPP", "TAPER"}:
        cut_first = (
            f"Because this is short notice, cut {limiter_profile['cut_first']} before touching phase-critical "
            "sharpness or boxing quality."
        )
    if weight_cut_risk and phase == "TAPER":
        cut_first = f"{cut_first}; during the cut, remove glycolytic density before alactic sharpness or rehab support."
    cut_first = _join_rule_parts(
        cut_first,
        f"When sport load spikes, cut {sport_load_profile['cut_first_when_sport_load_spikes']} first.",
    )

    return {
        "must_keep": _clean_list(guardrails.get("must_keep_if_present", [])),
        "drop_order_if_thin": _clean_list(guardrails.get("conditioning_drop_order_if_thin", [])),
        "conditioning_sequence": list(limiter_profile["conditioning_sequence"].get(phase, [])),
        "conditioning_sequence_driver": "main_limiter",
        "protect_first": protect_first,
        "protect_first_driver": "safety_and_readiness" if fatigue in {"moderate", "high"} else "main_limiter",
        "cut_first_when_collisions_rise": cut_first,
        "cut_first_driver": "sport_load_collision_rules",
        "tissue_protection_priority": tissue_protection_priority,
        "freshness_priority": freshness_priority,
        "sport_load_owns_density": sport_load_owns_density,
    }


def _build_weekly_stress_map(
    athlete_model: dict,
    phase_briefs: dict[str, dict],
    limiter_profile: dict,
    sport_load_profile: dict,
) -> dict[str, dict]:
    stress_map: dict[str, dict] = {}

    for phase in phase_briefs:
        resolved = _resolve_phase_rule_state(
            phase,
            athlete_model,
            phase_briefs.get(phase, {}),
            limiter_profile,
            sport_load_profile,
        )
        if phase == "GPP":
            highest_neural_day = "Place the highest-neural primary strength day immediately after the weekly recovery / lowest-load day so force quality stays crisp before volume accumulates."
            highest_glycolytic_day = "Keep one density-focused day only, and never let it sit beside hard sparring."
            lowest_load_day = "Use one midweek lowest-load day for recovery, rehab, and easy aerobic support only, then follow it with the primary strength anchor."
        elif phase == "SPP":
            highest_neural_day = "Anchor the highest-neural primary strength day immediately after the recovery / lowest-load day, then keep it away from hard sparring collisions."
            highest_glycolytic_day = "Use one highest glycolytic day as the main fight-pace stressor unless hard sparring already occupies that slot."
            lowest_load_day = "Keep one lowest-load day for recovery, tissue care, and limiter-preserving support work before the main neural-strength anchor."
        else:
            highest_neural_day = "Use one highest neural day as a sharpness primer, not as a fatigue builder."
            highest_glycolytic_day = "Only keep a light fight-pace touch; drop glycolytic density first if freshness or boxing quality falls."
            lowest_load_day = "Make one day clearly lowest-load with recovery, rehab, and freshness protection only."

        stress_map[phase] = {
            "organising_limiter": limiter_profile["label"],
            "highest_neural_day": highest_neural_day,
            "highest_glycolytic_day": highest_glycolytic_day,
            "lowest_load_day": lowest_load_day,
            "conditioning_sequence": list(resolved.get("conditioning_sequence", [])),
            "drill_emphasis": list(limiter_profile["drill_emphasis"]),
            "protect_first": resolved.get("protect_first", ""),
            "cut_first_when_collisions_rise": resolved.get("cut_first_when_collisions_rise", ""),
            "sparring_collision_rule": limiter_profile["sparring_collision_rule"],
            "sport_load_interaction": _join_rule_parts(
                limiter_profile["boxing_load_rule"],
                sport_load_profile["quality_override"],
            ),
            "highest_collision_sport_load": sport_load_profile["highest_collision_load"],
            "sport_load_collision_rules": list(sport_load_profile["collision_rules"]),
            "replace_missing_live_load": sport_load_profile["replace_missing_live_load"],
            "resolved_rule_state": resolved,
        }
    return stress_map

_WEEKLY_STAGE_TEMPLATES = {
    "GPP": {
        "single": {
            "key": "foundation_to_repeatability",
            "label": "foundation / repeatability",
            "objective": "Use the available base window to restore structure and rebuild repeatability before chasing extra specificity.",
            "emphasize": ["structural restoration", "repeatability build"],
            "protect": ["low-damage base work"],
            "deprioritize": ["fight-pace density", "collision-heavy extras"],
            "load_bias": "build",
        },
        "early": {
            "key": "foundation_restore",
            "label": "foundation / structural restoration",
            "objective": "Restore structural tolerance, aerobic support, and technical rhythm before density rises.",
            "emphasize": ["structural restoration", "aerobic support"],
            "protect": ["tissue calm", "technical rhythm"],
            "deprioritize": ["fight-pace density", "non-essential explosive extras"],
            "load_bias": "build",
        },
        "middle": {
            "key": "build_repeatability",
            "label": "build / repeatability",
            "objective": "Build repeatability and general force without breaking the base the phase is trying to create.",
            "emphasize": ["repeatability", "general force"],
            "protect": ["repeatable quality under manageable fatigue"],
            "deprioritize": ["late-camp sharpness chasing", "redundant accessory fatigue"],
            "load_bias": "build",
        },
        "late": {
            "key": "general_to_specific_bridge",
            "label": "bridge / transfer",
            "objective": "Bridge general work toward specific transfer while keeping the base qualities alive.",
            "emphasize": ["transfer under fatigue", "specific support"],
            "protect": ["base qualities"],
            "deprioritize": ["extra general volume"],
            "load_bias": "consolidate",
        },
    },
    "SPP": {
        "single": {
            "key": "specific_density_to_peak",
            "label": "specific density / peak",
            "objective": "Compress specific density build and peak transfer into one focused week because the camp does not have room for separation.",
            "emphasize": ["fight-pace density", "sharp transfer"],
            "protect": ["specific quality", "freshness"],
            "deprioritize": ["non-specific volume", "extra accessory work"],
            "load_bias": "concentrate",
        },
        "early": {
            "key": "specific_entry",
            "label": "specific entry",
            "objective": "Shift the camp from general work into clearly fight-specific stress and sport transfer.",
            "emphasize": ["specific transfer", "fight-pace entry"],
            "protect": ["sport quality"],
            "deprioritize": ["extra general volume"],
            "load_bias": "build",
        },
        "middle": {
            "key": "specific_density_build",
            "label": "specific density build",
            "objective": "Make fight-specific repeatability and density the main developmental job of the week.",
            "emphasize": ["fight-pace density", "repeatability under sport load"],
            "protect": ["quality under density"],
            "deprioritize": ["redundant accessory work"],
            "load_bias": "concentrate",
        },
        "late": {
            "key": "peak_specificity",
            "label": "peak specificity",
            "objective": "Keep specificity high while reducing any work that blunts sharpness or technical quality.",
            "emphasize": ["sharp transfer", "specific confidence"],
            "protect": ["freshness", "sport sharpness"],
            "deprioritize": ["excess fatigue", "generic volume"],
            "load_bias": "peak",
        },
    },
    "TAPER": {
        "single": {
            "key": "taper_to_fight",
            "label": "taper / fight-readiness",
            "objective": "Reduce noise, keep rhythm, and arrive at the fight fresh and technically ready.",
            "emphasize": ["freshness", "rhythm", "confidence"],
            "protect": ["sharpness", "recovery"],
            "deprioritize": ["fatigue accumulation", "new drill exposure"],
            "load_bias": "reduce",
        },
        "early": {
            "key": "taper_freshness",
            "label": "taper / freshness",
            "objective": "Strip out fatigue and keep only the minimum work needed to maintain sharpness.",
            "emphasize": ["freshness", "neural sharpness"],
            "protect": ["recovery", "confidence"],
            "deprioritize": ["lactate-heavy density", "soreness-heavy loading"],
            "load_bias": "reduce",
        },
        "late": {
            "key": "fight_week_survival_rhythm",
            "label": "fight-week survival / rhythm",
            "objective": "Protect rhythm, confidence, and freshness while removing anything that can flatten performance.",
            "emphasize": ["rhythm", "confidence", "freshness"],
            "protect": ["sharpness", "weight-cut survival"],
            "deprioritize": ["all avoidable fatigue", "non-essential volume"],
            "load_bias": "minimal_dose",
        },
    },
}


def _phase_progression_slot_count(brief: dict) -> int:
    weeks = int(brief.get("weeks") or 0)
    days = int(brief.get("days") or 0)
    if weeks > 0:
        return weeks
    return 1 if days > 0 else 0


def _split_phase_days(days: int, slot_count: int) -> list[int]:
    if slot_count <= 0:
        return []
    if days <= 0:
        return [0] * slot_count
    base, remainder = divmod(days, slot_count)
    return [base + (1 if idx < remainder else 0) for idx in range(slot_count)]


def _progression_templates_for_phase(phase: str, slot_count: int, athlete_model: dict, phase_days: int) -> list[dict]:
    templates = _WEEKLY_STAGE_TEMPLATES[phase]
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    short_notice = bool(athlete_model.get("short_notice"))
    fight_week_like = short_notice or phase_days <= 7 or "fight_week" in readiness_flags

    if phase == "GPP":
        if slot_count <= 1:
            return [templates["single"]]
        if slot_count == 2:
            return [templates["early"], templates["middle"]]
        return [templates["early"]] + [templates["middle"]] * (slot_count - 2) + [templates["late"]]

    if phase == "SPP":
        if slot_count <= 1:
            return [templates["single"]]
        if slot_count == 2:
            return [templates["middle"], templates["late"]]
        return [templates["early"]] + [templates["middle"]] * (slot_count - 2) + [templates["late"]]

    if slot_count <= 1:
        return [templates["late"] if fight_week_like else templates["single"]]
    return [templates["early"]] + [templates["late"]] * (slot_count - 1)


def _build_week_by_week_progression(
    athlete_model: dict,
    phase_briefs: dict[str, dict],
    weekly_stress_map: dict[str, dict],
) -> dict:
    week_entries: list[dict] = []
    week_index = 1

    for phase in ("GPP", "SPP", "TAPER"):
        brief = phase_briefs.get(phase)
        if not brief:
            continue
        slot_count = _phase_progression_slot_count(brief)
        if slot_count <= 0:
            continue

        phase_days = int(brief.get("days") or 0)
        stage_templates = _progression_templates_for_phase(phase, slot_count, athlete_model, phase_days)
        day_spans = _split_phase_days(phase_days, slot_count)
        stress = weekly_stress_map.get(phase, {})
        guardrails = brief.get("selection_guardrails") or {}

        for phase_week_index, stage in enumerate(stage_templates, start=1):
            week_entries.append(
                {
                    "week_index": week_index,
                    "phase": phase,
                    "phase_week_index": phase_week_index,
                    "phase_week_total": slot_count,
                    "span_days": day_spans[phase_week_index - 1] if phase_week_index - 1 < len(day_spans) else 0,
                    "stage_key": stage["key"],
                    "stage_label": stage["label"],
                    "stage_objective": stage["objective"],
                    "load_bias": stage["load_bias"],
                    "session_counts": dict(brief.get("session_counts") or {}),
                    "build": _dedupe_preserve_order(_clean_list(brief.get("emphasize", [])) + list(stage.get("emphasize", []))),
                    "protect": _dedupe_preserve_order(_clean_list(brief.get("risk_flags", [])) + list(stage.get("protect", []))),
                    "deprioritize": _dedupe_preserve_order(_clean_list(brief.get("deprioritize", [])) + list(stage.get("deprioritize", []))),
                    "must_keep": _clean_list(guardrails.get("must_keep_if_present", [])),
                    "drop_order_if_thin": _clean_list(guardrails.get("conditioning_drop_order_if_thin", [])),
                    "conditioning_sequence": list(stress.get("conditioning_sequence", [])),
                    "highest_neural_day": stress.get("highest_neural_day", ""),
                    "highest_glycolytic_day": stress.get("highest_glycolytic_day", ""),
                    "lowest_load_day": stress.get("lowest_load_day", ""),
                    "protect_first": stress.get("protect_first", ""),
                    "cut_first_when_collisions_rise": stress.get("cut_first_when_collisions_rise", ""),
                    "sport_load_interaction": stress.get("sport_load_interaction", ""),
                    "highest_collision_sport_load": stress.get("highest_collision_sport_load", ""),
                    "resolved_rule_state": dict(stress.get("resolved_rule_state", {})),
                }
            )
            week_index += 1

    return {
        "model": "adaptive_phase_overlay.v1",
        "source_of_truth": [
            "Phase order and duration come from the existing deterministic phase allocation.",
            "Progression jobs compress or expand to fit the active phase duration without rewriting phase boundaries.",
            "Days refine span reporting so short active phases still get one compressed week entry when needed.",
        ],
        "active_week_count": len(week_entries),
        "weeks": week_entries,
    }


def _role_anchor(role_key: str) -> str:
    if role_key in {
        "primary_strength_day",
        "structural_strength_day",
        "neural_plus_strength_day",
        "neural_primer_day",
        "alactic_speed_day",
        "alactic_sharpness_day",
        "alactic_coordination_day",
        "alactic_support_day",
    }:
        return "highest_neural_day"
    if role_key in {"fight_pace_repeatability_day", "light_fight_pace_touch_day"}:
        return "highest_glycolytic_day"
    if role_key in {"recovery_reset_day", "tissue_recovery_day", "fight_week_freshness_day"}:
        return "lowest_load_day"
    return "support_day"


def _placement_rule_for_anchor(anchor: str, week_entry: dict) -> str:
    if anchor == "highest_neural_day":
        return week_entry.get("highest_neural_day", "Use this as the week's highest neural slot.")
    if anchor == "highest_glycolytic_day":
        return week_entry.get("highest_glycolytic_day", "Use this as the week's main density slot.")
    if anchor == "lowest_load_day":
        return week_entry.get("lowest_load_day", "Keep this as the lowest-load day of the week.")
    return "Place this away from the highest collision sport load when possible."


def _strength_role_key(phase: str, stage_key: str, limiter_key: str, idx: int) -> str:
    if phase == "GPP":
        if idx == 0:
            return "structural_strength_day" if limiter_key == "tissue_state" else "primary_strength_day"
        return "secondary_strength_day"
    if phase == "SPP":
        if idx == 0:
            return "neural_plus_strength_day"
        if stage_key in {"peak_specificity", "specific_density_to_peak"}:
            return "strength_touch_day"
        return "transfer_strength_day"
    if idx == 0:
        return "neural_primer_day"
    return "small_strength_touch_day"


def _conditioning_role_key(phase: str, system: str, limiter_key: str) -> str:
    if system == "aerobic":
        if phase == "GPP":
            return "aerobic_coordination_day" if limiter_key == "coordination" else "aerobic_base_day"
        if phase == "SPP":
            return "repeatability_support_day" if limiter_key == "aerobic_repeatability" else "aerobic_support_day"
        return "aerobic_flush_day"
    if system == "glycolytic":
        if phase == "TAPER":
            return "light_fight_pace_touch_day"
        if phase == "SPP":
            return "fight_pace_repeatability_day"
        return "controlled_repeatability_day"
    if phase == "TAPER":
        return "alactic_sharpness_day"
    if phase == "SPP":
        return "alactic_speed_day"
    return "alactic_coordination_day" if limiter_key == "coordination" else "alactic_support_day"


def _recovery_role_key(phase: str, stage_key: str, athlete_model: dict) -> str:
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    if phase == "TAPER" or stage_key == "fight_week_survival_rhythm" or "fight_week" in readiness_flags:
        return "fight_week_freshness_day"
    if athlete_model.get("injuries"):
        return "tissue_recovery_day"
    return "recovery_reset_day"


def _role_selection_rule(role_key: str, category: str, system: str | None = None) -> str:
    if category == "strength":
        if role_key in {"primary_strength_day", "structural_strength_day", "neural_plus_strength_day", "neural_primer_day"}:
            return "Use the highest-priority compliant strength slot first."
        return "Use a remaining compliant strength slot with lower interference cost than the main strength day."
    if category == "conditioning":
        if system == "aerobic":
            return "Prefer compliant aerobic or low-damage conditioning slots first."
        if system == "glycolytic":
            return "Prefer compliant glycolytic slots only when phase guardrails still allow density work."
        return "Prefer compliant alactic slots that preserve speed and sharpness."
    return "Use rehab slots first; if rehab is absent, keep this day recovery-only."


def _role_governance(
    week_entry: dict,
    *,
    category: str,
    role_key: str,
    athlete_model: dict,
    system: str | None = None,
    idx: int = 0,
) -> dict:
    phase = str(week_entry.get("phase", "")).upper()
    resolved_rule_state = dict(week_entry.get("resolved_rule_state", {}))
    must_keep = set(_clean_list(resolved_rule_state.get("must_keep", week_entry.get("must_keep", []))))
    drop_order = _clean_list(resolved_rule_state.get("drop_order_if_thin", week_entry.get("drop_order_if_thin", [])))
    cut_first_text = str(
        resolved_rule_state.get("cut_first_when_collisions_rise", week_entry.get("cut_first_when_collisions_rise", ""))
    ).lower()
    highest_collision_load = str(week_entry.get("highest_collision_sport_load", "")).strip()
    tissue_protection_priority = bool(resolved_rule_state.get("tissue_protection_priority"))
    freshness_priority = bool(resolved_rule_state.get("freshness_priority"))
    sport_load_owns_density = bool(resolved_rule_state.get("sport_load_owns_density"))

    hard_suppression: list[str] = []
    suppression_rules: list[str] = []

    if category == "strength" and phase == "TAPER" and idx > 0:
        hard_suppression.append(
            "Taper survival rules suppress extra strength touches once the primary primer already exists."
        )
    if category == "strength" and role_key == "neural_primer_day" and tissue_protection_priority:
        hard_suppression.append(
            "Safety and readiness prioritize tissue protection, so sharpness-dominant neural primer work is suppressed."
        )

    if category == "conditioning" and system:
        if system in drop_order and system not in must_keep:
            suppression_rules.append(
                f"{system.replace('_', ' ')} work is optional in this week and must drop before must-keep systems if the plan gets thin."
            )
        if role_key == "alactic_sharpness_day" and tissue_protection_priority:
            hard_suppression.append(
                "Safety and readiness prioritize tissue protection, so sharpness-dominant alactic work is suppressed."
            )
        if system == "glycolytic" and system not in must_keep and (
            (phase == "TAPER" and sport_load_owns_density and highest_collision_load) or "glycolytic density" in cut_first_text
        ):
            hard_suppression.append(
                "Taper survival and sport-load rules keep glycolytic density optional once live load already owns density."
            )
        if system == "aerobic" and phase == "TAPER" and system not in must_keep and freshness_priority:
            suppression_rules.append(
                "Optional aerobic work cannot outrank fight-week freshness protection."
            )

    if category == "recovery":
        suppression_rules.append(
            "Recovery roles may replace work, but cannot create extra workload or displace rehab."
        )

    return {
        "authority": "execution_layer_only",
        "execution_only": True,
        "governed_by": [entry["driver"] for entry in PLANNING_DECISION_HIERARCHY],
        "cannot_override": [
            "phase_survival_rules",
            "safety_and_readiness",
            "sport_load_collision_rules",
            "main_limiter",
            "session_counts",
            "must_keep",
            "drop_order_if_thin",
            "conditioning_sequence",
        ],
        "resolved_authority": {
            "protect_first_driver": resolved_rule_state.get("protect_first_driver"),
            "cut_first_driver": resolved_rule_state.get("cut_first_driver"),
            "conditioning_sequence_driver": resolved_rule_state.get("conditioning_sequence_driver"),
        },
        "suppression_rules": suppression_rules,
        "hard_suppression_reasons": hard_suppression,
    }


_PRIMARY_STRENGTH_ROLE_KEYS = {
    "primary_strength_day",
    "structural_strength_day",
    "neural_plus_strength_day",
    "neural_primer_day",
}
_WEEKDAY_ORDER = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _athlete_sport_key(athlete_model: dict) -> str:
    return str(athlete_model.get("sport") or "").strip().lower().replace(" ", "_")


def _ordered_weekdays(values: list[str]) -> list[str]:
    cleaned = _dedupe_preserve_order([str(value).strip() for value in values if str(value).strip()])
    return sorted(cleaned, key=lambda day: (_WEEKDAY_ORDER.get(day.strip().lower(), 99), day.strip().lower()))


def _declared_day_sets(athlete_model: dict) -> tuple[list[str], set[str], set[str]]:
    training_days = _ordered_weekdays(_clean_list(athlete_model.get("training_days", [])))
    hard_sparring = {day for day in _ordered_weekdays(_clean_list(athlete_model.get("hard_sparring_days", []))) if day in training_days}
    technical_skill = {day for day in _ordered_weekdays(_clean_list(athlete_model.get("technical_skill_days", []))) if day in training_days}
    return training_days, hard_sparring, technical_skill


def _append_day_hint(role: dict, day: str | None, reason: str | None = None) -> None:
    if not day:
        role["scheduled_day_hint"] = ""
        role["day_assignment_reason"] = ""
        return
    role["scheduled_day_hint"] = day
    role["day_assignment_reason"] = reason or ""
    placement = str(role.get("placement_rule", "")).strip()
    extra = f"Prefer {day} for this role."
    if reason:
        extra = f"{extra} {reason}"
    role["placement_rule"] = f"{placement} {extra}".strip() if placement else extra


def _dedupe_clean_strings(values: list[Any]) -> list[str]:
    return _dedupe_preserve_order([str(value).strip() for value in values if str(value).strip()])


def _append_week_coach_note_flag(week_entry: dict, flag: str) -> None:
    current_flags = _dedupe_clean_strings(_clean_list(week_entry.get("coach_note_flags", [])))
    if flag and flag not in current_flags:
        current_flags.append(flag)
    week_entry["coach_note_flags"] = current_flags


def _hard_sparring_coach_note_flags(plan_entry: dict[str, Any] | None = None) -> list[str]:
    status = str((plan_entry or {}).get("status") or "hard_as_planned").strip() or "hard_as_planned"
    return ["deload hard sparring"] if status != "hard_as_planned" else []


def _hard_sparring_role(week_entry: dict, day: str, plan_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    status = str((plan_entry or {}).get("status") or "hard_as_planned").strip() or "hard_as_planned"
    reason_codes = list((plan_entry or {}).get("reason_codes") or [])
    coach_note_flags = _hard_sparring_coach_note_flags(plan_entry)
    role: dict[str, Any] = {
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "preferred_pool": "declared_hard_sparring_days",
        "selection_rule": "Keep the declared hard sparring slot fixed. If readiness is compromised, deload the sparring dose instead of replacing the day role.",
        "anchor": "highest_collision_sport_load",
        "placement_rule": "Keep this declared hard sparring slot fixed on the athlete's stated day.",
        "governance": {
            "authority": "declared_schedule_lock",
            "execution_only": False,
            "governed_by": [entry["driver"] for entry in PLANNING_DECISION_HIERARCHY],
            "cannot_override": [
                "declared_hard_sparring_days",
                "weekly_role_map",
                "session_counts",
                "resequence",
                "compression",
                "repair",
            ],
            "resolved_authority": {
                "protect_first_driver": (week_entry.get("resolved_rule_state") or {}).get("protect_first_driver"),
                "cut_first_driver": (week_entry.get("resolved_rule_state") or {}).get("cut_first_driver"),
                "conditioning_sequence_driver": (week_entry.get("resolved_rule_state") or {}).get("conditioning_sequence_driver"),
            },
            "suppression_rules": ["Declared hard sparring days are immutable weekly role locks."],
            "hard_suppression_reasons": [],
            "locked_day": day,
        },
        "scheduled_day_hint": day,
        "day_assignment_reason": "Declared hard sparring day is fixed in the weekly role map.",
        "hard_sparring_status": status,
        "hard_sparring_reason_codes": reason_codes,
        "hard_sparring_reason": str((plan_entry or {}).get("reason") or ""),
        "coach_note_flags": coach_note_flags,
    }
    if role["coach_note_flags"]:
        role["placement_rule"] += " Deload the sparring dose instead of changing the slot."
    return role


def _make_hard_sparring_lock_suppression(role: dict, day: str) -> dict[str, Any]:
    return {
        "category": role.get("category"),
        "role_key": role.get("role_key"),
        "preferred_system": role.get("preferred_system", ""),
        "reasons": [f"Declared hard sparring locks {day} as hard_sparring_day in the weekly role map."],
        "governance": dict(role.get("governance", {})),
        "locked_day": day,
        "replacement_role_key": "hard_sparring_day",
    }


def _replaceable_role_priority(role: dict, *, day: str) -> tuple[int, int]:
    scheduled_day = str(role.get("scheduled_day_hint") or "").strip()
    if scheduled_day == day:
        return (-1, 0)
    category = str(role.get("category") or "").strip()
    role_key = str(role.get("role_key") or "").strip()
    if category == "conditioning":
        return (0 if role.get("preferred_system") == "glycolytic" else 1, 1)
    if category == "strength" and role_key not in _PRIMARY_STRENGTH_ROLE_KEYS:
        return (2, 2)
    if category == "recovery":
        return (3, 3)
    if category == "strength":
        return (4, 4)
    return (5, 5)


def _lock_declared_hard_sparring_roles(
    week_entry: dict,
    session_roles: list[dict],
    suppressed_roles: list[dict],
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    declared_hard_days = _ordered_weekdays(
        _clean_list(week_entry.get("declared_hard_sparring_days") or athlete_model.get("hard_sparring_days", []))
    )
    if not declared_hard_days:
        return session_roles, suppressed_roles

    updated_roles = list(session_roles)
    updated_suppressed = list(suppressed_roles)
    plan_by_day = {
        str(entry.get("day") or "").strip(): entry
        for entry in (hard_sparring_plan or [])
        if str(entry.get("day") or "").strip()
    }
    used_indices: set[int] = set()

    for day in declared_hard_days:
        replacement = _hard_sparring_role(week_entry, day, plan_by_day.get(day))
        existing_idx = next(
            (
                idx for idx, role in enumerate(updated_roles)
                if role.get("role_key") == "hard_sparring_day" and str(role.get("scheduled_day_hint") or "").strip() == day
            ),
            None,
        )
        if existing_idx is not None:
            updated_roles[existing_idx] = replacement
            used_indices.add(existing_idx)
            continue

        candidate_indices = [
            idx
            for idx, role in enumerate(updated_roles)
            if idx not in used_indices and role.get("role_key") != "hard_sparring_day"
        ]
        candidate_idx = None
        if candidate_indices:
            candidate_idx = min(
                candidate_indices,
                key=lambda idx: _replaceable_role_priority(updated_roles[idx], day=day),
            )

        if candidate_idx is None:
            updated_roles.append(replacement)
            used_indices.add(len(updated_roles) - 1)
            continue

        updated_suppressed.append(_make_hard_sparring_lock_suppression(updated_roles[candidate_idx], day))
        updated_roles[candidate_idx] = replacement
        used_indices.add(candidate_idx)

    if any(role.get("coach_note_flags") for role in updated_roles if role.get("role_key") == "hard_sparring_day"):
        _append_week_coach_note_flag(week_entry, "deload hard sparring")

    for idx, role in enumerate(updated_roles, start=1):
        role["session_index"] = idx
    return updated_roles, updated_suppressed


def _assign_declared_day_hints(
    ordered: list[dict],
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> list[dict]:
    if not ordered:
        return ordered

    training_days, hard_sparring_days, technical_skill_days = _declared_day_sets(athlete_model)
    if not training_days:
        return ordered

    day_assignments: dict[int, str] = {}
    used_days: set[str] = set()

    for idx, role in enumerate(ordered):
        if role.get("role_key") != "hard_sparring_day":
            continue
        locked_day = str(role.get("scheduled_day_hint") or "").strip()
        if locked_day and locked_day in training_days and locked_day not in used_days:
            day_assignments[idx] = locked_day
            used_days.add(locked_day)

    recovery_idx = next((idx for idx, role in enumerate(ordered) if role.get("category") == "recovery"), None)
    primary_idx = next(
        (idx for idx, role in enumerate(ordered) if role.get("category") == "strength" and role.get("role_key") in _PRIMARY_STRENGTH_ROLE_KEYS),
        None,
    )
    glycolytic_idx = next(
        (
            idx
            for idx, role in enumerate(ordered)
            if role.get("category") == "conditioning" and role.get("preferred_system") == "glycolytic"
        ),
        None,
    )
    aerobic_idx = next(
        (
            idx
            for idx, role in enumerate(ordered)
            if role.get("category") == "conditioning" and role.get("preferred_system") == "aerobic"
        ),
        None,
    )
    if recovery_idx is not None and primary_idx is not None and len(training_days) >= 2:
        middle = max(0, len(training_days) // 2)
        best_pair: tuple[int, int] | None = None
        best_score = -10_000
        for idx in range(len(training_days) - 1):
            recovery_day = training_days[idx]
            primary_day = training_days[idx + 1]
            if primary_day in hard_sparring_days:
                continue
            score = 100
            if recovery_day not in hard_sparring_days:
                score += 10
            if recovery_day in technical_skill_days:
                score += 4
            score -= abs((idx + 1) - middle)
            if score > best_score:
                best_score = score
                best_pair = (idx, idx + 1)
        if best_pair is None:
            fallback_idx = next((idx for idx, day in enumerate(training_days[1:], start=1) if day not in hard_sparring_days), 1)
            best_pair = (max(0, fallback_idx - 1), fallback_idx)

        recovery_day = training_days[best_pair[0]]
        primary_day = training_days[best_pair[1]]
        day_assignments[recovery_idx] = recovery_day
        day_assignments[primary_idx] = primary_day
        used_days.update({recovery_day, primary_day})

    if glycolytic_idx is not None:
        preferred_glycolytic_day = next(
            (day for day in reversed(training_days) if day not in hard_sparring_days and day not in used_days),
            None,
        )
        if not preferred_glycolytic_day:
            preferred_glycolytic_day = next((day for day in reversed(training_days) if day not in used_days), None)
        if preferred_glycolytic_day:
            day_assignments[glycolytic_idx] = preferred_glycolytic_day
            used_days.add(preferred_glycolytic_day)

    if aerobic_idx is not None:
        preferred_aerobic_day = next((day for day in training_days if day in technical_skill_days and day not in used_days), None)
        if preferred_aerobic_day:
            day_assignments[aerobic_idx] = preferred_aerobic_day
            used_days.add(preferred_aerobic_day)

    for idx, day in day_assignments.items():
        role = ordered[idx]
        reason = ""
        if role.get("role_key") == "hard_sparring_day":
            reason = "Declared hard sparring days stay locked in the weekly role map; only the sparring dose may deload."
        elif idx == primary_idx:
            reason = "Keep the main neural-strength slot away from declared hard sparring and immediately after the recovery day when possible."
        elif idx == recovery_idx:
            reason = "Use the lowest-load day immediately before the primary strength anchor when possible."
        elif idx == glycolytic_idx and day in hard_sparring_days:
            reason = "Let declared hard sparring own the main collision-heavy combat load when it already exists."
        elif idx == aerobic_idx and day in technical_skill_days:
            reason = "Use declared technical skill days for lower-noise support work when possible."
        _append_day_hint(role, day, reason)

    for idx, role in enumerate(ordered):
        if idx not in day_assignments:
            _append_day_hint(role, "")

    return ordered


def _preferred_boxer_conditioning_sequence(phase: str, conditioning_sequence: list[str]) -> list[str]:
    phase = str(phase or "").upper()
    if phase == "GPP":
        preferred = ["aerobic", "alactic", "glycolytic"]
    elif phase == "SPP":
        preferred = ["aerobic", "glycolytic", "alactic"]
    else:
        preferred = ["alactic", "aerobic", "glycolytic"]
    return _dedupe_preserve_order(preferred + list(conditioning_sequence or []))


def _resequence_session_roles(
    week_entry: dict,
    session_roles: list[dict],
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> list[dict]:
    if len(session_roles) <= 1:
        return session_roles

    ordered = list(session_roles)
    sport_key = _athlete_sport_key(athlete_model)
    phase = str(week_entry.get("phase", "")).upper()

    def _is_primary_strength(role: dict) -> bool:
        return role.get("category") == "strength" and role.get("role_key") in _PRIMARY_STRENGTH_ROLE_KEYS

    def _is_support_strength(role: dict) -> bool:
        return role.get("category") == "strength" and not _is_primary_strength(role)

    def _is_low_damage_conditioning(role: dict) -> bool:
        if role.get("category") != "conditioning":
            return False
        if role.get("preferred_system") == "aerobic":
            return True
        return role.get("role_key") in {"repeatability_support_day", "controlled_repeatability_day"}

    def _take_first(predicate, used: set[int], result: list[dict]) -> None:
        for idx, role in enumerate(ordered):
            if idx in used:
                continue
            if predicate(role):
                used.add(idx)
                result.append(role)
                return

    if sport_key == "boxing" and phase in {"GPP", "SPP"}:
        used: set[int] = set()
        result: list[dict] = []
        _take_first(_is_support_strength, used, result)
        _take_first(_is_low_damage_conditioning, used, result)
        _take_first(lambda role: role.get("category") == "recovery", used, result)
        _take_first(_is_primary_strength, used, result)
        for idx, role in enumerate(ordered):
            if idx in used:
                continue
            if role.get("category") == "conditioning":
                used.add(idx)
                result.append(role)
        for idx, role in enumerate(ordered):
            if idx in used:
                continue
            result.append(role)
        ordered = result
    else:
        recovery_idx = next((idx for idx, role in enumerate(ordered) if role.get("category") == "recovery"), None)
        primary_idx = next((idx for idx, role in enumerate(ordered) if _is_primary_strength(role)), None)
        if recovery_idx is not None and primary_idx is not None and primary_idx != recovery_idx + 1:
            primary_role = ordered.pop(primary_idx)
            if primary_idx < recovery_idx:
                recovery_idx -= 1
            ordered.insert(recovery_idx + 1, primary_role)

    for idx, role in enumerate(ordered, start=1):
        role["session_index"] = idx
    ordered = _assign_declared_day_hints(ordered, athlete_model, hard_sparring_plan=hard_sparring_plan)
    return ordered


def _short_camp_priority_catalog(compressed: dict) -> dict[str, str]:
    label_by_kind: dict[str, str] = {}
    for bucket in ("primary_targets", "maintenance_targets", "embedded_support", "deferred"):
        for entry in compressed.get(bucket, []) or []:
            kind = str((entry or {}).get("kind", "")).strip()
            label = str((entry or {}).get("label", "")).strip()
            if kind and label and kind not in label_by_kind:
                label_by_kind[kind] = label
    return label_by_kind


def _compressed_priority_for_role(role: dict, athlete_model: dict) -> tuple[str, str]:
    compressed = athlete_model.get("compressed_priorities") or {}
    label_by_kind = _short_camp_priority_catalog(compressed)
    if not compressed.get("is_short_camp"):
        return "", ""

    role_key = str(role.get("role_key", "")).strip()
    category = str(role.get("category", "")).strip()
    system = str(role.get("preferred_system", "")).strip()

    if category == "recovery":
        if label_by_kind.get("freshness_protection"):
            return label_by_kind["freshness_protection"], "primary_target"
        return "embedded recovery support", "embedded_support"

    if category == "conditioning" and system == "aerobic" and label_by_kind.get("conditioning_maintenance"):
        return label_by_kind["conditioning_maintenance"], "maintenance_target"

    if category == "conditioning" and system == "glycolytic" and label_by_kind.get("conditioning_maintenance"):
        return label_by_kind["conditioning_maintenance"], "maintenance_target"

    if (
        category == "conditioning"
        and system == "alactic"
        and label_by_kind.get("power_expression")
    ):
        return label_by_kind["power_expression"], "primary_target"

    if role_key in {
        "aerobic_coordination_day",
        "repeatability_support_day",
        "aerobic_support_day",
        "controlled_repeatability_day",
        "fight_pace_repeatability_day",
        "light_fight_pace_touch_day",
    } and label_by_kind.get("technical_sharpness"):
        return label_by_kind["technical_sharpness"], "primary_target"

    if role_key in {"primary_strength_day", "neural_plus_strength_day", "neural_primer_day", "alactic_sharpness_day", "alactic_speed_day"}:
        if label_by_kind.get("power_expression"):
            return label_by_kind["power_expression"], "primary_target"
        if label_by_kind.get("technical_sharpness"):
            return label_by_kind["technical_sharpness"], "primary_target"

    if role_key in {"strength_touch_day", "transfer_strength_day", "small_strength_touch_day"}:
        if label_by_kind.get("power_expression"):
            return label_by_kind["power_expression"], "primary_target"

    return "", ""


def _apply_short_camp_role_compression(
    week_entry: dict,
    session_roles: list[dict],
    suppressed_roles: list[dict],
    athlete_model: dict,
) -> tuple[list[dict], list[dict]]:
    compressed = athlete_model.get("compressed_priorities") or {}
    if not compressed.get("is_short_camp"):
        return session_roles, suppressed_roles

    kept_roles: list[dict] = []
    updated_suppressed = list(suppressed_roles)

    for role in session_roles:
        label, bucket = _compressed_priority_for_role(role, athlete_model)
        if label:
            role["compressed_priority_label"] = label
            role["compressed_priority_bucket"] = bucket
            kept_roles.append(role)
            continue
        if role.get("category") == "recovery":
            role["compressed_priority_label"] = "embedded recovery support"
            role["compressed_priority_bucket"] = "embedded_support"
            kept_roles.append(role)
            continue
        updated_suppressed.append(
            {
                "category": role.get("category"),
                "role_key": role.get("role_key"),
                "preferred_system": role.get("preferred_system", ""),
                "reasons": [
                    "Short-camp compression removed this standalone session purpose because it did not map to a compressed week-level priority."
                ],
                "governance": dict(role.get("governance", {})),
            }
        )

    for idx, role in enumerate(kept_roles, start=1):
        role["session_index"] = idx
    return kept_roles, updated_suppressed


def _intentional_compression_stub() -> dict[str, Any]:
    return {
        "active": False,
        "reason_codes": [],
        "reason": "",
        "summary": "",
    }


def _high_fatigue_compression_reason_codes(
    athlete_model: dict,
    *,
    effective_hard_spar_count: int | None = None,
) -> list[str]:
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    if fatigue != "high" and "high_fatigue" not in readiness_flags:
        return []

    reason_codes = ["high_fatigue"]
    hard_spar_count = effective_hard_spar_count
    if hard_spar_count is None:
        hard_spar_count = len(_clean_list(athlete_model.get("hard_sparring_days", [])))
    if hard_spar_count >= 2:
        reason_codes.append("two_hard_spar_days")
    if _is_high_pressure_weight_cut(athlete_model=athlete_model):
        reason_codes.append("high_pressure_weight_cut")
    elif athlete_model.get("weight_cut_risk") or readiness_flags & {"active_weight_cut", "aggressive_weight_cut"}:
        reason_codes.append("active_weight_cut")
    if athlete_model.get("injuries") or "injury_management" in readiness_flags:
        reason_codes.append("injury_management")
    return reason_codes


def _compression_summary(reason_codes: list[str]) -> str:
    if not reason_codes:
        return ""
    label = ", ".join(code.replace("_", " ") for code in reason_codes)
    return f"Keep the smaller week on purpose to protect freshness under {label}."


def _next_training_days_after_effective_hard_spar(
    training_days: list[str],
    effective_hard_days_list: set[str],
) -> set[str]:
    if not training_days or not effective_hard_days_list:
        return set()

    next_days: set[str] = set()
    ordered_training_days = _ordered_weekdays(training_days)
    for hard_day in effective_hard_days_list:
        hard_day_index = _WEEKDAY_ORDER.get(str(hard_day).strip().lower(), -1)
        if hard_day_index < 0:
            continue
        next_day = next(
            (
                day
                for day in ordered_training_days
                if _WEEKDAY_ORDER.get(str(day).strip().lower(), -1) > hard_day_index
            ),
            None,
        )
        if next_day:
            next_days.add(next_day)
    return next_days


def _make_compression_suppression(role: dict, reason_codes: list[str], summary: str) -> dict[str, Any]:
    return {
        "category": role.get("category"),
        "role_key": role.get("role_key"),
        "preferred_system": role.get("preferred_system", ""),
        "reasons": [summary],
        "governance": dict(role.get("governance", {})),
        "intentional_compression": True,
        "compression_reason_codes": list(reason_codes),
        "compression_summary": summary,
    }


def _active_weight_cut_is_meaningful(athlete_model: dict) -> bool:
    """True when the athlete has a non-trivial active weight cut."""
    if athlete_model.get("weight_cut_risk"):
        return True
    weight_cut_pct = float(athlete_model.get("weight_cut_pct") or 0.0)
    if weight_cut_pct >= 3.0:
        return True
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    return bool(readiness_flags & {"active_weight_cut", "aggressive_weight_cut"})


def _active_injury_is_moderate_plus(athlete_model: dict) -> bool:
    """True when the athlete has an active injury or restriction at moderate or greater severity."""
    if athlete_model.get("injuries"):
        return True
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    return "injury_management" in readiness_flags


def _compute_readiness_compression(athlete_model: dict) -> int:
    """
    Compute readiness compression score (0–4) based on:
    - High fatigue (+1)
    - Meaningful active weight cut (+1)
    - Active injury/restriction at moderate or greater severity (+1)
    - Proximity to fight (≤17 days) (+1)
    """
    compression = 0
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    if fatigue == "high":
        compression += 1
    if _active_weight_cut_is_meaningful(athlete_model):
        compression += 1
    if _active_injury_is_moderate_plus(athlete_model):
        compression += 1
    days_to_fight = athlete_model.get("days_until_fight")
    if isinstance(days_to_fight, int) and 0 <= days_to_fight <= 17:
        compression += 1
    return compression


def _compression_floor_value(compression: int) -> int:
    """Convert compression score to compression_floor (number of non-spar slots to remove)."""
    if compression == 0:
        return 0
    if compression <= 2:
        return 1
    return 2  # compression >= 3


def _non_spar_role_priority_rank(
    role: dict,
    phase: str,
    is_hard_spar_week: bool,
    is_meaningful_cut: bool,
    must_keep: set[str] | None = None,
) -> int:
    """
    Return a priority rank for a non-sparring role.
    Higher rank = higher priority (kept when budget is tight).
    Must-keep roles receive the highest rank (100).
    """
    if must_keep is None:
        must_keep = set()

    role_key = str(role.get("role_key") or "").strip()
    preferred_system = str(role.get("preferred_system") or "").strip()
    category = str(role.get("category") or "").strip()

    # Must-keep roles always survive compression
    if preferred_system in must_keep or role_key in must_keep:
        return 100

    demote_glycolytic = is_hard_spar_week or is_meaningful_cut

    if phase == "GPP":
        # GPP priority (highest → lowest): primary_strength > aerobic > secondary_strength > recovery
        if role_key in {"primary_strength_day", "structural_strength_day"}:
            return 4
        if category == "conditioning" and preferred_system == "aerobic":
            return 3
        if role_key in {"aerobic_support_day", "aerobic_base_day", "aerobic_coordination_day"}:
            return 3
        if category == "strength":
            return 2
        if category == "recovery":
            return 1
        return 2  # other roles default to secondary strength level

    if phase == "SPP":
        # SPP priority (highest → lowest, normal): neural_plus > repeatability > fight_pace > recovery
        # With demote_glycolytic: fight_pace demoted to first-cut (rank 1), recovery promoted to rank 2
        if role_key == "neural_plus_strength_day":
            return 4
        if role_key == "repeatability_support_day" or (category == "conditioning" and preferred_system == "aerobic"):
            return 3
        if role_key == "fight_pace_repeatability_day" or (category == "conditioning" and preferred_system == "glycolytic"):
            return 1 if demote_glycolytic else 2
        if category == "recovery":
            return 2 if demote_glycolytic else 1
        if category == "strength":
            return 2  # secondary strength in SPP
        return 2  # other roles default

    # TAPER: alactic sharpness > aerobic support > glycolytic > recovery
    if category == "conditioning" and preferred_system == "alactic":
        return 4
    if category == "conditioning" and preferred_system == "aerobic":
        return 3
    if category == "conditioning" and preferred_system == "glycolytic":
        return 1 if demote_glycolytic else 2
    if category == "recovery":
        return 1
    return 2


def _build_spar_allocation_reason_codes(
    athlete_model: dict,
    compression: int,
    is_hard_spar_week: bool,
    is_meaningful_cut: bool,
) -> list[str]:
    reason_codes: list[str] = []
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    if fatigue == "high":
        reason_codes.append("high_fatigue")
    if is_hard_spar_week:
        reason_codes.append("two_hard_spar_days")
    if is_meaningful_cut:
        reason_codes.append("active_weight_cut")
    if _active_injury_is_moderate_plus(athlete_model):
        reason_codes.append("injury_management")
    days_to_fight = athlete_model.get("days_until_fight")
    if isinstance(days_to_fight, int) and 0 <= days_to_fight <= 17:
        reason_codes.append("proximity_to_fight")
    return reason_codes


def _apply_high_fatigue_week_compression(
    week_entry: dict,
    session_roles: list[dict],
    suppressed_roles: list[dict],
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Spar-first weekly allocation:
    1. Count sparring against the weekly cap
    2. Apply readiness compression (fatigue, weight cut, injury, proximity) to non-sparring slots only
    3. Select only the highest-priority non-sparring roles up to non_spar_target
    4. Suppress excess roles and mark intentionally unused training days
    """
    week_entry["intentional_compression"] = _intentional_compression_stub()
    if not session_roles:
        return session_roles, suppressed_roles

    compressed = athlete_model.get("compressed_priorities") or {}
    if compressed.get("is_short_camp"):
        return session_roles, suppressed_roles

    training_days = _ordered_weekdays(_clean_list(athlete_model.get("training_days", [])))
    if not training_days:
        # Without declared training days we cannot enforce the spar-first cap;
        # fall back to legacy single-role high-fatigue compression.
        return _apply_legacy_high_fatigue_compression(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )

    # Step 1: Count sparring against the weekly cap
    hard_sparring_days_set = set(_ordered_weekdays(_clean_list(athlete_model.get("hard_sparring_days", []))))
    sessions_per_week = int(athlete_model.get("training_frequency", len(training_days)))
    weekly_cap = min(sessions_per_week, len(training_days))
    locked_spar_days = {day for day in training_days if day in hard_sparring_days_set}
    spar_count = len(locked_spar_days)
    non_spar_cap = max(0, weekly_cap - spar_count)

    # Step 2: Compute readiness compression score (applied to non-sparring slots only)
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    compression = _compute_readiness_compression(athlete_model)
    compression_floor = _compression_floor_value(compression)

    # Step 3: Compute target number of non-sparring active sessions
    phase = str(week_entry.get("phase", "")).strip().upper()
    if phase in {"GPP", "SPP"}:
        min_non_spar_active = 1
    else:  # TAPER
        min_non_spar_active = 0

    if fatigue == "moderate":
        non_spar_target = non_spar_cap
    else:
        non_spar_target = max(min_non_spar_active, non_spar_cap - compression_floor)
    # Never exceed the available non-spar capacity
    non_spar_target = min(non_spar_target, non_spar_cap)

    # Separate sparring and non-sparring roles
    spar_roles = [r for r in session_roles if r.get("role_key") == "hard_sparring_day"]
    non_spar_roles = [r for r in session_roles if r.get("role_key") != "hard_sparring_day"]

    current_non_spar_count = len(non_spar_roles)
    if current_non_spar_count <= non_spar_target:
        # Already within budget – populate intentionally unused days and return
        week_entry["intentionally_unused_days"] = _compute_intentionally_unused_days(
            training_days, session_roles, has_recovery_role=any(r.get("category") == "recovery" for r in non_spar_roles),
        )
        return session_roles, suppressed_roles

    # Step 4: Pick only the highest-priority non-sparring roles
    is_hard_spar_week = len(hard_sparring_days_set) >= 2
    is_meaningful_cut = _active_weight_cut_is_meaningful(athlete_model)

    resolved_rule_state = dict(week_entry.get("resolved_rule_state") or {})
    must_keep = set(_clean_list(resolved_rule_state.get("must_keep", week_entry.get("must_keep", []))))

    ranked_roles = sorted(
        non_spar_roles,
        key=lambda r: _non_spar_role_priority_rank(r, phase, is_hard_spar_week, is_meaningful_cut, must_keep),
        reverse=True,  # highest priority first
    )

    kept_non_spar = ranked_roles[:non_spar_target]
    dropped_non_spar = ranked_roles[non_spar_target:]

    reason_codes = _build_spar_allocation_reason_codes(athlete_model, compression, is_hard_spar_week, is_meaningful_cut)
    if not reason_codes:
        reason_codes = ["spar_first_cap"]
    summary = _compression_summary(reason_codes)

    kept_roles = spar_roles + kept_non_spar
    updated_suppressed = list(suppressed_roles)
    for role in dropped_non_spar:
        updated_suppressed.append(_make_compression_suppression(role, reason_codes, summary))

    # Step 5: Identify intentionally unused training days
    has_recovery_in_kept = any(r.get("category") == "recovery" for r in kept_non_spar)
    week_entry["intentionally_unused_days"] = _compute_intentionally_unused_days(
        training_days, kept_roles, has_recovery_role=has_recovery_in_kept,
    )

    week_entry["intentional_compression"] = {
        "active": True,
        "reason_codes": list(reason_codes),
        "reason": ", ".join(reason_codes),
        "summary": summary,
    }
    return kept_roles, updated_suppressed


def _compute_intentionally_unused_days(
    training_days: list[str],
    kept_roles: list[dict],
    *,
    has_recovery_role: bool,
) -> list[dict[str, str]]:
    """
    Return the training days that are not assigned to any kept role.
    Unused days become recovery_only_day if the week has no recovery bias yet,
    otherwise off_day.
    """
    used_days: set[str] = set()
    for role in kept_roles:
        day = str(role.get("scheduled_day_hint") or "").strip()
        if day:
            used_days.add(day)
    result = []
    for day in training_days:
        if day not in used_days:
            result.append({
                "day": day,
                "role": "off_day" if has_recovery_role else "recovery_only_day",
            })
    return result


def _apply_legacy_high_fatigue_compression(
    week_entry: dict,
    session_roles: list[dict],
    suppressed_roles: list[dict],
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Legacy single-role compression used when no declared training days are available."""
    effective_hard_count = effective_hard_day_count(hard_sparring_plan or []) if hard_sparring_plan else None
    reason_codes = _high_fatigue_compression_reason_codes(
        athlete_model,
        effective_hard_spar_count=effective_hard_count,
    )
    if not reason_codes:
        return session_roles, suppressed_roles

    declared_hard_days = _ordered_weekdays(
        _clean_list(week_entry.get("declared_hard_sparring_days") or athlete_model.get("hard_sparring_days"))
    )
    resolved_rule_state = dict(week_entry.get("resolved_rule_state") or {})
    must_keep = set(_clean_list(resolved_rule_state.get("must_keep", week_entry.get("must_keep", []))))
    training_days = _ordered_weekdays(_clean_list(athlete_model.get("training_days", [])))
    effective_days = set(effective_hard_days(hard_sparring_plan or []))
    has_downgraded_declared_day = bool(declared_hard_days) and len(effective_days) < len(declared_hard_days)
    blocked_follow_on_days = _next_training_days_after_effective_hard_spar(training_days, effective_days)
    summary = _compression_summary(reason_codes)

    kept_roles = list(session_roles)
    updated_suppressed = list(suppressed_roles)

    if has_downgraded_declared_day:
        _append_week_coach_note_flag(week_entry, "deload hard sparring")

    removable_role: dict[str, Any] | None = None
    glycolytic_role = next(
        (
            role for role in kept_roles
            if role.get("category") == "conditioning" and role.get("preferred_system") == "glycolytic"
        ),
        None,
    )
    if glycolytic_role is not None and has_downgraded_declared_day:
        glycolytic_day = str(glycolytic_role.get("scheduled_day_hint") or "").strip()
        if glycolytic_day in blocked_follow_on_days and glycolytic_role.get("preferred_system") not in must_keep:
            removable_role = glycolytic_role

    if removable_role is None:
        removable_role = next(
            (
                role for role in kept_roles
                if role.get("category") == "strength" and role.get("role_key") not in _PRIMARY_STRENGTH_ROLE_KEYS
            ),
            None,
        )
    if removable_role is None:
        removable_role = next(
            (
                role for role in kept_roles
                if role.get("category") == "conditioning"
                and role.get("preferred_system") != "glycolytic"
                and role.get("preferred_system") not in must_keep
            ),
            None,
        )
    if removable_role is None:
        removable_role = next(
            (
                role for role in kept_roles
                if role.get("category") == "conditioning" and role.get("preferred_system") not in must_keep
            ),
            None,
        )
    if removable_role is None:
        recovery_roles = [role for role in kept_roles if role.get("category") == "recovery"]
        if len(recovery_roles) > 1:
            removable_role = recovery_roles[-1]

    if removable_role is None:
        return kept_roles, updated_suppressed

    kept_roles.remove(removable_role)
    updated_suppressed.append(_make_compression_suppression(removable_role, reason_codes, summary))

    week_entry["intentional_compression"] = {
        "active": True,
        "reason_codes": list(reason_codes),
        "reason": ", ".join(reason_codes),
        "summary": summary,
    }
    return kept_roles, updated_suppressed


def _fight_week_override_band(days_until_fight: Any) -> str:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return "none"
    if days < 0:
        return "none"
    if days <= 1:
        return "final_day_protocol"
    if days <= 3:
        return "micro_taper_protocol"
    if days <= 5:
        return "mini_taper_protocol"
    return "none"


def _fight_week_override_payload(days_until_fight: Any) -> dict[str, Any] | None:
    band = _fight_week_override_band(days_until_fight)
    if band == "none":
        return None

    base = {
        "active": True,
        "days_until_fight": days_until_fight,
        "band": band,
        "red_flags": ["do not chase fitness now"],
    }

    if band == "final_day_protocol":
        return {
            **base,
            "plan_mode": "readiness_protocol_only",
            "coach_note": "Fight is immediate. Do not run a normal training week or add fitness work.",
            "allowed_session_roles": [],
            "protocol": [
                "No strength work, no conditioning blocks, and no volume accumulation.",
                "Optional short neural primer only if movement quality is crisp and fatigue is low.",
                "Use mobility, activation, breathing, and short shakeout only.",
                "Include hydration, fuel, sleep, and weight-cut execution reminders.",
                "Today should usually be warm-up guidance, activation, mental cues, and post-fight recovery/refuel notes only.",
            ],
        }

    if band == "micro_taper_protocol":
        return {
            **base,
            "plan_mode": "micro_taper_only",
            "coach_note": "Use a micro-taper only. Do not render a normal weekly build.",
            "allowed_session_roles": ["alactic_sharpness_day", "fight_week_freshness_day"],
            "max_sessions": 2,
            "protocol": [
                "At most one short primer session plus one light mobility/recovery session.",
                "No hard conditioning, no muscle-damaging lifts, and no new drills.",
                "Keep intensity sharp and volume tiny to arrive fresh.",
            ],
        }

    return {
        **base,
        "plan_mode": "mini_taper_only",
        "coach_note": "Use a mini taper only. Do not render a full normal week.",
        "allowed_session_roles": ["neural_primer_day", "alactic_sharpness_day", "fight_week_freshness_day"],
        "max_sessions": 3,
        "protocol": [
            "Reduce volume and keep only high-value sharpness exposures.",
            "Preserve speed, timing, and rhythm with one to two key sessions.",
            "Allow only very low-cost conditioning if truly needed.",
        ],
    }


def _build_weekly_role_map(
    athlete_model: dict,
    week_by_week_progression: dict,
    limiter_profile: dict,
    fight_week_override: dict[str, Any] | None = None,
) -> dict:
    weeks: list[dict] = []
    limiter_key = limiter_profile.get("key", "general_fight_readiness")

    for week_entry in week_by_week_progression.get("weeks", []):
        session_counts = dict(week_entry.get("session_counts") or {})
        conditioning_sequence = list(week_entry.get("conditioning_sequence", [])) or ["aerobic", "glycolytic", "alactic"]
        sport_key = _athlete_sport_key(athlete_model)
        if sport_key == "boxing" and week_entry.get("phase", "").upper() in {"GPP", "SPP"} and int(session_counts.get("conditioning", 0) or 0) >= 2:
            conditioning_sequence = _preferred_boxer_conditioning_sequence(
                week_entry.get("phase", ""),
                conditioning_sequence,
            )
        session_roles: list[dict] = []
        suppressed_roles: list[dict] = []
        session_index = 1

        for idx in range(max(0, int(session_counts.get("strength", 0)))):
            role_key = _strength_role_key(
                week_entry.get("phase", ""),
                week_entry.get("stage_key", ""),
                limiter_key,
                idx,
            )
            anchor = _role_anchor(role_key)
            governance = _role_governance(
                week_entry,
                category="strength",
                role_key=role_key,
                athlete_model=athlete_model,
                idx=idx,
            )
            if governance["hard_suppression_reasons"]:
                suppressed_roles.append(
                    {
                        "category": "strength",
                        "role_key": role_key,
                        "reasons": governance["hard_suppression_reasons"],
                        "governance": governance,
                    }
                )
                continue
            session_roles.append(
                {
                    "session_index": session_index,
                    "category": "strength",
                    "role_key": role_key,
                    "preferred_pool": "strength_slots",
                    "selection_rule": _role_selection_rule(role_key, "strength"),
                    "anchor": anchor,
                    "placement_rule": _placement_rule_for_anchor(anchor, week_entry),
                    "governance": governance,
                }
            )
            session_index += 1

        conditioning_count = max(0, int(session_counts.get("conditioning", 0)))
        for idx in range(conditioning_count):
            system = conditioning_sequence[idx] if idx < len(conditioning_sequence) else conditioning_sequence[-1]
            role_key = _conditioning_role_key(week_entry.get("phase", ""), system, limiter_key)
            anchor = _role_anchor(role_key)
            governance = _role_governance(
                week_entry,
                category="conditioning",
                role_key=role_key,
                athlete_model=athlete_model,
                system=system,
                idx=idx,
            )
            if governance["hard_suppression_reasons"]:
                suppressed_roles.append(
                    {
                        "category": "conditioning",
                        "role_key": role_key,
                        "preferred_system": system,
                        "reasons": governance["hard_suppression_reasons"],
                        "governance": governance,
                    }
                )
                continue
            session_roles.append(
                {
                    "session_index": session_index,
                    "category": "conditioning",
                    "role_key": role_key,
                    "preferred_pool": "conditioning_slots",
                    "preferred_system": system,
                    "selection_rule": _role_selection_rule(role_key, "conditioning", system),
                    "anchor": anchor,
                    "placement_rule": _placement_rule_for_anchor(anchor, week_entry),
                    "governance": governance,
                }
            )
            session_index += 1

        for idx in range(max(0, int(session_counts.get("recovery", 0)))):
            role_key = _recovery_role_key(
                week_entry.get("phase", ""),
                week_entry.get("stage_key", ""),
                athlete_model,
            )
            anchor = _role_anchor(role_key)
            governance = _role_governance(
                week_entry,
                category="recovery",
                role_key=role_key,
                athlete_model=athlete_model,
                idx=idx,
            )
            session_roles.append(
                {
                    "session_index": session_index,
                    "category": "recovery",
                    "role_key": role_key,
                    "preferred_pool": "rehab_slots_or_recovery_only",
                    "selection_rule": _role_selection_rule(role_key, "recovery"),
                    "anchor": anchor,
                    "placement_rule": _placement_rule_for_anchor(anchor, week_entry),
                    "governance": governance,
                }
            )
            session_index += 1

        session_roles, suppressed_roles = _apply_short_camp_role_compression(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
        )
        hard_sparring_plan = compute_hard_sparring_plan(
            week={
                "phase": week_entry.get("phase"),
                "stage_key": week_entry.get("stage_key"),
                "week_index": week_entry.get("week_index"),
                "declared_hard_sparring_days": _ordered_weekdays(_clean_list(athlete_model.get("hard_sparring_days", []))),
                "session_roles": session_roles,
            },
            athlete_snapshot=athlete_model,
        )
        effective_days = effective_hard_days(hard_sparring_plan)
        week_entry["hard_sparring_plan"] = hard_sparring_plan
        week_entry["effective_hard_sparring_days"] = list(effective_days)
        week_entry["intentional_compression"] = _intentional_compression_stub()
        week_entry["coach_note_flags"] = _dedupe_clean_strings(
            [
                flag
                for entry in hard_sparring_plan
                for flag in _hard_sparring_coach_note_flags(entry)
            ]
        )

        session_roles = _resequence_session_roles(
            week_entry,
            session_roles,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
        session_roles, suppressed_roles = _lock_declared_hard_sparring_roles(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
        session_roles, suppressed_roles = _apply_high_fatigue_week_compression(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
        session_roles, suppressed_roles = _lock_declared_hard_sparring_roles(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
        session_roles = _resequence_session_roles(
            week_entry,
            session_roles,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )

        weeks.append(
            {
                "week_index": week_entry.get("week_index"),
                "phase": week_entry.get("phase"),
                "stage_key": week_entry.get("stage_key"),
                "phase_week_index": week_entry.get("phase_week_index"),
                "phase_week_total": week_entry.get("phase_week_total"),
                "declared_training_days": _ordered_weekdays(_clean_list(athlete_model.get("training_days", []))),
                "declared_hard_sparring_days": _ordered_weekdays(_clean_list(athlete_model.get("hard_sparring_days", []))),
                "declared_technical_skill_days": _ordered_weekdays(_clean_list(athlete_model.get("technical_skill_days", []))),
                "hard_sparring_plan": hard_sparring_plan,
                "effective_hard_sparring_days": list(effective_days),
                "coach_note_flags": _dedupe_clean_strings(_clean_list(week_entry.get("coach_note_flags", []))),
                "intentional_compression": dict(week_entry.get("intentional_compression") or _intentional_compression_stub()),
                "intentionally_unused_days": list(week_entry.get("intentionally_unused_days") or []),
                "session_roles": session_roles,
                "suppressed_roles": suppressed_roles,
            }
        )

    if fight_week_override and fight_week_override.get("active"):
        band = str(fight_week_override.get("band") or "")
        if band == "final_day_protocol":
            weeks = []
        else:
            allowed_roles = set(_clean_list(fight_week_override.get("allowed_session_roles", [])))
            max_sessions = int(fight_week_override.get("max_sessions") or 0)
            trimmed_weeks: list[dict] = []
            if weeks:
                week = dict(weeks[0])
                roles = list(week.get("session_roles") or [])
                filtered_roles = [role for role in roles if role.get("role_key") in allowed_roles]
                if max_sessions > 0:
                    filtered_roles = filtered_roles[:max_sessions]
                week["session_roles"] = filtered_roles
                suppressed_roles = list(week.get("suppressed_roles") or [])
                suppressed_roles.append(
                    {
                        "category": "plan",
                        "role_key": "fight_week_override",
                        "reasons": [str(fight_week_override.get("coach_note") or "fight-week override active")],
                    }
                )
                week["suppressed_roles"] = suppressed_roles
                week["coach_note_flags"] = _dedupe_clean_strings(
                    _clean_list(week.get("coach_note_flags", [])) + ["fight-week override active"]
                )
                week["intentional_compression"] = {
                    "active": True,
                    "reason_codes": ["fight_week_override"],
                    "reason": "fight_week_override",
                    "summary": str(fight_week_override.get("coach_note") or "fight-week override active"),
                }
                trimmed_weeks = [week]
            weeks = trimmed_weeks

    return {
        "model": "session_role_overlay.v1",
        "source_of_truth": [
            "Session roles inherit week-by-week progression rather than replacing phase logic.",
            "Session counts come from existing deterministic phase session allocation.",
            "Anchors inherit the weekly stress map so phase guardrails, safety, and sport-load rules keep priority.",
            "Weekly roles are an execution layer only and cannot overrule the planning hierarchy.",
        ],
        "fight_week_override": fight_week_override or {"active": False},
        "weeks": weeks,
    }
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
    hard_sparring_days = _clean_list(athlete_model.get("hard_sparring_days", []))
    technical_skill_days = _clean_list(athlete_model.get("technical_skill_days", []))
    high_pressure_cut = _is_high_pressure_weight_cut(athlete_model=athlete_model)
    compressed = athlete_model.get("compressed_priorities") or {}
    primary_labels = _priority_bucket_labels(compressed.get("primary_targets", []))
    maintenance_labels = _priority_bucket_labels(compressed.get("maintenance_targets", []))
    embedded_labels = _priority_bucket_labels(compressed.get("embedded_support", []))
    deferred_labels = _priority_bucket_labels(compressed.get("deferred", []))

    if injuries:
        preserve.append("Keep rehab continuity and remove only clearly conflicting work.")
        avoid.append("Do not keep drills that mechanically overlap the injured pattern just because they sound different.")
    if athlete_model.get("weight_cut_risk"):
        preserve.append("Keep recovery spacing and low-damage conditioning alive while cut stress is active.")
        preserve.append("Protect strength and speed quality by keeping fueling support around key sessions.")
        avoid.append("Avoid unnecessary soreness-heavy conditioning, glycolytic density, or accessory volume during the cut.")
        if high_pressure_cut:
            preserve.append("Preserve freshness first when cut pressure is high.")
            avoid.append("Do not spend cut margin on optional fatigue that does not directly support the fight.")
    if "conditioning" in goals:
        push.append("Prioritize conditioning slots that match the phase objective before extra accessories.")
    if "power" in goals:
        push.append("Preserve explosive and alactic work if compliant options remain.")
    if athlete_model.get("weight_cut_risk"):
        push.append("Choose the crispest high-value work and trim optional fatigue before it blunts strength expression or conditioning tolerance.")
    if hard_sparring_days:
        preserve.append("Let declared hard sparring own the highest collision combat load before adding extra glycolytic stress.")
        push.append("Keep the primary neural strength day away from declared hard sparring when a cleaner weekly placement exists.")
        avoid.append("Do not stack the main glycolytic stressor directly beside declared hard sparring unless the schedule truly forces it.")
    if technical_skill_days:
        preserve.append("Use declared technical skill days for lower-noise support work when the weekly rhythm needs a lighter combat touch.")
    if compressed.get("is_short_camp"):
        preserve.append(
            f"Keep the week selective by driving sessions from {', '.join(primary_labels)} and at most one maintenance target."
        )
        avoid.append("Do not turn every selected goal or weakness into its own session objective inside a short camp.")
        if maintenance_labels:
            push.append(f"Keep {maintenance_labels[0]} to one small exposure instead of a full extra emphasis day.")
        if embedded_labels:
            avoid.append(f"Treat {', '.join(embedded_labels)} as embedded support through warm-up, recovery, or drill selection.")
        if deferred_labels:
            avoid.append(f"Defer {', '.join(deferred_labels)} as standalone objectives in this short window.")

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


def _resolve_visible_phase_framing(phase: str, brief: dict, week_by_week_progression: dict) -> dict[str, str]:
    weeks = [
        week
        for week in (week_by_week_progression.get("weeks", []) or [])
        if week.get("phase") == phase
    ]
    if len(weeks) != 1:
        return {
            "label": phase,
            "objective": brief.get("objective", ""),
        }

    week = weeks[0]
    return {
        "label": week.get("stage_label") or phase,
        "objective": week.get("stage_objective") or brief.get("objective", ""),
    }


def _build_phase_strategy(
    phase_briefs: dict[str, dict],
    candidate_pools: dict[str, dict],
    week_by_week_progression: dict,
) -> dict[str, dict]:
    strategy: dict[str, dict] = {}
    for phase, brief in phase_briefs.items():
        pool = candidate_pools.get(phase, {})
        visible_framing = _resolve_visible_phase_framing(phase, brief, week_by_week_progression)
        strategy[phase] = {
            "objective": brief.get("objective", ""),
            "visible_label": visible_framing["label"],
            "visible_objective": visible_framing["objective"],
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
    athlete_model = dict(athlete_model)
    athlete_model["compressed_priorities"] = athlete_model.get("compressed_priorities") or _compress_short_camp_priorities(
        athlete_model
    )
    limiter_profile = _build_limiter_profile(athlete_model, restrictions)
    sport_load_profile = _build_sport_load_profile(athlete_model)
    weekly_stress_map = _build_weekly_stress_map(
        athlete_model,
        phase_briefs,
        limiter_profile,
        sport_load_profile,
    )
    week_by_week_progression = _build_week_by_week_progression(
        athlete_model,
        phase_briefs,
        weekly_stress_map,
    )
    fight_week_override = _fight_week_override_payload(athlete_model.get("days_until_fight"))
    weekly_role_map = _build_weekly_role_map(
        athlete_model,
        week_by_week_progression,
        limiter_profile,
        fight_week_override=fight_week_override,
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
        "compressed_priorities": athlete_model.get("compressed_priorities", {}),
        "limiter_profile": limiter_profile,
        "sport_load_profile": sport_load_profile,
        "decision_hierarchy": PLANNING_DECISION_HIERARCHY,
        "main_risks": _derive_main_risks(athlete_model, restrictions),
        "global_priorities": _derive_global_priorities(athlete_model, phase_briefs, candidate_pools),
        "phase_strategy": _build_phase_strategy(phase_briefs, candidate_pools, week_by_week_progression),
        "weekly_stress_map": weekly_stress_map,
        "week_by_week_progression": week_by_week_progression,
        "fight_week_override": fight_week_override or {"active": False},
        "weekly_role_map": weekly_role_map,
        "restrictions": restrictions,
        "candidate_pools": candidate_pools,
        "omission_ledger": omission_ledger,
        "decision_rules": rewrite_guidance,
    }

def _serialize_strength_option(exercise: dict, why: str) -> dict:
    movement = str(exercise.get("movement", "")).strip().lower().replace(" ", "_")
    movement_patterns = [movement] if movement else []
    movement_patterns.extend(_clean_list(exercise.get("tags", [])))
    quality_profile = classify_strength_item(exercise)
    required_equipment = _clean_list(exercise.get("required_equipment") or exercise.get("equipment", []))
    return {
        "name": exercise.get("name", "Unnamed"),
        "source": "exercise_bank",
        "movement_patterns": _dedupe_preserve_order(movement_patterns),
        "restriction_tags": _extract_restriction_tags(exercise),
        "mechanical_risk_tags": _extract_mechanical_risk_tags(exercise),
        "prescription": exercise.get("prescription") or exercise.get("method") or "",
        "why": why or "balanced selection",
        "quality_class": quality_profile["quality_class"],
        "anchor_capable": quality_profile["anchor_capable"],
        "support_only": quality_profile["support_only"],
        "base_categories": quality_profile["base_categories"],
        "required_equipment": required_equipment,
        "universally_available": not required_equipment or set(required_equipment).issubset({"bodyweight"}),
        "generic_fallback": bool(exercise.get("generic_fallback")),
    }


def _serialize_conditioning_option(drill: dict, system: str, why: str) -> dict:
    tags = _clean_list(drill.get("tags", []))
    required_equipment = _clean_list(drill.get("required_equipment") or drill.get("equipment", []))
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
        "required_equipment": required_equipment,
        "universally_available": not required_equipment or set(required_equipment).issubset({"bodyweight"}),
        "generic_fallback": bool(drill.get("generic_fallback")),
        "availability_contingency_reason": drill.get("availability_contingency_reason") or "",
        "session_index": drill.get("session_index"),
    }


def _serialize_rehab_option(prescription: str, *, role: str, source: str, why: str, function_class: str = "") -> dict:
    name = re.split(r"\s+(?:[\u2013-]|\u00e2\u20ac\u201c)\s+", prescription, maxsplit=1)[0].strip()
    # Strip any inline [Function: X] tag from the display name
    name = re.sub(r"\s*\[Function:[^\]]*\]", "", name).strip()
    fc = function_class or classify_drill_function(name, prescription)
    function_label = _FUNCTION_LABELS.get(fc, fc.replace("_", " ").title())
    return {
        "name": name or "Rehab Drill",
        "source": source,
        "movement_patterns": [role],
        "restriction_tags": ["rehab", role],
        "mechanical_risk_tags": ["rehab", role],
        "prescription": prescription,
        "why": why,
        "function_class": fc,
        "rehab_function_label": function_label,
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
    exercises = list(strength_block.get("exercises", []))
    selected_names = {
        exercise.get("name")
        for exercise in exercises
        if exercise.get("name")
    }
    sessions = infer_strength_sessions(exercises, strength_block.get("num_sessions", 1))
    position_to_session: dict[int, int] = {}
    for session in sessions:
        for position in session.get("positions", []):
            position_to_session[position] = session.get("session_index", 1)
    slots: list[dict] = []
    for idx, exercise in enumerate(exercises, start=1):
        name = exercise.get("name")
        if not name:
            continue
        reasons = reason_lookup.get(name, {})
        movement = str(exercise.get("movement", "")).strip().lower().replace(" ", "_")
        role = movement or "strength_support"
        quality_profile = classify_strength_item(exercise)
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
                "session_index": position_to_session.get(idx - 1, 1),
                "quality_class": quality_profile["quality_class"],
                "anchor_capable": quality_profile["anchor_capable"],
                "support_only": quality_profile["support_only"],
                "base_categories": quality_profile["base_categories"],
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
                    "session_index": int(drill.get("session_index", idx) or idx),
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
        # "Why today" framing: the selected drill carries phase + issue context.
        # Stage 2 is expected to enrich this with day-type reasoning.
        phase_context = f"{phase} phase" if phase else "current phase"
        why_today_template = (
            f"Targets {location.lower()} {injury_type.lower()} during {phase_context}. "
            "When scheduling, state why this drill appears on this specific day type "
            "(e.g. pre-sparring activation, post-strength reset, aerobic-day tolerance work)."
        )
        # Track function classes already represented in selected drills so
        # alternates are scored toward function diversity — not hard-blocked.
        selected_functions = {
            classify_drill_function(line) for line in selected_lines
        }
        for idx, line in enumerate(selected_lines, start=1):
            drill_func = classify_drill_function(line)
            function_label = _FUNCTION_LABELS.get(drill_func, drill_func.replace("_", " ").title())
            # Collect candidate alternates, preferring drills from different function buckets.
            # We gather up to 4 candidates so diversity sorting has enough to work with.
            scored_alternates: list[tuple[int, dict]] = []
            for option in rehab_options:
                if option == line or option in selected_set:
                    continue
                opt_func = classify_drill_function(option)
                # Prefer function diversity, but do not hard-block same-function
                # alternates — the model may choose any of them with good reason.
                priority_score = 0 if opt_func not in selected_functions else 1
                scored_alternates.append(
                    (
                        priority_score,
                        _serialize_rehab_option(
                            option,
                            role=role,
                            source="rehab_bank",
                            why=why_today_template,
                            function_class=opt_func,
                        ),
                    )
                )
                if len(scored_alternates) >= 4:
                    break
            # Sort by priority score (diverse-function first) then take top 2.
            top_alternates = [opt for _, opt in sorted(scored_alternates, key=lambda x: x[0])][:2]
            slots.append(
                {
                    "slot_id": f"{phase.lower()}_{role}_{idx}_{_slugify(line)}",
                    "role": role,
                    "purpose": why_today_template,
                    "function_class": drill_func,
                    "rehab_function_label": function_label,
                    "selected": _serialize_rehab_option(
                        line,
                        role=role,
                        source="rehab_block",
                        why=why_today_template,
                        function_class=drill_func,
                    ),
                    "alternates": top_alternates,
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
            "Prefer selected items first only if they remain strong and compliant.",
            "If a selected item is removed, replace with the strongest compliant same-role option first.",
            "Do not let support drills take over anchor slots when stronger compliant options exist.",
            "Treat option mechanical_risk_tags plus restriction blocked_patterns/mechanical_equivalents as hard clues for mechanically equivalent matches.",
            "Do not invent new items when a strong compliant option already exists in the pool.",
            "Keep every final primary drill, support drill, and fallback equipment-valid for the athlete profile.",
            "Only keep an explicit fallback when a real unresolved access or availability contingency still exists.",
            "If declared hard sparring days exist, treat them as fixed collision points when placing the main glycolytic stressor or primary neural strength session.",
        ],
        "writing_rules": [
            "Keep the final plan athlete-facing and clean.",
            "Do not mention excluded items.",
            "Preserve phase objectives when rewriting text.",
            "For any corrective or adjustment line, make one clear coaching call instead of defaulting to hedged advice.",
            "Prefer command-then-reason on corrective lines; do not lead with explanation and then soften it into a suggestion.",
            "Keep rationale short and tie it to performance, safety, readiness, or the week's main objective.",
            "Do not start corrective lines with generic openers such as 'focus on', 'ensure', 'make sure', or 'it's important to'; start with the action.",
            "Use autonomy-supportive phrasing only within real guardrails; if choice is safe and useful, offer at most two practical options, and only when both options are safe and materially equivalent for the day's goal.",
            "Replace generic motivation, empty empathy, and boilerplate safety reminders with concrete next-action language.",
            "Do not use generic motivation such as 'stay consistent', 'trust the process', 'push yourself', or 'you've got this'.",
            "Do not use empty safety lines such as 'listen to your body', 'be careful', or 'avoid overtraining' unless they are followed by a concrete rule, symptom trigger, or plan change.",
            "Aim critique at the plan, load, or execution issue, never at the athlete's character.",
            "Keep high-value isometrics when they fit, but do not let them default to anchor status if a stronger compliant loaded option exists.",
            "For conditioning, give one primary prescription and at most one explicit fallback.",
            "Collapse internal template/menu options into one final prescription whenever the athlete context already resolves the choice.",
            "Keep every active week present and structurally complete, including late-camp weeks.",
            "For boxer weeks, keep the default rhythm of support strength, low-damage conditioning, recovery, primary strength, then the main phase-specific conditioning stressor unless a stronger planning rule forces a change.",
            "Do not echo Primary, Fallback, Drill, or option-menu labels across most session lines.",
            "Avoid low-trust filler such as 'listen to your body', 'stay consistent', 'stay motivated', or 'you've got this' unless it is immediately made specific and operational.",
            "Use simple session titles such as Strength, Recovery, Aerobic support, Fight-pace conditioning, Alactic sharpness, or Neural primer.",
            "In taper weeks, remove optional branches aggressively and keep the work short, final, and low-noise.",
            "If the athlete's declared equipment already resolves the choice, do not show a fallback branch.",
            "If declared hard sparring or technical skill days exist, use them to make the weekly rhythm more concrete instead of writing generic sparring caveats.",
            "Treat declared hard sparring days in weekly_role_map as immutable hard_sparring_day slots. If readiness is compromised, deload the sparring dose on that day instead of replacing the day role.",
            "Respect the weekly session count implied by weekly_role_map; do not turn extra available days into extra active training days.",
            "If the athlete has more available days than planned sessions, leave the spare days off or clearly optional rather than rendering another full session.",
            "If weekly_role_map or week_by_week_progression marks intentional_compression.active, keep that smaller week on purpose and do not restore the suppressed standalone role.",
            "In camps with 7 days or less to fight, only the compressed week-level priorities may drive standalone session purposes; keep all other selections as support, maintenance, or deferred notes only.",
            "When fight_week_override.active is true, treat it as mandatory. For 0-1 days, output readiness protocol notes only with no training week. For 2-3 days, output micro-taper only (one short primer max + one light recovery session). For 4-5 days, output mini taper only (freshness-first, minimal volume).",
            "If active weight cut is present, explicitly acknowledge that cut stress changes recovery and training tolerance in the athlete-facing plan.",
            "Never state 'weight cut none active' or 'recovery tolerance is standard' when readiness flags or weight_cut_pct indicate an active cut.",
            "If the cut is high-pressure, include one short summary-level note plus one support-level note; do not bury it only in the athlete profile or nutrition numbers.",
            "Use athlete_model.competitive_maturity only to calibrate wording specificity; it must not change workload, session count, recovery assumptions, or injury/cut conservatism.",
            "If fatigue is high or fight-week pressure is active, reduce optionality and make the directive plain.",
            "If injury management is active, lead with constraints, substitutions, or stop rules instead of optional language.",
            "If active weight cut is present, keep the language shorter, safety-first, and non-negotiable about recovery margin.",
            "Vary sentence openings and cut repeated filler reminders so the final plan reads like a coach's final prescription, not a template.",
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

STAGE2_FINALIZER_PROMPT = """You are Stage 2 (planner/finalizer).

Input = PLANNING BRIEF + Stage 1 draft plan + athlete profile + restrictions + candidate pools.

SOURCE OF TRUTH
1. PLANNING BRIEF = primary authority for athlete intent, phase strategy, priorities, and risks.
2. Restrictions = hard constraints.
3. Candidate pools = preferred exercise reservoir.
4. Stage 1 draft = raw material only, not final authority.

RULE 1 - HARD FILTER
Remove any exercise, drill, or prescription that violates any restriction, including synonyms and mechanically equivalent patterns.
Apply this to strength, conditioning, rehab, warm-ups, finishers, and any new item considered.
Do not modify a violating item into compliance. Replace it or drop it.

RULE 2 - PLAN THE CAMP, DON'T JUST EDIT
Build the best final plan from the PLANNING BRIEF.
Use week_by_week_progression and weekly_role_map to sequence the camp.
You may reorganize sessions, simplify sections, tighten phase focus, and improve sequencing if the result is more coherent and still consistent with the planning brief and restrictions.

RULE 3 - SELECTION ORDER
Prefer:
1. strong compliant Stage 1 items
2. same-role compliant alternates from candidate pools
3. other compliant options from candidate pools

Do not keep a weak Stage 1 choice just because it already exists.

RULE 4 - ANCHOR SESSION STANDARD
Each weekly anchor strength/power session must contain at least one serious high-transfer strength or power exercise if a compliant option exists for the athlete's sport, phase, equipment, and injury profile.
Do not build anchor sessions mostly from bird dogs, dead bugs, planks, carries, bridge holds, breathing drills, mobility, or rehab-level work unless restrictions clearly force that outcome.
Support work may assist the anchor. It cannot become the anchor.

RULE 5 - SAFE STRONG, NOT SAFE SOFT
Do not confuse tissue protection with undertraining.
In GPP and SPP, choose the safest strong option, not the safest soft option.
If a compliant loaded pattern exists, prefer it over low-output filler for key slots.

RULE 6 - SPORT SPECIFICITY
The final plan must look like a real combat-sport camp for this athlete, not generic athletic work.
Conditioning, power work, weekly rhythm, and taper choices must clearly match the athlete's sport, style, fatigue state, injury context, equipment access, and phase priorities.

RULE 7 - SUPPORT WORK STAYS IN SUPPORT ROLE
Rehab, isometrics, carries, trunk stability, breathing, mobility, and tissue-protection work should support the plan, not dominate it, unless the planning brief clearly requires a protection-first camp.
If volume must be cut, cut accessory/support work first.

RULE 8 - EQUIPMENT CONGRUENCE
Every primary drill, support drill, and fallback must be valid for the athlete's declared equipment access unless an explicit contingency note says otherwise.
If the athlete profile already resolves the access question, render only the resolved option.

RULE 9 - REPLACEMENTS MUST IMPROVE QUALITY
When removing weak or violating items, replace them with stronger compliant options, not weaker support work.
Do not leave unresolved access branches when one valid choice is already obvious from the athlete profile.

RULE 10 - TAPER DISCIPLINE
In taper weeks, simplify aggressively.
Remove novelty, reduce accessory volume, avoid soreness-inducing density, and keep only the most useful sharpness, rhythm, confidence, and freshness work.
Do not render taper sessions as option menus or branching templates.
In normal taper sessions, resolve to one final prescription with no default fallback branch.
If planning_brief.fight_week_override.active is true, follow it as a hard override:
- 0-1 days: no training week; output coach note plus readiness protocol only.
- 2-3 days: micro-taper only (one short primer max + one light mobility/recovery session).
- 4-5 days: mini taper only (freshness-first, reduced volume, 1-2 sharpness sessions).
Never chase fitness in these windows.

RULE 11 - OUTPUT DISCIPLINE
Keep the athlete-facing output concise, high-signal, and easy to scan.
Minimize repetition.
Cut filler, duplication, and generic coaching reminders.
Keep coaching notes short and only where session-critical.
Coach voice should feel decisive, respectful, and gym-realistic.
For any corrective or adjustment line, make the call, give a short why, and then the next action.
Prefer command then reason, not explanation then suggestion.
Do not open corrective lines with 'focus on', 'ensure', 'make sure', or 'it's important to'. Start with the action.
Use autonomy-supportive phrasing only when a real safe choice exists; if so, offer at most two practical options, and only when both are safe and materially equivalent.
Do not rely on generic motivation such as 'stay consistent', 'trust the process', 'push yourself', or 'you've got this'.
Do not use empty safety boilerplate such as 'listen to your body', 'be careful', or 'avoid overtraining' unless the line adds a concrete rule, symptom trigger, or plan change.
Do not aim critique at the athlete's character.
Collapse templates into one final prescription whenever the athlete context already resolves the choice.
Do not repeat Primary, Fallback, Drill, or menu-style labels across most session lines.
Allow at most one explicit fallback in a session, and only when absolutely necessary.
Treat declared hard sparring days in weekly_role_map as immutable hard_sparring_day slots. If readiness is compromised, deload the sparring dose on that day instead of replacing the day role.
Do not exceed the weekly session count implied by weekly_role_map. If the athlete has extra available days, leave them off or clearly optional instead of turning them into extra active sessions.
Keep every active week present and structurally complete, including late-camp weeks.
If weekly_role_map or week_by_week_progression marks intentional_compression.active, keep that smaller week on purpose and do not restore the suppressed standalone role.
For boxer weeks, keep the default rhythm of support strength, low-damage conditioning, recovery, primary strength, then the main phase-specific conditioning stressor unless a stronger planning rule forces a change.
Use simple session titles and coach-readable drill labels, but do not spend this pass flattening non-standard names if the drill description is already mechanically clear.
If fatigue is high or fight-week pressure is active, reduce optionality and make the safest performance-preserving call plainly.
If injury management is active, lead with constraints, substitutions, or stop rules rather than optional language.
If active weight cut is present, say so plainly in the final plan and explain that it tightens recovery and training tolerance.
Never write 'weight cut none active' or 'recovery tolerance is standard' when active weight-cut flags are present.
If active weight cut is present, keep the wording shorter and safety-first rather than optimization-heavy.
If the cut is high-pressure, include one short summary-level note plus one support-level note; do not bury it only in the athlete profile or raw nutrition numbers.
In short camps, every rendered session must map to one compressed week-level priority from the planning brief. Do not create a standalone session purpose for embedded-support or deferred items.

RULE 12 - SURGICAL REHAB INTEGRATION
Rehab must never feel copy-pasted, generic, or repeated by default.
You have full authority to choose, adjust, or remove any rehab item from the candidate pools based on athlete context.
Use the function_class tags (activation / control / isometric_analgesia / mobility / tendon_loading / recovery_downregulation) as scoring guidance — not hard constraints. A drill may repeat across sessions if it serves a meaningfully different role.
A session should usually contain only 1–2 rehab functions and 5–10 minutes of total rehab work.
Hard sparring days: minimal rehab only (at most 1 drill — low-volume activation or a brief post-session reset if needed; nothing that competes with freshness).
Strength/power days: choose rehab that prepares the specific risk point for the main lift (e.g. glute activation before unilateral lower-body, scap prep before pressing).
Aerobic/recovery days: rehab may be slightly more developmental (tissue tolerance, control, mobility, low-load patterning).

For every rehab item you keep or add, render it in this format:
  • [Drill name] — [Dose]
    Purpose: [what exact mechanism this addresses — reference the specific limitation, not just the body part]
    Why today: [why this drill appears on this specific day type — pre-sparring activation / post-strength reset / aerobic-day tolerance / recovery reset / etc.]

If a drill repeats across sessions, the Why today line must make the changed role explicit (e.g. "activation before unilateral lower-body work" vs "downregulation after high-volume sparring"). Identical role + identical drill on multiple days requires explicit justification in the Why today line.

Use precise mechanism wording: "hip flexor irritation under loaded unilateral patterns", "ankle instability during stance changes", not "hip rehab" or "shoulder activation".

Before finalizing any rehab item, ask:
1. What exact issue is this solving?
2. Why is it on this day specifically?
3. Does it duplicate a rehab item already used this week with the same role?
4. Is this the lowest effective dose?
5. Would this still look intentional if the athlete read it line by line?
If any rehab item fails three or more of these checks, remove or replace it.

Do not add rehab as filler. The model retains explicit authority to add, adjust, repeat, or remove any rehab item when the athlete context justifies it.

OUTPUT
Return a clean athlete-facing final plan that is:
- concise
- coach-readable
- sport-specific
- restriction-compliant
- internally coherent
- phase-appropriate

Preserve the best of Stage 1, but remove weak exercise choices, filler, poor sequencing, underpowered anchor sessions, unresolved access branches, and incomplete late-camp weeks.
"""


def _json_block(value: dict | list) -> str:
    return "```json\n" + json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n```"


def _athlete_profile_block(planning_brief: dict | None, stage2_payload: dict) -> dict:
    if isinstance(planning_brief, dict):
        athlete_snapshot = planning_brief.get("athlete_snapshot")
        if isinstance(athlete_snapshot, dict):
            return athlete_snapshot
        athlete_model = planning_brief.get("athlete_model")
        if isinstance(athlete_model, dict):
            return athlete_model
    athlete_model = stage2_payload.get("athlete_model")
    return athlete_model if isinstance(athlete_model, dict) else {}


def build_stage2_handoff_text(
    *,
    stage2_payload: dict,
    plan_text: str,
    coach_notes: str = "",
    planning_brief: dict | None = None,
) -> str:
    context_block = planning_brief or {
        "athlete_snapshot": stage2_payload.get("athlete_model", {}),
        "restrictions": stage2_payload.get("restrictions", []),
        "phase_briefs": stage2_payload.get("phase_briefs", {}),
        "candidate_pools": stage2_payload.get("candidate_pools", {}),
        "omission_ledger": stage2_payload.get("omission_ledger", {}),
        "decision_rules": stage2_payload.get("rewrite_guidance", {}),
    }
    athlete_profile = _athlete_profile_block(planning_brief, stage2_payload)
    sections = [
        STAGE2_FINALIZER_PROMPT.strip(),
        "PLANNING BRIEF\n" + _json_block(context_block),
        "ATHLETE PROFILE\n" + _json_block(athlete_profile),
    ]
    cleaned_notes = (coach_notes or "").strip()
    if cleaned_notes:
        sections.append("COACH NOTES\n" + cleaned_notes)
    sections.append("STAGE 1 DRAFT PLAN\n" + (plan_text or "").strip())
    return "\n\n---\n\n".join(section for section in sections if section.strip())
