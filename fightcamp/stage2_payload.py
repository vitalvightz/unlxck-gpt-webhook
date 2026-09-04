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

from . import stage2_planning_brief as stage2_planning_brief_module
from .stage2_finalizer_packet import build_stage2_finalizer_packet
from .stage2_llm_boundary import build_stage2_llm_planning_brief
from .stage2_payload_open_ongoing import (
    _uses_open_ongoing_payload,
    build_open_ongoing_payload,
)
from . import stage2_role_map as stage2_role_map_module
from .stage2_payload_late_fight import (  # noqa: F401  (re-exported for tests/back-compat)
    CANONICAL_HARD_SPARRING_BAN_LABEL,
    CANONICAL_HARD_SPARRING_LABEL,
    CANONICAL_HARD_SPARRING_NOTE,
    CANONICAL_TECHNICAL_ONLY_NOTE,
    _build_late_fight_plan_spec,
    _build_late_fight_session_sequence,
    _build_late_fight_week_by_week_progression,
    _build_late_fight_weekly_role_map,
    _camp_downstream_countdown_continuation,
    _days_out_payload_block,
    _days_out_payload_mode,
    _fight_week_override_payload,
    _handoff_mode_instructions,
    _is_app_owned_visible_role,
    _late_fight_permissions,
    _late_fight_rendering_rules,
    _visible_calendar_session_sequence,
    _resolve_late_fight_phase,
    _uses_late_fight_stage2_payload,
    ensure_declared_coach_combat_spine,
    is_low_cost_coexistable_filler,
)
from .gap_fill_inserts import apply_gap_fill_inserts
from .conditioning import athlete_facing_system_label, technical_footwork_prescription_fields
from .fight_day_override import apply_fight_day_override_to_weekly_role_map
from .role_labels import stamp_weekly_role_map_labels
from .camp_week_fillers import apply_camp_week_fillers
from .late_camp_role_morph import apply_late_camp_role_morph
from .prescription_resolver import apply_effective_strength_prescriptions
from .normal_calendar_placement import fill_missing_session_days
from .late_selector_windows import classify_late_selector_window
from .normalization import (  # noqa: F401  (phrase_in_text re-exported for back-compat)
    clean_list,
    dedupe_preserve_order,
    normalize_fatigue_level,
    normalize_text,
    phrase_in_text,
    slugify,
)
from .rehab_protocols import (
    _FUNCTION_LABELS,
    _is_surface_type,
    classify_drill_function,
    rehab_drill_options_for_phase,
)
from .restriction_parsing import CANONICAL_RESTRICTIONS  # noqa: F401  (re-exported for back-compat)
from .priority_profile import build_priority_profile, describe_priority_focus
from .selection_metadata import build_score_evidence, normalize_selection_metadata
from .stage2_render_guards import (  # noqa: F401  (re-exported for backwards compatibility)
    _NO_ACTIVE_INJURY_MARKERS,
    _all_active_injuries_surface_only,
    _append_render_guard_writing_rules,
    _has_active_injury_from_athlete_model,
    _has_active_injury_from_training_context,
    _meaningful_injury_values,
    _render_guard_flags,
)
from .sparring_dose_planner import (
    effective_hard_day_count,
    effective_hard_days,
    sandwiched_training_days,
)
from .calendar_context import (
    CalendarLegalityView,
    classify_role,
    normal_week_legality,
    week_scope,
    weekday_position,
)
from .combat_load_policy import PlacementDirective
from .strength_session_quality import classify_strength_item, infer_strength_sessions
from .training_context import TrainingContext, allocate_sessions
from .nutrition import compute_nutrition_targets
from .recovery import compute_recovery_plan
from .mindset_module import compute_mindset_plan
from .weight_cut import (  # noqa: F401  (re-exported for back-compat)
    compute_cut_severity_score,
    cut_severity_bucket,
)

# Re-export from sub-modules for backward compatibility. Names that are also
# defined locally further down this file are intentionally omitted here because
# the local definitions are the canonical ones — they shadow the imports at
# execution time, so listing them under "re-export" only triggers F811 noise.
from .stage2_planning_brief import (  # noqa: F401
    CONDITIONING_ROLE_PURPOSES,
    PHASE_CONDITIONING_PRIORITY,
    PHASE_DEPRIORITIZE,
    PHASE_EMPHASIS,
    PHASE_OBJECTIVES,
    PHASE_SELECTION_GUARDRAILS,
    PLANNING_DECISION_HIERARCHY,
    RESTRICTION_PATTERN_HINTS,
    _MECHANICAL_TAG_PREFIXES,
    _MECHANICAL_TAGS,
    _RESTRICTION_CANONICAL_KEYS,
    _LIMITER_PROFILES,
    _SPORT_LOAD_PROFILES,
    _UNKNOWN_COMPETITIVE_MATURITY,
    _WEEKLY_STAGE_TEMPLATES,
    _build_athlete_model,
    _build_limiter_profile,
    _build_phase_selection_guardrails,
    _build_sport_load_profile,
    _build_weekly_stress_map,
    _conditioning_slot_priority,
    _derive_athlete_archetype,
    _derive_competitive_maturity,
    _derive_main_limiter,
    _derive_main_risks,
    _derive_readiness_flags,
    _downgrade_priority,
    _extract_mechanical_risk_tags,
    _extract_restriction_tags,
    _is_high_pressure_weight_cut,
    _normalize_limiter_tokens,
    _parse_record,
    _primary_sport_load_key,
    _priority_bucket,
    _priority_bucket_labels,
    _priority_value,
    _resolve_phase_rule_state,
    _serialize_restrictions,
    _strength_slot_priority,
)
from .stage2_role_map import (  # noqa: F401
    _append_day_hint,
    _athlete_sport_key,
    _apply_short_camp_role_compression,
    _build_week_by_week_progression,
    _compression_floor_value,
    _compression_summary,
    _compute_intentionally_unused_days,
    _final_week_sparring_cap_summary,
    _hard_sparring_coach_note_flags,
    _hard_sparring_role,
    _high_fatigue_compression_reason_codes,
    _make_compression_suppression,
    _make_final_week_sparring_cap_suppression,
    _make_hard_sparring_lock_suppression,
    _next_training_days_after_effective_hard_spar,
    _phase_progression_slot_count,
    _placement_rule_for_anchor,
    _preferred_boxer_conditioning_sequence,
    _progression_templates_for_phase,
    _replaceable_role_priority,
    _resequence_session_roles,
    _role_governance,
    _rotate_weekdays_from_plan_start,
    _short_camp_priority_catalog,
    _strength_role_key,
    _conditioning_role_key,
    _split_phase_days,
)







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





def _compress_short_camp_priorities(athlete_model: dict) -> dict:
    return stage2_planning_brief_module._compress_short_camp_priorities(athlete_model)


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













_PRIMARY_STRENGTH_ROLE_KEYS = {
    "primary_strength_day",
    "structural_strength_day",
    "neural_plus_strength_day",
    "neural_primer_day",
}
_LOW_LOAD_SUPPORT_ROLE_KEYS = {
    "recovery_reset_day",
    "tissue_recovery_day",
    "aerobic_support_day",
    "aerobic_base_day",
    "aerobic_coordination_day",
    "repeatability_support_day",
    "controlled_repeatability_day",
    "technical_touch_day",
    "fight_week_freshness_day",
}
_OPTIONAL_ALACTIC_ROLE_KEYS = {
    "alactic_sharpness_day",
    "alactic_speed_day",
    "alactic_support_day",
    "alactic_coordination_day",
}
_CROWDED_ANCHOR_FORBIDDEN_TOKENS = [
    "standalone_glycolytic",
    "hinge_transfer",
    "contrast_work",
    "jumps",
    "sharpness_touch",
    "hard_sparring",
]
_CROWDED_SUPPORT_FORBIDDEN_TOKENS = [
    "primary_strength_anchor",
    "standalone_glycolytic",
    "hinge_transfer",
    "contrast_work",
    "jumps",
    "sharpness_touch",
    "hard_sparring",
]
_WEEKDAY_ORDER = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _normalized_fatigue_level(athlete_model: dict) -> str:
    return normalize_fatigue_level(athlete_model)


def _ordered_weekdays(values: list[str]) -> list[str]:
    cleaned = _dedupe_preserve_order([str(value).strip() for value in values if str(value).strip()])
    return sorted(cleaned, key=lambda day: (_WEEKDAY_ORDER.get(day.strip().lower(), 99), day.strip().lower()))


def _dedupe_clean_strings(values: list[Any]) -> list[str]:
    return _dedupe_preserve_order([str(value).strip() for value in values if str(value).strip()])


def _is_anchor_role(role: dict[str, Any]) -> bool:
    return role.get("category") == "strength" and role.get("role_key") in _PRIMARY_STRENGTH_ROLE_KEYS


def _is_low_load_support_role(role: dict[str, Any]) -> bool:
    if role.get("category") == "recovery":
        return True
    if role.get("category") == "conditioning" and role.get("preferred_system") == "aerobic":
        return True
    return str(role.get("role_key") or "").strip() in _LOW_LOAD_SUPPORT_ROLE_KEYS


def _is_optional_alactic_role(role: dict[str, Any]) -> bool:
    if role.get("category") == "conditioning" and role.get("preferred_system") == "alactic":
        return True
    return str(role.get("role_key") or "").strip() in _OPTIONAL_ALACTIC_ROLE_KEYS


def _main_job_for_role(role: dict[str, Any]) -> str:
    role_key = str(role.get("role_key") or "").strip()
    if role_key == "hard_sparring_day":
        return "hard_sparring"
    if _is_anchor_role(role):
        return "anchor"
    if _is_low_load_support_role(role):
        return "support_recovery"
    if role.get("category") == "conditioning":
        return "conditioning"
    return role_key or str(role.get("category") or "").strip()


def _apply_day_identity_governance(role: dict[str, Any], *, crowded_week_active: bool) -> None:
    governance = dict(role.get("governance") or {})
    main_job = _main_job_for_role(role)
    governance["main_job"] = main_job

    if crowded_week_active and main_job == "anchor":
        governance["support_cap"] = "light_only"
        governance["forbidden_secondary_stressors"] = list(_CROWDED_ANCHOR_FORBIDDEN_TOKENS)
    elif crowded_week_active and main_job == "support_recovery":
        governance["support_cap"] = "light_only"
        governance["forbidden_secondary_stressors"] = list(_CROWDED_SUPPORT_FORBIDDEN_TOKENS)
    else:
        governance.setdefault("support_cap", "")
        governance.setdefault("forbidden_secondary_stressors", [])

    role["governance"] = governance


def _append_week_coach_note_flag(week_entry: dict, flag: str) -> None:
    current_flags = _dedupe_clean_strings(_clean_list(week_entry.get("coach_note_flags", [])))
    if flag and flag not in current_flags:
        current_flags.append(flag)
    week_entry["coach_note_flags"] = current_flags






