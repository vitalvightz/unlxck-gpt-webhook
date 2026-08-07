"""Compact Stage 2 finalizer packet.

This module converts the full internal Stage 2 payload into a small LLM-facing
packet. The full payload remains useful for debugging and tests, but the LLM
should not receive internal candidate pools, phase toolbox menus, or unused
rehab options.

Purpose:
- reduce LLM prompt bloat
- prevent GPP/SPP/TAPER toolbox leakage
- prevent rehab/prehab leakage when no active injury exists
- keep finalizer focused on selected sessions and render rules
"""

from __future__ import annotations

from typing import Any

from .fight_day_override import FIGHT_DAY_PROTOCOL_TEXT
from .stage2_render_guards import _all_active_injuries_surface_only, _render_guard_flags


_ATHLETE_KEYS = (
    "sport",
    "status",
    "record",
    "rounds_format",
    "camp_length_weeks",
    "days_until_fight",
    "fight_date",
    "next_fight_date",
    "fatigue",
    "age",
    "weight_cut_risk",
    "weight_cut_pct",
    "weight_cut_status",
    "cut_severity_score",
    "cut_severity_bucket",
    "technical_styles",
    "tactical_styles",
    "weaknesses",
    "key_goals",
    "equipment",
    "training_frequency",
    "training_days",
    "hard_sparring_days",
    "support_work_days",
    "technical_skill_days",
    "short_notice",
    "plan_creation_weekday",
    "readiness_flags",
    "has_active_injury",
    "injuries_raw_text",
    "parsed_injuries",
    "guided_injury",
    "injury_restrictions",
)


_FORBIDDEN_TOOLBOX_LABELS = [
    "GPP toolbox",
    "SPP toolbox",
    "TAPER toolbox",
    "key drills to keep in your toolbox",
    "available options",
    "phase reference menu",
    "SPP tools",
    "GPP tools",
    "TAPER tools",
]


_FORBIDDEN_REHAB_LABELS = [
    "Rehab",
    "Injury Rehab",
    "Brief Rehab",
    "Prepare / brief rehab",
    "Prehab",
    "Rehab / Mobility",
]


def _compact_dict(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: source.get(key) for key in keys if key in source}


def _compact_athlete_model(athlete_model: dict[str, Any]) -> dict[str, Any]:
    return _compact_dict(athlete_model or {}, _ATHLETE_KEYS)


def _compact_restrictions(restrictions: Any) -> list[dict[str, Any]]:
    if not isinstance(restrictions, list):
        return []
    compact: list[dict[str, Any]] = []
    for entry in restrictions:
        if not isinstance(entry, dict):
            continue
        compact.append(
            {
                key: entry.get(key)
                for key in (
                    "restriction",
                    "region",
                    "side",
                    "strength",
                    "source_phrase",
                    "blocked_patterns",
                    "mechanical_equivalents",
                )
                if entry.get(key) not in (None, "", [])
            }
        )
    return compact


def _compact_role(role: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "session_index",
        "category",
        "role_key",
        "scheduled_day_hint",
        "preferred_pool",
        "preferred_system",
        "preferred_tags",
        "preferred_exercise_names",
        "anchor",
        # NOTE: selection_rule / placement_rule / day_assignment_reason are
        # deliberately NOT surfaced to the finalizer. They are internal Stage 1
        # selection/placement rationale (which slot was chosen and why), not
        # athlete-facing content, and no render instruction references them. The
        # finalizer treats Stage 1 as candidates and owns its own placement, with
        # the authoritative day signal coming from scheduled_day_hint +
        # calendar_days; these strings were highly repetitive (a handful of unique
        # values stamped across every role) and only bloated the prompt.
        "coach_owned",
        "display_text",
        "athlete_facing_label",
        "countdown_label",
        "scheduled_countdown_label",
        "countdown_display_label",
        "countdown_weekday",
        "real_weekday",
        "countdown_offset",
        "placement_basis",

        # Sparring dose truth from the planner / role map
        "hard_sparring_status",
        "hard_sparring_class",
        "hard_sparring_reason_codes",
        "hard_sparring_reason",
        "coach_note_flags",
        "coach_note",
        "replacement_role_key",
        "downgraded_from_role_key",
        "locked_day",

        # Gas-tank / recovery-day upgrade flags
        "gas_tank_recovery_touch",
        "allowed_on_recovery_day",
        "recovery_compatible",
        "converted_from_unused_day",
        "original_role_key",
        "original_unused_day_role",

        # Dedicated recovery/mobility support markers
        "is_dedicated_recovery_mobility_day",
        "priority_recovery_touch",
        "support_kind",
        "counts_toward_conditioning_cap",
        "counts_toward_exercise_cap",
        "counts_toward_strength_cap",

        # Safety filters for low-aerobic recovery work
        "blocked_systems",
        "blocked_intensities",
        "blocked_tags",
    )
    return {key: role.get(key) for key in keep if role.get(key) not in (None, "", [])}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def _int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _planned_weekly_count(week: dict[str, Any], athlete_model: dict[str, Any]) -> int:
    for key in ("weekly_training_frequency", "training_frequency", "weekly_sessions"):
        if key in athlete_model:
            count = _int_value(athlete_model.get(key), -1)
            if count >= 0:
                return count
    declared_training_days = _as_list(week.get("declared_training_days"))
    if declared_training_days:
        return len(declared_training_days)
    counts = week.get("session_counts")
    if isinstance(counts, dict):
        return sum(_int_value(counts.get(key), 0) for key in ("strength", "conditioning", "recovery", "technical"))
    return 0


