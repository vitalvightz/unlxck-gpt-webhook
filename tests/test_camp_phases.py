from fightcamp.camp_phases import _effective_phase_block_count, calculate_phase_weeks
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


def test_calculate_phase_weeks_uses_compressed_spp_and_taper_at_8_days():
    phases = calculate_phase_weeks(6, "boxing", days_until_fight=8)

    assert phases["GPP"] == 0
    assert phases["SPP"] >= 1
    assert phases["TAPER"] >= 1
    assert not (phases["SPP"] == 1 and phases["TAPER"] == 0)
    assert sum(phases["days"].values()) == 8


def test_calculate_phase_weeks_uses_compressed_spp_and_taper_at_10_days():
    phases = calculate_phase_weeks(6, "boxing", days_until_fight=10)

    assert phases["GPP"] == 0
    assert phases["SPP"] >= 1
    assert phases["TAPER"] >= 1
    assert not (phases["SPP"] == 1 and phases["TAPER"] == 0)
    assert sum(phases["days"].values()) == 10


def test_calculate_phase_weeks_uses_compressed_spp_and_taper_at_13_days():
    phases = calculate_phase_weeks(6, "boxing", days_until_fight=13)

    assert phases["GPP"] == 0
    assert phases["SPP"] >= 1
    assert phases["TAPER"] >= 1
    assert sum(phases["days"].values()) == 13


def test_calculate_phase_weeks_keeps_14_days_on_normal_short_notice_logic():
    phases = calculate_phase_weeks(6, "boxing", days_until_fight=14)

    assert phases["GPP"] == 0
    assert phases["SPP"] == 1
    assert phases["TAPER"] == 1
    assert sum(phases["days"].values()) == 14


def test_calculate_phase_weeks_keeps_current_characterized_outputs_for_representative_cases():
    cases = [
        (
            "boxing base 8 weeks",
            dict(camp_length=8, sport="boxing"),
            {"GPP": 3, "SPP": 3, "TAPER": 2, "days": {"GPP": 21, "SPP": 21, "TAPER": 14}},
        ),
        (
            "boxing pro low fatigue 8 weeks",
            dict(
                camp_length=8,
                sport="boxing",
                status="professional",
                fatigue="low",
                mental_block=["generic"],
            ),
            {"GPP": 2, "SPP": 4, "TAPER": 2, "days": {"GPP": 14, "SPP": 28, "TAPER": 14}},
        ),
        (
            "pressure fighter 8 weeks",
            dict(camp_length=8, sport="boxing", style="pressure fighter"),
            {"GPP": 3, "SPP": 4, "TAPER": 1, "days": {"GPP": 21, "SPP": 28, "TAPER": 7}},
        ),
        (
            "grappler mma 8 weeks",
            dict(camp_length=8, sport="mma", style="grappler"),
            {"GPP": 4, "SPP": 3, "TAPER": 1, "days": {"GPP": 28, "SPP": 21, "TAPER": 7}},
        ),
        (
            "22 day boundary",
            dict(camp_length=6, sport="boxing", days_until_fight=22),
            {"GPP": 1, "SPP": 1, "TAPER": 1, "days": {"GPP": 7, "SPP": 8, "TAPER": 7}},
        ),
        (
            "21 day boundary",
            dict(camp_length=6, sport="boxing", days_until_fight=21),
            {"GPP": 0, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 14, "TAPER": 7}},
        ),
    ]

    for _, kwargs, expected in cases:
        assert calculate_phase_weeks(**kwargs) == expected


def test_calculate_phase_weeks_preserves_basic_invariants_across_style_matrix():
    cases = [
        dict(camp_length=8, sport="boxing"),
        dict(camp_length=8, sport="boxing", style="pressure fighter"),
        dict(camp_length=8, sport="mma", style="grappler"),
        dict(camp_length=6, sport="boxing", style="counter striker"),
        dict(camp_length=6, sport="mma", style="wrestler"),
        dict(camp_length=5, sport="boxing", status="professional", fatigue="low", mental_block=["generic"]),
        dict(camp_length=6, sport="boxing", days_until_fight=22),
        dict(camp_length=6, sport="boxing", days_until_fight=21),
    ]

    for kwargs in cases:
        phases = calculate_phase_weeks(**kwargs)
        total_days = kwargs["days_until_fight"] if isinstance(kwargs.get("days_until_fight"), int) and kwargs.get("days_until_fight") >= 0 else kwargs["camp_length"] * 7
        normalized_weeks = _effective_phase_block_count(total_days)

        assert phases["GPP"] >= 0
        assert phases["SPP"] >= 0
        assert phases["TAPER"] >= 0
        assert phases["GPP"] + phases["SPP"] + phases["TAPER"] == normalized_weeks
        assert sum(phases["days"].values()) == total_days
