from types import SimpleNamespace

from fightcamp import strength
from fightcamp.priority_profile import (
    MAX_GOAL_PRIORITY_BONUS,
    MAX_WEAKNESS_PRIORITY_BONUS,
    build_priority_profile,
    total_goal_priority_bonus,
    total_weakness_priority_bonus,
)


def _profile(goals, primary_goal, weaks, primary_weak):
    return build_priority_profile(
        SimpleNamespace(
            key_goals=goals,
            primary_goal=primary_goal,
            weak_areas=weaks,
            primary_weak_area=primary_weak,
        )
    )


def test_strength_primary_goal_bonus_beats_secondary():
    profile = _profile(["power", "mobility"], "power", ["cns_fatigue"], "cns_fatigue")
    a_score, a_reasons = strength.score_exercise(
        exercise_tags=["power"], weakness_tags=[], goal_tags=["power", "mobility"], style_tags=[], must_have_tags=[],
        phase_tags=[], current_phase="GPP", fatigue_level="low", available_equipment=["bodyweight"],
        required_equipment=["bodyweight"], is_rehab=False, priority_profile=profile,
    )
    b_score, b_reasons = strength.score_exercise(
        exercise_tags=["mobility"], weakness_tags=[], goal_tags=["power", "mobility"], style_tags=[], must_have_tags=[],
        phase_tags=[], current_phase="GPP", fatigue_level="low", available_equipment=["bodyweight"],
        required_equipment=["bodyweight"], is_rehab=False, priority_profile=profile,
    )
    assert a_score > b_score
    assert "priority_primary_goal_match:power" in a_reasons["reason_codes"]


def test_primary_weakness_bonus_beats_secondary():
    profile = _profile(["power"], "power", ["cns_fatigue", "hip_mobility"], "cns_fatigue")
    assert total_weakness_priority_bonus(["cns_fatigue"], profile) > total_weakness_priority_bonus(["hip_mobility"], profile)


def test_conditioning_priority_goal_weights_and_reason_codes():
    profile = _profile(["conditioning", "mobility"], "conditioning", ["cns_fatigue"], "cns_fatigue")
    assert total_goal_priority_bonus(["conditioning"], profile) > total_goal_priority_bonus(["mobility"], profile)


def test_priority_caps_prevent_tag_spam():
    profile = _profile(["power", "mobility", "conditioning", "speed"], "power", ["cns_fatigue", "hip_mobility", "balance"], "cns_fatigue")
    assert total_goal_priority_bonus(["mobility", "conditioning", "speed", "mobility"], profile) <= MAX_GOAL_PRIORITY_BONUS
    assert total_weakness_priority_bonus(["hip_mobility", "balance", "hip_mobility"], profile) <= MAX_WEAKNESS_PRIORITY_BONUS


def test_backward_compatibility_primary_fallback_and_safety_gate():
    profile = build_priority_profile(SimpleNamespace(key_goals=["power", "mobility"], weak_areas=["cns_fatigue"], primary_goal="", primary_weak_area=""))
    assert profile.primary_goal == "power"
    assert profile.primary_weak_area == "cns_fatigue"

    score, _ = strength.score_exercise(
        exercise_tags=["power"], weakness_tags=[], goal_tags=["power"], style_tags=[], must_have_tags=[],
        phase_tags=[], current_phase="GPP", fatigue_level="low", available_equipment=["bodyweight"],
        required_equipment=["barbell"], is_rehab=False, priority_profile=profile,
    )
    assert score == -999
