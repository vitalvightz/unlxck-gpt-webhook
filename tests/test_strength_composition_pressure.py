from __future__ import annotations

import pytest

from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.session_composition import (
    compose_normal_strength_assignments,
    composition_pressure_state,
)


def _slot(
    name: str,
    priority: int,
    *,
    movement: str,
    tags: list[str] | None = None,
    movement_patterns: list[str] | None = None,
    equipment: list[str] | None = None,
    prescription: str = "3 x 5 @ RPE 7",
) -> dict:
    return {
        "slot_id": f"slot-{priority}-{name}",
        "session_index": 1,
        "priority": priority,
        "selected": {
            "name": name,
            "movement": movement,
            "tags": tags or [],
            "movement_patterns": movement_patterns or [],
            "equipment": equipment or [],
            "prescription": prescription,
        },
    }


def _diverse_slots() -> list[dict]:
    return [
        _slot(
            "Trap Bar Deadlift",
            1,
            movement="hinge",
            tags=["compound", "posterior_chain"],
            movement_patterns=["hinge", "posterior_chain"],
            equipment=["barbell"],
        ),
        _slot(
            "Landmine Press",
            2,
            movement="press",
            tags=["compound", "upper_body"],
            movement_patterns=["push", "upper_body"],
            equipment=["landmine"],
        ),
        _slot(
            "Broad Jump",
            3,
            movement="jump",
            tags=["explosive", "mech_lower_jump"],
            movement_patterns=["jump", "explosive", "mech_lower_jump"],
            prescription="4 x 3, full recovery",
        ),
        _slot(
            "Rotational Med-Ball Throw",
            4,
            movement="rotation",
            tags=["explosive", "rotational"],
            movement_patterns=["rotational", "explosive"],
            equipment=["medicine_ball"],
            prescription="4 x 3/side, full recovery",
        ),
        _slot(
            "Plyometric Push-Up",
            5,
            movement="push",
            tags=["explosive", "upper_body", "mech_upper_press"],
            movement_patterns=["explosive", "upper_body", "mech_upper_press"],
            prescription="3 x 4, full recovery",
        ),
        _slot(
            "Pallof Hold",
            6,
            movement="core",
            tags=["anti_rotation", "core", "stability"],
            movement_patterns=["anti_rotation", "core"],
            prescription="2 x 20s/side",
        ),
    ]


def _role_map(role_key: str = "primary_strength_day", *, phase: str = "GPP") -> dict:
    return {
        "weeks": [
            {
                "phase": phase,
                "session_roles": [
                    {
                        "role_key": role_key,
                        "category": "strength",
                        "strength_session_index": 1,
                    }
                ],
            }
        ]
    }


def _compose(athlete: dict, *, role_key: str = "primary_strength_day", slots=None) -> tuple[dict, dict]:
    role_map = _role_map(role_key)
    candidate_pools = {"GPP": {"strength_slots": slots or _diverse_slots()}}
    token = planner_athlete_model_context.set(athlete)
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools=candidate_pools,
        )
    finally:
        planner_athlete_model_context.reset(token)
    role = role_map["weeks"][0]["session_roles"][0]
    return role_map, role


@pytest.mark.parametrize(
    ("athlete", "expected"),
    [
        ({"fatigue": "low", "cut_severity_bucket": "none"}, 0),
        ({"fatigue": "moderate", "cut_severity_bucket": "none"}, 1),
        ({"fatigue": "high", "cut_severity_bucket": "none"}, 2),
        ({"fatigue": "low", "cut_severity_bucket": "moderate"}, 1),
        ({"fatigue": "low", "cut_severity_bucket": "high"}, 2),
        ({"fatigue": "low", "cut_severity_bucket": "critical"}, 3),
        ({"fatigue": "low", "cut_severity_bucket": "extreme"}, 3),
        ({"fatigue": "low", "cut_severity_bucket": "none", "injuries": ["ankle sprain"]}, 1),
        ({"fatigue": "moderate", "cut_severity_bucket": "moderate"}, 2),
        ({"fatigue": "high", "cut_severity_bucket": "moderate"}, 3),
        ({"fatigue": "high", "cut_severity_bucket": "none", "injuries": ["ankle sprain"]}, 3),
    ],
)
def test_composition_pressure_uses_existing_buckets_and_interactions(athlete, expected):
    assert composition_pressure_state(athlete)["pressure"] == expected


