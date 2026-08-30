import pytest

from fightcamp.combat_load_policy import (
    CalendarEvent,
    CalendarLoadProfile,
    DayOccupancy,
    LoadClass,
    PlacementDirective,
    build_calendar_context,
    contact_load_class,
    contact_load_profile,
    evaluate_calendar_candidate,
    evaluate_candidate_at_position,
    is_effective_hard_contact,
    role_load_class,
    role_load_profile,
)


def _profile(
    load: LoadClass,
    occupancy: DayOccupancy | None = None,
) -> CalendarLoadProfile:
    if occupancy is None:
        if load in {LoadClass.OFF, LoadClass.ZERO_LOAD}:
            occupancy = DayOccupancy.COEXISTABLE
        elif load in {
            LoadClass.HARD_CONTACT,
            LoadClass.REDUCED_CONTACT,
            LoadClass.TECHNICAL_CONTACT,
        }:
            occupancy = DayOccupancy.EXCLUSIVE_PHYSICAL
        else:
            occupancy = DayOccupancy.PHYSICAL
    return CalendarLoadProfile(load_class=load, occupancy=occupancy)


def _event(
    position: int,
    load: LoadClass,
    *,
    occupancy: DayOccupancy | None = None,
    scope=None,
) -> CalendarEvent:
    return CalendarEvent(
        position=position,
        profile=_profile(load, occupancy),
        collision_scope=scope,
    )


def test_resolved_contact_state_preserves_hard_reduced_and_technical_distinctions():
    assert contact_load_class({"effective_load": "hard"}) is LoadClass.HARD_CONTACT
    assert contact_load_class({"status": "hard_as_planned"}) is LoadClass.HARD_CONTACT
    assert contact_load_class({"effective_load": "reduced"}) is LoadClass.REDUCED_CONTACT
    assert contact_load_class({"status": "deload_suggested"}) is LoadClass.REDUCED_CONTACT
    assert contact_load_class({"effective_load": "technical"}) is LoadClass.TECHNICAL_CONTACT
    assert (
        contact_load_class({"status": "convert_to_technical_suggested"})
        is LoadClass.TECHNICAL_CONTACT
    )
    assert contact_load_class({"effective_load": "none"}) is LoadClass.OFF


def test_contact_classifier_never_infers_from_display_label_or_declared_role_alone():
    assert contact_load_class({"athlete_facing_label": "Hard sparring"}) is None
    assert role_load_class({"role_key": "hard_sparring_day"}) is None


def test_resolved_contact_truth_outranks_and_validates_explicit_stamp():
    assert (
        contact_load_class(
            {
                "effective_load": "technical",
                "calendar_load_class": LoadClass.TECHNICAL_CONTACT,
            }
        )
        is LoadClass.TECHNICAL_CONTACT
    )
    with pytest.raises(ValueError):
        contact_load_class(
            {
                "effective_load": "technical",
                "calendar_load_class": "hard_contact",
            }
        )


def test_conflicting_resolved_contact_fields_fail_explicit():
    with pytest.raises(ValueError):
        contact_load_profile(
            {
                "effective_load": "technical",
                "status": "hard_as_planned",
            }
        )


def test_only_resolved_hard_contact_counts_as_effective_hard_contact():
    assert is_effective_hard_contact({"effective_load": "hard"}) is True
    assert is_effective_hard_contact({"effective_load": "technical"}) is False
    assert is_effective_hard_contact({"effective_load": "reduced"}) is False


def test_role_classifier_covers_stable_existing_semantics_and_occupancy():
    tactical = role_load_profile({"role_key": "tactical_watch"})
    assert tactical == _profile(LoadClass.ZERO_LOAD, DayOccupancy.COEXISTABLE)

    recovery_insert = role_load_profile({"role_key": "recovery_reset"})
    assert recovery_insert == _profile(LoadClass.RECOVERY_ONLY, DayOccupancy.COEXISTABLE)

    freshness = role_load_profile({"role_key": "fight_week_freshness_day"})
    assert freshness == _profile(
        LoadClass.RECOVERY_ONLY,
        DayOccupancy.EXCLUSIVE_PHYSICAL,
    )

    mobility = role_load_profile({"role_key": "mobility_rehab"})
    assert mobility == _profile(LoadClass.RECOVERY_ONLY, DayOccupancy.PHYSICAL)

    assert (
        role_load_class({"role_key": "technical_shadow_rhythm"})
        is LoadClass.LOW_LOAD_PHYSICAL
    )
    assert role_load_class({"role_key": "technical_touch_day"}) is LoadClass.TECHNICAL_CONTACT
    assert role_load_class({"role_key": "light_combat_day"}) is LoadClass.TECHNICAL_CONTACT


