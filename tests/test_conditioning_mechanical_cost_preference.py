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
    _conditioning_mechanical_cost_is_high,
    _conditioning_verified_interval_dose,
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


# --- Dose units are verified, never assumed ---------------------------------


def test_seconds_and_minutes_prescriptions_are_verified():
    assert _conditioning_verified_interval_dose(BANK["Agility Ladder Sprints"]) == (15.0, 45.0, 10.0)
    assert _conditioning_verified_interval_dose(BANK["Plyo Step-Up Intervals"]) == (30.0, 90.0, 6.0)
    # minutes are converted, not rejected
    assert _conditioning_verified_interval_dose(BANK["Echo Bike Tempo Intervals"]) == (180.0, 120.0, 4.0)


@pytest.mark.parametrize(
    "name",
    ["Mixed Stroke Tempo Set", "Swim Intervals (Freestyle)", "Depth Jump to Sprint"],
)
def test_distance_and_rep_encoded_work_is_refused(name):
    # work_sec holds metres or a rep count in these entries. Reading it as
    # seconds would report e.g. 4x200m as 800 seconds of active work.
    assert _conditioning_verified_interval_dose(BANK[name]) is None


def test_numbers_must_agree_with_the_written_prescription():
    drill = dict(BANK["Agility Ladder Sprints"])
    drill["work_sec"] = 60  # contradicts "10x15s on/45s off"
    assert _conditioning_verified_interval_dose(drill) is None


def test_total_minutes_is_never_read_as_active_work():
    # total_minutes is full elapsed time under the dose contract, so it
    # includes rest and cannot stand in for active work.
    assert _conditioning_verified_interval_dose({"total_minutes": 18.0, "rest_sec": 60, "rounds": 4}) is None


# --- The promotion refuses anything it cannot establish ---------------------


def _entry(name: str, reasons: dict | None = None):
    return (BANK[name], 0.0, reasons or {})


def test_promotion_swaps_an_identical_prescription_for_a_cheaper_one():
    # Both are 10 x 15 sec with 45 sec rest; the candidate's RPE is not lower.
    pool = [_entry("Agility Ladder Sprints"), _entry("Shadowboxing Power Bursts")]
    assert _promote_lower_cost_conditioning_head(pool) is True
    assert pool[0][0]["name"] == "Shadowboxing Power Bursts"


def test_promotion_refuses_a_different_interval_structure():
    # Equal active seconds are not equal stimulus: a 6 x 30 sec hinge interval
    # is not interchangeable with a 10 x 15 sec sprint interval.
    pool = [_entry("Agility Ladder Sprints"), _entry("KB Swing Intervals")]
    assert _promote_lower_cost_conditioning_head(pool) is False
    assert pool[0][0]["name"] == "Agility Ladder Sprints"


def test_promotion_refuses_a_lower_intensity_candidate():
    softer = dict(BANK["Shadowboxing Power Bursts"])
    softer["rpe"] = 5  # head is rpe 8
    pool = [_entry("Agility Ladder Sprints"), (softer, 0.0, {})]
    assert _promote_lower_cost_conditioning_head(pool) is False


def test_promotion_refuses_fewer_rounds():
    shorter = dict(BANK["Shadowboxing Power Bursts"])
    shorter["rounds"] = 6
    shorter["duration"] = "6x15s on/45s off"
    pool = [_entry("Agility Ladder Sprints"), (shorter, 0.0, {})]
    assert _promote_lower_cost_conditioning_head(pool) is False


def test_promotion_never_displaces_an_explicitly_requested_exercise():
    # A named exercise is a coach instruction, not a style default.
    pool = [
        _entry("Agility Ladder Sprints", {"preferred_exercise_name_match": 3.0}),
        _entry("Shadowboxing Power Bursts"),
    ]
    assert _promote_lower_cost_conditioning_head(pool) is False
    assert pool[0][0]["name"] == "Agility Ladder Sprints"


def test_promotion_leaves_an_already_low_cost_head_alone():
    pool = [_entry("KB Swing Intervals"), _entry("Agility Ladder Sprints")]
    assert _promote_lower_cost_conditioning_head(pool) is False


def test_promotion_is_a_no_op_without_an_alternative():
    assert _promote_lower_cost_conditioning_head([_entry("Agility Ladder Sprints")]) is False


# --- The delivered dose cannot shrink ---------------------------------------


def test_matching_work_and_rest_keeps_the_partitioner_allocation_safe():
    """The Stage-2 partitioner allocates rounds round-robin against a shared
    budget, so a larger ceiling alone does NOT guarantee a larger allocation.
    Requiring identical work and rest makes the two drills interchangeable to
    that algorithm, which is what makes equal-or-more rounds safe.
    """

    def partition(drills, target, cap):
        alloc = {n: 1 for n, _, _, _ in drills}
        active = sum(w for _, w, _, _ in drills)
        elapsed = active
        while True:
            progressed = False
            for n, w, r, mx in drills:
                if alloc[n] >= mx or active + w > target or elapsed + w + r > cap:
                    continue
                alloc[n] += 1
                active += w
                elapsed += w + r
                progressed = True
            if not progressed:
                break
        return {n: alloc[n] * w for n, w, _, _ in drills}

    others = [("otherA", 120, 60, 1), ("otherB", 120, 60, 1)]
    # Different structure, equal 200s ceilings: the allocation DOES shrink,
    # which is precisely why that comparison is refused above.
    assert partition([("c", 20, 60, 10)] + others, 360.0, 1800.0)["c"] == 120
    assert partition([("c", 100, 60, 2)] + others, 360.0, 1800.0)["c"] == 100

    # Identical work and rest, more rounds: never delivers less.
    for rounds in range(2, 11):
        base = partition([("c", 15, 45, 2)] + others, 360.0, 1800.0)["c"]
        more = partition([("c", 15, 45, rounds)] + others, 360.0, 1800.0)["c"]
        assert more >= base


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
