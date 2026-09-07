import pytest

from fightcamp.session_composition import compose_normal_conditioning_assignments


def _option(name: str, *, duration: float, rpe: int = 5, intensity: str = "moderate") -> dict:
    return {
        "name": name,
        "selection_metadata": {
            "total_minutes": duration,
            "rpe": rpe,
            "intensity": intensity,
        },
    }


def _role_map(*, day: str = "wednesday", hard_days: list[str] | None = None) -> dict:
    return {
        "weeks": [{
            "phase": "SPP",
            "effective_hard_sparring_days": hard_days or [],
            "session_roles": [{
                "category": "conditioning",
                "role_key": "aerobic_support_day",
                "preferred_system": "aerobic",
                "scheduled_day_hint": day,
            }],
        }],
    }


def _pools(*options: dict) -> dict:
    selected, *alternates = options
    return {"SPP": {"conditioning_slots": [{
        "slot_id": "spp-aerobic-1",
        "role": "aerobic",
        "selected": selected,
        "alternates": alternates,
    }]}}


def _role(role_map: dict) -> dict:
    return role_map["weeks"][0]["session_roles"][0]


def test_conditioning_session_uses_three_suitable_bank_exercises() -> None:
    role_map = _role_map()
    compose_normal_conditioning_assignments(
        weekly_role_map=role_map,
        candidate_pools=_pools(
            _option("Tempo Flow", duration=12),
            _option("Bike Rhythm", duration=10),
            _option("Shadow Aerobic", duration=8),
        ),
    )

    assert [item["name"] for item in _role(role_map)["selected_exercise_assignments"]] == [
        "Tempo Flow", "Bike Rhythm", "Shadow Aerobic",
    ]


def test_long_aerobic_session_uses_two_exercise_minimum() -> None:
    role_map = _role_map()
    compose_normal_conditioning_assignments(
        weekly_role_map=role_map,
        candidate_pools=_pools(
            _option("Long Aerobic Base", duration=25),
            _option("Breathing Flush", duration=8, rpe=3, intensity="low"),
            _option("Extra Tempo", duration=8),
        ),
    )

    assert len(_role(role_map)["selected_exercise_assignments"]) == 2


@pytest.mark.parametrize("hard_day", ["tuesday", "thursday"])
def test_hard_sparring_adjacency_allows_reduced_conditioning_workload(hard_day: str) -> None:
    role_map = _role_map(hard_days=[hard_day])
    compose_normal_conditioning_assignments(
        weekly_role_map=role_map,
        candidate_pools=_pools(
            _option("Tempo Flow", duration=12),
            _option("Bike Rhythm", duration=10),
            _option("Shadow Aerobic", duration=8),
        ),
    )

    assert len(_role(role_map)["selected_exercise_assignments"]) == 1


def test_conditioning_minimum_does_not_stack_high_load_options() -> None:
    role_map = _role_map()
    compose_normal_conditioning_assignments(
        weekly_role_map=role_map,
        candidate_pools=_pools(
            _option("Hard Primary", duration=10, rpe=9, intensity="high"),
            _option("Hard Repeat", duration=10, rpe=9, intensity="high"),
            _option("Max Repeat", duration=10, rpe=10, intensity="max"),
        ),
    )

    assert [item["name"] for item in _role(role_map)["selected_exercise_assignments"]] == ["Hard Primary"]