def test_strength_classifier_uses_resolved_dose_instead_of_touch_name():
    meaningful = role_load_profile(
        {
            "role_key": "strength_touch_day",
            "category": "strength",
            "stress_class": "meaningful_stress",
            "cost_class": "medium",
        }
    )
    assert meaningful.load_class is LoadClass.MEANINGFUL_STRENGTH

    micro = role_load_profile(
        {
            "role_key": "strength_touch_day",
            "category": "strength",
            "strength_dose_cap": {"max_sets": 1, "max_reps": 2},
        }
    )
    assert micro.load_class is LoadClass.NEURAL_MICRODOSE


def test_post_morph_strength_dose_not_display_label_controls_classification():
    role = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "athlete_facing_label": "Strength",
        "late_camp_strength_morph": True,
        "strength_dose_cap": {"max_sets": 1, "max_reps": 1},
    }
    assert role_load_class(role) is LoadClass.NEURAL_MICRODOSE


def test_late_fight_medium_stress_touch_is_not_silently_low_load():
    role = {
        "role_key": "light_fight_pace_touch_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "stress_class": "meaningful_stress",
        "cost_class": "medium",
    }
    assert role_load_class(role) is LoadClass.MEANINGFUL_CONDITIONING


def test_post_morph_fight_pace_touch_becomes_low_load_aerobic():
    role = {
        "role_key": "light_fight_pace_touch_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "stress_class": "support",
        "cost_class": "low",
        "counts_toward_conditioning_cap": False,
        "late_camp_role_morph": True,
    }
    assert role_load_class(role) is LoadClass.LOW_LOAD_AEROBIC


def test_role_classifier_accepts_explicit_canonical_stamp_and_unknowns_fail_explicit():
    profile = role_load_profile(
        {
            "calendar_load_class": LoadClass.LOW_LOAD_AEROBIC,
            "calendar_day_occupancy": DayOccupancy.PHYSICAL,
        }
    )
    assert profile == _profile(LoadClass.LOW_LOAD_AEROBIC, DayOccupancy.PHYSICAL)
    assert role_load_profile({"role_key": "future_unknown_role"}) is None


def test_explicit_profile_cannot_bypass_contact_or_physical_ownership():
    with pytest.raises(ValueError):
        role_load_profile(
            {
                "role_key": "primary_strength_day",
                "category": "strength",
                "calendar_load_class": "hard_contact",
            }
        )

    with pytest.raises(ValueError):
        role_load_profile(
            {
                "role_key": "primary_strength_day",
                "category": "strength",
                "calendar_load_class": "meaningful_strength",
                "calendar_day_occupancy": "coexistable",
            }
        )

    with pytest.raises(ValueError):
        role_load_profile(
            {
                "role_key": "technical_touch_day",
                "calendar_load_class": "meaningful_strength",
            }
        )


def test_calendar_context_is_position_based_not_weekday_based():
    events = [
        _event(100, LoadClass.HARD_CONTACT, scope="microcycle-a"),
        _event(104, LoadClass.HARD_CONTACT, scope="microcycle-a"),
    ]

    first_gap = build_calendar_context(101, events, candidate_scope="microcycle-a")
    later_gap = build_calendar_context(103, events, candidate_scope="microcycle-a")

    assert first_gap.previous_hard_distance == 1
    assert first_gap.next_hard_distance == 3
    assert first_gap.between_effective_hard_contacts is True
    assert later_gap.previous_hard_distance == 3
    assert later_gap.next_hard_distance == 1
    assert later_gap.between_effective_hard_contacts is True


def test_every_position_between_two_hard_contacts_in_same_scope_uses_protected_policy():
    events = [
        _event(20, LoadClass.HARD_CONTACT, scope="w1"),
        _event(24, LoadClass.HARD_CONTACT, scope="w1"),
    ]

    for candidate_position in (21, 22, 23):
        decision = evaluate_candidate_at_position(
            _profile(LoadClass.MEANINGFUL_STRENGTH),
            candidate_position=candidate_position,
            events=events,
            candidate_scope="w1",
        )
        assert decision.directive is PlacementDirective.FORBID
        assert decision.reason_code == "between_hard_contacts_meaningful_or_physical_stress"


def test_full_camp_events_do_not_turn_every_day_between_first_and_last_hard_into_sandwich():
    events = [
        _event(10, LoadClass.HARD_CONTACT, scope="w1"),
        _event(13, LoadClass.HARD_CONTACT, scope="w1"),
        _event(20, LoadClass.HARD_CONTACT, scope="w2"),
        _event(23, LoadClass.HARD_CONTACT, scope="w2"),
    ]

    context = build_calendar_context(16, events, candidate_scope="w-mid")
    assert context.between_effective_hard_contacts is False
    decision = evaluate_calendar_candidate(_profile(LoadClass.MEANINGFUL_STRENGTH), context)
    assert decision.directive is PlacementDirective.ALLOW


