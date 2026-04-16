"""Stage 2 payload assembly, candidate pools, finalizer prompt, and handoff text.

Internal implementation is split across:
  - stage2_planning_brief  — athlete model, phases, limiter, sport load
  - stage2_role_map        — week progression, role slots, compression

Everything is re-exported here so external callers don't need to change
their import paths.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .stage2_payload_late_fight import (
    _build_late_fight_plan_spec,
    _build_late_fight_session_sequence,
    _build_late_fight_week_by_week_progression,
    _build_late_fight_weekly_role_map,
    _days_out_payload_block,
    _days_out_payload_mode,
    _fight_week_override_payload,
    _handoff_mode_instructions,
    _late_fight_permissions,
    _late_fight_rendering_rules,
    _uses_late_fight_stage2_payload,
)
from .normalization import clean_list, normalize_text, phrase_in_text, slugify, dedupe_preserve_order
from .restriction_parsing import CANONICAL_RESTRICTIONS
from .rehab_protocols import _rehab_drills_for_phase, classify_drill_function, _FUNCTION_LABELS
from .sparring_dose_planner import compute_hard_sparring_plan, effective_hard_day_count, effective_hard_days
from .strength_session_quality import classify_strength_item, infer_strength_sessions
from .training_context import TrainingContext, allocate_sessions

# Re-export from sub-modules for backward compatibility
from .stage2_planning_brief import (  # noqa: F401
    CONDITIONING_ROLE_PURPOSES,
    PLANNING_DECISION_HIERARCHY,
    _build_athlete_model,
    _build_limiter_profile,
    _build_phase_briefs,
    _build_phase_selection_guardrails,
    _build_sport_load_profile,
    _build_weekly_stress_map,
    _compress_short_camp_priorities,
    _conditioning_slot_priority,
    dedupe_preserve_order,
    _derive_athlete_archetype,
    _derive_competitive_maturity,
    _derive_main_limiter,
    _derive_main_risks,
    _derive_readiness_flags,
    _downgrade_priority,
    _extract_mechanical_risk_tags,
    _extract_restriction_tags,
    _is_high_pressure_weight_cut,
    _join_rule_parts,
    _normalize_limiter_tokens,
    _parse_record,
    _primary_limiter_key,
    _primary_sport_load_key,
    _priority_bucket,
    _priority_bucket_labels,
    _priority_value,
    _resolve_phase_rule_state,
    _serialize_restrictions,
    _strength_slot_priority,
)
from .stage2_role_map import (  # noqa: F401
    _active_injury_is_moderate_plus,
    _active_weight_cut_is_meaningful,
    _apply_high_fatigue_week_compression,
    _apply_legacy_high_fatigue_compression,
    _apply_short_camp_role_compression,
    _assign_declared_day_hints,
    _build_spar_allocation_reason_codes,
    _build_week_by_week_progression,
    _build_weekly_role_map,
    _compression_floor_value,
    _compression_summary,
    _compute_intentionally_unused_days,
    _compute_readiness_compression,
    _high_fatigue_compression_reason_codes,
    _intentional_compression_stub,
    _lock_declared_hard_sparring_roles,
    _make_compression_suppression,
    _non_spar_role_priority_rank,
    _phase_progression_slot_count,
    _preferred_boxer_conditioning_sequence,
    _resequence_session_roles,
    _role_anchor,
    _role_governance,
    _role_selection_rule,
    _split_phase_days,
)



def _derive_global_priorities(
    athlete_model: dict,
    phase_briefs: dict[str, dict],
    candidate_pools: dict[str, dict],
) -> dict[str, list[str]]:
    preserve: list[str] = []
    push: list[str] = []
    avoid: list[str] = []

    injuries = clean_list(athlete_model.get("injuries", []))
    goals = clean_list(athlete_model.get("key_goals", []))
    hard_sparring_days = clean_list(athlete_model.get("hard_sparring_days", []))
    technical_skill_days = clean_list(athlete_model.get("technical_skill_days", []))
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
        "preserve": dedupe_preserve_order(preserve) or ["Preserve the main phase objectives and any active rehab work."],
        "push": dedupe_preserve_order(push) or ["Push the highest-priority phase qualities first."],
        "avoid": dedupe_preserve_order(avoid) or ["Avoid changes that break the phase intent or restriction logic."],
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
            "build": clean_list(brief.get("emphasize", [])),
            "protect": clean_list(brief.get("risk_flags", [])),
            "deprioritize": clean_list(brief.get("deprioritize", [])),
            "must_keep": clean_list((brief.get("selection_guardrails") or {}).get("must_keep_if_present", [])),
            "drop_order_if_thin": clean_list((brief.get("selection_guardrails") or {}).get("conditioning_drop_order_if_thin", [])),
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
    days_until_fight = athlete_model.get("days_until_fight")

    if _uses_late_fight_stage2_payload(days_until_fight):
        fight_week_override = _fight_week_override_payload(days_until_fight)
        days_out_payload = _days_out_payload_block(days_until_fight, athlete_model)
        late_fight_progression = _build_late_fight_week_by_week_progression(days_until_fight, athlete_model, phase_briefs)
        weekly_role_map = _build_late_fight_weekly_role_map(days_until_fight, athlete_model, fight_week_override)
        session_sequence = _build_late_fight_session_sequence(days_until_fight, athlete_model)
        return {
            "schema_version": "planning_brief.v1",
            "generator_mode": "deterministic_late_fight_planner_plus_ai_finalizer",
            "payload_variant": "late_fight_stage2_payload",
            "athlete_snapshot": athlete_model,
            "days_out_payload": days_out_payload,
            "late_fight_plan_spec": _build_late_fight_plan_spec(days_until_fight, athlete_model),
            "late_fight_session_sequence": session_sequence,
            "fight_demands": {
                "sport": athlete_model.get("sport"),
                "status": athlete_model.get("status"),
                "rounds_format": athlete_model.get("rounds_format"),
                "camp_length_weeks": athlete_model.get("camp_length_weeks"),
                "days_until_fight": days_until_fight,
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
            "phase_strategy": _build_phase_strategy(phase_briefs, candidate_pools, late_fight_progression),
            "weekly_stress_map": weekly_stress_map,
            "week_by_week_progression": late_fight_progression,
            "fight_week_override": fight_week_override or {"active": False},
            "weekly_role_map": weekly_role_map,
            "rendering_rules": days_out_payload.get("rendering_rules", {}),
            "restrictions": restrictions,
            "candidate_pools": candidate_pools,
            "omission_ledger": omission_ledger,
            "decision_rules": rewrite_guidance,
        }

    fight_week_override = _fight_week_override_payload(days_until_fight)
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
            "days_until_fight": days_until_fight,
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
    movement_patterns.extend(clean_list(exercise.get("tags", [])))
    quality_profile = classify_strength_item(exercise)
    required_equipment = clean_list(exercise.get("required_equipment") or exercise.get("equipment", []))
    return {
        "name": exercise.get("name", "Unnamed"),
        "source": "exercise_bank",
        "movement_patterns": dedupe_preserve_order(movement_patterns),
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
    tags = clean_list(drill.get("tags", []))
    required_equipment = clean_list(drill.get("required_equipment") or drill.get("equipment", []))
    return {
        "name": drill.get("name", "Unnamed"),
        "source": "conditioning_bank",
        "movement_patterns": dedupe_preserve_order([system] + tags),
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
                "slot_id": f"{phase.lower()}_strength_{idx}_{slugify(name)}",
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
                    "slot_id": f"{phase.lower()}_{system}_{idx}_{slugify(name)}",
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
        role = f"rehab_{slugify(location)}_{slugify(injury_type)}"
        selected_lines = [line for line in group.get("drills", []) if line]
        if phase.upper() == "TAPER":
            selected_lines = [line for line in selected_lines if "nordic" not in line.lower()]
            if not selected_lines:
                continue
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
                if (
                    option == line
                    or option in selected_set
                    or (phase.upper() == "TAPER" and "nordic" in option.lower())
                ):
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
                    "slot_id": f"{phase.lower()}_{role}_{idx}_{slugify(line)}",
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


def _build_injury_context(*, athlete_model: dict) -> dict[str, Any]:
    triage_summary = athlete_model.get("triage_summary")
    return {
        "raw_injury_text": athlete_model.get("injuries_raw_text") or "",
        "injuries_flat": clean_list(athlete_model.get("injuries", [])),
        "parsed_injuries": athlete_model.get("parsed_injuries") or [],
        "guided_injury": athlete_model.get("guided_injury"),
        "restrictions": athlete_model.get("injury_restrictions") or [],
        "triage_summary": triage_summary if isinstance(triage_summary, dict) else {},
    }


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
    athlete_model["triage_summary"] = dict(training_context.triage_summary or {})
    injury_context = _build_injury_context(athlete_model=athlete_model)
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
            "Use simple session titles that match the phase and countdown window: Strength, Recovery, Aerobic support, Fight-pace conditioning, Alactic sharpness, or Neural primer in normal camp; Sharpness Session, Technical Touch, Freshness Session, Primer, Activation, or Fight-Day Warm-Up in late-fight windows.",
            "In taper weeks, remove optional branches aggressively and keep the work short, final, and low-noise.",
            "If the athlete's declared equipment already resolves the choice, do not show a fallback branch.",
            "If declared hard sparring or technical skill days exist, use them to make the weekly rhythm more concrete instead of writing generic sparring caveats.",
            "Treat declared hard sparring days in weekly_role_map as immutable hard_sparring_day slots. If readiness is compromised, deload the sparring dose on that day instead of replacing the day role.",
            "Respect the weekly session count implied by weekly_role_map; do not turn extra available days into extra active training days.",
            "If the athlete has more available days than planned sessions, leave the spare days off or clearly optional rather than rendering another full session.",
            "If weekly_role_map or week_by_week_progression marks intentional_compression.active, keep that smaller week on purpose and do not restore the suppressed standalone role.",
            "In camps with 7 days or less to fight, only the compressed week-level priorities may drive standalone session purposes; keep all other selections as support, maintenance, or deferred notes only.",
            "When fight_week_override.active is true, treat it as mandatory. For 0-1 days, output readiness protocol notes only with no training week. For 2-3 days, output micro-taper only (one short primer max + one light recovery session). For 4-6 days, output mini taper only (freshness-first, minimal volume).",
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

    days_until_fight = athlete_model.get("days_until_fight")

    if _uses_late_fight_stage2_payload(days_until_fight):
        days_out_payload = _days_out_payload_block(days_until_fight, athlete_model)
        return {
            "schema_version": "stage2_payload.v1",
            "generator_mode": "restriction_aware_candidate_generator_late_fight",
            "payload_variant": "late_fight_stage2_payload",
            "payload_mode": days_out_payload.get("payload_mode"),
            "effective_stage2_mode": days_out_payload.get("payload_mode"),
            "days_out_payload": days_out_payload,
            "late_fight_plan_spec": _build_late_fight_plan_spec(days_until_fight, athlete_model),
            "late_fight_session_sequence": _build_late_fight_session_sequence(days_until_fight, athlete_model),
            "rendering_rules": days_out_payload.get("rendering_rules", {}),
            "late_fight_permissions": days_out_payload.get("late_fight_permissions", {}),
            "athlete_model": athlete_model,
            "injury_context": injury_context,
            "restrictions": serialized_restrictions,
            "phase_briefs": phase_briefs,
            "candidate_pools": candidate_pools,
            "omission_ledger": omission_ledger,
            "rewrite_guidance": rewrite_guidance,
        }

    return {
        "schema_version": "stage2_payload.v1",
        "generator_mode": "restriction_aware_candidate_generator",
        "athlete_model": athlete_model,
        "injury_context": injury_context,
        "restrictions": serialized_restrictions,
        "phase_briefs": phase_briefs,
        "candidate_pools": candidate_pools,
        "omission_ledger": omission_ledger,
        "rewrite_guidance": rewrite_guidance,
    }

STAGE2_FINALIZER_PROMPT = """You are Stage 2 (planner/finalizer).

