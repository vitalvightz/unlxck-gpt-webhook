from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.session_composition import compose_normal_conditioning_assignments
from fightcamp.stage2_validator import validate_stage2_output


def _conditioning_option(name: str, minutes: float) -> dict:
    return {
        "name": name,
        "selection_metadata": {
            "name": name,
            "system": "aerobic",
            "total_minutes": minutes,
            "rpe": 4,
            "intensity": "low",
        },
    }


def _conditioning_slot(index: int, name: str, minutes: float) -> dict:
    return {
        "slot_id": f"spp-aerobic-{index}",
        "role": "aerobic",
        "selected": _conditioning_option(name, minutes),
        "alternates": [],
    }


def _tgu_slot() -> dict:
    return {
        "slot_id": "spp-trunk-1",
        "session_index": 1,
        "priority": 1,
        "quality_class": "support_accessory",
        "support_only": True,
        "selected": {
            "name": "Turkish Get-Up",
            "prescription": "5 x 5 reps per side",
            "quality_class": "support_accessory",
            "support_only": True,
            "tags": ["trunk_strength", "core", "balance"],
            "movement": "core",
            "equipment": [],
        },
        "alternates": [],
    }


def _role_map() -> dict:
    return {
        "weeks": [
            {
                "phase": "SPP",
                "effective_hard_sparring_days": [],
                "session_roles": [
                    {
                        "category": "conditioning",
                        "role_key": "aerobic_support_day",
                        "preferred_system": "aerobic",
                        "scheduled_day_hint": "wednesday",
                    }
                ],
            }
        ]
    }


def _compose(role_map: dict, pools: dict) -> dict:
    token = planner_athlete_model_context.set(
        {
            "weaknesses": ["trunk_strength"],
            "fatigue": "low",
            "cut_severity_bucket": "none",
        }
    )
    try:
        compose_normal_conditioning_assignments(
            weekly_role_map=role_map,
            candidate_pools=pools,
        )
    finally:
        planner_athlete_model_context.reset(token)
    return role_map["weeks"][0]["session_roles"][0]


def test_embedded_trunk_support_cannot_make_underfilled_aerobic_role_complete():
    role = _compose(
        _role_map(),
        {
            "SPP": {
                "conditioning_slots": [
                    _conditioning_slot(1, "Tempo Flow", 2),
                    _conditioning_slot(2, "Bike Rhythm", 2),
                ],
                "strength_slots": [_tgu_slot()],
            }
        },
    )

    assignments = role["selected_exercise_assignments"]
    assert [item["name"] for item in assignments] == ["Tempo Flow", "Bike Rhythm"]
    assert all(not item.get("embedded_support") for item in assignments)

    policy = role["conditioning_composition_policy"]
    assert policy["conditioning_workload_met"] is False
    assert policy["conditioning_selected_count"] == 2
    assert policy["workload_limited"] is True
    assert policy["underfill_reason"] == "phase_system_workload_unmet"
    assert policy["embedded_trunk_support"] is False
    assert policy["embedded_trunk_support_skip_reason"] == "conditioning_workload_unmet"


def test_embedded_trunk_support_remains_optional_after_aerobic_workload_is_met():
    role = _compose(
        _role_map(),
        {
            "SPP": {
                "conditioning_slots": [
                    _conditioning_slot(1, "Tempo Flow", 4),
                    _conditioning_slot(2, "Bike Rhythm", 4),
                ],
                "strength_slots": [_tgu_slot()],
            }
        },
    )

    assignments = role["selected_exercise_assignments"]
    assert [item["name"] for item in assignments] == [
        "Tempo Flow",
        "Bike Rhythm",
        "Turkish Get-Up",
    ]
    assert assignments[-1]["embedded_support"] is True

    policy = role["conditioning_composition_policy"]
    assert policy["conditioning_workload_met"] is True
    assert policy["conditioning_selected_count"] == 2
    assert policy["workload_limited"] is False
    assert policy["embedded_trunk_support"] is True


def test_missing_conditioning_pool_is_explicitly_underfilled_not_support_only():
    role = _compose(
        _role_map(),
        {"SPP": {"conditioning_slots": [], "strength_slots": [_tgu_slot()]}},
    )

    assert role["selected_exercise_assignments"] == []
    policy = role["conditioning_composition_policy"]
    assert policy["conditioning_workload_met"] is False
    assert policy["conditioning_selected_count"] == 0
    assert policy["workload_limited"] is True
    assert policy["underfill_reason"] == "phase_system_workload_unmet"


def test_validator_blocks_underfilled_conditioning_role():
    role_map = _role_map()
    role = _compose(
        role_map,
        {
            "SPP": {
                "conditioning_slots": [
                    _conditioning_slot(1, "Tempo Flow", 2),
                    _conditioning_slot(2, "Bike Rhythm", 2),
                ],
                "strength_slots": [_tgu_slot()],
            }
        },
    )
    assert role["conditioning_composition_policy"]["conditioning_workload_met"] is False

    report = validate_stage2_output(
        planning_brief={"weekly_role_map": role_map},
        final_plan_text=(
            "## Week 1 — SPP\n"
            "### Wednesday — Aerobic support\n"
            "- Tempo Flow — 2 min\n"
            "- Bike Rhythm — 2 min"
        ),
    )
    assert any(
        error.get("code") == "conditioning_role_workload_underfilled"
        for error in report["errors"]
    )
    assert report["is_valid"] is False
