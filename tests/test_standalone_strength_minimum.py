"""Standalone strength / strength+power sessions prefer a four-exercise minimum.

The lift only applies to the 3-capped full strength roles, at zero readiness
pressure, on a day with no contact or other meaningful session. Every existing
reduce-only rule still bounds the result.
"""

from __future__ import annotations

import pytest

from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.session_composition import (
    compose_normal_strength_assignments,
)
from tests.test_strength_composition_pressure import _diverse_slots, _slot

_FRESH = {"fatigue": "low", "cut_severity_bucket": "none"}


def _strength_role(role_key: str, d_day: int = 30) -> dict:
    return {
        "role_key": role_key,
        "category": "strength",
        "strength_session_index": 1,
        "scheduled_countdown_label": f"D-{d_day}",
    }


def _compose(
    role_key: str,
    *,
    athlete: dict | None = None,
    phase: str = "GPP",
    extra_roles: list[dict] | None = None,
    hard_sparring_plan: list[dict] | None = None,
    slots: list[dict] | None = None,
    d_day: int = 30,
) -> dict:
    role = _strength_role(role_key, d_day)
    week = {
        "phase": phase,
        "session_roles": [role, *(extra_roles or [])],
        "hard_sparring_plan": hard_sparring_plan or [],
    }
    token = planner_athlete_model_context.set(athlete or _FRESH)
    try:
        compose_normal_strength_assignments(
            weekly_role_map={"weeks": [week]},
            candidate_pools={phase: {"strength_slots": slots or _diverse_slots()}},
        )
    finally:
        planner_athlete_model_context.reset(token)
    return role


def _count(role: dict) -> int:
    return len(role["selected_exercise_assignments"])


@pytest.mark.parametrize(
    ("role_key", "phase"),
    [
        ("secondary_strength_day", "GPP"),
        ("neural_plus_strength_day", "SPP"),
        ("transfer_strength_day", "SPP"),
    ],
)
def test_standalone_three_exercise_session_becomes_four(role_key, phase):
    role = _compose(role_key, phase=phase)
    policy = role["strength_composition_policy"]
    assert policy["base_exercise_cap"] == 3
    assert policy["standalone_minimum_applied"] is True
    assert policy["effective_exercise_cap"] == 4
    assert _count(role) == 4


def test_session_already_at_four_is_unchanged():
    role = _compose("primary_strength_day")
    policy = role["strength_composition_policy"]
    assert policy["standalone_minimum_applied"] is False
    assert policy["effective_exercise_cap"] == 4
    assert _count(role) == 4


def test_minimum_never_invents_exercises_beyond_stage1_membership():
    role = _compose("secondary_strength_day", slots=_diverse_slots()[:3])
    assert role["strength_composition_policy"]["effective_exercise_cap"] == 4
    assert _count(role) == 3


def test_strength_on_hard_sparring_day_stays_at_three():
    role = _compose(
        "neural_plus_strength_day",
        phase="SPP",
        hard_sparring_plan=[{"d_day": 30, "status": "hard_as_planned"}],
    )
    policy = role["strength_composition_policy"]
    assert policy["standalone_minimum_applied"] is False
    assert policy["effective_exercise_cap"] == 3
    assert _count(role) == 3


def test_strength_the_day_before_hard_sparring_stays_at_three():
    role = _compose(
        "transfer_strength_day",
        phase="SPP",
        hard_sparring_plan=[{"d_day": 29, "status": "hard_as_planned"}],
    )
    assert role["strength_composition_policy"]["standalone_minimum_applied"] is False
    assert _count(role) == 3


def test_strength_sharing_day_with_meaningful_conditioning_stays_at_three():
    conditioning = {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "preferred_system": "glycolytic",
        "scheduled_countdown_label": "D-30",
    }
    role = _compose("secondary_strength_day", extra_roles=[conditioning])
    assert role["strength_composition_policy"]["standalone_minimum_applied"] is False
    assert _count(role) == 3


def test_undated_strength_role_fails_closed():
    role = _strength_role("secondary_strength_day")
    role.pop("scheduled_countdown_label")
    token = planner_athlete_model_context.set(_FRESH)
    try:
        compose_normal_strength_assignments(
            weekly_role_map={"weeks": [{"phase": "GPP", "session_roles": [role]}]},
            candidate_pools={"GPP": {"strength_slots": _diverse_slots()}},
        )
    finally:
        planner_athlete_model_context.reset(token)
    assert role["strength_composition_policy"]["standalone_minimum_applied"] is False
    assert _count(role) == 3