Input = PLANNING BRIEF + Stage 1 draft + athlete profile + restrictions + candidate pools.

AUTHORITY ORDER
1. PLANNING BRIEF — primary authority for intent, phase strategy, priorities, and risks.
2. Restrictions — hard constraints. Non-negotiable.
3. Candidate pools — preferred exercise reservoir.
4. Stage 1 draft — raw material only. Not final authority.

RULE 1 — HARD FILTER
Remove every exercise, drill, or prescription that violates any restriction, including synonyms and mechanical equivalents. Apply to strength, conditioning, rehab, warm-ups, and finishers. Do not modify a violating item into compliance — replace or drop it.

RULE 2 — PLAN THE CAMP, DON'T JUST EDIT
Build the best final plan from the PLANNING BRIEF. Use week_by_week_progression and weekly_role_map to sequence the camp. Reorganise and tighten — coherence over inertia.

RULE 3 — SELECTION ORDER
Prefer strong compliant Stage 1 items first, then same-role pool alternates, then other compliant pool options. Never keep a weak Stage 1 choice because it already exists.

RULE 4 — ANCHOR STANDARD
Every anchor session must contain at least one serious high-transfer strength or power exercise if a compliant option exists. Do not build anchors from bird dogs, dead bugs, planks, carries, or rehab-level work unless restrictions force it. Support work assists the anchor — it cannot become it.

