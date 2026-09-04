"""Declared light combat is a coach-owned, immutable calendar lock — globally.

Declared light-combat / technical days (``support_work_days``) are mandatory,
coach-owned calendar context on that exact weekday. They are *S&C-compatible, not
day-exclusive*: app-owned S&C may share the day only when the shared
``combat_load_policy`` says the combination is legal; when it does not, the S&C
moves or is dropped and the light-combat slot remains. That invariant must hold in
BOTH planners — normal camp (D-14+) and the D-13 inward countdown spine — through
the one shared ``declared_combat_ownership`` helper.

Regression: the normal ``D>13`` planner used to carry ``support_work_days`` into
the weekly map only as ``declared_support_work_days`` metadata and never created
the mandatory ``light_combat_day`` spine, so an app-owned aerobic support session
could take the declared Wednesday and the light-combat session simply vanished.
"""

from copy import deepcopy

import pytest

from fightcamp.calendar_integrity import (
    CalendarIntegrityError,
    apply_final_calendar_integrity,
)
from fightcamp.combat_load_policy import LoadClass, role_load_class
from fightcamp.declared_combat_ownership import (
    LIGHT_COMBAT_ROLE_KEY,
    build_declared_light_combat_role,
    declared_light_combat_weekdays,
)
from fightcamp.stage2_payload_late_fight import (
    _countdown_weekday_map,
    _visible_calendar_session_sequence,
    ensure_declared_coach_combat_spine,
)
from fightcamp.stage2_role_map import (
    _build_weekly_role_map,
    _lock_declared_light_combat_roles,
)


TRAINING_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def _athlete(**overrides):
    athlete = {
        "sport_style": "boxing",
        "sport": "boxing",
        "training_days": list(TRAINING_DAYS),
        "hard_sparring_days": ["monday", "friday"],
        "support_work_days": ["wednesday"],
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        # A Wednesday fight so declared Wednesday sessions land on exact multiples
        # of seven (D-21, D-14, D-7) in the countdown.
        "fight_date": "2027-07-21",
        "days_until_fight": 28,
    }
    athlete.update(overrides)
    return athlete


def _gpp_progression(weeks: int):
    return {
        "weeks": [
            {
                "week_index": i + 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["aerobic", "aerobic"],
            }
            for i in range(weeks)
        ]
    }


def _wednesday_role(week: dict) -> dict | None:
    return next(
        (
            role
            for role in week.get("session_roles", [])
            if str(role.get("scheduled_day_hint") or "").strip().lower() == "wednesday"
        ),
        None,
    )


def _physical_roles_on(week: dict, weekday: str) -> list[dict]:
    return [
        role
        for role in week.get("session_roles", [])
        if str(role.get("scheduled_day_hint") or "").strip().lower() == weekday
        and str(role.get("role_key") or "").strip().lower() != LIGHT_COMBAT_ROLE_KEY
        and role_load_class(role) not in (None, LoadClass.OFF, LoadClass.ZERO_LOAD)
    ]


# ---------------------------------------------------------------------------
# The reported regression: D-21 / D-14 normal-camp Wednesdays must survive.
# ---------------------------------------------------------------------------
def test_declared_light_combat_survives_every_normal_camp_wednesday():
    # A 4-week camp anchored on a Wednesday fight puts declared Wednesdays on
    # D-21, D-14, D-7, and D-0 (the fight itself). D-21 and D-14 are exactly the
    # normal-camp days that used to lose their light-combat session.
    role_map = _build_weekly_role_map(
        _athlete(), _gpp_progression(4), {"key": "conditioning_endurance"}
    )
    by_label = {}
    for week in role_map["weeks"]:
        role = _wednesday_role(week)
        assert role is not None, "every declared Wednesday must own a session role"
        by_label[role.get("scheduled_countdown_label")] = role

    for label in ("D-21", "D-14", "D-7"):
        role = by_label.get(label)
        assert role is not None, f"expected a Wednesday session at {label}"
        assert role["role_key"] == LIGHT_COMBAT_ROLE_KEY
        assert role["coach_owned"] is True
        assert role["declared_day_locked"] is True


def test_aerobic_support_never_replaces_declared_light_combat_wednesday():
    role_map = _build_weekly_role_map(
        _athlete(), _gpp_progression(4), {"key": "conditioning_endurance"}
    )
    for week in role_map["weeks"]:
        wednesday = _wednesday_role(week)
        # The D-0 fight week is owned by the fight-day protocol, not a session.
        if wednesday["role_key"] == "fight_day_protocol":
            continue
        assert wednesday["role_key"] == LIGHT_COMBAT_ROLE_KEY
        # Never: an aerobic (or any other exclusive/physical S&C) sitting on the
        # declared Wednesday in place of, or on top of, the light-combat slot.
        assert _physical_roles_on(week, "wednesday") == []


def test_declared_light_combat_multi_week_plan_passes_final_governor():
    role_map = _build_weekly_role_map(
        _athlete(), _gpp_progression(4), {"key": "conditioning_endurance"}
    )
    # Adding a real (exclusive technical-contact) light_combat_day role must leave
    # the deterministic calendar legal end-to-end.
    apply_final_calendar_integrity(deepcopy(role_map))