def _is_coach_owned_role(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()
    return bool(role.get("coach_owned")) or category == "sparring" or role_key == "hard_sparring_day"


def _collect_reason_codes(week: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for collection_key in ("session_roles", "suppressed_roles", "hard_sparring_plan"):
        for entry in _as_list(week.get(collection_key)):
            if not isinstance(entry, dict):
                continue
            for code_key in ("reason_codes", "hard_sparring_reason_codes", "compression_reason_codes"):
                codes.update(str(code).strip() for code in _as_list(entry.get(code_key)) if str(code).strip())
    compression = week.get("intentional_compression")
    if isinstance(compression, dict):
        codes.update(str(code).strip() for code in _as_list(compression.get("reason_codes")) if str(code).strip())
        reason = str(compression.get("reason") or "").strip()
        if reason:
            codes.add(reason)
    fight_day_override = week.get("fight_day_override")
    if isinstance(fight_day_override, dict) and fight_day_override.get("active"):
        codes.add("fight_day_override")
    return codes


def _has_active_weight_cut(athlete_model: dict[str, Any]) -> bool:
    if athlete_model.get("weight_cut_risk"):
        return True
    if str(athlete_model.get("cut_severity_bucket") or "").strip().lower() not in {"", "none", "low"}:
        return True
    try:
        return float(athlete_model.get("weight_cut_pct") or 0) > 0
    except (TypeError, ValueError):
        return False


def _has_active_injury(athlete_model: dict[str, Any]) -> bool:
    return bool(
        athlete_model.get("has_active_injury")
        or _as_list(athlete_model.get("parsed_injuries"))
        or _as_list(athlete_model.get("injury_restrictions"))
        or str(athlete_model.get("injuries_raw_text") or "").strip()
    )


def _session_count_summary(week: dict[str, Any], athlete_model: dict[str, Any]) -> dict[str, Any]:
    roles = [role for role in _as_list(week.get("session_roles")) if isinstance(role, dict)]
    coach_owned_count = sum(1 for role in roles if _is_coach_owned_role(role))
    app_owned_count = max(0, len(roles) - coach_owned_count)
    planned_count = _planned_weekly_count(week, athlete_model)
    rendered_total = len(roles)
    reduced = planned_count > 0 and rendered_total < planned_count
    reason_codes = _collect_reason_codes(week)
    compression = week.get("intentional_compression")

    reasons: list[str] = []
    if str(week.get("phase") or "").strip().upper() == "TAPER":
        reasons.append("taper")
    if (_has_active_weight_cut(athlete_model) and str(athlete_model.get("cut_severity_bucket") or "").strip().lower() not in {"", "none", "low", "moderate"}) or reason_codes & {"active_weight_cut", "high_pressure_weight_cut", "weight_cut_high_suppress_hard_work", "weight_cut_unsafe_block"}:
        reasons.append("weight_cut")
    if "d17_hard_sparring_ban" in reason_codes:
        reasons.append("d17_technical_only_rule")
    if (
        _has_active_injury(athlete_model) or "injury_management" in reason_codes
    ) and not _all_active_injuries_surface_only(athlete_model):
        reasons.append("injury_management")
    if coach_owned_count or week.get("hard_sparring_plan") or week.get("effective_hard_sparring_days"):
        reasons.append("coach_led_contact_load")
    if "fight_week_override" in reason_codes:
        reasons.append("fight_week_override")
    if isinstance(compression, dict) and compression.get("active"):
        reasons.append("intentional_compression")

    reason_labels = {
        "taper": "Taper trims volume while preserving sharpness.",
        "weight_cut": "Target-weight pressure tightens recovery tolerance.",
        "d17_technical_only_rule": "D-17+ hard-contact rule moves contact work to technical-only.",
        "injury_management": "Injury management removes or compresses risky standalone work.",
        "coach_led_contact_load": "Hard sparring / contact work owns part of the weekly load.",
        "fight_week_override": "Fight-week override caps app-owned work.",
        "intentional_compression": "Planner marked this as intentional compression.",
    }

    summary = {
        "planned_weekly_count": planned_count,
        "rendered_total_count": rendered_total,
        "rendered_app_owned_count": app_owned_count,
        "coach_owned_count": coach_owned_count,
        "reduced_from_planned": reduced,
        "reduction_reasons": [reason_labels[reason] for reason in dict.fromkeys(reasons)] if reduced else [],
        "reason_codes": sorted(reason_codes),
    }
    return {key: value for key, value in summary.items() if value not in (None, "", [])}


def _compact_weekly_role_map(weekly_role_map: Any, athlete_model: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(weekly_role_map, dict):
        return {}

    athlete_model = athlete_model or {}
    compact_weeks: list[dict[str, Any]] = []
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue

        compact_weeks.append(
            {
                key: value
                for key, value in {
                    "week_index": week.get("week_index"),
                    "phase": week.get("phase"),
                    "label": week.get("label"),
                    "session_roles": [
                        _compact_role(role)
                        for role in (week.get("session_roles") or [])
                        if isinstance(role, dict)
                    ],
                    "suppressed_roles": [
                        _compact_role(role)
                        for role in (week.get("suppressed_roles") or [])
                        if isinstance(role, dict)
                    ],
                    "fight_day_override": week.get("fight_day_override"),
                    "projected_days_until_fight_start": week.get("projected_days_until_fight_start"),
                    "projected_days_until_fight_end": week.get("projected_days_until_fight_end"),
                    "countdown_range": week.get("countdown_range"),
                    "calendar_days": week.get("calendar_days"),
                    "intentionally_unused_days": week.get("intentionally_unused_days"),
                    "declared_training_days": week.get("declared_training_days"),
                    "declared_hard_sparring_days": week.get("declared_hard_sparring_days"),
                    "declared_support_work_days": week.get("declared_support_work_days"),
                    "hard_sparring_plan": [
                        dict(entry)
                        for entry in week.get("hard_sparring_plan")
                        if isinstance(entry, dict)
                    ] if isinstance(week.get("hard_sparring_plan"), list) else None,
                    "effective_hard_sparring_days": week.get("effective_hard_sparring_days"),
                    "final_week_sparring_cap": week.get("final_week_sparring_cap"),
                    "coach_note_flags": week.get("coach_note_flags"),
                    "intentional_compression": week.get("intentional_compression"),
                    "session_count_summary": _session_count_summary(week, athlete_model),
                }.items()
                if value not in (None, "", [])
            }
        )

    return {
        key: value
        for key, value in {
            "weeks": compact_weeks,
            "fight_day_override": weekly_role_map.get("fight_day_override"),
        }.items()
        if value not in (None, "", [])
    }


# Internal late-fight scaffolding the finalizer never needs. The LLM already
# gets the countdown session list via selected_plan.session_sequence
# (visible_session_sequence is a byte-identical copy of it), and allocator /
# role_budget / permission_policy are Stage 1 allocation internals that no render
# instruction references. The one referenced cap (max_active_roles) lives at the
# spec top level and is preserved; only these internal-only keys are stripped.
_LATE_FIGHT_SPEC_INTERNAL_KEYS = (
    "visible_session_sequence",
    "allocator",
    "role_budget",
    "permission_policy",
)


def _compact_late_fight_plan_spec(late_fight_plan_spec: Any) -> Any:
    """Return the LLM-facing late-fight spec without internal allocation scaffolding.

    Non-mutating: builds a new dict so the source spec (still read by the Stage 1
    pipeline and the Stage 2 validator) is untouched. ``countdown_mode_sequence``
    is preserved because the handoff's countdown-continuation map reads it.
    """

    if not isinstance(late_fight_plan_spec, dict):
        return late_fight_plan_spec
    return {
        key: value
        for key, value in late_fight_plan_spec.items()
        if key not in _LATE_FIGHT_SPEC_INTERNAL_KEYS
    }


def _compact_session_sequence(stage2_payload: dict[str, Any]) -> list[dict[str, Any]]:
    plan_spec = stage2_payload.get("late_fight_plan_spec") or {}
    if isinstance(plan_spec, dict):
        value = plan_spec.get("visible_session_sequence")
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]

    for key in (
        "late_fight_session_sequence",
        "session_sequence",
        "countdown_sessions",
    ):
        value = stage2_payload.get(key)
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]

    if isinstance(plan_spec, dict):
        value = plan_spec.get("session_sequence") or plan_spec.get("sessions")
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]

    return []


