import pytest

from fightcamp.combat_load_policy import (
    DayOccupancy,
    LoadClass,
    contact_load_profile,
    role_load_profile,
)


def test_invalid_nonempty_canonical_stamps_fail_loudly():
    with pytest.raises(ValueError):
        role_load_profile(
            {
                "role_key": "tactical_watch",
                "calendar_load_class": "not_a_real_load",
            }
        )

    with pytest.raises(ValueError):
        role_load_profile(
            {
                "role_key": "future_unknown_role",
                "calendar_load_class": "low_load_aerobic",
                "calendar_day_occupancy": "not_an_occupancy",
            }
        )

    with pytest.raises(ValueError):
        contact_load_profile(
            {
                "effective_load": "hard",
                "calendar_day_occupancy": "not_an_occupancy",
            }
        )


def test_known_late_fight_role_keys_keep_semantics_even_without_redundant_category():
    strength = role_load_profile({"role_key": "strength_touch_day"})
    primer = role_load_profile({"role_key": "neural_primer_day"})
    alactic = role_load_profile(
        {
            "role_key": "alactic_sharpness_day",
            "stress_class": "meaningful_stress",
            "cost_class": "medium",
        }
    )

    assert strength.load_class is LoadClass.MEANINGFUL_STRENGTH
    assert strength.occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL
    assert primer.load_class is LoadClass.MEANINGFUL_STRENGTH
    assert primer.occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL
    assert alactic.load_class is LoadClass.MEANINGFUL_CONDITIONING
    assert alactic.occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL


def test_matching_stamp_does_not_downgrade_known_exclusive_occupancy():
    profile = role_load_profile(
        {
            "role_key": "strength_touch_day",
            "calendar_load_class": "meaningful_strength",
        }
    )
    assert profile.load_class is LoadClass.MEANINGFUL_STRENGTH
    assert profile.occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL


def test_known_role_stamp_cannot_redefine_load_or_occupancy():
    with pytest.raises(ValueError):
        role_load_profile(
            {
                "role_key": "strength_touch_day",
                "calendar_load_class": "low_load_physical",
            }
        )

    with pytest.raises(ValueError):
        role_load_profile(
            {
                "role_key": "strength_touch_day",
                "calendar_load_class": "meaningful_strength",
                "calendar_day_occupancy": "physical",
            }
        )
