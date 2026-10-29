"""A pre-taper week cut by the D-14 cutoff must not become its own obligation.

Regression: Haris Aftab Ahmad's 28 November 2026 camp (D-30). Its programme
weeks run D-30..D-23, D-22..D-15, D-14..D-8 (SPP) and a D-7..D-0 taper. Only
D-14 of the third week sits at or above the development cutoff, and the weekly
path turned that single day into an isolated D-14..D-14 build window. Power
(D-24, D-17) and conditioning (D-30, D-16) were real, development-quality and
recurring, yet both goals failed for the one-day sliver.

The athlete's 6 x 3 min "Boxing Punishment Drill" is a bank 6 x 2 min (12 min)
round-based drill re-anchored to their 3-minute rounds; its evidence must state
the 18 minutes actually prescribed.
"""
from contextvars import copy_context

import pytest

from fightcamp.goal_preservation import _coverage, _other_stimuli, _requirements
from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.session_composition import conditioning_assignment_from_slot

HARIS_WEEKS = [("GPP", 30, 23), ("SPP", 22, 15), ("SPP", 14, 8), ("TAPER", 7, 0)]


def _brief(weeks=HARIS_WEEKS, days=30):
    return {
        "athlete_snapshot": {"days_until_fight": days},
        "weekly_role_map": {"weeks": [
            {"week_index": index, "phase": phase, "session_roles": [],
             "calendar_days": [{"d_day": d, "is_fight_day": d == 0} for d in range(high, low - 1, -1)]}
            for index, (phase, high, low) in enumerate(weeks, 1)
        ]},
    }


def _windows(goal, brief, state="build"):
    entry = {"goal": goal, "state": state}
    return [(w["min_d_day"], w["max_d_day"]) for w in _requirements(entry, brief)]


def _evidence(intent, *days):
    return [{"d_day": day, "intents": [intent], "development_quality": True} for day in days]


def _missing(goal, intent, brief, evidence):
    entry = {"goal": goal, "state": "build", "required_intent": intent}
    return [(w["min_d_day"], w["max_d_day"]) for w in _coverage(entry, brief, evidence)[1]]


@pytest.mark.parametrize("goal", ["power", "conditioning"])
def test_haris_boundary_fragment_merges_into_adjacent_week(goal):
    # Before: [(23, 30), (15, 22), (14, 14)].
    assert _windows(goal, _brief()) == [(23, 30), (14, 22)]


def test_haris_power_and_conditioning_receive_credit_for_real_exposures():
    brief = _brief()
    assert _missing("power", "ballistic_power", brief, _evidence("ballistic_power", 24, 17)) == []
    assert _missing("conditioning", "energy_system_training", brief,
                    _evidence("energy_system_training", 30, 16)) == []


def test_haris_missing_second_week_still_fails():
    brief = _brief()
    # One opening-week exposure cannot discharge the next development week.
    assert _missing("power", "ballistic_power", brief, _evidence("ballistic_power", 24)) == [(14, 22)]
    assert _missing("conditioning", "energy_system_training", brief,
                    _evidence("energy_system_training", 30)) == [(14, 22)]
    # Two exposures inside one week do not pay for the other.
    assert _missing("power", "ballistic_power", brief, _evidence("ballistic_power", 17, 15)) == [(23, 30)]


def test_haris_taper_and_maintenance_exposures_earn_no_build_credit():
    brief = _brief()
    late = _evidence("ballistic_power", 24) + _evidence("ballistic_power", 13, 10)
    assert _missing("power", "ballistic_power", brief, late) == [(14, 22)]
    weak = _evidence("ballistic_power", 24) + [
        {"d_day": 17, "intents": ["ballistic_power"], "development_quality": False}]
    assert _missing("power", "ballistic_power", brief, weak) == [(14, 22)]


def test_majority_eligible_straddling_week_keeps_its_own_requirement():
    # D-19..D-13 has six eligible days: a real development week, not a sliver.
    brief = _brief([("GPP", 26, 20), ("SPP", 19, 13), ("TAPER", 12, 0)], days=26)
    assert _windows("power", brief) == [(20, 26), (14, 19)]
    assert _missing("power", "ballistic_power", brief, _evidence("ballistic_power", 22)) == [(14, 19)]


def test_full_eligible_weeks_are_unchanged():
    brief = _brief([("GPP", 29, 22), ("SPP", 21, 14), ("SPP", 13, 7), ("TAPER", 6, 0)], days=29)
    assert _windows("power", brief) == [(22, 29), (14, 21)]


def test_lone_fragment_is_not_dropped():
    # With no adjacent eligible week the fragment remains the requirement; the
    # goal is never marked satisfied by default.
    brief = _brief([("SPP", 15, 9), ("TAPER", 8, 0)], days=15)
    assert _windows("power", brief) == [(14, 15)]
    assert _missing("power", "ballistic_power", brief, []) == [(14, 15)]


