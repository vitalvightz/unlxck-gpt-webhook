from __future__ import annotations

import pytest

from fightcamp import conditioning


NEW_DRILLS = {
    "Thai Ring-Cut Pressure Walkdown",
    "Long-Guard Clinch Entry Step",
    "Shot-Line Circle-Off Reset",
    "Kick-Recovery Anti-Shot Rebase",
    "Fence Exit to Center Rebase",
    "Wrestling Stance-Motion Circle Reset",
    "Standing Guard-Pass Base Circle",
}


def _flags(*, sport: str, style: str, phase: str = "SPP", days: int = 21) -> dict:
    return {
        "phase": phase,
        "fatigue": "low",
        "sport": sport,
        "fight_format": sport,
        "style_tactical": [style],
        "style_technical": [sport],
        "equipment": ["bodyweight"],
        "training_days": ["Mon"],
        "training_frequency": 1,
        "days_available": 1,
        "key_goals": ["footwork"],
        "weaknesses": [],
        "injuries": [],
        "days_until_fight": days,
        "time_to_fight_days": days,
        "stance": "orthodox",
    }


def test_research_expansion_adds_exactly_the_expected_new_patterns():
    names = {drill["name"] for drill in conditioning.get_technical_footwork_bank()}
    assert NEW_DRILLS <= names


@pytest.mark.parametrize(
    ("sport", "style", "expected", "required_function"),
    [
        ("muay_thai", "pressure_fighter", "Thai Ring-Cut Pressure Walkdown", "ring_cutting"),
        ("muay_thai", "clinch_fighter", "Long-Guard Clinch Entry Step", "clinch_management"),
        ("mma", "counter_striker", "Fence Exit to Center Rebase", "defensive_exit"),
        ("mma", "kicker", "Kick-Recovery Anti-Shot Rebase", "kick_recovery"),
    ],
)
def test_new_patterns_fill_real_style_function_gaps(
    sport: str, style: str, expected: str, required_function: str
):
    selected = conditioning.select_technical_footwork_drill(
        _flags(sport=sport, style=style), set(), []
    )

    assert selected is not None
    assert selected["name"] == expected
    assert required_function in selected["tactical_function"]


def test_mma_defensive_exits_cover_fence_and_open_space_without_dead_bank_content():
    flags = _flags(sport="mma", style="counter_striker")
    candidates = conditioning.select_technical_footwork_candidates(flags, set(), [])
    by_name = {drill["name"]: drill for drill in candidates}

    fence = by_name["Fence Exit to Center Rebase"]
    shot_line = by_name["Shot-Line Circle-Off Reset"]
    assert "cage_control" in fence["tactical_function"]
    assert "takedown_defense" in shot_line["tactical_function"]
    assert "mma" in fence["tags"] and "mma" in shot_line["tags"]

    # The boundary-specific exit wins the deterministic tie first; after it is
    # already used, the open-space shot-line exit becomes the next personalised
    # choice instead of sitting unreachable in the bank.
    next_choice = conditioning.select_technical_footwork_drill(
        flags, {"Fence Exit to Center Rebase"}, []
    )
    assert next_choice is not None
    assert next_choice["name"] == "Shot-Line Circle-Off Reset"


def test_wrestling_gets_a_low_cost_taper_stance_motion_pattern():
    selected = conditioning.select_technical_footwork_drill(
        _flags(sport="wrestling", style="wrestler", phase="TAPER", days=4), set(), []
    )

    assert selected is not None
    assert selected["name"] == "Wrestling Stance-Motion Circle Reset"
    assert selected["movement_cost"] == "low"
    assert "d4_to_d2" in selected["late_windows"]


def test_bjj_gets_a_genuine_standing_taper_pattern_without_mma_cross_fill():
    selected = conditioning.select_technical_footwork_drill(
        _flags(sport="bjj", style="grappler", phase="TAPER", days=4), set(), []
    )

    assert selected is not None
    assert selected["name"] == "Standing Guard-Pass Base Circle"
    assert "bjj" in selected["tags"]
    assert "mma" not in selected["tags"]
    assert "d4_to_d2" in selected["late_windows"]


def test_new_drills_keep_existing_technical_footwork_safety_contract():
    bank = {
        drill["name"]: drill
        for drill in conditioning.get_technical_footwork_bank()
        if drill["name"] in NEW_DRILLS
    }
    assert set(bank) == NEW_DRILLS

    for drill in bank.values():
        assert drill["modality"] == "technical_footwork"
        assert drill["system"] == "aerobic"
        assert drill["impact_cost"] == "low"
        assert drill["lactate_load"] == "low"
        assert drill["movement_cost"] in {"low", "moderate"}
        assert drill["rpe"] <= 5
        assert "mech_lower_limb_weight_bearing" in drill["mechanical_risk_tags"]
        assert drill["late_windows"]
