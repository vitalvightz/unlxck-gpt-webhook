from __future__ import annotations

from copy import deepcopy

import fightcamp.empty_combat_week_policy as policy
from fightcamp.calendar_integrity import apply_final_calendar_integrity
from fightcamp.stage2_role_map import _build_weekly_role_map, _is_hard_pressure_conditioning_role


def _athlete() -> dict:
    return {
        "sport": "boxing",
        "status": "amateur",
        "record": "0-0",
        "rounds_format": "3 x 3",
        "fight_date": "2026-10-11",
        "days_until_fight": 35,
        "plan_creation_weekday": "wednesday",
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "injury_mode": "full_plan",
        "injuries": [],
        "readiness_flags": ["baseline"],
        "primary_goal": "conditioning",
        "key_goals": ["conditioning", "speed"],
        "weaknesses": ["gas_tank"],
        "training_frequency": 4,
        "training_days": ["Monday", "Wednesday", "Thursday", "Friday", "Sunday"],
        "hard_sparring_days": [],
        "support_work_days": ["Wednesday"],
        "technical_skill_days": ["Wednesday"],
        "tactical_styles": ["distance_striker"],
    }


def _progression() -> dict:
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["aerobic", "glycolytic", "alactic"],
            },
            *[
                {
                    "week_index": index,
                    "phase": "GPP" if index < 4 else "SPP",
                    "stage_key": "general_capacity",
                    "span_days": 7,
                    "session_counts": {
                        "strength": 2,
                        "conditioning": 2,
                        "recovery": 1,
                    },
                    "conditioning_sequence": ["aerobic", "glycolytic", "alactic"],
                }
                for index in range(2, 6)
            ],
        ]
    }


def test_policy_does_not_own_post_assignment_calendar_moves():
    # Regression for the architecture contract: this feature may create/upgrade a
    # hard-conditioning role, but it must not rewrite scheduled_day_hint after the
    # canonical role-map/calendar legality owner has assigned the week.
    assert not hasattr(policy, "_move_pressure_to_early_slot")

    role_map = _build_weekly_role_map(
        _athlete(),
        _progression(),
        {"key": "aerobic_repeatability"},
    )
    week = role_map["weeks"][0]
    pressure = next(
        role
        for role in week["session_roles"]
        if role.get("category") == "conditioning"
        and _is_hard_pressure_conditioning_role(role)
    )
    light_combat = next(
        role
        for role in week["session_roles"]
        if role.get("role_key") == "light_combat_day"
    )

    assert pressure["scheduled_day_hint"]
    assert pressure["scheduled_day_hint"].lower() != "wednesday"
    assert light_combat["scheduled_day_hint"].lower() == "wednesday"
    assert "canonical combat-load legality" in pressure["placement_rule"].lower()

    # The finished weekly calendar must also satisfy the final shared governor.
    apply_final_calendar_integrity(deepcopy(role_map))
