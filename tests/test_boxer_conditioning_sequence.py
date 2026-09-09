"""The limiter's system order outranks the boxer style preference.

`_preferred_boxer_conditioning_sequence` prepended a boxer preference onto the
limiter's conditioning sequence, overriding it. In GPP that preference ranks
alactic above glycolytic, so a boxer with only two conditioning slots lost the
fight-pace exposure their own conditioning limiter had placed second and got an
alactic day instead - the 0.2 phase-ratio system displacing the 0.3 system with
no safety or contact reason behind it.

The preference now only orders systems the limiter did not rank.
"""
from fightcamp.stage2_role_map import _preferred_boxer_conditioning_sequence as sequence


def test_conditioning_limiter_keeps_fight_pace_ahead_of_sharpness():
    # aerobic_repeatability / general_fight_readiness order for GPP.
    assert sequence("GPP", ["aerobic", "glycolytic", "alactic"]) == [
        "aerobic", "glycolytic", "alactic",
    ]


def test_sharpness_limiter_that_ranks_alactic_first_is_left_alone():
    """The preference is only overruled where it inverts the phase ratios."""
    assert sequence("GPP", ["alactic", "aerobic", "glycolytic"]) == [
        "aerobic", "alactic", "glycolytic",
    ]


def test_spp_still_leads_with_aerobic_for_boxers():
    """SPP's preference already ranks glycolytic second, so it is untouched."""
    assert sequence("SPP", ["glycolytic", "alactic", "aerobic"]) == [
        "aerobic", "glycolytic", "alactic",
    ]


def test_boxer_preference_still_applies_when_the_limiter_ranks_neither():
    assert sequence("GPP", ["aerobic"]) == ["aerobic", "alactic", "glycolytic"]
    assert sequence("SPP", ["aerobic"]) == ["aerobic", "glycolytic", "alactic"]


def test_no_limiter_order_falls_back_to_the_boxer_preference():
    assert sequence("GPP", []) == ["aerobic", "alactic", "glycolytic"]
    assert sequence("SPP", None) == ["aerobic", "glycolytic", "alactic"]
    assert sequence("TAPER", []) == ["alactic", "aerobic", "glycolytic"]


def test_every_system_survives_and_none_is_duplicated():
    for limiter in (
        ["aerobic", "glycolytic", "alactic"],
        ["glycolytic", "alactic", "aerobic"],
        ["alactic"],
        [],
    ):
        for phase in ("GPP", "SPP", "TAPER"):
            result = sequence(phase, limiter)
            assert len(result) == len(set(result))
            assert set(result) == {"aerobic", "glycolytic", "alactic"}


def test_first_two_slots_of_a_conditioning_limiter_are_aerobic_then_fight_pace():
    """Two conditioning slots must not spend one on the lowest-ratio system."""
    assert sequence("GPP", ["aerobic", "glycolytic", "alactic"])[:2] == [
        "aerobic", "glycolytic",
    ]