@pytest.mark.parametrize(
    "role_key",
    ["strength_touch_day", "neural_primer_day", "small_strength_touch_day"],
)
def test_touch_and_primer_roles_are_not_lifted(role_key):
    role = _compose(role_key, phase="SPP")
    policy = role["strength_composition_policy"]
    assert policy["standalone_minimum_applied"] is False
    assert policy["effective_exercise_cap"] == 2
    assert _count(role) <= 2


def test_taper_phase_is_not_lifted():
    role = _compose("transfer_strength_day", phase="TAPER")
    assert role["strength_composition_policy"]["standalone_minimum_applied"] is False
    assert _count(role) <= 3


_MODERATE_ATHLETES = [
    {"fatigue": "moderate", "cut_severity_bucket": "none"},
    {"fatigue": "low", "cut_severity_bucket": "moderate"},
    {"fatigue": "low", "cut_severity_bucket": "none", "injuries": ["ankle sprain"]},
]


@pytest.mark.parametrize("athlete", _MODERATE_ATHLETES)
@pytest.mark.parametrize(
    ("role_key", "phase"),
    [
        ("primary_strength_day", "GPP"),
        ("secondary_strength_day", "GPP"),
        ("neural_plus_strength_day", "SPP"),
    ],
)
def test_moderate_fatigue_cut_or_injury_still_lifts_to_four(athlete, role_key, phase):
    role = _compose(role_key, phase=phase, athlete=athlete)
    policy = role["strength_composition_policy"]
    assert policy["pressure"] == 1
    assert policy["standalone_minimum_applied"] is True
    assert policy["effective_exercise_cap"] == 4
    # Moderate pressure keeps its one-per-family limit.
    assert policy["major_family_limit"] == 1
    assert _count(role) == 4


def test_moderate_pressure_on_hard_sparring_day_is_not_lifted():
    role = _compose(
        "neural_plus_strength_day",
        phase="SPP",
        athlete=_MODERATE_ATHLETES[0],
        hard_sparring_plan=[{"d_day": 30, "status": "hard_as_planned"}],
    )
    policy = role["strength_composition_policy"]
    assert policy["standalone_minimum_applied"] is False
    assert policy["effective_exercise_cap"] == 2


@pytest.mark.parametrize(
    "athlete",
    [
        {"fatigue": "high", "cut_severity_bucket": "none"},
        {"fatigue": "low", "cut_severity_bucket": "high"},
        {"fatigue": "low", "cut_severity_bucket": "critical"},
        # Two moderate stressors combine above moderate.
        {"fatigue": "moderate", "cut_severity_bucket": "moderate"},
        {"fatigue": "moderate", "cut_severity_bucket": "none", "injuries": ["ankle sprain"]},
    ],
)
def test_above_moderate_pressure_overrides_the_minimum(athlete):
    role = _compose("neural_plus_strength_day", phase="SPP", athlete=athlete)
    policy = role["strength_composition_policy"]
    assert policy["pressure"] >= 2
    assert policy["standalone_minimum_applied"] is False
    assert policy["effective_exercise_cap"] < 3
    assert _count(role) == policy["effective_exercise_cap"]


def test_family_limit_still_wins_over_the_minimum():
    # Four lower-body strength lifts: the two-per-family limit keeps two.
    slots = [
        _slot(name, index, movement="squat", tags=["compound"], movement_patterns=["squat"])
        for index, name in enumerate(
            ["Back Squat", "Front Squat", "Split Squat", "Goblet Squat"], start=1
        )
    ]
    role = _compose("secondary_strength_day", slots=slots)
    assert role["strength_composition_policy"]["standalone_minimum_applied"] is True
    assert _count(role) < 4


def test_conditioning_composition_is_untouched():
    conditioning = {
        "role_key": "aerobic_base_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "scheduled_countdown_label": "D-28",
    }
    role_map = {"weeks": [{"phase": "GPP", "session_roles": [conditioning]}]}
    token = planner_athlete_model_context.set(_FRESH)
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": _diverse_slots()}},
        )
    finally:
        planner_athlete_model_context.reset(token)
    assert "strength_composition_policy" not in conditioning
    assert "selected_exercise_assignments" not in conditioning