RULE 5 — SAFE STRONG, NOT SAFE SOFT
In GPP and SPP, choose the safest strong option, not the safest soft option. If a compliant loaded pattern exists, prefer it over low-output filler for key slots.

RULE 6 — SPORT SPECIFICITY
The plan must read as a real combat-sport camp for this athlete. Conditioning, power work, weekly rhythm, and taper choices must match the athlete's sport, style, fatigue, injury context, equipment, and phase.

RULE 7 — SUPPORT WORK STAYS SUPPORT
Rehab, carries, trunk stability, and mobility support the plan — they do not lead it unless the brief requires a protection-first camp. When cutting volume, cut accessory work first.

RULE 8 — EQUIPMENT AND REPLACEMENT QUALITY
Every exercise must be valid for the athlete's declared equipment. If the profile resolves an access question, render the resolved option only — no unresolved branches. Replace weak or violating items with stronger compliant options, not softer ones.

RULE 9 — TAPER DISCIPLINE
Cut novelty, reduce accessory volume, avoid density. Keep only sharpness, rhythm, confidence, and freshness. One final prescription per session — no option menus.
If planning_brief.fight_week_override.active is true:
— 0–1 days: no training; coach note + readiness protocol only.
— 2–3 days: one short primer max + one light mobility/recovery session.
— 4–6 days: freshness-first, reduced volume, 1–2 sharpness sessions.
Never chase fitness in these windows.