@pytest.mark.parametrize(
    ("athlete", "expected_cap"),
    [
        ({"fatigue": "low", "cut_severity_bucket": "none"}, 4),
        ({"fatigue": "moderate", "cut_severity_bucket": "none"}, 3),
        ({"fatigue": "high", "cut_severity_bucket": "none"}, 2),
        ({"fatigue": "high", "cut_severity_bucket": "moderate"}, 2),
    ],
)
def test_primary_strength_cap_scales_with_composition_pressure(athlete, expected_cap):
    _, role = _compose(athlete)
    policy = role["strength_composition_policy"]
    assert policy["base_exercise_cap"] == 4
    assert policy["effective_exercise_cap"] == expected_cap
    assert len(role["selected_exercise_assignments"]) <= expected_cap


def test_normal_state_allows_two_same_family_exposures_but_not_three():
    slots = [
        _slot("Broad Jump", 1, movement="jump", tags=["explosive", "mech_lower_jump"], movement_patterns=["jump", "explosive", "mech_lower_jump"]),
        _slot("Lateral Bound", 2, movement="jump", tags=["explosive", "mech_lower_jump"], movement_patterns=["bound", "explosive", "mech_lower_jump"]),
        _slot("Jump Lunge", 3, movement="lunge", tags=["explosive", "mech_lower_jump"], movement_patterns=["jump", "explosive", "mech_lower_jump"]),
        _slot("Banded Row", 4, movement="pull", tags=["compound", "upper_body"], movement_patterns=["pull", "upper_body"]),
        _slot("Landmine Press", 5, movement="press", tags=["compound", "upper_body"], movement_patterns=["push", "upper_body"], equipment=["landmine"]),
    ]
    _, role = _compose({"fatigue": "low", "cut_severity_bucket": "none"}, slots=slots)
    names = [item["name"] for item in role["selected_exercise_assignments"]]
    lower_power_names = {"Broad Jump", "Lateral Bound", "Jump Lunge"}
    assert len(lower_power_names & set(names)) == 2
    assert role["strength_composition_policy"]["major_family_limit"] == 2


def test_material_pressure_reduces_same_family_limit_to_one():
    slots = [
        _slot("Broad Jump", 1, movement="jump", tags=["explosive", "mech_lower_jump"], movement_patterns=["jump", "explosive", "mech_lower_jump"]),
        _slot("Lateral Bound", 2, movement="jump", tags=["explosive", "mech_lower_jump"], movement_patterns=["bound", "explosive", "mech_lower_jump"]),
        _slot("Jump Lunge", 3, movement="lunge", tags=["explosive", "mech_lower_jump"], movement_patterns=["jump", "explosive", "mech_lower_jump"]),
        _slot("Banded Row", 4, movement="pull", tags=["compound", "upper_body"], movement_patterns=["pull", "upper_body"]),
        _slot("Trap Bar Deadlift", 5, movement="hinge", tags=["compound", "posterior_chain"], movement_patterns=["hinge", "posterior_chain"], equipment=["barbell"]),
    ]
    _, role = _compose({"fatigue": "moderate", "cut_severity_bucket": "none"}, slots=slots)
    names = [item["name"] for item in role["selected_exercise_assignments"]]
    assert len({"Broad Jump", "Lateral Bound", "Jump Lunge"} & set(names)) == 1
    assert role["strength_composition_policy"]["major_family_limit"] == 1


