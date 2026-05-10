from fightcamp.priority_profile import build_priority_profile
from fightcamp.strength import score_exercise


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
