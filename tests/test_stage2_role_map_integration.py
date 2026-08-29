from fightcamp.stage2_role_map_integration import (
    integrated_allocation_sort_key,
    integrated_compression_floor,
    late_camp_week_reference_d_day,
)


def test_reference_day_uses_closest_scheduled_day():
    week = {"calendar_days": [{"d_day": 21}, {"d_day": 19}, {"d_day": 18}]}
    athlete = {"days_until_fight": 22}
    assert late_camp_week_reference_d_day(week, athlete) == 18


def test_reference_day_falls_back_to_generation_countdown():
    assert late_camp_week_reference_d_day({}, {"days_until_fight": 20}) == 20


def test_high_cut_adds_one_bounded_compression_slot():
    week = {"calendar_days": [{"d_day": 20}, {"d_day": 18}]}
    athlete = {"cut_severity_bucket": "high", "days_until_fight": 22}
    assert integrated_compression_floor(base_floor=1, week_entry=week, athlete_model=athlete) == 2


def test_moderate_cut_does_not_add_extra_compression():
    week = {"calendar_days": [{"d_day": 20}, {"d_day": 18}]}
    athlete = {"cut_severity_bucket": "moderate", "days_until_fight": 22}
    assert integrated_compression_floor(base_floor=1, week_entry=week, athlete_model=athlete) == 1


def test_goal_priority_only_breaks_equal_base_rank():
    power = {"primary_goal": "power", "key_goals": ["speed"]}
    strength_role = {"category": "strength", "role_key": "neural_plus_strength_day"}
    conditioning_role = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
    }
    assert integrated_allocation_sort_key(
        role=strength_role, base_rank=4, athlete_model=power
    ) > integrated_allocation_sort_key(
        role=conditioning_role, base_rank=4, athlete_model=power
    )


def test_lower_safety_rank_stays_lower_despite_goal_priority():
    conditioning = {"primary_goal": "conditioning"}
    strength_role = {"category": "strength", "role_key": "neural_plus_strength_day"}
    conditioning_role = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
    }
    assert integrated_allocation_sort_key(
        role=strength_role, base_rank=4, athlete_model=conditioning
    ) > integrated_allocation_sort_key(
        role=conditioning_role, base_rank=1, athlete_model=conditioning
    )