def test_neural_strength_hybrid_can_satisfy_strength_and_power_without_forcing_duplicates():
    slots = [
        _slot(
            "Heavy RDL → Broad Jump",
            1,
            movement="hinge",
            tags=["compound", "posterior_chain", "explosive", "mech_lower_jump"],
            movement_patterns=["hinge", "posterior_chain", "explosive", "mech_lower_jump"],
            equipment=["barbell"],
            prescription="3 x 3 @ 85% then 3 broad jumps",
        ),
        _slot("Barbell Thruster", 2, movement="squat", tags=["compound", "explosive", "upper_body"], movement_patterns=["squat", "press", "explosive", "upper_body"], equipment=["barbell"]),
        _slot("Jump Lunge", 3, movement="lunge", tags=["explosive", "mech_lower_jump"], movement_patterns=["jump", "explosive", "mech_lower_jump"]),
        _slot("Pallof Hold", 4, movement="core", tags=["anti_rotation", "core"], movement_patterns=["anti_rotation", "core"]),
    ]
    _, role = _compose(
        {"fatigue": "low", "cut_severity_bucket": "moderate"},
        role_key="neural_plus_strength_day",
        slots=slots,
    )
    names = [item["name"] for item in role["selected_exercise_assignments"]]
    assert names[0] == "Heavy RDL → Broad Jump"
    assert "Jump Lunge" not in names
    assert len(names) == 2
    assert role["strength_composition_policy"]["effective_exercise_cap"] == 2


def test_current_fatigue_only_tightens_first_active_week():
    role_map = {
        "weeks": [
            {
                "phase": "GPP",
                "session_roles": [
                    {
                        "role_key": "primary_strength_day",
                        "category": "strength",
                        "strength_session_index": 1,
                        "scheduled_countdown_label": "D-41",
                    }
                ],
            },
            {
                "phase": "GPP",
                "session_roles": [
                    {
                        "role_key": "primary_strength_day",
                        "category": "strength",
                        "strength_session_index": 1,
                        "scheduled_countdown_label": "D-34",
                    }
                ],
            },
        ]
    }
    token = planner_athlete_model_context.set(
        {"fatigue": "high", "cut_severity_bucket": "none", "days_until_fight": 42}
    )
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": _diverse_slots()}},
        )
    finally:
        planner_athlete_model_context.reset(token)

    first_policy = role_map["weeks"][0]["session_roles"][0]["strength_composition_policy"]
    future_policy = role_map["weeks"][1]["session_roles"][0]["strength_composition_policy"]
    assert first_policy["fatigue_applied"] is True
    assert first_policy["pressure"] == 2
    assert first_policy["effective_exercise_cap"] == 2
    assert future_policy["fatigue_applied"] is False
    assert future_policy["fatigue_pressure"] == 0
    assert future_policy["pressure"] == 0
    assert future_policy["effective_exercise_cap"] == 4


def test_weight_cut_pressure_recalculates_from_each_roles_d_day():
    role_map = {
        "weeks": [
            {
                "phase": "GPP",
                "session_roles": [
                    {
                        "role_key": "primary_strength_day",
                        "category": "strength",
                        "strength_session_index": 1,
                        "scheduled_countdown_label": "D-35",
                    }
                ],
            },
            {
                "phase": "GPP",
                "session_roles": [
                    {
                        "role_key": "primary_strength_day",
                        "category": "strength",
                        "strength_session_index": 1,
                        "scheduled_countdown_label": "D-7",
                    }
                ],
            },
        ]
    }
    token = planner_athlete_model_context.set(
        {
            "fatigue": "low",
            "weight_cut_risk": True,
            "weight_cut_pct": 4.5,
            "days_until_fight": 35,
        }
    )
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": _diverse_slots()}},
        )
    finally:
        planner_athlete_model_context.reset(token)

    early_policy = role_map["weeks"][0]["session_roles"][0]["strength_composition_policy"]
    late_policy = role_map["weeks"][1]["session_roles"][0]["strength_composition_policy"]
    assert early_policy["role_days_until_fight"] == 35
    assert early_policy["cut_severity_bucket"] == "moderate"
    assert early_policy["effective_exercise_cap"] == 3
    assert late_policy["role_days_until_fight"] == 7
    assert late_policy["cut_severity_bucket"] == "high"
    assert late_policy["effective_exercise_cap"] == 2


