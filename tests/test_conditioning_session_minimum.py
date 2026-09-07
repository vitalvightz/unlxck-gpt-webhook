import pytest

from fightcamp.session_composition import compose_normal_conditioning_assignments
from fightcamp.stage2_validator import _conditioning_assignment_warnings


def _option(name: str, *, duration: float, rpe: int = 5, intensity: str = "moderate") -> dict:
    return {
        "name": name,
        "prescription": f"{duration:g} min",
        "selection_metadata": {
            "name": name,
            "system": "aerobic",
            "total_minutes": duration,
            "rpe": rpe,
            "intensity": intensity,
        },
    }


def _pool(*options: dict) -> dict:
    selected, *alternates = options
    return {"SPP": {"conditioning_slots": [{
        "slot_id": "spp-aerobic-1", "role": "aerobic", "selected": selected, "alternates": alternates,
    }]}}


def _role_map(*, day: str = "wednesday", hard_days: list[str] | None = None) -> dict:
    return {"weeks": [{
        "phase": "SPP", "effective_hard_sparring_days": hard_days or [],
        "session_roles": [{
            "category": "conditioning", "role_key": "aerobic_support_day",
            "preferred_system": "aerobic", "scheduled_day_hint": day,
        }],
    }]}


def _conditioner(role_map: dict) -> dict:
    return role_map["weeks"][0]["session_roles"][0]


def test_conditioning_session_selects_three_suitable_bank_exercises():
    role_map = _role_map()
    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=_pool(
        _option("Tempo Flow", duration=12), _option("Bike Rhythm", duration=10),
        _option("Shadow Aerobic", duration=8),
    ))

    role = _conditioner(role_map)
    assert [item["name"] for item in role["selected_exercise_assignments"]] == [
        "Tempo Flow", "Bike Rhythm", "Shadow Aerobic",
    ]
    assert role["conditioning_composition_policy"]["minimum_exercise_count"] == 3
    assert [item["effective_prescription"] for item in role["selected_exercise_assignments"]] == [
        "12 min", "10 min", "8 min",
    ]


def test_long_aerobic_session_uses_two_exercise_minimum():
    role_map = _role_map()
    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=_pool(
        _option("Long Aerobic Base", duration=25),
        _option("Breathing Flush", duration=8, rpe=3, intensity="low"),
        _option("Extra Tempo", duration=8),
    ))

    role = _conditioner(role_map)
    assert len(role["selected_exercise_assignments"]) == 2
    assert role["conditioning_composition_policy"]["long_aerobic_session"] is True
    assert role["conditioning_composition_policy"]["minimum_exercise_count"] == 2


@pytest.mark.parametrize("hard_day", ["tuesday", "thursday"])
def test_hard_sparring_adjacency_removes_conditioning_minimum(hard_day):
    role_map = _role_map(day="wednesday", hard_days=[hard_day])
    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=_pool(
        _option("Tempo Flow", duration=12), _option("Bike Rhythm", duration=10),
        _option("Shadow Aerobic", duration=8),
    ))

    role = _conditioner(role_map)
    assert len(role["selected_exercise_assignments"]) == 1
    assert role["conditioning_composition_policy"]["minimum_exercise_count"] is None
    assert role["conditioning_composition_policy"]["hard_sparring_adjacent"] is True


def test_conditioning_minimum_does_not_stack_unsuitable_high_load_options():
    role_map = _role_map()
    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=_pool(
        _option("Hard Primary", duration=10, rpe=9, intensity="high"),
        _option("Hard Repeat", duration=10, rpe=9, intensity="high"),
        _option("Max Repeat", duration=10, rpe=10, intensity="max"),
    ))

    role = _conditioner(role_map)
    assert [item["name"] for item in role["selected_exercise_assignments"]] == ["Hard Primary"]
    assert role["conditioning_composition_policy"]["workload_limited"] is True


def test_validator_blocks_omitted_selected_conditioning_exercises():
    brief = {
        "weekly_role_map": {
            "weeks": [{
                "calendar_days": [{"weekday": "wednesday", "d_day": 20}],
                "session_roles": [{
                    "category": "conditioning",
                    "role_key": "aerobic_support_day",
                    "scheduled_day_hint": "wednesday",
                    "selected_exercise_assignments": [
                        {"name": "Tempo Flow"},
                        {"name": "Bike Rhythm"},
                        {"name": "Shadow Aerobic"},
                    ],
                }],
            }],
        },
    }
    rendered = "D-20 (Wednesday) — Aerobic support\n- Tempo Flow — 12 min"

    warnings = _conditioning_assignment_warnings(brief, rendered)

    assert warnings[0]["missing_exercises"] == ["Bike Rhythm", "Shadow Aerobic"]
