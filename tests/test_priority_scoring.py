from fightcamp.priority_profile import build_priority_profile
from fightcamp.strength import score_exercise
from fightcamp.conditioning import (
    CONDITIONING_GOAL_PRIORITY_SCALE,
    CONDITIONING_WEAKNESS_PRIORITY_SCALE,
)
from fightcamp.priority_profile import total_goal_priority_bonus, total_weakness_priority_bonus


def _base_kwargs():
    return dict(
        exercise_tags=["explosive", "core"],
        weakness_tags=["core", "balance"],
        goal_tags=["explosive", "speed"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["bodyweight"],
        is_rehab=False,
    )


def test_strength_primary_goal_and_weakness_have_higher_bonus():
    profile_primary = build_priority_profile(
        {
            "key_goals": ["power", "speed"],
            "primary_goal": "power",
            "weak_areas": ["core", "balance"],
            "primary_weak_area": "core",
        }
    )
    score_primary, reasons_primary = score_exercise(
        **_base_kwargs(),
        priority_profile=profile_primary,
        matched_goal_labels=["power"],
        matched_weakness_labels=["core"],
    )

    profile_secondary = build_priority_profile(
        {
            "key_goals": ["power", "speed"],
            "primary_goal": "speed",
            "weak_areas": ["core", "balance"],
            "primary_weak_area": "balance",
        }
    )
    score_secondary, reasons_secondary = score_exercise(
        **_base_kwargs(),
        priority_profile=profile_secondary,
        matched_goal_labels=["power"],
        matched_weakness_labels=["core"],
    )

    assert score_primary > score_secondary
    assert reasons_primary["goal_priority_bonus"] == 0.8
    assert reasons_secondary["goal_priority_bonus"] == 0.4
    assert reasons_primary["weakness_priority_bonus"] == 0.9
    assert reasons_secondary["weakness_priority_bonus"] == 0.45
    assert "priority_primary_goal_match:power" in reasons_primary["reason_codes"]
    assert "priority_secondary_goal_match:power" in reasons_secondary["reason_codes"]


def test_strength_priority_bonus_respects_caps():
    profile = build_priority_profile(
        {
            "key_goals": ["power", "speed", "conditioning"],
            "primary_goal": "power",
            "weak_areas": ["core", "balance", "hip_mobility"],
            "primary_weak_area": "core",
        }
    )
    _score, reasons = score_exercise(
        **_base_kwargs(),
        priority_profile=profile,
        matched_goal_labels=["power", "speed", "conditioning"],
        matched_weakness_labels=["core", "balance", "hip_mobility"],
    )

    assert reasons["goal_priority_bonus"] == 1.2
    assert reasons["weakness_priority_bonus"] == 1.35


def test_conditioning_priority_scaling_primary_exceeds_secondary():
    primary_profile = build_priority_profile(
        {
            "key_goals": ["conditioning", "power"],
            "primary_goal": "conditioning",
            "weak_areas": ["core", "balance"],
            "primary_weak_area": "core",
        }
    )
    secondary_profile = build_priority_profile(
        {
            "key_goals": ["conditioning", "power"],
            "primary_goal": "power",
            "weak_areas": ["core", "balance"],
            "primary_weak_area": "balance",
        }
    )

    raw_goal_primary = total_goal_priority_bonus(["conditioning"], primary_profile)
    raw_goal_secondary = total_goal_priority_bonus(["conditioning"], secondary_profile)
    raw_weak_primary = total_weakness_priority_bonus(["core"], primary_profile)
    raw_weak_secondary = total_weakness_priority_bonus(["core"], secondary_profile)

    goal_primary = raw_goal_primary * CONDITIONING_GOAL_PRIORITY_SCALE
    goal_secondary = raw_goal_secondary * CONDITIONING_GOAL_PRIORITY_SCALE
    weakness_primary = raw_weak_primary * CONDITIONING_WEAKNESS_PRIORITY_SCALE
    weakness_secondary = raw_weak_secondary * CONDITIONING_WEAKNESS_PRIORITY_SCALE

    assert goal_primary > goal_secondary
    assert weakness_primary > weakness_secondary
    assert goal_primary > raw_goal_primary
    assert weakness_primary > raw_weak_primary


def test_conditioning_priority_scaling_respects_target_scaled_maximums():
    profile = build_priority_profile(
        {
            "key_goals": ["conditioning", "power", "speed"],
            "primary_goal": "conditioning",
            "weak_areas": ["core", "balance", "hip_mobility"],
            "primary_weak_area": "core",
        }
    )
    raw_goal = total_goal_priority_bonus(["conditioning", "power", "speed"], profile)
    raw_weakness = total_weakness_priority_bonus(["core", "balance", "hip_mobility"], profile)
    goal_scaled = raw_goal * CONDITIONING_GOAL_PRIORITY_SCALE
    weakness_scaled = raw_weakness * CONDITIONING_WEAKNESS_PRIORITY_SCALE

    assert goal_scaled <= 4.0
    assert weakness_scaled <= 5.0
