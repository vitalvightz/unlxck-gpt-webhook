"""Cross-day S&C load: realised composition, not the planned role promise.

Reproduces the class of flaw where a meaningful glycolytic day is followed the
very next day by a substantial neural/mechanical session, and nothing objects
because no hard contact is involved.

The canonical authority under test is ``combat_load_policy``. These tests drive
it directly for the rule itself, and through the composed-plan seam for the
sequence (role placement -> composition -> realised classification -> calendar
revalidation).
"""

from __future__ import annotations

import pytest

from fightcamp.combat_load_policy import (
    BodyRegion,
    CalendarEvent,
    CalendarLoadProfile,
    DayOccupancy,
    LoadClass,
    PlacementDirective,
    SessionStress,
    StressLevel,
    evaluate_candidate_at_position,
    role_load_profile,
)
from fightcamp.session_composition import (
    apply_realised_load_calendar_revalidation,
    assignment_from_slot,
    compose_normal_conditioning_assignments,
    _stress_stamp,
    realised_role_stress,
    realised_session_stress,
)


def _bank_slot(name, prescription, mechanical_risk_tags, *, system="alactic"):
    """A candidate slot shaped the way the production pools shape one."""
    return {
        "slot_id": f"slot-{name.lower().replace(' ', '-')}",
        "session_index": 1,
        "priority": 1,
        "purpose": name,
        "role": system,
        "selected": {
            "name": name,
            "role": system,
            "prescription": prescription,
            "selection_metadata": {
                "mechanical_risk_tags": list(mechanical_risk_tags),
                "duration": prescription,
            },
        },
    }


def _profile(load_class, stress=None, occupancy=None):
    return CalendarLoadProfile(
        load_class=load_class,
        occupancy=occupancy or DayOccupancy.PHYSICAL,
        stress=stress,
    )


HARD_GLYCOLYTIC = _profile(
    LoadClass.MEANINGFUL_CONDITIONING, SessionStress(systemic=StressLevel.HIGH)
)