# ---------------------------------------------------------------------------
# S&C-compatible, not day-exclusive: legality is the shared policy's call.
# ---------------------------------------------------------------------------
def _lock_week():
    week_entry = {"week_index": 1, "declared_hard_sparring_days": []}
    athlete = {
        "training_days": list(TRAINING_DAYS),
        "support_work_days": ["wednesday"],
        "hard_sparring_days": [],
    }
    return week_entry, athlete


def test_illegal_same_day_sc_moves_off_light_combat_and_slot_remains():
    week_entry, athlete = _lock_week()
    session_roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "aerobic_support_day",
            "preferred_system": "aerobic",
            "scheduled_day_hint": "wednesday",
            "allowed_on_recovery_day": True,
        }
    ]
    roles, suppressed = _lock_declared_light_combat_roles(
        week_entry, session_roles, [], athlete
    )

    wednesday = [r for r in roles if r.get("scheduled_day_hint") == "wednesday"]
    assert [r["role_key"] for r in wednesday] == [LIGHT_COMBAT_ROLE_KEY]
    assert wednesday[0]["coach_owned"] is True

    # The aerobic yielded: it is either moved to a legal free day or suppressed,
    # but it never replaces the coach-owned light-combat slot.
    aerobic = next(
        (r for r in roles if r.get("role_key") == "aerobic_support_day"), None
    )
    if aerobic is not None:
        assert aerobic["scheduled_day_hint"] != "wednesday"
    else:
        assert any(s.get("replacement_role_key") == LIGHT_COMBAT_ROLE_KEY for s in suppressed)


def test_legal_low_cost_support_stacks_on_light_combat_day():
    week_entry, athlete = _lock_week()
    session_roles = [
        {
            "session_index": 1,
            "category": "support_insert",
            "role_key": "tactical_cue_card",
            "scheduled_day_hint": "wednesday",
            "stress_class": "support",
            "cost_class": "low",
            "governance": {"meaningful_stress": False},
        }
    ]
    roles, _ = _lock_declared_light_combat_roles(
        week_entry, session_roles, [], athlete
    )

    wednesday = {
        r["role_key"] for r in roles if r.get("scheduled_day_hint") == "wednesday"
    }
    # Zero-load coexistable support is legal to share the day, so it stacks and the
    # light-combat lock is added alongside it — not instead of it.
    assert wednesday == {LIGHT_COMBAT_ROLE_KEY, "tactical_cue_card"}


# ---------------------------------------------------------------------------
# One shared ownership definition, consumed by both planners.
# ---------------------------------------------------------------------------
def test_normal_camp_and_late_fight_agree_on_coach_owned_light_combat():
    athlete = _athlete()

    role_map = _build_weekly_role_map(
        athlete, _gpp_progression(4), {"key": "conditioning_endurance"}
    )
    normal_wednesday = _wednesday_role(role_map["weeks"][0])  # D-21 Wednesday

    spine = ensure_declared_coach_combat_spine(
        [], athlete, _countdown_weekday_map("wednesday", 28)
    )
    late_wednesday = next(
        role
        for role in _visible_calendar_session_sequence(spine)
        if role.get("role_key") == LIGHT_COMBAT_ROLE_KEY
    )

    for role in (normal_wednesday, late_wednesday):
        assert role["role_key"] == LIGHT_COMBAT_ROLE_KEY
        assert role["coach_owned"] is True
        assert str(role["scheduled_day_hint"]).lower() == "wednesday"
        # Classified as exclusive technical contact by the one collision authority.
        assert role_load_class(role) is LoadClass.TECHNICAL_CONTACT


# ---------------------------------------------------------------------------
# Shared helper unit contract.
# ---------------------------------------------------------------------------
def test_declared_light_combat_weekdays_excludes_hard_days_and_respects_training():
    athlete = {
        "training_days": ["monday", "tuesday", "wednesday"],
        "support_work_days": ["Wednesday", "Friday", "Monday"],
        "hard_sparring_days": ["monday"],
    }
    # Friday is dropped (not a training day); Monday is dropped (declared hard
    # sparring already owns it); Wednesday remains.
    assert declared_light_combat_weekdays(
        athlete, training_days=athlete["training_days"]
    ) == ["wednesday"]


def test_declared_light_combat_weekdays_falls_back_to_technical_skill_days():
    athlete = {"technical_skill_days": ["Tuesday", "Thursday"]}
    assert declared_light_combat_weekdays(athlete) == ["tuesday", "thursday"]


def test_build_declared_light_combat_role_is_coach_owned_locked():
    role = build_declared_light_combat_role("Wednesday")
    assert role["role_key"] == LIGHT_COMBAT_ROLE_KEY
    assert role["scheduled_day_hint"] == "wednesday"
    assert role["coach_owned"] is True
    assert role["declared_day_locked"] is True
    assert role["placement_basis"] == "locked"
    assert role_load_class(role) is LoadClass.TECHNICAL_CONTACT
