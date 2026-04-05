from __future__ import annotations

from typing import Any


_PAYLOAD_MODE_MAP = {
    0: "fight_day_protocol_payload",
    1: "pre_fight_day_payload",
    2: "late_fight_session_payload",
    3: "late_fight_session_payload",
    4: "late_fight_session_payload",
    5: "late_fight_week_payload",
    6: "late_fight_week_payload",
    7: "late_fight_week_payload",
}

_WEEKDAY_ORDER = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


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


def _ordered_weekdays(values: list[str]) -> list[str]:
    cleaned = _dedupe_preserve_order([str(value).strip() for value in values if str(value).strip()])
    return sorted(cleaned, key=lambda day: (_WEEKDAY_ORDER.get(day.strip().lower(), 99), day.strip().lower()))


def _active_window_weekdays(athlete_model: dict) -> list[str]:
    values = []
    for value in _clean_list(athlete_model.get("active_window_weekdays", [])):
        normalized = str(value).strip()
        if normalized:
            values.append(normalized)
    return values


def _windowed_weekdays(values: list[str], athlete_model: dict) -> list[str]:
    active_window = _active_window_weekdays(athlete_model)
    if not active_window:
        return _ordered_weekdays(values)
    canonical_to_original: dict[str, str] = {}
    for value in _dedupe_preserve_order([str(item).strip() for item in values if str(item).strip()]):
        canonical = str(value).strip().lower()
        if canonical in _WEEKDAY_ORDER and canonical not in canonical_to_original:
            canonical_to_original[canonical] = value
    ordered: list[str] = []
    for day in active_window:
        lowered = str(day).strip().lower()
        aliases = [key for key, index in _WEEKDAY_ORDER.items() if index == _WEEKDAY_ORDER.get(lowered)]
        original = next((canonical_to_original[alias] for alias in aliases if alias in canonical_to_original), None)
        if original:
            ordered.append(original)
    return ordered


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
    if role_key in {"fight_pace_repeatability_day", "light_fight_pace_touch_day", "hard_sparring_day"}:
        return "highest_glycolytic_day"
    if role_key in {"recovery_reset_day", "tissue_recovery_day", "fight_week_freshness_day"}:
        return "lowest_load_day"
    return "support_day"


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
    if days <= 6:
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


def _days_out_payload_mode(days_until_fight: Any) -> str:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return "camp_payload"
    if days < 0:
        return "camp_payload"
    return _PAYLOAD_MODE_MAP.get(days, "camp_payload")


def _uses_late_fight_stage2_payload(days_until_fight: Any) -> bool:
    return _days_out_payload_mode(days_until_fight) != "camp_payload"


def _days_out_bucket(days_until_fight: Any) -> str:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return "CAMP"
    if days < 0 or days > 7:
        return "CAMP"
    return f"D-{days}"