def test_without_explicit_scope_sandwich_policy_falls_back_to_adjacency_only():
    events = [
        _event(30, LoadClass.HARD_CONTACT, scope="w1"),
        _event(34, LoadClass.HARD_CONTACT, scope="w1"),
    ]
    context = build_calendar_context(32, events)
    assert context.between_effective_hard_contacts is False


def test_immediate_post_hard_rule_crosses_scope_boundary():
    events = [_event(40, LoadClass.HARD_CONTACT, scope="old-week")]
    decision = evaluate_candidate_at_position(
        _profile(LoadClass.MEANINGFUL_STRENGTH),
        candidate_position=41,
        events=events,
        candidate_scope="new-week",
    )
    assert decision.directive is PlacementDirective.FORBID
    assert decision.reason_code == "post_hard_contact_meaningful_stress"


def test_same_geometry_shifted_to_different_positions_has_identical_policy():
    geometry_a = [
        _event(2, LoadClass.HARD_CONTACT, scope="x"),
        _event(5, LoadClass.HARD_CONTACT, scope="x"),
    ]
    geometry_b = [
        _event(50, LoadClass.HARD_CONTACT, scope="x"),
        _event(53, LoadClass.HARD_CONTACT, scope="x"),
    ]

    a = evaluate_candidate_at_position(
        _profile(LoadClass.MEANINGFUL_CONDITIONING),
        candidate_position=3,
        events=geometry_a,
        candidate_scope="x",
    )
    b = evaluate_candidate_at_position(
        _profile(LoadClass.MEANINGFUL_CONDITIONING),
        candidate_position=51,
        events=geometry_b,
        candidate_scope="x",
    )

    assert a.directive is b.directive is PlacementDirective.FORBID
    assert a.reason_code == b.reason_code


def test_technical_contact_owns_its_day_without_creating_next_day_hard_pressure():
    events = [_event(60, LoadClass.TECHNICAL_CONTACT)]

    same_day_strength = evaluate_candidate_at_position(
        _profile(LoadClass.MEANINGFUL_STRENGTH),
        candidate_position=60,
        events=events,
    )
    next_day_strength = evaluate_candidate_at_position(
        _profile(LoadClass.MEANINGFUL_STRENGTH),
        candidate_position=61,
        events=events,
    )

    assert same_day_strength.directive is PlacementDirective.FORBID
    assert same_day_strength.reason_code == "contact_day_extra_physical_conflict"
    assert next_day_strength.directive is PlacementDirective.ALLOW


def test_contact_day_allows_true_coexistable_recovery_insert_but_not_freshness_session():
    events = [_event(70, LoadClass.TECHNICAL_CONTACT)]
    recovery_insert = role_load_profile({"role_key": "recovery_reset"})
    freshness_session = role_load_profile({"role_key": "fight_week_freshness_day"})

    allowed = evaluate_candidate_at_position(
        recovery_insert,
        candidate_position=70,
        events=events,
    )
    blocked = evaluate_candidate_at_position(
        freshness_session,
        candidate_position=70,
        events=events,
    )

    assert allowed.directive is PlacementDirective.ALLOW
    assert blocked.directive is PlacementDirective.FORBID


def test_mobility_rehab_is_low_load_but_not_contact_day_coexistable():
    events = [_event(75, LoadClass.HARD_CONTACT)]
    mobility = role_load_profile({"role_key": "mobility_rehab"})
    decision = evaluate_candidate_at_position(mobility, candidate_position=75, events=events)
    assert decision.directive is PlacementDirective.FORBID


def test_duplicate_contact_on_same_day_is_forbidden():
    events = [_event(80, LoadClass.HARD_CONTACT)]
    duplicate_hard = evaluate_candidate_at_position(
        _profile(LoadClass.HARD_CONTACT),
        candidate_position=80,
        events=events,
    )
    assert duplicate_hard.directive is PlacementDirective.FORBID

    technical_events = [_event(81, LoadClass.TECHNICAL_CONTACT)]
    duplicate_technical = evaluate_candidate_at_position(
        _profile(LoadClass.TECHNICAL_CONTACT),
        candidate_position=81,
        events=technical_events,
    )
    assert duplicate_technical.directive is PlacementDirective.FORBID


def test_contact_candidate_cannot_be_added_to_existing_physical_session():
    events = [_event(85, LoadClass.MEANINGFUL_STRENGTH)]
    decision = evaluate_candidate_at_position(
        _profile(LoadClass.TECHNICAL_CONTACT),
        candidate_position=85,
        events=events,
    )
    assert decision.directive is PlacementDirective.FORBID
    assert decision.reason_code == "contact_candidate_physical_conflict"