def _is_meaningful_stressor(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip()
    if role_key in {"main_conditioning_stressor", "fight_pace_block", "full_neural_session"}:
        return True
    main_job = _main_job_for_role(role)
    if main_job in {"hard_sparring", "anchor"}:
        return True
    if main_job == "conditioning":
        system = str(role.get("preferred_system") or "").strip().lower()
        if system == "glycolytic":
            return True
        if role_key in {
            "fight_pace_repeatability_day",
            "light_fight_pace_touch_day",
        }:
            return True
    load_tokens = {
        str(token).strip().lower()
        for token in (
            list(role.get("stress_flags") or [])
            + list(role.get("load_flags") or [])
            + list(role.get("tags") or [])
            + list((role.get("governance") or {}).get("load_flags") or [])
        )
        if str(token).strip()
    }
    if {"high_cns", "high_neural", "high_metabolic", "high_load", "main_conditioning_stressor"} & load_tokens:
        return True
    return False




def _intentional_compression_stub() -> dict[str, Any]:
    return {
        "active": False,
        "policy": "",
        "risk_signals": [],
        "reason_codes": [],
        "reason": "",
        "summary": "",
        "max_non_spar_roles": None,
        "max_support_roles": None,
        "standalone_glycolytic_allowed": True,
    }


def _active_weight_cut_is_meaningful(athlete_model: dict) -> bool:
    """Compatibility wrapper; keep stage2_payload behavior aligned with stage2_role_map."""
    return stage2_role_map_module._active_weight_cut_is_meaningful(athlete_model)


def _cut_severity_compression_points(athlete_model: dict) -> int:
    """Compatibility wrapper; keep stage2_payload behavior aligned with stage2_role_map."""
    return stage2_role_map_module._cut_severity_compression_points(athlete_model)


def _active_injury_affects_generic_compression(athlete_model: dict) -> bool:
    """True when the generic readiness layer should count injury pressure."""
    # A stable surface/skin-only injury is a hygiene note, not injured tissue —
    # it must not add compression pressure.
    if _all_active_injuries_surface_only(athlete_model):
        return False
    if athlete_model.get("injuries"):
        return True
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    return "injury_management" in readiness_flags


def _active_injury_is_moderate_plus(athlete_model: dict) -> bool:
    """True when the boxing crowded-week trigger sees moderate+ injury pressure."""
    # A stable surface/skin-only injury never counts as moderate+ tissue pressure.
    if _all_active_injuries_surface_only(athlete_model):
        return False
    injuries = _clean_list(athlete_model.get("injuries", []))
    readiness_flags = set(_clean_list(athlete_model.get("readiness_flags", [])))
    if readiness_flags & {"injury_management", "moderate_injury", "significant_injury", "severe_injury"}:
        return True
    for entry in injuries:
        lowered = entry.lower()
        if any(token in lowered for token in ("moderate", "severe", "major", "significant", "grade 2", "grade ii", "grade 3", "grade iii")):
            return True
    return False


def _compute_readiness_compression(athlete_model: dict) -> int:
    """
    Compute readiness compression score (0–5) based on:
    - High fatigue (+1)
    - Active cut severity (+0/+1/+2)
    - Active injury/restriction at moderate or greater severity (+1)
    - Proximity to fight (≤17 days) (+1)
    """
    compression = 0
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    if fatigue == "high":
        compression += 1
    compression += _cut_severity_compression_points(athlete_model)
    if _active_injury_affects_generic_compression(athlete_model):
        compression += 1
    days_to_fight = athlete_model.get("days_until_fight")
    if isinstance(days_to_fight, int) and 0 <= days_to_fight <= 17:
        compression += 1
    return compression


def _non_spar_role_priority_rank(
    role: dict,
    phase: str,
    is_hard_spar_week: bool,
    is_meaningful_cut: bool,
    must_keep: set[str] | None = None,
    *,
    crowded_week: bool = False,
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

    if crowded_week:
        if _is_anchor_role(role):
            return 5
        if _is_low_load_support_role(role):
            return 4
        if _is_optional_alactic_role(role):
            return 3
        if role_key == "fight_pace_repeatability_day" or (category == "conditioning" and preferred_system == "glycolytic"):
            return 2
        if category == "strength":
            return 1
        return 2

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
    if _active_injury_affects_generic_compression(athlete_model):
        reason_codes.append("injury_management")
    days_to_fight = athlete_model.get("days_until_fight")
    if isinstance(days_to_fight, int) and 0 <= days_to_fight <= 17:
        reason_codes.append("proximity_to_fight")
    return reason_codes


def _forbidden_between_effective_hard_contacts(
    role: dict[str, Any], day: str, legality: CalendarLegalityView
) -> bool:
    """Ask ``combat_load_policy`` whether ``role`` may sit between two hard contacts.

    Contact-spacing legality is owned by :mod:`combat_load_policy`; Stage 2 delegates
    to it via the shared :mod:`calendar_context` classifier rather than re-deriving a
    local allow-list. A role the shared classifier cannot place (``None`` — e.g. a
    visible contact mirror, whose contact is owned by ``hard_sparring_plan``) is left
    for its owner and is not suppressed here.
    """
    profile = classify_role(role)
    if profile is None:
        return False
    position = weekday_position(day)
    if position is None:
        return False
    return (
        legality.decision_at_position(profile, position).directive
        is PlacementDirective.FORBID
    )


def _suppress_sandwiched_glycolytic(
    week_entry: dict,
    session_roles: list[dict],
    suppressed_roles: list[dict],
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Suppress roles scheduled between two effective hard sparring days whose load the
    shared policy forbids there. Not gated on fatigue or compression signals — it's a
    structural invariant about recovery windows between hard contacts.

    The "which loads are legal between two hard contacts" decision is owned by
    ``combat_load_policy`` and consulted through :func:`_forbidden_between_effective_hard_contacts`;
    Stage 2 only locates sandwiched days (from resolved contact state) and enforces the
    policy's answer, preserving the ``must_keep`` role-budget override.
    """
    effective_spar_days = set(effective_hard_days(hard_sparring_plan or []))
    if len(effective_spar_days) < 2:
        return session_roles, suppressed_roles

    training_days = _ordered_weekdays(_clean_list(athlete_model.get("training_days", [])))
    sandwiched = sandwiched_training_days(training_days, effective_spar_days)
    if not sandwiched:
        return session_roles, suppressed_roles
    legality = normal_week_legality(
        hard_sparring_plan,
        [],
        scope=week_scope(week_entry),
    )

    resolved = dict(week_entry.get("resolved_rule_state") or {})
    must_keep = set(_clean_list(resolved.get("must_keep", week_entry.get("must_keep", []))))

    kept: list[dict] = []
    updated_suppressed = list(suppressed_roles)
    for role in session_roles:
        on_sandwiched_day = str(role.get("scheduled_day_hint") or "").strip() in sandwiched
        if on_sandwiched_day and role.get("preferred_system") in must_keep:
            kept.append(role)
            continue

        should_suppress = on_sandwiched_day and _forbidden_between_effective_hard_contacts(
            role,
            str(role.get("scheduled_day_hint") or "").strip(),
            legality,
        )
        if should_suppress:
            updated_suppressed.append(
                _make_compression_suppression(
                    role,
                    ["sandwiched_hard_days"],
                    "Session falls between two hard sparring days and is not low-load support — suppressed to protect recovery between hard contacts.",
                )
            )
        else:
            kept.append(role)
    return kept, updated_suppressed


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

    # Structural rule: suppress glycolytic on days sandwiched between two effective hard spar
    # days. Fires unconditionally before sport-specific dispatch so it applies to all paths
    # (boxing crowded-week, boxing early-exit, and the general spar-first cap).
    session_roles, suppressed_roles = _suppress_sandwiched_glycolytic(
        week_entry,
        session_roles,
        suppressed_roles,
        athlete_model,
        hard_sparring_plan=hard_sparring_plan,
    )

    boxing_policy_state = stage2_role_map_module._boxing_crowded_week_policy_state(week_entry, athlete_model)
    if boxing_policy_state["active"]:
        return stage2_role_map_module._apply_boxing_crowded_week_compression(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
        )
    if _athlete_sport_key(athlete_model) == "boxing":
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
    """Compatibility wrapper for the single weekly role-map implementation."""
    return stage2_role_map_module._build_weekly_role_map(
        athlete_model,
        week_by_week_progression,
        limiter_profile,
        fight_week_override=fight_week_override,
    )


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
    support_work_days = _clean_list(
        athlete_model.get("support_work_days", athlete_model.get("technical_skill_days", []))
    )
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
    if support_work_days:
        preserve.append("Use declared support work days for lower-noise support work when the weekly rhythm needs a lighter combat touch.")
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


def _slot_exercise_name(slot: dict[str, Any]) -> str:
    for key in ("selected", "primary", "exercise", "drill"):
        value = slot.get(key)
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("exercise_name") or value.get("drill_name") or "").strip()
            if name:
                return name
    return str(slot.get("name") or slot.get("exercise_name") or slot.get("drill_name") or "").strip()


def _slot_selected_option(slot: dict[str, Any]) -> dict[str, Any]:
    selected = slot.get("selected")
    return selected if isinstance(selected, dict) else {}


def _slot_text(slot: dict[str, Any]) -> str:
    selected = _slot_selected_option(slot)
    parts = [
        str(slot.get("role") or ""),
        str(slot.get("purpose") or ""),
        str(slot.get("quality_class") or ""),
        str(selected.get("quality_class") or ""),
        str(selected.get("prescription") or ""),
        " ".join(clean_list(selected.get("movement_patterns"))),
        " ".join(clean_list(selected.get("restriction_tags"))),
        " ".join(clean_list(selected.get("mechanical_risk_tags"))),
    ]
    return " ".join(part for part in parts if part).lower()


def _slot_countdown_labels(slot: dict[str, Any]) -> list[str]:
    selected = _slot_selected_option(slot)
    labels: list[str] = []
    for source in (slot, selected):
        for key in ("scheduled_countdown_label", "countdown_label", "days_out_bucket"):
            value = source.get(key)
            if value:
                labels.append(str(value))
        labels.extend(clean_list(source.get("allowed_countdown_labels")))
        labels.extend(clean_list(source.get("countdown_labels")))
    return dedupe_preserve_order(labels)


def _slot_support_only(slot: dict[str, Any]) -> bool:
    selected = _slot_selected_option(slot)
    return bool(slot.get("support_only") or selected.get("support_only"))


def _slot_anchor_capable(slot: dict[str, Any]) -> bool:
    selected = _slot_selected_option(slot)
    return bool(slot.get("anchor_capable") or selected.get("anchor_capable"))


def _slot_is_low_load_reset(slot: dict[str, Any]) -> bool:
    text = _slot_text(slot)
    return _slot_support_only(slot) or any(
        phrase in text
        for phrase in ("rehab", "prehab", "mobility", "breathing", "reset", "recovery")
    )


def _slot_matches_late_fight_role(slot: dict[str, Any], slot_group: str, role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip()
    preferred_system = str(role.get("preferred_system") or "").strip().lower()
    slot_role = str(slot.get("role") or "").strip().lower()
    text = _slot_text(slot)

    if slot_group == "rehab_slots":
        return role_key in {"fight_week_freshness_day", "technical_touch_day"}
    if slot_group == "conditioning_slots":
        if preferred_system:
            return slot_role == preferred_system
        return role_key in {"alactic_sharpness_day", "light_fight_pace_touch_day", "technical_touch_day"}
    if slot_group != "strength_slots":
        return False

    if role_key == "strength_touch_day":
        return _slot_anchor_capable(slot) and not _slot_is_low_load_reset(slot)
    if role_key == "neural_primer_day":
        return _slot_anchor_capable(slot) and any(
            phrase in text
            for phrase in ("isometric", "neural", "primer", "speed", "rate_of_force", "coordination")
        )
    if role_key == "technical_touch_day":
        return any(
            phrase in text
            for phrase in ("shadowboxing", "shadow boxing", "technical", "footwork", "skill_refinement", "coordination")
        ) and not any(phrase in text for phrase in ("loaded", "heavy", "trap_bar", "deadlift"))
    if role_key == "fight_week_freshness_day":
        return _slot_is_low_load_reset(slot)
    return False


def _scheduled_late_fight_roles(spec: dict[str, Any]) -> list[dict[str, Any]]:
    roles = spec.get("visible_session_sequence") or spec.get("session_sequence") or []
    return [role for role in roles if isinstance(role, dict) and str(role.get("scheduled_countdown_label") or "")]


def _candidate_slots_for_role(candidate_pools: dict[str, dict], role: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    matched: list[tuple[str, str, dict[str, Any]]] = []
    for phase, pool in (candidate_pools or {}).items():
        if not isinstance(pool, dict):
            continue
        for slot_group in ("strength_slots", "conditioning_slots", "rehab_slots"):
            for slot in pool.get(slot_group, []) or []:
                if not isinstance(slot, dict) or not _slot_exercise_name(slot):
                    continue
                if _slot_matches_late_fight_role(slot, slot_group, role):
                    matched.append((str(phase), slot_group, slot))
    return matched


# Mirror of the Stage 2 validator's D-1 safety rule
# (stage2_validator: ``dangerous_late_fight_strength_or_conditioning``). Any
# loaded strength or conditioning exposure rendered on D-1 is a hard blocker, so
# the allocator must never assign such an exercise to that day — D-1 stays a
# breathing / mobility / technical-cue primer only.
_LATE_FIGHT_D1_UNSAFE_NAME = re.compile(
    r"\b(strength|conditioning|sprints?|interval|heavy|loaded|deadlift|squat|trap[-_ ]bar|barbell"
    r"|band(?:s|ed)?|dumbbells?|kettlebells?|med(?:icine)?[-_ ]ball|slam[-_ ]ball|sled|sandbag"
    r"|cable|landmine|weight[-_ ]vest|pull[-_ ]?up)\b",
    re.IGNORECASE,
)

# Lazily built name -> requires-equipment map covering the strength,
# conditioning, and coordination banks. D-1 allows no equipment of any kind,
# so any bank exercise that needs equipment must never be assigned there.
_D1_EQUIPMENT_BY_NAME: dict[str, bool] | None = None


def _bank_requires_equipment(name: str) -> bool:
    global _D1_EQUIPMENT_BY_NAME
    if _D1_EQUIPMENT_BY_NAME is None:
        from .bank_schema import requires_equipment
        from .conditioning import get_conditioning_bank, get_coordination_bank
        from .strength import get_exercise_bank

        requirements: dict[str, bool] = {}
        for bank in (get_exercise_bank(), get_conditioning_bank(), get_coordination_bank()):
            for item in bank:
                item_name = str(item.get("name") or "").strip().lower()
                if item_name:
                    # A name duplicated across banks stays equipment-required
                    # if any version of it requires equipment.
                    requirements[item_name] = requirements.get(item_name, False) or requires_equipment(item)
        _D1_EQUIPMENT_BY_NAME = requirements
    return _D1_EQUIPMENT_BY_NAME.get(str(name or "").strip().lower(), False)


def _late_fight_assignment_is_unsafe(day_label: str, name: str) -> bool:
    """Return True when ``name`` must not be assigned to ``day_label``.

    Today this only guards D-1, matching the validator's D-1 blocker exactly:
    loaded/strength/conditioning name signals plus any bank exercise that
    requires equipment (D-1 is equipment-free).
    """
    if str(day_label or "").strip().upper() != "D-1":
        return False
    if _LATE_FIGHT_D1_UNSAFE_NAME.search(str(name or "")):
        return True
    return _bank_requires_equipment(name)


def _build_late_fight_allowed_exercises_by_day(
    *,
    spec: dict[str, Any],
    candidate_pools: dict[str, dict],
) -> tuple[dict[str, list[str]], dict[str, list[dict[str, Any]]]]:
    allowed_by_day: dict[str, list[str]] = {}
    assignments_by_day: dict[str, list[dict[str, Any]]] = {}
    consumed_slot_ids: set[str] = set()

    for role in _scheduled_late_fight_roles(spec):
        day_label = str(role.get("scheduled_countdown_label") or role.get("countdown_label") or "").strip()
        if not day_label:
            continue
        allowed_by_day.setdefault(day_label, [])
        assignments_by_day.setdefault(day_label, [])

        explicit_matches: list[tuple[str, str, dict[str, Any]]] = []
        fallback_matches: list[tuple[str, str, dict[str, Any]]] = []
        for phase, slot_group, slot in _candidate_slots_for_role(candidate_pools, role):
            # Drop day-unsafe candidates (e.g. loaded work on D-1) before
            # selection so a safe explicit match or fallback can still be used
            # instead of leaving the day empty.
            if _late_fight_assignment_is_unsafe(day_label, _slot_exercise_name(slot)):
                continue
            slot_id = str(slot.get("slot_id") or f"{phase}:{slot_group}:{_slot_exercise_name(slot)}")
            labels = _slot_countdown_labels(slot)
            if labels:
                if day_label in labels:
                    explicit_matches.append((phase, slot_group, slot))
                continue
            if slot_id not in consumed_slot_ids:
                fallback_matches.append((phase, slot_group, slot))

        selected_matches = explicit_matches or fallback_matches[:1]
        for phase, slot_group, slot in selected_matches:
            name = _slot_exercise_name(slot)
            if not name:
                continue
            slot_id = str(slot.get("slot_id") or f"{phase}:{slot_group}:{name}")
            if not _slot_countdown_labels(slot):
                consumed_slot_ids.add(slot_id)
            allowed_by_day[day_label].append(name)
            assignments_by_day[day_label].append(
                {
                    "name": name,
                    "role_key": role.get("role_key"),
                    "scheduled_countdown_label": day_label,
                    "slot_id": slot.get("slot_id"),
                    "slot_group": slot_group,
                    "phase": phase,
                }
            )

    return (
        {day: dedupe_preserve_order(names) for day, names in allowed_by_day.items()},
        assignments_by_day,
    )


def _late_fight_countdown_days_from_spec(days_until_fight: Any, spec: dict[str, Any]) -> list[int]:
    days: list[int] = []
    for segment in spec.get("countdown_mode_sequence", []) or []:
        if not isinstance(segment, dict):
            continue
        start_day = segment.get("start_day")
        end_day = segment.get("end_day")
        if isinstance(start_day, int) and isinstance(end_day, int):
            days.extend(range(start_day, end_day - 1, -1))
    if days:
        return dedupe_preserve_order(days)
    try:
        day = int(days_until_fight)
    except (TypeError, ValueError):
        return []
    return [day] if day >= 0 else []


def _with_late_fight_allowed_exercises(
    *,
    spec: dict[str, Any],
    candidate_pools: dict[str, dict],
    days_until_fight: Any,
) -> dict[str, Any]:
    allowed_by_day, assignments_by_day = _build_late_fight_allowed_exercises_by_day(
        spec=spec,
        candidate_pools=candidate_pools,
    )
    for day in _late_fight_countdown_days_from_spec(days_until_fight, spec):
        allowed_by_day.setdefault(f"D-{day}", [])
    return {
        **spec,
        "allowed_exercises_by_day": allowed_by_day,
        "allowed_exercise_assignments_by_day": assignments_by_day,
    }


def _apply_boxing_crowded_week_post_processing(
    weekly_role_map: dict[str, Any],
    *,
    athlete_model: dict[str, Any],
) -> None:
    """Decorate roles using crowded-week truth already owned by the role map.

    ``athlete_model`` remains in the compatibility signature, but this payload
    layer must not use it to re-evaluate compression or role survival.
    """
    del athlete_model
    weeks = weekly_role_map.get("weeks")
    if not isinstance(weeks, list):
        return
    for week_entry in weeks:
        if not isinstance(week_entry, dict):
            continue
        compression = week_entry.get("intentional_compression")
        crowded_week_active = (
            isinstance(compression, dict)
            and compression.get("policy") == "boxing_crowded_week"
        )
        for role in week_entry.get("session_roles") or []:
            if isinstance(role, dict):
                _apply_day_identity_governance(role, crowded_week_active=crowded_week_active)


def build_computed_support(*, flags: dict, phases: list[str] | None = None) -> dict:
    """Bundle Stage 1's own computed nutrition/recovery/mindset numbers.

    Carries the deterministic Stage 1 support data into the planning brief as
    structured (not prose) blocks so the Stage 1 → structured_plan conversion
    consumes them faithfully instead of re-deriving them from compressed
    markdown. ``coach_gated`` sub-sections inside nutrition/recovery hold exact
    acute weight-cut and supplement dosing and must never be surfaced directly
    to athletes (coach/medical-gated only).
    """
    active_phases = [str(p).upper() for p in (phases or ["GPP", "SPP", "TAPER"])]
    # De-dup while preserving order.
    ordered_phases = list(dict.fromkeys(active_phases))

    nutrition_by_phase = {
        phase: compute_nutrition_targets(flags={**flags, "phase": phase})
        for phase in ordered_phases
    }
    recovery_by_phase = {
        phase: compute_recovery_plan({**flags, "phase": phase})
        for phase in ordered_phases
    }
    return {
        "schema_version": "computed_support.v1",
        "source": "stage1_deterministic",
        "athlete_facing_note": (
            "coach_gated sub-sections hold acute weight-cut and supplement "
            "dosing — never surface them directly to athletes."
        ),
        "nutrition": {"by_phase": nutrition_by_phase},
        "recovery": {"by_phase": recovery_by_phase},
        "mindset": compute_mindset_plan(flags),
        # Deterministic safeguard state travels with the deterministic numbers.
        # The structured-plan safety audit reads this to decide whether Stage 2
        # wording is allowed to mention a cut at all, which is how "AI is
        # subordinate to the deterministic safety rules" is actually enforced
        # rather than merely asserted.
        "safeguards": {"is_minor": bool(flags.get("is_minor", False))},
    }


def build_planning_brief(
    *, athlete_model: dict, restrictions: list[dict], phase_briefs: dict[str, dict],
    candidate_pools: dict[str, dict], omission_ledger: dict[str, dict],
    rewrite_guidance: dict, plan_input: Any | None = None,
    computed_support: dict | None = None,
) -> dict:
    from .goal_preservation import reconcile_goal_preservation

    brief = _build_planning_brief(
        athlete_model=athlete_model, restrictions=restrictions, phase_briefs=phase_briefs,
        candidate_pools=candidate_pools, omission_ledger=omission_ledger,
        rewrite_guidance=rewrite_guidance, plan_input=plan_input, computed_support=computed_support,
    )
    # Open ongoing systems do not yet have a deterministic executable calendar.
    # The universal selection classification still lives in compressed_priorities;
    # the resolved-camp contract applies to all dated camps, including D-0.
    if brief.get("payload_variant") == "open_ongoing_stage2_payload":
        return brief
    if "late_fight_session_sequence" in brief:
        from .goal_preservation import _effective_map
        # Resolve the actual final sequence, not the earlier weekly mirror.
        role_map = _effective_map(brief)
        apply_effective_strength_prescriptions(
            weekly_role_map=role_map, candidate_pools=candidate_pools, athlete_model=athlete_model,
        )
    return reconcile_goal_preservation(brief)


def _build_planning_brief(
    *,
    athlete_model: dict,
    restrictions: list[dict],
    phase_briefs: dict[str, dict],
    candidate_pools: dict[str, dict],
    omission_ledger: dict[str, dict],
    rewrite_guidance: dict,
    plan_input: Any | None = None,
    computed_support: dict | None = None,
) -> dict:
    athlete_model = dict(athlete_model)
    # Persist the explicit resolved primary goal (from plan_input when present)
    # onto the athlete model before classification. Open/ongoing payloads return
    # before reconciliation, so compressed_priorities.goal_preservation is their
    # only goal-state authority; without this, classification would assume the
    # first key_goals entry is primary whenever athlete_model omits primary_goal.
    _resolved_primary = build_priority_profile(
        plan_input if plan_input is not None else athlete_model
    ).primary_goal
    if _resolved_primary:
        athlete_model["primary_goal"] = _resolved_primary
    # Compute short-camp compression up front so downstream consumers (role
    # map, weekly stress map, planning brief output) see a real
    # ``compressed_priorities`` dict. The helper is otherwise dead code, which
    # leaves the field empty whenever a caller skips ``build_stage2_payload``
    # and goes straight to ``build_planning_brief``.
    if not athlete_model.get("compressed_priorities"):
        athlete_model["compressed_priorities"] = _compress_short_camp_priorities(athlete_model)
    rewrite_guidance = _append_render_guard_writing_rules(rewrite_guidance, athlete_model=athlete_model, days_until_fight=athlete_model.get("days_until_fight"))
    days_until_fight = athlete_model.get("days_until_fight")
    priority_source = plan_input if plan_input is not None else athlete_model
    priority_profile = build_priority_profile(priority_source)
    collision_details = getattr(plan_input, "goal_weakness_collision_details", None) if plan_input is not None else None
    primary_collision_detail = ""
    if isinstance(collision_details, list) and collision_details:
        first = collision_details[0]
        if isinstance(first, dict):
            primary_collision_detail = str(first.get("detail", "") or "")
    priority_focus = describe_priority_focus(
        priority_profile,
        collision_detail=primary_collision_detail or (getattr(plan_input, "goal_weakness_collision_detail", "") if plan_input is not None else ""),
        collision_tags=getattr(plan_input, "goal_weakness_collision_tags", None) if plan_input is not None else None,
        collision_details=collision_details if isinstance(collision_details, list) else None,
    )

    if _uses_open_ongoing_payload(athlete_model):
        open_payload = build_open_ongoing_payload(athlete_model=athlete_model)
        return {
            "schema_version": "planning_brief.v1",
            "generator_mode": "deterministic_open_ongoing_planner_plus_ai_finalizer",
            "payload_variant": "open_ongoing_stage2_payload",
            "payload_mode": open_payload.get("payload_mode"),
            "render_mode": open_payload.get("render_mode"),
            "athlete_snapshot": athlete_model,
            "open_plan_spec": open_payload.get("open_plan_spec") or {},
            "priority_focus": priority_focus,
            "restrictions": restrictions,
            "candidate_pools": candidate_pools,
            "omission_ledger": omission_ledger,
            "decision_rules": rewrite_guidance,
            "computed_support": computed_support or {},
        }

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

    if _uses_late_fight_stage2_payload(days_until_fight):
        fight_week_override = _fight_week_override_payload(days_until_fight)
        days_out_payload = _days_out_payload_block(days_until_fight, athlete_model)
        late_fight_phase = _resolve_late_fight_phase(phase_briefs)
        late_fight_progression = _build_late_fight_week_by_week_progression(days_until_fight, athlete_model, phase_briefs)
        weekly_role_map = _build_late_fight_weekly_role_map(
            days_until_fight,
            athlete_model,
            fight_week_override,
            phase=late_fight_phase,
        )
        weekly_role_map = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)
        weekly_role_map = stamp_weekly_role_map_labels(weekly_role_map)
        base_late_fight_plan_spec = _build_late_fight_plan_spec(
            days_until_fight,
            athlete_model,
        )

        pre_gap_sequence = ensure_declared_coach_combat_spine(
            list(
                base_late_fight_plan_spec.get("session_sequence")
                or base_late_fight_plan_spec.get("visible_session_sequence")
                or _build_late_fight_session_sequence(days_until_fight, athlete_model)
            ),
            athlete_model,
            dict(base_late_fight_plan_spec.get("countdown_weekday_map", {})),
        )
        session_sequence = _visible_calendar_session_sequence(
            apply_gap_fill_inserts(pre_gap_sequence, athlete_model)
        )
        app_session_sequence = [
            role
            for role in session_sequence
            if _is_app_owned_visible_role(role.get("role_key"))
        ]

        late_fight_plan_spec = _with_late_fight_allowed_exercises(
            spec={
                **base_late_fight_plan_spec,
                # Carry the authoritative late-fight phase so goal-preservation's
                # _effective_map resolves the effective dose against the pool that
                # actually produced this sequence, not an arbitrary first pool.
                "phase": late_fight_phase,
                "role_budget": {
                    **dict(base_late_fight_plan_spec.get("role_budget", {})),
                    "selected_active_roles": sum(
                        1
                        for role in app_session_sequence
                        if not is_low_cost_coexistable_filler(role)
                    ),
                    "selected_meaningful_stress_exposures": sum(
                        1
                        for role in app_session_sequence
                        if role.get("stress_class") == "meaningful_stress"
                    ),
                    "selected_support_roles": sum(
                        1
                        for role in app_session_sequence
                        if role.get("stress_class") == "support"
                        and not is_low_cost_coexistable_filler(role)
                    ),
                },
                "visible_session_sequence": session_sequence,
                "visible_session_cap": len(app_session_sequence),
                "max_active_roles": len(app_session_sequence),
                "visible_session_roles": [
                    role.get("role_key")
                    for role in app_session_sequence
                    if isinstance(role, dict)
                ],
            },
            candidate_pools=candidate_pools,
            days_until_fight=days_until_fight,
        )

        return {
            "schema_version": "planning_brief.v1",
            "generator_mode": "deterministic_late_fight_planner_plus_ai_finalizer",
            "payload_variant": "late_fight_stage2_payload",
            "athlete_snapshot": athlete_model,
            "days_out_payload": days_out_payload,
            "late_fight_plan_spec": late_fight_plan_spec,
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
            "priority_focus": priority_focus,
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
            "computed_support": computed_support or {},
        }

    fight_week_override = _fight_week_override_payload(days_until_fight)
    weekly_role_map = stage2_role_map_module._build_weekly_role_map(
        athlete_model,
        week_by_week_progression,
        limiter_profile,
        fight_week_override=fight_week_override,
    )
    # The role map owns the crowded-week policy and every role-survival choice.
    # Payload only decorates its already-final decision with day-identity fields.
    _apply_boxing_crowded_week_post_processing(
        weekly_role_map,
        athlete_model=athlete_model,
    )
    # Deterministically place any session role the planner left dayless, then
    # stamp labels. Post-processing can append suppressed/omitted roles after the
    # inner builder ran, so do both here for full coverage.
    fill_missing_session_days(weekly_role_map)
    # Add low-cost support fillers to SPP/TAPER weeks (free days first, then at
    # most one shared day) using the same insert policy as the late-fight path.
    apply_camp_week_fillers(weekly_role_map, athlete_model)
    # Late-camp role morph: hard fight-pace/glycolytic conditioning scheduled at
    # D-13 or closer softens to a low-cost rhythm touch. Runs last so no quota
    # or protected-slot rule can preserve hard glycolytic work inside D-13; the
    # D-21→D-18 combat-pressure floor is untouched by construction.
    apply_late_camp_role_morph(weekly_role_map)
    # Deterministic prescription resolution: now that every strength role has its
    # scheduled D-day and final countdown dose envelope, resolve the single
    # authoritative effective prescription per candidate strength exercise so
    # Stage 2 never has to reconcile the exercise-bank dose against the role caps.
    # Runs AFTER the morph (which owns dose shaping) and BEFORE label stamping.
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
        athlete_model=athlete_model,
    )
    weekly_role_map = stamp_weekly_role_map_labels(weekly_role_map)
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
        "priority_focus": priority_focus,
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
        "computed_support": computed_support or {},
    }

def _with_selection_evidence(option: dict, item: dict, score_evidence: dict | None = None) -> dict:
    evidence = build_score_evidence(score_evidence=score_evidence)
    option.update(
        {
            "score": evidence["score"],
            "reason_codes": evidence["reason_codes"],
            "penalties": evidence["penalties"],
            "restriction_hits": evidence["restriction_hits"],
            "late_window_adjustment": evidence["late_window_adjustment"],
            "score_evidence": evidence,
            "selection_metadata": normalize_selection_metadata(item),
        }
    )
    return option


def _why_log_score_evidence(why_entry: dict) -> dict:
    reasons = why_entry.get("reasons", {}) if isinstance(why_entry, dict) else {}
    explanation = why_entry.get("explanation") if isinstance(why_entry, dict) else None
    return build_score_evidence(reasons=reasons, explanation=explanation)


def _serialize_strength_option(exercise: dict, why: str, score_evidence: dict | None = None, *, phase: str | None = None) -> dict:
    movement = str(exercise.get("movement", "")).strip().lower().replace(" ", "_")
    movement_patterns = [movement] if movement else []
    movement_patterns.extend(clean_list(exercise.get("tags", [])))
    quality_profile = classify_strength_item(exercise)
    required_equipment = clean_list(exercise.get("required_equipment") or exercise.get("equipment", []))
    prescription = exercise.get("prescription") or ""
    if not prescription and phase:
        # Carry the same actual bank-template dose that Stage 1 renders. A method
        # token such as "strength" or "power" is not an effective prescription.
        from .strength import _classify_prescription_type, _prescription_templates
        prescription = _prescription_templates(phase)[_classify_prescription_type(exercise)]
    return _with_selection_evidence({
        "name": exercise.get("name", "Unnamed"),
        "source": "exercise_bank",
        "movement_patterns": dedupe_preserve_order(movement_patterns),
        "restriction_tags": _extract_restriction_tags(exercise),
        "mechanical_risk_tags": _extract_mechanical_risk_tags(exercise),
        "prescription": prescription or exercise.get("method") or "",
        "real_strength_maintenance": exercise.get("real_strength_maintenance") is True,
        "why": why or "balanced selection",
        "quality_class": quality_profile["quality_class"],
        "anchor_capable": quality_profile["anchor_capable"],
        "support_only": quality_profile["support_only"],
        "base_categories": quality_profile["base_categories"],
        "required_equipment": required_equipment,
        "universally_available": not required_equipment or set(required_equipment).issubset({"bodyweight"}),
        "generic_fallback": bool(exercise.get("generic_fallback")),
    }, exercise, score_evidence)


def _serialize_conditioning_option(
    drill: dict,
    system: str,
    why: str,
    *,
    late_window: str | None = None,
    score_evidence: dict | None = None,
    stance: str | None = None,
) -> dict:
    tags = clean_list(drill.get("tags", []))
    required_equipment = clean_list(drill.get("required_equipment") or drill.get("equipment", []))
    option = {
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
        "athlete_facing_system_label": athlete_facing_system_label(drill, late_window=late_window),
    }
    if drill.get("modality") == "technical_footwork":
        prescription_fields = technical_footwork_prescription_fields(drill, stance=stance)
        option["prescription"] = " | ".join(
            part
            for part in [
                prescription_fields["timing"],
                prescription_fields["rest"],
                drill.get("load") or drill.get("intensity"),
            ]
            if part
        )
        option["technical_footwork_prescription"] = {
            key: drill[key]
            for key in (
                "cue_source",
                "cue",
                "cue_execution",
                "side_rule",
                "sets",
                "reps",
                "reps_per_side",
                "rest_sec",
                "quality_stop_rule",
            )
            if key in drill
        }
        # Resolved athlete-facing side/stance instruction, not just the raw
        # side_rule enum, so the finalizer never has to re-derive it from
        # athlete_snapshot.stance on its own.
        option["technical_footwork_prescription"]["side_instruction"] = prescription_fields[
            "side_instruction"
        ]
    return _with_selection_evidence(option, drill, score_evidence)


def _serialize_rehab_option(
    prescription: str,
    *,
    role: str,
    source: str,
    why: str,
    function_class: str = "",
    drill_id: str = "",
) -> dict:
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
        # The canonical rehab-bank id, carried so a completed drill can be
        # attributed to an injury without matching on the display name (which
        # Stage 2 rewrites). Empty when the option did not come from the bank.
        "rehab_drill_id": drill_id,
    }


def _build_strength_alternates(
    strength_block: dict,
    *,
    role: str,
    selected_names: set[str],
    current_name: str,
    phase: str | None = None,
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
                candidate.get("score_evidence")
                or build_score_evidence(
                    score=candidate.get("score"),
                    reasons=candidate.get("reasons") or {},
                    explanation=candidate.get("explanation"),
                ),
                # An alternate promoted via replace_with_same_role must carry the
                # same phase-specific bank-template dose authority as the selected
                # option, never a bare "strength"/"power" method token.
                phase=phase,
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
    late_window: str | None = None,
    stance: str | None = None,
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
                late_window=late_window,
                score_evidence=candidate.get("score_evidence")
                or build_score_evidence(
                    score=candidate.get("score"),
                    reasons=candidate.get("reasons") or {},
                    explanation=candidate.get("explanation"),
                ),
                stance=stance,
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
        # Mirror the reservoir role key: unclassified movements bucket under
        # "strength_support" there, so the slot must use the same key or the
        # alternate lookup silently returns nothing for jumps/bounds/hops whose
        # movement resolves to "unknown".
        role = movement if movement and movement != "unknown" else "strength_support"
        quality_profile = classify_strength_item(exercise)
        slots.append(
            {
                "slot_id": f"{phase.lower()}_strength_{idx}_{slugify(name)}",
                "role": role,
                "purpose": reasons.get("explanation", "balanced selection"),
                "selected": _serialize_strength_option(
                    exercise,
                    reasons.get("explanation", "balanced selection"),
                    _why_log_score_evidence(reasons),
                    phase=phase,
                ),
                "alternates": _build_strength_alternates(
                    strength_block,
                    role=role,
                    selected_names=selected_names,
                    current_name=name,
                    phase=phase,
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


def _build_conditioning_slots(
    phase_block: dict | None,
    phase: str,
    *,
    late_window: str | None = None,
    stance: str | None = None,
) -> list[dict]:
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
                        late_window=late_window,
                        score_evidence=_why_log_score_evidence(reasons),
                        stance=stance,
                    ),
                    "alternates": _build_conditioning_alternates(
                        phase_block,
                        system=system,
                        selected_names=selected_names,
                        current_name=name,
                        late_window=late_window,
                        stance=stance,
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
        # Surface/skin injuries are wound-care guidance, not prescriptive
        # loading slots. Promoting them to rehab slots makes the finalizer
        # render wound-care "stop rules" as plan content, which then collides
        # with any friction/contact restriction the athlete set on that same
        # wound and falsely holds the plan. Keep them advisory only.
        if _is_surface_type(injury_type):
            continue
        role = f"rehab_{slugify(location)}_{slugify(injury_type)}"
        selected_lines = [line for line in group.get("drills", []) if line]
        if phase.upper() == "TAPER":
            selected_lines = [line for line in selected_lines if "nordic" not in line.lower()]
            if not selected_lines:
                continue
        selected_set = set(selected_lines)
        rehab_option_records = rehab_drill_options_for_phase(
            injury_type.lower(),
            location.lower().replace(" ", "_"),
            phase,
            limit=6,
        )
        rehab_options = [record["line"] for record in rehab_option_records]
        # Canonical bank id per rendered line, so both the selected drill and
        # its alternates keep a stable identity through Stage 2.
        drill_ids_by_line = {
            record["line"]: str((record.get("drill") or {}).get("id") or "")
            for record in rehab_option_records
        }
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
                            drill_id=drill_ids_by_line.get(option, ""),
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
                        drill_id=drill_ids_by_line.get(line, ""),
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
    payload_mode: str = "",
) -> dict:
    late_window = classify_late_selector_window(training_context.days_until_fight)
    athlete_model = _build_athlete_model(
        training_context=training_context,
        sport=mapped_format,
        record=record,
        rounds_format=rounds_format,
        camp_length_weeks=camp_len,
        short_notice=short_notice,
    )
    has_active_injury = _has_active_injury_from_athlete_model(athlete_model)
    candidate_pools: dict[str, dict] = {}
    for phase in ("GPP", "SPP", "TAPER"):
        if phase_weeks.get(phase, 0) <= 0 and phase_weeks.get("days", {}).get(phase, 0) < 1:
            continue
        candidate_pools[phase] = {
            "strength_slots": _build_strength_slots(strength_blocks.get(phase), phase),
            "conditioning_slots": _build_conditioning_slots(
                conditioning_blocks.get(phase),
                phase,
                late_window=late_window,
                stance=athlete_model.get("stance"),
            ),
            "rehab_slots": _build_rehab_slots(rehab_blocks.get(phase, ""), phase) if has_active_injury else [],
        }

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
            "If declared hard sparring or support work days exist, use them to make the weekly rhythm more concrete instead of writing generic sparring caveats.",
            "Treat declared hard sparring days in weekly_role_map as immutable hard_sparring_day slots except when final_week_sparring_cap.active is true. In final taper weeks, final_week_sparring_cap overrides the coach-declared hard-day lock: render at most one effective hard sparring day, and do not present capped_declared_hard_sparring_days as sparring.",
"Hard sparring days are the athlete's own combat locks (run in their gym, with or without a coach). The app does not prescribe or lead the sparring itself, and it never deloads, caps, or drops a declared hard sparring day. At D-18 or further out render the label '" + CANONICAL_HARD_SPARRING_LABEL + "' (or the equivalent sport-specific label such as 'MMA — hard sparring / controlled hard contact') followed by exactly one short note: '" + CANONICAL_HARD_SPARRING_NOTE + "' From D-17 onward hard sparring is banned: render '" + CANONICAL_HARD_SPARRING_BAN_LABEL + "' (or sport-equivalent) — the same applies whenever the day carries reason code 'd17_hard_sparring_ban' — followed by exactly one short note: '" + CANONICAL_TECHNICAL_ONLY_NOTE + "' A technical-only day must never carry the hard-sparring note. Do not output round counts, time-x-rounds formulas, intensity targets, dose, RPE, work:rest, or any sparring template wording (e.g. never '6-8 x 3-min rounds at set intensity', 'X rounds technical sparring', 'live rounds at moderate intensity'). Do not narrate intent, do not add a 'why today' line, do not list focus areas, do not suggest pad/bag/clinch volume — the athlete owns that contact work. Never schedule programmed S&C on a declared hard-sparring/contact day. Anything more than the label plus that one note is a violation of this rule.",
            "Respect the weekly session count implied by weekly_role_map; do not turn extra available days into extra active training days.",
            "If the athlete has more available days than planned sessions, leave the spare days off or clearly optional rather than rendering another full session.",
            "If weekly_role_map or week_by_week_progression marks intentional_compression.active, keep that smaller week on purpose and do not restore the suppressed standalone role.",
            "If weekly_role_map.intentional_compression.policy is boxing_crowded_week, keep hard sparring as the week owner, then one anchor, then at most one low-load support day.",
            "In boxing crowded weeks, do not turn anchor days or recovery/support days into multi-stressor sessions by adding glycolytic, transfer, or extra sharpness work.",
            "In camps with 7 days or less to fight, only the compressed week-level priorities may drive standalone session purposes; keep all other selections as support, maintenance, or deferred notes only.",
            "When fight_week_override.active is true, treat it as mandatory. For 0-1 days, output readiness protocol notes only with no training week. For 2-3 days, output micro-taper only (one short primer max + one light recovery session). For 4-6 days, output mini taper only (freshness-first, minimal volume).",
            "If a target-weight constraint is present, explicitly acknowledge that it changes recovery and training tolerance in the athlete-facing plan.",
            "Never state 'weight cut none active' or 'recovery tolerance is standard' when readiness flags or weight_cut_pct indicate an active cut.",
            "If the cut is high-pressure, include one short summary-level note plus one support-level note; do not bury it only in the athlete profile or nutrition numbers.",
            "Use athlete_model.competitive_maturity only to calibrate wording specificity; it must not change workload, session count, recovery assumptions, or injury/cut conservatism.",
            "If fatigue is high or fight-week pressure is active, reduce optionality and make the directive plain.",
            "If injury management is active, lead with constraints, substitutions, or stop rules instead of optional language.",
            "If a target-weight constraint is present, keep the language shorter, safety-first, and non-negotiable about recovery margin.",
            "Vary sentence openings and cut repeated filler reminders so the final plan reads like a coach's final prescription, not a template.",
        ],
    }
    rewrite_guidance = _append_render_guard_writing_rules(
        rewrite_guidance,
        athlete_model=athlete_model,
        payload_mode=payload_mode,
        days_until_fight=training_context.days_until_fight,
    )
    triage_summary = athlete_model.get("triage_summary")
    triage_resume_approved = isinstance(triage_summary, dict) and bool(
        triage_summary.get("triage_resume_approved")
    )
    if triage_resume_approved:
        rewrite_guidance.setdefault("writing_rules", []).append(
            "If triage_resume_approved is true, do not write 'clinician clearance required', "
            "'until cleared', or equivalent re-clearance language. Keep only concrete current "
            "load constraints and symptom stop-rules."
        )

    days_until_fight = athlete_model.get("days_until_fight")

    if _uses_open_ongoing_payload(athlete_model):
        open_payload = build_open_ongoing_payload(athlete_model=athlete_model)
        return {
            "schema_version": "stage2_payload.v1",
            "generator_mode": "restriction_aware_candidate_generator_open_ongoing",
            "payload_variant": "open_ongoing_stage2_payload",
            "payload_mode": open_payload.get("payload_mode"),
            "effective_stage2_mode": open_payload.get("payload_mode"),
            "render_mode": open_payload.get("render_mode"),
            "open_plan_spec": open_payload.get("open_plan_spec") or {},
            "athlete_model": athlete_model,
            "injury_context": injury_context,
            "restrictions": serialized_restrictions,
            "phase_briefs": phase_briefs,
            "candidate_pools": candidate_pools,
            "omission_ledger": omission_ledger,
            "rewrite_guidance": rewrite_guidance,
        }

    if _uses_late_fight_stage2_payload(days_until_fight):
        days_out_payload = _days_out_payload_block(days_until_fight, athlete_model)

        base_late_fight_plan_spec = _build_late_fight_plan_spec(
            days_until_fight,
            athlete_model,
        )

        pre_gap_sequence = ensure_declared_coach_combat_spine(
            list(
                base_late_fight_plan_spec.get("session_sequence")
                or base_late_fight_plan_spec.get("visible_session_sequence")
                or []
            ),
            athlete_model,
            dict(base_late_fight_plan_spec.get("countdown_weekday_map", {})),
        )
        visible_session_sequence = _visible_calendar_session_sequence(
            apply_gap_fill_inserts(pre_gap_sequence, athlete_model)
        )
        app_visible_session_sequence = [
            role
            for role in visible_session_sequence
            if _is_app_owned_visible_role(role.get("role_key"))
        ]

        late_fight_plan_spec = _with_late_fight_allowed_exercises(
            spec={
                **base_late_fight_plan_spec,
                # Same authoritative late-fight phase on the stage2 payload spec so
                # every consumer resolves the effective dose against the correct
                # pool rather than an arbitrary candidate-pool key.
                "phase": _resolve_late_fight_phase(phase_briefs),
                "role_budget": {
                    **dict(base_late_fight_plan_spec.get("role_budget", {})),
                    "selected_active_roles": sum(
                        1
                        for role in app_visible_session_sequence
                        if not is_low_cost_coexistable_filler(role)
                    ),
                    "selected_meaningful_stress_exposures": sum(
                        1
                        for role in app_visible_session_sequence
                        if role.get("stress_class") == "meaningful_stress"
                    ),
                    "selected_support_roles": sum(
                        1
                        for role in app_visible_session_sequence
                        if role.get("stress_class") == "support"
                        and not is_low_cost_coexistable_filler(role)
                    ),
                },
                "visible_session_sequence": visible_session_sequence,
                "visible_session_cap": len(app_visible_session_sequence),
                "max_active_roles": len(app_visible_session_sequence),
                "visible_session_roles": [
                    role.get("role_key")
                    for role in app_visible_session_sequence
                    if isinstance(role, dict)
                ],
            },
            candidate_pools=candidate_pools,
            days_until_fight=days_until_fight,
        )

        return {
            "schema_version": "stage2_payload.v1",
            "generator_mode": "restriction_aware_candidate_generator_late_fight",
            "payload_variant": "late_fight_stage2_payload",
            "payload_mode": days_out_payload.get("payload_mode"),
            "effective_stage2_mode": days_out_payload.get("payload_mode"),
            "days_out_payload": days_out_payload,
            "late_fight_plan_spec": late_fight_plan_spec,
            "late_fight_session_sequence": visible_session_sequence,
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

Input = FINALIZER PACKET + Stage 1 draft + athlete profile + optional injury context.

AUTHORITY ORDER
1. FINALIZER PACKET — primary authority for calendar, render mode, countdown labels, restrictions, priorities, compact selected candidate facts, session-count metadata, and risks.
2. Render guards and restrictions — hard constraints. Non-negotiable.
3. Weekly role map / hard-sparring days — source of truth for visible session count, day ownership, declared days, and protected hard-sparring/contact slots.
4. Stage 1 selected exercises and draft text — candidate material only. Not final authority.

RULE 1 — HARD FILTER
Remove every exercise, drill, or prescription that violates any restriction, including synonyms and mechanical equivalents. Apply to strength, conditioning, rehab, warm-ups, and finishers. Do not modify a violating item into compliance — replace or drop it.

RULE 2 — PLAN THE CAMP, DON'T JUST EDIT
Build the best final plan from the FINALIZER PACKET. Use selected_plan, weekly_role_map, session_sequence, week_by_week_progression, and render_guards to sequence the camp. Reorganise and tighten — coherence over inertia.

RULE 3 — SELECTION ORDER
Preserve the calendar, declared days, coach-led ownership, session count, phase, and taper window from selected_plan / weekly_role_map, but make the final exercise and prescription choices yourself. Treat Stage 1 selected exercises as candidates, not truth; draft text is also candidate material. Keep a Stage 1 item only when it is the best compliant coaching choice for the athlete's sport, fight date, phase, injury, weight cut, fatigue, goals, weak areas, and schedule. If a Stage 1 item is weak, generic, violating, off-role, or poorly timed, override it using compact selected candidate facts, fallback items, selected_plan, or final coaching judgement. Do not create athlete-facing option menus. Never let Stage 1 draft wording decide final exercise rendering when the FINALIZER PACKET says a different role, day, count, restriction, or taper rule owns the session.

RULE 4 — ANCHOR STANDARD
Every anchor session must contain at least one serious high-transfer strength or power exercise if a compliant compact candidate or finalizer-safe substitution exists. Do not build anchors from bird dogs, dead bugs, planks, carries, or rehab-level work unless restrictions force it. Support work assists the anchor — it cannot become it.

RULE 5 — SAFE STRONG, NOT SAFE SOFT
In GPP and SPP, choose the safest strong option, not the safest soft option. If a compliant loaded pattern exists in compact candidate facts or selected_plan, prefer it over low-output filler for key slots.

RULE 6 — SPORT SPECIFICITY
The plan must read as a real combat-sport camp for this athlete. Conditioning, power work, weekly rhythm, and taper choices must match the athlete's sport, style, fight date, fatigue, injury context, weight cut, equipment, goals, weak areas, sparring/contact schedule, and phase.

RULE 6A — SESSION COACHING STANDARD
Every app-owned session must include exact drill/exercise, sets/reps/duration, rest, intensity or RPE, purpose, why today, and a progression/regression or stop rule. From D-10 to the fight, that line must offer regressions and stop rules only — never a progression/advance option (no "add load/sets", "heavier ball", "stronger band", or "to progress"). Strength & conditioning sessions (strength, power, alactic, aerobic, fight-pace, neural speed work) lock earlier: from D-13 they too offer regressions and stop rules only. Fillers, rehab, mobility, and light recovery work may still progress on D-13 to D-11; D-14 and earlier may progress everywhere. Do not render generic slot labels such as "Strength", "Aerobic support", or "Low-load mobility support" without actual coaching content.
If selected_plan.weekly_role_map.weeks[*].session_count_summary.reduced_from_planned is true, explain the smaller week once in the week lead using the provided reduction_reasons. Do not restore suppressed sessions to make the week look fuller.
If a wrist sprain or wrist restriction exists, repeat the exact restrictions and include wrist-safe isometric or rehab exposure where appropriate; do not prescribe loaded wrist extension, gripping volume, catching, front-rack, or punch-volume work that violates the restriction.
If a weight cut exists, reduce volume and noisy accessories, not specificity.
If power or speed goals exist, include low-volume explosive, speed, or neural work unless explicitly blocked.
If core, trunk, bracing, or anti-rotation is a weak area, include anti-rotation or bracing work.
If the fight is close, prefer neural primers, isometrics, trunk stiffness, rhythm, and freshness over generic strength volume.
Taper means reduce volume, not remove sharpness.

RULE 7 — SUPPORT WORK STAYS SUPPORT
Rehab, carries, trunk stability, and mobility support the plan — they do not lead it unless the packet clearly requires a protection-first camp. When cutting volume, cut accessory work first.

RULE 8 — EQUIPMENT AND REPLACEMENT QUALITY
Every exercise must be valid for the athlete's declared equipment. If the profile resolves an access question, render the resolved option only — no unresolved branches. Replace weak or violating Stage 1 items with stronger compliant options from compact candidate facts, selected_plan, or finalizer-safe substitutions, not softer invented options.

RULE 9 — TAPER DISCIPLINE
Cut novelty, reduce accessory volume, avoid density. Keep only sharpness, rhythm, confidence, and freshness. One final prescription per session — no option menus.
If selected_plan.fight_week_override.active or selected_plan.weekly_role_map.fight_week_override.active is true:
— 0–1 days: no training; coach note + readiness protocol only.
— 2–3 days: one short primer max + one light mobility/recovery session.
— 4–6 days: freshness-first, reduced volume, 1–2 sharpness sessions.
Never chase fitness in these windows.

RULE 9A — FIGHT-DAY (D-0) HARD OVERRIDE
If selected_plan.weekly_role_map.fight_day_override.active is true, or any week's fight_day_override.active is true, only D-0 is the athlete's fight day. Never treat D-7 (or any other shared weekday) as fight day. D-0 must render as the countdown heading plus one body line: "Follow coach warm-up and fight protocol; no additional S&C." No extra S&C, mobility, rehab, primer, sparring, or coach-led session on D-0. This override beats every declared hard sparring lock, every weekday role, and every phase rhythm. Even when the fight weekday is also a declared hard sparring day, it never renders as sparring on D-0. Do not restore any suppressed role on that day.

RULE 9B — TAPER MICRO-SUPPORT
If selected_plan.late_fight_plan_spec.taper_micro_support_policy.active is true, treat that policy as a hard overlay.
Render taper micro-support only as "Optional micro-support:" attached to an already-valid day. Never write the internal tag `taper_micro_support` in the final plan, including in brackets or parentheses. Never render it as a session title, primary anchor, visible session role, or standalone training day.
Obey the policy's allowed_categories, suppressed_categories, max_items, max_total_minutes, and per-category rules exactly.
If the policy suppresses core, neck, heavy bag, grip, shadowboxing, or band face pull, do not render them as taper micro-support.
On D-1, taper_micro_support is limited to breathing, mobility, or light technical shadowboxing only. No equipment of any kind is allowed on D-1: never render core, neck, heavy bag, grip, conditioning, band work (including light band face pulls), med ball, weights, or power work on D-1.
For core micro-support, keep only familiar low-fatigue stability work in tiny doses. Never use hanging leg raises, Russian twists, weighted sit-ups, long planks, high-rep abs, or any trunk/hip-flexor work likely to create soreness, pump, fatigue, or heavy breathing.
For neck micro-support, keep isometric-only, one set, 10 sec each direction, RPE 2-4, familiar only, and never D-4 or closer unless the policy explicitly allows it.
For heavy-bag micro-support, keep technical rhythm only, 1-2 x 45-60 sec, light contact only, and never let it become conditioning, power work, or shoulder-pump work.
For boxing tapers, do not render grip work at all.

RULE 10 — WEIGHT CUT AND INJURY MANAGEMENT
Active weight cut: state it plainly in one short summary note, never buried in nutrition data. Match the tone to the graded cut severity (athlete_snapshot.cut_severity_bucket: none / low / moderate / high / critical / extreme) — do NOT treat every cut as an emergency:
* none / low / moderate: this is a routine cut. Give ONE calm summary note about protecting recovery and fuelling (light precautions are fine at moderate). Do NOT add a weight-cut stop/report rule, do NOT tell the athlete to seek medical supervision, notify their coach, or frame it as a danger.
* high: add one measured support note (protect freshness, keep optional fatigue low). Supervision language is allowed but keep it proportionate.
* critical / extreme: safety-first supervision framing is appropriate — flag the elevated risk plainly.
Never escalate above the graded severity; when unsure, under-warn.
Unknown cut data: when athlete_snapshot.weight_cut_status is not "known", the athlete did not give both weights, so the cut size is UNKNOWN — not zero and not severe. Do not describe a cut, do not assign a severity, and do not claim there is no cut. Give one short neutral note naming what is missing ("no target weight set", "no current weight recorded", or "no weights recorded") and that cut guidance needs it. Never invent a target weight or a cut percentage.
Active injury: lead with constraints, substitutions, and stop rules — not optional language.
* If render_guards.suppress_rehab_headings == true, do not render sections/headings titled: Rehab, Prehab, Brief Rehab, Injury Rehab, Prepare / brief rehab, or Rehab / Mobility.
* If render_guards.suppress_rehab_headings == true, generic low-load work may only be labelled: Activation, Movement Prep, Mobility, Warm-up, or Reset — never as rehab/prehab.
* If render_guards.suppress_phase_toolbox_sections == true, do not render standalone: GPP toolbox/reference sections, SPP toolbox/reference sections, TAPER toolbox/reference sections, “key drills to keep in your toolbox”, “available options”, “SPP tools”, “GPP tools”, or “phase reference menus”.
* Candidate pools are internal selection data only and must not become athlete-facing menus.
Both flags narrow training tolerance and must shape the output structurally.
When injury wording is vague or underspecified, use INJURY CONTEXT to infer the safest high-probability interpretation. Never override hard restrictions or triage blocks, and prefer conservative substitutions and wording when detail is incomplete.

RULE 11 — OUTPUT DISCIPLINE
Write like an elite coach, not a document generator. Coach voice should feel decisive, respectful, and gym-realistic.
— Lead with action. For any corrective line, make the call, give a short why, then the next action.
Do not render planner/meta recap blocks in athlete-facing output. Never output headings or lines like: "Ownership:", "Hard-sparring summary:", "SPP additions summary", "Late-camp sparring", "Short support notes", "Final coaching call", "Schedule integrity", or "That’s the camp plan."
Do not output admin/compliance explanations about pool resolution, equipment swap policy, or internal planning rationale.
Do not open corrective lines with 'focus on', 'ensure', 'make sure', or 'it's important to'. Start with the action.
Never use an em dash or en dash (the long '—' or '–') anywhere in the output. Coaches write in full stops and commas; the long dash reads as machine-generated text and undermines the plan. Where you would reach for one, use a full stop if a new sentence starts, a comma if the clause continues, a colon if a label introduces detail, or a normal hyphen for a numeric range such as 3-5 reps or 45-60 sec. Do not use a spaced hyphen (' - ') as a substitute. Bullet lines start with '- ', never with a long dash.
Use autonomy-supportive phrasing only when a real safe choice exists; if so, offer at most two practical options, and only when both are safe and materially equivalent.
Do not rely on generic motivation such as 'stay consistent', 'trust the process', 'push yourself', or 'you've got this'.
Do not use empty safety boilerplate such as 'listen to your body', 'be careful', or 'avoid overtraining' unless the line adds a concrete rule, symptom trigger, or plan change.
Never use the word "app" (or "the app", "this app", "the platform", "app-owned", "app-provided", "app S&C") in athlete-facing text. The athlete is reading their own plan — name the work directly ("your S&C and rehab inserts", "your programmed sessions", "your hard sparring/contact session") and never attribute anything to an app. Do not assume the athlete has a coach: never say "coach-led", "coach owns this session", "train with your coach", or "coach-owned" in athlete-facing text — name hard sparring / contact work as the athlete's own.
Do not aim critique at the athlete's character.
Collapse templates into one final prescription whenever the athlete context already resolves the choice.
Do not repeat Primary, Fallback, Drill, or menu-style labels across most session lines.
Allow at most one explicit fallback in a session, and only when absolutely necessary.
Treat declared hard sparring days in selected_plan.weekly_role_map as immutable hard_sparring_day slots except when final_week_sparring_cap.active is true. In final taper weeks, final_week_sparring_cap overrides the coach-declared hard-day lock: render at most one effective hard sparring day, and do not present capped_declared_hard_sparring_days as sparring.
Hard sparring days are the athlete's own combat locks (run in their gym, with or without a coach). The app must not prescribe or lead the sparring itself, and it never deloads, caps, or drops a declared hard sparring day. At D-18 or further out render the label "Hard sparring — controlled hard contact" (or the equivalent sport-specific label such as "MMA — hard sparring / controlled hard contact") followed by exactly one short note: "Your declared hard-sparring/contact session — no extra S&C. Keep freshness priority." From D-17 onward hard sparring is banned: render "Technical-only combat" (or sport-equivalent) — the same applies whenever the day carries reason code "d17_hard_sparring_ban" — followed by exactly one short note: "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority." A technical-only day must never carry the hard-sparring note. Do not output round counts, time-x-rounds formulas, intensity targets, dose, RPE, work:rest, or any sparring template wording. Do not narrate intent, do not add a "why today" line, do not list focus areas, do not suggest pad/bag/clinch volume — the athlete owns that contact work. Never schedule programmed S&C on a declared hard-sparring/contact day. Anything more than the label plus that one note is a violation of this rule.
Do not exceed the weekly session count implied by selected_plan.weekly_role_map. If the athlete has extra available days, leave them off or clearly optional instead of turning them into extra active sessions.
Keep every active week present and structurally complete, including late-camp weeks.
If selected_plan.weekly_role_map or selected_plan.week_by_week_progression marks intentional_compression.active, keep that smaller week on purpose and do not restore the suppressed standalone role.
If selected_plan.weekly_role_map.intentional_compression.policy is boxing_crowded_week, keep hard sparring as the week owner, preserve one anchor if available, and allow at most one low-load support day.
In boxing crowded weeks, do not turn anchor days or recovery/support days into multi-stressor sessions by adding glycolytic, transfer, or extra sharpness work.
For boxer weeks, keep the default rhythm of support strength, low-damage conditioning, recovery, primary strength, then the main phase-specific conditioning stressor unless a stronger planning rule forces a change.
Use simple session titles and coach-readable drill labels, but do not spend this pass flattening non-standard names if the drill description is already mechanically clear.
If fatigue is high or fight-week pressure is active, reduce optionality and make the safest performance-preserving call plainly.
If injury management is active, lead with constraints, substitutions, or stop rules rather than optional language.
If a target-weight constraint is present, say so plainly in the final plan and explain that it tightens recovery and training tolerance.
Never write 'weight cut none active' or 'recovery tolerance is standard' when target-weight constraint flags are present.
If athlete_snapshot.weight_cut_status is not "known", there is no target-weight constraint to state — say the target weight is not set instead of asserting either a cut or an absence of one.
If a target-weight constraint is present, keep the wording shorter and safety-first rather than optimization-heavy.
If the cut is high-pressure, include one short summary-level note plus one support-level note; do not bury it only in the athlete profile or raw nutrition numbers.
In short camps, every rendered session must map to one compressed week-level priority from the finalizer packet. Do not create a standalone session purpose for embedded-support or deferred items.
Placement governs day assignment only; it does not change insert voice, ownership, or visible session count.

RULE 12 — SURGICAL REHAB INTEGRATION
Rehab must be intentional, not copy-pasted. Full authority to add, adjust, or remove any rehab item.
Use the function_class tags when present as scoring guidance — not hard constraints.
— Each session: 1–2 rehab functions, 5–10 minutes total.
— Spar days: 1 drill max — activation or brief post-session reset only.
— Strength/power days: prepare the specific risk point for the main lift.
— Aerobic/recovery days: tissue tolerance, control, mobility, low-load patterning.

Render every rehab item as:
  • [Drill name] — [Dose]
    Purpose: [exact mechanism — the specific limitation, not just the body part]
    Why today: [why this day type — pre-sparring activation / post-strength reset / aerobic tolerance / etc.]

If render_guards.suppress_rehab_headings == true, do not use this rehab format. Label generic low-load work as Activation, Movement Prep, Mobility, Warm-up, or Reset instead.

If a drill repeats across sessions, the Why today must make the changed role explicit. Use precise mechanism wording — not vague body-part labels. Before keeping any rehab item: confirm it solves a specific issue, belongs on this day, and does not duplicate a same-role drill already used this week. Drop it if it fails two of three.

RULE 13 — LATE-FIGHT LABEL DISCIPLINE
Applies when render_guards.suppress_phase_toolbox_sections == true.

Output is countdown-led. Lead every active day with countdown_display_label (D-N (Weekday)). Do not emit phase scaffolding: no "Week 1/2/3", no "PHASE N: GPP/SPP/TAPER", no "Phase Weeks", no "Phase Days", no "Phase must-keep", no "TAPER phase guidance", no "SPP insert", no "Mindset Focus" / "Strength & Power" / "Conditioning" sub-headers framed by phase.
Do not expose internal role keys or internal system labels as session titles. Translate role keys into coach-voiced names from the intent, drills selected, and countdown day. Canonical mapping:
  strength_touch_day         -> "Power Transfer Touch"
  alactic_sharpness_day      -> "Fight-Speed Primer"
  neural_primer_day          -> "Final Neural Cue"
  fight_week_freshness_day   -> "Freshness Reset"
  light_fight_pace_touch_day -> "Technical Rhythm Touch"
  technical_touch_day        -> "Technical Touch"
  hard_sparring_day          -> athlete-owned combat lock; never deloaded, capped, or dropped by the plan. At D-18 or further out render minimally as "Hard sparring — controlled hard contact" or sport-equivalent (e.g. "MMA — hard sparring / controlled hard contact"). From D-17 onward hard sparring is banned (also whenever the day carries reason code "d17_hard_sparring_ban"): render "Technical-only combat" or sport-equivalent. The athlete owns the day (with or without a coach); the app must not prescribe rounds, intensity, dose, work:rest, RPE, or any sparring template wording, and no programmed S&C is scheduled on that day. After a hard-sparring label emit exactly one note: "Your declared hard-sparring/contact session — no extra S&C. Keep freshness priority." After a technical-only combat label emit exactly one note: "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority." Nothing else.
Never write "Strength touch", "Alactic sharpness", "Neural primer", "SPP", "Glycolytic", "Alactic", or "Aerobic" as an athlete-facing session title.

For conditioning drill system labels, use selected_plan session fields such as athlete_facing_system_label when present. If absent, translate the drill intent into athlete-facing language. Never use the word "Glycolytic" in D-7 or tighter windows. When a drill carries short-work + full-rest prescription, call it "footwork speed repeatability", "coordination conditioning", "reactive footwork", or "technical rhythm" per its tags.

Cut fluff: one sentence of "why today" per session maximum, no repeated explanations, no "phase preserved" menus. Coach calls only.
"""


UNLXCK_FINAL_RENDER_CONTRACT = """UNLXCK FINAL RENDER CONTRACT

Non-negotiable output contract:
0. Lead notes come first when active injury, weight cut, freshness, or volume/compression logic exists. Use short coach-facing notes before the first week.
1. Late-fight plans must use D-X countdown headers.
2. Late-fight active-day headers must be: D-X (Weekday) — clear athlete-facing session role.
3. Do not use raw system titles as athlete-facing session titles. Avoid as session titles only: Strength touch, Alactic sharpness, Neural primer, Glycolytic, Alactic, Aerobic. Phase headers may still use GPP, SPP, and TAPER for longer camps.
4. Longer camps must use phase/week headers in this style:
   GPP — Week 1 (D-X to D-X) — Objective
   SPP — Week 2 (D-X to D-X) — Objective
   TAPER — Week 3 (D-X to D-X) — Objective
5. Every app-owned training day must clearly show:
   - why the session exists today
   - exact drill/exercise, sets/reps/duration, rest, and intensity/RPE
   - for D-7 and tighter, never raise a selected drill's RPE or volume; if a selected drill has RPE/rounds/work_sec fields, use those caps
   - the purpose behind the work
   - progression/regression or stop rule; from D-10 to the fight, offer regressions and stop rules only — never a progression/advance option (no "add load/sets", "heavier ball", "stronger band", or "to progress"). From D-13, strength & conditioning sessions (strength, power, alactic, aerobic, fight-pace, neural speed work) also lock to regressions/stop rules only; fillers, rehab, mobility, and light recovery work may still progress on D-13 to D-11. D-14 and earlier may progress everywhere.
   - render meaningful adjustment lines only: "Easier: <action>" and
     "Stop: <trigger/action>" on separate lines. Never emit a bare
     "Regression /", "Regression", or slash-separated structural label.
   - injury/rehab insert when relevant
   - coach call when needed
6. If session_count_summary.reduced_from_planned is true for a week, include one short reason tied to taper, weight cut, D-17 technical-only rule, injury/cut management, hard sparring / contact load, fight-week override, or intentional compression.
7. Hard sparring / technical-only combat days must stay minimal: the hard-sparring/contact label plus one freshness note only — no programmed S&C stacked on the day.
8. D-0 must be fight day protocol only.
9. Active injury or active cut context must appear as a short lead summary before the training detail.
10. Do not expose scaffold labels such as "Anchor —", "role_key", "taper_micro_support", "candidate pool", "validator", or "planning brief".
11. Return only the athlete-facing final plan.

Mini example (do not copy the volume/intensity when rendering D-7 or tighter; selected drill caps override it):
D-5 (Tuesday) — Fight-speed primer
Why: sharpen punch speed without adding fatigue.
- Movement prep: 5 min shoulder swings, band pull-aparts, easy shadowboxing.
- Explosive Boxing Burst Intervals — 2-3 x 5-6 sec fast relaxed bursts; RPE 6; full recovery 90-120 sec.
- Coach call: Stop when speed drops. This sharpens output without soreness.

Preferred longer-camp week header:
SPP — Week 4 (D-28 to D-22) — Raise fight-pace repeatability without compromising sparring freshness."""




_OPEN_ONGOING_RENDER_MODE_INSTRUCTIONS = """OPEN ONGOING RENDER MODE

You are rendering an athlete-facing open ongoing training system.

This athlete has no scheduled fight date. Therefore, do not write a fight camp, countdown, taper, or D-day plan.

Render the plan in this exact order:

1. Immediate Coach Summary
2. Current Training Rules
3. Weekly Rhythm
4. Session Cards
5. 4-Week Development Block
6. Progression Rules
7. Priority Hierarchy
8. Adjustment Rules
9. Rehab / Red Flags
10. 4-Week Reassessment Gate

Rules:
- Use concise coach-facing language.
- Keep the structure easy to scan.
- Use one consistent session-card format.
- Keep hard sparring / contact sessions separate from the programmed S&C.
- Use a renewable 4-week block: Week 1 baseline, Week 2 small progression, Week 3 highest controlled week, Week 4 deload/reassess.
- Do not mention GPP, SPP, TAPER, D-day, countdown, fight week, fight-day protocol, or final-week sparring cap.
- Do not invent exercises outside the selected/session-approved data.
- Do not expose internal candidate pools, scoring logic, tags, or unused options.
- If restrictions/red flags exist, render them once in the safety section and reference them briefly in session cards only when needed.
- If symptoms, fatigue, or weight-cut pressure rise, remove optional conditioning before trimming key anchors.
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


def _continuation_days_until_fight(
    finalizer_packet: dict,
    planning_brief: dict | None,
) -> Any:
    """Best-effort ``days_until_fight`` for the countdown-continuation fallback."""
    for source in (finalizer_packet, planning_brief):
        if not isinstance(source, dict):
            continue
        for model_key in ("athlete_model", "athlete_snapshot"):
            model = source.get(model_key)
            if isinstance(model, dict) and model.get("days_until_fight") is not None:
                return model.get("days_until_fight")
        fight_demands = source.get("fight_demands")
        if isinstance(fight_demands, dict) and fight_demands.get("days_until_fight") is not None:
            return fight_demands.get("days_until_fight")
    return None


def _countdown_continuation_map_from_packet(
    finalizer_packet: dict,
    planning_brief: dict | None,
) -> list[dict]:
    selected_plan = finalizer_packet.get("selected_plan", {})
    if isinstance(selected_plan, dict):
        late_fight_plan_spec = selected_plan.get("late_fight_plan_spec", {}) or {}
        if isinstance(late_fight_plan_spec, dict):
            continuation_map = list(late_fight_plan_spec.get("countdown_mode_sequence", []) or [])
            if continuation_map:
                return continuation_map

        days_out_payload = selected_plan.get("days_out_payload", {}) or {}
        if isinstance(days_out_payload, dict):
            continuation_map = list(days_out_payload.get("countdown_mode_sequence", []) or [])
            if continuation_map:
                return continuation_map

    if isinstance(planning_brief, dict):
        continuation_map = list(
            (
                planning_brief.get("late_fight_plan_spec", {}) or {}
            ).get("countdown_mode_sequence", [])
        )
        if continuation_map:
            return continuation_map
        continuation_map = list(
            (planning_brief.get("days_out_payload", {}) or {}).get("countdown_mode_sequence", [])
        )
        if continuation_map:
            return continuation_map

    # Fallback for normal-camp (D-14+) plans. Their planning brief carries no
    # late_fight_plan_spec / days_out_payload (D-14+ stays on the normal camp
    # planner), but the plan's continuous calendar still reaches the D-13 -> D-0
    # fight-week tail. Derive the downstream continuation from days_until_fight so
    # those scheduled days inherit the existing late-fight mode contracts instead
    # of silently rendering as normal-camp work into fight week. Empty for late
    # plans (already handled above) and for undated / open plans.
    return _camp_downstream_countdown_continuation(
        _continuation_days_until_fight(finalizer_packet, planning_brief)
    )


def _append_countdown_continuation_instructions(
    *,
    mode_instructions: str,
    payload_mode: str,
    continuation_map: list[dict],
) -> str:
    if not continuation_map:
        return mode_instructions

    if len(continuation_map) <= 1:
        return mode_instructions

    # A late-fight/fight-week top mode carries non-empty mode instructions; a
    # normal-camp plan (camp_payload / camp_plan bucket) carries none. Use that to
    # pick the intro: the late-fight continuation-start plan continues its own
    # active countdown, whereas a camp plan only hands its D-13 -> D-0 tail to the
    # fight-week contracts and must NOT reframe its earlier camp days.
    is_camp_top_mode = not str(mode_instructions or "").strip()
    if is_camp_top_mode:
        intro = (
            "This plan stays on the normal camp planner from its generation day through "
            "D-14. From D-13 onward its scheduled countdown days follow the existing "
            "fight-week contracts mapped below — apply each mapped payload mode to its own "
            "D-day window, in descending order through D-0. Do not convert the earlier camp "
            "days into a late-fight countdown."
        )
    else:
        intro = (
            "Continue the active late-fight countdown from this start window through D-0 "
            "exactly as mapped below."
        )

    continuation_lines = ["COUNTDOWN CONTINUATION MAP", intro]

    for segment in continuation_map:
        stage_key = str(segment.get("stage_key") or "").strip()
        segment_mode = str(segment.get("payload_mode") or "").strip()
        start_day = segment.get("start_day")
        end_day = segment.get("end_day")
        if stage_key and segment_mode and isinstance(start_day, int) and isinstance(end_day, int):
            continuation_lines.append(
                f"- {stage_key}: {segment_mode} (D-{start_day} to D-{end_day})"
            )

    if len(continuation_lines) <= 2:
        return mode_instructions

    continuation_block = "\n".join(continuation_lines)
    if mode_instructions:
        return mode_instructions + "\n\n" + continuation_block
    return continuation_block


def build_stage2_handoff_text(
    *,
    stage2_payload: dict,
    plan_text: str,
    coach_notes: str = "",
    planning_brief: dict | None = None,
) -> str:
    planning_brief = build_stage2_llm_planning_brief(planning_brief)
    finalizer_packet = build_stage2_finalizer_packet(
        stage2_payload=stage2_payload,
        planning_brief=planning_brief,
    )

    athlete_profile = _athlete_profile_block(planning_brief, stage2_payload)
    render_mode = str(finalizer_packet.get("render_mode") or "").strip()
    # ``render_mode`` is the abstract bucket ("camp_plan",
    # "late_fight_countdown_only", "open_ongoing_system") used for dispatching
    # rendering rules. ``_handoff_mode_instructions`` keys on the specific
    # payload mode (e.g. ``pre_fight_compressed_payload``), so we must look
    # that up directly — using ``render_mode`` here drops mode instructions
    # entirely for every late-fight day.
    payload_mode = (
        stage2_payload.get("payload_mode")
        or stage2_payload.get("effective_stage2_mode")
        or render_mode
        or "camp_payload"
    )

    # ── Payload-mode-sensitive hard instructions ──────────────────
    mode_instructions = _handoff_mode_instructions(payload_mode)

    continuation_map = _countdown_continuation_map_from_packet(
        finalizer_packet=finalizer_packet,
        planning_brief=planning_brief,
    )
    mode_instructions = _append_countdown_continuation_instructions(
        mode_instructions=mode_instructions,
        payload_mode=payload_mode,
        continuation_map=continuation_map,
    )
    # Priority-hierarchy guidance is NOT restated here: the finalizer packet's
    # hard_rules already carry the full priority_focus doctrine (preserve
    # hierarchy, honour collisions via priority_focus.collision_detail /
    # collision_details, treat derived_clarification_tags as internal-only), and
    # the packet's selected_plan.priority_focus block supplies the underlying
    # values. A parallel prose section here only duplicated those rules.
    sections = [
        STAGE2_FINALIZER_PROMPT.strip(),
        UNLXCK_FINAL_RENDER_CONTRACT.strip(),
    ]

    if mode_instructions:
        sections.append("PAYLOAD MODE INSTRUCTIONS\n" + mode_instructions)
    if render_mode == "open_ongoing_system":
        sections.append(_OPEN_ONGOING_RENDER_MODE_INSTRUCTIONS.strip())

    sections.append("FINALIZER PACKET\n" + _json_block(finalizer_packet))
    sections.append("ATHLETE PROFILE\n" + _json_block(athlete_profile))

    injury_context = stage2_payload.get("injury_context")
    if isinstance(injury_context, dict):
        sections.append("INJURY CONTEXT\n" + _json_block(injury_context))

    cleaned_notes = (coach_notes or "").strip()
    if cleaned_notes:
        sections.append("COACH NOTES\n" + cleaned_notes)

    sections.append("STAGE 1 DRAFT PLAN\n" + (plan_text or "").strip())

    return "\n\n---\n\n".join(section for section in sections if section.strip())