def _late_fight_window(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "late_fight_week_payload":
        return "d7_to_d5"
    if mode == "late_fight_session_payload":
        return "d4_to_d2"
    if mode == "pre_fight_day_payload":
        return "d1"
    if mode == "fight_day_protocol_payload":
        return "d0"
    return "camp"


def _late_fight_session_type_rules(days_until_fight: Any) -> tuple[list[str], list[str]]:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "late_fight_week_payload":
        return ["strength", "conditioning", "recovery", "technical"], ["broad_development_week"]
    if mode == "late_fight_session_payload":
        try:
            days = int(days_until_fight)
        except (TypeError, ValueError):
            days = 3
        allowed = ["recovery", "technical"]
        if days >= 3:
            allowed.insert(0, "conditioning")
        return allowed, ["full_strength_block", "glycolytic_build", "broad_weekly_architecture"]
    if mode == "pre_fight_day_payload":
        return ["primer", "technical", "recovery"], ["full_strength_block", "conditioning_block", "hard_sparring"]
    if mode == "fight_day_protocol_payload":
        return ["activation", "warm_up", "tactical_cues", "fueling", "recovery_notes"], ["strength", "conditioning", "sparring", "weekly_architecture"]
    return ["strength", "conditioning", "recovery", "technical", "sparring"], []


def _late_fight_permissions(days_until_fight: Any, athlete_model: dict) -> dict:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "camp_payload":
        return {
            "mode": mode,
            "allow_full_weekly_structure": True,
            "allow_normal_session_roles": True,
            "allow_anchor_wording": True,
            "allow_development_language": True,
            "allow_glycolytic_build": True,
            "allow_broad_weakness_building": True,
            "max_meaningful_strength_anchors": None,
            "max_meaningful_conditioning_stressors": None,
            "allow_hard_sparring_influence": True,
            "allow_weekly_frequency_reasoning": True,
            "allow_multi_session_stress": True,
            "sparring_role": "full_collision_owner",
        }
    if mode == "late_fight_week_payload":
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": True,
            "allow_normal_session_roles": True,
            "allow_anchor_wording": True,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": 1,
            "max_meaningful_conditioning_stressors": 1,
            "allow_hard_sparring_influence": True,
            "allow_weekly_frequency_reasoning": True,
            "allow_multi_session_stress": False,
            "sparring_role": "collision_owner_narrow",
            "forbid": [
                "broad development language",
                "multiple meaningful non-sparring stressors",
            ],
        }
    if mode == "late_fight_session_payload":
        try:
            days = int(days_until_fight)
        except (TypeError, ValueError):
            days = 3
        sparring_role = "advisory_only" if days <= 2 else "narrowing_influence"
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": False,
            "allow_session_list_only": True,
            "allow_normal_session_roles": False,
            "allow_anchor_wording": False,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": 0,
            "max_meaningful_conditioning_stressors": 0,
            "allow_hard_sparring_influence": days >= 3,
            "allow_weekly_frequency_reasoning": False,
            "allow_multi_session_stress": False,
            "sparring_role": sparring_role,
            "allow_alactic_sharpness": days >= 3,
            "allow_activation_mobility": True,
            "forbid": [
                "normal camp-week framing",
                "broad weekly architecture",
                "developmental strength block",
                "glycolytic build logic",
                "broad weakness-building language",
                "program block framing",
                "phase-explanation dump",
                "long rationale sections",
            ],
        }
    if mode == "pre_fight_day_payload":
        return {
            "mode": mode,
            "allow_full_weekly_structure": False,
            "allow_compressed_weekly_structure": False,
            "allow_session_list_only": False,
            "allow_primer_only": True,
            "allow_normal_session_roles": False,
            "allow_anchor_wording": False,
            "allow_development_language": False,
            "allow_glycolytic_build": False,
            "allow_broad_weakness_building": False,
            "max_meaningful_strength_anchors": 0,
            "max_meaningful_conditioning_stressors": 0,
            "allow_hard_sparring_influence": False,
            "allow_weekly_frequency_reasoning": False,
            "allow_multi_session_stress": False,
            "sparring_role": "suppressed",
            "allow": [
                "neural primer",
                "light technical touch",
                "mobility / reset",
                "pre-fight instructions",
            ],
            "forbid": [
                "anchor wording",
                "primary strength",
                "full strength block",
                "glycolytic insert",
                "weekly architecture framing",
                "hard sparring influence",
                "conditioning-system allocation",
                "fight-pace density",
                "conditioning block",
            ],
        }
    return {
        "mode": mode,
        "allow_full_weekly_structure": False,
        "allow_compressed_weekly_structure": False,
        "allow_session_list_only": False,
        "allow_primer_only": False,
        "allow_fight_day_protocol_only": True,
        "allow_normal_session_roles": False,
        "allow_anchor_wording": False,
        "allow_development_language": False,
        "allow_glycolytic_build": False,
        "allow_broad_weakness_building": False,
        "max_meaningful_strength_anchors": 0,
        "max_meaningful_conditioning_stressors": 0,
        "allow_hard_sparring_influence": False,
        "allow_weekly_frequency_reasoning": False,
        "allow_multi_session_stress": False,
        "sparring_role": "suppressed",
        "allow": [
            "activation",
            "warm-up",
            "tactical cueing",
            "fueling / hydration / logistics",
            "post-fight recovery notes",
        ],
        "forbid": [
            "all normal week logic",
            "strength generation",
            "conditioning generation",
            "session-role generation",
            "hard sparring relevance",
            "weekly role map rendering as a real week",
        ],
    }


