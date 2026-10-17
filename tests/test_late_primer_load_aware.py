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


def test_a_complement_with_an_unmeasurable_dose_is_refused():
    role = _role()
    unknown = _primer("Feel Drill", family="technical_neural", tags=(), prescription="as feels right")
    unknown["selected"]["selection_metadata"]["lactate_load"] = ""
    members = _compose(role, strength=[_strength("Jump In Place")], conditioning=[unknown])
    assert _names(members) == ["Jump In Place"]


def test_an_unmeasurable_lead_takes_no_complements():
    role = _role("neural_primer_day", d_day=7)
    unknown = _primer("Feel Drill", tags=(), prescription="as feels right")
    unknown["selected"]["selection_metadata"]["lactate_load"] = ""
    members = _compose(role, conditioning=[unknown, _primer("Counter Reset", family="technical_neural", index=1)])
    # The measurable primer leads instead; the unknown one is never a complement.
    assert _names(members) == ["Counter Reset"]


def test_durations_are_not_counted_as_repetitions():
    from fightcamp.session_composition import _prescription_total_reps, prescription_dose_known

    assert _prescription_total_reps("2x5s with 120s rest") == 0
    assert _prescription_total_reps("4–6 x 6–10 sec fast bursts") == 0
    assert _prescription_total_reps("4x4 reps, 60s rest") == 16
    assert prescription_dose_known("2x5s with 120s rest")
    assert not prescription_dose_known("as feels right")


def _light_combat(d_day):
    return {"role_key": "light_combat_day", "category": "technical", "coach_owned": True,
            "declared_day_locked": True, "scheduled_countdown_label": f"D-{d_day}", "countdown_offset": d_day}


def test_a_forbidden_day_moves_the_composed_primer_to_an_adjacent_legal_day():
    role = _role("neural_primer_day", d_day=7, scheduled_day_hint="monday")
    members = _compose(role, conditioning=[_primer("Counter Reset")], sequence=[role, _role("strength_touch_day", d_day=7)])
    assert _names(members) == ["Counter Reset"]
    resolution = role["late_load_resolution"]
    assert resolution["action"] == "relocated_to_adjacent_day"
    assert resolution["from_d_day"] == 7 and resolution["to_d_day"] == 8
    assert role["scheduled_countdown_label"] == "D-8" and role["scheduled_day_hint"] == "sunday"
    assert members[0]["scheduled_countdown_label"] == "D-8"


def _occupancy_filler(d_day):
    return {"role_key": "joint_prep", "category": "support_insert", "physical_occupancy_fill": True,
            "governance": {"authority": "gap_fill_support_insert", "meaningful_stress": False},
            "stress_class": "support", "cost_class": "low", "scheduled_countdown_label": f"D-{d_day}",
            "countdown_offset": d_day}


def test_a_relocated_primer_takes_the_day_from_an_occupancy_filler():
    from fightcamp.stage2_payload import drop_displaced_occupancy_fillers

    role = _role("neural_primer_day", d_day=7, scheduled_day_hint="monday")
    filler = _occupancy_filler(6)
    blocked = _role("strength_touch_day", d_day=8)
    sequence = [role, _role("strength_touch_day", d_day=7), filler, blocked]
    _compose(role, conditioning=[_primer("Counter Reset")], sequence=sequence)
    assert role["late_load_resolution"]["to_d_day"] == 6
    assert role["late_load_resolution"]["displaced_fillers"] == ["joint_prep"]
    drop_displaced_occupancy_fillers(sequence)
    assert filler not in sequence


def test_compatible_technical_day_keeps_the_composed_primer_without_duplicate_reduction():
    role = _role("neural_primer_day", d_day=7)
    quiet = _primer("Stance Cue", family="technical_neural", tags=(), prescription="2x3s with 120s rest", index=1)
    members = _compose(role, conditioning=[_primer("Counter Reset"), quiet],
                       sequence=[role, _light_combat(7)])
    assert _names(members) == ["Counter Reset", "Stance Cue"]
    assert "late_load_resolution" not in role


def test_a_reduction_the_policy_still_forbids_is_never_accepted():
    # The day belongs to another exclusive stressor: even a microdose may not share it.
    role = _role("neural_primer_day", d_day=7)
    quiet = _primer("Stance Cue", family="technical_neural", tags=(), prescription="2x3s with 120s rest", index=1)
    owner = _role("strength_touch_day", d_day=7)
    members = _compose(role, conditioning=[_primer("Counter Reset"), quiet], sequence=[role, owner])
    assert members == []
    assert role["late_load_resolution"]["action"] == "suppressed_no_safe_prescription"


