"""A bookkeeping-unused weekday can still hold a real coach-owned session.

Live week 2 marked Saturday in `intentionally_unused_days` (role
`recovery_only_day`) while that same Saturday carried the coach-owned
`light_combat_day`. The host loop rejected any host whose weekday appeared in
that list, so the legal technical host was skipped and the Power microdose fell
through to a glycolytic fight-pace conditioning day.

The weekday flag alone must not decide this. `combat_load_policy` is the sole
authority on what may share a combat day, and it already grants the low-cost /
neural-microdose exception only to a provenance-stamped declared light-combat
appointment.
"""

from __future__ import annotations

import pytest

from fightcamp.declared_combat_ownership import build_declared_light_combat_role
from fightcamp.goal_preservation import (
    _MICRODOSE_SPECS,
    _attach_goal_microdose,
    _microdose_coexists_on_protected_day,
    _microdose_host_roles,
    role_d_day,
)


_POWER_ENTRY = {
    "goal": "power",
    "priority": "primary",
    "state": "build",
    "required_intent": "ballistic_power",
    "evidence": [],
}


def _light_combat():
    role = build_declared_light_combat_role("saturday")
    role["session_index"] = 1
    return role


def _conditioning():
    return {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
        "scheduled_day_hint": "Friday",
        "session_index": 2,
    }


def _hard_spar_on_saturday():
    return {
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "preferred_pool": "declared_hard_sparring_days",
        "scheduled_day_hint": "Saturday",
        "session_index": 3,
    }


def _week(*roles, protected=("Saturday",)):
    week = {
        "week_index": 2,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "saturday", "d_day": 26},
            {"weekday": "friday", "d_day": 25},
        ],
        "declared_training_days": ["friday", "saturday"],
        "session_roles": list(roles),
    }
    if protected:
        week["intentionally_unused_days"] = [
            {"day": day, "role": "recovery_only_day"} for day in protected
        ]
    return week


def _attach(week, entry=None):
    brief = {
        "athlete_snapshot": {
            "sport": "boxing",
            "days_until_fight": 27,
            "training_frequency": 3,
            "key_goals": ["power"],
            "primary_goal": "power",
            "weak_areas": ["footwork"],
            "primary_weak_area": "footwork",
        },
        "weekly_role_map": {"weeks": [week]},
        "candidate_pools": {},
    }
    audit = _attach_goal_microdose(brief, 0, entry or _POWER_ENTRY)
    return audit, brief["weekly_role_map"]["weeks"][0]


def _winner(week_state):
    return [
        (role["role_key"], role_d_day(week_state, role))
        for role in week_state["session_roles"]
        if role.get("priority_microdose")
    ]


# 1. Considered through canonical legality, not rejected on the weekday flag
def test_a_protected_weekday_holding_light_combat_is_still_considered():
    week = _week(_conditioning(), _light_combat())
    assert [role["role_key"] for role in _microdose_host_roles(week)] == [
        "light_combat_day",
        "fight_pace_repeatability_day",
    ]
    assert _microdose_coexists_on_protected_day(_light_combat(), _MICRODOSE_SPECS["power"])


# 2. A legal neural microdose makes the technical host win over conditioning
def test_legal_neural_microdose_beats_conditioning_on_a_protected_day():
    audit, week_state = _attach(_week(_conditioning(), _light_combat()))
    assert audit["result"] == "microdose_attached"
    assert audit["role_key"] == "light_combat_day"
    assert _winner(week_state) == [("light_combat_day", 26)]


# 3. A truly unused day stays protected
def test_a_truly_unused_day_remains_protected():
    """No session on Saturday: the day is genuinely rest and must not be used."""
    audit, week_state = _attach(_week(_conditioning()))
    assert audit["role_key"] == "fight_pace_repeatability_day"
    assert _winner(week_state) == [("fight_pace_repeatability_day", 25)]


def test_a_protected_day_with_no_canonical_profile_stays_protected():
    generic = {
        "category": "technical",
        "role_key": "technical_touch_day",
        "scheduled_day_hint": "Saturday",
        "session_index": 1,
    }
    assert not _microdose_coexists_on_protected_day(generic, _MICRODOSE_SPECS["power"])


# 4. Canonical illegality means conditioning may win
def test_an_exposure_the_policy_forbids_does_not_take_the_light_combat_day():
    """The strength touch is MEANINGFUL_STRENGTH, not a true microdose, so the
    policy refuses it on a light-combat day and conditioning takes it."""
    assert not _microdose_coexists_on_protected_day(_light_combat(), _MICRODOSE_SPECS["strength"])
    strength_entry = {
        "goal": "strength",
        "priority": "primary",
        "state": "build",
        "required_intent": "meaningful_strength",
        "evidence": [],
    }
    audit, week_state = _attach(_week(_conditioning(), _light_combat()), strength_entry)
    assert audit["role_key"] == "fight_pace_repeatability_day"
    assert _winner(week_state) == [("fight_pace_repeatability_day", 25)]


@pytest.mark.parametrize(
    "goal,load_class",
    [
        ("power", "NEURAL_MICRODOSE"),
        ("speed", "NEURAL_MICRODOSE"),
        ("strength", "MEANINGFUL_STRENGTH"),
        ("footwork", "LOW_LOAD_PHYSICAL"),
        ("mobility", "LOW_LOAD_PHYSICAL"),
    ],
)
def test_every_spec_declares_an_honest_collision_class(goal, load_class):
    assert _MICRODOSE_SPECS[goal]["load_class"] == load_class


# 5. Hard-spar provenance on the same weekday stays forbidden
def test_hard_sparring_on_the_protected_weekday_is_still_forbidden():
    week = _week(_conditioning(), _hard_spar_on_saturday())
    assert [role["role_key"] for role in _microdose_host_roles(week)] == [
        "fight_pace_repeatability_day"
    ]
    audit, week_state = _attach(week)
    assert audit["role_key"] == "fight_pace_repeatability_day"
    spar = [r for r in week_state["session_roles"] if r["category"] == "sparring"]
    assert all("priority_microdose" not in role for role in spar)


# 6. Nothing is added
def test_session_count_and_training_days_are_unchanged():
    week = _week(_conditioning(), _light_combat())
    before_sessions = len(week["session_roles"])
    before_days = list(week["declared_training_days"])
    _, week_state = _attach(week)
    assert len(week_state["session_roles"]) == before_sessions
    assert week_state["declared_training_days"] == before_days


def test_the_protected_day_attachment_is_idempotent():
    week = _week(_conditioning(), _light_combat())
    brief = {
        "athlete_snapshot": {
            "sport": "boxing",
            "days_until_fight": 27,
            "training_frequency": 3,
            "key_goals": ["power"],
            "primary_goal": "power",
            "weak_areas": ["footwork"],
            "primary_weak_area": "footwork",
        },
        "weekly_role_map": {"weeks": [week]},
        "candidate_pools": {},
    }
    _attach_goal_microdose(brief, 0, _POWER_ENTRY)
    second = _attach_goal_microdose(brief, 0, _POWER_ENTRY)
    assert second["result"] == "floor_already_met"
    roles = brief["weekly_role_map"]["weeks"][0]["session_roles"]
    assert sum(1 for role in roles if role.get("priority_microdose")) == 1