def _decide(candidate, neighbour_position=-26, candidate_position=-25):
    return evaluate_candidate_at_position(
        candidate,
        candidate_position=candidate_position,
        events=[CalendarEvent(neighbour_position, HARD_GLYCOLYTIC, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )


# --- the rule itself ---------------------------------------------------------

def test_substantial_plyometric_day_after_meaningful_glycolytic_is_deprioritized():
    """D-26 hard glycolytic -> D-25 substantial lower-body plyometrics."""
    realised_plyo = _profile(
        LoadClass.NEURAL_MICRODOSE,
        SessionStress(
            neural_mechanical=StressLevel.HIGH, regions=frozenset({BodyRegion.LOWER})
        ),
    )
    decision = _decide(realised_plyo)

    assert decision.directive is PlacementDirective.DEPRIORITIZE
    assert decision.reason_code == "adjacent_day_systemic_then_mechanical"


def test_rule_is_symmetric_when_the_hard_day_comes_after():
    """Ordering must not decide legality: the conflict is the adjacency."""
    realised_plyo = _profile(
        LoadClass.NEURAL_MICRODOSE,
        SessionStress(
            neural_mechanical=StressLevel.HIGH, regions=frozenset({BodyRegion.LOWER})
        ),
    )
    decision = _decide(realised_plyo, neighbour_position=-24)
    assert decision.directive is PlacementDirective.DEPRIORITIZE


def test_genuine_neural_microdose_still_follows_meaningful_conditioning():
    """A true small primer stays legal — this is not a mandatory rest rule."""
    microdose = _profile(
        LoadClass.NEURAL_MICRODOSE,
        SessionStress(
            neural_mechanical=StressLevel.LOW, regions=frozenset({BodyRegion.LOWER})
        ),
    )
    assert _decide(microdose).directive is PlacementDirective.ALLOW


@pytest.mark.parametrize(
    "load_class",
    [
        LoadClass.LOW_LOAD_AEROBIC,
        LoadClass.RECOVERY_ONLY,
        LoadClass.LOW_LOAD_PHYSICAL,
    ],
)
def test_recovery_and_easy_aerobic_work_remain_legal(load_class):
    """Recovery, mobility and easy aerobic work may follow a hard glycolytic day."""
    assert _decide(_profile(load_class)).directive is PlacementDirective.ALLOW


def test_repeated_regional_mechanical_load_is_deprioritized():
    """Generic case: meaningful lower-body strength -> high-impact speed next day."""
    heavy_lower_strength = _profile(
        LoadClass.MEANINGFUL_STRENGTH,
        SessionStress(
            neural_mechanical=StressLevel.MODERATE,
            regions=frozenset({BodyRegion.LOWER}),
        ),
    )
    impact_speed = _profile(
        LoadClass.NEURAL_MICRODOSE,
        SessionStress(
            neural_mechanical=StressLevel.HIGH, regions=frozenset({BodyRegion.LOWER})
        ),
    )
    decision = evaluate_candidate_at_position(
        impact_speed,
        candidate_position=-25,
        events=[CalendarEvent(-26, heavy_lower_strength, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )
    assert decision.directive is PlacementDirective.DEPRIORITIZE
    assert decision.reason_code == "adjacent_day_repeat_regional_mechanical_load"


def test_different_body_regions_do_not_trigger_the_regional_rule():
    """Region overlap is required; upper-body work after lower-body work is fine."""
    lower = _profile(
        LoadClass.MEANINGFUL_STRENGTH,
        SessionStress(
            neural_mechanical=StressLevel.MODERATE,
            regions=frozenset({BodyRegion.LOWER}),
        ),
    )
    upper = _profile(
        LoadClass.MEANINGFUL_STRENGTH,
        SessionStress(
            neural_mechanical=StressLevel.MODERATE,
            regions=frozenset({BodyRegion.UPPER}),
        ),
    )
    decision = evaluate_candidate_at_position(
        upper,
        candidate_position=-25,
        events=[CalendarEvent(-26, lower, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )
    assert decision.directive is PlacementDirective.ALLOW


def test_unstamped_profiles_abstain_entirely():
    """A profile with no vector and no class default changes no behaviour."""
    unknown = CalendarLoadProfile(
        load_class=LoadClass.MEANINGFUL_CONDITIONING,
        occupancy=DayOccupancy.PHYSICAL,
    )
    neighbour = CalendarLoadProfile(
        load_class=LoadClass.MEANINGFUL_STRENGTH, occupancy=DayOccupancy.PHYSICAL
    )
    decision = evaluate_candidate_at_position(
        unknown,
        candidate_position=-25,
        events=[CalendarEvent(-26, neighbour, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )
    # Planned class defaults alone (MODERATE systemic, MODERATE neural, no known
    # region) are below the threshold, so nothing fires without realised evidence.
    assert decision.directive is PlacementDirective.ALLOW


# --- realised measurement ----------------------------------------------------

def test_role_key_promise_is_overridden_by_the_realised_stamp():
    """alactic_speed_day is NEURAL_MICRODOSE until composition says otherwise."""
    role = {"role_key": "alactic_speed_day", "category": "conditioning",
            "preferred_system": "alactic"}
    planned = role_load_profile(role)
    assert planned.load_class is LoadClass.NEURAL_MICRODOSE
    assert planned.stress is None

    role["calendar_stress"] = {
        "systemic": 0, "neural_mechanical": 3, "regions": ["lower"],
    }
    realised = role_load_profile(role)
    # The class is unchanged — a stamp measures cost, it does not reclassify.
    assert realised.load_class is LoadClass.NEURAL_MICRODOSE
    assert realised.stress.neural_mechanical is StressLevel.HIGH
    assert realised.stress.regions == frozenset({BodyRegion.LOWER})


def test_realised_stress_measures_the_composed_plyometric_session():
    """Measured from assignments as the real composition builder emits them."""
    assignments = [
        assignment_from_slot("SPP", "conditioning_slots", _bank_slot(
            "Alternating Bounds", "4x5/side, 2min rest",
            ["mech_ballistic", "mech_lower_jump"],
        )),
        assignment_from_slot("SPP", "conditioning_slots", _bank_slot(
            "Single-Leg Hop (Stabilize)", "4x5/side, 90s rest",
            ["mech_landing_impact", "mech_lower_jump"],
        )),
    ]
    stress = realised_session_stress(assignments)
    assert stress.neural_mechanical is StressLevel.HIGH
    assert BodyRegion.LOWER in stress.regions


def test_authored_mechanical_tags_survive_onto_production_assignments():
    """Regression: the assignment is the only surviving record of what a session
    mechanically is, because the candidate pool it came from is compacted.

    Dropping the tags here made body region permanently unknown downstream,
    which silently disabled the region-gated cross-day rule entirely.
    """
    slot = _bank_slot(
        "Trap Bar Deadlift", "3 x 5 @ RPE 7",
        ["mech_lower_hip_hinge", "mech_trunk_stability"],
    )
    assignment = assignment_from_slot("SPP", "strength_slots", slot)
    assert assignment["mechanical_risk_tags"] == [
        "mech_lower_hip_hinge", "mech_trunk_stability",
    ]

    # The bank also states them on the item itself rather than in metadata.
    bare = {"slot_id": "s2", "selected": {
        "name": "Broad Jump", "prescription": "5x4",
        "mechanical_risk_tags": ["mech_ballistic", "mech_lower_jump"],
    }}
    assert assignment_from_slot("SPP", "strength_slots", bare)[
        "mechanical_risk_tags"
    ] == ["mech_ballistic", "mech_lower_jump"]


def test_realised_stress_uses_the_resolved_strength_dose_not_the_bank_dose():
    """Strength membership and strength dose are separate authorities.

    A strength assignment carries only the raw bank dose until
    ``prescription_resolver`` writes the role's scheduled-day answer. Measuring
    off the bank dose scores a capped primer at the dose it was capped away from.
    """
    role = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "selected_exercise_assignments": [
            {
                "slot_id": "s1",
                "name": "Back Squat",
                "slot_group": "strength_slots",
                # Uncapped bank dose: 5 x 8 = 40 reps, above the microdose ceiling.
                "base_prescription": "5 sets x 8 reps @ RPE 8",
                "mechanical_risk_tags": ["mech_lower_squat"],
            }
        ],
        "effective_strength_prescriptions": [
            {
                "slot_id": "s1",
                "name": "Back Squat",
                # Resolver's authoritative answer: 2 x 3 = 6 reps.
                "effective_prescription": "2 x 3 @ RPE 6",
            }
        ],
    }
    # Measured off the bank dose this reads as a meaningful session.
    assert realised_session_stress(
        role["selected_exercise_assignments"]
    ).neural_mechanical is StressLevel.MODERATE
    # Measured off the authoritative dose it is correctly a small one.
    assert realised_role_stress(role).neural_mechanical is StressLevel.LOW


def test_embedded_support_does_not_inflate_realised_stress():
    """A dose-capped embedded support item is not the session's cost."""
    stress = realised_session_stress(
        [
            assignment_from_slot("SPP", "conditioning_slots", _bank_slot(
                "Pogo Hops", "2x5", ["mech_lower_jump"],
            )),
            {
                **assignment_from_slot("SPP", "strength_slots", _bank_slot(
                    "Overhead Carry (Single Arm)",
                    "2-4 sets x 6-10 reps or 20-40s tempo (3-1-3), RPE 6-8",
                    ["mech_shoulder_overhead", "mech_upper_carry"],
                )),
                "embedded_support": True,
                "effective_prescription": "1-2 controlled sets; stop before fatigue",
            },
        ]
    )
    # A small pogo session is genuinely low, and stays low: the capped upper-body
    # support neither raises the level nor contributes its UPPER region.
    assert stress.neural_mechanical is StressLevel.LOW
    assert stress.regions == frozenset({BodyRegion.LOWER})


def test_unmeasurable_session_leaves_the_planned_vector_alone():
    assert realised_session_stress([]) is None
    assert realised_session_stress([{"name": "Unknown", "effective_prescription": ""}]) is None


# --- the composed-plan seam --------------------------------------------------

def _spp_week():
    """A declared-7-day SPP week with the reproduction adjacency at D-26/D-25."""
    return {
        "week_index": 1,
        "phase": "SPP",
        "declared_training_days": [
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        ],
        "calendar_days": [
            {"weekday": "monday", "d_day": 25},
            {"weekday": "tuesday", "d_day": 24},
            {"weekday": "wednesday", "d_day": 23},
            {"weekday": "thursday", "d_day": 22},
            {"weekday": "friday", "d_day": 21},
            {"weekday": "saturday", "d_day": 27},
            {"weekday": "sunday", "d_day": 26},
        ],
        "session_roles": [],
    }


def _glycolytic_role():
    return {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "preferred_system": "glycolytic",
        "meaningful_stress": True,
        "scheduled_day_hint": "Sunday",
        "scheduled_countdown_label": "D-26",
        "scheduled_d_day": 26,
        "selected_exercise_assignments": [
            {
                "name": "Assault Bike Capacity Builder",
                "effective_prescription": "20min EMOM: 12 cal",
                "mechanical_risk_tags": ["mech_systemic_fatigue"],
            }
        ],
    }


def _plyometric_role(assignments=None):
    return {
        "role_key": "alactic_speed_day",
        "category": "conditioning",
        "preferred_system": "alactic",
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": "D-25",
        "scheduled_d_day": 25,
        "selected_exercise_assignments": assignments
        if assignments is not None
        else [
            {
                "name": "Alternating Bounds",
                "effective_prescription": "4x5/side, 2min rest",
                "mechanical_risk_tags": ["mech_ballistic", "mech_lower_jump"],
            },
            {
                "name": "Single-Leg Hop (Stabilize)",
                "effective_prescription": "4x5/side, 90s rest",
                "mechanical_risk_tags": ["mech_landing_impact", "mech_lower_jump"],
            },
        ],
    }


def _adjacent_load_conflicts(weekly_role_map):
    """Reason codes for any adjacent-day load conflict left on the calendar."""
    from fightcamp.calendar_context import build_events, role_refs

    conflicts = []
    for ref in role_refs(weekly_role_map):
        decision = evaluate_candidate_at_position(
            ref.profile,
            candidate_position=-ref.d_day,
            events=build_events(weekly_role_map, exclude_role=ref.role),
            candidate_scope=ref.scope,
        )
        if decision.reason_code.startswith("adjacent_day_"):
            conflicts.append(decision.reason_code)
    return conflicts


def test_reproduction_does_not_survive_when_a_cleaner_slot_exists():
    """D-26 meaningful glycolytic + D-25 substantial plyometrics must not stand."""
    week = _spp_week()
    week["session_roles"] = [_glycolytic_role(), _plyometric_role()]
    weekly_role_map = {"weeks": [week]}

    apply_realised_load_calendar_revalidation(weekly_role_map)

    # Either role may be the one that moves; what must not survive is the
    # adjacency itself.
    assert not _adjacent_load_conflicts(weekly_role_map)
    # Relocated, never deleted: the planner does not destroy training here.
    assert not week.get("suppressed_roles")
    assert len(week["session_roles"]) == 2
    assert weekly_role_map["realised_load_revalidation"]["actions"][0]["action"] == "relocated"


def test_a_true_microdose_keeps_its_day_next_to_the_glycolytic_session():
    """The rule is graded: a genuinely small alactic touch is left where it is."""
    week = _spp_week()
    week["session_roles"] = [
        _glycolytic_role(),
        _plyometric_role(
            [
                {
                    "name": "Pogo Hops",
                    "effective_prescription": "2x4",
                    "mechanical_risk_tags": ["mech_lower_jump"],
                }
            ]
        ),
    ]
    weekly_role_map = {"weeks": [week]}

    apply_realised_load_calendar_revalidation(weekly_role_map)

    plyo = next(
        role for role in week["session_roles"]
        if role["role_key"] == "alactic_speed_day"
    )
    assert plyo["scheduled_d_day"] == 25
    assert "realised_load_revalidation" not in weekly_role_map


def test_plan_without_the_adjacency_is_left_completely_alone():
    """A normal SPP plan must be stable under the new pass."""
    week = _spp_week()
    aerobic = {
        "role_key": "aerobic_support_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": "D-25",
        "scheduled_d_day": 25,
        "selected_exercise_assignments": [
            {"name": "Easy Bike Flush", "effective_prescription": "20 min",
             "mechanical_risk_tags": []}
        ],
    }
    week["session_roles"] = [_glycolytic_role(), aerobic]
    weekly_role_map = {"weeks": [week]}
    before = [role["scheduled_d_day"] for role in week["session_roles"]]

    apply_realised_load_calendar_revalidation(weekly_role_map)

    assert [role["scheduled_d_day"] for role in week["session_roles"]] == before
    assert "realised_load_revalidation" not in weekly_role_map


def test_injury_substitution_cannot_bypass_the_cross_day_policy():
    """A lower-body-safe substitution is re-judged on the load it actually creates.

    Filtering an upper-limb injury out of a session is legitimate. Concentrating
    the resulting stress into one region is not automatically load-neutral, and
    must not become a route around the adjacency rule.
    """
    week = _spp_week()
    # The composed session after upper-limb exclusions: entirely lower-body.
    substituted = _plyometric_role(
        [
            {
                "name": "Broad Jump",
                "effective_prescription": "5x4",
                "mechanical_risk_tags": ["mech_ballistic", "mech_lower_jump"],
            },
            {
                "name": "Split Squat Jump",
                "effective_prescription": "4x6/side",
                "mechanical_risk_tags": ["mech_landing_impact", "mech_lower_lunge"],
            },
        ]
    )
    week["session_roles"] = [_glycolytic_role(), substituted]
    weekly_role_map = {"weeks": [week]}

    apply_realised_load_calendar_revalidation(weekly_role_map)

    assert not _adjacent_load_conflicts(weekly_role_map)
    assert not week.get("suppressed_roles")


def test_hard_sparring_collision_behaviour_is_unchanged():
    """Contact rules keep precedence and their existing verdicts.

    The new adjacency rule sits after every contact branch, so a day next to
    hard contact is still judged by the contact rules and reports their reason
    codes, not the new ones.
    """
    from fightcamp.combat_load_policy import contact_load_profile

    hard = contact_load_profile({"effective_load": "hard"})
    realised_plyo = _profile(
        LoadClass.NEURAL_MICRODOSE,
        SessionStress(
            neural_mechanical=StressLevel.HIGH, regions=frozenset({BodyRegion.LOWER})
        ),
    )

    after_contact = evaluate_candidate_at_position(
        realised_plyo,
        candidate_position=-25,
        events=[CalendarEvent(-26, hard, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )
    assert after_contact.reason_code == "post_hard_contact_microdose"

    # Back-to-back hard contact stays FORBID.
    consecutive = evaluate_candidate_at_position(
        hard,
        candidate_position=-25,
        events=[CalendarEvent(-26, hard, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )
    assert consecutive.directive is PlacementDirective.FORBID
    assert consecutive.reason_code == "consecutive_effective_hard_contact"

    # Same-day contact stacking stays FORBID.
    same_day = evaluate_candidate_at_position(
        realised_plyo,
        candidate_position=-26,
        events=[CalendarEvent(-26, hard, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )
    assert same_day.directive is PlacementDirective.FORBID


def test_a_relocated_role_is_re_morphed_for_its_new_countdown_day():
    """Relocation must not leave a dose resolved for the day the role left.

    This pass runs after the countdown dose morph, and a move can cross a morph
    band boundary (strength morphs through D-17), so the canonical morph owner is
    called again — the same contract the final governor follows.
    """
    week = _spp_week()
    week["session_roles"] = [_glycolytic_role(), _plyometric_role()]
    weekly_role_map = {"weeks": [week]}

    apply_realised_load_calendar_revalidation(weekly_role_map)

    for role in week["session_roles"]:
        relocation = role.get("calendar_integrity_relocation")
        if not relocation:
            continue
        # The role's own countdown metadata agrees with where it now sits.
        assert role["scheduled_d_day"] == relocation["to_d_day"]
        assert role["scheduled_countdown_label"] == f"D-{relocation['to_d_day']}"


def test_end_to_end_through_the_real_conditioning_composition_builder():
    """Drive the production composition path, not hand-built assignments.

    The earlier version of this regression injected ``mechanical_risk_tags``
    directly onto assignments. Production assignments did not carry them at all,
    so body region was permanently unknown and the region-gated rule could never
    fire on a real plan. This test fails if that seam regresses, because the
    assignments here are built only by ``compose_normal_conditioning_assignments``.
    """
    from fightcamp.planner_context import planner_athlete_model_context

    week = _spp_week()
    glycolytic = {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "preferred_system": "glycolytic",
        "meaningful_stress": True,
        "scheduled_day_hint": "Sunday",
        "scheduled_countdown_label": "D-26",
        "scheduled_d_day": 26,
    }
    plyo = {
        "role_key": "alactic_speed_day",
        "category": "conditioning",
        "preferred_system": "alactic",
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": "D-25",
        "scheduled_d_day": 25,
    }
    week["session_roles"] = [glycolytic, plyo]
    weekly_role_map = {"weeks": [week]}
    pools = {
        "SPP": {
            "conditioning_slots": [
                _bank_slot(
                    "Assault Bike Capacity Builder", "20min EMOM: 12 cal",
                    ["mech_systemic_fatigue"], system="glycolytic",
                ),
                _bank_slot(
                    "Alternating Bounds", "4x5/side, 2min rest",
                    ["mech_ballistic", "mech_lower_jump"],
                ),
                _bank_slot(
                    "Single-Leg Hop (Stabilize)", "4x5/side, 90s rest",
                    ["mech_landing_impact", "mech_lower_jump"],
                ),
            ],
            "strength_slots": [],
        }
    }

    token = planner_athlete_model_context.set({})
    try:
        compose_normal_conditioning_assignments(
            weekly_role_map=weekly_role_map, candidate_pools=pools,
        )
    finally:
        planner_athlete_model_context.reset(token)

    # The composition builder itself must carry the authored tags through.
    composed = plyo["selected_exercise_assignments"]
    assert composed, "the real builder composed nothing"
    assert any(item.get("mechanical_risk_tags") for item in composed)

    # And the realised measurement must then see a lower-body session.
    stress = realised_role_stress(plyo)
    assert BodyRegion.LOWER in stress.regions, (
        "body region is unknown on a real composed session"
    )

    apply_realised_load_calendar_revalidation(weekly_role_map)
    assert not _adjacent_load_conflicts(weekly_role_map)
    assert not week.get("suppressed_roles")
    assert len(week["session_roles"]) == 2


def test_relocation_across_a_morph_boundary_restamps_from_the_new_days_dose():
    """A relocated role's persisted stress must describe the dose it ends with.

    Relocation re-morphs and re-doses the role for its new day. D-18+ is
    uncapped; D-17 and closer caps strength to 3x3. A role moved across that
    boundary is a materially smaller session than the one that was moved, and
    the stamp written before the move describes the dose on the day it left.
    A stale stamp is a lie to every later reader, not just to this pass.

    Drives the real morph and the real prescription resolver, not stand-ins.
    """
    from fightcamp.prescription_resolver import apply_effective_strength_prescriptions

    # Declared days deliberately skip D-18/D-17, so the only legal destinations
    # sit on the far side of the morph boundary.
    week = {
        "week_index": 1,
        "phase": "SPP",
        "declared_training_days": ["sunday", "monday", "tuesday", "wednesday"],
        "calendar_days": [
            {"weekday": "sunday", "d_day": 20},
            {"weekday": "monday", "d_day": 19},
            {"weekday": "tuesday", "d_day": 16},
            {"weekday": "wednesday", "d_day": 15},
        ],
        "session_roles": [],
    }
    glycolytic = {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "preferred_system": "glycolytic",
        "meaningful_stress": True,
        "scheduled_day_hint": "Sunday",
        "scheduled_countdown_label": "D-20",
        "scheduled_d_day": 20,
        # Deliberately unmeasurable (no mechanical tags, no rep count), so this
        # role gets no realised stamp and is never itself a relocation
        # candidate. It still contributes systemic=HIGH from its glycolytic
        # class derivation, so it is a *fixed* neighbour and the strength role
        # is unambiguously the one that has to move. Without this the two roles
        # simply swap days and nothing crosses the boundary under test.
        "selected_exercise_assignments": [
            {
                "name": "Assault Bike Capacity Builder",
                "effective_prescription": "20min EMOM: 12 cal",
            }
        ],
    }
    strength = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": "D-19",
        "scheduled_d_day": 19,
        "selected_exercise_assignments": [
            {
                "slot_id": "st1",
                "name": "Back Squat",
                "slot_group": "strength_slots",
                "source_phase": "SPP",
                # Uncapped bank dose: 5 x 8 = 40 reps.
                "base_prescription": "5 sets x 8 reps @ RPE 8",
                "mechanical_risk_tags": ["mech_lower_squat", "mech_axial_heavy"],
            }
        ],
    }
    week["session_roles"] = [glycolytic, strength]
    weekly_role_map = {"weeks": [week]}
    pools = {
        "SPP": {
            "strength_slots": [
                {
                    "slot_id": "st1",
                    "session_index": 1,
                    "priority": 1,
                    "quality_class": "anchor_loaded",
                    "selected": {
                        "name": "Back Squat",
                        "prescription": "5 sets x 8 reps @ RPE 8",
                        "quality_class": "anchor_loaded",
                    },
                }
            ]
        }
    }

    def _redose(role_map):
        return apply_effective_strength_prescriptions(
            weekly_role_map=role_map, candidate_pools=pools, athlete_model={},
        )

    _redose(weekly_role_map)
    # Before the move: uncapped at D-19, so heavy axial work at full bank volume.
    assert realised_role_stress(strength).neural_mechanical is StressLevel.HIGH

    apply_realised_load_calendar_revalidation(
        weekly_role_map, redose_callback=_redose,
    )

    # It crossed the boundary.
    assert strength["scheduled_d_day"] <= 17
    assert strength["scheduled_countdown_label"] == f"D-{strength['scheduled_d_day']}"

    # The authoritative dose is the new day's, not the day it left.
    resolved = strength["effective_strength_prescriptions"][0]["effective_prescription"]
    assert resolved == "3 x 3 @ RPE 6-7 max"
    assert "5 sets x 8 reps" not in resolved

    # And the persisted stamp reflects that smaller dose rather than the old one.
    stamp = strength["calendar_stress"]
    assert stamp == _stress_stamp(realised_role_stress(strength))
    # Still heavy axial work, but at 3x3 rather than 5x8 it is no longer a
    # top-end session — the stamp tracks the dose, which is the whole point.
    assert stamp["neural_mechanical"] == int(StressLevel.MODERATE)

    # Bounded, and the destination is legal under the refreshed load.
    report = weekly_role_map["realised_load_revalidation"]
    assert report["rounds_run"] <= report["max_rounds"] == 2
    assert not report["residual_conflicts"]
    assert not _adjacent_load_conflicts(weekly_role_map)


def test_stamps_are_fresh_even_when_the_last_round_relocates(monkeypatch):
    """At the round cap there is no next round to re-stamp, so the pass must.

    Each round re-stamps at its start, which covers every relocation except one:
    a move made by the *final* round is followed by a re-dose and then by nothing.
    Without the closing refresh that role would persist a stamp describing the
    dose it had on the day it left. Forcing the cap to one round isolates exactly
    that boundary.
    """
    import fightcamp.session_composition as composition
    from fightcamp.prescription_resolver import apply_effective_strength_prescriptions

    monkeypatch.setattr(composition, "_MAX_REVALIDATION_ROUNDS", 1)

    week = {
        "week_index": 1,
        "phase": "SPP",
        "declared_training_days": ["sunday", "monday", "tuesday", "wednesday"],
        "calendar_days": [
            {"weekday": "sunday", "d_day": 20},
            {"weekday": "monday", "d_day": 19},
            {"weekday": "tuesday", "d_day": 16},
            {"weekday": "wednesday", "d_day": 15},
        ],
        "session_roles": [],
    }
    glycolytic = {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "preferred_system": "glycolytic",
        "meaningful_stress": True,
        "scheduled_day_hint": "Sunday",
        "scheduled_countdown_label": "D-20",
        "scheduled_d_day": 20,
        "selected_exercise_assignments": [
            {"name": "Assault Bike Capacity Builder",
             "effective_prescription": "20min EMOM: 12 cal"}
        ],
    }
    strength = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": "D-19",
        "scheduled_d_day": 19,
        "selected_exercise_assignments": [
            {
                "slot_id": "st1", "name": "Back Squat",
                "slot_group": "strength_slots", "source_phase": "SPP",
                "base_prescription": "5 sets x 8 reps @ RPE 8",
                "mechanical_risk_tags": ["mech_lower_squat", "mech_axial_heavy"],
            }
        ],
    }
    week["session_roles"] = [glycolytic, strength]
    weekly_role_map = {"weeks": [week]}
    pools = {"SPP": {"strength_slots": [{
        "slot_id": "st1", "session_index": 1, "priority": 1,
        "quality_class": "anchor_loaded",
        "selected": {"name": "Back Squat",
                     "prescription": "5 sets x 8 reps @ RPE 8",
                     "quality_class": "anchor_loaded"},
    }]}}

    def _redose(role_map):
        return apply_effective_strength_prescriptions(
            weekly_role_map=role_map, candidate_pools=pools, athlete_model={},
        )

    _redose(weekly_role_map)
    composition.apply_realised_load_calendar_revalidation(
        weekly_role_map, redose_callback=_redose,
    )

    assert strength["scheduled_d_day"] <= 17, "the fixture did not cross the boundary"
    report = weekly_role_map["realised_load_revalidation"]
    assert report["rounds_run"] == 1 == report["max_rounds"]

    # Every persisted stamp still equals a fresh measurement of the final dose.
    for role in week["session_roles"]:
        fresh = realised_role_stress(role)
        if fresh is None:
            assert "calendar_stress" not in role
        else:
            assert role["calendar_stress"] == _stress_stamp(fresh)


def test_revalidation_is_bounded_and_records_what_it_did_not_chase():
    """The pass must terminate even when every day it can reach is in conflict.

    Relocation changes a role's day, which re-doses it, which changes its load,
    which can change where it belongs — a fixpoint search that is deliberately
    not run to convergence. The bound must hold and the leftover must be visible
    rather than silently accepted.
    """
    week = _spp_week()
    # Three substantial lower-body sessions on consecutive days: whichever way
    # they are shuffled some adjacency remains, so relocation cannot settle.
    roles = []
    for offset, day in ((26, "Sunday"), (25, "Monday"), (24, "Tuesday")):
        roles.append({
            "role_key": "alactic_speed_day",
            "category": "conditioning",
            "preferred_system": "alactic",
            "scheduled_day_hint": day,
            "scheduled_countdown_label": f"D-{offset}",
            "scheduled_d_day": offset,
            "selected_exercise_assignments": [
                assignment_from_slot("SPP", "conditioning_slots", _bank_slot(
                    f"Bounds {offset}", "5x6/side",
                    ["mech_ballistic", "mech_landing_impact", "mech_lower_jump"],
                ))
            ],
        })
    week["session_roles"] = roles
    # Only these three days exist, so there is nowhere clean to escape to.
    week["declared_training_days"] = ["sunday", "monday", "tuesday"]
    week["calendar_days"] = [
        {"weekday": "sunday", "d_day": 26},
        {"weekday": "monday", "d_day": 25},
        {"weekday": "tuesday", "d_day": 24},
    ]
    weekly_role_map = {"weeks": [week]}

    apply_realised_load_calendar_revalidation(weekly_role_map)

    report = weekly_role_map["realised_load_revalidation"]
    assert report["rounds_run"] <= report["max_rounds"] == 2
    # Nothing was destroyed to force a resolution.
    assert len(week["session_roles"]) == 3
    assert not week.get("suppressed_roles")
    # What could not be resolved is reported, not hidden.
    assert report["residual_conflicts"]
    assert all(
        item["directive"] == "deprioritize" for item in report["residual_conflicts"]
    )