def test_a_forbidden_fixed_day_with_no_safe_option_removes_the_session():
    role = _role("neural_primer_day", d_day=7)
    members = _compose(role, conditioning=[_primer("Counter Reset")], sequence=[role, _role("strength_touch_day", d_day=7)])
    assert members == []
    assert role["late_load_resolution"]["action"] == "suppressed_no_safe_prescription"


def test_policy_classifies_a_measured_microdose_primer_as_a_microdose():
    from fightcamp.combat_load_policy import DayOccupancy, LoadClass, role_load_profile

    role = _role("neural_primer_day", d_day=7)
    assert role_load_profile(role).occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL
    micro = {**role, "calendar_stress": {"systemic": 0, "neural_mechanical": 1, "regions": [],
                                         "authority": "realised_session_composition"}}
    profile = role_load_profile(micro)
    assert profile.load_class is LoadClass.NEURAL_MICRODOSE
    assert profile.occupancy is DayOccupancy.PHYSICAL
    heavier = {**micro, "calendar_stress": {**micro["calendar_stress"], "neural_mechanical": 2}}
    assert role_load_profile(heavier).occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL
    unattributed = {**micro, "calendar_stress": {**micro["calendar_stress"], "authority": "hand_written"}}
    assert role_load_profile(unattributed).occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL


def test_a_sport_specific_primer_leads_the_style_taper_group_for_a_non_boxer():
    from fightcamp.planner_context import planner_athlete_model_context

    generic = _primer("Hand Burst", family="pure_neural", index=0)
    generic["selected"]["selection_metadata"]["tags"] = ["boxing", "kickboxing", "muay_thai"]
    generic["selected"]["relevance"] = {"style_hits": 2, "goal_hits": 2}
    kick = _primer("Kick Reset", family="pure_neural", index=1)
    kick["selected"]["selection_metadata"]["tags"] = ["kickboxing", "muay_thai"]
    kick["selected"]["relevance"] = {"style_hits": 0, "goal_hits": 0}

    for sport, expected in (("kickboxing", ["Kick Reset", "Hand Burst"]), ("boxing", ["Hand Burst"])):
        token = planner_athlete_model_context.set(
            {"sport": sport, "phase_weeks": {"days": {"GPP": 0, "SPP": 14, "TAPER": 0}}})
        try:
            role = _role("neural_primer_day", d_day=7)
            members = _compose(role, conditioning=[generic, kick])
        finally:
            planner_athlete_model_context.reset(token)
        # A boxer cannot use the kick drill (sport gate); a kickboxer leads with it,
        # and it is a different stimulus from the same-family hand drill.
        assert _names(members) == expected, sport


@pytest.mark.parametrize(("d_day", "expected"), [
    (13, "4x3 reps, 1min rest"),
    (7, "4x3 reps, 1min rest"),
    (6, "3x3 reps, 1min rest"),
    (5, "3x3 reps, 1min rest"),
    (3, "2x3 reps, 1min rest"),
])
def test_late_primer_caps_conditioning_bank_rep_sets(d_day, expected):
    from fightcamp.stage2_payload import _late_primer_member_dose

    role = _role("alactic_sharpness_day", d_day=d_day)
    slot = {"role": "alactic", "selected": {
        "name": "Overhead Med Ball Slam (Snappy)", "system": "ATP-PCr",
        "prescription": "6x3 reps, 1min rest",
    }}
    assert _late_primer_member_dose(role, "conditioning_slots", slot, complement=False) == expected
    assert _late_primer_member_dose(role, "conditioning_slots", slot, complement=True) == "1x3 reps, 1min rest"


def test_late_primer_never_increases_a_smaller_conditioning_prescription():
    from fightcamp.stage2_payload import _late_primer_member_dose

    role = _role("alactic_sharpness_day", d_day=6)
    slot = {"role": "alactic", "selected": {
        "name": "Small throw", "system": "ATP-PCr", "prescription": "2x3 reps, 2min rest",
    }}
    assert _late_primer_member_dose(role, "conditioning_slots", slot, complement=False) == "2x3 reps, 2min rest"


def test_late_primer_conditioning_dose_reduction_preserves_timed_units():
    from fightcamp.stage2_payload import _late_primer_member_dose

    role = _role("alactic_sharpness_day", d_day=6)
    slot = {"role": "alactic", "selected": {
        "name": "Shadow bursts", "system": "ATP-PCr",
        "prescription": "6x5s with 120s rest",
    }}
    assert _late_primer_member_dose(role, "conditioning_slots", slot, complement=False) == "3x5s with 120s rest"