def _late_fight_rendering_rules(days_until_fight: Any) -> dict:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "camp_payload":
        return {"mode": mode, "rules": []}
    if mode == "late_fight_week_payload":
        return {
            "mode": mode,
            "framing": "compressed_week",
            "rules": [
                "Use concise compressed week framing.",
                "No broad development language.",
                "Cap meaningful non-sparring stressors at one.",
                "Keep sparring collision logic active.",
            ],
        }
    if mode == "late_fight_session_payload":
        return {
            "mode": mode,
            "framing": "session_by_session",
            "rules": [
                "Render session-by-session, not as a program block.",
                "No 'program block' framing.",
                "No phase-explanation dump.",
                "No long rationale sections.",
                "Keep each session description tight and action-oriented.",
            ],
        }
    if mode == "pre_fight_day_payload":
        return {
            "mode": mode,
            "framing": "primer_only",
            "rules": [
                "Output primer-only content.",
                "No anchor, primary strength, conditioning block, or fight-pace density language.",
                "Prefer terms: primer, touch, sharpness, reset, rhythm.",
                "Keep the entire output under 300 words.",
            ],
            "forbidden_terms": [
                "anchor",
                "primary strength",
                "conditioning block",
                "fight-pace density",
            ],
            "preferred_terms": [
                "primer",
                "touch",
                "sharpness",
                "reset",
                "rhythm",
            ],
        }
    return {
        "mode": mode,
        "framing": "fight_day_protocol",
        "rules": [
            "No training language.",
            "Output activation, warm-up, cue, fuel, and recovery content only.",
            "Do not render a weekly role map or session architecture.",
            "Keep the output minimal and fight-day focused.",
        ],
        "forbidden_terms": [
            "anchor",
            "primary strength",
            "conditioning block",
            "fight-pace density",
            "weekly role map",
            "session architecture",
        ],
        "preferred_terms": [
            "activation",
            "warm-up",
            "cue",
            "fuel",
            "recover",
        ],
    }


def _days_out_payload_block(days_until_fight: Any, athlete_model: dict) -> dict:
    mode = _days_out_payload_mode(days_until_fight)
    permissions = _late_fight_permissions(days_until_fight, athlete_model)
    rendering_rules = _late_fight_rendering_rules(days_until_fight)
    fight_week_override = _fight_week_override_payload(days_until_fight)
    allowed_session_types, forbidden_session_types = _late_fight_session_type_rules(days_until_fight)
    return {
        "days_until_fight": days_until_fight,
        "payload_mode": mode,
        "payload_variant": "late_fight_stage2_payload" if _uses_late_fight_stage2_payload(days_until_fight) else "normal_stage2_payload",
        "days_out_bucket": _days_out_bucket(days_until_fight),
        "late_fight_window": _late_fight_window(days_until_fight),
        "fight_week_override": fight_week_override or {"active": False},
        "late_fight_permissions": permissions,
        "allowed_session_types": allowed_session_types,
        "forbidden_session_types": forbidden_session_types,
        "rendering_rules": rendering_rules,
    }


def _late_fight_role_entry(
    *,
    session_index: int,
    category: str,
    role_key: str,
    selection_rule: str,
    preferred_pool: str,
    placement_rule: str,
    preferred_system: str | None = None,
) -> dict[str, Any]:
    entry = {
        "session_index": session_index,
        "category": category,
        "role_key": role_key,
        "preferred_pool": preferred_pool,
        "selection_rule": selection_rule,
        "anchor": _role_anchor(role_key),
        "placement_rule": placement_rule,
        "governance": {"late_fight_payload": True},
    }
    if preferred_system:
        entry["preferred_system"] = preferred_system
    return entry