_PUNISHMENT = {
    "name": "Boxing Punishment Drill (Bad Position Rounds)",
    "prescription": "6x2min (start each round fatigued)",
    "selection_metadata": {
        "system": "glycolytic", "duration": "6x2min (start each round fatigued)",
        "tags": ["boxing", "conditioning", "glycolytic", "work_capacity"],
        "work_sec": 120, "rounds": 6, "total_minutes": 12, "rpe": 6, "round_based": True,
    },
}


def _conditioning_stimulus(round_minutes=3, rounds=None):
    slot = {"slot_id": "glycolytic_1", "role": "glycolytic", "selected": _PUNISHMENT}
    context = copy_context()
    context.run(planner_athlete_model_context.set, {"rounds_format": f"6x{round_minutes}"})
    member = context.run(conditioning_assignment_from_slot, "SPP", slot, _PUNISHMENT, allocated_rounds=rounds)
    role = {"role_key": "conditioning_day", "category": "conditioning", "preferred_system": "glycolytic",
            "scheduled_countdown_label": "D-16", "selected_exercise_assignments": [member]}
    pools = {"SPP": {"conditioning_slots": [slot]}}
    return member, _other_stimuli(role, pools, "SPP", {"restrictions": []})


def test_round_based_drill_records_effective_18_minutes_not_bank_12():
    member, stimuli = _conditioning_stimulus()
    stimulus = next(s for s in stimuli if s["name"] == _PUNISHMENT["name"])
    assert (stimulus["work_sec"], stimulus["rounds"]) == (180, 6)
    assert stimulus["total_minutes"] == 18
    assert "energy_system_training" in stimulus["intents"]
    # The athlete's prescription is reported, never rewritten by the measurement.
    assert stimulus["effective_prescription"] == member["effective_prescription"]
    assert _PUNISHMENT["selection_metadata"]["total_minutes"] == 12


def test_bank_dose_keeps_its_authored_total_when_not_reanchored():
    _, stimuli = _conditioning_stimulus(round_minutes=2)
    stimulus = next(s for s in stimuli if s["name"] == _PUNISHMENT["name"])
    assert (stimulus["work_sec"], stimulus["rounds"], stimulus["total_minutes"]) == (120, 6, 12)


def test_partitioned_rounds_shrink_the_recorded_total():
    # Composition may allocate fewer rounds; the total follows them, so a
    # reduced dose is never reported at the bank's larger figure.
    _, stimuli = _conditioning_stimulus(rounds=2)
    stimulus = next(s for s in stimuli if s["name"] == _PUNISHMENT["name"])
    assert (stimulus["work_sec"], stimulus["rounds"], stimulus["total_minutes"]) == (180, 2, 6)


def _power_evidence(day):
    from selector_assignments import apply_with_selected_membership
    from fightcamp.goal_preservation import collect_goal_evidence
    from test_goal_preservation import _brief as _strength_brief, _role, _slot

    slots = [_slot(name, "anchor_power", prescription=dose, tags=["explosive", "mech_ballistic"])
             for name, dose in (("Medicine Ball Rotational Slam", "4 x 4 explosive throws, full rest"),
                                ("Trap Bar Jump", "4 x 3 @ RPE 8"))]
    brief = _strength_brief(days=30, roles=[_role(day)], slots=slots)
    apply_with_selected_membership(weekly_role_map=brief["weekly_role_map"],
                                   candidate_pools=brief["candidate_pools"], athlete_model=brief["athlete_snapshot"])
    return {e["name"]: e for e in collect_goal_evidence(brief) if "ballistic_power" in e["intents"]}


def test_medicine_ball_and_ballistic_prescriptions_earn_development_power_credit():
    evidence = _power_evidence(24)
    assert set(evidence) == {"Medicine Ball Rotational Slam", "Trap Bar Jump"}
    assert all(e["development_quality"] for e in evidence.values())
    assert (evidence["Medicine Ball Rotational Slam"]["sets"], evidence["Medicine Ball Rotational Slam"]["reps"]) == (4, 4)


def test_same_power_work_inside_the_fight_tail_is_not_development_credit():
    assert not any(e["development_quality"] for e in _power_evidence(10).values())


def test_short_week_majority_is_judged_against_its_own_length():
    # A five-day week with three eligible days is a majority of that week and
    # keeps its own recurring requirement.
    brief = _brief([("GPP", 23, 17), ("SPP", 16, 12), ("TAPER", 11, 0)], days=23)
    assert _windows("power", brief) == [(17, 23), (14, 16)]
    assert _missing("power", "ballistic_power", brief, _evidence("ballistic_power", 20)) == [(14, 16)]
