"""Standalone strength / strength+power sessions may take one extra exercise.

Composition only proposes the extra exercise. ``apply_standalone_strength_minimum``
keeps it only when the existing realised-load revalidation places every session
exactly as it would without it and every existing dose is unchanged.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.session_composition import (
    _placement_signature,
    apply_realised_load_calendar_revalidation,
    apply_standalone_strength_minimum,
    compose_normal_strength_assignments,
)
from tests.test_strength_composition_pressure import _diverse_slots, _slot

_FRESH = {"fatigue": "low", "cut_severity_bucket": "none"}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _strength_role(role_key: str, d_day: int = 30, *, index: int = 1) -> dict:
    return {
        "role_key": role_key,
        "category": "strength",
        "strength_session_index": index,
        "session_index": index,
        "scheduled_day_hint": _WEEKDAYS[30 - d_day].title(),
        "scheduled_countdown_label": f"D-{d_day}",
    }


def _week(roles: list[dict], *, phase: str = "GPP", hard_sparring_plan=None) -> dict:
    return {
        "week_index": 1,
        "phase": phase,
        "declared_training_days": list(_WEEKDAYS),
        "calendar_days": [
            {"weekday": weekday, "d_day": 30 - offset}
            for offset, weekday in enumerate(_WEEKDAYS)
        ],
        "session_roles": roles,
        "hard_sparring_plan": hard_sparring_plan or [],
    }


def _redose_for(pools: dict, athlete: dict):
    def _redose(target: dict) -> dict:
        return apply_effective_strength_prescriptions(
            weekly_role_map=target, candidate_pools=pools, athlete_model=athlete
        )

    return _redose


def _run(
    role_map: dict,
    slots: list[dict],
    *,
    athlete: dict | None = None,
    phase: str = "GPP",
    redose=None,
) -> dict:
    """Mirror the pipeline: compose, dose, confirm the extra item, revalidate."""
    pools = {phase: {"strength_slots": slots}}
    athlete = athlete or _FRESH
    redose = redose or _redose_for(pools, athlete)
    token = planner_athlete_model_context.set(athlete)
    try:
        compose_normal_strength_assignments(weekly_role_map=role_map, candidate_pools=pools)
        redose(role_map)
        apply_standalone_strength_minimum(
            role_map, candidate_pools=pools, redose_callback=redose
        )
        apply_realised_load_calendar_revalidation(role_map, redose_callback=redose)
    finally:
        planner_athlete_model_context.reset(token)
    return role_map


def _single(role_key: str, *, phase: str = "GPP", slots=None, hard_sparring_plan=None, **kwargs) -> dict:
    role = _strength_role(role_key)
    _run(
        {"weeks": [_week([role], phase=phase, hard_sparring_plan=hard_sparring_plan)]},
        slots or _diverse_slots(),
        phase=phase,
        **kwargs,
    )
    return role


def _count(role: dict) -> int:
    return len(role["selected_exercise_assignments"])


def _decision(role: dict) -> dict | None:
    return role["strength_composition_policy"].get("standalone_minimum")


@pytest.mark.parametrize(
    ("role_key", "phase"),
    [
        ("secondary_strength_day", "GPP"),
        ("neural_plus_strength_day", "SPP"),
        ("transfer_strength_day", "SPP"),
    ],
)
def test_standalone_three_exercise_session_becomes_four(role_key, phase):
    role = _single(role_key, phase=phase)
    policy = role["strength_composition_policy"]
    # The role cap itself is untouched; only one confirmed extra item is added.
    assert policy["effective_exercise_cap"] == 3
    assert _decision(role)["status"] == "applied"
    assert policy["standalone_minimum_applied"] is True
    assert _count(role) == 4
    assert policy["selected_count"] == 4
    assert role["effective_strength_envelope"]["allowed_exercise_names"] == policy["selected_names"]


def test_session_already_at_four_is_unchanged():
    role = _single("primary_strength_day")
    assert _decision(role) is None
    assert role["strength_composition_policy"]["standalone_minimum_applied"] is False
    assert _count(role) == 4


def test_minimum_never_invents_exercises_beyond_stage1_membership():
    role = _single("secondary_strength_day", slots=_diverse_slots()[:3])
    assert _decision(role) is None
    assert _count(role) == 3


def test_family_limit_still_wins_over_the_minimum():
    slots = [
        _slot(name, index, movement="squat", tags=["compound"], movement_patterns=["squat"])
        for index, name in enumerate(
            ["Back Squat", "Front Squat", "Split Squat", "Goblet Squat"], start=1
        )
    ]
    role = _single("secondary_strength_day", slots=slots)
    assert _decision(role) is None
    assert _count(role) == 2


@pytest.mark.parametrize(
    ("contact_d_day", "role_key"),
    [(30, "neural_plus_strength_day"), (29, "transfer_strength_day")],
)
def test_hard_sparring_day_and_day_before_are_not_lifted(contact_d_day, role_key):
    role = _single(
        role_key,
        phase="SPP",
        hard_sparring_plan=[{"d_day": contact_d_day, "status": "hard_as_planned"}],
    )
    assert _decision(role) is None
    assert _count(role) == 3


def test_strength_sharing_day_with_meaningful_conditioning_is_not_lifted():
    role = _strength_role("secondary_strength_day")
    conditioning = {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "preferred_system": "glycolytic",
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": "D-30",
    }
    _run({"weeks": [_week([role, conditioning])]}, _diverse_slots())
    assert _decision(role) is None
    assert _count(role) == 3


@pytest.mark.parametrize(
    "role_key",
    ["strength_touch_day", "neural_primer_day", "small_strength_touch_day"],
)
def test_touch_and_primer_roles_are_not_lifted(role_key):
    role = _single(role_key, phase="SPP")
    assert _decision(role) is None
    assert _count(role) <= 2


def test_taper_phase_is_not_lifted():
    role = _single("transfer_strength_day", phase="TAPER")
    assert _decision(role) is None


@pytest.mark.parametrize(
    ("athlete", "role_key", "before"),
    [
        ({"fatigue": "moderate", "cut_severity_bucket": "none"}, "primary_strength_day", 3),
        ({"fatigue": "low", "cut_severity_bucket": "moderate"}, "neural_plus_strength_day", 2),
        ({"fatigue": "low", "cut_severity_bucket": "none", "injuries": ["ankle sprain"]}, "secondary_strength_day", 2),
    ],
)
def test_moderate_pressure_still_allows_exactly_one_extra(athlete, role_key, before):
    phase = "SPP" if role_key == "neural_plus_strength_day" else "GPP"
    role = _single(role_key, phase=phase, athlete=athlete)
    policy = role["strength_composition_policy"]
    assert policy["pressure"] == 1
    assert policy["effective_exercise_cap"] == before
    assert _decision(role)["status"] == "applied"
    assert _count(role) == before + 1


@pytest.mark.parametrize(
    "athlete",
    [
        {"fatigue": "high", "cut_severity_bucket": "none"},
        {"fatigue": "low", "cut_severity_bucket": "high"},
        {"fatigue": "moderate", "cut_severity_bucket": "moderate"},
        {"fatigue": "moderate", "cut_severity_bucket": "none", "injuries": ["ankle sprain"]},
    ],
)
def test_above_moderate_pressure_overrides_the_minimum(athlete):
    role = _single("neural_plus_strength_day", phase="SPP", athlete=athlete)
    policy = role["strength_composition_policy"]
    assert policy["pressure"] >= 2
    assert _decision(role) is None
    assert _count(role) == policy["effective_exercise_cap"] == 2


def _mech_slot(name: str, priority: int, session_index: int, mech: str, **kwargs) -> dict:
    slot = _slot(name, priority, **kwargs)
    slot["session_index"] = session_index
    slot["selected"]["mechanical_risk_tags"] = [mech]
    return slot


def _load_sensitive_map() -> tuple[dict, list[dict]]:
    """A D-30 secondary session (30 reps, upper/trunk: LOW realised load) that
    turns MODERATE with a lower-body region once a 4th item is added, next to a
    D-29 primary session already MODERATE on the lower and upper body."""
    neighbour = _strength_role("primary_strength_day", 29, index=1)
    target = _strength_role("secondary_strength_day", 30, index=2)
    slots = [
        _mech_slot("Box Squat", 1, 1, "mech_lower_squat", movement="squat",
                   tags=["compound"], movement_patterns=["squat"], prescription="3 x 5"),
        _mech_slot("Bench Press", 2, 1, "mech_upper_press", movement="press",
                   tags=["compound", "upper_body"], movement_patterns=["push", "upper_body"],
                   prescription="3 x 5"),
        _mech_slot("Split Squat", 3, 1, "mech_lower_squat", movement="squat",
                   movement_patterns=["squat"], prescription="3 x 5"),
        _mech_slot("Push-Up", 4, 1, "mech_upper_press", movement="press",
                   tags=["upper_body"], movement_patterns=["push", "upper_body"],
                   prescription="3 x 5"),
        _mech_slot("Chin-Up", 5, 2, "mech_upper_pull", movement="pull",
                   tags=["upper_body"], movement_patterns=["pull", "upper_body"],
                   prescription="2 x 5"),
        _mech_slot("Med-Ball Rotational Throw", 6, 2, "mech_trunk_rotation", movement="rotation",
                   tags=["explosive", "rotational"], movement_patterns=["rotational", "explosive"],
                   prescription="2 x 5"),
        _mech_slot("Plyometric Push-Up", 7, 2, "mech_upper_plyo", movement="push",
                   tags=["explosive", "upper_body"], movement_patterns=["explosive", "upper_body"],
                   prescription="2 x 5"),
        _mech_slot("Romanian Deadlift", 8, 2, "mech_lower_hinge", movement="hinge",
                   tags=["compound", "posterior_chain"], movement_patterns=["hinge", "posterior_chain"],
                   prescription="3 x 5"),
    ]
    return {"weeks": [_week([target, neighbour])]}, slots


def test_extra_exercise_that_would_change_realised_load_placement_is_rejected():
    role_map, slots = _load_sensitive_map()
    target = role_map["weeks"][0]["session_roles"][0]
    _run(role_map, slots)

    assert _decision(target)["status"] == "rejected"
    assert _decision(target)["reason"] == "realised_load_placement_changed"
    assert target["strength_composition_policy"]["standalone_minimum_applied"] is False
    assert _count(target) == 3
    assert target["scheduled_countdown_label"] == "D-30"


def test_rejected_extra_leaves_placement_identical_to_no_extra():
    role_map, slots = _load_sensitive_map()
    reference = deepcopy(role_map)
    _run(role_map, slots)

    # Reference: the pre-feature pipeline, with no confirmation step at all.
    pools = {"GPP": {"strength_slots": slots}}
    redose = _redose_for(pools, _FRESH)
    token = planner_athlete_model_context.set(_FRESH)
    try:
        compose_normal_strength_assignments(weekly_role_map=reference, candidate_pools=pools)
        redose(reference)
        apply_realised_load_calendar_revalidation(reference, redose_callback=redose)
    finally:
        planner_athlete_model_context.reset(token)

    assert _placement_signature(role_map) == _placement_signature(reference)
    assert role_map.get("realised_load_revalidation") == reference.get(
        "realised_load_revalidation"
    )
    for role, ref_role in zip(
        role_map["weeks"][0]["session_roles"], reference["weeks"][0]["session_roles"]
    ):
        assert role["selected_exercise_assignments"] == ref_role["selected_exercise_assignments"]


def test_extra_exercise_that_changes_an_existing_dose_is_rejected():
    pools = {"GPP": {"strength_slots": _diverse_slots()}}
    base_redose = _redose_for(pools, _FRESH)

    def _squeezing_redose(target: dict) -> dict:
        base_redose(target)
        for week in target["weeks"]:
            for role in week["session_roles"]:
                if len(role.get("selected_exercise_assignments") or []) >= 4:
                    for item in role.get("effective_strength_prescriptions") or []:
                        item["effective_prescription"] = "1 x 1"
        return target

    role = _strength_role("secondary_strength_day")
    _run({"weeks": [_week([role])]}, _diverse_slots(), redose=_squeezing_redose)
    assert _decision(role)["status"] == "rejected"
    assert _decision(role)["reason"] == "existing_dose_changed"
    assert _count(role) == 3


def test_recomposition_carries_the_confirmed_decision_forward():
    applied = _strength_role("secondary_strength_day")
    role_map = _run({"weeks": [_week([applied])]}, _diverse_slots())
    assert _count(applied) == 4

    rejected_map, slots = _load_sensitive_map()
    rejected = rejected_map["weeks"][0]["session_roles"][0]
    _run(rejected_map, slots)
    assert _count(rejected) == 3

    # A goal-repair trial recomposes the whole map without re-confirming.
    for target, pools in (
        (role_map, {"GPP": {"strength_slots": _diverse_slots()}}),
        (rejected_map, {"GPP": {"strength_slots": slots}}),
    ):
        token = planner_athlete_model_context.set(_FRESH)
        try:
            compose_normal_strength_assignments(weekly_role_map=target, candidate_pools=pools)
        finally:
            planner_athlete_model_context.reset(token)
    assert _decision(applied)["status"] == "applied"
    assert _count(applied) == 4
    assert _decision(rejected)["status"] == "rejected"
    assert _count(rejected) == 3


def test_unconfirmed_proposal_never_changes_the_session():
    role = _strength_role("secondary_strength_day")
    token = planner_athlete_model_context.set(_FRESH)
    try:
        compose_normal_strength_assignments(
            weekly_role_map={"weeks": [_week([role])]},
            candidate_pools={"GPP": {"strength_slots": _diverse_slots()}},
        )
    finally:
        planner_athlete_model_context.reset(token)
    assert _decision(role)["status"] == "proposed"
    assert _count(role) == 3


def test_conditioning_roles_are_untouched():
    conditioning = {
        "role_key": "aerobic_base_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "Wednesday",
        "scheduled_countdown_label": "D-28",
    }
    _run({"weeks": [_week([conditioning])]}, _diverse_slots())
    assert "strength_composition_policy" not in conditioning
    assert "selected_exercise_assignments" not in conditioning
