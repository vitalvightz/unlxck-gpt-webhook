from types import SimpleNamespace

from fightcamp import conditioning, strength
from fightcamp.priority_profile import (
    build_priority_profile,
    total_collision_safe_priority_bonus,
    total_strength_collision_safe_priority_bonus,
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


def test_strength_primary_collision_does_not_double_count():
    profile = _profile(["power"], "power", ["power"], "power")

    score, reasons = strength.score_exercise(
        exercise_tags=["power"],
        weakness_tags=["power"],
        goal_tags=["power"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=[],
        required_equipment=[],
        is_rehab=False,
        priority_profile=profile,
    )

    assert score == 1.1
    assert score < 1.7
    assert "priority_primary_goal_match:power" in reasons["reason_codes"]
    assert "priority_primary_weakness_match:power" in reasons["reason_codes"]
    assert "priority_collision_goal_weakness:power" in reasons["reason_codes"]


def test_strength_primary_collision_beats_secondary_goal_only_match():
    profile = _profile(["power", "mobility"], "power", ["power"], "power")

    collision_score, _ = strength.score_exercise(
        exercise_tags=["power"],
        weakness_tags=["power"],
        goal_tags=["power", "mobility"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=[],
        required_equipment=[],
        is_rehab=False,
        priority_profile=profile,
    )
    secondary_score, _ = strength.score_exercise(
        exercise_tags=["mobility"],
        weakness_tags=["power"],
        goal_tags=["power", "mobility"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=[],
        required_equipment=[],
        is_rehab=False,
        priority_profile=profile,
    )

    assert collision_score > secondary_score


def test_strength_non_collision_keeps_prior_goal_plus_weakness_sum():
    profile = _profile(["power"], "power", ["gas_tank"], "gas_tank")

    score, reasons = strength.score_exercise(
        exercise_tags=["power", "gas_tank"],
        weakness_tags=["gas_tank"],
        goal_tags=["power"],
        style_tags=[],
        must_have_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=[],
        required_equipment=[],
        is_rehab=False,
        priority_profile=profile,
    )

    assert score == 1.7
    assert "priority_primary_goal_match:power" in reasons["reason_codes"]
    assert "priority_primary_weakness_match:gas_tank" in reasons["reason_codes"]
    assert "priority_collision_goal_weakness:power" not in reasons["reason_codes"]


def test_strength_non_collision_keeps_separate_goal_cap():
    profile = _profile(["power", "mobility", "conditioning", "speed"], "power", [], "")

    assert total_strength_collision_safe_priority_bonus(
        ["power", "mobility", "conditioning", "speed"],
        [],
        profile,
    ) == total_goal_priority_bonus(["power", "mobility", "conditioning", "speed"], profile)


def test_conditioning_priority_goal_weights_and_reason_codes():
    profile = _profile(["conditioning", "mobility"], "conditioning", ["cns_fatigue"], "cns_fatigue")
    assert total_goal_priority_bonus(["conditioning"], profile) > total_goal_priority_bonus(["mobility"], profile)


def test_conditioning_block_uses_primary_goal_priority(monkeypatch):
    monkeypatch.setattr(
        conditioning,
        "get_conditioning_bank",
        lambda: [
            {
                "name": "Primary Goal Drill",
                "placement": "conditioning",
                "phases": ["GPP"],
                "system": "aerobic",
                "tags": ["conditioning", "boxing"],
                "equipment": ["bodyweight"],
            },
            {
                "name": "Secondary Goal Drill",
                "placement": "conditioning",
                "phases": ["GPP"],
                "system": "aerobic",
                "tags": ["mobility", "boxing"],
                "equipment": ["bodyweight"],
            },
        ],
    )
    flags = {
        "phase": "GPP",
        "fatigue": "low",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "key_goals": ["conditioning", "mobility"],
        "primary_goal": "conditioning",
        "weaknesses": [],
        "primary_weak_area": "",
        "injuries": [],
        "equipment": ["bodyweight"],
        "training_frequency": 1,
        "days_available": 1,
    }
    _, _, _, _, _, candidate_reservoir = conditioning.generate_conditioning_block(flags)
    reasons_by_name = {
        entry["drill"]["name"]: entry["reasons"]
        for entry in candidate_reservoir["aerobic"]
    }
    assert reasons_by_name["Primary Goal Drill"]["final_score"] > reasons_by_name["Secondary Goal Drill"]["final_score"]
    assert "priority_primary_goal_match:conditioning" in reasons_by_name["Primary Goal Drill"]["reason_codes"]


def test_priority_caps_prevent_tag_spam():
    profile = _profile(["power", "mobility", "conditioning", "speed"], "power", ["cns_fatigue", "hip_mobility", "balance"], "cns_fatigue")
    assert conditioning._conditioning_goal_priority_bonus(["power", "mobility", "conditioning", "speed"], profile) == 4.0
    assert conditioning._conditioning_weakness_priority_bonus(["cns_fatigue", "hip_mobility", "balance", "defense"], profile) == 5.0


def test_conditioning_primary_collision_is_controlled():
    profile = _profile(["power"], "power", ["power"], "power")

    bonus = conditioning._conditioning_collision_safe_priority_bonus(["power"], ["power"], profile)

    assert bonus == 3.0
    assert bonus < 4.5


def test_conditioning_secondary_overlap_is_controlled():
    profile = _profile(["power", "mobility"], "power", ["gas_tank", "mobility"], "gas_tank")

    bonus = conditioning._conditioning_collision_safe_priority_bonus(["mobility"], ["mobility"], profile)

    assert bonus == 1.5
    assert bonus < 2.25


def test_collision_safe_helpers_respect_caps():
    profile = _profile(
        ["power", "mobility", "speed"],
        "power",
        ["power", "mobility", "speed"],
        "power",
    )

    assert total_collision_safe_priority_bonus(
        ["power", "mobility"],
        ["power", "mobility"],
        profile,
        max_bonus=1.0,
    ) == 1.0
    assert conditioning._conditioning_collision_safe_priority_bonus(
        ["power", "mobility", "speed"],
        ["power", "mobility", "speed"],
        profile,
    ) == conditioning.CONDITIONING_MAX_COLLISION_SAFE_PRIORITY_BONUS


def test_conditioning_collision_reason_code_is_not_athlete_facing(monkeypatch):
    monkeypatch.setitem(conditioning.GOAL_TAG_MAP, "power", ["power"])
    monkeypatch.setitem(conditioning.WEAKNESS_TAG_MAP, "power", ["power"])
    monkeypatch.setattr(
        conditioning,
        "get_conditioning_bank",
        lambda: [
            {
                "name": "Power Priority Drill",
                "placement": "conditioning",
                "phases": ["GPP"],
                "system": "aerobic",
                "tags": ["power", "boxing"],
                "equipment": ["bodyweight"],
            },
        ],
    )
    flags = {
        "phase": "GPP",
        "fatigue": "low",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "key_goals": ["power"],
        "primary_goal": "power",
        "weaknesses": ["power"],
        "primary_weak_area": "power",
        "injuries": [],
        "equipment": ["bodyweight"],
        "training_frequency": 1,
        "days_available": 1,
    }

    output_lines, _, _, _, _, candidate_reservoir = conditioning.generate_conditioning_block(flags)
    # Locate the collision drill by identity rather than reservoir position: a
    # real exact-sport style drill can legitimately out-rank this synthetic one,
    # and this test is about the reason code's *visibility*, not its ranking.
    entry = next(
        item
        for item in candidate_reservoir["aerobic"]
        if item["drill"]["name"] == "Power Priority Drill"
    )
    reasons = entry["reasons"]

    assert "priority_collision_goal_weakness:power" in reasons["reason_codes"]
    assert "priority_collision_goal_weakness:power" not in "\n".join(output_lines)


def test_collision_priority_does_not_override_safety_gate():
    profile = build_priority_profile(
        SimpleNamespace(
            key_goals=["power", "mobility"],
            weak_areas=["power"],
            primary_goal="power",
            primary_weak_area="power",
        )
    )
    assert profile.primary_goal == "power"
    assert profile.primary_weak_area == "power"

    score, _ = strength.score_exercise(
        exercise_tags=["power"], weakness_tags=[], goal_tags=["power"], style_tags=[], must_have_tags=[],
        phase_tags=[], current_phase="GPP", fatigue_level="low", available_equipment=["bodyweight"],
        required_equipment=["barbell"], is_rehab=False, priority_profile=profile,
    )
    assert score == -999
