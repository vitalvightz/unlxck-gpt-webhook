from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.session_composition import compose_normal_strength_assignments
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import (
    _build_strength_slots,
    _closed_membership_render_manifest,
)


_BANK = json.loads(
    (Path(__file__).parents[1] / "data" / "exercise_bank.json").read_text(
        encoding="utf-8"
    )
)


def _bank_item(name: str) -> dict:
    return deepcopy(next(item for item in _BANK if item.get("name") == name))


def _role_map() -> dict:
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase": "GPP",
                "declared_training_days": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
                "calendar_days": [
                    {"weekday": "monday", "d_day": 21},
                    {"weekday": "tuesday", "d_day": 20},
                    {"weekday": "wednesday", "d_day": 19},
                    {"weekday": "thursday", "d_day": 18},
                    {"weekday": "friday", "d_day": 17},
                ],
                "session_roles": [
                    {
                        "session_index": 1,
                        "strength_session_index": 1,
                        "role_key": "primary_strength_day",
                        "category": "strength",
                        "scheduled_day_hint": "Monday",
                        "scheduled_countdown_label": "D-21",
                    },
                    {
                        "session_index": 2,
                        "strength_session_index": 2,
                        "role_key": "secondary_strength_day",
                        "category": "strength",
                        "scheduled_day_hint": "Tuesday",
                        "scheduled_countdown_label": "D-20",
                    },
                ],
            }
        ]
    }


def _compose(role_map: dict, slots: list[dict], athlete: dict | None = None) -> None:
    athlete = athlete or {"fatigue": "low", "cut_severity_bucket": "none"}
    token = planner_athlete_model_context.set(athlete)
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map,
            candidate_pools={"GPP": {"strength_slots": slots}},
        )
    finally:
        planner_athlete_model_context.reset(token)


def _slot(
    name: str,
    session_index: int,
    priority: int,
    *,
    tags: list[str],
    low_cost: bool,
) -> dict:
    level = "low" if low_cost else "high"
    metadata = {
        "mechanical_risk_tags": tags,
        "movement_cost": level,
        "impact_cost": "low",
        "eccentric_cost": level,
        "landing_cost": "none",
        "cns_load": level,
        "soreness_risk": level,
    }
    return {
        "slot_id": f"slot-{session_index}-{priority}",
        "session_index": session_index,
        "priority": priority,
        "selected": {
            "name": name,
            "movement": "carry" if "Carry" in name else "isometric",
            "movement_patterns": tags,
            "mechanical_risk_tags": tags,
            "selection_metadata": metadata,
            "prescription": "3 x 5 @ RPE 7",
        },
    }


def test_reproduction_consecutive_strength_days_remain_eligible_and_render_closed_membership():
    prescriptions = {
        "Slow-Lowered Pull-Up": "2-3 x 6-10 @ RPE 6-7",
        "Kettlebell Swing": "3-5 x 4-6, crisp intent, 60-90 sec rest",
        "Chop Holds (Anti-Rotation)": "2-4 x 6-10 or 20-40 sec @ RPE 6-8",
        "Trap Bar Carry (Frame Neutral)": "3 x 8-12 @ 60-75% 1RM",
        "Farmer Walk Hold (Static)": "3-5 x 10-20 sec @ 7-9/10 effort",
        "DB Alternating Incline Press (30-45°)": "2-3 x 6-10 @ RPE 6-7",
        "Single-Leg Spanish Squat Hold": "3-5 x 10-20 sec @ 7-9/10 effort",
    }
    ordered_names = list(prescriptions)
    exercises = []
    for name in ordered_names:
        exercise = _bank_item(name)
        exercise["prescription"] = prescriptions[name]
        exercises.append(exercise)

    slots = _build_strength_slots(
        {"exercises": exercises, "num_sessions": 2, "why_log": []}, "GPP"
    )
    first_session_names = set(ordered_names[:4])
    for slot in slots:
        slot["session_index"] = (
            1 if slot["selected"]["name"] in first_session_names else 2
        )
    role_map = _role_map()
    _compose(role_map, slots)
    apply_late_camp_role_morph(role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=role_map,
        candidate_pools={"GPP": {"strength_slots": slots}},
        athlete_model={"fatigue": "low", "cut_severity_bucket": "none"},
    )

    roles = role_map["weeks"][0]["session_roles"]
    assert [role["scheduled_countdown_label"] for role in roles] == ["D-21", "D-20"]
    assert roles[1]["strength_composition_policy"]["adjacent_strength_recovery"] == {
        "consecutive": True,
        "previous_d_day": 21,
        "current_d_day": 20,
        "shared_mechanical_tags": ["mech_grip_support", "mech_trunk_stability"],
        "substantial_overlap_tags": [],
        "previous_material_items": [
            "Kettlebell Swing",
            "Trap Bar Carry (Frame Neutral)",
        ],
        "current_material_items": [],
        "current_verified_low_cost_items": [
            "Farmer Walk Hold (Static)",
            "Single-Leg Spanish Squat Hold",
        ],
        "decision": "compatible",
    }

    persisted_brief = json.loads(
        json.dumps(
            {
                "athlete_model": {},
                "weekly_role_map": role_map,
                "candidate_pools": {"GPP": {"strength_slots": slots}},
            }
        )
    )
    packet = build_stage2_finalizer_packet(
        stage2_payload={"render_mode": "camp_plan"},
        planning_brief=persisted_brief,
    )
    rendered_roles = packet["selected_plan"]["weekly_role_map"]["weeks"][0][
        "session_roles"
    ]
    assert [role["scheduled_countdown_label"] for role in rendered_roles] == [
        "D-21",
        "D-20",
    ]
    assert [item["name"] for item in rendered_roles[1]["selected_exercise_assignments"]] == [
        "Farmer Walk Hold (Static)",
        "DB Alternating Incline Press (30-45°)",
        "Single-Leg Spanish Squat Hold",
    ]
    packet["render_mode"] = "camp_plan"
    manifest = _closed_membership_render_manifest(packet)
    d20 = next(item for item in manifest if item["scheduled_countdown_label"] == "D-20")
    assert d20["unresolved"] == []
    assert d20["exercise_lines"] == [
        "- Farmer Walk Hold (Static): 3-5 x 10-20 sec @ 7-9/10 effort",
        "- DB Alternating Incline Press (30-45°): 2-3 x 6-10 @ RPE 6-7",
        "- Single-Leg Spanish Squat Hold: 3-5 x 10-20 sec @ 7-9/10 effort",
    ]


