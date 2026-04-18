"""Week-by-week progression, session role slots, sparring lock, day-hint
assignment, and high-fatigue compression — the second layer of the Stage 2
planning brief.

All public functions here are re-exported from stage2_payload for
backward compatibility.
"""
from __future__ import annotations

from typing import Any

from .normalization import clean_list, ordered_weekdays as _ordered_weekdays
from .sparring_dose_planner import (
    compute_hard_sparring_plan,
    effective_hard_day_count,
    effective_hard_days,
    sandwiched_training_days,
)
from .stage2_payload_late_fight import (
    _build_late_fight_week_by_week_progression,
    _build_late_fight_weekly_role_map,
    _days_out_payload_mode,
    _uses_late_fight_stage2_payload,
    _role_anchor,
)
from .stage2_planning_brief import (
    _build_phase_briefs,
    _build_phase_selection_guardrails,
    _build_weekly_stress_map,
    _compress_short_camp_priorities,
    dedupe_preserve_order,
    _derive_athlete_archetype,
    _derive_competitive_maturity,
    _derive_main_limiter,
    _derive_main_risks,
    _derive_readiness_flags,
    _is_high_pressure_weight_cut,
    _priority_bucket_labels,
    _WEEKLY_STAGE_TEMPLATES,
    PLANNING_DECISION_HIERARCHY,
)

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
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
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
                    "build": dedupe_preserve_order(clean_list(brief.get("emphasize", [])) + list(stage.get("emphasize", []))),
                    "protect": dedupe_preserve_order(clean_list(brief.get("risk_flags", [])) + list(stage.get("protect", []))),
                    "deprioritize": dedupe_preserve_order(clean_list(brief.get("deprioritize", [])) + list(stage.get("deprioritize", []))),
                    "must_keep": clean_list(guardrails.get("must_keep_if_present", [])),
                    "drop_order_if_thin": clean_list(guardrails.get("conditioning_drop_order_if_thin", [])),
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
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
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
    must_keep = set(clean_list(resolved_rule_state.get("must_keep", week_entry.get("must_keep", []))))
    drop_order = clean_list(resolved_rule_state.get("drop_order_if_thin", week_entry.get("drop_order_if_thin", [])))
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




def _declared_day_sets(athlete_model: dict) -> tuple[list[str], set[str], set[str]]:
    training_days = _ordered_weekdays(clean_list(athlete_model.get("training_days", [])))
    hard_sparring = {day for day in _ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))) if day in training_days}
    support_work = {
        day
        for day in _ordered_weekdays(
            clean_list(athlete_model.get("support_work_days") or athlete_model.get("technical_skill_days") or [])
        )
        if day in training_days
    }
    return training_days, hard_sparring, support_work


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
    return dedupe_preserve_order([str(value).strip() for value in values if str(value).strip()])


def _append_week_coach_note_flag(week_entry: dict, flag: str) -> None:
    current_flags = _dedupe_clean_strings(clean_list(week_entry.get("coach_note_flags", [])))
    if flag and flag not in current_flags:
        current_flags.append(flag)
    week_entry["coach_note_flags"] = current_flags


def _hard_sparring_coach_note_flags(plan_entry: dict[str, Any] | None = None) -> list[str]:
    status = str((plan_entry or {}).get("status") or "hard_as_planned").strip() or "hard_as_planned"
    return ["deload hard sparring"] if status != "hard_as_planned" else []


