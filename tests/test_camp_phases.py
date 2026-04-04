from fightcamp.camp_phases import calculate_phase_weeks
from fightcamp.phases import PHASE_VALUES, PhaseEnum


def test_phase_enum_exposes_supported_phase_values():
    assert PhaseEnum.GPP.value == "GPP"
    assert PhaseEnum.SPP.value == "SPP"
    assert PhaseEnum.TAPER.value == "TAPER"
    assert PHASE_VALUES == ("GPP", "SPP", "TAPER")



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

def test_calculate_phase_weeks_keeps_taper_for_16_day_camps():
    phases = calculate_phase_weeks(6, "boxing", days_until_fight=16)

    assert phases["GPP"] == 0
    assert phases["SPP"] == 1
    assert phases["TAPER"] == 1
    assert phases["days"]["TAPER"] > 0
    assert sum(phases["days"].values()) == 16


def test_calculate_phase_weeks_keeps_taper_for_18_day_camps():
    phases = calculate_phase_weeks(6, "boxing", days_until_fight=18)

    assert phases["TAPER"] == 1
    assert phases["days"]["TAPER"] > 0
    assert sum(phases["days"].values()) == 18


def test_calculate_phase_weeks_keeps_taper_for_16_day_pressure_fighter():
    phases = calculate_phase_weeks(6, "boxing", style="pressure fighter", days_until_fight=16)

    assert phases["TAPER"] == 1
    assert phases["SPP"] == 1
    assert phases["days"]["TAPER"] > 0


def test_calculate_phase_weeks_keeps_taper_for_16_day_grappler():
    phases = calculate_phase_weeks(6, "boxing", style="grappler", days_until_fight=16)

    assert phases["TAPER"] == 1
    assert phases["days"]["TAPER"] > 0


def test_calculate_phase_weeks_treats_21_days_as_short_notice_boundary():
    at_boundary = calculate_phase_weeks(6, "boxing", days_until_fight=21)
    above_boundary = calculate_phase_weeks(6, "boxing", days_until_fight=22)

    assert at_boundary["GPP"] == 0
    assert above_boundary["GPP"] >= 1
    assert at_boundary["TAPER"] >= 1
    assert above_boundary["TAPER"] >= 1


def test_calculate_phase_weeks_under_7_days_forces_taper_phase():
    phases = calculate_phase_weeks(6, "boxing", days_until_fight=6)

    assert phases["GPP"] == 0
    assert phases["SPP"] == 0
    assert phases["TAPER"] == 1
    assert phases["days"]["TAPER"] == 6
    assert sum(phases["days"].values()) == 6
