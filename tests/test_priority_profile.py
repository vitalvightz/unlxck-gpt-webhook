from types import SimpleNamespace

from fightcamp.priority_profile import (
    MAX_GOAL_PRIORITY_BONUS,
    MAX_WEAKNESS_PRIORITY_BONUS,
    PRIMARY_GOAL_WEIGHT,
    PRIMARY_WEAKNESS_WEIGHT,
    SECONDARY_GOAL_WEIGHT,
    SECONDARY_WEAKNESS_WEIGHT,
    PriorityProfile,
    build_priority_profile,
    describe_priority_focus,
    goal_priority_weight,
    normalize_priority_values,
    total_goal_priority_bonus,
    total_weakness_priority_bonus,
    weakness_priority_weight,
)


def test_normalizes_comma_separated_values():
    assert normalize_priority_values("power, mobility, power") == ["power", "mobility"]


def test_builds_explicit_profile():
    plan_input = SimpleNamespace(
        key_goals="power, conditioning, mobility",
        primary_goal="conditioning",
        weak_areas="cns_fatigue, hip_mobility",
        primary_weak_area="hip_mobility",
    )

    profile = build_priority_profile(plan_input)

    assert profile.primary_goal == "conditioning"
    assert profile.secondary_goals == ["power", "mobility"]
    assert profile.primary_weak_area == "hip_mobility"
    assert profile.secondary_weak_areas == ["cns_fatigue"]


def test_falls_back_when_primary_missing():
    plan_input = SimpleNamespace(
        key_goals="power, mobility",
        primary_goal="",
        weak_areas="",
        primary_weak_area="",
    )

    profile = build_priority_profile(plan_input)

    assert profile.primary_goal == "power"
    assert profile.secondary_goals == ["mobility"]


def test_falls_back_when_primary_invalid():
    plan_input = SimpleNamespace(
        key_goals="power, mobility",
        primary_goal="conditioning",
        weak_areas="",
        primary_weak_area="",
    )

    profile = build_priority_profile(plan_input)

    assert profile.primary_goal == "power"
    assert profile.secondary_goals == ["mobility"]


def test_empty_profile_is_safe():
    plan_input = SimpleNamespace(
        key_goals="",
        primary_goal="",
        weak_areas="",
        primary_weak_area="",
    )

    profile = build_priority_profile(plan_input)

    assert profile.primary_goal == ""
    assert profile.primary_weak_area == ""
    assert profile.secondary_goals == []
    assert profile.secondary_weak_areas == []


def test_goal_weights_work():
    profile = PriorityProfile(
        primary_goal="power",
        secondary_goals=["mobility"],
        primary_weak_area="",
        secondary_weak_areas=[],
        all_goals=["power", "mobility"],
        all_weak_areas=[],
    )

    assert goal_priority_weight("power", profile) == PRIMARY_GOAL_WEIGHT
    assert goal_priority_weight("mobility", profile) == SECONDARY_GOAL_WEIGHT
    assert goal_priority_weight("conditioning", profile) == 0.0


def test_weakness_weights_work():
    profile = PriorityProfile(
        primary_goal="",
        secondary_goals=[],
        primary_weak_area="cns_fatigue",
        secondary_weak_areas=["hip_mobility"],
        all_goals=[],
        all_weak_areas=["cns_fatigue", "hip_mobility"],
    )

    assert weakness_priority_weight("cns_fatigue", profile) == PRIMARY_WEAKNESS_WEIGHT
    assert weakness_priority_weight("hip_mobility", profile) == SECONDARY_WEAKNESS_WEIGHT
    assert weakness_priority_weight("grip_strength", profile) == 0.0


def test_aggregate_bonuses_are_capped():
    profile = PriorityProfile(
        primary_goal="power",
        secondary_goals=["conditioning", "mobility", "speed"],
        primary_weak_area="cns_fatigue",
        secondary_weak_areas=["hip_mobility", "defense", "balance"],
        all_goals=["power", "conditioning", "mobility", "speed"],
        all_weak_areas=["cns_fatigue", "hip_mobility", "defense", "balance"],
    )

    assert total_goal_priority_bonus(["power", "conditioning", "mobility", "speed"], profile) <= MAX_GOAL_PRIORITY_BONUS
    assert total_weakness_priority_bonus(["cns_fatigue", "hip_mobility", "defense", "balance"], profile) <= MAX_WEAKNESS_PRIORITY_BONUS


def test_duplicate_tags_do_not_double_count():
    profile = PriorityProfile(
        primary_goal="power",
        secondary_goals=["mobility"],
        primary_weak_area="",
        secondary_weak_areas=[],
        all_goals=["power", "mobility"],
        all_weak_areas=[],
    )

    assert total_goal_priority_bonus(["power", "power", "mobility"], profile) == total_goal_priority_bonus(
        ["power", "mobility"], profile
    )


def test_summary_helper_works():
    profile = PriorityProfile(
        primary_goal="power",
        secondary_goals=["conditioning", "mobility"],
        primary_weak_area="cns_fatigue",
        secondary_weak_areas=["hip_mobility"],
        all_goals=["power", "conditioning", "mobility"],
        all_weak_areas=["cns_fatigue", "hip_mobility"],
    )

    summary = describe_priority_focus(profile)

    assert summary["main_focus"] == "Build power while managing cns_fatigue."


def test_build_priority_profile_supports_dict_input():
    profile = build_priority_profile(
        {
            "key_goals": ["power", "mobility"],
            "primary_goal": "power",
            "weak_areas": ["cns_fatigue", "hip_mobility"],
            "primary_weak_area": "cns_fatigue",
        }
    )

    assert profile.primary_goal == "power"
    assert profile.primary_weak_area == "cns_fatigue"


def test_build_priority_profile_supports_weaknesses_alias():
    profile = build_priority_profile(
        {
            "key_goals": ["power"],
            "weaknesses": ["core", "balance"],
            "primary_weak_area": "core",
        }
    )

    assert profile.primary_weak_area == "core"
    assert profile.secondary_weak_areas == ["balance"]
