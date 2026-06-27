from __future__ import annotations

from typing import Any

from .normalization import clean_list, dedupe_preserve_order
from .role_labels import athlete_facing_label_for


_CATEGORY_ALIASES = {
    "strength": {
        "strength",
        "maximal_strength",
        "maximal_strength_maintenance",
        "strength_maintenance",
        "max_strength",
    },
    "speed_reaction": {
        "speed",
        "reaction",
        "reactive",
        "acceleration",
        "speed_reaction",
    },
    "footwork": {
        "footwork",
        "lateral_movement",
        "ringcraft",
        "angles",
        "pivot",
        "stance_reset",
        "angle_exit",
        "lateral",
    },
    "conditioning": {
        "conditioning",
        "gas_tank",
        "aerobic_base",
        "work_capacity",
        "endurance",
        "conditioning_endurance",
    },
    "mobility": {
        "mobility",
        "stiffness",
        "movement_quality",
        "range",
        "range_of_motion",
    },
    "power": {
        "power",
        "explosive",
        "explosive_power",
        "rate_of_force",
    },
    "skill_striking": {
        "skill_refinement",
        "striking",
        "boxing",
        "technical_sharpness",
        "technical_quality",
    },
}

_REAL_STRENGTH_LOAD_TYPES = {
    "loaded",
    "sled",
    "carry",
    "cable",
    "heavy_isometric",
    "machine",
    "barbell",
    "dumbbell",
    "kettlebell",
}

_REAL_STRENGTH_MOVEMENT_BUCKETS = {
    "hinge",
    "squat",
    "split_squat",
    "upper_push",
    "upper_pull",
    "carry",
    "sled_push_drag",
    "heavy_isometric_strength_hold",
    "anti_rotation_trunk_strength",
}

_NON_STRENGTH_FULFILMENT_EQUIPMENT = {"band", "bands", "bodyweight", "body_weight", "none", "no_equipment"}


def normalize_fulfilment_token(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
    )


def _category_for_token(token: str) -> str:
    for category, aliases in _CATEGORY_ALIASES.items():
        if token in aliases:
            return category
    return token


def _is_late_fight_strength_contract_role(role: dict[str, Any]) -> bool:
    offset = _coerce_optional_int(role.get("countdown_offset"))
    governance = role.get("governance") if isinstance(role.get("governance"), dict) else {}
    return (
        role.get("fulfilment_contract_required") is True
        or bool(governance.get("late_fight_payload"))
        or (offset is not None and offset <= 21)
    )


def _is_real_strength_contract_role(role: dict[str, Any]) -> bool:
    equipment = {normalize_fulfilment_token(value) for value in clean_list(role.get("equipment_used", []))}
    novelty = normalize_fulfilment_token(role.get("novelty"))
    return (
        role.get("strength_fulfilment_type") == "real_strength_maintenance"
        and role.get("must_render") is True
        and bool(equipment)
        and not equipment <= _NON_STRENGTH_FULFILMENT_EQUIPMENT
        and normalize_fulfilment_token(role.get("load_type")) in _REAL_STRENGTH_LOAD_TYPES
        and normalize_fulfilment_token(role.get("movement_bucket")) in _REAL_STRENGTH_MOVEMENT_BUCKETS
        and normalize_fulfilment_token(role.get("volume_class")) == "low"
        and normalize_fulfilment_token(role.get("soreness_risk")) == "low"
        and (novelty in {"", "familiar", "not_new"} or role.get("not_new") is True)
    )


def _is_strength_contract_downgrade(role: dict[str, Any]) -> bool:
    return (
        role.get("strength_fulfilment_type") == "downgraded_equipment_limited"
        and bool(clean_list(role.get("reasons", [])))
    )