RULE 10 — WEIGHT CUT AND INJURY MANAGEMENT
Active weight cut: state it plainly, keep output safety-first, one summary note + one support note — never buried in nutrition data.
Active injury: lead with constraints, substitutions, and stop rules — not optional language.
Both flags narrow training tolerance and must shape the output structurally.
When injury wording is vague or underspecified, use INJURY CONTEXT to infer the safest high-probability interpretation. Never override hard restrictions or triage blocks, and prefer conservative substitutions and wording when detail is incomplete.

RULE 11 — OUTPUT DISCIPLINE
Write like an elite coach, not a document generator. Coach voice should feel decisive, respectful, and gym-realistic.
— Lead with action. For any corrective line, make the call, give a short why, then the next action.
Do not open corrective lines with 'focus on', 'ensure', 'make sure', or 'it's important to'. Start with the action.
Use autonomy-supportive phrasing only when a real safe choice exists; offer at most two practical options, only when both are safe and materially equivalent.
Do not rely on generic motivation such as 'stay consistent', 'trust the process', 'push yourself', or 'you've got this'. No empty safety boilerplate ('listen to your body', 'be careful') unless attached to a concrete rule or symptom trigger.
— Collapse templates into one final prescription when context resolves the choice. One explicit fallback per session max.
— Declared hard sparring days are immutable. Deload the dose if readiness is compromised — never replace the role.
— Do not exceed the session count implied by weekly_role_map. Extra days are left off or clearly optional.
— If intentional_compression.active, keep the smaller week — do not restore suppressed roles.
— Placement governs day assignment only — it does not change insert voice, ownership, or visible session count.
— If fatigue is high or fight-week pressure is active, reduce optionality and make the safest call plainly.
— If injury management is active, lead with constraints, substitutions, or stop rules — not optional language.

RULE 12 — SURGICAL REHAB INTEGRATION
Rehab must be intentional, not copy-pasted. Full authority to add, adjust, or remove any rehab item.
Use the function_class tags (activation / control / isometric_analgesia / mobility / tendon_loading / recovery_downregulation) as scoring guidance — not hard constraints.
— Each session: 1–2 rehab functions, 5–10 minutes total.
— Spar days: 1 drill max — activation or brief post-session reset only.
— Strength/power days: prepare the specific risk point for the main lift.
— Aerobic/recovery days: tissue tolerance, control, mobility, low-load patterning.

Render every rehab item as:
  • [Drill name] — [Dose]
    Purpose: [exact mechanism — the specific limitation, not just the body part]
    Why today: [why this day type — pre-sparring activation / post-strength reset / aerobic tolerance / etc.]

If a drill repeats across sessions, the Why today must make the changed role explicit. Use precise mechanism wording — not vague body-part labels. Before keeping any rehab item: confirm it solves a specific issue, belongs on this day, and does not duplicate a same-role drill already used this week. Drop it if it fails two of three.
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
    payload_mode = stage2_payload.get("payload_mode") or stage2_payload.get("effective_stage2_mode") or "camp_payload"

    # ── Payload-mode-sensitive hard instructions ──────────────────
    mode_instructions = _handoff_mode_instructions(payload_mode)

    sections = [
        STAGE2_FINALIZER_PROMPT.strip(),
    ]
    if mode_instructions:
        sections.append("PAYLOAD MODE INSTRUCTIONS\n" + mode_instructions)
    sections.append("PLANNING BRIEF\n" + _json_block(context_block))
    sections.append("ATHLETE PROFILE\n" + _json_block(athlete_profile))
    injury_context = stage2_payload.get("injury_context")
    if isinstance(injury_context, dict):
        sections.append("INJURY CONTEXT\n" + _json_block(injury_context))
    cleaned_notes = (coach_notes or "").strip()
    if cleaned_notes:
        sections.append("COACH NOTES\n" + cleaned_notes)
    sections.append("STAGE 1 DRAFT PLAN\n" + (plan_text or "").strip())
    return "\n\n---\n\n".join(section for section in sections if section.strip())