def _render_guards(stage2_payload: dict[str, Any]) -> dict[str, Any]:
    athlete_model = stage2_payload.get("athlete_model") or {}
    rewrite_guidance = stage2_payload.get("rewrite_guidance") or {}
    guards = rewrite_guidance.get("render_guards")

    if isinstance(guards, dict) and guards:
        return guards

    return _render_guard_flags(
        athlete_model=athlete_model,
        payload_mode=str(stage2_payload.get("payload_mode") or ""),
        days_until_fight=athlete_model.get("days_until_fight"),
    )


def build_stage2_finalizer_packet(
    *,
    stage2_payload: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the compact LLM-facing Stage 2 packet.

    This function must not mutate the original Stage 2 payload.
    It intentionally excludes full candidate pools and internal scoring data.

    planning_brief is optional but preferred when available because it can carry
    richer late-fight/session sequencing data than the raw Stage 2 payload.
    """

    source = planning_brief if isinstance(planning_brief, dict) else stage2_payload

    athlete_model = (
        source.get("athlete_snapshot")
        or source.get("athlete_model")
        or stage2_payload.get("athlete_model")
        or {}
    )
    rewrite_guidance = (
        source.get("decision_rules")
        or source.get("rewrite_guidance")
        or stage2_payload.get("rewrite_guidance")
        or {}
    )

    guards = _render_guards(
        {
            **stage2_payload,
            "athlete_model": athlete_model,
            "rewrite_guidance": rewrite_guidance,
            "payload_mode": (
                source.get("payload_mode")
                or source.get("effective_stage2_mode")
                or stage2_payload.get("payload_mode")
                or stage2_payload.get("effective_stage2_mode")
                or ""
            ),
        }
    )
    render_mode = guards.get("render_mode") or "camp_plan"

    weekly_role_map = source.get("weekly_role_map") or stage2_payload.get("weekly_role_map")
    late_fight_plan_spec = _compact_late_fight_plan_spec(
        source.get("late_fight_plan_spec")
        or stage2_payload.get("late_fight_plan_spec")
        or {}
    )
    open_plan_spec = (
        source.get("open_plan_spec")
        or stage2_payload.get("open_plan_spec")
        or {}
    )

    packet = {
        "packet_type": "stage2_finalizer_packet",
        "packet_version": 1,
        "render_mode": render_mode,
        "athlete_model": _compact_athlete_model(athlete_model),
        "render_guards": guards,
        "hard_rules": [
            "Render only athlete-facing plan content.",
            "Do not expose candidate pools, scoring logic, internal menus, or unused options.",
            "weekly_role_map.weeks[*].calendar_days is the only authority for weekday and D-day labels.",
            "Do not infer D-days from weekday order.",
            "Do not invent D-days from the fight date manually.",
            "Only render session_roles whose scheduled_day_hint exists in that week's calendar_days.",
            "Use session_count_summary to explain reduced weeks; do not restore suppressed roles to match the athlete's planned weekly frequency.",
            "Stage 1 draft exercise text is candidate material only. Final exercise rendering must obey weekly_role_map role, count, day ownership, restrictions, and taper rules first.",
            "If selected_plan.session_sequence is present, render every entry in selected_plan.session_sequence as its own athlete-facing countdown card.",
            "Each selected_plan.session_sequence entry with scheduled_countdown_label/countdown_display_label must appear as a visible D-X header in the final output.",
            "Do not omit selected support, recovery, freshness, mobility, reset, or technical roles because they are low stress or short duration.",
            "Do not collapse a selected countdown session into Lead notes, another day, movement prep, mobility finisher, rationale, or a generic note. It must keep its own D-X card.",
            "If selected_plan.session_sequence contains D-3 fight_week_freshness_day, render a D-3 freshness/reset card even when it is support-class and low RPE.",
            "Render selected countdown cards in descending countdown order, then append D-0 last.",
            "If a calendar day has is_fight_day=true, render fight_day_protocol only.",
            "If a calendar day has is_after_fight_day=true, render no app-led training.",
            "If a weekday is not present in calendar_days, do not render it.",
            "Do not render any session after D-0 unless a post-fight recovery mode is explicitly active.",
            "D-0 always renders as fight-day protocol only.",
            "If late_fight_plan_spec is present, append a terminal D-0 fight-day protocol block after the final active countdown day. D-0 is not an app training session, does not count toward max_active_roles, and must be the final athlete-facing block.",
            "Do not append Coach note, Final coach notes, summary, nutrition, recovery, or any footer after D-0. Put summary notes in Lead notes before the first week or omit them.",
            f"Fight-day protocol text: {FIGHT_DAY_PROTOCOL_TEXT}",
            "Declared hard-sparring/contact days override app S&C unless the contact work is light or cancelled.",
            "For late_fight_plan_spec.allowed_exercises_by_day, each countdown day may render only those listed exercise names plus generic breathing, mobility/reset, shadowboxing/technical cues, hard-sparring/contact session labels, and rehab/prehab band resets except on D-1, where all band work is blocked.",
            "Preserve the priority hierarchy from priority_focus. Do not treat all goals and weak areas equally. Primary goal and primary weak area shape emphasis; secondary selections support without taking over.",
            "If priority_focus.goal_weakness_collisions is non-empty, treat overlap as valid athlete intent. Do not remove it or overcorrect it. Use priority_focus.collision_detail when present to clarify the limiter.",
            "If priority_focus.collision_details contains multiple entries, preserve each clarification. Do not collapse all overlaps into the first detail. Use each detail to sharpen the relevant training emphasis.",
            "Use priority_focus.derived_clarification_tags as internal emphasis signals when preserving the plan's intent. These tags clarify the kind of adaptation the athlete meant, but they do not override hard safety, schedule, injury, phase, or recovery constraints.",
            "Do not expose derived_clarification_tags or raw scoring/reason-code labels directly in athlete-facing text.",
            "Use parsed_injuries and guided_source_injury_subtypes as injury context only. Do not override parsed injury_type or invent diagnoses from subtype tags.",
            "Small mobility prep, reset, or warm-up that appears inside another session does not satisfy or replace a dedicated recovery/mobility day. A role flagged is_dedicated_recovery_mobility_day is a session-level recovery tool and must not be suppressed because mobility already appears as prep elsewhere in the week.",
        ],
        "forbidden_output": {
            "phase_toolbox_labels": list(_FORBIDDEN_TOOLBOX_LABELS),
            "rehab_labels_when_no_active_injury": (
                list(_FORBIDDEN_REHAB_LABELS)
                if guards.get("suppress_rehab_headings")
                else []
            ),
        },
        "restrictions": _compact_restrictions(
            source.get("restrictions") or stage2_payload.get("restrictions")
        ),
        "selected_plan": {
            "session_sequence": _compact_session_sequence(source)
            or _compact_session_sequence(stage2_payload),
            "weekly_role_map": _compact_weekly_role_map(weekly_role_map, athlete_model),
            "late_fight_plan_spec": late_fight_plan_spec,
            "open_plan_spec": open_plan_spec,
            "fight_week_override": (
                source.get("fight_week_override")
                or stage2_payload.get("fight_week_override")
                or {}
            ),
            "week_by_week_progression": (
                source.get("week_by_week_progression")
                or stage2_payload.get("week_by_week_progression")
                or {}
            ),
            "priority_focus": (
                source.get("priority_focus")
                or stage2_payload.get("priority_focus")
                or {}
            ),
        },
        "writing_rules": list((rewrite_guidance or {}).get("writing_rules") or []),
    }

    # Only dated camp mode needs compact phase context.
    if render_mode == "camp_plan":
        packet["phase_briefs"] = (
            source.get("phase_briefs")
            or stage2_payload.get("phase_briefs")
            or {}
        )

    return packet