def test_day_after_hard_contact_forbids_meaningful_s_and_c():
    events = [_event(90, LoadClass.HARD_CONTACT)]

    for load in (
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
    ):
        decision = evaluate_candidate_at_position(
            _profile(load),
            candidate_position=91,
            events=events,
        )
        assert decision.directive is PlacementDirective.FORBID
        assert decision.reason_code == "post_hard_contact_meaningful_stress"


def test_day_after_hard_contact_deprioritizes_true_microdose_and_reduced_contact():
    events = [_event(100, LoadClass.HARD_CONTACT)]

    neural = evaluate_candidate_at_position(
        _profile(LoadClass.NEURAL_MICRODOSE),
        candidate_position=101,
        events=events,
    )
    reduced = evaluate_candidate_at_position(
        _profile(LoadClass.REDUCED_CONTACT),
        candidate_position=101,
        events=events,
    )

    assert neural.directive is PlacementDirective.DEPRIORITIZE
    assert reduced.directive is PlacementDirective.DEPRIORITIZE
    assert neural.allowed is True
    assert neural.should_deprioritize is True


def test_meaningful_work_before_hard_contact_is_deprioritized_not_blanket_banned():
    events = [_event(110, LoadClass.HARD_CONTACT)]
    decision = evaluate_candidate_at_position(
        _profile(LoadClass.MEANINGFUL_STRENGTH),
        candidate_position=109,
        events=events,
    )
    assert decision.directive is PlacementDirective.DEPRIORITIZE
    assert decision.reason_code == "pre_hard_contact_managed_stress"


def test_back_to_back_effective_hard_contact_is_forbidden():
    events = [_event(120, LoadClass.HARD_CONTACT)]
    decision = evaluate_candidate_at_position(
        _profile(LoadClass.HARD_CONTACT),
        candidate_position=121,
        events=events,
    )
    assert decision.directive is PlacementDirective.FORBID
    assert decision.reason_code == "consecutive_effective_hard_contact"


def test_scoped_between_hard_contacts_allows_low_cost_but_not_low_load_physical():
    events = [
        _event(130, LoadClass.HARD_CONTACT, scope="w"),
        _event(134, LoadClass.HARD_CONTACT, scope="w"),
    ]

    for profile in (
        _profile(LoadClass.OFF, DayOccupancy.COEXISTABLE),
        _profile(LoadClass.ZERO_LOAD, DayOccupancy.COEXISTABLE),
        _profile(LoadClass.RECOVERY_ONLY, DayOccupancy.COEXISTABLE),
        _profile(LoadClass.LOW_LOAD_AEROBIC),
    ):
        decision = evaluate_candidate_at_position(
            profile,
            candidate_position=132,
            events=events,
            candidate_scope="w",
        )
        assert decision.directive is PlacementDirective.ALLOW

    physical = evaluate_candidate_at_position(
        _profile(LoadClass.LOW_LOAD_PHYSICAL),
        candidate_position=132,
        events=events,
        candidate_scope="w",
    )
    assert physical.directive is PlacementDirective.FORBID


def test_technical_and_reduced_contact_have_distinct_scoped_between_contact_cost():
    events = [
        _event(140, LoadClass.HARD_CONTACT, scope="w"),
        _event(144, LoadClass.HARD_CONTACT, scope="w"),
    ]

    technical = evaluate_candidate_at_position(
        _profile(LoadClass.TECHNICAL_CONTACT),
        candidate_position=142,
        events=events,
        candidate_scope="w",
    )
    reduced = evaluate_candidate_at_position(
        _profile(LoadClass.REDUCED_CONTACT),
        candidate_position=142,
        events=events,
        candidate_scope="w",
    )

    assert technical.directive is PlacementDirective.DEPRIORITIZE
    assert reduced.directive is PlacementDirective.DEPRIORITIZE
    assert technical.reason_code != reduced.reason_code


def test_context_and_evaluation_do_not_mutate_event_input():
    events = [
        _event(150, LoadClass.HARD_CONTACT, scope="w"),
        _event(154, LoadClass.HARD_CONTACT, scope="w"),
    ]
    snapshot = list(events)

    context = build_calendar_context(152, events, candidate_scope="w")
    decision = evaluate_calendar_candidate(
        _profile(LoadClass.RECOVERY_ONLY, DayOccupancy.COEXISTABLE),
        context,
    )

    assert decision.directive is PlacementDirective.ALLOW
    assert events == snapshot


def test_invalid_event_shape_fails_explicit():
    with pytest.raises(TypeError):
        build_calendar_context(1, [object()])


def test_non_contact_unrelated_day_is_allowed():
    context = build_calendar_context(200, [])
    decision = evaluate_calendar_candidate(
        _profile(LoadClass.MEANINGFUL_STRENGTH),
        context,
    )

    assert decision.directive is PlacementDirective.ALLOW
    assert decision.reason_code == "no_calendar_collision"
