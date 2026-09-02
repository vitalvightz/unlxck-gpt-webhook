"""Step 10 regression freeze for canonical planner ownership boundaries."""

from __future__ import annotations

import pytest

from fightcamp import calendar_context as cc
from fightcamp.combat_load_policy import (
    CalendarEvent,
    CalendarLoadProfile,
    DayOccupancy,
    LoadClass,
    PlacementDirective,
    evaluate_candidate_at_position,
)


def _profile(load: LoadClass) -> CalendarLoadProfile:
    occupancy = (
        DayOccupancy.COEXISTABLE
        if load in {LoadClass.OFF, LoadClass.ZERO_LOAD}
        else DayOccupancy.EXCLUSIVE_PHYSICAL
        if load in {
            LoadClass.HARD_CONTACT,
            LoadClass.REDUCED_CONTACT,
            LoadClass.TECHNICAL_CONTACT,
        }
        else DayOccupancy.PHYSICAL
    )
    return CalendarLoadProfile(load, occupancy)


def _decision(
    load: LoadClass,
    position: int,
    hard_positions: tuple[int, ...],
    *,
    scope: str = "week",
):
    events = [CalendarEvent(p, _profile(LoadClass.HARD_CONTACT), scope) for p in hard_positions]
    return evaluate_candidate_at_position(
        _profile(load),
        candidate_position=position,
        events=events,
        candidate_scope=scope,
    )


@pytest.mark.parametrize(
    ("load", "expected"),
    [
        (LoadClass.OFF, PlacementDirective.ALLOW),
        (LoadClass.ZERO_LOAD, PlacementDirective.ALLOW),
        (LoadClass.RECOVERY_ONLY, PlacementDirective.ALLOW),
        (LoadClass.LOW_LOAD_AEROBIC, PlacementDirective.ALLOW),
        (LoadClass.LOW_LOAD_PHYSICAL, PlacementDirective.DEPRIORITIZE),
        (LoadClass.TECHNICAL_CONTACT, PlacementDirective.DEPRIORITIZE),
        (LoadClass.REDUCED_CONTACT, PlacementDirective.DEPRIORITIZE),
        (LoadClass.MEANINGFUL_STRENGTH, PlacementDirective.FORBID),
        (LoadClass.MEANINGFUL_CONDITIONING, PlacementDirective.FORBID),
        (LoadClass.NEURAL_MICRODOSE, PlacementDirective.FORBID),
    ],
)
def test_canonical_between_two_hard_contacts_matrix(load, expected):
    assert _decision(load, 2, (1, 3)).directive is expected


@pytest.mark.parametrize(
    ("load", "expected"),
    [
        (LoadClass.MEANINGFUL_STRENGTH, PlacementDirective.FORBID),
        (LoadClass.MEANINGFUL_CONDITIONING, PlacementDirective.FORBID),
        (LoadClass.NEURAL_MICRODOSE, PlacementDirective.DEPRIORITIZE),
        (LoadClass.REDUCED_CONTACT, PlacementDirective.DEPRIORITIZE),
        (LoadClass.TECHNICAL_CONTACT, PlacementDirective.ALLOW),
        (LoadClass.LOW_LOAD_PHYSICAL, PlacementDirective.ALLOW),
        (LoadClass.LOW_LOAD_AEROBIC, PlacementDirective.ALLOW),
        (LoadClass.RECOVERY_ONLY, PlacementDirective.ALLOW),
    ],
)
def test_canonical_immediately_after_hard_matrix(load, expected):
    assert _decision(load, 2, (1,)).directive is expected


@pytest.mark.parametrize(
    ("load", "expected"),
    [
        (LoadClass.MEANINGFUL_STRENGTH, PlacementDirective.DEPRIORITIZE),
        (LoadClass.MEANINGFUL_CONDITIONING, PlacementDirective.DEPRIORITIZE),
        (LoadClass.NEURAL_MICRODOSE, PlacementDirective.DEPRIORITIZE),
        (LoadClass.REDUCED_CONTACT, PlacementDirective.DEPRIORITIZE),
        (LoadClass.TECHNICAL_CONTACT, PlacementDirective.ALLOW),
        (LoadClass.LOW_LOAD_PHYSICAL, PlacementDirective.ALLOW),
        (LoadClass.LOW_LOAD_AEROBIC, PlacementDirective.ALLOW),
    ],
)
def test_canonical_immediately_before_hard_matrix(load, expected):
    assert _decision(load, 1, (2,)).directive is expected


def test_same_day_exclusive_physical_and_contact_is_forbidden():
    contact = CalendarEvent(1, _profile(LoadClass.HARD_CONTACT), "week")
    decision = evaluate_candidate_at_position(
        _profile(LoadClass.MEANINGFUL_STRENGTH),
        candidate_position=1,
        events=[contact],
        candidate_scope="week",
    )
    assert decision.directive is PlacementDirective.FORBID
    assert decision.reason_code == "contact_day_extra_physical_conflict"


def test_consecutive_effective_hard_contact_is_forbidden():
    decision = _decision(LoadClass.HARD_CONTACT, 2, (1,))
    assert decision.directive is PlacementDirective.FORBID
    assert decision.reason_code == "consecutive_effective_hard_contact"


@pytest.mark.parametrize(
    "load",
    [
        LoadClass.REDUCED_CONTACT,
        LoadClass.TECHNICAL_CONTACT,
        LoadClass.LOW_LOAD_AEROBIC,
        LoadClass.NEURAL_MICRODOSE,
    ],
)
def test_normal_and_countdown_representations_have_identical_legality(load):
    normal = _decision(load, cc.weekday_position("tuesday"), (cc.weekday_position("monday"),))
    countdown = _decision(load, -17, (-18,))
    assert (normal.directive, normal.reason_code) == (countdown.directive, countdown.reason_code)


def test_two_hard_sandwich_has_identical_legality_across_representations():
    normal = _decision(
        LoadClass.MEANINGFUL_STRENGTH,
        cc.weekday_position("wednesday"),
        (cc.weekday_position("monday"), cc.weekday_position("friday")),
    )
    countdown = _decision(LoadClass.MEANINGFUL_STRENGTH, -19, (-21, -18))
    assert (normal.directive, normal.reason_code) == (countdown.directive, countdown.reason_code)


@pytest.mark.parametrize(
    ("resolved", "expected"),
    [
        (None, [LoadClass.HARD_CONTACT, LoadClass.HARD_CONTACT]),
        ([], []),
        (
            [
                {"day": "monday", "effective_load": "technical"},
                {"day": "friday", "effective_load": "reduced"},
            ],
            [LoadClass.TECHNICAL_CONTACT, LoadClass.REDUCED_CONTACT],
        ),
        ([{"day": "monday", "effective_load": "suppressed"}], []),
    ],
)
def test_resolved_state_presence_controls_declared_fallback(resolved, expected):
    events = cc.normal_week_contact_events(
        resolved,
        ["monday", "friday"],
        scope=("normal_week", 1),
    )
    assert [event.profile.load_class for event in events] == expected


def test_renderer_weekday_resolution_is_read_only_and_does_not_restore_roles():
    from fightcamp.weekly_plan_render import _resolve_role_weekdays

    roles = [{"role_key": "primary_strength_day", "scheduled_day_hint": ""}]
    before = [dict(role) for role in roles]
    assert _resolve_role_weekdays(roles) == {0: ""}
    assert roles == before
    assert _resolve_role_weekdays([]) == {}
