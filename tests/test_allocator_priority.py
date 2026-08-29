from fightcamp.allocator_priority import (
    allocation_sort_key,
    readiness_compression_floor_with_late_cut,
)


def test_goal_priority_breaks_equal_base_rank_for_power_primary():
    athlete = {"primary_goal": "power", "key_goals": ["power", "conditioning"]}
    strength = {"category": "strength", "role_key": "neural_plus_strength_day"}
    conditioning = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
    }
    assert allocation_sort_key(base_rank=4, role=strength, athlete_model=athlete) > allocation_sort_key(
        base_rank=4, role=conditioning, athlete_model=athlete
    )


def test_goal_priority_breaks_equal_base_rank_for_conditioning_primary():
    athlete = {"primary_goal": "conditioning", "key_goals": ["conditioning", "power"]}
    strength = {"category": "strength", "role_key": "neural_plus_strength_day"}
    conditioning = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
    }
    assert allocation_sort_key(base_rank=4, role=conditioning, athlete_model=athlete) > allocation_sort_key(
        base_rank=4, role=strength, athlete_model=athlete
    )


def test_goal_priority_never_overrides_a_safety_demoted_base_rank():
    athlete = {"primary_goal": "conditioning"}
    strength = {"category": "strength", "role_key": "neural_plus_strength_day"}
    conditioning = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
    }
    assert allocation_sort_key(base_rank=4, role=strength, athlete_model=athlete) > allocation_sort_key(
        base_rank=1, role=conditioning, athlete_model=athlete
    )


def test_high_cut_adds_one_bounded_compression_slot():
    assert readiness_compression_floor_with_late_cut(
        base_floor=1,
        athlete_model={"cut_severity_bucket": "high", "days_until_fight": 20},
    ) == 2


def test_moderate_cut_keeps_existing_floor():
    assert readiness_compression_floor_with_late_cut(
        base_floor=1,
        athlete_model={"cut_severity_bucket": "moderate", "days_until_fight": 20},
    ) == 1
