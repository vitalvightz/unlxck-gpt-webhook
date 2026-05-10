from types import SimpleNamespace

from fightcamp.priority_profile import (
    COLLISION_INTENT_BONUS,
    MAX_GOAL_PRIORITY_BONUS,
    MAX_WEAKNESS_PRIORITY_BONUS,
    PRIMARY_GOAL_WEIGHT,
    PRIMARY_WEAKNESS_WEIGHT,
    SECONDARY_GOAL_WEIGHT,
    SECONDARY_WEAKNESS_WEIGHT,
    PriorityProfile,
    build_priority_profile,
    collision_safe_priority_bonus_for_tag,
    describe_priority_focus,
    goal_priority_weight,
    is_priority_collision_tag,
    normalize_priority_values,
    total_collision_safe_priority_bonus,
    total_goal_priority_bonus,
    total_weakness_priority_bonus,
    weakness_priority_weight,
)
from fightcamp.tagging import normalize_tag


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


def test_profile_detects_primary_goal_weakness_collision():
    plan_input = SimpleNamespace(
        key_goals="power, conditioning",
        primary_goal="power",
        weak_areas="power, gas_tank",
        primary_weak_area="power",
    )

    profile = build_priority_profile(plan_input)

    assert profile.goal_weakness_collisions == ["power"]
    assert profile.primary_goal_weakness_collision is True
    assert profile.primary_collision_tag == "power"
    assert profile.all_goals == ["power", "conditioning"]
    assert profile.all_weak_areas == ["power", "gas_tank"]


def test_profile_detects_secondary_goal_weakness_overlap():
    plan_input = SimpleNamespace(
        key_goals="power, mobility",
        primary_goal="power",
        weak_areas="gas_tank, mobility",
        primary_weak_area="gas_tank",
    )

    profile = build_priority_profile(plan_input)

    assert profile.goal_weakness_collisions == ["mobility"]
    assert profile.primary_goal_weakness_collision is False
    assert profile.primary_collision_tag == ""


def test_profile_detects_normalized_case_overlap_and_preserves_goal_value():
    plan_input = SimpleNamespace(
        key_goals="Power, Conditioning",
        primary_goal="Power",
        weak_areas="power, Gas Tank",
        primary_weak_area="power",
    )

    profile = build_priority_profile(plan_input)

    assert profile.goal_weakness_collisions == ["Power"]
    assert profile.primary_goal_weakness_collision is True
    assert profile.primary_collision_tag == "Power"


def test_profile_detects_space_vs_underscore_overlap():
    plan_input = SimpleNamespace(
        key_goals="Gas Tank, mobility",
        primary_goal="mobility",
        weak_areas="gas_tank, balance",
        primary_weak_area="balance",
    )

    profile = build_priority_profile(plan_input)

    assert profile.goal_weakness_collisions == ["Gas Tank"]
    assert profile.primary_goal_weakness_collision is False
    assert profile.primary_collision_tag == ""


def test_profile_detects_power_explosiveness_overlap_when_normalizer_supports_it():
    plan_input = SimpleNamespace(
        key_goals="Power & Explosiveness, mobility",
        primary_goal="mobility",
        weak_areas="power_explosiveness, balance",
        primary_weak_area="balance",
    )

    profile = build_priority_profile(plan_input)
    expected = (
        ["Power & Explosiveness"]
        if normalize_tag("Power & Explosiveness") == normalize_tag("power_explosiveness")
        else []
    )

    assert profile.goal_weakness_collisions == expected


def test_profile_without_overlap_has_clean_collision_metadata():
    plan_input = SimpleNamespace(
        key_goals="power, mobility",
        primary_goal="power",
        weak_areas="gas_tank, balance",
        primary_weak_area="gas_tank",
    )

    profile = build_priority_profile(plan_input)

    assert profile.goal_weakness_collisions == []
    assert profile.primary_goal_weakness_collision is False
    assert profile.primary_collision_tag == ""


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


def test_collision_safe_priority_bonus_uses_intent_bonus_not_full_sum():
    profile = build_priority_profile(
        SimpleNamespace(
            key_goals=["power"],
            primary_goal="power",
            weak_areas=["power"],
            primary_weak_area="power",
        )
    )

    assert is_priority_collision_tag("power", profile) is True
    assert collision_safe_priority_bonus_for_tag("power", profile) == PRIMARY_WEAKNESS_WEIGHT + COLLISION_INTENT_BONUS


def test_total_collision_safe_priority_bonus_dedupes_and_caps():
    profile = build_priority_profile(
        SimpleNamespace(
            key_goals=["power", "mobility"],
            primary_goal="power",
            weak_areas=["power", "mobility"],
            primary_weak_area="power",
        )
    )

    assert total_collision_safe_priority_bonus(["power"], ["power"], profile) == 1.1
    assert total_collision_safe_priority_bonus(
        ["power", "mobility"],
        ["power", "mobility"],
        profile,
        max_bonus=1.0,
    ) == 1.0


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
