"""Athlete model, phase briefs, limiter profile, sport-load profile, and
weekly stress map — the first layer of the Stage 2 planning brief.

All public functions here are re-exported from stage2_payload for
backward compatibility.
"""
from __future__ import annotations

import re
from typing import Any

from .input_parsing import _athlete_calendar_now, _utc_now
from .normalization import clean_list, normalize_text, phrase_in_text, slugify, dedupe_preserve_order
from .restriction_parsing import CANONICAL_RESTRICTIONS
from .training_context import TrainingContext, allocate_sessions


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
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
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
    # We define plan_creation_weekday as athlete-local weekday so late-fight
    # weekday mapping remains aligned with the athlete calendar.
    plan_creation_dt = _athlete_calendar_now(training_context.athlete_timezone, now_utc=_utc_now())
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
        "mental_blocks": clean_list(training_context.mental_block),
        "equipment": training_context.equipment,
        "training_frequency": training_context.training_frequency,
        "training_days": training_context.training_days,
        "hard_sparring_days": training_context.hard_sparring_days,
        "technical_skill_days": training_context.technical_skill_days,
        "training_preference": training_context.training_preference,
        "injuries": training_context.injuries,
        "injuries_raw_text": training_context.injuries_raw_text,
        "parsed_injuries": [dict(item) for item in training_context.parsed_injuries],
        "guided_injury": dict(training_context.guided_injury) if training_context.guided_injury else None,
        "injury_restrictions": [dict(item) for item in training_context.injury_restrictions],
        "short_notice": short_notice,
        "plan_creation_weekday": plan_creation_dt.strftime("%A").lower(),
        "plan_creation_weekday_basis": "athlete_local_weekday",
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

    weakness_tokens = _normalize_limiter_tokens(clean_list(athlete_model.get("weaknesses", [])))
    goal_tokens = _normalize_limiter_tokens(clean_list(athlete_model.get("key_goals", [])))
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
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
        *(value.replace("_", " ") for value in clean_list(athlete_model.get("key_goals", []))),
        *(value.replace("_", " ") for value in clean_list(athlete_model.get("weaknesses", []))),
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
        guardrails["conditioning_drop_order_if_thin"] = dedupe_preserve_order(
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
            "risk_flags": dedupe_preserve_order(risk_flags),
            "session_counts": session_counts,
            "selection_guardrails": _build_phase_selection_guardrails(phase, training_context),
            "weeks": phase_weeks.get(phase, 0),
            "days": phase_weeks.get("days", {}).get(phase, 0),
        }
    return briefs



def _derive_athlete_archetype(athlete_model: dict) -> dict:
    technical_styles = clean_list(athlete_model.get("technical_styles", []))
    tactical_styles = clean_list(athlete_model.get("tactical_styles", []))
    style_identity = dedupe_preserve_order(technical_styles + tactical_styles) or ["generalist"]

    readiness = "stable"
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
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
        "equipment_profile": clean_list(athlete_model.get("equipment", [])),
    }


def _derive_main_limiter(athlete_model: dict) -> str:
    compressed = athlete_model.get("compressed_priorities") or {}
    primary_labels = _priority_bucket_labels(compressed.get("primary_targets", []))
    if primary_labels:
        return f"Primary limiter is {primary_labels[0]}."
    weaknesses = clean_list(athlete_model.get("weaknesses", []))
    goals = clean_list(athlete_model.get("key_goals", []))
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))

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
    injuries = clean_list(athlete_model.get("injuries", []))
    hard_sparring_days = clean_list(athlete_model.get("hard_sparring_days", []))
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

    weakness_tokens = _normalize_limiter_tokens(clean_list(athlete_model.get("weaknesses", [])))
    goal_tokens = _normalize_limiter_tokens(clean_list(athlete_model.get("key_goals", [])))
    style_tokens = _normalize_limiter_tokens(
        clean_list(athlete_model.get("technical_styles", [])) + clean_list(athlete_model.get("tactical_styles", []))
    )
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
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
    cleaned = dedupe_preserve_order([str(part).strip() for part in parts if str(part).strip()])
    return " ".join(cleaned)



def _primary_sport_load_key(athlete_model: dict) -> str:
    sport_tokens = _normalize_limiter_tokens(clean_list(athlete_model.get("sport")))
    style_tokens = _normalize_limiter_tokens(
        clean_list(athlete_model.get("technical_styles", [])) + clean_list(athlete_model.get("tactical_styles", []))
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
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
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
        "must_keep": clean_list(guardrails.get("must_keep_if_present", [])),
        "drop_order_if_thin": clean_list(guardrails.get("conditioning_drop_order_if_thin", [])),
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
