from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.session_composition import compose_normal_strength_assignments


def test_serialized_base_categories_drive_redundancy_without_raw_tags():
    slots = [
        {
            "slot_id": "power-1",
            "session_index": 1,
            "priority": 1,
            "base_categories": ["lower_body_power"],
            "selected": {"name": "Power A", "base_categories": ["lower_body_power"]},
        },
        {
            "slot_id": "power-2",
            "session_index": 1,
            "priority": 2,
            "base_categories": ["lower_body_power"],
            "selected": {"name": "Power B", "base_categories": ["lower_body_power"]},
        },
        {
            "slot_id": "strength-1",
            "session_index": 1,
            "priority": 3,
            "base_categories": ["lower_body_loaded"],
            "selected": {"name": "Strength A", "base_categories": ["lower_body_loaded"]},
        },
    ]
    role_map = {
        "weeks": [{
            "phase": "GPP",
            "session_roles": [{
                "role_key": "primary_strength_day",
                "category": "strength",
                "strength_session_index": 1,
            }],
        }]
    }

    token = planner_athlete_model_context.set({"fatigue": "high", "cut_severity_bucket": "none"})
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": slots}},
        )
    finally:
        planner_athlete_model_context.reset(token)

    role = role_map["weeks"][0]["session_roles"][0]
    names = [item["name"] for item in role["selected_exercise_assignments"]]
    assert "Strength A" in names
    assert len({"Power A", "Power B"} & set(names)) == 1
    assert role["strength_composition_policy"]["major_family_limit"] == 1


def test_serialized_support_only_is_deprioritized_when_session_shrinks():
    slots = [
        {
            "slot_id": "support-1",
            "session_index": 1,
            "priority": 1,
            "support_only": True,
            "selected": {"name": "Support A", "support_only": True},
        },
        {
            "slot_id": "strength-1",
            "session_index": 1,
            "priority": 2,
            "base_categories": ["lower_body_loaded"],
            "selected": {"name": "Strength A", "base_categories": ["lower_body_loaded"]},
        },
        {
            "slot_id": "power-1",
            "session_index": 1,
            "priority": 3,
            "base_categories": ["rotational_power"],
            "selected": {"name": "Power A", "base_categories": ["rotational_power"]},
        },
    ]
    role_map = {
        "weeks": [{
            "phase": "GPP",
            "session_roles": [{
                "role_key": "primary_strength_day",
                "category": "strength",
                "strength_session_index": 1,
            }],
        }]
    }

    token = planner_athlete_model_context.set({"fatigue": "high", "cut_severity_bucket": "moderate"})
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": slots}},
        )
    finally:
        planner_athlete_model_context.reset(token)

    role = role_map["weeks"][0]["session_roles"][0]
    assert [item["name"] for item in role["selected_exercise_assignments"]] == [
        "Strength A",
        "Power A",
    ]


def test_support_status_does_not_reorder_stage1_when_no_shrink_is_needed():
    slots = [
        {
            "slot_id": "support-1",
            "session_index": 1,
            "priority": 1,
            "support_only": True,
            "selected": {"name": "Support A", "support_only": True},
        },
        {
            "slot_id": "strength-1",
            "session_index": 1,
            "priority": 2,
            "base_categories": ["lower_body_loaded"],
            "selected": {"name": "Strength A", "base_categories": ["lower_body_loaded"]},
        },
        {
            "slot_id": "power-1",
            "session_index": 1,
            "priority": 3,
            "base_categories": ["rotational_power"],
            "selected": {"name": "Power A", "base_categories": ["rotational_power"]},
        },
    ]
    role_map = {
        "weeks": [{
            "phase": "GPP",
            "session_roles": [{
                "role_key": "primary_strength_day",
                "category": "strength",
                "strength_session_index": 1,
            }],
        }]
    }

    token = planner_athlete_model_context.set({"fatigue": "low", "cut_severity_bucket": "none"})
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": slots}},
        )
    finally:
        planner_athlete_model_context.reset(token)

    role = role_map["weeks"][0]["session_roles"][0]
    assert [item["name"] for item in role["selected_exercise_assignments"]] == [
        "Support A",
        "Strength A",
        "Power A",
    ]
