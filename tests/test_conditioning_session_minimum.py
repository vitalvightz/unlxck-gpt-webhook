import json
from pathlib import Path

import pytest

from fightcamp.session_composition import compose_normal_conditioning_assignments
from fightcamp.stage2_payload import build_stage2_handoff_text
from fightcamp.stage2_validator import validate_stage2_output


def _option(
    name: str,
    *,
    duration: float,
    rpe: int = 5,
    intensity: str = "moderate",
    work_sec: int | None = None,
    rest_sec: int | None = None,
    rounds: int | None = None,
) -> dict:
    return {
        "name": name,
        "selection_metadata": {
            "name": name,
            "system": "aerobic",
            "total_minutes": duration,
            "rpe": rpe,
            "intensity": intensity,
            "work_sec": work_sec,
            "rest_sec": rest_sec,
            "rounds": rounds,
        },
    }


def _pool(*options: dict) -> dict:
    """One Stage 1 slot per option.

    Session membership is one member per slot. A slot's ``alternates`` are its
    same-role substitution reservoir and are never session members, so a
    multi-exercise session must come from multiple selected slots.
    """
    return {
        "SPP": {
            "conditioning_slots": [
                {
                    "slot_id": f"spp-aerobic-{index}",
                    "role": "aerobic",
                    "selected": option,
                    "alternates": [],
                }
                for index, option in enumerate(options, start=1)
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


def test_conditioning_session_grows_across_slots_until_the_phase_workload_is_met():
    """Short exposures keep stacking; the session closes on workload, not count."""
    role_map = _role_map()
    pools = _pool(
        _option("Tempo Flow", duration=3),
        _option("Bike Rhythm", duration=3),
        _option("Shadow Aerobic", duration=3),
    )

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assert [item["name"] for item in role["selected_exercise_assignments"]] == [
        "Tempo Flow",
        "Bike Rhythm",
        "Shadow Aerobic",
    ]
    policy = role["conditioning_composition_policy"]
    assert policy["minimum_exercise_count"] == 3
    assert policy["workload_limited"] is False


def test_session_alternates_are_never_session_members():
    """A slot's substitution reservoir must not become a fake circuit.

    This is the D-18 regression: one selected drill plus its two same-role
    backups was rendered as a three-exercise session.
    """
    role_map = _role_map()
    pools = {
        "SPP": {
            "conditioning_slots": [
                {
                    "slot_id": "spp-aerobic-1",
                    "role": "aerobic",
                    "selected": _option("Selected Flow", duration=3),
                    "alternates": [
                        _option("Backup One", duration=3),
                        _option("Backup Two", duration=3),
                    ],
                }
            ]
        }
    }

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assert [item["name"] for item in role["selected_exercise_assignments"]] == ["Selected Flow"]


def test_one_long_aerobic_exposure_completes_the_session_on_its_own():
    """No count floor is forced once a single exposure carries the workload."""
    role_map = _role_map()
    pools = _pool(
        _option("Long Aerobic Base", duration=25),
        _option("Breathing Flush", duration=8, rpe=3, intensity="low"),
        _option("Extra Tempo", duration=8),
    )

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assert [item["name"] for item in role["selected_exercise_assignments"]] == [
        "Long Aerobic Base"
    ]
    policy = role["conditioning_composition_policy"]
    assert policy["minimum_exercise_count"] == 1
    assert policy["workload_limited"] is False


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


def test_conditioning_minimum_partitions_high_load_options_without_stacking_full_workouts():
    role_map = _role_map()
    pools = _pool(
        _option("Hard Primary", duration=8, rpe=9, intensity="high", work_sec=30, rest_sec=60, rounds=6),
        _option("Hard Repeat", duration=8, rpe=9, intensity="high", work_sec=30, rest_sec=60, rounds=6),
        _option("Max Repeat", duration=8, rpe=10, intensity="max", work_sec=30, rest_sec=60, rounds=4),
    )

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assignments = role["selected_exercise_assignments"]
    assert [item["name"] for item in assignments] == ["Hard Primary", "Hard Repeat", "Max Repeat"]
    assert [item["effective_rounds"] for item in assignments] == [6, 6, 4]
    envelope = role["conditioning_composition_policy"]["high_load_workload_envelope"]
    assert envelope["target_active_work_seconds"] == 480
    assert envelope["allocated_active_work_seconds"] == 480
    assert envelope["allocated_elapsed_seconds"] <= envelope["elapsed_cap_seconds"]
    assert role["conditioning_composition_policy"]["workload_limited"] is False


def test_real_bank_mixed_conditioning_doses_keep_their_own_modality_and_rest():
    bank = {
        item["name"]: item
        for item in json.loads(Path("data/conditioning_bank.json").read_text(encoding="utf-8"))
    }

    def bank_option(name: str) -> dict:
        item = bank[name]
        return {
            "name": name,
            "prescription": item["duration"],
            "selection_metadata": dict(item),
        }

    plyo = bank_option("Plyo Step-Up Jumps")
    swings = bank_option("KB Swing Intervals")
    broad_jumps = bank_option("Burpee Broad Jumps")
    role_map = {
        "weeks": [{
            "phase": "GPP",
            "session_roles": [{
                "category": "conditioning",
                "role_key": "glycolytic_capacity_day",
                "preferred_system": "glycolytic",
                "scheduled_day_hint": "wednesday",
                "scheduled_countdown_label": "D-28",
            }],
            "calendar_days": [{"weekday": "wednesday", "d_day": 28}],
        }]
    }
    pools = {"GPP": {"conditioning_slots": [
        {"slot_id": "gpp-glycolytic-1", "role": "glycolytic", "selected": plyo, "alternates": []},
        {"slot_id": "gpp-glycolytic-2", "role": "glycolytic", "selected": swings, "alternates": []},
        {"slot_id": "gpp-glycolytic-3", "role": "glycolytic", "selected": broad_jumps, "alternates": []},
    ]}}

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    assignments = role_map["weeks"][0]["session_roles"][0]["selected_exercise_assignments"]
    effective = {item["name"]: item["effective_prescription"] for item in assignments}
    assert effective == {
        "Plyo Step-Up Jumps": "6x8/side, 90s rest",
        "KB Swing Intervals": "6 x 30 sec work; 90 sec rest; RPE 8",
        "Burpee Broad Jumps": "4 x 30 sec work; 150 sec rest; RPE 8",
    }
    brief = {
        "athlete_snapshot": {"days_until_fight": 28, "sport": "boxing"},
        "weekly_role_map": role_map,
    }
    handoff = build_stage2_handoff_text(
        stage2_payload={"athlete_model": brief["athlete_snapshot"]},
        planning_brief=brief,
        plan_text="D-28 (Wednesday) - Conditioning",
    )
    for name, prescription in effective.items():
        assert f"- {name}: {prescription}" in handoff

    rendered = "D-28 (Wednesday) - Conditioning\n" + "\n".join(
        f"- {name}: {prescription}" for name, prescription in effective.items()
    )
    report = validate_stage2_output(planning_brief=brief, final_plan_text=rendered)
    assert not any(
        item["code"] == "selected_conditioning_effective_prescription_mismatch"
        for item in report["errors"]
    )


def test_conditioning_minimum_underfills_when_high_load_dose_is_unknown():
    role_map = _role_map()
    pools = _pool(
        _option("Hard Primary", duration=3, rpe=9, intensity="high"),
        _option("Hard Repeat", duration=3, rpe=9, intensity="high"),
        _option("Max Repeat", duration=3, rpe=10, intensity="max"),
    )

    compose_normal_conditioning_assignments(weekly_role_map=role_map, candidate_pools=pools)

    role = _conditioner(role_map)
    assert role["selected_exercise_assignments"] == []
    assert role["conditioning_composition_policy"]["underfill_reason"] == "high_load_dose_unknown"
    assert role["conditioning_composition_policy"]["workload_limited"] is True


# ---------------------------------------------------------------------------
# Athlete round duration owns round-based work
# ---------------------------------------------------------------------------


def _round_option(name: str, *, work_sec: int, rounds: int, round_based: bool) -> dict:
    return {
        "name": name,
        "prescription": f"{rounds}x{work_sec // 60}min",
        "selection_metadata": {
            "name": name,
            "system": "glycolytic",
            "work_sec": work_sec,
            "rest_sec": 60,
            "rounds": rounds,
            "rpe": 7,
            "round_based": round_based,
        },
    }


def _glycolytic_role_map() -> dict:
    return {
        "weeks": [
            {
                "phase": "SPP",
                "session_roles": [
                    {
                        "category": "conditioning",
                        "role_key": "fight_pace_repeatability_day",
                        "preferred_system": "glycolytic",
                        "scheduled_day_hint": "wednesday",
                    }
                ],
            }
        ]
    }


def _compose_with_athlete(role_map, pools, athlete):
    from fightcamp.planner_context import planner_athlete_model_context

    token = planner_athlete_model_context.set(athlete)
    try:
        compose_normal_conditioning_assignments(
            weekly_role_map=role_map, candidate_pools=pools
        )
    finally:
        planner_athlete_model_context.reset(token)


@pytest.mark.parametrize(
    "rounds_format,expected",
    [
        ("3 x 3", "5 x 3 min round; 60 sec rest; RPE 7"),
        ("5 x 5", "5 x 5 min round; 60 sec rest; RPE 7"),
        ("3 x 2", "5 x 2 min round; 60 sec rest; RPE 7"),
    ],
)
def test_round_based_work_uses_the_athlete_round_duration(rounds_format, expected):
    """The athlete's own "Rounds x Minutes" owns round length — never a fixed 3 min.

    Round count, rest and RPE stay with the bank entry.
    """
    role_map = _glycolytic_role_map()
    pools = {
        "SPP": {
            "conditioning_slots": [
                {
                    "slot_id": "spp-glyc-1",
                    "role": "glycolytic",
                    "selected": _round_option(
                        "Pad Rounds", work_sec=300, rounds=5, round_based=True
                    ),
                    "alternates": [],
                }
            ]
        }
    }
    _compose_with_athlete(role_map, pools, {"rounds_format": rounds_format})

    assignments = _conditioner(role_map)["selected_exercise_assignments"]
    assert [item["effective_prescription"] for item in assignments] == [expected]


def test_non_round_based_work_keeps_its_authored_bank_dose():
    """A threshold block or interval drill is not a fight round: bank dose stands."""
    role_map = _glycolytic_role_map()
    pools = {
        "SPP": {
            "conditioning_slots": [
                {
                    "slot_id": "spp-glyc-1",
                    "role": "glycolytic",
                    "selected": _round_option(
                        "Bike Threshold Block", work_sec=480, rounds=2, round_based=False
                    ),
                    "alternates": [],
                }
            ]
        }
    }
    _compose_with_athlete(role_map, pools, {"rounds_format": "3 x 3"})

    assignments = _conditioner(role_map)["selected_exercise_assignments"]
    assert [item["effective_prescription"] for item in assignments] == ["2x8min"]


def test_round_based_work_without_an_athlete_format_keeps_the_bank_dose():
    role_map = _glycolytic_role_map()
    pools = {
        "SPP": {
            "conditioning_slots": [
                {
                    "slot_id": "spp-glyc-1",
                    "role": "glycolytic",
                    "selected": _round_option(
                        "Pad Rounds", work_sec=300, rounds=5, round_based=True
                    ),
                    "alternates": [],
                }
            ]
        }
    }
    _compose_with_athlete(role_map, pools, {"rounds_format": "not a format"})

    assignments = _conditioner(role_map)["selected_exercise_assignments"]
    assert [item["effective_prescription"] for item in assignments] == ["5x5min"]
