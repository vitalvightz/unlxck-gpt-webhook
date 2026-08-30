from fightcamp.combat_load_policy import (
    CalendarEvent,
    LoadClass,
    PlacementDirective,
    build_calendar_context,
    contact_load_class,
    evaluate_calendar_candidate,
    evaluate_candidate_at_position,
    is_effective_hard_contact,
    role_load_class,
)


def _event(position: int, load: LoadClass) -> CalendarEvent:
    return CalendarEvent(position=position, load_class=load)


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


def test_only_resolved_hard_contact_counts_as_effective_hard_contact():
    assert is_effective_hard_contact({"effective_load": "hard"}) is True
    assert is_effective_hard_contact({"effective_load": "technical"}) is False
    assert is_effective_hard_contact({"effective_load": "reduced"}) is False


def test_role_classifier_covers_existing_deterministic_semantics():
    assert role_load_class({"role_key": "tactical_watch"}) is LoadClass.ZERO_LOAD
    assert (
        role_load_class({"role_key": "fight_week_freshness_day"})
        is LoadClass.RECOVERY_ONLY
    )
    assert (
        role_load_class({"role_key": "technical_shadow_rhythm"})
        is LoadClass.LOW_LOAD_PHYSICAL
    )
    assert (
        role_load_class(
            {
                "role_key": "light_fight_pace_touch_day",
                "category": "conditioning",
                "preferred_system": "aerobic",
            }
        )
        is LoadClass.LOW_LOAD_AEROBIC
    )
    assert (
        role_load_class({"role_key": "technical_touch_day"})
        is LoadClass.TECHNICAL_CONTACT
    )
    assert (
        role_load_class(
            {"role_key": "primary_strength_day", "category": "strength"}
        )
        is LoadClass.MEANINGFUL_STRENGTH
    )
    assert (
        role_load_class(
            {
                "role_key": "fight_pace_repeatability_day",
                "category": "conditioning",
                "preferred_system": "glycolytic",
            }
        )
        is LoadClass.MEANINGFUL_CONDITIONING
    )


def test_role_classifier_uses_post_morph_strength_dose_not_display_label():
    role = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "athlete_facing_label": "Strength",
        "late_camp_strength_morph": True,
        "strength_dose_cap": {"max_sets": 1, "max_reps": 1},
    }
    assert role_load_class(role) is LoadClass.NEURAL_MICRODOSE


def test_role_classifier_accepts_explicit_canonical_stamp_and_unknowns_fail_explicit():
    assert (
        role_load_class({"calendar_load_class": "low_load_aerobic"})
        is LoadClass.LOW_LOAD_AEROBIC
    )
    assert role_load_class({"role_key": "future_unknown_role"}) is None


def test_calendar_context_is_position_based_not_weekday_based():
    events = [_event(100, LoadClass.HARD_CONTACT), _event(104, LoadClass.HARD_CONTACT)]

    first_gap = build_calendar_context(101, events)
    later_gap = build_calendar_context(103, events)

    assert first_gap.previous_hard_distance == 1
    assert first_gap.next_hard_distance == 3
    assert first_gap.between_effective_hard_contacts is True
    assert later_gap.previous_hard_distance == 3
    assert later_gap.next_hard_distance == 1
    assert later_gap.between_effective_hard_contacts is True


def test_every_position_between_two_hard_contacts_uses_sandwiched_policy():
    events = [_event(20, LoadClass.HARD_CONTACT), _event(24, LoadClass.HARD_CONTACT)]

    for candidate_position in (21, 22, 23):
        decision = evaluate_candidate_at_position(
            LoadClass.MEANINGFUL_STRENGTH,
            candidate_position=candidate_position,
            events=events,
        )
        assert decision.directive is PlacementDirective.FORBID
        assert decision.reason_code == "between_hard_contacts_meaningful_or_physical_stress"


def test_same_geometry_shifted_to_different_positions_has_identical_policy():
    geometry_a = [_event(2, LoadClass.HARD_CONTACT), _event(5, LoadClass.HARD_CONTACT)]
    geometry_b = [_event(50, LoadClass.HARD_CONTACT), _event(53, LoadClass.HARD_CONTACT)]

    a = evaluate_candidate_at_position(
        LoadClass.MEANINGFUL_CONDITIONING,
        candidate_position=3,
        events=geometry_a,
    )
    b = evaluate_candidate_at_position(
        LoadClass.MEANINGFUL_CONDITIONING,
        candidate_position=51,
        events=geometry_b,
    )

    assert a.directive is b.directive is PlacementDirective.FORBID
    assert a.reason_code == b.reason_code


def test_technical_contact_owns_its_day_without_creating_hard_recovery_pressure():
    events = [_event(10, LoadClass.TECHNICAL_CONTACT)]

    same_day_strength = evaluate_candidate_at_position(
        LoadClass.MEANINGFUL_STRENGTH,
        candidate_position=10,
        events=events,
    )
    next_day_strength = evaluate_candidate_at_position(
        LoadClass.MEANINGFUL_STRENGTH,
        candidate_position=11,
        events=events,
    )

    assert same_day_strength.directive is PlacementDirective.FORBID
    assert same_day_strength.reason_code == "contact_day_extra_physical_conflict"
    assert next_day_strength.directive is PlacementDirective.ALLOW