def _hard_sparring_role(week_entry: dict, day: str, plan_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    status = str((plan_entry or {}).get("status") or "hard_as_planned").strip() or "hard_as_planned"
    hard_sparring_class = str((plan_entry or {}).get("hard_day_class") or "").strip() or (
        "managed_hard" if status != "hard_as_planned" else "primary_hard"
    )
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
        "hard_sparring_class": hard_sparring_class,
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
        clean_list(week_entry.get("declared_hard_sparring_days") or athlete_model.get("hard_sparring_days", []))
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

    training_days, hard_sparring_days, support_work_days = _declared_day_sets(athlete_model)
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
            if recovery_day in support_work_days:
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
        preferred_aerobic_day = next((day for day in training_days if day in support_work_days and day not in used_days), None)
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
        elif idx == aerobic_idx and day in support_work_days:
            reason = "Use declared Support Work Days (non-hard training days / S&C-compatible slots) for lower-noise support work when possible."
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
    return dedupe_preserve_order(preferred + list(conditioning_sequence or []))


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
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
    if fatigue != "high" and "high_fatigue" not in readiness_flags:
        return []

    reason_codes = ["high_fatigue"]
    hard_spar_count = effective_hard_spar_count
    if hard_spar_count is None:
        hard_spar_count = len(clean_list(athlete_model.get("hard_sparring_days", [])))
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
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
    return bool(readiness_flags & {"active_weight_cut", "aggressive_weight_cut"})


def _active_injury_is_moderate_plus(athlete_model: dict) -> bool:
    """True when the athlete has an active injury or restriction at moderate or greater severity."""
    if athlete_model.get("injuries"):
        return True
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
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

    training_days = _ordered_weekdays(clean_list(athlete_model.get("training_days", [])))
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

    # Structural rule: suppress glycolytic on days sandwiched between two effective hard spar days.
    # This fires unconditionally — it is not gated on fatigue or compression signals.
    _effective_spar_days = set(effective_hard_days(hard_sparring_plan or []))
    if len(_effective_spar_days) >= 2:
        _resolved = dict(week_entry.get("resolved_rule_state") or {})
        _must_keep_early = set(clean_list(_resolved.get("must_keep", week_entry.get("must_keep", []))))
        _sandwiched = sandwiched_training_days(training_days, _effective_spar_days)
        if _sandwiched:
            _kept: list[dict] = []
            for _role in session_roles:
                if (
                    _role.get("category") == "conditioning"
                    and _role.get("preferred_system") == "glycolytic"
                    and _role.get("preferred_system") not in _must_keep_early
                    and str(_role.get("scheduled_day_hint") or "").strip() in _sandwiched
                ):
                    suppressed_roles = list(suppressed_roles) + [
                        _make_compression_suppression(
                            _role,
                            ["sandwiched_hard_days"],
                            "Glycolytic session falls between two hard sparring days — suppressed to protect recovery between hard contacts.",
                        )
                    ]
                else:
                    _kept.append(_role)
            session_roles = _kept

    # Step 1: Count sparring against the weekly cap
    hard_sparring_days_set = set(_ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))))
    sessions_per_week = int(athlete_model.get("training_frequency") or len(training_days))
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
    must_keep = set(clean_list(resolved_rule_state.get("must_keep", week_entry.get("must_keep", []))))

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
        clean_list(week_entry.get("declared_hard_sparring_days") or athlete_model.get("hard_sparring_days"))
    )
    resolved_rule_state = dict(week_entry.get("resolved_rule_state") or {})
    must_keep = set(clean_list(resolved_rule_state.get("must_keep", week_entry.get("must_keep", []))))
    training_days = _ordered_weekdays(clean_list(athlete_model.get("training_days", [])))
    effective_days = set(effective_hard_days(hard_sparring_plan or []))
    has_downgraded_declared_day = bool(declared_hard_days) and len(effective_days) < len(declared_hard_days)
    blocked_follow_on_days = _next_training_days_after_effective_hard_spar(training_days, effective_days)
    summary = _compression_summary(reason_codes)

    kept_roles = list(session_roles)
    updated_suppressed = list(suppressed_roles)

    if has_downgraded_declared_day:
        _append_week_coach_note_flag(week_entry, "deload hard sparring")

    sandwiched_days = sandwiched_training_days(training_days, effective_days)
    removable_role: dict[str, Any] | None = None
    glycolytic_role = next(
        (
            role for role in kept_roles
            if role.get("category") == "conditioning" and role.get("preferred_system") == "glycolytic"
        ),
        None,
    )
    if glycolytic_role is not None and glycolytic_role.get("preferred_system") not in must_keep:
        glycolytic_day = str(glycolytic_role.get("scheduled_day_hint") or "").strip()
        on_follow_on = glycolytic_day in blocked_follow_on_days and has_downgraded_declared_day
        on_sandwiched = glycolytic_day in sandwiched_days
        if on_follow_on or on_sandwiched:
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
                "declared_hard_sparring_days": _ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))),
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
                "declared_training_days": _ordered_weekdays(clean_list(athlete_model.get("training_days", []))),
                "declared_hard_sparring_days": _ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))),
                "declared_support_work_days": _ordered_weekdays(clean_list(athlete_model.get("support_work_days", athlete_model.get("technical_skill_days", [])))),
                "declared_technical_skill_days": _ordered_weekdays(clean_list(athlete_model.get("technical_skill_days", []))),
                "hard_sparring_plan": hard_sparring_plan,
                "effective_hard_sparring_days": list(effective_days),
                "coach_note_flags": _dedupe_clean_strings(clean_list(week_entry.get("coach_note_flags", []))),
                "intentional_compression": dict(week_entry.get("intentional_compression") or _intentional_compression_stub()),
                "intentionally_unused_days": list(week_entry.get("intentionally_unused_days") or []),
                "session_roles": session_roles,
                "suppressed_roles": suppressed_roles,
            }
        )

    # Legacy fight_week_override compatibility (acts as further filter if still active)
    if fight_week_override and fight_week_override.get("active"):
        band = str(fight_week_override.get("band") or "")
        if band == "final_day_protocol":
            weeks = []
        else:
            allowed_roles = set(clean_list(fight_week_override.get("allowed_session_roles", [])))
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
                    clean_list(week.get("coach_note_flags", [])) + ["fight-week override active"]
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