def _late_fight_session_roles(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    mode = _days_out_payload_mode(days_until_fight)
    declared_hard_days = _windowed_weekdays(_clean_list(athlete_model.get("hard_sparring_days", [])), athlete_model)
    if mode == "late_fight_week_payload":
        roles: list[dict[str, Any]] = []
        session_index = 1
        if declared_hard_days:
            roles.append(
                _late_fight_role_entry(
                    session_index=session_index,
                    category="conditioning",
                    role_key="hard_sparring_day",
                    preferred_pool="declared_hard_sparring_days",
                    selection_rule="Keep one declared hard sparring day fixed only if the draft already carries it in this window.",
                    placement_rule="Treat the declared hard sparring day as fixed and compress everything around it.",
                )
            )
            session_index += 1
        roles.append(
            _late_fight_role_entry(
                session_index=session_index,
                category="strength",
                role_key="neural_primer_day",
                preferred_pool="strength_slots",
                selection_rule="Use one sharp, low-volume neural strength or power exposure only.",
                placement_rule="Keep this away from the main collision load and keep the dose small.",
            )
        )
        session_index += 1
        if not declared_hard_days:
            roles.append(
                _late_fight_role_entry(
                    session_index=session_index,
                    category="conditioning",
                    role_key="alactic_sharpness_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="alactic",
                    selection_rule="Use one alactic sharpness exposure instead of a normal conditioning build.",
                    placement_rule="Keep this brief and crisp; do not turn it into density work.",
                )
            )
            session_index += 1
        roles.append(
            _late_fight_role_entry(
                session_index=session_index,
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Use freshness, mobility, and reset work to preserve readiness.",
                placement_rule="Keep this as the lowest-load day of the week.",
            )
        )
        return roles
    if mode == "late_fight_session_payload":
        roles: list[dict[str, Any]] = []
        try:
            days = int(days_until_fight)
        except (TypeError, ValueError):
            days = 3
        if days >= 3:
            roles.append(
                _late_fight_role_entry(
                    session_index=1,
                    category="conditioning",
                    role_key="alactic_sharpness_day",
                    preferred_pool="conditioning_slots",
                    preferred_system="alactic",
                    selection_rule="Use one short alactic sharpness touch only if it keeps the athlete fresher, not flatter.",
                    placement_rule="Keep this brief and low-noise.",
                )
            )
        roles.append(
            _late_fight_role_entry(
                session_index=len(roles) + 1,
                category="recovery",
                role_key="fight_week_freshness_day",
                preferred_pool="rehab_slots_or_recovery_only",
                selection_rule="Use recovery, breathing, and mobility to preserve rhythm and readiness.",
                placement_rule="Keep this as the lowest-load session in the window.",
            )
        )
        return roles
    if mode == "pre_fight_day_payload":
        return [
            _late_fight_role_entry(
                session_index=1,
                category="strength",
                role_key="neural_primer_day",
                preferred_pool="strength_slots",
                selection_rule="Render at most one tiny neural primer; do not build a normal training week.",
                placement_rule="Keep it short, clean, and immediately supportive of tomorrow's performance.",
            )
        ]
    return []


def _build_late_fight_session_sequence(days_until_fight: Any, athlete_model: dict) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for role in _late_fight_session_roles(days_until_fight, athlete_model):
        sequence.append(
            {
                "session_index": role.get("session_index"),
                "category": role.get("category"),
                "role_key": role.get("role_key"),
                "preferred_pool": role.get("preferred_pool"),
                "preferred_system": role.get("preferred_system"),
                "selection_rule": role.get("selection_rule"),
                "placement_rule": role.get("placement_rule"),
                "anchor": role.get("anchor"),
            }
        )
    return sequence


def _late_fight_stage_label(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "late_fight_week_payload":
        return "Late Fight Week"
    if mode == "late_fight_session_payload":
        return "Late Fight Sessions"
    if mode == "pre_fight_day_payload":
        return "Pre-Fight Day"
    if mode == "fight_day_protocol_payload":
        return "Fight Day"
    return "Camp"


def _late_fight_summary(days_until_fight: Any) -> str:
    mode = _days_out_payload_mode(days_until_fight)
    if mode == "late_fight_week_payload":
        return "Use a compressed late-fight week. Keep only sharpness, one meaningful exposure, and freshness support."
    if mode == "late_fight_session_payload":
        return "Use a short late-fight session list. No normal camp-week architecture or development work."
    if mode == "pre_fight_day_payload":
        return "Use primer-only guidance. No normal week framing and no conditioning build."
    if mode == "fight_day_protocol_payload":
        return "Use fight-day protocol guidance only. No training-week language."
    return "Use the normal camp-stage payload."


def _build_late_fight_week_by_week_progression(days_until_fight: Any, athlete_model: dict, phase_briefs: dict[str, dict]) -> dict[str, Any]:
    if _days_out_payload_mode(days_until_fight) in {
        "fight_day_protocol_payload",
        "pre_fight_day_payload",
        "late_fight_session_payload",
    }:
        return {"weeks": []}
    phase = next((phase_name for phase_name in ("TAPER", "SPP", "GPP") if phase_name in phase_briefs), next(iter(phase_briefs), "TAPER"))
    roles = _late_fight_session_roles(days_until_fight, athlete_model)
    session_counts = {
        "strength": sum(1 for role in roles if role.get("category") == "strength"),
        "conditioning": sum(1 for role in roles if role.get("category") == "conditioning"),
        "recovery": sum(1 for role in roles if role.get("category") == "recovery"),
    }
    conditioning_sequence = [role.get("preferred_system") for role in roles if role.get("category") == "conditioning" and role.get("preferred_system")]
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase": phase,
                "stage_key": _late_fight_window(days_until_fight),
                "stage_label": _late_fight_stage_label(days_until_fight),
                "stage_objective": _late_fight_summary(days_until_fight),
                "phase_week_index": 1,
                "phase_week_total": 1,
                "session_counts": session_counts,
                "conditioning_sequence": conditioning_sequence or ["alactic"],
                "intentional_compression": {
                    "active": True,
                    "reason_codes": [_days_out_payload_mode(days_until_fight)],
                    "reason": _days_out_payload_mode(days_until_fight),
                    "summary": _late_fight_summary(days_until_fight),
                },
            }
        ]
    }