def test_recovery_only_can_coexist_with_technical_contact_but_extra_physical_cannot():
    events = [_event(7, LoadClass.TECHNICAL_CONTACT)]

    recovery = evaluate_candidate_at_position(
        LoadClass.RECOVERY_ONLY,
        candidate_position=7,
        events=events,
    )
    physical = evaluate_candidate_at_position(
        LoadClass.LOW_LOAD_PHYSICAL,
        candidate_position=7,
        events=events,
    )

    assert recovery.directive is PlacementDirective.ALLOW
    assert physical.directive is PlacementDirective.FORBID


def test_hard_contact_day_owns_physical_day_but_zero_and_recovery_support_can_coexist():
    events = [_event(30, LoadClass.HARD_CONTACT)]

    for candidate in (
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
        LoadClass.NEURAL_MICRODOSE,
        LoadClass.LOW_LOAD_PHYSICAL,
        LoadClass.LOW_LOAD_AEROBIC,
        LoadClass.TECHNICAL_CONTACT,
        LoadClass.REDUCED_CONTACT,
    ):
        decision = evaluate_candidate_at_position(
            candidate,
            candidate_position=30,
            events=events,
        )
        assert decision.directive is PlacementDirective.FORBID

    for candidate in (LoadClass.ZERO_LOAD, LoadClass.RECOVERY_ONLY):
        decision = evaluate_candidate_at_position(
            candidate,
            candidate_position=30,
            events=events,
        )
        assert decision.directive is PlacementDirective.ALLOW


def test_day_after_hard_contact_forbids_meaningful_s_and_c():
    events = [_event(40, LoadClass.HARD_CONTACT)]

    for candidate in (
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
    ):
        decision = evaluate_candidate_at_position(
            candidate,
            candidate_position=41,
            events=events,
        )
        assert decision.directive is PlacementDirective.FORBID
        assert decision.reason_code == "post_hard_contact_meaningful_stress"


def test_day_after_hard_contact_deprioritizes_neural_and_reduced_contact():
    events = [_event(40, LoadClass.HARD_CONTACT)]

    neural = evaluate_candidate_at_position(
        LoadClass.NEURAL_MICRODOSE,
        candidate_position=41,
        events=events,
    )
    reduced = evaluate_candidate_at_position(
        LoadClass.REDUCED_CONTACT,
        candidate_position=41,
        events=events,
    )

    assert neural.directive is PlacementDirective.DEPRIORITIZE
    assert reduced.directive is PlacementDirective.DEPRIORITIZE
    assert neural.allowed is True
    assert neural.should_deprioritize is True


def test_meaningful_work_before_hard_contact_is_deprioritized_not_blanket_banned():
    events = [_event(70, LoadClass.HARD_CONTACT)]

    decision = evaluate_candidate_at_position(
        LoadClass.MEANINGFUL_STRENGTH,
        candidate_position=69,
        events=events,
    )

    assert decision.directive is PlacementDirective.DEPRIORITIZE
    assert decision.reason_code == "pre_hard_contact_managed_stress"


def test_back_to_back_effective_hard_contact_is_forbidden():
    events = [_event(80, LoadClass.HARD_CONTACT)]

    decision = evaluate_candidate_at_position(
        LoadClass.HARD_CONTACT,
        candidate_position=81,
        events=events,
    )
    assert decision.directive is PlacementDirective.FORBID
    assert decision.reason_code == "consecutive_effective_hard_contact"


def test_between_hard_contacts_allows_low_cost_but_not_low_load_physical():
    events = [_event(90, LoadClass.HARD_CONTACT), _event(94, LoadClass.HARD_CONTACT)]

    for candidate in (
        LoadClass.OFF,
        LoadClass.ZERO_LOAD,
        LoadClass.RECOVERY_ONLY,
        LoadClass.LOW_LOAD_AEROBIC,
    ):
        decision = evaluate_candidate_at_position(
            candidate,
            candidate_position=92,
            events=events,
        )
        assert decision.directive is PlacementDirective.ALLOW

    physical = evaluate_candidate_at_position(
        LoadClass.LOW_LOAD_PHYSICAL,
        candidate_position=92,
        events=events,
    )
    assert physical.directive is PlacementDirective.FORBID


def test_technical_and_reduced_contact_have_distinct_sandwich_cost():
    events = [_event(100, LoadClass.HARD_CONTACT), _event(104, LoadClass.HARD_CONTACT)]

    technical = evaluate_candidate_at_position(
        LoadClass.TECHNICAL_CONTACT,
        candidate_position=102,
        events=events,
    )
    reduced = evaluate_candidate_at_position(
        LoadClass.REDUCED_CONTACT,
        candidate_position=102,
        events=events,
    )

    assert technical.directive is PlacementDirective.DEPRIORITIZE
    assert reduced.directive is PlacementDirective.DEPRIORITIZE
    assert technical.reason_code != reduced.reason_code


def test_context_and_evaluation_do_not_mutate_event_input():
    events = [
        _event(110, LoadClass.HARD_CONTACT),
        _event(114, LoadClass.HARD_CONTACT),
    ]
    snapshot = list(events)

    context = build_calendar_context(112, events)
    decision = evaluate_calendar_candidate(LoadClass.RECOVERY_ONLY, context)

    assert decision.directive is PlacementDirective.ALLOW
    assert events == snapshot


def test_non_contact_unrelated_day_is_allowed():
    context = build_calendar_context(200, [])
    decision = evaluate_calendar_candidate(LoadClass.MEANINGFUL_STRENGTH, context)

    assert decision.directive is PlacementDirective.ALLOW
    assert decision.reason_code == "no_calendar_collision"
