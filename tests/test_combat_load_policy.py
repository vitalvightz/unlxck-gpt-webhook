from fightcamp.combat_load_policy import (
    CollisionRelation,
    Legality,
    LoadClass,
    contact_load_class,
    evaluate_calendar_candidate,
    evaluate_hard_contact_collision,
    is_effective_hard_contact,
    relation_to_hard_contact,
)


def test_resolved_contact_state_maps_to_shared_load_vocabulary():
    assert contact_load_class({"effective_load": "hard"}) is LoadClass.HARD_CONTACT
    assert contact_load_class({"status": "hard_as_planned"}) is LoadClass.HARD_CONTACT
    assert contact_load_class({"effective_load": "technical"}) is LoadClass.TECHNICAL_CONTACT
    assert contact_load_class({"effective_load": "reduced"}) is LoadClass.TECHNICAL_CONTACT
    assert contact_load_class({"status": "deload_suggested"}) is LoadClass.TECHNICAL_CONTACT
    assert contact_load_class({"effective_load": "none"}) is LoadClass.OFF
    assert contact_load_class({"athlete_facing_label": "Hard sparring"}) is None


def test_only_resolved_hard_contact_counts_as_effective_hard_contact():
    assert is_effective_hard_contact({"effective_load": "hard"}) is True
    assert is_effective_hard_contact({"effective_load": "technical"}) is False
    assert is_effective_hard_contact({"effective_load": "reduced"}) is False
    assert is_effective_hard_contact({"status": "convert_to_technical_suggested"}) is False


def test_same_day_hard_contact_owns_physical_day():
    for candidate in (
        LoadClass.TECHNICAL_CONTACT,
        LoadClass.LOW_LOAD_SUPPORT,
        LoadClass.NEURAL_MICRODOSE,
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
    ):
        decision = evaluate_hard_contact_collision(candidate, CollisionRelation.SAME_DAY)
        assert decision.verdict is Legality.FORBIDDEN
        assert decision.reason_code == "hard_contact_same_day_physical_conflict"

    assert (
        evaluate_hard_contact_collision(
            LoadClass.ZERO_LOAD_TACTICAL,
            CollisionRelation.SAME_DAY,
        ).verdict
        is Legality.ALLOWED
    )


def test_day_after_hard_contact_forbids_meaningful_s_and_c():
    strength = evaluate_hard_contact_collision(
        LoadClass.MEANINGFUL_STRENGTH,
        CollisionRelation.DAY_AFTER,
    )
    conditioning = evaluate_hard_contact_collision(
        LoadClass.MEANINGFUL_CONDITIONING,
        CollisionRelation.DAY_AFTER,
    )

    assert strength.verdict is Legality.FORBIDDEN
    assert conditioning.verdict is Legality.FORBIDDEN
    assert strength.reason_code == "post_hard_contact_meaningful_stress"


def test_day_after_hard_contact_allows_low_cost_work_and_only_cautions_microdose():
    assert (
        evaluate_hard_contact_collision(
            LoadClass.LOW_LOAD_SUPPORT,
            CollisionRelation.DAY_AFTER,
        ).verdict
        is Legality.ALLOWED
    )
    assert (
        evaluate_hard_contact_collision(
            LoadClass.ZERO_LOAD_TACTICAL,
            CollisionRelation.DAY_AFTER,
        ).verdict
        is Legality.ALLOWED
    )
    assert (
        evaluate_hard_contact_collision(
            LoadClass.NEURAL_MICRODOSE,
            CollisionRelation.DAY_AFTER,
        ).verdict
        is Legality.ALLOWED_WITH_CAUTION
    )


def test_meaningful_work_before_hard_contact_is_managed_not_blanket_banned():
    decision = evaluate_hard_contact_collision(
        LoadClass.MEANINGFUL_STRENGTH,
        CollisionRelation.DAY_BEFORE,
    )

    assert decision.verdict is Legality.ALLOWED_WITH_CAUTION
    assert decision.reason_code == "pre_hard_contact_managed_stress"


def test_back_to_back_effective_hard_contact_is_forbidden():
    assert (
        evaluate_hard_contact_collision(
            LoadClass.HARD_CONTACT,
            CollisionRelation.DAY_BEFORE,
        ).verdict
        is Legality.FORBIDDEN
    )
    assert (
        evaluate_hard_contact_collision(
            LoadClass.HARD_CONTACT,
            CollisionRelation.DAY_AFTER,
        ).verdict
        is Legality.FORBIDDEN
    )


def test_sandwiched_day_reserves_space_for_low_cost_support():
    assert (
        evaluate_hard_contact_collision(
            LoadClass.LOW_LOAD_SUPPORT,
            CollisionRelation.SANDWICHED,
        ).verdict
        is Legality.ALLOWED
    )
    assert (
        evaluate_hard_contact_collision(
            LoadClass.TECHNICAL_CONTACT,
            CollisionRelation.SANDWICHED,
        ).verdict
        is Legality.ALLOWED_WITH_CAUTION
    )

    for candidate in (
        LoadClass.NEURAL_MICRODOSE,
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
        LoadClass.HARD_CONTACT,
    ):
        assert (
            evaluate_hard_contact_collision(
                candidate,
                CollisionRelation.SANDWICHED,
            ).verdict
            is Legality.FORBIDDEN
        )


def test_only_hard_contact_creates_collision_relation():
    assert (
        relation_to_hard_contact(
            previous_day_loads=[LoadClass.TECHNICAL_CONTACT],
            next_day_loads=[LoadClass.TECHNICAL_CONTACT],
        )
        is CollisionRelation.UNRELATED
    )
    assert (
        relation_to_hard_contact(
            previous_day_loads=[LoadClass.HARD_CONTACT],
        )
        is CollisionRelation.DAY_AFTER
    )
    assert (
        relation_to_hard_contact(
            previous_day_loads=[LoadClass.HARD_CONTACT],
            next_day_loads=[LoadClass.HARD_CONTACT],
        )
        is CollisionRelation.SANDWICHED
    )


def test_calendar_query_detects_tue_fri_hard_sandwich_without_mutation():
    previous = [LoadClass.HARD_CONTACT]
    following = [LoadClass.HARD_CONTACT]

    decision = evaluate_calendar_candidate(
        LoadClass.MEANINGFUL_STRENGTH,
        previous_day_loads=previous,
        next_day_loads=following,
    )

    assert decision.verdict is Legality.FORBIDDEN
    assert decision.reason_code == "sandwiched_meaningful_or_hard_stress"
    assert previous == [LoadClass.HARD_CONTACT]
    assert following == [LoadClass.HARD_CONTACT]


def test_unrelated_day_is_allowed():
    decision = evaluate_calendar_candidate(LoadClass.MEANINGFUL_STRENGTH)
    assert decision.verdict is Legality.ALLOWED
    assert decision.reason_code == "no_effective_hard_contact_collision"
