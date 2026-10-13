"""Load-aware late-fight primer composition.

A countdown neural / speed / power session (``strength_touch_day``,
``neural_primer_day``, ``alactic_sharpness_day``) is composed from Stage 1's
legal candidates, up to three exercises:

* meaningful Stage 1 work leads; a support-only Style Taper primer complements
  it and never displaces it merely because it was the preferred fallback;
* each further member adds a different stimulus, the session carries at most one
  loaded lift, and complements are a single set / round;
* the combined session is measured with ``realised_session_stress`` and may not
  rise above the role's planned vector (or the lead-only session), nor make its
  cross-day legality worse than the lead alone.
"""
from __future__ import annotations

import pytest

from fightcamp.late_camp_role_morph import late_fight_strength_dose_cap
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.session_composition import attach_late_fight_assignments, realised_role_stress
from fightcamp.stage2_payload import (
    LATE_PRIMER_MAX_MEMBERS,
    _build_late_fight_allowed_exercises_by_day,
)


def _strength(name, quality="anchor_power", tags=("mech_ballistic", "mech_lower_jump"),
              prescription="4x3 reps at max speed; full rest 120s", index=0):
    selected = {
        "name": name, "quality_class": quality, "anchor_capable": True,
        "prescription": prescription, "mechanical_risk_tags": list(tags),
    }
    return {"slot_id": f"spp_strength_{index}_{name.lower().replace(' ', '_')}", "session_index": 1,
            "priority": index, "quality_class": quality, "anchor_capable": True, "selected": selected}


def _primer(name, family="pure_neural", tags=("mech_acceleration", "mech_upper_press"), index=0,
            prescription="2x5s with 120s rest"):
    metadata = {"support_only": True, "meaningful_stress": False, "lactate_load": "low",
                "primer_family": family, "mechanical_risk_tags": list(tags), "system": "alactic",
                "late_windows": ["all"]}
    return {"slot_id": f"spp_primer_{index}_{name.lower().replace(' ', '_')}", "role": "alactic",
            "selected": {"name": name, "source": "style_taper", "system": "alactic",
                         "prescription": prescription, "support_only": True,
                         "relevance": {"style_hits": 1, "goal_hits": 1}, "bank_order": index,
                         "selection_metadata": metadata}}


def _role(key="strength_touch_day", d_day=10, **extra):
    cap = late_fight_strength_dose_cap(d_day)
    return {"role_key": key, "category": "strength", "scheduled_countdown_label": f"D-{d_day}",
            "countdown_offset": d_day, "strength_dose_cap": cap, "rpe_cap": cap["rpe_cap"], **extra}


def _compose(role, strength=(), conditioning=(), sequence=None):
    pools = {"SPP": {"strength_slots": list(strength), "conditioning_slots": list(conditioning)}}
    roles = sequence or [role]
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": roles, "phase": "SPP"}, candidate_pools=pools)
    attach_late_fight_assignments(roles, assignments)
    role_map = {"weeks": [{"phase": "SPP", "session_roles": roles}]}
    apply_effective_strength_prescriptions(weekly_role_map=role_map, candidate_pools=pools)
    return role["selected_exercise_assignments"]


def _names(members):
    return [member["name"] for member in members]


def test_meaningful_anchor_leads_and_support_primer_only_complements():
    role = _role()
    members = _compose(role, strength=[_strength("Jump In Place")], conditioning=[_primer("Counter Reset")])
    assert _names(members) == ["Jump In Place", "Counter Reset"]
    assert not role.get("support_only_fill")
    assert members[1]["primer_complement"] is True
    # The complement is one round, not the bank's two.
    assert members[1]["effective_prescription"] == "1x5s with 120s rest"


def test_support_primers_fill_the_day_only_when_no_meaningful_candidate_is_legal():
    role = _role("neural_primer_day", d_day=7)
    members = _compose(role, conditioning=[_primer("Counter Reset"), _primer("Stance Cue", family="technical_neural", index=1)])
    assert _names(members) == ["Counter Reset", "Stance Cue"]
    assert role["support_only_fill"] is True and role["meaningful_stress_fulfilled"] is False
    assert role["late_assignment_diagnostics"]["meaningful_legal_candidates"] == 0


@pytest.mark.parametrize("count", [0, 1, 2, 3, 5])
def test_a_primer_holds_at_most_three_complementary_exercises(count):
    candidates = [
        _primer(f"Primer {index}", family=f"family_{index}", tags=(), index=index)
        for index in range(count)
    ]
    role = _role("neural_primer_day", d_day=7)
    members = _compose(role, conditioning=candidates)
    assert len(members) == min(count, LATE_PRIMER_MAX_MEMBERS)
    assert len(set(_names(members))) == len(members)


