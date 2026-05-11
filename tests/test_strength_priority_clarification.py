from types import SimpleNamespace

from fightcamp import strength
from fightcamp.priority_clarification_tags import derive_clarification_tags
from fightcamp.priority_profile import build_priority_profile


def _profile():
    return build_priority_profile(
        SimpleNamespace(
            key_goals=["strength"],
            primary_goal="strength",
            weak_areas=["strength"],
            primary_weak_area="strength",
        )
    )


def test_no_clarification_tags_no_score_change():
    profile = _profile()
    base_score, _ = strength.score_exercise(
        exercise_tags=["posterior_chain", "deadlift"],
        weakness_tags=["strength"],
        goal_tags=["strength"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["bodyweight"],
        is_rehab=False,
        priority_profile=profile,
        derived_clarification_tags=[],
    )
    no_input_score, _ = strength.score_exercise(
        exercise_tags=["posterior_chain", "deadlift"],
        weakness_tags=["strength"],
        goal_tags=["strength"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["bodyweight"],
        is_rehab=False,
        priority_profile=profile,
    )
    assert base_score == no_input_score


def test_posterior_chain_detail_bumps_matching_tags_only():
    profile = _profile()
    derived = derive_clarification_tags([{"tag": "strength", "detail": "Posterior-chain strength"}])

    match_score, match_reasons = strength.score_exercise(
        exercise_tags=["posterior_chain", "hip_dominant", "deadlift"],
        weakness_tags=["strength"],
        goal_tags=["strength"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["bodyweight"],
        is_rehab=False,
        priority_profile=profile,
        derived_clarification_tags=derived,
    )
    non_match_score, non_match_reasons = strength.score_exercise(
        exercise_tags=["upper_body", "shoulders"],
        weakness_tags=["strength"],
        goal_tags=["strength"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["bodyweight"],
        is_rehab=False,
        priority_profile=profile,
        derived_clarification_tags=derived,
    )
    assert match_score > non_match_score
    assert "priority_clarification_tag_match:posterior_chain" in match_reasons["reason_codes"]
    assert not any(code.startswith("priority_clarification_tag_match") for code in non_match_reasons["reason_codes"])


def test_clarification_bonus_is_capped():
    score, reasons = strength.score_exercise(
        exercise_tags=["posterior_chain", "hip_dominant", "hamstring", "deadlift"],
        weakness_tags=[],
        goal_tags=[],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["bodyweight"],
        is_rehab=False,
        derived_clarification_tags=["posterior_chain", "hip_dominant", "hamstring", "deadlift"],
    )
    assert reasons["clarification_bonus"] == strength.STRENGTH_MAX_CLARIFICATION_TAG_BONUS
    assert score >= strength.STRENGTH_MAX_CLARIFICATION_TAG_BONUS


def test_reason_codes_do_not_leak_into_strength_text_output():
    plan_text = strength.format_strength_block(
        exercises=[{"name": "Trap Bar Deadlift", "tags": ["posterior_chain"]}],
        phase="GPP",
        fatigue="low",
    )
    assert "priority_clarification_tag_match" not in plan_text
    assert "priority_primary_goal_match" not in plan_text
    assert "priority_collision_goal_weakness" not in plan_text


def test_blocked_equipment_still_blocks_matching_clarification_tags():
    score, _ = strength.score_exercise(
        exercise_tags=["deadlift", "posterior_chain"],
        weakness_tags=[],
        goal_tags=[],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["barbell"],
        is_rehab=False,
        derived_clarification_tags=["deadlift", "posterior_chain"],
    )
    assert score == -999


def test_upper_body_strength_clarification_bumps_upper_only():
    derived = derive_clarification_tags([{"tag": "strength", "detail": "Upper-body strength"}])
    upper_score, _ = strength.score_exercise(
        exercise_tags=["upper_body", "pull", "grip", "isometric"],
        weakness_tags=[],
        goal_tags=[],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["bodyweight"],
        is_rehab=False,
        derived_clarification_tags=derived,
    )
    lower_score, lower_reasons = strength.score_exercise(
        exercise_tags=["posterior_chain", "hip_dominant"],
        weakness_tags=[],
        goal_tags=[],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["bodyweight"],
        required_equipment=["bodyweight"],
        is_rehab=False,
        derived_clarification_tags=derived,
    )
    assert upper_score > lower_score
    assert not any(code.startswith("priority_clarification_tag_match") for code in lower_reasons["reason_codes"])