def test_substantial_repeated_loading_is_removed_but_different_low_cost_work_remains():
    grip_trunk = ["mech_grip_support", "mech_trunk_stability"]
    slots = [
        _slot("Heavy Carry A", 1, 1, tags=grip_trunk, low_cost=False),
        _slot("Heavy Carry B", 2, 1, tags=grip_trunk, low_cost=False),
        _slot("Low-Cost Knee Hold", 2, 2, tags=["mech_lower_squat"], low_cost=True),
    ]
    role_map = _role_map()
    _compose(role_map, slots)

    second = role_map["weeks"][0]["session_roles"][1]
    assert [item["name"] for item in second["selected_exercise_assignments"]] == [
        "Low-Cost Knee Hold"
    ]
    policy = second["strength_composition_policy"]
    assert policy["adjacent_strength_recovery"]["decision"] == "selection_modified"
    assert policy["adjacent_strength_recovery"]["substantial_overlap_tags"] == grip_trunk
    assert {item["name"]: item["reason"] for item in policy["dropped"]}[
        "Heavy Carry B"
    ] == "substantial_repeated_mechanical_loading"


def test_low_cost_maintenance_overlap_is_not_treated_as_substantial_loading():
    grip = ["mech_grip_support"]
    slots = [
        _slot("Heavy Carry", 1, 1, tags=grip, low_cost=False),
        _slot("Grip Maintenance Hold", 2, 1, tags=grip, low_cost=True),
    ]
    role_map = _role_map()
    _compose(role_map, slots)

    second = role_map["weeks"][0]["session_roles"][1]
    assert [item["name"] for item in second["selected_exercise_assignments"]] == [
        "Grip Maintenance Hold"
    ]
    assert second["strength_composition_policy"]["adjacent_strength_recovery"][
        "decision"
    ] == "compatible"


def test_injury_recovery_pressure_still_tightens_composition():
    slots = [
        _slot("Upper Pull", 1, 1, tags=["mech_upper_pull"], low_cost=True),
        _slot("Upper Press", 2, 1, tags=["mech_upper_press"], low_cost=True),
        _slot("Knee Hold", 2, 2, tags=["mech_lower_squat"], low_cost=True),
        _slot("Trunk Hold", 2, 3, tags=["mech_trunk_stability"], low_cost=True),
    ]
    role_map = _role_map()
    _compose(
        role_map,
        slots,
        athlete={
            "fatigue": "low",
            "cut_severity_bucket": "none",
            "injuries": ["shoulder strain"],
        },
    )

    second = role_map["weeks"][0]["session_roles"][1]
    assert second["strength_composition_policy"]["injury_restricted"] is True
    assert second["strength_composition_policy"]["effective_exercise_cap"] == 2
    assert len(second["selected_exercise_assignments"]) == 2


def test_session_moves_when_no_compatible_closed_membership_workload_exists():
    grip_trunk = ["mech_grip_support", "mech_trunk_stability"]
    slots = [
        _slot("Heavy Carry A", 1, 1, tags=grip_trunk, low_cost=False),
        _slot("Heavy Carry B", 2, 1, tags=grip_trunk, low_cost=False),
    ]
    role_map = _role_map()
    _compose(role_map, slots)

    second = role_map["weeks"][0]["session_roles"][1]
    assert second["scheduled_countdown_label"] == "D-19"
    assert second["scheduled_day_hint"] == "Wednesday"
    recovery = second["strength_composition_policy"]["adjacent_strength_recovery"]
    assert recovery["decision"] == "relocated"
    assert recovery["relocated_to_d_day"] == 19
    assert second["calendar_integrity_relocation"]["reason_code"] == (
        "substantial_repeated_mechanical_loading"
    )