def test_repeated_stimulus_is_not_stacked_when_a_different_one_exists():
    role = _role()
    members = _compose(role, strength=[_strength("Jump In Place", index=0), _strength("Box Jump", index=1)],
                       conditioning=[_primer("Counter Reset")])
    # Two jumps are the same stimulus; the second slot goes to something different.
    assert _names(members) == ["Jump In Place", "Counter Reset"]


def test_a_session_carries_at_most_one_loaded_lift_and_complements_are_single_sets():
    role = _role(d_day=12)
    members = _compose(role, strength=[
        _strength("Jump In Place", index=0),
        _strength("Trap Lift", quality="anchor_loaded", tags=("mech_lower_hip_hinge",), prescription="3x3 @ RPE 7", index=1),
        _strength("Row Lift", quality="anchor_force_isometric", tags=("mech_upper_pull",), prescription="3x3 @ RPE 7", index=2),
    ])
    assert _names(members) == ["Jump In Place", "Trap Lift"]
    doses = {item["name"]: item for item in role["effective_strength_prescriptions"]}
    assert doses["Jump In Place"]["effective_max_sets"] == 2
    assert doses["Trap Lift"]["effective_max_sets"] == 1


def test_a_complement_that_raises_systemic_load_is_refused():
    role = _role()
    members = _compose(role, strength=[
        _strength("Jump In Place", index=0),
        _strength("Sled Iso", quality="anchor_force_isometric", tags=("mech_systemic_fatigue",), index=1),
    ])
    assert _names(members) == ["Jump In Place"]


def test_combined_workload_above_the_session_envelope_is_refused():
    role = _role()
    members = _compose(
        role,
        strength=[_strength("Jump In Place", index=0)],
        # Even cut to one round, 40 fast contacts on top of the lead take the
        # session past a microdose.
        conditioning=[_primer("Contact Volume", tags=("mech_reactive",), prescription="3x40 reps fast")],
    )
    assert _names(members) == ["Jump In Place"]
    stress = realised_role_stress(role)
    assert int(stress.neural_mechanical) <= 2


def test_a_complement_may_not_create_a_cross_day_collision_the_lead_avoids():
    neighbour = _role(d_day=9, calendar_stress={"systemic": 0, "neural_mechanical": 2, "regions": ["upper"]})
    role = _role(d_day=10)
    lead_only = _compose(dict(role), strength=[_strength("Jump In Place")], sequence=None)
    assert _names(lead_only) == ["Jump In Place"]
    members = _compose(
        role,
        strength=[_strength("Jump In Place")],
        conditioning=[_primer("Upper Burst", tags=("mech_ballistic", "mech_upper_press"))],
        sequence=[role, neighbour],
    )
    # The upper-body burst would repeat meaningful upper-body load on the next
    # day; the lead-only session does not, so the complement is refused.
    assert _names(members) == ["Jump In Place"]


def test_no_legal_candidate_leaves_the_session_empty_rather_than_inventing_one():
    role = _role("neural_primer_day", d_day=7)
    assert _compose(role) == []


def test_composed_primer_is_stamped_with_its_realised_session_load():
    role = _role()
    _compose(role, strength=[_strength("Jump In Place")], conditioning=[_primer("Counter Reset")])
    stamp = role["calendar_stress"]
    assert stamp["authority"] == "realised_session_composition"
    assert stamp["neural_mechanical"] == 2 and stamp["systemic"] == 0


def test_a_lead_whose_own_session_dominates_yields_to_one_that_fits():
    role = _role("neural_primer_day", d_day=7)
    members = _compose(role, conditioning=[
        _primer("Volume Burst", tags=("mech_reactive",), prescription="2x40 reps fast", index=0),
        _primer("Counter Reset", family="technical_neural", index=1),
    ])
    assert members[0]["name"] == "Counter Reset"
    assert "Volume Burst" not in _names(members)


def test_when_every_lead_dominates_the_best_is_kept_alone():
    role = _role("neural_primer_day", d_day=7)
    members = _compose(role, conditioning=[
        _primer("Volume Burst", tags=("mech_reactive",), prescription="2x40 reps fast", index=0),
        _primer("Volume Hop", family="technical_neural", tags=("mech_reactive",), prescription="2x40 reps fast", index=1),
    ])
    assert _names(members) == ["Volume Burst"]
