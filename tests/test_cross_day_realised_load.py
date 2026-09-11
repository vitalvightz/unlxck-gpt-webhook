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
    realised_session_stress,
)


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
    stress = realised_session_stress(
        [
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
        ]
    )
    assert stress.neural_mechanical is StressLevel.HIGH
    assert BodyRegion.LOWER in stress.regions


def test_embedded_support_does_not_inflate_realised_stress():
    """A dose-capped embedded support item is not the session's cost."""
    stress = realised_session_stress(
        [
            {
                "name": "Pogo Hops",
                "effective_prescription": "2x5",
                "mechanical_risk_tags": ["mech_ballistic", "mech_lower_jump"],
            },
            {
                "name": "Overhead Carry (Single Arm)",
                "embedded_support": True,
                "effective_prescription": "1-2 controlled sets; stop before fatigue",
                "mechanical_risk_tags": ["mech_shoulder_overhead", "mech_upper_carry"],
            },
        ]
    )
    assert stress.neural_mechanical is StressLevel.MODERATE
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
