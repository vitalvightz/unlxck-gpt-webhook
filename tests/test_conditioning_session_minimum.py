import pytest

from fightcamp.session_composition import compose_normal_conditioning_assignments


def _option(name: str, *, duration: float, rpe: int = 5, intensity: str = "moderate") -> dict:
    return {
        "name": name,
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
    return {
        "SPP": {
            "conditioning_slots": [
                {
                    "slot_id": "spp-aerobic-1",
                    "role": "aerobic",
                    "selected": selected,
                    "alternates": alternates,
                }
            ]
        }
    }


def _role_map(*, day: str = "wednesday", hard_days: list[str] | None = None) -> dict:
    return {
        "weeks": [
            {
                "phase": "SPP",
                "effective_hard_sparring_days": hard_days or [],
                "session_roles": [
                    {
                        "category": "conditioning",
                        "role_key": "aerobic_support_day",
                        "preferred_system": "aerobic",
                        "scheduled_day_hint": day,
                    }
                ],
            }
        ]
    }


def _conditioner(role_map: dict) -> dict:
    return role_map["weeks"][0]["session_roles"][0]


def test_conditioning_session_selects_three_suitable_bank_exercises():
    role_map = _role_map()
    pools = _pool(
        _option("Tempo Flow", duration=12),
        _option("Bike Rhythm", duration=10),
        _option("Shadow Aerobic", duration=8),
    )

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assert [item["name"] for item in role["selected_exercise_assignments"]] == [
        "Tempo Flow",
        "Bike Rhythm",
        "Shadow Aerobic",
    ]
    assert role["conditioning_composition_policy"]["minimum_exercise_count"] == 3


def test_long_aerobic_session_uses_two_exercise_minimum():
    role_map = _role_map()
    pools = _pool(
        _option("Long Aerobic Base", duration=25),
        _option("Breathing Flush", duration=8, rpe=3, intensity="low"),
        _option("Extra Tempo", duration=8),
    )

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assert len(role["selected_exercise_assignments"]) == 2
    assert role["conditioning_composition_policy"]["long_aerobic_session"] is True
    assert role["conditioning_composition_policy"]["minimum_exercise_count"] == 2


@pytest.mark.parametrize("hard_day", ["tuesday", "thursday"])
def test_hard_sparring_adjacency_removes_conditioning_minimum(hard_day):
    role_map = _role_map(day="wednesday", hard_days=[hard_day])
    pools = _pool(
        _option("Tempo Flow", duration=12),
        _option("Bike Rhythm", duration=10),
        _option("Shadow Aerobic", duration=8),
    )

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assert len(role["selected_exercise_assignments"]) == 1
    assert role["conditioning_composition_policy"]["minimum_exercise_count"] is None
    assert role["conditioning_composition_policy"]["hard_sparring_adjacent"] is True


def test_conditioning_minimum_does_not_stack_unsuitable_high_load_options():
    role_map = _role_map()
    pools = _pool(
        _option("Hard Primary", duration=10, rpe=9, intensity="high"),
        _option("Hard Repeat", duration=10, rpe=9, intensity="high"),
        _option("Max Repeat", duration=10, rpe=10, intensity="max"),
    )

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assert [item["name"] for item in role["selected_exercise_assignments"]] == ["Hard Primary"]
    assert role["conditioning_composition_policy"]["workload_limited"] is True