def _build_late_fight_weekly_role_map(days_until_fight: Any, athlete_model: dict, fight_week_override: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = _days_out_payload_mode(days_until_fight)
    roles = _late_fight_session_roles(days_until_fight, athlete_model)
    if mode in {"fight_day_protocol_payload", "pre_fight_day_payload", "late_fight_session_payload"}:
        weeks: list[dict[str, Any]] = []
    else:
        weeks = [
            {
                "week_index": 1,
                "phase": "TAPER",
                "stage_key": _late_fight_window(days_until_fight),
                "phase_week_index": 1,
                "phase_week_total": 1,
                "declared_training_days": _windowed_weekdays(_clean_list(athlete_model.get("training_days", [])), athlete_model),
                "declared_hard_sparring_days": _windowed_weekdays(_clean_list(athlete_model.get("hard_sparring_days", [])), athlete_model),
                "declared_technical_skill_days": _windowed_weekdays(_clean_list(athlete_model.get("technical_skill_days", [])), athlete_model),
                "hard_sparring_plan": [],
                "effective_hard_sparring_days": [],
                "coach_note_flags": [_late_fight_stage_label(days_until_fight)],
                "intentional_compression": {
                    "active": True,
                    "reason_codes": [mode],
                    "reason": mode,
                    "summary": _late_fight_summary(days_until_fight),
                },
                "intentionally_unused_days": [],
                "session_roles": roles,
                "suppressed_roles": [
                    {
                        "category": "plan",
                        "role_key": "normal_stage2_payload",
                        "reasons": ["late_fight_stage2_payload: bypassed normal camp-style stage2 payload assumptions"],
                    }
                ],
            }
        ]
    return {
        "model": "late_fight_role_overlay.v1",
        "source_of_truth": [
            "Late-fight Stage 2 payload bypasses the normal camp-week payload path for 7 days and less.",
            "Use the late-fight role map as a compressed execution guide, not as a normal weekly build.",
            "Keep the output aligned to the time window first, then the athlete profile.",
        ],
        "payload_variant": "late_fight_stage2_payload",
        "payload_mode": mode,
        "fight_week_override": fight_week_override or {"active": False},
        "weeks": weeks,
    }


def _build_late_fight_plan_spec(days_until_fight: Any, athlete_model: dict) -> dict[str, Any]:
    payload_block = _days_out_payload_block(days_until_fight, athlete_model)
    roles = _late_fight_session_roles(days_until_fight, athlete_model)
    session_sequence = _build_late_fight_session_sequence(days_until_fight, athlete_model)
    return {
        "payload_variant": "late_fight_stage2_payload",
        "payload_mode": payload_block["payload_mode"],
        "days_out_bucket": payload_block["days_out_bucket"],
        "late_fight_window": payload_block["late_fight_window"],
        "summary": _late_fight_summary(days_until_fight),
        "active_window_weekdays": _active_window_weekdays(athlete_model),
        "session_cap": len(roles),
        "session_roles": [role.get("role_key") for role in roles],
        "session_sequence": session_sequence,
        "allowed_session_types": payload_block["allowed_session_types"],
        "forbidden_session_types": payload_block["forbidden_session_types"],
        "rendering_rules": payload_block["rendering_rules"],
    }


def _handoff_mode_instructions(payload_mode: str) -> str:
    if payload_mode == "fight_day_protocol_payload":
        return (
            "HARD OVERRIDE — FIGHT DAY PROTOCOL\n"
            "This is D-0. The athlete fights today.\n"
            "Do NOT generate a training week, session-role structure, or weekly architecture.\n"
            "Do NOT use strength, conditioning, session-role, anchor, or programming language.\n"
            "Output ONLY:\n"
            "- Activation / warm-up protocol\n"
            "- Tactical cueing (style, stance, rhythm)\n"
            "- Fueling / hydration / logistics\n"
            "- Post-fight recovery notes\n"
            "Keep it short, decisive, and fight-ready.\n"
            "Do NOT restore any suppressed roles from the planning brief."
        )
    if payload_mode == "pre_fight_day_payload":
        return (
            "HARD OVERRIDE — PRE-FIGHT DAY (D-1)\n"
            "This is the day before the fight. Do NOT build a normal training week.\n"
            "Output ONLY:\n"
            "- Neural primer (max 1 short session)\n"
            "- Light technical touch if applicable\n"
            "- Mobility / reset protocol\n"
            "- Pre-fight instructions and preparation notes\n"
            "FORBIDDEN TERMS: anchor, primary strength, conditioning block, fight-pace density, glycolytic.\n"
            "PREFERRED TERMS: primer, touch, sharpness, reset, rhythm.\n"
            "Do NOT use weekly architecture framing.\n"
            "Do NOT restore suppressed session roles.\n"
            "Do NOT generate hard sparring or conditioning-system allocation."
        )
    if payload_mode == "late_fight_session_payload":
        return (
            "LATE FIGHT MODE — SESSION-BY-SESSION (D-4 to D-2)\n"
            "Do NOT frame this as a normal camp week.\n"
            "Present the plan session-by-session, not as a program block.\n"
            "Do NOT render week headers, Monday-to-Sunday structure, or a full weekly schedule.\n"
            "Do NOT use broad development language, phase-explanation dumps, or long rationale sections.\n"
            "Do NOT generate developmental strength blocks or glycolytic build logic.\n"
            "Hard sparring influence narrows progressively (D-4/D-3 can still influence, D-2 advisory only).\n"
            "Keep output concise. No weekly frequency reasoning.\n"
            "No 'program block' framing. No phase-explanation dump."
        )
    if payload_mode == "late_fight_week_payload":
        return (
            "LATE FIGHT MODE — COMPRESSED WEEK (D-7 to D-5)\n"
            "This is late fight week. Use compressed weekly framing.\n"
            "Max 1 meaningful strength anchor. Max 1 meaningful conditioning stressor.\n"
            "Allow hard sparring logic where declared.\n"
            "Forbid broad development language and multiple non-sparring stressors.\n"
            "Keep output concise. No broad development build."
        )
    return ""