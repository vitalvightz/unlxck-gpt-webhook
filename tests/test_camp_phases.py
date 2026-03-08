from fightcamp.camp_phases import calculate_phase_weeks



def test_calculate_phase_weeks_prefers_days_until_fight_over_weeks_out():
    days_driven = calculate_phase_weeks(6, "boxing", days_until_fight=10)
    one_week_equivalent = calculate_phase_weeks(1, "boxing", days_until_fight=10)
    week_only = calculate_phase_weeks(6, "boxing")

    assert days_driven == one_week_equivalent
    assert days_driven != week_only
    assert sum(days_driven["days"].values()) == 10



def test_calculate_phase_weeks_uses_same_day_fight_as_exact_days_input():
    same_day = calculate_phase_weeks(6, "boxing", days_until_fight=0)
    same_day_equivalent = calculate_phase_weeks(1, "boxing", days_until_fight=0)
    week_only = calculate_phase_weeks(6, "boxing")

    assert same_day == same_day_equivalent
    assert same_day != week_only
    assert sum(same_day["days"].values()) == 0