def _requested_obligations(athlete_model: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries: list[tuple[str, Any]] = []
    primary_goal = athlete_model.get("primary_goal")
    if str(primary_goal or "").strip():
        raw_entries.append(("primary_goal", primary_goal))
    primary_weak = athlete_model.get("primary_weak_area")
    if str(primary_weak or "").strip():
        raw_entries.append(("primary_weak_area", primary_weak))

    for value in clean_list(athlete_model.get("key_goals", [])):
        raw_entries.append(("secondary_goal", value))
    for value in clean_list(athlete_model.get("goals", [])):
        raw_entries.append(("secondary_goal", value))
    for key in ("weaknesses", "weak_areas"):
        for value in clean_list(athlete_model.get(key, [])):
            raw_entries.append(("weak_area", value))

    obligations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source_type, requested in raw_entries:
        token = normalize_fulfilment_token(requested)
        if not token:
            continue
        category = _category_for_token(token)
        key = (source_type, category)
        if key in seen:
            continue
        seen.add(key)
        obligations.append(
            {
                "source_type": source_type,
                "requested": str(requested).strip(),
                "normalized": token,
                "category": category,
            }
        )
    return obligations


def _role_fulfilment_categories(role: dict[str, Any]) -> list[str]:
    categories: list[str] = []
    role_key = normalize_fulfilment_token(role.get("role_key"))
    category = normalize_fulfilment_token(role.get("category"))
    system = normalize_fulfilment_token(role.get("preferred_system"))
    support_kind = normalize_fulfilment_token(role.get("support_kind"))
    tags = {normalize_fulfilment_token(tag) for tag in clean_list(role.get("preferred_tags", []))}
    names = " ".join(clean_list(role.get("preferred_exercise_names", []))).lower()
    explicit = clean_list(role.get("fulfilment_categories", []))
    explicit_categories = [normalize_fulfilment_token(value) for value in explicit]
    strength_like = (
        (category == "strength" and role_key not in {"neural_primer_day", "small_strength_touch_day"})
        or role_key
        in {
            "primary_strength_day",
            "structural_strength_day",
            "neural_plus_strength_day",
            "strength_touch_day",
        }
        or "strength" in explicit_categories
    )
    late_fight_strength_contract = strength_like and _is_late_fight_strength_contract_role(role)

    if strength_like and (
        not late_fight_strength_contract
        or _is_real_strength_contract_role(role)
        or _is_strength_contract_downgrade(role)
    ):
        categories.append("strength")
    if role_key in {"neural_primer_day", "alactic_sharpness_day", "alactic_speed_day"} or system == "alactic":
        categories.extend(["speed_reaction", "power"])
    if support_kind == "footwork" or "footwork" in tags or "pivot" in tags or "angle_exit" in tags or "footwork" in names:
        categories.extend(["footwork", "skill_striking"])
    if support_kind == "mobility" or "mobility" in tags or role_key in {
        "fight_week_freshness_day",
        "converted_mobility_support_day",
        "recovery_reset_day",
        "tissue_recovery_day",
    }:
        categories.append("mobility")
    if support_kind == "gas_tank" or system == "aerobic" or role_key in {
        "fight_pace_repeatability_day",
        "light_fight_pace_touch_day",
        "converted_low_aerobic_gas_tank_day",
        "recovery_aerobic_gas_tank_day",
    }:
        categories.append("conditioning")
    if role_key in {"technical_touch_day", "light_combat_day"}:
        categories.append("skill_striking")

    categories.extend(
        value
        for value in explicit_categories
        if value != "strength"
        or not late_fight_strength_contract
        or _is_real_strength_contract_role(role)
        or _is_strength_contract_downgrade(role)
    )
    return dedupe_preserve_order([value for value in categories if value])


def _coerce_optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safety_outcome(athlete_model: dict[str, Any], category: str) -> tuple[str, str]:
    days = _coerce_optional_int(athlete_model.get("days_until_fight"))
    fatigue = normalize_fulfilment_token(athlete_model.get("fatigue"))
    flags = {normalize_fulfilment_token(flag) for flag in clean_list(athlete_model.get("readiness_flags", []))}
    injury_mode = normalize_fulfilment_token(athlete_model.get("injury_mode"))
    injuries = clean_list(athlete_model.get("injuries", []))

    if days is not None and days <= 0:
        return "blocked", "D-0 fight-day protocol blocks additional training fulfilment."
    if fatigue == "high" or "high_fatigue" in flags:
        return "downgrade", "High fatigue forces minimum-dose or recovery-only fulfilment."
    if injury_mode in {"medical_hold", "restricted_rehab_only"} or flags & {"red_flag_injury", "severe_injury"}:
        return "blocked", "Injury safety gate blocks non-rehab fulfilment."
    if injuries and category in {"strength", "speed_reaction", "power", "conditioning"}:
        return "downgrade", "Active injury context requires a safer lower-noise fulfilment."
    if flags & {"aggressive_weight_cut", "extreme_weight_cut"} and category == "conditioning":
        return "downgrade", "Weight-cut pressure blocks glycolytic fulfilment; use low-noise maintenance."
    return "passed", "Safety gate passed for a visible minimum effective dose."


def apply_goal_weakness_fulfilment_contract(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map

    obligations = _requested_obligations(athlete_model)
    weeks = [week for week in weekly_role_map.get("weeks", []) or [] if isinstance(week, dict)]
    rendered_roles: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []
    suppressed_roles: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []

    for week in weeks:
        for role in week.get("session_roles", []) or []:
            if not isinstance(role, dict):
                continue
            categories = _role_fulfilment_categories(role)
            if categories:
                role["fulfilment_categories"] = categories
            rendered_roles.append((week, role, categories))
        for role in week.get("suppressed_roles", []) or []:
            if isinstance(role, dict):
                categories = _role_fulfilment_categories(role)
                if categories:
                    role["fulfilment_categories"] = categories
                suppressed_roles.append((week, role, categories))

    contract: list[dict[str, Any]] = []
    for obligation in obligations:
        category = obligation["category"]
        gate, gate_reason = _safety_outcome(athlete_model, category)
        match = next(
            (
                (week, role)
                for week, role, categories in rendered_roles
                if category in categories
            ),
            None,
        )
        suppressed_match = next(
            (
                (week, role)
                for week, role, categories in suppressed_roles
                if category in categories
            ),
            None,
        )

        entry = {
            **obligation,
            "safety_gate_outcome": gate,
            "safety_gate_reason": gate_reason,
            "fulfilment_type": "suppressed",
            "rendered_session": None,
            "suppression_reason": "",
        }
        if match is not None:
            week, role = match
            role_obligations = list(role.get("fulfils_obligations", []))
            obligation_key = f"{obligation['source_type']}:{category}"
            if obligation_key not in role_obligations:
                role_obligations.append(obligation_key)
            role["fulfils_obligations"] = role_obligations
            entry["fulfilment_type"] = "downgraded" if gate == "downgrade" else "full"
            entry["rendered_session"] = {
                "week_index": week.get("week_index"),
                "stage_key": week.get("stage_key"),
                "countdown_label": role.get("scheduled_countdown_label") or role.get("countdown_label"),
                "weekday": role.get("scheduled_day_hint") or role.get("real_weekday"),
                "role_key": role.get("role_key"),
                "athlete_facing_label": role.get("athlete_facing_label")
                or athlete_facing_label_for(role.get("role_key")),
                "preferred_exercise_names": clean_list(role.get("preferred_exercise_names", [])),
            }
        elif suppressed_match is not None:
            _week, role = suppressed_match
            reasons = clean_list(role.get("reasons", []))
            entry["suppression_reason"] = reasons[0] if reasons else "Role was explicitly suppressed by planner guardrails."
        else:
            entry["suppression_reason"] = (
                gate_reason
                if gate == "blocked"
                else "No compliant visible role survived safety, taper, coach-owned day, and compression rules."
            )
        contract.append(entry)

    weekly_role_map["fulfilment_contract"] = contract
    why_log = dict(weekly_role_map.get("why_log") or {})
    why_log["goal_weakness_fulfilment"] = contract
    weekly_role_map["why_log"] = why_log
    return weekly_role_map
