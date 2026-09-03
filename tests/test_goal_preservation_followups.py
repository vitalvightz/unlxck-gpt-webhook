"""Follow-up regressions for goal-preservation deferral authority."""

import pytest

from fightcamp.goal_preservation import reconcile_goal_preservation, validate_goal_preservation
from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions


def _slot(name="Deadlift", quality="anchor_loaded"):
    return {
        "slot_id": name,
        "session_index": 1,
        "role": "hinge",
        "quality_class": quality,
        "anchor_capable": True,
        "selected": {
            "name": name,
            "quality_class": quality,
            "prescription": "3 x 3 @ RPE 7",
            "movement_patterns": ["speed"] if quality == "anchor_power" else ["hinge"],
        },
    }


def _role(day=18):
    return {
        "role_key": "strength_touch_day",
        "category": "strength",
        "strength_session_index": 1,
        "session_index": 1,
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": f"D-{day}",
    }


def _brief(*, days, role, slots):
    return {
        "athlete_snapshot": {
            "key_goals": ["speed", "strength"],
            "primary_goal": "speed",
            "days_until_fight": days,
            "fatigue": "low",
            "training_frequency": 4,
        },
        "priority_focus": {"primary_goal": "speed", "secondary_goals": ["strength"]},
        "weekly_role_map": {
            "weeks": [{
                "week_index": 1,
                "phase": "SPP",
                "declared_training_days": ["Monday", "Thursday"],
                "calendar_days": [
                    {"weekday": "monday", "d_day": days},
                    {"weekday": "thursday", "d_day": max(1, days - 3)},
                ],
                "session_roles": [role],
                "suppressed_roles": [],
            }]
        },
        "candidate_pools": {"SPP": {"strength_slots": slots}},
        "restrictions": [],
    }


def _goal(brief, name):
    return next(entry for entry in brief["goal_preservation"] if entry["goal"] == name)


def test_two_hard_spar_days_alone_cannot_justify_strength_deferral():
    role = _role(13)
    brief = _brief(
        days=26,
        role=role,
        slots=[_slot("Medicine Ball Rotational Slam", "anchor_power")],
    )
    brief["athlete_snapshot"].update(
        sport="mma",
        weaknesses=["footwork", "power"],
        equipment=["barbell", "kettlebells", "medicine_ball"],
        hard_sparring_days=["Tuesday", "Friday"],
    )
    week = brief["weekly_role_map"]["weeks"][0]
    week["calendar_days"] = [
        {"weekday": "monday", "d_day": 13},
        {"weekday": "thursday", "d_day": 18},
        {"weekday": "friday", "d_day": 25},
    ]
    week["suppressed_roles"] = [{
        "category": "strength",
        "role_key": "primary_strength_day",
        "compression_reason_codes": ["two_hard_spar_days"],
    }]

    apply_late_camp_role_morph(brief["weekly_role_map"])
    apply_effective_strength_prescriptions(
        weekly_role_map=brief["weekly_role_map"],
        candidate_pools=brief["candidate_pools"],
        athlete_model=brief["athlete_snapshot"],
    )
    reconcile_goal_preservation(brief)

    strength = _goal(brief, "strength")
    assert strength["state"] == "maintain"
    assert strength["satisfied"] is False
    assert strength["evidence"] == []
    assert strength["constraints"] == []
    assert "calendar_capacity" not in strength["reason_codes"]
    assert any(error["goal"] == "strength" for error in validate_goal_preservation(brief))


@pytest.mark.parametrize("day", [8, 10, 13])
def test_direct_late_countdown_readiness_reduction_can_justify_strength_deferral(day):
    role = _role(day)
    brief = _brief(days=day, role=role, slots=[_slot()])
    brief["athlete_snapshot"].update(
        key_goals=["strength"],
        primary_goal="strength",
        fatigue="high",
    )
    brief["priority_focus"] = {"primary_goal": "strength", "secondary_goals": []}
    brief["late_fight_session_sequence"] = [role]

    direct_role_map = {
        "weeks": [{
            "week_index": 1,
            "phase": "SPP",
            "session_roles": brief["late_fight_session_sequence"],
        }]
    }
    apply_late_camp_role_morph(direct_role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=direct_role_map,
        candidate_pools=brief["candidate_pools"],
        athlete_model=brief["athlete_snapshot"],
    )

    assert any(
        item.get("effective_loaded") and item.get("effective_max_sets") == 1
        for item in role.get("effective_strength_prescriptions") or []
    )

    reconcile_goal_preservation(brief)
    strength = _goal(brief, "strength")

    assert strength["state"] == "defer"
    assert strength["satisfied"] is False
    assert strength["evidence"] == []
    assert any(
        constraint.get("reason_code") == "high_fatigue"
        and constraint.get("authority") == "effective_strength_prescriptions"
        for constraint in strength["constraints"]
    )
    assert validate_goal_preservation(brief) == []
