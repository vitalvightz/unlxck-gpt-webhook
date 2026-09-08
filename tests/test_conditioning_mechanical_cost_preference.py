"""Mechanical cost decides a conditioning slot at equal-or-better dose.

A drill's recovery cost (``impact_cost`` / landing-impact ``mech_*`` tags) and
its prescribed dose (``work_sec`` x ``rounds``, or a steady-state
``total_minutes``) are both already recorded in the banks. Nothing consulted
them when ordering a conditioning slot, so the highest-scoring candidate won
even when a lower-cost drill in the same system delivered at least as much
active work.

The rule is deliberately narrow: it fires only for a declared conditioning
objective, only in the aerobic and glycolytic systems, and never trades a
smaller dose for a cheaper one. High-impact work stays first choice for a power
athlete, and stays untouched in an alactic slot where landing impact is the
training stimulus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fightcamp import conditioning
from fightcamp.conditioning import (
    _conditioning_active_work_seconds,
    _conditioning_mechanical_cost_is_high,
    _promote_lower_cost_conditioning_head,
)


def _bank() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for name in ("conditioning_bank.json", "style_conditioning_bank.json"):
        for entry in json.loads(Path(f"data/{name}").read_text(encoding="utf-8")):
            entries[entry["name"]] = entry
    return entries


BANK = _bank()


def _flags(phase: str, **over) -> dict:
    flags = {
        "phase": phase,
        "sport": "boxing",
        "style_technical": ["boxing"],
        "style_tactical": ["Counter Striker"],
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "fatigue": "low",
        "equipment": ["heavy_bag", "assault_bike", "rower", "kettlebells", "box"],
        "training_frequency": 4,
        "days_available": 4,
        "days_until_fight": 35,
        "time_to_fight_days": 35,
        "injuries": [],
        "restrictions": [],
    }
    flags.update(over)
    return flags


# --- The cost signal itself -------------------------------------------------


def test_landing_impact_counts_even_when_impact_cost_is_low():
    # "Plyo Step-Up Intervals" records impact_cost=low but carries
    # mech_landing_impact: repeated step-down landings are a real recovery cost.
    drill = BANK["Plyo Step-Up Intervals"]
    assert drill["impact_cost"] == "low"
    assert "mech_landing_impact" in drill["tags"]
    assert _conditioning_mechanical_cost_is_high(drill) is True


def test_hinge_and_machine_intervals_are_not_high_cost():
    assert _conditioning_mechanical_cost_is_high(BANK["KB Swing Intervals"]) is False
    assert _conditioning_mechanical_cost_is_high(BANK["Echo Bike Tempo Intervals"]) is False
    assert _conditioning_mechanical_cost_is_high(BANK["Agility Ladder Sprints"]) is True
    assert _conditioning_mechanical_cost_is_high(BANK["Burpee Broad Jumps"]) is True


def test_active_work_reads_intervals_and_steady_state():
    assert _conditioning_active_work_seconds(BANK["Agility Ladder Sprints"]) == 150.0  # 10 x 15s
    assert _conditioning_active_work_seconds(BANK["KB Swing Intervals"]) == 180.0  # 6 x 30s
    steady = {"total_minutes": 30}
    assert _conditioning_active_work_seconds(steady) == 1800.0
    assert _conditioning_active_work_seconds({}) is None


# --- The promotion never trades down on dose --------------------------------


def _entry(name: str):
    return (BANK[name], 0.0, {})


def test_promotion_prefers_a_cheaper_candidate_at_equal_dose():
    pool = [_entry("Agility Ladder Sprints"), _entry("Shadowboxing Power Bursts")]
    assert _promote_lower_cost_conditioning_head(pool) is True
    assert pool[0][0]["name"] == "Shadowboxing Power Bursts"


def test_promotion_refuses_a_cheaper_candidate_with_a_smaller_dose():
    # Burpee Broad Jumps is 120s active; a cheaper option must still deliver
    # at least the head's active work to take the slot.
    smaller = ({"name": "Tiny Low Cost", "impact_cost": "low", "tags": [], "work_sec": 10, "rounds": 2}, 0.0, {})
    pool = [_entry("Agility Ladder Sprints"), smaller]
    assert _promote_lower_cost_conditioning_head(pool) is False
    assert pool[0][0]["name"] == "Agility Ladder Sprints"


def test_promotion_leaves_an_already_low_cost_head_alone():
    pool = [_entry("KB Swing Intervals"), _entry("Agility Ladder Sprints")]
    assert _promote_lower_cost_conditioning_head(pool) is False
    assert pool[0][0]["name"] == "KB Swing Intervals"


def test_promotion_is_a_no_op_without_an_alternative():
    pool = [_entry("Agility Ladder Sprints")]
    assert _promote_lower_cost_conditioning_head(pool) is False


# --- End to end -------------------------------------------------------------


def _winner(result, system: str) -> str | None:
    drills = result[3].get(system) or []
    return str(drills[0]["name"]) if drills else None


@pytest.mark.parametrize("phase", ["GPP", "SPP"])
def test_conditioning_objective_gets_a_low_cost_glycolytic_slot(phase):
    result = conditioning.generate_conditioning_block(_flags(phase))
    winner = _winner(result, "glycolytic")
    if winner is None:
        pytest.skip(f"no glycolytic slot resolved for {phase}")
    assert _conditioning_mechanical_cost_is_high(BANK[winner]) is False, winner


def test_power_athlete_keeps_high_impact_conditioning():
    # The preference must not become a blanket ban: plyometric and
    # change-of-direction work is the point for a power/coordination athlete.
    gas = conditioning.generate_conditioning_block(_flags("GPP"))
    power = conditioning.generate_conditioning_block(
        _flags("GPP", key_goals=["power", "speed"], weaknesses=["coordination", "speed"])
    )
    assert _winner(gas, "glycolytic") != _winner(power, "glycolytic")
    assert _conditioning_mechanical_cost_is_high(BANK[_winner(power, "glycolytic")]) is True


def test_alactic_slot_is_untouched_for_a_conditioning_athlete():
    # Landing impact is the stimulus in an alactic slot, not a cost to avoid.
    result = conditioning.generate_conditioning_block(_flags("GPP"))
    winner = _winner(result, "alactic")
    if winner is None:
        pytest.skip("no alactic slot resolved")
    assert _conditioning_mechanical_cost_is_high(BANK[winner]) is True