def test_composition_context_persists_for_recomposition_after_build_context_resets():
    role_map, first_role = _compose(
        {"fatigue": "moderate", "cut_severity_bucket": "moderate"}
    )
    assert role_map["strength_composition_context"]["pressure"] == 2
    first_names = [item["name"] for item in first_role["selected_exercise_assignments"]]

    compose_normal_strength_assignments(
        weekly_role_map=role_map,
        candidate_pools={"GPP": {"strength_slots": _diverse_slots()}},
    )
    second_role = role_map["weeks"][0]["session_roles"][0]
    assert second_role["strength_composition_policy"]["pressure"] == 2
    assert [item["name"] for item in second_role["selected_exercise_assignments"]] == first_names


@pytest.mark.parametrize(
    ("athlete", "expected_cap"),
    [
        ({"fatigue": "low", "cut_severity_bucket": "none"}, 3),
        ({"fatigue": "low", "cut_severity_bucket": "moderate"}, 2),
    ],
)
def test_neural_plus_strength_cap_scales_from_three(athlete, expected_cap):
    _, role = _compose(athlete, role_key="neural_plus_strength_day")
    policy = role["strength_composition_policy"]
    assert policy["base_exercise_cap"] == 3
    assert policy["effective_exercise_cap"] == expected_cap


def test_current_fatigue_applies_to_first_week_with_normal_strength():
    role_map = {
        "weeks": [
            {
                "phase": "GPP",
                "session_roles": [
                    {"role_key": "aerobic_base_day", "category": "conditioning"}
                ],
            },
            {
                "phase": "GPP",
                "session_roles": [
                    {
                        "role_key": "primary_strength_day",
                        "category": "strength",
                        "strength_session_index": 1,
                    }
                ],
            },
            {
                "phase": "GPP",
                "session_roles": [
                    {
                        "role_key": "primary_strength_day",
                        "category": "strength",
                        "strength_session_index": 1,
                    }
                ],
            },
        ]
    }
    token = planner_athlete_model_context.set(
        {"fatigue": "high", "cut_severity_bucket": "none"}
    )
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": _diverse_slots()}},
        )
    finally:
        planner_athlete_model_context.reset(token)

    first = role_map["weeks"][1]["session_roles"][0]["strength_composition_policy"]
    later = role_map["weeks"][2]["session_roles"][0]["strength_composition_policy"]
    assert first["fatigue_applied"] is True
    assert first["effective_exercise_cap"] == 2
    assert later["fatigue_applied"] is False
    assert later["effective_exercise_cap"] == 4


@pytest.mark.parametrize(
    ("role_key", "d_day", "expected_cap"),
    [
        ("primary_strength_day", 26, 3),
        ("neural_plus_strength_day", 19, 2),
    ],
)
def test_active_three_point_four_percent_cut_uses_canonical_role_pressure(
    role_key, d_day, expected_cap
):
    role_map = _role_map(role_key)
    role = role_map["weeks"][0]["session_roles"][0]
    role["scheduled_countdown_label"] = f"D-{d_day}"
    token = planner_athlete_model_context.set(
        {"fatigue": "low", "weight_cut_risk": True, "weight_cut_pct": 3.4}
    )
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": _diverse_slots()}},
        )
    finally:
        planner_athlete_model_context.reset(token)

    policy = role["strength_composition_policy"]
    assert policy["cut_severity_bucket"] == "moderate"
    assert policy["effective_exercise_cap"] == expected_cap
    assert len(role["selected_exercise_assignments"]) <= expected_cap
