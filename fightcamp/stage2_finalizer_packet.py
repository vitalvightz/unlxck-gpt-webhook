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
from .stage2_render_guards import _render_guard_flags


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
        "selection_rule",
        "placement_rule",
        "day_assignment_reason",
        "coach_owned",
        "display_text",
        "athlete_facing_label",

        # Gas-tank / recovery-day upgrade flags
        "gas_tank_recovery_touch",
        "allowed_on_recovery_day",
        "recovery_compatible",
        "converted_from_unused_day",
        "original_role_key",
        "original_unused_day_role",

        # Safety filters for low-aerobic recovery work
        "blocked_systems",
        "blocked_intensities",
        "blocked_tags",
    )
    return {key: role.get(key) for key in keep if role.get(key) not in (None, "", [])}


def _compact_weekly_role_map(weekly_role_map: Any) -> dict[str, Any]:
    if not isinstance(weekly_role_map, dict):
        return {}

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
                    "effective_hard_sparring_days": week.get("effective_hard_sparring_days"),
                    "final_week_sparring_cap": week.get("final_week_sparring_cap"),
                    "coach_note_flags": week.get("coach_note_flags"),
                    "intentional_compression": week.get("intentional_compression"),
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


def _compact_calendar_authority(weekly_role_map: Any) -> dict[str, Any]:
    if not isinstance(weekly_role_map, dict):
        return {"weeks": []}

    compact_weeks: list[dict[str, Any]] = []
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        calendar_days = [
            day
            for day in (week.get("calendar_days") or [])
            if isinstance(day, dict)
        ]
        compact_weeks.append(
            {
                "week_index": week.get("week_index"),
                "phase": week.get("phase"),
                "calendar_days": calendar_days,
                "countdown_range": week.get("countdown_range"),
                "session_day_hints": [
                    {
                        "session_index": role.get("session_index"),
                        "role_key": role.get("role_key"),
                        "scheduled_day_hint": role.get("scheduled_day_hint"),
                    }
                    for role in (week.get("session_roles") or [])
                    if isinstance(role, dict)
                ],
                "fight_day_override": week.get("fight_day_override"),
            }
        )

    return {"weeks": compact_weeks}


def _compact_session_sequence(stage2_payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "late_fight_session_sequence",
        "session_sequence",
        "countdown_sessions",
    ):
        value = stage2_payload.get(key)
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]

    plan_spec = stage2_payload.get("late_fight_plan_spec") or {}
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
    late_fight_plan_spec = (
        source.get("late_fight_plan_spec")
        or stage2_payload.get("late_fight_plan_spec")
        or {}
    )

    days_out_payload = (
        source.get("days_out_payload")
        or stage2_payload.get("days_out_payload")
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
            "If a calendar day has is_fight_day=true, render fight_day_protocol only.",
            "If a calendar day has is_after_fight_day=true, render no app-led training.",
            "If a weekday is not present in calendar_days, do not render it.",
            "Do not render any session after D-0 unless a post-fight recovery mode is explicitly active.",
            "D-0 always renders as fight-day protocol only.",
            f"Fight-day protocol text: {FIGHT_DAY_PROTOCOL_TEXT}",
            "Coach-owned days override app S&C unless coach-led work is light or cancelled.",
            "For late_fight_plan_spec.allowed_exercises_by_day, each countdown day may render only those listed exercise names plus generic breathing, mobility/reset, shadowboxing/technical cues, coach-led session labels, and rehab/prehab band resets.",
            "Preserve the priority hierarchy from priority_focus. Do not treat all goals and weak areas equally. Primary goal and primary weak area shape emphasis; secondary selections support without taking over.",
            "If priority_focus.goal_weakness_collisions is non-empty, treat overlap as valid athlete intent. Do not remove it or overcorrect it. Use priority_focus.collision_detail when present to clarify the limiter.",
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
            "weekly_role_map": _compact_weekly_role_map(weekly_role_map),
            "calendar_authority": _compact_calendar_authority(weekly_role_map),
            "late_fight_plan_spec": late_fight_plan_spec,
            "days_out_payload": days_out_payload,
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

    # Normal camp may still need compact phase context. Late-fight should not.
    if render_mode != "late_fight_countdown_only":
        packet["phase_briefs"] = (
            source.get("phase_briefs")
            or stage2_payload.get("phase_briefs")
            or {}
        )

    return packet
